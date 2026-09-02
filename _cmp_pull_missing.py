# -*- coding: utf-8 -*-
"""补拉当前模拟持仓中 _bt_daily_px_full.json 缺失的股票日K（腾讯前复权，分页）。
输出 _cmp_px_missing.json：{code: {date: {close, ret}}}
ret = 前复权收盘相邻日比 - 1（与回测 _bt_daily_px_full.json 的复权日收益同口径）。
"""
import json, os, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir("D:/workspace/ai_fund_framework")

MISSING = ["301219.SZ", "601339.SH", "600066.SH", "600928.SH", "000783.SZ", "601211.SH"]
START, END = "2021-05-06", "2026-08-28"


def tx_code(code: str) -> str:
    c, suf = code.split(".")
    return ("sh" if suf.upper().startswith("SH") else "sz") + c


def fetch_page(tc: str, end: str, count: int = 800) -> list:
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={tc},day,{START},{end},{count},qfq")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")
    d = json.loads(raw)
    data = d.get("data", {})
    if not isinstance(data, dict):
        return []
    v = data.get(tc, {})
    if not isinstance(v, dict):
        return []
    rows = v.get("qfqday") or v.get("day") or []
    return rows


out = {}
for code in MISSING:
    tc = tx_code(code)
    merged, end, guard = {}, END, 0
    while end >= START and guard < 6:
        guard += 1
        rows = None
        for attempt in range(3):
            try:
                rows = fetch_page(tc, end)
                break
            except Exception as e:
                print(f"  {code} {end} 第{attempt+1}次失败: {e}")
                time.sleep(2)
        if not rows:
            break
        for r in rows:
            merged[r[0]] = r
        earliest = min(r[0] for r in rows)
        if earliest <= START or len(rows) < 800:
            break
        # 往前翻页：以上一页最早日期减 1 天为新的 end
        y, m, d = map(int, earliest.split("-"))
        import datetime as dt
        end = (dt.date(y, m, d) - dt.timedelta(days=1)).isoformat()
        time.sleep(0.4)
    s = {}
    prev = None
    for dt0 in sorted(merged):
        try:
            close = float(merged[dt0][2])
        except Exception:
            continue
        ret = (close / prev - 1.0) if prev else 0.0
        s[dt0] = {"close": close, "ret": round(ret, 8)}
        prev = close
    out[code] = s
    dates = sorted(s.keys())
    print(f"{code} {tc}: {len(dates)} 天  {dates[0]} ~ {dates[-1]}")

json.dump(out, open("_cmp_px_missing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n→ _cmp_px_missing.json")
