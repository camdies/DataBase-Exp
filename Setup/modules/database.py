"""MySQL provisioning: never drop or overwrite an existing database."""
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
from . import configuration as cfg
from .environment import port_free


def url_for(host, port, username, password, database=None):
    from sqlalchemy.engine import URL
    return URL.create('mysql+pymysql', username=username, password=password, host=host,
                      port=port, database=database, query={'charset': 'utf8mb4'}).render_as_string(hide_password=False)


def engine_for(url):
    from sqlalchemy import create_engine
    return create_engine(url, connect_args={'connect_timeout': 5, 'read_timeout': 15,
                                           'write_timeout': 15}, pool_pre_ping=True)


def check_version(conn):
    version = conn.exec_driver_sql('SELECT VERSION()').scalar()
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', version)
    if 'mariadb' in version.lower() or not match or tuple(map(int, match.groups())) < (8, 0, 16):
        raise cfg.SetupError('需要支持 CHECK 约束的 MySQL 8.0.16+；不支持 MariaDB。')


def verify(url):
    from sqlalchemy import inspect, select, CheckConstraint
    from backend.models import metadata
    engine = engine_for(url)
    try:
        with engine.connect() as conn:
            check_version(conn)
            inspector = inspect(conn)
            actual = set(inspector.get_table_names())
            if not set(metadata.tables) <= actual:
                raise cfg.SetupError('数据库缺少课程业务表；请完成初始化，勿对已有库重复导入。')
            for table in metadata.sorted_tables:
                columns = {c['name'] for c in inspector.get_columns(table.name)}
                if not set(table.columns.keys()) <= columns:
                    raise cfg.SetupError(f'表 {table.name} 缺少必需字段。')
                expected_pk = [c.name for c in table.primary_key.columns]
                if inspector.get_pk_constraint(table.name)['constrained_columns'] != expected_pk:
                    raise cfg.SetupError(f'表 {table.name} 主键与当前模型不符。')
                actual_fks = {(tuple(fk['constrained_columns']), fk['referred_table'], tuple(fk['referred_columns']))
                              for fk in inspector.get_foreign_keys(table.name)}
                expected_fks = {(tuple(fk.column_keys), fk.referred_table.name,
                                 tuple(element.column.name for element in fk.elements))
                                for fk in table.foreign_key_constraints}
                if not expected_fks <= actual_fks:
                    raise cfg.SetupError(f'表 {table.name} 外键与当前模型不符。')
                expected_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
                if not expected_checks <= {c['name'] for c in inspector.get_check_constraints(table.name)}:
                    raise cfg.SetupError(f'表 {table.name} 缺少必需 CHECK 约束。')
                conn.execute(select(table).limit(1)).first()
    finally:
        engine.dispose()


def identifier(name):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,47}', name):
        raise cfg.SetupError('库名只能包含英文字母、数字和下划线，且必须以字母开头（最多48字符）。')
    return name


