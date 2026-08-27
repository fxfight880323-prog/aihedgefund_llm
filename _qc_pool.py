# -*- coding: utf-8 -*-
"""_qc_pool.py — 质量池(未切top40) × 估值band分位 推导
1) SQLite 复现 LX-core 筛选的 L6+L4+L5 层（不做 PE 升序 top40 截断）→ 每期质量池
   L6: mv≥100亿 + PE>0 | L4: PE≤25 或 股息率≥2% | L5: 预期增速≤25% 且 0<PEG≤2
2) 用 _bt_band_val/*.parquet (2016-08~2026-04 日频估值) 计算每期每只池内股的
   PB/PE 5年前置分位（与 _bt_band_calc.py 口径一致：窗口[as_of-5y, as_of]，样本≥60）
输出: _qc_pool.json
"""
import json, os, sqlite3, sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/workspace/ai_fund_framework/"
os.chdir(BASE)

PIT_DATES = [
    ("2021-08", "2021-08-31"), ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"), ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"), ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"), ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"), ("2026-04", "2026-04-30"),
]
MIN_N = 60
MV_MIN = 100 * 10000          # 100亿 = 100万(万元)
PE_CEIL, DIV_YIELD = 25.0, 0.02
EXP_G_CEIL, PEG_CEIL = 25.0, 2.0


def load_month(con, month):
    cur = con.cursor()
    cur.execute("select ticker from pit_universe where month=?", (month,))
    univ = [r[0] for r in cur.fetchall()]
    val = {}
    cur.execute("select ticker, pe_ttm, pb, total_mv from valuation where month=?", (month,))
    for tk, pe, pb, mv in cur.fetchall():
        val[tk] = {"pe": pe, "pb": pb, "mv": mv}
    fac = {}
    cur.execute("select ticker, gpm, cetop, npyoy, roes, dtop5 from factor_panel where month=?", (month,))
    for tk, gpm, cetop, npyoy, roes, dtop5 in cur.fetchall():
        # dtop5 异常清洗铁律: >=0.5 置 None
        if dtop5 is not None and dtop5 >= 0.5:
            dtop5 = None
        fac[tk] = {"gpm": gpm, "cetop": cetop, "npyoy": npyoy, "roes": roes, "dtop5": dtop5}
    cons = {}
    cur.execute("select ticker, con_np_yoy, con_peg, con_roe from consensus where month=?", (month,))
    for tk, g, peg, roe in cur.fetchall():
        cons[tk] = {"con_np_yoy": g, "con_peg": peg, "con_roe": roe}
    return univ, val, fac, cons


def screen_pool(univ, val, fac, cons):
    """L6+L4+L5（core 层，无变体质量层、无 top40 截断）"""
    pool = []
    n_drop = {"mv": 0, "pe": 0, "l4": 0, "l5": 0}
    for tk in univ:
        v = val.get(tk) or {}
        f = fac.get(tk) or {}
        c = cons.get(tk) or {}
        mv, pe = v.get("pe") and v.get("mv"), v.get("pe")
        mv = v.get("mv")
        pe = v.get("pe")
        if mv is None or mv < MV_MIN:
            n_drop["mv"] += 1
            continue
        if pe is None or pe <= 0:
            n_drop["pe"] += 1
            continue
        dy = f.get("dtop5")
        l4 = (pe <= PE_CEIL) or (dy is not None and dy >= DIV_YIELD)
        if not l4:
            n_drop["l4"] += 1
            continue
        g = c.get("con_np_yoy")
        peg = c.get("con_peg")
        l5 = (g is not None and g <= EXP_G_CEIL and peg is not None and 0 < peg <= PEG_CEIL)
        if not l5:
            n_drop["l5"] += 1
            continue
        pool.append(tk)
    return pool, n_drop


def main():
    # ---- 1. 合并 band 日频估值 ----
    files = sorted(f for f in os.listdir(BASE + "_bt_band_val") if f.endswith(".parquet"))
    dfs = [pd.read_parquet(BASE + "_bt_band_val/" + f) for f in files]
    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["pb"]).sort_values(["stock_code", "date"]).reset_index(drop=True)
    print(f"band 日频估值: {len(df):,} 行, {df['stock_code'].nunique()} 只, "
          f"{df['date'].min().date()} ~ {df['date'].max().date()}")
    groups = {tk: g for tk, g in df.groupby("stock_code")}

    # ---- 2. 每期筛选 + band 分位 ----
    con = sqlite3.connect(BASE + "data/a_share_market.db")
    out = {}
    union_pool = set()
    for month, as_of_s in PIT_DATES:
        univ, val, fac, cons = load_month(con, month)
        pool, n_drop = screen_pool(univ, val, fac, cons)
        as_of = pd.Timestamp(as_of_s)
        w0 = as_of - pd.DateOffset(years=5)
        band = {}
        miss = 0
        for tk in pool:
            g = groups.get(tk)
            if g is None:
                miss += 1
                continue
            win = g[(g["date"] >= w0) & (g["date"] <= as_of)]
            if len(win) < MIN_N:
                miss += 1
                continue
            anchor = win.iloc[-1]
            pb_now = float(anchor["pb"])
            pb_pct = float((win["pb"] < pb_now).mean() * 100)
            pe_now = float(anchor["pe_ttm"]) if anchor["pe_ttm"] == anchor["pe_ttm"] else None
            pe_pct = None
            if pe_now is not None and pe_now > 0:
                pe_pos = win["pe_ttm"][win["pe_ttm"] > 0]
                if len(pe_pos) > 0:
                    pe_pct = float((pe_pos < pe_now).mean() * 100)
            band[tk] = {"pb": round(pb_now, 3), "pe": round(pe_now, 2) if pe_now else None,
                        "pb_pct": round(pb_pct, 1), "pe_pct": round(pe_pct, 1) if pe_pct is not None else None,
                        "n": int(len(win)), "anchor": str(anchor["date"].date()),
                        "mv_yi": round((val[tk]["mv"] or 0) / 10000, 1),
                        "gpm": fac.get(tk, {}).get("gpm"),
                        "con_roe": cons.get(tk, {}).get("con_roe")}
        union_pool.update(band.keys())
        out[month] = {"as_of": as_of_s, "pool_n": len(pool), "band_n": len(band),
                      "band_miss": miss, "drop": n_drop, "band": band}
        print(f"{month}: 全A {len(univ)} → 池 {len(pool)} (drop {n_drop}) → 有band {len(band)} (缺 {miss})")
    con.close()

    json.dump({"months": out, "union_pool": sorted(union_pool), "n_union": len(union_pool)},
              open(BASE + "_qc_pool.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n质量池 union（有band）: {len(union_pool)} 只 → _qc_pool.json")


if __name__ == "__main__":
    main()
