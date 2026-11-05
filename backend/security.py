"""共享 bcrypt 帮助函数与 JWT 鉴权，所有受保护路由显式声明角色。"""
import os
from functools import wraps
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from flask import request, current_app, g
from sqlalchemy import select
from .models import account
from .validation import Problem


def hash_password(password):
    if not isinstance(password, str) or not 10 <= len(password.encode('utf-8')) <= 72:
        raise ValueError('密码需要 10–72 字节')
    rounds = int(os.getenv('BCRYPT_ROUNDS', '12'))
    if not 12 <= rounds <= 16:
        raise ValueError('BCRYPT_ROUNDS 必须在 12–16 之间')
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def issue_token(user):
    return jwt.encode({'sub': str(user['id']), 'exp': datetime.now(timezone.utc) + timedelta(hours=4)},
                      current_app.config['SECRET_KEY'], algorithm='HS256')


def require_auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        try:
            if not header.startswith('Bearer '):
                raise ValueError()
            claims = jwt.decode(header[7:], current_app.config['SECRET_KEY'], algorithms=['HS256'],
                                options={'require': ['sub', 'exp']})
            uid = int(claims['sub'])
        except (jwt.InvalidTokenError, ValueError, TypeError):
            raise Problem(401, 'UNAUTHENTICATED', '请登录或重新登录')
        with current_app.extensions['db'].connect() as conn:
            user = conn.execute(select(account).where(account.c.id == uid)).mappings().first()
        if not user:
            raise Problem(401, 'UNAUTHENTICATED', '账户不存在')
        g.actor = dict(user)
        return fn(*args, **kwargs)
    return wrapped


def require_role(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if g.actor['role'] not in roles:
                raise Problem(403, 'FORBIDDEN', '当前账户没有此操作权限')
            return fn(*args, **kwargs)
        return wrapped
    return decorator
