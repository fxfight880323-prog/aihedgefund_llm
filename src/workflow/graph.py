"""LangGraph workflow definition — the fund's pipeline as a graph.

This is the heart of the system. The fund's cycle is a LangGraph StateGraph
that flows through these nodes:

    ┌─────────────┐     ┌──────────────┐     ┌──────────────┐
    │ fetch_data  │────▶│ run_analysts │────▶│ blend_signals│
    └─────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
    ┌─────────────┐     ┌──────────────┐         ▼
    │ record_cycle│◀────│execute_orders│◀───┌────────────┐
    └─────────────┘     └──────────────┘    │apply_risk  │
                        ▲                   └────────────┘
                        │                         │
                  ┌─────────────┐                 ▼
                  │ build_orders│◀────────────────┘
                  └─────────────┘

Each node is a pure function: (FundState) -> dict[updates].
LangGraph handles the state threading, checkpointing, and parallelism.

WHY LANGRAPH (vs. a simple pipeline):
  - Checkpointing: resume a backtest from any point
  - Parallelism: run analysts in parallel across tickers
  - Human-in-the-loop: pause before execution for approval
  - Streaming: stream signal generation and reasoning to a UI
  - Conditional edges: skip execution if all signals are neutral
  - Subgraphs: each strategy can be its own subgraph
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

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


def build_fund_graph() -> Any:
    """Build and compile the fund cycle workflow graph.

    Returns a compiled LangGraph runnable. Call .invoke(state) to run
    one complete cycle.

    Usage:
        graph = build_fund_graph()
        result = graph.invoke({
            "fund_name": "My Fund",
            "as_of": "2024-01-15",
            "universe": ["AAPL", "MSFT", "NVDA"],
            "capital": 100_000,
            "metadata": {
                "fund_spec": spec,
                "data_client": client,
                "broker": broker,
            },
        })
    """
    graph = StateGraph(FundState)

    # ---- Add nodes ----
    graph.add_node("fetch_data", fetch_data)
    graph.add_node("run_analysts", run_analysts)
    graph.add_node("blend_signals", blend_signals)
    graph.add_node("apply_risk", apply_risk)
    graph.add_node("build_orders", build_orders)
    graph.add_node("execute_orders", execute_orders)
    graph.add_node("record_cycle", record_cycle)

    # ---- Add edges (the pipeline flow) ----
    graph.set_entry_point("fetch_data")
    graph.add_edge("fetch_data", "run_analysts")
    graph.add_edge("run_analysts", "blend_signals")
    graph.add_edge("blend_signals", "apply_risk")
    graph.add_edge("apply_risk", "build_orders")
    graph.add_edge("build_orders", "execute_orders")
    graph.add_edge("execute_orders", "record_cycle")
    graph.add_edge("record_cycle", END)

    # ---- Conditional edges (optional, see below) ----
    # You can add conditional logic, e.g. skip execution if all signals neutral:
    #
    # def should_execute(state: FundState) -> str:
    #     final_weights = state.get("final_weights", {})
    #     if all(abs(w) < 0.001 for w in final_weights.values()):
    #         return "skip"
    #     return "execute"
    #
    # graph.add_conditional_edges(
    #     "apply_risk",
    #     should_execute,
    #     {"skip": "record_cycle", "execute": "build_orders"},
    # )

    return graph.compile()


# ===========================================================================
# Optional: Build a graph with human-in-the-loop approval
# ===========================================================================

def build_fund_graph_with_approval() -> Any:
    """Fund graph that pauses before execution for human approval.

    The graph stops at build_orders and waits for a human to approve
    before executing. This is the "paper before live" principle.

    Usage:
        graph = build_fund_graph_with_approval()
        config = {"configurable": {"thread_id": "cycle-2024-01-15"}}
        result = graph.invoke(initial_state, config)
        # Graph pauses at build_orders
        # Review the proposed orders in result["orders"]
        # Resume:
        result = graph.invoke(None, config)  # continues to execute + record
    """
    graph = StateGraph(FundState)

    graph.add_node("fetch_data", fetch_data)
    graph.add_node("run_analysts", run_analysts)
    graph.add_node("blend_signals", blend_signals)
    graph.add_node("apply_risk", apply_risk)
    graph.add_node("build_orders", build_orders)
    graph.add_node("execute_orders", execute_orders)
    graph.add_node("record_cycle", record_cycle)

    graph.set_entry_point("fetch_data")
    graph.add_edge("fetch_data", "run_analysts")
    graph.add_edge("run_analysts", "blend_signals")
    graph.add_edge("blend_signals", "apply_risk")
    graph.add_edge("apply_risk", "build_orders")

    # Pause here for human approval
    # LangGraph will stop and wait for the next invoke() call

    graph.add_edge("build_orders", "execute_orders")
    graph.add_edge("execute_orders", "record_cycle")
    graph.add_edge("record_cycle", END)

    return graph.compile(interrupt_before=["execute_orders"])


# ===========================================================================
# Optional: Build a graph with parallel analysts
# ===========================================================================

def build_fund_graph_parallel() -> Any:
    """Fund graph where each alpha model runs as a parallel subgraph.

    This uses LangGraph's fan-out/fan-in pattern to run all analysts
    simultaneously, which is faster for LLM agents that each make API calls.
    """
    # This is a more advanced pattern — the basic graph works fine for most cases.
    # For parallel execution, you'd use Send() to fan out to per-model nodes,
    # then collect results. See LangGraph docs for the Send API.
    return build_fund_graph()
