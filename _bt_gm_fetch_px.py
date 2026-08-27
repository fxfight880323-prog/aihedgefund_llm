# -*- coding: utf-8 -*-
"""补拉 gm 名单缺价股票日K（腾讯 fqkline qfq）→ 合并进 _bt_daily_px_full.json。

复权口径: qfqday.close 作为 adj，day 未复权 OHLC × (adj/close) 折算，
与 _bt_garp_audit.py 的 bar 构造一致（复权价序列只差常数倍，收益口径不变）。
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/workspace/ai_fund_framework/"
PX_FULL = BASE + "_bt_daily_px_full.json"


def tx_symbol(code):
    mkt = "SH" if code.endswith(".SH") else "SZ"
    return (mkt + code[:6]).lower()


def fetch_one(code):
    sym = tx_symbol(code)
    url = (f"https://ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},day,2021-04-25,2026-08-31,1400,qfq")
    for attempt in range(4):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8"))
            node = data["data"][sym]
            qfq = node.get("qfqday") or []
            raw = node.get("day") or []
            if not qfq:
                return code, None
            raw_map = {r[0]: r for r in raw}
            out = {}
            for r in qfq:  # [date, open, close, high, low, volume]
                dt = r[0]
                rr = raw_map.get(dt)
                c_raw = float(rr[2]) if rr else float(r[2])
                a = float(r[2])
                if c_raw <= 0 or a <= 0:
                    continue
                ratio = a / c_raw
                o = (float(r[1]) if rr is None else float(rr[1])) * ratio
                h = (float(r[3]) if rr is None else float(rr[3])) * ratio
                lo = (float(r[4]) if rr is None else float(rr[4])) * ratio
                out[dt] = {"open": o, "high": h, "low": lo, "close": c_raw, "adj": a}
            return code, out
        except Exception as e:
            if attempt == 3:
                print(f"  FAIL {code}: {str(e)[:100]}")
                return code, None
            time.sleep(1.5)
    return code, None


def main():
    gm = json.load(open(BASE + "_bt_gm_weights.json", encoding="utf-8"))
    px = json.load(open(PX_FULL, encoding="utf-8"))
    have = set(px.keys())
    need = set()
    for p in ("w_core", "w_gm"):
        for month, lst in gm[p].items():
            for tk in lst:
                if tk not in have:
                    need.add(tk)
    print(f"缺价股票: {len(need)} 只")
    if not need:
        print("无需补拉")
        return
    codes = sorted(need)
    got = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, c): c for c in codes}
        done = 0
        for f in as_completed(futs):
            c, v = f.result()
            if v:
                got[c] = v
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(codes)}")
    print(f"成功 {len(got)}/{len(codes)}")
    merged = dict(px)
    for c, v in got.items():
        merged[c] = v
    json.dump(merged, open(PX_FULL, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"merged: {len(merged)} 只 → {PX_FULL}")
    # 存一份新增名单便于核对
    json.dump({c: got[c] for c in sorted(got)}, open(BASE + "_bt_gm_px_new.json", "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
