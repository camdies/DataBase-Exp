"""Command line and interactive menu. Run with the project's virtual environment."""
import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Setup.modules import configuration as cfg
from Setup.modules import database, diagnostics, environment, service


def ask(label, default=None):
    value = input(f'{label}' + (f' [{default}]' if default is not None else '') + ': ').strip()
    return value or default or ''


def password(label, confirm=True):
    value = getpass.getpass(label + ': ')
    if not value or any(c in value for c in '\r\n\x00'):
        raise cfg.SetupError('密码不能为空或含换行。')
    if confirm and value != getpass.getpass('再次输入: '):
        raise cfg.SetupError('两次密码不一致。')
    return value


def port(label, default):
    try:
        value = int(ask(label, default))
        if not 1 <= value <= 65535:
            raise ValueError()
        return value
    except ValueError:
        raise cfg.SetupError('端口必须为 1–65535 的整数。') from None


def connection(database_required=True):
    host = ask('数据库主机', '127.0.0.1')
    number = port('数据库端口', 3306)
    user = ask('数据库账户', 'course_app' if database_required else 'root')
    secret = password('数据库账户密码', confirm=False)
    name = ask('数据库名', 'course_inventory') if database_required else None
    return database.url_for(host, number, user, secret, name)


def configure(first=False):
    if service.owned_process(service.record()):
        raise cfg.SetupError('请先停止 Web 服务，再修改配置。')
    current = None
    if (cfg.ROOT / '.env').exists():
        try:
            current = cfg.read_env()
        except cfg.SetupError:
            if ask('现有配置无效。保留私有备份并重新配置？（y/N）', 'N').lower() != 'y':
                raise cfg.SetupError('已保留原配置，请修正后重试。')
            import time
            cfg.atomic_text(cfg.LOCAL / f'config-backup-{time.time_ns()}.env',
                            (cfg.ROOT / '.env').read_text(encoding='utf-8-sig'))
    settings = cfg.settings()
    if current and first:
        print('检测到已有配置；不会重复初始化或自动重置密码。')
        if settings['database_mode'] == 'managed':
            database.ensure_managed()
        database.verify(current['DATABASE_URL'])
        print('现有数据库验证通过。可使用 Start.cmd 或 bash Setup/linux/manager.sh start。')
        return
    choice = ask('数据库方式：1=连接已有库，2=已有 MySQL 上创建新库，3=本机专用 MySQL' +
                 ('，0=保留连接' if current else ''), '0' if current else '3')
    if choice == '0' and current:
        values = current
    elif choice == '1':
        candidate = connection()
        database.verify(candidate)
        values = (current or cfg.new_env(candidate)) | {'DATABASE_URL': candidate}
        settings['database_mode'] = 'external'
    elif choice in ('2', '3'):
        if choice == '3':
            if not database.managed_record() and not database.find_mysqld():
                if os.name != 'nt':
                    raise cfg.SetupError('请先安装 MySQL，或选择连接已有实例。')
                print('需要下载并安装 MySQL Server 与 VC++ 运行库；系统可能显示 UAC。')
                subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                str(cfg.ROOT / 'Setup/bootstrap.ps1'), '-Action', 'install-mysql'], check=True)
            admin_url = database.ensure_managed()
        else:
            admin_url = connection(database_required=False)
        import secrets
        name = database.identifier(ask('新数据库名（必须不存在）', 'course_inventory'))
        app_user = database.identifier(ask('新应用数据库账户', 'course_app_' + secrets.token_hex(3)))
        app_password = password('设置应用数据库账户密码')
        admin_password = password('设置网页 admin 密码（10–72 UTF-8 字节）')
        clerk_password = password('设置网页 clerk 密码（10–72 UTF-8 字节）')
        candidate = database.initialize(admin_url, name, app_user, app_password, admin_password, clerk_password)
        values = (current or cfg.new_env(candidate)) | {'DATABASE_URL': candidate}
        # Persist immediately after database provisioning, before optional prompts.
        cfg.write_env(values)
        settings['database_mode'] = 'managed' if choice == '3' else 'external'
        cfg.save_json(cfg.LOCAL / 'settings.json', settings)
    else:
        raise cfg.SetupError('数据库方式选项无效。')
    settings['port'] = port('网页端口', settings['port'])
    access = ask('访问模式：1=仅本机，2=局域网', '2' if settings['host'] == '0.0.0.0' else '1')
    if access not in ('1', '2'):
        raise cfg.SetupError('访问模式选项无效。')
    settings['host'] = '127.0.0.1' if access == '1' else '0.0.0.0'
    cfg.write_env(values)
    cfg.save_json(cfg.LOCAL / 'settings.json', settings)
    cfg.save_json(cfg.LOCAL / 'install-state.json', {'phase': 'configured'})
    print('配置已保存。JWT 密钥保留在本机；正常重启不会重新生成。')
    if first:
        service.start()


