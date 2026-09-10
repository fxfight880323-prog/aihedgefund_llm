"""
AD_top15_mom60top50 完整历史收益风险分析
- 重跑一次，存完整日 NAV
- 从 NAV 计算月度收益、最大回撤期、胜率、最大单月涨跌、年化波动率、信息比率
- 输出 JSON + HTML
"""
import sys, os, json, bisect
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
from _bt_garp_decompose import load_all, load_bars
import _bt_garp as G
import _bt_q20_pareto as P

# ---- 加载数据 ----
univ, cons, val, fac, fin, names = load_all()
px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
bars, all_dates = load_bars(px_full)

# ---- 构造 base pool + mom ctx ----
base_pools = {}
for month, as_of in P.PIT_DATES:
    members = univ.get(month, [])
    vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
    base_pools[month] = P.screen_q20(month, members, vv, ff, cc)

mom_ctx = {}
for month, as_of in P.PIT_DATES:
    m, elig = P.build_mom_series(bars, all_dates, as_of)
    if not m:
        mom_ctx[month] = {"mom": {}, "mom60_pct": {}}
        continue
    m60_vals = sorted([v["mom60"] for v in m.values() if v["mom60"] is not None])
    mom60_pct = {}
    for tk, v in m.items():
        if v["mom60"] is not None and m60_vals:
            pos = bisect.bisect_left(m60_vals, v["mom60"])
            mom60_pct[tk] = pos / len(m60_vals) * 100.0
    mom_ctx[month] = {"mom": m, "mom60_pct": mom60_pct}

# ---- 跑 AD_top15_mom60top50 ----
N_TOP = 15
GATE = "mom60_top50"

w_by_dt = {}
for month, as_of in P.PIT_DATES:
    bp = base_pools[month]
    ctx = mom_ctx[month]
    bp = [s for s in bp if P.GATES[GATE](s, ctx)]
    picked = sorted(bp, key=lambda s: -s["blend"])[:N_TOP]
    w = P.cap_weight(picked, 0.08)
    trig = max(d for d in all_dates if d <= as_of)
    w_by_dt[trig] = w

r = G.run("AD_top15_mom60top50", w_by_dt, bars)
nav_list = r["nav"]   # list of {"date": d, "nav": v}
print(f"AD_top15_mom60top50 NAV: {len(nav_list)} 天")
print(f"总收益: {r['total']*100:+.2f}%  年化: {r['ann']*100:+.2f}%  MDD: {r['mdd']*100:.2f}%")

# 转为 dict
nav = {x["date"]: x["nav"] for x in nav_list}
nav_sorted = sorted(nav.items())

# ---- 月度收益 ----
monthly_nav = {}
for dt, v in nav_sorted:
    ym = dt[:7]
    if ym not in monthly_nav:
        monthly_nav[ym] = {"start": None, "end": None}
    if monthly_nav[ym]["start"] is None:
        monthly_nav[ym]["start"] = v
    monthly_nav[ym]["end"] = v
monthly_ret = {ym: m["end"]/m["start"]-1 for ym, m in monthly_nav.items() if m["start"] and m["start"]>0}

mret_vals = list(monthly_ret.values())
win = sum(1 for r in mret_vals if r > 0)
loss = sum(1 for r in mret_vals if r < 0)
flat = sum(1 for r in mret_vals if r == 0)
print(f"\n月度收益: {len(mret_vals)} 月")
print(f"  胜: {win}, 负: {loss}, 平: {flat}")
print(f"  最大单月: {max(mret_vals)*100:+.2f}%  ({max(monthly_ret, key=monthly_ret.get)})")
print(f"  最小单月: {min(mret_vals)*100:+.2f}%  ({min(monthly_ret, key=monthly_ret.get)})")
print(f"  月度均值: {sum(mret_vals)/len(mret_vals)*100:.2f}%")
m = sum(mret_vals)/len(mret_vals)
mstd = (sum((x-m)**2 for x in mret_vals)/len(mret_vals))**0.5
print(f"  月度 std: {mstd*100:.2f}%")

# ---- 最大回撤期 ----
peak = 0
peak_dt = None
max_dd = 0
max_dd_peak_dt = None
max_dd_trough_dt = None
recovery_dt = None
in_dd = False
for dt, v in nav_sorted:
    if v > peak:
        peak = v
        peak_dt = dt
        # 创新高 → 如果之前处于回撤中，恢复
        if in_dd:
            recovery_dt = dt
            in_dd = False
    dd = v / peak - 1 if peak > 0 else 0
    if dd < max_dd:
        max_dd = dd
        max_dd_peak_dt = peak_dt
        max_dd_trough_dt = dt
        in_dd = True
        recovery_dt = None  # 新最大回撤开始，重置 recovery
