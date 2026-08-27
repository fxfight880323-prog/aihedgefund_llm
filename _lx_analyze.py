"""Analyze 008272 (刘旭) core-holding profile & validate first-principle signals.

Reads: _lx_core.json / _lx_val.parquet / _lx_consensus.json / _lx_financial.json
Output: _lx_analysis.json (statistics + per-stock feature table)
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")


def load_core():
    return json.load(open(os.path.join(BASE, "_lx_core.json"), encoding="utf-8"))


def main():
    core = load_core()
    df = pd.DataFrame(core)
    df["mv"] = df["market_value"] / 1e8  # 亿元

    print("=" * 70)
    print("一、持仓基本统计")
    print(f"核心持仓 {len(df)} 只, 合计市值 {df['mv'].sum():.1f} 亿")
    print(f"前十大占净值合计 {df[df['pct_nav'].notna()].sort_values('pct_nav', ascending=False).head(10)['pct_nav'].sum():.1f}%")

    # 行业分布 (中信 L1)
    ind = df.groupby("citics_l1")["mv"].sum().sort_values(ascending=False)
    print("\n行业分布(按市值, 中信L1):")
    for k, v in ind.items():
        n = (df["citics_l1"] == k).sum()
        print(f"  {k}: {v:.1f}亿 ({n}只)")

    # 市场分布
    mkt = df["code"].str[-2:].map({".SZ": "深A", ".SH": "沪A", ".BJ": "北A", ".HK": "港股"})
    print("\n市场分布:")
    print(mkt.value_counts().to_string())

    # ---- 估值面板 ----
    val = pd.read_parquet(os.path.join(BASE, "_lx_val.parquet"))
    val["date"] = pd.to_datetime(val["date"])
    val["total_mv_yi"] = val["total_mv"] / 10000.0  # 万元->亿

    latest = val.sort_values("date").groupby("stock_code").tail(1).set_index("stock_code")
    print("\n二、最新估值 (2026-08-19 附近):")
    stats = {}
    for code, row in latest.iterrows():
        stats[code] = {"pe_ttm": round(row["pe_ttm"], 1), "pb": round(row["pb"], 2),
                       "total_mv_yi": round(row["total_mv_yi"], 0)}
    pe = latest["pe_ttm"].dropna()
    print(f"  PE_TTM: 中位数 {pe.median():.1f}, 均值 {pe.mean():.1f}, "
          f"<20的占比 {(pe < 20).mean()*100:.0f}%")
    print(f"  市值: 中位数 {latest['total_mv_yi'].median():.0f}亿, 千亿以上 "
          f"{(latest['total_mv_yi'] > 1000).sum()} 只")

    # 3年估值分位
    val_p = val.copy()
    val_p["pe_rank"] = val_p.groupby("stock_code")["pe_ttm"].rank(pct=True)
    val_p["pb_rank"] = val_p.groupby("stock_code")["pb"].rank(pct=True)
    lastp = val_p.sort_values("date").groupby("stock_code").tail(1).set_index("stock_code")
    print("\n  当前 PE 处于自身2.6y分位:")
    q = lastp["pe_rank"].dropna()
    print(f"  中位分位 {q.median()*100:.0f}%, <50%分位占比 {(q < 0.5).mean()*100:.0f}%")

    # ---- 一致预期 ----
    con = json.load(open(os.path.join(BASE, "_lx_consensus.json"), encoding="utf-8"))["records"]
    if con:
        con_df = pd.DataFrame(con)
        print("\n三、一致预期 (2026FY):")
        for col, name in [("con_roe", "预期ROE"), ("con_np_yoy", "预期净利增速"),
                          ("con_peg", "PEG"), ("np_revision_4w", "4周预期修正")]:
            if col in con_df.columns:
                s = pd.to_numeric(con_df[col], errors="coerce").dropna()
                if len(s):
                    print(f"  {name}: 中位数 {s.median():.1f}% | "
                          f"<30%占比 {(s < 30).mean()*100:.0f}%" if col != "con_peg"
                          else f"  {name}: 中位数 {s.median():.2f}")

    # ---- 财务宽表 top12 ----
    fin = json.load(open(os.path.join(BASE, "_lx_financial.json"), encoding="utf-8"))
    print(f"\n四、财务宽表缓存 {len(fin)} 只, 字段示例:")
    for code, v in list(fin.items())[:2]:
        if isinstance(v, dict):
            keys = list(v.keys())[:20]
            print(f"  {code}: {keys}")

    json.dump({"latest_val": stats}, open(os.path.join(BASE, "_lx_latest_val.json"), "w"),
              ensure_ascii=False, indent=1)
    print("\nDONE")


if __name__ == "__main__":
    main()
