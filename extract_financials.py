# -*- coding: utf-8 -*-
"""
Extract raw PIT financial data from D:\\workspace\\ai_fund_framework.

Sources:
  _bt_pit_financials.json : dict[ticker] -> dict["YYYY-Q"] -> {roe, revenue, gross_margin}
  _bt_pit_prices.json     : dict[ticker] -> dict["YYYY-MM"] -> close price
  _bt_pit_warmup.json     : dict[ticker] -> dict["YYYY-MM"] -> close price
  _bt_pit_selection.json  : dict["YYYY-MM"] -> {as_of, ..., candidates: [[ticker, name, sw1], ...]}
"""
import json
import os
import sys

os.chdir(r"D:\workspace\ai_fund_framework")
sys.path.insert(0, r"D:\workspace\ai_fund_framework")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\workspace\ai_fund_framework"
TARGET = "601127.SH"
PEERS = [
    ("301012.SZ", "扬电科技"),
    ("001309.SZ", "德明利"),
    ("688525.SH", "佰维存储"),
    ("605333.SH", "沪光股份"),
    ("300604.SZ", "长川科技"),
]


def load(name):
    with open(os.path.join(BASE, name), "r", encoding="utf-8") as f:
        return json.load(f)


def fmt_num(v):
    """Format without truncation: thousands separators for big ints, else plain repr."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, int):
            return f"{v:,}"
        return repr(v)
    return str(v)


def sort_key(period):
    y, q = period.split("-")
    return int(y), int(q)


def main():
    fin = load("_bt_pit_financials.json")
    prices = load("_bt_pit_prices.json")
    warmup = load("_bt_pit_warmup.json")
    selection = load("_bt_pit_selection.json")

    # ---------- (a) ALL raw financial rows for 601127.SH ----------
    print("=" * 100)
    print(f"(a) 601127.SH 赛力斯 - 全部财务指标行（按日期升序）")
    print("=" * 100)
    periods = sorted(fin[TARGET].keys(), key=sort_key)
    # union of all field names, so no field is missed
    all_fields = sorted(set().union(*(set(v.keys()) for v in fin[TARGET].values())))
    header = ["period"] + all_fields
    print(f"{'period':<10}" + "".join(f"{f!s:>28}" for f in all_fields))
    print("-" * (10 + 28 * len(all_fields)))
    for p in periods:
        row = fin[TARGET][p]
        print(f"{p:<10}" + "".join(f"{fmt_num(row.get(f)):>28}" for f in all_fields))
    print(f"共 {len(periods)} 期。字段：{all_fields}")

    # ---------- (b) 2024-08 full candidate list ----------
    print()
    print("=" * 100)
    print('(b) 2024-08 调仓月 完整候选列表 (ticker, name, sw1 industry)')
    print("=" * 100)
    m = selection["2024-08"]
    print(f"as_of={m['as_of']}  n_rows={m['n_rows']}  n_industries={m['n_industries']}")
    cands = m["candidates"]
    print(f"候选数量：{len(cands)}")
    print(f"{'#':>3}  {'ticker':<12}{'name':<14}{'sw1 industry'}")
    print("-" * 50)
    for i, (ticker, name, industry) in enumerate(cands, 1):
        print(f"{i:>3}  {ticker:<12}{name:<14}{industry}")

    # ---------- (c) 601127.SH prices + warmup, monthly closes 2023-2024 ----------
    print()
    print("=" * 100)
    print("(c) 601127.SH 赛力斯 - 月度收盘价（prices + warmup 合并），2023 与 2024")
    print("=" * 100)
    merged = {}
    merged.update(warmup.get(TARGET, {}))
    merged.update(prices.get(TARGET, {}))  # prices takes precedence on overlap
    months_2324 = sorted(k for k in merged if k.startswith(("2023-", "2024-")))
    print(f"{'month':<10}{'close':>14}   {'source'}")
    print("-" * 40)
    for k in months_2324:
        src = "prices" if k in prices.get(TARGET, {}) else ("warmup" if k in warmup.get(TARGET, {}) else "both")
        print(f"{k:<10}{merged[k]:>14,.2f}   {src}")
    # expected months in 2023-2024 vs actual, to surface source-data gaps explicitly
    import itertools
    all_2023_2024 = [f"{y}-{mm:02d}" for y in (2023, 2024) for mm in range(1, 13)]
    missing = [k for k in all_2023_2024 if k not in merged]
    print(f"共 {len(months_2324)} 个月份；原始数据缺失：{missing if missing else '无'}")

    # ---------- (d) peer financials: revenue & gross_margin per period ----------
    print()
    print("=" * 100)
    print("(d) 2024-08 调仓其他股票 - 各期 revenue 与 gross_margin")
    print("=" * 100)
    peer_names = dict(PEERS)
    peer_tickers = [t for t, _ in PEERS]
    for t in peer_tickers:
        print(f"\n--- {t} {peer_names[t]} ---")
        if t not in fin:
            print("  (financials 中无此股票数据)")
            continue
        ps = sorted(fin[t].keys(), key=sort_key)
        print(f"{'period':<10}{'revenue':>22}{'gross_margin':>16}")
        print("-" * 50)
        for p in ps:
            row = fin[t][p]
            rev = row.get("revenue")
            gm = row.get("gross_margin")
            rev_s = fmt_num(rev) if rev is not None else "(缺失)"
            gm_s = fmt_num(gm) if gm is not None else "(缺失)"
            print(f"{p:<10}{rev_s:>22}{gm_s:>16}")
        print(f"共 {len(ps)} 期")


if __name__ == "__main__":
    main()