def initialize(admin_url, name, app_user, app_password, admin_password, clerk_password):
    """Create a NEW database; failed imports remain recorded for inspection."""
    from sqlalchemy import text, update
    from sqlalchemy.engine import make_url
    from backend.models import account
    from backend.security import hash_password
    from tools.manage import counts
    from pymysql.constants import CLIENT
    import pymysql
    name, app_user = identifier(name), identifier(app_user)
    # Validate passwords and required files before the first DDL mutation.
    hashes = {role: hash_password(password) for role, password in
              [('admin', admin_password), ('clerk', clerk_password)]}
    files = [cfg.ROOT.parent / 'data' / f for f in ('schema_mysql.sql', 'backup_mysql.sql')]
    if not all(path.is_file() for path in files):
        raise cfg.SetupError('缺少 ../data/schema_mysql.sql 或 backup_mysql.sql。请完整解压学号_姓名目录。')
    admin = engine_for(admin_url)
    state = {'database': name, 'phase': 'checking'}
    try:
        with admin.connect() as conn:
            check_version(conn)
            account_host = conn.exec_driver_sql("SELECT SUBSTRING_INDEX(USER(), '@', -1)").scalar()
            if not account_host or '%' in account_host:
                raise cfg.SetupError('无法确定应用账户的连接来源。')
            if conn.execute(text('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=:name'),
                            {'name': name}).first():
                raise cfg.SetupError('目标数据库已存在，拒绝覆盖。请选择连接已有库，或填写新的库名。')
            if conn.execute(text('SELECT User FROM mysql.user WHERE User=:user'), {'user': app_user}).first():
                raise cfg.SetupError('应用数据库账户已存在，拒绝覆盖；请使用新的账户名。')
            cfg.save_json(cfg.LOCAL / 'install-state.json', state | {'phase': 'creating'})
            conn.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            conn.commit()
        source = make_url(admin_url)
        # Real mysql dump syntax, including versioned comments and table locks,
        # is interpreted by MySQL, not a homegrown semicolon splitter.
        with pymysql.connect(host=source.host, port=source.port or 3306, user=source.username,
                             password=source.password, database=name, charset='utf8mb4',
                             client_flag=CLIENT.MULTI_STATEMENTS, connect_timeout=5,
                             read_timeout=120, write_timeout=120, autocommit=True) as conn:
            for path in files:
                cfg.save_json(cfg.LOCAL / 'install-state.json', state | {'phase': path.name})
                with conn.cursor() as cursor:
                    cursor.execute(path.read_text(encoding='utf-8-sig'))
                    while cursor.nextset():
                        pass
        target = engine_for(source.set(database=name).render_as_string(hide_password=False))
        try:
            expected = {'account': 2, 'customer': 2000, 'warehouse': 3, 'product': 1000,
                        'stock': 3000, 'sales_order': 25000, 'order_item': 50000, 'shipment': 25000,
                        'total': 106005}
            if counts(target) != expected:
                raise cfg.SetupError('导入后的逐表数量与交付数据不一致，初始化未完成。')
            with target.begin() as conn:
                for role, hashed in hashes.items():
                    changed = conn.execute(update(account).where(account.c.username == role).values(password_hash=hashed))
                    if changed.rowcount != 1:
                        raise cfg.SetupError('初始账户数据异常。')
            with admin.begin() as conn:
                # Identifiers validated above; values are driver-bound parameters.
                conn.exec_driver_sql('CREATE USER %s@%s IDENTIFIED BY %s', (app_user, account_host, app_password))
                conn.exec_driver_sql(f'GRANT SELECT, INSERT, UPDATE, DELETE ON `{name}`.* TO %s@%s', (app_user, account_host))
            app_url = url_for(source.host, source.port or 3306, app_user, app_password, name)
            verify(app_url)
            cfg.save_json(cfg.LOCAL / 'install-state.json', state | {'phase': 'database-ready'})
            return app_url
        finally:
            target.dispose()
    except BaseException:
        # Do not imply transactional rollback for MySQL DDL, or delete partial data.
        if cfg.read_json(cfg.LOCAL / 'install-state.json', {}).get('database') == name:
            cfg.save_json(cfg.LOCAL / 'install-state.json', state | {'phase': 'needs-review'})
        raise
    finally:
        admin.dispose()


def find_mysqld():
    found = shutil.which('mysqld')
    if found:
        return Path(found)
    if os.name == 'nt':
        base = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'MySQL'
        candidates = sorted(base.glob('MySQL Server */bin/mysqld.exe'), reverse=True)
        if candidates:
            return candidates[0]
    return None


def managed_record():
    return cfg.read_json(cfg.LOCAL / 'mysql.json')


