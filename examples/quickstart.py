"""Quick start example — run the example fund on a few tickers.

This is the simplest way to see the framework in action.

Prerequisites:
  1. pip install -e .
  2. Set FINANCIAL_DATASETS_API_KEY in .env (or use a custom data client)

Run:
  python examples/quickstart.py
"""

from __future__ import annotations

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow.runner import run_fund_cycle
from src.core.models import CycleRecord


def print_cycle(record: CycleRecord):
    """Pretty-print a cycle record."""
    print("=" * 70)
    print(f"  Fund: {record.fund_name}")
    print(f"  Date: {record.as_of}")
    print(f"  NAV:  ${record.nav:,.2f}")
    print("=" * 70)

    # Signals
    print("\n  ANALYST SIGNALS:")
    print("-" * 70)
    for signal in record.signals:
        if signal.value == 0 and signal.metadata.get("abstained"):
            continue
        bar_len = int(abs(signal.value) * 20)
        bar = ("█" * bar_len).ljust(20)
        direction = "+" if signal.value >= 0 else "-"
        print(f"  {signal.model_name:15s} {signal.ticker:6s} [{direction}{bar}] {signal.value:+.2f}")
        if signal.reasoning:
            print(f"  {'':15s}  └─ {signal.reasoning[:80]}")

    # Target vs Final weights
    print("\n  PORTFOLIO WEIGHTS:")
    print("-" * 70)
    all_tickers = sorted(set(list(record.target_weights.keys()) + list(record.final_weights.keys())))
    for ticker in all_tickers:
        target = record.target_weights.get(ticker, 0)
        final = record.final_weights.get(ticker, 0)
        clamped = " (clamped)" if target != final else ""
        print(f"  {ticker:6s}  target: {target:+.2%}  final: {final:+.2%}{clamped}")

    # Risk clamps
    if record.clamps:
        print("\n  RISK CLAMPS:")
        print("-" * 70)
        for clamp in record.clamps:
            ticker_str = f" [{clamp.ticker}]" if clamp.ticker else ""
            print(f"  {clamp.limit}{ticker_str}: {clamp.before:+.2%} → {clamp.after:+.2%}")

    # Orders
    if record.orders:
        print("\n  ORDERS:")
        print("-" * 70)
        for order in record.orders:
            print(f"  {order.side.value.upper():4s} {order.shares:>8.1f} {order.ticker:6s} @ ${order.limit_price:.2f}")

    # Positions
    print("\n  FINAL POSITIONS:")
    print("-" * 70)
    for ticker, shares in record.positions.items():
        price = record.marks.get(ticker, 0)
        value = shares * price
        print(f"  {ticker:6s}  {shares:>10.2f} shares  @ ${price:.2f}  = ${value:,.2f}")
    print(f"  {'CASH':6s}  {'':>10s}           {'':16s}  = ${record.cash:,.2f}")
    print(f"  {'NAV':6s}  {'':>10s}           {'':16s}  = ${record.nav:,.2f}")
    print()


def main():
    """Run the example fund."""

    # ── Option A: Use Financial Datasets API (needs API key) ──
    # record = run_fund_cycle(
    #     mandate_path="config/funds/example_fund.yaml",
    #     tickers=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
    #     as_of="2024-06-01",
    # )

    # ── Option B: Use a mock data client (no API key needed) ──
    from examples.mock_data import MockDataClient
    from src.execution.broker import SimBroker

    record = run_fund_cycle(
        mandate_path="config/funds/example_fund.yaml",
        tickers=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        as_of="2024-06-01",
        data_client=MockDataClient(),
        broker=SimBroker(capital=100_000),
    )

    print_cycle(record)


if __name__ == "__main__":
    main()
