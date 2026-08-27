# -*- coding: utf-8 -*-
"""Type D 合规审计：garp 系列回测（采纳实验 + 增速上限实验）按
docs/prompt_template_fund_framework.md（v1.0 · 2026-08-25）逐铁律校验。

审计发现的违规与修复：
  V1 [铁律10] 金融剔除(excl_fin)贯穿所有回测变体基座 → 补全池(含金融)基座复跑
  V2 [铁律5/8] 缺同口径"半年调仓等权全A"基准 → 接入 _bt_daily_ew_hold_nav.json
  V3 [⑤/铁律1] 持仓数量目标≠实际：原实验 242 只日K覆盖不全，garp 系变体
     每期 4~19 只入选股被引擎静默跳过（权重变现金）→ 补拉 255 只日K
     （_bt_daily_px_full.json 497 只）后全量复跑，并重跑机制分析
     （增速分桶前瞻收益改用全市场 5730 只日收益面板，消除覆盖偏差）

锚点校验：
  - core/全池基座 应复现 LX-core 日频+复权 +55.55%
  - core/finex 基座 应复现历史 finex +29.45%（原实验该变体全覆盖，数字有效）
"""
import json, os, sys, datetime
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import numpy as np
import pandas as pd

import _lx_allA_variant as L
import _bt_garp as G
from src.backtest.engine import BarData

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP
CAPITAL = 1_000_000.0

# 14 变体 × 双基座；finex=剔除金融(原实验基座)，full=全池(铁律10合规基座)
VARIANTS = {
    "core":      (25.0, 2.0, "pe"),
    "g40p2":     (40.0, 2.0, "pe"),
    "g60p2":     (60.0, 2.0, "pe"),
    "g99":       (99.0, 2.0, "pe"),
    "g30":       (30.0, 1.0, "pe"),
    "g40":       (40.0, 1.0, "pe"),
    "g60":       (60.0, 1.0, "pe"),      # garp 现行
    "g80":       (80.0, 1.0, "pe"),
    "g100":      (100.0, 1.0, "pe"),
    "g150":      (150.0, 1.0, "pe"),
    "nolimit":   (1e9,  1.0, "pe"),
    "peg_sort":  (60.0, 2.0, "peg"),
    "garp_q20":  (60.0, 1.0, "blend20"),
    "garp_q50":  (60.0, 1.0, "blend50"),
}
BASES = {"finex": True, "full": False}

BUCKETS = [(0.0, 30.0), (30.0, 60.0), (60.0, 100.0), (100.0, 200.0), (200.0, 1e18)]
BUCKET_LABELS = ["0-30%", "30-60%", "60-100%", "100-200%", "200%+"]