def ensure_managed(executable=None):
    from .service import owned_process, process_record, spawn
    info = managed_record()
    if info and info.get('phase') != 'ready':
        raise cfg.SetupError('专用数据库的上次初始化未完成。保留 mysql.json 和数据目录，按 README 恢复；不自动重新初始化。')
    if not info:
        executable = Path(executable) if executable else find_mysqld()
        if not executable or not executable.is_file():
            raise cfg.SetupError('未找到 mysqld；请运行 bootstrap.ps1 -Action install-mysql，或选择已有 MySQL。')
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share')))
        home = base / 'CourseInventory' / secrets.token_hex(12)
        home.mkdir(parents=True, exist_ok=False)
        cfg.protect(home)
        port = next((p for p in range(3307, 3407) if port_free('127.0.0.1', p)), None)
        if not port:
            raise cfg.SetupError('没有可用的专用 MySQL 端口（3307–3406）。')
        info = {'home': str(home), 'executable': str(executable.resolve()), 'port': port,
                'password': secrets.token_urlsafe(32), 'phase': 'initializing'}
        cfg.save_json(cfg.LOCAL / 'mysql.json', info)
        config = ('[mysqld]\n' + f'basedir="{executable.resolve().parent.parent.as_posix()}"\n' +
                  f'datadir="{(home / "data").as_posix()}"\nport={port}\nbind-address=127.0.0.1\n' +
                  f'log-error="{(home / "mysql-error.log").as_posix()}"\nmysqlx=0\n')
        if os.name != 'nt':
            config += f'socket="{(home / "mysql.sock").as_posix()}"\npid-file="{(home / "mysql.pid").as_posix()}"\n'
        cfg.atomic_text(home / 'my.ini', config)
        with (home / 'initialize.log').open('wb') as log:
            subprocess.run([str(executable), f'--defaults-file={home / "my.ini"}', '--initialize-insecure'],
                           stdout=log, stderr=log, check=True, timeout=180,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        initial = True
    else:
        initial = False
    if owned_process(info.get('process')):
        return url_for('127.0.0.1', info['port'], 'root', info['password'])
    if not port_free('127.0.0.1', info['port']):
        raise cfg.SetupError('专用数据库端口被其他进程占用，不会接管或关闭该进程。')
    home = Path(info['home'])
    process = spawn([info['executable'], f'--defaults-file={home / "my.ini"}'], home / 'console.log')
    try:
        info['process'] = process_record(process.pid)
        cfg.save_json(cfg.LOCAL / 'mysql.json', info)
        import pymysql
        for _ in range(120):
            if process.poll() is not None:
                raise cfg.SetupError('专用 MySQL 退出，请检查其 mysql-error.log（常见原因为运行库缺失）。')
            try:
                with pymysql.connect(host='127.0.0.1', port=info['port'], user='root',
                                     password='' if initial else info['password'], connect_timeout=1) as conn:
                    if initial:
                        with conn.cursor() as cursor:
                            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (info['password'],))
                    break
            except pymysql.OperationalError as exc:
                if exc.args[0] not in (2003, 2013):
                    raise
                time.sleep(0.5)
        else:
            raise cfg.SetupError('专用 MySQL 启动超时。')
        info['phase'] = 'ready'
        cfg.save_json(cfg.LOCAL / 'mysql.json', info)
        return url_for('127.0.0.1', info['port'], 'root', info['password'])
    except BaseException:
        # The process was created in this call; stop it if bootstrap failed.
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        raise


def stop_managed():
    from .service import owned_process, wait_stopped
    info = managed_record()
    if not info:
        return
    process = owned_process(info.get('process'))
    if not process:
        return
    import pymysql
    with pymysql.connect(host='127.0.0.1', port=info['port'], user='root',
                         password=info['password'], connect_timeout=5) as conn:
        with conn.cursor() as cursor:
            cursor.execute('SHUTDOWN')
    # A non-child zombie on Linux has already stopped but psutil.wait cannot
    # reap it; process identity/status is the relevant shutdown condition.
    wait_stopped(info['process'], 30)
    print('本项目专用 MySQL 已正常停止。')
