"""章宏帆框架 × 分析师一致预期 — 2×2 诚实回测。

同池（章宏帆龙头池 58 只）同价（_zhf_prices.json）同成本（5bp+10bp）
同日历（2021-08 ~ 2026-04 十期半年调仓）vnpy 引擎：

  ZHF-act  章宏帆框架 + 实际财报（_bt_financials.json）
  ZHF-cons 章宏帆框架 + 一致预期（_bt_zhf_consensus.json）
  C-cons   纯 C-Score 一致预期信号（同池，数据本身的基线）

映射说明（诚实）：
  growth  := con_np_yoy/100        （预期净利增速 → 景气代理）
  roe     := con_roe               （预期 ROE）
  pe      := con_pe                （预期 PE）
  accel   := np_revision_4w > 0    （4 周预期上调 → 加速代理）
  gm      := 无预期毛利率数据 → 中性 0.5；B 类识别退化为"温和增速+预期上调"
  G5      := 无 EPS/PE 历史序列 → 不可用，penalty=1.0
  mcap    := 无市值数据 → 池即环节龙头（is_leader=True, is_big_leader=False）
  link_map:= 静态 2026-05 快照（框架的方向偏好，同 backtest_rotation）
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import StrategyTemplate
from src.core.models import Signal
from src.portfolio.balanced_sharpness import BalancedSharpnessBlend
from src.signals.c_score import calculate_c_score
from src.signals.rotation_growth import RotationGrowthModel, DEFAULT_LINK_MAP

from examples.alla_rotation import LEADER_SEEDS

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

PRICES_FILE = "_zhf_prices.json"
FIN_FILE = "_bt_financials.json"
CONS_FILE = "_bt_zhf_consensus.json"
BENCH_FILE = "_bt_benchmark.json"

PE_CEILING_BY_LINK = {
    "半导体设备": 150, "半导体材料": 100, "CPU+光芯片": 120,
    "国产算力": 200, "存储": 60, "PCB材料": 35,
    "光模块/光通信": 45, "电子制造/封测": 45, "晶圆代工": 100,
}


def build_leaders() -> dict[str, tuple[str, str]]:
    """{tk: (name, link)} — 全龙头池。"""
    out: dict[str, tuple[str, str]] = {}
    for link, seeds in LEADER_SEEDS.items():
        if link.startswith("_"):
            continue
        real = link[:-3] if link.endswith("_HK") else link
        for name, tk in seeds.items():
            out.setdefault(tk, (name, real))
    return out


# ===========================================================================
# 一致预期装载
# ===========================================================================

def load_consensus() -> dict[str, dict[str, dict]]:
    """{month: {ticker: record}} — 同 backtest_c_score.load_consensus。"""
    cons = json.loads(open(CONS_FILE, encoding="utf-8").read())
    out: dict[str, dict[str, dict]] = {}
    for month, d in cons.items():
        as_of_year = int(month[:4])
        best: dict[str, dict] = {}
        for r in d.get("records", []):
            sc = r.get("stock_code", "")
            tk = sc.split(".")[0] + "." + ("SH" if sc.endswith((".SH", ".sh")) else "SZ")
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


# ===========================================================================
# ZHF-act：章宏帆框架 + 实际财报（修复旧回测 gm 键丢失 bug）
# ===========================================================================

class ActAdapter:
    def __init__(self, fin_at: dict, month_key: str, names: dict, links: dict):
        self._fin = fin_at
        self._month = month_key
        self._names = names
        self._links = links

    def get_prices(self, ticker, start_date, end_date):
        return []

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=60):
        periods = self._fin.get(ticker, {})
        rows = []
        for pk in sorted(periods.keys(), reverse=True)[:limit]:
            y, q = int(pk[:4]), int(pk[5])
            d = f"{y}-{q * 3:02d}-30"
            if d > end_date:
                continue
            m = periods[pk]
            rows.append({"ticker": ticker, "date": d, "period": period,
                         "revenue": m.get("revenue"),
                         "gross_margin": m.get("gm"),      # 修复：gm→gross_margin
                         "roe": m.get("roe")})
        return rows

    def get_company_facts(self, ticker):
        return {"ticker": ticker, "name": self._names.get(ticker, ""),
                "sector": "", "industry": "",
                "link": self._links.get(ticker)}

    def get_earnings(self, ticker):
        return None


def avail_financials(financials: dict, as_of: str) -> dict:
    from datetime import date
    out = {}
    d = date.fromisoformat(as_of)
    for tk, periods in financials.items():
        filtered = {}
        for pk, metrics in periods.items():
            parts = pk.split("-")
            if len(parts) != 2:
                continue
            y, q = int(parts[0]), int(parts[1])
            if q == 1:
                deadline = date(y, 4, 30)
            elif q == 2:
                deadline = date(y, 8, 31)
            elif q == 3:
                deadline = date(y, 10, 31)
            else:
                deadline = date(y + 1, 4, 30)
            if deadline <= d:
                filtered[pk] = metrics
        if filtered:
            out[tk] = filtered
    return out


def build_zhf_act_weights(financials: dict, leaders: dict) -> dict[str, dict[str, float]]:
    """每期：RotationGrowthModel(静态link_map) → blend → weights。"""
    model = RotationGrowthModel(
        boom_growth=0.40,
        pe_ceiling_by_link=PE_CEILING_BY_LINK,
        off_theme_scope=None)
    blender = BalancedSharpnessBlend(
        top_direction_weight=0.22, tail_direction_weight=0.12,
        max_directions=8, class_mix={"A": 0.60, "B": 0.35, "C": 0.05},
        per_name_cap=0.05, off_theme_sleeve=0.05,
        max_names_per_direction=6, scale_to_target=True)
    names = {tk: v[0] for tk, v in leaders.items()}
    links = {tk: v[1] for tk, v in leaders.items()}

    weights_by_dt: dict[str, dict[str, float]] = {}
    for month, as_of in PIT_DATES:
        fin_at = avail_financials(financials, as_of)
        adapter = ActAdapter(fin_at, month, names, links)
        signals = []
        for tk in leaders:
            try:
                sig = model.predict(tk, as_of, adapter)
            except Exception:
                continue
            if sig is not None and sig.value > 0:
                signals.append(sig)
        result = blender.blend(signals, {"rotation_growth": 1.0}, gross_target=1.0)
        weights_by_dt[month] = {t: w for t, w in result.weights.items() if w > 0}
        n_cls = {}
        for s in signals:
            cls_ = (s.metadata or {}).get("asset_class", "?")
            n_cls[cls_] = n_cls.get(cls_, 0) + 1
        print(f"  [ZHF-act {month}] sig={len(signals)} hold={len(weights_by_dt[month])} "
              f"cls={n_cls}")
    return weights_by_dt


# ===========================================================================
# ZHF-cons：章宏帆框架逻辑 × 一致预期（忠实转写 + 显式映射）
# ===========================================================================

def _band(x, low, high):
    if x is None:
        return 0.5
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (x - low) / (high - low)))


def zhf_cons_signal(rec: dict, link: str | None,
                    pe_ceil: float) -> Signal | None:
    """单只股票：章宏帆决策树 × 一致预期字段。返回 Signal 或 None(abstain)。"""
    g = None
    if rec.get("con_np_yoy") is not None:
        try:
            g = float(rec["con_np_yoy"]) / 100.0
        except (TypeError, ValueError):
            g = None
    roe = rec.get("con_roe")
    pe = rec.get("con_pe")
    rev4 = rec.get("np_revision_4w")
    try:
        roe = float(roe) if roe is not None else None
        pe = float(pe) if pe is not None else None
        rev4 = float(rev4) if rev4 is not None else None
    except (TypeError, ValueError):
        pass

    if g is None:
        return None  # 无一致预期增速 → abstain
    accel = rev4 is not None and rev4 > 0

    # 环节稀缺度（静态框架方向偏好）
    if link and link in DEFAULT_LINK_MAP:
        s_scores = list(DEFAULT_LINK_MAP[link].get("s_scores", [0] * 5))
    else:
        s_scores = [0] * 5
    link_norm = sum(s_scores) / 10.0

    # 质量乘数（龙头池：is_leader=True；无毛利率预期 → q_gm 中性）
    profitable = pe is None or pe > 0
    q_gm, q_roe = 0.5, _band(roe, 0.0, 20.0)
    quality_mult = 0.55 + 0.25 * q_gm + 0.15 * q_roe + 0.10 \
        + (0.05 if profitable else -0.25)
    quality_mult = max(0.30, min(1.15, quality_mult))

    # L1 分类
    low_quality = (roe is not None and roe < 5) or not profitable
    if g >= 1.50 and low_quality:
        cls = "C"
    elif g >= 0.40 and accel:
        if not profitable:
            return None  # A 类要求正利润（预期亏损 → 不买）
        if roe is not None and roe < 8:
            cls = "C"    # 高增速低预期ROE → 降级小仓
        else:
            cls = "A"
    elif (g >= 0.24 and roe is not None and roe >= 15):
        cls = "A"        # 质量豁免通道（龙头+ROE≥15；毛利率约束因无数据放宽）
        quality_mult *= 0.85
    elif accel and 0 < g < 0.40:
        cls = "B"        # B 类：温和预期增速 + 预期上调（无毛利率 → 放宽识别）
    elif (roe is not None and roe >= 15):
        cls = "OFF"      # OFF sleeve（限科技域：池内全是科技链，直接给）
    else:
        return None

    # 类则估值
    if cls == "A":
        upside = g  # 原框架 growth*(1+gm/100)，gm 缺省 → growth
        if upside < 0.30:
            value = 0.15
        else:
            value = min(1.0, 0.30 + 0.50 * link_norm + 0.20 * min(g, 1.0))
    elif cls == "B":
        if pe is not None and pe > pe_ceil:
            value = -0.5   # 预期估值超上限 → 减仓信号
        elif pe is not None and pe <= 0:
            return None
        else:
            value = min(0.8, 0.30 + 0.40 * link_norm + (0.20 if accel else 0.0))
    elif cls == "C":
        value = min(0.30, 0.20 + 0.10 * link_norm)
    else:  # OFF
        value = min(0.40, 0.20 + 0.10 * min((roe or 0) / 30.0, 1.0))

    value *= quality_mult  # G5=1.0（无历史序列），L5=neutral

    if value <= 0:
        return None
    return Signal(
        model_name="zhf_cons", ticker="", date="", value=round(value, 4),
        reasoning="", components={"link_score": sum(s_scores)},
        metadata={"asset_class": cls, "link": link,
                  "con_np_yoy": rec.get("con_np_yoy"),
                  "con_roe": roe, "con_pe": pe, "rev4": rev4},
    )


def build_zhf_cons_weights(cons_map_all: dict, leaders: dict
                           ) -> tuple[dict[str, dict[str, float]], dict]:
    blender = BalancedSharpnessBlend(
        top_direction_weight=0.22, tail_direction_weight=0.12,
        max_directions=8, class_mix={"A": 0.60, "B": 0.35, "C": 0.05},
        per_name_cap=0.05, off_theme_sleeve=0.05,
        max_names_per_direction=6, scale_to_target=True)
    weights_by_dt: dict[str, dict[str, float]] = {}
    diag: dict[str, dict] = {}
    for month, as_of in PIT_DATES:
        cons = cons_map_all.get(month, {})
        signals, n_cls, n_abstain = [], {}, 0
        for tk, (name, link) in leaders.items():
            rec = cons.get(tk)
            if not rec:
                n_abstain += 1
                continue
            sig = zhf_cons_signal(rec, link, PE_CEILING_BY_LINK.get(link, 20.0))
            if sig is None:
                n_abstain += 1
                continue
            sig.ticker = tk
            sig.date = as_of
            cls = (sig.metadata or {}).get("asset_class")
            n_cls[cls] = n_cls.get(cls, 0) + 1
            signals.append(sig)
        result = blender.blend(signals, {"zhf_cons": 1.0}, gross_target=1.0)
        weights_by_dt[month] = {t: w for t, w in result.weights.items() if w > 0}
        diag[month] = {"pool": len(leaders), "cov": len(cons),
                       "abstain": n_abstain, "cls": n_cls,
                       "hold": len(weights_by_dt[month])}
        print(f"  [ZHF-cons {month}] cov={len(cons)} sig={len(signals)} "
              f"abstain={n_abstain} hold={len(weights_by_dt[month])} cls={n_cls}")
    return weights_by_dt, diag


# ===========================================================================
# C-cons：纯一致预期信号（同池基线）
# ===========================================================================

def build_c_cons_weights(cons_map_all: dict, leaders: dict
                         ) -> tuple[dict[str, dict[str, float]], dict]:
    weights_by_dt: dict[str, dict[str, float]] = {}
    diag: dict[str, dict] = {}
    for month, as_of in PIT_DATES:
        cons = cons_map_all.get(month, {})
        signals, dist = [], {}
        for tk, (name, link) in leaders.items():
            rec = cons.get(tk)
            if not rec:
                continue
            c_score, _d = calculate_c_score(rec)
            dist[c_score] = dist.get(c_score, 0) + 1
            if c_score >= 2:
                value = {2: 0.30, 3: 0.50, 4: 0.70}[min(c_score, 4)]
                signals.append(Signal(
                    model_name="c_cons", ticker=tk, date=as_of,
                    value=value, reasoning=f"C={c_score}/4",
                    components={"c_score": c_score},
                    metadata={"name": name, "link": link}))
        w = {}
        total = sum(s.value for s in signals)
        if signals and total > 0:
            for s in signals:
                w[s.ticker] = round(min(0.10, s.value / total * 0.9), 4)
        weights_by_dt[month] = {t: v for t, v in w.items() if v > 0}
        diag[month] = {"cov": len(cons), "c_dist": dist, "hold": len(w)}
        print(f"  [C-cons {month}] cov={len(cons)} dist={dist} hold={len(w)}")
    return weights_by_dt, diag


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


def run_variant(name: str, weights_by_dt: dict, bars: dict, bench: dict,
                nav_file: str) -> dict:
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
    dts = sorted(bal.keys())
    total = bal[dts[-1]] / CAPITAL - 1
    yrs = len(dts) / 12
    ann = (1 + total) ** (1 / yrs) - 1 if total > -1 else -1
    mdd = stats.get("max_ddpercent", 0) / 100.0
    br = bench.get(dts[-1], 0) / bench.get(dts[0], 1) - 1 if dts[0] in bench and dts[-1] in bench else None
    ex = total - br if br is not None else None
    print(f"  [{name}] 总收益 {total:+.1%} | 年化 {ann:+.1%} | MDD {mdd:.1%} | "
          f"基准 {br:+.1%} | 超额 {ex:+.1%}")
    nav = [{"month": r["dt"], "nav": r["balance"]} for r in daily if r["dt"] in bench]
    json.dump(nav, open(nav_file, "w", encoding="utf-8"), ensure_ascii=False)
    return {"name": name, "total": total, "ann": ann, "mdd": mdd,
            "bench": br, "excess": ex, "nav": nav}


# ===========================================================================
# main
# ===========================================================================

def main():
    print("=" * 76)
    print("  章宏帆框架 × 分析师一致预期 — 2×2 回测（同池同价同成本）")
    print("=" * 76)
    leaders = build_leaders()
    print(f"龙头池: {len(leaders)} 只")

    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    financials = json.loads(open(FIN_FILE, encoding="utf-8").read())
    cons = load_consensus()
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())

    # 价格 -> bars（月度 BarData，2021-06 起）
    bars = {}
    for tk, m in prices.items():
        mm = {mk: px for mk, px in m.items() if px and px > 0 and mk >= "2021-06"}
        if mm:
            bars[tk] = {mk: BarData(tk, mk, px, px, px, px) for mk, px in mm.items()}

    print("\n① ZHF-act（框架+实际财报）")
    w_act = build_zhf_act_weights(financials, leaders)
    print("\n② ZHF-cons（框架+一致预期）")
    w_cons, d_cons = build_zhf_cons_weights(cons, leaders)
    print("\n③ C-cons（纯一致预期）")
    w_c, d_c = build_c_cons_weights(cons, leaders)

    print("\n④ 引擎回测")
    results = [
        run_variant("ZHF-act 框架×财报", w_act, bars, bench, "_bt_zhf_act_nav.json"),
        run_variant("ZHF-cons 框架×预期", w_cons, bars, bench, "_bt_zhf_cons_nav.json"),
        run_variant("C-cons 纯预期", w_c, bars, bench, "_bt_zhf_c_nav.json"),
    ]
    json.dump({"act": w_act, "cons": w_cons, "c": w_c,
               "diag_cons": d_cons, "diag_c": d_c},
              open("_bt_zhf_weights.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(results, open("_bt_zhf_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_zhf_results.json | 权重 → _bt_zhf_weights.json")


if __name__ == "__main__":
    main()
