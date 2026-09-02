# -*- coding: utf-8 -*-
"""低PE因子10年回测 — 前复权月K批量拉取（腾讯 fqkline qfqmonth）。

拉取所有 20 期成分并集 + 中证全指(000985.SH) 的前复权月K收盘价，
存 {ticker: {date: close}}。qfqmonth.close 即前复权收盘价，序列收益=含分红总回报。

用法:
  python _bt_lowpe_10y_px.py            # 全量
  python _bt_lowpe_10y_px.py --test     # 只拉 5 只验证
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/workspace/ai_fund_framework/"
OUT = BASE + "_bt_lowpe_10y_px.json"
IDX_OUT = BASE + "_bt_lowpe_10y_idx.json"
START = "2016-01-01"
END = "2026-08-31"


def tx_symbol(code):
    if code.endswith(".SH"):
        return ("sh" + code[:6])
    if code.endswith(".SZ"):
        return ("sz" + code[:6])
    return code


def fetch_one(code):
    sym = tx_symbol(code)
    url = (f"https://ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},month,{START},{END},200,qfq")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8"))
            node = data["data"][sym]
            k = node.get("qfqmonth") or node.get("month") or []
            if not k:
                return code, None
            out = {}
            for r in k:  # [date, open, close, high, low, volume]
                c = float(r[2])
                if c > 0:
                    out[r[0]] = c
            return code, out
        except Exception as e:
            if attempt == 3:
                return code, None
            time.sleep(1.0)
    return code, None


def main():
    test = "--test" in sys.argv
    syms = json.load(open(BASE + "_bt_lowpe_10y_symbols.json", encoding="utf-8"))
    codes = sorted(syms)
    if test:
        codes = codes[:5]
    print(f"待拉月K: {len(codes)} 只（2016-01 ~ 2026-08 前复权）")

    got = {}
    fail = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(fetch_one, c): c for c in codes}
        done = 0
        for f in as_completed(futs):
            c, v = f.result()
            if v:
                got[c] = v
            else:
                fail.append(c)
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(codes)}  成功{len(got)} 失败{len(fail)}")
    print(f"完成: 成功 {len(got)}/{len(codes)}，失败 {len(fail)}")
    if fail:
        print("失败样本:", fail[:20])

    # 追加中证全指
    idx = fetch_one("000985.SH")
    print(f"中证全指: {len(idx[1]) if idx[1] else 0} 根月K")

    json.dump(got, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(idx[1] if idx[1] else {}, open(IDX_OUT, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(fail, open(BASE + "_bt_lowpe_10y_px_fail.json", "w"), ensure_ascii=False)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
