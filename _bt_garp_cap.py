# -*- coding: utf-8 -*-
"""市值加权集中度权衡实验（承接四环节归因）。

问题：g60 等权 +67.01%（分散），纯市值加权 +106.46%（前3家集中60%）。
问：市值加权 + 单票上限(cap) 或 市值开根号，能否既保留大盘价值暴露、又压掉集中度？

变体（全部 full 基座，PE升序 top40，日频复权，含成本 5bp+10bp）:
  g60        等权（锚点）
  mvw_nocap  纯市值加权
  mvw_cap15  市值加权 + 单票上限 15%
  mvw_cap10  市值加权 + 单票上限 10%
  mvw_cap8   市值加权 + 单票上限 8%
  mvw_cap5   市值加权 + 单票上限 5%
  sqrt_mv    市值开根号加权（天然降集中）

指标：总收益/年化/MDD + 集中度（每期 top3 权重占比均值、每期 HHI→有效持仓数 N_eff）。
"""
import json, os, sys, datetime
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import screen_decomp, load_bars

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS = L.MAX_HOLDINGS


def cap_weight(picked, cap):
    """市值加权 + 单票上限 cap（迭代 waterfall：超 cap 截断，多余按市值再分配）。"""
    mv = {s["tk"]: s["mv"] for s in picked}
    tot = sum(mv.values())
    w = {tk: m / tot for tk, m in mv.items()}
    for _ in range(200):
        over = {tk: wv - cap for tk, wv in w.items() if wv > cap + 1e-12}
        if not over:
            break
        excess = sum(over.values())
        under = {tk: mv[tk] for tk in w if w[tk] <= cap + 1e-12}
        if not under:
            break
        utot = sum(under.values())
        for tk in over:
            w[tk] = cap
        for tk in under:
            w[tk] += excess * under[tk] / utot
    return w


def sqrt_weight(picked):
    mv = {s["tk"]: s["mv"] ** 0.5 for s in picked}
    tot = sum(mv.values())
    return {tk: m / tot for tk, m in mv.items()}


def conc_metrics(all_w):  # all_w: {month: {tk: w}}
    top3s, hhis = [], []
    for month, w in all_w.items():
        ws = sorted(w.values(), reverse=True)
        top3s.append(sum(ws[:3]))
        hhis.append(sum(x * x for x in w.values()))
    n = len(all_w)
    return (sum(top3s) / n, sum(hhis) / n, 1.0 / (sum(hhis) / n))


def main():
    print("=" * 88)
    print("  市值加权集中度权衡实验（PE升序 top40，full 基座，日频+复权）")
    print("=" * 88)

    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)

    # g60 池 top40（与归因脚本同口径）
    picks = {}
    for month, as_of in PIT_DATES:
        m = univ[month]
        vv, ff, cc = val[month], fac[month], cons[month]
        pool = screen_decomp(month, m, vv, ff, cc, set(), 100.0, 60.0, 1.0, True, True)
        pool.sort(key=lambda s: s["pe"])
        picks[month] = pool[:MAX_HOLDINGS]

    # 权重方案
    schemes = {
        "g60":        lambda p: {s["tk"]: round(min(1.0 / max(len(p), 1), 0.05), 4) for s in p},
        "mvw_nocap":  lambda p: {s["tk"]: s["mv"] / sum(x["mv"] for x in p) for s in p},
        "mvw_cap15":  lambda p: cap_weight(p, 0.15),
        "mvw_cap10":  lambda p: cap_weight(p, 0.10),
        "mvw_cap8":   lambda p: cap_weight(p, 0.08),
        "mvw_cap5":   lambda p: cap_weight(p, 0.05),
        "sqrt_mv":    lambda p: sqrt_weight(p),
    }

    # 装载价格
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"  复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 覆盖审计
    miss = {}
    for month, as_of in PIT_DATES:
        mm = [s["tk"] for s in picks[month] if s["tk"] not in px_syms]
        if mm:
            miss[month] = mm
    print(f"  [覆盖审计] g60 top40 丢股: {sum(len(v) for v in miss.values())} 只-期 "
          f"{'✓ 全覆盖' if not miss else '⚠️'}")

    results = {}
    conc = {}
    for name, fn in schemes.items():
        all_w = {}
        for month, as_of in PIT_DATES:
            w = fn(picks[month])
            all_w[month] = w
        w_by_dt = {}
        for month, asof in PIT_DATES:
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = all_w[month]
        r = G.run(name, w_by_dt, bars)
        top3, hhi, neff = conc_metrics(all_w)
        results[name] = r
        conc[name] = {"top3": top3, "hhi": hhi, "neff": neff}
        print(f"  {name:12s}: 总 {r['total']:+7.2%} 年化 {r['ann']:+6.2%} MDD {r['mdd']:6.2%} "
              f"| top3 {top3:5.1%} HHI {hhi:.3f} N_eff {neff:5.1f}")

    # 锚点
    audit = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
    print(f"\n  [锚点] g60={results['g60']['total']:+.4f} (期望 +0.6701) | "
          f"mvw_nocap={results['mvw_nocap']['total']:+.4f} (期望 +1.0646)")

    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "window": [all_dates[0], all_dates[-1]]},
        "results": {k: {kk: vv for kk, vv in v.items() if kk != "nav"}
                    for k, v in results.items()},
        "conc": conc,
        "coverage_miss": miss,
    }
    json.dump(out, open("_bt_garp_cap_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_cap_results.json")


if __name__ == "__main__":
    main()
