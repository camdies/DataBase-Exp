#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
    echo '不要 sudo 运行整个脚本；请用普通用户运行，安装依赖时会单独请求 sudo。' >&2
    exit 1
fi
if ! python3 -c 'import sys,venv,ensurepip; assert sys.version_info >= (3,12)' 2>/dev/null || ! command -v mysqld >/dev/null; then
    . /etc/os-release
    if [ "${ID:-}" != ubuntu ] || [ "${VERSION_ID:-}" != 24.04 ]; then
        echo '自动安装支持 Ubuntu 24.04；其他 Linux 请先安装 Python 3.12+、venv、MySQL 8.0.16+。' >&2
        exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip mysql-server
fi
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/manager.sh" first-run "$@"
