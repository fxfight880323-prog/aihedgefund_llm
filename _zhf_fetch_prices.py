"""补齐章宏帆龙头池月末收盘价（腾讯月K线，qfq，2021-06 → 2026-08）。

A股: sz/sh + code；港股: hk + 5位代码。输出 _zhf_prices.json {tk: {YYYY-MM: close}}。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.path.insert(0, ".")
from examples.alla_rotation import LEADER_SEEDS

OUT = "_zhf_prices.json"


def market_prefix(tk: str) -> str:
    if tk.endswith(".HK"):
        return "hk" + tk[:5]
    code = tk.split(".")[0]
    return ("sh" if code.startswith("6") else "sz") + code


def fetch_monthly(tk: str) -> dict[str, float]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={market_prefix(tk)},month,2021-06-01,2026-08-19,200,qfq")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    data = raw.get("data")
    sub = (data or {}).get(market_prefix(tk), {}) if isinstance(data, dict) else {}
    rows = (sub.get("qfqmonth") or sub.get("month") or [])
    out = {}
    for r in rows:
        if len(r) >= 3 and r[0] and float(r[2]) > 0:
            out[r[0][:7]] = float(r[2])   # [date, open, close, high, low, vol]
    return out


def main():
    leaders: dict[str, str] = {}
    for link, seeds in LEADER_SEEDS.items():
        if link.startswith("_"):
            continue
        for name, tk in seeds.items():
            leaders.setdefault(tk, name)

    cache = {}
    try:
        cache = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        pass

    ok, fail = 0, []
    for i, (tk, name) in enumerate(sorted(leaders.items())):
        if tk in cache and cache[tk]:
            ok += 1
            continue
        try:
            m = fetch_monthly(tk)
            if m:
                cache[tk] = m
                ok += 1
                span = (min(m), max(m))
                print(f"[{i+1}/{len(leaders)}] {tk} {name}: {len(m)} 个月 {span[0]}~{span[1]}",
                      flush=True)
            else:
                fail.append((tk, name, "empty"))
                print(f"[{i+1}/{len(leaders)}] {tk} {name}: EMPTY", flush=True)
        except Exception as e:
            fail.append((tk, name, str(e)[:80]))
            print(f"[{i+1}/{len(leaders)}] {tk} {name}: ERR {str(e)[:80]}", flush=True)
        time.sleep(0.3)
        if (i + 1) % 10 == 0:
            json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

    json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    cov = {tk: len([m for m in v if v[m]]) for tk, v in cache.items()}
    full = sum(1 for tk in cov if cov[tk] >= 55)
    print(f"\n完成: {ok}/{len(leaders)} 只, 满覆盖(≥55月) {full} 只, 失败 {len(fail)}")
    for tk, name, why in fail:
        print(f"  FAIL {tk} {name}: {why}")


if __name__ == "__main__":
    main()
