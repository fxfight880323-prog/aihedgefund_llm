"""刘旭式框架 × 万得全A 全市场诚实回测（无池子偏差）。

池子 = 万得全A(881001.WI) 每期 PIT 成分（4441 → 5500 只），2021-08 起半年度调仓，
同引擎同成本（5bp+10bp）同日历。把"刘旭选股逻辑解构"的数值化信号翻译成
全市场可批量获取的真实数据层（估值面板 + HF 质量因子 + 一致预期），做变体分解：

  LX-core   L4 估值安全边际(PE≤25 或 股息率≥2%) + L5 低预期(预期增速≤25% 且 PEG≤2)
            + 市值≥100亿 + PE>0（持仓解构中覆盖率最高的"不贵的低预期"核心）
  LX-qual   core + L1 质量代理(一致预期 ROE≥12%)           [质量通道]
  LX-cf     core + L2 现金流代理(营业现金流/市值>0)          [现金流质量]
  LX-gm     core + L3 竞争地位代理(毛利率≥全市场中位数)      [毛利率]
  LX-full   core + qual + cf + gm                            [完整刘旭式近似]

市值诊断变体（回答"超额缺口来自风格暴露还是选股无效"）:
  *_mv30   同层级但市值下限降至 30 亿
  *_mv0    同层级但无市值下限（仅剔除市值缺失）
  对比 mv100 版本：若缺口随下限放松大幅收窄 → 缺口来自大市值风格暴露
  （2021-2026 小盘显著跑赢大盘）；若缺口依旧 → 选股逻辑本身在全A失效。

基准（方法论铁律：先对比等权池子再下结论）：
  EW-全A   等权万得全A NAV（PIT 成分 + 真实月K）
  CSI-All  中证全指 000985.SH（市值加权）

数据文件:
  _bt_winda_universe.json   万得全A PIT 成分
  _bt_lx_allA_valuation.json pe_ttm/pb/total_mv（估值面板）
  _bt_lx_allA_factors.json   gpm/cetop/npyoy/roes/dtop5 等 HF 因子
  _bt_winda_consensus.json   一致预期（con_roe/con_np_yoy/con_peg）
  _bt_winda_prices.json      全市场真实月K
  _bt_winda_index.json       中证全指

说明（诚实标注）:
  - juzi 财务宽表为单股接口，全市场逐只不可行 → ROE 用一致预期 ROE(con_roe) 代理
    （分析师覆盖偏差：小盘股 con_roe 缺失会被剔除，这是框架的真实暴露）
  - 现金流用 HF 因子 cetop(营业现金流市值比) 代理 OCF/净利润
  - 毛利率用全市场中位数代替行业中位数（近似）
"""
from __future__ import annotations

import json
import os
import sys
import statistics
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal

CAPITAL = 1_000_000
PIT_DATES = [
    ("2021-08", "2021-08-31"),
    ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"),
    ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"),
    ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"),
    ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"),
    ("2026-04", "2026-04-30"),
]
REBALANCES = [d[0] for d in PIT_DATES]

UNIV_FILE = "_bt_winda_universe.json"
VAL_FILE = "_bt_lx_allA_valuation.json"
FAC_FILE = "_bt_lx_allA_factors.json"
CONS_FILE = "_bt_winda_consensus.json"
PRICES_FILE = "_bt_winda_prices.json"
INDEX_FILE = "_bt_winda_index.json"

# 变体规格: 名称 -> (层级, 市值下限/亿)；mv0 = 无下限（仅剔除市值缺失）
# gm25/gm30/gm35 = 毛利率固定阈值变体（%），对齐申万版 sw_gm(≥30%) 交叉验证
VARIANT_SPECS: dict[str, tuple[str, float]] = {
    "core":      ("core", 100.0),
    "qual":      ("qual", 100.0),
    "cf":        ("cf",   100.0),
    "gm":        ("gm",   100.0),
    "gm25":      ("gm25", 100.0),
    "gm30":      ("gm30", 100.0),
    "gm35":      ("gm35", 100.0),
    "full":      ("full", 100.0),
    "core_mv30": ("core", 30.0),
    "full_mv30": ("full", 30.0),
    "core_mv0":  ("core", 0.0),
    "full_mv0":  ("full", 0.0),
}
VARIANTS = list(VARIANT_SPECS.keys())

# 毛利率固定阈值（%，gpm 因子单位为百分数）——与申万版 sw_gm 固定30%对齐
GM_FIXED = {"gm25": 25.0, "gm30": 30.0, "gm35": 35.0}

