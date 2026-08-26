# -*- coding: utf-8 -*-
"""日频价格拉取：242 只持仓股票日频（juzi parquet）+ 中证全指日K（腾讯）。
用法:
  1) 先由 AI 调用 juzi factor_get_return_panel 得到 parquet URL，写入 _bt_daily_url.json
  2) 本脚本下载 parquet → 解析为 {ticker: {date: {open, high, low, close, adj_close, ret}}} → _bt_daily_px.json
  3) 拉中证全指 000985.SH 日K → _bt_daily_idx.json
"""
import json, os, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

BASE = "D:/workspace/ai_fund_framework/"
os.chdir(BASE)

def download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print(f"  cached {path} ({os.path.getsize(path)//1024}KB)")
        return path
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())
    print(f"  saved {path} ({os.path.getsize(path)//1024}KB)")
    return path

def pull_idx():
    """中证全指 000985.SH 日K（腾讯，前复权无意义，指数直接收盘）"""
    out = BASE + "_bt_daily_idx.json"
    if os.path.exists(out):
        print("idx cached")
        return json.load(open(out, encoding="utf-8"))
    url = ("http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="
           "sh000985,day,2021-05-01,2026-08-31,1400,qfq")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
    node = data["data"]["sh000985"]
    k = node.get("qfqday") or node.get("day")
    rows = {}
    for r in k:  # [date, open, close, high, low, volume]
        rows[r[0]] = {"open": float(r[1]), "close": float(r[2]),
                      "high": float(r[3]), "low": float(r[4])}
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"idx: {len(rows)} days {min(rows)}~{max(rows)}")
    return rows

def main():
    # 1) juzi parquet URL
    u = json.load(open(BASE + "_bt_daily_url.json", encoding="utf-8"))
    url = u["url"] if isinstance(u, dict) else u
    p = download(url, BASE + "_bt_daily_px.parquet")
    import pandas as pd
    df = pd.read_parquet(p)
    print("cols:", list(df.columns), "shape:", df.shape)
    # 2) 解析为 {ticker: {date: {...}}}
    df = df.sort_values(["stock_code", "date"])
    px = {}
    for tk, g in df.groupby("stock_code"):
        d = {}
        for _, r in g.iterrows():
            dt = str(r["date"])[:10]
            d[dt] = {"open": float(r["open_"]) if r["open_"] == r["open_"] else None,
                     "high": float(r["high_"]) if r["high_"] == r["high_"] else None,
                     "low": float(r["low_"]) if r["low_"] == r["low_"] else None,
                     "close": float(r["close_"]) if r["close_"] == r["close_"] else None,
                     "adj": float(r["adj_close"]) if r["adj_close"] == r["adj_close"] else None,
                     "ret": float(r["daily_return"]) if r["daily_return"] == r["daily_return"] else None}
        px[tk] = d
    json.dump(px, open(BASE + "_bt_daily_px.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"parsed {len(px)} stocks, sample 000001.SZ days: {len(px.get('000001.SZ', {}))}")

    # 3) 中证全指
    pull_idx()

if __name__ == "__main__":
    main()
