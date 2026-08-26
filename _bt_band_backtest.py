# -*- coding: utf-8 -*-
"""LX-core + 金融剔除 + PB band 规避层 —— 三变体 5 年回测 (2021-08 ~ 2026-04)

变体:
  core              基线 LX-core (PE 升序 top40, 市值≥100亿, PE>0, L4/L5)
  core_finex        core + 金融剔除 (_bt_sw_fin_universe.json 123 只)
  core_finex_band   core_finex + PB band 规避层 (PB 5y分位 > 90% 剔除)

引擎/成本/价格与 _lx_allA_variant.py 完全一致 (5bp+10bp, 半年度调仓, top40 等权, 单票5%上限)。
band 口径: pb_pct = (窗口[as_of-5y, as_of]内 pb < 当日pb).mean()*100, 样本<60交易日视为无效不剔除。
"""
from __future__ import annotations
import json, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal

# ---- 复用原引擎的装载与常量 ----
import _lx_allA_variant as L
PIT_DATES = L.PIT_DATES
REBALANCES = L.REBALANCES
PE_CEIL, DIV_YIELD, EXP_G_CEIL, PEG_CEIL = L.PE_CEIL, L.DIV_YIELD, L.EXP_G_CEIL, L.PEG_CEIL
MAX_HOLDINGS, PER_NAME_CAP = L.MAX_HOLDINGS, L.PER_NAME_CAP
CAPITAL = L.CAPITAL
BAND_CEIL = 90.0   # PB 5y分位规避阈值

FIN_FILE = "_bt_sw_fin_universe.json"
BAND_FILE = "_bt_band_pb_pct.json"

VARIANTS = ["core", "core_finex", "core_finex_band"]


def load_fin() -> set[str]:
    d = json.loads(open(FIN_FILE, encoding="utf-8").read())
    out = set()
    for sec, info in d.items():
        if isinstance(info, dict) and isinstance(info.get("members"), list):
            out.update(info["members"])
    return out


def screen_bt(month: str, univ: list[str], val: dict, fac: dict, cons: dict,
              excl_fin: set, excl_band: set) -> tuple[list, dict]:
    """LX-core 筛选 (与 L.screen(tier='core') 一致) + 可选排除层。
    返回 (picked 40 只, stats)"""
    sigs: list[Signal] = []
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
        if tk in excl_band:
            stats["drop_band"] += 1
            continue

        sigs.append(Signal(
            model_name="lx_core_bt", ticker=tk, date=month, value=float(-pe),
            reasoning=f"pe={pe:.1f} dy={dy or 0:.1%} g={exp_g:.0f} peg={peg:.1f}",
            components={"pe": float(pe), "dy": float(dy) if dy is not None else float("nan"),
                        "exp_g": float(exp_g) if exp_g is not None else float("nan"),
                        "peg": float(peg) if peg is not None else float("nan")}))
    sigs.sort(key=lambda s: -s.value)
    picked = sigs[:MAX_HOLDINGS]
    stats["pass"] = len(picked)
    stats["n_total"] = len(sigs)
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


def run_variant(name, weights_by_dt, bars, bench):
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    engine.add_strategy(WeightsStrategy(engine, {"weights_by_dt": weights_by_dt}))
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(d for d in bal if d in bench)
    total = bal[dts[-1]] / bal[dts[0]] - 1
    yrs = len(dts) / 12
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1
    mdd = stats.get("max_ddpercent", 0) / 100.0
    nav = [{"month": d, "nav": bal[d]} for d in dts]
    return {"name": name, "total": total, "ann": ann, "mdd": mdd, "nav": nav}


