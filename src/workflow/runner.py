"""Workflow runner — the entry point for running a fund cycle.

Handles:
  - Loading a fund mandate from YAML
  - Instantiating data client, broker, and models
  - Running the LangGraph workflow
  - Returning the complete CycleRecord

Usage:
    from src.workflow.runner import run_fund_cycle

    record = run_fund_cycle(
        mandate_path="config/funds/my_fund.yaml",
        tickers=["AAPL", "MSFT", "NVDA"],
        as_of="2024-01-15",
        capital=100_000,
    )
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env at module import time so that API keys
# are available before any client is instantiated.
load_dotenv()

from src.core.fund_spec import load_fund, FundSpec
from src.core.models import CycleRecord
from src.data.fin_datasets_client import FinancialDatasetsClient
from src.execution.broker import SimBroker
from src.utils.llm_client import get_default_llm_client
from src.workflow.graph import build_fund_graph

# Import signals to populate the alpha model registry
import src.signals  # noqa: F401 — side effect: registers all built-in models


def run_fund_cycle(
    mandate_path: str,
    tickers: list[str],
    as_of: str | None = None,
    capital: float | None = None,
    data_client: Any = None,
    broker: Any = None,
    human_approval: bool = False,
) -> CycleRecord:
    """Run one complete fund cycle.

    Args:
        mandate_path: Path to the fund mandate YAML file.
        tickers: Tickers to run the fund on (the mandate is ticker-free).
        as_of: Date to run as (YYYY-MM-DD). Defaults to today.
        capital: Starting capital. Defaults to the mandate's capital.
        data_client: Custom data client. Defaults to FinancialDatasetsClient.
        broker: Custom broker. Defaults to SimBroker.
        human_approval: If True, pause before execution for review.

    Returns:
        CycleRecord with the complete cycle audit trail.
    """
    # Load fund mandate
    spec = load_fund(mandate_path)

    # Set defaults
    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m-%d")
    if capital is None:
        capital = spec.capital
    if data_client is None:
        data_client = FinancialDatasetsClient()
    if broker is None:
        broker = SimBroker(capital=capital)

    # Default LLM client (Zhipu AI) used by LLMAgent subclasses.
    # Set to None if ZHIPU_API_KEY is not configured; LLM agents will abstain.
    llm_client = get_default_llm_client()

    # Build initial state
    initial_state = {
        "fund_name": spec.name,
        "as_of": as_of,
        "universe": [t.upper().strip() for t in tickers],
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

    # Build and run the graph
    if human_approval:
        from src.workflow.graph import build_fund_graph_with_approval
        graph = build_fund_graph_with_approval()
    else:
        graph = build_fund_graph()

    result = graph.invoke(initial_state)

    # Build the cycle record
    return CycleRecord(
        fund_name=result.get("fund_name", spec.name),
        as_of=result.get("as_of", as_of),
        universe=result.get("universe", tickers),
        marks=result.get("marks", {}),
        signals=result.get("signals", []),
        target_weights=result.get("target_weights", {}),
        final_weights=result.get("final_weights", {}),
        clamps=result.get("clamps", []),
        orders=result.get("orders", []),
        fills=result.get("fills", []),
        positions=result.get("positions", {}),
        cash=result.get("cash", capital),
        nav=result.get("nav", capital),
        equity_before=result.get("equity_before", capital),
        metadata={
            "skipped": result.get("skipped", []),
            "errors": result.get("errors", []),
        },
    )


def run_fund_backtest(
    mandate_path: str,
    tickers: list[str],
    start_date: str,
    end_date: str,
    capital: float | None = None,
    data_client: Any = None,
) -> list[CycleRecord]:
    """Run the fund over a historical period.

    Loops run_fund_cycle over each rebalance date in the period.
    The rebalance cadence comes from the mandate (daily/weekly/monthly).

    Returns a list of CycleRecords — one per rebalance date.
    """
    spec = load_fund(mandate_path)
    if capital is None:
        capital = spec.capital
    if data_client is None:
        data_client = FinancialDatasetsClient()

    # Generate rebalance dates based on cadence
    dates = _generate_rebalance_dates(
        start_date, end_date, spec.rebalance, spec.benchmark, data_client
    )

    records: list[CycleRecord] = []
    broker = SimBroker(capital=capital)

    for i, as_of in enumerate(dates):
        # Carry the book forward (broker maintains state between cycles)
        record = run_fund_cycle(
            mandate_path=mandate_path,
            tickers=tickers,
            as_of=as_of,
            capital=capital,
            data_client=data_client,
            broker=broker,  # reuse broker to carry positions
        )
        records.append(record)

        # Update capital for next cycle to current NAV
        capital = record.nav
        broker._cash = capital  # in a real system, the broker tracks this

    return records


def _generate_rebalance_dates(
    start_date: str,
    end_date: str,
    cadence: str,
    benchmark: str,
    data_client: Any,
) -> list[str]:
    """Generate rebalance dates based on cadence.

    For a real backtest, you'd use the benchmark's trading calendar to
    skip holidays and weekends. For simplicity, this generates calendar dates.
    """
    from datetime import date, timedelta

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if cadence == "daily":
        delta = timedelta(days=1)
    elif cadence == "weekly":
        delta = timedelta(days=7)
    elif cadence == "monthly":
        delta = timedelta(days=30)
    else:
        delta = timedelta(days=7)

    dates: list[str] = []
    current = start
    while current <= end:
        # Skip weekends
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += delta

    return dates
