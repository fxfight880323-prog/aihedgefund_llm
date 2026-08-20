"""章宏帆框架 × v3rec 化（预期只否决）— 万得全A 全市场诚实回测。

用户需求：ZHF 框架也和 v3rec 一样，分析师一致预期数据只做【否决】不做【打分】，
再补上卖出纪律。

诚实前提（数据约束，必须先读）：
  全市场(万得全A 4441~5503 只) PIT 实际财务数据（营收/ROE/毛利率）当前不可得
  —— juzi 财务接口单股粒度(5500×10 次调用不可行)、妙想/自选股为当前快照
  （对 2021 调仓日即未来函数，铁律禁止）。全市场唯一 PIT 可得 = 一致预期快照
  （con_np_yoy / con_roe / con_pe / con_peg / np_revision_4w，snapshot ≤ 调仓日）。
  因此本实验在数据约束下的最近似执行：
    · 预期数据降级为【绝对否决闸门】（v3rec 三闸门，先于框架，任何条件命中即弃）
    · ZHF 决策树打分层保留（类配比/集中度纪律），但输入字段只能是 con_*
    · 卖出纪律用可得数据实现：预期恶化 overlay（rev4w≤0 / PEG≥2 / 预期增速环比下滑）
      + 价格回撤止损（月度出场；替代 v3rec 的 PS/PS_med 卖出 —— 无实际营收不可算）
  若未来补齐全市场实际财务，"打分层用实际财务 + 预期只否决"才是 v3rec 严格类比，
  本实验为其最近似版本。

三臂（同池同价同成本 5bp+10bp 同日历，vnpy 引擎）：
  arm1 ZHF-veto        预期三闸门否决 + ZHF 打分，无卖出（隔离否决边际）
  arm2 ZHF-veto-sell   arm1 + 卖出纪律（预期恶化 overlay + 回撤止损 -40% 月度）
  arm3 ZHF-veto-switch arm2 + 风格开关（过去12月基准<-10% 熊市 → gross 0.5）

基准：EW-全A（等权 NAV，PIT 成分+真实月K）| 中证全指 000985.SH | ZHF-cons(-7.3%)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal
from _zhf_winda_variant import (load_consensus, load_universe, build_portfolio,
                                ew_universe_nav, contribution,
                                CAPITAL, PIT_DATES, REBALANCES,
                                UNIV_FILE, CONS_FILE, PRICES_FILE, INDEX_FILE,
                                PE_CEIL, CLASS_BUDGET, PER_NAME_CAP, MAX_HOLDINGS)
from _zhf_cons_variant import zhf_cons_signal

# ---- v3rec 三闸门（先于框架的绝对否决）----
YOY_MIN = 0.0            # 预期净利增速 > 0（已知负增长 → 弃）
REV4W_MIN = 0.0          # 预期修正动量 > 0（分析师在往下调 → 弃）
PEG_MIN, PEG_MAX = 0.0, 2.0   # 预期 PEG ∈ (0,2)（估值不合理 → 弃）
DRAWDOWN_STOP = 0.40     # 回撤止损：从持有期峰值回撤 ≥ 40% → 清仓（月度）
YOY_DROP_MIN = 0.0       # 预期增速环比下滑触发阈值：≥该比例视为恶化（0=任何下滑）
BEAR_12M_RET = -0.10     # 风格开关：过去 12 个月基准收益 < -10% = 熊市
BEAR_GROSS = 0.5         # 熊市 gross 目标

OUT_PREFIX = "_bt_zhf_veto"


def consensus_veto(rec: dict | None) -> str | None:
    """返回命中闸门名；None = 通过。"""
    if not rec:
        return "cov"
    try:
        yoy = float(rec.get("con_np_yoy")) if rec.get("con_np_yoy") is not None else None
    except (TypeError, ValueError):
        yoy = None
    if yoy is None or yoy <= YOY_MIN:
        return "yoy_le0"
    try:
        rev = float(rec.get("np_revision_4w")) if rec.get("np_revision_4w") is not None else None
    except (TypeError, ValueError):
        rev = None
    if rev is None or rev <= REV4W_MIN:
        return "rev_le0"
    try:
        peg = float(rec.get("con_peg")) if rec.get("con_peg") is not None else None
    except (TypeError, ValueError):
        peg = None
    if peg is not None and (peg <= PEG_MIN or peg >= PEG_MAX):
        return "peg_bad"
    return None


def build_signals_veto(cons: dict, month: str, as_of: str) -> tuple[list[Signal], Counter]:
    """否决闸门 → ZHF 决策树打分（link=None，全市场无产业链方向）。"""
    sigs, veto = [], Counter()
    for tk, rec in cons.items():
        v = consensus_veto(rec)
        if v:
            veto[v] += 1
            continue
        sig = zhf_cons_signal(rec, None, PE_CEIL)
        if sig is None:
            veto["tree_abstain"] += 1
            continue
        sig.ticker, sig.date = tk, as_of
        sigs.append(sig)
    return sigs, veto


def bearish_at(idx: dict, month: str) -> bool:
    pts = [(mk, v) for mk, v in sorted(idx.items()) if mk <= month and v and v > 0]
    if len(pts) < 12:
        return False
    cur, prev = pts[-1][1], pts[-12][1]
    if prev <= 0:
        return False
    return (cur / prev - 1.0) < BEAR_12M_RET


# ===========================================================================
# 卖出纪律策略（arm1 退化：sell_on=False 即纯调仓）
# ===========================================================================

class VetoSellStrategy(StrategyTemplate):
    """卖出纪律（全市场数据约束版）：
      · 调仓月 overlay：预期恶化（rev4w≤0 / PEG≥2 / 预期增速环比下滑[con_year 对齐]）→ 清仓
      · 非调仓月：价格回撤止损（持有期峰值回撤 ≥ DRAWDOWN_STOP）→ 清仓
      · 风格开关（arm3）：熊市 gross=0.5
    PS/PS_med 卖出不可行（无实际营收），已在 docstring 标注。"""

    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]
        self.cons_by_month = setting["cons_by_month"]
        self.rebalance_dts = setting["rebalance_dts"]
        self.sell_on = setting.get("sell_on", True)
        self.gross_by_dt = setting.get("gross_by_dt", {})
        self.drawdown_stop = setting.get("drawdown_stop", DRAWDOWN_STOP)
        self.yoy_drop_min = setting.get("yoy_drop_min", YOY_DROP_MIN)
        self.sell_log: list[dict] = []
        self.history: list[dict] = []
        self.peak: dict[str, float] = {}
        self.rebal_idx = {m: i for i, m in enumerate(self.rebalance_dts)}

    def _exp_sell_check(self, tk: str, dt: str) -> tuple[bool, str]:
        """预期恶化 overlay（仅调仓月有 PIT 快照）。"""
        cur = (self.cons_by_month.get(dt) or {}).get(tk)
        if not cur:
            return False, ""
        hits = []
        try:
            rev = float(cur.get("np_revision_4w")) if cur.get("np_revision_4w") is not None else None
            if rev is not None and rev <= REV4W_MIN:
                hits.append(f"rev4w={rev:.0f}≤0")
        except (TypeError, ValueError):
            pass
        try:
            peg = float(cur.get("con_peg")) if cur.get("con_peg") is not None else None
            if peg is not None and peg >= PEG_MAX:
                hits.append(f"PEG={peg:.2f}≥2")
        except (TypeError, ValueError):
            pass
        i = self.rebal_idx.get(dt)
        if i and i > 0:
            prev = (self.cons_by_month.get(self.rebalance_dts[i - 1]) or {}).get(tk)
            if prev:
                py, cy = prev.get("con_np_yoy"), cur.get("con_np_yoy")
                try:
                    py = float(py) if py is not None else None
                    cy = float(cy) if cy is not None else None
                except (TypeError, ValueError):
                    py = cy = None
                if (py is not None and cy is not None
                        and prev.get("con_year") == cur.get("con_year")
                        and py > 0
                        and cy < py * (1.0 - self.yoy_drop_min)):
                    hits.append(f"con_yoy {py:.0f}→{cy:.0f}")
        return bool(hits), " + ".join(hits)

    def _dd_sell_check(self, tk: str, dt: str, bar) -> tuple[bool, str]:
        px = bar.close_price
        if px <= 0:
            return False, ""
        if tk not in self.peak:
            self.peak[tk] = px
            return False, ""
        self.peak[tk] = max(self.peak[tk], px)
        if px <= self.peak[tk] * (1.0 - self.drawdown_stop):
            return True, (f"回撤{1 - px / self.peak[tk]:.0%}"
                          f"≥{self.drawdown_stop:.0%}")
        return False, ""

    def _log_sell(self, dt, tk, reason, kind, weight):
        equity = self.engine.get_equity(self.engine.bars)
        self.sell_log.append({
            "dt": dt, "ticker": tk, "reason": reason, "kind": kind,
            "weight": weight,
            "pos_before": self.engine.pos_data.get(tk, 0.0),
            "equity": equity,
        })

    def on_bars(self, bars):
        dt = self.engine.datetime
        if dt not in self.rebalance_dts:
            if self.sell_on:
                for sym, pos in list(self.engine.pos_data.items()):
                    if pos <= 0:
                        continue
                    bar = bars.get(sym) or self.engine.bars.get(sym)
                    if not bar:
                        continue
                    hit, reason = self._dd_sell_check(sym, dt, bar)
                    if not hit:
                        continue
                    self.set_target(sym, 0.0)
                    self.rebalance_portfolio(bars)
                    self._log_sell(dt, sym, reason, "monthly_exit",
                                   self.engine.pos_data.get(sym, 0.0) *
                                   bar.close_price /
                                   max(self.engine.get_equity(bars), 1.0))
                    self.peak.pop(sym, None)
            return

        weights = self.weights_by_dt.get(dt, {})
        gross = self.gross_by_dt.get(dt, 1.0)
        equity = self.engine.get_equity(bars)
        self.target_data = {}
        for tk, w in weights.items():
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar and bar.close_price > 0:
                self.target_data[tk] = w * gross * equity / bar.close_price
        for s, pos in list(self.engine.pos_data.items()):
            if pos > 0 and s not in weights:
                self.target_data[s] = 0.0
        self.rebalance_portfolio(bars)
        # 重置回撤跟踪：调仓日以新价起算
        for tk in weights:
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar:
                self.peak[tk] = bar.close_price
        # 预期恶化 overlay（新权重内命中 → 不买/清仓）
        if self.sell_on:
            for tk in list(weights):
                hit, reason = self._exp_sell_check(tk, dt)
                if not hit:
                    continue
                self.cancel_all()
                self.target_data.pop(tk, None)
                self.target_data[tk] = 0.0
                self.rebalance_portfolio(bars)
                self._log_sell(dt, tk, reason, "rebalance_overlay",
                               weights[tk] * gross)
                self.peak.pop(tk, None)
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "gross": gross, "weights": weights,
        })


# ===========================================================================
# main
# ===========================================================================

def main():
    univ = load_universe()
    cons = load_consensus()   # {month: {tk: rec}}（已按 con_year 对齐）
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    idx = json.loads(open(INDEX_FILE, encoding="utf-8").read())
    old = json.loads(open("_bt_winda_results.json", encoding="utf-8").read())
    zhf_cons_old = old["zhf"]
    print("=" * 78)
    print("  章宏帆框架 × v3rec 化（预期只否决）+ 卖出纪律 · 万得全A")
    print("=" * 78)

    bars = {}
    for tk, m in prices.items():
        mm = {mk: px for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        if mm:
            bars[tk] = {mk: BarData(tk, mk, px, px, px, px) for mk, px in mm.items()}
    all_months = sorted({mk for m in bars.values() for mk in m})

    # ---- 基准 ----
    print("\n① 基准")
    ew = ew_universe_nav(univ, prices, all_months)
    bench_months = sorted(ew.keys())
    n0 = bench_months[0]
    bench_ew = {mk: ew[mk] / ew[n0] for mk in bench_months}
    print(f"  等权全A: {bench_months[0]}~{bench_months[-1]} "
          f"{len(bench_months)} 个月 | 终值 {bench_ew[bench_months[-1]]:.3f}")

    # ---- 逐期信号 + 权重 ----
    print("\n② 逐期筛选（否决闸门 → ZHF 树）")
    weights_by_dt: dict[str, dict] = {}
    diag: dict[str, dict] = {}
    veto_all: Counter = Counter()
    for month, as_of in PIT_DATES:
        sigs, veto = build_signals_veto(cons.get(month, {}), month, as_of)
        w = build_portfolio(sigs)
        weights_by_dt[month] = w
        veto_all += veto
        cls = Counter((s.metadata or {}).get("asset_class") for s in sigs)
        diag[month] = {
            "univ": len(univ.get(month, [])), "cov": len(cons.get(month, {})),
            "veto": dict(veto), "pass": len(sigs), "cls": dict(cls),
            "hold": len(w), "gross": round(sum(w.values()), 4),
        }
        print(f"  [{month}] univ={diag[month]['univ']} 通过={len(sigs)} "
              f"否决={dict(veto)} cls={dict(cls)} hold={len(w)}")
    print(f"  否决汇总: {dict(veto_all)}")

    # 风格开关（arm3）：熊市 gross
    gross_by_dt = {m: (BEAR_GROSS if bearish_at(idx, m) else 1.0)
                   for m in REBALANCES}
    bear_months = [m for m, g in gross_by_dt.items() if g < 1.0]
    print(f"  熊市期(基准12M<-10%): {bear_months or '无'}")

    # ---- 引擎 ----
    print("\n③ 引擎回测")
    engine_common = {
        "weights_by_dt": weights_by_dt, "cons_by_month": cons,
        "rebalance_dts": REBALANCES,
    }
    arms = []
    for name, sell_on, switch, dd, yoy_drop in [
        ("ZHF-veto", False, False, DRAWDOWN_STOP, YOY_DROP_MIN),
        ("ZHF-veto-sell", True, False, DRAWDOWN_STOP, YOY_DROP_MIN),
        ("ZHF-veto-switch", True, True, DRAWDOWN_STOP, YOY_DROP_MIN),
        ("ZHF-veto-sell-strict", True, False, 0.50, 0.50),
    ]:
        eng = BacktestingEngine()
        eng.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                           rate=0.0005, slippage=0.001)
        eng.add_data(bars)
        strat = VetoSellStrategy(eng, {
            **engine_common,
            "sell_on": sell_on,
            "gross_by_dt": gross_by_dt if switch else {},
            "drawdown_stop": dd,
            "yoy_drop_min": yoy_drop,
        })
        eng.add_strategy(strat)
        eng.run_backtesting()
        daily = eng.calculate_result()
        stats = eng.calculate_statistics(daily, output=False)
        bal = {r["dt"]: r["balance"] for r in daily}
        dts = sorted(d for d in bal if d in bench_ew)
        total = bal[dts[-1]] / bal[dts[0]] - 1
        yrs = len(dts) / 12
        ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1
        mdd = stats.get("max_ddpercent", 0) / 100.0
        excess_ew = total - (bench_ew[dts[-1]] / bench_ew[dts[0]] - 1)
        nav = [{"month": d, "nav": bal[d]} for d in dts]
        result = {"name": name, "total": total, "ann": ann, "mdd": mdd,
                  "excess_ew": excess_ew, "nav": nav,
                  "n_sells": len(strat.sell_log),
                  "sell_log": strat.sell_log}
        arms.append(result)
        print(f"  [{name}] 总收益 {total:+.1%} | 年化 {ann:+.1%} | "
              f"MDD {mdd:.1%} | 超额(等权全A) {excess_ew:+.1%} | "
              f"卖出 {len(strat.sell_log)} 笔")
        json.dump(nav, open(f"{OUT_PREFIX}_{name}_nav.json", "w",
                            encoding="utf-8"), ensure_ascii=False)
        # 逐期收益
        hist_dts = [h["dt"] for h in strat.history]
        per_ret = {}
        for i, h in enumerate(strat.history):
            mk = h["dt"]
            if mk not in bal:
                continue
            nxt = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
            end_mk = nxt if (nxt and nxt in bal) else dts[-1]
            ret = bal[end_mk] / bal[mk] - 1
            per_ret[mk] = ret
            print(f"      [{mk}] {ret:+.1%}（{h['n']} 只, gross {h['gross']:.0%}）")
        result["per_period_ret"] = per_ret
        if strat.sell_log:
            by_reason: Counter = Counter(s["reason"] for s in strat.sell_log)
            by_kind: Counter = Counter(s["kind"] for s in strat.sell_log)
            print(f"      卖出: {dict(by_kind)}")
            for k, v in sorted(by_reason.items(), key=lambda x: -x[1])[:6]:
                print(f"        {k}: {v}")

    # ---- 个股贡献（arm2）----
    print("\n④ 个股贡献（ZHF-veto-sell 每期 Top）")
    contrib = contribution(weights_by_dt, prices, bench_months, univ)
    for row in contrib:
        line = f"  {row['month']}→{row['end']}: {row['total_ret']:+.1%} ({row['n']}只)"
        print(line)
        for it in row["top"]:
            print(f"      {it['tk']:12s} w={it['w']:.1%} "
                  f"ret={it['ret']:+.1%} contrib={it['contrib']:+.2%}")

    # ---- 保存 ----
    r_ew = {"name": "EW-全A", "total": bench_ew[bench_months[-1]] - 1,
            "ann": (bench_ew[bench_months[-1]]) ** (12 / len(bench_months)) - 1,
            "mdd": None, "excess_ew": 0.0,
            "nav": [{"month": m, "nav": v} for m, v in bench_ew.items()]}
    out = {
        "arms": arms, "ew": r_ew,
        "zhf_cons_old": {"name": "ZHF-cons", "total": zhf_cons_old["total"],
                         "ann": zhf_cons_old["ann"], "mdd": zhf_cons_old["mdd"]},
        "diag": diag, "veto_all": dict(veto_all),
        "bear_months": bear_months,
        "weights_by_dt": weights_by_dt,
        "contrib": contrib,
        "bench_ew": bench_ew,
        "bench_months": bench_months,
        "drawdown_stop": DRAWDOWN_STOP,
    }
    json.dump(out, open(f"{OUT_PREFIX}_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n结果 → {OUT_PREFIX}_results.json")


if __name__ == "__main__":
    main()
