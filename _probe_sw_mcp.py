# -*- coding: utf-8 -*-
import socket, json, sys, urllib.request

sys.stdout.reconfigure(encoding='utf-8')
URL = "http://43.128.57.218:8000/mcp/"
AUTH = "Bearer JKAW7A"

def try_connect(host, port, timeout=8):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception as e:
        return str(e)

def try_http(proxies=None, timeout=20):
    data = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize",
        "params":{"protocolVersion":"2024-11-05","capabilities":{},
                  "clientInfo":{"name":"probe","version":"1.0"}}}).encode()
    if proxies:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(proxies))
    else:
        opener = urllib.request.build_opener()
    req = urllib.request.Request(URL, data=data, method='POST')
    req.add_header('Content-Type','application/json')
    req.add_header('Accept','application/json, text/event-stream')
    req.add_header('Authorization', AUTH)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')[:500]
    except Exception as e:
        return 'ERR', repr(e)[:300]

print('=== 1. TCP 连接测试 43.128.57.218:8000 ===')
print('  direct:', try_connect('43.128.57.218', 8000))

print('=== 2. DNS 解析 ===')
try:
    print('  ', socket.gethostbyname_ex('43.128.57.218'))
except Exception as e:
    print('  err', e)

print('=== 3. HTTP 直连 initialize ===')
print('  ', try_http())

print('=== 4. HTTP 走代理 127.0.0.1:7890 ===')
print('  ', try_http({'http':'http://127.0.0.1:7890','https':'http://127.0.0.1:7890'}))