print(f"\n最大回撤: {max_dd*100:.2f}%")
print(f"  高点: {max_dd_peak_dt}  低点: {max_dd_trough_dt}  恢复: {recovery_dt}")

# ---- 年度收益 ----
yearly = {}
for dt, v in nav_sorted:
    y = dt[:4]
    if y not in yearly:
        yearly[y] = {"start": None, "end": None}
    if yearly[y]["start"] is None:
        yearly[y]["start"] = v
    yearly[y]["end"] = v
yearly_ret = {y: m["end"]/m["start"]-1 for y, m in yearly.items() if m["start"]}
print(f"\n年度收益:")
for y, ret in sorted(yearly_ret.items()):
    print(f"  {y}: {ret*100:+.2f}%")

# ---- 信息比率 vs 全A等权 ----
import numpy as np
ew_data = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))
# ew_data 是 dict of date:nav，需要 list 形式
ew_nav = ew_data.get("nav", ew_data)  # 看结构
if isinstance(ew_nav, dict) and "2021-06-01" in ew_nav:
    pass  # 直接 dict
elif isinstance(ew_nav, list):
    ew_nav = {x["date"]: x["nav"] for x in ew_nav}

common_dates = sorted(set(nav.keys()) & set(ew_nav.keys()))
ret_s = []
ret_e = []
for i in range(1, len(common_dates)):
    d0, d1 = common_dates[i-1], common_dates[i]
    if nav[d0] and nav[d1] and ew_nav[d0] and ew_nav[d1]:
        ret_s.append(nav[d1]/nav[d0] - 1)
        ret_e.append(ew_nav[d1]/ew_nav[d0] - 1)
arr_s, arr_e = np.array(ret_s), np.array(ret_e)
excess = arr_s - arr_e
ann_excess = excess.mean()*252
vol_excess = excess.std()*np.sqrt(252)
ir = ann_excess/vol_excess if vol_excess>0 else None
beta = np.cov(arr_s, arr_e)[0,1]/np.var(arr_e) if np.var(arr_e)>0 else None
alpha_daily = arr_s.mean() - (beta * arr_e.mean()) if beta else None
alpha_ann = alpha_daily*252 if alpha_daily is not None else None
ann_vol = arr_s.std()*np.sqrt(252)
print(f"\n相对全A等权基准:")
print(f"  Alpha (年化): {alpha_ann*100:+.2f}%")
print(f"  Beta: {beta:.3f}")
print(f"  IR (信息比率): {ir:.3f}")
print(f"  年化波动率: {ann_vol*100:.2f}%")

# 调仓次数
print(f"\n调仓次数: {len(w_by_dt)} 次（半年调仓口径）")

# ---- 持仓换手率 ----
prev_set = None
total_turnover = 0
for month, w in w_by_dt.items():
    cur_set = set(w.keys())
    if prev_set is not None:
        leave = prev_set - cur_set
        enter = cur_set - prev_set
        turnover = (len(leave) + len(enter)) / 2 / len(prev_set | cur_set) if prev_set | cur_set else 0
        total_turnover += turnover
    prev_set = cur_set
avg_turnover = total_turnover / max(len(w_by_dt)-1, 1)
print(f"平均换手率（每半年调仓）: {avg_turnover*100:.1f}%")

# ---- 保存 ----
out = {
    "strategy": "AD_top15_mom60top50",
    "asof_data": max(nav.keys()),
    "summary_metrics": {
        "total_return": r["total"], "annual_return": r["ann"],
        "annual_volatility": float(ann_vol),
        "mdd": r["mdd"], "sharpe": r.get("sharpe"),
    },
    "yearly_return": yearly_ret,
    "monthly_return": monthly_ret,
    "max_drawdown": {
        "depth": float(max_dd), "peak_dt": max_dd_peak_dt,
        "trough_dt": max_dd_trough_dt, "recovery_dt": recovery_dt,
    },
    "monthly_stats": {
        "n_months": len(mret_vals), "wins": win, "losses": loss, "flats": flat,
        "win_rate": win/(win+loss) if (win+loss) else None,
        "max_month": float(max(mret_vals)),
        "min_month": float(min(mret_vals)),
        "mean_month": float(m),
        "std_month": float(mstd),
        "best_month_ym": max(monthly_ret, key=monthly_ret.get),
        "worst_month_ym": min(monthly_ret, key=monthly_ret.get),
    },
    "vs_ew_allA": {
        "alpha_annual": float(alpha_ann) if alpha_ann is not None else None,
        "beta": float(beta) if beta is not None else None,
        "ir": float(ir) if ir is not None else None,
        "ew_total": ew_data.get("total", None),
    },
    "n_rebalances": len(w_by_dt),
    "avg_turnover_per_rebal": avg_turnover,
    "nav": nav,
}
json.dump(out, open("_ad_history.json","w",encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
print(f"\n数据已存: _ad_history.json")