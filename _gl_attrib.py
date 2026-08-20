# -*- coding: utf-8 -*-
"""2021-2024 业绩差归因：行业暴露 / 个股贡献 / 持仓特征 / 与基准对比"""
import json, statistics, sys

sel = json.load(open('_bt_pit_selection.json', encoding='utf-8'))
fin = json.load(open('_bt_pit_financials.json', encoding='utf-8'))
prices = json.load(open('_bt_pit_prices.json', encoding='utf-8'))
bench = json.load(open('_bt_benchmark.json', encoding='utf-8'))
det = json.load(open('_bt_gl_valsell_baseline_detail.json', encoding='utf-8'))
wts = det['weights_by_dt']
dets = det['detail_by_dt']
nav = json.load(open('_bt_gl_nav.json', encoding='utf-8'))
nav_d = {r['month']: r['nav'] for r in nav}

def month_add(m, d):
    y, mo = int(m[:4]), int(m[5:])
    t = y * 12 + (mo - 1) + d
    return f"{t // 12}-{t % 12 + 1:02d}"

periods = sorted(wts.keys()) + [None]  # None = 最后期末
starts = sorted(wts.keys())

def port_ret(tickers, w, m0, m1):
    """等权组合收益（价格收益近似，忽略调仓月内时点差异）"""
    rets = []
    for tk in tickers:
        p0 = prices.get(tk, {}).get(m0)
        p1 = prices.get(tk, {}).get(m1)
        if p0 and p1 and p0 > 0:
            rets.append(p1 / p0 - 1.0)
    if not rets:
        return None
    return sum(rets) / len(rets), rets

print("=" * 100)
print("一、每调仓期组合收益 vs 基准（策略基准 = 等权沪深300/中证500？看 _bt_benchmark）")
print("=" * 100)
for i, m0 in enumerate(starts):
    m1 = starts[i + 1] if i + 1 < len(starts) else '2026-08'
    # 组合收益：期初(调仓月) → 期末(下次调仓月)
    tks = list(wts[m0].keys())
    r = port_ret(tks, wts[m0], m0, m1)
    b0, b1 = bench.get(m0), bench.get(m1)
    bret = b1 / b0 - 1 if (b0 and b1) else None
    if r:
        # 区间内组合净值（用 nav 区间近似）
        n0 = nav_d.get(month_add(m0, 0))
        n1 = nav_d.get(m1)
        nret = n1 / n0 - 1 if (n0 and n1) else None
        nret_s = f"净值{nret:+.1%}" if nret is not None else "净值--"
        print(f"{m0} → {m1}: 持仓{len(tks):2d}只 等权价格收益 {r[0]:+.1%}  基准 {bret:+.1%}  {nret_s}")

print()
print("=" * 100)
print("二、每期持仓行业分布（申万一级）")
print("=" * 100)
for m0 in starts:
    tks = list(wts[m0].keys())
    ind = {}
    for tk in tks:
        d0 = dets[m0].get(tk, {})
        sw1 = d0.get('sw1', '?')
        ind[sw1] = ind.get(sw1, 0) + 1
    top = sorted(ind.items(), key=lambda x: -x[1])[:5]
    print(f"{m0} ({len(tks)}只): " + "  ".join(f"{k}×{v}" for k, v in top))

print()
print("=" * 100)
print("三、每期持仓特征：营收YoY中位数 / 价格÷TTM营收(相对估值proxy)中位数")
print("=" * 100)
# 预计算 ttm 表（简化：直接用各报告期最新 revenue 年度化）
def ttm_simple(per):
    qp = {}
    for pk, m in per.items():
        try:
            y, q = int(pk.split('-')[0]), int(pk.split('-')[1])
        except Exception:
            continue
        if m.get('revenue'):
            qp[(y, q)] = m['revenue']
    if not qp:
        return None
    (y, q), rev = max(qp.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    py = qp.get((y - 1, q))
    pf = qp.get((y - 1, 4))
    if py and pf and pf > py:
        return rev + (pf - py)
    mult = {1: 4.0, 2: 2.0, 3: 4.0 / 3.0, 4: 1.0}.get(q)
    return rev * mult if mult else None

import datetime
def asof_of(month):
    y, m = int(month[:4]), int(month[5:])
    return f"{y}-{m:02d}-30"

for m0 in starts:
    asof = asof_of(m0)
    tks = list(wts[m0].keys())
    yoys, pxs = [], []
    for tk in tks:
        per = fin.get(tk, {})
        pit = {k: v for k, v in per.items() if k <= m0.replace('-', '-')}  # 粗PIT
        # 用报告期截止 <= asof 的记录
        pit = {k: v for k, v in per.items() if k <= f"{m0}-99"}  # 全部可用
        # 简化：选最新
        yoy = dets[m0].get(tk, {}).get('yoy')
        if yoy:
            yoys.append(yoy)
        px = prices.get(tk, {}).get(m0)
        ttm = ttm_simple(per)
        if px and ttm:
            pxs.append(px / ttm)
    ym = statistics.median(yoys) if yoys else None
    pm = statistics.median(pxs) if pxs else None
    print(f"{m0}: YoY中位 {ym*100:+.0f}%  价格/TTM营收中位 {pm:.6f}" if ym and pm else f"{m0}: YoY {ym} px/ttm {pm}")
