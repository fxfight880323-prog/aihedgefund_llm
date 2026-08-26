"""Extract full feature table for 008272 core holdings (real data).

A-shares: valuation panel (PE/PB/percentile) + consensus + wide_financial
HK: tencent quote (PE/PB/dividend yield)
Output: _lx_analysis.json
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")

CORE = json.load(open(os.path.join(BASE, "_lx_core.json"), encoding="utf-8"))
NAME = {h["code"]: h["name"] for h in CORE}
PCT = {h["code"]: h.get("pct_nav") for h in CORE}

FIN_KEYS = {
    "roe_yearly": "s_fa_roe_yearly",
    "roe": "s_fa_roe",
    "roic_yearly": "s_fa_roic_yearly",
    "grossmargin": "s_fa_grossprofitmargin",
    "netmargin": "s_fa_netprofitmargin",
    "ocf2profit": "s_fa_ocftoprofit",
    "ocf2or": "s_fa_ocftoor",
    "yoy_or": "s_fa_yoyor",
    "yoy_np": "s_fa_yoynetprofit",
    "debt2assets": "s_fa_debttoassets",
    "assetsturn": "s_fa_assetsturn",
    "fcff": "s_fa_fcff",
    "ocfps": "s_fa_ocfps",
    "eps": "s_fa_eps_basic",
    "deducted_profit": "s_fa_deductedprofit",
    "profittogr": "s_fa_profittogr",
}


def hk_quote(codes):
    out = {}
    for i in range(0, len(codes), 10):
        batch = codes[i:i + 10]
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        req = urllib.request.Request(url, headers={"Referer": "https://gu.qq.com"})
        raw = urllib.request.urlopen(req, timeout=30).read().decode("gbk", errors="replace")
        for line in raw.strip().split(";"):
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            code = key.split("_")[-1]
            f = val.strip('"').split("~")
            try:
                out[code] = {
                    "name": f[1], "price": float(f[3]),
                    "pe_ttm": float(f[39]) if f[39] else None,
                    "pb": float(f[43]) if f[43] else None,
                    "div_yield": float(f[47]) if f[47] else None,
                }
            except (ValueError, IndexError):
                out[code] = {"name": f[1] if len(f) > 1 else code}
    return out


def main():
    # ---- A-share valuation ----
    val = pd.read_parquet(os.path.join(BASE, "_lx_val.parquet"))
    val["date"] = pd.to_datetime(val["date"])
    latest = val.sort_values("date").groupby("stock_code").tail(1)
    val_p = val.copy()
    val_p["pe_rank"] = val_p.groupby("stock_code")["pe_ttm"].rank(pct=True)
    val_p["pb_rank"] = val_p.groupby("stock_code")["pb"].rank(pct=True)
    lastp = val_p.sort_values("date").groupby("stock_code").tail(1).set_index("stock_code")
    latest = latest.set_index("stock_code")

    # ---- consensus ----
    con = json.load(open(os.path.join(BASE, "_lx_consensus.json"), encoding="utf-8"))["records"]
    con_df = pd.DataFrame(con).set_index("stock_code") if con else pd.DataFrame()

    # ---- wide financial ----
    fin = json.load(open(os.path.join(BASE, "_lx_financial.json"), encoding="utf-8"))

    rows = []
    for h in CORE:
        code, name = h["code"], h["name"]
        row = {"code": code, "name": name, "market": "A股" if code.endswith((".SZ", ".SH", ".BJ")) else "港股",
               "pct_nav": PCT.get(code), "citics_l1": h.get("citics_l1")}
        if code in latest.index:
            lv = latest.loc[code]
            lp = lastp.loc[code]
            row.update({
                "pe_ttm": round(float(lv["pe_ttm"]), 1) if pd.notna(lv["pe_ttm"]) else None,
                "pb": round(float(lv["pb"]), 2) if pd.notna(lv["pb"]) else None,
                "total_mv_yi": round(float(lv["total_mv"]) / 10000, 0),
                "pe_pct_3y": round(float(lp["pe_rank"]) * 100, 0) if pd.notna(lp["pe_rank"]) else None,
                "pb_pct_3y": round(float(lp["pb_rank"]) * 100, 0) if pd.notna(lp["pb_rank"]) else None,
            })
        if code in con_df.index:
            c = con_df.loc[code]
            for col, key in [("con_roe", "con_roe"), ("con_np_yoy", "con_np_yoy"),
                             ("con_peg", "con_peg"), ("np_revision_4w", "np_revision_4w"),
                             ("con_pe", "con_pe")]:
                v = c.get(key) if hasattr(c, "get") else None
                try:
                    row[key] = round(float(v), 1) if v is not None and str(v) != "nan" else None
                except (TypeError, ValueError):
                    row[key] = None
        if code in fin:
            fv = fin[code].get("values", {})
            for key, fk in FIN_KEYS.items():
                v = fv.get(fk)
                try:
                    row[key] = round(float(v), 2) if v is not None else None
                except (TypeError, ValueError):
                    row[key] = None
        rows.append(row)

    # ---- HK quote ----
    hk_codes = [h["code"] for h in CORE if h["code"].endswith(".HK")]
    hk = hk_quote(["hk" + c[:4].zfill(5) for c in hk_codes])
    for r in rows:
        if r["market"] == "港股":
            q = hk.get("hk" + r["code"][:4].zfill(5), {})
            r["pe_ttm"] = q.get("pe_ttm")
            r["pb"] = q.get("pb")
            r["div_yield"] = q.get("div_yield")

    df = pd.DataFrame(rows)
    df.to_json(os.path.join(BASE, "_lx_analysis.json"), orient="records", force_ascii=False, indent=1)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    show_cols = ["code", "name", "market", "pct_nav", "citics_l1", "pe_ttm", "pb", "div_yield",
                 "pe_pct_3y", "total_mv_yi", "con_roe", "con_np_yoy", "con_peg",
                 "roe_yearly", "grossmargin", "ocf2profit", "yoy_np"]
    print(df[show_cols].to_string(index=False))
    print("\n=== 汇总 ===")
    a = df[df["market"] == "A股"]
    h = df[df["market"] == "港股"]
    print(f"A股 {len(a)} 只: PE中位 {a['pe_ttm'].median():.1f}, PE<20占比 {(a['pe_ttm'] < 20).mean()*100:.0f}%")
    print(f"  市值中位 {a['total_mv_yi'].median():.0f}亿, 千亿以上 {(a['total_mv_yi'] > 1000).sum()} 只")
    print(f"  PE 3y分位中位 {a['pe_pct_3y'].median():.0f}%, <40%分位 {(a['pe_pct_3y'] < 40).sum()} 只")
    if "con_roe" in a:
        print(f"  预期ROE中位 {a['con_roe'].median():.1f}%, 预期增速中位 {a['con_np_yoy'].median():.1f}%")
    if "roe_yearly" in a:
        print(f"  ROE年度中位 {a['roe_yearly'].median():.1f}%, 毛利率中位 {a['grossmargin'].median():.1f}%")
        print(f"  OCF/净利中位 {a['ocf2profit'].median():.2f}, 净利增速中位 {a['yoy_np'].median():.1f}%")
    if "div_yield" in h:
        print(f"港股 {len(h)} 只: PE中位 {h['pe_ttm'].median():.1f}, 股息率中位 {h['div_yield'].median():.1f}%")


if __name__ == "__main__":
    main()
