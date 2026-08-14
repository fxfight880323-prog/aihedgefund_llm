"""TEMPLATE: Custom Quant Alpha Model
============================================================================

Copy this file, rename it, and implement your own quant signal.

IDEAS FOR QUANT MODELS:
  - Momentum: 12-1 month price momentum
  - Mean reversion: RSI-based or Bollinger band
  - Value: P/E, P/B, EV/EBITDA screens
  - Quality: ROE + earnings stability + low leverage
  - Factor combos: Fama-French 5-factor
  - Sentiment: news/social media sentiment aggregation
  - Technical: MACD, RSI, moving average crossovers
  - Statistical: cointegration, z-score mean reversion
  - Macro: regime detection, yield curve signals
  - Alternative: insider trading, patent filings, satellite data

Your model can use any data the DataClient provides, plus any custom
data source you build (see src/data/_template_client.py).

REGISTRATION:
  In src/signals/__init__.py, add:
    from src.signals.my_model import MyModel
    ALPHA_MODEL_REGISTRY["my_model"] = MyModel

USAGE IN STRATEGY YAML:
  models:
    - name: my_model
      weight: 1.0
      params:
        lookback_days: 252
        threshold: 0.05
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.core.models import Signal
from src.core.interfaces import QuantModel


class TemplateQuantModel(QuantModel):
    """BLANK TEMPLATE — implement your quant signal here.

    The predict() method is called once per (ticker, date) during a cycle.
    It must return a Signal with value in [-1, +1].

    RULES:
      - Point-in-time: only use data with date <= the given date
      - 0.0 = no view (abstain). Don't fake conviction.
      - Cache expensive fetches in __init__ or on the instance.
    """

    def __init__(self, **params):
        """Accept constructor params from the strategy YAML.

        In your YAML:
            models:
              - name: my_model
                params:
                  lookback_days: 252
                  threshold: 0.05

        These arrive as kwargs here.
        """
        # self.lookback = params.get("lookback_days", 252)
        # self.threshold = params.get("threshold", 0.05)
        self._cache: dict[str, Any] = {}
        self._params = params

    @property
    def name(self) -> str:
        """This must match the key in ALPHA_MODEL_REGISTRY."""
        return "my_model"  # TODO: Rename to your model's name

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        """Form a point-in-time view on *ticker* as of *date*.

        STEPS:
          1. Fetch data from data_client (point-in-time!)
          2. Compute your signal
          3. Map to conviction in [-1, +1]
          4. Return a Signal with reasoning
        """
        # ---- STEP 1: Fetch data ----
        # as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
        # start = (as_of - timedelta(days=self.lookback)).isoformat()
        # prices = data_client.get_prices(ticker, start, date)
        # if not prices or len(prices) < 30:
        #     return self._neutral(ticker, date)

        # ---- STEP 2: Compute your signal ----
        # Example: simple momentum
        # closes = [p["close"] for p in prices]
        # momentum = (closes[-1] / closes[-20]) - 1  # 20-day return
        #
        # Example: RSI
        # rsi = self._compute_rsi(closes)
        #
        # Example: fundamental screen
        # metrics = data_client.get_financial_metrics(ticker, date, limit=1)
        # roe = metrics[0].get("roe", 0) if metrics else 0

        # ---- STEP 3: Map to conviction [-1, +1] ----
        # value = self._sigmoid(momentum, scale=3.0)
        # OR: value = 1.0 if momentum > self.threshold else -1.0

        # ---- STEP 4: Return Signal ----
        # return Signal(
        #     model_name=self.name,
        #     ticker=ticker,
        #     date=date,
        #     value=value,
        #     reasoning=f"Momentum: {momentum:.2%} over 20 days",
        #     components={"momentum": momentum},
        #     metadata={"lookback": self.lookback},
        # )

        # TODO: Remove this placeholder and implement your logic
        return self._neutral(ticker, date)

    def _neutral(self, ticker: str, date: str) -> Signal:
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=0.0,
            reasoning="No signal generated (template not implemented)",
        )

    # ---- HELPER METHODS ----
    # Add your own computation helpers here. Common patterns:

    def _compute_rsi(self, closes: list[float], period: int = 14) -> float:
        """RSI — add any technical indicators you need."""
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _zscore(self, value: float, series: list[float]) -> float:
        """Z-score of a value relative to a series."""
        if len(series) < 2:
            return 0.0
        mean = sum(series) / len(series)
        variance = sum((x - mean) ** 2 for x in series) / len(series)
        std = variance ** 0.5
        if std == 0:
            return 0.0
        return (value - mean) / std
