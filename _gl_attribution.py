# -*- coding: utf-8 -*-
"""growth_loop 回测持仓明细 + 个股贡献归因（重放引擎，捕获逐笔成交）。

口径（诚实标注）：
  1. 个股贡献 = 该股全部月份 net_pnl 之和（holding_pnl + trading_pnl - 佣金），
     精确等于组合总收益的加总（balance 由逐期 net_pnl 累计重建）。
  2. 持仓明细以调仓月下单、次月撮合后的实际股数/成本为准（vnpy 语义：
     信息在 N 期，成交在 N+1 期，无前视）。
  3. 只含 HOOK 层（H1/H2/H6）+ B 补位；LOOP 层 LLM 深研无法诚实回测。
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData  # noqa: E402
from src.backtest.strategy import (StrategyTemplate,      # noqa: E402
                                   avail_financials)
from src.core.models import Signal                        # noqa: E402
from src.signals.hooks import evaluate_hooks              # noqa: E402

CAPITAL = 1_000_000
PER_NAME_CAP = 0.08

SEL_FILE = "_bt_pit_selection.json"
FIN_FILE = "_bt_pit_financials.json"
PRICES_FILE = "_bt_pit_prices.json"
WARMUP_FILE = "_bt_pit_warmup.json"
BENCH_FILE = "_bt_benchmark.json"

REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]

CUR_DT = [""]


# ---------------------------------------------------------------------------
# 复用 backtest_growth_loop 的 HOOK 筛选逻辑（确定性规则，可复现）
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


def build_signals(fin_at: dict, candidates: list[tuple], prices_all: dict,
                  min_holdings: int = 20) -> tuple[list[Signal], dict]:
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
            conv = 0.30
            signals.append(Signal(
                model_name="growth_loop", ticker=tk,
                date=CUR_DT[0] + "-28", value=conv,
                reasoning=f"B-fill yoy={yoy0:.0%}"))
            detail[tk] = {"name": name, "sw1": sw1, "hooks": [],
                          "yoy": yoy0, "dd": None, "conviction": conv,
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
# 重放 + 归因
# ---------------------------------------------------------------------------

def main():
    sel = json.loads(open(SEL_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    prices_all = {tk: {**warmup.get(tk, {}), **m}
                  for tk, m in prices.items()}

    weights_by_dt, detail_by_dt = {}, {}
    for month in REBALANCES:
        if month not in sel:
            continue
        as_of = sel[month]["as_of"]
        fin_at = avail_financials(financials, as_of)
        CUR_DT[0] = month
        signals, detail = build_signals(fin_at, sel[month]["candidates"],
                                        prices_all)
        weights_by_dt[month] = blend_weights(signals)
        detail_by_dt[month] = detail

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
    engine.run_backtesting()
    daily = engine.calculate_result()
    engine.calculate_statistics(daily, output=False)

    # ---- 归因计算 ----
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())
    total_ret = bal[dts[-1]] - CAPITAL

    # 1) 个股贡献：逐月 net_pnl 累计（daily_results 的合约级 PnL）
    stock_pnl: dict[str, float] = {}
    stock_periods: dict[str, dict] = {}
    pnl_by_dt: dict[str, dict[str, float]] = {}
    for dt in dts:
        res = engine.daily_results.get(dt)
        if not res:
            continue
        per_dt: dict[str, float] = {}
        for sym, c in res.contracts.items():
            stock_pnl[sym] = stock_pnl.get(sym, 0.0) + c.net_pnl
            if c.net_pnl != 0.0:
                per_dt[sym] = c.net_pnl
            if c.start_pos or c.trades:
                sp = stock_periods.setdefault(
                    sym, {"first": None, "last": None})
                sp["first"] = sp["first"] or dt
                sp["last"] = dt
        pnl_by_dt[dt] = per_dt
    # 股票名称/行业
    name_of, ind_of, tier_of, hooks_of = {}, {}, {}, {}
    for month, det in detail_by_dt.items():
        for tk, d in det.items():
            name_of[tk] = d["name"]
            ind_of[tk] = d["sw1"]
            tier_of[tk] = d["tier"]
            hooks_of[tk] = "+".join(d["hooks"]) if d["hooks"] else "B补位"

    # 2) 每只股票交易摘要（首买价 / 末卖价 / 净买入金额）
    trade_sum: dict[str, dict] = {}
    for t in engine.trades:
        s = trade_sum.setdefault(t.symbol, {
            "buys": 0.0, "sells": 0.0, "buy_cost": 0.0, "sell_proc": 0.0,
            "first_buy": None, "last_sell": None})
        if t.direction == "LONG":
            s["buys"] += t.volume
            s["buy_cost"] += t.turnover + t.commission
            s["first_buy"] = s["first_buy"] or t.dt
        else:
            s["sells"] += t.volume
            s["sell_proc"] += t.turnover - t.commission
            s["last_sell"] = t.dt

    # 3) 期末市值（末月 close × 末月 pos）
    end_pos: dict[str, float] = {}
    for t in engine.trades:
        dv = t.volume if t.direction == "LONG" else -t.volume
        end_pos[t.symbol] = end_pos.get(t.symbol, 0.0) + dv
    last_dt = dts[-1]
    close_last = {}
    for sym, m in bars.items():
        c = m.get(last_dt)
        if c:
            close_last[sym] = c.close_price

    # 4) 持仓期间（首买 → 末卖/期末）价格表现（近似口径）
    hold_perf: dict[str, dict] = {}
    for sym in stock_pnl:
        buys = trade_sum.get(sym, {})
        first_buy = buys.get("first_buy")
        sell_dt = buys.get("last_sell")
        prices_sym = prices_all.get(sym, {})
        p_enter = prices_sym.get(first_buy) if first_buy else None
        if end_pos.get(sym, 0.0) > 0:      # 期末仍持有 → 用期末价
            p_exit = close_last.get(sym)
            exit_lab = "期末持有"
        else:                              # 已清仓 → 用最后卖出月价
            p_exit = prices_sym.get(sell_dt) if sell_dt else close_last.get(sym)
            exit_lab = sell_dt or "期末"
        ret = (p_exit / p_enter - 1.0
               if p_enter and p_exit and p_enter > 0 else None)
        hold_perf[sym] = {"enter": first_buy, "exit": exit_lab,
                          "p_enter": p_enter, "p_exit": p_exit,
                          "price_ret": ret}

    # 5) 逐期持仓明细（调仓目标 → 撮合后实际）
    period_holds: list[dict] = []
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        nxt = (strategy.history[i + 1]["dt"]
               if i + 1 < len(strategy.history) else last_dt)
        # 撮合发生在调仓次月；实际持仓取次月撮合后的 pos 快照
        fill_dt = next((d for d in dts if d > mk), last_dt)
        pos_snap: dict[str, float] = {}
        for t in engine.trades:
            if t.dt <= fill_dt:
                dv = t.volume if t.direction == "LONG" else -t.volume
                pos_snap[t.symbol] = pos_snap.get(t.symbol, 0.0) + dv
        # 区间收益
        ret_span = bal.get(nxt, bal[last_dt]) / bal[mk] - 1
        rows = []
        for tk, w in sorted(h["weights"].items(), key=lambda x: -x[1]):
            px_fill = None
            bar = bars.get(tk, {}).get(fill_dt)
            if bar:
                px_fill = bar.close_price
            sh = pos_snap.get(tk, 0.0)
            cost = 0.0
            for t in engine.trades:
                if t.symbol == tk and t.dt <= fill_dt:
                    cost += (t.turnover + t.commission if t.direction ==
                             "LONG" else -(t.turnover - t.commission))
            rows.append({
                "dt": mk, "ticker": tk, "name": name_of.get(tk, tk),
                "sw1": ind_of.get(tk, ""), "tier": tier_of.get(tk, "?"),
                "hooks": hooks_of.get(tk, ""),
                "target_w": w, "shares": sh,
                "fill_price": px_fill, "cost_basis": cost,
                "mkt_val": sh * px_fill if sh and px_fill else 0.0,
            })
        period_holds.append({
            "dt": mk, "n": len(rows), "equity": h["equity"],
            "ret_span": ret_span,
            "gross": sum(h["weights"].values()),
            "rows": rows})
        # 期间个股贡献（下单月 → 下次下单月之间的逐月 pnl 之和）
        if nxt == last_dt:                    # 最后一期：含期末月
            span_dts = [x for x in dts if x >= mk]
        else:
            span_dts = [x for x in dts if mk <= x < nxt]
        span_pnl: dict[str, float] = {}
        for sd in span_dts:
            for sym, v in pnl_by_dt.get(sd, {}).items():
                span_pnl[sym] = span_pnl.get(sym, 0.0) + v
        for r in period_holds[-1]["rows"]:
            r["span_pnl"] = span_pnl.get(r["ticker"], 0.0)

    # 只保留实际交易过的股票（net_pnl != 0 或曾有持仓市值）
    traded = {sym for sym in stock_pnl
              if stock_pnl[sym] != 0.0 or end_pos.get(sym, 0.0) > 0
              or trade_sum.get(sym, {}).get("buys", 0.0) > 0}
    stock_pnl = {k: v for k, v in stock_pnl.items() if k in traded}
    pos_sum = sum(v for v in stock_pnl.values() if v > 0)
    neg_sum = sum(v for v in stock_pnl.values() if v < 0)
    by_tier: dict[str, float] = {}
    by_hook: dict[str, float] = {}
    by_ind: dict[str, float] = {}
    for sym, v in stock_pnl.items():
        tier = tier_of.get(sym, "?")
        by_tier[tier] = by_tier.get(tier, 0.0) + v
        hk = hooks_of.get(sym, "")
        by_hook[hk] = by_hook.get(hk, 0.0) + v
        ind = ind_of.get(sym, "")
        by_ind[ind] = by_ind.get(ind, 0.0) + v

    out = {
        "capital": CAPITAL,
        "start": dts[0], "end": dts[-1],
        "end_balance": bal[dts[-1]],
        "total_return": total_ret,
        "total_return_pct": total_ret / CAPITAL,
        "bench_return": bench.get(dts[-1], 0) / bench.get(dts[0], 1) - 1
        if bench.get(dts[0]) else None,
        "pos_contrib_sum": pos_sum, "neg_contrib_sum": neg_sum,
        "n_stocks": len(stock_pnl),
        "by_tier": by_tier, "by_hook": by_hook, "by_ind": by_ind,
        "stock_pnl": {sym: {"name": name_of.get(sym, sym),
                            "ind": ind_of.get(sym, ""),
                            "tier": tier_of.get(sym, "?"),
                            "hooks": hooks_of.get(sym, ""),
                            "net_pnl": v,
                            "pct_of_total": v / total_ret if total_ret
                            else 0.0,
                            "first": stock_periods.get(sym, {}).get("first"),
                            "last": stock_periods.get(sym, {}).get("last"),
                            "net_buy_amount": (trade_sum.get(sym, {}).get(
                                "buy_cost", 0.0) - trade_sum.get(
                                sym, {}).get("sell_proc", 0.0)),
                            "end_mkt_val": (end_pos.get(sym, 0.0)
                                            * close_last.get(sym, 0.0)),
                            "hold": hold_perf.get(sym, {}),
                            }
                       for sym, v in sorted(stock_pnl.items(),
                                            key=lambda x: -x[1])},
        "periods": period_holds,
    }
    json.dump(out, open("_gl_attribution.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # CSV: 个股贡献
    with open("_gl_stock_contribution.csv", "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "name", "industry", "tier", "hooks",
                    "net_pnl", "pct_of_total", "first_month",
                    "last_month", "net_buy_amount", "end_mkt_val",
                    "enter_month", "exit_month", "price_ret"])
        for sym, s in out["stock_pnl"].items():
            hp = s["hold"]
            w.writerow([sym, s["name"], s["ind"], s["tier"], s["hooks"],
                        round(s["net_pnl"], 2),
                        round(s["pct_of_total"], 6), s["first"], s["last"],
                        round(s["net_buy_amount"], 2),
                        round(s["end_mkt_val"], 2),
                        hp.get("enter"), hp.get("exit"),
                        round(hp["price_ret"], 6) if hp.get("price_ret")
                        is not None else ""])

    # CSV: 逐期持仓
    with open("_gl_holdings_detail.csv", "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["period", "ticker", "name", "industry", "tier",
                    "hooks", "target_w", "shares", "fill_price",
                    "cost_basis", "mkt_val"])
        for p in period_holds:
            for r in p["rows"]:
                w.writerow([p["dt"], r["ticker"], r["name"], r["sw1"],
                            r["tier"], r["hooks"], round(r["target_w"], 4),
                            int(r["shares"]), round(r["fill_price"], 2)
                            if r["fill_price"] else "",
                            round(r["cost_basis"], 2),
                            round(r["mkt_val"], 2)])

    # ---- 控制台摘要 ----
    print(f"总收益: {total_ret:+,.0f} ({total_ret/CAPITAL:+.1%}) "
          f"| {dts[0]} → {dts[-1]}")
    print(f"个股贡献合计: {sum(stock_pnl.values()):+,.0f} "
          f"(应≈总收益)")
    print(f"正贡献合计 {pos_sum:+,.0f} / 负贡献合计 {neg_sum:+,.0f} | "
          f"实际交易 {len(stock_pnl)} 只")
    print(f"按层级: {json.dumps(by_tier, ensure_ascii=False)}")
    print(f"按hook: {json.dumps({k: round(v) for k, v in sorted(by_hook.items(), key=lambda x: -x[1])[:8]}, ensure_ascii=False)}")
    print("\n贡献 TOP 10:")
    for sym, s in list(out["stock_pnl"].items())[:10]:
        print(f"  {sym} {s['name']:8s} {s['ind']:6s} {s['tier']} "
              f"{s['hooks']:10s} {s['net_pnl']:+,.0f} "
              f"({s['pct_of_total']:+.1%})")
    print("\n贡献 BOTTOM 10:")
    for sym, s in list(out["stock_pnl"].items())[-10:]:
        print(f"  {sym} {s['name']:8s} {s['ind']:6s} {s['tier']} "
              f"{s['hooks']:10s} {s['net_pnl']:+,.0f} "
              f"({s['pct_of_total']:+.1%})")
    print("\n逐期持仓:")
    for p in period_holds:
        print(f"  [{p['dt']}] {p['n']} 只 gross {p['gross']:.0%} "
              f"区间 {p['ret_span']:+.1%}")
    print("\n输出: _gl_attribution.json / _gl_stock_contribution.csv / "
          "_gl_holdings_detail.csv")


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
        self.history.append({
            "dt": dt, "n": len(weights), "equity": equity,
            "weights": weights})


if __name__ == "__main__":
    main()
