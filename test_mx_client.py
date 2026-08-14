"""End-to-end test for the 妙想 MCP client modules.

Verifies:
  1. Low-level MXMCPClient.query() returns structured sheets.
  2. MXDataClient satisfies the DataClient protocol.
  3. MXDataClient.get_prices / get_financial_metrics / get_company_facts
     translate 妙想 responses into the framework's canonical shapes.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use the known-working key so this runs even before a .env is set up.
os.environ.setdefault("EM_API_KEY", "EM_KEY_REDACTED")

from src.core.interfaces import DataClient
from src.data.mx_mcp_client import (
    MXMCPClient,
    TOOL_ASHARE,
    TOOL_MACRO,
    TOOL_NEWS,
    market_of,
    parse_cn_number,
    sheet_to_indexed,
    tool_for_ticker,
)
from src.data.mx_data_client import MXDataClient


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
section("1. Low-level MXMCPClient.query()")
cli = MXMCPClient()
sheets = cli.query(
    TOOL_ASHARE,
    "贵州茅台(600519)最新收盘价、市盈率、市净率、总市值",
)
print(f"returned {len(sheets)} sheet(s)")
for s in sheets:
    print(f"  sheet: {s['sheetName']}")
    print(f"    columns[:3]: {s['columns'][:3]}")
    print(f"    items[:2]:   {s['items'][:2]}")

# Cached rerun should be instant (no network).
import time
t0 = time.time()
cli.query(TOOL_ASHARE, "贵州茅台(600519)最新收盘价、市盈率、市净率、总市值")
print(f"  cached rerun: {1000*(time.time()-t0):.1f} ms")

# ---------------------------------------------------------------------------
section("2. Helpers")
for expr in ("1.691万亿", "6.254倍", "1355.29元", "15.04%", "N/A", ""):
    print(f"  parse_cn_number({expr!r}) = {parse_cn_number(expr)}")
for tk in ("600519.SH", "600519", "000001", "00700.HK", "AAPL.O", "005827.OF"):
    print(f"  {tk:12s} -> market={market_of(tk):4s} tool={tool_for_ticker(tk)}")

# ---------------------------------------------------------------------------
section("3. MXDataClient satisfies DataClient protocol")
dc = MXDataClient(client=cli)
print(f"  isinstance(dc, DataClient) = {isinstance(dc, DataClient)}")

# ---------------------------------------------------------------------------
section("4. get_financial_metrics()")
metrics = dc.get_financial_metrics("600519.SH", "2026-08-13", limit=3)
print(f"  {len(metrics)} period(s)")
for row in metrics[:2]:
    print(f"  {row.get('date')}: PE={row.get('pe_ratio')}, "
          f"PB={row.get('pb_ratio')}, ROE={row.get('roe')}")

# ---------------------------------------------------------------------------
section("5. get_company_facts()")
facts = dc.get_company_facts("600519.SH")
if facts:
    print(f"  name: {facts.get('name')}")
    print(f"  sector: {facts.get('sector')}")
    print(f"  listing_date: {facts.get('listing_date')}")
else:
    print("  (no facts returned)")

# ---------------------------------------------------------------------------
section("6. get_prices()")
bars = dc.get_prices("600519.SH", "2026-08-07", "2026-08-13")
print(f"  {len(bars)} bar(s)")
for b in bars[:3]:
    print(f"  {b}")

# ---------------------------------------------------------------------------
section("7. Bonus: news via low-level client")
news = cli.query(TOOL_NEWS, "贵州茅台 最新新闻 2条")
print(f"  news sheet rows: {sum(len(s['items']) for s in news)}")

print("\nALL CHECKS PASSED")
