# -*- coding: utf-8 -*-
"""IRR 门槛实验：个股 IRR ≥ GOAL(target_return=15%) 才允许投资。

目标：回答"选股时加一道 IRR ≥ goal 的门，5 年回测效果会怎样"。
口径（诚实标注，全部 point-in-time，无未来数据）：

  1. IRR 定义（年化，3 年持有视角，与 GOAL 层 horizon_years=3 对齐）：
       g     = 最新报告期营收 YoY（与 HOOK 层同一 PIT 序列；g 截断 [-50%, +100%]）
       PS₀   = as_of 月末价 / TTM 营收（TTM = 最新累计营收 + 上年年报 - 上年同季）
       PS_med = as_of 前 36 个月内每月 PS 的中位数（每月 PS 均用该月已披露
               报告期计算，严格 PIT）
       IRR   = ((1+g)^3 × (PS_med / PS₀))^(1/3) - 1
       含义：若未来 3 年营收按 g 增长、估值倍数回归到自身历史中位数，
       年化回报 = IRR。估值贵的（PS₀ >> PS_med）会被惩罚，便宜的会被奖励。
  2. 门槛：GOAL.target_return = 0.15（config/strategies/growth_loop.yaml）。
     irr15 = IRR ≥ 15%；irr20 = IRR ≥ 20%（敏感性）。
  3. 加门位置：候选 → [IRR 门] → HOOK 筛选 → A 层信念 / B 补位 →
     conviction 加权（单票 8% 上限）。B 补位池也过 IRR 门（否则等于绕门）。
  4. PS 历史不足（<6 个有效月）→ IRR 不可算 → 加门模式下视为不通过
     （保守：无法证明 IRR ≥ goal 就不投），并在诊断中单列计数。
  5. baseline 模式不加门，用于复现 _bt_gl_nav.json（860,178）校验口径一致。

用法: python _gl_irr_variant.py <mode>   # baseline | irr15 | irr20
"""
from __future__ import annotations

import calendar
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import (BacktestingEngine, BarData, _month_span)
from src.backtest.strategy import StrategyTemplate, avail_financials
from src.core.models import Signal
from src.signals.hooks import evaluate_hooks

CAPITAL = 1_000_000
PER_NAME_CAP = 0.08
MIN_HOLDINGS = 20
HORIZON = 3
G_CAP = 1.0
G_FLOOR = -0.5
PS_MIN_POINTS = 6
PS_LOOKBACK_MONTHS = 36

SEL_FILE = "_bt_pit_selection.json"
FIN_FILE = "_bt_pit_financials.json"
PRICES_FILE = "_bt_pit_prices.json"
WARMUP_FILE = "_bt_pit_warmup.json"
BENCH_FILE = "_bt_benchmark.json"
BASELINE_NAV_FILE = "_bt_gl_nav.json"

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]

CUR_DT = [""]


# ---------------------------------------------------------------------------
# 指标计算（与 GL 回测完全一致）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# IRR 计算
# ---------------------------------------------------------------------------

def ttm_revenue(pit_periods: dict) -> float | None:
    """trailing-12M 营收（基于 PIT 报告期集合；报表为年内累计值）。

    TTM = 最新累计营收 + (上年年报 - 上年同季累计)  ← 标准 TTM 拆补
    若上年年报/同季缺失 → 按报告期跨度年化（Q1×4, H1×2, Q3×4/3, 年报×1）。
    """
    qp: dict[tuple[int, int], float] = {}
    for pk, m in pit_periods.items():
        parts = pk.split("-")
        if len(parts) != 2:
            continue
        try:
            y, q = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if m.get("revenue"):
            qp.setdefault((y, q), m["revenue"])
    if not qp:
        return None
    (y, q), rev = max(qp.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    prev_yq = qp.get((y - 1, q))
    prev_fy = qp.get((y - 1, 4))
    if prev_yq and prev_fy and prev_fy > prev_yq:
        return rev + (prev_fy - prev_yq)
    mult = {1: 4.0, 2: 2.0, 3: 4.0 / 3.0, 4: 1.0}.get(q)
    return rev * mult if mult else None


def month_end_asof(month: str) -> str:
    y, m = int(month[:4]), int(month[5:])
    return f"{month}-{calendar.monthrange(y, m)[1]}"


def iter_prior_months(month: str, n: int) -> list[str]:
    y, m = int(month[:4]), int(month[5:])
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}-{m:02d}")
    return out


