# -*- coding: utf-8 -*-
"""直连申万金工 MCP 底层 HTTP（streamable transport），绕过 WorkBuddy 会话层。
测试 get_factor_value 是否仍被截断到 120 行。若返回 >120 行则截断在客户端层，
可全量直拉；若仍 120 行则截断在服务端工具层。
"""
import json, sys, time, urllib.request

sys.stdout.reconfigure(encoding='utf-8')

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
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode('utf-8')
        sid = resp.headers.get('Mcp-Session-Id')
        ct = resp.headers.get('Content-Type', '')
    if not body.strip():
        return [], sid
    # 解析 JSON 或 SSE
    if 'text/event-stream' in ct:
        # 取 data: 行
        objs = []
        for line in body.splitlines():
            line = line.strip()
            if line.startswith('data:'):
                objs.append(json.loads(line[5:].strip()))
        return objs, sid
    return [json.loads(body)], sid

def main():
    # 1. initialize
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "direct-client", "version": "1.0"},
        }
    }
    res, sid = rpc(init)
    print('initialize:', json.dumps(res, ensure_ascii=False)[:300])
    # 2. initialized 通知
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    rpc(note, sid)
    # 3. tools/call: 300 只探针
    codes = json.load(open('_tmp_gbm_probe300.json', encoding='utf-8'))
    print('probe codes:', len(codes))
    call = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "get_factor_value",
            "arguments": {"date": "2021-08-31", "factors": ["GBM量价"], "ts_codes": codes}
        }
    }
    t0 = time.time()
    res, sid2 = rpc(call, sid)
    dt = time.time() - t0
    print(f'call took {dt:.1f}s, session: {sid2}')
    for r in res:
        if 'result' in r:
            content = r['result'].get('content', [])
            for c in content:
                if c.get('type') == 'text':
                    txt = c['text']
                    try:
                        obj = json.loads(txt)
                        recs = obj.get('records', obj if isinstance(obj, list) else [])
                        print('text len:', len(txt), 'records:', len(recs))
                        meta = obj.get('metadata', obj.get('meta', {}))
                        if meta:
                            print('metadata:', json.dumps(meta, ensure_ascii=False)[:300])
                        if recs:
                            print('first:', json.dumps(recs[0], ensure_ascii=False)[:200])
                            print('last :', json.dumps(recs[-1], ensure_ascii=False)[:200])
                    except Exception as e:
                        print('parse err:', e, 'raw head:', txt[:300])
        elif 'error' in r:
            print('ERROR:', json.dumps(r['error'], ensure_ascii=False)[:300])

if __name__ == '__main__':
    main()