PE_CEIL = 25.0             # L4 PE_TTM ≤ 25
DIV_YIELD = 0.02           # L4 股息率 ≥ 2%（dtop5 比率）
EXP_G_CEIL = 25.0          # L5 一致预期净利增速 ≤ 25%
PEG_CEIL = 2.0             # L5 PEG ≤ 2
CON_ROE = 12.0             # L1 质量代理 一致预期 ROE ≥ 12%
MAX_HOLDINGS = 40
PER_NAME_CAP = 0.05


# ===========================================================================
# 装载
# ===========================================================================

def load_consensus() -> dict[str, dict[str, dict]]:
    """{month: {ticker: record}} — 每期取 con_year 最接近 as_of 年的记录。"""
    cons = json.loads(open(CONS_FILE, encoding="utf-8").read())
    out: dict[str, dict[str, dict]] = {}
    for month, d in cons.items():
        as_of_year = int(month[:4])
        best: dict[str, dict] = {}
        for r in d.get("records", []):
            sc = r.get("stock_code", "")
            if "." not in sc:
                continue
            code, mkt = sc.split(".")
            if code[0] == "6":
                tk = f"{code}.SH"
            elif code[0] in ("0", "3"):
                tk = f"{code}.SZ"
            else:
                tk = f"{code}.BJ"
            cy = r.get("con_year") or 0

            def dist(y):
                if y == as_of_year:
                    return 0
                if y == as_of_year + 1:
                    return 1
                return 2 + abs((y or 0) - as_of_year)

            if tk not in best or dist(cy) < dist(best[tk].get("con_year") or 0):
                best[tk] = r
        out[month] = best
    return out


def load_map(path: str) -> dict[str, dict[str, dict]]:
    """{month: {ticker: record}} for valuation / factor panels."""
    d = json.loads(open(path, encoding="utf-8").read())
    out: dict[str, dict[str, dict]] = {}
    for month, m in d.items():
        rec = {}
        for r in m.get("records", []):
            sc = r.get("stock_code", "")
            if "." not in sc:
                continue
            code, mkt = sc.split(".")
            if code[0] == "6":
                tk = f"{code}.SH"
            elif code[0] in ("0", "3"):
                tk = f"{code}.SZ"
            else:
                tk = f"{code}.BJ"
            rec[tk] = r
        out[month] = rec
    return out


def load_universe() -> dict[str, list[str]]:
    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    return {m: d.get("members", []) for m, d in univ.items()}


# ===========================================================================
# 信号：刘旭式筛选器（分层记录每层命中/淘汰）
# ===========================================================================

