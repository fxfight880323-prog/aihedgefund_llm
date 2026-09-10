# -*- coding: utf-8 -*-
"""路径B · 硬门槛缩池 —— 在 L4+L5 基础上叠加质量/估值/预期 硬门槛。

目标：把每期 q20 候选池（均值~294 只）压到 10-30 只，
     让"持仓更少"从排序前N截断(路径A) 升级为"源头就不通过"。

变体（全部 full 基座 + q20 排序 + cap8 加权 + top20，N 由路径A 选最优）：
  锚点 q20_top20      只走 L4+L5 + q20 排序
  roe12              + ROE ≥ 12%
  peg5               + PEG ≤ 0.5
  roe12_peg5         + ROE ≥ 12% AND PEG ≤ 0.5
  roe12_peg5_pb80    + ROE ≥ 12% AND PEG ≤ 0.5 AND 池内 PB 分位 ≤ 80%
  roe15_peg5_strict  + ROE ≥ 15% AND PEG ≤ 0.5

口径：full 基座(含金融)、日频复权、含成本 5bp+10bp、mv≥100亿、L4+L5(garp门控)。
锚点：路径A top20 = +97.0% / MDD 18.4% / N_eff 15.7
"""
import json, os, sys, datetime
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


def screen_pool(month, univ, val, fac, cons, gate):
    """L4+L5 + gate(month, s) 硬门槛 → q20 排序字段填充。"""
    pool = []
    for tk in univ:
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}
        mv = L._num(v.get("total_mv"))
        pe = L._num(v.get("pe_ttm"))
        pb = L._num(v.get("pb"))
        dy = L._num(f.get("dtop5"))
        exp_g = L._num(c.get("con_np_yoy"))
        peg = L._num(c.get("con_peg"))
        roe = L._num(c.get("con_roe"))
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
        cetop = L._num(f.get("cetop"))
        s = {"tk": tk, "pe": pe, "mv": mv, "pb": pb,
             "gpm": gpm or 0, "roe": roe, "cetop": cetop or 0}
        if not gate(s):
            continue
        pool.append(s)
    if not pool:
        return []
    gpm_vals = [s["gpm"] for s in pool if s["gpm"]]
    roe_vals = [s["roe"] for s in pool if s["roe"] is not None]
    cet_vals = [s["cetop"] for s in pool if s["cetop"]]
    pe_vals = [s["pe"] for s in pool]
    pb_vals = [s["pb"] for s in pool if s["pb"] is not None]
    for s in pool:
        s["gpm_pct"] = pct_rank(gpm_vals, s["gpm"]) if s["gpm"] else 0
        s["roe_pct"] = pct_rank(roe_vals, s["roe"]) if s["roe"] is not None else 0
        s["cet_pct"] = pct_rank(cet_vals, s["cetop"]) if s["cetop"] else 0
        s["q_score"] = (s["gpm_pct"] + s["roe_pct"] + s["cet_pct"]) / 3.0
        s["pe_pct"] = 100.0 - pct_rank(pe_vals, s["pe"])
        s["blend"] = 0.8 * s["pe_pct"] + 0.2 * s["q_score"]
        s["pb_pct"] = pct_rank(pb_vals, s["pb"]) if s["pb"] is not None else None
    return pool


# 硬门槛定义
def gate_roe12(s):
    return s["roe"] is not None and s["roe"] >= 0.12

def gate_peg5(s):
    peg = L._num((s.get("tk"),))  # placeholder, 真实 PEG 在 screen_pool 之前已算
    return True

def gate_combo_roe12(s):
    return gate_roe12(s)

def gate_combo_peg5(s):
    pe = s["pe"]
    exp_g_ok = True
    # PEG ≤ 0.5 需要一致预期净利润增速 > 0
    return True


