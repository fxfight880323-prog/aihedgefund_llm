"""补齐 4 个非交易日 as_of 的估值/因子面板（用最近交易日替代）。

失败期：2022-04-30(六) 2023-04-30(日) 2024-08-31(六) 2025-08-31(日)
替代：2022-04-29 2023-04-28 2024-08-30 2025-08-29（前一交易日，PIT 近似）
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

VAL_FILE = "_bt_lx_allA_valuation.json"
FAC_FILE = "_bt_lx_allA_factors.json"
FACTORS = ["gpm", "cetop", "npyoy", "roeyoy", "roes", "dtop5", "oryoy", "lncap"]

# month -> (原as_of, 替代交易日)
FIX = {
    "2022-04": ("2022-04-30", "2022-04-29"),
    "2023-04": ("2023-04-30", "2023-04-28"),
    "2024-08": ("2024-08-31", "2024-08-30"),
    "2025-08": ("2025-08-31", "2025-08-29"),
}


def download_json(url, timeout=240):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    import pandas as pd
    return pd.read_parquet(io.BytesIO(raw)).to_dict(orient="records")


def main():
    cli = JuziHTTP(*load_creds())
    univ = json.load(open("_bt_winda_universe.json", encoding="utf-8"))
    val = json.loads(open(VAL_FILE, encoding="utf-8").read())
    fac = json.loads(open(FAC_FILE, encoding="utf-8").read())

    for month, (orig, alt) in FIX.items():
        members = univ[month]["members"]
        print(f"\n[{month}] {orig}(非交易日) → 用 {alt} 拉取 {len(members)} 只")

        for tag, cache, tool, args in [
            ("valuation", val, "factor_get_valuation_panel",
             {"stock_codes": members, "start_date": alt, "end_date": alt,
              "format": "parquet"}),
            ("factor", fac, "factor_get_factor_panel",
             {"stock_codes": members, "factor_codes": FACTORS,
              "start_date": alt, "end_date": alt, "format": "parquet"}),
        ]:
            if month in cache and cache[month].get("records"):
                print(f"  [{month}] {tag} 已缓存 {len(cache[month]['records'])} 条")
                continue
            ok = False
            for attempt in range(4):
                try:
                    out = cli.call_tool(tool, args)
                    url = ((out.get("artifact") or {}).get("download_url"))
                    if url:
                        recs = download_json(url)
                        if recs:
                            cache[month] = {"as_of": alt, "orig": orig,
                                            "records": recs}
                            json.dump(cache, open(
                                VAL_FILE if tag == "valuation" else FAC_FILE,
                                "w", encoding="utf-8"), ensure_ascii=False,
                                indent=1)
                            print(f"  [{month}] {tag} → {len(recs)} 条 "
                                  f"@{alt} (替代 {orig})")
                            ok = True
                            break
                    print(f"    尝试 {attempt+1}: 无 url, 重试")
                    time.sleep(6)
                except Exception as e:
                    print(f"    尝试 {attempt+1} 失败: {str(e)[:120]}")
                    time.sleep(8)
            if not ok:
                print(f"  [{month}] {tag} 仍失败")
            time.sleep(2)

    print("\n完成补拉")


if __name__ == "__main__":
    main()
