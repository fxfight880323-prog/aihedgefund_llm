# -*- coding: utf-8 -*-
"""growth loop 回测 NAV 深度分析：逐年分解 / 回撤 / 月度收益 / 基准对比。"""
import json, sys, math

def load(p):
    return json.load(open(p, encoding="utf-8"))

nav = load("_bt_gl_nav.json")          # [{"month","nav"}]
bench = load("_bt_benchmark.json")     # {month: value}

# NAV 去重（同一月保留最后值）
d = {}
for r in nav:
    d[r["month"]] = r["nav"]
months = sorted(d.keys())
m0, m1 = months[0], months[-1]
cap = d[m0]
years = (int(m1[:4]) + int(m1[5:7])/12) - (int(m0[:4]) + int(m0[5:7])/12)

total = d[m1]/cap - 1
annual = (1+total)**(1/years) - 1

# 年度分解（按自然年，取每年末）
print("="*60)
print("growth_loop HOOK 层 · 5 年 PIT 回测 · 深度分析")
print(f"区间 {m0} → {m1} | {years:.1f} 年 | 初始 ¥{cap:,.0f} → 期末 ¥{d[m1]:,.0f}")
print(f"总收益 {total:+.2%} | 年化 {annual:+.2%}")
print("="*60)

# 逐年收益
yrs = sorted({m[:4] for m in months})
prev_m = months[0]
print("\n① 逐年收益（策略 vs 中证全指基准）")
for y in yrs:
    ym = [m for m in months if m[:4] == y]
    if not ym:
        continue
    end_m = ym[-1]
    if end_m not in d or end_m not in bench:
        continue
    # 起点：上一年末（或最早月）
    prevs = [m for m in months if m < end_m]
    start_m = prevs[-1] if prevs else end_m
    if start_m == end_m:
        continue
    r_s = d[end_m]/d[start_m] - 1
    r_b = bench[end_m]/bench[start_m] - 1
    print(f"  {y}: 策略 {r_s:+8.1%} | 基准 {r_b:+8.1%} | 超额 {r_s-r_b:+8.1%}")

# 调仓期收益（每期调仓后到下次调仓前）
print("\n② 逐调仓期收益")
REB = ["2021-08","2022-04","2022-08","2023-04","2023-08",
       "2024-04","2024-08","2025-04","2025-08","2026-04"]
for i, mk in enumerate(REB):
    nxt = REB[i+1] if i+1 < len(REB) else months[-1]
    if mk not in d or nxt not in d:
        continue
    r_s = d[nxt]/d[mk] - 1
    r_b = bench[nxt]/bench[mk] - 1
    print(f"  {mk} → {nxt}: 策略 {r_s:+8.1%} | 基准 {r_b:+8.1%} | 超额 {r_s-r_b:+8.1%}")

# 回撤
print("\n③ 回撤")
high, mdd, mdd_start, mdd_end = d[months[0]], 0.0, months[0], months[0]
dd_start = months[0]
for m in months:
    v = d[m]
    if v >= high:
        high = v
        dd_start = m
    dd = v/high - 1
    if dd < mdd:
        mdd = dd
        mdd_start, mdd_end = dd_start, m
print(f"  最大回撤 {mdd:.1%} | {mdd_start} → {mdd_end}")

# 月度收益统计
rets = [d[months[i]]/d[months[i-1]]-1 for i in range(1, len(months))]
win = sum(1 for r in rets if r > 0)
print(f"\n④ 月度收益: {len(rets)} 个月 | 上涨 {win} ({win/len(rets):.0%}) | "
      f"均值 {sum(rets)/len(rets):+.2%} | 中位 {sorted(rets)[len(rets)//2]:+.2%} | "
      f"最差 {min(rets):.1%} | 最好 {max(rets):.1%}")

# 期末持仓分布（最后调仓期）
sel = load("_bt_pit_selection.json")
fin = load("_bt_pit_financials.json")
print("\n⑤ 最后调仓期候选概况（2026-04）")
s = sel.get("2026-04", {})
print(f"  候选 {len(s.get('candidates', []))} 只 | as_of {s.get('as_of')}")

# 全期候选 pool 统计
all_c = set()
for m, s in sel.items():
    for tk, name, sw1 in s["candidates"]:
        all_c.add((tk, name, sw1))
print(f"  全期唯一候选 {len(all_c)} 只")