def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def screen(month: str, univ: list[str], val: dict, fac: dict,
           cons: dict, tier: str, min_mv_yi: float) -> tuple[list[Signal], dict]:
    """按层级(tier)×市值下限(min_mv_yi)筛选 → Signal(value=-pe, 等权入池)。

    信念用 PE 升序（便宜优先）：质量层叠加在"便宜"之上做增量过滤，
    使 qual/cf/gm/full 与 core 产生可观测的区分度。
    """
    sigs: list[Signal] = []
    stats = Counter()
    gpm_vals = []
    for tk in univ:
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}

        mv = _num(v.get("total_mv"))            # 万元
        pe = _num(v.get("pe_ttm"))
        dy = _num(f.get("dtop5"))                # 股息率(比率)
        exp_g = _num(c.get("con_np_yoy"))
        peg = _num(c.get("con_peg"))
        con_roe = _num(c.get("con_roe"))
        cetop = _num(f.get("cetop"))
        gpm = _num(f.get("gpm"))
        npyoy = _num(f.get("npyoy"))

        stats["uni"] += 1

        # ---- L6 排除项近似：市值 ≥ min_mv_yi，PE > 0 ----
        if mv is None:
            stats["drop_mv_missing"] += 1
            continue
        if mv < min_mv_yi * 10000:
            stats["drop_mv_low"] += 1
            continue
        if pe is None or pe <= 0:
            stats["drop_pe"] += 1
            continue

        # ---- L4 估值安全边际：PE ≤ 25 或 股息率 ≥ 2% ----
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            stats["drop_l4"] += 1
            continue

        # ---- L5 低预期逆向：预期增速 ≤ 25% 且 0 < PEG ≤ 2 ----
        l5 = (exp_g is not None and exp_g <= EXP_G_CEIL
              and peg is not None and 0 < peg <= PEG_CEIL)
        if not l5:
            stats["drop_l5"] += 1
            continue

        # ---- 变体质量层 ----
        if tier in ("qual", "full"):
            if con_roe is None or con_roe < CON_ROE:
                stats[f"drop_{tier}"] += 1
                continue
        if tier in ("cf", "full"):
            if cetop is None or cetop <= 0:
                stats[f"drop_{tier}"] += 1
                continue
        gm_fixed = GM_FIXED.get(tier)
        if gm_fixed is not None:
            # 固定阈值变体（gm25/gm30/gm35）：第一轮直接过滤，% 单位
            if gpm is None or gpm < gm_fixed:
                stats[f"drop_{tier}"] += 1
                continue
        elif tier in ("gm", "full"):
            if gpm is not None:
                gpm_vals.append(gpm)
            else:
                stats[f"drop_{tier}"] += 1
                continue

        # ---- 信念：PE 升序（便宜优先，"不贵的低预期"）----
        belief = -pe
        sigs.append(Signal(
            model_name=f"lx_{tier}", ticker=tk, date=month,
            value=float(belief),
            reasoning=f"pe={pe:.1f} dy={dy or 0:.1%} g={exp_g:.0f} "
                      f"peg={peg:.1f} roe={con_roe or 0:.0f}",
            components={"pe": pe, "dy": dy, "exp_g": exp_g, "peg": peg,
                        "con_roe": con_roe, "cetop": cetop, "gpm": gpm,
                        "npyoy": npyoy} if all(v is not None for v in
                        (pe, dy, exp_g, peg, con_roe, cetop, gpm, npyoy))
                        else {k: (v if v is not None else float("nan"))
                              for k, v in dict(pe=pe, dy=dy, exp_g=exp_g,
                                               peg=peg, con_roe=con_roe,
                                               cetop=cetop, gpm=gpm,
                                               npyoy=npyoy).items()},
            metadata={"asset_class": "A"}))

    # ---- 毛利率变体需要全市场中位数，第二轮剔除 ----
    if tier in ("gm", "full") and gpm_vals:
        gmed = statistics.median(gpm_vals)
        stats["gpm_median"] = round(gmed, 3)
        n_before = len(sigs)
        sigs = [s for s in sigs
                if s.components.get("gpm") is not None
                and s.components["gpm"] >= gmed]
        stats["drop_gm_med"] = n_before - len(sigs)

    # ---- 组合构造：top-40 等权，单票 5% ----
    sigs.sort(key=lambda s: -s.value)
    picked = sigs[:MAX_HOLDINGS]
    weights = {}
    if picked:
        w = 1.0 / len(picked)
        w = min(w, PER_NAME_CAP)
        weights = {s.ticker: round(w, 4) for s in picked}
    stats["pass"] = len(picked)
    stats["n_total"] = len(sigs)
    return picked, dict(stats)


# ===========================================================================
# 等权万得全A基准 NAV（PIT 成分，真实月K）
# ===========================================================================

def _members_at(univ: dict[str, list[str]], mk: str) -> set[str]:
    pick = None
    for m, a in PIT_DATES:
        if a[:7] <= mk:
            pick = m
        else:
            break
    return set(univ.get(pick, []) if pick else [])


def ew_universe_nav(univ: dict[str, list[str]], prices: dict,
                    months: list[str]) -> dict[str, float]:
    nav: dict[str, float] = {}
    prev_px: dict[str, float] = {}
    cur_nav = 1.0
    for mk in sorted(months):
        members = _members_at(univ, mk)
        rets = []
        for tk in members:
            p_prev = prev_px.get(tk)
            p_cur = prices.get(tk, {}).get(mk)
            if p_prev and p_cur and p_prev > 0:
                rets.append(p_cur / p_prev - 1.0)
        if rets:
            cur_nav *= (1.0 + sum(rets) / len(rets))
        nav[mk] = cur_nav
        prev_px = {tk: prices.get(tk, {}).get(mk)
                   for tk in members if prices.get(tk, {}).get(mk)}
    return nav


# ===========================================================================
# 引擎
# ===========================================================================

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


def run_variant(name: str, weights_by_dt: dict, bars: dict, bench: dict) -> dict:
    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    strategy = WeightsStrategy(engine, {"weights_by_dt": weights_by_dt})
    engine.add_strategy(strategy)
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily, output=False)

    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(d for d in bal if d in bench)
    if len(dts) < 2:
        return {"name": name, "total": 0.0, "ann": 0.0, "mdd": 0.0, "nav": []}
    total = bal[dts[-1]] / bal[dts[0]] - 1
    yrs = len(dts) / 12
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1
    mdd = stats.get("max_ddpercent", 0) / 100.0
    nav = [{"month": d, "nav": bal[d]} for d in dts]
    return {"name": name, "total": total, "ann": ann, "mdd": mdd, "nav": nav}


# ===========================================================================
# main
# ===========================================================================

