"""Build in isolation; publish only validated assets while the server is stopped."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
import zipfile
from . import configuration as cfg

VERSION = '24.16.0'
ARCHIVES = {
    'win-x64.zip': 'edaca9bd58ec8e92037dac4e877d52f6b8f430b81c18b57e264b4e2fb111cd56',
    'linux-x64.tar.xz': 'd804845d34eddc21dc1092b519d643ef40b1f58ec5dec5c22b1f4bd8fabde6c9',
    'linux-arm64.tar.xz': '524659219d6a207a7400f2bde15d19ba060ffbe0d32a8643319ad67e3bb64c78',
}


def runtime(install=False):
    """Use a pinned private runtime; never accidentally invoke Windows npm in WSL."""
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower())
    suffix = f'win-{arch}.zip' if os.name == 'nt' else f'linux-{arch}.tar.xz'
    if suffix not in ARCHIVES or (os.name != 'nt' and platform.system() != 'Linux'):
        raise cfg.SetupError('自动 Node.js 安装支持 Windows x64、Linux x64/arm64。')
    name = f'node-v{VERSION}-{suffix}'
    base = cfg.LOCAL / 'runtimes'
    folder = base / name.removesuffix('.zip').removesuffix('.tar.xz')
    node = folder / ('node.exe' if os.name == 'nt' else 'bin/node')
    npm = folder / ('node_modules/npm/bin/npm-cli.js' if os.name == 'nt' else 'lib/node_modules/npm/bin/npm-cli.js')
    if not node.is_file() or not npm.is_file():
        if not install:
            raise cfg.SetupError('尚未准备项目 Node.js；请运行 build-frontend 或首次配置。')
        base.mkdir(parents=True, exist_ok=True)
        archive = base / name
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVES[suffix]:
            print(f'下载项目专用 Node.js {VERSION}，不修改系统 PATH。', flush=True)
            partial = archive.with_suffix(archive.suffix + '.part')
            try:
                with urllib.request.urlopen(f'https://nodejs.org/dist/v{VERSION}/{name}', timeout=60) as response, partial.open('wb') as output:
                    shutil.copyfileobj(response, output)
            except (urllib.error.URLError, TimeoutError) as exc:
                raise cfg.SetupError(f'无法下载 Node.js；检查网络或从 https://nodejs.org/dist/v{VERSION}/{name} '
                                     f'下载后放到 {archive}，重试仍会校验摘要。') from exc
            if hashlib.sha256(partial.read_bytes()).hexdigest() != ARCHIVES[suffix]:
                raise cfg.SetupError('Node.js 下载摘要校验失败，未解压或执行。')
            partial.replace(archive)
        with tempfile.TemporaryDirectory(dir=base, prefix='extract-') as temp:
            if os.name == 'nt':
                with zipfile.ZipFile(archive) as package:
                    package.extractall(temp)
            else:
                with tarfile.open(archive) as package:
                    package.extractall(temp, filter='data')
            if folder.exists():
                folder.rename(base / (folder.name + f'-old-{time.time_ns()}'))
            (Path(temp) / folder.name).rename(folder)
    result = subprocess.run([str(node), '--version'], capture_output=True, text=True, check=True)
    if result.stdout.strip() != 'v' + VERSION:
        raise cfg.SetupError('项目 Node.js 版本异常，请检查 Setup/.local/runtimes。')
    return node, npm


def fingerprint():
    root = cfg.ROOT / 'frontend'
    paths = [p for p in root.iterdir() if p.is_file()]
    for directory in ('src', 'public'):
        if (root / directory).exists():
            paths.extend(p for p in (root / directory).rglob('*') if p.is_file())
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def check_fresh():
    record = cfg.read_json(cfg.ROOT / 'frontend/dist/setup-build.json')
    if not record or record.get('source_sha256') != fingerprint():
        raise cfg.SetupError('前端尚无构建记录或源码已变化，请运行 build-frontend。')


def publish(staged, target):
    backup = target.with_name('dist-backup-' + str(time.time_ns()))
    if target.exists():
        target.rename(backup)
    try:
        staged.rename(target)
    except BaseException:
        if backup.exists():
            backup.rename(target)
        raise
    return backup if backup.exists() else None


def build():
    from . import service, environment
    if service.owned_process(service.record()):
        raise cfg.SetupError('请先停止 Web 服务，再重新编译前端。')
    root = cfg.ROOT / 'frontend'
    if not (root / 'package-lock.json').is_file():
        raise cfg.SetupError('缺少 frontend/package-lock.json，无法复现安装依赖。')
    node, npm = runtime(install=True)
    cfg.LOGS.mkdir(parents=True, exist_ok=True)
    logfile = cfg.LOGS / f'frontend-{time.time_ns()}.log'
    before = fingerprint()
    env = os.environ.copy()
    env['PATH'] = str(node.parent) + os.pathsep + env.get('PATH', '')
    print('安装前端依赖并构建；日志：' + str(logfile), flush=True)
    # Same filesystem as dist permits a rename-based publication and rollback.
    with tempfile.TemporaryDirectory(prefix='.frontend-build-', dir=cfg.ROOT) as temp:
        work = Path(temp)
        for path in root.iterdir():
            if path.is_file():
                shutil.copy2(path, work / path.name)
        for directory in ('src', 'public'):
            if (root / directory).exists():
                shutil.copytree(root / directory, work / directory)
        with logfile.open('w', encoding='utf-8') as output:
            for args in (['ci', '--no-audit', '--no-fund'], ['run', 'build']):
                result = subprocess.run([str(node), str(npm), *args], cwd=work, env=env,
                                        stdout=output, stderr=subprocess.STDOUT)
                if result.returncode:
                    raise cfg.SetupError('前端构建失败，原产物已保留。请查看：' + str(logfile))
        environment.check_assets(work / 'dist')
        if fingerprint() != before:
            raise cfg.SetupError('构建期间源码发生变化，未替换原产物，请重新构建。')
        (work / 'dist/setup-build.json').write_text(json.dumps({
            'source_sha256': before, 'node': VERSION, 'built_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }), encoding='utf-8')
        backup = publish(work / 'dist', root / 'dist')
    print('前端构建成功。' + (f'旧产物保留在：{backup}' if backup else ''))
