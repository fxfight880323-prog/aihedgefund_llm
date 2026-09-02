# -*- coding: utf-8 -*-
"""低PE因子10年稳健性检验 — 横截面PE分位组合回测（2016-08 ~ 2026-04，半年调仓）。

回答：「银行金融低估值PE的收益，是时代给予（2021后价值回归），还是长期有效？」

设计（前复权月K，半年调仓，无成本，等权）:
  池子 = 万得全A(881001.WI) PIT 成分（20期）
  信号 = pe_ttm（估值面板，PIT）
  组合:
    Q1~Q5     按 pe_ttm 升序分5组（各20%），等权持有
    lowpe40    pe_ttm 升序 top40（对应 g60 的持仓结构，但不含 garp 门控）
    EW         全部有效 pe_ttm 成分等权（基准）
    CSI        中证全指 000985.SH（价格基准，无分红）
  拆分: Q1 / lowpe40 内金融 vs 非金融（静态申万金融名单）
  分段: 2016-2020 vs 2021-2026

口径诚实标注:
  - 月频前复权(qfqmonth) + 月末撮合，非日频T+1；与 g60 日频口径有偏差，用5年重叠区校准
  - 无交易成本（分位组合多空差分对成本不敏感，方向性结论稳健）
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

UNIV_FILE = "_bt_lowpe_10y_universe.json"
VAL_FILE = "_bt_lowpe_10y_valuation.json"
PX_FILE = "_bt_lowpe_10y_px.json"
IDX_FILE = "_bt_lowpe_10y_idx.json"
FIN_FILE = "_bt_sw_fin_universe.json"

PIT = [
    ("2016-08", "2016-08-31"), ("2017-04", "2017-04-30"),
    ("2017-08", "2017-08-31"), ("2018-04", "2018-04-30"),
    ("2018-08", "2018-08-31"), ("2019-04", "2019-04-30"),
    ("2019-08", "2019-08-31"), ("2020-04", "2020-04-30"),
    ("2020-08", "2020-08-31"), ("2021-04", "2021-04-30"),
    ("2021-08", "2021-08-31"), ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"), ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"), ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"), ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"), ("2026-04", "2026-04-30"),
]

N_QUANTILE = 5
TOP_N = 40


def load_fin():
    d = json.load(open(FIN_FILE, encoding="utf-8"))
    fin = set()
    for grp in ("银行", "非银金融"):
        if grp in d:
            fin.update(d[grp].get("members", []))
    return fin


def period_close(pxtk, asof):
    """取某只股票在 as_of 当月（或之前最近）的前复权月K收盘价。"""
    dates = sorted(pxtk.keys())
    cand = [dt for dt in dates if dt <= asof]
    if not cand:
        return None
    return pxtk[cand[-1]]


def main():
    print("=" * 88)
    print("  低PE因子10年稳健性检验（前复权月K，半年调仓，等权，无成本）")
    print("=" * 88)

    univ = json.load(open(UNIV_FILE, encoding="utf-8"))
    val = json.load(open(VAL_FILE, encoding="utf-8"))
    px = json.load(open(PX_FILE, encoding="utf-8"))
    idx = json.load(open(IDX_FILE, encoding="utf-8"))
    fin = load_fin()
    print(f"  成分期数 {len(univ)} | 估值期数 {len(val)} | 月K {len(px)} 只 | 金融名单 {len(fin)} 只")

    # 每期选股 + 分位
    # period_pick[month] = {q1:[tk..], q2:[..], .., q5:[..], top40:[..], ew:[..]}
    period = {}
    for month, as_of in PIT:
        if month not in univ or month not in val:
            continue
        members = univ[month]["members"]
        recs = {r["stock_code"]: r for r in val[month]["records"]}
        rows = []
        for tk in members:
            r = recs.get(tk)
            pe = r.get("pe_ttm") if r else None
            if pe is None or pe != pe or pe <= 0:  # pe != pe 过滤 NaN
                continue
            rows.append((tk, pe))
        rows.sort(key=lambda x: x[1])
        n = len(rows)
        if n < N_QUANTILE:
            continue
        qs = defaultdict(list)
        for i, (tk, pe) in enumerate(rows):
            q = min(i * N_QUANTILE // n, N_QUANTILE - 1)
            qs[f"q{q+1}"].append(tk)
        period[month] = {
            "as_of": as_of, "n": n,
            "q1": qs["q1"], "q2": qs["q2"], "q3": qs["q3"],
            "q4": qs["q4"], "q5": qs["q5"],
            "top40": [tk for tk, _ in rows[:TOP_N]],
            "ew": [tk for tk, _ in rows],
        }

    months = [m for m, _ in PIT if m in period]
    print(f"  有效调仓期 {len(months)} 期: {months[0]} ~ {months[-1]}")

    # 组合净值序列（半年调仓，月K撮合）
    # 每个组合返回 {date: nav} 序列，date 为各调仓期月末
    combos = ["q1", "q2", "q3", "q4", "q5", "top40", "ew"]

    def combo_nav(name):
        nav = {}
        prev_close = None
        for mi, month in enumerate(months):
            asof = period[month]["as_of"]
            toks = period[month][name]
            # 本期入场价（as_of 月 close 均值）
            cs = []
            for tk in toks:
                pxtk = px.get(tk)
                if not pxtk:
                    continue
                c = period_close(pxtk, asof)
                if c:
                    cs.append(c)
            if not cs:
                continue
            cur = sum(cs) / len(cs)  # 等权，用 close 均值近似（各股收益的算术平均）
            # 更准确：用每只股相对上期价格算收益。这里用"组合平均价"会在换股时引入偏差。
            # 改为：记录每只股的本期价，下期算每只股收益再平均。
            nav[asof] = cur
        return nav

    # 更准确的收益计算：逐段算每只股收益再等权平均（避免换股时价格水平不连续）
    def combo_ret(name):
        segs = []  # (start_date, end_date, ret)
        for mi in range(len(months) - 1):
            m0, m1 = months[mi], months[mi + 1]
            a0, a1 = period[m0]["as_of"], period[m1]["as_of"]
            toks = period[m0][name]
            rs = []
            for tk in toks:
                pxtk = px.get(tk)
                if not pxtk:
                    continue
                c0 = period_close(pxtk, a0)
                c1 = period_close(pxtk, a1)
                if c0 and c1 and c0 > 0:
                    rs.append(c1 / c0 - 1)
            if rs:
                segs.append((a0, a1, sum(rs) / len(rs), len(rs)))
        return segs

    print("\n  计算各组合分段收益...")
    combos_ret = {name: combo_ret(name) for name in combos}

    # 中证全指同期
    def idx_ret():
        segs = []
        for mi in range(len(months) - 1):
            a0, a1 = period[months[mi]]["as_of"], period[months[mi + 1]]["as_of"]
            d0 = [d for d in sorted(idx) if d <= a0]
            d1 = [d for d in sorted(idx) if d <= a1]
            if d0 and d1:
                c0, c1 = idx[d0[-1]], idx[d1[-1]]
                if c0 > 0:
                    segs.append((a0, a1, c1 / c0 - 1, 1))
        return segs
    idx_segs = idx_ret()

    # 逐段 → 净值
    def segs_to_nav(segs, start_nav=1.0):
        navs = [(segs[0][0], start_nav)]
        cur = start_nav
        for s0, s1, r, _n in segs:
            cur *= (1 + r)
            navs.append((s1, cur))
        return navs

    def yearly(nav_list):
        d = {d: n for d, n in nav_list}
        dts = sorted(d)
        years = sorted(set(dt[:4] for dt in dts))
        out, prev_end = {}, None
        for y in years:
            y_dts = [dt for dt in dts if dt[:4] == y]
            end = d[y_dts[-1]]
            out[y] = end / d[y_dts[0]] - 1 if prev_end is None else end / prev_end - 1
            prev_end = end
        return out

    results = {}
    for name in combos:
        navs = segs_to_nav(combos_ret[name])
        total = navs[-1][1] / navs[0][1] - 1
        yrs = yearly(navs)
        results[name] = {"total": total, "yearly": yrs, "nav": navs}
    idx_navs = segs_to_nav(idx_segs)
    results["csi"] = {"total": idx_navs[-1][1] / idx_navs[0][1] - 1,
                      "yearly": yearly(idx_navs), "nav": idx_navs}

    # 多空（Q1 - Q5）逐年
    ls_yearly = {}
    yset = sorted(set(results["q1"]["yearly"]) | set(results["q5"]["yearly"]))
    for y in yset:
        ls_yearly[y] = results["q1"]["yearly"].get(y, 0) - results["q5"]["yearly"].get(y, 0)

    # 金融/非金融拆分（Q1 内 和 top40 内，逐段）
    def fin_split(name):
        segs = []
        for mi in range(len(months) - 1):
            m0, m1 = months[mi], months[mi + 1]
            a0, a1 = period[m0]["as_of"], period[m1]["as_of"]
            toks = period[m0][name]
            f, nf = [], []
            for tk in toks:
                pxtk = px.get(tk)
                if not pxtk:
                    continue
                c0, c1 = period_close(pxtk, a0), period_close(pxtk, a1)
                if c0 and c1 and c0 > 0:
                    (f if tk in fin else nf).append(c1 / c0 - 1)
            segs.append({"a0": a0, "a1": a1,
                         "fin_ret": sum(f) / len(f) if f else None,
                         "nonfin_ret": sum(nf) / len(nf) if nf else None,
                         "fin_n": len(f), "nonfin_n": len(nf)})
        return segs

    q1_split = fin_split("q1")
    top40_split = fin_split("top40")

    # 金融浓度（每期 top40 和 q1 金融占比）
    fin_conc = {}
    for month in months:
        q1_toks = period[month]["q1"]
        top_toks = period[month]["top40"]
        fin_conc[month] = {
            "q1_fin": sum(1 for t in q1_toks if t in fin) / max(len(q1_toks), 1),
            "top40_fin": sum(1 for t in top_toks if t in fin) / max(len(top_toks), 1),
        }

    # 分段累计
    def seg_total(nav_list, y0, y1):
        d = {dt: n for dt, n in nav_list}
        dts = sorted(dt for dt in d if y0 <= dt[:4] <= y1)
        if not dts:
            return None
        return d[dts[-1]] / d[dts[0]] - 1

    segments = {}
    for name in combos + ["csi"]:
        navs = results[name]["nav"]
        segments[name] = {
            "2016-2020": seg_total(navs, "2016", "2020"),
            "2021-2026": seg_total(navs, "2021", "2026"),
        }

    # 锚点校准（5年重叠区：top40 月频 vs 日频 g60）
    audit = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
    g60_daily = audit["rerun"]["full"]["g60"]["total"]  # +0.6701
    # 月频 top40 在 2021-08 ~ 2026-04 的累计
    top40_nav = results["top40"]["nav"]
    d = {dt: n for dt, n in top40_nav}
    dts = sorted(dt for dt in d if dt >= "2021-08")
    top40_monthly_5y = d[dts[-1]] / d[dts[0]] - 1 if dts else None

    out = {
        "meta": {
            "window": f"{months[0]} ~ {months[-1]}",
            "n_periods": len(months),
            "price": "前复权月K(qfqmonth) 月末撮合",
            "cost": "无成本",
            "note": "低PE分位组合，方向性结论稳健；绝对收益需标注月频口径偏差",
        },
        "results": {k: {"total": v["total"], "yearly": v["yearly"]}
                    for k, v in results.items()},
        "longshort_q1q5": ls_yearly,
        "fin_split_q1": q1_split,
        "fin_split_top40": top40_split,
        "fin_conc": fin_conc,
        "segments": segments,
        "calib": {
            "g60_daily_5y": g60_daily,
            "top40_monthly_5y": top40_monthly_5y,
            "gap_pp": (top40_monthly_5y - g60_daily) * 100 if top40_monthly_5y is not None else None,
        },
    }
    json.dump(out, open("_bt_lowpe_10y_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---- 控制台摘要 ----
    print("\n" + "=" * 88)
    print("  10年累计收益（前复权月K，半年调仓）")
    print("=" * 88)
    years = sorted(set(y for k in results for y in results[k]["yearly"]))
    hdr = "%-8s" % "组合" + "".join("%9s" % y for y in years) + "%10s" % "累计"
    print(hdr)
    order = ["q1", "q2", "q3", "q4", "q5", "top40", "ew", "csi"]
    for name in order:
        r = results[name]
        row = "%-8s" % name
        for y in years:
            row += "%9.1f" % (r["yearly"].get(y, 0) * 100)
        row += "%10.1f" % (r["total"] * 100)
        print(row)
    print("\nQ1-Q5 多空逐年:")
    print("  " + "  ".join(f"{y}:{v*100:+.1f}pp" for y, v in sorted(ls_yearly.items())))
    print("\n分段累计:")
    for name in order:
        s = segments[name]
        print(f"  {name:8s} 2016-2020 {s['2016-2020']*100 if s['2016-2020'] is not None else float('nan'):+7.1f}%  "
              f"2021-2026 {s['2021-2026']*100 if s['2021-2026'] is not None else float('nan'):+7.1f}%")
    print(f"\n校准: g60日频5年 +{g60_daily*100:.1f}% | top40月频5年 "
          f"+{top40_monthly_5y*100:.1f}% | 偏差 {out['calib']['gap_pp']:+.1f}pp")
    print("\n→ _bt_lowpe_10y_results.json")


if __name__ == "__main__":
    main()
