# -*- coding: utf-8 -*-
"""行为金融认知偏差 × 万得全A 全市场回测（无池子偏差）。

把 6.3.2 节「预期中的偏差」翻译成可量化信号，验证能否带来 alpha：

  阶段A 信号裸测（全A池，mv≥100亿 + PE>0，与刘旭同池子）：
    bf_rev12    过去12月收益 升序        ← 代表性启发/外推信念的反向交易（短期反转）
    bf_mom12    过去12月收益 降序        ← 外推信念直接兑现（追涨，预期为负的对照）
    bf_52wk_hi  价格/52周高点 降序(买近高点) ← 锚定效应→反应不足（Li&Yu 2012 突破策略）
    bf_52wk_lo  价格/52周高点 升序(买深跌)  ← 锚定效应→过度反应修复（深跌反转）
    bf_lowvol   过去12月收益波动率 升序    ← 过度自信/可得性→投机过热的反向（低波动异象）
    bf_rev4w    一致预期4周修正 降序       ← 保守主义→反应不足（买预期上调，PEAD）

  阶段B 嵌入框架（LX-core 筛选通过后，替换排序信念）：
    lx_pe       LX-core + PE升序（对照组，即原 LX-core +60% 的逻辑）
    lx_52wk_hi  LX-core + 52周高点距离降序
    lx_lowvol   LX-core + 低波升序
    lx_rev12    LX-core + 12月收益升序
    lx_rev4w    LX-core + 4周预期修正降序

回测设置（与 _lx_allA_variant.py 完全一致）：半年度调仓，top-40 等权，单票5%，
成本 5bp+10bp，引擎 BacktestingEngine。基准：EW-全A（PIT成分等权，同区间）+ CSI-全指。

数据：_bt_winda_universe/_bt_lx_allA_valuation/_bt_lx_allA_factors/
      _bt_winda_consensus/_bt_winda_prices/_bt_winda_index（全部 PIT 缓存，2021-06 起价格）
诚实标注：价格自 2021-06 起 → 行为信号需 12 个月窗口 → 回测区间 2022-08 起（8期）。
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal

CAPITAL = 1_000_000
PIT_DATES = [
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

PE_CEIL = 25.0
DIV_YIELD = 0.02
EXP_G_CEIL = 25.0
PEG_CEIL = 2.0
MAX_HOLDINGS = 40
PER_NAME_CAP = 0.05
MIN_MV_YI = 100.0

# 变体 → (模式, 排序因子)
# 模式 bf = 行为信号裸测;  lx = 刘旭框架筛选后替换排序
VARIANT_SPECS: dict[str, tuple[str, str]] = {
    "bf_rev12":   ("bf", "rev12"),
    "bf_mom12":   ("bf", "mom12"),
    "bf_52wk_hi": ("bf", "52wk_hi"),
    "bf_52wk_lo": ("bf", "52wk_lo"),
    "bf_lowvol":  ("bf", "lowvol"),
    "bf_rev4w":   ("bf", "rev4w"),
    "lx_pe":      ("lx", "pe"),
    "lx_52wk_hi": ("lx", "52wk_hi"),
    "lx_lowvol":  ("lx", "lowvol"),
    "lx_rev12":   ("lx", "rev12"),
    "lx_rev4w":   ("lx", "rev4w"),
}
VARIANTS = list(VARIANT_SPECS.keys())


# ===========================================================================
# 装载
# ===========================================================================

def load_consensus() -> dict[str, dict[str, dict]]:
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
# 价格特征（信号窗口 = 调仓月 m 的 [m-12, m-1]，基准月 m-1，无 look-ahead）
# ===========================================================================

def build_price_features(prices: dict, all_months: list[str]):
    """返回 (feats_by_month, months_idx)。
    feats_by_month[m][tk] = {ret12, hi52, dist52, vol12} 或 None（窗口不足/无价）。
    """
    idx = {mk: i for i, mk in enumerate(all_months)}
    feats: dict[str, dict] = {}
    for m in REBALANCES:
        i = idx.get(m)
        if i is None or i < 12:
            feats[m] = {}
            continue
        w12 = all_months[i - 12:i]          # [m-12, m-1] 12 个月
        cur_mk = all_months[i - 1]
        out: dict[str, dict] = {}
        for tk, mp in prices.items():
            px_cur = mp.get(cur_mk)
            if not px_cur or px_cur <= 0:
                continue
            wpx = [mp.get(k) for k in w12]
            if any(p is None or p <= 0 for p in wpx):
                continue
            p0 = wpx[0]
            ret12 = px_cur / p0 - 1.0
            hi52 = max(wpx)
            dist52 = px_cur / hi52 if hi52 > 0 else None
            rets = []
            for a, b in zip(wpx[:-1], wpx[1:]):
                if a and a > 0:
                    rets.append(b / a - 1.0)
            vol12 = statistics.pstdev(rets) if len(rets) >= 6 else None
            if vol12 is None or dist52 is None:
                continue
            out[tk] = {"ret12": ret12, "hi52": hi52, "dist52": dist52,
                       "vol12": vol12}
        feats[m] = out
    return feats


# ===========================================================================
# 信号
# ===========================================================================

def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def _feat(feats: dict, tk: str, key: str):
    r = feats.get(tk)
    return r.get(key) if r else None


def make_signal(month, tk, model_name, belief, components, reasoning):
    return Signal(
        model_name=model_name, ticker=tk, date=month, value=float(belief),
        reasoning=reasoning,
        components={k: (v if v is not None else float("nan"))
                    for k, v in components.items()},
        metadata={"asset_class": "A"})


def screen(month, univ, val, fac, cons, feats, mode, sort_key) -> tuple[list, dict]:
    sigs: list[Signal] = []
    stats = Counter()
    for tk in univ:
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}

        mv = _num(v.get("total_mv"))
        pe = _num(v.get("pe_ttm"))
        dy = _num(f.get("dtop5"))
        exp_g = _num(c.get("con_np_yoy"))
        peg = _num(c.get("con_peg"))
        rev4w = _num(c.get("np_revision_4w"))

        stats["uni"] += 1
        if mv is None or mv < MIN_MV_YI * 10000:
            stats["drop_mv"] += 1
            continue
        if pe is None or pe <= 0:
            stats["drop_pe"] += 1
            continue

        if mode == "lx":
            l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
            if not l4:
                stats["drop_l4"] += 1
                continue
            l5 = (exp_g is not None and exp_g <= EXP_G_CEIL
                  and peg is not None and 0 < peg <= PEG_CEIL)
            if not l5:
                stats["drop_l5"] += 1
                continue

        # ---- 排序因子 ----
        if sort_key == "pe":
            belief, reason = -pe, f"pe={pe:.1f}"
        elif sort_key == "rev12":
            r12 = _feat(feats, tk, "ret12")
            if r12 is None:
                stats["drop_sig"] += 1
                continue
            belief, reason = -r12, f"ret12={r12:+.1%}"
        elif sort_key == "mom12":
            r12 = _feat(feats, tk, "ret12")
            if r12 is None:
                stats["drop_sig"] += 1
                continue
            belief, reason = r12, f"ret12={r12:+.1%}"
        elif sort_key == "52wk_hi":
            d52 = _feat(feats, tk, "dist52")
            if d52 is None:
                stats["drop_sig"] += 1
                continue
            belief, reason = d52, f"dist52={d52:.2f}"
        elif sort_key == "52wk_lo":
            d52 = _feat(feats, tk, "dist52")
            if d52 is None:
                stats["drop_sig"] += 1
                continue
            belief, reason = -d52, f"dist52={d52:.2f}"
        elif sort_key == "lowvol":
            vl = _feat(feats, tk, "vol12")
            if vl is None:
                stats["drop_sig"] += 1
                continue
            belief, reason = -vl, f"vol12={vl:.1%}"
        elif sort_key == "rev4w":
            if rev4w is None:
                stats["drop_sig"] += 1
                continue
            belief, reason = rev4w, f"rev4w={rev4w:.2f}"
        else:
            belief, reason = 0.0, ""

        sigs.append(make_signal(
            month, tk, f"bf_{sort_key}" if mode == "bf" else f"lx_{sort_key}",
            belief,
            {"pe": pe, "dy": dy, "exp_g": exp_g, "peg": peg,
             "ret12": _feat(feats, tk, "ret12"),
             "dist52": _feat(feats, tk, "dist52"),
             "vol12": _feat(feats, tk, "vol12"),
             "rev4w": rev4w},
            f"{reason} mv={mv/10000:.0f}亿"))

    sigs.sort(key=lambda s: -s.value)
    picked = sigs[:MAX_HOLDINGS]
    stats["pass"] = len(picked)
    stats["n_sig"] = len(sigs)
    return picked, dict(stats)


# ===========================================================================
# 等权万得全A基准
# ===========================================================================

def _members_at(univ: dict[str, list[str]], mk: str) -> set[str]:
    pick = None
    for m, a in PIT_DATES:
        if a[:7] <= mk:
            pick = m
        else:
            break
    return set(univ.get(pick, []) if pick else [])


def ew_universe_nav(univ, prices, months) -> dict[str, float]:
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


def run_variant(name, weights_by_dt, bars, bench) -> dict:
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


def _weights_from(sigs: list) -> dict[str, float]:
    weights = {}
    if sigs:
        w = min(1.0 / len(sigs), PER_NAME_CAP)
        weights = {s.ticker: round(w, 4) for s in sigs}
    return weights


# ===========================================================================
# main
# ===========================================================================

def main():
    print("=" * 78)
    print("  行为金融认知偏差 × 万得全A 全市场回测（无池子偏差）")
    print("  区间: 2022-08 ~ 2026-04（8期半年度调仓；价格窗口 2021-07 起）")
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

    # 价格特征（无 look-ahead: 窗口 [m-12, m-1]）
    feats = build_price_features(prices, all_months)
    for m in REBALANCES:
        print(f"  [feat {m}] 信号可得 {len(feats[m])} 只")

    # 基准（裁剪到回测区间, 与策略同起点）
    ew_full = ew_universe_nav(univ, prices, all_months)
    s_months = sorted(mk for mk in ew_full if mk >= "2022-08")
    b0 = ew_full[s_months[0]]
    bench_ew = {mk: ew_full[mk] / b0 for mk in s_months}
    idx = {mk: v for mk, v in index.items() if mk in bench_ew}
    if idx:
        ib0 = idx[s_months[0]]
        bench_idx = {mk: idx[mk] / ib0 for mk in s_months if mk in idx}
    else:
        bench_idx = None
    print(f"  等权全A: {s_months[0]}~{s_months[-1]} 终值 {bench_ew[s_months[-1]]:.3f}")
    if bench_idx:
        print(f"  中证全指: 终值 {bench_idx[s_months[-1]]:.3f}")

    # 信号 + 权重
    print("\n② 筛选（每期 pass 数）")
    all_weights: dict[str, dict[str, dict[str, float]]] = {}
    all_diag: dict[str, dict] = {}
    for month, as_of in PIT_DATES:
        members = univ.get(month, [])
        all_diag[month] = {"univ": len(members)}
        line = f"  [{month}] univ={len(members)}"
        for v, (mode, sk) in VARIANT_SPECS.items():
            sigs, st = screen(month, members, val.get(month, {}),
                              fac.get(month, {}), cons.get(month, {}),
                              feats.get(month, {}), mode, sk)
            all_weights.setdefault(v, {})[month] = _weights_from(sigs)
            all_diag[month][f"{v}_pass"] = st.get("pass", 0)
            all_diag[month][f"{v}_n_sig"] = st.get("n_sig", 0)
            line += f" | {v}={st.get('pass', 0)}"
        print(line)

    # 引擎回测
    print("\n③ 引擎回测")
    r_ew = {"name": "EW-全A", "total": bench_ew[s_months[-1]] - 1,
            "ann": (bench_ew[s_months[-1]]) ** (12 / len(s_months)) - 1,
            "mdd": None,
            "nav": [{"month": m, "nav": v} for m, v in bench_ew.items()]}
    r_idx = None
    if bench_idx:
        r_idx = {"name": "CSI-全指", "total": bench_idx[s_months[-1]] - 1,
                 "ann": (bench_idx[s_months[-1]]) ** (12 / len(s_months)) - 1,
                 "mdd": None,
                 "nav": [{"month": m, "nav": v} for m, v in bench_idx.items()]}
    results = {}
    for v in VARIANTS:
        r = run_variant(v, all_weights[v], bars, bench_ew)
        r["excess_ew"] = r["total"] - r_ew["total"]
        r["excess_idx"] = (r["total"] - r_idx["total"]) if r_idx else None
        results[v] = r
        print(f"  {v:11s}: 总收益 {r['total']:+.1%} | 年化 {r['ann']:+.1%} | "
              f"MDD {r['mdd']:+.1%} | 超额(等权全A) {r['excess_ew']:+.1%}")
    print(f"  EW-全A   : 总收益 {r_ew['total']:+.1%} | 年化 {r_ew['ann']:+.1%}")
    if r_idx:
        print(f"  CSI-全指 : 总收益 {r_idx['total']:+.1%} | 年化 {r_idx['ann']:+.1%}")

    out = {
        "results": results, "ew": r_ew, "idx": r_idx,
        "diag": all_diag, "weights": all_weights,
        "bench_ew": bench_ew, "bench_idx": bench_idx,
        "meta": {"period": "2022-08~2026-04", "n_reb": len(PIT_DATES),
                 "pit_dates": PIT_DATES,
                 "signals": {
                     "bf_rev12": "12月收益升序(短期反转,外推信念反向)",
                     "bf_mom12": "12月收益降序(追涨,外推信念对照)",
                     "bf_52wk_hi": "52周高点距离降序(锚定→反应不足)",
                     "bf_52wk_lo": "52周高点距离升序(深跌反转,过度反应修复)",
                     "bf_lowvol": "12月波动率升序(低波动,投机反向)",
                     "bf_rev4w": "4周预期修正降序(保守主义→反应不足)",
                     "lx_*": "刘旭框架筛选后替换排序信念",
                 }},
    }
    json.dump(out, open("_bt_bf_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_bf_results.json")


if __name__ == "__main__":
    main()
