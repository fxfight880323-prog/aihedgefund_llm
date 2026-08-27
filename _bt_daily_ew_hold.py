# -*- coding: utf-8 -*-
"""半年调仓等权全A 日频 nav（与 LX-core 策略严格同口径的池子基准）。
构造：每个调仓触发日等权买入当期 PIT 成分 → 持有到下一调仓触发日（期间无再平衡，权重随价格漂移）。
对比 _bt_daily_ew.py 的每日再平衡等权（含再平衡收益，会高估基准）。
"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
import pandas as pd
import numpy as np

OUT = "_bt_ew_daily"
# ---- 读取全市场日频收益面板 ----
print("读取全市场日频收益面板...")
frames = []
for f in sorted(os.listdir(OUT)):
    if f.endswith(".parquet"):
        df = pd.read_parquet(os.path.join(OUT, f), columns=["date", "stock_code", "daily_return"])
        frames.append(df)
        print(f"  {f}: {len(df)} 行")
all_df = pd.concat(frames, ignore_index=True)
print(f"合并: {len(all_df)} 行 | 股票 {all_df['stock_code'].nunique()}")

wide = all_df.pivot_table(index="date", columns="stock_code", values="daily_return")
wide = wide.sort_index()
print(f"宽表: {wide.shape[0]} 天 × {wide.shape[1]} 只")
wide.to_parquet("_bt_ew_daily/wide_daily_return.parquet")
print("宽表缓存 → _bt_ew_daily/wide_daily_return.parquet")

# ---- PIT 成分与调仓触发日 ----
univ = json.load(open("_bt_winda_universe.json", encoding="utf-8"))
PIT = sorted(univ.keys())
trig_days = {}
for p in PIT:
    asof = univ[p]["as_of"]
    trig = max(d for d in wide.index if d <= asof)
    trig_days[p] = trig
    print(f"  期 {p}: as_of {asof} → 触发日 {trig}（{len(univ[p]['members'])} 只）")

# ---- 逐日迭代：买入持有等权 ----
print("\n计算半年调仓等权全A 日频 nav...")
nav, cur = {}, 1.0
w = None          # 当前权重 dict(Series)
members = None    # 当前持仓集合
ret_cols = wide.columns
idx = list(wide.index)

for i, dt in enumerate(idx):
    # 调仓：触发日当天收盘后按次日开盘换仓（近似：触发日次日生效）
    for p, trig in trig_days.items():
        if dt == trig:
            members = set(univ[p]["members"]) & set(ret_cols)
            n = len(members)
            w = pd.Series(1.0 / n, index=sorted(members))
            break
    if w is None:
        nav[dt] = cur
        continue
    # 当日收益 = 权重 × 成分股当日收益
    rets = wide.loc[dt, w.index].fillna(0.0)
    r_d = float((w * rets).sum())
    # 权重漂移（买入持有，无再平衡）
    w = w * (1.0 + rets) / (1.0 + r_d)
    cur *= (1.0 + r_d)
    nav[dt] = cur

out = {dt: v for dt, v in nav.items() if dt >= "2021-06-01"}
peak, mdd = 1.0, 0.0
for v in out.values():
    peak = max(peak, v)
    if peak > 0:
        mdd = max(mdd, 1.0 - v / peak)
total = out[max(out)] - 1.0
yrs = len(out) / 252.0
ann = (1 + total) ** (1 / yrs) - 1
print(f"\n半年调仓等权全A 日频: 总收益 {total:+.2%} | 年化 {ann:+.2%} | MDD {mdd:.2%} | {len(out)} 天")
json.dump({"nav": out, "total": total, "ann": ann, "mdd": mdd},
          open("_bt_daily_ew_hold_nav.json", "w", encoding="utf-8"), ensure_ascii=False)
print("结果 → _bt_daily_ew_hold_nav.json")
