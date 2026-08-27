# -*- coding: utf-8 -*-
"""行业层面筹码合成的领先性快检：
chip@2026-06-30 -> 7月行业收益；chip@2026-07-31 -> 8月(至今)行业收益.
行业收益 = 行业内等权股票收益均值（东财行业口径，现势映射，仅作快检）."""
import json
import os
import sqlite3
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples"))
from fetch_consensus import JuziHTTP, load_creds  # noqa: E402
from _chip_industry_fetch import fetch_chip  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATE = "2026-06-30"

cur = json.load(open(os.path.join(HERE, "_chip_industry_data.json"), encoding="utf-8"))
codes = [r["ts_code"] for r in cur["stocks"]]
ind_map = {r["ts_code"]: r["industry"] for r in cur["stocks"]}

cache = os.path.join(HERE, "_chip_industry_0630.json")
if os.path.exists(cache):
    chip = json.load(open(cache, encoding="utf-8"))
else:
    url, token = load_creds()
    url = url.rstrip("/") + "/" if url.rstrip("/").endswith("/mcp") else url
    cli = JuziHTTP(url, token)
    chip = fetch_chip(cli, codes)
    json.dump(chip, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
print(f"chip@{DATE}: {len(chip)} stocks")

con = sqlite3.connect(os.path.join(HERE, "data", "a_share_market.db"))
close = {}
for m in ("2026-06", "2026-07", "2026-08"):
    close[m] = dict(con.execute(
        "SELECT ticker, close FROM monthly_close WHERE month=?", (m,)))


def industry_fwd(chip_map, m0, m1, min_n=15):
    """按行业聚合因子均值，再算行业前向收益（行业内等权）。"""
    groups = {}
    for tc, v in chip_map.items():
        ind = ind_map.get(tc)
        if ind:
            groups.setdefault(ind, []).append((tc, v))
    out = []
    for ind, lst in groups.items():
        if len(lst) < min_n:
            continue
        rets = []
        for tc, _ in lst:
            a, b = close[m0].get(tc), close[m1].get(tc)
            if a and b:
                rets.append(b / a - 1)
        if len(rets) >= min_n * 0.6:
            out.append({"industry": ind, "n": len(lst),
                        "chip_mean": st.mean(v for _, v in lst),
                        "fwd_ret": st.mean(rets)})
    return out


# 检验1：chip@06-30 -> 2026-07 行业收益
r1 = industry_fwd(chip, "2026-06", "2026-07")
# 检验2：chip@07-31 -> 2026-08(至今) 行业收益
chip2 = {r["ts_code"]: r["chip"] for r in cur["stocks"]}
r2 = industry_fwd(chip2, "2026-07", "2026-08")


def report(rows, tag):
    rows = sorted(rows, key=lambda r: r["chip_mean"])
    n = len(rows)
    q = n // 5
    if q == 0:
        print(f"{tag}: industries={n} too few")
        return
    print(f"\n== {tag} (n_ind={n}) ==")
    print("chip最低1/5行业(集中) 前6:", [(r["industry"], round(r["chip_mean"],2),
          f"{r['fwd_ret']*100:+.1f}%") for r in rows[:6]])
    print("chip最高1/5行业(分散) 后6:", [(r["industry"], round(r["chip_mean"],2),
          f"{r['fwd_ret']*100:+.1f}%") for r in rows[-6:]])
    lo = st.mean(r["fwd_ret"] for r in rows[:q])
    hi = st.mean(r["fwd_ret"] for r in rows[-q:])
    mid = st.mean(r["fwd_ret"] for r in rows)
    print(f"集中端Q1均收益 {lo*100:+.2f}% | 全体 {mid*100:+.2f}% | 分散端Q5 {hi*100:+.2f}% | Q1-Q5 = {(lo-hi)*100:+.2f}pp")
    # 相关性
    xs = [r["chip_mean"] for r in rows]; ys = [r["fwd_ret"] for r in rows]
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / len(xs)
    corr = cov / (st.pstdev(xs) * st.pstdev(ys))
    print(f"corr(行业chip均值, 前向收益) = {corr:+.2f}")


report(r1, "chip@2026-06-30 -> 7月收益")
report(r2, "chip@2026-07-31 -> 8月至今收益")
