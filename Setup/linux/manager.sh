#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
action="${1:-menu}"
if [ "$#" -gt 0 ]; then shift; fi
if [ "$(id -u)" -eq 0 ]; then
    echo '请用普通用户运行；仅安装系统依赖时使用 sudo。' >&2
    exit 1
fi
case "$action" in
  first-run|repair)
    if ! python3 -c 'import sys, venv; assert sys.version_info >= (3,12)' 2>/dev/null; then
      echo '需要 Python 3.12+ 和 venv；Ubuntu 24.04 请执行 bash Setup/linux/setup.sh。' >&2
      exit 1
    fi
    python3 "$root/Setup/manager.py" repair
    if [ "$action" = repair ]; then exit 0; fi
    ;;
esac
if [ -x "$root/.venv/bin/python" ]; then
    exec "$root/.venv/bin/python" "$root/Setup/manager.py" "$action" "$@"
fi
if [ "$action" = check ]; then
    exec python3 "$root/Setup/manager.py" check "$@"
fi
echo '尚未建立 Linux 虚拟环境，请先运行 bash Setup/linux/setup.sh。' >&2
exit 1