def main():
    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    prices = json.loads(open(L.PRICES_FILE, encoding="utf-8").read())
    index = json.loads(open(L.INDEX_FILE, encoding="utf-8").read())

    fin = load_fin()
    band = json.loads(open(BAND_FILE, encoding="utf-8").read())
    print(f"金融名单: {len(fin)} 只 | band 表: {list(band.keys())}")

    bars = {}
    for tk, m in prices.items():
        mm = {mk: px for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        if mm:
            bars[tk] = {mk: BarData(tk, mk, px, px, px, px) for mk, px in mm.items()}
    all_months = sorted({mk for m in bars.values() for mk in m})

    # 基准 (等权全A + 中证全指)
    ew = L.ew_universe_nav(univ, prices, all_months)
    bench_months = sorted(ew.keys())
    n0 = bench_months[0]
    bench_ew = {mk: ew[mk] / ew[n0] for mk in bench_months}
    idx = {mk: v for mk, v in index.items() if mk in all_months}
    bench_idx = {mk: idx[mk] / idx[n0] for mk in bench_months if mk in idx} if n0 in idx else None
    r_ew = {"name": "EW-全A", "total": bench_ew[bench_months[-1]] - 1,
            "ann": bench_ew[bench_months[-1]] ** (12 / len(bench_months)) - 1,
            "mdd": None, "nav": [{"month": m, "nav": v} for m, v in bench_ew.items()]}
    r_idx = ({"name": "CSI-全指", "total": bench_idx[bench_months[-1]] - 1,
              "ann": bench_idx[bench_months[-1]] ** (12 / len(bench_months)) - 1,
              "mdd": None,
              "nav": [{"month": m, "nav": v} for m, v in bench_idx.items()]} if bench_idx else None)

    # 逐期筛选
    all_weights = {v: {} for v in VARIANTS}
    all_diag = {}
    per_period = {}
    print("\n逐期筛选 (候选/金融剔/band剔/最终持仓):")
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        excl_fin = {tk for tk in members if tk in fin}
        bmap = band.get(month, {})
        excl_band = {tk for tk, r in bmap.items()
                     if r.get("pb_pct") is not None and r["pb_pct"] > BAND_CEIL}
        excl_band = excl_band & set(members)
        all_diag[month] = {"univ": len(members), "fin": len(excl_fin),
                           "band_high": len(excl_band)}
        line = f"[{month}] univ={len(members)} 金融={len(excl_fin)} band>90={len(excl_band)}"
        for v in VARIANTS:
            excl = set()
            if "finex" in v:
                excl |= excl_fin
            if "band" in v:
                excl |= excl_band
            sigs, st = screen_bt(month, members, val.get(month, {}),
                                 fac.get(month, {}), cons.get(month, {}),
                                 excl, set())
            all_weights[v][month] = {s.ticker: round(min(1.0 / max(len(sigs), 1), PER_NAME_CAP), 4)
                                     for s in sigs}
            all_diag[month][f"{v}_pass"] = st["pass"]
            all_diag[month][f"{v}_fin_drop"] = st.get("drop_fin", 0)
            all_diag[month][f"{v}_band_drop"] = st.get("drop_band", 0)
            line += f" | {v}={st['pass']}"
        per_period[month] = {v: [s.ticker for s in
                                 screen_bt(month, members, val.get(month, {}),
                                           fac.get(month, {}), cons.get(month, {}),
                                           ({tk for tk in members if tk in fin} if "finex" in v else set())
                                           | ({tk for tk, r in (band.get(month) or {}).items()
                                               if r.get("pb_pct") is not None and r["pb_pct"] > BAND_CEIL}
                                              & set(members) if "band" in v else set()),
                                           set())[0]]
                             for v in VARIANTS}
        print(line)

    # 引擎回测
    print("\n引擎回测:")
    results = {}
    for v in VARIANTS:
        r = run_variant(f"LX-{v}", all_weights[v], bars, bench_ew)
        r["excess_ew"] = r["total"] - r_ew["total"]
        r["excess_idx"] = (r["total"] - r_idx["total"]) if bench_idx else None
        results[v] = r
        print(f"  {v:18s}: 总 {r['total']:+.1%} | 年化 {r['ann']:+.1%} | "
              f"MDD {r['mdd']:+.1%} | 超额EW {r['excess_ew']:+.1%}")

    out = {"results": results, "ew": r_ew, "idx": r_idx,
           "diag": all_diag, "weights": all_weights, "holdings": per_period}
    json.dump(out, open("_bt_band_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_band_results.json")


if __name__ == "__main__":
    main()
