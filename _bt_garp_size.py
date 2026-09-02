# -*- coding: utf-8 -*-
"""持仓规模对 g60 单点依赖的影响：top40 → top120 扩大持仓能否摊平 2024 单点。

任务11 核心：Q1分位(几百只)比 top40(40只)更分散，但持有几百只不现实，
折中是扩大 topN。检验 N=40/60/80/100/120 的收益、MDD、单点依赖度。
口径：full基座(含金融)、日频复权、含成本5bp+10bp、PE升序等权。
"""
import json, os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import (load_all, screen_decomp, load_bars,
                                build_weights)

PIT_DATES = L.PIT_DATES
G60_G, G60_PEG = 60.0, 1.0
SIZES = [40, 60, 80, 100, 120]


def yearly(nav_list):
    d = {x["date"]: x["nav"] for x in nav_list}
    dts = sorted(d)
    years = sorted(set(dt[:4] for dt in dts))
    out, prev_end = {}, None
    for y in years:
        y_dts = [dt for dt in dts if dt[:4] == y]
        end = d[y_dts[-1]]
        out[y] = end / d[y_dts[0]] - 1 if prev_end is None else end / prev_end - 1
        prev_end = end
    return out


def dep_best(yearly_ret):
    """单点依赖度：1 - 去最好年后收益/总收益"""
    total = 1.0
    for y, r in yearly_ret.items():
        total *= (1 + r)
    total -= 1
    best = max(yearly_ret.values())
    ex = 1.0
    for y, r in yearly_ret.items():
        if r == best:
            continue
        ex *= (1 + r)
    ex -= 1
    return 1 - ex / total if total > 0 else float("nan")


def main():
    print("=" * 88)
    print("  持仓规模 top40→120 对 g60 单点依赖的影响（日频+复权，full基座）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())

    pools = {n: {} for n in SIZES}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        p = screen_decomp(month, members, vv, ff, cc, set(),
                          100.0, G60_G, G60_PEG, True, True)
        sp = sorted(p, key=lambda s: s["pe"])
        for n in SIZES:
            pools[n][month] = sp[:n]

    res = {}
    for n in SIZES:
        w_by_dt = {}
        for month, asof in PIT_DATES:
            wgt = build_weights(pools[n][month], "equal")
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = wgt
        r = G.run(f"top{n}", w_by_dt, bars)
        r["yearly"] = yearly(r["nav"])
        r["dep"] = dep_best(r["yearly"])
        res[n] = r

    print("\n[结果] 持仓规模 → 收益/MDD/依赖度:")
    print(f"{'持仓':>6}{'总收益':>10}{'年化':>8}{'MDD':>8}{'依赖度':>8}{'2021-23':>10}{'2024-26':>10}")
    for n in SIZES:
        r = res[n]
        yl = r["yearly"]
        years = sorted(yl)
        early = 1.0; late = 1.0
        for y in years:
            rr = 1 + yl[y]
            if y <= "2023":
                early *= rr
            else:
                late *= rr
        print(f"{n:>6}{r['total']*100:>9.1f}%{r['ann']*100:>7.1f}%{r['mdd']*100:>7.1f}%"
              f"{r['dep']:>7.2f}{early-1:>9.1f}%{late-1:>9.1f}%")

    print("\n[分年度收益矩阵]（%）:")
    years = sorted(set(y for n in SIZES for y in res[n]["yearly"]))
    print(f"{'持仓':>6}" + "".join(f"{y:>9}" for y in years))
    for n in SIZES:
        yl = res[n]["yearly"]
        print(f"{n:>6}" + "".join(f"{yl.get(y,0)*100:>9.1f}" for y in years))

    # 覆盖审计
    print("\n[覆盖审计] 各规模选股并集 vs 530只差集:")
    for n in SIZES:
        miss = 0
        for month, _ in PIT_DATES:
            miss += sum(1 for s in pools[n][month] if s["tk"] not in px_syms)
        print(f"  top{n}: {miss} 只-期缺失 {'⚠️' if miss else '✓'}")

    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "base": "full(含金融)", "freq": "日频+复权",
                 "sizes": SIZES},
        "results": {str(n): {"total": res[n]["total"], "ann": res[n]["ann"],
                             "mdd": res[n]["mdd"], "dep": res[n]["dep"],
                             "yearly": res[n]["yearly"]} for n in SIZES},
    }
    json.dump(out, open("_bt_garp_size_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_size_results.json")


if __name__ == "__main__":
    main()
