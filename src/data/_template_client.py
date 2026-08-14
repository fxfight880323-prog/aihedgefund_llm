"""TEMPLATE: Custom Data Client
============================================================================

Copy this file, rename it, and implement the methods to bring your own
data source into the fund. You could wrap:
  - yfinance (free Yahoo Finance data)
  - Alpha Vantage API
  - Bloomberg Terminal
  - Your broker's API (Alpaca, IB, etc.)
  - A local database of your own research data
  - Alternative data (satellite, social media, shipping)

The only requirement: implement these four methods. The framework handles
the rest.

REGISTRATION:
  After implementing, register in src/data/__init__.py:
    from src.data.my_client import MyClient
    DATA_CLIENT_REGISTRY["my_source"] = MyClient

USAGE IN CODE:
    from src.data.my_client import MyClient
    data_client = MyClient(api_key="...")
    # Pass to workflow runner
"""

from __future__ import annotations

from typing import Any

from src.data.cache import DiskCache


class TemplateDataClient:
    """BLANK TEMPLATE — implement these methods to add your data source.

    CONTRACT (non-negotiable):
      - Empty list/None = data doesn't exist (NOT an error)
      - Infrastructure failures (auth, network) must RAISE
      - Must be point-in-time: only return data available by end_date
    """

    def __init__(self, **kwargs):
        """Initialize your client.

        Common params:
          - api_key: str
          - cache: DiskCache
          - base_url: str
        """
        # self._api_key = kwargs.get("api_key", "")
        # self._cache = kwargs.get("cache") or DiskCache()
        pass

    def get_prices(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Return historical prices for a ticker.

        MUST return a list of dicts with at minimum:
            {"time": "2024-01-15", "open": ..., "high": ..., "low": ...,
             "close": ..., "volume": ...}

        Point-in-time: only return bars where time <= end_date.
        """
        # TODO: Implement your data fetching logic here
        raise NotImplementedError("Implement get_prices() in your data client")

    def get_financial_metrics(
        self, ticker: str, end_date: str, period: str = "ttm", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return fundamental metrics for a ticker.

        Suggested fields (implement what you have):
            market_cap, pe_ratio, pb_ratio, ps_ratio,
            roe, roa, gross_margin, operating_margin, net_margin,
            debt_to_equity, current_ratio, free_cash_flow_yield,
            revenue_growth, earnings_growth

        Point-in-time: only return data that was PUBLIC by end_date.
        """
        # TODO: Implement your data fetching logic here
        raise NotImplementedError("Implement get_financial_metrics()")

    def get_company_facts(self, ticker: str) -> dict[str, Any] | None:
        """Return company description, sector, industry, etc.

        Return None if not available. This is for context only.
        """
        # TODO: Implement
        return None

    def get_earnings(self, ticker: str) -> dict[str, Any] | None:
        """Return earnings data (actual vs estimate, surprise).

        Suggested structure:
            {"eps_actual": 1.50, "eps_estimated": 1.40, "surprise": "BEAT"}
        """
        # TODO: Implement
        return None


# ===========================================================================
# OPTIONAL: Add custom data methods beyond the standard interface
# ===========================================================================

class TemplateAlternativeDataClient:
    """TEMPLATE: Alternative data source for custom alpha models.

    This is for data that doesn't fit the standard DataClient interface:
      - Satellite imagery analysis
      - Social media sentiment
      - Web traffic / app downloads
      - Supply chain data
      - Patent filings
      - Congressional trading data

    Your custom alpha models can use these methods directly — they don't
    need to go through the standard DataClient protocol.
    """

    def get_sentiment(self, ticker: str, date: str) -> float:
        """Return sentiment score [-1, 1] for a ticker on a date."""
        # TODO: Implement your alternative data logic
        raise NotImplementedError

    def get_social_mentions(self, ticker: str, date: str, days: int = 7) -> dict:
        """Return social media mention counts and sentiment."""
        # TODO: Implement
        raise NotImplementedError

    def get_insider_transactions(self, ticker: str, date: str) -> list[dict]:
        """Return insider buying/selling data."""
        # TODO: Implement
        raise NotImplementedError
