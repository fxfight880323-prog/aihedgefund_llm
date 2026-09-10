# -*- coding: utf-8 -*-
"""q20 管线 + PB band 规避层 —— 对照回测。

目的：验证「PB 5年分位>90% 规避」层在 q20 管线上是否像 LX-core 那样正贡献。

铁律对齐（docs/prompt_template_fund_framework.md）：
  #1 真实数据（band 分位来自日频估值 parquet，非合成）
  #2 池子 = 万得全A PIT（L.PIT_DATES 10 期）
  #3 日频统计 / #4 复权 / #5 同口径基准 / #6 零未来函数（band 窗口 [as_of-5y, as_of]）
  #8 先对比再下结论（等权 PIT 基准）
  #9 MDD 日频标准口径
  #10 金融不剔除（回测管线含金融，band 只做规避层）

band 口径（与 _bt_band_calc.py / valuation-band-screen 一致）：
  pb_pct = (窗口[as_of-5y, as_of] 内 pb < 当日pb).mean()*100，样本<60交易日→无效(None，不剔除)
  规避 = pb_pct > BAND_CEIL
  缺失票（band 无数据）= 不规避（保守，避免数据缺失误杀）

变体矩阵：
  A_top40          q20 排序 top40, cap8, 无 gate, 无 band（锚点 = 实盘 Q20·质衡优选口径）
  A_top40_band90   + PB>90% 规避
  A_top40_band80   + PB>80% 规避（敏感性）
  AD_top15         q20 + mom60_top50 gate, top15, cap8, 无 band（Pareto 最优锚点）
  AD_top15_band90  + PB>90% 规避
  AD_top15_band80  + PB>80% 规避（敏感性）
"""
from __future__ import annotations
import json, os, sys, datetime, bisect, math
import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import load_all, load_bars

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _bt_q20_pareto as P

PIT_DATES = L.PIT_DATES
RF_ANNUAL = 0.02
BAND_FILE = "_bt_band_pb_pct.json"

# (label, N, gate_name, band_ceil)  band_ceil=None 表示不加 band 层
VARIANTS = [
    ("A_top40",          40, None,           None),
    ("A_top40_band90",   40, None,           90.0),
    ("A_top40_band80",   40, None,           80.0),
    ("AD_top15",         15, "mom60_top50",  None),
    ("AD_top15_band90",  15, "mom60_top50",  90.0),
    ("AD_top15_band80",  15, "mom60_top50",  80.0),
]


def apply_band(bp, month, band, band_ceil):
    """剔除 PB 分位 > band_ceil 的票；band 缺失(pb_pct=None)不剔除。"""
    if band_ceil is None:
        return bp
    bmap = band.get(month, {})
    out = []
    for s in bp:
        r = bmap.get(s["tk"])
        if r is None or r.get("pb_pct") is None:
            out.append(s)          # band 缺失 → 保留（保守）
        elif r["pb_pct"] <= band_ceil:
            out.append(s)
        # else: pb_pct > ceil → 剔除
    return out


