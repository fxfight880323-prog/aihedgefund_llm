"""growth_loop（GOAL→HOOK→LOOP）单模型 · 点时全市场 5 年回测。

诚实边界（先声明）：
  1. LOOP 层（L1-L7 LLM 深研）无法诚实回测——GLM-4 训练数据含未来
     信息。本回测只用 HOOK 层（确定性数值规则 H1/H2/H6）+ L8 信念的
     确定性代理（hook 强度 × 增速）。诊断里必须标注这一差距。
  2. H3（连续 BEAT）无点时盈利预测数据 → 诚实 abstain。
  3. universe = 每期全市场点时筛选 top-100 增速候选（backtest_pit 的
     缓存，当前市值>50 亿过滤，无任何行业偏好——"排除已知行业"）。

组合规则（对齐 config/funds/growth_demo.yaml）：
  conviction_weighted，gross 1.0，单票上限 8%（剧本 GOAL: 8% at cost）
  剧本"A 上限 3"是 LOOP 深研的 LLM 成本约束，不是组合规则 → 回测取
  全部触发 hook 的标的，按信念加权。
  无 hook 触发 = 空仓（剧本：空仓也是决策）。

Run:
    python examples/backtest_growth_loop.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import (BacktestingEngine, BarData,
                                 _month_span)
from src.backtest.strategy import (StrategyTemplate,
                                   avail_financials)
from src.core.models import Signal
from src.signals.hooks import evaluate_hooks
from src.data.mx_data_client import parse_cn_number

CAPITAL = 1_000_000
PER_NAME_CAP = 0.08          # 剧本 GOAL: 8% at cost
GROSS_TARGET = 1.0

SEL_FILE = "_bt_pit_selection.json"
FIN_FILE = "_bt_pit_financials.json"
PRICES_FILE = "_bt_pit_prices.json"
WARMUP_FILE = "_bt_pit_warmup.json"
BENCH_FILE = "_bt_benchmark.json"
NAV_FILE = "_bt_gl_nav.json"

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]


# ===========================================================================
# HOOK 筛选（点时确定性层）
# ===========================================================================

def series_of(periods: dict[str, dict]) -> tuple[list[float], list[float]]:
    """period-matched 营收 YoY（newest-first）与毛利率（newest-first）。"""
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
    """距过去 12 个月最高收盘的回撤（0-1）。"""
    closes = [(mk, v) for mk, v in sorted(monthly.items())
              if mk <= dt and v and v > 0]
    if len(closes) < 6:            # 至少半年历史
        return None
    window = closes[-13:]          # ~12 个月
    high = max(v for _, v in window)
    cur = window[-1][1]
    if high <= 0:
        return None
    return max(0.0, 1.0 - cur / high)


def conviction_proxy(n_hooks: int, hook_ids: list[str],
                     latest_yoy: float) -> float:
    """L8 信念的确定性代理（HOOK 层无法做 L1-L7 深研的减分）。"""
    base = 0.5 + 0.2 * (n_hooks - 1)
    growth_boost = 0.3 * min(max(latest_yoy, 0.0), 1.5) / 1.5
    h1_boost = 0.05 if "H1" in hook_ids else 0.0   # 剧本最高优先 hook
    return min(1.0, base + growth_boost + h1_boost)


def build_signals(fin_at: dict, candidates: list[tuple], prices_all: dict,
                   min_holdings: int = 20
                   ) -> tuple[list[Signal], dict]:
    """对当期候选跑 HOOK 筛选 → 信念信号 + 诊断明细。

    hook 触发不足 min_holdings 时，从 B 观察名单（数据正常但无 hook，
    剧本 B = 观察不建仓；此处按用户要求以低信念补足持仓下限）
    按最新增速排名补位。
    """
    signals: list[Signal] = []
    detail: dict[str, dict] = {}
    b_pool: list[tuple[float, str, str, str]] = []   # (yoy, tk, name, sw1)
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
            reason = (f"hooks={'+'.join(hooks)} yoy={yoy[0]:.0%}"
                      + (f" dd={dd:.0%}" if dd is not None else ""))
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=conv, reasoning=reason))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": hooks,
                          "yoy": yoy[0], "dd": dd, "conviction": conv,
                          "tier": "A"}
        else:
            b_pool.append((yoy[0], tk, name, sw1))

    # B 补位（低信念 0.30：低于任何 hook 触发组合的信念）
    if len(signals) < min_holdings:
        b_pool.sort(key=lambda x: -x[0])
        for yoy0, tk, name, sw1 in b_pool[:min_holdings - len(signals)]:
            conv = 0.30
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=conv,
                reasoning=f"B-fill（无 hook）yoy={yoy0:.0%}"))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": [],
                          "yoy": yoy0, "dd": None, "conviction": conv,
                          "tier": "B"}
    signals.sort(key=lambda s: -s.value)
    return signals, detail


CUR_DT = [""]


# ===========================================================================
# 权重策略（预计算权重 → 引擎执行）
# ===========================================================================

class WeightsStrategy(StrategyTemplate):
    """按预计算的逐期权重调仓（conviction_weighted + 8% 单票上限）。"""

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
    """conviction_weighted（gross 1.0）+ 单票 8% 上限（超限留现金）。"""
    from src.portfolio.construction import ConvictionWeightedBlend
    blender = ConvictionWeightedBlend()
    result = blender.blend(signals, {"growth_loop": 1.0},
                           gross_target=GROSS_TARGET)
    capped = {}
    for tk, w in result.weights.items():
        if w > 0:
            capped[tk] = min(w, PER_NAME_CAP)
    return capped


# ===========================================================================
# 主流程
# ===========================================================================

def main():
    print("=" * 78)
    print("  growth_loop（GOAL→HOOK→LOOP）· 点时全市场 5 年回测")
    print("  HOOK 层确定性回测 | universe=全市场点时 top-100（无行业偏好）")
    print("  半年度调仓 | conviction_weighted + 单票 8% | 成本 5bp+10bp")
    print("=" * 78)

    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    # ---- 逐期 HOOK 筛选 → 权重 ----
    weights_by_dt, detail_by_dt = {}, {}
    print("\n① 逐期 HOOK 筛选（H1 加速 / H2 毛利率拐点 / H6 深回撤高增长）")
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
        hook_stat: dict[str, int] = {}
        for d in detail.values():
            if d["tier"] == "A":
                for h in d["hooks"]:
                    hook_stat[h] = hook_stat.get(h, 0) + 1
        n_a = sum(1 for d in detail.values() if d["tier"] == "A")
        print(f"  [{month}] 候选 {len(sel[month]['candidates'])} → "
              f"hook 触发 {n_a}（B 补位 {len(signals) - n_a}）→ "
              f"持仓 {len(weights)} 只 | hooks: {hook_stat} | gross "
              f"{sum(weights.values()):.0%}")

    # ---- vnpy 引擎执行 ----
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

    # ---- 诊断 ----
    print("\n④ 逐期诊断（持仓明细 × 期收益）")
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
        for name, sw1, hooks, w, tier in h["names"][:8]:
            hs = "+".join(hooks) if hooks else "B补位"
            print(f"     {name:8s} {sw1:6s} {tier} {hs:8s} {w:.1%}")

    # hook 频率与持仓结构诊断
    print("\n⑤ 结构诊断")
    all_hooks: dict[str, int] = {}
    gross_list = []
    for month, detail in detail_by_dt.items():
        for d in detail.values():
            for hk in d["hooks"]:
                all_hooks[hk] = all_hooks.get(hk, 0) + 1
        gross_list.append(sum(weights_by_dt[month].values()))
    print(f"  hook 触发分布（全部候选）: {all_hooks}")
    print(f"  期均 gross: {sum(gross_list)/len(gross_list):.0%}（单票 8% "
          f"上限 + 少量触发 → 自然留现金）")
    nav = [{"month": r["dt"], "nav": r["balance"]}
           for r in daily if r["dt"] in bench]
    json.dump(nav, open(NAV_FILE, "w", encoding="utf-8"))
    print(f"\n  NAV → {NAV_FILE}")


if __name__ == "__main__":
    main()
