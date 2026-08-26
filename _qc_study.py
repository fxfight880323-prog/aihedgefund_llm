# -*- coding: utf-8 -*-
"""_qc_study.py — 高质量公司低估值买入：个股层 + 组合层实证
Part A 个股层（药明康德/美的/宁德，真实数据 2018~2026-08）:
  - PE/PB 自身历史分位（expanding, min 250d；另报 5y 窗口口径）
  - PB 分位区间 × 前瞻 6M 收益（腾讯前复权日K）
  - 低估 episode 识别（PB分位<30% 连续≥10日）→ 入场前瞻 6M/12M
  - 质量轨迹（SQLite factor_panel + consensus, 2021-08~2026-08）
  - dist52
Part B 组合层（LX 质量池 894 只 × 10 期 PIT）:
  - PB 分位 5 分区 × 前瞻 126d 收益（juzi forward_return_126d @ anchor）
  - PE 分位分区（参考口径）
  - 净值模拟：质量池×PB<40 vs 池等权 vs PB>60 vs 中证全指（期边界 adj_close 链式）
  - LX-core 实际持仓的 band 分布与前瞻收益
  - 非金融子集稳健性
输出: _qc_results.json
口径: PIT 池 = 万得全A as_of 成分; band = 自身 5y 日频分位; 前瞻收益=复权价口径;
      无成本无滑点(与含成本回测对比时须标注)
"""
import json, os, sqlite3, sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/workspace/ai_fund_framework/"
os.chdir(BASE)

CASE = {"603259.SH": "药明康德", "000333.SZ": "美的集团", "300750.SZ": "宁德时代"}
PIT_DATES = [
    ("2021-08", "2021-08-31"), ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"), ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"), ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"), ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"), ("2026-04", "2026-04-30"),
]
ZONES = [(0, 20, "0-20"), (20, 40, "20-40"), (40, 60, "40-60"),
         (60, 80, "60-80"), (80, 101, "80-100")]


def zone_of(pct):
    if pct is None:
        return None
    for lo, hi, name in ZONES:
        if lo <= pct < hi:
            return name
    return None