def main():
    print("=" * 88)
    print("  q20 管线 + PB band 规避层 · 对照回测")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    band = json.load(open(BAND_FILE, encoding="utf-8"))
    print(f"band 快照: {len(band)} 期, 覆盖月份 {sorted(band.keys())}")

    # 每期 base pool
    base_pools = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        base_pools[month] = P.screen_q20(month, members, vv, ff, cc)

    # 每期动量信号
    mom_ctx = {}
    for month, as_of in PIT_DATES:
        m, elig = P.build_mom_series(bars, all_dates, as_of)
        m60_vals = sorted([v["mom60"] for v in m.values() if v["mom60"] is not None])
        mom60_pct = {}
        for tk, v in m.items():
            if v["mom60"] is not None and m60_vals:
                pos = bisect.bisect_left(m60_vals, v["mom60"])
                mom60_pct[tk] = pos / len(m60_vals) * 100.0
        mom_ctx[month] = {"mom": m, "mom60_pct": mom60_pct}

    results = {}
    band_diag = {}   # 每期每变体 band 剔除明细
    print("\n[回测]（含成本 5bp+10bp，cap8 加权）…")

    for label, n_top, gate_name, band_ceil in VARIANTS:
        all_w = []
        diag = {}
        for month, asof in PIT_DATES:
            bp = base_pools[month]
            n_before = len(bp)
            # 1) band 规避层
            bp_banded = apply_band(bp, month, band, band_ceil)
            n_band_drop = n_before - len(bp_banded)
            # 2) gate
            if gate_name:
                ctx = mom_ctx[month]
                bp_banded = [s for s in bp_banded if P.GATES[gate_name](s, ctx)]
            # 3) 排序取 topN
            picked = sorted(bp_banded, key=lambda s: -s["blend"])[:n_top]
            w = P.cap_weight(picked, 0.08)
            all_w.append(w)
            diag[month] = {"n_pool": n_before, "n_band_drop": n_band_drop,
                           "n_after": len(picked)}

        # 覆盖率：持仓中 band 缺失 + 高位
        miss = sum(1 for month, _ in PIT_DATES
                   for tk in all_w[PIT_DATES.index((month, _))] if tk not in px_syms)

        w_by_dt = {}
        for (month, asof), w in zip(PIT_DATES, all_w):
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = w

        r = G.run(label, w_by_dt, bars)
        r["yearly"] = P.yearly(r["nav"])
        r["avg_holdings"] = sum(len(w) for w in all_w) / len(all_w)
        top3, hhi, neff = P.conc_metrics(all_w)
        r["top3"] = top3
        r["neff"] = neff
        r["n_target"] = n_top
        sharpe_data = P.compute_sharpe(r["nav"])
        r["sharpe"] = sharpe_data["sharpe"] if sharpe_data else None
        r["ann_vol"] = sharpe_data["ann_vol"] if sharpe_data else None
        r["calmar"] = r["ann"] / r["mdd"] if r["mdd"] and r["mdd"] > 0 else None
        r["band_ceil"] = band_ceil

        results[label] = r
        band_diag[label] = diag
        sharpe_s = f"{r['sharpe']:.2f}" if r['sharpe'] is not None else "N/A"
        print(f"  {label:18s}: 总 {r['total']*100:+7.1f}% 年化 {r['ann']*100:+5.1f}% "
              f"MDD {r['mdd']*100:6.1f}% | 夏普 {sharpe_s} | N {r['avg_holdings']:.1f}")

    # 每期 band 剔除统计（只统计 band 变体）
    print("\n[band 层每期剔除明细] 池 → band剔除 → gate后 → 最终持仓:")
    for label, n_top, gate_name, band_ceil in VARIANTS:
        if band_ceil is None:
            continue
        print(f"  {label} (PB>{band_ceil:.0f}% 剔除):")
        for month, _ in PIT_DATES:
            d = band_diag[label][month]
            print(f"    [{month}] 池={d['n_pool']} 剔除={d['n_band_drop']} 最终={d['n_after']}")

    # 等权 PIT 基准（铁律 #8）
    print("\n[等权 PIT 基准对照]")
    # 复用 _bt_garp 的等权基准？这里用简单口径：每期等权全A nav
    # 直接调 G 跑一个等权全A（每期 PIT 成分等权）
    ew_w = {}
    for month, asof in PIT_DATES:
        members = univ.get(month, [])
        members = [tk for tk in members if tk in px_syms]
        if not members:
            continue
        w = {tk: 1.0 / len(members) for tk in members}
        trig = max(d for d in all_dates if d <= asof)
        ew_w[trig] = w
    if ew_w:
        r_ew = G.run("EW_PIT", ew_w, bars)
        print(f"  等权PIT: 总 {r_ew['total']*100:+7.1f}% 年化 {r_ew['ann']*100:+5.1f}% "
              f"MDD {r_ew['mdd']*100:6.1f}%")
        for label, r in results.items():
            r["excess_ew"] = r["total"] - r_ew["total"]
    else:
        r_ew = None

    # 汇总
    print("\n[汇总对比] 总收益 × 年化 × MDD × 夏普 × Calmar × N × 超额EW:")
    print(f"{'变体':<18}{'总收益':>9}{'年化':>8}{'MDD':>8}{'夏普':>7}{'Calmar':>8}"
          f"{'N':>6}{'超额EW':>9}")
    for label, n_top, gate_name, band_ceil in VARIANTS:
        r = results[label]
        sharpe_s = f"{r['sharpe']:.2f}" if r['sharpe'] is not None else "  N/A"
        calmar_s = f"{r['calmar']:.2f}" if r['calmar'] is not None else "  N/A"
        ex_s = f"{r['excess_ew']*100:+7.1f}pp" if "excess_ew" in r and r["excess_ew"] is not None else "  N/A"
        print(f"{label:<18}{r['total']*100:+8.1f}%{r['ann']*100:+7.1f}%"
              f"{r['mdd']*100:7.1f}%{sharpe_s:>7}{calmar_s:>8}{r['avg_holdings']:>5.1f}{ex_s:>9}")

    # 保存
    out = {
        "meta": {"run_at": datetime.datetime.now().isoformat()[:19],
                 "method": "q20 排序 + 可选 mom60_top50 gate × cap8 × 可选 PB band 规避层",
                 "band_ceil_options": [90.0, 80.0],
                 "band_file": BAND_FILE,
                 "band_missing_policy": "缺失票(pb_pct=None)不剔除（保守）",
                 "freq": "日频+复权", "rf_annual": RF_ANNUAL},
        "results": {label: {"total": r["total"], "ann": r["ann"],
                            "mdd": r["mdd"], "sharpe": r["sharpe"],
                            "ann_vol": r["ann_vol"], "calmar": r["calmar"],
                            "avg_holdings": r["avg_holdings"],
                            "excess_ew": r.get("excess_ew"),
                            "n_target": r["n_target"],
                            "top3": r["top3"], "neff": r["neff"],
                            "yearly": r["yearly"], "band_ceil": r["band_ceil"]}
                    for label, r in results.items()},
        "band_diag": band_diag,
        "ew": {"total": r_ew["total"], "ann": r_ew["ann"], "mdd": r_ew["mdd"]} if r_ew else None,
    }
    json.dump(out, open("_bt_q20_band_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_q20_band_results.json")


if __name__ == "__main__":
    main()
