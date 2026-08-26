"""Fetch real fundamental profile for 008272 (刘旭) core holdings - v2.

Data sources (juzi-mcp, real data, PIT):
  1. factor_get_valuation_panel (parquet) -> PE_TTM / PB / total_mv, 2024-01 ~ 2026-08
  2. factor_get_consensus_forecast (inline) -> con_roe / con_np_yoy / con_peg / np_revision_4w
  3. factor_get_wide_financial (per-stock) -> ROE / gross margin / OCF quality

Outputs: _lx_val.parquet / _lx_consensus.json / _lx_financial.json / _lx_core.json
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import load_creds, JuziHTTP  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
HOLDINGS = r"C:\Users\xfugm\.workbuddy\workspace\files\91232\6078897d-8e67-4781-8f33-7be6ca03bd08\_fund_008272_holdings_2025AR.json"
CORE_MV = 100_0000  # >= 1M CNY


def download_parquet(url: str) -> pd.DataFrame:
    with urllib.request.urlopen(url, timeout=300) as r:
        return pd.read_parquet(io.BytesIO(r.read()))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    holdings = json.load(open(HOLDINGS, encoding="utf-8"))["holdings"]
    core = [h for h in holdings if (h.get("market_value") or 0) >= CORE_MV]
    core.sort(key=lambda h: -(h.get("market_value") or 0))
    json.dump(core, open(os.path.join(BASE, "_lx_core.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"核心持仓 {len(core)} 只")

    a_shares = [h["code"] for h in core if h["code"].endswith((".SZ", ".SH", ".BJ"))]
    hk = [h["code"] for h in core if h["code"].endswith(".HK")]
    print(f"A股 {len(a_shares)} 只 | 港股 {len(hk)} 只")

    url, token = load_creds()
    cli = JuziHTTP(url, token)

    # ---- 1. valuation panel -> parquet ----
    val_pq = os.path.join(BASE, "_lx_val.parquet")
    if not os.path.exists(val_pq):
        print(f"[1] 估值面板 {len(a_shares)} 只 x 2.6y (parquet)...")
        out = cli.call_tool("factor_get_valuation_panel", {
            "stock_codes": a_shares,
            "start_date": "2024-01-01",
            "end_date": "2026-08-19",
            "format": "parquet",
        })
        dl = out.get("artifact", {}).get("download_url")
        if not dl:
            print(f"    !!! no download_url: {str(out)[:400]}")
        else:
            df = download_parquet(dl)
            df.to_parquet(val_pq)
            print(f"    -> {len(df)} 行, {df['stock_code'].nunique()} 只 x "
                  f"{df['date'].nunique()} 交易日")
        time.sleep(2)
    else:
        df = pd.read_parquet(val_pq)
        print(f"[1] 已缓存估值面板 {len(df)} 行")

    # ---- 2. consensus forecast ----
    con_f = os.path.join(BASE, "_lx_consensus.json")
    if not os.path.exists(con_f):
        print(f"[2] 一致预期 {len(a_shares)} 只 ...")
        out = cli.call_tool("factor_get_consensus_forecast", {
            "stock_codes": a_shares,
            "as_of_date": "2026-08-19",
            "forecast_year": 2026,
            "format": "inline",
        })
        recs = out.get("records", [])
        json.dump({"as_of": "2026-08-19", "records": recs},
                  open(con_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"    -> {len(recs)} 条")
        time.sleep(2)
    else:
        print(f"[2] 已缓存一致预期 {len(json.load(open(con_f, encoding='utf-8'))['records'])} 条")

    # ---- 3. wide_financial per top-12 A-share ----
    fin_f = os.path.join(BASE, "_lx_financial.json")
    top_a = [h["code"] for h in core if h["code"].endswith((".SZ", ".SH"))][:12]
    if not os.path.exists(fin_f):
        print(f"[3] 财务宽表 top-{len(top_a)} A股 ...")
        fin = {}
        for i, code in enumerate(top_a):
            for attempt in range(3):
                try:
                    out = cli.call_tool("factor_get_wide_financial", {
                        "stock_code": code, "end_date": "2026-08-19", "freq": "monthly",
                    })
                    fin[code] = out
                    print(f"    {i+1}/{len(top_a)} {code} ok")
                    break
                except Exception as e:
                    print(f"    {i+1}/{len(top_a)} {code} fail: {e}")
                    time.sleep(6)
            time.sleep(1)
        json.dump(fin, open(fin_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print(f"[3] 已缓存财务宽表 {len(json.load(open(fin_f, encoding='utf-8')))} 只")

    print("\nDONE")


if __name__ == "__main__":
    main()
