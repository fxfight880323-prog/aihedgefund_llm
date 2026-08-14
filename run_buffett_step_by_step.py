"""Buffett agent graph walkthrough — execute each node step by step.

This script demonstrates the LangGraph fund cycle node by node,
using only the Buffett LLM agent.  Because no real LLM API key is
required for a dry-run demonstration, we inject a mock LLM client that
returns a controlled signal, and we use MockDataClient for market data.

To run with a real LLM, set ZHIPU_API_KEY (or another provider) and
remove the mock_llm_client injection.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.workflow.graph import build_fund_graph
from src.workflow.state import FundState
from src.workflow.nodes import (
    fetch_data,
    run_analysts,
    blend_signals,
    apply_risk,
    build_orders,
    execute_orders,
    record_cycle,
)
from src.core.fund_spec import load_fund
from src.execution.broker import SimBroker
from examples.mock_data import MockDataClient


class MockLLMClient:
    """A tiny deterministic LLM that returns a Buffett-style JSON signal."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Parse the ticker out of the user prompt (first line is "Company: X")
        ticker = "UNKNOWN"
        for line in user_prompt.splitlines():
            if line.startswith("Company:"):
                ticker = line.split(":", 1)[1].strip()
                break

        # Give AAPL a bullish Buffett signal, MSFT neutral-bullish, others neutral.
        if ticker == "AAPL":
            return (
                '{"signal": "bullish", "confidence": 85, '
                '"reasoning": "Wide moat, consistent ROE, and reasonable valuation."}'
            )
        if ticker == "MSFT":
            return (
                '{"signal": "bullish", "confidence": 70, '
                '"reasoning": "Strong cloud franchise with durable recurring revenue."}'
            )
        return (
            '{"signal": "neutral", "confidence": 50, '
            '"reasoning": "Mixed evidence; not clearly attractive or unattractive."}'
        )


def merge_updates(state: FundState, updates: dict) -> FundState:
    """LangGraph merges node outputs into the shared state."""
    state = dict(state)
    for key, value in updates.items():
        state[key] = value
    return state


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main():
    mandate_path = "config/funds/buffett_test.yaml"
    tickers = ["AAPL", "MSFT"]
    as_of = "2024-06-01"
    capital = 100_000

    spec = load_fund(mandate_path)
    data_client = MockDataClient()
    broker = SimBroker(capital=capital)
    llm_client = MockLLMClient()

    # Display the graph structure defined in src/workflow/graph.py
    print_section("GRAPH STRUCTURE")
    print("  Nodes:")
    for node in [
        "fetch_data",
        "run_analysts",
        "blend_signals",
        "apply_risk",
        "build_orders",
        "execute_orders",
        "record_cycle",
    ]:
        print(f"    - {node}")
    print("  Edges:")
    print("    fetch_data -> run_analysts")
    print("    run_analysts -> blend_signals")
    print("    blend_signals -> apply_risk")
    print("    apply_risk -> build_orders")
    print("    build_orders -> execute_orders")
    print("    execute_orders -> record_cycle")
    print("    record_cycle -> END")

    # Initial state
    state: FundState = {
        "fund_name": spec.name,
        "as_of": as_of,
        "universe": [t.upper() for t in tickers],
        "capital": capital,
        "marks": {},
        "skipped": [],
        "signals": [],
        "convictions": {},
        "target_weights": {},
        "final_weights": {},
        "clamps": [],
        "orders": [],
        "fills": [],
        "positions": {},
        "cash": capital,
        "nav": capital,
        "equity_before": capital,
        "errors": [],
        "metadata": {
            "fund_spec": spec,
            "data_client": data_client,
            "broker": broker,
            "capital": capital,
            "llm_client": llm_client,
        },
    }

    print_section("INITIAL STATE")
    print(f"  Fund: {state['fund_name']}")
    print(f"  As of: {state['as_of']}")
    print(f"  Universe: {state['universe']}")
    print(f"  Capital: ${state['capital']:,.0f}")

    # ------------------------------------------------------------------
    # NODE 1: fetch_data
    # ------------------------------------------------------------------
    print_section("NODE 1: fetch_data")
    updates = fetch_data(state)
    state = merge_updates(state, updates)
    print(f"  Marks fetched: {state['marks']}")
    print(f"  Skipped: {state['skipped']}")

    # ------------------------------------------------------------------
    # NODE 2: run_analysts
    # ------------------------------------------------------------------
    print_section("NODE 2: run_analysts (Buffett only)")
    updates = run_analysts(state)
    state = merge_updates(state, updates)
    for signal in state["signals"]:
        print(
            f"  {signal.model_name:10s} {signal.ticker:6s} "
            f"value={signal.value:+.2f}  reasoning={signal.reasoning}"
        )

    # ------------------------------------------------------------------
    # NODE 3: blend_signals
    # ------------------------------------------------------------------
    print_section("NODE 3: blend_signals")
    updates = blend_signals(state)
    state = merge_updates(state, updates)
    print("  Convictions:")
    for ticker, conv in state["convictions"].items():
        print(f"    {ticker}: {conv:+.4f}")
    print("  Target weights:")
    for ticker, w in state["target_weights"].items():
        print(f"    {ticker}: {w:+.2%}")

    # ------------------------------------------------------------------
    # NODE 4: apply_risk
    # ------------------------------------------------------------------
    print_section("NODE 4: apply_risk")
    updates = apply_risk(state)
    state = merge_updates(state, updates)
    print("  Final weights:")
    for ticker, w in state["final_weights"].items():
        print(f"    {ticker}: {w:+.2%}")
    print(f"  Clamps applied: {len(state['clamps'])}")
    for clamp in state["clamps"]:
        print(f"    {clamp.limit}: {clamp.before:+.2%} -> {clamp.after:+.2%}")

    # ------------------------------------------------------------------
    # NODE 5: build_orders
    # ------------------------------------------------------------------
    print_section("NODE 5: build_orders")
    updates = build_orders(state)
    state = merge_updates(state, updates)
    if state["orders"]:
        for order in state["orders"]:
            print(
                f"  {order.side.value.upper():4s} {order.shares:>10.2f} "
                f"{order.ticker:6s} @ ${order.limit_price:.2f}  ({order.reasoning})"
            )
    else:
        print("  No orders generated.")

    # ------------------------------------------------------------------
    # NODE 6: execute_orders
    # ------------------------------------------------------------------
    print_section("NODE 6: execute_orders")
    updates = execute_orders(state)
    state = merge_updates(state, updates)
    if state["fills"]:
        for fill in state["fills"]:
            print(
                f"  FILLED {fill.side.value.upper():4s} {fill.shares:>10.2f} "
                f"{fill.ticker:6s} @ ${fill.price:.2f}"
            )
    else:
        print("  No fills.")

    # ------------------------------------------------------------------
    # NODE 7: record_cycle
    # ------------------------------------------------------------------
    print_section("NODE 7: record_cycle")
    updates = record_cycle(state)
    state = merge_updates(state, updates)
    print("  Final positions:")
    for ticker, shares in state["positions"].items():
        price = state["marks"].get(ticker, 0)
        value = shares * price
        print(f"    {ticker}: {shares:>10.2f} shares @ ${price:.2f} = ${value:,.2f}")
    print(f"  Cash: ${state['cash']:,.2f}")
    print(f"  NAV:  ${state['nav']:,.2f}")

    print_section("CYCLE COMPLETE")
    print(f"  Final state keys: {sorted(state.keys())}")


if __name__ == "__main__":
    main()
