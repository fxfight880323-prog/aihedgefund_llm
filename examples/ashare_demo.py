"""A-share demo — run the value fund on real 妙想 (MX) data.

This is the China-equivalent of examples/quickstart.py. It runs one full
fund cycle over a small A-share universe using the 妙想 MCP data client
(MXDataClient) and the pure-quant `ashare_value` model — no LLM key needed.

Prerequisites:
  - pip install -e .   (or have src/ on the path, as below)
  - EM_API_KEY set in the environment or a .env file
    (the 妙想 key from the East Money 妙想 platform)

Run:
    python examples/ashare_demo.py
"""

from __future__ import annotations

import os
import sys

# Make the project importable when run from source without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.mx_data_client import MXDataClient
from src.workflow.runner import run_fund_cycle


# A small, liquid, sector-diverse A-share universe for the demo.
UNIVERSE = [
    "600519.SH",  # 贵州茅台  — 食品饮料 (白酒)
    "300750.SZ",  # 宁德时代  — 电力设备 (动力电池)
    "000858.SZ",  # 五粮液    — 食品饮料 (白酒)
    "601318.SH",  # 中国平安  — 非银金融 (保险)
    "000001.SZ",  # 平安银行  — 银行
    "600036.SH",  # 招商银行  — 银行
    "000333.SZ",  # 美的集团  — 家用电器
    "600276.SH",  # 恒瑞医药  — 医药生物
]

MANDATE = "config/funds/ashare_demo.yaml"
AS_OF = "2026-08-13"


def main():
    # MXDataClient uses a hardcoded fallback 妙想 key, so this runs with no
    # environment setup. Set EM_API_KEY only to override the default.
    data_client = MXDataClient()

    print("=" * 72)
    print("  A股价值基金 Demo  (妙想 MCP 实时数据 · ashare_value 量化模型)")
    print("=" * 72)
    print(f"  Universe: {', '.join(UNIVERSE)}")
    print(f"  As of:    {AS_OF}")
    print(f"  Mandate:  {MANDATE}")
    print()

    record = run_fund_cycle(
        mandate_path=MANDATE,
        tickers=UNIVERSE,
        as_of=AS_OF,
        data_client=data_client,
    )

    print_cycle(record)


def print_cycle(record):
    """Pretty-print the cycle: signals → weights → orders → book."""
    print("=" * 72)
    print(f"  {record.fund_name}")
    print(f"  As of: {record.as_of}    Capital: ¥{record.equity_before:,.0f}")
    print("=" * 72)

    # ---- Signals ----
    print("\n  分析师信号 (ashare_value):")
    print("-" * 72)
    for sig in sorted(record.signals, key=lambda s: -s.value):
        bar_len = int(abs(sig.value) * 20)
        bar = ("█" * bar_len).ljust(20)
        sign = "+" if sig.value >= 0 else "-"
        print(f"  {sig.ticker:11s} [{sign}{bar}] {sig.value:+.3f}")
        c = sig.components or {}
        print(f"  {'':11s}  质量={c.get('quality', 0):+.2f} "
              f"估值={c.get('valuation', 0):+.2f} "
              f"成长={c.get('growth', 0):+.2f}  "
              f"| PE={sig.metadata.get('pe_ratio')} "
              f"PB={sig.metadata.get('pb_ratio')} "
              f"ROE={sig.metadata.get('roe')}")
        if sig.reasoning:
            print(f"  {'':11s}  └─ {sig.reasoning}")

    skipped = record.metadata.get("skipped", [])
    if skipped:
        print(f"\n  跳过 (无数据): {skipped}")

    # ---- Weights ----
    print("\n  目标权重 vs 风控后权重:")
    print("-" * 72)
    tickers = sorted(set(record.target_weights) | set(record.final_weights))
    for tk in tickers:
        target = record.target_weights.get(tk, 0)
        final = record.final_weights.get(tk, 0)
        flag = "  (触限)" if target != final else ""
        print(f"  {tk:11s}  目标: {target:+.2%}   最终: {final:+.2%}{flag}")

    # ---- Orders ----
    if record.orders:
        print("\n  交易指令:")
        print("-" * 72)
        for o in record.orders:
            print(f"  {o.side.value.upper():4s} {o.shares:>12.0f} 股 "
                  f"{o.ticker:11s} @ ¥{o.limit_price:<10.2f} ({o.reasoning})")

    # ---- Final book ----
    print("\n  持仓与净值:")
    print("-" * 72)
    for tk, shares in sorted(record.positions.items()):
        price = record.marks.get(tk, 0) or 0
        value = shares * price
        print(f"  {tk:11s}  {shares:>12.0f} 股 @ ¥{price:<10.2f} = ¥{value:>16,.0f}")
    print(f"\n  现金:   ¥{record.cash:>16,.0f}")
    print(f"  净值:   ¥{record.nav:>16,.0f}")

    errors = record.metadata.get("errors", [])
    if errors:
        print(f"\n  错误: {errors}")

    print("\n" + "=" * 72)
    print("  周期完成")
    print("=" * 72)


if __name__ == "__main__":
    main()
