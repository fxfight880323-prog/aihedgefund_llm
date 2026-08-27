# -*- coding: utf-8 -*-
"""周频面板构建：日频 parquet -> 周五截面 + 63日滚动量 -> _sr_weekly.parquet

输出列: date(周五快照日), stock_code, ep, bp, size, industry,
        turn_3m, vol_3m, beta_3m, fwd20, ret_1w
Universe 过滤: PB<=0 丢弃在信号层做（保留原始值）; 上市<126交易日在此剔除。
"""
import os
import glob
import numpy as np
import pandas as pd

CACHE = r"D:\workspace\ai_fund_framework\_sr_cache"
OUT = os.path.join(CACHE, "_sr_weekly.parquet")

# ---------- 1. 读全部年度 parquet ----------
val_parts, ret_parts = [], []
for y in range(2010, 2027):
    vp = os.path.join(CACHE, f"val_{y}.parquet")
    rp = os.path.join(CACHE, f"ret_{y}.parquet")
    if os.path.exists(vp):
        val_parts.append(pd.read_parquet(vp, columns=["date", "stock_code", "pe_ttm", "pb", "turnover", "float_mv"]))
    if os.path.exists(rp):
        ret_parts.append(pd.read_parquet(rp, columns=["date", "stock_code", "daily_return", "industry_l1", "forward_return_20d"]))
print(f"years found: val={len(val_parts)} ret={len(ret_parts)}")

val = pd.concat(val_parts, ignore_index=True)
ret = pd.concat(ret_parts, ignore_index=True)
val["date"] = pd.to_datetime(val["date"])
ret["date"] = pd.to_datetime(ret["date"])
print(f"val rows={len(val):,}  ret rows={len(ret):,}")

# ---------- 2. 交易日历 + 周五标记 ----------
all_days = np.sort(ret["date"].unique())
day_idx = pd.Series(range(len(all_days)), index=all_days)
# 周频快照：每周最后一个交易日（周五为默认，节假日自动落到该周最后交易日）
day_df = pd.DataFrame({"date": all_days})
day_df["isoweek"] = day_df["date"].dt.isocalendar().week.astype(int)
day_df["isoyear"] = day_df["date"].dt.isocalendar().year.astype(int)
last_of_week = day_df.groupby(["isoyear", "isoweek"])["date"].max().values
fri_set = pd.DatetimeIndex(last_of_week)
print(f"weeks: {len(fri_set)}  {fri_set[0].date()} -> {fri_set[-1].date()}")

# ---------- 3. pivot 日频矩阵 ----------
print("pivoting daily_return ...")
retm = ret.pivot_table(index="date", columns="stock_code", values="daily_return", aggfunc="last")
print("pivoting turnover ...")
turnm = val.pivot_table(index="date", columns="stock_code", values="turnover", aggfunc="last")

# 市场收益（中证全指）
idx = pd.read_csv(os.path.join(CACHE, "idx_csiall.csv"), parse_dates=["date"]).set_index("date")["close"].sort_index()
mkt_ret = idx.pct_change()
# 对齐到 retm 索引（缺失日 ffill 前值收益=0 不可取；直接 reindex 后 dropna 由 min_periods 处理）
mkt_ret = mkt_ret.reindex(retm.index)

W = 63  # 3个月
def roll_mean(df, w):
    return df.rolling(w, min_periods=int(w * 0.8)).mean()

print("rolling 63d: turn_3m / vol_3m / beta parts ...")
turn_3m = roll_mean(turnm, W)
vol_3m = retm.rolling(W, min_periods=int(W * 0.8)).std()
# beta = cov(r, m)/var(m) via E[rm]-E[r]E[m]
rm = retm.mul(mkt_ret, axis=0)
m_bar = roll_mean(pd.DataFrame(index=retm.index).assign(m=mkt_ret)["m"].to_frame(), W)["m"]
r_bar = roll_mean(retm, W)
rm_bar = roll_mean(rm, W)
var_m = m_bar ** 2  # placeholder, replaced below
# 正确: var(m) = E[m^2] - E[m]^2 ; cov = E[rm] - E[r]E[m]
m2 = pd.DataFrame(np.tile((mkt_ret ** 2).values[:, None], (1, retm.shape[1])), index=retm.index, columns=retm.columns)
m2_bar = roll_mean(m2, W)
beta_3m = (rm_bar - r_bar.mul(m_bar, axis=0)) / (m2_bar.iloc[:, 0] - m_bar ** 2).values[:, None]
del rm, m2, m2_bar, r_bar, rm_bar

