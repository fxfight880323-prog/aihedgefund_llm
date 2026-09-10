# -*- coding: utf-8 -*-
"""最新持仓建议 —— 严格复用回测框架 screen_q20 口径 + 最新 2026-08 数据。

修正点（相对旧 _holdings_today.py）：
  1. 数据源：直接读 SQLite 最新月份（2026-08），而非只到 2026-04 的 JSON 快照。
  2. 口径：严格复用 _bt_q20_pareto.screen_q20（含市值/PE上限或股息/PEG/预期增速 5 道门槛，
     q_score = (gpm_pct + con_roe_pct + cetop_pct)/3 截面分位），不再是 npyoy+roes+gpm 原始值相加。
  3. 动量 gate：用回测同款日 K（_bt_daily_px_full.json，530 只核心票），
     而非 monthly_close 全市场近似。

输出：AD_top15_mom60top50 当前截面持仓（asof = 2026-08）。
"""
import sys, os, json, bisect, sqlite3
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_q20_pareto as P
from _bt_garp_decompose import load_bars

DB = "D:/workspace/ai_fund_framework/data/a_share_market.db"


def load_month_from_db(month):
    """从 SQLite 读指定月份的 pit_universe/valuation/factor_panel/consensus。
    返回 (univ_list, val_dict, fac_dict, cons_dict)，字段名与 screen_q20 对齐。"""
    db = sqlite3.connect(DB)
    members = [r[0] for r in db.execute(
        "SELECT ticker FROM pit_universe WHERE month=? ORDER BY ticker", (month,)).fetchall()]

    def _map(table, cols):
        d = {}
        q = f"SELECT ticker,{','.join(cols)} FROM {table} WHERE month=?"
        for row in db.execute(q, (month,)).fetchall():
            d[row[0]] = dict(zip(cols, row[1:]))
        return d

    val = _map("valuation", ["total_mv", "pe_ttm"])
    fac = _map("factor_panel", ["dtop5", "gpm", "cetop", "oryoy", "npyoy"])
    cons = _map("consensus", ["con_np_yoy", "con_peg", "con_roe"])
    db.close()
    return members, val, fac, cons


def main():
    month = "2026-08"
    asof = "2026-08-31"

    print("=" * 88)
    print("  最新持仓建议 · AD_top15_mom60top50（严格回测口径 + 最新数据）")
    print("=" * 88)

    members, val, fac, cons = load_month_from_db(month)
    print(f"[PIT {month}] 万得全A 成分: {len(members)} 只")

    # 1. 严格复用回测 screen_q20
    base_pool = P.screen_q20(month, members, val, fac, cons)
    print(f"screen_q20 后 base pool: {len(base_pool)} 只")

    # 2. 动量（回测同款日 K）
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    mom, elig = P.build_mom_series(bars, all_dates, asof)
    m60_vals = sorted([v["mom60"] for v in mom.values() if v["mom60"] is not None])
    mom60_pct = {}
    for tk, v in mom.items():
        if v["mom60"] is not None and m60_vals:
            pos = bisect.bisect_left(m60_vals, v["mom60"])
            mom60_pct[tk] = pos / len(m60_vals) * 100.0
    ctx = {"mom": mom, "mom60_pct": mom60_pct}
    print(f"日 K 动量覆盖: {len(mom)} 只（asof={asof}，最新交易日 {elig[-1] if elig else 'N/A'}）")

    # 3. mom60_top50 gate
    gated = [s for s in base_pool if P.GATES["mom60_top50"](s, ctx)]
    print(f"gate (mom60 截面分位>50) 后: {len(gated)} 只")

    # 4. top15 + cap8
    picked = sorted(gated, key=lambda s: -s["blend"])[:15]
    w = P.cap_weight(picked, 0.08)
    print(f"top15: {len(picked)} 只")

    # 名字映射
    names = {}
    try:
        names = json.load(open("_bt_band_names.json", encoding="utf-8"))
    except Exception:
        pass

    holdings = []
    for s in picked:
        tk = s["tk"]
        v = val.get(tk, {})
        f = fac.get(tk, {})
        c = cons.get(tk, {})
        mom_pct = mom60_pct.get(tk, 0)
        mom60 = mom.get(tk, {}).get("mom60") if tk in mom else None
        holdings.append({
            "ticker": tk,
            "name": names.get(tk, "") if isinstance(names, dict) else "",
            "pe_ttm": v.get("pe_ttm"),
            "total_mv_yi": (L._num(v.get("total_mv")) or 0) / 10000,
            "pe_pct": round(s["pe_pct"], 1),
            "q_score": round(s["q_score"], 1),
            "blend": round(s["blend"], 1),
            "gpm_pct": round(s["gpm_pct"], 1),
            "roe_pct": round(s["roe_pct"], 1),
            "cet_pct": round(s["cet_pct"], 1),
            "con_np_yoy": c.get("con_np_yoy"),
            "con_peg": c.get("con_peg"),
            "mom60": round(mom60 * 100, 1) if mom60 is not None else None,
            "mom60_pct": round(mom_pct, 1),
            "weight_pct": round(w.get(tk, 0) * 100, 2),
        })

    holdings.sort(key=lambda h: -h["weight_pct"])

    print("\n" + "=" * 88)
    print(f"推荐持仓（asof={asof}，共 {len(holdings)} 只，cap8 加权）")
    print("=" * 88)
    print(f"{'ticker':<11}{'名称':<10}{'PE':>6}{'市值(亿)':>9}{'PE%':>6}{'q20':>6}"
          f"{'mom60%':>8}{'mom分位':>8}{'权重%':>8}")
    print("-" * 88)
    for h in holdings:
        print(f"{h['ticker']:<11}{(h['name'] or '')[:9]:<10}{h['pe_ttm']:>6.1f}"
              f"{h['total_mv_yi']:>9.0f}{h['pe_pct']:>6.1f}{h['blend']:>6.1f}"
              f"{(h['mom60'] if h['mom60'] is not None else 0):>+7.1f}%"
              f"{h['mom60_pct']:>7.1f}%{h['weight_pct']:>7.2f}%")

    out = {
        "strategy": "AD_top15_mom60top50",
        "pit_month": month,
        "asof": asof,
        "next_rebalance": "2027-04-30",
        "method": "严格复用 _bt_q20_pareto.screen_q20 + 日K mom60_top50 gate + top15 + cap8",
        "pool_size": {
            "pit_total": len(members),
            "screen_q20_base": len(base_pool),
            "mom60_calc": len(mom),
            "gate_pass": len(gated),
            "top15": len(picked),
        },
        "holdings": holdings,
    }
    json.dump(out, open("_holdings_latest.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n数据 → _holdings_latest.json")


if __name__ == "__main__":
    main()
