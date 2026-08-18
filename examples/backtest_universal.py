"""通用行业轮动回测 — vnpy 式引擎版（章宏帆方法论）。

架构（参照 vnpy_portfoliostrategy）：
  BacktestingEngine（src/backtest/engine.py）
    月度 union-of-dates 主循环；cross_limit_order() → on_bars() →
    update_daily_close()；N 月末下单 → N+1 月撮合（无前视）；
    PortfolioDailyResult mark-to-market；vnpy 统计公式（×12 月频年化）。
  RotationStrategy（src/backtest/strategy.py）
    调仓月（披露截止日月末：4/30、8/31）执行：
    ① 点时财务过滤 → ② 动态行业稀缺度表（每期重建，通用轮动：
       2021 轮到新能源而非锚死 AI 链）→ ③ 模型打分 → ④ blend 组仓
    → ⑤ 权重×权益 → 目标股数 → rebalance_portfolio

Universe   = ~76 只跨行业龙头（新能源/CXO/军工/有色/消费/AI 链）
成本       = 佣金 5bp + 滑点 10bp（单边，计入成交价）
基准       = 中证全指（000985.SH）月频

诚实标注：
  - 龙头池有幸存者偏差（2026 年知道的龙头 ≠ 当年的龙头）
  - PE/市值未入回测（B 类 PE 上限与 G5 分解不触发）
  - 行业 S 分由成分股基本面代理（S1 广度/S2 水平/S3 毛利率/
    S4 加速度），非供应链审计

Run:
    python examples/backtest_universal.py [--fetch-missing]
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.backtest.engine import BacktestingEngine, BarData
from src.backtest.strategy import RotationStrategy
from src.data.mx_data_client import parse_cn_number, sheet_to_indexed
from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE, TOOL_INDEX

CAPITAL = 1_000_000
RATE = 0.0005          # 佣金 5bp
SLIPPAGE = 0.001       # 滑点 10bp（单边，入价）

FINANCIALS_FILE = "_bt_uni_financials.json"
PRICES_FILE = "_bt_uni_prices.json"
BENCHMARK_FILE = "_bt_benchmark.json"
NAV_FILE = "_bt_uni_nav.json"

# 披露截止日（调仓时点 = 该日月末 bar）
REBALANCE_AS_OF = [
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

# ===========================================================================
# 跨行业龙头 universe（76 只，覆盖 2021-2026 各阶段高增长行业）
# ===========================================================================

UNIVERSE: list[tuple[str, str, str]] = [
    # ---- 新能源（2021 主线）----
    ("300750.SZ", "宁德时代", "动力电池"),
    ("601012.SH", "隆基绿能", "光伏"),
    ("300274.SZ", "阳光电源", "光伏逆变器"),
    ("002460.SZ", "赣锋锂业", "锂资源"),
    ("002466.SZ", "天齐锂业", "锂资源"),
    ("600516.SH", "方大炭素", "碳材料"),
    ("688599.SH", "天合光能", "光伏组件"),
    ("688223.SH", "晶科能源", "光伏组件"),
    ("002594.SZ", "比亚迪", "新能源车"),
    ("601127.SH", "赛力斯", "新能源车"),
    ("300014.SZ", "亿纬锂能", "消费电池"),
    ("002812.SZ", "恩捷股份", "锂电隔膜"),
    ("603659.SH", "璞泰来", "锂电负极"),
    ("002340.SZ", "格林美", "电池回收"),
    # ---- CRO / 医药（2021 景气）----
    ("603259.SH", "药明康德", "CRO"),
    ("002821.SZ", "凯莱英", "CRO"),
    ("300122.SZ", "智飞生物", "疫苗"),
    ("603087.SH", "甘李药业", "胰岛素"),
    ("600276.SH", "恒瑞医药", "创新药"),
    ("000538.SZ", "云南白药", "中药"),
    # ---- 消费（2021 核心）----
    ("600519.SH", "贵州茅台", "白酒"),
    ("000858.SZ", "五粮液", "白酒"),
    ("000568.SZ", "泸州老窖", "白酒"),
    ("600809.SH", "山西汾酒", "白酒"),
    ("603288.SH", "海天味业", "调味品"),
    ("600887.SH", "伊利股份", "乳制品"),
    # ---- 军工（2021-2022 景气）----
    ("600893.SH", "航发动力", "航空发动机"),
    ("601989.SH", "中国重工", "船舶"),
    ("002179.SZ", "中航光电", "军工连接器"),
    ("600760.SH", "中航沈飞", "战斗机"),
    # ---- 有色/资源（2021-2022 周期）----
    ("603799.SH", "华友钴业", "钴资源"),
    ("603993.SH", "洛阳钼业", "钼资源"),
    ("600362.SH", "江西铜业", "铜"),
    ("601899.SH", "紫金矿业", "金铜"),
    ("600111.SH", "北方稀土", "稀土"),
    # ---- AI / 半导体（2023-2026 主线）----
    ("300308.SZ", "中际旭创", "光模块"),
    ("300502.SZ", "新易盛", "光模块"),
    ("300394.SZ", "天孚通信", "光模块"),
    ("688256.SH", "寒武纪", "AI芯片"),
    ("688041.SH", "海光信息", "CPU"),
    ("603986.SH", "兆易创新", "存储"),
    ("301308.SZ", "江波龙", "存储模组"),
    ("688525.SH", "佰维存储", "存储模组"),
    ("002371.SZ", "北方华创", "半导体设备"),
    ("688012.SH", "中微公司", "半导体设备"),
    ("688082.SH", "盛美上海", "半导体设备"),
    ("688120.SH", "华海清科", "半导体设备"),
    ("600183.SH", "生益科技", "覆铜板"),
    ("688183.SH", "生益电子", "PCB"),
    ("002463.SZ", "沪电股份", "PCB"),
    ("300661.SZ", "圣邦股份", "模拟芯片"),
    ("002049.SZ", "紫光国微", "特种芯片"),
    ("688981.SH", "中芯国际", "晶圆代工"),
    ("688126.SH", "沪硅产业", "硅片"),
    ("688146.SH", "中船特气", "电子特气"),
    ("688019.SH", "安集科技", "CMP材料"),
    ("300054.SZ", "鼎龙股份", "半导体材料"),
    ("002475.SZ", "立讯精密", "消费电子"),
    ("601231.SH", "环旭电子", "SiP封装"),
    ("002138.SZ", "顺络电子", "被动元件"),
    ("300408.SZ", "三环集团", "被动元件"),
    ("688372.SH", "伟测科技", "芯片测试"),
    # ---- 通信/算力基础设施 ----
    ("301165.SZ", "锐捷网络", "网络设备"),
    ("300620.SZ", "光库科技", "光纤器件"),
    ("688313.SH", "仕佳光子", "光芯片"),
    # ---- 高端制造 ----
    ("688006.SH", "杭可科技", "锂电设备"),
    ("300450.SZ", "先导智能", "锂电设备"),
    ("601615.SH", "东方雨虹", "防水材料"),
    ("600584.SH", "长电科技", "封测"),
    ("002156.SZ", "通富微电", "封测"),
    # ---- 计算机/软件 ----
    ("688111.SH", "金山办公", "办公软件"),
    ("002415.SH", "海康威视", "安防"),
    ("688002.SH", "睿创微纳", "红外"),
    # ---- 化工/材料 ----
    ("002741.SZ", "光华科技", "PCB化学品"),
    ("300285.SZ", "国瓷材料", "电子陶瓷"),
    ("688396.SH", "华润微", "功率半导体"),
]
_seen: set = set()
UNIVERSE = [(t, n, i) for t, n, i in UNIVERSE
            if t not in _seen and not _seen.add(t)]


# ===========================================================================
# 数据
# ===========================================================================

def load_data() -> tuple[dict, dict, dict]:
    financials = json.loads(open(FINANCIALS_FILE, encoding="utf-8").read())
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())
    bench = json.loads(open(BENCHMARK_FILE, encoding="utf-8").read())
    # 旧缓存字段名 gm → 模型读 gross_margin（修复旧回测静默丢毛利率的 bug）
    for periods in financials.values():
        for m in periods.values():
            if "gm" in m and "gross_margin" not in m:
                m["gross_margin"] = m.pop("gm")
    return financials, prices, bench


def fetch_missing_prices(prices: dict, bench: dict) -> None:
    """补拉 2025-12 之后的月度价格（旧任务中断的缺口）。"""
    from dotenv import load_dotenv as _l
    _l()
    cli = MXMCPClient()
    months_have = set()
    for m in prices.values():
        months_have.update(m.keys())
    last = max(months_have)
    y0, m0 = int(last[:4]), int(last[5:7])
    missing_months = []
    y, m = y0, m0 + 1
    while (y, m) <= (2026, 8):
        missing_months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    if not missing_months:
        print("  价格无缺口")
        return
    lo, hi = missing_months[0], missing_months[-1]
    print(f"  补拉 {lo} → {hi}（{len(missing_months)} 个月）")
    lo_cn = f"{lo[:4]}年{int(lo[5:7])}月"
    hi_cn = f"{hi[:4]}年{int(hi[5:7])}月"
    for i, (tk, name, _) in enumerate(UNIVERSE):
        if tk not in prices:
            continue
        q = f"{name}({tk}) {lo_cn}到{hi_cn}每月末的收盘价"
        try:
            sheets = cli.query(TOOL_ASHARE, q, use_cache=False)
        except Exception as e:
            print(f"    {tk} 拉取失败: {e}")
            continue
        for sh in sheets:
            for metric, by_col in sheet_to_indexed(sh).items():
                if "收盘" not in str(metric):
                    continue
                for col, val in by_col.items():
                    v = parse_cn_number(str(val).split("|")[0])
                    dm = re.search(r"(\d{4})[-年]?(\d{1,2})", str(col))
                    if v and dm:
                        y_, m_ = int(dm.group(1)), int(dm.group(2))
                        prices[tk][f"{y_:04d}-{m_:02d}"] = v
        if (i + 1) % 20 == 0:
            print(f"    … {i + 1}/{len(UNIVERSE)}", flush=True)
    json.dump(prices, open(PRICES_FILE, "w", encoding="utf-8"))
    # 基准补拉
    bench_last = max(bench.keys())
    if bench_last < hi:
        sheets = cli.query(TOOL_INDEX,
                           f"中证全指(000985.SH) {bench_last[:4]}年"
                           f"{int(bench_last[5:7])}月到{hi_cn}每月末的收盘价",
                           use_cache=False)
        for sh in sheets:
            for metric, by_col in sheet_to_indexed(sh).items():
                if "收盘" not in str(metric):
                    continue
                for col, val in by_col.items():
                    v = parse_cn_number(str(val).split("|")[0])
                    dm = re.search(r"(\d{4})[-年]?(\d{1,2})", str(col))
                    if v and dm:
                        y_, m_ = int(dm.group(1)), int(dm.group(2))
                        bench[f"{y_:04d}-{m_:02d}"] = v
        json.dump(bench, open(BENCHMARK_FILE, "w", encoding="utf-8"))
        print("  基准补拉完成")


# ===========================================================================
# 主流程
# ===========================================================================

def build_bars(prices: dict, universe: list[tuple[str, str, str]]):
    bars: dict[str, dict[str, BarData]] = {}
    for tk, _n, _l in universe:
        series = prices.get(tk)
        if not series:
            continue
        bars[tk] = {
            mk: BarData(tk, mk, px, px, px, px)
            for mk, px in series.items() if px and px > 0
        }
    return bars


def main(fetch_missing: bool = False):
    print("=" * 78)
    print("  章宏帆轮动 · 通用行业回测（vnpy 式引擎，月频，半年度调仓）")
    print("=" * 78)

    financials, prices, bench = load_data()
    if fetch_missing:
        print("\n① 补拉数据缺口…")
        fetch_missing_prices(prices, bench)

    bars = build_bars(prices, UNIVERSE)
    symbols = list(bars.keys())
    dt_all = sorted({mk for s in bars.values() for mk in s})
    print(f"\n① 数据: {len(financials)} 只财务 | {len(symbols)} 只价格 | "
          f"{dt_all[0]} → {dt_all[-1]}")

    # 调仓月 = 披露截止日所在月（有行情才调）
    rb_map = {}   # month → as_of
    for as_of in REBALANCE_AS_OF:
        mk = as_of[:7]
        if mk in dt_all:
            rb_map[mk] = as_of
    print(f"   调仓月: {', '.join(sorted(rb_map))}")

    # ---- 引擎与策略 ----
    engine = BacktestingEngine()
    engine.set_parameters(symbols=symbols, capital=CAPITAL,
                          rate=RATE, slippage=SLIPPAGE,
                          annual_periods=12, risk_free=0.02)
    engine.add_data(bars)
    strategy = RotationStrategy(engine, {
        "financials": financials,
        "universe": UNIVERSE,
        "rebalance_dts": set(rb_map.keys()),
        "disclosure_of": rb_map,
    })
    engine.add_strategy(strategy)

    print("\n② 回测运行…")
    engine.run_backtesting()

    print("\n③ 结算与统计…")
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(daily)

    # ---- 基准对比 ----
    print("\n④ 基准对比（中证全指）")
    nav_rows = []
    b0 = None
    n0 = None
    for row in daily:
        mk = row["dt"]
        if mk not in bench or not bench[mk]:
            continue
        if n0 is None:
            n0, b0 = row["balance"], bench[mk]
        nav_rows.append({
            "month": mk,
            "nav": row["balance"],
            "bench": bench[mk],
            "strategy_ret": row["balance"] / n0 - 1,
            "bench_ret": bench[mk] / b0 - 1,
        })
    if nav_rows:
        last = nav_rows[-1]
        from src.backtest.engine import _month_span
        yrs = _month_span(nav_rows[0]["month"], last["month"]) / 12
        print(f"   期末策略: {last['strategy_ret']:+.1%}  |  "
              f"基准: {last['bench_ret']:+.1%}  |  "
              f"超额: {last['strategy_ret'] - last['bench_ret']:+.1%}")
        print(f"   策略年化 {(1 + last['strategy_ret']) ** (1 / yrs) - 1:+.1%}"
              f"  vs 基准 {(1 + last['bench_ret']) ** (1 / yrs) - 1:+.1%}"
              f"  （{yrs:.1f} 年）")
    json.dump(nav_rows, open(NAV_FILE, "w", encoding="utf-8"))

    # ---- 调仓历史与归因 ----
    print("\n⑤ 调仓历史")
    label_names = {tk: n for tk, n, _ in UNIVERSE}
    for h in strategy.history:
        top = ", ".join(f"{lab} {w:.0%}"
                        for lab, w in sorted(h["by_label"].items(),
                                             key=lambda x: -x[1])[:5])
        print(f"   [{h['dt']}] {h['n_hold']} 只持仓 | {top}")

    # 逐期收益（调仓到调仓；持仓自下一期生效）
    print("\n⑥ 分期收益（持仓生效期，含基准对比）")
    bal = {r["dt"]: r["balance"] for r in daily}
    ordered_dts = sorted(bal.keys())
    hist_dts = [h["dt"] for h in strategy.history]
    for i, h in enumerate(strategy.history):
        mk = h["dt"]
        if mk not in ordered_dts:
            continue
        j = ordered_dts.index(mk)
        next_rb = hist_dts[i + 1] if i + 1 < len(hist_dts) else None
        end_mk = next_rb if next_rb in bal else ordered_dts[-1]
        base_mk = ordered_dts[j]          # 下单月（本期收盘）
        if end_mk not in bal or end_mk <= base_mk:
            continue
        ret = bal[end_mk] / bal[base_mk] - 1
        b_ret = ""
        if base_mk in bench and end_mk in bench \
                and bench[base_mk] and bench[end_mk]:
            b_ret = f" | 基准 {bench[end_mk] / bench[base_mk] - 1:+.1%}"
        print(f"   {h['dt']} → {end_mk}: {ret:+.1%}{b_ret} "
              f"({h['n_hold']} 只)")

    # 持仓明细（最后一期）
    if strategy.history:
        h = strategy.history[-1]
        print(f"\n⑦ 最后一期持仓（{h['dt']}）")
        for tk, w in sorted(h["weights"].items(),
                            key=lambda x: -x[1])[:20]:
            print(f"   {tk} {label_names.get(tk, ''):8s} {w:.1%}")

    print("\n完成。NAV 路径 →", NAV_FILE)


if __name__ == "__main__":
    main(fetch_missing="--fetch-missing" in sys.argv)
