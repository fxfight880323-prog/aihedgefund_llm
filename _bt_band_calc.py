# -*- coding: utf-8 -*-
"""898 只候选 × 10 调仓日的 PB 5 年前置分位计算
输入: _bt_band_val/val_*.parquet (18 批日频估值, 2016-08-01 ~ 2026-04-30)
输出: _bt_band_pb_pct.json
  {month: {ticker: {"pb_pct": 0-100, "n": 窗口交易日数, "pb": 当日pb, "anchor": 锚点日}}}
口径 (与 _band_mark.py / _lx_now_band.py 一致):
  pb_pct = (窗口内 pb < 当日pb).mean() * 100   规避: pb_pct > 90
  窗口 = [as_of - 5年, as_of]; 锚点 = 该股 ≤ as_of 最近交易日
  窗口样本 < 60 交易日 → band 无效 (pb_pct=None, 不剔除)
"""
import json, os, sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

PIT_DATES = [
    ("2021-08", "2021-08-31"), ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"), ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"), ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"), ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"), ("2026-04", "2026-04-30"),
]
MIN_N = 60  # 最少窗口样本（交易日）

# ---- 1. 合并 18 批 ----
files = sorted(f for f in os.listdir(BASE + "_bt_band_val") if f.endswith(".parquet"))
dfs = []
for f in files:
    d = pd.read_parquet(BASE + "_bt_band_val/" + f)
    dfs.append(d)
df = pd.concat(dfs, ignore_index=True)
df["date"] = pd.to_datetime(df["date"])
df = df.dropna(subset=["pb"]).sort_values(["stock_code", "date"]).reset_index(drop=True)
print(f"合并日频: {len(df):,} 行, {df['stock_code'].nunique()} 只, "
      f"{df['date'].min().date()} ~ {df['date'].max().date()}")

# ---- 2. 按股票分组（每组日期有序），对每个调仓日切片计算 ----
groups = {tk: g for tk, g in df.groupby("stock_code")}
out: dict[str, dict] = {}
for month, as_of_s in PIT_DATES:
    as_of = pd.Timestamp(as_of_s)
    w0 = as_of - pd.DateOffset(years=5)
    m = {}
    for tk, g in groups.items():
        # 窗口切片（日期已有序，布尔索引即可，~2200 行/股）
        win = g[(g["date"] >= w0) & (g["date"] <= as_of)]
        if len(win) < MIN_N:
            continue
        anchor = win.iloc[-1]          # ≤ as_of 最近交易日
        pb_v = float(anchor["pb"])
        pb_pct = float((win["pb"] < pb_v).mean() * 100)
        m[tk] = {"pb_pct": round(pb_pct, 1), "n": int(len(win)),
                 "pb": round(pb_v, 3), "anchor": str(anchor["date"].date())}
    out[month] = m
    n_valid = sum(1 for v in m.values() if v["pb_pct"] is not None)
    n_high = sum(1 for v in m.values() if v["pb_pct"] is not None and v["pb_pct"] > 90)
    print(f"[{month}] as_of={as_of_s} band有效={n_valid} 只 | PB>90% 规避 {n_high} 只")

json.dump(out, open(BASE + "_bt_band_pb_pct.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n输出 _bt_band_pb_pct.json")
