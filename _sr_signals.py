# -*- coding: utf-8 -*-
"""四大 TAA 信号管线：周五截面 -> _sr_signals.csv

方向约定（统一算 Value 方向 / Small 方向）：
  score > 0 -> Value ETF (512890 红利低波) / Small ETF (512100 中证1000)
  score < 0 -> Growth ETF (159915 创业板)  / Large ETF (510050 上证50)

信号:
  odds_z   : 估值价差 LLT30 + 312周 z（逆向，高=该风格便宜）
  winrate  : 六周期代理（仅 Growth/Value sleeve）
  trend_z  : rankIC(lag 4周) -> ICIR52 -> 312周 z（顺势）
  crowd_z  : 换手/波动/Beta 三比值 LLT30 + 312周 z 平均（极端高=拥挤）
"""
import os
import numpy as np
import pandas as pd

CACHE = r"D:\workspace\ai_fund_framework\_sr_cache"
WEEKLY = os.path.join(CACHE, "_sr_weekly.parquet")
OUT = os.path.join(CACHE, "_sr_signals.csv")

ZWIN = 312     # 6年周频
ZMIN = 312     # 严格 warm-up
LLT_D = 30

# ---------------- helpers ----------------
def llt(p, d=LLT_D):
    a = 2.0 / (d + 1)
    p = np.asarray(p, dtype=float)
    n = len(p)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    out[0] = p[0]
    if n > 1:
        out[1] = p[1]
    for t in range(2, n):
        out[t] = ((a - a * a / 4) * p[t] + (a * a / 2) * p[t - 1]
                  - (a - 3 * a * a / 4) * p[t - 2]
                  + 2 * (1 - a) * out[t - 1] - (1 - a) ** 2 * out[t - 2])
    return out

def roll_z(s, win=ZWIN, minp=ZMIN):
    m = s.rolling(win, min_periods=minp).mean()
    sd = s.rolling(win, min_periods=minp).std()
    return (s - m) / sd

def quintile_masks(df, factor, high_is_long=True):
    """行业内五分组: long=Q5(或Q1), short=对立组"""
    pct = df.groupby(["date", "industry"])[factor].rank(pct=True)
    if high_is_long:
        return (pct >= 0.8).values, (pct <= 0.2).values
    else:
        return (pct <= 0.2).values, (pct >= 0.8).values

def spread_series(df, factor, high_is_long=True, use_log=True, spread_col=None):
    """分组用 factor, 价差用 median(log(spread_col))_long - _short (规格§3 统一 BP 语义)"""
    sc = spread_col or factor
    x = np.log(df[sc].where(df[sc] > 0)) if use_log else df[sc]
    pct = df.groupby(["date", "industry"])[factor].rank(pct=True)
    if high_is_long:
        lm, sm = (pct >= 0.8).values, (pct <= 0.2).values
    else:
        lm, sm = (pct <= 0.2).values, (pct >= 0.8).values
    tmp = pd.DataFrame({"date": df["date"].values, "x": x.values, "lm": lm, "sm": sm})
    lg = tmp[tmp["lm"]].groupby("date")["x"].median()
    sh = tmp[tmp["sm"]].groupby("date")["x"].median()
    return (lg - sh).sort_index()

def ratio_series(df, factor, col, high_is_long=True):
    """mean(col[long]) / mean(col[short]) 按周五"""
    lm, sm = quintile_masks(df, factor, high_is_long)
    tmp = pd.DataFrame({"date": df["date"].values, "x": df[col].values,
                        "lm": lm, "sm": sm})
    lg = tmp[tmp["lm"]].groupby("date")["x"].mean()
    sh = tmp[tmp["sm"]].groupby("date")["x"].mean()
    return (lg / sh).sort_index()

# ---------------- load ----------------
print("loading weekly panel ...")
wk = pd.read_parquet(WEEKLY)
wk["date"] = pd.to_datetime(wk["date"])
wk = wk.dropna(subset=["industry"])
print(f"rows={len(wk):,}  weeks={wk['date'].nunique()}")

dates = np.sort(wk["date"].unique())

# ---------------- Odds ----------------
print("Odds: spreads ...")
ep_sp = spread_series(wk, "ep", high_is_long=True)      # value cheap = high ep, 价差= log(EP)
bp_sp = spread_series(wk, "bp", high_is_long=True)      # 价差 = log(BP)
# size 对子: 分组用 size(小=long), 价差统一用 BP (规格§3: raw_spread=median(log(BP_long))-median(log(BP_short)))
sz_sp = spread_series(wk, "size", high_is_long=False, spread_col="bp")

def odds_z_from(spread):
    s = spread.ffill()
    sm = pd.Series(llt(s.values), index=s.index)
    return roll_z(sm)

odds_ep = odds_z_from(ep_sp)
odds_bp = odds_z_from(bp_sp)
odds_sz = odds_z_from(sz_sp)
odds_val = (odds_ep + odds_bp) / 2.0

# ---------------- Trend ----------------
print("Trend: rankIC ...")
# 残差化: 每周截面内 行业去均值 + size 十分位去均值 (对 ep/bp); size 因子不残差化
for f in ["ep", "bp"]:
    ind_mean = wk.groupby(["date", "industry"])[f].transform("mean")
    r = wk[f] - ind_mean
    # size 十分位按周截面计算
    sz_pct = wk.groupby("date")["size"].rank(pct=True)
    sz_bin = np.minimum((sz_pct.fillna(0.5) * 10).astype(int), 9)
    sz_mean = pd.DataFrame({"v": r.values, "d": wk["date"].values, "b": sz_bin.values}) \
        .groupby(["d", "b"])["v"].transform("mean")
    wk[f + "_resid"] = r.values - sz_mean.values

