# -*- coding: utf-8 -*-
"""市值加权 cap 甜点区的分年度收益拆解。

问题：cap8~10 相对等权的 ~+40pp 超额，是稳定年化贡献，还是某一年（如 2024 金融修复年）单点爆发？

口径：full 基座，PE升序 top40，日频复权，含成本。年度收益 = 年末nav/上年末nav-1（2021 为 6月起、2026 为至 8 月的不完整年）。
"""
import json, os, sys, datetime

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import screen_decomp, load_bars
from _bt_garp_cap import cap_weight

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS = L.MAX_HOLDINGS


def yearly(nav_list):
    d = {x["date"]: x["nav"] for x in nav_list}
    dts = sorted(d)
    years = sorted(set(dt[:4] for dt in dts))
    out, prev_end = {}, None
    for y in years:
        y_dts = [dt for dt in dts if dt[:4] == y]
        end = d[y_dts[-1]]
        out[y] = end / d[y_dts[0]] - 1 if prev_end is None else end / prev_end - 1
        prev_end = end
    return out


def main():
    print("=" * 88)
    print("  cap 甜点区分年度收益拆解（等权 vs 市值加权 cap 系）")
    print("=" * 88)

    univ = L.load_universe(); cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE); fac = L.load_map(L.FAC_FILE)

    picks = {}
    for month, as_of in PIT_DATES:
        m = univ[month]; vv, ff, cc = val[month], fac[month], cons[month]
        pool = screen_decomp(month, m, vv, ff, cc, set(), 100.0, 60.0, 1.0, True, True)
        pool.sort(key=lambda s: s["pe"])
        picks[month] = pool[:MAX_HOLDINGS]

    schemes = {
        "等权g60": lambda p: {s["tk"]: round(min(1.0 / max(len(p), 1), 0.05), 4) for s in p},
        "cap8":    lambda p: cap_weight(p, 0.08),
        "cap10":   lambda p: cap_weight(p, 0.10),
        "cap15":   lambda p: cap_weight(p, 0.15),
        "无上限":  lambda p: {s["tk"]: s["mv"] / sum(x["mv"] for x in p) for s in p},
    }

    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    print(f"  复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    navs = {}
    for name, fn in schemes.items():
        all_w = {month: fn(picks[month]) for month, _ in PIT_DATES}
        w_by_dt = {}
        for month, asof in PIT_DATES:
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = all_w[month]
        r = G.run(name, w_by_dt, bars)
        navs[name] = r["nav"]
        print(f"  {name:8s}: 总 {r['total']:+7.2%} 年化 {r['ann']:+6.2%} MDD {r['mdd']:6.2%}")

    # 基准：等权全A
    ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))
    navs["等权全A"] = [{"date": d, "nav": v} for d, v in sorted(ew["nav"].items())]

    # 分年度
    yearly_map = {k: yearly(v) for k, v in navs.items()}
    years = sorted(set(y for m in yearly_map.values() for y in m))
    print(f"\n  年度区间: {years}")

    # 年度收益矩阵
    print("\n  [年度收益] 行=变体，列=年份")
    header = "    " + "".join(f"{y:>10}" for y in years)
    print(header)
    for name in ["等权全A", "等权g60", "cap8", "cap10", "cap15", "无上限"]:
        ym = yearly_map[name]
        line = f"  {name:8s}"
        for y in years:
            v = ym.get(y)
            line += f"{v:>10.1%}" if v is not None else f"{'--':>10}"
        print(line)

    # 年度超额（vs 等权g60）
    base = yearly_map["等权g60"]
    print("\n  [年度超额 vs 等权g60]")
    header = "    " + "".join(f"{y:>10}" for y in years)
    print(header)
    for name in ["cap8", "cap10", "cap15", "无上限"]:
        ym = yearly_map[name]
        line = f"  {name:8s}"
        for y in years:
            v = ym.get(y); b = base.get(y)
            line += f"{(v-b):>+10.1%}" if (v is not None and b is not None) else f"{'--':>10}"
        print(line)

    # 基准对照：等权全A 年度
    print("\n  [等权全A 年度收益（对照）]")
    ym = yearly_map["等权全A"]
    print("  " + "  ".join(f"{y}: {ym[y]:+.1%}" for y in years))

    # 落盘
    out = {"yearly": yearly_map, "years": years}
    json.dump(out, open("_bt_garp_cap_yearly.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_cap_yearly.json")


if __name__ == "__main__":
    main()
