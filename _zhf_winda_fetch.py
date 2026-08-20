"""万得全A(881001.WI) 全市场回测 — 数据拉取：PIT 成分 + PIT 一致预期。

- Universe: factor_get_universe_members('881001.WI', as_of) → members（含 in/out 日期）
- Consensus: factor_get_consensus_forecast(universe='881001.WI', as_of, format=parquet)
  → artifact.download_url → pandas 读 parquet（inline 被截断 500 行，全量走 parquet）
- 基准: 中证全指 000985.SH（腾讯月K）+ 等权全A NAV

用法:
  python _zhf_winda_fetch.py --test   # 只拉第一期
  python _zhf_winda_fetch.py          # 全 10 期
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

UNIV_FILE = "_bt_winda_universe.json"
CONS_FILE = "_bt_winda_consensus.json"

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


def load_cache(path: str) -> dict:
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {}


def download_json(url: str, timeout: int = 180) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    import io
    import pandas as pd
    df = pd.read_parquet(io.BytesIO(raw))
    return df.to_dict(orient="records")


def main():
    test = "--test" in sys.argv
    cli = JuziHTTP(*load_creds())
    print("connected to juzi-mcp")

    univ = load_cache(UNIV_FILE)
    cons = load_cache(CONS_FILE)
    periods = PIT[:1] if test else PIT

    # ---- ① PIT 成分股 ----
    print("\n① 万得全A PIT 成分")
    for month, as_of in periods:
        if month in univ and univ[month].get("members"):
            print(f"  [{month}] 已缓存 {univ[month]['count']} 只")
            continue
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_universe_members", {
                    "index_code": "881001.WI", "as_of_date": as_of,
                    "format": "inline"})
                members = [r.get("stock_code", "") for r in out.get("members", [])]
                members = [m for m in members if m]
                if members:
                    univ[month] = {"as_of": as_of, "count": len(members),
                                   "members": members}
                    json.dump(univ, open(UNIV_FILE, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                    print(f"  [{month}] {len(members)} 只 @ {as_of} | "
                          f"样例: {members[:3]}")
                    break
                print(f"    尝试 {attempt+1}: 0 条，重试")
                time.sleep(5)
            except Exception as e:
                print(f"    尝试 {attempt+1} 失败: {str(e)[:120]}")
                time.sleep(8)
        time.sleep(1)

    # ---- ② PIT 一致预期（parquet 全量）----
    print("\n② 一致预期 PIT 快照 (parquet)")
    for month, as_of in periods:
        if month in cons and cons[month].get("records"):
            print(f"  [{month}] 已缓存 {len(cons[month]['records'])} 条")
            continue
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_consensus_forecast", {
                    "universe": "881001.WI", "as_of_date": as_of,
                    "format": "parquet"})
                url = ((out.get("artifact") or {}).get("download_url"))
                if not url:
                    print(f"    无 download_url: {str(out)[:150]}")
                    time.sleep(5)
                    continue
                recs = download_json(url)
                if recs:
                    cons[month] = {
                        "as_of": as_of,
                        "snapshot_date": out.get("snapshot_date"),
                        "records": recs,
                    }
                    json.dump(cons, open(CONS_FILE, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                    sz = os.path.getsize(CONS_FILE) / 1024 / 1024
                    print(f"  [{month}] {len(recs)} 条 | snapshot "
                          f"{out.get('snapshot_date')} | 累计 {sz:.1f}MB")
                    break
                print(f"    尝试 {attempt+1}: 0 条，重试")
                time.sleep(5)
            except Exception as e:
                print(f"    尝试 {attempt+1} 失败: {str(e)[:120]}")
                time.sleep(8)
        time.sleep(2)

    print(f"\n完成: universe {len(univ)} 期 → {UNIV_FILE} | "
          f"consensus {len(cons)} 期 → {CONS_FILE}")


if __name__ == "__main__":
    main()
