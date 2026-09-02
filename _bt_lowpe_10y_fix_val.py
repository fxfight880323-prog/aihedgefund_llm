# -*- coding: utf-8 -*-
"""补拉 7 期缺失估值（as_of 落在周末 → 回退到最近交易日）。"""
import io
import json
import os
import sys
import time
import urllib.request
import datetime

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")
from examples.fetch_consensus import JuziHTTP, load_creds

UNIV_FILE = "_bt_lowpe_10y_universe.json"
VAL_FILE = "_bt_lowpe_10y_valuation.json"

MISSING = ["2017-04", "2018-04", "2019-08", "2022-04", "2023-04", "2024-08", "2025-08"]


def download_parquet(url):
    import pandas as pd
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    return pd.read_parquet(io.BytesIO(raw)).to_dict(orient="records")


def main():
    cli = JuziHTTP(*load_creds())
    univ = json.load(open(UNIV_FILE, encoding="utf-8"))
    val = json.load(open(VAL_FILE, encoding="utf-8"))

    for month in MISSING:
        as_of = univ[month]["as_of"]
        members = univ[month]["members"]
        # 回退策略：从 as_of 往前最多 10 天，找第一个有数据的交易日
        got = None
        for back in range(0, 11):
            d = (datetime.date.fromisoformat(as_of) - datetime.timedelta(days=back)).isoformat()
            try:
                out = cli.call_tool("factor_get_valuation_panel", {
                    "stock_codes": members, "start_date": d,
                    "end_date": d, "format": "parquet"})
                url = (out.get("artifact") or {}).get("download_url")
                if url:
                    recs = download_parquet(url)
                    if recs:
                        got = (d, recs)
                        break
            except Exception as e:
                print(f"  {month} 回退{back}天({d}) 失败: {str(e)[:80]}")
            time.sleep(2)
        if got:
            d, recs = got
            val[month] = {"as_of": as_of, "val_date": d, "records": recs}
            json.dump(val, open(VAL_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  {month}: as_of={as_of} 回退到 {d}，{len(recs)} 条 ✓")
        else:
            print(f"  {month}: 回退10天仍失败 ✗")

    print(f"\n估值期数: {len(val)} / 20")


if __name__ == "__main__":
    main()