def check():
    result = environment.check()
    for item in result:
        print(f'[{"通过" if item["ok"] else "需处理"}] {item["item"]}: {item["message"]}')
    return 0 if all(item['ok'] for item in result) else 1


def execute(args):
    action = args.action
    if action == '_serve':
        service.serve()
        return 0
    if action == 'repair':
        with cfg.operation_lock():
            if service.owned_process(service.record()):
                raise cfg.SetupError('请先停止 Web 服务再修复依赖。')
            environment.repair()
        return 0
    if action == 'check':
        return check()
    if action == 'check-repair':
        check_result = check()
        if ask('修复 Python 依赖？数据库和配置不会被覆盖（y/N）', 'N').lower() == 'y':
            # Re-run in the repaired interpreter so imported packages are fresh.
            with cfg.operation_lock():
                if service.owned_process(service.record()):
                    raise cfg.SetupError('请先停止服务。')
                environment.repair()
            return subprocess.run([str(environment.python_path()), str(Path(__file__).resolve()), 'check'],
                                  cwd=cfg.ROOT).returncode
        return check_result
    environment.require_dependencies()
    if action == 'status':
        diagnostics.status()
    elif action == 'diagnostics':
        diagnostics.export_report()
    elif action == 'logs':
        diagnostics.logs()
    else:
        with cfg.operation_lock():
            if action in ('first-run', 'configure'):
                configure(first=action == 'first-run')
            elif action == 'start':
                service.start(not args.no_browser)
            elif action == 'stop':
                service.stop(args.force)
                if args.with_database:
                    database.stop_managed()
            elif action == 'restart':
                service.stop(args.force)
                service.start(not args.no_browser)
    return 0


def menu():
    options = {'1': 'first-run', '2': 'check-repair', '3': 'start', '4': 'stop',
               '5': 'restart', '6': 'status', '7': 'configure', '8': 'logs', '9': 'diagnostics'}
    while True:
        if environment.python_path().is_file() and Path(sys.prefix).resolve() != (cfg.ROOT / '.venv').resolve():
            return subprocess.run([str(environment.python_path()), str(Path(__file__).resolve()), 'menu'],
                                  cwd=cfg.ROOT).returncode
        print('\n订单与库存系统 — 管理工具\n'
              '[1] 首次安装与配置  [2] 环境检查与修复\n'
              '[3] 快速启动        [4] 快速停机\n'
              '[5] 重启服务        [6] 查看运行状态\n'
              '[7] 修改配置        [8] 查看日志位置\n'
              '[9] 导出诊断报告    [0] 退出菜单（不停止服务）')
        choice = ask('选择', '0')
        if choice == '0':
            return 0
        if choice not in options:
            print('请输入菜单中的编号。')
            continue
        action = options[choice]
        try:
            if action == 'first-run':
                with cfg.operation_lock():
                    if service.owned_process(service.record()):
                        raise cfg.SetupError('请先停止 Web 服务。')
                    environment.repair()
                subprocess.run([str(environment.python_path()), str(Path(__file__).resolve()), 'first-run'], cwd=cfg.ROOT)
            else:
                execute(argparse.Namespace(action=action, force=False, no_browser=False, with_database=False))
        except Exception as exc:
            print(environment.safe_error(exc))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='课程系统安装与服务管理')
    parser.add_argument('action', nargs='?', default='menu', choices=['menu', 'first-run', 'configure',
                        'check', 'check-repair', 'repair', 'start', 'stop', 'restart', 'status', 'logs', 'diagnostics', '_serve'])
    parser.add_argument('--force', action='store_true', help='正常停机超时后强制停止已核验的 Web 进程')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--with-database', action='store_true', help='停机时同时正常关闭本项目专用数据库')
    args = parser.parse_args()
    try:
        if args.action == 'menu':
            return menu()
        return execute(args)
    except (KeyboardInterrupt, EOFError):
        print('\n操作取消；已创建的数据库和配置会保留。')
        return 130
    except Exception as exc:
        print(environment.safe_error(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
