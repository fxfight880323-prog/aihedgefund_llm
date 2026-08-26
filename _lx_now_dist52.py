# -*- coding: utf-8 -*-
"""刘旭框架当前推荐名单 × 锚定-近高点(dist52) 检查
dist52 = 当前收盘价 / 过去52周(250交易日)最高价
- dist52 -> 1: 价格贴近52周高点 -> 锚定效应下的"反应不足"信号(偏多)
- dist52 -> 0: 深跌远离高点 -> L3规避规则"距52周高点过远不买入"
数据源: 腾讯 ifzq.gtimg.cn 日K(前复权), 真实行情
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

# ---------- 1. 组装推荐名单(并集) ----------
res = json.load(open(BASE + "_lx_now_results.json", encoding="utf-8"))
sc = json.load(open(BASE + "_lx_now_scored.json", encoding="utf-8"))

pool = {}  # code -> info
for r in res["core"]:
    pool.setdefault(r["code"], dict(r, layer="core"))
for r in res["gm"]:
    pool.setdefault(r["code"], dict(r, layer="gm"))
for r in sc["top40"]:
    if r["code"] in pool:
        pool[r["code"]]["score_rank"] = r.get("score_rank")
        pool[r["code"]]["score_total"] = r.get("score_total")
    else:
        pool.setdefault(r["code"], dict(r, layer="scored"))

codes = sorted(pool.keys())
print(f"推荐名单并集: {len(codes)} 只 (core40 + gm40 + 评分top40)")


# ---------- 2. 拉日K并计算52周高点距离 ----------
def tx_symbol(code):
    return ("SH" if code.endswith(".SH") else "SZ") + code[:6]


def fetch_one(code):
    sym = tx_symbol(code).lower()
    url = (f"https://ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},day,,,270,qfq")
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15)
            data = r.json()["data"][sym]
            rows = data.get("qfqday") or data.get("day") or []
            if not rows:
                return code, None
            # rows: [date, open, close, high, low, volume, ...]
            rows = rows[-250:]  # ~52周
            highs = [float(x[3]) for x in rows]
            lows = [float(x[4]) for x in rows]
            closes = [float(x[2]) for x in rows]
            last_date = rows[-1][0]
            hi52, lo52, cur = max(highs), min(lows), closes[-1]
            return code, {
                "last_date": last_date,
                "hi52": round(hi52, 3),
                "lo52": round(lo52, 3),
                "price": cur,
                "dist52": round(cur / hi52, 4) if hi52 > 0 else None,
                "off52_pct": round((cur / hi52 - 1) * 100, 2) if hi52 > 0 else None,
            }
        except Exception as e:
            if attempt == 2:
                print(f"  FAIL {code}: {e}")
                return code, None
            time.sleep(1.5)


results = {}
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(fetch_one, c): c for c in codes}
    done = 0
    for f in as_completed(futs):
        c, v = f.result()
        if v:
            results[c] = v
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(codes)}")

print(f"成功获取 {len(results)}/{len(codes)}")


# ---------- 3. 分档 ----------
def tier(d):
    if d is None:
        return "?"
    if d >= 0.95:
        return "贴近高点"
    if d >= 0.85:
        return "较近"
    if d >= 0.70:
        return "中等"
    return "过远"


out_rows = []
for c in codes:
    if c not in results:
        continue
    info = pool[c]
    v = results[c]
    t = tier(v["dist52"])
    out_rows.append({
        "code": c, "name": info.get("name", ""), "layer": info.get("layer", ""),
        "score_rank": info.get("score_rank"), "score_total": info.get("score_total"),
        "pe": info.get("pe"), "peg": info.get("peg"), "dy": info.get("dy"),
        "price": v["price"], "hi52": v["hi52"], "lo52": v["lo52"],
        "dist52": v["dist52"], "off52_pct": v["off52_pct"],
        "tier": t, "last_date": v["last_date"],
    })

out_rows.sort(key=lambda r: (-(r["dist52"] or 0)))
n_far = sum(1 for r in out_rows if r["tier"] == "过远")
n_near = sum(1 for r in out_rows if r["tier"] in ("贴近高点", "较近"))
print(f"贴近/较近: {n_near} 只, 过远(<0.70): {n_far} 只")

json.dump({"as_of_price": "latest", "rows": out_rows},
          open(BASE + "_lx_now_dist52.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("saved _lx_now_dist52.json")

# CSV
import csv
with open(BASE + "刘旭框架_距52周高点.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["代码", "名称", "层级", "评分排名", "综合评分", "PE", "PEG", "股息率%",
                "现价", "52周最高", "52周最低", "dist52(现价/52周高)", "距高点%",
                "分档", "行情日期"])
    for r in out_rows:
        w.writerow([r["code"], r["name"], r["layer"],
                    r["score_rank"] or "", r["score_total"] or "",
                    r["pe"] if r["pe"] is not None else "",
                    r["peg"] if r["peg"] is not None else "",
                    r["dy"] if r["dy"] is not None else "",
                    r["price"], r["hi52"], r["lo52"], r["dist52"],
                    r["off52_pct"], r["tier"], r["last_date"]])
print("saved 刘旭框架_距52周高点.csv")
