# -*- coding: utf-8 -*-
"""增速上限审视实验：garp 门控（增速≤60% + 0<PEG≤1）中的"增速上限"到底在挡什么？

用户质疑：PEG≤1 已隐含"估值匹配增长"，为什么还要增速上限？只看 PEG 会怎样？

数学事实（实验设计依据）：在 L4(PE≤25 或高股息) 之内，PEG≤1 ≈ PE ≤ g —— 是增速的
单边下限约束。g≥25 的股票 PE≤25 时 PEG≤1 自动成立，超高增速股完全不受 PEG 约束。
增速上限是 PEG 之外唯一挡住"周期峰值/极端外推"的闸门。本实验拆掉它看后果。

变体（全部 PE 升序、core_finex 口径、日频+复权、2021-08~2026-08）：
  core_finex   增速≤25% + PEG≤2（旧基线，参照）
  g30/g40/g60/g80/g100/g150/nolimit   增速≤{30,40,60,80,100,150,∞}% + PEG≤1

机制分析：
  A. 增速分桶前瞻收益：PEG≤1 全池按一致预期增速分桶 (0,30]/(30,60]/(60,100]/
     (100,200]/(200,∞)，前瞻 6M/12M 复权收益（pooled 股-期样本）
  B. top40 侵入分析：nolimit 相对 g60 的 top40 差异股（被上限挡住的 + 被挤出的）
     及其前瞻 6M 收益
"""
import json, os, sys, datetime
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from src.backtest.engine import BarData

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP

VARIANTS = {
    "core_finex": (25.0, 2.0, "pe"),
    "g30":        (30.0, 1.0, "pe"),
    "g40":        (40.0, 1.0, "pe"),
    "g60":        (60.0, 1.0, "pe"),
    "g80":        (80.0, 1.0, "pe"),
    "g100":       (100.0, 1.0, "pe"),
    "g150":       (150.0, 1.0, "pe"),
    "nolimit":    (1e9,  1.0, "pe"),
}

BUCKETS = [(0.0, 30.0), (30.0, 60.0), (60.0, 100.0), (100.0, 200.0), (200.0, 1e18)]
BUCKET_LABELS = ["0-30%", "30-60%", "60-100%", "100-200%", "200%+"]


def build_pool(month, univ, val, fac, cons, excl_fin, g_ceil, peg_ceil):
    """返回通过全部 core 条件 + L5（增速≤g_ceil 且 0<PEG≤peg_ceil）的完整池（不截断 top40）。"""
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
        if not ((pe <= L.PE_CEIL) or (dy is not None and dy >= L.DIV_YIELD)):
            continue
        if not (exp_g is not None and exp_g <= g_ceil
                and peg is not None and 0 < peg <= peg_ceil):
            continue
        if tk in excl_fin:
            continue
        pool.append({"tk": tk, "pe": pe, "exp_g": exp_g, "peg": peg})
    return pool


def load_names():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bt_band_names.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def fwd_ret(px, tk, asof, cal_days, min_frac=0.8):
    """前瞻复权收益：asof 后首个交易日 → asof+cal_days 内最后交易日。
    前瞻窗口数据不足 80% 时返回 None（避免部分收益偏差）。"""
    d = px.get(tk)
    if not d:
        return None
    dates = sorted(dt for dt in d if dt >= asof)
    if not dates:
        return None
    d0 = dates[0]
    t0 = datetime.date.fromisoformat(d0)
    tgt = (t0 + datetime.timedelta(days=cal_days)).isoformat()
    cand = [dt for dt in dates if dt <= tgt]
    if not cand:
        return None
    d1 = cand[-1]
    span = (datetime.date.fromisoformat(d1) - t0).days
    if span < cal_days * min_frac:
        return None
    a0, a1 = d[d0].get("adj"), d[d1].get("adj")
    if not a0 or not a1 or a0 <= 0 or a1 <= 0:
        return None
    return {"ret": a1 / a0 - 1.0, "d0": d0, "d1": d1}


