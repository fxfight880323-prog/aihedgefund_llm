# -*- coding: utf-8 -*-
"""core(garp门控/含金融) vs LX-gm(质量过滤版=core+gpm≥全市场中位数) 日频回测对比。

口径 = _bt_garp_audit.py 权威口径:
  池子  = 万得全A PIT 成分（10期）;  全池基座(不剔金融)
  L4    = PE≤25 或 股息率≥2%
  L5    = garp: 增速≤60% 且 0<PEG≤1
  排序  = PE 升序 top40 等权(单票≤5%)
  gm    = L4+L5 命中池 内 gpm≥全市场中位数 → 再 PE 升序 top40
  引擎  = 日频复权 + 半年度调仓 + T+1 撮合 + 5bp费率+10bp滑点
  价格  = _bt_daily_px_full.json (497 只, 审计补拉全量)

锚点: core/full 应复现 garp 审计 full/g60 = +67.01% / MDD 16.67%
"""
from __future__ import annotations
import json
import statistics
import sys
from collections import Counter

sys.path.insert(0, "D:/workspace/ai_fund_framework")
sys.stdout.reconfigure(encoding="utf-8")
os_cwd = "D:/workspace/ai_fund_framework"

import _lx_allA_variant as L
import _bt_garp as G
from src.backtest.engine import BarData

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP
CAPITAL = 1_000_000.0
G_CEIL, PEG_CEIL = 60.0, 1.0   # garp 现行门控


def screen_gm(month, univ, val, fac, cons):
    """core(pe升序40) + gm(gpm≥中位→pe升序40)，双名单返回。
    与 G.screen_garp(g_ceil=60, peg_ceil=1, 'pe', excl_fin=set()) 同基座，
    gm 在其 pool 上追加质量过滤（gpm≥pool内真实gpm中位数，与 kfin screen 同口径）。
    """
    pool = []
    gpm_vals = []
    stats = Counter()
    for tk in univ:
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}
        mv = L._num(v.get("total_mv"))
        pe = L._num(v.get("pe_ttm"))
        dy = L._num(f.get("dtop5"))
        exp_g = L._num(c.get("con_np_yoy"))
        peg = L._num(c.get("con_peg"))
        gpm = L._num(f.get("gpm"))
        stats["uni"] += 1
        if mv is None or mv < 100 * 10000:
            stats["drop_mv"] += 1
            continue
        if pe is None or pe <= 0:
            stats["drop_pe"] += 1
            continue
        if not ((pe <= L.PE_CEIL) or (dy is not None and dy >= L.DIV_YIELD)):
            stats["drop_l4"] += 1
            continue
        if not (exp_g is not None and exp_g <= G_CEIL
                and peg is not None and 0 < peg <= PEG_CEIL):
            stats["drop_l5"] += 1
            continue
        gpm_v = gpm if gpm is not None else 0.0
        if gpm is not None:
            gpm_vals.append(gpm)
        pool.append({"tk": tk, "pe": pe, "dy": dy or 0, "exp_g": exp_g or 0,
                     "peg": peg or 0, "gpm": gpm_v, "gpm_raw": gpm})
    if not pool:
        return [], [], dict(stats), None
    gmed = statistics.median(gpm_vals) if gpm_vals else None
    pool.sort(key=lambda s: s["pe"])
    core40 = [s["tk"] for s in pool[:MAX_HOLDINGS]]
    gm_pool = [s for s in pool if s["gpm"] >= gmed] if gmed is not None else pool
    gm_pool.sort(key=lambda s: s["pe"])
    gm40 = [s["tk"] for s in gm_pool[:MAX_HOLDINGS]]
    stats["pool"] = len(pool)
    stats["gm_pass"] = len(gm_pool)
    stats["gpm_median"] = gmed
    return core40, gm40, dict(stats), gmed


def build_bars(px):
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
    return bars


def main():
    print("=" * 78)
    print("  core(garp/全池) vs LX-gm(质量过滤) 日频回测")
    print("=" * 78)
    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    fin = G.load_fin()

    px = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars = build_bars(px)
    all_dates = sorted({dt for m in bars.values() for dt in m})
    print(f"bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # ---- 每期名单 ----
    w_core, w_gm, meta = {}, {}, {}
    miss_core = miss_gm = 0
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        c40, g40, st, gmed = screen_gm(month, members, val.get(month, {}),
                                       fac.get(month, {}), cons.get(month, {}))
        w_core[month] = c40
        w_gm[month] = g40
        meta[month] = st
        mc = [t for t in c40 if t not in bars]
        mg = [t for t in g40 if t not in bars]
        miss_core += len(mc)
        miss_gm += len(mg)
        print(f"{month}: pool={st['pool']} gm_pass={st['gm_pass']} "
              f"gpm中位={st['gpm_median']:.2f} core缺价={len(mc)} gm缺价={len(mg)}")
    print(f"\n缺价合计: core {miss_core} | gm {miss_gm}")
    if miss_core or miss_gm:
        print("!! 存在缺价股票，需补拉腾讯日K后再跑")
        json.dump({"w_core": w_core, "w_gm": w_gm, "meta": meta},
                  open("_bt_gm_weights.json", "w", encoding="utf-8"), ensure_ascii=False)
        sys.exit(2)

    # ---- 触发日映射（同审计 rerun：月末最近交易日收盘触发 → 引擎次日开盘成交）----
    def to_weights(weights):
        wd = {}
        for month, as_of in PIT_DATES:
            trig = max(d for d in all_dates if d <= as_of)
            wd[trig] = {tk: round(1.0 / MAX_HOLDINGS, 4) for tk in weights[month]}
        return wd

    res_core = G.run("core", to_weights(w_core), bars)
    res_gm = G.run("gm", to_weights(w_gm), bars)

    print(f"\ncore(garp/全池): total={res_core['total']:+.2%} ann={res_core['ann']:+.2%} "
          f"mdd={res_core['mdd']:.2%}")
    print(f"gm(质量过滤)  : total={res_gm['total']:+.2%} ann={res_gm['ann']:+.2%} "
          f"mdd={res_gm['mdd']:.2%}")
    print(f"锚点校验: core/full 期望 +67.01% → 实际 {res_core['total']:+.2%} "
          f"(差 {(res_core['total']-0.6701):+.2%})")

    # ---- 基准 nav ----
    ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))["nav"]
    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    out = {
        "core": res_core["nav"], "gm": res_gm["nav"],
        "ew": [{"date": d, "nav": v} for d, v in sorted(ew.items()) if d >= "2021-06-01"],
        "idx": [{"date": d, "nav": idx[d]["close"]} for d in sorted(idx) if d >= "2021-06-01"],
        "weights": {"core": w_core, "gm": w_gm},
        "meta": meta,
        "fin": sorted(fin),
    }
    json.dump(out, open("_bt_gm_daily_data.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("saved _bt_gm_daily_data.json")


if __name__ == "__main__":
    main()
