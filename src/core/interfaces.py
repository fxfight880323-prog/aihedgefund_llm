"""Abstract interfaces — the contracts every pluggable component implements.

The framework is built on these five interfaces:

    AlphaModel    → forms a view (Signal) on a ticker
    DataClient    → provides point-in-time market data
    BlendPolicy   → turns signals into target weights
    RiskModel     → clamps weights against hard limits
    Broker        → executes orders and tracks positions

Everything else is orchestration. Implement any of these and it plugs in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from src.core.models import (
    BlendResult,
    ClampEvent,
    Fill,
    Order,
    Position,
    RiskResult,
    Signal,
)


# ===========================================================================
# 1. AlphaModel — the analyst interface
# ===========================================================================

class AlphaModel(ABC):
    """Abstract base for all alpha models. Forms a view, returns a Signal.

    Two flavors share this interface:
      - QuantModel: pure Python math (momentum, mean-reversion, factor screens)
      - LLMAgent:   LLM reasons over data in a persona's voice

    The model only forms a *view* (conviction). It does NOT decide position
    sizing or timing — that's portfolio construction and execution.

    TO ADD YOUR OWN MODEL:
      1. Subclass AlphaModel (or QuantModel / LLMAgent)
      2. Implement `name` property and `predict()` method
      3. Register it in src/signals/__init__.py
      4. Reference it in a strategy YAML

    Example:
        class MyMomentumModel(QuantModel):
            @property
            def name(self) -> str:
                return "my_momentum"

            def predict(self, ticker, date, data_client) -> Signal:
                prices = data_client.get_prices(ticker, ...)
                # ... your logic ...
                return Signal(
                    model_name="my_momentum",
                    ticker=ticker,
                    date=date,
                    value=0.7,  # bullish
                    reasoning="Strong 12-month momentum",
                )
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Model identifier (e.g. 'pead', 'buffett', 'my_momentum')."""
        ...

    @abstractmethod
    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        """Form a point-in-time view on *ticker* as of *date*.

        MUST be point-in-time: only use data with date <= *date*.
        Return a Signal with conviction in [-1, +1].
        Use 0.0 to express "no view" (abstain).
        """
        ...


class QuantModel(AlphaModel):
    """Base for pure-math alpha models (no LLM).

    Provides shared numeric helpers. Subclass this for quant signals.
    """

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            f = float(value)
            return default if (f != f or f in (float("inf"), float("-inf"))) else f
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _normalize_to_signal(raw: float, low: float = -1.0, high: float = 1.0) -> float:
        return max(low, min(high, raw))

    @staticmethod
    def _sigmoid(x: float, scale: float = 5.0) -> float:
        import math
        return float(math.tanh(x * scale))


class LLMAgent(AlphaModel):
    """Base for LLM-powered investor agents.

    A persona is just a name + a system prompt. The base class handles
    LLM calls, caching, and parsing. Override `get_system_prompt()` and
    optionally `build_user_prompt()`.

    TO ADD YOUR OWN LLM AGENT:
      1. Subclass LLMAgent
      2. Set `name` and `get_system_prompt()`
      3. Optionally override `build_user_prompt()` to change what data the LLM sees
      4. Register in src/signals/__init__.py
    """

    def __init__(self, llm_client=None, **kwargs):
        self._llm = llm_client
        self._kwargs = kwargs

    def get_system_prompt(self) -> str:
        raise NotImplementedError(
            f"{type(self).__name__} must define get_system_prompt()"
        )

    def build_user_prompt(self, ticker: str, date: str, data_client: Any) -> str:
        """Override to customize what the LLM sees. Default: raw data dump."""
        return f"Analyze {ticker} as of {date}."

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        """Default LLM predict flow. Override for custom logic."""
        if self._llm is None:
            return Signal(
                model_name=self.name,
                ticker=ticker,
                date=date,
                value=0.0,
                reasoning="No LLM client configured",
                metadata={"abstained": True},
            )

        system = self.get_system_prompt()
        user = self.build_user_prompt(ticker, date, data_client)

        try:
            response = self._llm.complete(system, user)
            parsed = self._parse_response(response)
        except Exception as e:
            return Signal(
                model_name=self.name,
                ticker=ticker,
                date=date,
                value=0.0,
                reasoning=f"LLM error: {e}",
                metadata={"abstained": True, "error": str(e)},
            )

        signal_map = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}
        value = signal_map.get(parsed.get("signal", "neutral"), 0.0)
        value *= parsed.get("confidence", 0) / 100.0

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=value,
            reasoning=parsed.get("reasoning", ""),
            metadata={
                "signal": parsed.get("signal"),
                "confidence": parsed.get("confidence"),
            },
        )

    def _parse_response(self, response: str) -> dict:
        import json
        import re
        match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"signal": "neutral", "confidence": 0, "reasoning": "unparseable"}


# ===========================================================================
# 2. DataClient — the data provider interface
# ===========================================================================

@runtime_checkable
class DataClient(Protocol):
    """Protocol that all data sources must satisfy.

    Contract:
      - Empty list = data genuinely doesn't exist (not an error)
      - Infrastructure failures (auth, network) must RAISE, not return empty
      - Must be point-in-time: only return data filed/available by end_date

    TO ADD YOUR OWN DATA SOURCE:
      1. Implement these methods
      2. No inheritance needed — structural typing
      3. Register in src/data/__init__.py
    """

    def get_prices(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[dict]:
        """Return list of {time, open, high, low, close, volume}."""
        ...

    def get_financial_metrics(
        self, ticker: str, end_date: str, period: str = "ttm", limit: int = 10
    ) -> list[dict]:
        """Return fundamental metrics (P/E, ROE, margins, etc.)."""
        ...

    def get_company_facts(self, ticker: str) -> dict | None:
        """Return company description, sector, industry, etc."""
        ...

    def get_earnings(self, ticker: str) -> dict | None:
        """Return earnings data (actual vs estimate)."""
        ...


# ===========================================================================
# 3. BlendPolicy — portfolio construction interface
# ===========================================================================

class BlendPolicy(ABC):
    """How analyst views combine into target weights.

    Default implementation: conviction_weighted.
    TO ADD YOUR OWN: subclass and implement `blend()`.

    Example ideas:
      - Risk-parity blending
      - Bayesian updating (prior + signals)
      - LLM meta-aggregator that reads all signals and decides weights
    """

    @abstractmethod
    def blend(
        self,
        signals: list[Signal],
        model_weights: dict[str, float],
        gross_target: float = 1.0,
        market_neutral: bool = False,
    ) -> BlendResult:
        """Turn signals into target weights."""
        ...


# ===========================================================================
# 4. RiskModel — hard limits interface
# ===========================================================================

class RiskModel(ABC):
    """Hard caps that the analysts cannot override.

    "Conviction requests, risk disposes."

    TO ADD YOUR OWN: subclass and implement `apply()`.
    Example ideas:
      - Volatility-targeted risk
      - Drawdown-based deleveraging
      - Sector exposure limits
      - Correlation-based position limits
    """

    @abstractmethod
    def apply(self, weights: dict[str, float]) -> RiskResult:
        """Clamp target weights against risk limits."""
        ...


# ===========================================================================
# 5. Broker — execution interface
# ===========================================================================

class Broker(ABC):
    """Protocol for order execution and position tracking.

    TO ADD YOUR OWN BROKER:
      - PaperBroker: live data, simulated fills
      - AlpacaBroker: real API, paper or live
      - IBBroker: Interactive Brokers integration
    """

    @abstractmethod
    def positions(self) -> dict[str, Position]:
        ...

    @abstractmethod
    def cash(self) -> float:
        ...

    @abstractmethod
    def place_order(self, order: Order) -> Fill:
        ...

    @abstractmethod
    def get_price(self, ticker: str) -> float | None:
        ...
