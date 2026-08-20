"""Fetch consensus forecast snapshots (PIT) from juzi-mcp for F/C-Score backtest.

Calls factor_get_consensus_forecast for each rebalance period's candidate pool,
caching to _bt_cscore_consensus.json.

Run (needs .env with JUZI_MCP_URL / JUZI_MCP_TOKEN, or reads ~/.workbuddy/mcp.json):
    python examples/fetch_consensus.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "_bt_cscore_consensus.json")
TICKER_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "_cs_ticker_lists.json")

# (month, as_of)
PIT = [
    ("2021-08", "2021-08-31"),
    ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"),
    ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"),
    ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"),
    ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"),
    ("2026-04", "2026-04-30"),
]


def load_creds():
    """Get juzi-mcp URL + token from ~/.workbuddy/mcp.json."""
    p = os.path.expanduser("~/.workbuddy/mcp.json")
    cfg = json.load(open(p, encoding="utf-8"))
    c = cfg["mcpServers"]["juzi-mcp"]
    url = c["url"]
    token = c["headers"]["Authorization"].replace("Bearer ", "")
    return url, token


class JuziHTTP:
    """Minimal MCP streamable-http client for juzi-mcp."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.session_id: str | None = None
        self._id = 0
        self._initialize()

    def _post(self, body: dict, want_json: bool = True):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": ("application/json, text/event-stream" if want_json
                       else "application/json"),
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"),
            headers=headers, method="POST")
        resp = urllib.request.urlopen(req, timeout=180)
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        raw = resp.read().decode("utf-8")
        return self._parse_sse(raw)

    @staticmethod
    def _parse_sse(raw: str):
        """MCP http responses may be SSE-framed; extract the JSON payload."""
        # Try direct JSON first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # SSE: lines of "data: {...}"
        out = None
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    out = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return out

    def _initialize(self):
        self._post({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "fscore-bt", "version": "1.0"},
            },
        })
        self._post({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })

    def call_tool(self, name: str, args: dict) -> dict:
        self._id += 1
        resp = self._post({
            "jsonrpc": "2.0", "id": self._id, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        })
        if not resp or "result" not in resp:
            raise RuntimeError(f"bad response: {str(resp)[:300]}")
        content = resp["result"].get("content", [])
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except json.JSONDecodeError:
                    return {"raw": item["text"]}
        return {"raw": str(content)[:500]}


def main():
    url, token = load_creds()
    cli = JuziHTTP(url, token)
    print("connected to juzi-mcp")

    ticker_lists = json.load(open(TICKER_FILE, encoding="utf-8"))

    # Load incremental cache
    cache: dict = {}
    if os.path.exists(OUT_FILE):
        cache = json.loads(open(OUT_FILE, encoding="utf-8").read())
        print(f"  已缓存 {len(cache)} 期")

    for month, as_of in PIT:
        if month in cache and cache[month].get("records"):
            print(f"  [{month}] 已缓存 ({len(cache[month]['records'])} 条)")
            continue
        tickers = ticker_lists.get(month, {}).get("tickers", [])
        if not tickers:
            print(f"  [{month}] 无候选列表，跳过")
            continue

        print(f"  [{month}] 拉取 {len(tickers)} 只 @ {as_of} ...")
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_consensus_forecast", {
                    "stock_codes": tickers,
                    "as_of_date": as_of,
                    "format": "inline",
                })
                records = out.get("records", [])
                if records:
                    cache[month] = {
                        "as_of": as_of,
                        "snapshot_date": out.get("snapshot_date"),
                        "records": records,
                    }
                    json.dump(cache, open(OUT_FILE, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                    print(f"    → {len(records)} 条 (snapshot "
                          f"{out.get('snapshot_date')})")
                    break
                print(f"    尝试 {attempt+1}: 0 条，重试...")
                time.sleep(5)
            except Exception as e:
                print(f"    尝试 {attempt+1} 失败: {e}")
                time.sleep(8)
        time.sleep(2)

    print(f"\n完成: {len(cache)} 期 → {OUT_FILE}")


if __name__ == "__main__":
    main()
