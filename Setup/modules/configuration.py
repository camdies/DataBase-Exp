"""Private, non-executable configuration and atomic local state."""
import contextlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'Setup' / '.local'
LOGS = ROOT / 'runtime_logs' / 'setup'
DEFAULTS = {'host': '127.0.0.1', 'port': 5001, 'threads': 8, 'open_browser': True,
            'database_mode': 'external'}
ENV_KEYS = {'DATABASE_URL', 'JWT_SECRET', 'BCRYPT_ROUNDS', 'ACCESS_LOG_DIR'}


class SetupError(RuntimeError):
    """Only explicitly safe messages may be shown to the user."""


def protect(path):
    path = Path(path)
    if os.name == 'nt':
        # SID avoids localized account names and domain/backslash ambiguity.
        sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'],
                                      text=True).strip().split(',')[-1].strip('"')
        flags = '(OI)(CI)F' if path.is_dir() else 'F'
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                                 f'*{sid}:{flags}', '*S-1-5-18:F'], capture_output=True)
        if result.returncode:
            raise SetupError('无法限制本机私有文件权限，请检查目录权限。')
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def atomic_text(path, content, private=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.setup-', dir=path.parent)
    try:
        os.close(fd)
        if private:
            protect(temp)
        Path(temp).write_text(content, encoding='utf-8')
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def save_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read_json(path, default=None):
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        raise SetupError(f'{Path(path).name} 无法读取，请保留文件后重新配置。') from None


def settings():
    value = read_json(LOCAL / 'settings.json', {})
    if not isinstance(value, dict):
        raise SetupError('settings.json 必须为对象。')
    result = DEFAULTS | value
    if result['host'] not in ('127.0.0.1', '0.0.0.0'):
        raise SetupError('监听地址只支持 127.0.0.1 或 0.0.0.0。')
    for key, lower, upper in [('port', 1, 65535), ('threads', 1, 64)]:
        if type(result[key]) is not int or not lower <= result[key] <= upper:
            raise SetupError(f'{key} 超出有效范围。')
    if result['database_mode'] not in ('external', 'managed'):
        raise SetupError('数据库管理方式无效。')
    return result


def read_env(path=None):
    path = Path(path or ROOT / '.env')
    if not path.exists():
        raise SetupError('缺少 code/.env，请先执行首次配置。')
    result = {}
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or key not in ENV_KEYS or key in result:
            raise SetupError(f'.env 第 {number} 行键名无效或重复。')
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                raise SetupError(f'.env 第 {number} 行引号格式错误。') from None
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        if not isinstance(value, str) or any(c in value for c in '\r\n\x00'):
            raise SetupError('.env 包含不支持的值。')
        result[key] = value
    validate_env(result)
    return result


def validate_env(values):
    secret = values.get('JWT_SECRET', '')
    if len(secret) < 32 or len(set(secret)) < 12 or secret.startswith('REPLACE_'):
        raise SetupError('JWT_SECRET 缺失或不符合随机密钥要求。')
    try:
        from sqlalchemy.engine import make_url
        url = make_url(values.get('DATABASE_URL', ''))
        if url.drivername != 'mysql+pymysql' or not url.host or not url.database or not url.username:
            raise ValueError()
        if not url.password or 'URL_ENCODED_PASSWORD' in url.password:
            raise ValueError()
        if not 12 <= int(values.get('BCRYPT_ROUNDS', '12')) <= 16:
            raise ValueError()
    except Exception:
        # SQLAlchemy URL parse errors can contain the input URL; never echo them.
        raise SetupError('数据库连接或 BCRYPT_ROUNDS 配置无效。') from None


def write_env(values):
    validate_env(values)
    atomic_text(ROOT / '.env', '# Setup 私有配置；值按 JSON 字符串存储，不作为脚本执行。\n' +
                '\n'.join(f'{k}={json.dumps(v, ensure_ascii=False)}' for k, v in values.items()) + '\n')


def child_env(values=None):
    result = os.environ.copy()
    result.update(values if values is not None else read_env())
    log_dir = Path(result.get('ACCESS_LOG_DIR', 'runtime_logs'))
    result['ACCESS_LOG_DIR'] = str(log_dir if log_dir.is_absolute() else ROOT / log_dir)
    result['PYTHONUTF8'] = '1'
    result['PYTHONUNBUFFERED'] = '1'
    return result


def new_env(database_url):
    return {'DATABASE_URL': database_url, 'JWT_SECRET': secrets.token_urlsafe(48),
            'BCRYPT_ROUNDS': '12', 'ACCESS_LOG_DIR': 'runtime_logs'}


@contextlib.contextmanager
def operation_lock():
    LOCAL.mkdir(parents=True, exist_ok=True)
    protect(LOCAL)
    with (LOCAL / 'operation.lock').open('a+b') as handle:
        handle.seek(0)
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SetupError('另一个配置或启停操作正在执行，请等待完成。') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
