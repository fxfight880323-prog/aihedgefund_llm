# -*- coding: utf-8 -*-
"""ROA 加权强化实验：undervalued 组内按 ROA 权重分配 conviction。

目标：回答"若 undervalued 组（高 F-score + 高 BM）内不按 F-score 等
权分配 conviction，而是按 ROA 加权（高 ROA → 高 conviction → 更多
仓位），5 年回测效果会怎样"。

逻辑（诚实标注，全部 point-in-time，无未来数据）：

  baseline（_bt_fscore_nav.json）:
    undervalued: conviction = 0.5 + 0.1*(F-7)     # 仅看 F-score
    其他组:      原逻辑不变

  roa_weight:
    undervalued: conviction = 0.3 + 0.7 * roa_norm  # ROA 归一化 [0,1]
    其中 roa_norm = (roa - min_roa) / (max_roa - min_roa)
    仅在 undervalued 组内归一化（同月同组内比较）
    其他组: 原逻辑不变

  → blend_weights 按 conviction 占比分配仓位，单票 6% 上限不变。

用法: python _fs_roaw_variant.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData, _month_span
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal
from src.signals.f_score import (
    calculate_f_score,
    classify_expectation,
    _safe,
)

# Reuse cached data from baseline F-score backtest
SEL_FILE = "_bt_fscore_selection.json"
PRICES_FILE = "_bt_fscore_prices.json"
BENCH_FILE = "_bt_benchmark.json"
NAV_FILE = "_bt_fscore_roaw_nav.json"
BASELINE_NAV_FILE = "_bt_fscore_nav.json"

CAPITAL = 1_000_000
PER_NAME_CAP = 0.06
GROSS_TARGET = 1.0
MIN_HOLDINGS = 15
F_SCORE_THRESHOLD = 7
PE_MAX = 20.0
PB_MAX = 2.0

# PIT dates (same as baseline)
PIT_DATES = [
    ("2021-08", "2021-08-31", "2021年中报", "2020年中报"),
    ("2022-04", "2022-04-30", "2021年年报", "2020年年报"),
    ("2022-08", "2022-08-31", "2022年中报", "2021年中报"),
    ("2023-04", "2023-04-30", "2022年年报", "2021年年报"),
    ("2023-08", "2023-08-31", "2023年中报", "2022年中报"),
    ("2024-04", "2024-04-30", "2023年年报", "2022年年报"),
    ("2024-08", "2024-08-31", "2024年中报", "2023年中报"),
    ("2025-04", "2025-04-30", "2024年年报", "2023年年报"),
    ("2025-08", "2025-08-31", "2025年中报", "2024年中报"),
    ("2026-04", "2026-04-30", "2025年年报", "2024年年报"),
]


# ===========================================================================
# Phase 1: Build signals with ROA-weighted conviction for undervalued
# ===========================================================================

def build_signals_roa_weighted(
    candidates: list[dict],
    as_of: str,
    month: str,
) -> tuple[list[Signal], dict]:
    """Calculate F-score, classify expectation, then for undervalued
    stocks, set conviction proportional to ROA (within-group normalized).

    Two-pass approach:
      Pass 1: compute F-scores, identify undervalued stocks, collect ROAs
      Pass 2: set conviction — undervalued = 0.3 + 0.7*roa_norm, others = original
    """
    # --- Pass 1: compute F-scores and collect undervalued ROAs ---
    scored: list[dict] = []
    undervalued_roas: list[float] = []

    # Compute PB tercile thresholds
    pbs = [c["pb"] for c in candidates if c["pb"] and c["pb"] > 0]
    if len(pbs) < 5:
        return [], {}
    pb_p33 = sorted(pbs)[len(pbs) // 3]
    pb_p67 = sorted(pbs)[len(pbs) * 2 // 3]

    for c in candidates:
        tk = c["tk"]
        curr = c["curr"]
        prev = c.get("prev", {})

        if not curr or not curr.get("roa"):
            continue

        pe = _safe(c.get("pe"))
        pb = _safe(c.get("pb"))
        if pb is None or pb <= 0:
            continue
        if pe is not None and pe > PE_MAX:
            continue
        if pb > PB_MAX:
            continue

        f_score, f_detail = calculate_f_score(curr, prev)

        bm = 1.0 / pb
        if pb <= pb_p33:
            bm_tercile = "high"
        elif pb >= pb_p67:
            bm_tercile = "low"
        else:
            bm_tercile = "mid"

        expectation = classify_expectation(f_score, bm_tercile)
        roa = _safe(curr.get("roa"))

        scored.append({
            "tk": tk, "name": c["name"], "sw1": c["sw1"],
            "pe": pe, "pb": pb, "bm": round(bm, 4),
            "f_score": f_score, "f_detail": f_detail,
            "bm_tercile": bm_tercile,
            "expectation": expectation,
            "roa": roa,
            "curr": curr, "prev": prev,
        })

        if expectation == "undervalued" and roa is not None:
            undervalued_roas.append(roa)

    # Compute ROA normalization range within undervalued group
    if undervalued_roas:
        # Use robust bounds: 5th and 95th percentile to avoid outlier sensitivity
        sorted_roas = sorted(undervalued_roas)
        n = len(sorted_roas)
        p5 = sorted_roas[max(0, n // 20)]
        p95 = sorted_roas[min(n - 1, n * 19 // 20)]
        # Fallback if not enough spread
        if p95 <= p5:
            p5 = sorted_roas[0]
            p95 = sorted_roas[-1]
    else:
        p5 = p95 = 0.0

    # --- Pass 2: assign conviction ---
    signals: list[Signal] = []
    detail: dict[str, dict] = {}

    for s in scored:
        exp = s["expectation"]
        roa = s["roa"]
        f_score = s["f_score"]

        if exp == "undervalued":
            # ROA-weighted conviction: map ROA to [0.3, 1.0]
            if p95 > p5 and roa is not None:
                roa_norm = max(0.0, min(1.0, (roa - p5) / (p95 - p5)))
            elif roa is not None and roa > 0:
                roa_norm = 0.5  # single undervalued stock or no spread
            else:
                roa_norm = 0.3
            value = 0.3 + 0.7 * roa_norm  # [0.3, 1.0]
        elif f_score >= F_SCORE_THRESHOLD and s["bm_tercile"] in ("high", "mid"):
            value = 0.3 + 0.05 * (f_score - F_SCORE_THRESHOLD)
            value = min(0.5, value)
        elif f_score >= 5 and s["bm_tercile"] == "high":
            value = 0.15
        else:
            value = 0.0

        if value > 0:
            signals.append(Signal(
                model_name="f_score_roaw",
                ticker=s["tk"],
                date=as_of,
                value=round(value, 4),
                reasoning=(
                    f"F={f_score}/9 BM_tercile={s['bm_tercile']} "
                    f"PE={s['pe']} PB={s['pb']:.2f} exp={exp} "
                    f"ROA={roa} roa_norm={value:.3f}"
                ),
                components={
                    "f_score": float(f_score),
                    "bm": s["bm"],
                    "pe": s["pe"] or 0.0,
                    "pb": s["pb"] or 0.0,
                    "roa": roa or 0.0,
                },
                metadata={
                    "f_detail": s["f_detail"],
                    "expectation": exp,
                    "name": s["name"],
                    "sw1": s["sw1"],
                    "roa": roa,
                },
            ))
            detail[s["tk"]] = {
                "name": s["name"], "sw1": s["sw1"],
                "f_score": f_score, "f_detail": s["f_detail"],
                "pe": s["pe"], "pb": s["pb"], "bm": s["bm"],
                "bm_tercile": s["bm_tercile"],
                "expectation": exp,
                "conviction": value,
                "roa": roa,
            }

    signals.sort(key=lambda sig: -sig.value)
    return signals, detail


def blend_weights(signals: list[Signal]) -> dict[str, float]:
    """Conviction-weighted + per-name cap + scale to gross target."""
    if not signals:
        return {}
    total_conv = sum(s.value for s in signals)
    if total_conv <= 0:
        return {}
    weights: dict[str, float] = {}
    for sig in signals:
        w = sig.value / total_conv * GROSS_TARGET
        weights[sig.ticker] = min(w, PER_NAME_CAP)

    invested = sum(weights.values())
    if invested < GROSS_TARGET * 0.9 and len(weights) < MIN_HOLDINGS:
        if invested > 0:
            scale = GROSS_TARGET / invested
            for tk in weights:
                weights[tk] = min(weights[tk] * scale, PER_NAME_CAP)
    return weights


# ===========================================================================
# Phase 2: vnpy-style backtest
# ===========================================================================

class FScoreROAStrategy(StrategyTemplate):
    """Pre-computed weights strategy for F-score ROA-weighted backtest."""

    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
        self.detail_by_dt = setting.get("detail_by_dt", {})
        self.history: list[dict] = []

    def on_bars(self, bars):
        dt = self.engine.datetime
        if dt not in self.weights_by_dt:
            return
        weights = self.weights_by_dt[dt]
        equity = self.engine.get_equity(bars)
        self.target_data = {}
        for tk, w in weights.items():
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar and bar.close_price > 0:
                self.target_data[tk] = w * equity / bar.close_price
        for s, pos in list(self.engine.pos_data.items()):
            if pos > 0 and s not in weights:
                self.target_data[s] = 0.0
        self.rebalance_portfolio(bars)

        detail = self.detail_by_dt.get(dt, {})
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "weights": weights,
            "names": [
                (detail[t]["name"], detail[t]["sw1"],
                 detail[t]["f_score"], w, detail[t].get("expectation", ""),
                 detail[t].get("roa"))
                for t, w in sorted(weights.items(), key=lambda x: -x[1])
                if t in detail
            ],
        })


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 78)
    print("  F-Score ROA 加权强化 · undervalued 组按 ROA 分配 conviction")
    print("  基线: F-Score +12.6% / 回撤 -17.1% / 超额 +8.1pp")
    print("  变更: undervalued conviction = 0.3 + 0.7*ROA_norm")
    print("  半年度调仓 | 单票 6% | 成本 5bp+10bp | PIT 无未来数据")
    print("=" * 78)

    # Load cached selection data
    if not os.path.exists(SEL_FILE):
        print(f"\n  缓存 {SEL_FILE} 不存在，请先运行 backtest_f_score.py --select")
        return
    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    print(f"\n① 加载选择缓存: {len(sel)} 期")

    # Phase 2: Build signals with ROA-weighted conviction
    print("\n② F-Score 计算 + ROA 加权 conviction")
    weights_by_dt, detail_by_dt = {}, {}
    for month, as_of, cn_period, cn_prev in PIT_DATES:
        if month not in sel:
            continue
        candidates = sel[month]["candidates"]
        signals, detail = build_signals_roa_weighted(candidates, as_of, month)
        weights = blend_weights(signals)
        weights_by_dt[month] = weights
        detail_by_dt[month] = detail

        exp_counts: dict[str, int] = {}
        f_scores: list[int] = []
        roa_vals: list[float] = []
        for d in detail.values():
            exp_counts[d["expectation"]] = (
                exp_counts.get(d["expectation"], 0) + 1)
            f_scores.append(d["f_score"])
            if d.get("roa") is not None:
                roa_vals.append(d["roa"])
        avg_f = (sum(f_scores) / len(f_scores) if f_scores else 0)
        avg_roa = (sum(roa_vals) / len(roa_vals) if roa_vals else 0)
        undervalued_n = exp_counts.get("undervalued", 0)
        print(
            f"  [{month}] 候选 {len(candidates)} → "
            f"信号 {len(signals)} → 持仓 {len(weights)} 只 | "
            f"avg F={avg_f:.1f} avg ROA={avg_roa:.2f} | "
            f"undervalued={undervalued_n} | "
            f"gross {sum(weights.values()):.0%}"
        )

    # Phase 3: Load price data
    print("\n③ 加载价格数据")
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    print(f"  价格: {len(prices)} 只 | 基准: {len(bench)} 月")

    # Phase 4: Engine backtest
    print("\n④ 引擎回测…")
    bars = {
        tk: {mk: BarData(tk, mk, px, px, px, px)
             for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        for tk, m in prices.items()
    }
    bars = {tk: m for tk, m in bars.items() if m}

    engine = BacktestingEngine()
    engine.set_parameters(
        symbols=list(bars.keys()),
        capital=CAPITAL,
        rate=0.0005,
        slippage=0.001,
    )
    engine.add_data(bars)
    strategy = FScoreROAStrategy(engine, {
        "weights_by_dt": weights_by_dt,
        "detail_by_dt": detail_by_dt,
    })
    engine.add_strategy(strategy)
    engine.run_backtesting()

    # Phase 5: Results
    print("\n⑤ 结算…")
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily)

    # Benchmark comparison
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())
    if dts and dts[0] in bench and dts[-1] in bench:
        r = bal[dts[-1]] / CAPITAL - 1
        br = bench[dts[-1]] / bench[dts[0]] - 1
        yrs = _month_span(dts[0], dts[-1]) / 12
        print(f"\n  基准: 策略 {r:+.1%} vs 沪深300 {br:+.1%} | "
              f"超额 {r - br:+.1%} | 年化 {((1+r)**(1/yrs)-1):+.1%}"
              f" vs {((1+br)**(1/yrs)-1):+.1%}")

    # Phase 6: Per-period diagnostics
    print("\n⑥ 逐期诊断")
    hist_dts = [h["dt"] for h in strategy.history]
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        if mk not in bal:
            continue
        nxt = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
        end_mk = nxt if nxt in bal else dts[-1]
        ret = bal[end_mk] / bal[mk] - 1 if end_mk in bal else 0.0
        br = (bench[end_mk] / bench[mk] - 1
              if bench.get(mk) and bench.get(end_mk) else None)
        ex = (f" | 基准 {br:+.1%} | 超额 {ret - br:+.1%}"
              if br is not None else "")
        print(f"\n  > {mk}: {ret:+.1%}{ex} ({h['n']} 只, "
              f"gross {sum(h['weights'].values()):.0%})")
        for name, sw1, fs, w, exp, roa in h["names"][:8]:
            roa_str = f"ROA={roa:.2f}" if roa is not None else "ROA=N/A"
            print(f"     {name:8s} {sw1:6s} F={fs} {exp:14s} {w:.1%} {roa_str}")

    # Baseline comparison
    if os.path.exists(BASELINE_NAV_FILE):
        print("\n⑦ 与基线对比")
        base_nav = json.loads(open(BASELINE_NAV_FILE, encoding="utf-8").read())
        base_s = {n["month"]: n["nav"] / CAPITAL for n in base_nav}
        new_s = {r["dt"]: r["balance"] / CAPITAL for r in daily if r["dt"] in bench}

        common = sorted(set(base_s.keys()) & set(new_s.keys()))
        if common:
            b_ret = base_s[common[-1]] - 1
            n_ret = new_s[common[-1]] - 1
            print(f"  基线 F-Score:    {b_ret:+.1%}")
            print(f"  ROA 加权强化:    {n_ret:+.1%}")
            print(f"  差异:            {n_ret - b_ret:+.1%} pp")

    # Save NAV
    nav = [{"month": r["dt"], "nav": r["balance"]}
           for r in daily if r["dt"] in bench]
    json.dump(nav, open(NAV_FILE, "w", encoding="utf-8"))
    print(f"\n  NAV -> {NAV_FILE}")


if __name__ == "__main__":
    main()
