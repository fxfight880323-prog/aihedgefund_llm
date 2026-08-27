"""Style-Rotation 数据拉取：juzi 全市场日频面板 (2010 -> 最新).

- factor_get_valuation_panel   (universe=a_share_all, 按年分块, parquet)
- factor_get_return_panel      (含 industry_l1 + forward_return_20d, parquet)

输出: _sr_cache/val_{year}.parquet / _sr_cache/ret_{year}.parquet
运行: C:/Users/xfugm/.workbuddy/binaries/python/envs/default/Scripts/python.exe _sr_fetch_juzi.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "_sr_cache")
os.makedirs(CACHE, exist_ok=True)

YEARS = list(range(2010, 2027))
END_2026 = "2026-08-25"


def load_creds():
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
        self.session_id = None
        self._id = 0
        self._initialize()

    def _post(self, body: dict):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"),
            headers=headers, method="POST")
        resp = urllib.request.urlopen(req, timeout=900)
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        raw = resp.read().decode("utf-8")
        return self._parse_sse(raw)

    @staticmethod
    def _parse_sse(raw: str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
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
        self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "style-rot", "version": "1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, args: dict) -> dict:
        self._id += 1
        resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                           "params": {"name": name, "arguments": args}})
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


def download(url: str, path: str):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def fetch_panel(cli, tool, args, out_path, label):
    if os.path.exists(out_path) and os.path.getsize(out_path) > 200_000:
        print(f"[skip] {label} (cached {os.path.getsize(out_path)//1024}KB)", flush=True)
        return True
    for attempt in range(3):
        try:
            out = cli.call_tool(tool, args)
            url = None
            if isinstance(out, dict):
                url = out.get("download_url") or out.get("artifact", {}).get("download_url") \
                      if isinstance(out.get("artifact"), dict) else out.get("download_url")
                if url is None:
                    # 兜底: 扫描所有字符串字段
                    def find_url(o):
                        if isinstance(o, str) and o.startswith("http"):
                            return o
                        if isinstance(o, dict):
                            for v in o.values():
                                u = find_url(v)
                                if u:
                                    return u
                        return None
                    url = find_url(out)
            if not url:
                print(f"  [{label}] 无 download_url, keys={list(out.keys()) if isinstance(out, dict) else type(out)}", flush=True)
                print(f"  resp head: {str(out)[:400]}", flush=True)
                time.sleep(5)
                continue
            download(url, out_path)
            sz = os.path.getsize(out_path)
            print(f"  [{label}] -> {sz//1024}KB (count={out.get('count') if isinstance(out, dict) else '?'})", flush=True)
            return True
        except Exception as e:
            print(f"  [{label}] 尝试{attempt+1}失败: {e}", flush=True)
            time.sleep(10)
    return False


def main():
    url, token = load_creds()
    cli = JuziHTTP(url, token)
    print("connected to juzi-mcp", flush=True)

    fails = []
    for year in YEARS:
        s = f"{year}-01-01"
        e = f"{year}-12-31" if year < 2026 else END_2026
        ok1 = fetch_panel(cli, "factor_get_valuation_panel",
                          {"universe": "a_share_all", "start_date": s, "end_date": e,
                           "format": "parquet"},
                          os.path.join(CACHE, f"val_{year}.parquet"), f"val {year}")
        ok2 = fetch_panel(cli, "factor_get_return_panel",
                          {"universe": "a_share_all", "start_date": s, "end_date": e,
                           "return_horizons": [20], "include_industry": True,
                           "format": "parquet"},
                          os.path.join(CACHE, f"ret_{year}.parquet"), f"ret {year}")
        if not (ok1 and ok2):
            fails.append(year)
        time.sleep(1)

    print(f"\n完成. 失败年份: {fails}", flush=True)


if __name__ == "__main__":
    main()
