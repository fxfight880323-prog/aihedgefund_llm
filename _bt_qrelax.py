# -*- coding: utf-8 -*-
"""高质量放松 PE 排序实验：在 LX-core 筛选池内，用质量百分位排名"补贴"PE 排名，
看混合排序能否跑赢纯 PE 升序。

变体（均在 core_finex 口径，即剔除金融）:
  core_finex     纯 PE 升序 top40 (基线)
  q20            混合排名 = 0.8*pe_rank + 0.2*quality_rank
  q40            混合排名 = 0.6*pe_rank + 0.4*quality_rank
  q50            混合排名 = 0.5*pe_rank + 0.5*quality_rank
  two_bucket     30 最便宜 + 10 最高质量(从剩余池中选)
  qadj_pe        排序值 = PE * (1 - 0.15*quality_z)  质量越高PE折扣越大

质量百分位 = gpm + con_roe + cetop 三者在池内百分位的均值。
日频+复权口径，与 _bt_daily_bt.py 完全一致。
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
PE_CEIL, DIV_YIELD, EXP_G_CEIL, PEG_CEIL = L.PE_CEIL, L.DIV_YIELD, L.EXP_G_CEIL, L.PEG_CEIL
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP
CAPITAL = 1_000_000.0

VARIANTS = ["core_finex", "q20", "q40", "q50", "two_bucket", "qadj_pe"]

FIN_FILE = os.path.dirname(os.path.abspath(__file__)) + "/_bt_sw_fin_universe.json"


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


def screen_with_quality(month, univ, val, fac, cons, excl_fin, variant):
    """LX-core 筛选 + 质量-PE 混合排名。
    返回 (picked list of (ticker, pe, gpm, roe, cetop, quality_score, blend_rank), stats)
    """
    pool = []  # (tk, pe, dy, exp_g, peg, gpm, roe, cetop)
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
        l5 = (exp_g is not None and exp_g <= EXP_G_CEIL
              and peg is not None and 0 < peg <= PEG_CEIL)
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

    # 计算池内百分位
    gpm_vals = [s["gpm"] for s in pool if s["gpm"] is not None]
    roe_vals = [s["roe"] for s in pool if s["roe"] is not None]
    cet_vals = [s["cetop"] for s in pool if s["cetop"] is not None]

    for s in pool:
        s["gpm_pct"] = pct_rank(gpm_vals, s["gpm"]) if s["gpm"] else 0
        s["roe_pct"] = pct_rank(roe_vals, s["roe"]) if s["roe"] else 0
        s["cet_pct"] = pct_rank(cet_vals, s["cetop"]) if s["cetop"] else 0
        s["q_score"] = (s["gpm_pct"] + s["roe_pct"] + s["cet_pct"]) / 3.0

    # PE 百分位 (越低越好 → 反转: 100 - pct_rank)
    pe_vals = [s["pe"] for s in pool]
    for s in pool:
        s["pe_pct"] = 100.0 - pct_rank(pe_vals, s["pe"])  # PE 低 → pe_pct 高

    # ---- 按变体排名 ----
    if variant == "core_finex":
        pool.sort(key=lambda s: s["pe"])
        picked = pool[:MAX_HOLDINGS]

    elif variant == "two_bucket":
        pool.sort(key=lambda s: s["pe"])
        cheap30 = pool[:30]
        remaining = pool[30:]
        remaining.sort(key=lambda s: -s["q_score"])
        picked = cheap30 + remaining[:10]

    elif variant == "qadj_pe":
        # quality z-score
        q_scores = [s["q_score"] for s in pool]
        q_mean = statistics.mean(q_scores) if q_scores else 50
        q_std = statistics.stdev(q_scores) if len(q_scores) > 1 else 1
        if q_std == 0:
            q_std = 1
        for s in pool:
            s["q_z"] = (s["q_score"] - q_mean) / q_std
            # 调整后 PE = 原始PE * (1 - 0.15*q_z)
            # 质量高于均值 → q_z > 0 → PE 折扣 → 排名更靠前
            s["adj_pe"] = s["pe"] * (1.0 - 0.15 * s["q_z"])
        pool.sort(key=lambda s: s["adj_pe"])
        picked = pool[:MAX_HOLDINGS]

    elif variant in ("q20", "q40", "q50"):
        w_q = {"q20": 0.2, "q40": 0.4, "q50": 0.5}[variant]
        w_pe = 1.0 - w_q
        for s in pool:
            s["blend"] = w_pe * s["pe_pct"] + w_q * s["q_score"]
        pool.sort(key=lambda s: -s["blend"])
        picked = pool[:MAX_HOLDINGS]

    else:
        pool.sort(key=lambda s: s["pe"])
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
    print("  高质量放松 PE 排序实验 (日频+复权, core_finex 口径)")
    print("=" * 78)

    # 数据
    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    fin = load_fin()
    print(f"金融名单: {len(fin)} 只")

    # 日频价格 (复权)
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

    # 中证全指
    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dts = sorted(d for d in idx if d >= "2021-06-01")
    base = idx[idx_dts[0]]["close"]
    idx_total = idx[idx_dts[-1]]["close"] / base - 1.0
    idx_mdd = mdd_of([idx[d]["close"] / base for d in idx_dts])
    print(f"中证全指: {idx_total:+.2%} | MDD {idx_mdd:.2%}")

    # 逐期筛选 + 权重
    all_weights = {v: {} for v in VARIANTS}
    all_holdings = {}
    all_diag = {}

    print("\n逐期筛选:")
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        excl_fin = {tk for tk in members if tk in fin}
        all_diag[month] = {"univ": len(members), "fin": len(excl_fin)}
        line = f"  [{month}] univ={len(members)} fin={len(excl_fin)}"

        for v in VARIANTS:
            picked, st = screen_with_quality(
                month, members, val.get(month, {}),
                fac.get(month, {}), cons.get(month, {}),
                excl_fin, v)
            n = len(picked)
            w = round(min(1.0 / max(n, 1), PER_NAME_CAP), 4)
            all_weights[v][month] = {s["tk"]: w for s in picked}
            all_holdings.setdefault(v, {})[month] = [
                {"tk": s["tk"], "pe": round(s["pe"], 1),
                 "gpm": round(s["gpm"], 1), "roe": round(s["roe"], 1),
                 "q_score": round(s["q_score"], 1)}
                for s in picked]
            all_diag[month][f"{v}_pass"] = st.get("pass", 0)
            all_diag[month][f"{v}_pool"] = st.get("pool", 0)
            line += f" | {v}={st.get('pass',0)}"
        print(line)

    # 权重 → 调仓触发日
    w_by_dt = {}
    for v in VARIANTS:
        wd = {}
        for month, asof in PIT_DATES:
            trig = max(d for d in all_dates if d <= asof)
            wd[trig] = all_weights[v][month]
        w_by_dt[v] = wd
    for trig in sorted(w_by_dt["core_finex"]):
        print(f"  调仓触发日 {trig}")

    # 回测
    print("\n回测结果:")
    results = {}
    for v in VARIANTS:
        r = run(v, w_by_dt[v], bars)
        r["excess_idx"] = r["total"] - idx_total
        results[v] = r
        print(f"  {v:15s}: 总收益 {r['total']:+.2%} | 年化 {r['ann']:+.2%} | "
              f"MDD {r['mdd']:.2%} | 超额(中证全指) {r['excess_idx']:+.2%} | "
              f"{r['n_days']} 天")
    print(f"  {'中证全指':15s}: 总收益 {idx_total:+.2%} | MDD {idx_mdd:.2%}")

    # 对比表
    base_r = results["core_finex"]
    print(f"\n{'='*78}")
    print(f"  {'变体':15s} | {'总收益':>8s} | {'年化':>7s} | {'MDD':>7s} | "
          f"{'超额中证':>8s} | {'vs基线':>8s}")
    print(f"  {'-'*72}")
    for v in VARIANTS:
        r = results[v]
        delta = r["total"] - base_r["total"]
        tag = " ← 基线" if v == "core_finex" else (" ↑" if delta > 0 else " ↓")
        print(f"  {v:15s} | {r['total']:+7.2%} | {r['ann']:+6.2%} | "
              f"{r['mdd']:6.2%} | {r['excess_idx']:+7.2%} | {delta:+7.2%}{tag}")
    print(f"  {'中证全指':15s} | {idx_total:+7.2%} | {'':>7s} | {idx_mdd:6.2%} |")

    # 福耀玻璃 覆盖情况
    print(f"\n{'='*78}")
    print("  福耀玻璃 (600660.SH) 在各变体中的覆盖:")
    for v in VARIANTS:
        for month, holdings in all_holdings.get(v, {}).items():
            fy = [h for h in holdings if "600660" in h["tk"]]
            if fy:
                print(f"  {v:15s} [{month}]: PE={fy[0]['pe']} gpm={fy[0]['gpm']}% "
                      f"ROE={fy[0]['roe']}% q_score={fy[0]['q_score']}")
                break
        else:
            print(f"  {v:15s}: 未入选")

    out = {"results": results, "idx": {"total": idx_total, "mdd": idx_mdd},
           "diag": all_diag, "holdings": all_holdings}
    out_path = os.path.dirname(os.path.abspath(__file__)) + "/_bt_qrelax_results.json"
    json.dump(out, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n结果 → {out_path}")


if __name__ == "__main__":
    main()
