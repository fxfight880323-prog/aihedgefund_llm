"""Test 妙想(MX) MCP Server over raw Streamable HTTP with JSON-RPC.

Directly calls https://mxapi.eastmoney.com/mxds/mcp without relying on
Kimi Code CLI's MCP registration, so it works in the current session.
"""

from __future__ import annotations

import json
import os
import sys

import requests

URL = "https://mxapi.eastmoney.com/mxds/mcp"
API_KEY = os.environ.get("EM_API_KEY", "EM_KEY_REDACTED")

session = requests.Session()
session.trust_env = False  # avoid system proxy
session.headers.update({
    "em_api_key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
})


def post(payload: dict):
    """Send a single JSON-RPC message and return the parsed response body."""
    body = json.dumps(payload, ensure_ascii=False)
    print(f"\n>>> POST {URL}\n{body}")
    resp = session.post(URL, data=body, timeout=60)
    print(f"<<< status={resp.status_code}")
    text = resp.text
    print(text[:2000])
    return text


def parse_first_json(text: str):
    """Try to parse first JSON object from the response text."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Maybe multiple JSON objects concatenated or SSE lines
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
        return None


# 1. Initialize
init_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "mx-test", "version": "1.0"},
    },
}
post(init_payload)

# 2. Initialized notification
post({
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
})

# 3. List tools
list_text = post({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {},
})
list_result = parse_first_json(list_text)
if list_result and "result" in list_result:
    tools = list_result["result"].get("tools", [])
    print(f"\n>>> Found {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool.get('name')}: {tool.get('description', '')[:80]}")

    # 4. Try to find a tool for A-stock metrics / valuation
    target = None
    keywords = ["估值", "valuation", "指标", "indicator", "财务", "finance", "基本面", "fundamental", "PB", "ROE", "市盈率", "市净率", "A股"]
    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "")
        combined = (name + " " + desc).lower()
        if any(kw.lower() in combined for kw in keywords):
            target = tool
            print(f"\n>>> Matched tool: {name}")
            break

    if target:
        print(f"\nSchema:\n{json.dumps(target.get('inputSchema', {}), ensure_ascii=False, indent=2)}")
        # Try a generic call; arguments may need adjustment after inspecting schema.
        tool_name = target["name"]
        call_text = post({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {"symbol": "600519.SH"},
            },
        })
        print(f"\nCall result parse: {parse_first_json(call_text)}")
else:
    print("\n>>> Could not list tools.", file=sys.stderr)