def load_names():
    try:
        d = json.load(open("_bt_band_names.json", encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def build_pool(month, univ, val, fac, cons, excl_fin, g_ceil, peg_ceil):
    """PEG≤1 池（机制分析用，与 _bt_garp_ceiling.build_pool 同口径）。"""
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


def main():
    print("=" * 78)
    print("  Type D 合规审计：garp 系列回测 × prompt_template_fund_framework.md")
    print("=" * 78)

    # ---------------- 数据装载 ----------------
    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    fin = G.load_fin()
    names = load_names()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars = {}
    for tk, d in px_full.items():
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
    print(f"复权 bar（修复后）: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dts = sorted(d for d in idx if d >= "2021-06-01")
    idx_base = idx[idx_dts[0]]["close"]
    idx_total = idx[idx_dts[-1]]["close"] / idx_base - 1.0
    idx_mdd = G.mdd_of([idx[d]["close"] / idx_base for d in idx_dts])

    ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))
    ew_total, ew_ann, ew_mdd = ew["total"], ew["ann"], ew["mdd"]
    ew_dts = sorted(ew["nav"].keys())
    print(f"基准: 半年调仓等权全A {ew_total:+.2%}/MDD {ew_mdd:.2%} | "
          f"中证全指 {idx_total:+.2%}/MDD {idx_mdd:.2%}")

    # 原实验（污染）结果
    old_ceiling = json.load(open("_bt_garp_ceiling_results.json", encoding="utf-8"))
    old_adopt = json.load(open("_bt_garp_results.json", encoding="utf-8"))

    # ---------------- 静态检查点 ----------------
    print("\n[静态检查点]")
    pit_counts = {m: len(univ.get(m, [])) for m, _ in PIT_DATES}
    print(f"  铁律2 PIT池: {pit_counts}")
    px_syms = set(px_full.keys())
    # 原实验丢股记录（finex 基座 8 变体，对旧 242 只覆盖）
    px_old = json.load(open("_bt_daily_px.json", encoding="utf-8"))
    px_old_syms = set(px_old.keys())
    cov_before = {}
    for v, (g, p, s) in VARIANTS.items():
        miss = {}
        for month, as_of in PIT_DATES:
            members = univ.get(month, [])
            excl = {t for t in members if t in fin}
            picked, _ = G.screen_garp(month, members, val.get(month, {}),
                                      fac.get(month, {}), cons.get(month, {}),
                                      excl, g, p, s)
            m = [x["tk"] for x in picked if x["tk"] not in px_old_syms]
            if m:
                miss[month] = len(m)
        cov_before[v] = miss
    # 修复后覆盖（双基座断言）
    cov_after_ok = True
    for v, (g, p, s) in VARIANTS.items():
        for month, as_of in PIT_DATES:
            members = univ.get(month, [])
            excl = {t for t in members if t in fin}
            for base in (excl, set()):
                picked, _ = G.screen_garp(month, members, val.get(month, {}),
                                          fac.get(month, {}), cons.get(month, {}),
                                          base, g, p, s)
                if any(x["tk"] not in px_syms for x in picked):
                    cov_after_ok = False
    print(f"  持仓数量: 原实验丢股(finex基座) {cov_before} | 修复后全覆盖: {cov_after_ok}")
    # 复权有效性抽样
    n_ratio, n_tot = 0, 0
    for tk in list(px_full)[:80]:
        for dt, r in list(px_full[tk].items())[:3]:
            if r.get("close") and r.get("adj"):
                n_tot += 1
                if abs(r["adj"] / r["close"] - 1.0) > 1e-6:
                    n_ratio += 1
    print(f"  铁律4 复权: 抽样 {n_tot} 条中 {n_ratio} 条 adj≠close "
          f"({n_ratio/max(n_tot,1):.0%} 存在复权调整)")

    # ---------------- 双基座 × 14 变体复跑 ----------------
    print("\n[复跑] 双基座 × 14 变体（全 497 只日K覆盖）")
    rerun = {"finex": {}, "full": {}}
    holdings_log = {"finex": {}, "full": {}}
    for base_name, use_finex in BASES.items():
        for v, (g, p, s) in VARIANTS.items():
            all_weights, hold = {}, {}
            fin_pp = []
            for month, as_of in PIT_DATES:
                members = univ.get(month, [])
                excl = {t for t in members if t in fin} if use_finex else set()
                picked, st = G.screen_garp(month, members, val.get(month, {}),
                                           fac.get(month, {}), cons.get(month, {}),
                                           excl, g, p, s)
                n = len(picked)
                w = round(min(1.0 / max(n, 1), PER_NAME_CAP), 4)
                all_weights[month] = {x["tk"]: w for x in picked}
                hold[month] = picked
                fin_pp.append(sum(1 for x in picked if x["tk"] in fin))
            w_by_dt = {}
            for month, asof in PIT_DATES:
                trig = max(d for d in all_dates if d <= asof)
                w_by_dt[trig] = all_weights[month]
            r = G.run(v, w_by_dt, bars)
            r["excess_ew"] = r["total"] - ew_total
            r["excess_idx"] = r["total"] - idx_total
            r["avg_holdings"] = sum(len(h) for h in hold.values()) / len(hold)
            r["fin_per_period"] = fin_pp
            r.pop("nav", None)  # nav 单独存
            rerun[base_name][v] = r
            holdings_log[base_name][v] = hold
            print(f"  [{base_name}] {v:9s}: 总 {r['total']:+7.2%} 年化 {r['ann']:+6.2%} "
                  f"MDD {r['mdd']:6.2%} | 超EW {r['excess_ew']:+7.2%} 超指数 "
                  f"{r['excess_idx']:+7.2%} | 持仓均值 {r['avg_holdings']:.1f} "
                  f"金融/期 {fin_pp}")

    # 锚点校验
    anchors = {
        "core_full_total": rerun["full"]["core"]["total"],
        "lxcore_hist": 0.5555,
        "core_finex_total": rerun["finex"]["core"]["total"],
        "finex_hist": 0.2945,
    }
    print(f"\n[锚点] core/全池 {anchors['core_full_total']:+.2%} (期望≈+55.55%) | "
          f"core/finex {anchors['core_finex_total']:+.2%} (期望=+29.45%)")

    # ---------------- 机制分析重跑（全市场覆盖） ----------------
    print("\n[机制A] PEG≤1 池增速分桶前瞻收益（全市场 5730 只面板）")
    frames = []
    for f in sorted(os.listdir("_bt_ew_daily")):
        if f.endswith(".parquet") and not f.startswith("wide"):
            frames.append(pd.read_parquet(os.path.join("_bt_ew_daily", f),
                                          columns=["date", "stock_code", "daily_return"]))
    all_df = pd.concat(frames, ignore_index=True)
    wide = all_df.pivot_table(index="date", columns="stock_code", values="daily_return")
    wide = wide.sort_index()
    widx = list(wide.index)

    def fwd_from_panel(codes, asof, cal_days, min_frac=0.8):
        """d0=asof后首个交易日 → d0+cal_days 内最后交易日；复利日收益。"""
        dts = [d for d in widx if d >= asof]
        if not dts:
            return {}
        d0 = dts[0]
        t0 = datetime.date.fromisoformat(d0)
        tgt = (t0 + datetime.timedelta(days=cal_days)).isoformat()
        cand = [d for d in dts if d <= tgt]
        if not cand:
            return {}
        d1 = cand[-1]
        span = (datetime.date.fromisoformat(d1) - t0).days
        if span < cal_days * min_frac:
            return {}
        sub = wide.loc[d0:d1, [c for c in codes if c in wide.columns]]
        valid = sub.notna().sum(axis=0)
        need = max(int(len(cand) * min_frac), 1)
        ok = valid[valid >= need].index
        rets = (1.0 + sub[ok]).prod(axis=0, skipna=True) - 1.0
        return {c: float(rets[c]) for c in ok if rets[c] == rets[c]}

    bucket_stats = {lab: {"n": 0, "sum_pe": 0.0, "sum_peg": 0.0, "sum_g": 0.0,
                          "n6": 0, "sum6": 0.0, "win6": 0,
                          "n12": 0, "sum12": 0.0, "win12": 0}
                    for lab in BUCKET_LABELS}
    per_period_pool = []
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        excl_fin = {t for t in members if t in fin}
        pool = build_pool(month, members, val.get(month, {}), fac.get(month, {}),
                          cons.get(month, {}), excl_fin, 1e9, 1.0)
        codes = [s["tk"] for s in pool]
        r6 = fwd_from_panel(codes, as_of, 183)
        r12 = fwd_from_panel(codes, as_of, 365)
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
            if s["tk"] in r6:
                bs["n6"] += 1
                bs["sum6"] += r6[s["tk"]]
                bs["win6"] += 1 if r6[s["tk"]] > 0 else 0
            if s["tk"] in r12:
                bs["n12"] += 1
                bs["sum12"] += r12[s["tk"]]
                bs["win12"] += 1 if r12[s["tk"]] > 0 else 0
        per_period_pool.append({"month": month, "pool": len(pool),
                                "buckets": dict(cnt),
                                "cov6": len(r6), "cov12": len(r12)})
        print(f"  [{month}] 池={len(pool):4d} 前瞻覆盖6M={len(r6):4d} 12M={len(r12):4d} | " +
              " / ".join(f"{cnt.get(lb,0):4d}" for lb in BUCKET_LABELS))

    print("\n  分桶 → 前瞻收益（修复后，全市场覆盖）:")
    for lab in BUCKET_LABELS:
        bs = bucket_stats[lab]
        if bs["n"] == 0:
            continue
        m6 = f"{bs['sum6']/bs['n6']:+7.2%}" if bs["n6"] else "     --"
        w6 = f"{bs['win6']/bs['n6']:5.1%}" if bs["n6"] else "   --"
        m12 = f"{bs['sum12']/bs['n12']:+7.2%}" if bs["n12"] else "     --"
        w12 = f"{bs['win12']/bs['n12']:5.1%}" if bs["n12"] else "   --"
        print(f"    {lab:9s} n={bs['n']:5d} | 6M {m6} 胜率{w6} n6={bs['n6']:5d} | "
              f"12M {m12} 胜率{w12} n12={bs['n12']:5d}")

    # 机制B：top40 侵入（finex 基座，修复后全覆盖）
    print("\n[机制B] top40 侵入分析重跑（nolimit vs g60, finex 基座）")
    intrusions, displaced = [], []
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        excl_fin = {t for t in members if t in fin}
        g60_p, _ = G.screen_garp(month, members, val.get(month, {}),
                                 fac.get(month, {}), cons.get(month, {}),
                                 excl_fin, 60.0, 1.0, "pe")
        nl_p, _ = G.screen_garp(month, members, val.get(month, {}),
                                fac.get(month, {}), cons.get(month, {}),
                                excl_fin, 1e9, 1.0, "pe")
        g60_map = {s["tk"]: s for s in g60_p}
        nl_map = {s["tk"]: s for s in nl_p}
        for tk in set(nl_map) - set(g60_map):
            s = nl_map[tk]
            r6 = fwd_from_panel([tk], as_of, 183).get(tk)
            intrusions.append({"month": month, "tk": tk, "name": names.get(tk, ""),
                               "pe": round(s["pe"], 1), "exp_g": round(s["exp_g"], 1),
                               "peg": round(s["peg"], 2),
                               "fwd6": None if r6 is None else round(r6, 4)})
        for tk in set(g60_map) - set(nl_map):
            s = g60_map[tk]
            r6 = fwd_from_panel([tk], as_of, 183).get(tk)
            displaced.append({"month": month, "tk": tk, "name": names.get(tk, ""),
                              "pe": round(s["pe"], 1), "exp_g": round(s["exp_g"], 1),
                              "peg": round(s["peg"], 2),
                              "fwd6": None if r6 is None else round(r6, 4)})
    int_rets = [x["fwd6"] for x in intrusions if x["fwd6"] is not None]
    dis_rets = [x["fwd6"] for x in displaced if x["fwd6"] is not None]
    print(f"  被上限挡出 top40: {len(intrusions)} 只-期 | 前瞻6M均值 "
          f"{(sum(int_rets)/len(int_rets) if int_rets else float('nan')):+.2%} | "
          f"胜率 {(sum(1 for r in int_rets if r>0)/len(int_rets) if int_rets else 0):.1%}")
    print(f"  因侵入被挤出: {len(displaced)} 只-期 | 前瞻6M均值 "
          f"{(sum(dis_rets)/len(dis_rets) if dis_rets else float('nan')):+.2%}")

    # ---------------- 落盘 ----------------
    out = {
        "meta": {
            "run_at": datetime.datetime.now().isoformat()[:19],
            "template": "docs/prompt_template_fund_framework.md v1.0",
            "px_file": "_bt_daily_px_full.json",
            "px_stocks": len(px_full),
            "window": [all_dates[0], all_dates[-1]],
            "pit_counts": pit_counts,
            "adj_sample": {"n": n_tot, "ratio_ne1": n_ratio},
        },
        "benchmarks": {
            "ew_hold": {"total": ew_total, "ann": ew_ann, "mdd": ew_mdd,
                        "n_days": len(ew_dts), "window": [ew_dts[0], ew_dts[-1]]},
            "csi_all": {"total": idx_total, "mdd": idx_mdd,
                        "n_days": len(idx_dts), "window": [idx_dts[0], idx_dts[-1]]},
        },
        "coverage_before": cov_before,
        "coverage_after_ok": cov_after_ok,
        "rerun": rerun,
        "anchors": anchors,
        "old_ceiling_results": {k: v for k, v in old_ceiling["results"].items()},
        "old_adopt_results": {k: {kk: vv for kk, vv in v.items() if kk != "nav"}
                              for k, v in old_adopt["results"].items()},
        "bucket_stats": bucket_stats,
        "per_period_pool": per_period_pool,
        "intrusions": intrusions,
        "displaced": displaced,
    }
    json.dump(out, open("_bt_garp_audit_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_audit_results.json")


if __name__ == "__main__":
    main()
