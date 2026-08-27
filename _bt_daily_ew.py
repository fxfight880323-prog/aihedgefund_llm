# -*- coding: utf-8 -*-
"""下载 6 段全市场日频 parquet → 计算等权全A（PIT 成分）日频 nav。
ew 逻辑对齐月频引擎 _members_at：每天取 as_of ≤ 该日的最近一期 PIT 成分，
等权日收益 = mean(成分股 daily_return)，nav 连乘。
"""
import json, os, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

import pandas as pd

URLS = json.load(open("_bt_daily_ew_urls.json", encoding="utf-8"))
OUT_DIR = "_bt_ew_daily"
os.makedirs(OUT_DIR, exist_ok=True)

def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print(f"  cached {path}")
        return True
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())
    print(f"  saved {path} ({os.path.getsize(path)//1024//1024}MB)")
    return True

for seg, info in URLS.items():
    download(info["url"], f"{OUT_DIR}/{seg}.parquet")

# 读取全部并合并（只保留 date/stock_code/daily_return）
print("\n读取 parquet...")
frames = []
for seg in URLS:
    p = f"{OUT_DIR}/{seg}.parquet"
    df = pd.read_parquet(p, columns=["date", "stock_code", "daily_return"])
    frames.append(df)
    print(f"  {seg}: {len(df)} 行 {df['date'].min()} ~ {df['date'].max()}")
all_df = pd.concat(frames, ignore_index=True)
print(f"合并: {len(all_df)} 行 | 股票 {all_df['stock_code'].nunique()} | "
      f"日期 {all_df['date'].min()} ~ {all_df['date'].max()}")

# PIT 成分
univ = json.load(open("_bt_winda_universe.json", encoding="utf-8"))
PIT = sorted(univ.keys())
print("PIT 期数:", PIT)

def members_at(dt: str) -> set:
    pick = None
    for p in PIT:
        asof = univ[p]["as_of"]
        if asof <= dt:
            pick = p
        else:
            break
    if pick:
        return set(univ[pick]["members"])
    return set()

# 按日分组计算 ew 收益
print("\n计算等权全A 日频 nav...")
g = all_df.groupby("date")
dates = sorted(g.groups.keys())
nav = {}
cur = 1.0
prev_nav = None
rows = []
for dt in dates:
    members = members_at(dt)
    sub = g.get_group(dt)
    if members:
        sub = sub[sub["stock_code"].isin(members)]
    r = sub["daily_return"].dropna()
    if len(r) > 0:
        cur *= (1.0 + float(r.mean()))
    nav[dt] = cur

# 2021-06 前算起（对齐月频 ew 起点逻辑：2021-06 起 nav=1.0）
out = {dt: v for dt, v in nav.items() if dt >= "2021-06-01"}
print(f"ew 日频 nav: {len(out)} 天 {min(out)} ~ {max(out)} | 终值 {out[max(out)]:.4f}")

# MDD
peak, mdd = 1.0, 0.0
for v in out.values():
    peak = max(peak, v)
    mdd = max(mdd, peak / v - 1.0)
total = out[max(out)] - 1.0
yrs = len(out) / 252.0
ann = (1 + total) ** (1 / yrs) - 1
print(f"等权全A 日频: 总收益 {total:+.2%} | 年化 {ann:+.2%} | MDD {mdd:.2%}")

json.dump({"nav": out, "total": total, "ann": ann, "mdd": mdd},
          open("_bt_daily_ew_nav.json", "w", encoding="utf-8"), ensure_ascii=False)
print("结果 → _bt_daily_ew_nav.json")
