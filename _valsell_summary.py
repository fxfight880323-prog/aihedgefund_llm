# -*- coding: utf-8 -*-
import json

modes = ['baseline', 'val15', 'val20', 'decel20', 'decel2q', 'valdecel']
for m in modes:
    d = json.load(open(f'_bt_gl_valsell_{m}_diag.json', encoding='utf-8'))
    sv = d['sell_verify']
    avg = '--' if sv.get('avg_ret_6m') is None else f"{sv['avg_ret_6m']:+.1%}"
    print(f"{m:9s} 总收益 {d['total_return']:+7.1%} "
          f"年化 {d['annualized']:+6.1%} 回撤 {d['mdd']:7.1%} "
          f"超额 {d['excess']:+7.1%} 卖出 {d['n_sells']:3d} 笔 "
          f"后6月 {avg} 卖对 {sv['right']}/{sv['n']}")

navs = {}
for m in modes:
    rows = json.load(open(f'_bt_gl_valsell_{m}_nav.json', encoding='utf-8'))
    navs[m] = {r['month']: r['nav'] for r in rows}
months = sorted(list(navs['baseline'].keys()))

def bucket(m):
    y = int(m[:4])
    return '2021H2' if y == 2021 else ('2026H1' if y == 2026 else str(y))

print()
for m in navs:
    per = {}
    dts = [x for x in months if x in navs[m]]
    for i, x in enumerate(dts):
        end = dts[i + 1] if i + 1 < len(dts) else dts[-1]
        if end != x:
            b = bucket(x)
            r = navs[m][end] / navs[m][x] - 1.0
            per[b] = per.get(b, 1.0) * (1 + r) - 1.0
    line = "  ".join(f"{k} {v:+.1%}" for k, v in per.items())
    print(f"{m:9s} {line}")
