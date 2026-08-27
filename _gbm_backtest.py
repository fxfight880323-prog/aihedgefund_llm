"""GBM量价因子 × 万得全A PIT 池 全市场诚实回测（无池子偏差）。

问题：申万金工 GBM量价（LightGBM 周频量价 ML 因子，IC 0.114/IR 0.85 全库最强）
在万得全A PIT 成分池上到底有没有超额？还是只是小市值/低波风格 beta？

方法（方法论铁律：先对比等权池子再下结论）：
- 池子 = 万得全A(881001.WI) 每期 PIT 成分（4441 → 5503 只）
- 信号 = 申万金工 GBM量价 月末快照值（每期对全成分股拉取）
- 组合 = 每期按 GBM 值排序取 top-N，等权持有，半年度再平衡，同引擎同成本(5bp+10bp)
- 基准 = EW-全A（同池子等权 NAV，真实月K）+ CSI-全指（市值加权）+ LX-core（刘旭最强方法论）

变体：
- gbm40      top-40 等权（核心）
- gbm20      top-20（更集中）
- gbm60      top-60（更分散）
- gbmLow40   GBM 值最低 40 只（多空方向对照）
- gbm40_mv100 top-40 + 市值≥100亿（剔除小市值后 alpha 是否还在 → 市值归因）

诊断：
- 每期 top-40 市值分布 vs 全池（total_mv 万元→亿）→ 超额是否=小市值 beta
- 每自然年组合 vs EW-全A 超额
- 相邻期换手率

数据文件:
  _bt_winda_universe.json  万得全A PIT 成分
  _bt_gbm_values.json      GBM量价 因子值（本次拉取）
  _bt_winda_prices.json    全市场真实月K
  _bt_winda_index.json     中证全指
  _bt_lx_allA_valuation.json  估值面板（total_mv）
  _bt_lx_allA_results.json 刘旭变体结果（对比）
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate

CAPITAL = 1_000_000
PIT_DATES = [
    ("2021-08", "2021-08-31"),
    ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"),
    ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"),
    ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"),
    ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"),
    ("2026-04", "2026-04-30"),
]
REBALANCES = [d[0] for d in PIT_DATES]

UNIV_FILE = "_bt_winda_universe.json"
GBM_FILE = "_bt_gbm_values.json"
PRICES_FILE = "_bt_winda_prices.json"
INDEX_FILE = "_bt_winda_index.json"
VAL_FILE = "_bt_lx_allA_valuation.json"
LX_FILE = "_bt_lx_allA_results.json"
OUT = "_bt_gbm_results.json"

TOP_N = 40
MAX_HOLDINGS = 40
MV_FLOOR_YI = 100.0


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def load_universe() -> dict[str, list[str]]:
    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    return {m: d.get("members", []) for m, d in univ.items()}


def load_gbm() -> dict[str, dict[str, float]]:
    d = json.loads(open(GBM_FILE, encoding="utf-8").read())
    out: dict[str, dict[str, float]] = {}
    for month, rec in d.items():
        out[month] = {tk: v for tk, v in rec.items() if _num(v) is not None}
    return out


def load_val() -> dict[str, dict[str, dict]]:
    d = json.loads(open(VAL_FILE, encoding="utf-8").read())
    out: dict[str, dict[str, dict]] = {}
    for month, m in d.items():
        rec = {}
        for r in m.get("records", []):
            sc = r.get("stock_code", "")
            if "." not in sc:
                continue
            code, mkt = sc.split(".")
            tk = f"{code}.SH" if code[0] == "6" else f"{code}.SZ" if code[0] in ("0", "3") else f"{code}.BJ"
            rec[tk] = r
        out[month] = rec
    return out


def _members_at(univ: dict[str, list[str]], mk: str) -> set[str]:
    pick = None
    for m, a in PIT_DATES:
        if a[:7] <= mk:
            pick = m
        else:
            break
    return set(univ.get(pick, []) if pick else [])


def ew_universe_nav(univ: dict[str, list[str]], prices: dict,
                    months: list[str]) -> dict[str, float]:
    nav: dict[str, float] = {}
    prev_px: dict[str, float] = {}
    cur_nav = 1.0
    for mk in sorted(months):
        members = _members_at(univ, mk)
        rets = []
        for tk in members:
            p_prev = prev_px.get(tk)
            p_cur = prices.get(tk, {}).get(mk)
            if p_prev and p_cur and p_prev > 0:
                rets.append(p_cur / p_prev - 1.0)
        if rets:
            cur_nav *= (1.0 + sum(rets) / len(rets))
        nav[mk] = cur_nav
        prev_px = {tk: prices.get(tk, {}).get(mk)
                   for tk in members if prices.get(tk, {}).get(mk)}
    return nav


# ---- 组合构造 ----

def gbm_picks(gbm: dict[str, float], univ: list[str], val: dict,
              top_n: int, low: bool = False, mv_floor: float = 0.0):
    pool = []
    for tk in univ:
        g = _num(gbm.get(tk))
        if g is None:
            continue
        if mv_floor > 0:
            mv = _num((val.get(tk) or {}).get("total_mv"))
            if mv is None or mv < mv_floor * 10000:
                continue
        pool.append((tk, g))
    pool.sort(key=lambda x: -x[1] if not low else x[1])
    picks = pool[:top_n]
    return picks, len(pool), len(pool) / len(univ) if univ else 0.0


def weights_from(picks) -> dict[str, float]:
    if not picks:
        return {}
    w = 1.0 / len(picks)
    return {tk: w for tk, _ in picks}


# ---- 引擎 ----

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


def run_variant(name: str, weights_by_dt: dict, bars: dict, bench: dict) -> dict:
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {"weights_by_dt": weights_by_dt})
    engine.add_strategy(strategy)
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)

    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(d for d in bal if d in bench)
    if len(dts) < 2:
        return {"name": name, "total": 0.0, "ann": 0.0, "mdd": 0.0, "nav": []}
    total = bal[dts[-1]] / bal[dts[0]] - 1
    yrs = len(dts) / 12
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1
    mdd = stats.get("max_ddpercent", 0) / 100.0
    nav = [{"month": d, "nav": bal[d]} for d in dts]
    return {"name": name, "total": total, "ann": ann, "mdd": mdd, "nav": nav}


def yearly_returns(nav: list[dict], bench_nav: list[dict]) -> dict[str, dict]:
    """按自然年聚合组合与基准收益。"""
    def agg(rows):
        by_year = {}
        for r in rows:
            y = r["month"][:4]
            by_year.setdefault(y, []).append(r["nav"])
        out = {}
        for y, vals in by_year.items():
            out[y] = vals[-1] / vals[0] - 1 if vals[0] > 0 else None
        return out

    a = agg(nav)
    b = agg(bench_nav)
    years = sorted(set(a) & set(b))
    return {y: {"strategy": a[y], "bench": b[y],
                "excess": (a[y] - b[y]) if (a[y] is not None and b[y] is not None) else None}
            for y in years}


def turnover(prev: dict, cur: dict) -> float | None:
    if not prev:
        return None
    s_prev, s_cur = set(prev), set(cur)
    return 1.0 - len(s_prev & s_cur) / max(len(s_prev), 1)


def main():
    print("=" * 78)
    print("  GBM量价 × 万得全A PIT 池 全市场回测（无池子偏差）")
    print("=" * 78)

    univ = load_universe()
    gbm = load_gbm()
    val = load_val()
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    index = json.loads(open(INDEX_FILE, encoding="utf-8").read())
    print(f"万得全A 成分: {[len(univ[m]) for m in REBALANCES]}")
    print(f"GBM 值覆盖: {[len(gbm[m]) for m in REBALANCES]}")

    bars = {}
    for tk, m in prices.items():
        mm = {mk: px for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        if mm:
            bars[tk] = {mk: BarData(tk, mk, px, px, px, px) for mk, px in mm.items()}
    all_months = sorted({mk for m in bars.values() for mk in m})

    # 基准
    print("\n① 基准")
    ew = ew_universe_nav(univ, prices, all_months)
    idx = {mk: v for mk, v in index.items() if mk in all_months}
    bench_months = sorted(ew.keys())
    n0 = bench_months[0]
    bench_ew = {mk: ew[mk] / ew[n0] for mk in bench_months}
    if n0 in idx:
        base_idx = idx[n0]
        bench_idx = {mk: idx[mk] / base_idx for mk in bench_months if mk in idx}
    else:
        bench_idx = None
    print(f"  等权全A: {bench_months[0]}~{bench_months[-1]} "
          f"{len(bench_months)} 个月 | 终值 {bench_ew[bench_months[-1]]:.3f}")
    if bench_idx:
        print(f"  中证全指: 终值 {bench_idx[bench_months[-1]]:.3f}")

    # 变体权重
    SPECS = [
        ("gbm40", {"top_n": 40, "low": False, "mv_floor": 0.0}),
        ("gbm20", {"top_n": 20, "low": False, "mv_floor": 0.0}),
        ("gbm60", {"top_n": 60, "low": False, "mv_floor": 0.0}),
        ("gbmLow40", {"top_n": 40, "low": True, "mv_floor": 0.0}),
        ("gbm40_mv100", {"top_n": 40, "low": False, "mv_floor": MV_FLOOR_YI}),
    ]
    all_weights: dict[str, dict[str, dict[str, float]]] = {}
    all_diag: dict[str, dict] = {}
    prev_hold: dict[str, set[str]] = {}

    print("\n② 每期选股")
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        g = gbm.get(month, {})
        v = val.get(month, {})
        all_diag[month] = {"univ": len(members), "gbm_cov": len(g),
                           "gbm_cov_pct": len(g) / len(members) if members else 0.0}
        line = f"  [{month}] univ={len(members)} gbm覆盖={len(g)}"
        for vname, spec in SPECS:
            picks, pool_n, cov = gbm_picks(g, members, v, spec["top_n"],
                                           spec["low"], spec["mv_floor"])
            all_weights.setdefault(vname, {})[month] = weights_from(picks)
            to = turnover(prev_hold.get(vname), set(tk for tk, _ in picks))
            prev_hold[vname] = set(tk for tk, _ in picks)
            # 市值诊断
            mvs = [_num((v.get(tk) or {}).get("total_mv")) for tk, _ in picks]
            mvs = [m / 10000 for m in mvs if m]  # 万元→亿
            med = sorted(mvs)[len(mvs) // 2] if mvs else None
            small = (sum(1 for m in mvs if m < 30) / len(mvs)) if mvs else None
            mid = (sum(1 for m in mvs if 30 <= m < 100) / len(mvs)) if mvs else None
            big = (sum(1 for m in mvs if m >= 100) / len(mvs)) if mvs else None
            all_diag[month][f"{vname}_med_mv"] = med
            all_diag[month][f"{vname}_small_pct"] = small
            all_diag[month][f"{vname}_mid_pct"] = mid
            all_diag[month][f"{vname}_big_pct"] = big
            all_diag[month][f"{vname}_turnover"] = to
            line += f" | {vname}={len(picks)}(中位市值{med:.0f}亿, 换手{to if to is None else f'{to:.0%}'})"
        print(line)

    # 引擎回测
    print("\n③ 引擎回测（5bp+10bp 成本）")
    bench_ew_nav = [{"month": m, "nav": v} for m, v in bench_ew.items()]
    results = {}
    for vname in [s[0] for s in SPECS]:
        r = run_variant(vname, all_weights[vname], bars, bench_ew)
        results[vname] = r
        print(f"  {vname:14s} 总收益 {r['total']:+8.1%}  年化 {r['ann']:+7.1%}  MDD {r['mdd']:7.1%}")

    # 基准行
    r_ew = {"name": "EW-全A", "total": bench_ew[bench_months[-1]] - 1,
            "ann": (bench_ew[bench_months[-1]]) ** (12 / len(bench_months)) - 1,
            "mdd": None, "nav": bench_ew_nav}
    r_idx = None
    if bench_idx:
        r_idx = {"name": "CSI-全指",
                 "total": bench_idx[bench_months[-1]] - 1,
                 "ann": (bench_idx[bench_months[-1]]) ** (12 / len(bench_months)) - 1,
                 "mdd": None,
                 "nav": [{"month": m, "nav": v} for m, v in bench_idx.items()]}
    print(f"  {'EW-全A':14s} 总收益 {r_ew['total']:+8.1%}  年化 {r_ew['ann']:+7.1%}")

    # 刘旭对比（引用）
    lx = json.loads(open(LX_FILE, encoding="utf-8").read())
    lx_core = lx["results"].get("core", {})

    # 分年 + 换手
    print("\n④ 分年度收益（组合 vs EW-全A）")
    yearly = {}
    for vname in [s[0] for s in SPECS]:
        yr = yearly_returns(results[vname]["nav"], bench_ew_nav)
        yearly[vname] = yr
        print(f"  {vname:14s} " + " ".join(
            f"{y}: {d['strategy']*100:+.1f}/{d['excess']*100:+.1f}pp"
            for y, d in yr.items()))

    out = {
        "meta": {
            "pool": "万得全A(881001.WI) PIT 成分",
            "factor": "申万金工 GBM量价（LightGBM 周频 ML 因子, 月末快照）",
            "rebalance": "半年度, 同引擎同成本 5bp+10bp",
            "period": f"{bench_months[0]} ~ {bench_months[-1]}",
            "generated": "2026-08-24",
        },
        "results": results,
        "ew": r_ew,
        "idx": r_idx,
        "lx_core": lx_core,
        "weights": all_weights,
        "diag": all_diag,
        "yearly": yearly,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n已保存 {OUT}")


if __name__ == "__main__":
    main()
