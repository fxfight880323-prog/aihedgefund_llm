# -*- coding: utf-8 -*-
import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
URL = "http://159.138.132.129/mcp/"
AUTH = "Bearer JKAW7A"

FACTORS = ["估值","低波","低流动性","分析师","动量","反转","市值","成长","盈利","红利",
           "筹码成本差","筹码成本","机构筹码集中度","筹码合成","行业轮动","GBM量价"]

def rpc(payload, sid=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, method='POST')
    req.add_header('Content-Type','application/json'); req.add_header('Accept','application/json, text/event-stream'); req.add_header('Authorization', AUTH)
    if sid: req.add_header('Mcp-Session-Id', sid)
    with urllib.request.urlopen(req, timeout=120) as r:
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

msgs, sid = rpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"ic-rank","version":"1.0"}}})
rpc({"jsonrpc":"2.0","method":"notifications/initialized"}, sid)

all_data = {}
for f in FACTORS:
    for attempt in range(3):
        try:
            msgs, _ = rpc({"jsonrpc":"2.0","id":2,"method":"tools/call",
                "params":{"name":"get_factor_ic","arguments":{"factor":f,"start":"2020-01-31","end":"2026-08-31"}}}, sid)
            txt = get_text(msgs)
            obj = json.loads(txt)
            if 'error' in obj:
                print(f"{f}: ERROR {obj['error'][:80]}", flush=True)
                all_data[f] = None
            else:
                all_data[f] = obj
                m = obj['metadata']
                print(f"{f}: IC={m['ic_mean']:.4f} IR={m['ir']:.4f} pos={m['positive_ratio']:.2f} months={m['valid_months']}", flush=True)
            break
        except Exception as e:
            if attempt==2:
                print(f"{f}: FAIL {str(e)[:80]}", flush=True)
                all_data[f] = None
            time.sleep(2)
    time.sleep(0.2)

with open('_factor_ic_all.json','w',encoding='utf-8') as fp:
    json.dump(all_data, fp, ensure_ascii=False)
print("\nSAVED _factor_ic_all.json")
