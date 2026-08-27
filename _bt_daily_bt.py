# -*- coding: utf-8 -*-
"""日频颗粒度回测：LX-core / +金融剔除 / +金融+PB band 三变体。
对齐 vnpy 语义（调仓日收盘下限价单 → 次交易日撮合），仅把 bar 颗粒度从月频换成日频。
MDD 按日频全序列计算（月频会低估月内回撤）。
v2 (2026-08-25 17:40): bar 改用【复权价】(adj 折算 OHLC) —— 修正未复权 close 导致策略收益
不含分红、与复权 ew 基准口径不一致的 bug（core 80% 金融高分红持仓被系统性低估）。
"""
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
VARIANTS = ["core", "core_finex", "core_finex_band"]
CAPITAL = 1_000_000.0


class WeightsStrategy(StrategyTemplate):
    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]

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
        self.rebalance_portfolio(bars)


def mdd_of(nav_seq: list[float]) -> float:
    """标准 MDD = (peak - trough) / peak"""
    peak, mdd = nav_seq[0], 0.0
    for v in nav_seq:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def run(variant: str, weights_by_dt: dict, bars: dict) -> dict:
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001,
                          annual_periods=252)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {"weights_by_dt": weights_by_dt})
    engine.add_strategy(strategy)
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)

    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(d for d in bal if d >= "2021-06-01")
    nav = [{"date": d, "nav": bal[d]} for d in dts]
    total = bal[dts[-1]] / bal[dts[0]] - 1.0
    yrs = len(dts) / 252.0
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1.0
    mdd = mdd_of([bal[d] for d in dts])   # 日频全序列回撤
    return {"name": variant, "total": total, "ann": ann, "mdd": mdd,
            "nav": nav, "n_days": len(dts),
            "mdd_vnpy": stats.get("max_ddpercent", 0) / 100.0}


def main():
    # 日频价格（v2: 复权口径，adj 折算 OHLC，与 ew 基准 daily_return 对齐）
    px = json.load(open("_bt_daily_px.json", encoding="utf-8"))
    bars = {}
    n_adj = 0
    for tk, d in px.items():
        mm = {}
        for dt, r in d.items():
            c, a = r.get("close"), r.get("adj")
            if c and a and c > 0 and a > 0 and dt >= "2021-05-01":
                ratio = a / c
                mm[dt] = BarData(tk, dt,
                                 (r.get("open") or c) * ratio,
                                 (r.get("high") or c) * ratio,
                                 (r.get("low") or c) * ratio,
                                 a)
                n_adj += 1
        if mm:
            bars[tk] = mm
    print(f"复权 bar: {len(bars)} 只 | {n_adj} 条（adj 折算 OHLC）")
    all_dates = sorted({dt for m in bars.values() for dt in m})
    print(f"日频 bars: {len(bars)} 只 | 交易日 {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)})")

    # 权重 → 调仓触发日（≤ as_of 的最近交易日）
    weights = json.load(open("_bt_band_results.json", encoding="utf-8"))["weights"]
    w_by_dt = {}
    for v in VARIANTS:
        wd = {}
        for month, asof in PIT_DATES:
            trig = max(d for d in all_dates if d <= asof)
            wd[trig] = weights[v][month]
        w_by_dt[v] = wd
    for trig in sorted(w_by_dt["core"]):
        print(f"  调仓触发日 {trig}")

    # 基准：中证全指日频
    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dts = sorted(d for d in idx if d >= "2021-06-01")
    base = idx[idx_dts[0]]["close"]
    idx_nav = {d: idx[d]["close"] / base for d in idx_dts}
    idx_mdd = mdd_of([idx_nav[d] for d in idx_dts])
    idx_total = idx_nav[idx_dts[-1]] - 1.0
    idx_ann = (1 + idx_total) ** (252 / len(idx_dts)) - 1

    # 三变体日频回测
    results = {}
    for v in VARIANTS:
        r = run(v, w_by_dt[v], bars)
        r["excess_idx"] = r["total"] - idx_total
        results[v] = r
        print(f"\n{v}:")
        print(f"  总收益 {r['total']:+.2%} | 年化 {r['ann']:+.2%} | "
              f"MDD(日频) {r['mdd']:.2%} | MDD(vnpy) {r['mdd_vnpy']:.2%} | "
              f"超额(中证全指) {r['excess_idx']:+.2%} | {r['n_days']} 个交易日")

    print(f"\n中证全指(日频): 总收益 {idx_total:+.2%} | 年化 {idx_ann:+.2%} | "
          f"MDD(日频) {idx_mdd:.2%}")

    out = {"results": results, "idx": {"total": idx_total, "ann": idx_ann,
                                       "mdd": idx_mdd, "nav": idx_nav},
           "periods": PIT_DATES}
    json.dump(out, open("_bt_daily_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_daily_results.json")


if __name__ == "__main__":
    main()
