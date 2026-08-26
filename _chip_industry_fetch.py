# -*- coding: utf-8 -*-
"""筹码合成因子 × 行业筛选：全A因子值(申万金工MCP) + 行业映射(东财行情) -> 行业聚合.

输出 _chip_industry_data.json:
  stocks: [{ts_code, name, industry, chip}]  (chip = 筹码合成 z-score, 2026-07-31)
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples"))
from fetch_consensus import JuziHTTP, load_creds  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_chip_industry_data.json")
DATE = "2026-07-31"

# ---------- 1) 东财全A行情 + 行业板块 ----------
def fetch_em_industry():
    stocks, pn = [], 1
    while True:
        url = ("https://push2delay.eastmoney.com/api/qt/clist/get"
               f"?pn={pn}&pz=200&po=1&np=1&fltt=2&invt=2&fid=f12"
               "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
               "&fields=f12,f13,f14,f100")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/"})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        diff = (d.get("data") or {}).get("diff") or []
        if not diff:
            break
        for it in diff:
            code, mkt = it["f12"], it["f13"]
            suffix = ".SH" if mkt == 1 else ".SZ"
            stocks.append({
                "ts_code": code + suffix,
                "name": it.get("f14", ""),
                "industry": it.get("f100") or "未知",
            })
        pn += 1
        time.sleep(0.3)
    return stocks


# ---------- 2) 批量拉筹码合成 ----------
def fetch_chip(cli, codes):
    out, B = {}, 100  # 服务器对返回记录数截断(~120行)，批必须 < 120
    for i in range(0, len(codes), B):
        batch = codes[i:i + B]
        got = 0
        for attempt in range(3):
            try:
                r = cli.call_tool("get_factor_value", {
                    "factors": ["筹码合成"], "ts_codes": batch, "date": DATE})
                recs = r.get("records") or r.get("data") or []
                got = len(recs)
                for rec in recs:
                    v = rec.get("筹码合成")
                    if v is not None:
                        out[rec["ts_code"]] = v
                break
            except Exception as e:
                print(f"batch {i//B} attempt {attempt+1} failed: {e}")
                time.sleep(3)
        if (i // B) % 10 == 0:
            print(f"  chip batch {i//B + 1}/{(len(codes)+B-1)//B}: +{got}, total {len(out)}")
    return out


def main():
    stocks = fetch_em_industry()
    print(f"eastmoney stocks with industry: {len(stocks)}")

    url, token = load_creds()
    url = url.rstrip("/") + "/" if url.rstrip("/").endswith("/mcp") else url
    cli = JuziHTTP(url, token)
    print("connected to SW MCP")

    chip = fetch_chip(cli, [s["ts_code"] for s in stocks])
    print(f"stocks with chip factor: {len(chip)}")

    rows = []
    for s in stocks:
        v = chip.get(s["ts_code"])
        if v is not None:
            rows.append({"ts_code": s["ts_code"], "name": s["name"],
                         "industry": s["industry"], "chip": v})
    json.dump({"date": DATE, "n": len(rows), "stocks": rows},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"saved {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
