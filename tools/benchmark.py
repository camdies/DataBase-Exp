"""多客户端、多账户 HTTP 并发访问；每个客户端独立登录，记录每次访问。"""
import argparse
import csv
import json
import math
import os
import statistics
import time
import platform
import socket
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def call(base, path, token=None, data=None, client_id=None, benchmark_id=None):
    headers = {'Content-Type':'application/json', 'User-Agent': 'CourseBenchmark/'+platform.system()}
    if client_id:
        headers['X-Client-ID'] = client_id
    if benchmark_id:
        headers['X-Benchmark-ID'] = benchmark_id
    if token:
        headers['Authorization'] = 'Bearer '+token
    req = Request(base+path, headers=headers, data=json.dumps(data).encode() if data is not None else None)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.load(r), r.headers.get('X-Request-ID','')
    except HTTPError as e:
        return e.code, {}, e.headers.get('X-Request-ID','')
    except (URLError, TimeoutError):
        return 0, {}, ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--clients', type=int, default=8)
    parser.add_argument('--requests', type=int, default=40, help='每客户端访问次数')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--users-file', type=Path, help='私有JSON数组，元素包含username/password；不要放入提交目录')
    args = parser.parse_args()
    if not 1 <= args.clients <= 64 or not 1 <= args.requests <= 10000:
        parser.error('客户端数 1–64，请求数 1–10000')
    if args.users_file:
        users = [(u['username'], u['password']) for u in json.loads(args.users_file.read_text(encoding='utf-8'))]
        if not users:
            parser.error('users-file至少包含一个账户')
    else:
        users = [('admin',os.environ['ADMIN_PASSWORD']), ('clerk',os.environ['CLERK_PASSWORD'])]
    benchmark_id = uuid4().hex
    client_ids = [uuid4().hex for _ in range(args.clients)]
    tokens = []
    # 登录不计入数据库查询吞吐；每客户端获取自己的 token。
    for i in range(args.clients):
        user, password = users[i%len(users)]
        status, body, _ = call(args.base_url, '/api/login', data={'username':user,'password':password}, client_id=client_ids[i])
        if status != 200:
            raise RuntimeError(f'客户端 {i} 登录失败 HTTP {status}')
        tokens.append(body['data']['token'])
    barrier = Barrier(args.clients)
    def worker(i):
        rows = []
        barrier.wait()
        for j in range(args.requests):
            path = '/api/orders?customer_id='+str((i*args.requests+j)%2000+1) if j%2 == 0 else '/api/products?page='+str(j%40+1)
            start = time.perf_counter()
            status, body, rid = call(args.base_url,path,tokens[i], client_id=client_ids[i], benchmark_id=benchmark_id)
            rows.append({'client':i,'client_id':client_ids[i],'benchmark_id':benchmark_id,'user':users[i%len(users)][0],'sequence':j,'path':path,'status':status,
                         'ok':status == 200 and body.get('success') is True,
                         'latency_ms':round((time.perf_counter()-start)*1000,3),'request_id':rid})
        return rows
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        rows = [row for batch in pool.map(worker,range(args.clients)) for row in batch]
    elapsed = time.perf_counter()-start
    values = sorted(x['latency_ms'] for x in rows)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output/'requests.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {'timestamp_utc':datetime.now(timezone.utc).isoformat(), 'client_platform':platform.platform(),
               'server_url':args.base_url,'clients':args.clients,'accounts':sorted({users[i%len(users)][0] for i in range(args.clients)}), 'benchmark_id':benchmark_id,'requests':len(rows),
               'successful':sum(x['ok'] for x in rows), 'failed':sum(not x['ok'] for x in rows),
               'elapsed_s':elapsed, 'throughput_rps':len(rows)/elapsed,
               'mean_ms':statistics.mean(values),'p50_ms':statistics.median(values),
               'p95_ms':values[math.ceil(len(values)*.95)-1],'max_ms':max(values),
               'workload':'50% 按客户跨表订单查询；50% 商品及分仓库存查询；不含登录'}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if summary['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
