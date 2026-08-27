# -*- coding: utf-8 -*-
"""L5 低预期门控放松实验：紫金矿业这类"高质量+高增速+低PE"（GARP 型）公司
被 L5 增速≤25% 门控剔除。检验放松增速门控能否纳入它们并提升收益。

变体（均在 core_finex 口径 = LX-core 剔除金融，日频+复权）:
  core_finex    L5 = 增速≤25% 且 PEG≤2，排序=PE升序           (基线)
  g40           L5 = 增速≤40% 且 PEG≤2，排序=PE升序
  g60           L5 = 增速≤60% 且 PEG≤2，排序=PE升序
  g99           L5 = 增速≤99%(≈不限) 且 PEG≤2，排序=PE升序
  garp          L5 = 增速≤60% 且 PEG≤1 (GARP严格：高增速但估值须匹配)，排序=PE升序
  peg_sort      L5 = 增速≤60% 且 PEG≤2，排序=PEG升序 (GARP标准排序信号)

追踪: 紫金矿业(601899.SH) 每期覆盖情况。
"""
import json, os, sys, statistics
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
import _lx_allA_variant as L

PIT_DATES = L.PIT_DATES
PE_CEIL, DIV_YIELD, PEG_CEIL = L.PE_CEIL, L.DIV_YIELD, L.PEG_CEIL
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP
CAPITAL = 1_000_000.0

# 变体 → (增速上限, PEG上限, 排序键)  | 排序键: pe=PE升序, peg=PEG升序,
# blend20=0.8*pe_pct+0.2*q_score, blend50=0.5*pe_pct+0.5*q_score (池内百分位)
VARIANTS = {
    "core_finex": (25.0, 2.0, "pe"),
    "g40":        (40.0, 2.0, "pe"),
    "g60":        (60.0, 2.0, "pe"),
    "g99":        (99.0, 2.0, "pe"),
    "garp":       (60.0, 1.0, "pe"),
    "peg_sort":   (60.0, 2.0, "peg"),
    "garp_q20":   (60.0, 1.0, "blend20"),
    "garp_q50":   (60.0, 1.0, "blend50"),
}

FIN_FILE = os.path.dirname(os.path.abspath(__file__)) + "/_bt_sw_fin_universe.json"
TRACK = "601899.SH"  # 紫金矿业


def load_fin() -> set:
    d = json.loads(open(FIN_FILE, encoding="utf-8").read())
    out = set()
    for sec, info in d.items():
        if isinstance(info, dict) and isinstance(info.get("members"), list):
            out.update(info["members"])
    return out


def pct_rank(values: list, v: float) -> float:
    """池内百分位 (0~100)，值越大越好。"""
    n = len(values)
    if n == 0:
        return 50.0
    below = sum(1 for x in values if x < v)
    return below / n * 100.0


def screen_garp(month, univ, val, fac, cons, excl_fin, g_ceil, peg_ceil, sort_key):
    """L5 门控放松筛选。返回 (picked list, stats)。"""
    pool = []
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
        con_roe = L._num(c.get("con_roe"))
        cetop = L._num(f.get("cetop"))
        gpm = L._num(f.get("gpm"))

        stats["uni"] += 1
        if mv is None:
            stats["drop_mv_missing"] += 1
            continue
        if mv < 100 * 10000:
            stats["drop_mv_low"] += 1
            continue
        if pe is None or pe <= 0:
            stats["drop_pe"] += 1
            continue
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            stats["drop_l4"] += 1
            continue
        # ---- L5 放松版：增速 ≤ g_ceil 且 0 < PEG ≤ peg_ceil ----
        l5 = (exp_g is not None and exp_g <= g_ceil
              and peg is not None and 0 < peg <= peg_ceil)
        if not l5:
            stats["drop_l5"] += 1
            continue
        if tk in excl_fin:
            stats["drop_fin"] += 1
            continue

        pool.append({"tk": tk, "pe": pe, "dy": dy or 0, "exp_g": exp_g or 0,
                     "peg": peg or 0, "gpm": gpm or 0, "roe": con_roe or 0,
                     "cetop": cetop or 0})

    if not pool:
        stats["pass"] = 0
        return [], dict(stats)

    # ---- 混合排序需要池内百分位 ----
    if sort_key in ("blend20", "blend50"):
        gpm_vals = [s["gpm"] for s in pool]
        roe_vals = [s["roe"] for s in pool]
        cet_vals = [s["cetop"] for s in pool]
        pe_vals = [s["pe"] for s in pool]
        for s in pool:
            q = (pct_rank(gpm_vals, s["gpm"]) + pct_rank(roe_vals, s["roe"])
                 + pct_rank(cet_vals, s["cetop"])) / 3.0
            s["q_score"] = q
            s["pe_pct"] = 100.0 - pct_rank(pe_vals, s["pe"])
            s["blend20"] = 0.8 * s["pe_pct"] + 0.2 * q
            s["blend50"] = 0.5 * s["pe_pct"] + 0.5 * q

    if sort_key == "pe":
        pool.sort(key=lambda s: s["pe"])
    elif sort_key == "peg":
        pool.sort(key=lambda s: s["peg"])
    elif sort_key == "blend20":
        pool.sort(key=lambda s: -s["blend20"])
    else:
        pool.sort(key=lambda s: -s["blend50"])
    picked = pool[:MAX_HOLDINGS]
    stats["pass"] = len(picked)
    stats["pool"] = len(pool)
    return picked, dict(stats)