# ============================================================
# Part A 个股层
# ============================================================
def part_a():
    val = pd.read_parquet("_qc_valuation.parquet")
    val["date"] = pd.to_datetime(val["date"])
    daily = json.load(open("_qc_daily.json", encoding="utf-8"))
    quote = json.load(open("_qc_quote.json", encoding="utf-8"))
    out = {}
    for code, name in CASE.items():
        g = val[val["stock_code"] == code].sort_values("date").reset_index(drop=True)
        pb = g["pb"].values
        pe = g["pe_ttm"].values
        dates = [str(d.date()) for d in g["date"]]
        n = len(g)

        # expanding 分位（min 250 交易日）
        pb_pct = [None] * n
        pe_pct = [None] * n
        for i in range(n):
            if i < 250:
                continue
            hist_pb = pb[:i + 1]
            pb_pct[i] = float((hist_pb < pb[i]).mean() * 100)
            if pe[i] is not None and not np.isnan(pe[i]) and pe[i] > 0:
                hist_pe = [x for x in pe[:i + 1] if x is not None and not np.isnan(x) and x > 0]
                if len(hist_pe) >= 100:
                    pe_pct[i] = float(sum(1 for x in hist_pe if x < pe[i]) / len(hist_pe) * 100)

        # 5y 窗口分位（band 报告口径）
        def pct_5y(series, cur):
            s = pd.Series([x for x in series[-1250:] if x is not None and not np.isnan(x) and x > 0])
            if len(s) == 0 or cur is None or np.isnan(cur) or cur <= 0:
                return None
            return float((s < cur).mean() * 100)

        cur_pb, cur_pe = pb[-1], pe[-1]
        pb_pct5 = pct_5y(pb, cur_pb)  # PB>0 基本恒真
        pe_pct5 = pct_5y(pe, cur_pe)

        # 日K（前复权 close 序列，与估值日期对齐）
        dk = daily[code]
        kdates = sorted(dk.keys())
        closes = [dk[d]["close"] for d in kdates]
        # dist52
        dist52 = None
        if len(closes) >= 252:
            hi52 = max(closes[-252:])
            dist52 = round((1 - closes[-1] / hi52) * 100, 1)

        # 分位区间 × 前瞻 6M/12M（用日K）
        def fwd_ret(i, days):
            j = i + days
            if j >= len(kdates):
                return None
            return closes[j] / closes[i] - 1

        zone_stats = {}
        for lo, hi, zn in ZONES:
            r6, r12 = [], []
            for i in range(n):
                z = zone_of(pb_pct[i])
                if z == zn:
                    f6 = fwd_ret(i, 126)
                    f12 = fwd_ret(i, 252)
                    if f6 is not None:
                        r6.append(f6)
                    if f12 is not None:
                        r12.append(f12)
            if r6:
                zone_stats[zn] = {
                    "n6": len(r6), "mean6": float(np.mean(r6)), "med6": float(np.median(r6)),
                    "win6": float(np.mean([1 if x > 0 else 0 for x in r6])),
                    "n12": len(r12),
                    "mean12": float(np.mean(r12)) if r12 else None,
                    "win12": float(np.mean([1 if x > 0 else 0 for x in r12])) if r12 else None,
                }
            else:
                zone_stats[zn] = {"n6": 0}

        # 低估 episode: pb_pct<30 连续≥10 交易日
        episodes = []
        i = 0
        while i < n:
            if pb_pct[i] is not None and pb_pct[i] < 30:
                j = i
                while j < n and pb_pct[j] is not None and pb_pct[j] < 30:
                    j += 1
                if j - i >= 10:
                    # entry = episode 第一个交易日, 用日K前瞻
                    # 找 kdates 中 >= dates[i] 的索引
                    ki = next((k for k, d in enumerate(kdates) if d >= dates[i]), None)
                    if ki is not None:
                        f6 = fwd_ret(ki, 126)
                        f12 = fwd_ret(ki, 252)
                        # episode 期间最低 PB 分位
                        minpct = min(x for x in pb_pct[i:j] if x is not None)
                        minpb = min(pb[i:j])
                        episodes.append({
                            "start": dates[i], "end": dates[j - 1], "days": j - i,
                            "pb_start": round(float(pb[i]), 2), "pe_start": round(float(pe[i]), 2) if pe[i] == pe[i] else None,
                            "pb_pct_min": round(minpct, 1), "pb_min": round(float(minpb), 2),
                            "fwd6m": round(float(f6) * 100, 1) if f6 is not None else None,
                            "fwd12m": round(float(f12) * 100, 1) if f12 is not None else None,
                        })
                i = j
            else:
                i += 1

        out[code] = {
            "name": name,
            "current": {
                "date": dates[-1], "price": closes[-1],
                "pe": round(float(cur_pe), 2) if cur_pe == cur_pe else None,
                "pb": round(float(cur_pb), 2),
                "pe_pct_hist": round(pe_pct[-1], 1) if pe_pct[-1] is not None else None,
                "pb_pct_hist": round(pb_pct[-1], 1),
                "pe_pct_5y": round(pe_pct5, 1) if pe_pct5 is not None else None,
                "pb_pct_5y": round(pb_pct5, 1),
                "dist52_pct": dist52,
                "total_mv_yi": quote.get(code, {}).get("total_mv_yi"),
            },
            "n_days": n, "first": dates[0],
            "zone_stats": zone_stats,
            "episodes": episodes,
        }
        cur = out[code]["current"]
        print(f"{name} {code}: 现价 {cur['price']} PE {cur['pe']}({cur['pe_pct_hist']}%分位) "
              f"PB {cur['pb']}({cur['pb_pct_hist']}%分位/5y {cur['pb_pct_5y']}%) dist52 {dist52}% "
              f"| episodes {len(episodes)}")
        for e in episodes:
            print(f"   {e['start']}~{e['end']} ({e['days']}d) PB {e['pb_start']} 分位低至 {e['pb_pct_min']}% "
                  f"→ 6M {e['fwd6m']}% 12M {e['fwd12m']}%")

    # 质量轨迹（SQLite）
    con = sqlite3.connect(BASE + "data/a_share_market.db")
    cur = con.cursor()
    for code in CASE:
        rows = []
        cur.execute("select month, gpm, roes, cetop, npyoy from factor_panel where ticker=? order by month", (code,))
        fac = {r[0]: r for r in cur.fetchall()}
        cur.execute("select month, con_roe, con_np_yoy, con_peg from consensus where ticker=? order by month", (code,))
        cons = {r[0]: r for r in cur.fetchall()}
        for m in sorted(fac.keys()):
            f, c = fac[m], cons.get(m, (None, None, None))
            rows.append({"month": m, "gpm": f[1], "roes": f[2], "cetop": f[3],
                         "npyoy": f[4], "con_roe": c[0], "con_np_yoy": c[1], "con_peg": c[2]})
        out[code]["quality_trend"] = rows
    con.close()
    return out


