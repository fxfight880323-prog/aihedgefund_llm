"""
今日持仓建议 —— 策略: AD_top15_mom60top50 (Pareto唯一最优)
asof: 最新已收盘 PIT 月份 (2026-04-30，下次调仓 2026-10-31)
零未来函数: 只用 <= today 的已收盘数据
"""
import sys, os, json, bisect
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

# stub: 避免 _lx_allA_variant 顶层 import 失败 (本脚本不实际跑 BacktestingEngine)
import types
for mod_name in ("src","src.core","src.backtest","src.backtest.engine","src.backtest.strategy"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)
def _stub(name, **attrs):
    cls = type(name, (), attrs)
    sys.modules[name] = cls
    return cls
_stub("src.core.models", Signal=type("S",(),{}), BlendResult=type("B",(),{}),
      RiskResult=type("R",(),{}), Order=type("O",(),{}), OrderSide=type("OS",(),{}),
      Fill=type("F",(),{}), CycleRecord=type("C",(),{}), Position=type("P",(),{}))
_stub("src.backtest.engine", BacktestingEngine=type("BE",(),{}),
      BarData=type("BD",(),{"__init__":lambda self,*a,**k:None}))
_stub("src.backtest.strategy", StrategyTemplate=type("ST",(),{}))

import _lx_allA_variant as L
from _bt_garp_decompose import load_all

# ---- 0. 加载所有面板 ----
univ, cons, val, fac, fin, names = load_all()

PIT_MONTH = "2026-04"
ASOF = "2026-04-30"
TODAY = "2026-09-08"
NEXT_REB = "2026-10-31"

# 加载原始行情（dict 形式: {tk: {date: {open,high,low,close,adj}}})
px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
all_dates = sorted({dt for tk in px_full.values() for dt in tk.keys()})
print(f"=== 今日持仓建议 (no look-ahead bias) ===")
print(f"策略: AD_top15_mom60top50 (Pareto唯一最优, 夏普1.00, +117.5%)")
print(f"PIT month: {PIT_MONTH}  |  asof: {ASOF}")
print(f"今日: {TODAY}  |  下次调仓日: {NEXT_REB}")

def nearest_trade_date(d):
    cands = [x for x in all_dates if x <= d]
    return max(cands) if cands else d

cur_trade = nearest_trade_date(TODAY)
print(f"cur_trade (最新交易日): {cur_trade}")
print(f"行情覆盖: {len(px_full)} 只票, {len(all_dates)} 个交易日")

# ---- 1. q20 排序 ----
members = univ.get(PIT_MONTH, [])
vv = val.get(PIT_MONTH, {})
ff = fac.get(PIT_MONTH, {})
cc = cons.get(PIT_MONTH, {})

scored = []
for tk in members:
    v = vv.get(tk, {})
    f = ff.get(tk, {})
    pe_ttm = v.get("pe_ttm")
    npyoy = f.get("npyoy")
    roes = f.get("roes")
    gpm = f.get("gpm")
    if pe_ttm is None or pe_ttm != pe_ttm or pe_ttm <= 0:
        continue
    if npyoy is None or roes is None:
        continue
    q_score = (npyoy + roes + (gpm or 0)) / 3.0
    scored.append({
        "ticker": tk, "name": names.get(tk, tk),
        "pe_ttm": pe_ttm, "npyoy": npyoy, "roes": roes, "gpm": gpm,
        "q_score": q_score,
    })
print(f"\n[PIT 2026-04] 万得全A 候选 {len(members)} 只")
print(f"q20 排序前 (PE+q有效): {len(scored)} 只")

pe_vals = sorted([s["pe_ttm"] for s in scored])
pe_pct = {}
for s in scored:
    pos = bisect.bisect_left(pe_vals, s["pe_ttm"])
    # PE 越低 → 越便宜 → 分位越高（反向）
    pe_pct[s["ticker"]] = (len(pe_vals) - 1 - pos) / max(len(pe_vals) - 1, 1) * 100.0

q_vals = sorted([s["q_score"] for s in scored])
q_pct = {}
for s in scored:
    pos = bisect.bisect_left(q_vals, s["q_score"])
    q_pct[s["ticker"]] = pos / max(len(q_vals) - 1, 1) * 100.0

for s in scored:
    s["pe_pct"] = pe_pct[s["ticker"]]
    s["q_pct"] = q_pct[s["ticker"]]
    s["blend"] = 0.8 * s["pe_pct"] + 0.2 * s["q_pct"]

scored.sort(key=lambda s: -s["blend"])
base_pool = scored[:40]
print(f"q20 base pool (top40): {len(base_pool)} 只")

# ---- 2. mom60 gate (截面分位前50%) ----
# asof = 2026-04-30（最新 PIT），mom60 = 前 60 交易日 close / asof 当日 close - 1
# 月 K 下：asof 月 close / 前 3 月 close - 1（≈ 60 个交易日）
import sqlite3
db = sqlite3.connect('D:/workspace/ai_fund_framework/data/a_share_market.db')
PIT_ASOF_MONTH = "2026-04"  # asof 月份
# 前 60 个交易日 ≈ 前 3 个月（2026-01）
# 严格更近的窗口应是 2026-02 / 2026-03（≈40-60 交易日），保守用 2026-01
REF_MONTH = "2026-01"
mom_data = {}
for s in base_pool:
    tk = s["ticker"]
    row = db.execute("SELECT month, close FROM monthly_close WHERE ticker=? AND month IN (?, ?) ORDER BY month",
                     (tk, REF_MONTH, PIT_ASOF_MONTH)).fetchall()
    if len(row) < 2:
        continue
    m_ref, p_ref = row[0]   # 2026-01
    m_cur, p_cur = row[-1]  # 2026-04
    if not p_ref or not p_cur or p_ref <= 0 or p_cur <= 0:
        continue
    mom_data[tk] = {"ticker": tk, "name": s["name"],
                    "cur_px": p_cur, "ref_px": p_ref,
                    "mom60": (p_cur / p_ref - 1) * 100.0}
