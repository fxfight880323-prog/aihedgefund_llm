"""TEMPLATE: Custom Broker
============================================================================

Copy this file and implement your own broker for live or paper trading.

IDEAS:
  - AlpacaBroker: use Alpaca Markets API (paper or live)
  - IBBroker: Interactive Brokers TWS/IB Gateway
  - CCXTBroker: Crypto exchange (Kraken, Binance)
  - PaperBroker: live data, simulated fills (with slippage model)
  - MultiBroker: route orders to different brokers

REGISTRATION:
  In src/execution/__init__.py, add:
    from src.execution.my_broker import MyBroker
"""

from __future__ import annotations

from src.core.models import Order, Fill, Position
from src.core.interfaces import Broker


class TemplateBroker(Broker):
    """BLANK TEMPLATE — implement your own broker.

    For live trading, implement these methods to connect to your broker's API.
    """

    def __init__(self, **params):
        """Initialize broker connection.

        Common params:
          - api_key: str
          - api_secret: str
          - base_url: str
          - paper: bool (paper trading mode)
        """
        # self._client = connect_to_broker(**params)
        pass

    def positions(self) -> dict[str, Position]:
        """Query current positions from the broker."""
        # TODO: Call broker API
        # positions = self._client.get_positions()
        # return {p.ticker: Position(ticker=p.ticker, shares=p.qty, avg_cost=p.avg_price)
        #         for p in positions}
        raise NotImplementedError

    def cash(self) -> float:
        """Query current cash balance."""
        # TODO: Call broker API
        # return float(self._client.get_account().cash)
        raise NotImplementedError

    def place_order(self, order: Order) -> Fill:
        """Submit an order and return the fill.

        For live trading, you might:
          - Submit a market or limit order
          - Wait for fill confirmation
          - Handle partial fills
          - Add slippage / commission tracking
        """
        # TODO: Call broker API
        # result = self._client.submit_order(
        #     symbol=order.ticker,
        #     qty=order.shares,
        #     side=order.side.value,
        #     type="market" if order.limit_price is None else "limit",
        #     limit_price=order.limit_price,
        # )
        # return Fill(ticker=order.ticker, side=order.side,
        #             shares=result.filled_qty, price=result.filled_avg_price)
        raise NotImplementedError

    def get_price(self, ticker: str) -> float | None:
        """Get real-time price for a ticker."""
        # TODO: Call broker API
        # quote = self._client.get_latest_quote(ticker)
        # return quote.ask_price  # or mid price
        raise NotImplementedError
