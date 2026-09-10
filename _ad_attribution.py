"""
AD_top15_mom60top50 收益来源归因分析
方法：P/E 对数恒等式分解（数学恒等，不依赖字段准确性）

对每个调仓周期 [m_t → m_{t+1}]，每只持仓票：
  价格回报 R_i = 复权价_{t+1} / 复权价_t - 1
  估值变化 pe_chg_i = PE_{t+1} / PE_t - 1
  → 非估值贡献（盈利+股息+回购等）eps_chg_i = (1+R_i)/(1+pe_chg_i) - 1

组合层面（cap8 权重加权，起始权重）：
  总回报 R = Σ w_i R_i
  估值贡献 = Σ w_i pe_chg_i
  非估值贡献 = R - 估值贡献

再拆非估值：
  股息贡献 = Σ w_i × dtop5_i × 0.5（半年股息）
  盈利增长贡献 = 非估值贡献 - 股息贡献（残差，含真实盈利增长+回购+交互）

跨期累加用对数空间（复利），最终换算成贡献百分点和占比。
"""
import sys, os, json, bisect, math, sqlite3
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
from _bt_garp_decompose import load_all, load_bars
import _bt_garp as G
import _bt_q20_pareto as P

# ---- 加载 ----
univ, cons, val, fac, fin, names = load_all()
px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
bars, all_dates = load_bars(px_full)

db = sqlite3.connect("data/a_share_market.db")

# ---- 构造 w_by_dt (复用 AD 逻辑) ----
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

w_by_month = {}   # {month: {tk: weight}}
for month, as_of in P.PIT_DATES:
    bp = base_pools[month]
    ctx = mom_ctx[month]
    bp = [s for s in bp if P.GATES["mom60_top50"](s, ctx)]
    picked = sorted(bp, key=lambda s: -s["blend"])[:15]
    w = P.cap_weight(picked, 0.08)
    w_by_month[month] = w

# ---- 每期归因 ----
periods = P.PIT_DATES  # [(month, asof), ...]
n_periods = len(periods) - 1  # 最后一期无"下一期"

# 预取每期每票的 PE 和 dtop5
def get_pe(month, tk):
    v = val.get(month, {}).get(tk, {})
    return L._num(v.get("pe_ttm"))

def get_dy(month, tk):
    f = fac.get(month, {}).get(tk, {})
    return L._num(f.get("dtop5"))

def get_px(tk, asof):
    """复权价（asof 当日或最近交易日）"""
    mp = bars.get(tk, {})
    if not mp:
        return None
    elig = [d for d in mp if d <= asof]
    if not elig:
        return None
    d = max(elig)
    return mp[d].close_price

print("=" * 90)
print("  AD_top15_mom60top50 收益来源归因（P/E 对数恒等式分解）")
print("=" * 90)

period_rows = []
log_ret_total = 0.0
log_val_total = 0.0
log_div_total = 0.0
log_grow_total = 0.0

for t in range(n_periods):
    m_t, asof_t = periods[t]
    m_n, asof_n = periods[t+1]
    w = w_by_month.get(m_t, {})
    if not w:
        continue

    R = 0.0          # 组合价格回报（复权）
    val_contrib = 0.0
    div_contrib = 0.0
    n_valid = 0

    for tk, wi in w.items():
        pe_t = get_pe(m_t, tk)
        pe_n = get_pe(m_n, tk)
        px_t = get_px(tk, asof_t)
        px_n = get_px(tk, asof_n)
        dy_t = get_dy(m_t, tk)

        if pe_t is None or pe_n is None or pe_t <= 0 or pe_n <= 0:
            continue
        if px_t is None or px_n is None or px_t <= 0 or px_n <= 0:
            continue

        r_i = px_n / px_t - 1.0
        pe_chg_i = pe_n / pe_t - 1.0
        R += wi * r_i
        val_contrib += wi * pe_chg_i
        if dy_t is not None:
            div_contrib += wi * dy_t * 0.5  # 半年股息
        n_valid += 1

    nonval_contrib = R - val_contrib            # 非估值（盈利+股息+回购+交互）
    grow_contrib = nonval_contrib - div_contrib  # 纯盈利增长（残差）

    log_ret_total += math.log(1 + R) if R > -1 else 0
    log_val_total += math.log(1 + val_contrib) if val_contrib > -1 else 0
    log_div_total += math.log(1 + div_contrib) if div_contrib > -1 else 0
    log_grow_total += math.log(1 + grow_contrib) if grow_contrib > -1 else 0

    period_rows.append({
        "period": f"{m_t} → {m_n}",
        "n_valid": n_valid,
        "total_ret": R,
        "val_contrib": val_contrib,
        "div_contrib": div_contrib,
        "grow_contrib": grow_contrib,
    })
    print(f"  [{m_t}→{m_n}] 持仓{n_valid}只 总回报{R*100:+7.2f}% = "
          f"估值{val_contrib*100:+7.2f}% + 股息{div_contrib*100:+6.2f}% + 盈利{grow_contrib*100:+7.2f}%")

# ---- 跨期累计 ----
total_ret = math.exp(log_ret_total) - 1
val_ret = math.exp(log_val_total) - 1
div_ret = math.exp(log_div_total) - 1
grow_ret = math.exp(log_grow_total) - 1

print("\n" + "=" * 90)
print("  5 年累计归因（对数复利）")
print("=" * 90)
print(f"  总回报:        {total_ret*100:+7.2f}%")
print(f"  估值贡献:      {val_ret*100:+7.2f}%   (占比 {val_ret/total_ret*100:5.1f}%)")
print(f"  股息贡献:      {div_ret*100:+7.2f}%   (占比 {div_ret/total_ret*100:5.1f}%)")
print(f"  盈利增长贡献:  {grow_ret*100:+7.2f}%   (占比 {grow_ret/total_ret*100:5.1f}%)")

# 算术对照（直接累加，无复利）
sum_total = sum(r["total_ret"] for r in period_rows)
sum_val = sum(r["val_contrib"] for r in period_rows)
sum_div = sum(r["div_contrib"] for r in period_rows)
sum_grow = sum(r["grow_contrib"] for r in period_rows)
print(f"\n  [算术对照] 总{sum_total*100:+.1f}% = 估值{sum_val*100:+.1f}% + 股息{sum_div*100:+.1f}% + 盈利{sum_grow*100:+.1f}%")

# ---- 保存 ----
out = {
    "strategy": "AD_top15_mom60top50",
    "method": "P/E 对数恒等式分解 + 股息分离",
    "n_periods": n_periods,
    "periods": period_rows,
    "cumulative_log": {
        "total_return": float(total_ret),
        "valuation_contribution": float(val_ret),
        "dividend_contribution": float(div_ret),
        "growth_contribution": float(grow_ret),
        "val_share": float(val_ret/total_ret) if total_ret else None,
        "div_share": float(div_ret/total_ret) if total_ret else None,
        "growth_share": float(grow_ret/total_ret) if total_ret else None,
    },
    "cumulative_arithmetic": {
        "total_return": float(sum_total),
        "valuation": float(sum_val),
        "dividend": float(sum_div),
        "growth": float(sum_grow),
    },
}
json.dump(out, open("_ad_attribution.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n数据已存: _ad_attribution.json")