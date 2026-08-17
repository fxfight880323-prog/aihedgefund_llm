"""LangGraph workflow nodes — each node is one stage of the fund cycle.

    fetch_data → run_analysts → blend_signals → apply_risk → build_orders → execute → record

Each function takes the FundState, does its job, and returns a dict of
updates to merge into the state. This is the LangGraph convention.
"""

from __future__ import annotations

from datetime import date as _date, timedelta
from typing import Any

from src.core.models import Signal, Order, OrderSide, Fill
from src.core.fund_spec import FundSpec
from src.core.interfaces import LLMAgent
from src.core.registry import (
    ALPHA_MODEL_REGISTRY,
    BLEND_POLICY_REGISTRY,
    get_alpha_model,
)
from src.risk.limits import HardLimits
from src.workflow.state import FundState

# How far back to look for the most recent close
_MARK_LOOKBACK_DAYS = 7


# ===========================================================================
# Node 1: Fetch market data (prices for all tickers in universe)
# ===========================================================================

def fetch_data(state: FundState) -> dict[str, Any]:
    """Fetch last close prices for all tickers in the universe.

    Point-in-time: only returns data on or before the as_of date.
    """
    as_of = state["as_of"]
    universe = state["universe"]
    data_client = state["metadata"]["data_client"]

    start = (_date.fromisoformat(as_of) - timedelta(days=_MARK_LOOKBACK_DAYS)).isoformat()
    marks: dict[str, float] = {}
    skipped: list[dict[str, Any]] = []

    for ticker in universe:
        try:
            prices = data_client.get_prices(ticker, start, as_of)
            bars = [p for p in prices if p.get("time", "")[:10] <= as_of]
            if bars:
                marks[ticker] = max(bars, key=lambda p: p.get("time", ""))["close"]
            else:
                skipped.append({"ticker": ticker, "reason": "no price data"})
        except Exception as e:
            skipped.append({"ticker": ticker, "reason": str(e)})

    return {"marks": marks, "skipped": skipped}


# ===========================================================================
# Node 2: Run all alpha models (analysts) on all tickers
# ===========================================================================

def run_analysts(state: FundState) -> dict[str, Any]:
    """Run every alpha model in every strategy on every tradeable ticker.

    This is where the fund's analysts form their views. Each model produces
    a Signal with conviction in [-1, +1] and a written thesis.
    """
    spec: FundSpec = state["metadata"]["fund_spec"]
    marks = state.get("marks", {})
    data_client = state["metadata"]["data_client"]
    as_of = state["as_of"]

    tradeable = list(marks.keys())
    all_signals: list[Signal] = []

    for strategy in spec.strategies:
        for model_spec in strategy.models:
            # Inject the shared LLM client into LLM agents.
            model_cls = ALPHA_MODEL_REGISTRY[model_spec.name]
            params = dict(model_spec.params)
            if issubclass(model_cls, LLMAgent):
                params.setdefault("llm_client", state["metadata"].get("llm_client"))

            # Instantiate the model
            model = get_alpha_model(model_spec.name, **params)
            for ticker in tradeable:
                try:
                    signal = model.predict(ticker, as_of, data_client)
                    all_signals.append(signal)
                except Exception as e:
                    all_signals.append(Signal(
                        model_name=model_spec.name,
                        ticker=ticker,
                        date=as_of,
                        value=0.0,
                        reasoning=f"Error: {e}",
                        metadata={"abstained": True, "error": str(e)},
                    ))

    return {"signals": all_signals}


# ===========================================================================
# Node 3: Blend signals into target weights (portfolio construction)
# ===========================================================================

