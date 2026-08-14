"""LangGraph workflow state — the data that flows through the graph.

This is the shared state object that every node in the graph reads and writes.
It's a TypedDict so LangGraph can track it across nodes.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.core.models import Signal, BlendResult, RiskResult, Order, Fill, ClampEvent


class FundState(TypedDict, total=False):
    """The complete state of one fund cycle.

    This dict is passed through the LangGraph workflow. Each node reads
    some keys and writes others. The final state IS the cycle record.

    Flow:
        universe → fetch_data → run_analysts → blend_signals →
        apply_risk → build_orders → execute → record
    """

    # ---- Input ----
    fund_name: str
    as_of: str
    universe: list[str]
    capital: float

    # ---- Data ----
    marks: dict[str, float]               # ticker -> last close price
    skipped: list[dict[str, Any]]          # tickers with no price data

    # ---- Signals ----
    signals: list[Signal]                  # all analyst signals this cycle

    # ---- Portfolio ----
    convictions: dict[str, float]          # blended view per ticker
    target_weights: dict[str, float]       # pre-risk target weights

    # ---- Risk ----
    final_weights: dict[str, float]        # post-risk weights
    clamps: list[ClampEvent]               # risk limit events

    # ---- Execution ----
    orders: list[Order]
    fills: list[Fill]

    # ---- Result ----
    positions: dict[str, float]
    cash: float
    nav: float
    equity_before: float

    # ---- Metadata ----
    errors: list[str]
    metadata: dict[str, Any]
