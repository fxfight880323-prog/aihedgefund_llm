"""vnpy 式回测引擎单测：撮合语义、mark-to-market、统计公式。"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate, build_period_link_map
from src.core.models import OrderSide


class SimpleStrategy(StrategyTemplate):
    """月 0 满仓买入，月 2 全卖出。"""

    def on_bars(self, bars):
        dt = self.engine.datetime
        if dt == "2021-01":
            self.set_target("AAA", 1000)
            self.rebalance_portfolio(bars)
        elif dt == "2021-03":
            self.set_target("AAA", 0)
            self.rebalance_portfolio(bars)


def make_engine(px=(10.0, 11.0, 12.0, 11.5), capital=100_000.0):
    eng = BacktestingEngine()
    eng.set_parameters(symbols=["AAA"], capital=capital,
                       rate=0.0, slippage=0.0)
    months = ["2021-01", "2021-02", "2021-03", "2021-04"]
    bars = {"AAA": {m: BarData("AAA", m, p, p, p, p)
                    for m, p in zip(months, px)}}
    eng.add_data(bars)
    eng.add_strategy(SimpleStrategy(eng, {}))
    return eng, months


class TestCrossSemantics:
    def test_order_fills_next_month(self):
        """月 1 下单 → 月 2 成交（vnpy: N 期下单 N+1 期撮合）。"""
        eng, months = make_engine()
        eng.run_backtesting()
        # 唯一一笔买入成交在 2021-02（下单于 2021-01）
        buys = [t for t in eng.trades if t.direction == "LONG"]
        assert len(buys) == 1
        assert buys[0].dt == "2021-02"
        assert buys[0].price == 11.0

    def test_no_lookahead_price(self):
        """成交价是下一期价，不是当期价（10 ≠ 11）。"""
        eng, _ = make_engine()
        eng.run_backtesting()
        buys = [t for t in eng.trades if t.direction == "LONG"]
        assert buys[0].price != 10.0

    def test_sell_also_next_month(self):
        eng, _ = make_engine()
        eng.run_backtesting()
        sells = [t for t in eng.trades if t.direction == "SHORT"]
        assert len(sells) == 1
        assert sells[0].dt == "2021-04"
        assert sells[0].price == 11.5


class TestAccounting:
    def test_cash_and_position_chain(self):
        trace = {}

        class Probe(SimpleStrategy):
            def on_bars(self, bars):
                super().on_bars(bars)
                trace[self.engine.datetime] = (self.engine.cash,
                                               self.engine.pos_data
                                               .get("AAA", 0.0))

        eng, _ = make_engine()
        eng.add_strategy(Probe(eng, {}))
        eng.run_backtesting()
        # on_bars(2021-02)：本期开盘已撮合买入 1000 股 @11
        assert abs(trace["2021-02"][0] - 89_000.0) < 1e-6
        assert trace["2021-02"][1] == 1000
        # 4 月卖出 1000 @11.5 → 现金 = 89000 + 11500
        assert abs(eng.cash - 100_500.0) < 1e-6
        assert eng.pos_data["AAA"] == 0.0

    def test_equity_mark_to_market(self):
        eng, _ = make_engine()
        eng.run_backtesting()
        # 3 月末：89000 现金 + 1000 股 × 12 = 101000
        # （在 3 月 on_bars 前查询）
        eng2, _ = make_engine()
        equity_at_3 = {}

        class Probe(SimpleStrategy):
            def on_bars(self, bars):
                equity_at_3[self.engine.datetime] = \
                    self.engine.get_equity(bars)
                super().on_bars(bars)

        eng2.add_strategy(Probe(eng2, {}))
        eng2.run_backtesting()
        assert abs(equity_at_3["2021-03"] - 101_000.0) < 1e-6

    def test_pnl_reconstruction_matches_cash(self):
        """vnpy 式 net_pnl 累计重建 ≈ 现金记账终值（零成本时相等）。"""
        eng, _ = make_engine()
        eng.run_backtesting()
        daily = eng.calculate_result()
        final_balance = daily[-1]["balance"]
        assert abs(final_balance - eng.cash) < 1e-6

    def test_holding_pnl_attribution(self):
        """持有期 PnL 归因：buy@11 → 持有到 12（+1000）→ 卖@11.5。"""
        eng, _ = make_engine()
        eng.run_backtesting()
        daily = eng.calculate_result()
        by_dt = {r["dt"]: r for r in daily}
        # 2 月（成交月）：trading_pnl = 1000×(11-11)=0，holding = 0
        # 3 月：holding_pnl = 1000×(12-11) = +1000
        assert abs(by_dt["2021-03"]["holding_pnl"] - 1000.0) < 1e-6
        # 4 月（卖出月）：holding = 1000×(11.5-12) = -500,
        #                trading = 1000×(11.5-11.5)=0
        assert abs(by_dt["2021-04"]["holding_pnl"] + 500.0) < 1e-6
        total = sum(r["net_pnl"] for r in daily)
        assert abs(total - 500.0) < 1e-6   # 1000×(11.5-11)

    def test_commission_charged(self):
        eng = BacktestingEngine()
        eng.set_parameters(symbols=["AAA"], capital=100_000,
                           rate=0.001, slippage=0.0)
        months = ["2021-01", "2021-02"]
        eng.add_data({"AAA": {m: BarData("AAA", m, 10, 10, 10, 10)
                              for m in months}})
        eng.add_strategy(SimpleStrategy(eng, {}))
        eng.run_backtesting()
        buys = [t for t in eng.trades if t.direction == "LONG"]
        assert buys[0].commission == buys[0].turnover * 0.001
        assert eng.cash < 100_000 - 10_000

    def test_slippage_in_fill_price(self):
        eng = BacktestingEngine()
        eng.set_parameters(symbols=["AAA"], capital=100_000,
                           rate=0.0, slippage=0.01)
        months = ["2021-01", "2021-02"]
        eng.add_data({"AAA": {m: BarData("AAA", m, 10, 10, 10, 10)
                              for m in months}})
        eng.add_strategy(SimpleStrategy(eng, {}))
        eng.run_backtesting()
        buys = [t for t in eng.trades if t.direction == "LONG"]
        assert abs(buys[0].price - 10 * 1.01) < 1e-9


class TestStatistics:
    def test_sharpe_formula_monthly(self):
        """sharpe = (mean - rf/√12)/std × √12（vnpy 公式，月频）。"""
        eng, _ = make_engine(capital=100_000)
        eng.run_backtesting()
        daily = eng.calculate_result()
        stats = eng.calculate_statistics(daily, output=False)
        balances = [r["balance"] for r in daily]
        rets = [math.log(balances[i] / balances[i - 1])
                for i in range(1, len(balances))]
        mean = sum(rets) / len(rets)
        std = math.sqrt(sum((r - mean) ** 2 for r in rets)
                        / (len(rets) - 1))
        expect = (mean - 0.02 / math.sqrt(12)) / std * math.sqrt(12)
        assert abs(stats["sharpe_ratio"] - expect) < 1e-9

    def test_total_return(self):
        eng, _ = make_engine()
        eng.run_backtesting()
        daily = eng.calculate_result()
        stats = eng.calculate_statistics(daily, output=False)
        assert abs(stats["total_return"] - 0.5) < 1e-9   # +0.5%


class TestPortfolioResult:
    def test_multi_symbol_missing_month_ffill(self):
        """BBB 缺 2 月 → 撮合缓存平 bar，不喂策略回调。"""
        eng = BacktestingEngine()
        eng.set_parameters(symbols=["AAA", "BBB"], capital=100_000,
                           rate=0.0, slippage=0.0)
        fed_bars = []

        class Probe(StrategyTemplate):
            def on_bars(self, bars):
                fed_bars.append((self.engine.datetime, set(bars.keys())))

        eng.add_data({
            "AAA": {m: BarData("AAA", m, 10, 10, 10, 10)
                    for m in ["2021-01", "2021-02", "2021-03"]},
            "BBB": {"2021-01": BarData("BBB", "2021-01", 5, 5, 5, 5),
                    "2021-03": BarData("BBB", "2021-03", 6, 6, 6, 6)},
        })
        eng.add_strategy(Probe(eng, {}))
        eng.run_backtesting()
        by_dt = dict(fed_bars)
        assert "BBB" not in by_dt["2021-02"]   # 缺期不喂
        assert "AAA" in by_dt["2021-02"]
        assert "BBB" in by_dt["2021-03"]
        # daily close 记录了 ffill 后的 BBB 平 bar
        assert eng.daily_results["2021-02"].close_prices["BBB"] == 5.0


class TestPeriodLinkMap:
    def test_industry_scores_from_fundamentals(self):
        fin = {
            "AAA": {"2021-1": {"revenue": 200, "gross_margin": 35},
                    "2020-1": {"revenue": 100, "gross_margin": 30}},
            "BBB": {"2021-1": {"revenue": 105, "gross_margin": 20},
                    "2020-1": {"revenue": 100, "gross_margin": 25}},
        }
        uni = [("AAA", "甲", "高景气行业"), ("BBB", "乙", "低景气行业")]
        lm = build_period_link_map(fin, uni)
        hi = lm["高景气行业"]["s_scores"]
        lo = lm["低景气行业"]["s_scores"]
        assert sum(hi) > sum(lo)
        # AAA: yoy=100% → S1(广度≥40%)=2, S2(水平)=2, S3(毛利率升)=2,
        # S4(加速度: 无上上期 → 0)
        assert hi == [2, 2, 2, 0, 0]
        # BBB: yoy=5% → 全低分
        assert sum(lo) <= 2

    def test_all_industries_present(self):
        """所有行业都入表 → assigned_link 必匹配 → 不触发 scope abstain。"""
        fin = {}
        uni = [("AAA", "甲", "行业一"), ("BBB", "乙", "行业二")]
        lm = build_period_link_map(fin, uni)
        assert set(lm.keys()) == {"行业一", "行业二"}
