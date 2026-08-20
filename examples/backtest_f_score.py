"""Piotroski F-Score + BM expectation gap strategy -- point-in-time backtest.

Based on:
  - Piotroski & So (2012): F-Score x BM expectation matrix
  - Liu Xu (Dacheng Fund): PE<=20, PB<=2, ROA focus, low turnover

Strategy:
  1. Universe: A-shares with PB < 2, PE < 20, market cap > 5B (value stocks)
  2. F-Score: 9 binary indicators (profitability / leverage / efficiency)
  3. BM = 1/PB, classified into terciles
  4. Select "incongruent value" stocks: high F-score (>=7) + high BM
  5. Equal-weight or conviction-weighted portfolio
  6. Semi-annual rebalancing (April + August, aligned with reporting)

Point-in-time semantics:
  - Financial data filtered to only available reporting periods
  - No look-ahead bias: signals at month N, execution at month N+1

Run:
    python examples/backtest_f_score.py --select    # fetch data (cached)
    python examples/backtest_f_score.py             # backtest only
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

from src.backtest.engine import BacktestingEngine, BarData, _month_span
from src.backtest.strategy import StrategyTemplate, avail_financials
from src.core.models import Signal
from src.signals.f_score import (
    calculate_f_score,
    classify_expectation,
    _safe,
)
from src.data.mx_data_client import (
    MXDataClient, parse_cn_number, sheet_to_indexed,
)
from src.data.mx_mcp_client import MXMCPClient, TOOL_SCREENER, TOOL_ASHARE

CAPITAL = 1_000_000
PER_NAME_CAP = 0.06          # 6% per position (Liu Xu: concentrated)
GROSS_TARGET = 1.0
MIN_HOLDINGS = 15            # target portfolio size
F_SCORE_THRESHOLD = 7       # minimum F-score to buy
PE_MAX = 20.0               # Liu Xu: PE <= 20
PB_MAX = 2.0                # Liu Xu: PB <= 2

# Cache files
SEL_FILE = "_bt_fscore_selection.json"
FIN_FILE = "_bt_fscore_financials.json"
PRICES_FILE = "_bt_fscore_prices.json"
BENCH_FILE = "_bt_benchmark.json"       # reused from pit backtest
NAV_FILE = "_bt_fscore_nav.json"

# (rebalance month, as_of, cn_period, cn_prev_period)
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

REBALANCES = [d[0] for d in PIT_DATES]


# ===========================================================================
# Utilities
# ===========================================================================

def norm_ticker(code: str) -> str | None:
    c = str(code).strip().split(".")[0]
    if not re.fullmatch(r"\d{6}", c):
        return None
    if c[0] == "6":
        return f"{c}.SH"
    if c[0] in ("0", "3"):
        return f"{c}.SZ"
    return None


def _field(row: dict, *needles, exclude=()) -> str | None:
    for k, v in row.items():
        ks = str(k)
        if all(n in ks for n in needles) and not any(e in ks for e in exclude):
            return str(v)
    return None


def _scr_val(row: dict, *needles, exclude=()) -> float | None:
    """Extract a numeric value from a screener row.

    Handles MX screener conventions:
    - Column names have date suffixes: '总资产报酬率ROA(TTM)(%)-截至2026.08.19最新'
    - Values have pipe-delimited period: '-24.86|2026半年报'
    """
    for k, v in row.items():
        ks = str(k)
        if all(n in ks for n in needles) and not any(e in ks for e in exclude):
            return parse_cn_number(str(v).split("|")[0].strip())
    return None


def _scr_val_ne(row: dict, *needles, exclude=()) -> float | None:
    """Like _scr_val but skips empty values, trying the next matching column.

    Needed for change-log style metrics (e.g. 总股本) where the exact
    period-end date may be empty but nearby dates have data.
    """
    for k, v in row.items():
        ks = str(k)
        if all(n in ks for n in needles) and not any(e in ks for e in exclude):
            parsed = parse_cn_number(str(v).split("|")[0].strip())
            if parsed is not None:
                return parsed
    return None


# ===========================================================================
# Phase 1: Selection -- ONE combined PIT screener query per period
# ===========================================================================

def _period_date_suffix(cn_period: str) -> str:
    """'2021年年报' -> '2021.12.31'; '2021年中报' -> '2021.06.30'."""
    import re as _re
    m = _re.match(r"(\d{4})年(年报|中报|一季报|三季报)", cn_period)
    if not m:
        return ""
    year, ptype = m.group(1), m.group(2)
    return {
        "年报": f"{year}.12.31",
        "中报": f"{year}.06.30",
        "一季报": f"{year}.03.31",
        "三季报": f"{year}.09.30",
    }[ptype]


def _to_cn_date(date_str: str) -> str:
    """'2022-04-30' -> '2022年4月30日'."""
    y, m, d = date_str.split("-")
    return f"{y}年{int(m)}月{int(d)}日"


def run_selection() -> dict:
    """One combined point-in-time screener query per rebalance period.

    - Valuation (PB/PE/mcap) filters applied as of the rebalance date
      ('截至{date}') — NOT today's values (avoids look-ahead bias).
    - Fundamentals from the current reporting period AND the previous
      year's same period (for YoY F-score deltas) — both in ONE query.
    - Rate-limit aware: delay between queries + retry empty results.
    """
    import time as _time

    cli = MXMCPClient()
    if os.path.exists(SEL_FILE):
        sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
        # Validate: all periods present AND non-empty (else re-fetch missing)
        empty = [m for m, d in sel.items() if not d.get("candidates")]
        if sel and not empty and len(sel) == len(PIT_DATES):
            print(f"  选择结果已缓存: {len(sel)} 期")
            return sel
        if empty:
            print(f"  缓存存在但 {len(empty)} 期为空，补拉: {empty}")
            sel = {m: d for m, d in sel.items() if d.get("candidates")}
        else:
            print(f"  缓存不完整 ({len(sel)}/{len(PIT_DATES)} 期)，补拉缺失")
    else:
        sel: dict[str, dict] = {}

    for month, as_of, cn_period, cn_prev in PIT_DATES:
        if month in sel and sel[month].get("candidates"):
            continue  # already have this period

        curr_date = _period_date_suffix(cn_period)
        prev_date = _period_date_suffix(cn_prev)
        curr_year = cn_period[:4]   # "2021"
        prev_year = cn_prev[:4]     # "2020"
        as_of_cn = _to_cn_date(as_of)
        as_of_ym = as_of[:7].replace("-", ".")   # "2022.04"

        print(f"\n  [{month}] PIT查询: 估值@{as_of} | 基本面 {cn_period}+{cn_prev}")
        q = (
            f"截至{as_of_cn}，市净率PB大于0且小于2，"
            f"市盈率PE(TTM)大于0且小于20，"
            f"总市值大于50亿元的A股，按市净率PB从低到高排名前100只，"
            f"显示股票代码、股票简称、申万行业分类、"
            f"市净率PB、市盈率PE(TTM)、"
            f"{cn_period}的总资产报酬率、{cn_prev}的总资产报酬率、"
            f"{cn_period}的经营活动产生的现金流量净额、"
            f"{cn_period}的净利润、"
            f"{cn_period}的资产负债率、{cn_prev}的资产负债率、"
            f"{cn_period}的流动比率、{cn_prev}的流动比率、"
            f"{cn_period}的总资产周转率、{cn_prev}的总资产周转率、"
            f"{cn_period}的总股本、{cn_prev}的总股本、"
            f"{cn_period}的销售毛利率、{cn_prev}的销售毛利率、"
            f"{cn_period}的总资产"
        )

        # Retry loop: MX API rate-limits bursts of complex queries
        candidates: list[dict] = []
        for attempt in range(4):
            try:
                sheets = cli.query(TOOL_SCREENER, q, use_cache=False)
            except Exception as e:
                print(f"    尝试 {attempt + 1} 失败: {e}")
                _time.sleep(8)
                continue

            for sh in sheets:
                for rank, row in sheet_to_indexed(sh).items():
                    code = _field(row, "代码")
                    tk = norm_ticker(code or "")
                    if not tk:
                        continue
                    name = (_field(row, "简称") or
                            _field(row, "名称") or "").strip()
                    if "ST" in name or "退" in name:
                        continue
                    sw = _field(row, "申万行业") or ""
                    sw1 = sw.split("-")[0] if sw else "未知"

                    pb = _scr_val(row, "市净率", as_of_ym,
                                  exclude=("扣除", "商誉"))
                    pe = _scr_val(row, "市盈率", as_of_ym,
                                  exclude=("动", "扣除", "商誉"))

                    curr = {
                        "roa": _scr_val(row, "总资产", "报酬", curr_date),
                        "cfo": _scr_val(row, "经营活动", "现金流量净额",
                                        curr_date),
                        "net_income": _scr_val(row, "净利润", curr_date),
                        "debt_ratio": _scr_val(row, "资产负债率", curr_date),
                        "current_ratio": _scr_val(row, "流动比率", curr_date),
                        "asset_turnover": _scr_val(row, "总资产", "周转",
                                                   curr_date),
                        "shares": _scr_val_ne(row, "总股本", curr_year),
                        "gross_margin": _scr_val(row, "毛利率", curr_date),
                        "total_assets": (
                            _scr_val(row, "资产总计", curr_date)
                            or _scr_val(row, "总资产", curr_date,
                                        exclude=("报酬", "周转", "收益", "ROA"))),
                    }

                    prev = {
                        "roa": _scr_val(row, "总资产", "报酬", prev_date),
                        "debt_ratio": _scr_val(row, "资产负债率", prev_date),
                        "current_ratio": _scr_val(row, "流动比率", prev_date),
                        "asset_turnover": _scr_val(row, "总资产", "周转",
                                                   prev_date),
                        "shares": _scr_val_ne(row, "总股本", prev_year),
                        "gross_margin": _scr_val(row, "毛利率", prev_date),
                    }

                    cfo = curr.get("cfo")
                    ta = curr.get("total_assets")
                    if cfo is not None and ta is not None and ta > 0:
                        curr["cfo_ta"] = (cfo / ta) * 100.0

                    candidates.append({
                        "tk": tk, "name": name, "sw1": sw1,
                        "pb": pb, "pe": pe,
                        "curr": curr,
                        "prev": prev,
                    })

            if candidates:
                break  # success
            # Empty result — likely rate-limited; wait longer and retry
            print(f"    尝试 {attempt + 1}: 0 条结果，等待重试...")
            _time.sleep(10)

        sel[month] = {
            "as_of": as_of,
            "cn_period": cn_period,
            "candidates": candidates,
        }
        n_prev = sum(1 for c in candidates
                     if c["prev"].get("roa") is not None)
        print(f"    → {len(candidates)} 只候选 | {n_prev} 只有上年ROA")

        # Persist incrementally so progress isn't lost on failure
        json.dump(sel, open(SEL_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

        # Be gentle with the API between periods
        if month != PIT_DATES[-1][0]:
            _time.sleep(6)

    json.dump(sel, open(SEL_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n  选择结果 → {SEL_FILE}")
    return sel


# ===========================================================================
# Phase 2: F-Score calculation + portfolio construction
# ===========================================================================

def build_signals(
    candidates: list[dict],
    as_of: str,
    month: str,
) -> tuple[list[Signal], dict]:
    """Calculate F-score for each candidate, classify expectation,
    return signals for "incongruent value" stocks.
    """
    signals: list[Signal] = []
    detail: dict[str, dict] = {}

    # Compute PB tercile thresholds from candidates
    pbs = [c["pb"] for c in candidates if c["pb"] and c["pb"] > 0]
    if len(pbs) < 5:
        return signals, detail
    pb_p33 = sorted(pbs)[len(pbs) // 3]
    pb_p67 = sorted(pbs)[len(pbs) * 2 // 3]

    for c in candidates:
        tk = c["tk"]
        curr = c["curr"]
        prev = c.get("prev", {})

        # Skip if no current data
        if not curr or not curr.get("roa"):
            continue

        # Liu Xu's valuation filters
        pe = _safe(c.get("pe"))
        pb = _safe(c.get("pb"))
        if pb is None or pb <= 0:
            continue
        if pe is not None and pe > PE_MAX:
            continue
        if pb > PB_MAX:
            continue

        # Calculate F-score
        f_score, f_detail = calculate_f_score(curr, prev)

        # BM tercile
        bm = 1.0 / pb
        if pb <= pb_p33:
            bm_tercile = "high"
        elif pb >= pb_p67:
            bm_tercile = "low"
        else:
            bm_tercile = "mid"

        expectation = classify_expectation(f_score, bm_tercile)

        # Signal value
        if expectation == "undervalued":
            # High F-score + high BM: strong buy
            value = min(1.0, 0.5 + 0.1 * (f_score - 7))
        elif f_score >= F_SCORE_THRESHOLD and bm_tercile in ("high", "mid"):
            value = 0.3 + 0.05 * (f_score - F_SCORE_THRESHOLD)
            value = min(0.5, value)
        elif f_score >= 5 and bm_tercile == "high":
            value = 0.15
        else:
            value = 0.0

        if value > 0:
            signals.append(Signal(
                model_name="f_score",
                ticker=tk,
                date=as_of,
                value=round(value, 4),
                reasoning=(
                    f"F={f_score}/9 BM_tercile={bm_tercile} "
                    f"PE={pe} PB={pb:.2f} exp={expectation}"
                ),
                components={
                    "f_score": float(f_score),
                    "bm": round(bm, 4),
                    "pe": pe or 0.0,
                    "pb": pb or 0.0,
                },
                metadata={
                    "f_detail": f_detail,
                    "expectation": expectation,
                    "name": c["name"],
                    "sw1": c["sw1"],
                },
            ))
            detail[tk] = {
                "name": c["name"], "sw1": c["sw1"],
                "f_score": f_score, "f_detail": f_detail,
                "pe": pe, "pb": pb, "bm": round(bm, 4),
                "bm_tercile": bm_tercile,
                "expectation": expectation,
                "conviction": value,
            }

    signals.sort(key=lambda s: -s.value)
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

    # Scale up if under-invested and we have room
    invested = sum(weights.values())
    if invested < GROSS_TARGET * 0.9 and len(weights) < MIN_HOLDINGS:
        # Can't add more signals; just scale existing
        if invested > 0:
            scale = GROSS_TARGET / invested
            for tk in weights:
                weights[tk] = min(weights[tk] * scale, PER_NAME_CAP)
    return weights


# ===========================================================================
# Phase 3: vnpy-style backtest engine execution
# ===========================================================================

class FScoreStrategy(StrategyTemplate):
    """Pre-computed weights strategy for F-score backtest."""

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
                 detail[t]["f_score"], w, detail[t].get("expectation", ""))
                for t, w in sorted(weights.items(), key=lambda x: -x[1])
                if t in detail
            ],
        })


# ===========================================================================
# Phase 4: Price data fetching
# ===========================================================================

def fetch_prices(tickers: list[str], start: str = "2019-01-01",
                end: str = "2026-08-31") -> dict:
    """Fetch monthly close prices for all tickers."""
    if os.path.exists(PRICES_FILE):
        prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
        print(f"  价格数据已缓存: {len(prices)} 只")
        # Check if any tickers are missing
        missing = [t for t in tickers if t not in prices]
        if not missing:
            return prices
        tickers = missing
        print(f"  补拉 {len(tickers)} 只缺失标的...")
    else:
        prices = {}

    client = MXDataClient()
    for i, tk in enumerate(tickers):
        if tk in prices:
            continue
        try:
            bars = client.get_prices(tk, start, end)
            monthly: dict[str, float] = {}
            for bar in bars:
                d = bar["time"][:7]  # YYYY-MM
                monthly[d] = bar["close"]
            if monthly:
                prices[tk] = monthly
        except Exception as e:
            pass
        if (i + 1) % 20 == 0:
            print(f"    价格进度 {i+1}/{len(tickers)}")

    json.dump(prices, open(PRICES_FILE, "w", encoding="utf-8"))
    print(f"  价格数据 → {PRICES_FILE} ({len(prices)} 只)")
    return prices


def fetch_benchmark() -> dict:
    """Fetch benchmark (沪深300 or 中证全指) monthly closes."""
    if os.path.exists(BENCH_FILE):
        bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
        if bench:
            return bench

    client = MXDataClient()
    try:
        bars = client.get_prices("000300.SH", "2019-01-01", "2026-08-31")
        bench = {bar["time"][:7]: bar["close"] for bar in bars}
    except Exception:
        bench = {}
    json.dump(bench, open(BENCH_FILE, "w", encoding="utf-8"))
    return bench


# ===========================================================================
# Main
# ===========================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="F-Score backtest")
    parser.add_argument("--select", action="store_true",
                        help="Run data selection (fetch from MX)")
    args = parser.parse_args()

    print("=" * 78)
    print("  Piotroski F-Score + BM 预期差 · 点时全市场 5 年回测")
    print("  F-Score (9 因子) × BM (1/PB) | 刘旭: PE<=20, PB<=2")
    print("  半年度调仓 | conviction_weighted + 单票 6% | 成本 5bp+10bp")
    print("=" * 78)

    # Phase 1: Selection
    if args.select:
        print("\n① 数据选择（MX 选股器）")
        sel = run_selection()
    else:
        if not os.path.exists(SEL_FILE):
            print(f"\n  缓存 {SEL_FILE} 不存在，请先运行 --select")
            return
        sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
        print(f"\n① 加载选择缓存: {len(sel)} 期")

    # Phase 2: F-Score signals + portfolio construction
    print("\n② F-Score 计算 + 预期差分类")
    weights_by_dt, detail_by_dt = {}, {}
    for month, as_of, cn_period, cn_prev in PIT_DATES:
        if month not in sel:
            continue
        candidates = sel[month]["candidates"]
        signals, detail = build_signals(candidates, as_of, month)
        weights = blend_weights(signals)
        weights_by_dt[month] = weights
        detail_by_dt[month] = detail

        # Diagnostics
        exp_counts: dict[str, int] = {}
        f_scores: list[int] = []
        for d in detail.values():
            exp_counts[d["expectation"]] = (
                exp_counts.get(d["expectation"], 0) + 1)
            f_scores.append(d["f_score"])
        avg_f = (sum(f_scores) / len(f_scores) if f_scores else 0)
        print(
            f"  [{month}] 候选 {len(candidates)} → "
            f"信号 {len(signals)} → 持仓 {len(weights)} 只 | "
            f"avg F={avg_f:.1f} | gross {sum(weights.values()):.0%} | "
            f"exp: {exp_counts}"
        )

    # Phase 3: Price data
    print("\n③ 加载价格数据")
    all_tickers = set()
    for w in weights_by_dt.values():
        all_tickers.update(w.keys())
    prices = fetch_prices(list(all_tickers))
    bench = fetch_benchmark()

    # Phase 4: vnpy engine execution
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
        rate=0.0005,       # 5bp commission
        slippage=0.001,   # 10bp slippage
    )
    engine.add_data(bars)
    strategy = FScoreStrategy(engine, {
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

    # Phase 6: Diagnostics
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
        for name, sw1, fs, w, exp in h["names"][:8]:
            print(f"     {name:8s} {sw1:6s} F={fs} {exp:14s} {w:.1%}")

    # Structure diagnostics
    print("\n⑦ 结构诊断")
    all_f: dict[int, int] = {}
    all_exp: dict[str, int] = {}
    for month, detail in detail_by_dt.items():
        for d in detail.values():
            all_f[d["f_score"]] = all_f.get(d["f_score"], 0) + 1
            all_exp[d["expectation"]] = all_exp.get(d["expectation"], 0) + 1
    print(f"  F-score 分布: {dict(sorted(all_f.items()))}")
    print(f"  预期分类: {all_exp}")

    nav = [{"month": r["dt"], "nav": r["balance"]}
           for r in daily if r["dt"] in bench]
    json.dump(nav, open(NAV_FILE, "w", encoding="utf-8"))
    print(f"\n  NAV -> {NAV_FILE}")


if __name__ == "__main__":
    main()
