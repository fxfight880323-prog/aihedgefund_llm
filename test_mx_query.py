"""Query 妙想(MX) MCP with correct `query` argument.

Diagnostic: a 200 + 'First must not be null' on the first script came from a
bad `symbol` arg. A 400 'Invalid message format' appears when the call is made
*after* a requests.Session has seen the notification POST response. So we use a
brand-new Session per request to keep things clean.
"""

from __future__ import annotations

import json

import requests

URL = "https://mxapi.eastmoney.com/mxds/mcp"
KEY = os.environ.get("EM_API_KEY")


def fresh():
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "em_api_key": KEY,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    return s


def one_shot(payload: dict):
    s = fresh()
    r = s.post(URL, data=json.dumps(payload, ensure_ascii=True), timeout=120)
    return r


# initialize in its own session
one_shot({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "mx-test", "version": "1.0"},
    },
})

# real call in a fresh session, correct `query` argument
r = one_shot({
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {
        "name": "mx_ashare_finance_data",
        "arguments": {"query": "贵州茅台(600519)最新收盘价、市盈率、市净率、总市值"},
    },
})

print("STATUS:", r.status_code)
try:
    data = json.loads(r.text)
except json.JSONDecodeError:
    print("RAW (tail):", r.text[-1000:])
    raise SystemExit(1)

print("keys:", list(data.keys()))
print("message:", data.get("message"))
if "result" in data:
    res = data["result"]
    print("isError:", res.get("isError"))
    for c in res.get("content", []):
        print("---- content ----")
        print(c.get("text", ""))
elif "error" in data:
    print("error:", json.dumps(data["error"], ensure_ascii=False)[:800])
