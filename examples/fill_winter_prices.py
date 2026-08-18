"""补齐月度价格的冬季缺口（每年 12 月-次年 5 月）。

旧拉取的"X年6月到Y年8月"查询被 MX 解析为每年 6-11 月，缺每年
12 月-次年 5 月。本脚本用两冬合一的枚举查询补齐：
  A 查询: 2021年12月-2022年5月 + 2022年12月-2023年5月
  B 查询: 2023年12月-2024年5月 + 2024年12月-2025年5月
解析规则：只收列名含 "(月)" 的月末值，"(日)" 列跳过（防止日频
值覆盖月末值）。

Run:
    python examples/fill_winter_prices.py
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".env"))

from src.data.mx_data_client import parse_cn_number, sheet_to_indexed
from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE, TOOL_INDEX

PRICES_FILE = "_bt_uni_prices.json"
BENCHMARK_FILE = "_bt_benchmark.json"

QUERY_PAIRS = [
    ("2021年12月至2022年5月", "2022年12月至2023年5月"),
    ("2023年12月至2024年5月", "2024年12月至2025年5月"),
]

from examples.backtest_universal import UNIVERSE


def parse_monthly(sheets) -> dict[str, float]:
    out: dict[str, float] = {}
    for sh in sheets:
        for metric, by_col in sheet_to_indexed(sh).items():
            if "收盘" not in str(metric):
                continue
            for col, val in by_col.items():
                cs = str(col)
                if "(日)" in cs:
                    continue          # 日频列 → 跳过
                v = parse_cn_number(str(val).split("|")[0])
                dm = re.search(r"(\d{4})[-年]?(\d{1,2})", cs)
                if v and dm:
                    y, m = int(dm.group(1)), int(dm.group(2))
                    out[f"{y:04d}-{m:02d}"] = v
    return out


def main():
    cli = MXMCPClient()
    prices = json.loads(open(PRICES_FILE, encoding="utf-8").read())

    # 目标缺口：每年 12 月-次年 5 月
    need = set()
    for y in range(2021, 2026):
        need.add(f"{y}-12")
        for m in range(1, 6):
            need.add(f"{y + 1}-{m:02d}")
    # 只补已有股票
    symbols = [tk for tk, _, _ in UNIVERSE if tk in prices]

    added_total = 0
    for qi, (w1, w2) in enumerate(QUERY_PAIRS):
        print(f"\n查询组 {qi + 1}/{len(QUERY_PAIRS)}: {w1} + {w2}")
        for i, tk in enumerate(symbols):
            name = next(n for t, n, _ in UNIVERSE if t == tk)
            q = (f"{name}({tk}) {w1}各月末的收盘价，"
                 f"以及{w2}各月末的收盘价")
            try:
                sheets = cli.query(TOOL_ASHARE, q, use_cache=False)
            except Exception as e:
                print(f"    {tk} 失败: {e}")
                continue
            got = parse_monthly(sheets)
            added = 0
            for mk, v in got.items():
                if mk in need and mk not in prices.get(tk, {}):
                    prices.setdefault(tk, {})[mk] = v
                    added += 1
            added_total += added
            if (i + 1) % 20 == 0:
                print(f"    … {i + 1}/{len(symbols)}", flush=True)
        json.dump(prices, open(PRICES_FILE, "w", encoding="utf-8"))
        print(f"  组 {qi + 1} 完成（累计新增 {added_total} 个月度点）")

    # 基准同样补冬季
    bench = json.loads(open(BENCHMARK_FILE, encoding="utf-8").read())
    bench_need = {mk for mk in need if mk <= max(bench.keys())} - set(bench)
    if bench_need:
        print(f"\n基准补拉: {sorted(bench_need)}")
        for w1, w2 in QUERY_PAIRS:
            q = (f"中证全指(000985.SH) {w1}各月末的收盘价，"
                 f"以及{w2}各月末的收盘价")
            try:
                sheets = cli.query(TOOL_INDEX, q, use_cache=False)
                got = parse_monthly(sheets)
                for mk, v in got.items():
                    if mk not in bench:
                        bench[mk] = v
            except Exception as e:
                print(f"  基准失败: {e}")
        json.dump(bench, open(BENCHMARK_FILE, "w", encoding="utf-8"))

    # 覆盖检查
    all_m = sorted({m for s in prices.values() for m in s})
    print(f"\n价格月份覆盖: {all_m[0]} → {all_m[-1]}，共 {len(all_m)} 个月")
    holes = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13)
             if "2021-06" <= f"{y}-{m:02d}" <= "2026-08"
             and f"{y}-{m:02d}" not in all_m]
    print(f"剩余缺口: {holes}")


if __name__ == "__main__":
    main()
