"""生成并验证真正的 RAR，排除本机配置/依赖；小于100MB才交付。"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDE = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.env', 'config.ini', 'runtime_logs', '.local'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--student-id',default='学号')
    parser.add_argument('--name',default='姓名')
    parser.add_argument('--output',type=Path,default=ROOT.parent)
    args=parser.parse_args()
    folder=f'{args.student_id}_{args.name}'
    if not re.fullmatch(r'[\w\-]+_[\w\-]+',folder):
        parser.error('学号和姓名只允许文字、数字、下划线或连字符')
    rar=shutil.which('rar')
    if not rar:
        for candidate in [Path(os.getenv('ProgramFiles','C:/Program Files'))/'WinRAR/Rar.exe']:
            if candidate.exists(): rar=str(candidate);break
    if not rar: raise SystemExit('需要 rar（Linux）或 WinRAR/Rar.exe；不能把ZIP改名冒充RAR')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='course-submission-') as tmp:
        stage=Path(tmp)/folder
        def ignore(directory,names):
            return [n for n in names if n in EXCLUDE or n.startswith('.venv-old-') or n.endswith(('.pyc','.log','.rar'))]
        for section in ['data','code','doument']:
            shutil.copytree(ROOT/section,stage/section,ignore=ignore)
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        hashes='\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(stage).as_posix() for p in files)
        (stage/'doument/SHA256SUMS.txt').write_text(hashes+'\n',encoding='utf-8')
        archive=Path(tmp)/(folder+'.rar')
        subprocess.run([rar,'a','-r','-m5','-idq',str(archive),folder],cwd=tmp,check=True)
        subprocess.run([rar,'t','-idq',str(archive)],check=True)
        if archive.stat().st_size>=100_000_000: raise RuntimeError('RAR超过100MB，拒绝交付')
        if archive.read_bytes()[:6]!=b'Rar!\x1a\x07': raise RuntimeError('不是RAR格式')
        target=output/archive.name
        shutil.copy2(archive,target)
        print(f'RAR verified: {target}\nSize: {target.stat().st_size} bytes\nFiles: {len(files)+1}\nSHA256: {hashlib.sha256(target.read_bytes()).hexdigest()}')


if __name__=='__main__': main()
