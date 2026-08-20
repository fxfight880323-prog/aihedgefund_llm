# -*- coding: utf-8 -*-
"""个股层面归因：每个亏损期的最大拖累 / 增速兑现假说 / 估值水平"""
import json, statistics

sel = json.load(open('_bt_pit_selection.json', encoding='utf-8'))
fin = json.load(open('_bt_pit_financials.json', encoding='utf-8'))
prices = json.load(open('_bt_pit_prices.json', encoding='utf-8'))
bench = json.load(open('_bt_benchmark.json', encoding='utf-8'))
det = json.load(open('_bt_gl_valsell_baseline_detail.json', encoding='utf-8'))
wts = det['weights_by_dt']
dets = det['detail_by_dt']

starts = sorted(wts.keys())

def month_add(m, d):
    y, mo = int(m[:4]), int(m[5:])
    t = y * 12 + (mo - 1) + d
    return f"{t // 12}-{t % 12 + 1:02d}"

def per_ret(tk, m0, m1):
    p0, p1 = prices.get(tk, {}).get(m0), prices.get(tk, {}).get(m1)
    if p0 and p1 and p0 > 0:
        return p1 / p0 - 1.0
    return None

def latest_yoy(tk, asof):
    """PIT 最新的 YoY 与报告期；以及再往前一期的 YoY（看趋势）"""
    per = fin.get(tk, {})
    # PIT: 报告期 <= asof
    avail = {k: v for k, v in per.items() if k <= asof}
    if not avail:
        return None, None, None
    # yoy 直接取 detail 里的（当时选股用的）
    return None

print("=" * 108)
print("每个亏损调仓期的 Top 拖累个股（等权口径，单只=1/N 拖累 = 个股收益/N）")
print("=" * 108)
for i, m0 in enumerate(starts):
    m1 = starts[i + 1] if i + 1 < len(starts) else '2026-08'
    tks = list(wts[m0].keys())
    n = len(tks)
    rows = []
    for tk in tks:
        r = per_ret(tk, m0, m1)
        if r is not None:
            nm = dets[m0].get(tk, {}).get('name', tk)
            sw1 = dets[m0].get(tk, {}).get('sw1', '?')
            yoy = dets[m0].get(tk, {}).get('yoy')
            rows.append((r, tk, nm, sw1, yoy))
    if not rows:
        continue
    rows.sort()
    total = sum(r for r, *_ in rows) / n
    bench_ret = bench.get(m1, 1) / bench.get(m0, 1) - 1
    print(f"\n【{m0} → {m1}】组合(等权) {total:+.1%} vs 基准 {bench_ret:+.1%}  超额 {total - bench_ret:+.1%}pp  ({n}只)")
    print(f"  {'个股':<12s} {'名称':<10s} {'行业':<8s} {'区间收益':>8s} {'拖累(1/N)':>9s} {'选股时YoY':>9s}")
    for r, tk, nm, sw1, yoy in rows[:8]:
        print(f"  {tk:<12s} {nm:<10s} {sw1:<8s} {r:>+8.1%} {r/n:>+9.1%} {(yoy*100 if yoy else 0):>+8.0f}%")
    if len(rows) > 8:
        # 最好/最差各列
        best = rows[-1]
        print(f"  最差: {rows[0][1]} {rows[0][2]} {rows[0][3]} {rows[0][0]:+.1%}   最好: {best[1]} {best[2]} {best[3]} {best[0]:+.1%}")
