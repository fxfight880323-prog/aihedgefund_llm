# -*- coding: utf-8 -*-
"""LX-core / garp(g60) 收益四环节归因分解。

问题（承接"申万估值因子 IC≈0 与 PE升序 top40 日频 alpha 的矛盾"）:
  g60_full = 增速≤60% + PEG≤1 + mv≥100亿 + PE升序 top40 等权，总收益 +67.01%。
  alpha 到底来自哪一环？把收益拆成 4+1 个可独立拆除的环节。

方法双轨（全部 full 基座 = 含金融，日频+复权口径）:
  Part 1 面板等权（构建法）—— 全市场 5730 只日收益面板，无成本，半年调仓等权漂移。
          从"全A等权"逐步加过滤器，每步增量 = 该环节贡献（无丢股、无覆盖偏差）:
            全A等权 → mv30 → mv100 → +L4(PE≤25或dy≥2%) → +L5(g≤60&PEG≤1)
  Part 2 价格回测（拆除法）—— 530 只复权日K，含成本(5bp+10bp)，与 _bt_garp_audit 同口径。
          从 g60 逐个拆除单一环节（ceteris paribus）:
            PEG门控(g60 vs no_peg) / PE排序方向(g60 vs pe_desc) /
            等权构建(g60 vs mvweight) / 排序必要性(g60 vs pool_ew) /
            市值约束档位(g60 vs mv30/mv0)

锚点校验（Type D 铁律）:
  all_ew 面板等权 ≈ +41.13%（_bt_daily_ew_hold_nav.json）
  g60 价格回测 ≈ +67.01%（_bt_garp_audit_results.json rerun.full.g60）
"""
import json, os, sys, datetime, statistics
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
PE_CEIL, DIV_YIELD = L.PE_CEIL, L.DIV_YIELD
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP
CAPITAL = 1_000_000.0

G60_G, G60_PEG = 60.0, 1.0


# ===========================================================================
# 数据装载
# ===========================================================================
def load_all():
    univ = L.load_universe()          # {month: [tk]}
    cons = L.load_consensus()         # {month: {tk: record}}
    val = L.load_map(L.VAL_FILE)      # {month: {tk: record}}
    fac = L.load_map(L.FAC_FILE)
    fin = G.load_fin()
    names = {}
    try:
        d = json.load(open("_bt_band_names.json", encoding="utf-8"))
        names = d if isinstance(d, dict) else {}
    except Exception:
        pass
    return univ, cons, val, fac, fin, names


# ===========================================================================
# 灵活筛选（full 基座，excl_fin 可空）
# ===========================================================================
def screen_decomp(month, univ, val, fac, cons, excl_fin,
                  mv_floor_yi, g_ceil, peg_ceil, l4_on, l5_on):
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
        if mv is None or mv < mv_floor_yi * 10000:
            continue
        if pe is None or pe <= 0:
            continue
        if l4_on and not ((pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)):
            continue
        if l5_on and not (exp_g is not None and exp_g <= g_ceil
                          and peg is not None and 0 < peg <= peg_ceil):
            continue
        if tk in excl_fin:
            continue
        pool.append({"tk": tk, "pe": pe, "mv": mv, "exp_g": exp_g or 0,
                     "peg": peg or 0})
    return pool


# ===========================================================================
# Part 1 面板等权（构建法）
# ===========================================================================
def panel_ew_nav(wide, idx, members_by_month):
    """半年调仓等权 + 期间权重漂移（与 _bt_daily_ew_hold.py 同口径）。"""
    trig_days = {}
    for month, as_of in PIT_DATES:
        trig = max(d for d in idx if d <= as_of)
        trig_days[month] = trig
    nav, cur = {}, 1.0
    w, members = None, None
    ret_cols = wide.columns
    for dt in idx:
        for month, trig in trig_days.items():
            if dt == trig:
                ms = [tk for tk in members_by_month.get(month, []) if tk in ret_cols]
                n = len(ms)
                w = pd.Series(1.0 / n, index=sorted(ms)) if n else None
                break
        if w is None:
            nav[dt] = cur
            continue
        rets = wide.loc[dt, w.index].fillna(0.0)
        r_d = float((w * rets).sum())
        w = w * (1.0 + rets) / (1.0 + r_d)
        cur *= (1.0 + r_d)
        nav[dt] = cur
    return {dt: v for dt, v in nav.items() if dt >= "2021-06-01"}


