"""Portfolio-sort group analysis for F-Score / C-Score x BM matrices.

Classic expectation-gap sort test (Piotroski-So style), answering:
  1. Do group returns show the predicted ordering? (undervalued > overvalued)
  2. Is the ordering CONSISTENT across periods? (hit rate / sign test)
  3. Is mean excess return statistically distinguishable from zero?
     (one-sample t-test on period excess returns, paired t on spreads)
  4. Stock-level rank IC per period (Spearman), mean IC + t-test.

Groups (within the already-filtered value pool, PB<2 PE<20 mcap>50亿):
  C-buckets: C<=1 | C=2 | C>=3   x BM terciles (high/mid/low, pool-internal)
  F-buckets: F<=4 | F=5-6 | F>=7 x same BM terciles
  Expectation classes: undervalued / moderate / congruent / speculative /
                       neutral / overvalued  (both matrices)

Forward return: equal-weighted close(M) -> close(M_next), M_next = next
rebalance month (last period 2026-04 -> 2026-08). GROSS returns (no costs).

Run:
    python examples/group_analysis.py          # uses/extends price cache
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.signals.f_score import calculate_f_score, classify_expectation, _safe
from src.signals.c_score import (
    calculate_c_score,
    classify_consensus_expectation,
)
from backtest_f_score import (
    PIT_DATES, norm_ticker, fetch_prices, fetch_benchmark, PE_MAX, PB_MAX,
)
from backtest_c_score import load_consensus

PRICES_FILE = "_bt_fscore_prices.json"
OUT_FILE = "_bt_group_analysis.json"

try:
    from scipy import stats as sps
except ImportError:
    sps = None


# ===========================================================================
# Stats helpers
# ===========================================================================

def t_test(xs: list[float]) -> dict:
    """One-sample t-test, H0: mean = 0."""
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": None, "t": None, "p": None}
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    se = sd / math.sqrt(n)
    t = mean / se if se > 0 else (math.inf if mean > 0 else -math.inf)
    if sps is not None:
        p = 2 * (1 - sps.t.cdf(abs(t), n - 1))
    else:
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return {"n": n, "mean": mean, "t": t, "p": p}


def sign_test(xs: list[float]) -> dict:
    """Two-sided sign test, H0: median = 0 (P(positive)=0.5)."""
    n_pos = sum(1 for x in xs if x > 0)
    n = sum(1 for x in xs if x != 0)
    if n == 0:
        return {"n": 0, "pos": 0, "p": None}
    if sps is not None:
        p = sps.binomtest(n_pos, n, 0.5).pvalue
    else:
        # normal approx
        z = (n_pos - n / 2) / math.sqrt(n / 4)
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return {"n": n, "pos": n_pos, "p": p}


def spearman(a: list[float], b: list[float]) -> float | None:
    if sps is not None:
        r = sps.spearmanr(a, b).statistic
        return None if math.isnan(r) else r
    # manual
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        for r, i in enumerate(order):
            rk[i] = r + 1.0
        return rk
    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va > 0 and vb > 0 else None


# ===========================================================================
# Panel construction
# ===========================================================================

def next_month(i: int) -> str:
    """Forward window end for the i-th rebalance."""
    if i + 1 < len(PIT_DATES):
        return PIT_DATES[i + 1][0]
    return "2026-08"   # last selection period -> latest cached prices


def build_panel(sel: dict, cons: dict, prices: dict) -> list[dict]:
    """One record per (period, stock): scores + terciles + forward return."""
    panel = []
    for i, (month, as_of, cn_period, cn_prev) in enumerate(PIT_DATES):
        if month not in sel:
            continue
        m_next = next_month(i)
        candidates = sel[month]["candidates"]
        cons_map = cons.get(month, {})

        pbs = [c["pb"] for c in candidates if c["pb"] and c["pb"] > 0]
        if len(pbs) < 5:
            continue
        pb_p33 = sorted(pbs)[len(pbs) // 3]
        pb_p67 = sorted(pbs)[len(pbs) * 2 // 3]

        for c in candidates:
            tk = c["tk"]
            pb = _safe(c.get("pb"))
            pe = _safe(c.get("pe"))
            if pb is None or pb <= 0 or pb > PB_MAX:
                continue
            if pe is not None and pe > PE_MAX:
                continue

            px0 = prices.get(tk, {}).get(month)
            px1 = prices.get(tk, {}).get(m_next)
            fwd = (px1 / px0 - 1) if (px0 and px1 and px0 > 0 and px1 > 0) \
                else None

            f_score, _ = calculate_f_score(c["curr"], c["prev"])
            bm_tercile = "high" if pb <= pb_p33 else (
                "low" if pb >= pb_p67 else "mid")

            rec = cons_map.get(tk)
            c_score = None
            if rec:
                c_score, _ = calculate_c_score(rec)

            panel.append({
                "month": month, "tk": tk, "pb": pb, "bm": 1.0 / pb,
                "bm_tercile": bm_tercile, "f": f_score, "c": c_score,
                "fwd": fwd, "has_price": fwd is not None,
            })
    return panel


# ===========================================================================
# Group aggregation
# ===========================================================================

def group_stats(panel: list[dict], key_fn, label_fn=None) -> dict:
    """Per-group: per-period EW returns -> mean excess, hit rate, t/p."""
    # group -> month -> [returns]
    per = {}
    counts = {}
    for r in panel:
        if r["fwd"] is None:
            continue
        g = key_fn(r)
        if g is None:
            continue
        per.setdefault(g, {}).setdefault(r["month"], []).append(r["fwd"])
        counts[g] = counts.get(g, 0) + 1

    # benchmark excess per (group, month)
    bench = fetch_benchmark()

    def bench_ret(m0: str, m1: str):
        if m0 in bench and m1 in bench:
            return bench[m1] / bench[m0] - 1
        return None

    month_pairs = {}
    for i, (month, *_rest) in enumerate(PIT_DATES):
        month_pairs[month] = bench_ret(month, next_month(i))

    out = {}
    for g, months in per.items():
        rets, excess, ns, month_list = [], [], [], []
        for m in sorted(months.keys()):
            rs = months[m]
            rets.append(sum(rs) / len(rs))
            ns.append(len(rs))
            month_list.append(m)
            br = month_pairs.get(m)
            if br is not None:
                excess.append(rets[-1] - br)
        tt_r = t_test(rets)
        tt_e = t_test(excess)
        st_e = sign_test(excess)
        out[g] = {
            "periods": len(rets), "avg_n": sum(ns) / len(ns),
            "stock_obs": counts[g],
            "mean_ret": tt_r["mean"], "ret_t": tt_r["t"], "ret_p": tt_r["p"],
            "mean_excess": tt_e["mean"], "exc_t": tt_e["t"],
            "exc_p": tt_e["p"],
            "hit_rate": st_e["pos"] / st_e["n"] if st_e["n"] else None,
            "sign_p": st_e["p"],
            "by_month": dict(zip(month_list, rets)),
            "excess_by_month": dict(zip(
                month_list[:len(excess)], excess)),
        }
    return out


def spread_test(panel: list[dict], g_hi, g_lo, key_fn) -> dict:
    """Paired spread: EW(g_hi) - EW(g_lo) per period, t-test + sign test."""
    def ew(g_filter):
        per = {}
        for r in panel:
            if r["fwd"] is None or not g_filter(r):
                continue
            per.setdefault(r["month"], []).append(r["fwd"])
        return {m: sum(v) / len(v) for m, v in per.items()}

    a, b = ew(g_hi), ew(g_lo)
    months = sorted(set(a) & set(b))
    diffs = [a[m] - b[m] for m in months]
    tt = t_test(diffs)
    st = sign_test(diffs)
    return {
        "n": len(diffs), "mean_spread": tt["mean"], "t": tt["t"],
        "p": tt["p"], "pos_months": st["pos"], "hit_rate": st["pos"] / st["n"]
        if st["n"] else None, "sign_p": st["p"],
        "by_month": dict(zip(months, diffs)),
    }


def ic_series(panel: list[dict], field: str) -> dict:
    """Per-period Spearman IC: score vs forward return (covered stocks)."""
    per = {}
    for r in panel:
        if r["fwd"] is None or r.get(field) is None:
            continue
        per.setdefault(r["month"], []).append((r[field], r["fwd"]))
    ics = {}
    for m, pairs in per.items():
        a = [p[0] for p in pairs]
        b = [p[1] for p in pairs]
        ic = spearman(a, b)
        if ic is not None:
            ics[m] = ic
    vals = list(ics.values())
    tt = t_test(vals)
    st = sign_test(vals)
    return {
        "n": len(vals), "mean_ic": tt["mean"], "ic_t": tt["t"],
        "ic_p": tt["p"], "ic_ir": (tt["mean"] / (math.sqrt(
            sum((v - tt["mean"]) ** 2 for v in vals) / max(1, len(vals) - 1))
        ) if len(vals) > 1 and tt["mean"] else None),
        "pos_rate": st["pos"] / st["n"] if st["n"] else None,
        "by_month": ics,
    }


# ===========================================================================
# Report
# ===========================================================================

def fmt(v, pct=True, digits=1):
    if v is None:
        return "  —  "
    if pct:
        return f"{v:+.{digits}%}"
    return f"{v:+.{digits}f}"


def print_group_table(title: str, stats: dict, order: list[str]):
    print(f"\n  ── {title} " + "─" * max(0, 46 - len(title)))
    print(f"  {'分组':<14s}{'期数':>4s}{'均N':>6s}{'均值':>8s}"
          f"{'超额':>8s}{'t':>7s}{'p值':>8s}{'胜率':>7s}{'符号p':>8s}")
    for g in order:
        s = stats.get(g)
        if not s:
            continue
        star = "**" if (s["exc_p"] is not None and s["exc_p"] < 0.05) else ""
        print(f"  {g:<14s}{s['periods']:>4d}{s['avg_n']:>6.1f}"
              f"{fmt(s['mean_ret']):>8s}{fmt(s['mean_excess']):>8s}"
              f"{fmt(s['exc_t'], False, 2):>7s}"
              f"{fmt(s['exc_p'], False, 3) if s['exc_p'] is not None else '  —  ':>8s}"
              f"{fmt(s['hit_rate']) if s['hit_rate'] is not None else '—':>7s}"
              f"{fmt(s['sign_p'], False, 3) if s['sign_p'] is not None else '—':>8s}{star}")


def main():
    print("=" * 78)
    print("  分组收益一致性 + 显著性检验 · F-Score / C-Score × BM 矩阵")
    print("  池内排序(PB<2 PE<20 mcap>50亿 top100) | 等权 | 毛收益 | 10期")
    print("=" * 78)

    sel = json.loads(open("_bt_fscore_selection.json", encoding="utf-8").read())
    cons = load_consensus()

    pool = set()
    for d in sel.values():
        for c in d["candidates"]:
            pool.add(c["tk"])
    print(f"\n① 价格数据 (全池 {len(pool)} 只)")
    prices = fetch_prices(sorted(pool))

    print("\n② 构建面板")
    panel = build_panel(sel, cons, prices)
    n_price = sum(1 for r in panel if r["has_price"])
    n_cov = sum(1 for r in panel if r["c"] is not None)
    print(f"  股票-期观测 {len(panel)} | 有前向价格 {n_price} "
          f"({n_price/len(panel):.0%}) | 有一致预期 {n_cov} ({n_cov/len(panel):.0%})")

    # ---- C-Score x BM ----
    def c_bucket(r):
        if r["c"] is None:
            return None
        return "C>=3" if r["c"] >= 3 else ("C=2" if r["c"] == 2 else "C<=1")

    def c_cell(r):
        if r["c"] is None:
            return None
        return f"{c_bucket(r)}×{r['bm_tercile']}BM"

    # ---- F-Score x BM ----
    def f_bucket(r):
        return "F>=7" if r["f"] >= 7 else ("F=5-6" if r["f"] >= 5 else "F<=4")

    def f_cell(r):
        return f"{f_bucket(r)}×{r['bm_tercile']}BM"

    def c_expect(r):
        if r["c"] is None:
            return None
        return classify_consensus_expectation(r["c"], r["bm_tercile"])

    def f_expect(r):
        return classify_expectation(r["f"], r["bm_tercile"])

    c_stats = group_stats(panel, c_bucket)
    f_stats = group_stats(panel, f_bucket)
    c_cells = group_stats(panel, c_cell)
    f_cells = group_stats(panel, f_cell)
    c_exp = group_stats(panel, c_expect)
    f_exp = group_stats(panel, f_expect)

    print("\n③ C-Score 分组 (一致预期质量)")
    print_group_table("C-Score 主分档", c_stats, ["C>=3", "C=2", "C<=1"])
    print_group_table("C-Score × BM 矩阵", c_cells,
                      [f"{b}×{m}BM" for b in ("C>=3", "C=2", "C<=1")
                       for m in ("high", "mid", "low")])
    print_group_table("C-Score 期望类型", c_exp,
                      ["undervalued", "speculative", "moderate",
                       "congruent", "neutral", "overvalued"])

    print("\n④ F-Score 分组 (实际财报质量, 对照)")
    print_group_table("F-Score 主分档", f_stats, ["F>=7", "F=5-6", "F<=4"])
    print_group_table("F-Score × BM 矩阵", f_cells,
                      [f"{b}×{m}BM" for b in ("F>=7", "F=5-6", "F<=4")
                       for m in ("high", "mid", "low")])
    print_group_table("F-Score 期望类型", f_exp,
                      ["undervalued", "speculative", "moderate",
                       "congruent", "neutral", "overvalued"])

    # ---- Spreads ----
    print("\n⑤ 多空价差 (undervalued − overvalued, 配对)")
    spreads = {}
    for name, key in (("C矩阵", c_expect), ("F矩阵", f_expect)):
        sp = spread_test(panel, lambda r, k=key: k(r) == "undervalued",
                         lambda r, k=key: k(r) == "overvalued", key)
        spreads[name] = sp
        star = "**" if sp["p"] is not None and sp["p"] < 0.05 else ""
        print(f"  {name}: 月均价差 {fmt(sp['mean_spread'])} | t={sp['t']:+.2f} "
              f"| p={sp['p']:.3f}" if sp["p"] is not None else
              f"  {name}: n不足", f"| 胜率 {sp['hit_rate']:.0%}"
              if sp["hit_rate"] else "", star)
    # within high-BM: high score vs low score
    for name, bucket in (("C>=3 vs C<=1 @ 高BM", c_bucket),
                         ("F>=7 vs F<=4 @ 高BM", f_bucket)):
        sp = spread_test(
            panel,
            lambda r, b=bucket: r["bm_tercile"] == "high" and b(r) in
            ("C>=3", "F>=7"),
            lambda r, b=bucket: r["bm_tercile"] == "high" and b(r) in
            ("C<=1", "F<=4"),
            bucket)
        spreads[name] = sp
        if sp["p"] is not None:
            print(f"  {name}: 月均 {fmt(sp['mean_spread'])} | "
                  f"t={sp['t']:+.2f} | p={sp['p']:.3f} | "
                  f"胜率 {sp['hit_rate']:.0%}"
                  + ("**" if sp["p"] < 0.05 else ""))

    # ---- IC ----
    print("\n⑥ 个股层面 Rank IC (Spearman, 得分 vs 前向收益)")
    ics = {
        "C-Score": ic_series(panel, "c"),
        "F-Score": ic_series(panel, "f"),
        "BM(1/PB)": ic_series(panel, "bm"),
    }
    print(f"  {'因子':<10s}{'期数':>4s}{'均值IC':>8s}{'t':>7s}{'p值':>8s}"
          f"{'IC>0率':>7s}")
    for name, s in ics.items():
        if s["n"] == 0:
            print(f"  {name:<10s}  无观测")
            continue
        print(f"  {name:<10s}{s['n']:>4d}{s['mean_ic']:>8.3f}"
              f"{s['ic_t']:>7.2f}{s['ic_p']:>8.3f}{s['pos_rate']:>7.0%}"
              + ("**" if s["ic_p"] < 0.05 else ""))

    # IC by month table (C vs F)
    print("\n  分期 IC 对比 (C-Score / F-Score / BM):")
    months = sorted(set().union(*[set(s["by_month"].keys())
                                  for s in ics.values()]))
    for m in months:
        row = f"  {m}  "
        for name in ("C-Score", "F-Score", "BM(1/PB)"):
            v = ics[name]["by_month"].get(m)
            row += f"{v:+.3f}  " if v is not None else "  —    "
        print(row)

    # ---- Save ----
    out = {
        "panel_stats": {
            "obs": len(panel), "with_price": n_price,
            "with_consensus": n_cov,
        },
        "c_buckets": c_stats, "f_buckets": f_stats,
        "c_cells": c_cells, "f_cells": f_cells,
        "c_expect": c_exp, "f_expect": f_exp,
        "spreads": spreads, "ic": ics,
    }
    json.dump(out, open(OUT_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n  结果 → {OUT_FILE}")


if __name__ == "__main__":
    main()
