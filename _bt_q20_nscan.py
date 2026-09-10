# -*- coding: utf-8 -*-
"""路径A：N 敏感性截断 —— q20_cap8 池子里取前 N=8/10/12/15 只。

目标：在保持 q20 排序 × cap8 加权 × 半年调仓口径不变的前提下，
     把"持仓数"作为唯一变量，验证"持仓更少是否换更大确定性"。

锚点：q20_cap8 (= q20 排序 + cap8 加权 + top40 池)  +118.5%, MDD -15.6%
变体：top_N = 8 / 10 / 12 / 15 / 20 / 25 / 30（保留 cap8）

口径：full 基座(含金融)、日频复权、含成本 5bp+10bp、mv≥100亿、L4+L5(garp门控)。
"""
import json, os, sys, datetime, statistics
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import (load_all, load_bars)


PIT_DATES = L.PIT_DATES
G60_G, G60_PEG = 60.0, 1.0


def pct_rank(values, v):
    n = len(values)
    if n == 0:
        return 50.0
    return sum(1 for x in values if x < v) / n * 100.0


def cap_weight(picked, cap):
    """市值加权 + 单票上限 cap（迭代 waterfall）。"""
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
    """full 基座 core-pass 池 + q20 排序字段。"""
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
    print("  路径A · N 敏感性截断（q20 排序 × cap8 加权，半年调仓）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 每期 pool
    pools = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        pools[month] = screen_q20(month, members, vv, ff, cc)

    pool_sizes = {m: len(pools[m]) for m, _ in PIT_DATES}
    print(f"  各期 q20 pool: 平均 {sum(pool_sizes.values())/len(pool_sizes):.1f} 只 "
          f"| 最大 {max(pool_sizes.values())} | 最小 {min(pool_sizes.values())}")

    # 变体：N 截断（排序方式固定为 q20 降序）
    N_LIST = [8, 10, 12, 15, 20, 25, 30, 40]   # 40 = q20_cap8 锚点
    CAP = 0.08

    def pick_top_n(pool, n):
        return sorted(pool, key=lambda s: -s["blend"])[:n]

    results = {}
    conc = {}
    coverage = {}
    yearly_conc = {}

    print("\n[变体定义] q20 排序 × cap8 加权 × 截断 N")
    print("\n[覆盖审计] 各 N 截断变体选股 vs 价格库:")
    for n in N_LIST:
        all_w = []
        for month, asof in PIT_DATES:
            picked = pick_top_n(pools[month], n)
            w = cap_weight(picked, CAP)
            all_w.append(w)
        # 覆盖审计
        miss = 0
        for month, _ in PIT_DATES:
            picked = pick_top_n(pools[month], n)
            miss += sum(1 for s in picked if s["tk"] not in px_syms)
        coverage[n] = miss

        w_by_dt = {}
        for (month, asof), w in zip(PIT_DATES, all_w):
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = w

        r = G.run(f"top{n}_cap8", w_by_dt, bars)
        r["yearly"] = yearly(r["nav"])
        r["dep"] = dep_best(r["yearly"])
        r["avg_holdings"] = sum(len(w) for w in all_w) / len(all_w)
        top3, hhi, neff = conc_metrics(all_w)
        r["top3"] = top3
        r["neff"] = neff
        results[n] = r
        conc[n] = {"top3": top3, "hhi": hhi, "neff": neff}
        print(f"  top{n:2d}: 总 {r['total']*100:+7.1f}% 年化 {r['ann']*100:+5.1f}% "
              f"MDD {r['mdd']*100:6.1f}% | 实际均持仓 {r['avg_holdings']:5.1f} "
              f"N_eff {neff:5.1f} top3 {top3:5.1%} | 覆盖丢股 {miss}")

    # 锚点
    q20_cap8_hist = None
    if os.path.exists("_bt_q20_cap_results.json"):
        old = json.load(open("_bt_q20_cap_results.json", encoding="utf-8"))
        q20_cap8_hist = old.get("results", {}).get("q20_cap8", {}).get("total")
    if q20_cap8_hist is not None:
        cur = results[40]["total"]
        print(f"\n  [锚点对齐] q20_cap8 (top40) 本次 {cur:+.4f}  vs 历史 {q20_cap8_hist:+.4f} "
              f"| 差 {cur - q20_cap8_hist:+.4f}")

    # 汇总表
    print("\n[结果汇总] q20 × cap8 × 截断 N:")
    print(f"{'N':>4}{'年化':>8}{'总收益':>9}{'MDD':>8}{'实际持仓':>9}{'N_eff':>7}{'top3':>7}{'依赖':>7}{'覆盖':>6}")
    for n in N_LIST:
        r = results[n]
        print(f"{n:>4}{r['ann']*100:>7.1f}%{r['total']*100:>+8.1f}%{r['mdd']*100:>7.1f}%"
              f"{r['avg_holdings']:>8.1f}{r['neff']:>6.1f}{r['top3']:>6.1%}{r['dep']:>7.2f}"
              f"{coverage[n]:>5}")

    # 分年度
    years = sorted(set(y for r in results.values() for y in r["yearly"]))
    print("\n[分年度收益]（%）:")
    print(f"{'N':>4}" + "".join(f"{y:>8}" for y in years))
    for n in N_LIST:
        yl = results[n]["yearly"]
        print(f"{n:>4}" + "".join(f"{yl.get(y,0)*100:>+7.1f}" for y in years))

    # 早/后期
    print("\n[早/后期拆分]:")
    for n in N_LIST:
        yl = results[n]["yearly"]
        early = late = 1.0
        for y in years:
            rr = 1 + yl.get(y, 0)
            if y <= "2023":
                early *= rr
            else:
                late *= rr
        print(f"  top{n:2d}: 2021-2023 {early-1:+7.1%} | 2024-2026 {late-1:+7.1%}")

    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "method": "q20=0.8*pe_pct+0.2*q_score; cap8(单票8%); N=截断",
                 "base": "full(含金融)", "freq": "日频+复权",
                 "anchor_q20_cap8_total": q20_cap8_hist,
                 "pool_size_avg": sum(pool_sizes.values()) / len(pool_sizes)},
        "pool_sizes": pool_sizes,
        "results": {str(n): {"total": results[n]["total"], "ann": results[n]["ann"],
                             "mdd": results[n]["mdd"], "dep": results[n]["dep"],
                             "avg_holdings": results[n]["avg_holdings"],
                             "top3": results[n]["top3"], "neff": results[n]["neff"],
                             "yearly": results[n]["yearly"]} for n in N_LIST},
        "coverage": {str(n): coverage[n] for n in N_LIST},
    }
    json.dump(out, open("_bt_q20_nscan_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_q20_nscan_results.json")


if __name__ == "__main__":
    main()