def nav_metrics(nav):
    dts = sorted(nav)
    total = nav[dts[-1]] - 1.0
    yrs = len(dts) / 252.0
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1.0
    peak, mdd = 1.0, 0.0
    for v in nav.values():
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return {"total": total, "ann": ann, "mdd": mdd, "n_days": len(dts)}


# ===========================================================================
# Part 2 价格回测（拆除法）
# ===========================================================================
def load_bars(px_full):
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
    return bars, all_dates


def build_weights(picked, weight_mode):
    """picked: list[dict(tk, pe, mv, ...)] → {tk: weight}"""
    if weight_mode == "equal":
        n = len(picked)
        w = round(min(1.0 / max(n, 1), PER_NAME_CAP), 4)
        return {s["tk"]: w for s in picked}
    if weight_mode == "mv":
        tot = sum(s["mv"] for s in picked)
        if tot <= 0:
            n = len(picked)
            return {s["tk"]: 1.0 / max(n, 1) for s in picked}
        return {s["tk"]: s["mv"] / tot for s in picked}
    raise ValueError(weight_mode)


def main():
    print("=" * 88)
    print("  LX-core / garp(g60) 四环节归因分解（日频+复权，full 基座）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    fin = set()  # full 基座：不剔除金融

    # ---- 全市场面板 ----
    print("\n[数据] 读取全市场日收益面板…")
    wide = pd.read_parquet("_bt_ew_daily/wide_daily_return.parquet")
    idx = sorted(wide.index)
    print(f"  宽表: {wide.shape[0]} 天 × {wide.shape[1]} 只 | {idx[0]} ~ {idx[-1]}")

    # ---- 每期成员（各变体池子）----
    print("\n[筛选] 逐期构建各变体池子…")
    # Part1 面板变体: key -> {month: [tk]}
    panel_members = {k: {} for k in
                     ["all_ew", "mv30_ew", "mv100_ew", "l4_ew", "pool_ew"]}
    # Part2 价格变体: key -> {month: [dict(tk,pe,mv)]}
    price_pools = {k: {} for k in
                   ["g60", "no_peg", "pe_desc", "mvweight", "pool_ew_bt",
                    "mv30_top40", "mv0_top40"]}
    pool_sizes = {k: [] for k in price_pools}

    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        m = members
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        # Part1 面板成员（全市场，无金融剔除）
        panel_members["all_ew"][month] = m
        panel_members["mv30_ew"][month] = [s["tk"] for s in screen_decomp(
            month, m, vv, ff, cc, set(), 30.0, 1e9, 1e9, False, False)]
        panel_members["mv100_ew"][month] = [s["tk"] for s in screen_decomp(
            month, m, vv, ff, cc, set(), 100.0, 1e9, 1e9, False, False)]
        panel_members["l4_ew"][month] = [s["tk"] for s in screen_decomp(
            month, m, vv, ff, cc, set(), 100.0, 1e9, 1e9, True, False)]
        panel_members["pool_ew"][month] = [s["tk"] for s in screen_decomp(
            month, m, vv, ff, cc, set(), 100.0, G60_G, G60_PEG, True, True)]

        # Part2 价格池子（full 基座）
        def pool_for(mv_floor, g, peg, l4=True, l5=True):
            return screen_decomp(month, m, vv, ff, cc, set(), mv_floor, g, peg, l4, l5)

        p_g60 = pool_for(100.0, G60_G, G60_PEG)
        p_nopeg = pool_for(100.0, G60_G, 1e9)
        p_mv30 = pool_for(30.0, G60_G, G60_PEG)
        p_mv0 = pool_for(0.0, G60_G, G60_PEG)

        # 排序
        def top40(pool, key):
            sp = sorted(pool, key=key)
            return sp[:MAX_HOLDINGS]

        price_pools["g60"][month] = top40(p_g60, lambda s: s["pe"])
        price_pools["no_peg"][month] = top40(p_nopeg, lambda s: s["pe"])
        price_pools["pe_desc"][month] = top40(p_g60, lambda s: -s["pe"])
        price_pools["mvweight"][month] = top40(p_g60, lambda s: s["pe"])
        price_pools["pool_ew_bt"][month] = p_g60            # 池子全体，不截断
        price_pools["mv30_top40"][month] = top40(p_mv30, lambda s: s["pe"])
        price_pools["mv0_top40"][month] = top40(p_mv0, lambda s: s["pe"])

        for k in price_pools:
            pool_sizes[k].append(len(price_pools[k][month]))

        print(f"  [{month}] univ={len(m)} all_ew={len(m)} mv30={len(panel_members['mv30_ew'][month])} "
              f"mv100={len(panel_members['mv100_ew'][month])} l4={len(panel_members['l4_ew'][month])} "
              f"pool={len(p_g60)} | top40 g60={len(price_pools['g60'][month])} "
              f"mv30pool={len(p_mv30)} mv0pool={len(p_mv0)}")

    # ---- Part1 面板等权回测 ----
    print("\n[Part1] 面板等权（构建法，全市场覆盖，无成本）…")
    panel_nav = {}
    for k in panel_members:
        nav = panel_ew_nav(wide, idx, panel_members[k])
        panel_nav[k] = nav_metrics(nav)
        print(f"  {k:12s}: 总 {panel_nav[k]['total']:+7.2%} 年化 {panel_nav[k]['ann']:+6.2%} "
              f"MDD {panel_nav[k]['mdd']:6.2%} | {panel_nav[k]['n_days']} 天")

    # 锚点1：全A等权 ≈ +41.13%
    ew_hold = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))
    print(f"  [锚点1] all_ew={panel_nav['all_ew']['total']:+.4f} vs 基准 "
          f"{ew_hold['total']:+.4f} (期望一致)")

    # ---- Part2 价格回测 ----
    print("\n[Part2] 价格回测（拆除法，530 只复权，含成本 5bp+10bp）…")
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"  复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # Type D 覆盖审计
    print("  [覆盖审计] 各变体选股并集 vs 530 只覆盖差集（丢股数）:")
    cov_report = {}
    for k in price_pools:
        miss = {}
        for month, _ in PIT_DATES:
            picked = price_pools[k][month]
            m = [s["tk"] for s in picked if s["tk"] not in px_syms]
            if m:
                miss[month] = m
        cov_report[k] = miss
        total_miss = sum(len(x) for x in miss.values())
        flag = "⚠️ 丢股" if total_miss else "✓ 全覆盖"
        print(f"    {k:12s}: {total_miss:3d} 只-期 缺失 {flag}")

    price_res = {}
    for k in price_pools:
        w_by_dt = {}
        for month, asof in PIT_DATES:
            picked = price_pools[k][month]
            if k == "mvweight":
                wgt = build_weights(picked, "mv")
            else:
                wgt = build_weights(picked, "equal")
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = wgt
        r = G.run(k, w_by_dt, bars)
        price_res[k] = r
        print(f"  {k:12s}: 总 {r['total']:+7.2%} 年化 {r['ann']:+6.2%} MDD {r['mdd']:6.2%}")

    # 锚点2：g60 ≈ +67.01%
    audit = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
    g60_hist = audit["rerun"]["full"]["g60"]["total"]
    print(f"  [锚点2] g60={price_res['g60']['total']:+.4f} vs audit {g60_hist:+.4f} (期望一致)")

    # ---- 落盘 ----
    out = {
        "meta": {
            "run_at": datetime.datetime.now().isoformat()[:19],
            "base": "full (含金融)", "freq": "日频+复权",
            "window_px": [all_dates[0], all_dates[-1]],
            "window_panel": [idx[0], idx[-1]],
        },
        "anchors": {
            "all_ew": panel_nav["all_ew"]["total"],
            "ew_hold_hist": ew_hold["total"],
            "g60": price_res["g60"]["total"],
            "g60_audit_hist": g60_hist,
        },
        "panel": panel_nav,
        "panel_pool_sizes": {k: [len(v) for v in panel_members[k].values()]
                             for k in panel_members},
        "price": price_res,
        "price_pool_sizes": pool_sizes,
        "coverage": cov_report,
    }
    json.dump(out, open("_bt_garp_decompose_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_decompose_results.json")


if __name__ == "__main__":
    main()
