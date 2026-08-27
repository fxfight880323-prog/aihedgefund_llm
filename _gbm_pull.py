# -*- coding: utf-8 -*-
"""直连申万金工 MCP 底层 HTTP，全量拉取 GBM量价 因子值（120只/批，绕过 LLM 循环）。
读取 _gbm_batches/manifest.json，为每个无 _res.json 的批次调用 get_factor_value，
把 records 写入 {batch}_res.json。断点续传：已完成的批次自动跳过。
最后运行 _gbm_assemble.py 汇总为 _bt_gbm_values.json。
"""
import json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
BATCH_DIR = os.path.join(BASE, '_gbm_batches')
URL = "http://43.128.57.218:8000/mcp/"
AUTH = "Bearer JKAW7A"

def rpc(payload, session_id=None):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(URL, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json, text/event-stream')
    req.add_header('Authorization', AUTH)
    if session_id:
        req.add_header('Mcp-Session-Id', session_id)
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode('utf-8')
        sid = resp.headers.get('Mcp-Session-Id')
        ct = resp.headers.get('Content-Type', '')
    if not body.strip():
        return [], sid
    if 'text/event-stream' in ct:
        objs = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith('data:'):
                objs.append(json.loads(line[5:].strip()))
        return objs, sid
    return [json.loads(body)], sid

def extract_records(msgs):
    """从 tools/call 响应中提取 records 数组（兼容多格式）。"""
    for r in msgs:
        if 'result' in r:
            for c in r['result'].get('content', []):
                if c.get('type') == 'text':
                    try:
                        obj = json.loads(c['text'])
                    except Exception:
                        continue
                    if isinstance(obj, list):
                        return obj
                    if isinstance(obj, dict):
                        for k in ('records', 'data', 'result'):
                            if isinstance(obj.get(k), list):
                                return obj[k]
        if 'error' in r:
            raise RuntimeError(f"MCP error: {json.dumps(r['error'], ensure_ascii=False)[:200]}")
    return []

def call_factor(ts_codes, date, session_id):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_factor_value",
                   "arguments": {"date": date, "factors": ["GBM量价"], "ts_codes": ts_codes}}
    }
    msgs, sid = rpc(payload, session_id)
    recs = extract_records(msgs)
    return recs, sid

def main():
    with open(os.path.join(BATCH_DIR, 'manifest.json'), 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    # 初始化会话
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "gbm-puller", "version": "1.0"}}}
    _, sid = rpc(init)
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)

    # 收集待处理批次
    pending = []
    for month, info in manifest.items():
        for bname in info['batches']:
            if not os.path.exists(os.path.join(BATCH_DIR, bname + '_res.json')):
                pending.append((month, bname, info['date']))

    total = len(pending)
    print(f'待处理批次: {total}', flush=True)
    t0 = time.time()
    done, failed = 0, []
    for i, (month, bname, date) in enumerate(pending):
        bpath = os.path.join(BATCH_DIR, bname + '.json')
        with open(bpath, 'r', encoding='utf-8') as f:
            b = json.load(f)
        for attempt in range(3):
            try:
                recs, sid = call_factor(b['ts_codes'], date, sid)
                break
            except Exception as e:
                if attempt == 2:
                    failed.append((bname, str(e)[:120]))
                    recs = None
                    break
                time.sleep(2 * (attempt + 1))
        if recs is None:
            continue
        with open(os.path.join(BATCH_DIR, bname + '_res.json'), 'w', encoding='utf-8') as f:
            json.dump(recs, f, ensure_ascii=False)
        done += 1
        if (i + 1) % 25 == 0 or i == total - 1:
            el = time.time() - t0
            rate = (i + 1) / el
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f'  [{i+1}/{total}] done={done} fail={len(failed)} rate={rate:.1f}批/s eta={eta/60:.1f}min', flush=True)
        time.sleep(0.15)

    print(f'\n完成: {done}/{total}  失败: {len(failed)}  总耗时: {(time.time()-t0)/60:.1f}min')
    for bname, err in failed[:20]:
        print(f'  FAIL {bname}: {err}')

    # 汇总
    print('\n=== 运行 _gbm_assemble.py ===')
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(BASE, '_gbm_assemble.py')],
                       capture_output=True, text=True, encoding='utf-8')
    print(r.stdout)
    if r.returncode != 0:
        print('stderr:', r.stderr[-2000:])

if __name__ == '__main__':
    main()
