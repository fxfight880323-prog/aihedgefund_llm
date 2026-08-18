"""回测深度归因报告：绩效总览、回撤、分期归因、个股贡献、持仓特征。

重跑引擎（数据已缓存，秒级）并输出：
  ① 绩效总览     vnpy 统计 + 基准对比 + 年度收益分解
  ② 回撤分析     滚动高点路径 + 主要回撤段
  ③ 分期归因     每个调仓期：策略/基准/超额 + 持仓行业分布
  ④ 个股贡献     按股票聚合 PnL（含成交明细）top 赢家/输家
  ⑤ 持仓特征     期均持仓数、集中度、换手、行业覆盖

Run:
    python examples/analyze_backtest.py
"""

from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.backtest_universal import (
    CAPITAL, UNIVERSE, build_bars, load_data,
)
from src.backtest.engine import BacktestingEngine, _month_span
from src.backtest.strategy import RotationStrategy

NAME = {tk: n for tk, n, _ in UNIVERSE}
LABEL = {tk: l for tk, _, l in UNIVERSE}


def run_engine():
    financials, prices, bench = load_data()
    bars = build_bars(prices, UNIVERSE)
    symbols = list(bars.keys())
    dt_all = sorted({mk for s in bars.values() for mk in s})
    rb_map = {}
    for as_of in ["2021-08-31", "2022-04-30", "2022-08-31",
                  "2023-04-30", "2023-08-31", "2024-04-30",
                  "2024-08-31", "2025-04-30", "2025-08-31",
                  "2026-04-30"]:
        mk = as_of[:7]
        if mk in dt_all:
            rb_map[mk] = as_of
    engine = BacktestingEngine()
    engine.set_parameters(symbols=symbols, capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = RotationStrategy(engine, {
        "financials": financials, "universe": UNIVERSE,
        "rebalance_dts": set(rb_map.keys()), "disclosure_of": rb_map,
    })
    engine.add_strategy(strategy)
    engine.run_backtesting()
    return engine, strategy, bench


def pct(x, nd=1):
    return f"{x * 100:+.{nd}f}%"


def main():
    engine, strategy, bench = run_engine()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())

    print("=" * 78)
    print("  章宏帆轮动 · 通用行业回测 — 深度归因报告（vnpy 式引擎）")
    print("  区间 2021-06 → 2026-08 | 月频估值 | 半年度调仓（披露截止日月末）")
    print("  成本：佣金 5bp + 滑点 10bp（单边入价）| 资金 ¥100 万")
    print("=" * 78)

    # ------------------------------------------------------------- ① 绩效
    print("\n" + "─" * 78)
    print("① 绩效总览")
    print("─" * 78)
    n_months = stats["total_months"]
    yrs = _month_span(dts[0], dts[-1]) / 12
    end = bal[dts[-1]]
    total = end / CAPITAL - 1
    b_end = bench.get(dts[-1])
    b_total = (b_end / bench[dts[0]] - 1) if b_end and dts[0] in bench \
        else None
    print(f"  期末权益        ¥{end:,.0f}（初始 ¥{CAPITAL:,.0f}）")
    print(f"  总收益          {pct(total)}    月数 {n_months}（{yrs:.1f} 年）")
    print(f"  年化收益        {pct((1 + total) ** (1 / yrs) - 1)}")
    print(f"  基准（中证全指）{pct(b_total) if b_total is not None else 'N/A'}"
          f"    年化 "
          f"{pct((1 + b_total) ** (1 / yrs) - 1) if b_total else 'N/A'}")
    if b_total is not None:
        print(f"  超额收益        {pct(total - b_total)}"
              f"    超额年化 {pct(((1+total)/(1+b_total)) ** (1/yrs) - 1)}")
    print(f"  夏普比率        {stats['sharpe_ratio']:.2f}"
          f"（rf=2%，月频 ×√12）")
    print(f"  最大回撤        {stats['max_ddpercent']:.1f}%"
          f"（{stats['max_dd_duration']}）")
    print(f"  收益回撤比      {stats['return_drawdown_ratio']:.2f}")
    print(f"  成交            {stats['total_trade_count']} 笔 | "
          f"总额 ¥{stats['total_turnover'] / 1e6:.1f}M | "
          f"佣金 ¥{stats['total_commission']:,.0f}")

    # 年度分解
    print("\n  年度收益分解（vs 基准）：")
    year_marks = []
    seen = set()
    for mk in dts:
        y = mk[:4]
        if y not in seen and mk.endswith("-12") or mk == dts[-1]:
            if y not in seen:
                year_marks.append(mk)
                seen.add(y)
    base = dts[0]
    for ym in year_marks:
        y = ym[:4]
        if ym in bal and base in bal:
            r = bal[ym] / bal[base] - 1
            br = (bench[ym] / bench[base] - 1
                  if ym in bench and base in bench and bench[base] else None)
            bl = f" | 基准 {pct(br)} | 超额 {pct(r - br)}" if br is not None else ""
            print(f"    {y}: {pct(r)}{bl}")
        base = ym

    # ------------------------------------------------------------- ② 回撤
    print("\n" + "─" * 78)
    print("② 回撤分析")
    print("─" * 78)
    high = bal[dts[0]]
    peak_dt = dts[0]
    segs = []
    cur = None
    for mk in dts:
        b = bal[mk]
        if b >= high:
            if cur and cur["dd"] < 0:
                segs.append(cur)
            high, peak_dt = b, mk
            cur = None
        else:
            if cur is None:
                cur = {"peak": peak_dt, "trough": mk, "dd": b - high,
                       "ddpct": (b - high) / high, "recov": None,
                       "low": b}
            elif b < cur["low"]:
                cur.update(trough=mk, dd=b - high,
                           ddpct=(b - high) / high, low=b)
            if cur["recov"] is None and b >= high:
                cur["recov"] = mk
    if cur and cur["dd"] < 0:
        segs.append(cur)
    segs.sort(key=lambda s: s["dd"])
    for i, s in enumerate(segs[:5], 1):
        span = _month_span(s["peak"], s["trough"])
        print(f"  #{i} {s['ddpct'] * 100:.1f}%  {s['peak']} 峰值 → "
              f"{s['trough']} 谷底（{span} 个月）"
              + (f" → {s['recov']} 修复" if s["recov"] else "（未修复）"))

    # ------------------------------------------------------------- ③ 分期归因
    print("\n" + "─" * 78)
    print("③ 分期归因（调仓期 × 行业配置）")
    print("─" * 78)
    hist_dts = [h["dt"] for h in strategy.history]
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        if mk not in bal:
            continue
        next_rb = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
        end_mk = next_rb if next_rb in bal else dts[-1]
        if end_mk not in bal or end_mk <= mk:
            continue
        r = bal[end_mk] / bal[mk] - 1
        br = (bench[end_mk] / bench[mk] - 1
              if mk in bench and end_mk in bench
              and bench.get(mk) and bench.get(end_mk) else None)
        ex = f" | 基准 {pct(br)} | 超额 {pct(r - br)}" if br is not None else ""
        top_links = " ".join(f"{n}({s}/10)"
                             for n, s in h["top_links"][:3])
        print(f"\n  ▶ {mk}（信息截至 {h['as_of']}）→ 持有至 {end_mk}: "
              f"{pct(r)}{ex}")
        print(f"    当期行业稀缺度 top: {top_links}")
        print(f"    持仓 {h['n_hold']} 只 | 权益 ¥{h['equity']:,.0f} | "
              f"行业分布: " + " ".join(
                  f"{lab} {w:.0%}" for lab, w in sorted(
                      h["by_label"].items(), key=lambda x: -x[1])[:6]))
        # 期内持仓明细（权重 ≥3%）
        detail = sorted(h["weights"].items(), key=lambda x: -x[1])
        line = "    ├─ "
        for tk, w in detail:
            if w < 0.03:
                continue
            line += f"{NAME.get(tk, tk)}({LABEL.get(tk, '?')}) {w:.0%}  "
        print(line)

    # ------------------------------------------------------------- ④ 个股贡献
    print("\n" + "─" * 78)
    print("④ 个股贡献（按标的聚合 net_pnl，含持有与交易损益）")
    print("─" * 78)
    contrib: dict[str, float] = {}
    trades_of: dict[str, list] = {}
    for dt, daily_res in engine.daily_results.items():
        for sym, c in daily_res.contracts.items():
            if c.net_pnl:
                contrib[sym] = contrib.get(sym, 0.0) + c.net_pnl
            for t in c.trades:
                trades_of.setdefault(sym, []).append(t)
    ranked = sorted(contrib.items(), key=lambda x: -x[1])
    print("\n  前 10 大赢家：")
    for sym, pnl in ranked[:10]:
        n_tr = len(trades_of.get(sym, []))
        print(f"    {sym} {NAME.get(sym, ''):8s} {LABEL.get(sym, ''):6s} "
              f"净贡献 ¥{pnl:>+10,.0f}（{pnl / CAPITAL:>+.1%} 本金）"
              f" {n_tr} 笔")
    print("\n  前 5 大输家：")
    for sym, pnl in ranked[-5:]:
        n_tr = len(trades_of.get(sym, []))
        print(f"    {sym} {NAME.get(sym, ''):8s} {LABEL.get(sym, ''):6s} "
              f"净贡献 ¥{pnl:>+10,.0f}（{pnl / CAPITAL:>+.1%} 本金）"
              f" {n_tr} 笔")
    # 盈亏结构
    wins = [v for _, v in ranked if v > 0]
    losses = [v for _, v in ranked if v < 0]
    print(f"\n  盈亏结构: {len(wins)} 赢 / {len(losses)} 亏 | "
          f"毛盈利 ¥{sum(wins):+,.0f} | 毛亏损 ¥{sum(losses):+,.0f} | "
          f"盈亏比 {sum(wins) / abs(sum(losses)):.2f}" if losses else "")

    # ------------------------------------------------------------- ⑤ 持仓特征
    print("\n" + "─" * 78)
    print("⑤ 持仓特征与换手")
    print("─" * 78)
    n_holds = [h["n_hold"] for h in strategy.history]
    top5s, hhi, industries = [], [], set()
    for h in strategy.history:
        ws = sorted(h["weights"].values(), reverse=True)
        top5s.append(sum(ws[:5]))
        hhi.append(sum(w * w for w in ws))
        industries.update(h["by_label"].keys())
    print(f"  期均持仓数     {sum(n_holds) / len(n_holds):.1f} 只"
          f"（{min(n_holds)}–{max(n_holds)}）")
    print(f"  前 5 大权重    期均 {sum(top5s) / len(top5s):.0%}")
    print(f"  HHI 集中度     期均 {sum(hhi) / len(hhi):.2f}"
          f"（1/N 均衡 ≈ {1 / (sum(n_holds) / len(n_holds)):.2f}）")
    print(f"  覆盖行业       {len(industries)} 个："
          f"{'、'.join(sorted(industries))}")
    # 换手
    prev_w: dict[str, float] = {}
    print("\n  各期换手（单边）：")
    for h in strategy.history:
        w = h["weights"]
        if prev_w:
            to = sum(abs(w.get(t, 0) - prev_w.get(t, 0))
                     for t in set(list(w) + list(prev_w))) / 2
        else:
            to = sum(w.values())
        kept = len(set(w) & set(prev_w))
        print(f"    {h['dt']}: 换手 {to:.0%} | 新进 "
              f"{len(set(w) - set(prev_w))} | 留用 {kept} | 清仓 "
              f"{len(set(prev_w) - set(w))}")
        prev_w = w

    # NAV 保存
    nav_rows = []
    for r in daily:
        mk = r["dt"]
        if mk in bench and bench.get(mk):
            nav_rows.append({"month": mk, "nav": r["balance"],
                             "bench": bench[mk]})
    json.dump(nav_rows, open("_bt_uni_nav.json", "w", encoding="utf-8"))
    print(f"\n  NAV 路径已保存 → _bt_uni_nav.json（{len(nav_rows)} 个月）")


if __name__ == "__main__":
    main()
