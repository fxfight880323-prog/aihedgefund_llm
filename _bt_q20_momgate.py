# -*- coding: utf-8 -*-
"""路径D · 双信号 gate —— q20 排序 + 动量/趋势 gate（as_of 当日可见）。

目标：在 q20_cap8 选出的票上，再加一层"动量/趋势"门控，要求
     「基本面便宜 + 质量」且「趋势确认」才持有 —— 减少持仓数并提升确定性。

gate 信号（全部基于 _bt_daily_px_full.json 复权价，as_of 当日及之前价格，
         严格不引入未来数据）：
  mom60   = 60 日动量 > 0（过去 60 个交易日上涨）
  mom120  = 120 日动量 > 0
  mom60_pos_top50 = mom60 截面分位 > 50%（动量前 50%）
  breakout_250 = 当前价 / 250日最高价 ≥ 0.80（趋势确认）
  breakout_120 = 当前价 / 120日最高价 ≥ 0.90

变体（全部 full 基座 + q20 排序 + cap8 + top20）：
  q20_top20           锚点（无 gate）
  q20_mom60           q20 + mom60 > 0
  q20_mom120          q20 + mom120 > 0
  q20_mom60_top50     q20 + mom60 截面分位 > 50%
  q20_breakout250     q20 + 当前价 / 250日高 ≥ 80%
  q20_breakout120     q20 + 当前价 / 120日高 ≥ 90%

口径：full 基座(含金融)、日频复权、含成本 5bp+10bp、mv≥100亿、L4+L5(garp门控)。
"""
import json, os, sys, datetime, bisect
import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import load_all, load_bars

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

PIT_DATES = L.PIT_DATES
G60_G, G60_PEG = 60.0, 1.0


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
    """对每只股票，计算调仓日 asof 之前的 60/120/250 日动量与新高距离。
    bars: {tk: {date_str: BarData-like (含 close_price)}}
    返回 {tk: {mom60, mom120, mom250, brk250, brk120}}，asof 之后数据严格不用。
    """
    # 找 asof 及之前的所有交易日
    elig_dates = [d for d in all_dates if d <= asof]
    if len(elig_dates) < 250:
        # 数据不足返回空
        return {}, elig_dates

    out = {}
    for tk, mp in bars.items():
        px_seq = [mp[d].close_price for d in elig_dates if d in mp]
        if len(px_seq) < 250:
            continue
        cur = px_seq[-1]
        # 动量
        mom60 = cur / px_seq[-61] - 1 if len(px_seq) >= 61 and px_seq[-61] > 0 else None
        mom120 = cur / px_seq[-121] - 1 if len(px_seq) >= 121 and px_seq[-121] > 0 else None
        mom250 = cur / px_seq[-251] - 1 if len(px_seq) >= 251 and px_seq[-251] > 0 else None
        # 新高距离
        hi250 = max(px_seq[-250:])
        hi120 = max(px_seq[-120:])
        brk250 = cur / hi250 if hi250 > 0 else None
        brk120 = cur / hi120 if hi120 > 0 else None
        out[tk] = {"mom60": mom60, "mom120": mom120, "mom250": mom250,
                   "brk250": brk250, "brk120": brk120}
    return out, elig_dates


