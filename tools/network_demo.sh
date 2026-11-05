#!/usr/bin/env bash
# 独立 IP 的可重复 HTTP 实验；只增加临时 veth/namespace，不修改主机默认路由或防火墙。
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo '请使用 sudo -E bash tools/network_demo.sh'; exit 1; fi
: "${ADMIN_PASSWORD:?请设置 ADMIN_PASSWORD}"
: "${CLERK_PASSWORD:?请设置 CLERK_PASSWORD}"
: "${PYTHON:=python3}"
if ip netns list | grep -q '^course-client\b' || ip link show cw-server >/dev/null 2>&1; then
  echo '实验命名空间或接口已经存在，拒绝覆盖'; exit 1
fi
if ip route show | grep -q '^172.29.241.0/30'; then echo '实验网段已占用，拒绝覆盖'; exit 1; fi
cleanup() { ip netns del course-client 2>/dev/null || true; ip link del cw-server 2>/dev/null || true; }
trap cleanup EXIT
ip netns add course-client
ip link add cw-server type veth peer name cw-client
ip link set cw-client netns course-client
ip addr add 172.29.241.1/30 dev cw-server
ip link set cw-server up
ip -n course-client addr add 172.29.241.2/30 dev cw-client
ip -n course-client link set cw-client up
ip -n course-client link set lo up
mkdir -p ../doument/evidence/network
ip -j addr show cw-server > ../doument/evidence/network/server-interface.json
ip -n course-client -j addr show cw-client > ../doument/evidence/network/client-interface.json
ip netns exec course-client "$PYTHON" -m tools.benchmark --base-url http://172.29.241.1:5001 --clients 8 --requests 40 --output ../doument/evidence/network
