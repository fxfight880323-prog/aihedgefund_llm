"""Consensus-enhanced F-Score backtest -- analyst expectations vs actual reports.

Variants (same pool, same costs, same rebalance calendar):
  A. C-Score + BM      -- pure consensus replacement (user hypothesis)
  B. F x C hybrid      -- F x BM conviction * consensus multiplier
  C. F-Score + BM      -- baseline (actual financials, for comparison)

Pool & PIT calendar identical to backtest_f_score.py:
  PB<2, PE<20, mcap>50亿, top-100 by PB, semi-annual (Apr/Aug) rebalance.

Data:
  - Candidate pool + fundamentals: _bt_fscore_selection.json (MX, cached)
  - Consensus snapshots:           _bt_cscore_consensus.json (juzi-mcp)

Run:
    python examples/backtest_c_score.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import BacktestingEngine, BarData, _month_span
from src.backtest.strategy import StrategyTemplate
from src.signals.f_score import calculate_f_score, classify_expectation, _safe
from src.signals.c_score import (
    calculate_c_score,
    classify_consensus_expectation,
    consensus_conviction,
    consensus_multiplier,
    C_SCORE_BUY,
)
from backtest_f_score import (  # reuse shared pieces
    PIT_DATES, PER_NAME_CAP, GROSS_TARGET, MIN_HOLDINGS, PE_MAX, PB_MAX,
    norm_ticker, _field, _scr_val, build_signals as build_f_signals,
    blend_weights, fetch_prices, fetch_benchmark, FScoreStrategy,
)

CAPITAL = 1_000_000

SEL_FILE = "_bt_fscore_selection.json"
CONS_FILE = "_bt_cscore_consensus.json"
PRICES_FILE = "_bt_fscore_prices.json"
BENCH_FILE = "_bt_benchmark.json"
NAV_C_FILE = "_bt_cscore_nav.json"
NAV_FC_FILE = "_bt_fcscore_nav.json"


# ===========================================================================
# Consensus loading & merging
# ===========================================================================

def load_consensus() -> dict[str, dict[str, dict]]:
    """{month: {ticker: consensus_record}} — deduped to as_of-year forecast."""
    cons = json.loads(open(CONS_FILE, encoding="utf-8").read())
    out: dict[str, dict[str, dict]] = {}
    for month, d in cons.items():
        as_of_year = int(month[:4])
        best: dict[str, dict] = {}
        for r in d.get("records", []):
            sc = r.get("stock_code", "")
            tk = norm_ticker(sc)
            if not tk:
                continue
            cy = r.get("con_year") or 0

            def dist(y):
                # prefer con_year == as_of year; next year acceptable
                if y == as_of_year:
                    return 0
                if y == as_of_year + 1:
                    return 1
                return 2 + abs((y or 0) - as_of_year)

            if tk not in best:
                best[tk] = r
            elif dist(cy) < dist(best[tk].get("con_year") or 0):
                best[tk] = r
        out[month] = best
    return out


# ===========================================================================
# Variant A: pure C-Score + BM
# ===========================================================================

def build_c_signals(candidates: list[dict], cons_map: dict[str, dict],
                    as_of: str) -> tuple[list, dict]:
    """C-Score x BM signals for the same candidate pool."""
    signals, detail = [], {}

    pbs = [c["pb"] for c in candidates if c["pb"] and c["pb"] > 0]
    if len(pbs) < 5:
        return signals, detail
    pb_p33 = sorted(pbs)[len(pbs) // 3]
    pb_p67 = sorted(pbs)[len(pbs) * 2 // 3]

    for c in candidates:
        tk = c["tk"]
        pb = _safe(c.get("pb"))
        pe = _safe(c.get("pe"))
        if pb is None or pb <= 0 or pb > PB_MAX:
            continue
        if pe is not None and pe > PE_MAX:
            continue

        rec = cons_map.get(tk)
        if not rec:
            continue  # no analyst coverage -> abstain (consensus strategy)

        c_score, c_detail = calculate_c_score(rec)
        bm = 1.0 / pb
        bm_tercile = "high" if pb <= pb_p33 else (
            "low" if pb >= pb_p67 else "mid")
        expectation = classify_consensus_expectation(c_score, bm_tercile)
        value = consensus_conviction(c_score, bm_tercile)

        if value > 0:
            from src.core.models import Signal
            signals.append(Signal(
                model_name="c_score", ticker=tk, date=as_of,
                value=round(value, 4),
                reasoning=(f"C={c_score}/4 BM={bm_tercile} "
                           f"con_roe={rec.get('con_roe')} "
                           f"con_np_yoy={rec.get('con_np_yoy')}"),
                components={"c_score": float(c_score), "bm": round(bm, 4)},
                metadata={"c_detail": c_detail, "expectation": expectation,
                          "name": c["name"], "sw1": c["sw1"]},
            ))
            detail[tk] = {
                "name": c["name"], "sw1": c["sw1"], "c_score": c_score,
                "c_detail": c_detail, "pb": pb, "pe": pe,
                "bm": round(bm, 4), "bm_tercile": bm_tercile,
                "expectation": expectation, "conviction": value,
                "con_roe": rec.get("con_roe"),
                "con_np_yoy": rec.get("con_np_yoy"),
                "con_pe": rec.get("con_pe"),
            }
    signals.sort(key=lambda s: -s.value)
    return signals, detail


# ===========================================================================
# Variant B: F x BM conviction * consensus multiplier
# ===========================================================================

def build_fc_signals(candidates: list[dict], cons_map: dict[str, dict],
                     as_of: str) -> tuple[list, dict]:
    """F-Score x BM base conviction, scaled by consensus multiplier."""
    f_signals, f_detail = build_f_signals(candidates, as_of, "")
    signals, detail = [], []

    for sig in f_signals:
        tk = sig.ticker
        rec = cons_map.get(tk)
        if not rec:
            mult = 1.0   # no coverage: keep F conviction unchanged
            c_score = None
            c_detail = {}
        else:
            c_score, c_detail = calculate_c_score(rec)
            mult = consensus_multiplier(c_score)

        base = sig.value
        value = round(min(1.0, base * mult), 4)
        if value < 0.05:
            continue   # consensus vetoed the position
        sig.value = value
        md = dict(sig.metadata or {})
        md["c_score"] = c_score
        md["consensus_mult"] = mult
        sig.metadata = md
        signals.append(sig)

        d = dict(f_detail[tk])
        d["c_score"] = c_score
        d["consensus_mult"] = mult
        d["fc_conviction"] = value
        detail.append((tk, d))
    signals.sort(key=lambda s: -s.value)
    return signals, dict(detail)


# ===========================================================================
# Multi-variant backtest runner
# ===========================================================================

class WeightsStrategy(StrategyTemplate):
    """Generic pre-computed-weights strategy (shared by all variants)."""

    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
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
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "weights": weights,
        })


def run_variant(name: str, weights_by_dt: dict, bars: dict,
                bench: dict, nav_file: str):
    engine = BacktestingEngine()
    engine.set_parameters(
        symbols=list(bars.keys()), capital=CAPITAL,
        rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {"weights_by_dt": weights_by_dt})
    engine.add_strategy(strategy)
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)

    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())
    total_ret = bal[dts[-1]] / CAPITAL - 1
    yrs = _month_span(dts[0], dts[-1]) / 12
    ann = (1 + total_ret) ** (1 / yrs) - 1
    mdd = stats.get("max_ddpercent", 0) / 100.0   # value already in %
    br = (bench[dts[-1]] / bench[dts[0]] - 1
          if dts[0] in bench and dts[-1] in bench else None)
    ex = (total_ret - br) if br is not None else None

    print(f"\n  [{name}]")
    print(f"    总收益 {total_ret:+.1%} | 年化 {ann:+.1%} | "
          f"最大回撤 {mdd:.1%} | 月数 {len(dts)}")
    if br is not None:
        print(f"    基准(沪深300) {br:+.1%} | 超额 {ex:+.1%}")

    nav = [{"month": r["dt"], "nav": r["balance"]}
           for r in daily if r["dt"] in bench]
    json.dump(nav, open(nav_file, "w", encoding="utf-8"))
    return {
        "name": name, "total": total_ret, "ann": ann, "mdd": mdd,
        "bench": br, "excess": ex,
        "nav": nav,
    }


def main():
    print("=" * 78)
    print("  分析师预期 vs 实际财报 · F-Score / C-Score / F×C 三组对比回测")
    print("  C-Score: con_roe>12% | con_np_yoy>0 | rev4w>0 | rev13w>0")
    print("  池: PB<2 PE<20 mcap>50亿 top100 | 半年调仓 | 成本 5bp+10bp")
    print("=" * 78)

    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    cons = load_consensus()
    print(f"\n① 加载: 选择缓存 {len(sel)} 期 | 一致预期 {len(cons)} 期")

    # Build weights for all variants
    print("\n② 信号构建")
    w_c: dict[str, dict[str, float]] = {}       # variant A
    w_fc: dict[str, dict[str, float]] = {}      # variant B
    w_f: dict[str, dict[str, float]] = {}       # baseline C
    diag: dict[str, dict] = {}

    for month, as_of, cn_period, cn_prev in PIT_DATES:
        if month not in sel:
            continue
        candidates = sel[month]["candidates"]
        cons_map = cons.get(month, {})

        # Variant A: pure C
        c_sigs, c_detail = build_c_signals(candidates, cons_map, as_of)
        w_c[month] = blend_weights(c_sigs)

        # Variant B: F x C hybrid
        fc_sigs, fc_detail = build_fc_signals(candidates, cons_map, as_of)
        w_fc[month] = blend_weights(fc_sigs)

        # Variant C: pure F (baseline)
        f_sigs, f_detail = build_f_signals(candidates, as_of, month)
        w_f[month] = blend_weights(f_sigs)

        # Diagnostics
        c_scores = [d["c_score"] for d in c_detail.values()]
        c_exp = Counter(d["expectation"] for d in c_detail.values())
        diag[month] = {
            "pool": len(candidates),
            "c_coverage": len(cons_map),
            "c_buys": len(c_sigs), "c_holdings": len(w_c[month]),
            "c_score_dist": dict(Counter(c_scores)),
            "c_exp": dict(c_exp),
            "fc_buys": len(fc_sigs), "fc_holdings": len(w_fc[month]),
            "f_buys": len(f_sigs), "f_holdings": len(w_f[month]),
        }
        print(
            f"  [{month}] pool={len(candidates)} cov={len(cons_map)} | "
            f"C: buy={len(c_sigs)} hold={len(w_c[month])} "
            f"dist={diag[month]['c_score_dist']} | "
            f"F×C: hold={len(w_fc[month])} | F: hold={len(w_f[month])}"
        )

    # Prices
    print("\n③ 价格数据")
    all_tickers = set()
    for w in (w_c, w_fc, w_f):
        for ww in w.values():
            all_tickers.update(ww.keys())
    prices = fetch_prices(list(all_tickers))
    bench = fetch_benchmark()

    bars = {
        tk: {mk: BarData(tk, mk, px, px, px, px)
             for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        for tk, m in prices.items()
    }
    bars = {tk: m for tk, m in bars.items() if m}

    # Run all variants
    print("\n④ 回测三个组合")
    results = []
    results.append(run_variant(
        "A: C-Score + BM (纯一致预期)", w_c, bars, bench, NAV_C_FILE))
    results.append(run_variant(
        "B: F×C 混合 (F×BM × 预期乘数)", w_fc, bars, bench, NAV_FC_FILE))
    results.append(run_variant(
        "C: F-Score + BM (基线, 实际财报)", w_f, bars, bench,
        "_bt_fscore_nav.json"))

    # Summary
    print("\n" + "=" * 78)
    print("  对比总结")
    print("=" * 78)
    print(f"  {'组合':<28s} {'总收益':>8s} {'年化':>8s} {'回撤':>8s} {'超额':>8s}")
    for r in results:
        ex = f"{r['excess']:+.1%}" if r["excess"] is not None else "—"
        print(f"  {r['name']:<30s} {r['total']:+8.1%} {r['ann']:+8.1%} "
              f"{r['mdd']:8.1%} {ex:>8s}")
    print()

    # Save diagnostics
    json.dump(diag, open("_bt_cscore_diag.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(results, open("_bt_cscore_results.json", "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  诊断 → _bt_cscore_diag.json | 结果 → _bt_cscore_results.json")


if __name__ == "__main__":
    main()
