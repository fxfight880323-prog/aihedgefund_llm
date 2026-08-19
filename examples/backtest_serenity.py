"""Serenity（供应链卡点猎手）方法论 · 点时 5 年回测。

把 serenity-skill 的 scorecard 八因子映射为点时可计算代理
（诚实标注：这是量化近似，不是 skill 本身的定性研究流程）：

  Serenity 因子            点时代理（财报 + 价格）
  ─────────────────────────────────────────────────────────
  demand_inflection (15)   营收 YoY 水平 × 加速度
  chokepoint_severity (15) 毛利率环比变化（扩supply收紧=定价权报表指纹）
  evidence_quality (15)    数据完整性（可得的报告期数）
  supplier_concentration(12) 行业定价权=行业内高毛利成员占比
  expansion_difficulty (12) 毛利率持续性（近 4 期最低值仍在抬升）
  valuation_disconnect (11) 深回撤 × 基本面未坏（反向动量）
  architecture_coupling(10) 毛利率水平（架构位置代理）
  catalyst_timing (10)     加速新鲜度（刚刚拐头 > 持续高位）

  罚项（×2/分）：
  hype_risk                1 年涨幅（低点至今 >100% → 罚）
  cyclicality              毛利率波动率（std > 8 → 罚）

层先于公司（skill 核心原则）：行业层分 = 该层 top-3 成员原始因子分
均值 → 层倾斜系数（top1 层 ×1.3 / 2nd ×1.2 / 3rd ×1.1）作用于公司
最终分的权重。

universe = 全市场点时 top-100 增速候选（backtest_pit 缓存，无行业
偏好）。持仓 = scorecard 前 20，分数比例权重，单票 8% 上限。
半年度调仓，vnpy 引擎（N 月末下单 N+1 月成交）。

Run:
    python examples/backtest_serenity.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import BacktestingEngine, BarData, _month_span
from src.backtest.strategy import StrategyTemplate, avail_financials
from src.backtest.strategy import _closes_upto

CAPITAL = 1_000_000
TOP_K = 20
PER_NAME_CAP = 0.08

SEL_FILE = "_bt_pit_selection.json"
FIN_FILE = "_bt_pit_financials.json"
PRICES_FILE = "_bt_pit_prices.json"
WARMUP_FILE = "_bt_pit_warmup.json"
BENCH_FILE = "_bt_benchmark.json"
NAV_FILE = "_bt_serenity_nav.json"

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]

WEIGHTS = {
    "demand_inflection": 15, "architecture_coupling": 10,
    "chokepoint_severity": 15, "supplier_concentration": 12,
    "expansion_difficulty": 12, "evidence_quality": 15,
    "valuation_disconnect": 11, "catalyst_timing": 10,
}


def series_of(periods: dict) -> tuple[list[float], list[float]]:
    rev_by_qp = {}
    for pk, m in periods.items():
        try:
            y, q = int(pk[:4]), int(pk[5])
        except (ValueError, IndexError):
            continue
        if m.get("revenue"):
            rev_by_qp.setdefault((y, q), m["revenue"])
    yoy = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            yoy.append(v / prev - 1.0)
    gm = [periods[pk]["gross_margin"] for pk in sorted(
        periods.keys(), key=lambda p: (int(p[:4]), int(p[5])),
        reverse=True) if periods[pk].get("gross_margin") is not None]
    return yoy, gm


def _rate(v, stops) -> int:
    """按阈值表打 0-5 分（stops 从高到低）。"""
    for i, s in enumerate(stops):
        if v >= s:
            return 5 - i
    return max(0, 5 - len(stops))


def serenity_score(yoy, gm, dd, runup, ind_gm_breadth, n_periods):
    """单标的 scorecard（返回 因子分明细 + 最终分）。"""
    g0 = yoy[0] if yoy else 0.0
    accel = len(yoy) >= 2 and yoy[0] > yoy[1]
    accel2 = len(yoy) >= 3 and yoy[0] > yoy[1] > yoy[2]
    gm_now = gm[0] if gm else None
    gm_prev = gm[1] if len(gm) > 1 else None
    gm_chg = (gm_now - gm_prev) if (gm_now is not None
                                     and gm_prev is not None) else 0.0
    gm_floor = min(gm[:4]) if gm else 0.0
    gm_std = (sum((x - sum(gm) / len(gm)) ** 2 for x in gm) / len(gm)
              ** 0.5) if len(gm) >= 3 else 0.0

    factors = {
        "demand_inflection": _rate(g0, [0.9, 0.6, 0.4, 0.2, 0.1])
        + (1 if accel2 else 0),
        "architecture_coupling": _rate(gm_now or 0, [50, 35, 25, 15, 8]),
        "chokepoint_severity": _rate(gm_chg, [12, 8, 4, 1.5, 0.3]),
        "supplier_concentration": _rate(ind_gm_breadth,
                                        [0.8, 0.6, 0.45, 0.3, 0.15]),
        "expansion_difficulty": _rate(gm_floor, [45, 32, 22, 14, 8]),
        "evidence_quality": _rate(n_periods, [7, 5, 4, 3, 2]),
        # 深回撤 + 基本面未坏 = 估值断层（反向动量）
        "valuation_disconnect": (_rate(dd or 0, [0.45, 0.35, 0.25, 0.15, 0.08])
                                 if (dd or 0) >= 0.15 and g0 >= 0.15 else 1),
        "catalyst_timing": 5 if accel2 else (3 if accel else 1),
    }
    raw = sum(min(factors[k], 5) / 5 * w for k, w in WEIGHTS.items())
    penalties = {"hype_risk": _rate(runup or 0, [2.0, 1.5, 1.0, 0.6, 0.3]),
                 "cyclicality": _rate(gm_std, [12, 8, 5, 3, 1.5])}
    pen = sum(penalties.values()) * 2.0
    return max(0.0, min(100.0, raw - pen)), raw, factors, penalties


def run_1y_stats(monthly: dict, dt: str):
    closes = _closes_upto(monthly, dt)
    if len(closes) < 6:
        return None, None
    window = closes[-13:]
    high, low = max(window), min(window)
    cur = window[-1]
    dd = max(0.0, 1 - cur / high) if high > 0 else 0.0
    runup = (cur / low - 1) if low > 0 else 0.0
    return dd, runup


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
            "names": sorted(
                (detail[t]["name"], detail[t]["sw1"],
                 round(detail[t]["final"], 1), w)
                for t, w in weights.items() if t in detail),
        })


def main():
    print("=" * 78)
    print("  Serenity（供应链卡点猎手）· 点时 5 年回测")
    print("  八因子 scorecard 量化代理 | 层先于公司 | top-20 | 单票 8%")
    print("  半年度调仓 | vnpy 引擎 | 成本 5bp+10bp")
    print("=" * 78)

    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    weights_by_dt, detail_by_dt = {}, {}
    print("\n① 逐期 Serenity scorecard")
    for month in REBALANCES:
        if month not in sel:
            continue
        as_of = sel[month]["as_of"]
        fin_at = avail_financials(financials, as_of)
        cands = sel[month]["candidates"]

        # 先算每标的基础数据
        stock_data = {}
        gm_by_ind: dict[str, list[float]] = {}
        for tk, name, sw1 in cands:
            periods = fin_at.get(tk)
            if not periods:
                continue
            yoy, gm = series_of(periods)
            if not yoy or not gm:
                continue
            dd, runup = run_1y_stats(prices_all.get(tk, {}), month)
            stock_data[tk] = (name, sw1, yoy, gm, dd, runup,
                              len(periods))
            if gm[0] is not None:
                gm_by_ind.setdefault(sw1, []).append(gm[0])
        # 行业定价权广度（高毛利成员占比）
        gm_breadth = {ind: sum(1 for g in gs if g >= 30) / len(gs)
                      for ind, gs in gm_by_ind.items() if gs}

        scored = {}
        for tk, (name, sw1, yoy, gm, dd, runup, np_) in stock_data.items():
            final, raw, factors, pens = serenity_score(
                yoy, gm, dd, runup, gm_breadth.get(sw1, 0.0), np_)
            scored[tk] = {"name": name, "sw1": sw1, "final": final,
                          "raw": raw, "factors": factors, "pens": pens,
                          "yoy": yoy[0]}

        # ---- 层先于公司：行业层分 = top-3 成员原始分均值 → 倾斜 ----
        by_ind: dict[str, list[float]] = {}
        for tk, s in scored.items():
            by_ind.setdefault(s["sw1"], []).append(s["raw"])
        layer_score = {ind: sum(sorted(rs, reverse=True)[:3]) / min(3, len(rs))
                       for ind, rs in by_ind.items()}
        layer_rank = sorted(layer_score.items(), key=lambda x: -x[1])
        tilt = {}
        for i, (ind, _) in enumerate(layer_rank):
            tilt[ind] = 1.3 if i == 0 else 1.2 if i == 1 else \
                1.1 if i == 2 else 1.0
        for tk, s in scored.items():
            s["final_tilted"] = s["final"] * tilt[s["sw1"]]

        # ---- top-20 → 分数比例权重 + 8% 上限 ----
        ranked = sorted(scored.items(), key=lambda x: -x[1]["final_tilted"])
        top = ranked[:TOP_K]
        total = sum(s["final_tilted"] for _, s in top) or 1.0
        weights = {}
        for tk, s in top:
            weights[tk] = min(s["final_tilted"] / total, PER_NAME_CAP)
        weights_by_dt[month] = weights
        detail_by_dt[month] = scored
        top3_layers = ", ".join(f"{ind}({sc:.0f})"
                                for ind, sc in layer_rank[:3])
        print(f"  [{month}] 评分 {len(scored)} 只 → 持仓 {len(weights)} | "
              f"层 top: {top3_layers} | gross {sum(weights.values()):.0%} | "
              f"榜首 " + ", ".join(
                  f"{s['name']}{s['final_tilted']:.0f}"
                  for _, s in ranked[:3]))

    # ---- 引擎 ----
    bars = {tk: {mk: BarData(tk, mk, px, px, px, px)
                 for mk, px in m.items()
                 if px and px > 0 and mk >= "2021-06"}
            for tk, m in prices_all.items()}
    bars = {tk: m for tk, m in bars.items() if m}
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {
        "weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt})
    engine.add_strategy(strategy)

    print("\n② 引擎回测…")
    engine.run_backtesting()

    print("\n③ 结算…")
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily)
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())
    if dts[0] in bench and dts[-1] in bench:
        r = bal[dts[-1]] / CAPITAL - 1
        br = bench[dts[-1]] / bench[dts[0]] - 1
        yrs = _month_span(dts[0], dts[-1]) / 12
        print(f"\n  基准: 策略 {r:+.1%} vs 中证全指 {br:+.1%} | "
              f"超额 {r - br:+.1%} | 年化 {((1+r)**(1/yrs)-1):+.1%}"
              f" vs {((1+br)**(1/yrs)-1):+.1%}")

    # ---- 归因 ----
    print("\n④ 逐期归因")
    hist_dts = [h["dt"] for h in strategy.history]
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        if mk not in bal:
            continue
        nxt = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
        end_mk = nxt if nxt in bal else dts[-1]
        ret = bal[end_mk] / bal[mk] - 1 if end_mk in bal else 0.0
        br = (bench[end_mk] / bench[mk] - 1
              if bench.get(mk) and bench.get(end_mk) else None)
        ex = f" | 基准 {br:+.1%} | 超额 {ret - br:+.1%}" if br is not None else ""
        print(f"\n  ▶ {mk}: {ret:+.1%}{ex}（{h['n']} 只，gross "
              f"{sum(h['weights'].values()):.0%}）")
        for name, sw1, score, w in h["names"][:6]:
            print(f"     {name:8s} {sw1:6s} 分{score:5.1f} {w:.1%}")

    # ---- 个股贡献 ----
    print("\n⑤ 个股贡献 top10/bottom5")
    contrib: dict[str, float] = {}
    for dt, daily_res in engine.daily_results.items():
        for sym, c in daily_res.contracts.items():
            if c.net_pnl:
                contrib[sym] = contrib.get(sym, 0.0) + c.net_pnl
    names = {t: d["name"] for m in detail_by_dt.values()
             for t, d in m.items()}
    inds = {t: d["sw1"] for m in detail_by_dt.values()
            for t, d in m.items()}
    ranked = sorted(contrib.items(), key=lambda x: -x[1])
    for sym, pnl in ranked[:10]:
        print(f"  + {names.get(sym, sym):8s} {inds.get(sym, ''):6s} "
              f"¥{pnl:>+9,.0f}")
    for sym, pnl in ranked[-5:]:
        print(f"  - {names.get(sym, sym):8s} {inds.get(sym, ''):6s} "
              f"¥{pnl:>+9,.0f}")
    wins = [v for _, v in ranked if v > 0]
    losses = [v for _, v in ranked if v < 0]
    if wins and losses:
        print(f"  盈亏结构: {len(wins)} 赢/{len(losses)} 亏 | "
              f"盈亏比 {sum(wins) / abs(sum(losses)):.2f}")

    nav = [{"month": r["dt"], "nav": r["balance"]}
           for r in daily if r["dt"] in bench]
    json.dump(nav, open(NAV_FILE, "w", encoding="utf-8"))
    print(f"\n  NAV → {NAV_FILE}")


if __name__ == "__main__":
    main()
