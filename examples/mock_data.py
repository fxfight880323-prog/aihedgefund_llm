"""Mock data client — for testing without an API key.

Returns realistic-looking synthetic data so you can test the framework
end-to-end without signing up for any API.

DO NOT use this for real analysis — the data is fake.
"""

from __future__ import annotations

import random
from typing import Any


class MockDataClient:
    """Returns synthetic data for testing. NOT for real use."""

    def __init__(self):
        self._prices: dict[str, list[dict]] = {}
        self._seed = 42

    def get_prices(self, ticker: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Return synthetic price history."""
        if ticker in self._prices:
            return [p for p in self._prices[ticker]
                    if start_date <= p["time"][:10] <= end_date]

        from datetime import date, timedelta
        random.seed(self._seed + hash(ticker) % 1000)

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        prices: list[dict[str, Any]] = []
        current = start
        price = random.uniform(50, 300)

        while current <= end:
            if current.weekday() < 5:
                daily_return = random.gauss(0.0003, 0.02)
                price *= (1 + daily_return)
                prices.append({
                    "time": current.isoformat(),
                    "open": price * random.uniform(0.99, 1.01),
                    "high": price * random.uniform(1.0, 1.03),
                    "low": price * random.uniform(0.97, 1.0),
                    "close": price,
                    "volume": random.randint(1_000_000, 50_000_000),
                })
            current += timedelta(days=1)

        self._prices[ticker] = prices
        return prices

    def get_financial_metrics(
        self, ticker: str, end_date: str, period: str = "ttm", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return synthetic fundamentals."""
        random.seed(self._seed + hash(ticker) % 1000)
        metrics: list[dict[str, Any]] = []
        for i in range(limit):
            metrics.append({
                "period": f"2024-Q{4-i}" if i < 4 else f"2023-Q{4-(i-4)}",
                "market_cap": random.uniform(1e10, 3e12),
                "pe_ratio": random.uniform(15, 45),
                "pb_ratio": random.uniform(3, 15),
                "roe": random.uniform(0.10, 0.40),
                "roa": random.uniform(0.05, 0.25),
                "gross_margin": random.uniform(0.35, 0.75),
                "operating_margin": random.uniform(0.15, 0.40),
                "net_margin": random.uniform(0.10, 0.30),
                "debt_to_equity": random.uniform(0.2, 1.5),
                "current_ratio": random.uniform(1.0, 3.0),
                "revenue_growth": random.uniform(0.05, 0.30),
                "earnings_growth": random.uniform(0.10, 0.35),
                "free_cash_flow_yield": random.uniform(0.01, 0.05),
            })
        return metrics

    def get_company_facts(self, ticker: str) -> dict[str, Any] | None:
        """Return synthetic company info."""
        sectors = {"AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
                   "GOOGL": "Communication Services", "AMZN": "Consumer Discretionary"}
        return {
            "ticker": ticker,
            "name": f"{ticker} Inc.",
            "sector": sectors.get(ticker, "Technology"),
            "industry": "Software",
            "description": f"{ticker} is a leading technology company.",
        }

    def get_earnings(self, ticker: str) -> dict[str, Any] | None:
        """Return synthetic earnings data."""
        # Deterministic per-ticker: some BEAT, some MISS, for interesting signals
        results = {
            "AAPL": ("BEAT", "2024-05-30"),
            "MSFT": ("BEAT", "2024-05-31"),
            "NVDA": ("BEAT", "2024-05-29"),
            "GOOGL": ("MISS", "2024-05-31"),
            "AMZN": ("MISS", "2024-05-30"),
        }
        surprise, filing = results.get(ticker, ("BEAT", "2024-05-30"))
        return {
            "ticker": ticker,
            "eps_actual": random.uniform(0.50, 3.00),
            "eps_estimated": random.uniform(0.45, 2.90),
            "eps_surprise": surprise,
            "filing_date": filing,
            "report_period": "2024-03-31",
        }