def main():
    print("=" * 78)
    print("  刘旭式框架 × 万得全A 全市场回测（无池子偏差）· 变体分解")
    print("=" * 78)

    univ = load_universe()
    cons = load_consensus()
    val = load_map(VAL_FILE)
    fac = load_map(FAC_FILE)
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    index = json.loads(open(INDEX_FILE, encoding="utf-8").read())
    print(f"万得全A 成分: {[len(univ[m]) for m in REBALANCES]}")

    # 价格 → 月度 bars
    bars = {}
    for tk, m in prices.items():
        mm = {mk: px for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        if mm:
            bars[tk] = {mk: BarData(tk, mk, px, px, px, px) for mk, px in mm.items()}
    all_months = sorted({mk for m in bars.values() for mk in m})

    # 基准
    print("\n① 基准")
    ew = ew_universe_nav(univ, prices, all_months)
    idx = {mk: v for mk, v in index.items() if mk in all_months}
    bench_months = sorted(ew.keys())
    n0 = bench_months[0]
    bench_ew = {mk: ew[mk] / ew[n0] for mk in bench_months}
    if n0 in idx:
        base_idx = idx[n0]
        bench_idx = {mk: idx[mk] / base_idx for mk in bench_months if mk in idx}
    else:
        bench_idx = None
    print(f"  等权全A: {bench_months[0]}~{bench_months[-1]} "
          f"{len(bench_months)} 个月 | 终值 {bench_ew[bench_months[-1]]:.3f}")
    if bench_idx:
        print(f"  中证全指: 终值 {bench_idx[bench_months[-1]]:.3f}")

    # 信号 + 权重（逐变体）
    print("\n② 筛选与权重（每期）")
    all_weights: dict[str, dict[str, dict[str, float]]] = {}
    all_diag: dict[str, dict] = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        all_diag[month] = {"univ": len(members),
                           "val_cov": len(val.get(month, {})),
                           "fac_cov": len(fac.get(month, {})),
                           "cons_cov": len(cons.get(month, {}))}
        line = f"  [{month}] univ={len(members)}"
        for v, (tier, mv_floor) in VARIANT_SPECS.items():
            sigs, st = screen(month, members, val.get(month, {}),
                              fac.get(month, {}), cons.get(month, {}),
                              tier, mv_floor)
            all_weights.setdefault(v, {})[month] = _weights_from(sigs)
            all_diag[month][f"{v}_pass"] = st.get("pass", 0)
            all_diag[month][f"{v}_drop"] = {k: st[k] for k in st
                                            if k.startswith("drop")}
            line += f" | {v}={st.get('pass', 0)}"
        print(line)

    # 引擎回测
    print("\n③ 引擎回测")
    r_ew = {"name": "EW-全A", "total": bench_ew[bench_months[-1]] - 1,
            "ann": (bench_ew[bench_months[-1]]) ** (12 / len(bench_months)) - 1,
            "mdd": None, "nav": [{"month": m, "nav": v}
                                 for m, v in bench_ew.items()]}
    if bench_idx:
        r_idx = {"name": "CSI-全指",
                 "total": bench_idx[bench_months[-1]] - 1,
                 "ann": (bench_idx[bench_months[-1]]) **
                        (12 / len(bench_months)) - 1,
                 "mdd": None,
                 "nav": [{"month": m, "nav": v}
                         for m, v in bench_idx.items()]}
    results = {}
    for v in VARIANTS:
        r = run_variant(f"LX-{v}", all_weights[v], bars, bench_ew)
        r["excess_ew"] = r["total"] - r_ew["total"]
        r["excess_idx"] = (r["total"] - r_idx["total"]) if bench_idx else None
        results[v] = r
        print(f"  LX-{v:5s}: 总收益 {r['total']:+.1%} | 年化 {r['ann']:+.1%} | "
              f"MDD {r['mdd']:+.1%} | 超额(等权全A) {r['excess_ew']:+.1%}")
    print(f"  EW-全A : 总收益 {r_ew['total']:+.1%} | 年化 {r_ew['ann']:+.1%}")
    if bench_idx:
        print(f"  CSI-全指: 总收益 {r_idx['total']:+.1%} | 年化 {r_idx['ann']:+.1%}")

    out = {
        "results": results, "ew": r_ew, "idx": r_idx if bench_idx else None,
        "diag": all_diag, "weights": all_weights,
        "bench_ew": bench_ew,
        "bench_idx": bench_idx,
    }
    json.dump(out, open("_bt_lx_allA_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_lx_allA_results.json")


def _weights_from(sigs: list) -> dict[str, float]:
    weights = {}
    if sigs:
        w = min(1.0 / len(sigs), PER_NAME_CAP)
        weights = {s.ticker: round(w, 4) for s in sigs}
    return weights


if __name__ == "__main__":
    main()
