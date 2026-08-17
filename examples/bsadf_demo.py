"""BSADF bubble-timing demo — run the BSADF + confluence fund on real 妙想 data.

Sister script to examples/ashare_demo.py. Runs one full fund cycle over a
small A-share universe using MXDataClient, with the `bsadf` (Phillips-Shi-Yu
bubble/fear detector) and `tech_confluence` (mechanical exit-timing) models.
No LLM key needed — both models are pure-quant.

Prerequisites:
  - pip install -e .   (or have src/ on the path, as below)
  - EM_API_KEY set in the environment or a .env file
    (the 妙想 key from the East Money 妙想 platform). A hardcoded fallback
    key ships with MXMCPClient, so this usually runs with no setup.

Run:
    python examples/bsadf_demo.py
"""

from __future__ import annotations

import os
import sys

# Make the project importable when run from source without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.mx_data_client import MXDataClient
from src.signals.bsadf import BSADFModel
from src.workflow.runner import run_fund_cycle


# A small universe of A-share growth/semiconductor names — the same tickers
# the standalone BSADF project backtested (data/stocks/*), so the framework's
# signals should match the standalone output/stocks/*.csv backtests.
UNIVERSE = [
    "688012.SH",  # 中微公司
    "688256.SH",  # 寒武纪
    "688041.SH",  # 海光信息
    "688981.SH",  # 中芯国际
    "300308.SZ",  # 中际旭创
    "300502.SZ",  # 新易盛
    "002371.SZ",  # 北方华创
    "601138.SH",  # 工业富联
]

MANDATE = "config/funds/bsadf_demo.yaml"
AS_OF = "2026-08-13"


def main():
    data_client = MXDataClient()

    print("=" * 72)
    print("  BSADF 泡沫择时 Demo  (妙想 MCP 实时数据 · bsadf + tech_confluence)")
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

    # ---- Signals, grouped by ticker ----
    print("\n  分析师信号 (bsadf + tech_confluence):")
    print("-" * 72)
    # Reorder: bsadf first, then tech_confluence, per ticker.
    by_ticker = {}
    for sig in record.signals:
        by_ticker.setdefault(sig.ticker, []).append(sig)
    for tk in sorted(by_ticker):
        for sig in by_ticker[tk]:
            bar_len = int(abs(sig.value) * 20)
            bar = ("█" * bar_len).ljust(20)
            sign = "+" if sig.value >= 0 else "-"
            print(f"  {sig.model_name:15s} {tk:11s} [{sign}{bar}] {sig.value:+.3f}")
            c = sig.components or {}
            if sig.model_name == "bsadf":
                print(f"  {'':15s}  BSADF={c.get('bsadf', 0):+.2f} "
                      f"CV95={c.get('cv_bubble', 0):.2f} "
                      f"CV90={c.get('cv_burst', 0):.2f} "
                      f"phase={sig.metadata.get('phase_name')} "
                      f"pos={c.get('pos', 0):.0%}")
            else:
                print(f"  {'':15s}  共振分={c.get('score', 0):.1f} "
                      f"(S1={c.get('s1_macd_div')} "
                      f"S2={c.get('s2_rsi_ob')} "
                      f"S3={c.get('s3_vol_div')} "
                      f"S4={c.get('s4_chandelier')} "
                      f"S5={c.get('s5_macd_x')})")
            if sig.reasoning:
                print(f"  {'':15s}  └─ {sig.reasoning}")

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

    print("\n" + "=" * 72)
    print("  周期完成")
    print("=" * 72)


def demo_standalone():
    """Quick standalone check — run BSADFModel on one ticker without the graph.

    Useful for verifying the port against the standalone backtest output
    (output/stocks/*.csv) before running the full fund cycle.
    """
    data_client = MXDataClient()
    model = BSADFModel(window=160, n_sim=500)  # smaller n_sim for speed
    ticker = "688012.SH"
    signal = model.predict(ticker, AS_OF, data_client)
    print(f"\n  [standalone] {ticker} @ {AS_OF}")
    print(f"  value={signal.value:+.3f}  reasoning={signal.reasoning}")
    print(f"  components={signal.components}")
    print(f"  metadata={signal.metadata}")


if __name__ == "__main__":
    # Run the standalone single-ticker check first (fast, no broker needed).
    demo_standalone()
    # Then the full fund cycle.
    main()
