"""Windows/Linux 通用生产 WSGI 入口；浏览器和 API 共用端口，无需 Node。"""
import argparse
from waitress import serve
from backend.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1', help='本机用127.0.0.1，局域网用0.0.0.0或服务器网卡IP')
    parser.add_argument('--port', type=int, default=5001)
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.threads <= 64:
        parser.error('端口1–65535，线程1–64')
    serve(create_app(), host=args.host, port=args.port, threads=args.threads,
          channel_timeout=60, max_request_body_size=65536,
          clear_untrusted_proxy_headers=True)


if __name__ == '__main__':
    main()
