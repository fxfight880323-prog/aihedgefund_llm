"""Fetch real fundamental profile for 008272 (刘旭) core holdings.

Data sources (juzi-mcp, real data, PIT):
  1. factor_get_valuation_panel   -> PE_TTM / PB / total_mv (batch, 3y history)
  2. factor_get_consensus_forecast-> con_roe / con_np_yoy / con_peg / np_revision_4w (batch)
  3. factor_get_wide_financial    -> ROE / gross margin / ocf/net_profit (per-stock, top A-share holdings)

Output: _lx_profile_cache.json
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import load_creds, JuziHTTP  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lx_profile_cache.json")
HOLDINGS = r"C:\Users\xfugm\.workbuddy\workspace\files\91232\6078897d-8e67-4781-8f33-7be6ca03bd08\_fund_008272_holdings_2025AR.json"

# core holdings: market_value >= 1M CNY (exclude IPO lottery positions)
CORE_MV = 100_0000


def main():
    holdings = json.load(open(HOLDINGS, encoding="utf-8"))["holdings"]
    core = [h for h in holdings if (h.get("market_value") or 0) >= CORE_MV]
    core.sort(key=lambda h: -(h.get("market_value") or 0))
    print(f"核心持仓 {len(core)} 只 (市值>=100万)")
    for h in core:
        print(f"  {h['code']} {h['name']} {h.get('pct_nav')}%")

    a_shares = [h["code"] for h in core if h["code"].endswith((".SZ", ".SH", ".BJ"))]
    hk_shares = [h["code"] for h in core if h["code"].endswith(".HK")]
    print(f"\nA股 {len(a_shares)} 只, 港股 {len(hk_shares)} 只")

    url, token = load_creds()
    cli = JuziHTTP(url, token)
    print("connected to juzi-mcp\n")

    cache = {}
    if os.path.exists(OUT):
        cache = json.load(open(OUT, encoding="utf-8"))
        print(f"已缓存: {list(cache.keys())}")

    # ---- 1. valuation panel: 3y of PE_TTM/PB/total_mv for A-share core ----
    if "valuation" not in cache and a_shares:
        print(f"[1] 估值面板 {len(a_shares)} 只 × 3y ...")
        out = cli.call_tool("factor_get_valuation_panel", {
            "stock_codes": a_shares,
            "start_date": "2023-01-01",
            "end_date": "2026-08-19",
            "format": "parquet",
        })
        # parquet -> download_url
        if isinstance(out, dict) and out.get("download_url"):
            cache["valuation"] = {"source": "parquet", "download_url": out["download_url"],
                                  "n_stocks": len(a_shares)}
            json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"    → parquet URL 已存 (需后续下载)")
        elif isinstance(out, dict) and out.get("records"):
            cache["valuation"] = {"source": "inline", "records": out["records"]}
            json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"    → {len(out['records'])} 条 inline")
        else:
            print(f"    ⚠️ 异常返回: {str(out)[:300]}")
        time.sleep(2)

    # ---- 2. consensus forecast (A-share core) ----
    if "consensus" not in cache and a_shares:
        print(f"[2] 一致预期 {len(a_shares)} 只 ...")
        out = cli.call_tool("factor_get_consensus_forecast", {
            "stock_codes": a_shares,
            "as_of_date": "2026-08-19",
            "forecast_year": 2026,
            "format": "inline",
        })
        recs = out.get("records", [])
        if recs:
            cache["consensus"] = {"as_of": "2026-08-19", "records": recs}
            json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"    → {len(recs)} 条")
        else:
            print(f"    ⚠️ 0 条: {str(out)[:300]}")
        time.sleep(2)

    # ---- 3. wide_financial per top-12 A-share holding ----
    if "financial" not in cache:
        top_a = [h["code"] for h in core if h["code"].endswith((".SZ", ".SH"))][:12]
        print(f"[3] 财务宽表 top-12 A股 ({len(top_a)} 只) ...")
        fin = {}
        for i, code in enumerate(top_a):
            for attempt in range(2):
                try:
                    out = cli.call_tool("factor_get_wide_financial", {
                        "stock_code": code, "end_date": "2026-08-19", "freq": "monthly",
                    })
                    if isinstance(out, dict) and out.get("raw"):
                        out = {"fields": out["raw"]}
                    fin[code] = out
                    print(f"    {i+1}/{len(top_a)} {code} ok")
                    break
                except Exception as e:
                    print(f"    {i+1}/{len(top_a)} {code} fail: {e}")
                    time.sleep(5)
            time.sleep(1)
        cache["financial"] = fin
        json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n完成 → {OUT}")
    print("缓存键:", list(cache.keys()))


if __name__ == "__main__":
    main()
