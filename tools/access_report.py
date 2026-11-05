"""聚合服务端 JSONL（含轮转文件），按用户与客户端统计；可与压测CSV关联。"""
import argparse
import json
import math
import statistics
from pathlib import Path


def summarize(rows):
    values = sorted(row['duration_ms'] for row in rows)
    return {'requests': len(rows), 'errors': sum(r['status'] >= 400 for r in rows),
            'mean_ms': round(statistics.mean(values), 3),
            'p95_ms': values[math.ceil(len(values) * .95) - 1], 'max_ms': max(values),
            'sql_count': sum(r['sql_count'] for r in rows),
            'sql_ms': round(sum(r['sql_ms'] for r in rows), 3)}


def report(directory, benchmark_id=None):
    rows, seen = [], set()
    for path in sorted(Path(directory).glob('access-*.jsonl*')):
        with path.open(encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f'{path.name}:{number} 不完整日志；请对停止写入的快照运行统计') from exc
                if benchmark_id and row['benchmark_id'] != benchmark_id:
                    continue
                if row['request_id'] not in seen:
                    seen.add(row['request_id']); rows.append(row)
    if not rows:
        raise ValueError('没有符合条件的访问记录')
    groups = {}
    for row in rows:
        key = (row['username'] or '<anonymous>', row['client_id'] or row['remote_ip'], row['client_os'])
        groups.setdefault(key, []).append(row)
    return {'benchmark_id': benchmark_id, 'overall': summarize(rows),
            'worker_pids': sorted({r['pid'] for r in rows}),
            'clients': [{'username': k[0], 'client_id': k[1], 'os': k[2], **summarize(v)} for k, v in sorted(groups.items())],
            'note': '服务端耗时含鉴权/连接池等待/查询/响应序列化，不含网络传输；SQL耗时仅游标执行，非整个事务。客户端ID与OS用于观测，不作为身份认证。'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log-dir', type=Path, required=True)
    parser.add_argument('--benchmark-id')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = report(args.log_dir, args.benchmark_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
