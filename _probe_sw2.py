# -*- coding: utf-8 -*-
import json, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

URL = "http://159.138.132.129/mcp"
AUTH = "Bearer JKAW7A"

def rpc(payload, sid=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method='POST')
    req.add_header('Content-Type','application/json')
    req.add_header('Accept','application/json, text/event-stream')
    req.add_header('Authorization', AUTH)
    if sid:
        req.add_header('Mcp-Session-Id', sid)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode('utf-8')
        nsid = r.headers.get('Mcp-Session-Id')
        ct = r.headers.get('Content-Type','')
    objs = []
    if 'text/event-stream' in ct:
        for line in body.splitlines():
            line = line.strip()
            if line.startswith('data:'):
                try: objs.append(json.loads(line[5:].strip()))
                except: pass
    elif body.strip():
        objs.append(json.loads(body))
    return objs, nsid

# 1. initialize
msgs, sid = rpc({"jsonrpc":"2.0","id":1,"method":"initialize",
    "params":{"protocolVersion":"2025-03-26","capabilities":{},
              "clientInfo":{"name":"probe","version":"1.0"}}})
print("=== initialize ===")
print("session:", sid)
srv = None
for r in msgs:
    if 'result' in r:
        srv = r['result'].get('serverInfo')
        print("serverInfo:", json.dumps(srv, ensure_ascii=False))
        print("capabilities:", json.dumps(r['result'].get('capabilities',{}), ensure_ascii=False))

# 2. notifications/initialized
rpc({"jsonrpc":"2.0","method":"notifications/initialized"}, sid)

# 3. tools/list
msgs, sid2 = rpc({"jsonrpc":"2.0","id":2,"method":"tools/list"}, sid)
print("\n=== tools/list ===")
for r in msgs:
    if 'result' in r:
        tools = r['result'].get('tools', [])
        print(f"共 {len(tools)} 个工具\n")
        for t in tools:
            print(f"- {t['name']}: {t.get('description','')[:120]}")
            schema = t.get('inputSchema', {})
            props = schema.get('properties', {})
            if props:
                print(f"    参数: {', '.join(props.keys())}")
    elif 'error' in r:
        print("ERROR:", json.dumps(r['error'], ensure_ascii=False))
