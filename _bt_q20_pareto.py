# -*- coding: utf-8 -*-
"""Pareto 前沿：收益 × 夏普 × 持仓数 —— 新目标函数。

新目标函数（用户提出）：
  「减少池子（持仓数 N）之后，需要收益更高 或者 夏普比率更高」

候选变体（合并路径A + 路径D，并新增 A×D 组合）：
  A 路径（截断 N）：
    A_top12 / A_top15 / A_top20 / A_top25 / A_top30 / A_top40
  D 路径（双信号 gate）：
    D_mom60_top50 / D_breakout250
  A×D 新组合（路径A 最优 N 配路径D 最优 gate）：
    AD_top15_mom60top50
    AD_top20_mom60top50
    AD_top20_breakout250
    AD_top30_breakout250

指标（全部新目标函数）：
  - 总收益 / 年化
  - MDD
  - 夏普比率（rf=2%，日收益 std × √252）
  - Calmar 比率（年化 / MDD）
  - 收益/N 比（每只持仓贡献的总收益）
  - 夏普/N 比（每只持仓贡献的夏普）
  - Pareto 排名（夏普 + 持仓数 双目标）
"""
import json, os, sys, datetime, bisect, math
import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import load_all, load_bars

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

PIT_DATES = L.PIT_DATES
G60_G, G60_PEG = 60.0, 1.0
RF_ANNUAL = 0.02


def pct_rank(values, v):
    n = len(values)
    if n == 0:
        return 50.0
    return sum(1 for x in values if x < v) / n * 100.0


def cap_weight(picked, cap):
    if not picked:
        return {}
    mv = {s["tk"]: s["mv"] for s in picked}
    tot = sum(mv.values())
    if tot <= 0:
        n = len(picked)
        return {s["tk"]: 1.0 / n for s in picked}
    w = {tk: m / tot for tk, m in mv.items()}
    for _ in range(200):
        over = {tk: wv - cap for tk, wv in w.items() if wv > cap + 1e-12}
        if not over:
            break
        excess = sum(over.values())
        under = {tk: mv[tk] for tk in w if w[tk] <= cap + 1e-12}
        if not under:
            break
        utot = sum(under.values())
        if utot <= 0:
            break
        for tk in over:
            w[tk] = cap
        for tk in under:
            w[tk] += excess * under[tk] / utot
    return w


def screen_q20(month, univ, val, fac, cons):
    pool = []
    for tk in univ:
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}
        mv = L._num(v.get("total_mv"))
        pe = L._num(v.get("pe_ttm"))
        dy = L._num(f.get("dtop5"))
        exp_g = L._num(c.get("con_np_yoy"))
        peg = L._num(c.get("con_peg"))
        if mv is None or mv < 100 * 10000:
            continue
        if pe is None or pe <= 0:
            continue
        if not (pe <= L.PE_CEIL or (dy is not None and dy >= L.DIV_YIELD)):
            continue
        if not (exp_g is not None and exp_g <= G60_G
                and peg is not None and 0 < peg <= G60_PEG):
            continue
        gpm = L._num(f.get("gpm"))
        roe = L._num(c.get("con_roe"))
        cetop = L._num(f.get("cetop"))
        pool.append({"tk": tk, "pe": pe, "mv": mv,
                     "gpm": gpm or 0, "roe": roe or 0, "cetop": cetop or 0})
    if not pool:
        return []
    gpm_vals = [s["gpm"] for s in pool if s["gpm"]]
    roe_vals = [s["roe"] for s in pool if s["roe"]]
    cet_vals = [s["cetop"] for s in pool if s["cetop"]]
    pe_vals = [s["pe"] for s in pool]
    for s in pool:
        s["gpm_pct"] = pct_rank(gpm_vals, s["gpm"]) if s["gpm"] else 0
        s["roe_pct"] = pct_rank(roe_vals, s["roe"]) if s["roe"] else 0
        s["cet_pct"] = pct_rank(cet_vals, s["cetop"]) if s["cetop"] else 0
        s["q_score"] = (s["gpm_pct"] + s["roe_pct"] + s["cet_pct"]) / 3.0
        s["pe_pct"] = 100.0 - pct_rank(pe_vals, s["pe"])
        s["blend"] = 0.8 * s["pe_pct"] + 0.2 * s["q_score"]
    return pool