def gate_mom60(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["mom60"] is not None and g["mom60"] > 0


def gate_mom120(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["mom120"] is not None and g["mom120"] > 0


def gate_mom60_top50(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["mom60"] is not None and ctx["mom60_pct"].get(s["tk"], 0) > 50


def gate_breakout250(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["brk250"] is not None and g["brk250"] >= 0.80


def gate_breakout120(s, ctx):
    g = ctx["mom"].get(s["tk"])
    return g is not None and g["brk120"] is not None and g["brk120"] >= 0.90


GATES = {
    "q20_mom60":       gate_mom60,
    "q20_mom120":      gate_mom120,
    "q20_mom60_top50": gate_mom60_top50,
    "q20_breakout250": gate_breakout250,
    "q20_breakout120": gate_breakout120,
}


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


def main():
    print("=" * 88)
    print("  路径D · 双信号 gate（q20 + 动量/趋势，as_of 当日可见）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 每期 base pool（q20 通过）
    base_pools = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        base_pools[month] = screen_q20(month, members, vv, ff, cc)

    pool_sizes = {m: len(base_pools[m]) for m, _ in PIT_DATES}
    print(f"  各期 q20 pool: 平均 {sum(pool_sizes.values())/len(pool_sizes):.1f} 只")

    # 每期构造动量信号（as_of 严格当日可见）
    mom_ctx = {}
    for month, as_of in PIT_DATES:
        m, elig = build_mom_series(bars, all_dates, as_of)
        # mom60 截面分位
        m60_vals = sorted([v["mom60"] for v in m.values() if v["mom60"] is not None])
        mom60_pct = {}
        for tk, v in m.items():
            if v["mom60"] is not None and m60_vals:
                # 二分查找位置
                pos = bisect.bisect_left(m60_vals, v["mom60"])
                mom60_pct[tk] = pos / len(m60_vals) * 100.0
        mom_ctx[month] = {"mom": m, "mom60_pct": mom60_pct}
    print(f"  动量信号：as_of 严格当日及之前，最长看 250 日窗口")

    # gate 变体
    N_TOP = 20
    CAP = 0.08

    # 锚点对齐：与路径B q20_top20
    anchor_b = json.load(open("_bt_q20_hardfilter_results.json", encoding="utf-8"))
    anchor_total = anchor_b["results"]["q20_top20"]["total"]

    results = {}
    coverage = {}

    print("\n[Gate 通过率 · 每期有多少 q20 候选通过 gate]:")
    pass_rates = {name: [] for name in GATES}
    for month, as_of in PIT_DATES:
        ctx = mom_ctx[month]
        bp = base_pools[month]
        for name, gate_fn in GATES.items():
            passed = sum(1 for s in bp if gate_fn(s, ctx))
            pass_rates[name].append(passed)

    for name in GATES:
        sizes = pass_rates[name]
        avg = sum(sizes) / len(sizes)
        print(f"  {name:22s}: 均 {avg:5.1f} | 最大 {max(sizes):3d} | 最小 {min(sizes):3d}")

    print("\n[回测] 价格回测（含成本 5bp+10bp）…")
    for name, gate_fn in GATES.items():
        all_w = []
        for month, asof in PIT_DATES:
            ctx = mom_ctx[month]
            bp = base_pools[month]
            passed = [s for s in bp if gate_fn(s, ctx)]
            picked = sorted(passed, key=lambda s: -s["blend"])[:N_TOP]
            w = cap_weight(picked, CAP)
            all_w.append(w)

        # 覆盖审计
        miss = 0
        for month, asof in PIT_DATES:
            ctx = mom_ctx[month]
            bp = base_pools[month]
            passed = [s for s in bp if gate_fn(s, ctx)]
            picked = sorted(passed, key=lambda s: -s["blend"])[:N_TOP]
            miss += sum(1 for s in picked if s["tk"] not in px_syms)
        coverage[name] = miss

        w_by_dt = {}
        for (month, asof), w in zip(PIT_DATES, all_w):
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = w

        r = G.run(name, w_by_dt, bars)
        r["yearly"] = yearly(r["nav"])
        r["dep"] = dep_best(r["yearly"])
        r["avg_holdings"] = sum(len(w) for w in all_w) / len(all_w)
        top3, hhi, neff = conc_metrics(all_w)
        r["top3"] = top3
        r["neff"] = neff
        r["gate_pass_avg"] = sum(pass_rates[name]) / len(pass_rates[name])
        results[name] = r
        print(f"  {name:22s}: 总 {r['total']*100:+7.1f}% 年化 {r['ann']*100:+5.1f}% "
              f"MDD {r['mdd']*100:6.1f}% | gate通过 {r['gate_pass_avg']:5.1f} | "
              f"持仓 {r['avg_holdings']:5.1f} | N_eff {neff:5.1f}")

    # 锚点对齐
    cur = anchor_total
    print(f"\n  [锚点] 路径B q20_top20 = {cur:+.4f} | "
          f"对照 d 变体：见下表")

    # 汇总
    print("\n[结果汇总] q20 × gate × cap8 × top20:")
    print(f"{'变体':<22}{'gate通过':>9}{'年化':>8}{'总收益':>9}{'MDD':>8}{'持仓':>7}{'N_eff':>7}{'top3':>7}{'依赖':>7}{'覆盖':>6}")
    for name in GATES:
        r = results[name]
        print(f"{name:<22}{r['gate_pass_avg']:>8.1f}{r['ann']*100:>+7.1f}%{r['total']*100:>+8.1f}%"
              f"{r['mdd']*100:>7.1f}%{r['avg_holdings']:>6.1f}{r['neff']:>6.1f}"
              f"{r['top3']:>6.1%}{r['dep']:>7.2f}{coverage[name]:>5}")

    # 与锚点对比
    print(f"\n[与锚点对比] 路径B q20_top20 = {anchor_total*100:+.1f}% / MDD -18.4%")
    for name in GATES:
        r = results[name]
        delta = (r["total"] - anchor_total) * 100
        print(f"  {name:22s}: {r['total']*100:+7.1f}% (Δ {delta:+5.1f}pp) | MDD {r['mdd']*100:+5.1f}%")

    # 分年度
    years = sorted(set(y for r in results.values() for y in r["yearly"]))
    print("\n[分年度收益]（%）:")
    print(f"{'变体':<22}" + "".join(f"{y:>8}" for y in years))
    for name in GATES:
        yl = results[name]["yearly"]
        print(f"{name:<22}" + "".join(f"{yl.get(y,0)*100:>+7.1f}" for y in years))

    # 早后期
    print("\n[早/后期拆分]:")
    for name in GATES:
        yl = results[name]["yearly"]
        early = late = 1.0
        for y in years:
            rr = 1 + yl.get(y, 0)
            if y <= "2023":
                early *= rr
            else:
                late *= rr
        print(f"  {name:<22}: 2021-2023 {early-1:+7.1%} | 2024-2026 {late-1:+7.1%}")

    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "method": "q20 排序 + 动量/趋势 gate × cap8 × top20",
                 "base": "full(含金融)", "freq": "日频+复权",
                 "anchor_pathB_top20_total": anchor_total,
                 "no_future": "gate 信号严格基于 as_of 及之前价格"},
        "results": {name: {"total": results[name]["total"], "ann": results[name]["ann"],
                            "mdd": results[name]["mdd"], "dep": results[name]["dep"],
                            "avg_holdings": results[name]["avg_holdings"],
                            "gate_pass_avg": results[name]["gate_pass_avg"],
                            "top3": results[name]["top3"], "neff": results[name]["neff"],
                            "yearly": results[name]["yearly"]}
                    for name in GATES},
        "coverage": coverage,
    }
    json.dump(out, open("_bt_q20_momgate_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_q20_momgate_results.json")


if __name__ == "__main__":
    main()