"""章宏帆轮动策略 — 5 年历史回测（Wind 全A universe，半年度调仓）。

设计：
  Universe    = 50 只龙头（7 个方向 × 每方向 5-8 只；已在实盘中确认）
  调仓频率    = 半年度（年报/中报披露截止日：4/30 和 8/31）
  回测区间    = 2021-08-31 → 2026-08-17（10 个调仓期）
  信号        = rotation_growth 模型，点时数据（只看当时已披露的财报）
  组仓        = balanced_sharpness blend（同实盘参数）
  P&L         = 持有到下一调仓日，以月末收盘价估值

  数据效率    = 每只龙头 2 次妙想查询：
                ① 历史季度财务（营收/毛利率/ROE，2020-2026 全部报告期）
                ② 历史月末价格/PE/总市值（2021-06 到 2026-08）
                + 1 次基准查询（中证全指月末价格）
                总计 ~101 次查询

诚实标注：
  - 环节稀缺度表（link_map）是 2026-05 快照——S 分在整个回测期固定，
    2021-2023 年存储/光模块未必是当时最稀缺的方向；真实可交易策略
    需要在每个时点重建环节排名（G1/G2 供应链审计的数据量远超本回测
    范围）
  - 龙头池本身有幸存者偏差（2026 年知道的龙头 ≠ 2021 年的龙头）
  - 结果应解读为"给定这个固定的方向偏好，历史上能捕获多少 AI 链
    景气度"，而不是"这个策略过去 5 年能赚多少钱"

Run:
    python examples/backtest_rotation.py [--fetch] [--skip-fetch]
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import numpy as np

from src.data.mx_data_client import parse_cn_number, sheet_to_indexed
from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE, TOOL_HK, TOOL_INDEX

# ===========================================================================
# 参数
# ===========================================================================

CAPITAL = 1_000_000
COST_BPS = 20  # 单边交易成本（基点）

# 调仓日（报告披露截止日近似）
REBALANCE_DATES = [
    "2021-08-31",  # 2021 中报
    "2022-04-30",  # 2021 年报 + 2022Q1
    "2022-08-31",  # 2022 中报
    "2023-04-30",  # 2022 年报 + 2023Q1
    "2023-08-31",  # 2023 中报
    "2024-04-30",  # 2023 年报 + 2024Q1
    "2024-08-31",  # 2024 中报
    "2025-04-30",  # 2024 年报 + 2025Q1
    "2025-08-31",  # 2025 中报
    "2026-04-30",  # 2025 年报 + 2026Q1
]
END_DATE = "2026-08-17"

# 龙头池（同 alla_rotation 的 LEADER_SEEDS，展平）
from examples.alla_rotation import LEADER_SEEDS

ALL_LEADERS: dict[str, str] = {}  # ticker → name
LEADER_LINK: dict[str, str] = {}  # ticker → link
for link, seeds in LEADER_SEEDS.items():
    if link.startswith("_"):
        continue
    real_link = link[:-3] if link.endswith("_HK") else link
    for name, ticker in seeds.items():
        clean_name = name[:-2] if name.endswith("_H") else name
        if ticker not in ALL_LEADERS:
            ALL_LEADERS[ticker] = clean_name
            LEADER_LINK[ticker] = real_link if real_link != "_HK_PLATFORMS" else None

FINANCIALS_FILE = "_bt_financials.json"
PRICES_FILE = "_bt_prices.json"
BENCHMARK_FILE = "_bt_benchmark.json"


# ===========================================================================
# 数据拉取
# ===========================================================================

def _pick(by_col: dict, *needles, period=None):
    """从 metric→{col: val} 中取值"""
    for col, val in by_col.items():
        cs = str(col)
        if period and period not in cs:
            continue
        v = parse_cn_number(str(val).split("|")[0])
        if v is not None:
            return v
    return None


def fetch_all(cli: MXMCPClient):
    """拉取全部龙头的历史财务 + 价格 + 基准。"""
    # ---- 1. 历史季度财务 ----
    if os.path.exists(FINANCIALS_FILE):
        financials = json.loads(open(FINANCIALS_FILE, encoding="utf-8").read())
        print(f"  财务数据已缓存: {len(financials)} 只")
    else:
        financials = {}
        for i, (tk, name) in enumerate(ALL_LEADERS.items()):
            tool = TOOL_HK if tk.endswith(".HK") else TOOL_ASHARE
            q = (f"{name}({tk}) 2020年中报到2026年中报每个报告期的"
                 f"营业收入、销售毛利率、净资产收益率ROE")
            try:
                sheets = cli.query(tool, q, use_cache=False)
            except Exception:
                continue
            periods: dict[str, dict] = {}
            for sh in sheets:
                for metric, by_col in sheet_to_indexed(sh).items():
                    ms = str(metric)
                    for col, val in by_col.items():
                        cs = str(col)
                        # 解析报告期标签 → (year, quarter)
                        ym = re.search(r"(\d{4})", cs)
                        if not ym:
                            continue
                        y = int(ym.group(1))
                        q_num = (1 if "一季" in cs else
                                 2 if "中报" in cs or "半年" in cs else
                                 3 if "三季" in cs else
                                 4 if "年报" in cs or "年度" in cs else None)
                        if q_num is None:
                            continue
                        pk = f"{y}-{q_num}"
                        v = parse_cn_number(str(val).split("|")[0])
                        if v is None:
                            continue
                        if "营业收入" in ms and "同比" not in ms:
                            periods.setdefault(pk, {})["revenue"] = v
                        elif "毛利率" in ms:
                            periods.setdefault(pk, {})["gm"] = v
                        elif "ROE" in ms or "净资产收益率" in ms:
                            periods.setdefault(pk, {})["roe"] = v
            if periods:
                financials[tk] = periods
            if (i + 1) % 10 == 0:
                print(f"    … 财务 {i + 1}/{len(ALL_LEADERS)}", flush=True)
        json.dump(financials, open(FINANCIALS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
        print(f"  财务拉取完成: {len(financials)}/{len(ALL_LEADERS)}")

    # ---- 2. 历史月末价格 + PE + 市值 ----
    if os.path.exists(PRICES_FILE):
        prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
        print(f"  价格数据已缓存: {len(prices)} 只")
    else:
        prices = {}
        for i, (tk, name) in enumerate(ALL_LEADERS.items()):
            tool = TOOL_HK if tk.endswith(".HK") else TOOL_ASHARE
            q = (f"{name}({tk}) 2021年6月到2026年8月每月末的收盘价和"
                 f"总市值")
            try:
                sheets = cli.query(tool, q, use_cache=False)
            except Exception:
                continue
            monthly: dict[str, float] = {}
            for sh in sheets:
                for metric, by_col in sheet_to_indexed(sh).items():
                    ms = str(metric)
                    if "收盘" not in ms:
                        continue
                    for col, val in by_col.items():
                        v = parse_cn_number(str(val).split("|")[0])
                        dm = re.search(r"(\d{4})[-年]?(\d{1,2})", str(col))
                        if v and dm:
                            y, m = int(dm.group(1)), int(dm.group(2))
                            monthly[f"{y:04d}-{m:02d}"] = v
            if monthly:
                prices[tk] = monthly
            if (i + 1) % 10 == 0:
                print(f"    … 价格 {i + 1}/{len(ALL_LEADERS)}", flush=True)
        json.dump(prices, open(PRICES_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
        print(f"  价格拉取完成: {len(prices)}/{len(ALL_LEADERS)}")

    # ---- 3. 基准（中证全指）----
    if os.path.exists(BENCHMARK_FILE):
        bench = json.loads(open(BENCHMARK_FILE, encoding="utf-8").read())
    else:
        sheets = cli.query(TOOL_INDEX,
                           "中证全指(000985.SH) 2021年6月到2026年8月"
                           "每月末的收盘价", use_cache=False)
        bench = {}
        for sh in sheets:
            for metric, by_col in sheet_to_indexed(sh).items():
                if "收盘" not in str(metric):
                    continue
                for col, val in by_col.items():
                    v = parse_cn_number(str(val).split("|")[0])
                    dm = re.search(r"(\d{4})[-年]?(\d{1,2})", str(col))
                    if v and dm:
                        y, m = int(dm.group(1)), int(dm.group(2))
                        bench[f"{y:04d}-{m:02d}"] = v
        json.dump(bench, open(BENCHMARK_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
        print(f"  基准拉取完成: {len(bench)} 个月")

    return financials, prices, bench


# ===========================================================================
# 点时数据构建 + 模型运行
# ===========================================================================

def _avail_financials(financials: dict, as_of: str) -> dict:
    """过滤到 as_of 日已披露的报告期（近似：年报 4/30、中报 8/31、
    一季报 4/30、三季报 10/31）。返回 {ticker: {period: metrics}}。"""
    out = {}
    d = date.fromisoformat(as_of)
    for tk, periods in financials.items():
        filtered = {}
        for pk, metrics in periods.items():
            parts = pk.split("-")
            if len(parts) != 2:
                continue
            try:
                y, q = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            # 披露截止日
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


def _build_series(tk: str, fin_at_date: dict, link: str | None) -> dict:
    """从点时财务构建模型输入（同 rotation_growth._load_series 的结构）。"""
    periods = fin_at_date.get(tk, {})
    # 同期对齐 YoY（rev 当前 / rev 上年同期）
    rev_by_qp = {}
    for pk, m in periods.items():
        y, q = int(pk[:4]), int(pk[5])
        if "revenue" in m and m["revenue"] != 0:
            rev_by_qp[(y, q)] = m["revenue"]
    rev_yoy = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            rev_yoy.append(v / prev - 1.0)

    gm = []
    roe = None
    for pk in sorted(periods.keys(), reverse=True):
        m = periods[pk]
        if "gm" in m:
            gm.append(m["gm"])
        if roe is None and "roe" in m:
            roe = m["roe"]

    return {
        "rev_yoy": rev_yoy, "gm": gm, "roe": roe,
        "pe": None,  # 从价格文件补充
        "market_cap": None,  # 从价格文件补充
        "name": ALL_LEADERS.get(tk, ""), "sector": "",
        "industry": "", "assigned_link": link,
    }


class BacktestAdapter:
    """离线 DataClient：从缓存的财务+价格数据提供模型输入。"""

    def __init__(self, financials, prices, fin_at_date, month_key):
        self._fin = financials
        self._prices = prices
        self._fin_at = fin_at_date
        self._month = month_key

    def get_prices(self, ticker, start_date, end_date):
        monthly = self._prices.get(ticker, {})
        px = monthly.get(self._month)
        if not px:
            return []
        return [{"time": f"{self._month}-28", "open": px, "high": px,
                 "low": px, "close": px, "volume": 1e6, "amount": 1e8}]

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        periods = self._fin_at.get(ticker, {})
        rows = []
        for pk in sorted(periods.keys(), reverse=True)[:limit]:
            y, q = int(pk[:4]), int(pk[5])
            d = f"{y}-{q * 3:02d}-{30 if q in (1, 3) else 30:02d}"
            if d > end_date:
                continue
            m = periods[pk]
            row = {"ticker": ticker, "date": d, "period": period}
            row.update(m)
            rows.append(row)
        return rows

    def get_company_facts(self, ticker):
        return {"ticker": ticker, "name": ALL_LEADERS.get(ticker, ""),
                "sector": "", "industry": "",
                "link": LEADER_LINK.get(ticker)}

    def get_earnings(self, ticker):
        return None


# ===========================================================================
# 回测主循环
# ===========================================================================

def run_backtest(financials, prices, bench):
    from src.signals.rotation_growth import RotationGrowthModel
    from src.portfolio.balanced_sharpness import BalancedSharpnessBlend
    from src.core.models import Signal

    model = RotationGrowthModel(
        boom_growth=0.40,
        pe_ceiling_by_link={
            "半导体设备": 150, "半导体材料": 100, "CPU+光芯片": 120,
            "国产算力": 200, "存储": 60, "PCB材料": 35,
            "光模块/光通信": 45, "电子制造/封测": 45, "晶圆代工": 100,
        })
    blender = BalancedSharpnessBlend(
        top_direction_weight=0.22, tail_direction_weight=0.12,
        max_directions=8, class_mix={"A": 0.60, "B": 0.35, "C": 0.05},
        per_name_cap=0.05, off_theme_sleeve=0.05,
        max_names_per_direction=6, scale_to_target=True)

    # 月度估值日（调仓日附近的月末）
    months = sorted(bench.keys())
    nav_path = []  # (date, nav, bench_nav)
    portfolio = None  # {ticker: shares}
    cash = CAPITAL
    prev_weights = {}

    for rb_idx, rb_date in enumerate(REBALANCE_DATES + [END_DATE]):
        is_last = rb_idx >= len(REBALANCE_DATES)
        if is_last:
            # 最后只估值，不调仓
            pass
        else:
            # ---- 调仓 ----
            fin_at = _avail_financials(financials, rb_date)
            # 找最近的月末价格
            ym = rb_date[:7]
            month_keys = [m for m in months if m >= ym]
            if not month_keys:
                continue
            mk = month_keys[0]

            adapter = BacktestAdapter(financials, prices, fin_at, mk)
            # 跑模型
            signals = []
            for tk in ALL_LEADERS:
                if tk not in financials or tk not in prices:
                    continue
                if mk not in prices.get(tk, {}):
                    continue
                try:
                    sig = model.predict(tk, rb_date, adapter)
                    signals.append(sig)
                except Exception:
                    continue

            # 组仓
            result = blender.blend(signals, {"rotation_growth": 1.0},
                                   gross_target=1.0)
            weights = {t: w for t, w in result.weights.items() if w > 0}

            # 计算换手和交易成本
            if prev_weights:
                turnover = sum(abs(weights.get(t, 0) - prev_weights.get(t, 0))
                               for t in set(list(weights) + list(prev_weights)))
            else:
                turnover = sum(weights.values())

            # 正确的总权益：现金 + 当前持仓按当月价格估值
            equity = cash
            if portfolio:
                for tk, shares in portfolio.items():
                    px_now = prices.get(tk, {}).get(mk, 0)
                    equity += shares * px_now

            cost = turnover * COST_BPS / 10000 * equity
            prev_weights = weights

            # 清仓重建：从总权益出发分配
            portfolio = {}
            cash = equity - cost
            px = {tk: prices[tk].get(mk) for tk in weights
                  if tk in prices and prices[tk].get(mk)}
            for tk, w in weights.items():
                if tk in px and px[tk] and px[tk] > 0:
                    shares = (w * equity) / px[tk]
                    portfolio[tk] = shares
                    cash -= w * equity

            print(f"\n  [{rb_date}] 调仓: {len(weights)} 持仓, "
                  f"换手 {turnover:.0%}, 成本 ¥{cost:,.0f}", flush=True)
            # 打印方向摘要
            by_link: dict[str, float] = {}
            for tk, w in weights.items():
                link = LEADER_LINK.get(tk) or "自下而上"
                by_link[link] = by_link.get(link, 0) + w
            for link, lw in sorted(by_link.items(), key=lambda x: -x[1]):
                members = sorted(
                    [(tk, w) for tk, w in weights.items()
                     if (LEADER_LINK.get(tk) or "自下而上") == link],
                    key=lambda x: -x[1])[:3]
                top = ", ".join(f"{ALL_LEADERS.get(tk, tk[:6])}({w:.0%})"
                                for tk, w in members)
                print(f"    {link:12s} {lw:5.1%}  {top}", flush=True)

        # ---- 估值（每月） ----
        # 从调仓日到下一调仓日之间的所有月末
        next_rb = (REBALANCE_DATES + [END_DATE])[rb_idx + 1] if not is_last else None
        if not next_rb:
            next_rb = END_DATE

        for mk in months:
            # 只处理调仓日之后、下一调仓日之前的月份
            mk_date = f"{mk}-28"
            if rb_date[:7] > mk or mk >= next_rb[:7]:
                if not (is_last and mk <= END_DATE[:7]):
                    continue

            # 组合净值
            nav = cash
            if portfolio:
                for tk, shares in portfolio.items():
                    px = prices.get(tk, {}).get(mk)
                    if px:
                        nav += shares * px

            # 基准净值
            bench_px = bench.get(mk)
            if bench_px and rb_idx == 0 and not nav_path:
                bench_base = bench_px

            if nav > 0:
                nav_path.append((mk, nav, bench_px))

    return nav_path


# ===========================================================================
# 业绩指标
# ===========================================================================

def compute_stats(nav_path):
    if not nav_path or len(nav_path) < 2:
        return {}
    navs = [n for _, n, _ in nav_path]
    benchs = [b for _, _, b in nav_path if b]
    dates = [d for d, _, _ in nav_path]

    total_ret = navs[-1] / navs[0] - 1
    n_months = len(navs)
    ann_ret = (1 + total_ret) ** (12 / max(n_months, 1)) - 1

    # 回撤
    peak = navs[0]
    max_dd = 0
    for n in navs:
        peak = max(peak, n)
        dd = 1 - n / peak
        max_dd = max(max_dd, dd)

    # 月度收益
    rets = [(navs[i] / navs[i - 1] - 1) for i in range(1, len(navs))
            if navs[i - 1] > 0]
    if len(rets) > 1 and np.std(rets) > 0:
        sharpe = np.mean(rets) / np.std(rets) * np.sqrt(12)
    else:
        sharpe = 0

    # 基准
    if len(benchs) > 1:
        bench_ret = benchs[-1] / benchs[0] - 1
        bench_ann = (1 + bench_ret) ** (12 / max(n_months, 1)) - 1
        bench_peak = benchs[0]
        bench_dd = 0
        for b in benchs:
            bench_peak = max(bench_peak, b)
            bench_dd = max(bench_dd, 1 - b / bench_peak)
    else:
        bench_ret = bench_ann = bench_dd = 0

    return {
        "total_ret": total_ret, "ann_ret": ann_ret, "max_dd": max_dd,
        "sharpe": sharpe, "n_months": n_months,
        "bench_ret": bench_ret, "bench_ann": bench_ann,
        "bench_dd": bench_dd, "excess": total_ret - bench_ret,
        "start": dates[0], "end": dates[-1],
    }


# ===========================================================================
# 主入口
# ===========================================================================

def main():
    print("=" * 76)
    print("  章宏帆轮动策略 · 5 年回测（全A龙头池 · 半年度调仓）")
    print("=" * 76)

    cli = MXMCPClient()
    financials, prices, bench = fetch_all(cli)
    print(f"\n  数据就绪: {len(financials)} 只财务, {len(prices)} 只价格, "
          f"{len(bench)} 个月基准")

    nav_path = run_backtest(financials, prices, bench)

    stats = compute_stats(nav_path)
    print("\n" + "=" * 76)
    print("  回测结果")
    print("=" * 76)
    print(f"  区间: {stats.get('start')} → {stats.get('end')} "
          f"({stats.get('n_months')} 个月)")
    print(f"\n  {'指标':<20s} {'策略':>12s} {'中证全指':>12s}")
    print(f"  {'─' * 46}")
    print(f"  {'累计收益':<18s} {stats['total_ret']:>11.1%} "
          f"{stats['bench_ret']:>11.1%}")
    print(f"  {'年化收益':<18s} {stats['ann_ret']:>11.1%} "
          f"{stats['bench_ann']:>11.1%}")
    print(f"  {'最大回撤':<18s} {stats['max_dd']:>11.1%} "
          f"{stats['bench_dd']:>11.1%}")
    print(f"  {'Sharpe':<20s} {stats['sharpe']:>11.2f}")
    print(f"  {'超额收益':<18s} {stats['excess']:>+11.1%}")
    print(f"\n  ⚠️  环节表为 2026 快照，存在前视偏差；龙头池有幸存者偏差")
    print(f"  结果应解读为方向捕获能力，不是可实现收益")
    print("=" * 76)

    # 保存月度净值
    out = [{"month": m, "nav": n, "bench": b} for m, n, b in nav_path]
    json.dump(out, open("_bt_nav.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    print("月度净值已存 _bt_nav.json")


if __name__ == "__main__":
    main()
