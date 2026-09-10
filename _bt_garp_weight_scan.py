# -*- coding: utf-8 -*-
"""GARP 权重扫描：真成长 × 低估值 的权重敏感性。

背景（用户问题）：
  q20 的 blend = 0.8×PE便宜度 + 0.2×质量分（gpm+roe+cetop）。
  质量分没捕捉"成长"，反而可能被"低 PE 大盘价值股"稀释。
  目标：做"真成长 + 低估值"的 GARP，扫 value 权重 w ∈ [0,1]，
  画收益/回撤/夏普 随 w 变化的曲线。

评分维度（截面分位，越高越好）：
  value_pct  = PE 便宜度（PE 越低分位越高）
  score_pct  = 四种"非价值"分（替换质量分）：
    1. quality    : 原质量分 (gpm+con_roe+cetop)/3  —— 对照基线
    2. con_np_yoy : 一致预期净利润增速（分析师预期成长）
    3. oryoy      : 营收同比增速（真实成长·营收端）
    4. npyoy      : 净利润同比增速（真实成长·利润端）

  blend(w) = w × value_pct + (1-w) × score_pct

回测框架（与 Pareto 唯一解 AD_top15_mom60top50 完全一致，只改评分）：
  池子筛选（screen_raw）同 screen_q20；mom60_top50 gate；top15 截断；cap8 加权；
  半年调仓；日频+复权；含成本 5bp+10bp。
"""
import json, os, sys, datetime, bisect, math
import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import load_all, load_bars
import _bt_q20_pareto as P

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

PIT_DATES = L.PIT_DATES
G60_G, G60_PEG = 60.0, 1.0
RF_ANNUAL = 0.02
N_TOP = 15
CAP = 0.08

# 四种"非价值"评分维度
SCORE_MODES = ["quality", "con_np_yoy", "oryoy", "npyoy"]
W_VALUES = [i / 10.0 for i in range(11)]  # 0.0, 0.1, ..., 1.0


def screen_raw(month, univ, val, fac, cons):
    """与 screen_q20 完全一致的池子筛选，但保留原始字段，不计算 blend。"""
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
        con_roe = L._num(c.get("con_roe"))
        cetop = L._num(f.get("cetop"))
        oryoy = L._num(f.get("oryoy"))
        npyoy = L._num(f.get("npyoy"))
        pool.append({"tk": tk, "pe": pe, "mv": mv,
                     "gpm": gpm, "con_roe": con_roe, "cetop": cetop,
                     "oryoy": oryoy, "npyoy": npyoy, "con_g": exp_g})
    return pool


def add_score_pct(pool, mode):
    """给 pool 里的每只票附加 score_pct（截面分位，越高越好）+ pe_pct。"""
    pe_vals = [s["pe"] for s in pool]
    for s in pool:
        s["pe_pct"] = 100.0 - P.pct_rank(pe_vals, s["pe"])

    if mode == "quality":
        gpm_vals = [s["gpm"] for s in pool if s["gpm"] is not None]
        roe_vals = [s["con_roe"] for s in pool if s["con_roe"] is not None]
        cet_vals = [s["cetop"] for s in pool if s["cetop"] is not None]
        for s in pool:
            gp = P.pct_rank(gpm_vals, s["gpm"]) if s["gpm"] is not None else 0.0
            rp = P.pct_rank(roe_vals, s["con_roe"]) if s["con_roe"] is not None else 0.0
            cp = P.pct_rank(cet_vals, s["cetop"]) if s["cetop"] is not None else 0.0
            s["score_pct"] = (gp + rp + cp) / 3.0
    elif mode == "con_np_yoy":
        vals = [s["con_g"] for s in pool if s["con_g"] is not None]
        for s in pool:
            s["score_pct"] = P.pct_rank(vals, s["con_g"]) if s["con_g"] is not None else 0.0
    elif mode == "oryoy":
        vals = [s["oryoy"] for s in pool if s["oryoy"] is not None]
        for s in pool:
            s["score_pct"] = P.pct_rank(vals, s["oryoy"]) if s["oryoy"] is not None else 0.0
    elif mode == "npyoy":
        vals = [s["npyoy"] for s in pool if s["npyoy"] is not None]
        for s in pool:
            s["score_pct"] = P.pct_rank(vals, s["npyoy"]) if s["npyoy"] is not None else 0.0
    return pool


