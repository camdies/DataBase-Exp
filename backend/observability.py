"""标准 logging + SQLAlchemy events；不记录口令、令牌、请求体或 SQL 参数。"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from flask import g, has_request_context, request
from sqlalchemy import event


class AccessHandler(RotatingFileHandler):
    def handleError(self, record):
        # 不让 logging 默认的静默错误掩盖磁盘写入失败。
        raise OSError('访问日志写入失败')


def attach_sql_metrics(engine):
    if getattr(engine, '_course_metrics_attached', False):
        return
    engine._course_metrics_attached = True

    @event.listens_for(engine, 'before_cursor_execute')
    def before(conn, cursor, statement, parameters, context, executemany):
        context._course_started = time.perf_counter()

    def finish(context, failed=False):
        start = getattr(context, '_course_started', None)
        if start is not None and has_request_context():
            g.sql_count = g.get('sql_count', 0) + 1
            g.sql_ms = g.get('sql_ms', 0.0) + (time.perf_counter() - start) * 1000
            g.sql_errors = g.get('sql_errors', 0) + int(failed)
            context._course_started = None

    @event.listens_for(engine, 'after_cursor_execute')
    def after(conn, cursor, statement, parameters, context, executemany):
        finish(context)

    @event.listens_for(engine, 'handle_error')
    def failed(context):
        finish(context.execution_context, True)


def configure(app, engine, log_dir=None):
    attach_sql_metrics(engine)
    directory = Path(log_dir or os.getenv('ACCESS_LOG_DIR', 'runtime_logs')).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # 每进程独立轮转，避免 Gunicorn 多 worker 同时 rename 同一文件。
    handler = AccessHandler(directory / f'access-{os.getpid()}.jsonl',
                            maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.Logger(f'course.access.{id(app)}', level=logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    app.extensions['access_log'] = logger
    app.extensions['access_log_handler'] = handler

    @app.before_request
    def start():
        g.request_id = uuid4().hex
        g.started = time.perf_counter()
        g.sql_count, g.sql_ms, g.sql_errors = 0, 0.0, 0

    @app.after_request
    def finish(response):
        elapsed = (time.perf_counter() - g.started) * 1000
        response.headers['X-Request-ID'] = g.request_id
        response.headers['Server-Timing'] = f'app;dur={elapsed:.3f}, sql;dur={g.sql_ms:.3f}'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if not request.path.startswith('/api/'):
            return response
        response.headers['Cache-Control'] = 'no-store'
        actor = g.get('actor', {})
        ua = request.user_agent.string[:512]
        client = request.headers.get('X-Client-ID', '')
        run = request.headers.get('X-Benchmark-ID', '')
        entry = {
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'request_id': g.request_id, 'pid': os.getpid(),
            'method': request.method,
            'route': request.url_rule.rule if request.url_rule else '<unmatched>',
            'remote_ip': request.remote_addr,
            'client_id': client if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', client) else None,
            'benchmark_id': run if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', run) else None,
            'client_os': 'Windows' if 'Windows' in ua else 'Linux' if 'Linux' in ua else 'Other',
            'user_id': actor.get('id'), 'username': actor.get('username'), 'role': actor.get('role'),
            'status': response.status_code, 'response_bytes': response.calculate_content_length(),
            'duration_ms': round(elapsed, 3), 'sql_count': g.sql_count,
            'sql_ms': round(g.sql_ms, 3), 'sql_errors': g.sql_errors,
        }
        try:
            logger.info(json.dumps(entry, ensure_ascii=False, separators=(',', ':')))
        except OSError:
            # 写事务可能已提交，不能将响应篡改为失败而诱发重复写入。
            # 明确告警，供运维检查磁盘；不是审计数据库事务。
            app.logger.critical('access_log_write_failed request_id=%s', g.request_id)
            response.headers['X-Access-Log-Status'] = 'failed'
        return response
