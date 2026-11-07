#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then echo '请使用普通用户运行。' >&2; exit 1; fi
. /etc/os-release
if [ "${ID:-}" != ubuntu ] || [ "${VERSION_ID:-}" != 24.04 ]; then
  echo '请先手动安装 MySQL 8.0.16+，或选择连接已有 MySQL；自动安装仅支持 Ubuntu 24.04。' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y mysql-server
