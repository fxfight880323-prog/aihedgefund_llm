"""vnpy 式组合回测引擎（参照 vnpy_portfoliostrategy/backtesting.py）。

架构对应关系（vnpy → 本模块）：
  BacktestingEngine          → BacktestingEngine（本模块）
  StrategyTemplate           → src/backtest/strategy.py
  BarData                    → BarData（月频，open=high=low=close 近似）
  ContractDailyResult        → ContractDailyResult
  PortfolioDailyResult       → PortfolioDailyResult
  new_bars(dt) 的撮合顺序    → cross_limit_order() → strategy.on_bars() → update_daily_close()
  calculate_statistics()     → 同公式，annual_periods=12（月频）

与 vnpy 的刻意差异（均为长多基金所需）：
  1. 引擎维护 cash 逐笔记账（vnpy 用 net_pnl 后验重建 balance）——
     目标仓位再平衡需要实时 equity 把权重换成股数。
  2. slippage 计入成交价（vnpy 作为独立成本行扣减）——保持 cash/持仓
     与 NAV 一致，经济上等价。
  3. 无空头方向（公募长多）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.core.models import Order, OrderSide


def _month_span(start: str, end: str) -> int:
    """两个月键之间的月数（含端点差），用于日历年化。"""
    try:
        y0, m0 = int(start[:4]), int(start[5:7])
        y1, m1 = int(end[:4]), int(end[5:7])
        return max((y1 - y0) * 12 + (m1 - m0), 1)
    except (ValueError, IndexError):
        return 1


@dataclass
class BarData:
    symbol: str
    dt: str            # 月键 "YYYY-MM"
    open_price: float
    high_price: float
    low_price: float
    close_price: float


@dataclass
class TradeData:
    tradeid: str
    symbol: str
    direction: str     # "LONG" / "SHORT"
    price: float       # 含滑点的实际成交价
    raw_price: float   # 撮合价（未含滑点）
    volume: float
    dt: str
    turnover: float
    commission: float


class ContractDailyResult:
    """单标的单期 PnL（同 vnpy_contractdailyresult）。"""

    def __init__(self, symbol: str, close_price: float):
        self.symbol = symbol
        self.close_price = close_price
        self.pre_close = 0.0
        self.start_pos = 0.0
        self.end_pos = 0.0
        self.trades: list[TradeData] = []
        self.turnover = 0.0
        self.commission = 0.0
        self.trading_pnl = 0.0
        self.holding_pnl = 0.0
        self.total_pnl = 0.0
        self.net_pnl = 0.0

    def add_trade(self, trade: TradeData) -> None:
        self.trades.append(trade)

    def calculate_pnl(self, pre_close: float, start_pos: float,
                      rate: float) -> None:
        self.pre_close = pre_close if pre_close else self.close_price
        self.start_pos = start_pos
        self.end_pos = start_pos
        self.holding_pnl = (self.start_pos
                            * (self.close_price - self.pre_close))
        for trade in self.trades:
            pos_change = (trade.volume if trade.direction == "LONG"
                          else -trade.volume)
            self.trading_pnl += pos_change * (self.close_price
                                              - trade.price)
            self.commission += trade.commission
            self.turnover += trade.turnover
            self.end_pos += pos_change
        self.total_pnl = self.trading_pnl + self.holding_pnl
        self.net_pnl = self.total_pnl - self.commission


class PortfolioDailyResult:
    """单期组合 PnL（聚合各标的）。"""

    def __init__(self, dt: str):
        self.dt = dt
        self.contracts: dict[str, ContractDailyResult] = {}

    def add_close(self, symbol: str, close_price: float) -> None:
        if symbol not in self.contracts:
            self.contracts[symbol] = ContractDailyResult(symbol, close_price)
        else:
            self.contracts[symbol].close_price = close_price

    def add_trade(self, trade: TradeData) -> None:
        if trade.symbol not in self.contracts:
            self.contracts[trade.symbol] = ContractDailyResult(
                trade.symbol, trade.price)
        self.contracts[trade.symbol].add_trade(trade)

    def calculate_pnl(self, pre_closes: dict[str, float],
                      start_poses: dict[str, float],
                      rates: dict[str, float]) -> dict[str, float]:
        for symbol, contract in self.contracts.items():
            contract.calculate_pnl(
                pre_closes.get(symbol, 0.0),
                start_poses.get(symbol, 0.0),
                rates.get(symbol, 0.0),
            )
        return {
            "trade_count": sum(len(c.trades) for c in
                               self.contracts.values()),
            "turnover": sum(c.turnover for c in self.contracts.values()),
            "commission": sum(c.commission for c in
                              self.contracts.values()),
            "trading_pnl": sum(c.trading_pnl for c in
                               self.contracts.values()),
            "holding_pnl": sum(c.holding_pnl for c in
                               self.contracts.values()),
            "total_pnl": sum(c.total_pnl for c in self.contracts.values()),
            "net_pnl": sum(c.net_pnl for c in self.contracts.values()),
        }

    @property
    def close_prices(self) -> dict[str, float]:
        return {s: c.close_price for s, c in self.contracts.items()}

    @property
    def end_poses(self) -> dict[str, float]:
        return {s: c.end_pos for s, c in self.contracts.items()}


class BacktestingEngine:
    """月频组合回测引擎。

    撮合语义（vnpy）：第 N 期 on_bars 内下的限价单，在第 N+1 期
    cross_limit_order() 撮合——成交价 = min(委托价, N+1 期开盘价)
    （多头），再加逆向滑点。信息在 N 期、成交在 N+1 期 → 无前视。
    """

    def __init__(self):
        self.strategy = None
        self.symbols: list[str] = []
        self.capital = 1_000_000.0
        self.rates: dict[str, float] = {}
        self.slippages: dict[str, float] = {}
        self.annual_periods = 12          # 月频 → 年化周期数
        self.risk_free = 0.02

        self.history_data: dict[str, dict[str, BarData]] = {}
        self.dts: list[str] = []
        self.datetime: str | None = None
        self.bars: dict[str, BarData] = {}   # 引擎撮合缓存（前向填充）

        self.cash = 0.0
        self.pos_data: dict[str, float] = {}
        self.active_limit_orders: dict[str, Order] = {}
        self.limit_orders: dict[str, Order] = {}
        self.order_count = 0
        self.trade_count = 0
        self.trades: list[TradeData] = []
        self.logs: list[str] = []
        self.daily_results: dict[str, PortfolioDailyResult] = {}
        self.daily_df: list[dict] = []
        self.statistics: dict = {}

    # ------------------------------------------------------------------
    # 设置
    # ------------------------------------------------------------------

    def set_parameters(self, symbols: list[str], capital: float,
                       rate: float = 0.0005,
                       slippage: float = 0.001,
                       annual_periods: int = 12,
                       risk_free: float = 0.02) -> None:
        self.symbols = list(symbols)
        self.capital = float(capital)
        self.cash = float(capital)
        self.rates = {s: rate for s in symbols}
        self.slippages = {s: slippage for s in symbols}
        self.annual_periods = annual_periods
        self.risk_free = risk_free

    def add_data(self, bars: dict[str, dict[str, BarData]]) -> None:
        self.history_data = bars
        dt_set: set[str] = set()
        for series in bars.values():
            dt_set.update(series.keys())
        self.dts = sorted(dt_set)

    def add_strategy(self, strategy) -> None:
        self.strategy = strategy

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run_backtesting(self) -> None:
        if not self.strategy:
            raise RuntimeError("add_strategy() first")
        self.strategy.on_init()
        self.strategy.inited = True
        self.strategy.on_start()
        self.strategy.trading = True

        total = len(self.dts)
        batch = max(total // 10, 1)
        for ix, dt in enumerate(self.dts):
            try:
                self.new_bars(dt)
            except Exception:
                self.output(f"异常，回测终止 @ {dt}")
                import traceback
                self.output(traceback.format_exc())
                return
            if (ix + 1) % batch == 0:
                self.output(f"回测进度 {ix + 1}/{total} ({dt})")
        self.strategy.on_stop()

    def new_bars(self, dt: str) -> None:
        self.datetime = dt
        bars: dict[str, BarData] = {}
        for symbol in self.symbols:
            bar = self.history_data.get(symbol, {}).get(dt)
            if bar is not None:
                self.bars[symbol] = bar
                bars[symbol] = bar
            elif symbol in self.bars:
                # vnpy 语义：缺失期用前期收盘做平 bar 维护撮合缓存，
                # 但不喂给策略回调
                old = self.bars[symbol]
                flat = BarData(symbol, dt, old.close_price,
                               old.close_price, old.close_price,
                               old.close_price)
                self.bars[symbol] = flat
        self.cross_limit_order()
        self.strategy.on_bars(bars)
        if self.strategy.inited:
            self.update_daily_close(dt)

    def update_daily_close(self, dt: str) -> None:
        result = self.daily_results.get(dt)
        if result is None:
            result = PortfolioDailyResult(dt)
            self.daily_results[dt] = result
        for symbol, bar in self.bars.items():
            result.add_close(symbol, bar.close_price)

    # ------------------------------------------------------------------
    # 订单与撮合
    # ------------------------------------------------------------------

    def send_order(self, strategy, symbol: str, side: Side,
                   price: float, volume: float) -> list[str]:
        if volume <= 0:
            return []
        self.order_count += 1
        oid = f"BT.{self.order_count}"
        order = Order(ticker=symbol, side=side, shares=volume,
                      limit_price=price, reasoning=oid)
        self.active_limit_orders[oid] = order
        self.limit_orders[oid] = order
        return [oid]

    def cancel_all(self) -> None:
        for oid in list(self.active_limit_orders.keys()):
            self.active_limit_orders.pop(oid)

    def cross_limit_order(self) -> None:
        """对本期 bar 撮合挂单（vnpy：先撮合、后回调）。"""
        for oid in list(self.active_limit_orders.keys()):
            order = self.active_limit_orders[oid]
            bar = self.bars.get(order.ticker)
            if bar is None:
                continue
            is_long = order.side == OrderSide.BUY
            slip = self.slippages.get(order.ticker, 0.0)
            rate = self.rates.get(order.ticker, 0.0)
            # 限价条件（多头：委托价 >= 本期最低价）
            if is_long and order.limit_price >= bar.low_price:
                raw = min(order.limit_price, bar.open_price)
                price = raw * (1 + slip)
            elif not is_long and order.limit_price <= bar.high_price:
                raw = max(order.limit_price, bar.open_price)
                price = raw * (1 - slip)
            else:
                continue
            self.execute_trade(order, price, raw, rate)
            self.active_limit_orders.pop(oid)

    def execute_trade(self, order: Order, price: float, raw: float,
                      rate: float) -> None:
        self.trade_count += 1
        turnover = order.shares * price
        commission = turnover * rate
        trade = TradeData(
            tradeid=str(self.trade_count),
            symbol=order.ticker,
            direction="LONG" if order.side == OrderSide.BUY else "SHORT",
            price=price, raw_price=raw, volume=order.shares,
            dt=self.datetime or "", turnover=turnover,
            commission=commission,
        )
        self.trades.append(trade)
        # 逐笔记账（vnpy 差异点 1/2：现金账 + 滑点入价）
        if order.side == OrderSide.BUY:
            self.pos_data[order.ticker] = (self.pos_data.get(order.ticker, 0.0)
                                           + order.shares)
            self.cash -= turnover + commission
        else:
            self.pos_data[order.ticker] = (self.pos_data.get(order.ticker, 0.0)
                                           - order.shares)
            if abs(self.pos_data[order.ticker]) < 1e-9:
                self.pos_data[order.ticker] = 0.0
            self.cash += turnover - commission
        # 交易落进当期 bucket
        dt = self.datetime or ""
        if dt:
            result = self.daily_results.get(dt)
            if result is None:
                result = PortfolioDailyResult(dt)
                self.daily_results[dt] = result
            result.add_trade(trade)

    def get_equity(self, bars: dict[str, BarData]) -> float:
        """当前权益（现金 + 持仓按最新价 mark-to-market）。"""
        holding = sum(self.pos_data.get(s, 0.0) * b.close_price
                      for s, b in bars.items())
        # 不在本次回调里的持仓用引擎缓存价
        extra = sum(self.pos_data.get(s, 0.0) * b.close_price
                    for s, b in self.bars.items() if s not in bars)
        return self.cash + holding + extra

    # ------------------------------------------------------------------
    # 结果与统计（vnpy 公式）
    # ------------------------------------------------------------------

    def calculate_result(self) -> list[dict]:
        results = [self.daily_results[dt] for dt in sorted(self.dts)]
        pre_closes: dict[str, float] = {}
        start_poses: dict[str, float] = {}
        self.daily_df = []
        for daily in results:
            agg = daily.calculate_pnl(pre_closes, start_poses, self.rates)
            row = {"dt": daily.dt, **agg}
            # 与逐笔记账交叉验证的余额（vnpy 用 net_pnl 累计重建）
            row["balance"] = (sum(r["net_pnl"] for r in self.daily_df)
                              + agg["net_pnl"] + self.capital)
            self.daily_df.append(row)
            pre_closes = daily.close_prices
            start_poses = daily.end_poses
        return self.daily_df

    def calculate_statistics(self, df: list[dict] | None = None,
                             output: bool = True) -> dict:
        rows = df if df is not None else self.daily_df
        if not rows:
            return {}
        capital = self.capital
        n = len(rows)
        balances = [r["balance"] for r in rows]
        rets = [math.log(balances[i] / balances[i - 1])
                if balances[i - 1] > 0 and balances[i] > 0 else 0.0
                for i in range(1, n)]
        mean_ret = sum(rets) / len(rets) if rets else 0.0
        std_ret = (math.sqrt(sum((r - mean_ret) ** 2 for r in rets)
                             / (len(rets) - 1)) if len(rets) > 1 else 0.0)
        p = self.annual_periods
        rf_period = self.risk_free / math.sqrt(p)
        sharpe = ((mean_ret - rf_period) / std_ret * math.sqrt(p)
                  if std_ret > 0 else 0.0)

        # 回撤（滚动最高余额）
        high = balances[0]
        max_dd = 0.0
        max_ddpct = 0.0
        dd_start = rows[0]["dt"]
        max_dd_start, max_dd_end = dd_start, dd_start
        for i, bal in enumerate(balances):
            if bal >= high:
                high = bal
                dd_start = rows[i]["dt"]
            dd = bal - high
            if dd < max_dd:
                max_dd = dd
                max_ddpct = dd / high * 100 if high > 0 else 0.0
                max_dd_start, max_dd_end = dd_start, rows[i]["dt"]

        end_balance = balances[-1]
        total_return = end_balance / capital - 1.0
        # 年化按日历月跨度（防数据缺口把年化放大）
        span_months = _month_span(rows[0]["dt"], rows[-1]["dt"])
        annual_return = total_return / span_months * self.annual_periods

        stats = {
            "start_date": rows[0]["dt"],
            "end_date": rows[-1]["dt"],
            "total_months": n,
            "capital": capital,
            "end_balance": end_balance,
            "total_return": total_return * 100,
            "annual_return": annual_return * 100,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "max_ddpercent": max_ddpct,
            "max_dd_duration": f"{max_dd_start} → {max_dd_end}",
            "return_drawdown_ratio": (-total_return * 100 / max_ddpct
                                      if max_ddpct < 0 else 0.0),
            "total_commission": sum(r["commission"] for r in rows),
            "total_turnover": sum(r["turnover"] for r in rows),
            "total_trade_count": sum(r["trade_count"] for r in rows),
        }
        self.statistics = stats
        if output:
            self.show_stats(stats)
        return stats

    @staticmethod
    def show_stats(stats: dict) -> None:
        print("\n" + "-" * 50)
        print("回测统计（vnpy 公式，月频年化 ×12）")
        print("-" * 50)
        keys_zh = {
            "start_date": "起始", "end_date": "结束",
            "total_months": "月数", "capital": "初始资金",
            "end_balance": "期末权益", "total_return": "总收益%",
            "annual_return": "年化收益%", "sharpe_ratio": "夏普",
            "max_drawdown": "最大回撤", "max_ddpercent": "最大回撤%",
            "max_dd_duration": "回撤区间", "return_drawdown_ratio":
            "收益回撤比", "total_commission": "总佣金",
            "total_turnover": "总成交额", "total_trade_count": "成交笔数",
        }
        for k, label in keys_zh.items():
            if k in stats:
                print(f"  {label:　<8}{stats[k]}")

    def output(self, msg: str) -> None:
        self.logs.append(msg)
        print(f"  {msg}", flush=True)
