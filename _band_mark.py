# -*- coding: utf-8 -*-
"""全量估值 band 标记: 对 _band_need.json 的股票集, 由多个 parquet URL 计算 5 年 PE/PB 分位
输出 _band_all.json (key=带后缀 code): pe_pct/pb_pct/flag/cur_pe/cur_pb/n_days
flag 口径(与 _lx_now_band.py 一致):
  规避: PB 5y分位 > 90%  安全边际: PE&PB < 30%  自身低位: PB < 30%
  偏高: PB > 70%  中性: 其余
"""
import json, os, sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

WARN_PB = 90   # 规避阈值
SAFE_PE = 30
SAFE_PB = 30
HIGH_PB = 70

urls = sys.argv[1:]
assert urls, "用法: _band_mark.py <parquet_url...>"

dfs = []
for u in urls:
    df = pd.read_parquet(u)
    df["date"] = pd.to_datetime(df["date"])
    dfs.append(df)
df = pd.concat(dfs, ignore_index=True)
print(f"合并日频: {len(df)} 行, {df['stock_code'].nunique()} 只")

need = json.load(open(BASE + "_band_need.json", encoding="utf-8"))
names = need["names"]

def pct(v, s):
    if v is None or v != v or len(s) == 0:
        return None
    return float((s < v).mean() * 100)

rows = []
for code, g in df.groupby("stock_code"):
    g = g.sort_values("date").dropna(subset=["pe_ttm", "pb"])
    if len(g) == 0:
        continue
    cur = g.iloc[-1]
    pe_v = float(cur["pe_ttm"]) if cur["pe_ttm"] == cur["pe_ttm"] else None
    pb_v = float(cur["pb"]) if cur["pb"] == cur["pb"] else None
    pe_pct = pct(pe_v, g["pe_ttm"])
    pb_pct = pct(pb_v, g["pb"])
    flags = []
    if pb_pct is not None and pb_pct > WARN_PB:
        flags.append("规避")
    if pe_pct is not None and pb_pct is not None and pe_pct < SAFE_PE and pb_pct < SAFE_PB:
        flags.append("安全边际")
    if pb_pct is not None and pb_pct < SAFE_PB:
        flags.append("自身低位")
    if pb_pct is not None and pb_pct > HIGH_PB:
        flags.append("偏高")
    if not flags:
        flags.append("中性")
    rows.append({
        "code": code,
        "name": names.get(code, code),
        "pe_pct": round(pe_pct, 1) if pe_pct is not None else None,
        "pb_pct": round(pb_pct, 1) if pb_pct is not None else None,
        "flag": flags[0],
        "cur_pe": round(pe_v, 2) if pe_v is not None else None,
        "cur_pb": round(pb_v, 2) if pb_v is not None else None,
        "n_days": len(g),
        "last_date": str(g["date"].iloc[-1].date()),
    })

out = {"rows": rows, "as_of": rows[0]["last_date"] if rows else None, "n": len(rows)}
json.dump(out, open(BASE + "_band_all.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"输出 _band_all.json: {len(rows)} 只 @ {out['as_of']}")
from collections import Counter
print("标记分布:", dict(Counter(r["flag"] for r in rows)))
