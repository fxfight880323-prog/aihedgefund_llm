"""刘旭框架全A回测 — 数据拉取：全市场估值面板 + HF 质量因子（10 期 PIT）。

数据层（全部真实市场数据，PIT 快照）：
  A. factor_get_valuation_panel  每期 as_of 单日 → pe_ttm / pb / total_mv(万元) / float_mv
  B. factor_get_factor_panel    每期 as_of 单日 → gpm 毛利率 / cetop 营业现金流市值比
                                    / npyoy 净利同比 / roeyoy ROE同比 / roes ROE稳定性
                                    / dtop5 股息率A / oryoy 营收同比 / lncap 对数市值
  C. 一致预期（复用 _bt_winda_consensus.json）→ con_roe / con_np_yoy / con_peg / con_pe

池子 = 万得全A(881001.WI) PIT 成分（_bt_winda_universe.json）。

用法:
  python _lx_allA_fetch.py [--test]   # --test 只拉第一期
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples.fetch_consensus import JuziHTTP, load_creds

VAL_FILE = "_bt_lx_allA_valuation.json"
FAC_FILE = "_bt_lx_allA_factors.json"

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

FACTORS = ["gpm", "cetop", "npyoy", "roeyoy", "roes", "dtop5", "oryoy", "lncap"]


def load_cache(path: str) -> dict:
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {}


def download_json(url: str, timeout: int = 240) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    import pandas as pd
    return pd.read_parquet(io.BytesIO(raw)).to_dict(orient="records")


def save(cache: dict, path: str, month: str, n: int):
    json.dump(cache, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  [{month}] 缓存 {n} 条 → {path} ({os.path.getsize(path)/1e6:.1f}MB)")


def main():
    test = "--test" in sys.argv
    cli = JuziHTTP(*load_creds())
    print("connected to juzi-mcp")

    univ = json.load(open("_bt_winda_universe.json", encoding="utf-8"))
    val = load_cache(VAL_FILE)
    fac = load_cache(FAC_FILE)
    periods = PIT[:1] if test else PIT

    for month, as_of in periods:
        members = univ.get(month, {}).get("members", [])
        if not members:
            print(f"  [{month}] 无成分，跳过")
            continue
        print(f"\n[{month}] 成分 {len(members)} 只 @ {as_of}")

        # ---- A. valuation panel ----
        if month not in val or not val[month].get("records"):
            ok = False
            for attempt in range(3):
                try:
                    out = cli.call_tool("factor_get_valuation_panel", {
                        "stock_codes": members, "start_date": as_of,
                        "end_date": as_of, "format": "parquet"})
                    url = ((out.get("artifact") or {}).get("download_url"))
                    if url:
                        recs = download_json(url)
                        if recs:
                            val[month] = {"as_of": as_of, "records": recs}
                            save(val, VAL_FILE, month, len(recs))
                            ok = True
                            break
                    print(f"    尝试 {attempt+1}: 无 url, 重试")
                    time.sleep(5)
                except Exception as e:
                    print(f"    尝试 {attempt+1} 失败: {str(e)[:120]}")
                    time.sleep(8)
            if not ok:
                print(f"  [{month}] valuation 拉取失败")
        else:
            print(f"  [{month}] valuation 已缓存 {len(val[month]['records'])} 条")

        # ---- B. HF factor panel ----
        if month not in fac or not fac[month].get("records"):
            ok = False
            for attempt in range(3):
                try:
                    out = cli.call_tool("factor_get_factor_panel", {
                        "stock_codes": members, "factor_codes": FACTORS,
                        "start_date": as_of, "end_date": as_of,
                        "format": "parquet"})
                    url = ((out.get("artifact") or {}).get("download_url"))
                    if url:
                        recs = download_json(url)
                        if recs:
                            fac[month] = {"as_of": as_of, "records": recs}
                            save(fac, FAC_FILE, month, len(recs))
                            ok = True
                            break
                    print(f"    尝试 {attempt+1}: 无 url, 重试")
                    time.sleep(5)
                except Exception as e:
                    print(f"    尝试 {attempt+1} 失败: {str(e)[:120]}")
                    time.sleep(8)
            if not ok:
                print(f"  [{month}] factor panel 拉取失败")
        else:
            print(f"  [{month}] factor 已缓存 {len(fac[month]['records'])} 条")

        time.sleep(1)

    print(f"\n完成: valuation {len(val)} 期 | factors {len(fac)} 期")


if __name__ == "__main__":
    main()