def avg(vals):
    return sum(vals) / len(vals) if vals else None


def main():
    print("=" * 78)
    print("  增速上限审视实验（PEG≤1 固定，增速上限 30→∞ 剂量响应，日频+复权）")
    print("=" * 78)

    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    fin = G.load_fin()
    names = load_names()
    print(f"金融名单: {len(fin)} 只 | 名称映射: {len(names)} 条")

    px = json.load(open("_bt_daily_px.json", encoding="utf-8"))
    bars = {}
    for tk, d in px.items():
        mm = {}
        for dt, r in d.items():
            c, a = r.get("close"), r.get("adj")
            if c and a and c > 0 and a > 0 and dt >= "2021-05-01":
                ratio = a / c
                mm[dt] = BarData(tk, dt, (r.get("open") or c) * ratio,
                                 (r.get("high") or c) * ratio,
                                 (r.get("low") or c) * ratio, a)
        if mm:
            bars[tk] = mm
    all_dates = sorted({dt for m in bars.values() for dt in m})
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dts = sorted(d for d in idx if d >= "2021-06-01")
    base = idx[idx_dts[0]]["close"]
    idx_total = idx[idx_dts[-1]]["close"] / base - 1.0
    idx_mdd = G.mdd_of([idx[d]["close"] / base for d in idx_dts])
    print(f"中证全指: {idx_total:+.2%} | MDD {idx_mdd:.2%}")

    # ---------- 逐期筛选 + 机制分析 ----------
    all_weights = {v: {} for v in VARIANTS}
    all_holdings = {}
    bucket_stats = {lab: {"n": 0, "sum_pe": 0.0, "sum_peg": 0.0, "sum_g": 0.0,
                          "n6": 0, "sum6": 0.0, "win6": 0,
                          "n12": 0, "sum12": 0.0, "win12": 0,
                          "ret6_list": [], "ret12_list": []}
                    for lab in BUCKET_LABELS}
    bucket_by_period = {}
    intrusions, displaced = [], []
    per_period = []

    print("\n逐期: PEG≤1 池规模 | 分桶计数(0-30/30-60/60-100/100-200/200+)")
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        excl_fin = {tk for tk in members if tk in fin}
        vm, fm, cm = val.get(month, {}), fac.get(month, {}), cons.get(month, {})

        for v, (g_ceil, peg_ceil, sort_key) in VARIANTS.items():
            picked, st = G.screen_garp(month, members, vm, fm, cm, excl_fin,
                                       g_ceil, peg_ceil, sort_key)
            n = len(picked)
            w = round(min(1.0 / max(n, 1), PER_NAME_CAP), 4)
            all_weights[v][month] = {s["tk"]: w for s in picked}
            all_holdings.setdefault(v, {})[month] = picked

        # ---- 机制 A：PEG≤1 全池（无增速上限）分桶 ----
        pool = build_pool(month, members, vm, fm, cm, excl_fin, 1e9, 1.0)
        cnt = Counter()
        for s in pool:
            lab = None
            for (lo, hi), lb in zip(BUCKETS, BUCKET_LABELS):
                if lo < s["exp_g"] <= hi:
                    lab = lb
                    break
            if lab is None:
                continue
            cnt[lab] += 1
            bs = bucket_stats[lab]
            bs["n"] += 1
            bs["sum_pe"] += s["pe"]
            bs["sum_peg"] += s["peg"]
            bs["sum_g"] += s["exp_g"]
            r6 = fwd_ret(px, s["tk"], as_of, 183)
            if r6 is not None:
                bs["n6"] += 1
                bs["sum6"] += r6["ret"]
                bs["win6"] += 1 if r6["ret"] > 0 else 0
                bs["ret6_list"].append(r6["ret"])
            r12 = fwd_ret(px, s["tk"], as_of, 365)
            if r12 is not None:
                bs["n12"] += 1
                bs["sum12"] += r12["ret"]
                bs["win12"] += 1 if r12["ret"] > 0 else 0
                bs["ret12_list"].append(r12["ret"])

        bucket_by_period[month] = dict(cnt)
        hi60 = cnt["60-100%"] + cnt["100-200%"] + cnt["200%+"]
        per_period.append({"month": month, "pool": len(pool), "hi60": hi60,
                           "buckets": dict(cnt)})
        print(f"  [{month}] 池={len(pool):4d} 增速>60={hi60:3d} | " +
              " / ".join(f"{cnt.get(lb, 0):4d}" for lb in BUCKET_LABELS))

        # ---- 机制 B：top40 侵入分析（nolimit vs g60）----
        g60_map = {s["tk"]: s for s in all_holdings["g60"][month]}
        nl_map = {s["tk"]: s for s in all_holdings["nolimit"][month]}
        for tk in set(nl_map) - set(g60_map):
            s = nl_map[tk]
            r6 = fwd_ret(px, tk, as_of, 183)
            intrusions.append({"month": month, "tk": tk, "name": names.get(tk, ""),
                               "pe": round(s["pe"], 1), "exp_g": round(s["exp_g"], 1),
                               "peg": round(s["peg"], 2),
                               "fwd6": None if r6 is None else round(r6["ret"], 4)})
        for tk in set(g60_map) - set(nl_map):
            s = g60_map[tk]
            r6 = fwd_ret(px, tk, as_of, 183)
            displaced.append({"month": month, "tk": tk, "name": names.get(tk, ""),
                              "pe": round(s["pe"], 1), "exp_g": round(s["exp_g"], 1),
                              "peg": round(s["peg"], 2),
                              "fwd6": None if r6 is None else round(r6["ret"], 4)})

    # ---------- 回测 ----------
    w_by_dt = {}
    for v in VARIANTS:
        wd = {}
        for month, asof in PIT_DATES:
            trig = max(d for d in all_dates if d <= asof)
            wd[trig] = all_weights[v][month]
        w_by_dt[v] = wd

    print("\n回测结果（全部 PE 升序排序，单边成本 15bp）:")
    results = {}
    for v in VARIANTS:
        r = G.run(v, w_by_dt[v], bars)
        r["excess_idx"] = r["total"] - idx_total
        results[v] = r
        print(f"  {v:11s}: 总收益 {r['total']:+.2%} | 年化 {r['ann']:+.2%} | "
              f"MDD {r['mdd']:.2%} | 超额(中证全指) {r['excess_idx']:+.2%} | {r['n_days']} 天")
    print(f"  {'中证全指':11s}: 总收益 {idx_total:+.2%} | MDD {idx_mdd:.2%}")

    # ---------- 汇总打印 ----------
    print(f"\n{'='*78}")
    print("  剂量响应（PEG≤1 固定，增速上限 → 收益/MDD）:")
    base_r = results["g60"]
    print(f"  {'变体':11s} | {'上限':>5s} | {'总收益':>8s} | {'年化':>7s} | {'MDD':>7s} | "
          f"{'vs g60':>8s}")
    print(f"  {'-'*60}")
    ceil_label = {"core_finex": "25%", "g30": "30%", "g40": "40%", "g60": "60%",
                  "g80": "80%", "g100": "100%", "g150": "150%", "nolimit": "无"}
    for v in VARIANTS:
        r = results[v]
        delta = r["total"] - base_r["total"]
        tag = " ← garp现行" if v == "g60" else ""
        print(f"  {v:11s} | {ceil_label[v]:>5s} | {r['total']:+7.2%} | "
              f"{r['ann']:+6.2%} | {r['mdd']:6.2%} | {delta:+7.2%}{tag}")

    print(f"\n{'='*78}")
    print("  机制 A：PEG≤1 池内增速分桶 → 前瞻收益（pooled 股-期样本，等权）")
    print(f"  {'增速桶':10s} | {'n':>5s} | {'avgPE':>6s} | {'avgPEG':>6s} | {'avg增速':>7s} | "
          f"{'6M均值':>8s} {'胜率':>6s} {'n6':>5s} | {'12M均值':>8s} {'胜率':>6s} {'n12':>5s}")
    print(f"  {'-'*100}")
    for lab in BUCKET_LABELS:
        bs = bucket_stats[lab]
        if bs["n"] == 0:
            print(f"  {lab:10s} |    0 |")
            continue
        m6 = f"{bs['sum6']/bs['n6']:+7.2%}" if bs["n6"] else "     --"
        w6 = f"{bs['win6']/bs['n6']:5.1%}" if bs["n6"] else "   --"
        m12 = f"{bs['sum12']/bs['n12']:+7.2%}" if bs["n12"] else "     --"
        w12 = f"{bs['win12']/bs['n12']:5.1%}" if bs["n12"] else "   --"
        print(f"  {lab:10s} | {bs['n']:5d} | {bs['sum_pe']/bs['n']:6.1f} | "
              f"{bs['sum_peg']/bs['n']:6.2f} | {bs['sum_g']/bs['n']:6.1f}% | "
              f"{m6} {w6} {bs['n6']:5d} | {m12} {w12} {bs['n12']:5d}")

    print(f"\n{'='*78}")
    print(f"  机制 B：top40 侵入分析（nolimit 相对 g60）")
    n_int = len(intrusions)
    int_rets = [x["fwd6"] for x in intrusions if x["fwd6"] is not None]
    dis_rets = [x["fwd6"] for x in displaced if x["fwd6"] is not None]
    print(f"  被增速上限挡出 top40 的股票: {n_int} 只-期 | 前瞻6M均值 "
          f"{(avg(int_rets) if int_rets else float('nan')):+.2%} | "
          f"胜率 {(sum(1 for r in int_rets if r > 0)/len(int_rets) if int_rets else 0):.1%}"
          f" (n={len(int_rets)})")
    print(f"  因侵入被挤出 top40 的股票: {len(displaced)} 只-期 | 前瞻6M均值 "
          f"{(avg(dis_rets) if dis_rets else float('nan')):+.2%}")
    print("\n  侵入明细（增速>60 且 PEG≤1 且 PE 低于 g60 cutoff）:")
    for x in intrusions:
        r6 = "--" if x["fwd6"] is None else f"{x['fwd6']:+.1%}"
        print(f"    [{x['month']}] {x['tk']:<10s} {x['name'][:6]:6s} "
              f"PE={x['pe']:>5.1f} 增速={x['exp_g']:>6.1f}% PEG={x['peg']:>5.2f} "
              f"前瞻6M={r6}")
    if displaced:
        print("\n  被挤出明细:")
        for x in displaced:
            r6 = "--" if x["fwd6"] is None else f"{x['fwd6']:+.1%}"
            print(f"    [{x['month']}] {x['tk']:<10s} {x['name'][:6]:6s} "
                  f"PE={x['pe']:>5.1f} 增速={x['exp_g']:>6.1f}% 前瞻6M={r6}")

    # ---------- 落盘 ----------
    out = {
        "results": {v: {k: r[k] for k in ("name", "total", "ann", "mdd",
                                          "excess_idx", "n_days")}
                    for v, r in results.items()},
        "navs": {v: results[v]["nav"] for v in results},
        "idx": {"total": idx_total, "mdd": idx_mdd},
        "bucket_stats": {lab: {k: v for k, v in bs.items() if not k.endswith("_list")}
                         for lab, bs in bucket_stats.items()},
        "bucket_by_period": bucket_by_period,
        "per_period": per_period,
        "intrusions": intrusions,
        "displaced": displaced,
        "variants": {v: {"g_ceil": (None if g >= 1e8 else g), "peg_ceil": p, "sort": s}
                     for v, (g, p, s) in VARIANTS.items()},
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_bt_garp_ceiling_results.json")
    json.dump(out, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n结果 → {out_path}")


if __name__ == "__main__":
    main()