def build_mom_series(bars, all_dates, asof):
    elig_dates = [d for d in all_dates if d <= asof]
    if len(elig_dates) < 250:
        return {}, elig_dates
    out = {}
    for tk, mp in bars.items():
        px_seq = [mp[d].close_price for d in elig_dates if d in mp]
        if len(px_seq) < 250:
            continue
        cur = px_seq[-1]
        mom60 = cur / px_seq[-61] - 1 if len(px_seq) >= 61 and px_seq[-61] > 0 else None
        hi250 = max(px_seq[-250:])
        brk250 = cur / hi250 if hi250 > 0 else None
        out[tk] = {"mom60": mom60, "brk250": brk250}
    return out, elig_dates


def gate_mom60_top50(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["mom60"] is not None and ctx["mom60_pct"].get(s["tk"], 0) > 50


def gate_breakout250(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["brk250"] is not None and g["brk250"] >= 0.80


GATES = {"mom60_top50": gate_mom60_top50, "breakout250": gate_breakout250}


def compute_sharpe(nav_seq, rf=RF_ANNUAL):
    """nav_seq: [{date, nav}, ...] 升序。返回年化夏普（rf=2%）。"""
    if len(nav_seq) < 60:
        return None
    daily_rets = []
    for i in range(1, len(nav_seq)):
        prev, cur = nav_seq[i-1]["nav"], nav_seq[i]["nav"]
        if prev > 0 and cur > 0:
            daily_rets.append(cur / prev - 1)
    if len(daily_rets) < 60:
        return None
    avg = sum(daily_rets) / len(daily_rets)
    var = sum((x - avg) ** 2 for x in daily_rets) / (len(daily_rets) - 1)
    std = math.sqrt(var)
    if std <= 0:
        return None
    ann_ret = (1 + avg) ** 252 - 1
    ann_std = std * math.sqrt(252)
    sharpe = (ann_ret - rf) / ann_std
    return {"sharpe": sharpe, "ann_vol": ann_std, "ann_ret_from_daily": ann_ret}


def conc_metrics(all_w):
    top3s, hhis = [], []
    for w in all_w:
        ws = sorted(w.values(), reverse=True)
        top3s.append(sum(ws[:3]))
        hhis.append(sum(x * x for x in w.values()))
    n = len(all_w)
    if n == 0:
        return 0, 0, 0
    return (sum(top3s) / n, sum(hhis) / n, 1.0 / (sum(hhis) / n))


def yearly(nav_list):
    d = {x["date"]: x["nav"] for x in nav_list}
    dts = sorted(d)
    years = sorted(set(dt[:4] for dt in dts))
    out, prev_end = {}, None
    for y in years:
        y_dts = [dt for dt in dts if dt[:4] == y]
        end = d[y_dts[-1]]
        out[y] = end / d[y_dts[0]] - 1 if prev_end is None else end / prev_end - 1
        prev_end = end
    return out


def dep_best(yearly_ret):
    total = 1.0
    for y, r in yearly_ret.items():
        total *= (1 + r)
    total -= 1
    best = max(yearly_ret.values())
    ex = 1.0
    for y, r in yearly_ret.items():
        if r == best:
            continue
        ex *= (1 + r)
    ex -= 1
    return 1 - ex / total if total > 0 else float("nan")


# 变体定义：(label, N, gate_name_or_None)
VARIANTS = [
    ("A_top12", 12, None),
    ("A_top15", 15, None),
    ("A_top20", 20, None),
    ("A_top25", 25, None),
    ("A_top30", 30, None),
    ("A_top40", 40, None),
    ("D_mom60_top50", 20, "mom60_top50"),
    ("D_breakout250", 20, "breakout250"),
    ("AD_top15_mom60top50", 15, "mom60_top50"),
    ("AD_top20_mom60top50", 20, "mom60_top50"),
    ("AD_top20_breakout250", 20, "breakout250"),
    ("AD_top30_breakout250", 30, "breakout250"),
]


def main():
    print("=" * 88)
    print("  Pareto 前沿 · 收益 × 夏普 × 持仓数")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 每期 base pool
    base_pools = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        base_pools[month] = screen_q20(month, members, vv, ff, cc)

    # 每期动量信号
    mom_ctx = {}
    for month, as_of in PIT_DATES:
        m, elig = build_mom_series(bars, all_dates, as_of)
        m60_vals = sorted([v["mom60"] for v in m.values() if v["mom60"] is not None])
        mom60_pct = {}
        for tk, v in m.items():
            if v["mom60"] is not None and m60_vals:
                pos = bisect.bisect_left(m60_vals, v["mom60"])
                mom60_pct[tk] = pos / len(m60_vals) * 100.0
        mom_ctx[month] = {"mom": m, "mom60_pct": mom60_pct}

    results = {}
    coverage = {}
    print("\n[回测] （含成本 5bp+10bp）…")

    for label, n_top, gate_name in VARIANTS:
        all_w = []
        for month, asof in PIT_DATES:
            bp = base_pools[month]
            if gate_name:
                ctx = mom_ctx[month]
                bp = [s for s in bp if GATES[gate_name](s, ctx)]
            picked = sorted(bp, key=lambda s: -s["blend"])[:n_top]
            w = cap_weight(picked, 0.08)
            all_w.append(w)

        miss = sum(1 for month, _ in PIT_DATES
                   for tk in all_w[PIT_DATES.index((month, _))]
                   if tk not in px_syms)

        w_by_dt = {}
        for (month, asof), w in zip(PIT_DATES, all_w):
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = w

        r = G.run(label, w_by_dt, bars)
        r["yearly"] = yearly(r["nav"])
        r["dep"] = dep_best(r["yearly"])
        r["avg_holdings"] = sum(len(w) for w in all_w) / len(all_w)
        top3, hhi, neff = conc_metrics(all_w)
        r["top3"] = top3
        r["neff"] = neff
        r["n_target"] = n_top
        # 新指标：夏普
        sharpe_data = compute_sharpe(r["nav"])
        if sharpe_data:
            r["sharpe"] = sharpe_data["sharpe"]
            r["ann_vol"] = sharpe_data["ann_vol"]
        else:
            r["sharpe"] = None
            r["ann_vol"] = None
        # Calmar = 年化 / MDD（MDD 是回撤幅度，正数）
        r["calmar"] = r["ann"] / r["mdd"] if r["mdd"] and r["mdd"] > 0 else None
        # 收益 / 实际持仓数
        r["ret_per_n"] = r["total"] / r["avg_holdings"] if r["avg_holdings"] > 0 else None
        # 夏普 / 实际持仓数
        r["sharpe_per_n"] = r["sharpe"] / r["avg_holdings"] if r["sharpe"] and r["avg_holdings"] > 0 else None

        coverage[label] = miss
        results[label] = r
        calmar_s = f"{r['calmar']:.2f}" if r['calmar'] is not None else "N/A"
        sharpe_s = f"{r['sharpe']:.2f}" if r['sharpe'] is not None else "N/A"
        print(f"  {label:24s}: 总 {r['total']*100:+7.1f}% 年化 {r['ann']*100:+5.1f}% "
              f"MDD {r['mdd']*100:6.1f}% | 夏普 {sharpe_s} Calmar {calmar_s} "
              f"| N {r['avg_holdings']:.1f}")

    # Pareto 排序（夏普 × 持仓数，目标：夏普大 + N 小）
    # 简单算法：每个变体被"占优"（dominated）若存在另一个变体夏普 ≥ 它 且 N ≤ 它，且至少一项严格更优
    sharpe_list = [(r["sharpe"], r["avg_holdings"], label)
                   for label, r in results.items() if r["sharpe"]]
    pareto_set = set()
    for i, (s1, n1, l1) in enumerate(sharpe_list):
        dominated = False
        for j, (s2, n2, l2) in enumerate(sharpe_list):
            if i == j:
                continue
            if s2 >= s1 and n2 <= n1 and (s2 > s1 or n2 < n1):
                dominated = True
                break
        if not dominated:
            pareto_set.add(l1)

    print(f"\n[Pareto 前沿] 夏普 × 持仓数（双目标）:")
    pareto_list = [(label, results[label]) for label in pareto_set]
    pareto_list.sort(key=lambda x: -x[1]["sharpe"])
    for label, r in pareto_list:
        print(f"  {label:24s}: 夏普 {r['sharpe']:.2f} | N {r['avg_holdings']:.1f} | "
              f"年化 {r['ann']*100:+.1f}% | MDD {r['mdd']*100:5.1f}%")

    # 收益/N 排序
    print(f"\n[收益 per 持仓] 总收益 / 实际持仓数:")
    by_ret_per_n = sorted(
        [(label, r["ret_per_n"]) for label, r in results.items() if r["ret_per_n"]],
        key=lambda x: -x[1])
    for label, rpn in by_ret_per_n[:8]:
        r = results[label]
        print(f"  {label:24s}: {rpn*100:+5.2f}%/只 | 总 {r['total']*100:+7.1f}% | "
              f"N {r['avg_holdings']:.1f}")

    # 夏普/N 排序
    print(f"\n[夏普 per 持仓] 夏普 / 实际持仓数:")
    by_sharpe_per_n = sorted(
        [(label, r["sharpe_per_n"]) for label, r in results.items() if r["sharpe_per_n"]],
        key=lambda x: -x[1])
    for label, spn in by_sharpe_per_n[:8]:
        r = results[label]
        print(f"  {label:24s}: {spn:.3f}/只 | 夏普 {r['sharpe']:.2f} | "
              f"N {r['avg_holdings']:.1f}")

    # 全汇总表
    print("\n[全汇总] 总收益 × 年化 × MDD × 夏普 × Calmar × N:")
    print(f"{'变体':<24}{'年化':>8}{'总收益':>9}{'MDD':>8}{'夏普':>7}{'Calmar':>8}{'实际持仓':>9}{'收益/N':>9}{'夏普/N':>8}")
    sorted_labels = sorted(results.keys(),
                           key=lambda l: -(results[l]["sharpe"] or 0))
    for label in sorted_labels:
        r = results[label]
        marker = "★" if label in pareto_set else " "
        sharpe_s = f"{r['sharpe']:>6.2f}" if r['sharpe'] is not None else "  N/A"
        calmar_s = f"{r['calmar']:>7.2f}" if r['calmar'] is not None else "    N/A"
        ret_n_s = f"{r['ret_per_n']*100:>+7.2f}%" if r['ret_per_n'] is not None else "    N/A"
        spn_s = f"{r['sharpe_per_n']:>7.3f}" if r['sharpe_per_n'] is not None else "    N/A"
        print(f"{marker}{label:<23}{r['ann']*100:>+7.1f}%{r['total']*100:>+8.1f}%"
              f"{r['mdd']*100:>7.1f}%{sharpe_s}{calmar_s}"
              f"{r['avg_holdings']:>8.1f}{ret_n_s}{spn_s}")

    # 保存
    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "method": "q20 排序 + 可选 gate × cap8 × N 截断",
                 "base": "full(含金融)", "freq": "日频+复权",
                 "rf_annual": RF_ANNUAL,
                 "n_target": [v[1] for v in VARIANTS],
                 "gate_names": [v[2] for v in VARIANTS if v[2]]},
        "results": {label: {"total": r["total"], "ann": r["ann"],
                            "mdd": r["mdd"], "sharpe": r["sharpe"],
                            "ann_vol": r["ann_vol"],
                            "calmar": r["calmar"],
                            "dep": r["dep"],
                            "avg_holdings": r["avg_holdings"],
                            "ret_per_n": r["ret_per_n"],
                            "sharpe_per_n": r["sharpe_per_n"],
                            "n_target": r["n_target"],
                            "top3": r["top3"], "neff": r["neff"],
                            "yearly": r["yearly"]}
                    for label, r in results.items()},
        "pareto_set": sorted(pareto_set),
        "coverage": coverage,
    }
    json.dump(out, open("_bt_q20_pareto_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_q20_pareto_results.json")


if __name__ == "__main__":
    main()