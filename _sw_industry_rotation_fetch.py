# -*- coding: utf-8 -*-
"""
申万行业轮动因子 全市场个股值拉取（2026-08-31 月末快照）
- 用 get_factor_value 批量查「行业轮动」因子 z-score
- ts_codes 来自万得全A PIT universe (_bt_lx_now_universe.json, 5533只)
- 分批调用，每批 500 只，失败重试
"""
import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

URL = "http://159.138.132.129/mcp/"
AUTH = "Bearer JKAW7A"
FACTOR = "行业轮动"
DATE = "2026-08-31"
BATCH = 100  # 申万 get_factor_value 单批硬上限 120 条，用 100 留余量

def rpc(payload, sid=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json, text/event-stream')
    req.add_header('Authorization', AUTH)
    if sid:
        req.add_header('Mcp-Session-Id', sid)
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read().decode('utf-8')
        nsid = r.headers.get('Mcp-Session-Id')
        ct = r.headers.get('Content-Type', '')
    objs = []
    if 'text/event-stream' in ct:
        for line in body.splitlines():
            line = line.strip()
            if line.startswith('data:'):
                try:
                    objs.append(json.loads(line[5:].strip()))
                except Exception:
                    pass
    elif body.strip():
        objs.append(json.loads(body))
    return objs, nsid

def get_text(msgs):
    for r in msgs:
        if 'result' in r:
            for c in r['result'].get('content', []):
                if c.get('type') == 'text':
                    return c['text']
        if 'error' in r:
            return 'ERROR: ' + json.dumps(r['error'], ensure_ascii=False)
    return None

# 初始化会话
msgs, sid = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                            "clientInfo": {"name": "sw-industry-rot", "version": "1.0"}}})
rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
print("session:", sid)

# 读取 universe
univ = json.load(open('_bt_lx_now_universe.json', encoding='utf-8'))
codes = univ['members']
print(f"universe {len(codes)} 只")

all_records = []
fail_batches = []

for i in range(0, len(codes), BATCH):
    batch = codes[i:i+BATCH]
    bid = i // BATCH + 1
    ok = False
    for attempt in range(3):
        try:
            msgs, _ = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "get_factor_value",
                                      "arguments": {"factors": [FACTOR],
                                                    "ts_codes": batch,
                                                    "date": DATE}}}, sid)
            txt = get_text(msgs)
            if txt and txt.startswith('ERROR'):
                print(f"  batch {bid}: {txt[:100]}", flush=True)
                if 'required' in txt or 'validation' in txt.lower():
                    # 参数问题不重试
                    fail_batches.append((i, txt[:200]))
                    break
                time.sleep(2)
                continue
            obj = json.loads(txt)
            recs = obj.get('records', [])
            all_records.extend(recs)
            print(f"  batch {bid}: {len(batch)} 只 -> 返回 {len(recs)} 条", flush=True)
            ok = True
            break
        except Exception as e:
            if attempt == 2:
                print(f"  batch {bid}: FAIL {str(e)[:80]}", flush=True)
                fail_batches.append((i, str(e)[:200]))
            time.sleep(2)
    if not ok:
        # 缩小批量重试
        for j in range(0, len(batch), 100):
            sub = batch[j:j+100]
            for attempt in range(3):
                try:
                    msgs, _ = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                   "params": {"name": "get_factor_value",
                                              "arguments": {"factors": [FACTOR],
                                                            "ts_codes": sub,
                                                            "date": DATE}}}, sid)
                    txt = get_text(msgs)
                    if txt and txt.startswith('ERROR'):
                        time.sleep(2)
                        continue
                    obj = json.loads(txt)
                    all_records.extend(obj.get('records', []))
                    break
                except Exception:
                    time.sleep(2)
    time.sleep(0.3)

# 去重（按 ts_code）
seen = {}
for rec in all_records:
    seen[rec['ts_code']] = rec

out = {
    'factor': FACTOR,
    'date': DATE,
    'n_requested': len(codes),
    'n_got': len(seen),
    'records': list(seen.values()),
    'fail_batches': fail_batches,
}

with open('_sw_industry_rotation_values.json', 'w', encoding='utf-8') as fp:
    json.dump(out, fp, ensure_ascii=False)

print(f"\n完成: 请求 {len(codes)} 只, 拿到 {len(seen)} 只, 失败批次 {len(fail_batches)}")