def rank_ic(df, fcol):
    ic = {}
    for d, x in df.groupby("date"):
        s = x[[fcol, "fwd20"]].dropna()
        if len(s) > 200:
            ic[d] = s[fcol].corr(s["fwd20"], method="spearman")
    return pd.Series(ic).sort_index()

ic_ep = rank_ic(wk, "ep_resid")
ic_bp = rank_ic(wk, "bp_resid")
ic_sz = rank_ic(wk, "size")
# 尾部 fwd20 缺失导致的 IC NaN -> 有限 ffill(5周), 避免滚动窗口 NaN 传染
ic_ep = ic_ep.ffill(limit=5)
ic_bp = ic_bp.ffill(limit=5)
ic_sz = ic_sz.ffill(limit=5)
# IC 滞后 4 周（20 交易日）防未来函数
ic_ep = ic_ep.shift(4)
ic_bp = ic_bp.shift(4)
ic_sz = ic_sz.shift(4)

def trend_z_from(ic):
    icir = ic.rolling(52, min_periods=52).mean() / ic.rolling(52, min_periods=52).std()
    return roll_z(icir)

trend_ep = trend_z_from(ic_ep)
trend_bp = trend_z_from(ic_bp)
trend_sz = trend_z_from(ic_sz)
trend_val = (trend_ep + trend_bp) / 2.0

# ---------------- Crowding ----------------
print("Crowding: ratios ...")
crowd_parts = {}
for sleeve, (factor, hil) in {"val_ep": ("ep", True), "val_bp": ("bp", True), "size": ("size", False)}.items():
    zs = []
    for col in ["turn_3m", "vol_3m", "beta_3m"]:
        r = ratio_series(wk, factor, col, high_is_long=hil).ffill()
        sm = pd.Series(llt(r.values), index=r.index)
        zs.append(roll_z(sm))
    crowd_parts[sleeve] = sum(zs) / 3.0

crowd_ep, crowd_bp, crowd_sz = crowd_parts["val_ep"], crowd_parts["val_bp"], crowd_parts["size"]
crowd_val = (crowd_ep + crowd_bp) / 2.0

# ---------------- WinRate (six-cycle proxy) ----------------
print("WinRate: six-cycle proxy ...")
r007 = pd.read_csv(os.path.join(CACHE, "macro_r007.csv"), parse_dates=["date"]).set_index("date")["value"].sort_index()
tsf = pd.read_csv(os.path.join(CACHE, "macro_tsf_yoy.csv"), parse_dates=["date"]).set_index("date")["value"].sort_index()

r007_m = r007.resample("ME").mean()
m_slope = r007_m.diff(3)            # 3月斜率: <0 = 利率下行 = 松
c_slope = tsf.diff(3)               # >0 = 信用扩张
# 公布滞后: 周 t 只能用上上月底已公布值 -> shift(1) 一个月
state = pd.DataFrame({"m": m_slope.shift(1), "c": c_slope.shift(1)}).dropna()

def growth_wr(row):
    if np.isnan(row["m"]) or np.isnan(row["c"]):
        return np.nan
    m_loose = row["m"] < 0
    c_exp = row["c"] > 0
    if m_loose and c_exp:  return 1.0
    if m_loose and not c_exp: return 0.5
    if (not m_loose) and c_exp: return 0.0
    return -1.0

state["gwr"] = state.apply(growth_wr, axis=1)
wr_monthly = state["gwr"]
# 扩展到周频: 周五取最近已知月度状态
wr_idx = pd.DatetimeIndex(dates)
wr_weekly = wr_monthly.reindex(wr_idx.union(wr_monthly.index)).ffill().reindex(wr_idx)
winrate_growth = wr_weekly
winrate_val = -wr_weekly

# ---------------- assemble ----------------
sig = pd.DataFrame({
    "date": pd.DatetimeIndex(dates),
    "odds_val": odds_val.reindex(dates).values,
    "odds_ep": odds_ep.reindex(dates).values,
    "odds_bp": odds_bp.reindex(dates).values,
    "odds_size": odds_sz.reindex(dates).values,
    "trend_val": trend_val.reindex(dates).values,
    "trend_size": trend_sz.reindex(dates).values,
    "crowd_val": crowd_val.reindex(dates).values,
    "crowd_size": crowd_sz.reindex(dates).values,
    "winrate_val": winrate_val.values,
    "winrate_growth": winrate_growth.values,
    "m_loose": (state["m"].reindex(wr_idx.union(state.index)).ffill().reindex(wr_idx) < 0).values,
    "c_exp": (state["c"].reindex(wr_idx.union(state.index)).ffill().reindex(wr_idx) > 0).values,
    # raw spreads for validation section
    "spread_ep": ep_sp.reindex(dates).values,
    "spread_bp": bp_sp.reindex(dates).values,
    "spread_size": sz_sp.reindex(dates).values,
    "ic_ep": ic_ep.reindex(dates).values,
    "ic_bp": ic_bp.reindex(dates).values,
    "ic_sz": ic_sz.reindex(dates).values,
})
sig = sig.dropna(subset=["odds_val", "odds_size", "trend_val", "trend_size", "crowd_val", "crowd_size"], how="all")
sig.to_csv(OUT, index=False)
print(f"saved {len(sig)} weeks -> {OUT}")
print(sig.dropna(subset=['odds_val']).head(3).to_string())
print(sig.dropna(subset=['odds_val']).tail(3).to_string())