def compute_irr(financials: dict, prices_all: dict, tk: str,
                month: str, as_of: str) -> dict | None:
    """个股 IRR（PIT）。返回 {irr, g, ps0, ps_med, px, rev, n_ps} 或 None。"""
    pit = avail_financials(financials, as_of).get(tk)
    if not pit:
        return None
    yoy, _ = series_of(pit)
    if not yoy:
        return None
    g = min(max(yoy[0], G_FLOOR), G_CAP)
    px = prices_all.get(tk, {}).get(month)
    if not px or px <= 0:
        return None
    rev = ttm_revenue(pit)
    if not rev or rev <= 0:
        return None
    ps0 = px / rev

    # PS 历史中位数（严格 PIT：每月用该月末已披露报告期算 TTM）
    ps_list: list[float] = []
    for m in iter_prior_months(month, PS_LOOKBACK_MONTHS):
        pm = prices_all.get(tk, {}).get(m)
        if not pm or pm <= 0:
            continue
        rev_m = ttm_revenue(avail_financials(
            financials, month_end_asof(m)).get(tk, {}))
        if rev_m and rev_m > 0:
            ps_list.append(pm / rev_m)
    if len(ps_list) < PS_MIN_POINTS:
        return None
    ps_med = statistics.median(ps_list)
    irr = (1.0 + g) ** HORIZON * (ps_med / ps0)
    irr = irr ** (1.0 / HORIZON) - 1.0
    return {"irr": irr, "g": g, "ps0": ps0, "ps_med": ps_med,
            "px": px, "rev": rev, "n_ps": len(ps_list)}


# ---------------------------------------------------------------------------
# 信号构建（baseline 无 IRR 门 / irr15 / irr20 加门）
# ---------------------------------------------------------------------------

def build_signals(fin_at: dict, candidates: list[tuple], prices_all: dict,
                  irr_at: dict | None, goal: float | None,
                  reject_uncomputable: bool = True,
                  min_holdings: int = MIN_HOLDINGS):
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
        # IRR 门（加门模式）：IRR < goal → 不投；不可算时按参数决定
        irr_info = (irr_at or {}).get(tk)
        if goal is not None:
            if irr_info is None:
                if reject_uncomputable:
                    continue
            elif irr_info["irr"] < goal:
                continue
        dd = drawdown_1y(prices_all.get(tk, {}), CUR_DT[0])
        res = evaluate_hooks(yoy, gm, dd, beats=None)
        hooks = [h["id"] for h in res["tripped"]]
        if hooks:
            conv = conviction_proxy(len(hooks), hooks, yoy[0])
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=conv,
                reasoning=f"hooks={'+'.join(hooks)} yoy={yoy[0]:.0%}"))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": hooks,
                          "yoy": yoy[0], "dd": dd, "conviction": conv,
                          "tier": "A", "irr": (irr_info or {}).get("irr"),
                          "g": (irr_info or {}).get("g"),
                          "ps0": (irr_info or {}).get("ps0"),
                          "ps_med": (irr_info or {}).get("ps_med")}
        else:
            b_pool.append((yoy[0], tk, name, sw1))
    if len(signals) < min_holdings:
        b_pool.sort(key=lambda x: -x[0])
        for yoy0, tk, name, sw1 in b_pool[:min_holdings - len(signals)]:
            irr_info = (irr_at or {}).get(tk)
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=0.30,
                reasoning=f"B-fill（无 hook）yoy={yoy0:.0%}"))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": [],
                          "yoy": yoy0, "dd": None, "conviction": 0.30,
                          "tier": "B", "irr": (irr_info or {}).get("irr"),
                          "g": (irr_info or {}).get("g"),
                          "ps0": (irr_info or {}).get("ps0"),
                          "ps_med": (irr_info or {}).get("ps_med")}
    signals.sort(key=lambda s: -s.value)
    return signals, detail


def blend_weights(signals: list[Signal]) -> dict[str, float]:
    from src.portfolio.construction import ConvictionWeightedBlend
    blender = ConvictionWeightedBlend()
    result = blender.blend(signals, {"growth_loop": 1.0}, gross_target=1.0)
    return {tk: min(w, PER_NAME_CAP) for tk, w in result.weights.items()
            if w > 0}


