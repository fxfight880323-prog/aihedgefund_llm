# -*- coding: utf-8 -*-
import json, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

URL = "http://159.138.132.129/mcp/"   # 尾斜杠
AUTH = "Bearer JKAW7A"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    pass

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

msgs, sid = rpc({"jsonrpc":"2.0","id":1,"method":"initialize",
    "params":{"protocolVersion":"2025-03-26","capabilities":{},
              "clientInfo":{"name":"probe","version":"1.0"}}})
print("=== initialize ===")
print("session:", sid)
for r in msgs:
    if 'result' in r:
        print("serverInfo:", json.dumps(r['result'].get('serverInfo'), ensure_ascii=False))
        print("instructions:", (r['result'].get('instructions') or '')[:300])
    elif 'error' in r:
        print("ERROR:", json.dumps(r['error'], ensure_ascii=False))

rpc({"jsonrpc":"2.0","method":"notifications/initialized"}, sid)

msgs, _ = rpc({"jsonrpc":"2.0","id":2,"method":"tools/list"}, sid)
print("\n=== tools/list ===")
for r in msgs:
    if 'result' in r:
        tools = r['result'].get('tools', [])
        print(f"共 {len(tools)} 个工具\n")
        for t in tools:
            print(f"- {t['name']}")
            print(f"    {t.get('description','')[:200]}")
            props = t.get('inputSchema', {}).get('properties', {})
            if props:
                print(f"    参数: {', '.join(props.keys())}")
    elif 'error' in r:
        print("ERROR:", json.dumps(r['error'], ensure_ascii=False))
