# -*- coding: utf-8 -*-
"""拉取 4 只风格 ETF 前复权日K（腾讯 ifzq fqkline，分页 count=640）"""
import json, time, csv, os
import urllib.request

OUT = r"D:\workspace\ai_fund_framework\_sr_cache"
os.makedirs(OUT, exist_ok=True)

ETFS = [
    ("sh512100", "etf_csi1000"),   # 南方中证1000ETF 2016-11 上市
    ("sh510050", "etf_sse50"),     # 华夏上证50ETF 2005
    ("sz159915", "etf_chinext"),   # 易方达创业板ETF 2011-12
    ("sh512890", "etf_divlowvol"), # 华泰柏瑞红利低波ETF 2019-01
]

HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://gu.qq.com/"}

def fetch_one(code):
    """倒序分页拉全部前复权日K，返回 [(date, open, close, high, low, volume)]"""
    rows = []
    end = ""  # 空 = 最新
    for _ in range(30):  # 上限 30 页足够（640*30 >> 4300）
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
               f"?param={code},day,,{end},640,qfq")
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        node = data.get("data", {}).get(code, {})
        k = node.get("qfqday") or node.get("day") or []
        if not k:
            break
        for row in k:
            # [date, open, close, high, low, volume, ...]
            rows.append((row[0], row[1], row[2], row[3], row[4], row[5]))
        oldest = k[0][0]
        if len(k) < 640:
            break
        end = oldest  # 下一页以最旧日期为终点
        time.sleep(0.5)
    # 去重（end 日期本身会重复出现）
    seen, uniq = set(), []
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0])
            uniq.append(row)
    uniq.sort(key=lambda x: x[0])
    return uniq

for code, slug in ETFS:
    rows = fetch_one(code)
    path = os.path.join(OUT, f"{slug}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "close", "high", "low", "volume"])
        for row in rows:
            w.writerow(row)
    print(f"{code} -> {slug}: {len(rows)} rows, {rows[0][0]} -> {rows[-1][0]}")
    time.sleep(0.5)

print("DONE")
