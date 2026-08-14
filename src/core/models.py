"""Core data contracts — the single source of truth for all structures.

These are the data types that flow through the LangGraph workflow.
Every alpha model, risk model, and executor produces or consumes these.

    Signal         ← an alpha model's view on a ticker (conviction + thesis)
    QuantSignals   ← all signals for a ticker on a date
    TargetWeight   ← a portfolio weight after blending + risk
    Order          ← an execution instruction
    Fill           ← a confirmed execution
    CycleRecord    ← the complete receipt of one fund cycle
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Signal — the atomic unit of investment intelligence
# ---------------------------------------------------------------------------

class Signal(BaseModel):
    """A view from an alpha model.

    This is what every analyst (quant or LLM) produces. The value is the
    *conviction* in [-1, +1]: -1 = maximally bearish, 0 = no view, +1 =
    maximally bullish. The reasoning is the thesis — for LLM agents it's
    the model's narrative; for quant models it's a formula description.

    Add your own metadata fields in the `metadata` dict. The framework
    never looks inside metadata — it's yours to use.
    """

    model_name: str = Field(description="which alpha model produced this, e.g. 'pead', 'buffett'")
    ticker: str
    date: str = Field(description="as-of date (YYYY-MM-DD)")
    value: float = Field(description="conviction from -1.0 (bearish) to +1.0 (bullish)")
    reasoning: str | None = None
    components: dict[str, float] = Field(
        default_factory=dict,
        description="quant decomposition — sub-scores that sum to the value",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuantSignals(BaseModel):
    """All signals for a single ticker on a single date."""

    ticker: str
    date: str
    signals: dict[str, Signal] = Field(default_factory=dict)
    composite_score: float | None = None


# ---------------------------------------------------------------------------
# Portfolio & Risk
# ---------------------------------------------------------------------------

class BlendResult(BaseModel):
    """Per-ticker blended convictions and the target weights they imply."""

    convictions: dict[str, float] = Field(
        description="blended view per ticker, pre-scaling"
    )
    weights: dict[str, float] = Field(
        description="target weight per ticker; sum(|w|) <= gross_target"
    )


class ClampEvent(BaseModel):
    """One risk limit firing — recorded so every clamp is explainable."""

    limit: str = Field(description="which limit fired, e.g. 'max_position_pct'")
    ticker: str | None = None
    before: float
    after: float


class RiskResult(BaseModel):
    """Clamped weights plus the audit trail of every limit that fired."""

    weights: dict[str, float]
    clamps: list[ClampEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Order(BaseModel):
    ticker: str
    side: OrderSide
    shares: float
    limit_price: float | None = None
    reasoning: str | None = None


class Fill(BaseModel):
    ticker: str
    side: OrderSide
    shares: float
    price: float
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Positions & Ledger
# ---------------------------------------------------------------------------

class Position(BaseModel):
    ticker: str
    shares: float
    avg_cost: float


class CycleRecord(BaseModel):
    """The complete receipt of one fund cycle — the audit trail.

    This is what gets persisted after every run. It contains every signal,
    every clamp, every order, and the final NAV. It's the fund's memory.
    """

    fund_name: str
    as_of: str
    universe: list[str]
    marks: dict[str, float] = Field(description="ticker -> last close price")
    signals: list[Signal] = Field(default_factory=list)
    target_weights: dict[str, float] = Field(default_factory=dict)
    final_weights: dict[str, float] = Field(default_factory=dict)
    clamps: list[ClampEvent] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    fills: list[Fill] = Field(default_factory=list)
    positions: dict[str, float] = Field(default_factory=dict)
    cash: float = 0.0
    nav: float = 0.0
    equity_before: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
