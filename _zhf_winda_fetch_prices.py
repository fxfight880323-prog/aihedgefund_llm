"""万得全A 全市场回测 — 月度价格拉取（腾讯月K qfq，多线程）。

- 股票池: 10 期万得全A成分股 union（~5500 只）
- 区间: 2021-06 → 2026-08
- 输出: _bt_winda_prices.json {tk: {YYYY-MM: close}}
- 基准: 中证全指 000985.SH → _bt_winda_index.json

用法:
  python _zhf_winda_fetch_prices.py
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UNIV_FILE = "_bt_winda_universe.json"
PRICES_FILE = "_bt_winda_prices.json"
INDEX_FILE = "_bt_winda_index.json"

START, END = "2021-06-01", "2026-08-19"
MIN_MONTH = "2021-06"
WORKERS = 8
# 2026-08-20: web.ifzq.gtimg.cn 被腾讯 WAF 拦截(HTTP 501 → waf.tencent.com)，
# 备用域名 ifzq.gtimg.cn 正常。顺序尝试，单次失败不重试(快速跳过, 避免触发风控)。
HOSTS = ["https://ifzq.gtimg.cn", "https://web.ifzq.gtimg.cn"]
TIMEOUT = 15


def market_prefix(tk: str) -> str:
    """juzi '600519.SH'/'300750.SZ'/'830799.BJ' → 腾讯 'sh600519'/'sz300750'/'bj830799'."""
    code, mkt = tk.split(".")
    mkt = mkt.upper()
    if mkt in ("SH", "SS"):
        return "sh" + code
    if mkt in ("SZ", "SE"):
        return "sz" + code
    if mkt in ("BJ", "BE", "BSE"):
        return "bj" + code
    # fallback by code
    if code.startswith(("6", "9")):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def fetch_monthly(sym: str) -> dict[str, float] | None:
    for host in HOSTS:
        url = (f"{host}/appstock/app/fqkline/get"
               f"?param={sym},month,{START},{END},200,qfq")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = json.loads(
                urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8"))
            data = raw.get("data") or {}
            sub = data.get(sym, {}) if isinstance(data, dict) else {}
            rows = sub.get("qfqmonth") or sub.get("month") or []
            out = {}
            for r in rows:
                if len(r) >= 3 and r[0] and float(r[2]) > 0:
                    out[r[0][:7]] = float(r[2])
            if out:
                return out
        except Exception:
            pass
    return None


def main():
    univ = json.loads(open(UNIV_FILE, encoding="utf-8").read())
    tks: set[str] = set()
    for m, d in univ.items():
        tks.update(d.get("members", []))
    tks = sorted(tks)
    print(f"万得全A 10期成分 union: {len(tks)} 只")

    cache: dict = {}
    if os.path.exists(PRICES_FILE):
        cache = json.loads(open(PRICES_FILE, encoding="utf-8").read())
        print(f"  已缓存 {len(cache)} 只")
    todo = [t for t in tks if t not in cache]
    print(f"  需拉取 {len(todo)} 只 (workers={WORKERS})", flush=True)

    t0 = time.time()
    ok, fail = 0, []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_monthly, market_prefix(t)): t for t in todo}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            t = futs[fut]
            try:
                m = fut.result()
            except Exception as e:
                m = None
                fail.append((t, str(e)[:60]))
            if m:
                cache[t] = m
                ok += 1
            else:
                fail.append((t, "empty"))
            if i % 300 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(todo)} 完成, ok={ok}, fail={len(fail)}, "
                      f"耗时 {el:.0f}s", flush=True)
                json.dump(cache, open(PRICES_FILE, "w", encoding="utf-8"),
                          ensure_ascii=False)

    json.dump(cache, open(PRICES_FILE, "w", encoding="utf-8"),
              ensure_ascii=False)
    el = time.time() - t0
    print(f"\n价格完成: {ok}/{len(todo)} 只, {len(fail)} 失败, 耗时 {el:.0f}s")

    # ---- 中证全指基准 ----
    idx = fetch_monthly("sh000985")
    if idx:
        json.dump(idx, open(INDEX_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
        print(f"中证全指 000985.SH: {len(idx)} 个月 {min(idx)}~{max(idx)}")
    else:
        print("中证全指拉取失败")

    if fail:
        print("失败样例:", fail[:10])


if __name__ == "__main__":
    main()