def main():
    print("=" * 88)
    print("  GARP 权重扫描 · 真成长 × 低估值（value 权重 w ∈ [0,1]）")
    print("=" * 88)

    univ, cons, val, fac, fin, names = load_all()
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    # 每期原始池（筛选后，未计算 blend）
    raw_pools = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
        raw_pools[month] = screen_raw(month, members, vv, ff, cc)
    print("每期原始池规模:", [len(raw_pools[m]) for m, _ in PIT_DATES])

    # 动量 context（与 Pareto 一致）
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

    results = {}   # results[mode][w] = metrics dict
    coverage = {}  # 覆盖率

    for mode in SCORE_MODES:
        # 预计算每期 pool（含 pe_pct + score_pct）
        pools = {}
        for month, as_of in PIT_DATES:
            pools[month] = add_score_pct(raw_pools[month], mode)

        results[mode] = {}
        coverage[mode] = {}
        print(f"\n[评分维度] {mode}  (w = value 权重 / PE便宜度 权重)")
        for w in W_VALUES:
            all_w = []
            for month, as_of in PIT_DATES:
                pool = pools[month]
                ctx = mom_ctx[month]
                pool = [s for s in pool if P.GATES["mom60_top50"](s, ctx)]
                for s in pool:
                    s["blend"] = w * s["pe_pct"] + (1 - w) * s["score_pct"]
                picked = sorted(pool, key=lambda s: -s["blend"])[:N_TOP]
                wgt = P.cap_weight(picked, CAP)
                all_w.append(wgt)

            miss = sum(1 for i, (month, _) in enumerate(PIT_DATES)
                       for tk in all_w[i] if tk not in px_syms)

            w_by_dt = {}
            for (month, as_of), wgt in zip(PIT_DATES, all_w):
                trig = max(d for d in all_dates if d <= as_of)
                w_by_dt[trig] = wgt

            r = G.run(f"{mode}_w{w:.1f}", w_by_dt, bars)
            sd = P.compute_sharpe(r["nav"])
            sharpe = sd["sharpe"] if sd else None
            ann_vol = sd["ann_vol"] if sd else None
            calmar = r["ann"] / r["mdd"] if r["mdd"] and r["mdd"] > 0 else None
            avg_n = sum(len(x) for x in all_w) / len(all_w)

            results[mode][w] = {
                "total": r["total"], "ann": r["ann"], "mdd": r["mdd"],
                "sharpe": sharpe, "ann_vol": ann_vol, "calmar": calmar,
                "avg_holdings": avg_n,
            }
            coverage[mode][w] = miss

            sharpe_s = f"{sharpe:.2f}" if sharpe is not None else "N/A"
            calmar_s = f"{calmar:.2f}" if calmar is not None else "N/A"
            print(f"  w={w:.1f} (价值{int(w*100):3d}%): 总{r['total']*100:+7.1f}% "
                  f"年化{r['ann']*100:+5.1f}% MDD{r['mdd']*100:6.1f}% "
                  f"夏普{sharpe_s} Calmar{calmar_s} | N {avg_n:.1f}")

    out = {
        "meta": {
            "run_at": datetime.datetime.now().isoformat()[:19],
            "method": "GARP 权重扫描 · 真成长 × 低估值",
            "framework": "AD_top15_mom60top50（top15 + mom60_top50 gate + cap8 + 半年调仓）",
            "score_modes": SCORE_MODES,
            "w_values": W_VALUES,
            "rf_annual": RF_ANNUAL,
        },
        "results": {m: {str(w): v for w, v in results[m].items()}
                     for m in SCORE_MODES},
        "coverage": {m: {str(w): v for w, v in coverage[m].items()}
                      for m in SCORE_MODES},
    }
    json.dump(out, open("_bt_garp_weight_scan_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_weight_scan_results.json")


if __name__ == "__main__":
    main()
