# -*- coding: utf-8 -*-
"""探测缓存数据: 时间范围 / 覆盖 / 字段 — 行为金融信号可行性检查"""
import json, sys

def main():
    prices = json.loads(open("_bt_winda_prices.json", encoding="utf-8").read())
    all_months = sorted({mk for m in prices.values() for mk in m})
    print(f"[prices] tickers={len(prices)} months={len(all_months)} range={all_months[0]}~{all_months[-1]}")
    # 每个 ticker 的月份数分布
    lens = sorted({len(m) for m in prices.values()})
    print(f"[prices] per-ticker month counts sample: {lens[:5]} ... {lens[-3:]}")

    univ = json.loads(open("_bt_winda_universe.json", encoding="utf-8").read())
    print("[universe] keys:", list(univ.keys())[:12])
    for m, d in list(univ.items())[:2]:
        print(f"  {m}: members={len(d.get('members', []))}")

    cons = json.loads(open("_bt_winda_consensus.json", encoding="utf-8").read())
    ks = list(cons.keys())
    print(f"[consensus] months={len(ks)} sample keys: {ks[:3]}...{ks[-2:]}")
    # 字段
    fields = set()
    for m in ks[:1]:
        for r in cons[m].get("records", [])[:5]:
            fields.update(r.keys())
    print("[consensus] fields:", sorted(fields))
    # 每期覆盖
    for m in ks[:3] + ks[-2:]:
        n = len(cons[m].get("records", []))
        print(f"  {m}: records={n}")

    val = json.loads(open("_bt_lx_allA_valuation.json", encoding="utf-8").read())
    print(f"[valuation] months={len(val)} keys={list(val.keys())[:2]}")
    for m, d in list(val.items())[:2]:
        recs = d.get("records", [])
        print(f"  {m}: records={len(recs)} sample={recs[0] if recs else None}")

    fac = json.loads(open("_bt_lx_allA_factors.json", encoding="utf-8").read())
    print(f"[factors] months={len(fac)} keys={list(fac.keys())[:2]}")
    for m, d in list(fac.items())[:2]:
        recs = d.get("records", [])
        print(f"  {m}: records={len(recs)} sample_keys={list(recs[0].keys()) if recs else None}")

if __name__ == "__main__":
    main()
