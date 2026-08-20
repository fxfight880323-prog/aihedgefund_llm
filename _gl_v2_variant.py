# -*- coding: utf-8 -*-
"""Growth Loop v2：4 条用户改进落地 + 逐条归因变体。

改进（全部 point-in-time，无未来数据）：
  A  YoY>300% 周期暴增过滤：yoy[0] > 300% 的候选直接排除（不进 A/B 池）
  B  估值护栏（买入端）：PS₀/PS_med ≥ 2.0 不投（PIT 月度 PS 中位数口径，
     与 valsell val20 同指标——之前实测 -14% → -2.6%）
  C  风格开关：调仓月过去 12 个月中证全指收益 < -10% → 熊市 → gross 0.5
  D  增速见顶降权+再配置：调仓月 decel ≤ -20pp 的票权重 ×0.5，腾出资金
     按其余票原权重比例再归一化（不转现金），随后重截单票 8% 上限

变体（隔离归因）：
  baseline  原版复现（校验 860,178）
  v2a       +A
  v2b       +A+B
  v2c       +A+B+C
  v2all     +A+B+C+D（4 条全上）

v3 系列（分析师一致预期 + PEG + 增速二阶导，买入端）：
  v3a      +分析师覆盖 / 预期净利增速>0 / rev4w>0（分析师上调）/ PEG∈(0,2)
  v3b      v3a + 实际增速二阶导>0 硬过滤（yoy 环比下滑直接排除）
  v3rec    v3a + 二阶导软加成（加速票 conviction+0.1）+ 风格开关 + 估值卖出
           （保留 v2rec 已验证的有效纪律，生产配置）

用法: python _gl_v2_variant.py <mode>
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
YOY300_TH = 3.0               # A: yoy > 300% 视为疑似周期暴增
VAL_TH = 2.0                  # B: PS/PS_med >= 2.0 视为估值不合理
BEAR_12M_RET = -0.10          # C: 过去 12 个月基准收益 < -10% = 熊市
BEAR_GROSS = 0.5              # C: 熊市 gross 目标
DECEL_PP = 20                 # D: 增速环比下滑 >= 20pp 视为见顶
DECEL_DW_FACTOR = 0.5         # D: 见顶降权系数
PEG_MAX = 2.0                 # v3: 一致预期 PEG 上限（0 < peg < 2）
CONS_REV_WINDOW = "rev4w"     # v3: 预期修正动量窗口（4 周，正=分析师上调）
ACCEL_BOOST = 0.10            # v3rec: 实际增速二阶导>0 的 conviction 加成

SEL_FILE = "_bt_pit_selection.json"
FIN_FILE = "_bt_pit_financials.json"
PRICES_FILE = "_bt_pit_prices.json"
WARMUP_FILE = "_bt_pit_warmup.json"
BENCH_FILE = "_bt_benchmark.json"
BASELINE_NAV_FILE = "_bt_gl_nav.json"
CONS_FILE = "_gl_v3_consensus.json"   # v3: 分析师一致预期 PIT 快照

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]

CUR_DT = [""]


# ---------------------------------------------------------------------------
# 指标计算（与 GL / IRR / valsell 完全一致，PIT）
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


def ttm_revenue(pit_periods: dict) -> float | None:
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


def build_ttm_table(financials: dict, months: list[str]) -> dict:
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
    """PS₀ / 前 36 个月 PS 中位数（PIT）。None = 历史不足不可算。"""
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
    pit = avail_financials(financials, as_of).get(tk)
    if not pit:
        return None
    yoy, _ = series_of(pit)
    if len(yoy) < 2:
        return None
    return (yoy[0] - yoy[1]) * 100.0


# ---------------------------------------------------------------------------
# C 风格开关：熊市判定（PIT，只用调仓月及之前的基准点位）
# ---------------------------------------------------------------------------

def bearish_at(bench: dict, month: str) -> bool:
    """过去 12 个月基准收益 < -10% → 熊市。历史不足 → 非熊市（中性）。"""
    pts = [(mk, v) for mk, v in sorted(bench.items())
           if mk <= month and v and v > 0]
    if len(pts) < 12:
        return False
    cur = pts[-1][1]
    prev = pts[-12][1]
    if prev <= 0:
        return False
    return (cur / prev - 1.0) < BEAR_12M_RET


# ---------------------------------------------------------------------------
# 信号构建（A yoy300 过滤 / B 估值护栏 / C 风格开关 gross / D 降权再配置）
# ---------------------------------------------------------------------------

def build_signals(fin_at: dict, candidates: list[tuple], prices_all: dict,
                  ttm_by_month: dict, month: str,
                  use_yoy300: bool, use_valguard: bool,
                  use_consensus: bool = False, consensus: dict | None = None,
                  second_deriv: str = "none",   # none | veto | boost
                  min_holdings: int = MIN_HOLDINGS):
    """返回 (signals, detail, veto_stat)。

    v3 买入端（分析师一致预期，PIT 快照）：
      - 必须有分析师覆盖（无覆盖 → 排除）
      - 预期净利增速 con_np_yoy > 0（已知负增长 → 排除）
      - 预期修正动量 rev4w > 0（分析师在上调 → 保留）
      - PEG ∈ (0, 2.0)（缺失放行，不误杀）
    二阶导：second_deriv="veto" → 实际 yoy 环比下滑硬排除；
            "boost" → 加速票 conviction +0.1（v3rec 生产配置）。

    veto_stat: {"yoy300","valguard","valguard_na","cons_na",
                "cons_yoy_le0","cons_down","peg_bad","yoy_decel"}
    """
    signals: list[Signal] = []
    detail: dict[str, dict] = {}
    b_pool: list[tuple[float, str, str, str]] = []
    veto_stat = {"yoy300": 0, "valguard": 0, "valguard_na": 0,
                 "cons_na": 0, "cons_yoy_le0": 0, "cons_down": 0,
                 "peg_bad": 0, "yoy_decel": 0}
    cons_m = (consensus or {}).get(month, {})
    for tk, name, sw1 in candidates:
        periods = fin_at.get(tk)
        if not periods:
            continue
        yoy, gm = series_of(periods)
        if not yoy:
            continue
        # A: YoY>300% 周期暴增过滤
        if use_yoy300 and yoy[0] > YOY300_TH:
            veto_stat["yoy300"] += 1
            continue
        # v3: 分析师一致预期（PIT 快照）
        c_yoy = c_peg = c_rev4w = None
        if use_consensus:
            c = cons_m.get(tk)
            if not c:
                veto_stat["cons_na"] += 1
                continue
            c_yoy = c.get("yoy")
            if c_yoy is not None and c_yoy <= 0:
                veto_stat["cons_yoy_le0"] += 1
                continue
            c_rev4w = c.get(CONS_REV_WINDOW)
            if c_rev4w is None or c_rev4w <= 0:
                veto_stat["cons_down"] += 1
                continue
            c_peg = c.get("peg")
            if c_peg is not None and (c_peg <= 0 or c_peg >= PEG_MAX):
                veto_stat["peg_bad"] += 1
                continue
        # v3: 实际增速二阶导（yoy 环比是否仍在上行）
        accel = len(yoy) >= 2 and yoy[0] > yoy[1]
        if second_deriv == "veto" and len(yoy) >= 2 and not accel:
            veto_stat["yoy_decel"] += 1
            continue
        # B: 估值护栏（买入端）——不可算放行（与卖出实验一致，不误杀次新）
        vr = None
        if use_valguard:
            vr = val_ratio_at(prices_all, ttm_by_month, tk, month)
            if vr is not None:
                if vr >= VAL_TH:
                    veto_stat["valguard"] += 1
                    continue
            else:
                veto_stat["valguard_na"] += 1
        decel_pp = ((yoy[0] - yoy[1]) * 100.0
                    if len(yoy) >= 2 else None)
        dd = drawdown_1y(prices_all.get(tk, {}), CUR_DT[0])
        res = evaluate_hooks(yoy, gm, dd, beats=None)
        hooks = [h["id"] for h in res["tripped"]]
        if hooks:
            conv = conviction_proxy(len(hooks), hooks, yoy[0])
            if second_deriv == "boost" and accel:
                conv = min(1.0, conv + ACCEL_BOOST)
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=conv,
                reasoning=f"hooks={'+'.join(hooks)} yoy={yoy[0]:.0%}"
                          + (f" rev4w={c_rev4w:+.0f}"
                             if c_rev4w is not None else "")))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": hooks,
                          "yoy": yoy[0], "dd": dd, "conviction": conv,
                          "tier": "A", "val_ratio": vr,
                          "decel_pp": decel_pp, "accel": accel,
                          "con_yoy": c_yoy, "con_peg": c_peg,
                          "con_rev4w": c_rev4w}
        else:
            b_pool.append((yoy[0], tk, name, sw1))
    if len(signals) < min_holdings:
        b_pool.sort(key=lambda x: -x[0])
        for yoy0, tk, name, sw1 in b_pool[:min_holdings - len(signals)]:
            vr = (val_ratio_at(prices_all, ttm_by_month, tk, month)
                  if use_valguard else None)
            # 修复：B-fill 需按当前票重算 yoy，不能用第一层循环泄漏的变量
            periods_b = fin_at.get(tk) or {}
            yoy_b, _ = series_of(periods_b)
            decel_pp = ((yoy0 - yoy_b[1]) * 100.0
                        if len(yoy_b) >= 2 else None)
            accel_b = len(yoy_b) >= 2 and yoy0 > yoy_b[1]
            cb = cons_m.get(tk) if use_consensus else None
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=0.30,
                reasoning=f"B-fill（无 hook）yoy={yoy0:.0%}"))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": [],
                          "yoy": yoy0, "dd": None, "conviction": 0.30,
                          "tier": "B", "val_ratio": vr,
                          "decel_pp": decel_pp, "accel": accel_b,
                          "con_yoy": (cb or {}).get("yoy") if cb else None,
                          "con_peg": (cb or {}).get("peg") if cb else None,
                          "con_rev4w": (cb or {}).get("rev4w") if cb else None}
    signals.sort(key=lambda s: -s.value)
    return signals, detail, veto_stat


def blend_weights(signals: list[Signal], gross_target: float
                  ) -> dict[str, float]:
    from src.portfolio.construction import ConvictionWeightedBlend
    blender = ConvictionWeightedBlend()
    result = blender.blend(signals, {"growth_loop": 1.0},
                           gross_target=gross_target)
    return {tk: min(w, PER_NAME_CAP) for tk, w in result.weights.items()
            if w > 0}


def decel_downgrade(weights: dict[str, float],
                    detail: dict[str, dict]) -> tuple[dict[str, float], list]:
    """D: decel ≤ -20pp 的票权重 ×0.5，腾出资金按其余票原权重比例再归一化。

    若全部触发或触发后剩余无票 → 不降（避免清空组合）。返回 (新权重, 日志)。
    """
    triggers = [tk for tk in weights
                if (detail.get(tk, {}).get("decel_pp") or 0.0) <= -DECEL_PP]
    if not triggers or len(triggers) == len(weights):
        return weights, []
    keep = {tk: w for tk, w in weights.items() if tk not in triggers}
    freed = sum(weights[tk] * (1 - DECEL_DW_FACTOR) for tk in triggers)
    keep_sum = sum(keep.values())
    if keep_sum <= 0:
        return weights, []
    out = {tk: w + freed * (w / keep_sum) for tk, w in keep.items()}
    # 单票上限重截（超限留现金）
    capped = {}
    for tk, w in out.items():
        if w > 0:
            capped[tk] = min(w, PER_NAME_CAP)
    log = [{"ticker": tk, "before": weights[tk],
            "after": weights[tk] * DECEL_DW_FACTOR,
            "decel_pp": detail[tk]["decel_pp"]} for tk in triggers]
    return capped, log


# ---------------------------------------------------------------------------
# 引擎重放（纯预计算权重，与 baseline 同款执行）
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
                       detail[t]["hooks"], w, detail[t].get("tier", "A"),
                       detail[t].get("val_ratio"), detail[t].get("decel_pp"))
                      for t, w in sorted(weights.items(),
                                         key=lambda x: -x[1])
                      if t in detail],
        })


# ---------------------------------------------------------------------------
# 估值卖出纪律策略（v2rec：风格开关 + 卖出端估值护栏 val20）
# ---------------------------------------------------------------------------

class ValSellStrategy(StrategyTemplate):
    """调仓月：权重生成（含风格开关）→ 持仓中 val_ratio≥2 清仓；
    非调仓月：逐月检查持仓估值，触发 → 卖出（次月撮合）。"""

    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
        self.detail_by_dt = setting.get("detail_by_dt", {})
        self.ttm_by_month = setting["ttm_by_month"]
        self.prices_all = setting["prices_all"]
        self.rebalance_dts = set(setting["rebalance_dts"])
        self.sell_log: list[dict] = []
        self.history: list[dict] = []

    def _sell_check(self, tk: str, dt: str) -> tuple[bool, str]:
        vr = val_ratio_at(self.prices_all, self.ttm_by_month, tk, dt)
        if vr is not None and vr >= VAL_TH:
            return True, f"PS/PS_med={vr:.2f}≥{VAL_TH}"
        return False, ""

    def _maybe_sell(self, dt: str, bars: dict) -> None:
        for sym, pos in list(self.engine.pos_data.items()):
            if pos <= 0:
                continue
            hit, reason = self._sell_check(sym, dt)
            if not hit:
                continue
            self.set_target(sym, 0.0)
            self.rebalance_portfolio(bars)
            bar = bars.get(sym) or self.engine.bars.get(sym)
            px = bar.close_price if bar else 0.0
            equity = self.engine.get_equity(bars)
            self.sell_log.append({
                "dt": dt, "ticker": sym, "reason": reason,
                "pos_before": pos, "px": px,
                "weight": (pos * px / equity if equity > 0 else None),
                "kind": "monthly_exit"})

    def on_bars(self, bars):
        dt = self.engine.datetime
        if dt not in self.rebalance_dts:
            self._maybe_sell(dt, bars)
            return
        weights = self.weights_by_dt.get(dt, {})
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
        # 估值卖出 overlay（调仓月：目标持仓触发 → 不买/清仓）
        for tk, w in list(weights.items()):
            hit, reason = self._sell_check(tk, dt)
            if not hit:
                continue
            self.cancel_all()
            self.target_data.pop(tk, None)
            self.target_data[tk] = 0.0
            self.rebalance_portfolio(bars)
            self.sell_log.append({
                "dt": dt, "ticker": tk, "reason": reason,
                "pos_before": self.engine.pos_data.get(tk, 0.0),
                "weight": w, "kind": "rebalance_overlay"})
        detail = self.detail_by_dt.get(dt, {})
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "weights": weights,
            "names": [(detail[t]["name"], detail[t]["sw1"],
                       detail[t]["hooks"], w, detail[t].get("tier", "A"),
                       detail[t].get("val_ratio"), detail[t].get("decel_pp"))
                      for t, w in sorted(weights.items(),
                                         key=lambda x: -x[1])
                      if t in detail],
        })


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    use_yoy300 = mode in ("v2a", "v2b", "v2c", "v2all")
    use_valguard = mode in ("v2b", "v2c", "v2all")
    use_styleswitch = mode in ("v2c", "v2all", "v2rec", "v3rec")
    use_deceldw = mode in ("v2all",)
    use_valsell = mode in ("v2rec", "v3rec")   # 卖出端估值护栏（val20 卖出纪律）
    use_consensus = mode in ("v3a", "v3b", "v3rec")
    second_deriv = ("veto" if mode == "v3b"
                    else ("boost" if mode == "v3rec" else "none"))
    nav_file = f"_bt_gl_v2_{mode}_nav.json"
    det_file = f"_bt_gl_v2_{mode}_detail.json"
    diag_file = f"_bt_gl_v2_{mode}_diag.json"

    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    consensus = (json.loads(open(CONS_FILE, encoding="utf-8").read())
                 if use_consensus else None)
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    months_all = sorted({mk for m in prices_all.values() for mk in m
                         if mk >= "2021-06"})
    print(f"① [{mode}] 预计算 {len(months_all)} 个月 TTM 营收表…")
    ttm_by_month = build_ttm_table(financials, months_all)

    # ---------- 逐期筛选 → 权重 ----------
    weights_by_dt, detail_by_dt = {}, {}
    diag: dict[str, dict] = {}
    dw_log_all: dict[str, list] = {}
    print(f"② [{mode}] 逐期筛选 "
          f"(yoy300={use_yoy300} valguard={use_valguard} "
          f"switch={use_styleswitch} decel_dw={use_deceldw} "
          f"valsell={use_valsell} consensus={use_consensus} "
          f"2nd_deriv={second_deriv})")
    for month in REBALANCES:
        if month not in sel:
            continue
        as_of = sel[month]["as_of"]
        fin_at = avail_financials(financials, as_of)
        CUR_DT[0] = month
        signals, detail, veto = build_signals(
            fin_at, sel[month]["candidates"], prices_all, ttm_by_month,
            month, use_yoy300, use_valguard,
            use_consensus=use_consensus, consensus=consensus,
            second_deriv=second_deriv)
        # C 风格开关：熊市 → gross 0.5
        bear = bearish_at(bench, month) if use_styleswitch else False
        gross_t = BEAR_GROSS if bear else 1.0
        weights = blend_weights(signals, gross_t)
        # D 降权再配置
        if use_deceldw:
            weights, dw_log = decel_downgrade(weights, detail)
            if dw_log:
                dw_log_all[month] = dw_log
        weights_by_dt[month] = weights
        detail_by_dt[month] = detail
        n_a = sum(1 for d in detail.values() if d["tier"] == "A")
        diag[month] = {
            "candidates": len(sel[month]["candidates"]),
            "veto_yoy300": veto["yoy300"],
            "veto_valguard": veto["valguard"],
            "valguard_na": veto["valguard_na"],
            "veto_cons_na": veto["cons_na"],
            "veto_cons_yoy_le0": veto["cons_yoy_le0"],
            "veto_cons_down": veto["cons_down"],
            "veto_peg_bad": veto["peg_bad"],
            "veto_yoy_decel": veto["yoy_decel"],
            "n_accel": sum(1 for d in detail.values() if d.get("accel")),
            "n_decel": sum(1 for d in detail.values()
                           if d.get("accel") is False),
            "bear": bear, "gross_target": gross_t,
            "a_tier": n_a, "b_fill": len(detail) - n_a,
            "holdings": len(weights), "gross": round(sum(weights.values()), 4),
            "decel_dw": len(dw_log_all.get(month, [])),
        }
        print(f"  [{month}] 候选 {len(sel[month]['candidates'])} | "
              f"滤暴增 {veto['yoy300']} | 滤估值 {veto['valguard']} | "
              f"无覆盖 {veto['cons_na']} | 预期降 {veto['cons_down']} | "
              f"滤PEG {veto['peg_bad']} | 二阶导滤 {veto['yoy_decel']} | "
              f"A {n_a}/B {len(detail)-n_a} | 持仓 {len(weights)} "
              f"gross {diag[month]['gross']:.0%}"
              + (" 熊市↓" if bear else "")
              + (f" 降权{len(dw_log_all.get(month, []))}" if use_deceldw else ""))

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
    if use_valsell:
        strategy = ValSellStrategy(engine, {
            "weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt,
            "ttm_by_month": ttm_by_month, "prices_all": prices_all,
            "rebalance_dts": REBALANCES})
    else:
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

    # ---------- 逐期收益 ----------
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
        print(f"  [{mk}] {ret:+.1%}{ex}（{h['n']} 只）")

    # ---------- 卖出统计（v2rec） ----------
    sells = strategy.sell_log if use_valsell else []
    if sells:
        n_overlay = sum(1 for s in sells if s["kind"] == "rebalance_overlay")
        n_monthly = sum(1 for s in sells if s["kind"] == "monthly_exit")
        print(f"\n⑤' 估值卖出纪律: {len(sells)} 笔"
              f"（调仓 overlay {n_overlay} / 月度出场 {n_monthly}）")
        by_reason: dict[str, int] = {}
        for s in sells:
            by_reason[s["reason"]] = by_reason.get(s["reason"], 0) + 1
        for k, v in sorted(by_reason.items(), key=lambda x: -x[1])[:5]:
            print(f"    {k}: {v}")

    nav = [{"month": r_["dt"], "nav": r_["balance"]}
           for r_ in daily if r_["dt"] in bench]
    json.dump(nav, open(nav_file, "w", encoding="utf-8"))
    json.dump({"weights_by_dt": weights_by_dt, "detail_by_dt": detail_by_dt,
               "history": strategy.history, "dw_log": dw_log_all,
               "sell_log": sells},
              open(det_file, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"mode": mode, "mdd": mdd, "annualized": ann,
               "total_return": r, "excess": r - br,
               "flags": {"yoy300": use_yoy300, "valguard": use_valguard,
                         "styleswitch": use_styleswitch,
                         "decel_dw": use_deceldw,
                         "valsell": use_valsell,
                         "consensus": use_consensus,
                         "second_deriv": second_deriv},
               "diag": diag, "per_period_ret": per_ret,
               "n_sells": len(sells)},
              open(diag_file, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n→ {nav_file} + {det_file} + {diag_file}")


if __name__ == "__main__":
    main()
