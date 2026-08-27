# -*- coding: utf-8 -*-
"""生成 _bt_band_report_data.json: 三变体统计 + 分年度 + 金融/非金融贡献拆解 + band 替换明细"""
import json, sys, math
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

BASE = "D:/workspace/ai_fund_framework/"
r = json.load(open(BASE + "_bt_band_results.json", encoding="utf-8"))
fin = json.load(open(BASE + "_bt_sw_fin_universe.json", encoding="utf-8"))
fin_set = set()
for sec, info in fin.items():
    if isinstance(info, dict) and isinstance(info.get("members"), list):
        fin_set.update(info["members"])
prices = json.load(open(BASE + "_bt_winda_prices.json", encoding="utf-8"))
px = pd.DataFrame({tk: dict(m) for tk, m in prices.items()}).sort_index()
hold = r["holdings"]

periods = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
           "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]
T_PERIOD = {p: i for i, p in enumerate(periods)}


def _next_month(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    mm += 1
    if mm > 12:
        y, mm = y + 1, 1
    return f"{y}-{mm:02d}"


BUY_MONTHS = {_next_month(p) for p in periods}
months = [m for m in px.index if m >= "2021-08"]


def nav_of(get_members):
    nav, active, hist = 1.0, [], {}
    series = {}
    for m in months:
        if m in T_PERIOD:
            members, active = active, list(get_members(m))
        elif m in BUY_MONTHS:
            members = []
            for tk in active:
                if tk in px.columns and m in px.index:
                    hist[tk] = px.at[m, tk]
        else:
            members = active
        rs = []
        for tk in members:
            if tk not in px.columns or m not in px.index:
                continue
            cm, pm = px.at[m, tk], hist.get(tk)
            if pm and cm and pd.notna(pm) and pd.notna(cm) and pm > 0:
                rs.append(cm / pm - 1.0)
            hist[tk] = cm
        if rs:
            nav *= 1.0 + sum(rs) / len(rs)
        series[m] = nav
    return series


def annual_stats(series, years):
    """分年度收益: 用年末/年初 nav"""
    out = {}
    all_m = sorted(series.keys())
    for y in years:
        ys = [m for m in all_m if m.startswith(str(y))]
        if len(ys) < 2:
            out[str(y)] = None
            continue
        start = series[all_m[max(0, all_m.index(ys[0]) - 1)]]  # 上一年末(若有)
        end = series[ys[-1]]
        out[str(y)] = end / start - 1.0
    return out


# ---- 引擎 nav (含成本/滑点/buffer) ----
eng_nav = {v: {x["month"]: x["nav"] / 1e6 for x in r["results"][v]["nav"]} for v in
           ["core", "core_finex", "core_finex_band"]}
ew_nav = {x["month"]: x["nav"] / 1e6 for x in r["ew"]["nav"]}
idx_nav = {x["month"]: x["nav"] / 1e6 for x in r["idx"]["nav"]}

years = list(range(2021, 2027))
annual = {v: annual_stats(eng_nav[v], years) for v in eng_nav}
annual["ew"] = annual_stats(ew_nav, years)
annual["idx"] = annual_stats(idx_nav, years)

# ---- 统计 ----
def stats_of(nav):
    vals = [nav[m] for m in sorted(nav)]
    total = vals[-1] / vals[0] - 1
    n = len(vals) - 1
    ann = (vals[-1] / vals[0]) ** (12 / n) - 1 if n > 0 else 0
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return {"total": total, "ann": ann, "mdd": mdd}


stat = {v: stats_of(eng_nav[v]) for v in eng_nav}
stat["ew"] = stats_of(ew_nav)
stat["idx"] = stats_of(idx_nav)
for v in ["core", "core_finex", "core_finex_band"]:
    stat[v]["excess_ew"] = stat[v]["total"] - stat["ew"]["total"]
    stat[v]["excess_idx"] = stat[v]["total"] - stat["idx"]["total"]

# ---- 金融/非金融贡献拆解 (线性) ----
def lin_decomp(get_members):
    """单次遍历同时归组: Σ_m w_fin·r_fin vs Σ_m w_nfin·r_nfin; 单组独存 nav"""
    active, hist = [], {}
    sum_fin = sum_nfin = 0.0
    nav_fin_only = nav_nfin_only = 1.0
    for m in months:
        if m in T_PERIOD:
            members, active = active, list(get_members(m))
        elif m in BUY_MONTHS:
            for tk in active:
                if tk in px.columns and m in px.index:
                    hist[tk] = px.at[m, tk]
            continue
        else:
            members = active
        r_fin, r_nfin, w_fin, w_nfin = [], [], 0, 0
        for tk in members:
            if tk not in px.columns or m not in px.index:
                continue
            cm, pm = px.at[m, tk], hist.get(tk)
            if pm and cm and pd.notna(pm) and pd.notna(cm) and pm > 0:
                rr = cm / pm - 1.0
                if tk in fin_set:
                    r_fin.append(rr)
                else:
                    r_nfin.append(rr)
            hist[tk] = cm
        n = len(r_fin) + len(r_nfin)
        if n > 0:
            w_fin, w_nfin = len(r_fin) / n, len(r_nfin) / n
            r_fin_m = sum(r_fin) / len(r_fin) if r_fin else 0.0
            r_nfin_m = sum(r_nfin) / len(r_nfin) if r_nfin else 0.0
            sum_fin += w_fin * r_fin_m
            sum_nfin += w_nfin * r_nfin_m
            nav_fin_only *= 1.0 + w_fin * r_fin_m
            nav_nfin_only *= 1.0 + w_nfin * r_nfin_m
    return {"sum_fin": sum_fin, "sum_nfin": sum_nfin,
            "nav_fin_only": nav_fin_only - 1, "nav_nfin_only": nav_nfin_only - 1}


decomp = {v: lin_decomp(lambda p, vv=v: hold[p][vv]) for v in
          ["core", "core_finex", "core_finex_band"]}

# ---- band 替换明细 (finex vs finex_band 持仓差异) ----
band_repl = []
for p in periods:
    a, b = set(hold[p]["core_finex"]), set(hold[p]["core_finex_band"])
    repl = sorted(b - a)
    out = sorted(a - b)
    if repl or out:
        band_repl.append({"period": p, "removed": out, "added": repl})
    else:
        band_repl.append({"period": p, "removed": [], "added": []})

# ---- 金融占比时序 ----
fin_share = {p: {"n_fin": sum(1 for t in hold[p]["core"] if t in fin_set),
                 "n_finex": sum(1 for t in hold[p]["core_finex"] if t in fin_set),
                 "n_finex_band": sum(1 for t in hold[p]["core_finex_band"] if t in fin_set)}
             for p in periods}

out = {
    "stat": stat, "annual": annual,
    "eng_nav": eng_nav, "ew_nav": ew_nav, "idx_nav": idx_nav,
    "decomp": decomp, "band_repl": band_repl, "fin_share": fin_share,
    "diag": r["diag"],
    "meta": {"periods": periods, "months": months,
             "core_total": stat["core"]["total"],
             "core_finex_total": stat["core_finex"]["total"],
             "core_finex_band_total": stat["core_finex_band"]["total"]},
}
json.dump(out, open(BASE + "_bt_band_report_data.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("统计:")
for v in ["core", "core_finex", "core_finex_band", "ew", "idx"]:
    s = stat[v]
    print(f"  {v:<16} 总收益 {s['total']:+8.1%}  年化 {s['ann']:+7.2%}  MDD {s['mdd']:7.1%}"
          + (f"  超额EW {s['excess_ew']:+6.1f}pp  超额指数 {s['excess_idx']:+6.1f}pp" if v in
             ["core", "core_finex", "core_finex_band"] else ""))
print("\n分年度(引擎口径):")
hdr = "  月份  " + "".join(f"{v[:12]:>14}" for v in ["core", "core_finex", "core_finex_band", "ew", "idx"])
print(hdr)
for y in years:
    row = f"  {y}  "
    for v in ["core", "core_finex", "core_finex_band", "ew", "idx"]:
        val = annual[v].get(str(y))
        row += f"{val:>+14.1%}" if val is not None else f"{'--':>14}"
    print(row)
print("\n贡献拆解(线性 Σ w·r):")
for v in ["core", "core_finex", "core_finex_band"]:
    d = decomp[v]
    print(f"  {v:<16} 金融 {d['sum_fin']:+.1%}  非金融 {d['sum_nfin']:+.1%}  "
          f"金融独存nav {d['nav_fin_only']:+.1%}  非金融独存nav {d['nav_nfin_only']:+.1%}")
print("\nband 替换明细:")
for br in band_repl:
    if br["removed"]:
        print(f"  {br['period']}: 剔 {br['removed']} → 入 {br['added']}")
print("\n金融占比:")
for p, fs in fin_share.items():
    print(f"  {p}: core {fs['n_fin']}/40  finex {fs['n_finex']}/40  finex_band {fs['n_finex_band']}/40")
print("\n输出 _bt_band_report_data.json")
