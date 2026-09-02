# -*- coding: utf-8 -*-
"""当前模拟持仓 vs 组合历史回测 对比分析。

口径：
  - 现持静态 = 固定模拟组合当前 40 只持仓，日频复权收益等权持有（权重漂移，不调仓）
    数据源 = _bt_daily_px_full.json（530 只回测日K）+ _cmp_px_missing.json（6 只补拉）
  - 回测策略 = _bt_garp_audit_results.json 汇总指标（core/g30/g60/nolimit, full 基座）
  - 基准 = _bt_daily_ew_hold_nav.json（半年调仓等权全A 1270 天）+ _bt_benchmark.json（中证全指月K）
  - 模拟盘实盘 = _sim_nav.json / _sim_q20_nav.json（建仓以来净值，含 15bp 成本）

输出：_cmp_hold_vs_bt.json → _cmp_hold_vs_bt_report.html
"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir("D:/workspace/ai_fund_framework")

# ---------- 1. 日收益面板 ----------
px = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
miss = json.load(open("_cmp_px_missing.json", encoding="utf-8"))
for code, s in miss.items():
    px[code] = {d: {"ret": v["ret"]} for d, v in s.items()}

# 统一 {code: {date: ret}}：优先 ret 字段，缺则用 adj 相邻比，再缺用 close 相邻比
RET = {}
for code, st in px.items():
    d = {}
    prev_adj = prev_close = None
    for dt0 in sorted(st):
        v = st[dt0]
        if "ret" in v and v["ret"] is not None:
            r = v["ret"]
        elif "adj" in v and prev_adj is not None:
            r = v["adj"] / prev_adj - 1.0
        elif "close" in v and prev_close is not None:
            r = v["close"] / prev_close - 1.0
        else:
            r = 0.0
        d[dt0] = r
        if "adj" in v:
            prev_adj = v["adj"]
        if "close" in v:
            prev_close = v["close"]
    RET[code] = d

ALL_DATES = sorted({dt0 for st in RET.values() for dt0 in st})
print(f"日K覆盖 {len(RET)} 只, 日期 {ALL_DATES[0]} ~ {ALL_DATES[-1]} ({len(ALL_DATES)} 天)")


def static_ew_curve(codes, d0="2021-06-01", d1="2026-08-24"):
    """现持静态等权日收益序列：{date: (ret, n)}，缺失股票上市前不计入。"""
    out = {}
    for d in ALL_DATES:
        if d < d0 or d > d1:
            continue
        rs = [RET[c][d] for c in codes if d in RET[c]]
        if not rs:
            continue
        out[d] = (sum(rs) / len(rs), len(rs))
    return out


def cumret(curve, a, b):
    """区间累计收益：a 日收盘买入，持有至 b 日收盘。"""
    prod = 1.0
    for d, (r, n) in curve.items():
        if d > a and d <= b:
            prod *= (1 + r)
    return prod - 1.0


def ann_ret(total, days):
    return (1 + total) ** (252 / days) - 1 if days > 0 else 0.0


def mdd_curve(curve, a, b):
    nav, peak, mdd = 1.0, 1.0, 0.0
    for d, (r, n) in curve.items():
        if d > a and d <= b:
            nav *= (1 + r)
            peak = max(peak, nav)
            mdd = max(mdd, (peak - nav) / peak)
    return mdd


def yearly(curve, a="2021-06-01", b="2026-08-24"):
    """按自然年窗口拆分累计收益。"""
    res = {}
    for d, (r, n) in curve.items():
        if d <= a or d > b:
            continue
        y = d[:4]
        res.setdefault(y, 1.0)
        res[y] *= (1 + r)
    return {y: v - 1.0 for y, v in res.items()}


LX = [p["code"] for p in json.load(open("_sim_portfolio.json", encoding="utf-8"))["positions"]]
Q20 = [p["code"] for p in json.load(open("_sim_q20_portfolio.json", encoding="utf-8"))["positions"]]
LX_N = [p["name"] for p in json.load(open("_sim_portfolio.json", encoding="utf-8"))["positions"]]
Q20_N = [p["name"] for p in json.load(open("_sim_q20_portfolio.json", encoding="utf-8"))["positions"]]

W_FULL = ("2021-06-01", "2026-08-24")
W_1Y = ("2025-08-25", "2026-08-24")
W_6M = ("2026-02-25", "2026-08-24")
W_SIM = ("2026-08-26", "2026-08-28")

curves = {
    "LX-40 现持": static_ew_curve(LX),
    "Q20-40 现持": static_ew_curve(Q20),
}

# ---------- 2. 基准曲线 ----------
ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))["nav"]
bm_m = json.load(open("_bt_benchmark.json", encoding="utf-8"))  # 中证全指月K {YYYY-MM: close}
bm_first = min(bm_m.values()); bm_last = max(bm_m.values())
BM_M = {k: v / bm_first for k, v in bm_m.items()}


def ew_ret(a, b):
    ds = [d for d in ew if a < d <= b]
    if not ds:
        return 0.0
    return ew[ds[-1]] / ew[max(x for x in ew if x <= a)] - 1.0


def bm_ret(a, b):
    """中证全指月K近似：取 <=b 的最后月与 <=a 的最后月之比 - 1。"""
    ma = max(k for k in BM_M if k <= a[:7])
    mb = max(k for k in BM_M if k <= b[:7])
    return BM_M[mb] / BM_M[ma] - 1.0


# ---------- 3. 汇总 ----------
res = {"curves": {}, "windows": {}, "bt": {}, "sim": {}, "holdings": {}}

for tag, c in curves.items():
    n0 = c[ALL_DATES[0]][1] if ALL_DATES[0] in c else 0
    # 全窗口覆盖检查
    cov = {}
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        ds = [d for d in c if d.startswith(y)]
        n = max((v[1] for v in c.values() if d for d in ds for v in []) ) if False else None
    res["curves"][tag] = {d: {"r": v[0], "n": v[1]} for d, v in c.items()}
    wins = {}
    for wn, (a, b) in [("full", W_FULL), ("1Y", W_1Y), ("6M", W_6M), ("sim_3d", W_SIM)]:
        tot = cumret(c, a, b)
        days = sum(1 for d in c if a < d <= b)
        wins[wn] = {
            "total": round(tot, 4),
            "ann": round(ann_ret(tot, days), 4) if days else None,
            "mdd": round(mdd_curve(c, a, b), 4),
            "days": days,
        }
    wins["yearly"] = yearly(c, *W_FULL)
    res["windows"][tag] = wins

# 基准窗口收益
res["bench_win"] = {
    "ew_full": {"total": round(ew_ret(*W_FULL), 4), "mdd": json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))["mdd"]},
    "ew_1y": {"total": round(ew_ret(*W_1Y), 4)},
    "ew_6m": {"total": round(ew_ret(*W_6M), 4)},
    "bm_full": {"total": round(bm_ret(*W_FULL), 4)},
    "bm_1y": {"total": round(bm_ret(*W_1Y), 4)},
    "bm_6m": {"total": round(bm_ret(*W_6M), 4)},
}

# 回测策略汇总（full 基座）
au = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
full, bms = au["rerun"]["full"], au["benchmarks"]
res["bt"] = {
    k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in full[k].items() if kk != "fin_per_period"}
    for k in ["core", "g30", "g60", "nolimit"]
}
res["bt"]["bm_ew"] = {"total": round(bms["ew_hold"]["total"], 4), "ann": round(bms["ew_hold"]["ann"], 4), "mdd": round(bms["ew_hold"]["mdd"], 4)}
res["bt"]["bm_idx"] = {"total": round(bms["csi_all"]["total"], 4), "mdd": round(bms["csi_all"]["mdd"], 4)}

# 模拟盘账本
res["sim"] = {
    "LX": json.load(open("_sim_nav.json", encoding="utf-8")),
    "Q20": json.load(open("_sim_q20_nav.json", encoding="utf-8")),
}

# 持仓快照
res["holdings"] = {
    "LX": [{"code": c, "name": n} for c, n in zip(LX, LX_N)],
    "Q20": [{"code": c, "name": n} for c, n in zip(Q20, Q20_N)],
}

# 现持静态建仓以来 3 天 vs 模拟盘账本
for tag in ["LX-40 现持", "Q20-40 现持"]:
    print(f"\n=== {tag} ===")
    for wn in ["full", "1Y", "6M", "sim_3d"]:
        w = res["windows"][tag][wn]
        print(f"  {wn:8s} total {w['total']*100:+.2f}%  ann {w['ann']*100 if w['ann'] else None}  mdd {w['mdd']*100:.2f}%  days {w['days']}")
    print("  yearly:", {y: f"{v*100:+.1f}%" for y, v in res['windows'][tag]['yearly'].items()})
print("\n=== 基准 ===")
print("  EW 全A full:", f"{res['bench_win']['ew_full']['total']*100:+.2f}%  1Y {res['bench_win']['ew_1y']['total']*100:+.2f}%  6M {res['bench_win']['ew_6m']['total']*100:+.2f}%")
print("  中证全指 full:", f"{res['bench_win']['bm_full']['total']*100:+.2f}%  1Y {res['bench_win']['bm_1y']['total']*100:+.2f}%  6M {res['bench_win']['bm_6m']['total']*100:+.2f}%")
print("\n=== 模拟盘账本 ===")
for tag, navs in res["sim"].items():
    last = navs[-1]
    print(f"  {tag}: {last['date']} nav {last['nav']:,.0f} cum {last['cum_ret']*100:+.2f}% vs bm {last['bm_cum']*100:+.2f}%")

json.dump(res, open("_cmp_hold_vs_bt.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n→ _cmp_hold_vs_bt.json")