# ============================================================
# Part B 组合层
# ============================================================
def part_b():
    pool = json.load(open("_qc_pool.json", encoding="utf-8"))["months"]
    ret = pd.read_parquet("_qc_ret.parquet")
    ret["date"] = ret["date"].astype(str)
    # 每股: date -> (adj_close, fwd126, fwd252)
    by_stock = {}
    for tk, gdf in ret.groupby("stock_code"):
        g = gdf.sort_values("date")
        by_stock[tk] = {r["date"]: (r["adj_close"], r["forward_return_126d"], r["forward_return_252d"])
                        for _, r in g.iterrows()}
    all_dates = sorted(ret["date"].unique())

    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dates = sorted(idx.keys())

    # 金融名单
    fin = set()
    try:
        d = json.load(open("_bt_sw_fin_universe.json", encoding="utf-8"))
        for sec, info in d.items():
            if isinstance(info, dict) and isinstance(info.get("members"), list):
                fin.update(info["members"])
    except Exception:
        pass

    core_w = json.load(open("_bt_band_results.json", encoding="utf-8"))["weights"]["core"]

    def idx_fwd(anchor, days=126):
        if anchor not in idx_dates:
            cand = [d for d in idx_dates if d <= anchor]
            if not cand:
                return None
            anchor = cand[-1]
        i = idx_dates.index(anchor)
        j = i + days
        if j >= len(idx_dates):
            return None
        return idx[idx_dates[j]]["close"] / idx[idx_dates[i]]["close"] - 1

    zone_pooled = {}      # zone -> [fwd126]
    zone_pooled_nf = {}   # 非金融
    zone_pooled_fin = {}
    pe_zone_pooled = {}
    dual_low, dual_rest = [], []
    per_period = []
    nav_rows = []         # 组合净值模拟（期边界）
    core_rows = []

    months = [m for m, _ in PIT_DATES]
    for pi, (month, as_of) in enumerate(PIT_DATES):
        band = pool[month]["band"]
        anchor_dates = {v["anchor"] for v in band.values()}
        # anchor = 多数股票的锚点日（≤as_of 最近交易日）
        anchor = max(anchor_dates) if anchor_dates else as_of
        # 期边界（净值模拟）
        entry = next((d for d in all_dates if d > as_of), None)
        nxt_as_of = PIT_DATES[pi + 1][1] if pi + 1 < len(PIT_DATES) else "9999-99-99"
        exit_d = next((d for d in all_dates if d > nxt_as_of), None) if pi + 1 < len(PIT_DATES) else all_dates[-1]

        period = {"month": month, "as_of": as_of, "anchor": anchor,
                  "pool_n": len(band), "zones": {}, "pool_avg": None, "idx_fwd": None,
                  "core_fwd": None, "core_zone_dist": {}, "nav": None}
        fwd_all = []
        zone_fwd = {zn: [] for _, _, zn in ZONES}
        pe_zone_fwd = {zn: [] for _, _, zn in ZONES}
        for tk, v in band.items():
            d = by_stock.get(tk, {}).get(anchor)
            if d is None:
                # 锚点日无数据（停牌等）→ 5 日内最近
                for off in range(1, 6):
                    dd = [x for x in all_dates if x <= anchor][-1 - off] if len(all_dates) > off else None
                    if dd and dd in by_stock.get(tk, {}):
                        d = by_stock[tk][dd]
                        break
            if d is None or d[1] is None or (isinstance(d[1], float) and np.isnan(d[1])):
                continue
            f6 = float(d[1])
            fwd_all.append(f6)
            zn = zone_of(v["pb_pct"])
            if zn:
                zone_fwd[zn].append(f6)
                zone_pooled.setdefault(zn, []).append(f6)
                if tk in fin:
                    zone_pooled_fin.setdefault(zn, []).append(f6)
                else:
                    zone_pooled_nf.setdefault(zn, []).append(f6)
            pzn = zone_of(v["pe_pct"])
            if pzn:
                pe_zone_fwd[pzn].append(f6)
                pe_zone_pooled.setdefault(pzn, []).append(f6)
            if v["pb_pct"] is not None and v["pb_pct"] < 30 and v["pe_pct"] is not None and v["pe_pct"] < 30:
                dual_low.append(f6)
            else:
                dual_rest.append(f6)

        period["pool_avg"] = float(np.mean(fwd_all)) if fwd_all else None
        period["idx_fwd"] = idx_fwd(anchor)
        for zn in zone_fwd:
            period["zones"][zn] = {"n": len(zone_fwd[zn]),
                                   "mean": float(np.mean(zone_fwd[zn])) if zone_fwd[zn] else None}
        period["pe_zones"] = {zn: {"n": len(pe_zone_fwd[zn]),
                                   "mean": float(np.mean(pe_zone_fwd[zn])) if pe_zone_fwd[zn] else None}
                              for zn in pe_zone_fwd}

        # LX-core 持仓前瞻
        core_list = list(core_w.get(month, {}).keys())
        cf = []
        for tk in core_list:
            v = band.get(tk)
            d = by_stock.get(tk, {}).get(anchor)
            if d is None or v is None or d[1] is None or (isinstance(d[1], float) and np.isnan(d[1])):
                continue
            cf.append((tk, float(d[1]), v["pb_pct"]))
        if cf:
            period["core_fwd"] = float(np.mean([x[1] for x in cf]))
            dist = {}
            for _, _, p in cf:
                zn = zone_of(p)
                if zn:
                    dist[zn] = dist.get(zn, 0) + 1
            period["core_zone_dist"] = dist
            core_rows.append({"month": month, "n": len(cf), "fwd": period["core_fwd"],
                              "pool_avg": period["pool_avg"], "dist": dist})

        # 净值模拟：期边界 adj_close
        if entry and exit_d:
            def port_ret(members):
                rs = []
                for tk in members:
                    m = by_stock.get(tk, {})
                    a, b = m.get(entry), m.get(exit_d)
                    if a and b and a[0] and b[0] and a[0] > 0:
                        rs.append(b[0] / a[0] - 1)
                return float(np.mean(rs)) if rs else None, len(rs)

            low_members = [tk for tk, v in band.items() if v["pb_pct"] is not None and v["pb_pct"] < 40]
            high_members = [tk for tk, v in band.items() if v["pb_pct"] is not None and v["pb_pct"] > 60]
            r_low, n_low = port_ret(low_members)
            r_high, n_high = port_ret(high_members)
            r_pool, n_pool = port_ret(list(band.keys()))
            r_core, n_core = port_ret(core_list)
            r_idx = idx[exit_d]["close"] / idx[entry]["close"] - 1 if exit_d in idx and entry in idx else None
            period["nav"] = {"entry": entry, "exit": exit_d, "partial": pi == len(PIT_DATES) - 1,
                             "low40": {"ret": r_low, "n": n_low},
                             "high60": {"ret": r_high, "n": n_high},
                             "pool_ew": {"ret": r_pool, "n": n_pool},
                             "core": {"ret": r_core, "n": n_core},
                             "idx": r_idx}
            nav_rows.append(period["nav"])
        per_period.append(period)
        zs = {zn: (f"{np.mean(zone_fwd[zn]):+.1%}" if zone_fwd[zn] else "—") for zn in zone_fwd}
        pa = f"{period['pool_avg']:+.1%}" if period["pool_avg"] is not None else "—"
        ia = f"{period['idx_fwd']:+.1%}" if period["idx_fwd"] is not None else "—"
        cf = f"{period['core_fwd']:+.1%}" if period["core_fwd"] is not None else "—"
        print(f"{month}: 池{len(band)} 均值{pa} 指数{ia} | 分区 {zs} | core {cf}")

    def agg(lst):
        if not lst:
            return None
        return {"n": len(lst), "mean": float(np.mean(lst)), "med": float(np.median(lst)),
                "win": float(np.mean([1 if x > 0 else 0 for x in lst]))}

    summary = {
        "pb_zones": {zn: agg(zone_pooled.get(zn, [])) for _, _, zn in ZONES},
        "pb_zones_nonfin": {zn: agg(zone_pooled_nf.get(zn, [])) for _, _, zn in ZONES},
        "pb_zones_fin": {zn: agg(zone_pooled_fin.get(zn, [])) for _, _, zn in ZONES},
        "pe_zones": {zn: agg(pe_zone_pooled.get(zn, [])) for _, _, zn in ZONES},
        "dual_low": agg(dual_low), "dual_rest": agg(dual_rest),
    }
    # pool_all: 每期等权（期均值再平均）
    pool_period_avgs = [p["pool_avg"] for p in per_period if p["pool_avg"] is not None]
    summary["pool_all"] = {"n": len(pool_period_avgs),
                           "mean": float(np.mean(pool_period_avgs)) if pool_period_avgs else None}
    idx_period = [p["idx_fwd"] for p in per_period if p["idx_fwd"] is not None]
    summary["idx_all"] = {"n": len(idx_period),
                          "mean": float(np.mean(idx_period)) if idx_period else None}
    core_period = [r["fwd"] for r in core_rows]
    summary["core_all"] = {"n": len(core_period),
                           "mean": float(np.mean(core_period)) if core_period else None}

    # 净值链
    def chain(key):
        nav, rows = 1.0, []
        for nr in nav_rows:
            r = nr.get(key)
            r = r["ret"] if isinstance(r, dict) else r
            if r is None:
                rows.append(None)
                continue
            nav *= (1 + r)
            rows.append(nav)
        return {"final": nav - 1, "series": rows}

    navs = {k: chain(k) for k in ["low40", "high60", "pool_ew", "core", "idx"]}
    print("\n== 净值模拟（期边界, 无成本, 2021-09 ~ 2026-08） ==")
    for k, v in navs.items():
        print(f"  {k}: {v['final']:+.1%}")

    # 三只案例股的框架视角
    case_in_pool = {}
    for code, name in CASE.items():
        rows = []
        for month, as_of in PIT_DATES:
            v = pool[month]["band"].get(code)
            if not v:
                rows.append({"month": month, "in_pool": False})
                continue
            d = by_stock.get(code, {}).get(v["anchor"])
            f6 = float(d[1]) if d and d[1] is not None and not np.isnan(d[1]) else None
            rows.append({"month": month, "in_pool": True, "pe": v["pe"], "pb": v["pb"],
                         "pb_pct": v["pb_pct"], "pe_pct": v["pe_pct"], "fwd126": f6})
        case_in_pool[code] = rows

    return {"per_period": per_period, "summary": summary, "navs": navs,
            "nav_rows": nav_rows, "core_rows": core_rows, "case_in_pool": case_in_pool,
            "n_fin": len(fin)}


if __name__ == "__main__":
    A = part_a()
    B = part_b()
    json.dump({"part_a": A, "part_b": B, "generated": "2026-08-26",
               "pit_dates": PIT_DATES},
              open("_qc_results.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("\nsaved _qc_results.json")
