import logging
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from flask import Flask, Blueprint, request, g, jsonify, send_from_directory
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as PoolTimeout
import bcrypt
from .models import account
from .security import require_auth, require_role, issue_token
from .controllers import InventoryController
from .validation import Problem, integer, string
from .observability import configure


class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat() + 'Z'
        return DefaultJSONProvider.default(value)


def create_app(engine=None, secret=None, log_dir=None):
    secret = secret or os.getenv('JWT_SECRET', '')
    if len(secret) < 32 or len(set(secret)) < 12:
        raise RuntimeError('JWT_SECRET 必须为至少 32 字符的随机密钥')
    app = Flask(__name__, static_folder=None)
    app.json = JSONProvider(app)
    app.config.update(SECRET_KEY=secret, MAX_CONTENT_LENGTH=64*1024)
    if engine is None:
        url = os.getenv('DATABASE_URL', '')
        if not url.startswith('mysql+pymysql://'):
            raise RuntimeError('DATABASE_URL 必须配置为 mysql+pymysql://...')
        engine = create_engine(url, pool_pre_ping=True, pool_size=8, max_overflow=4, pool_timeout=10,
                               isolation_level='READ COMMITTED', connect_args={'connect_timeout': 5})
    app.extensions['db'] = engine
    configure(app, engine, log_dir)
    controller = InventoryController(engine)
    api = Blueprint('api', __name__, url_prefix='/api')

    def ok(data=None, status=200):
        return jsonify(success=True, data=data, message='操作成功'), status

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise Problem(422, 'INVALID_INPUT', '请求体必须为 JSON 对象')
        return data

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, Problem):
            status, code, message = exc.status, exc.code, exc.message
        elif isinstance(exc, IntegrityError):
            status, code, message = 409, 'DATA_CONFLICT', '数据冲突：重复编号、重复请求或关联记录限制'
        elif isinstance(exc, OperationalError):
            number = getattr(exc.orig, 'args', [None])[0]
            status, code, message = ((409, 'RETRY_TRANSACTION', '事务发生锁冲突，请刷新后重试') if number in (1205,1213)
                                      else (503, 'DATABASE_UNAVAILABLE', '数据库暂时不可用'))
        elif isinstance(exc, PoolTimeout):
            status, code, message = 503, 'DATABASE_BUSY', '数据库连接繁忙，请稍后重试'
        elif isinstance(exc, HTTPException):
            status, code, message = exc.code, 'HTTP_ERROR', exc.description
        else:
            app.logger.error('request=%s unexpected error type=%s', g.get('request_id'), type(exc).__name__)
            status, code, message = 500, 'INTERNAL_ERROR', '服务异常，请携带请求编号联系管理员'
        return jsonify(success=False, data=None, code=code, message=message, request_id=g.get('request_id')), status

    @api.post('/login')
    def login():
        data = body()
        username = string(data.get('username'), '用户名', 40)
        password = data.get('password')
        if not isinstance(password, str) or not 1 <= len(password.encode()) <= 72:
            raise Problem(422, 'INVALID_INPUT', '密码需要 1–72 字节')
        with engine.connect() as c:
            user = c.execute(select(account).where(account.c.username == username)).mappings().first()
        if not user or not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
            raise Problem(401, 'LOGIN_FAILED', '用户名或密码错误')
        g.actor = dict(user)
        return ok({'token': issue_token(user), 'username': user['username'], 'role': user['role']})

    @api.get('/references')
    @require_auth
    @require_role('admin', 'clerk')
    def references():
        return ok(controller.references(g.actor, request.args.get('keyword', '')[:80]))

    @api.get('/products')
    @require_auth
    @require_role('admin', 'clerk')
    def products():
        return ok(controller.products(g.actor, request.args.get('keyword', '')[:80], integer(request.args.get('page', '1'), '页码', maximum=100000)))

    @api.post('/products')
    @require_auth
    @require_role('admin')
    def create_product():
        return ok(controller.save_product(g.actor, body()), 201)

    @api.put('/products/<int:pid>')
    @require_auth
    @require_role('admin')
    def edit_product(pid):
        return ok(controller.save_product(g.actor, body(), pid))

    @api.delete('/products/<int:pid>')
    @require_auth
    @require_role('admin')
    def delete_product(pid):
        return ok(controller.delete_product(g.actor, pid))

    @api.post('/stock/restock')
    @require_auth
    @require_role('admin')
    def restock():
        return ok(controller.restock(g.actor, body()))

    @api.get('/orders')
    @require_auth
    @require_role('admin', 'clerk')
    def orders():
        cid = request.args.get('customer_id')
        return ok(controller.orders(g.actor, integer(request.args.get('page', '1'), '页码', maximum=100000), integer(cid, '客户') if cid else None, request.args.get('status') or None, request.args.get('keyword', '')[:80]))

    @api.get('/inventory/summary')
    @require_auth
    @require_role('admin', 'clerk')
    def inventory_summary():
        return ok(controller.inventory_summary(g.actor))

    @api.get('/overview')
    @require_auth
    @require_role('admin', 'clerk')
    def overview():
        return ok(controller.overview(g.actor, integer(request.args.get('days', '30'), '趋势天数', maximum=90)))

    @api.get('/search')
    @require_auth
    @require_role('admin', 'clerk')
    def search():
        return ok(controller.search(g.actor, request.args.get('keyword', '')))

    @api.post('/orders')
    @require_auth
    @require_role('admin', 'clerk')
    def create_order():
        return ok(controller.create_order(g.actor, body()), 201)

    @api.get('/orders/<int:oid>')
    @require_auth
    @require_role('admin', 'clerk')
    def detail(oid):
        return ok(controller.detail(g.actor, oid))

    @api.post('/orders/<int:oid>/ship')
    @require_auth
    @require_role('admin', 'clerk')
    def ship(oid):
        return ok(controller.transition(g.actor, oid, 'ship', body()))

    @api.post('/orders/<int:oid>/cancel')
    @require_auth
    @require_role('admin', 'clerk')
    def cancel(oid):
        return ok(controller.transition(g.actor, oid, 'cancel', {}))

    @api.get('/model')
    @require_auth
    @require_role('admin', 'clerk')
    def model_metadata():
        from .model_export import model
        return ok(model())

    @api.post('/model/validate')
    @require_auth
    @require_role('admin', 'clerk')
    def model_validate():
        from .model_export import validate
        return ok(validate())

    @api.post('/model/generate')
    @require_auth
    @require_role('admin')
    def model_generate():
        from .model_export import generate
        return ok(generate())

    app.register_blueprint(api)
    dist = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'

    @app.get('/')
    def index():
        return send_from_directory(dist, 'index.html')

    @app.get('/assets/<path:filename>')
    def assets(filename):
        return send_from_directory(dist / 'assets', filename)

    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    create_app().run(host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '5001')), debug=False)