def blend_signals(state: FundState) -> dict[str, Any]:
    """Blend all analyst signals into target weights per strategy.

    Each strategy's signals are blended using its blend policy. Then the
    strategy sleeves are netted by their capital slice weights.
    """
    spec: FundSpec = state["metadata"]["fund_spec"]
    signals: list[Signal] = state.get("signals", [])
    tradeable = list(state.get("marks", {}).keys())

    # Group signals by strategy
    # In the current design, all models run on all tickers, so we need to
    # know which strategy each model belongs to. We use the fund spec.
    total_slice = sum(s.weight for s in spec.strategies)
    netted: dict[str, float] = {t: 0.0 for t in tradeable}
    all_convictions: dict[str, float] = {t: 0.0 for t in tradeable}

    for strategy in spec.strategies:
        # Get signals for this strategy's models only
        model_names = {m.name for m in strategy.models}
        strat_signals = [s for s in signals if s.model_name in model_names]

        # Blend — policy comes from the registry (YAML `blend.method`)
        import src.signals  # noqa: F401 — ensure policies are registered
        import src.portfolio  # noqa: F401

        blender = BLEND_POLICY_REGISTRY[strategy.blend.method](
            **strategy.blend.params
        )
        model_weights = strategy.model_weights
        blend = blender.blend(
            strat_signals,
            model_weights,
            gross_target=strategy.blend.gross_target,
            market_neutral=strategy.blend.market_neutral,
        )

        # Net into the fund book by capital slice
        slice_ = strategy.weight / total_slice
        for ticker, weight in blend.weights.items():
            netted[ticker] = netted.get(ticker, 0.0) + slice_ * weight
            all_convictions[ticker] = all_convictions.get(ticker, 0.0) + slice_ * blend.convictions.get(ticker, 0.0)

    return {
        "convictions": all_convictions,
        "target_weights": netted,
    }


# ===========================================================================
# Node 4: Apply risk limits (hard caps)
# ===========================================================================

def apply_risk(state: FundState) -> dict[str, Any]:
    """Clamp target weights against the fund's risk limits."""
    spec: FundSpec = state["metadata"]["fund_spec"]
    target_weights = state.get("target_weights", {})

    risk_model = HardLimits(
        max_position_pct=spec.risk.max_position_pct,
        max_gross_exposure=spec.risk.max_gross_exposure,
    )
    result = risk_model.apply(target_weights)

    return {
        "final_weights": result.weights,
        "clamps": result.clamps,
    }


# ===========================================================================
# Node 5: Build orders from target weights vs current positions
# ===========================================================================

def build_orders(state: FundState) -> dict[str, Any]:
    """Compute orders needed to move from current positions to target weights."""
    final_weights = state.get("final_weights", {})
    marks = state.get("marks", {})
    equity_before = state.get("equity_before", state.get("metadata", {}).get("capital", 100_000))

    # Get current positions from broker
    broker = state["metadata"].get("broker")
    current_positions: dict[str, float] = {}
    if broker:
        for ticker, pos in broker.positions().items():
            current_positions[ticker] = pos.shares

    orders: list[Order] = []
    all_tickers = sorted(set(list(final_weights.keys()) + list(current_positions.keys())))

    for ticker in all_tickers:
        price = marks.get(ticker)
        if not price or price <= 0:
            continue

        target_value = final_weights.get(ticker, 0.0) * equity_before
        target_shares = target_value / price
        current_shares = current_positions.get(ticker, 0.0)
        delta = target_shares - current_shares

        if abs(delta) < 0.01:  # skip negligible changes
            continue

        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        orders.append(Order(
            ticker=ticker,
            side=side,
            shares=abs(delta),
            limit_price=price,
            reasoning=f"Target: {final_weights.get(ticker, 0):.2%} of equity",
        ))

    return {"orders": orders}


# ===========================================================================
# Node 6: Execute orders through the broker
# ===========================================================================

def execute_orders(state: FundState) -> dict[str, Any]:
    """Place all orders through the broker and collect fills."""
    orders: list[Order] = state.get("orders", [])
    broker = state["metadata"].get("broker")

    fills: list[Fill] = []
    if broker is None:
        return {"fills": fills, "errors": ["No broker configured"]}

    for order in orders:
        try:
            fill = broker.place_order(order)
            fills.append(fill)
        except Exception as e:
            fills.append(Fill(
                ticker=order.ticker,
                side=order.side,
                shares=0,
                price=0,
            ))

    return {"fills": fills}


# ===========================================================================
# Node 7: Record the cycle (build the final state / CycleRecord)
# ===========================================================================

def record_cycle(state: FundState) -> dict[str, Any]:
    """Compute final NAV and positions for the cycle record."""
    broker = state["metadata"].get("broker")
    marks = state.get("marks", {})

    positions: dict[str, float] = {}
    cash = 0.0
    nav = 0.0

    if broker:
        for ticker, pos in broker.positions().items():
            positions[ticker] = pos.shares
        cash = broker.cash()
        nav = cash + sum(s * marks.get(t, 0) for t, s in positions.items())

    return {
        "positions": positions,
        "cash": cash,
        "nav": nav,
    }
