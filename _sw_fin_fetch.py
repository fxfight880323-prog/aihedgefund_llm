# -*- coding: utf-8 -*-
"""拉取申万银行(801780.SI)+非银金融(801790.SI) PIT 成分 @ 2026-08-20。

用于从万得全A 池子中剔除金融股（用户要求）。与全A universe 同源(juzi)。
输出: _bt_sw_fin_universe.json
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

OUT = "_bt_sw_fin_universe.json"
AS_OF = "2026-08-20"
INDEXES = {
    "bank": "801780.SI",      # 申万一级 银行
    "nbfin": "801790.SI",     # 申万一级 非银金融（券商/保险/多元金融）
}


def main():
    cli = JuziHTTP(*load_creds())
    print("connected to juzi-mcp")

    result = {}
    for key, idx in INDEXES.items():
        for attempt in range(3):
            try:
                out = cli.call_tool("factor_get_universe_members", {
                    "index_code": idx, "as_of_date": AS_OF, "format": "inline"})
                members = [r.get("stock_code", "") if isinstance(r, dict) else str(r)
                           for r in out.get("members", [])]
                members = [m for m in members if m]
                if members:
                    result[key] = {"index": idx, "as_of": AS_OF, "members": members}
                    print(f"{idx} ({key}) → {len(members)} 只 @ {AS_OF}")
                    break
                print(f"  尝试 {attempt+1}: 空, 重试")
                time.sleep(5)
            except Exception as e:
                print(f"  尝试 {attempt+1} 失败: {str(e)[:150]}")
                time.sleep(8)
        else:
            print(f"!! {idx} 拉取失败")

    if len(result) < len(INDEXES):
        print("!! 部分行业拉取失败，继续（缺哪个剔除哪个）")

    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    union = set()
    for v in result.values():
        union |= set(v["members"])
    print(f"\n金融股合计(去重): {len(union)} 只 → {OUT}")


if __name__ == "__main__":
    main()
