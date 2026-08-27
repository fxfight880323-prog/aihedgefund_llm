# -*- coding: utf-8 -*-
"""_qc_fetch.py — 高质量低估值案例股数据拉取（药明康德/美的/宁德时代）
1) qt.gtimg.cn 实时行情（价格/PE_TTM/PB/总市值）
2) web.ifzq.gtimg.cn 日K 前复权 2018-01-01 ~ 最新（含 52 周高点距离计算）
输出: _qc_quote.json / _qc_daily.json
"""
import json, os, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/workspace/ai_fund_framework/"
os.chdir(BASE)

STOCKS = {
    "603259.SH": "药明康德",
    "000333.SZ": "美的集团",
    "300750.SZ": "宁德时代",
}
# 腾讯代码格式
TMAP = {"603259.SH": "sh603259", "000333.SZ": "sz000333", "300750.SZ": "sz300750"}


def http_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore"))


def pull_quote():
    q = ",".join(TMAP.values())
    url = f"http://qt.gtimg.cn/q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    txt = urllib.request.urlopen(req, timeout=30).read().decode("gbk", "ignore")
    out = {}
    for line in txt.strip().split(";\n"):
        line = line.strip().rstrip(";")
        if not line or "=" not in line:
            continue
        var, payload = line.split("=", 1)
        f = payload.strip('"').split("~")
        if len(f) < 50:
            continue
        # f[1]=名称 f[2]=代码 f[3]=现价 f[39]=PE(TTM) f[44]=流通市值(亿) f[45]=总市值(亿) f[46]=PB
        out[f[2]] = {
            "ts_code": f[2], "name": f[1], "price": float(f[3]) if f[3] else None,
            "pe_ttm": float(f[39]) if f[39] else None,
            "pb": float(f[46]) if f[46] else None,
            "float_mv_yi": float(f[44]) if f[44] else None,
            "total_mv_yi": float(f[45]) if f[45] else None,
            "date": f[30] if len(f) > 30 else None,
        }
    json.dump(out, open("_qc_quote.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in out.items():
        print(f"{v['name']} {k}: 价 {v['price']}  PE(TTM) {v['pe_ttm']}  PB {v['pb']}  总市值 {v['total_mv_yi']}亿")
    return out


def pull_daily():
    out = {}
    chunks = [("2018-01-01", "2020-01-01"), ("2020-01-01", "2022-01-01"),
              ("2022-01-01", "2024-01-01"), ("2024-01-01", "2026-08-31")]
    for code, ts in TMAP.items():
        rows = {}
        for lo, hi in chunks:
            url = (f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
                   f"param={ts},day,{lo},{hi},640,qfq")
            data = http_json(url)
            node = data["data"][ts]
            k = node.get("qfqday") or node.get("day")
            for r in k:  # [date, open, close, high, low, volume, ...]
                rows[r[0]] = {"open": float(r[1]), "close": float(r[2]),
                              "high": float(r[3]), "low": float(r[4])}
            time.sleep(0.4)
        out[code] = rows
        print(f"{STOCKS[code]} {code}: {len(rows)} 天  {min(rows)} ~ {max(rows)}")
    json.dump(out, open("_qc_daily.json", "w", encoding="utf-8"), ensure_ascii=False)
    return out


if __name__ == "__main__":
    pull_quote()
    pull_daily()
    print("saved _qc_quote.json / _qc_daily.json")