class WeightsStrategy(StrategyTemplate):
    def __init__(self, engine, setting):
        super().__init__(engine, setting)
        self.weights_by_dt = setting["weights_by_dt"]

    def on_bars(self, bars):
        dt = self.engine.datetime
        if dt not in self.weights_by_dt:
            return
        weights = self.weights_by_dt[dt]
        equity = self.engine.get_equity(bars)
        self.target_data = {}
        for tk, w in weights.items():
            bar = bars.get(tk) or self.engine.bars.get(tk)
            if bar and bar.close_price > 0:
                self.target_data[tk] = w * equity / bar.close_price
        for s, pos in list(self.engine.pos_data.items()):
            if pos > 0 and s not in weights:
                self.target_data[s] = 0.0
        self.rebalance_portfolio(bars)


def mdd_of(nav_seq):
    peak, mdd = nav_seq[0], 0.0
    for v in nav_seq:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def run(variant, weights_by_dt, bars):
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001,
                          annual_periods=252)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {"weights_by_dt": weights_by_dt})
    engine.add_strategy(strategy)
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)

    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(d for d in bal if d >= "2021-06-01")
    nav = [{"date": d, "nav": bal[d]} for d in dts]
    total = bal[dts[-1]] / bal[dts[0]] - 1.0
    yrs = len(dts) / 252.0
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1.0
    mdd = mdd_of([bal[d] for d in dts])
    return {"name": variant, "total": total, "ann": ann, "mdd": mdd,
            "nav": nav, "n_days": len(dts)}


