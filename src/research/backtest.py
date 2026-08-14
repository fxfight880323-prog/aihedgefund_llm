"""Backtesting engine — run the fund over history and evaluate.

The backtest is the same run_cycle loop over historical dates with a
SimBroker. What you backtest is what would trade — same code path.
"""

from __future__ import annotations

from typing import Any

from src.core.models import CycleRecord
from src.workflow.runner import run_fund_backtest


def backtest_fund(
    mandate_path: str,
    tickers: list[str],
    start_date: str,
    end_date: str,
    capital: float = 100_000.0,
    data_client: Any = None,
) -> dict:
    """Backtest a fund over a historical period.

    Returns a dict with:
      - records: list of CycleRecord (one per rebalance)
      - equity_curve: list of (date, nav) tuples
      - stats: performance statistics
      - benchmark_curve: benchmark equity curve for comparison
    """
    records = run_fund_backtest(
        mandate_path=mandate_path,
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        capital=capital,
        data_client=data_client,
    )

    # Build equity curve
    equity_curve = [(r.as_of, r.nav) for r in records]

    # Compute stats
    stats = compute_stats(equity_curve)

    return {
        "records": records,
        "equity_curve": equity_curve,
        "stats": stats,
    }


def compute_stats(equity_curve: list[tuple[str, float]]) -> dict:
    """Compute performance statistics from an equity curve."""
    if len(equity_curve) < 2:
        return {}

    navs = [nav for _, nav in equity_curve]
    returns = [
        (navs[i] / navs[i - 1] - 1) if navs[i - 1] != 0 else 0
        for i in range(1, len(navs))
    ]

    total_return = (navs[-1] / navs[0] - 1) if navs[0] != 0 else 0

    # Annualized return (approximate)
    n_periods = len(returns)
    if n_periods > 0:
        annualized = (1 + total_return) ** (252 / max(n_periods, 1)) - 1
    else:
        annualized = 0

    # Sharpe ratio (assume risk-free = 0, weekly rebalance)
    if returns:
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = var_r ** 0.5
        sharpe = (mean_r / std_r * (52 ** 0.5)) if std_r > 0 else 0
    else:
        sharpe = 0

    # Max drawdown
    peak = navs[0]
    max_dd = 0
    for nav in navs:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Win rate
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / len(returns) if returns else 0

    return {
        "total_return": total_return,
        "annualized_return": annualized,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "n_periods": n_periods,
        "final_nav": navs[-1] if navs else capital,
    }