# ---------- 4. 周五快照 ----------
print("slicing Friday snapshots ...")
ret_f = retm.loc[retm.index.isin(fri_set)]
turn_f = turn_3m.loc[turn_3m.index.isin(fri_set)]
vol_f = vol_3m.loc[vol_3m.index.isin(fri_set)]
beta_f = beta_3m.loc[beta_3m.index.isin(fri_set)]

# 上市年龄过滤：首次有效日期 + 126 交易日
first_valid = retm.apply(lambda col: col.first_valid_index())
# 用交易日序号
day_ord = pd.Series(range(len(retm.index)), index=retm.index)
first_ord = first_valid.map(day_ord)
age_ok = pd.DataFrame(False, index=retm.index, columns=retm.columns)
# 向量化: age_ok[t, s] = day_ord[t] - first_ord[s] >= 126
fo = first_ord.reindex(retm.columns)
cur = day_ord.reindex(retm.index).values[:, None]
age_ok = pd.DataFrame((cur - fo.values[None, :]) >= 126, index=retm.index, columns=retm.columns)
age_f = age_ok.loc[age_ok.index.isin(fri_set)]
del retm, turnm, turn_3m, vol_3m, beta_3m, age_ok

# ---------- 5. val 周五行 ----------
print("val Friday slice ...")
val_f = val[val["date"].isin(fri_set)].copy()
ret_ind = ret[ret["date"].isin(fri_set)][["date", "stock_code", "industry_l1", "forward_return_20d"]].copy()

base = val_f.merge(ret_ind, on=["date", "stock_code"], how="left")
# 长表 -> 加滚动量（先 melt 周五矩阵）
def melt_f(mat, name):
    m = mat.reset_index().melt(id_vars="date", var_name="stock_code", value_name=name).dropna(subset=[name])
    return m

parts = [base]
for mat, name in [(turn_f, "turn_3m"), (vol_f, "vol_3m"), (beta_f, "beta_3m")]:
    parts.append(melt_f(mat, name))
    print(f"  {name}: {len(parts[-1]):,} rows")
# age 过滤
age_m = melt_f(age_f.astype(float), "age_ok").dropna(subset=["age_ok"])
parts.append(age_m)

print("merging ...")
from functools import reduce
wk = reduce(lambda a, b: pd.merge(a, b, on=["date", "stock_code"], how="left"), parts)
wk = wk[wk["age_ok"] == 1.0].drop(columns=["age_ok"])
wk = wk.dropna(subset=["pe_ttm", "pb"], how="all")
wk["ep"] = np.where(wk["pe_ttm"] > 0, 1.0 / wk["pe_ttm"], np.nan)
wk["bp"] = np.where(wk["pb"] > 0, 1.0 / wk["pb"], np.nan)
wk["size"] = np.log(wk["float_mv"].where(wk["float_mv"] > 0))
wk = wk.rename(columns={"forward_return_20d": "fwd20", "industry_l1": "industry"})
wk = wk[["date", "stock_code", "industry", "ep", "bp", "size", "turn_3m", "vol_3m", "beta_3m", "fwd20"]]
wk = wk.sort_values(["date", "stock_code"]).reset_index(drop=True)
print(f"weekly panel: {len(wk):,} rows, weeks={wk['date'].nunique()}, stocks~{wk['stock_code'].nunique()}")
wk.to_parquet(OUT, index=False)
print("saved ->", OUT)
