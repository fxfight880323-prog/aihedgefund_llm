"""Simulated broker — for backtesting and paper trading.

Maintains cash and positions. Fills orders at the given price.
No slippage or commissions by default — add them in place_order().
"""

from __future__ import annotations

from src.core.models import Order, OrderSide, Fill, Position


class SimBroker:
    """Simulated broker for backtesting.

    Usage:
        broker = SimBroker(capital=100_000)
        fill = broker.place_order(Order(ticker="AAPL", side="buy", shares=10, limit_price=150.0))
        print(broker.positions(), broker.cash())
    """

    def __init__(self, capital: float = 100_000.0):
        self._cash = capital
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []

    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def cash(self) -> float:
        return self._cash

    def get_price(self, ticker: str) -> float | None:
        """In backtest, prices are passed via the order's limit_price."""
        return None

    def place_order(self, order: Order) -> Fill:
        price = order.limit_price or 0.0
        if price <= 0:
            raise ValueError(f"Cannot fill {order.ticker}: no price")

        cost = price * order.shares

        if order.side == OrderSide.BUY:
            if cost > self._cash:
                # Scale to what we can afford
                order = Order(
                    ticker=order.ticker,
                    side=order.side,
                    shares=self._cash / price,
                    limit_price=price,
                    reasoning=order.reasoning,
                )
                cost = price * order.shares

            self._cash -= cost
            if order.ticker in self._positions:
                pos = self._positions[order.ticker]
                total_shares = pos.shares + order.shares
                total_cost = pos.shares * pos.avg_cost + cost
                self._positions[order.ticker] = Position(
                    ticker=order.ticker,
                    shares=total_shares,
                    avg_cost=total_cost / total_shares if total_shares else 0,
                )
            else:
                self._positions[order.ticker] = Position(
                    ticker=order.ticker,
                    shares=order.shares,
                    avg_cost=price,
                )

        elif order.side == OrderSide.SELL:
            if order.ticker not in self._positions:
                raise ValueError(f"Cannot sell {order.ticker}: not held")
            pos = self._positions[order.ticker]
            sell_shares = min(order.shares, pos.shares)
            self._cash += price * sell_shares
            remaining = pos.shares - sell_shares
            if remaining <= 1e-9:
                del self._positions[order.ticker]
            else:
                self._positions[order.ticker] = Position(
                    ticker=order.ticker,
                    shares=remaining,
                    avg_cost=pos.avg_cost,
                )
            order = Order(
                ticker=order.ticker,
                side=order.side,
                shares=sell_shares,
                limit_price=price,
                reasoning=order.reasoning,
            )

        fill = Fill(
            ticker=order.ticker,
            side=order.side,
            shares=order.shares,
            price=price,
        )
        self._fills.append(fill)
        return fill

    def portfolio_value(self, prices: dict[str, float]) -> float:
        """Total NAV = cash + sum(position_value)."""
        pos_value = sum(
            p.shares * prices.get(t, 0) for t, p in self._positions.items()
        )
        return self._cash + pos_value
