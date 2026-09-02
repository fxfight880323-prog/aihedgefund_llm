# -*- coding: utf-8 -*-
"""剔除极端低PE陷阱（PE<5 且非金融）对 g60 的影响。

承接 10 年结论：top40 极端低PE(PE1-5)是价值陷阱，Q1剔top40(健康低PE)收益更高。
但 5 年窗口 g60 已叠加 garp 门控(PEG≤1)，门控是否已筛掉陷阱？

诊断发现：g60 top40 在 2021-2023 仍混入大量 PE<5 地产/周期陷阱股
(2021-08 有28只、2023-04 有26只)，2024 后骤减。这些是 2021-2023 负收益的元凶。

本实验：剔除 PE<5(及 PE<8) 非金融陷阱股（保留 PE<5 的正常银行），
看早期收益是否改善、对 2024-2025 的单点依赖是否下降。

口径：full 基座(含金融)、日频复权、含成本 5bp+10bp、PE升序 top40 等权。
锚点：g60 ≈ +67.01%（_bt_garp_audit_results.json rerun.full.g60）。
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
MAX_HOLDINGS = L.MAX_HOLDINGS
G60_G, G60_PEG = 60.0, 1.0


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


def main():
    print("=" * 88)
    print("  剔除极端低PE陷阱(PE<5 非金融) 对 g60 的影响（日频+复权，full基座）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()
    print(f"金融名单: {len(fin)} 只")

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    price_pools = {k: {} for k in ["g60", "no_trap5", "no_trap8"]}
    trap_report = {}          # month -> 被剔除的陷阱股
    fin_count = {k: {} for k in price_pools}   # month -> 金融数

    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        p = screen_decomp(month, members, vv, ff, cc, set(),
                          100.0, G60_G, G60_PEG, True, True)

        p_g60 = sorted(p, key=lambda s: s["pe"])[:MAX_HOLDINGS]
        traps = [(s["tk"], round(s["pe"], 1))
                 for s in p_g60 if s["pe"] < 5.0 and s["tk"] not in fin]
        trap_report[month] = traps

        p_nt5 = sorted([s for s in p if not (s["pe"] < 5.0 and s["tk"] not in fin)],
                       key=lambda s: s["pe"])[:MAX_HOLDINGS]
        p_nt8 = sorted([s for s in p if not (s["pe"] < 8.0 and s["tk"] not in fin)],
                       key=lambda s: s["pe"])[:MAX_HOLDINGS]

        price_pools["g60"][month] = p_g60
        price_pools["no_trap5"][month] = p_nt5
        price_pools["no_trap8"][month] = p_nt8

        for k in price_pools:
            fin_count[k][month] = sum(1 for s in price_pools[k][month] if s["tk"] in fin)

        print(f"  [{month}] pool={len(p)} g60陷阱{len(traps)}只 | "
              f"g60金融{fin_count['g60'][month]} no_trap5金融{fin_count['no_trap5'][month]} "
              f"no_trap8金融{fin_count['no_trap8'][month]}")

    # 覆盖审计
    print("\n[覆盖审计] 选股并集 vs 530只覆盖差集:")
    cov = {}
    for k in price_pools:
        miss = {}
        for month, _ in PIT_DATES:
            m = [s["tk"] for s in price_pools[k][month] if s["tk"] not in px_syms]
            if m:
                miss[month] = m
        cov[k] = miss
        tot = sum(len(x) for x in miss.values())
        print(f"    {k:10s}: {tot:3d} 只-期缺失 {'⚠️' if tot else '✓'}")

    # 回测
    print("\n[回测] 价格回测（含成本 5bp+10bp）…")
    res = {}
    for k in price_pools:
        w_by_dt = {}
        for month, asof in PIT_DATES:
            picked = price_pools[k][month]
            wgt = build_weights(picked, "equal")
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = wgt
        r = G.run(k, w_by_dt, bars)
        r["yearly"] = yearly(r["nav"])
        res[k] = r
        print(f"  {k:10s}: 总 {r['total']:+7.2%} 年化 {r['ann']:+6.2%} MDD {r['mdd']:6.2%}")

    # 锚点
    audit = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
    g60_hist = audit["rerun"]["full"]["g60"]["total"]
    print(f"  [锚点] g60={res['g60']['total']:+.4f} vs audit {g60_hist:+.4f}")

    # 分年度对比
    print("\n[分年度收益]（%）:")
    years = sorted(set(y for k in res for y in res[k]["yearly"]))
    print(f"{'变体':<10}" + "".join(f"{y:>9}" for y in years) + f"{'合计':>9}")
    for k in price_pools:
        yl = res[k]["yearly"]
        row = f"{k:<10}" + "".join(f"{yl.get(y,0)*100:>9.1f}" for y in years)
        # 2021-2023 合计
        early = 1.0
        for y in years:
            if y <= "2023":
                early *= (1 + yl.get(y, 0))
        print(row + f"{(res[k]['total']*100):>9.1f}")

    # 2021-2023 早期 vs 2024-2025 后期 拆分
    print("\n[早/后期拆分]:")
    for k in price_pools:
        yl = res[k]["yearly"]
        early = 1.0; late = 1.0
        for y in years:
            r = 1 + yl.get(y, 0)
            if y <= "2023":
                early *= r
            else:
                late *= r
        print(f"  {k:10s}: 2021-2023 {early-1:+7.1%} | 2024-2026 {late-1:+7.1%}")

    # 落盘
    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "base": "full(含金融)", "freq": "日频+复权",
                 "trap_def": "PE<5(no_trap5) / PE<8(no_trap8) 且非金融",
                 "anchor_g60": g60_hist},
        "results": {k: {"total": res[k]["total"], "ann": res[k]["ann"],
                        "mdd": res[k]["mdd"], "yearly": res[k]["yearly"]}
                    for k in res},
        "trap_report": trap_report,
        "fin_count": fin_count,
        "coverage": cov,
    }
    json.dump(out, open("_bt_garp_notrap_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_notrap_results.json")


if __name__ == "__main__":
    main()
