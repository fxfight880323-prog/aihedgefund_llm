"""点时选择回测（去除幸存者偏差）+ BSADF 热度卖出。

与 backtest_universal.py 的本质区别：
  旧版 universe = 2026 年已知龙头池（幸存者偏差：选股时已知道谁赢了）
  本版每期从头执行方法论：
    ① 全市场增速 top-100 筛选（点时报告期数据，当前市值 >50亿 过滤）
    ② 自下而上聚合申万一级行业 → 行业稀缺度排名（先选行业）
    ③ 行业内质量门（ROE≥8 / 非ST / 上年同期营收≥5亿）→ 候选（再选个股）
    ④ RotationGrowthModel 打分 + BalancedSharpnessBlend 组仓
    ⑤ BSADF 月频相位叠加（BURST/FEAR/PROBE_EXIT→强制清仓，
       FADING→减半；RIDING/IGNITION→骑泡沫不动）

点时语义：
  - 筛选/财务字段带 -YYYY.MM.DD 后缀（该报告期数值）
  - 候选存在性用"上年同期营业收入 > 0"保证（未上市/无数据不入池）
  - 财务历史拉全报告期后按披露截止日过滤（avail_financials）
诚实标注：
  - 申万行业分类与 50亿 市值过滤是 2026 当前口径（轻度前视，行业
    归类变化远小于个股幸存者偏差）
  - MX 选股器对超长列表可能截断（每期实际返回行数见日志）

Run:
    python examples/backtest_pit.py --select    # 选择+取数（有缓存）
    python examples/backtest_pit.py             # 回测
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

from src.backtest.engine import BacktestingEngine, BarData, _month_span
from src.backtest.strategy import RotationStrategy, avail_financials
from src.data.mx_data_client import parse_cn_number, sheet_to_indexed
from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE, TOOL_SCREENER

CAPITAL = 1_000_000
SELECTION_FILE = "_bt_pit_selection.json"     # 每期筛选结果
FINANCIALS_FILE = "_bt_pit_financials.json"   # 财务（含旧缓存合并）
PRICES_FILE = "_bt_pit_prices.json"           # 价格（含旧缓存合并）
WARMUP_FILE = "_bt_pit_warmup.json"           # 2019-2021 BSADF 预热价格
BENCHMARK_FILE = "_bt_benchmark.json"
NAV_FILE = "_bt_pit_nav.json"

# (rebalance month, as_of, 报告期中文, 点时日期标签, 上年同期标签)
PIT_DATES = [
    ("2021-08", "2021-08-31", "2021年中报", "2021.06.30", "2020.06.30"),
    ("2022-04", "2022-04-30", "2022年一季报", "2022.03.31", "2021.03.31"),
    ("2022-08", "2022-08-31", "2022年中报", "2022.06.30", "2021.06.30"),
    ("2023-04", "2023-04-30", "2023年一季报", "2023.03.31", "2022.03.31"),
    ("2023-08", "2023-08-31", "2023年中报", "2023.06.30", "2022.06.30"),
    ("2024-04", "2024-04-30", "2024年一季报", "2024.03.31", "2023.03.31"),
    ("2024-08", "2024-08-31", "2024年中报", "2024.06.30", "2023.06.30"),
    ("2025-04", "2025-04-30", "2025年一季报", "2025.03.31", "2024.03.31"),
    ("2025-08", "2025-08-31", "2025年中报", "2025.06.30", "2024.06.30"),
    ("2026-04", "2026-04-30", "2026年一季报", "2026.03.31", "2025.03.31"),
]


def norm_ticker(code: str) -> str | None:
    c = str(code).strip().split(".")[0]
    if not re.fullmatch(r"\d{6}", c):
        return None
    if c[0] == "6":
        return f"{c}.SH"
    if c[0] in ("0", "3"):
        return f"{c}.SZ"
    return None                    # 北交所/其他跳过


def _field(row: dict, *needles, exclude=()) -> str | None:
    for k, v in row.items():
        ks = str(k)
        if all(n in ks for n in needles) and not any(e in ks for e in exclude):
            return str(v)
    return None


# ===========================================================================
# 阶段一：点时选择（先行业 → 后个股）
# ===========================================================================

def run_selection() -> dict:
    """每期：全市场 top-100 增速 → 行业聚合打分 → 行业内质量候选。"""
    cli = MXMCPClient()
    if os.path.exists(SELECTION_FILE):
        sel = json.loads(open(SELECTION_FILE, encoding="utf-8").read())
        print(f"  选择结果已缓存: {len(sel)} 期")
        return sel
    sel: dict[str, dict] = {}
    for month, as_of, cn_period, dtag, ptag in PIT_DATES:
        q = (f"{cn_period}营业收入同比增速从高到低排名前100的A股，"
             f"总市值大于50亿元，显示申万行业分类、{cn_period}营业收入"
             f"同比增长率、{cn_period}净资产收益率ROE、上年同期营业收入")
        try:
            sheets = cli.query(TOOL_SCREENER, q, use_cache=False)
        except Exception as e:
            print(f"  [{month}] 筛选失败: {e}")
            continue
        rows = []
        for sh in sheets:
            for rank, row in sheet_to_indexed(sh).items():
                code = _field(row, "代码")
                tk = norm_ticker(code or "")
                if not tk:
                    continue
                name = (_field(row, "名称") or "").strip()
                if "ST" in name or "退" in name:
                    continue
                sw = _field(row, "申万行业分类") or ""
                sw1 = sw.split("-")[0] if sw else "未知"
                g_raw = _field(row, "营业收入同比增长率", exclude=("元",))
                growth = parse_cn_number(g_raw.split("|")[0]) if g_raw else None
                r_raw = _field(row, "ROE")
                roe = (parse_cn_number(r_raw.split("|")[0])
                       if r_raw else None)
                # 上年同期营收（存在性 + 规模代理，亿元）
                prior_rev = None
                for k, v in row.items():
                    ks = str(k)
                    if ("营业收入" in ks and "元" in ks
                            and "同比" not in ks and ptag in ks):
                        raw = str(v).split("|")[0]
                        pv = parse_cn_number(raw)
                        if pv is not None:
                            # 裸数字（无 亿/万 后缀）单位为万元
                            if not re.search(r"[亿万]", raw):
                                pv = pv * 1e4
                            prior_rev = pv
                if growth is None or roe is None:
                    continue
                rows.append({
                    "tk": tk, "name": name, "sw1": sw1,
                    "growth": growth / 100.0,      # 百分数 → 分数
                    "roe": roe,
                    "prior_rev_yi": (prior_rev / 1e8
                                     if prior_rev else None),
                })
        if not rows:
            print(f"  [{month}] 无有效行")
            continue

        # ---- 自下而上行业聚合（先选行业）----
        groups: dict[str, list] = {}
        for r in rows:
            groups.setdefault(r["sw1"], []).append(r)
        link_map = {}
        for ind, members in groups.items():
            growths = sorted(m["growth"] for m in members)
            med_g = growths[len(growths) // 2]
            roe8 = sum(1 for m in members if m["roe"] >= 8) / len(members)
            s1 = min(2, len(members) // 4)
            s2 = min(2, max(0, int(med_g / 0.30)))
            s3 = min(2, round(2 * roe8))
            link_map[ind] = {"s_scores": [s1, s2, s3, 0, 0],
                             "keywords": [], "n_members": len(members),
                             "med_growth": med_g}
        ranked = sorted(link_map.items(),
                        key=lambda kv: -sum(kv[1]["s_scores"]))
        top_inds = {n for n, c in ranked[:5] if sum(c["s_scores"]) >= 3}

        # ---- 行业内候选（再选个股；质量门交给模型，此处只挡
        #      壳股/超小基数：增速 ≥30% + 上年同期营收 ≥1 亿）----
        cand = []
        for r in rows:
            if r["sw1"] not in top_inds:
                continue
            if r["growth"] < 0.30:
                continue
            if not r["prior_rev_yi"] or r["prior_rev_yi"] < 1:
                continue
            cand.append(r)
        cand.sort(key=lambda r: -(r["growth"] * min(r["roe"], 25)))
        per_ind: dict[str, int] = {}
        capped = []
        for r in cand:
            if per_ind.get(r["sw1"], 0) >= 8:
                continue
            per_ind[r["sw1"]] = per_ind.get(r["sw1"], 0) + 1
            capped.append(r)

        sel[month] = {
            "as_of": as_of, "n_rows": len(rows),
            "n_industries": len(groups),
            "top_industries": [(n, sum(c["s_scores"])) for n, c in ranked[:6]],
            "link_map": link_map,
            "candidates": [(r["tk"], r["name"], r["sw1"]) for r in capped],
        }
        print(f"  [{month}] {len(rows)} 行 → {len(groups)} 行业 | "
              f"top: {' '.join(f'{n}({s}/10)' for n, s in ranked[:4])} | "
              f"候选 {len(capped)} 只", flush=True)
        json.dump(sel, open(SELECTION_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
    return sel


# ===========================================================================
# 阶段二：候选的财务与价格（增量取数，合并旧缓存）
# ===========================================================================

def fetch_details(sel: dict) -> tuple[dict, dict, dict]:
    cli = MXMCPClient()
    financials = {}
    if os.path.exists(FINANCIALS_FILE):
        financials = json.loads(open(FINANCIALS_FILE, encoding="utf-8").read())
    if os.path.exists("_bt_uni_financials.json"):
        for tk, p in json.loads(open("_bt_uni_financials.json",
                                     encoding="utf-8").read()).items():
            for m in p.values():
                if "gm" in m and "gross_margin" not in m:
                    m["gross_margin"] = m.pop("gm")
            financials.setdefault(tk, p)
    prices = {}
    if os.path.exists(PRICES_FILE):
        prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    if os.path.exists("_bt_uni_prices.json"):
        for tk, m in json.loads(open("_bt_uni_prices.json",
                                     encoding="utf-8").read()).items():
            prices.setdefault(tk, m)
    warmup = {}
    if os.path.exists(WARMUP_FILE):
        warmup = json.loads(open(WARMUP_FILE, encoding="utf-8").read())

    all_cand: dict[str, str] = {}      # tk → name
    for month, s in sel.items():
        for tk, name, _ in s["candidates"]:
            all_cand[tk] = name
    print(f"  唯一候选 {len(all_cand)} 只（财务缓存 {len(financials)}，"
          f"价格缓存 {len(prices)}）")

    # ---- 财务（新候选）----
    todo = [tk for tk in all_cand if tk not in financials]
    for i, tk in enumerate(todo):
        name = all_cand[tk]
        q = (f"{name}({tk}) 2020年中报到2026年中报每个报告期的"
             f"营业收入、销售毛利率、净资产收益率ROE")
        try:
            sheets = cli.query(TOOL_ASHARE, q, use_cache=False)
        except Exception:
            continue
        periods: dict[str, dict] = {}
        for sh in sheets:
            for metric, by_col in sheet_to_indexed(sh).items():
                ms = str(metric)
                for col, val in by_col.items():
                    cs = str(col)
                    ym = re.search(r"(\d{4})", cs)
                    if not ym:
                        continue
                    y = int(ym.group(1))
                    qn = (1 if "一季" in cs else
                          2 if "中报" in cs or "半年" in cs else
                          3 if "三季" in cs else
                          4 if "年报" in cs or "年度" in cs else None)
                    if qn is None:
                        continue
                    pk = f"{y}-{qn}"
                    v = parse_cn_number(str(val).split("|")[0])
                    if v is None:
                        continue
                    if "营业收入" in ms and "同比" not in ms:
                        periods.setdefault(pk, {})["revenue"] = v
                    elif "毛利率" in ms:
                        periods.setdefault(pk, {})["gross_margin"] = v
                    elif "ROE" in ms or "净资产收益率" in ms:
                        periods.setdefault(pk, {})["roe"] = v
        if periods:
            financials[tk] = periods
        if (i + 1) % 10 == 0:
            print(f"    … 财务 {i + 1}/{len(todo)}", flush=True)
            json.dump(financials, open(FINANCIALS_FILE, "w",
                                       encoding="utf-8"), ensure_ascii=False)
    json.dump(financials, open(FINANCIALS_FILE, "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"  财务就绪: {sum(1 for tk in all_cand if tk in financials)}"
          f"/{len(all_cand)}")

    # ---- BSADF 预热价格（2019-01→2021-05，仅缺缓存的）----
    from examples.fill_winter_prices import parse_monthly
    todo_w = [tk for tk in all_cand if tk not in warmup]
    for i, tk in enumerate(todo_w):
        name = all_cand[tk]
        q = f"{name}({tk}) 2019年1月到2021年5月每月末的收盘价"
        try:
            got = parse_monthly(cli.query(TOOL_ASHARE, q, use_cache=False))
            if got:
                warmup[tk] = {k: v for k, v in got.items() if k < "2021-06"}
        except Exception:
            pass
        if (i + 1) % 10 == 0:
            print(f"    … 预热 {i + 1}/{len(todo_w)}", flush=True)
            json.dump(warmup, open(WARMUP_FILE, "w", encoding="utf-8"))
    json.dump(warmup, open(WARMUP_FILE, "w", encoding="utf-8"))
    print(f"  预热价格就绪: {len(warmup)} 只")

    # ---- 主区间价格（2021-06→2026-08，缺缓存的补拉）----
    todo_p = [tk for tk in all_cand
              if tk not in prices or len(prices[tk]) < 50]
    for i, tk in enumerate(todo_p):
        name = all_cand[tk]
        acc: dict[str, float] = prices.get(tk, {})
        queries = [
            f"{name}({tk}) 2021年6月到2023年11月每月末的收盘价",
            f"{name}({tk}) 2023年12月至2025年5月各月末的收盘价，"
            f"以及2024年12月至2025年5月各月末的收盘价",
            f"{name}({tk}) 2025年6月到2026年8月每月末的收盘价",
        ]
        for q in queries:
            try:
                got = parse_monthly(cli.query(TOOL_ASHARE, q,
                                              use_cache=False))
                acc.update(got)
            except Exception:
                continue
        if acc:
            prices[tk] = acc
        if (i + 1) % 5 == 0:
            print(f"    … 价格 {i + 1}/{len(todo_p)}", flush=True)
            json.dump(prices, open(PRICES_FILE, "w", encoding="utf-8"))
    json.dump(prices, open(PRICES_FILE, "w", encoding="utf-8"))
    print(f"  主区间价格就绪: {sum(1 for tk in all_cand if tk in prices)}"
          f"/{len(all_cand)}")
    return financials, prices, warmup


# ===========================================================================
# 阶段三：回测
# ===========================================================================

def run_backtest(sel, financials, prices, warmup):
    # 合并预热 + 主区间 → BSADF 输入（预热在前）
    bsadf_prices = {tk: {**warmup.get(tk, {}), **m}
                    for tk, m in prices.items()}
    # 引擎 bars：主区间
    bars = {tk: {mk: BarData(tk, mk, px, px, px, px)
                 for mk, px in m.items() if px and px > 0}
            for tk, m in prices.items()}
    bars = {tk: {mk: b for mk, b in m.items() if mk >= "2021-06"}
            for tk, m in bars.items()}
    bars = {tk: m for tk, m in bars.items() if m}

    candidates_by_dt, linkmap_by_dt, universe_all = {}, {}, set()
    for month, s in sel.items():
        cands = [(tk, name, sw1) for tk, name, sw1 in s["candidates"]]
        candidates_by_dt[month] = cands
        for c in cands:
            universe_all.add(c)
        linkmap_by_dt[month] = {
            ind: {"s_scores": cfg["s_scores"], "keywords": []}
            for ind, cfg in s.get("link_map", {}).items()}
    universe = sorted(universe_all)
    dt_all = sorted({mk for m in bars.values() for mk in m})
    rb_map = {month: s["as_of"] for month, s in sel.items()}
    print(f"\n  数据: {len(financials)} 财务 | {len(bars)} 价格 | "
          f"{dt_all[0]} → {dt_all[-1]}")
    print(f"  逐期候选: " + " ".join(
        f"{m}:{len(c)}" for m, c in sorted(candidates_by_dt.items())))

    engine = BacktestingEngine()
    engine.set_parameters(symbols=list(bars.keys()), capital=CAPITAL,
                          rate=0.0005, slippage=0.001)
    engine.add_data(bars)
    uni_list = [(tk, tk, "") for tk in universe]  # label 走候选注入
    strategy = RotationStrategy(engine, {
        "financials": financials,
        "universe": uni_list,
        "rebalance_dts": set(rb_map.keys()),
        "disclosure_of": rb_map,
        "candidates_by_dt": candidates_by_dt,
        "linkmap_by_dt": linkmap_by_dt,
        "bsadf": {"prices": bsadf_prices},
    })
    engine.add_strategy(strategy)
    engine.run_backtesting()
    return engine, strategy


def main(select_only: bool = False):
    print("=" * 78)
    print("  章宏帆轮动 · 点时选择回测（无幸存者偏差）+ BSADF 热度卖出")
    print("=" * 78)
    print("\n① 点时选择（全市场筛选 → 行业聚合 → 行业内候选）…")
    sel = run_selection()
    if select_only:
        return
    print("\n② 候选财务/价格取数…")
    financials, prices, warmup = fetch_details(sel)

    print("\n③ vnpy 引擎回测…")
    engine, strategy = run_backtest(sel, financials, prices, warmup)

    print("\n④ 结算与统计…")
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily)

    bench = json.loads(open(BENCHMARK_FILE, encoding="utf-8").read())
    bal = {r["dt"]: r["balance"] for r in daily}
    dts = sorted(bal.keys())
    if dts and dts[-1] in bench and dts[0] in bench:
        r = bal[dts[-1]] / CAPITAL - 1
        br = bench[dts[-1]] / bench[dts[0]] - 1
        yrs = _month_span(dts[0], dts[-1]) / 12
        print(f"\n  基准对比: 策略 {r:+.1%} vs 中证全指 {br:+.1%} | "
              f"超额 {r - br:+.1%} | 年化 {((1 + r) ** (1 / yrs) - 1):+.1%}"
              f" vs {((1 + br) ** (1 / yrs) - 1):+.1%}（{yrs:.1f} 年）")

    print("\n⑤ BSADF 卖出叠加日志")
    if strategy.bsadf_log:
        for e in strategy.bsadf_log:
            if e.get("unit") == "股":
                print(f"   [{e['dt']}] {e['ticker']} {e['phase']}: "
                      f"{e['before']:,.0f} 股 → {e['after']:,.0f} 股")
            else:
                print(f"   [{e['dt']}] {e['ticker']} {e['phase']}: "
                      f"{e['before']:.1%} → {e['after']:.1%}")
    else:
        print("   （本期无泡沫触发的卖出/减仓）")

    print("\n⑥ 逐期持仓")
    name_of = {}
    for s in sel.values():
        for tk, name, _ in s["candidates"]:
            name_of[tk] = name
    for h in strategy.history:
        tops = ", ".join(f"{name_of.get(t, t)} {w:.0%}"
                         for t, w in sorted(h["weights"].items(),
                                            key=lambda x: -x[1])[:6])
        print(f"   [{h['dt']}] {h['n_hold']} 只 | {tops}")

    nav_rows = [{"month": r["dt"], "nav": r["balance"]}
                for r in daily if r["dt"] in bench]
    json.dump(nav_rows, open(NAV_FILE, "w", encoding="utf-8"))
    print(f"\n完成。NAV → {NAV_FILE}")


if __name__ == "__main__":
    main(select_only="--select" in sys.argv)
