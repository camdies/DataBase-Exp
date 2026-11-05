"""Export only an allowlist of machine details; raw logs are not exported."""
from datetime import datetime, timezone
import importlib.metadata
import platform
from . import configuration as cfg
from . import environment, service


def status():
    value = service.record()
    running = bool(service.owned_process(value))
    print('Web 进程：' + ('运行中' if running else '未运行'))
    if running:
        try:
            service.verify_http(value)
            print('页面：可用；' + service.url(value))
        except Exception:
            print('页面：不可用或正在停止')
    for item in environment.check():
        print(f'[{"通过" if item["ok"] else "需处理"}] {item["item"]}: {item["message"]}')


def export_report():
    versions = {}
    for name in ('Flask', 'SQLAlchemy', 'PyMySQL', 'PyJWT', 'bcrypt', 'waitress', 'psutil'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = 'missing'
    report = {'generated_utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.system(), 'python': platform.python_version(),
              'packages': versions, 'checks': environment.check()}
    target = cfg.LOGS / ('diagnostic-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
    cfg.save_json(target, report)
    print('已导出诊断报告（不含 .env、密码、JWT 或原始日志）：' + str(target))
    return target


def logs():
    print('安装与运行日志目录：' + str(cfg.LOGS))
    for path in sorted(cfg.LOGS.glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
        print(f'  {path.name}  {path.stat().st_size} bytes')
    print('日志保留在本机；对外提供问题信息时优先使用 diagnostics 导出的报告。')
