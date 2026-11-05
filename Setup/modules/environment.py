"""Project-local Python repair and read-only preflight checks."""
import importlib.metadata
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from . import configuration as cfg


def python_path():
    return cfg.ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def repair():
    if sys.version_info < (3, 12):
        raise cfg.SetupError('需要 Python 3.12 或更新版本，请运行 FirstRun.cmd。')
    venv = cfg.ROOT / '.venv'
    executable = python_path()
    venv_config = venv / 'pyvenv.cfg'
    isolated = venv_config.is_file() and 'include-system-site-packages = false' in venv_config.read_text(encoding='utf-8').lower()
    usable = isolated and executable.exists() and subprocess.run(
        [str(executable), '-c', 'import sys; assert sys.version_info >= (3,12)'],
        capture_output=True).returncode == 0
    if not usable:
        if Path(sys.prefix).resolve() == venv.resolve():
            raise cfg.SetupError('当前虚拟环境已损坏，请关闭服务并通过 bootstrap.ps1 -Action repair 重建。')
        if venv.exists():
            # Retain damaged environments for manual inspection, never recursively delete.
            venv.rename(cfg.ROOT / f'.venv-old-{time.time_ns()}')
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
    for requirements in (cfg.ROOT / 'requirements.txt', cfg.ROOT / 'Setup/requirements.txt'):
        subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(requirements)],
                       cwd=cfg.ROOT, check=True)
    subprocess.run([str(executable), '-m', 'pip', 'check'], check=True)
    cfg.LOGS.mkdir(parents=True, exist_ok=True)
    with (cfg.LOGS / 'install.log').open('a', encoding='utf-8') as log:
        log.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' Python environment and pip check completed.\n')
    print('项目虚拟环境及依赖已修复。')


def require_dependencies():
    missing = []
    modules = {'Flask': ('flask', {3}), 'SQLAlchemy': ('sqlalchemy', {2}), 'PyMySQL': ('pymysql', {1}),
               'PyJWT': ('jwt', {2}), 'bcrypt': ('bcrypt', {4, 5}), 'waitress': ('waitress', {3}),
               'psutil': ('psutil', {6, 7})}
    if sys.version_info < (3, 12):
        raise cfg.SetupError('需要 Python 3.12 或更新版本。')
    for name, (module, majors) in modules.items():
        try:
            version = importlib.metadata.version(name)
            if int(version.split('.')[0]) not in majors:
                raise ValueError()
            importlib.import_module(module)
        except (importlib.metadata.PackageNotFoundError, ImportError, OSError, ValueError):
            missing.append(name)
    if missing:
        raise cfg.SetupError('缺少依赖：' + ', '.join(missing) + '。请运行环境修复。')


def check_assets():
    from html.parser import HTMLParser
    dist = cfg.ROOT / 'frontend/dist'
    index = dist / 'index.html'
    if not index.is_file():
        raise cfg.SetupError('缺少 frontend/dist/index.html；请恢复交付产物或重建前端。')
    class Assets(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name in ('src', 'href') and value and value.startswith('/assets/'):
                    target = (dist / value.lstrip('/')).resolve()
                    if not target.is_relative_to(dist.resolve()) or not target.is_file():
                        raise cfg.SetupError('前端引用资源缺失，请重新构建前端。')
    Assets().feed(index.read_text(encoding='utf-8'))


def port_free(host, port):
    try:
        with socket.socket() as sock:
            if os.name == 'nt':
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                # Match Waitress' POSIX binding: closed connections in TIME_WAIT
                # must not be mistaken for a live listener during restart.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
        return True
    except OSError:
        return False


def check_log_dir(values):
    directory = Path(cfg.child_env(values)['ACCESS_LOG_DIR'])
    # Read-only check must not create application files or directories.
    existing = directory
    while not existing.exists():
        existing = existing.parent
    if not existing.is_dir() or not os.access(existing, os.W_OK):
        raise cfg.SetupError('日志目录不可写。')
    if shutil.disk_usage(existing).free < 100 * 1024 * 1024:
        raise cfg.SetupError('日志所在磁盘剩余空间不足 100 MiB。')


def check():
    from . import database, service
    results = []
    def item(name, action):
        try:
            action()
            results.append({'item': name, 'ok': True, 'message': '通过'})
        except Exception as exc:
            results.append({'item': name, 'ok': False, 'message': safe_error(exc)})
    item('Python / 依赖', require_dependencies)
    item('前端产物', check_assets)
    item('本机配置', lambda: (cfg.read_env(), cfg.settings()))
    item('日志目录 / 磁盘', lambda: check_log_dir(cfg.read_env()))
    item('MySQL / 表结构', lambda: database.verify(cfg.read_env()['DATABASE_URL']))
    def port_check():
        settings = cfg.settings()
        record = service.record()
        if service.owned_process(record):
            service.verify_http(record)
        elif not port_free(settings['host'], settings['port']):
            raise cfg.SetupError('应用端口被其他程序占用；不会自动结束该程序。')
    item('服务 / 端口', port_check)
    return results


def safe_error(exc):
    if isinstance(exc, cfg.SetupError):
        return str(exc)
    if isinstance(exc, subprocess.CalledProcessError):
        return f'子命令执行失败（退出码 {exc.returncode}），请检查上方安装输出；不会继续后续步骤。'
    original = getattr(exc, 'orig', exc)
    args = getattr(original, 'args', ())
    code = args[0] if args and isinstance(args[0], int) else None
    reasons = {1045: 'MySQL 认证失败，请检查账户、密码及连接来源授权。',
               1044: 'MySQL 账户没有目标数据库权限。',
               1049: '目标数据库不存在，请检查库名或执行首次配置。',
               2003: '无法连接 MySQL，请检查主机、端口及服务状态。',
               2006: 'MySQL 连接已断开，请检查数据库服务与日志。',
               2013: 'MySQL 连接中断或超时，请检查网络及数据库状态。',
               1142: 'MySQL 权限不足，请检查操作所需授权。',
               1146: '缺少数据表；请检查初始化记录，不要向现有库重复导入。'}
    if code in reasons:
        return reasons[code]
    # Database exceptions, command output and traceback may contain credentials.
    return f'操作失败（{type(exc).__name__}）；请检查配置、权限或依赖。'
