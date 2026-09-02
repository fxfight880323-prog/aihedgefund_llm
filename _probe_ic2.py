# -*- coding: utf-8 -*-
import json, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
URL = "http://159.138.132.129/mcp/"
AUTH = "Bearer JKAW7A"
def rpc(payload, sid=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method='POST')
    req.add_header('Content-Type','application/json'); req.add_header('Accept','application/json, text/event-stream'); req.add_header('Authorization', AUTH)
    if sid: req.add_header('Mcp-Session-Id', sid)
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode('utf-8'); nsid=r.headers.get('Mcp-Session-Id'); ct=r.headers.get('Content-Type','')
    objs=[]
    if 'text/event-stream' in ct:
        for line in body.splitlines():
            line=line.strip()
            if line.startswith('data:'):
                try: objs.append(json.loads(line[5:].strip()))
                except: pass
    elif body.strip(): objs.append(json.loads(body))
    return objs, nsid
def get_text(msgs):
    for r in msgs:
        if 'result' in r:
            for c in r['result'].get('content',[]):
                if c.get('type')=='text': return c['text']
        if 'error' in r: return 'ERROR: '+json.dumps(r['error'],ensure_ascii=False)
    return None
msgs, sid = rpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"probe","version":"1.0"}}})
rpc({"jsonrpc":"2.0","method":"notifications/initialized"}, sid)
msgs, _ = rpc({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_factor_ic","arguments":{"factor":"估值","start":"2020-01-31","end":"2026-08-31"}}}, sid)
print(get_text(msgs))
