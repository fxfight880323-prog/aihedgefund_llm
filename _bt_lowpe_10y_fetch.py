# -*- coding: utf-8 -*-
"""低PE因子10年稳健性检验 — 数据拉取（2016-08 ~ 2026-04，半年调仓20期）。

拉取：
  ① 万得全A(881001.WI) PIT 成分（as_of_date + format=inline，返回真正历史成分）
  ② 估值面板 pe_ttm / pb / total_mv（每期 as_of 单日快照，parquet）

输出：
  _bt_lowpe_10y_universe.json   {month: {as_of, count, members[]}}
  _bt_lowpe_10y_valuation.json  {month: {as_of, records[{stock_code, pe_ttm, pb, total_mv, ...}]}}

用法:
  python _bt_lowpe_10y_fetch.py            # 全量20期
  python _bt_lowpe_10y_fetch.py --test     # 只拉前2期
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")
from examples.fetch_consensus import JuziHTTP, load_creds

UNIV_FILE = "_bt_lowpe_10y_universe.json"
VAL_FILE = "_bt_lowpe_10y_valuation.json"

# 半年调仓：每年 4 月（年报后）和 8 月（中报后）
PIT = [
    ("2016-08", "2016-08-31"),
    ("2017-04", "2017-04-30"),
    ("2017-08", "2017-08-31"),
    ("2018-04", "2018-04-30"),
    ("2018-08", "2018-08-31"),
    ("2019-04", "2019-04-30"),
    ("2019-08", "2019-08-31"),
    ("2020-04", "2020-04-30"),
    ("2020-08", "2020-08-31"),
    ("2021-04", "2021-04-30"),
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


def load_cache(path):
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {}


def download_parquet(url: str) -> list[dict]:
    import pandas as pd
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    return pd.read_parquet(io.BytesIO(raw)).to_dict(orient="records")


def main():
    test = "--test" in sys.argv
    cli = JuziHTTP(*load_creds())
    univ = load_cache(UNIV_FILE)
    val = load_cache(VAL_FILE)
    periods = PIT[:2] if test else PIT

    for month, as_of in periods:
        # ---- ① PIT 成分 ----
        if month not in univ or not univ[month].get("members"):
            ok = False
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
                        print(f"  [{month}] 成分 {len(members)} 只 @ {as_of}")
                        ok = True
                        break
                    time.sleep(4)
                except Exception as e:
                    print(f"  [{month}] 成分尝试{attempt+1}失败: {str(e)[:120]}")
                    time.sleep(6)
        else:
            print(f"  [{month}] 成分已缓存 {univ[month]['count']} 只")

        # ---- ② 估值面板 ----
        members = univ[month].get("members", [])
        if month not in val or not val[month].get("records"):
            if not members:
                continue
            ok = False
            for attempt in range(3):
                try:
                    out = cli.call_tool("factor_get_valuation_panel", {
                        "stock_codes": members, "start_date": as_of,
                        "end_date": as_of, "format": "parquet"})
                    url = (out.get("artifact") or {}).get("download_url")
                    if url:
                        recs = download_parquet(url)
                        if recs:
                            val[month] = {"as_of": as_of, "records": recs}
                            json.dump(val, open(VAL_FILE, "w", encoding="utf-8"),
                                      ensure_ascii=False, indent=1)
                            print(f"  [{month}] 估值 {len(recs)} 条")
                            ok = True
                            break
                    time.sleep(4)
                except Exception as e:
                    print(f"  [{month}] 估值尝试{attempt+1}失败: {str(e)[:120]}")
                    time.sleep(6)
        else:
            print(f"  [{month}] 估值已缓存 {len(val[month]['records'])} 条")

        time.sleep(1)

    # 汇总
    all_members = set()
    for month, _ in PIT:
        all_members.update(univ.get(month, {}).get("members", []))
    print(f"\n完成: 成分 {len(univ)} 期 | 估值 {len(val)} 期 | 成分并集 {len(all_members)} 只")
    json.dump(sorted(all_members), open("_bt_lowpe_10y_symbols.json", "w"),
              ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
