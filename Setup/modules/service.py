"""Owned processes only. Stop requests use private per-instance files, not an HTTP API."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from . import configuration as cfg


def record():
    return cfg.read_json(cfg.LOCAL / 'service-state.json')


def linux_identity(pid):
    # Kernel start ticks + boot ID survive wall-clock/NTP corrections on WSL.
    stat = Path(f'/proc/{pid}/stat').read_text()
    return {'start_ticks': stat.rsplit(')', 1)[1].split()[19],
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def process_record(pid):
    import psutil
    process = psutil.Process(pid)
    result = {'pid': pid, 'created': process.create_time(), 'exe': process.exe(),
              'cmdline': process.cmdline(), 'cwd': process.cwd()}
    if sys.platform.startswith('linux'):
        result.update(linux_identity(pid))
    return result


def owned_process(value):
    if not value:
        return None
    import psutil
    try:
        process = psutil.Process(value['pid'])
        same_start = (linux_identity(value['pid']) == {k: value[k] for k in ('start_ticks', 'boot_id')}
                      if sys.platform.startswith('linux') and 'start_ticks' in value
                      else abs(process.create_time() - value['created']) < 0.01)
        if (process.is_running() and process.status() != psutil.STATUS_ZOMBIE
                and same_start
                and os.path.normcase(process.exe()) == os.path.normcase(value['exe'])
                and process.cmdline() == value['cmdline']):
            return process
    except (psutil.NoSuchProcess, FileNotFoundError):
        return None
    except (psutil.AccessDenied, KeyError, TypeError, ValueError):
        raise cfg.SetupError('无法核验运行进程身份，拒绝启停；请检查状态文件或当前用户权限。') from None
    return None


def spawn(command, logfile, env=None):
    logfile = Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open('ab') as log:
        return subprocess.Popen(command, cwd=cfg.ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                start_new_session=os.name != 'nt')


def url(value):
    return f'http://127.0.0.1:{value["port"]}'


def verify_http(value):
    # Do not route a localhost readiness probe through a system HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url(value) + '/', timeout=2) as response:
        if response.status != 200 or response.headers.get('X-Course-Instance') != value['instance']:
            raise cfg.SetupError('HTTP 响应不是本次启动的课程服务。')


def stop_path(value):
    instance = value.get('instance', '')
    if len(instance) != 32 or any(c not in '0123456789abcdef' for c in instance):
        raise cfg.SetupError('运行实例标识无效。')
    return cfg.LOCAL / f'stop-{instance}'


def wait_stopped(value, timeout):
    deadline = time.monotonic() + timeout
    while owned_process(value):
        if time.monotonic() >= deadline:
            raise TimeoutError('Process is still running')
        time.sleep(0.1)


def start(open_browser=True):
    from . import database, environment
    old = record()
    if owned_process(old):
        verify_http(old)
        print('已运行：' + url(old))
        return old
    settings = cfg.settings()
    values = cfg.read_env()
    environment.check_assets()
    environment.check_log_dir(values)
    if not environment.port_free(settings['host'], settings['port']):
        raise cfg.SetupError('应用端口已被其他程序占用，请修改端口；不会自动结束其他程序。')
    if settings['database_mode'] == 'managed':
        database.ensure_managed()
    database.verify(values['DATABASE_URL'])
    if not environment.python_path().is_file():
        raise cfg.SetupError('缺少项目虚拟环境，请执行环境修复。')
    instance = secrets.token_hex(16)
    env = cfg.child_env(values)
    env['COURSE_INSTANCE'] = instance
    logfile = cfg.LOGS / f'service-{time.strftime("%Y%m%d-%H%M%S")}-{instance[:8]}.log'
    child = spawn([str(environment.python_path()), '-m', 'Setup.manager', '_serve'], logfile, env)
    try:
        value = process_record(child.pid) | {'instance': instance, 'port': settings['port'],
                                            'host': settings['host'], 'log': str(logfile)}
        cfg.save_json(cfg.LOCAL / 'service-state.json', value)
        for _ in range(80):
            if child.poll() is not None:
                raise cfg.SetupError('服务提前退出；请使用“查看日志”，日志：' + str(logfile))
            try:
                verify_http(value)
                break
            except (OSError, cfg.SetupError):
                time.sleep(0.25)
        else:
            raise cfg.SetupError('启动超时，已清理本次创建的 Web 进程。日志：' + str(logfile))
    except BaseException:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        (cfg.LOCAL / 'service-state.json').unlink(missing_ok=True)
        raise
    print('启动成功：' + url(value))
    if settings['host'] == '0.0.0.0':
        print('已监听局域网；其他电脑使用本机实际网卡 IP，防火墙需按客户端网段配置。')
    if open_browser and settings['open_browser']:
        webbrowser.open(url(value))
    return value


def stop(force=False, timeout=35):
    value = record()
    process = owned_process(value)
    if not process:
        (cfg.LOCAL / 'service-state.json').unlink(missing_ok=True)
        print('当前未运行。')
        return
    marker = stop_path(value)
    cfg.atomic_text(marker, value['instance'])
    import psutil
    try:
        wait_stopped(value, timeout)
    except TimeoutError:
        if not force:
            raise cfg.SetupError('正常停机尚未完成，服务正在排空请求；可稍后重试或显式执行 stop --force。') from None
        process = owned_process(value)
        if process:
            process.kill()
            process.wait(timeout=10)
    marker.unlink(missing_ok=True)
    (cfg.LOCAL / 'service-state.json').unlink(missing_ok=True)
    print('Web 服务已停止。')


class DrainMiddleware:
    def __init__(self, app, instance):
        self.app, self.instance = app, instance
        self.draining = False
        self.active = 0
        self.lock = threading.Lock()

    def __call__(self, environ, start_response):
        with self.lock:
            if self.draining:
                start_response('503 Service Unavailable', [('Content-Type', 'text/plain')])
                return [b'Server is stopping']
            self.active += 1
        def respond(status, headers, exc_info=None):
            return start_response(status, headers + [('X-Course-Instance', self.instance)], exc_info)
        def iterate():
            result = None
            try:
                result = self.app(environ, respond)
                yield from result
            finally:
                try:
                    if hasattr(result, 'close'):
                        result.close()
                finally:
                    with self.lock:
                        self.active -= 1
        return iterate()


def run_server(app, settings, instance):
    """Keep the IO loop alive while completing accepted requests and their output."""
    from waitress import create_server
    gate = DrainMiddleware(app, instance)
    server = create_server(gate, host=settings['host'], port=settings['port'], threads=settings['threads'],
                           channel_timeout=60, max_request_body_size=65536, clear_untrusted_proxy_headers=True)
    marker = stop_path({'instance': instance})
    try:
        while True:
            server.asyncore.loop(timeout=0.1, count=1, map=server._map)
            if marker.exists():
                with gate.lock:
                    gate.draining = True
                # Stop accepting new connections, but leave existing channels alive.
                if server.accepting:
                    server.accepting = False
                channels = list(server.active_channels.values())
                with gate.lock:
                    idle = gate.active == 0
                with server.task_dispatcher.lock:
                    idle = idle and not server.task_dispatcher.queue
                if idle and all(not ch.requests and ch.total_outbufs_len == 0 for ch in channels):
                    break
    finally:
        server.task_dispatcher.shutdown(timeout=30)
        for channel in list(server.active_channels.values()):
            channel.close()
        server.close()
        marker.unlink(missing_ok=True)


def serve():
    from backend.app import create_app
    instance = os.environ.get('COURSE_INSTANCE', '')
    stop_path({'instance': instance})
    app = create_app()
    try:
        run_server(app, cfg.settings(), instance)
    finally:
        app.extensions['db'].dispose()
        app.extensions['access_log_handler'].close()