# 在 screen_pool 调用前传入闭包：传入 dict 上下文
def make_gate(roe_min=None, peg_max=None, pb_pct_max=None, cons=None):
    """构造 gate(s, ctx) 闭包，screen_pool 内调用 gate(s, ctx)。"""
    def gate(s):
        if roe_min is not None:
            if s["roe"] is None or s["roe"] < roe_min:
                return False
        if peg_max is not None:
            tk = s["tk"]
            peg = (cons.get(tk) or {}).get("con_peg")
            peg = L._num(peg)
            if peg is None or peg <= 0 or peg > peg_max:
                return False
        if pb_pct_max is not None:
            if s.get("pb_pct") is None or s["pb_pct"] > pb_pct_max:
                return False
        return True
    return gate


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
    print("  路径B · 硬门槛缩池（q20 排序 × cap8 × top20，半年调仓）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set(fin) if fin else set()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 变体定义
    VARIANTS = {
        "q20_top20":       {"roe_min": None, "peg_max": None, "pb_pct_max": None},
        "roe12":           {"roe_min": 0.12, "peg_max": None, "pb_pct_max": None},
        "peg5":            {"roe_min": None, "peg_max": 0.5, "pb_pct_max": None},
        "roe12_peg5":      {"roe_min": 0.12, "peg_max": 0.5, "pb_pct_max": None},
        "roe12_peg5_pb80": {"roe_min": 0.12, "peg_max": 0.5, "pb_pct_max": 80.0},
        "roe15_peg5":      {"roe_min": 0.15, "peg_max": 0.5, "pb_pct_max": None},
    }
    N_TOP = 20
    CAP = 0.08

    # 每期 pool（带 gate）+ pool 大小
    pool_sizes = {name: {} for name in VARIANTS}
    pools = {name: {} for name in VARIANTS}

    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        # 第一次：构造完整候选（无 gate），计算 pb_pct
        base_pool = screen_pool(month, members, vv, ff, cc, lambda s: True)
        # 然后对每个变体应用 gate
        for name, spec in VARIANTS.items():
            gate = make_gate(roe_min=spec["roe_min"],
                             peg_max=spec["peg_max"],
                             pb_pct_max=spec["pb_pct_max"],
                             cons=cc)
            sub = [s for s in base_pool if gate(s)]
            pools[name][month] = sub
            pool_sizes[name][month] = len(sub)

    # 池大小汇总
    print("\n[池大小 · 各期通过硬门槛的候选数]")
    for name in VARIANTS:
        sizes = list(pool_sizes[name].values())
        print(f"  {name:20s}: 均 {sum(sizes)/len(sizes):5.1f} "
              f"| 最大 {max(sizes):3d} | 最小 {min(sizes):3d} "
              f"| 0 出现 {sum(1 for s in sizes if s == 0)}/{len(sizes)}")

    # 覆盖审计
    print("\n[覆盖审计] 各变体 vs 价格库:")
    coverage = {}
    for name in VARIANTS:
        miss = 0
        for month, _ in PIT_DATES:
            picked = sorted(pools[name][month], key=lambda s: -s["blend"])[:N_TOP]
            miss += sum(1 for s in picked if s["tk"] not in px_syms)
        coverage[name] = miss
        print(f"  {name:20s}: {miss:3d} 只-期缺失 {'⚠️' if miss else '✓'}")

    # 回测
    print("\n[回测] 价格回测（含成本 5bp+10bp）…")
    results = {}
    conc = {}

    for name, spec in VARIANTS.items():
        all_w = []
        for month, asof in PIT_DATES:
            sub = pools[name][month]
            # q20 排序取 top20
            picked = sorted(sub, key=lambda s: -s["blend"])[:N_TOP]
            w = cap_weight(picked, CAP)
            all_w.append(w)

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
        r["pool_avg"] = sum(pool_sizes[name].values()) / len(pool_sizes[name])
        r["pool_min"] = min(pool_sizes[name].values())
        results[name] = r
        conc[name] = {"top3": top3, "hhi": hhi, "neff": neff}
        print(f"  {name:20s}: 总 {r['total']*100:+7.1f}% 年化 {r['ann']*100:+5.1f}% "
              f"MDD {r['mdd']*100:6.1f}% | 池均 {r['pool_avg']:5.1f} | "
              f"持仓 {r['avg_holdings']:5.1f} | N_eff {neff:5.1f}")

    # 锚点对齐：与路径A top20 = +97.0%
    top20_anchor = 0.9702   # 路径A 结果
    cur = results["q20_top20"]["total"]
    print(f"\n  [锚点对齐] q20_top20 本次 {cur:+.4f} vs 路径A {top20_anchor:+.4f} "
          f"| 差 {(cur - top20_anchor)*100:+.2f}pp")

    # 汇总
    print("\n[结果汇总] 硬门槛 → q20 排序 × cap8 × top20:")
    print(f"{'变体':<22}{'池均':>6}{'年化':>8}{'总收益':>9}{'MDD':>8}{'持仓':>7}{'N_eff':>7}{'top3':>7}{'依赖':>7}{'覆盖':>6}")
    for name in VARIANTS:
        r = results[name]
        print(f"{name:<22}{r['pool_avg']:>5.1f}{r['ann']*100:>+7.1f}%{r['total']*100:>+8.1f}%"
              f"{r['mdd']*100:>7.1f}%{r['avg_holdings']:>6.1f}{r['neff']:>6.1f}"
              f"{r['top3']:>6.1%}{r['dep']:>7.2f}{coverage[name]:>5}")

    # 分年度
    years = sorted(set(y for r in results.values() for y in r["yearly"]))
    print("\n[分年度收益]（%）:")
    print(f"{'变体':<22}" + "".join(f"{y:>8}" for y in years))
    for name in VARIANTS:
        yl = results[name]["yearly"]
        print(f"{name:<22}" + "".join(f"{yl.get(y,0)*100:>+7.1f}" for y in years))

    # 早后期
    print("\n[早/后期拆分]:")
    for name in VARIANTS:
        yl = results[name]["yearly"]
        early = late = 1.0
        for y in years:
            rr = 1 + yl.get(y, 0)
            if y <= "2023":
                early *= rr
            else:
                late *= rr
        print(f"  {name:<22}: 2021-2023 {early-1:+7.1%} | 2024-2026 {late-1:+7.1%}")

    # 保存
    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "method": "q20 排序 × cap8 × top20 + 硬门槛",
                 "base": "full(含金融)", "freq": "日频+复权",
                 "anchor_q20_top20": top20_anchor},
        "variants": {name: {"roe_min": spec["roe_min"],
                            "peg_max": spec["peg_max"],
                            "pb_pct_max": spec["pb_pct_max"]}
                     for name, spec in VARIANTS.items()},
        "pool_sizes": pool_sizes,
        "results": {name: {"total": results[name]["total"], "ann": results[name]["ann"],
                            "mdd": results[name]["mdd"], "dep": results[name]["dep"],
                            "avg_holdings": results[name]["avg_holdings"],
                            "pool_avg": results[name]["pool_avg"],
                            "pool_min": results[name]["pool_min"],
                            "top3": results[name]["top3"], "neff": results[name]["neff"],
                            "yearly": results[name]["yearly"]}
                    for name in VARIANTS},
        "coverage": coverage,
    }
    json.dump(out, open("_bt_q20_hardfilter_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_q20_hardfilter_results.json")


if __name__ == "__main__":
    main()