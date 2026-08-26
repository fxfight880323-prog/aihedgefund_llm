# -*- coding: utf-8 -*-
"""诊断：日频引擎每期实际持仓 vs 目标权重（验证持仓漂移）"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")
from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate

PIT_DATES = [
    ("2021-08", "2021-08-31"), ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"), ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"), ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"), ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"), ("2026-04", "2026-04-30"),
]

class DiagStrategy(StrategyTemplate):
    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
        self.pos_log = {}
    def on_bars(self, bars):
        dt = self.engine.datetime
        if dt not in self.weights_by_dt:
            return
        weights = self.weights_by_dt[dt]
        equity = self.engine.get_equity(bars)
        self.target_data = {}
        for tk, w in weights.items():
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar and bar.close_price > 0:
                self.target_data[tk] = w * equity / bar.close_price
        for s, pos in list(self.engine.pos_data.items()):
            if pos > 0 and s not in weights:
                self.target_data[s] = 0.0
        # 记录调仓前持仓
        self.pos_log[dt] = {"before": {s: p for s, p in self.engine.pos_data.items() if p > 0},
                            "target": dict(weights)}
        self.rebalance_portfolio(bars)

px = json.load(open("_bt_daily_px.json", encoding="utf-8"))
bars = {}
for tk, d in px.items():
    mm = {}
    for dt, r in d.items():
        c = r.get("close")
        if c and c > 0 and dt >= "2021-05-01":
            mm[dt] = BarData(tk, dt, r.get("open") or c, r.get("high") or c,
                             r.get("low") or c, c)
    if mm:
        bars[tk] = mm
all_dates = sorted({dt for m in bars.values() for dt in m})

weights = json.load(open("_bt_band_results.json", encoding="utf-8"))["weights"]
w_by_dt = {}
for month, asof in PIT_DATES:
    trig = max(d for d in all_dates if d <= asof)
    w_by_dt[trig] = weights["core"][month]

engine = BacktestingEngine()
engine.set_parameters(symbols=list(bars.keys()), capital=1e6, rate=0.0005,
                      slippage=0.001, annual_periods=252)
engine.add_data(bars)
st = DiagStrategy(engine, {"weights_by_dt": w_by_dt})
engine.add_strategy(st)
engine.run_backtesting()

print(f"\n{'触发日':<12}{'调仓前持仓数':>12}{'目标持仓数':>12}")
for trig in sorted(w_by_dt):
    lg = st.pos_log.get(trig)
    if lg:
        print(f"{trig:<12}{len(lg['before']):>12}{len(lg['target']):>12}")

# 每期实际持仓（调仓后）
print("\n每期实际持仓（次月撮合后 pos>0 股票数）:")
import collections
# 从 pos_data 最终状态 + 交易记录反推不现实，用成交记录
trades = engine.trades
# 记录每次调仓后的持仓快照：在撮合日后 5 个交易日取样
snap = {}
for trig in sorted(w_by_dt):
    # 找到 trig 后的第 5 个交易日
    nxt = [d for d in all_dates if d > trig][:8]
    for d in nxt:
        snap.setdefault(trig, []).append((d, sum(1 for s, p in engine.pos_data.items() if p > 0)))
# pos_data 是最终状态，无法回溯。改为直接从 trades 统计每只股票净持仓
net = collections.Counter()
for t in trades:
    d = t.symbol
    net[d] += t.volume if t.direction == "LONG" else -t.volume
print("期末净持仓:", sum(1 for v in net.values() if v > 0), "只")
