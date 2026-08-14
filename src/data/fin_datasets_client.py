"""Financial Datasets API client.

Uses the financialdatasets.ai API for prices, fundamentals, and earnings.
This is the same data source used by ai-hedge-fund.

Get a free API key at: https://financialdatasets.ai
Set it as: FINANCIAL_DATASETS_API_KEY=xxx in .env
"""

from __future__ import annotations

import os
from typing import Any

import requests

from src.data.cache import DiskCache


class FinancialDatasetsClient:
    """DataClient implementation using financialdatasets.ai.

    All responses are cached to disk for fast reruns.
    """

    BASE_URL = "https://api.financialdatasets.ai"
    PRICES_ENDPOINT = "/prices"
    FUNDAMENTALS_ENDPOINT = "/financial-metrics"
    EARNINGS_ENDPOINT = "/earnings"

    def __init__(self, api_key: str | None = None, cache: DiskCache | None = None):
        self._api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "FINANCIAL_DATASETS_API_KEY not set. "
                "Get one at https://financialdatasets.ai"
            )
        self._cache = cache or DiskCache()
        self._session = requests.Session()
        self._session.headers.update({"X-API-KEY": self._api_key})

    def _fetch(self, endpoint: str, params: dict) -> dict:
        url = f"{self.BASE_URL}{endpoint}"
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_prices(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Return list of {time, open, high, low, close, volume}."""
        cache_key = ("prices", ticker, start_date, end_date)
        cached = self._cache.get(*cache_key)
        if cached is not None:
            return cached

        data = self._fetch(
            self.PRICES_ENDPOINT,
            {"ticker": ticker, "start_date": start_date, "end_date": end_date},
        )
        prices = data.get("prices", [])
        self._cache.put(prices, *cache_key)
        return prices

    def get_financial_metrics(
        self, ticker: str, end_date: str, period: str = "ttm", limit: int = 10
    ) -> list[dict[str, Any]]:
        cache_key = ("metrics", ticker, end_date, period, limit)
        cached = self._cache.get(*cache_key)
        if cached is not None:
            return cached

        data = self._fetch(
            self.FUNDAMENTALS_ENDPOINT,
            {"ticker": ticker, "period": period, "limit": limit},
        )
        metrics = data.get("financial_metrics", [])
        self._cache.put(metrics, *cache_key)
        return metrics

    def get_company_facts(self, ticker: str) -> dict[str, Any] | None:
        cache_key = ("facts", ticker)
        cached = self._cache.get(*cache_key)
        if cached is not None:
            return cached

        try:
            data = self._fetch(f"/company-facts", {"ticker": ticker})
            facts = data.get("company_facts")
            self._cache.put(facts, *cache_key)
            return facts
        except Exception:
            return None

    def get_earnings(self, ticker: str) -> dict[str, Any] | None:
        cache_key = ("earnings", ticker)
        cached = self._cache.get(*cache_key)
        if cached is not None:
            return cached

        try:
            data = self._fetch(self.EARNINGS_ENDPOINT, {"ticker": ticker})
            earnings = data.get("earnings")
            self._cache.put(earnings, *cache_key)
            return earnings
        except Exception:
            return None