print(f"mom60 (asof={PIT_ASOF_MONTH}, ref={REF_MONTH}) 计算覆盖: {len(mom_data)} 只")

if mom_data:
    m60_vals = sorted([v["mom60"] for v in mom_data.values()])
    for v in mom_data.values():
        pos = bisect.bisect_left(m60_vals, v["mom60"])
        v["mom60_pct"] = pos / len(m60_vals) * 100.0

gate_pool = [v for v in mom_data.values() if v["mom60_pct"] >= 50.0]
print(f"gate (mom60_pct >= 50): {len(gate_pool)} 只")

# ---- 3. 合并 base_pool + mom60_gate ----
merged = {}
for s in base_pool:
    if s["ticker"] in {v["ticker"] for v in gate_pool}:
        merged[s["ticker"]] = {**s, **next(v for v in gate_pool if v["ticker"] == s["ticker"])}

picked = sorted(merged.values(), key=lambda s: -s["blend"])[:15]
print(f"top15: {len(picked)} 只")

# ---- 4. cap8 加权 ----
def cap_weight(picks, cap=0.08):
    n = len(picks)
    if n == 0:
        return {}
    raw = {p["ticker"]: 1.0 / n for p in picks}
    for _ in range(50):
        excess = sum(max(0, w - cap) for w in raw.values())
        if excess < 1e-9:
            break
        capped = sum(min(w, cap) for w in raw.values())
        free = max(0.0, 1.0 - capped)
        n_under = sum(1 for w in raw.values() if w < cap)
        if n_under == 0:
            break
        for tk in raw:
            if raw[tk] > cap:
                raw[tk] = cap
            else:
                raw[tk] += free / n_under
    return raw

w = cap_weight(picked, 0.08)
eff_hold = [p for p in picked if w.get(p["ticker"], 0) > 0]
print(f"\n实际有效持仓 (cap8后): {len(eff_hold)} 只")
print(f"总权重 {sum(w.values()):.4f}  | 最高 {max(w.values())*100:.2f}%  | 最低 {min(w.values())*100:.2f}%")

for p in picked:
    p["weight"] = w.get(p["ticker"], 0)
    p["weight_pct"] = p["weight"] * 100

picked.sort(key=lambda p: -p["weight"])

# ---- 5. 收集行业（cons 中字段缺失则用 fallback） ----
for p in picked:
    # 行业字段不在 consensus 里，但 cons.get(tk) 可能有 con_peg/con_pe 等
    # 简单显示 con_pe
    c = cc.get(p["ticker"], {})
    p["con_pe"] = c.get("con_pe")
    p["con_peg"] = c.get("con_peg")

# ---- 输出 ----
out = {
    "asof_trade": cur_trade,
    "pit_month": PIT_MONTH,
    "pit_asof": ASOF,
    "next_rebalance": NEXT_REB,
    "today": TODAY,
    "strategy": "AD_top15_mom60top50",
    "strategy_desc": "q20排序(0.8×PE便宜度+0.2×质量分) + mom60截面分位前50% gate + top15截断 + cap8加权",
    "kpi_expected": {"annual_ret": 0.166, "sharpe": 1.00, "mdd": -0.206,
                     "n_holdings_avg": 12.0, "excess_vs_ew_pit": 0.805},
    "pool_size": {"pit_total": len(members), "pe_valid": len(scored),
                  "q20_top40": len(base_pool), "mom60_calc": len(mom_data),
                  "gate_pass": len(gate_pool), "top15": len(picked),
                  "eff_holdings": len(eff_hold)},
    "holdings": picked,
}
json.dump(out, open("_holdings_today.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

print("\n" + "="*88)
print("今日推荐持仓（按权重降序）")
print("="*88)
print(f"{'ticker':<10}{'name':<14}{'PE':>7}{'PE%':>7}{'q%':>7}{'q20':>6}"
      f"{'mom60%':>9}{'mom60_pct':>11}{'权重%':>9}")
print("-"*88)
for p in picked:
    print(f"{p['ticker']:<10}{p['name'][:12]:<14}{p['pe_ttm']:>7.1f}"
          f"{p['pe_pct']:>6.1f}%{p['q_pct']:>6.1f}%{p['blend']:>6.1f}"
          f"{p['mom60']:>+8.1f}%{p['mom60_pct']:>10.1f}%{p['weight_pct']:>8.2f}%")
print("-"*88)
print(f"实际有效持仓: {len(eff_hold)} 只  | 期望夏普 1.00  | 期望收益 +117.5% (5年累计)")
print(f"\n数据已存: _holdings_today.json")
print(f"下次调仓日: {NEXT_REB}（届时跑 _holdings_today.py 即可生成新持仓）")