"""拉取章宏帆龙头池一致预期 PIT 快照（10 调仓期）→ _bt_zhf_consensus.json。

复用 fetch_consensus.py 的 JuziHTTP 客户端；as_of 与 rotation 回测日历一致
（年报/中报披露截止日 4-30 / 8-31）。
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

OUT = "_bt_zhf_consensus.json"

PIT = [
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


def leader_tickers() -> list[str]:
    from examples.alla_rotation import LEADER_SEEDS
    tks: list[str] = []
    seen = set()
    for link, seeds in LEADER_SEEDS.items():
        if link.startswith("_"):
            continue
        for _name, tk in seeds.items():
            if tk not in seen:
                seen.add(tk)
                tks.append(tk)
    return sorted(tks)


def main():
    url, token = load_creds()
    cli = JuziHTTP(url, token)
    print("connected to juzi-mcp")

    tickers = leader_tickers()
    print(f"龙头池 {len(tickers)} 只: {tickers[:8]} ...")

    cache: dict = {}
    if os.path.exists(OUT):
        cache = json.loads(open(OUT, encoding="utf-8").read())
        print(f"  已缓存 {len(cache)} 期")

    for month, as_of in PIT:
        if month in cache and cache[month].get("records"):
            print(f"  [{month}] 已缓存 ({len(cache[month]['records'])} 条)")
            continue
        print(f"  [{month}] 拉取 {len(tickers)} 只 @ {as_of} ...", flush=True)
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_consensus_forecast", {
                    "stock_codes": tickers,
                    "as_of_date": as_of,
                    "format": "inline",
                })
                records = out.get("records", [])
                if records:
                    cache[month] = {
                        "as_of": as_of,
                        "snapshot_date": out.get("snapshot_date"),
                        "records": records,
                    }
                    json.dump(cache, open(OUT, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                    print(f"    → {len(records)} 条 (snapshot {out.get('snapshot_date')})")
                    break
                print(f"    尝试 {attempt+1}: 0 条，重试...", flush=True)
                time.sleep(5)
            except Exception as e:
                print(f"    尝试 {attempt+1} 失败: {e}", flush=True)
                time.sleep(8)
        time.sleep(2)

    print(f"\n完成: {len(cache)} 期 → {OUT}")


if __name__ == "__main__":
    main()
