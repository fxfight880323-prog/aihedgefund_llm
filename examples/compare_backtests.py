"""点时（无幸存者偏差）vs 龙头池（幸存者偏差）回测对比。"""

from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import _month_span

CAPITAL = 1_000_000


def load(path):
    rows = json.loads(open(path, encoding="utf-8").read())
    return {r["month"]: r["nav"] for r in rows}


def stats(nav: dict, label: str):
    dts = sorted(nav.keys())
    end = nav[dts[-1]]
    total = end / CAPITAL - 1
    yrs = _month_span(dts[0], dts[-1]) / 12
    rets = [math.log(nav[dts[i]] / nav[dts[i - 1]])
            for i in range(1, len(dts))]
    mean = sum(rets) / len(rets)
    std = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    sharpe = (mean - 0.02 / math.sqrt(12)) / std * math.sqrt(12) \
        if std > 0 else 0.0
    high, mdd = nav[dts[0]], 0.0
    for mk in dts:
        high = max(high, nav[mk])
        mdd = min(mdd, nav[mk] / high - 1)
    print(f"\n  [{label}] {dts[0]} → {dts[-1]}")
    print(f"    总收益 {total:+.1%} | 年化 {(1 + total) ** (1 / yrs) - 1:+.1%}"
          f" | 夏普 {sharpe:.2f} | 最大回撤 {mdd:.1%}")
    return nav


def main():
    bench = json.loads(open("_bt_benchmark.json", encoding="utf-8").read())
    uni = load("_bt_uni_nav.json")
    pit = load("_bt_pit_nav.json")
    print("=" * 70)
    print("  回测对比：点时选择（无幸存者偏差+BSADF）vs 龙头池")
    print("=" * 70)
    stats(uni, "龙头池（幸存者偏差版，backtest_universal）")
    stats(pit, "点时选择（无幸存者偏差 + BSADF 卖出，backtest_pit）")
    b_end = [m for m in sorted(bench) if m in uni]
    if b_end:
        b0, b1 = b_end[0], b_end[-1]
        br = bench[b1] / bench[b0] - 1
        yrs = _month_span(b0, b1) / 12
        print(f"\n  [基准 中证全指] 总收益 {br:+.1%} | "
              f"年化 {(1 + br) ** (1 / yrs) - 1:+.1%}")

    # 共同月份逐期对比
    common = sorted(set(uni) & set(pit))
    print(f"\n  逐半年收益对比（共同月份 {common[0]} → {common[-1]}）：")
    marks = [m for m in common if m.endswith(("04", "08", "12"))]
    prev = common[0]
    for mk in marks + [common[-1]]:
        if mk == prev:
            continue
        ru = uni.get(mk, uni[prev]) / uni[prev] - 1
        rp = pit.get(mk, pit[prev]) / pit[prev] - 1
        rb = (bench[mk] / bench[prev] - 1
              if bench.get(mk) and bench.get(prev) else float("nan"))
        print(f"    {prev} → {mk}: 龙头池 {ru:+6.1%} | 点时 {rp:+6.1%} | "
              f"基准 {rb:+6.1%}")
        prev = mk


if __name__ == "__main__":
    main()
