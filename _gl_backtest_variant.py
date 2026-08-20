# -*- coding: utf-8 -*-
"""行业聚合层实验 · 阶段4：GL 回测（参数化三方案）。

复用 examples/backtest_growth_loop.py 的 HOOK 筛选 + 权重 + 引擎逻辑，
参数化 selection 文件与输出 NAV 文件。数据（财务/价格/预热）三方案
共用 _bt_exp_* 缓存，保证口径一致。

用法: python _gl_backtest_variant.py <mode>   # mode = baseline|plan2|plan1
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import (BacktestingEngine, BarData, _month_span)
from src.backtest.strategy import avail_financials
from src.core.models import Signal
from src.signals.hooks import evaluate_hooks

CAPITAL = 1_000_000
PER_NAME_CAP = 0.08
GROSS_TARGET = 1.0

FIN_FILE = "_bt_exp_financials.json"
PRICES_FILE = "_bt_exp_prices.json"
WARMUP_FILE = "_bt_exp_warmup.json"
BENCH_FILE = "_bt_benchmark.json"

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]

CUR_DT = [""]


def series_of(periods: dict[str, dict]) -> tuple[list[float], list[float]]:
    rev_by_qp: dict[tuple, float] = {}
    for pk, m in periods.items():
        parts = pk.split("-")
        if len(parts) != 2:
            continue
        try:
            y, q = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if m.get("revenue"):
            rev_by_qp.setdefault((y, q), m["revenue"])
    yoy = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            yoy.append(v / prev - 1.0)
    gm = []
    for pk in sorted(periods.keys(),
                     key=lambda p: (int(p[:4]), int(p[5:])), reverse=True):
        v = periods[pk].get("gross_margin")
        if v is not None:
            gm.append(v)
    return yoy, gm


def drawdown_1y(monthly: dict[str, float], dt: str) -> float | None:
    closes = [(mk, v) for mk, v in sorted(monthly.items())
              if mk <= dt and v and v > 0]
    if len(closes) < 6:
        return None
    window = closes[-13:]
    high = max(v for _, v in window)
    cur = window[-1][1]
    if high <= 0:
        return None
    return max(0.0, 1.0 - cur / high)


def conviction_proxy(n_hooks: int, hook_ids: list[str],
                     latest_yoy: float) -> float:
    base = 0.5 + 0.2 * (n_hooks - 1)
    growth_boost = 0.3 * min(max(latest_yoy, 0.0), 1.5) / 1.5
    h1_boost = 0.05 if "H1" in hook_ids else 0.0
    return min(1.0, base + growth_boost + h1_boost)


def build_signals(fin_at: dict, candidates: list[tuple], prices_all: dict,
                  min_holdings: int = 20):
    signals: list[Signal] = []
    detail: dict[str, dict] = {}
    b_pool: list[tuple[float, str, str, str]] = []
    for tk, name, sw1 in candidates:
        periods = fin_at.get(tk)
        if not periods:
            continue
        yoy, gm = series_of(periods)
        if not yoy:
            continue
        dd = drawdown_1y(prices_all.get(tk, {}), CUR_DT[0])
        res = evaluate_hooks(yoy, gm, dd, beats=None)
        hooks = [h["id"] for h in res["tripped"]]
        if hooks:
            conv = conviction_proxy(len(hooks), hooks, yoy[0])
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=conv,
                reasoning=f"hooks={'+'.join(hooks)} yoy={yoy[0]:.0%}"
                          + (f" dd={dd:.0%}" if dd is not None else "")))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": hooks,
                          "yoy": yoy[0], "dd": dd, "conviction": conv,
                          "tier": "A"}
        else:
            b_pool.append((yoy[0], tk, name, sw1))
    if len(signals) < min_holdings:
        b_pool.sort(key=lambda x: -x[0])
        for yoy0, tk, name, sw1 in b_pool[:min_holdings - len(signals)]:
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=0.30,
                reasoning=f"B-fill（无 hook）yoy={yoy0:.0%}"))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": [],
                          "yoy": yoy0, "dd": None, "conviction": 0.30,
                          "tier": "B"}
    signals.sort(key=lambda s: -s.value)
    return signals, detail


from src.backtest.strategy import StrategyTemplate  # noqa: E402


class WeightsStrategy(StrategyTemplate):
    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
        self.detail_by_dt = setting.get("detail_by_dt", {})
        self.history: list[dict] = []

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
        detail = self.detail_by_dt.get(dt, {})
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "weights": weights,
            "names": [(detail[t]["name"], detail[t]["sw1"],
                       detail[t]["hooks"], w, detail[t].get("tier", "A"))
                      for t, w in sorted(weights.items(),
                                         key=lambda x: -x[1])
                      if t in detail],
        })


def blend_weights(signals: list[Signal]) -> dict[str, float]:
    from src.portfolio.construction import ConvictionWeightedBlend
    blender = ConvictionWeightedBlend()
    result = blender.blend(signals, {"growth_loop": 1.0},
                           gross_target=GROSS_TARGET)
    capped = {}
    for tk, w in result.weights.items():
        if w > 0:
            capped[tk] = min(w, PER_NAME_CAP)
    return capped


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    sel_file = f"_bt_sel_{mode}.json"
    nav_file = f"_bt_gl_{mode}_nav.json"

    sel = json.loads(open(sel_file, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    weights_by_dt, detail_by_dt = {}, {}
    print(f"\n① [{mode}] 逐期 HOOK 筛选")
    for month in REBALANCES:
        if month not in sel:
            continue
        as_of = sel[month]["as_of"]
        fin_at = avail_financials(financials, as_of)
        CUR_DT[0] = month
        signals, detail = build_signals(fin_at, sel[month]["candidates"],
                                        prices_all)
        weights = blend_weights(signals)
        weights_by_dt[month] = weights
        detail_by_dt[month] = detail
        n_a = sum(1 for d in detail.values() if d["tier"] == "A")
        hook_stat: dict[str, int] = {}
        for d in detail.values():
            if d["tier"] == "A":
                for h in d["hooks"]:
                    hook_stat[h] = hook_stat.get(h, 0) + 1
        print(f"  [{month}] 候选 {len(sel[month]['candidates'])} → "
              f"hook {n_a}（B 补 {len(signals)-n_a}）→ 持仓 "
              f"{len(weights)} | {hook_stat}")

    bars = {tk: {mk: BarData(tk, mk, px, px, px, px)
                 for mk, px in m.items() if px and px > 0
                 and mk >= "2021-06"}
            for tk, m in prices_all.items()}
    bars = {tk: m for tk, m in bars.items() if m}
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {
        "weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt})
    engine.add_strategy(strategy)

    print("② 引擎回测…")
    engine.run_backtesting()
    daily = engine.calculate_result()
    engine.calculate_statistics(daily)
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())

    r = bal[dts[-1]] / CAPITAL - 1
    br = bench[dts[-1]] / bench[dts[0]] - 1
    yrs = _month_span(dts[0], dts[-1]) / 12
    print(f"\n③ [{mode}] 总收益 {r:+.1%}（{bal[dts[-1]]:,.0f} 元）| "
          f"中证全指 {br:+.1%} | 超额 {r-br:+.1%} | "
          f"年化 {((1+r)**(1/yrs)-1):+.1%} vs {((1+br)**(1/yrs)-1):+.1%}")

    print("④ 逐期收益")
    hist_dts = [h["dt"] for h in strategy.history]
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        if mk not in bal:
            continue
        nxt = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
        end_mk = nxt if nxt in bal else dts[-1]
        ret = bal[end_mk] / bal[mk] - 1 if end_mk in bal else 0.0
        brk = (bench[end_mk[:7]] / bench[mk[:7]] - 1
               if bench.get(mk[:7]) and bench.get(end_mk[:7]) else None)
        ex = f" | 基准 {brk:+.1%}" if brk is not None else ""
        opt = [t for t in h["weights"]
               if t.split('.')[0] in
               {'300308','300502','300394','002281','688313','688668',
                '603083','300570'}]
        print(f"  [{mk}] {ret:+.1%}{ex}（{h['n']} 只）"
              + (f" | 光模块持仓 {opt}" if opt else ""))

    nav = [{"month": r_["dt"], "nav": r_["balance"]}
           for r_ in daily if r_["dt"] in bench]
    json.dump(nav, open(nav_file, "w", encoding="utf-8"))
    json.dump({"weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt,
               "history": strategy.history},
              open(f"_bt_gl_{mode}_detail.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"\n→ {nav_file} + _bt_gl_{mode}_detail.json")


if __name__ == "__main__":
    main()
