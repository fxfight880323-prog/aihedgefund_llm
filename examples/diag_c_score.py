"""Deep-dive diagnostics for C-Score vs F-Score backtest results.

Analyzes:
  1. Per-period returns of variant A (consensus) vs C (actual financials)
  2. Holding overlap between variants
  3. Sector exposure of variant A
  4. C-Score threshold sensitivity (C>=2, C>=3, C>=4)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData, _month_span
from src.signals.c_score import calculate_c_score
from backtest_c_score import (
    load_consensus, build_c_signals, WeightsStrategy, run_variant,
    build_fc_signals, CAPITAL,
)
from backtest_f_score import (
    build_signals as build_f_signals, blend_weights, PIT_DATES,
    PE_MAX, PB_MAX, _safe,
)

SEL_FILE = "_bt_fscore_selection.json"


def main():
    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    cons = load_consensus()
    prices = json.load(open("_bt_fscore_prices.json", encoding="utf-8"))
    bench = json.load(open("_bt_benchmark.json", encoding="utf-8"))
    res = json.load(open("_bt_cscore_results.json", encoding="utf-8"))

    navs = {r["name"]: {n["month"]: n["nav"] for n in r["nav"]}
            for r in res}
    a_nav = navs["A: C-Score + BM (纯一致预期)"]
    c_nav = navs["C: F-Score + BM (基线, 实际财报)"]

    # 1. Per-period returns A vs C
    print("=" * 70)
    print("① 逐期收益对比 (A=一致预期 vs C=实际财报)")
    print("=" * 70)
    months = sorted(a_nav.keys())
    rebal = [m for m, *_ in PIT_DATES]
    # period = rebalance month -> next rebalance month
    for i, m in enumerate(rebal):
        end = rebal[i + 1] if i + 1 < len(rebal) else months[-1]
        if m not in a_nav or end not in a_nav:
            continue
        ra = a_nav[end] / a_nav[m] - 1
        rc = c_nav[end] / c_nav[m] - 1 if m in c_nav and end in c_nav else None
        rb = bench[end] / bench[m] - 1 if bench.get(m) and bench.get(end) else None
        rc_s = f"{rc:+.1%}" if rc is not None else "  n/a"
        rb_s = f"{rb:+.1%}" if rb is not None else "  n/a"
        print(f"  {m} → {end}:  A {ra:+.1%}  C {rc_s}  bench {rb_s}"
              f"  {'A胜' if rc is not None and ra > rc else 'C胜'}")

    # 2. Holding overlap A vs C
    print("\n" + "=" * 70)
    print("② 持仓重叠度 (A ∩ C / A)")
    print("=" * 70)
    for month, as_of, *_ in PIT_DATES:
        candidates = sel[month]["candidates"]
        cons_map = cons.get(month, {})
        a_sigs, _ = build_c_signals(candidates, cons_map, as_of)
        c_sigs, _ = build_f_signals(candidates, as_of, month)
        a_set = {s.ticker for s in a_sigs}
        c_set = {s.ticker for s in c_sigs}
        ov = a_set & c_set
        print(f"  {month}: A={len(a_set)} C={len(c_set)} overlap={len(ov)}"
              f" ({len(ov)/max(1,len(a_set)):.0%})")

    # 3. Sector exposure of variant A buys
    print("\n" + "=" * 70)
    print("③ A 组合行业分布 (申万一级, 全期汇总)")
    print("=" * 70)
    sec_all = Counter()
    for month, as_of, *_ in PIT_DATES:
        candidates = sel[month]["candidates"]
        cons_map = cons.get(month, {})
        a_sigs, _ = build_c_signals(candidates, cons_map, as_of)
        cand_map = {c["tk"]: c for c in candidates}
        for s in a_sigs:
            sw1 = cand_map.get(s.ticker, {}).get("sw1", "?")
            sec_all[sw1] += 1
    for sw, n in sec_all.most_common(10):
        print(f"  {sw}: {n}")

    # 4. Threshold sensitivity: C >= 2 / C >= 3 / C >= 4
    print("\n" + "=" * 70)
    print("④ C-Score 阈值敏感性")
    print("=" * 70)
    import src.signals.c_score as cs_mod

    bars_all = {
        tk: {mk: BarData(tk, mk, px, px, px, px)
             for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        for tk, m in prices.items()
    }
    bars_all = {tk: m for tk, m in bars_all.items() if m}

    for thresh in (2, 3, 4):
        cs_mod.C_SCORE_BUY = thresh
        w: dict[str, dict[str, float]] = {}
        for month, as_of, *_ in PIT_DATES:
            candidates = sel[month]["candidates"]
            cons_map = cons.get(month, {})
            sigs, _ = build_c_signals(candidates, cons_map, as_of)
            w[month] = blend_weights(sigs)
        n_hold = sum(len(x) for x in w.values()) / len(w)
        engine = BacktestingEngine()
        engine.set_parameters(symbols=list(bars_all.keys()),
                              capital=CAPITAL,
                              rate=0.0005, slippage=0.001)
        engine.add_data(bars_all)
        strat = WeightsStrategy(engine, {"weights_by_dt": w})
        engine.add_strategy(strat)
        engine.run_backtesting()
        daily = engine.calculate_result()
        bal = {r["dt"]: r["balance"] for r in daily}
        dts = sorted(bal.keys())
        tot = bal[dts[-1]] / CAPITAL - 1
        yrs = _month_span(dts[0], dts[-1]) / 12
        ann = (1 + tot) ** (1 / yrs) - 1
        stats = engine.calculate_statistics(daily, output=False)
        mdd = stats.get("max_ddpercent", 0) / 100
        print(f"  C>={thresh}: hold={n_hold:.0f} 总收益 {tot:+.1%} "
              f"年化 {ann:+.1%} 回撤 {mdd:.1%}")

    # restore
    cs_mod.C_SCORE_BUY = 3


if __name__ == "__main__":
    main()
