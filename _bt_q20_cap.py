# -*- coding: utf-8 -*-
"""q20 排序 × 市值加权(cap) 组合实验（full 基座，含金融）。

背景：
  - q20 排序(0.8×PE便宜度 + 0.2×质量分) 已验证 +3.40pp，但口径是「剔金融 core_finex」，
    含金融(full)口径从未单独回测 —— 本实验补齐。
  - cap8~10 市值加权已验证「集中度换收益且逐年稳健」，但基于「PE升序 top40」池，
    未叠 q20 排序。

本实验把两者叠加到 full 基座：
  - 排序：PE升序(基线) vs q20 blend 降序
  - 加权：等权 vs 市值加权(cap8/10/15)
  交叉 8 个变体，看组合是否跑赢 g60 且摊平 2024 单点依赖。

口径：full 基座(含金融)、日频复权、含成本 5bp+10bp、mv≥100亿、L4+L5(garp门控)。
锚点：g60 = +67.01%（_bt_garp_audit_results.json rerun.full.g60）。
"""
import json, os, sys, datetime, statistics
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import (load_all, screen_decomp, load_bars,
                                build_weights)

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS = L.MAX_HOLDINGS
G60_G, G60_PEG = 60.0, 1.0


def pct_rank(values, v):
    n = len(values)
    if n == 0:
        return 50.0
    return sum(1 for x in values if x < v) / n * 100.0


def cap_weight(picked, cap):
    mv = {s["tk"]: s["mv"] for s in picked}
    tot = sum(mv.values())
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
        for tk in over:
            w[tk] = cap
        for tk in under:
            w[tk] += excess * under[tk] / utot
    return w


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


def screen_q20(month, univ, val, fac, cons):
    """full 基座 core-pass 池，附带质量字段，用于 q20 排序。"""
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
    # 池内百分位
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


def main():
    print("=" * 88)
    print("  q20 排序 × 市值加权(cap) 组合实验（full 基座，日频+复权）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 每期 pool（full 基座）
    pools = {}   # month -> list[dict]
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        pools[month] = screen_q20(month, members, vv, ff, cc)

    # 变体定义：name -> (排序 key, 加权方案)
    # 排序：pe(升序) / q20(blend 降序)
    # 加权：equal / cap8 / cap10 / cap15
    def sort_pe(pool):
        return sorted(pool, key=lambda s: s["pe"])[:MAX_HOLDINGS]

    def sort_q20(pool):
        return sorted(pool, key=lambda s: -s["blend"])[:MAX_HOLDINGS]

    variants = {
        "g60_pe_ew":    (sort_pe,  "equal"),
        "q20_ew":       (sort_q20, "equal"),
        "q20_cap8":     (sort_q20, "cap8"),
        "q20_cap10":    (sort_q20, "cap10"),
        "q20_cap15":    (sort_q20, "cap15"),
        "pe_cap10":     (sort_pe,  "cap10"),
    }

    def weight_of(picked, scheme):
        if scheme == "equal":
            return build_weights(picked, "equal")
        cap = {"cap8": 0.08, "cap10": 0.10, "cap15": 0.15}[scheme]
        return cap_weight(picked, cap)

    # 覆盖审计
    print("\n[覆盖审计] 各变体选股并集 vs 530只差集:")
    cov = {}
    for name, (sfn, _) in variants.items():
        miss = 0
        for month, _ in PIT_DATES:
            picked = sfn(pools[month])
            miss += sum(1 for s in picked if s["tk"] not in px_syms)
        cov[name] = miss
        print(f"    {name:12s}: {miss:3d} 只-期缺失 {'⚠️' if miss else '✓'}")

    # 回测
    print("\n[回测] 价格回测（含成本 5bp+10bp）…")
    results = {}
    for name, (sfn, wscheme) in variants.items():
        w_by_dt = {}
        fin_cnt = []
        for month, asof in PIT_DATES:
            picked = sfn(pools[month])
            w = weight_of(picked, wscheme)
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = w
            fin_cnt.append(sum(1 for s in picked if s["tk"] in fin))
        r = G.run(name, w_by_dt, bars)
        r["yearly"] = yearly(r["nav"])
        r["dep"] = dep_best(r["yearly"])
        r["fin_avg"] = sum(fin_cnt) / len(fin_cnt)
        results[name] = r

    # 锚点
    audit = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
    g60_hist = audit["rerun"]["full"]["g60"]["total"]
    print(f"  [锚点] g60_pe_ew={results['g60_pe_ew']['total']:+.4f} vs audit {g60_hist:+.4f}")

    # 汇总表
    print("\n[结果汇总]")
    print(f"{'变体':<12}{'总收益':>10}{'年化':>8}{'MDD':>8}{'依赖度':>8}{'金融/期':>8}")
    for name in variants:
        r = results[name]
        print(f"{name:<12}{r['total']*100:>9.1f}%{r['ann']*100:>7.1f}%{r['mdd']*100:>7.1f}%"
              f"{r['dep']:>7.2f}{r['fin_avg']:>7.1f}")

    # 分年度矩阵
    years = sorted(set(y for r in results.values() for y in r["yearly"]))
    print("\n[分年度收益]（%）:")
    print(f"{'变体':<12}" + "".join(f"{y:>9}" for y in years))
    for name in variants:
        yl = results[name]["yearly"]
        print(f"{name:<12}" + "".join(f"{yl.get(y,0)*100:>9.1f}" for y in years))

    # 早/后期拆分
    print("\n[早/后期拆分]:")
    for name in variants:
        yl = results[name]["yearly"]
        early = late = 1.0
        for y in years:
            rr = 1 + yl.get(y, 0)
            if y <= "2023":
                early *= rr
            else:
                late *= rr
        print(f"  {name:<12}: 2021-2023 {early-1:+7.1%} | 2024-2026 {late-1:+7.1%}")

    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "base": "full(含金融)", "freq": "日频+复权",
                 "anchor_g60": g60_hist,
                 "method": "q20=0.8*pe_pct+0.2*q_score; cap=市值加权+单票上限"},
        "results": {k: {"total": results[k]["total"], "ann": results[k]["ann"],
                        "mdd": results[k]["mdd"], "dep": results[k]["dep"],
                        "fin_avg": results[k]["fin_avg"],
                        "yearly": results[k]["yearly"]} for k in variants},
        "coverage": cov,
    }
    json.dump(out, open("_bt_q20_cap_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_q20_cap_results.json")


if __name__ == "__main__":
    main()
