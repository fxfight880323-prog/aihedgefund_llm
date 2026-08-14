"""Batch-test all 妙想(MX) MCP tools using the efficient, confirmed-working pattern.

CONFIRMED PATTERN (always use this):
  - JSON-RPC over POST to https://mxapi.eastmoney.com/mxds/mcp
  - Header: em_api_key
  - json.dumps(..., ensure_ascii=True)   <-- CRITICAL: UTF-8 raw Chinese => 400
  - tools/call arguments = {"query": "<natural language>"}  (only param)
  - Stateless transport: each request can be its own session.

Each tool gets one representative query; we print status / isError / content.
"""

from __future__ import annotations

import json

import requests

URL = "https://mxapi.eastmoney.com/mxds/mcp"
KEY = "EM_KEY_REDACTED"


def call_tool(name: str, query: str):
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "em_api_key": KEY,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": {"query": query}},
    }
    r = s.post(URL, data=json.dumps(payload, ensure_ascii=True), timeout=120)
    print(f"\n{'='*70}")
    print(f"TOOL: {name}")
    print(f"QUERY: {query}")
    print(f"STATUS: {r.status_code}")
    try:
        data = json.loads(r.text)
    except json.JSONDecodeError:
        print("RAW (tail):", r.text[-500:])
        return
    if "error" in data:
        print("error:", json.dumps(data["error"], ensure_ascii=False)[:500])
        return
    if "message" in data and data.get("message"):
        # framework-level 400 wrapper
        print("framework message:", data.get("message"))
        return
    res = data.get("result", {})
    print("isError:", res.get("isError"))
    for c in res.get("content", []):
        print("---- content ----")
        print(c.get("text", "")[:1500])


# Representative query per tool. (mx_us/hk/ashare/fund/bond/index finance_data,
# macro, screener, news, notice, comprehensive.)
TESTS = [
    ("mx_us_finance_data",          "苹果(AAPL)和特斯拉(TSLA)最新总市值、市盈率"),
    ("mx_hk_finance_data",          "腾讯控股(00700)最新收盘价、市盈率、市净率"),
    ("mx_ashare_finance_data",      "宁德时代(300750)最新市盈率、市净率、总市值"),
    ("mx_fund_finance_data",        "易方达蓝筹精选(005827)最新单位净值、近1年收益率"),
    ("mx_bond_finance_data",        "国债逆回购GC001最新年化收益率"),
    ("mx_index_block_finance_data", "沪深300指数最新收盘价、市盈率"),
    ("mx_macro_data",               "中国最近一期CPI同比、PPI同比"),
    ("mx_stocks_screener",          "A股市盈率最低的5只股票"),
    ("mx_finance_search_news",      "贵州茅台最新相关新闻3条"),
    ("mx_finance_search_notice",    "贵州茅台最新公告3条"),
    ("mx_comprehensive_finance_data", "华为技术有限公司的企业基本信息"),
]

for name, q in TESTS:
    try:
        call_tool(name, q)
    except Exception as exc:
        print(f"\n{'='*70}\nTOOL: {name}\nEXCEPTION: {exc}")