# ---------------------------------------------------------------------------
# 引擎重放
# ---------------------------------------------------------------------------

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
                       detail[t]["hooks"], detail[t].get("tier", "A"),
                       detail[t].get("irr"))
                      for t, w in sorted(weights.items(),
                                         key=lambda x: -x[1])
                      if t in detail],
        })


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    reject_uncomputable = True
    if mode.endswith("u"):          # irr15u: IRR 不可算 → 放行（不证伪即放行）
        reject_uncomputable = False
        mode = mode[:-1]
    goal = None if mode == "baseline" else float(mode.replace("irr", "")) / 100
    mode_suffix = "u" if not reject_uncomputable else ""
    nav_file = f"_bt_gl_irr_{mode}{mode_suffix}_nav.json"
    det_file = f"_bt_gl_irr_{mode}{mode_suffix}_detail.json"
    diag_file = f"_bt_gl_irr_{mode}{mode_suffix}_diag.json"

    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    # ---------- 逐期 IRR 预计算 ----------
    print(f"\n① [{mode}] IRR 逐期计算（goal={goal}）")
    irr_by_dt: dict[str, dict] = {}
    for month in REBALANCES:
        if month not in sel:
            continue
        as_of = sel[month]["as_of"]
        irr_map: dict[str, dict] = {}
        for tk, name, sw1 in sel[month]["candidates"]:
            info = compute_irr(financials, prices_all, tk, month, as_of)
            if info:
                irr_map[tk] = info
        irr_by_dt[month] = irr_map
        vals = [v["irr"] for v in irr_map.values()]
        passed = [v for v in vals if v >= (goal or -9)]
        print(f"  [{month}] 候选 {len(sel[month]['candidates'])} | "
              f"IRR可算 {len(vals)} | 过门 {len(passed)} | "
              f"中位IRR {statistics.median(vals):+.1%}" if vals else
              f"  [{month}] 候选 {len(sel[month]['candidates'])} | IRR 全不可算")

    # ---------- 信号 + 权重 ----------
    weights_by_dt, detail_by_dt = {}, {}
    diag: dict[str, dict] = {}
    print(f"\n② [{mode}] HOOK 筛选（IRR 门已生效）")
    for month in REBALANCES:
        if month not in sel:
            continue
        as_of = sel[month]["as_of"]
        fin_at = avail_financials(financials, as_of)
        CUR_DT[0] = month
        signals, detail = build_signals(fin_at, sel[month]["candidates"],
                                        prices_all, irr_by_dt.get(month),
                                        goal,
                                        reject_uncomputable=reject_uncomputable)
        weights = blend_weights(signals)
        weights_by_dt[month] = weights
        detail_by_dt[month] = detail
        n_a = sum(1 for d in detail.values() if d["tier"] == "A")
        diag[month] = {
            "candidates": len(sel[month]["candidates"]),
            "irr_ok": len(irr_by_dt.get(month, {})),
            "irr_fail_no_data": (len(sel[month]["candidates"])
                                 - len(irr_by_dt.get(month, {}))),
            "a_tier": n_a, "b_fill": len(detail) - n_a,
            "holdings": len(weights),
            "gross": round(sum(weights.values()), 4),
        }
        print(f"  [{month}] 候选 {len(sel[month]['candidates'])} → "
              f"IRR过门/可算 {diag[month]['irr_ok']} → A {n_a} / "
              f"B {diag[month]['b_fill']} → 持仓 {len(weights)} "
              f"gross {diag[month]['gross']:.0%}")

    # ---------- 引擎 ----------
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

    print("\n③ 引擎回测…")
    engine.run_backtesting()
    daily = engine.calculate_result()
    engine.calculate_statistics(daily, output=False)
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())

    r = bal[dts[-1]] / CAPITAL - 1
    br = bench[dts[-1]] / bench[dts[0]] - 1
    yrs = _month_span(dts[0], dts[-1]) / 12
    ann = (1 + r) ** (1 / yrs) - 1
    # 最大回撤
    peak = 0.0
    mdd = 0.0
    for dt in dts:
        peak = max(peak, bal[dt])
        mdd = min(mdd, bal[dt] / peak - 1)
    print(f"\n④ [{mode}] 总收益 {r:+.1%}（{bal[dts[-1]]:,.0f}）| "
          f"年化 {ann:+.1%} | 最大回撤 {mdd:.1%} | "
          f"中证全指 {br:+.1%} | 超额 {r-br:+.1%}")

    # baseline 校验
    if mode == "baseline" and os.path.exists(BASELINE_NAV_FILE):
        old = json.loads(open(BASELINE_NAV_FILE, encoding="utf-8").read())
        old_end = old[-1]["nav"]
        diff = (bal[dts[-1]] - old_end) / old_end
        print(f"  baseline 校验: 本次 {bal[dts[-1]]:,.0f} vs "
              f"_bt_gl_nav.json {old_end:,.0f} | 偏差 {diff:+.2%}")

    nav = [{"month": r_["dt"], "nav": r_["balance"]}
           for r_ in daily if r_["dt"] in bench]
    json.dump(nav, open(nav_file, "w", encoding="utf-8"))
    json.dump({"weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt,
               "history": strategy.history},
              open(det_file, "w", encoding="utf-8"), ensure_ascii=False)
    # 逐期收益
    print("\n⑤ 逐期收益")
    hist_dts = [h["dt"] for h in strategy.history]
    per_ret: dict[str, float] = {}
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        if mk not in bal:
            continue
        nxt = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
        end_mk = nxt if nxt in bal else dts[-1]
        ret = bal[end_mk] / bal[mk] - 1 if end_mk in bal else 0.0
        per_ret[mk] = ret
        brk = (bench[end_mk[:7]] / bench[mk[:7]] - 1
               if bench.get(mk[:7]) and bench.get(end_mk[:7]) else None)
        ex = f" | 基准 {brk:+.1%}" if brk is not None else ""
        irrs = [nm[4] for nm in h["names"] if nm[4] is not None]
        irr_txt = (f" | 持仓IRR {min(irrs):+.0%}~{max(irrs):+.0%}"
                   if irrs else "")
        print(f"  [{mk}] {ret:+.1%}{ex}（{h['n']} 只）{irr_txt}")

    json.dump({"goal": goal, "diag": diag, "per_period_ret": per_ret,
               "mdd": mdd, "annualized": ann, "total_return": r,
               "excess": r - br},
              open(diag_file, "w", encoding="utf-8"), ensure_ascii=False)

    print(f"\n→ {nav_file} + {det_file} + {diag_file}")


if __name__ == "__main__":
    main()
