# -*- coding: utf-8 -*-
"""卖出纪律实验：估值因子 + 二阶导增速减缓 → 卖出。

目标：回答"若卖出端考虑估值（估值不合理就卖）+ 二阶导增速减缓（增速
加速度转负就卖），5 年回测效果会怎样"。

口径（诚实标注，全部 point-in-time，无未来数据）：

  1. 估值因子（V，基于 PIT 月度 PS）：
       PS₀     = 当月月末价 / TTM 营收（TTM 用当月已披露报告期）
       PS_med  = 前 36 个月内每月 PIT PS 的中位数（历史不足 6 月→不可算）
       val_ratio = PS₀ / PS_med
       卖出触发：val_ratio ≥ 阈值（val15=1.5 / val20=2.0，即"估值比自身
       历史中位数贵 50%/100% 视为不合理"）

  2. 二阶导减速（D，基于 PIT 营收 YoY 序列）：
       yoy[0] 最新报告期营收同比；yoy[1] 上一报告期；yoy[2] 再上一期
       decel = yoy[0] - yoy[1]（增速的环比变化，即二阶导）
       decel20 触发：decel ≤ -20pp（增速掉 20 个百分点以上）
       decel2q 触发：yoy[0] < yoy[1] < yoy[2]（连续两期增速下滑）

  3. 触发时点：逐月检查（非调仓月检查当前持仓；调仓月先按 baseline
     生成权重，再对权重>0 的票做卖出 overlay 置 0）。卖出指令按 vnpy
     语义在次月撮合。任何月份触发 → 该票不被持有，资金转现金，等下一
     调仓月再配置 → 这是"卖出纪律"的诚实效果（卖出≠换仓）。

  4. baseline 模式不加卖出纪律，用于复现 _bt_gl_nav.json（860,178）校验。

  5. 卖出决策质量诊断（后视验证，仅用于评估规则优劣，不构成收益承诺）：
     每笔卖出记录 6 个月后该股收益 → 负=卖对了，正=卖错了，统计卖对率。

用法: python _gl_valsell_variant.py <mode>
      # baseline | val15 | val20 | decel20 | decel2q | valdecel
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
PS_LOOKBACK_MONTHS = 36
PS_MIN_POINTS = 6
DECEL_PP = 20          # decel20 阈值（pp）
VAL_RATIO_DEFAULT = 2.0

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


def shift_month(month: str, delta: int) -> str:
    """月份键平移（delta 可正可负）。"""
    y, m = int(month[:4]), int(month[5:])
    total = y * 12 + (m - 1) + delta
    return f"{total // 12}-{total % 12 + 1:02d}"


def ttm_revenue(pit_periods: dict) -> float | None:
    """trailing-12M 营收（PIT 报告期集合；报表为年内累计值）。"""
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


# ---------------------------------------------------------------------------
# 卖出条件（PIT 估值 + 二阶导减速）
# ---------------------------------------------------------------------------

def build_ttm_table(financials: dict, months: list[str]) -> dict:
    """{month: {tk: ttm_revenue}} —— 一次性预计算，月度 PIT 口径。"""
    fin_cache: dict[str, dict] = {}
    out = {}
    for month in months:
        asof = month_end_asof(month)
        if asof not in fin_cache:
            fin_cache[asof] = avail_financials(financials, asof)
        fin_at = fin_cache[asof]
        out[month] = {tk: ttm_revenue(per)
                      for tk, per in fin_at.items()
                      if ttm_revenue(per)}
    return out


def val_ratio_at(prices_all: dict, ttm_by_month: dict, tk: str,
                 month: str) -> float | None:
    """PS₀ / 前 36 个月 PS 中位数（PIT）。"""
    px = prices_all.get(tk, {}).get(month)
    rev_now = (ttm_by_month.get(month) or {}).get(tk)
    if not px or px <= 0 or not rev_now or rev_now <= 0:
        return None
    ps_now = px / rev_now
    ps_list = []
    for m in iter_prior_months(month, PS_LOOKBACK_MONTHS):
        pm = prices_all.get(tk, {}).get(m)
        rev_m = (ttm_by_month.get(m) or {}).get(tk)
        if pm and pm > 0 and rev_m and rev_m > 0:
            ps_list.append(pm / rev_m)
    if len(ps_list) < PS_MIN_POINTS:
        return None
    return ps_now / statistics.median(ps_list)


def decel_pp_at(financials: dict, tk: str, as_of: str) -> float | None:
    """最新 YoY - 上期 YoY（pp）。PIT。"""
    pit = avail_financials(financials, as_of).get(tk)
    if not pit:
        return None
    yoy, _ = series_of(pit)
    if len(yoy) < 2:
        return None
    return (yoy[0] - yoy[1]) * 100.0


def yoy_slope2_at(financials: dict, tk: str, as_of: str) -> bool | None:
    """连续两期增速下滑 yoy[0] < yoy[1] < yoy[2]。None=数据不足。"""
    pit = avail_financials(financials, as_of).get(tk)
    if not pit:
        return None
    yoy, _ = series_of(pit)
    if len(yoy) < 3:
        return None
    return yoy[0] < yoy[1] < yoy[2]


# ---------------------------------------------------------------------------
# 信号构建（baseline 同原版；卖出纪律在权重后 overlay）
# ---------------------------------------------------------------------------

def build_signals(fin_at: dict, candidates: list[tuple], prices_all: dict,
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


def blend_weights(signals: list[Signal]) -> dict[str, float]:
    from src.portfolio.construction import ConvictionWeightedBlend
    blender = ConvictionWeightedBlend()
    result = blender.blend(signals, {"growth_loop": 1.0}, gross_target=1.0)
    return {tk: min(w, PER_NAME_CAP) for tk, w in result.weights.items()
            if w > 0}


# ---------------------------------------------------------------------------
# 卖出纪律判定
# ---------------------------------------------------------------------------

def sell_check(mode: str, ttm_by_month: dict, fin_ctx: dict, tk: str,
               month: str) -> tuple[bool, str]:
    """返回 (触发?, 原因)。fin_ctx 提供 as_of / 财务原始数据。"""
    if mode == "baseline":
        return False, ""
    as_of = month_end_asof(month)
    fin = fin_ctx["financials"]
    reason: list[str] = []

    # 估值
    vr = val_ratio_at(fin_ctx["prices_all"], ttm_by_month, tk, month)
    if vr is not None:
        if mode in ("val15", "val20", "valdecel", "vald2q"):
            thr = 1.5 if mode == "val15" else VAL_RATIO_DEFAULT
            if vr >= thr:
                reason.append(f"PS/PS_med={vr:.2f}≥{thr}")
    # 二阶导减速
    decel = decel_pp_at(fin, tk, as_of)
    if decel is not None and mode in ("decel20", "valdecel"):
        if decel <= -DECEL_PP:
            reason.append(f"decel={decel:.0f}pp≤-{DECEL_PP}pp")
    if mode in ("decel2q", "vald2q"):
        s2 = yoy_slope2_at(fin, tk, as_of)
        if s2 is True:
            reason.append("连续两期增速下滑")
    return bool(reason), "|".join(reason)


# ---------------------------------------------------------------------------
# 引擎重放（带逐月卖出纪律）
# ---------------------------------------------------------------------------

class SellDisciplineStrategy(StrategyTemplate):
    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
        self.detail_by_dt = setting.get("detail_by_dt", {})
        self.mode = setting["mode"]
        self.ttm_by_month = setting["ttm_by_month"]
        self.fin_ctx = setting["fin_ctx"]
        self.rebalance_dts = set(setting["rebalance_dts"])
        self.sell_log: list[dict] = []
        self.history: list[dict] = []

    def _maybe_sell(self, dt: str, bars: dict) -> None:
        """逐月检查持仓（非调仓月）。触发 → 卖出（次月撮合）。"""
        for sym, pos in list(self.engine.pos_data.items()):
            if pos <= 0:
                continue
            hit, reason = sell_check(self.mode, self.ttm_by_month,
                                     self.fin_ctx, sym, dt)
            if not hit:
                continue
            equity = self.engine.get_equity(bars)
            self.set_target(sym, 0.0)
            self.rebalance_portfolio(bars)
            bar = bars.get(sym) or self.engine.bars.get(sym)
            px = bar.close_price if bar else 0.0
            self.sell_log.append({
                "dt": dt, "ticker": sym, "reason": reason,
                "pos_before": pos, "px": px,
                "value_before": pos * px,
                "weight": (pos * px / equity if equity > 0 else None),
                "kind": "monthly_exit",
            })
            # 记录估值/减速数值
            self.sell_log[-1]["val_ratio"] = val_ratio_at(
                self.fin_ctx["prices_all"], self.ttm_by_month, sym, dt)
            as_of = month_end_asof(dt)
            self.sell_log[-1]["decel_pp"] = decel_pp_at(
                self.fin_ctx["financials"], sym, as_of)

    def on_bars(self, bars):
        dt = self.engine.datetime
        # 非调仓月：卖出纪律（风控层，独立于调仓）
        if dt not in self.rebalance_dts:
            self._maybe_sell(dt, bars)
            return
        # 调仓月：权重生成 + 卖出 overlay
        weights = self.weights_by_dt.get(dt, {})
        equity = self.engine.get_equity(bars)
        self.target_data = {}
        for tk, w in weights.items():
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar and bar.close_price > 0:
                self.target_data[tk] = w * equity / bar.close_price
        # 清掉不在目标里的旧持仓
        for s, pos in list(self.engine.pos_data.items()):
            if pos > 0 and s not in weights:
                self.target_data[s] = 0.0
        self.rebalance_portfolio(bars)
        # 卖出 overlay：对目标持仓检查卖出条件
        for tk, w in list(weights.items()):
            hit, reason = sell_check(self.mode, self.ttm_by_month,
                                     self.fin_ctx, tk, dt)
            if not hit:
                continue
            # 触发 → 撤单并清零该票（不买/清仓）
            self.cancel_all()
            self.target_data.pop(tk, None)
            self.target_data[tk] = 0.0
            self.rebalance_portfolio(bars)
            bar = bars.get(tk) or self.engine.bars.get(tk)
            px = bar.close_price if bar else 0.0
            self.sell_log.append({
                "dt": dt, "ticker": tk, "reason": reason,
                "pos_before": self.engine.pos_data.get(tk, 0.0),
                "px": px,
                "value_before": (self.engine.pos_data.get(tk, 0.0) * px),
                "weight": w,
                "kind": "rebalance_overlay",
            })
            self.sell_log[-1]["val_ratio"] = val_ratio_at(
                self.fin_ctx["prices_all"], self.ttm_by_month, tk, dt)
            as_of = month_end_asof(dt)
            self.sell_log[-1]["decel_pp"] = decel_pp_at(
                self.fin_ctx["financials"], tk, as_of)
        detail = self.detail_by_dt.get(dt, {})
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "weights": weights,
            "names": [(detail[t]["name"], detail[t]["sw1"],
                       detail[t]["hooks"], detail[t].get("tier", "A"))
                      for t, w in sorted(weights.items(),
                                         key=lambda x: -x[1])
                      if t in detail],
        })


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    nav_file = f"_bt_gl_valsell_{mode}_nav.json"
    det_file = f"_bt_gl_valsell_{mode}_detail.json"
    diag_file = f"_bt_gl_valsell_{mode}_diag.json"

    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    # 全月份（引擎 bar 范围）→ TTM 营收表
    months_all = sorted({mk for m in prices_all.values() for mk in m
                         if mk >= "2021-06"})
    print(f"① [{mode}] 预计算 {len(months_all)} 个月 TTM 营收表…")
    ttm_by_month = build_ttm_table(financials, months_all)
    fin_ctx = {"financials": financials, "prices_all": prices_all}

    # ---------- 逐期 HOOK 筛选 + 权重（与 baseline 同口径） ----------
    weights_by_dt, detail_by_dt = {}, {}
    print(f"② [{mode}] 逐期 HOOK 筛选")
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
        print(f"  [{month}] 候选 {len(sel[month]['candidates'])} → "
              f"A {n_a} / B {len(detail)-n_a} → 持仓 {len(weights)}")

    # ---------- 引擎（逐月卖出纪律） ----------
    bars = {tk: {mk: BarData(tk, mk, px, px, px, px)
                 for mk, px in m.items() if px and px > 0
                 and mk >= "2021-06"}
            for tk, m in prices_all.items()}
    bars = {tk: m for tk, m in bars.items() if m}
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = SellDisciplineStrategy(engine, {
        "mode": mode, "weights_by_dt": weights_by_dt,
        "detail_by_dt": detail_by_dt, "ttm_by_month": ttm_by_month,
        "fin_ctx": fin_ctx, "rebalance_dts": REBALANCES})
    engine.add_strategy(strategy)

    print("③ 引擎回测（含逐月卖出纪律）…")
    engine.run_backtesting()
    daily = engine.calculate_result()
    engine.calculate_statistics(daily, output=False)
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())

    r = bal[dts[-1]] / CAPITAL - 1
    br = bench[dts[-1]] / bench[dts[0]] - 1
    yrs = _month_span(dts[0], dts[-1]) / 12
    ann = (1 + r) ** (1 / yrs) - 1
    peak = 0.0
    mdd = 0.0
    for dt in dts:
        peak = max(peak, bal[dt])
        mdd = min(mdd, bal[dt] / peak - 1)
    print(f"\n④ [{mode}] 总收益 {r:+.1%}（{bal[dts[-1]]:,.0f}）| "
          f"年化 {ann:+.1%} | 最大回撤 {mdd:.1%} | "
          f"中证全指 {br:+.1%} | 超额 {r-br:+.1%}")

    if mode == "baseline" and os.path.exists(BASELINE_NAV_FILE):
        old = json.loads(open(BASELINE_NAV_FILE, encoding="utf-8").read())
        diff = (bal[dts[-1]] - old[-1]["nav"]) / old[-1]["nav"]
        print(f"  baseline 校验: 本次 {bal[dts[-1]]:,.0f} vs "
              f"_bt_gl_nav.json {old[-1]['nav']:,.0f} | 偏差 {diff:+.2%}")

    # ---------- 卖出诊断 ----------
    print(f"\n⑤ 卖出纪律统计（{mode}）")
    sells = strategy.sell_log
    print(f"  卖出笔数: {len(sells)} | 调仓月 overlay "
          f"{sum(1 for s in sells if s['kind']=='rebalance_overlay')} | "
          f"月度出场 {sum(1 for s in sells if s['kind']=='monthly_exit')}")
    by_reason: dict[str, int] = {}
    for s in sells:
        by_reason[s["reason"]] = by_reason.get(s["reason"], 0) + 1
    for k, v in sorted(by_reason.items(), key=lambda x: -x[1])[:8]:
        print(f"    {k}: {v}")

    # 卖出后 6 个月验证（后视诊断）：成交月为 dt 的次月
    for s in sells:
        tk = s["ticker"]
        fill_m = shift_month(s["dt"], 1)          # 次月撮合
        px0 = prices_all.get(tk, {}).get(fill_m)
        px6 = prices_all.get(tk, {}).get(shift_month(fill_m, 6))
        if px0 and px0 > 0 and px6 and px6 > 0:
            s["ret_6m"] = px6 / px0 - 1.0
        else:
            s["ret_6m"] = None
    ok = [s for s in sells if s.get("ret_6m") is not None]
    if ok:
        right = sum(1 for s in ok if s["ret_6m"] < 0)
        avg6 = statistics.mean(s["ret_6m"] for s in ok)
        print(f"  卖出后 6 个月验证: 可验 {len(ok)} 笔 | 卖对(跌) "
              f"{right} ({right/len(ok):.0%}) | 平均后6月 "
              f"{avg6:+.1%}")
    # 组合收益拆解：触发卖出当月 vs 未触发
    nav = [{"month": r_["dt"], "nav": r_["balance"]}
           for r_ in daily if r_["dt"] in bench]
    json.dump(nav, open(nav_file, "w", encoding="utf-8"))
    json.dump({"weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt,
               "history": strategy.history, "sell_log": sells},
              open(det_file, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"mode": mode, "mdd": mdd, "annualized": ann,
               "total_return": r, "excess": r - br,
               "n_sells": len(sells),
               "sell_kind": {"overlay": sum(1 for s in sells
                                            if s["kind"] ==
                                            "rebalance_overlay"),
                             "monthly": sum(1 for s in sells
                                            if s["kind"] == "monthly_exit")},
               "sell_by_reason": by_reason,
               "sell_verify": {"n": len(ok), "right": sum(
                   1 for s in ok if s["ret_6m"] < 0),
                   "avg_ret_6m": (statistics.mean(s["ret_6m"] for s in ok)
                                  if ok else None)}},
              open(diag_file, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n→ {nav_file} + {det_file} + {diag_file}")


if __name__ == "__main__":
    main()
