"""PEAD alpha model — Post-Earnings Announcement Drift.

Example quant model. Forms a view based on earnings surprises:
bullish after a BEAT, bearish after a MISS, on the theory that the market
underreacts and the stock keeps drifting in the surprise direction.

This is your template for how a quant model works. Copy it, rename it,
change the logic — that's how you add your own signals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.core.models import Signal
from src.core.interfaces import QuantModel


class PEADModel(QuantModel):
    """Long after an EPS BEAT, short after a MISS."""

    def __init__(self, signal_window_days: int = 4, **kwargs):
        self._signal_window_days = signal_window_days
        self._cache: dict[str, list[dict]] = {}

    @property
    def name(self) -> str:
        return "pead"

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()

        # Get earnings data
        earnings = self._get_earnings(ticker, data_client)
        if not earnings:
            return self._neutral(ticker, date)

        # Find most recent earnings on or before our date
        past = []
        for e in earnings:
            filing_date = e.get("filing_date") or e.get("date")
            if not filing_date:
                continue
            try:
                fd = datetime.strptime(filing_date[:10], "%Y-%m-%d").date()
                if fd <= as_of:
                    past.append({**e, "_filing_date": fd})
            except (ValueError, TypeError):
                continue

        if not past:
            return self._neutral(ticker, date)

        # Most recent event
        event = max(past, key=lambda e: e["_filing_date"])
        filed = event["_filing_date"]

        # Only fire if the event is fresh
        if (as_of - filed).days > self._signal_window_days:
            return self._neutral(ticker, date)

        surprise = event.get("eps_surprise", "")
        if surprise == "BEAT":
            value = 1.0
        elif surprise == "MISS":
            value = -1.0
        else:
            return self._neutral(ticker, date)

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=value,
            reasoning=f"{surprise} on earnings (filed {filed.isoformat()})",
            metadata={
                "eps_surprise": surprise,
                "filing_date": filed.isoformat(),
            },
        )

    def _neutral(self, ticker: str, date: str) -> Signal:
        return Signal(
            model_name=self.name, ticker=ticker, date=date, value=0.0,
            reasoning="No qualifying earnings event in signal window"
        )

    def _get_earnings(self, ticker: str, data_client: Any) -> list[dict]:
        if ticker in self._cache:
            return self._cache[ticker]
        try:
            earnings_data = data_client.get_earnings(ticker)
            if earnings_data is None:
                records = []
            elif isinstance(earnings_data, list):
                records = earnings_data
            elif isinstance(earnings_data, dict):
                records = earnings_data.get("earnings_history", [earnings_data])
            else:
                records = []
        except Exception:
            records = []
        self._cache[ticker] = records
        return records
