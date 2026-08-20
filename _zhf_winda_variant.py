"""章宏帆框架 × 一致预期 — 万得全A 全市场诚实回测（无池子偏差）。

池子 = 万得全A(881001.WI) 每期 PIT 成分（4441 → 5500 只），从 2021-08 起
半年度调仓，同引擎同成本（5bp+10bp）同日历（与龙头池版完全一致）：

  ZHF-cons  章宏帆框架 × 一致预期（link=None：全市场无产业链方向映射）
  C-cons    纯 C-Score 一致预期（同池同数据基线）

基准（方法论铁律：先对比等权池子再下结论）：
  EW-全A   等权万得全A NAV（由 PIT 成分 + 真实月K 计算）
  CSI-All  中证全指 000985.SH（市值加权，万得全A 指数无公开序列的替代）

映射（同 _zhf_cons_variant.py，诚实）：
  growth=con_np_yoy/100 | roe=con_roe | pe=con_pe | accel=np_revision_4w>0
  gm 无预期数据→0.5 中性 | G5/L5 无历史序列→中性 | link_norm=0
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal
from src.signals.c_score import calculate_c_score
from _zhf_cons_variant import zhf_cons_signal  # 复用同一信号函数（link=None）

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
CONS_FILE = "_bt_winda_consensus.json"
PRICES_FILE = "_bt_winda_prices.json"
INDEX_FILE = "_bt_winda_index.json"

PE_CEIL = 20.0          # B 类估值护栏（框架 default，全市场统一）
CLASS_BUDGET = {"A": 0.60, "B": 0.35, "C": 0.05, "OFF": 0.05}
PER_NAME_CAP = 0.05
MAX_HOLDINGS = 40


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


def load_universe() -> dict[str, list[str]]:
    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    return {m: d.get("members", []) for m, d in univ.items()}


# ===========================================================================
# 组合构造（保留框架 A/B/C 类配比 + 单票上限 + 集中度）
# ===========================================================================

def build_portfolio(signals: list[Signal], budgets: dict | None = None,
                    per_cap: float = PER_NAME_CAP,
                    max_hold: int = MAX_HOLDINGS) -> dict[str, float]:
    """类配比 + 每类选信念最高 N 只 + 单票上限 + top-40 集中度。

    全市场无产业链方向，保留框架的类配比语义（A 主攻 60 / B 轮动 35 /
    C 小仓 5 / OFF 防御 5），类内按信念分配，防止高信念 A 类淹没 B/C。
    """
    budgets = budgets or CLASS_BUDGET
    per_class_keep = {"A": max_hold, "B": max_hold // 2, "C": 8, "OFF": 8}
    sigs = [s for s in signals if (s.value or 0) > 0]

    by_cls: dict[str, list[Signal]] = {}
    for s in sigs:
        c = (s.metadata or {}).get("asset_class", "A")
        by_cls.setdefault(c, []).append(s)

    picked: list[Signal] = []
    for c, lst in by_cls.items():
        lst = sorted(lst, key=lambda s: -s.value)
        picked.extend(lst[: per_class_keep.get(c, 8)])
    if not picked:
        return {}

    cls_val = {c: sum(s.value for s in picked if
                      (s.metadata or {}).get("asset_class", "A") == c)
               for c in set((s.metadata or {}).get("asset_class", "A")
                            for s in picked)}
    weights: dict[str, float] = {}
    for s in picked:
        c = (s.metadata or {}).get("asset_class", "A")
        if cls_val.get(c, 0) <= 0:
            continue
        w = budgets.get(c, 0.05) * s.value / cls_val[c]
        weights[s.ticker] = w
    weights = {t: min(w, per_cap) for t, w in weights.items()}
    weights = dict(sorted(weights.items(), key=lambda kv: -kv[1])[:max_hold])
    gross = sum(weights.values())
    if gross <= 0:
        return {}
    return {t: round(w / gross, 4) for t, w in weights.items() if w > 0}


# ===========================================================================
# 信号
# ===========================================================================

def build_zhf_cons(cons: dict, month: str, as_of: str) -> tuple[list[Signal], dict]:
    sigs, n_abstain, n_cls = [], 0, Counter()
    for tk, rec in cons.items():
        sig = zhf_cons_signal(rec, None, PE_CEIL)
        if sig is None:
            n_abstain += 1
            continue
        sig.ticker, sig.date = tk, as_of
        n_cls[(sig.metadata or {}).get("asset_class")] += 1
        sigs.append(sig)
    diag = {"cov": len(cons), "abstain": n_abstain, "cls": dict(n_cls)}
    return sigs, diag


def build_c_cons(cons: dict, month: str, as_of: str) -> tuple[list[Signal], dict]:
    sigs, dist = [], Counter()
    for tk, rec in cons.items():
        c_score, _d = calculate_c_score(rec)
        dist[c_score] += 1
        if c_score >= 2:
            value = {2: 0.30, 3: 0.50, 4: 0.70}[min(c_score, 4)]
            sigs.append(Signal(
                model_name="c_cons", ticker=tk, date=as_of, value=value,
                reasoning=f"C={c_score}/4", components={"c_score": c_score},
                metadata={"asset_class": "A"}))
    return sigs, {"cov": len(cons), "c_dist": dict(dist)}


# ===========================================================================
# 等权万得全A基准 NAV（PIT 成分，真实月K）
# ===========================================================================

def _members_at(univ: dict[str, list[str]], mk: str) -> set[str]:
    """最近一次调仓 as_of ≤ mk 的成分（PIT）。"""
    pick = None
    for m, a in PIT_DATES:
        if a[:7] <= mk:
            pick = m
        else:
            break
    return set(univ.get(pick, []) if pick else [])


def ew_universe_nav(univ: dict[str, list[str]], prices: dict,
                    months: list[str]) -> dict[str, float]:
    """每期成分在当前月等权收益 → 链式 NAV。月末价格缺失的股票跳过当月。"""
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
    # 与基准对齐窗口（首个调仓月 → 数据末月），保证收益口径一致
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
# 个股贡献
# ===========================================================================

def contribution(weights_by_dt: dict, prices: dict, bench_months: list,
                 univ: dict) -> list[dict]:
    """每期持仓 → 下一调仓期收益贡献（权重 × 个股收益 / 组合收益）。"""
    rows = []
    px = prices
    last_mk = bench_months[-1]
    for i, (month, as_of) in enumerate(PIT_DATES):
        nxt = REBALANCES[i + 1] if i + 1 < len(REBALANCES) else None
        weights = weights_by_dt.get(month, {})
        if not weights:
            continue
        end_mk = nxt if (nxt and nxt <= last_mk) else last_mk
        total_ret = 0.0
        items = []
        for tk, w in weights.items():
            p0 = px.get(tk, {}).get(month)
            p1 = px.get(tk, {}).get(end_mk)
            if p0 and p1 and p0 > 0:
                r = p1 / p0 - 1.0
                total_ret += w * r
                items.append({"tk": tk, "w": w, "ret": r,
                              "contrib": w * r})
        rows.append({"month": month, "end": end_mk, "n": len(items),
                     "total_ret": total_ret,
                     "top": sorted(items, key=lambda x: -abs(x["contrib"]))[:8]})
    return rows


# ===========================================================================
# main
# ===========================================================================

def main():
    print("=" * 78)
    print("  章宏帆框架 × 一致预期 · 万得全A 全市场回测（无池子偏差）")
    print("=" * 78)

    univ = load_universe()
    cons = load_consensus()
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
    base_ew = ew[n0]
    bench_ew = {mk: ew[mk] / base_ew for mk in bench_months}
    if n0 in idx:
        base_idx = idx[n0]
        bench_idx = {mk: idx[mk] / base_idx for mk in bench_months if mk in idx}
    else:
        bench_idx = None
    print(f"  等权全A: {bench_months[0]}~{bench_months[-1]} "
          f"{len(bench_months)} 个月 | 终值 {bench_ew[bench_months[-1]]:.3f}")
    if bench_idx:
        print(f"  中证全指: 终值 {bench_idx[bench_months[-1]]:.3f}")

    # 信号 + 权重
    print("\n② 信号与权重")
    w_zhf: dict[str, dict[str, float]] = {}
    w_c: dict[str, dict[str, float]] = {}
    diag = {}
    for month, as_of in PIT_DATES:
        c = cons.get(month, {})
        sigs_z, dz = build_zhf_cons(c, month, as_of)
        w_zhf[month] = build_portfolio(sigs_z)
        sigs_c, dc = build_c_cons(c, month, as_of)
        w_c[month] = build_portfolio(sigs_c)
        diag[month] = {
            "univ": len(univ.get(month, [])), "cov": dz["cov"],
            "zhf_abstain": dz["abstain"], "zhf_cls": dz["cls"],
            "zhf_hold": len(w_zhf[month]),
            "c_dist": dc["c_dist"], "c_hold": len(w_c[month]),
        }
        print(f"  [{month}] univ={diag[month]['univ']} cov={dz['cov']} "
              f"zhf_cls={dz['cls']} hold={len(w_zhf[month])} "
              f"| c_hold={len(w_c[month])}")

    # 引擎回测
    print("\n③ 引擎回测")
    bench_use = {**bench_ew, **({} if bench_idx is None else bench_idx)}
    r_zhf = run_variant("ZHF-cons 全市场", w_zhf, bars, bench_ew)
    r_c = run_variant("C-cons 全市场", w_c, bars, bench_ew)
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
    for r in (r_zhf, r_c, r_ew):
        print(f"  {r['name']}: 总收益 {r['total']:+.1%} | "
              f"年化 {r['ann']:+.1%} | MDD "
              f"{r['mdd'] if r['mdd'] is not None else '-'}")
    if bench_idx:
        print(f"  {r_idx['name']}: 总收益 {r_idx['total']:+.1%} | "
              f"年化 {r_idx['ann']:+.1%}")
        r_zhf["excess_ew"] = r_zhf["total"] - r_ew["total"]
        r_zhf["excess_idx"] = r_zhf["total"] - r_idx["total"]
        r_c["excess_ew"] = r_c["total"] - r_ew["total"]
        r_c["excess_idx"] = r_c["total"] - r_idx["total"]
    print(f"  ZHF-cons 超额(等权全A): {r_zhf.get('excess_ew', float('nan')):+.1%}")

    # 个股贡献
    print("\n④ 个股贡献（ZHF-cons 每期 Top 贡献）")
    contrib = contribution(w_zhf, prices, bench_months, univ)
    for row in contrib:
        line = f"  {row['month']}→{row['end']}: {row['total_ret']:+.1%} " \
               f"({row['n']}只)"
        print(line)
        for it in row["top"]:
            print(f"      {it['tk']:12s} w={it['w']:.1%} "
                  f"ret={it['ret']:+.1%} contrib={it['contrib']:+.2%}")

    out = {
        "zhf": r_zhf, "c": r_c, "ew": r_ew,
        "idx": r_idx if bench_idx else None,
        "diag": diag, "weights_zhf": w_zhf, "weights_c": w_c,
        "contrib": contrib,
        "bench_ew": bench_ew,
        "bench_idx": bench_idx,
    }
    json.dump(out, open("_bt_winda_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_winda_results.json")


if __name__ == "__main__":
    main()