def main():
    print("=" * 78)
    print("  L5 增速门控放松实验 (日频+复权, core_finex 口径)")
    print("=" * 78)

    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    fin = load_fin()
    print(f"金融名单: {len(fin)} 只")

    px = json.load(open("_bt_daily_px.json", encoding="utf-8"))
    bars = {}
    n_adj = 0
    for tk, d in px.items():
        mm = {}
        for dt, r in d.items():
            c, a = r.get("close"), r.get("adj")
            if c and a and c > 0 and a > 0 and dt >= "2021-05-01":
                ratio = a / c
                mm[dt] = BarData(tk, dt,
                                 (r.get("open") or c) * ratio,
                                 (r.get("high") or c) * ratio,
                                 (r.get("low") or c) * ratio,
                                 a)
                n_adj += 1
        if mm:
            bars[tk] = mm
    all_dates = sorted({dt for m in bars.values() for dt in m})
    print(f"复权 bar: {len(bars)} 只 | {n_adj} 条 | {all_dates[0]} ~ {all_dates[-1]}")

    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dts = sorted(d for d in idx if d >= "2021-06-01")
    base = idx[idx_dts[0]]["close"]
    idx_total = idx[idx_dts[-1]]["close"] / base - 1.0
    idx_mdd = mdd_of([idx[d]["close"] / base for d in idx_dts])
    print(f"中证全指: {idx_total:+.2%} | MDD {idx_mdd:.2%}")

    all_weights = {v: {} for v in VARIANTS}
    all_holdings = {}
    all_diag = {}

    print("\n逐期筛选:")
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        excl_fin = {tk for tk in members if tk in fin}
        all_diag[month] = {"univ": len(members), "fin": len(excl_fin)}
        line = f"  [{month}] univ={len(members)} fin={len(excl_fin)}"

        for v, (g_ceil, peg_ceil, sort_key) in VARIANTS.items():
            picked, st = screen_garp(month, members, val.get(month, {}),
                                     fac.get(month, {}), cons.get(month, {}),
                                     excl_fin, g_ceil, peg_ceil, sort_key)
            n = len(picked)
            w = round(min(1.0 / max(n, 1), PER_NAME_CAP), 4)
            all_weights[v][month] = {s["tk"]: w for s in picked}
            all_holdings.setdefault(v, {})[month] = [
                {"tk": s["tk"], "pe": round(s["pe"], 1),
                 "exp_g": round(s["exp_g"], 1), "peg": round(s["peg"], 2),
                 "gpm": round(s["gpm"], 1), "roe": round(s["roe"], 1)}
                for s in picked]
            all_diag[month][f"{v}_pass"] = st.get("pass", 0)
            all_diag[month][f"{v}_pool"] = st.get("pool", 0)
            line += f" | {v}={st.get('pass',0)}"
        print(line)

    w_by_dt = {}
    for v in VARIANTS:
        wd = {}
        for month, asof in PIT_DATES:
            trig = max(d for d in all_dates if d <= asof)
            wd[trig] = all_weights[v][month]
        w_by_dt[v] = wd

    print("\n回测结果:")
    results = {}
    for v in VARIANTS:
        r = run(v, w_by_dt[v], bars)
        r["excess_idx"] = r["total"] - idx_total
        results[v] = r
        print(f"  {v:12s}: 总收益 {r['total']:+.2%} | 年化 {r['ann']:+.2%} | "
              f"MDD {r['mdd']:.2%} | 超额(中证全指) {r['excess_idx']:+.2%} | "
              f"{r['n_days']} 天")
    print(f"  {'中证全指':12s}: 总收益 {idx_total:+.2%} | MDD {idx_mdd:.2%}")

    base_r = results["core_finex"]
    print(f"\n{'='*78}")
    print(f"  {'变体':12s} | {'增速上限':>6s} | {'总收益':>8s} | {'年化':>7s} | "
          f"{'MDD':>7s} | {'超额中证':>8s} | {'vs基线':>8s}")
    print(f"  {'-'*76}")
    for v, (g_ceil, peg_ceil, sort_key) in VARIANTS.items():
        r = results[v]
        delta = r["total"] - base_r["total"]
        tag = " ← 基线" if v == "core_finex" else (" ↑" if delta > 0 else " ↓")
        print(f"  {v:12s} | {g_ceil:>5.0f}%  | {r['total']:+7.2%} | "
              f"{r['ann']:+6.2%} | {r['mdd']:6.2%} | "
              f"{r['excess_idx']:+7.2%} | {delta:+7.2%}{tag}")
    print(f"  {'中证全指':12s} | {'':>6s} | {idx_total:+7.2%} | {'':>7s} | "
          f"{idx_mdd:6.2%} |")

    # 紫金矿业 覆盖
    print(f"\n{'='*78}")
    print(f"  紫金矿业 ({TRACK}) 在各变体中的覆盖:")
    for v in VARIANTS:
        for month, holdings in all_holdings.get(v, {}).items():
            hit = [h for h in holdings if TRACK in h["tk"]]
            if hit:
                h = hit[0]
                print(f"  {v:12s} [{month}]: PE={h['pe']} 增速={h['exp_g']}% "
                      f"PEG={h['peg']} gpm={h['gpm']}% ROE={h['roe']}%")
                break
        else:
            print(f"  {v:12s}: 未入选")

    out = {"results": results, "idx": {"total": idx_total, "mdd": idx_mdd},
           "diag": all_diag, "holdings": all_holdings,
           "variants": {v: {"g_ceil": g, "peg_ceil": p, "sort": s}
                        for v, (g, p, s) in VARIANTS.items()}}
    out_path = os.path.dirname(os.path.abspath(__file__)) + "/_bt_garp_results.json"
    json.dump(out, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n结果 → {out_path}")


if __name__ == "__main__":
    main()
