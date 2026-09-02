# -*- coding: utf-8 -*-
"""行业分散 / 降金融浓度对冲实验（承接 cap 甜点分年度拆解的尾部结论）。

背景：cap 甜点分年度拆解发现——等权 g60 收益依赖 2024(+33.1%)+2025(+16.7%)，
2021~2023 三年合计仅 +6.4%，底仓=低PE大盘金融价值股(金融占 top40 的 ~50%)的
单点 beta 集中。cap（市值加权上限）解决不了底层风格单点依赖。

问题：用「行业/金融浓度约束」把 top40 从金融集中强制分散到更宽行业，能否
在不大幅牺牲收益的前提下，降低单点依赖（提升行业有效持仓数 N_eff / 压低行业 HHI）？

变体（全部 full 基座 = 含金融，g60 口径 = 增速≤60% + PEG≤1 + mv≥100亿 + PE升序，
日频复权 + 成本 5bp+10bp，等权构建）:
  g60        基线（无行业约束）                      [锚点 +67.01%]
  fin_le_15  金融(银行+非银) ≤ 15 只                  [金融浓度阶梯]
  fin_le_12  金融 ≤ 12 只
  fin_le_10  金融 ≤ 10 只
  fin_le_8   金融 ≤ 8 只
  fin_le_5   金融 ≤ 5 只
  fin_0      金融 = 0 只（= finex 剔除金融，g60 口径）  [锚点 finex.g60 +37.30%]
  ind_le_10  申万二级每行业 ≤ 10 只                    [宽行业分散阶梯]
  ind_le_8   申万二级每行业 ≤ 8 只
  ind_le_6   申万二级每行业 ≤ 6 只

选股算法：g60 池按 PE 升序，贪心取 top40，但受「组计数 ≤ 上限」约束（超限跳过，
继续往下取），保留 PE 升序信念（便宜优先）不变，仅用行业约束重新分配席位。

行业分类：申万二级，来自 _chip_industry_data.json（juzi 行业面板，2026-07-31 快照，
5134 只）。金融组复用 _bt_sw_fin_universe.json 的 fin 集（银行+非银金融 123 只）。
快照非 PIT：早年退市股（阳光城/中南建设）缺失，手动兜底为「房地产开发」；行业分类
对大盘价值股长期稳定，此口径差异为方向性结论标注。

锚点校验（Type D 铁律）:
  g60   ≈ +0.6701（_bt_garp_audit_results.json rerun.full.g60）
  fin_0 ≈ +0.3730（_bt_garp_audit_results.json rerun.finex.g60）
"""
import json, os, sys, datetime
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_garp as G
from _bt_garp_decompose import screen_decomp, load_bars

PIT_DATES = L.PIT_DATES
MAX_HOLDINGS = L.MAX_HOLDINGS
G60_G, G60_PEG = 60.0, 1.0
MV_FLOOR = 100.0

# 金融组 = fin 集（银行 + 非银金融）
# 申万二级行业快照缺失兜底（早年退市地产股）
INDUSTRY_FALLBACK = {
    "000671.SZ": "房地产开发",   # 阳光城（退市）
    "000961.SZ": "房地产开发",   # 中南建设（退市）
}

VARIANTS = {
    "g60":        ("fin", None),
    "fin_le_15":  ("fin", 15),
    "fin_le_12":  ("fin", 12),
    "fin_le_10":  ("fin", 10),
    "fin_le_8":   ("fin", 8),
    "fin_le_5":   ("fin", 5),
    "fin_0":      ("fin", 0),
    "ind_le_10":  ("ind", 10),
    "ind_le_8":   ("ind", 8),
    "ind_le_6":   ("ind", 6),
}


def load_industry():
    d = json.load(open("_chip_industry_data.json", encoding="utf-8"))
    ind = {s["ts_code"]: s["industry"] for s in d["stocks"]}
    ind.update(INDUSTRY_FALLBACK)
    return ind


def select_capped(pool_sorted, fin, ind, mode, cap):
    """贪心按 PE 升序取 top40，受组计数上限约束。mode='fin'→金融/非金融两组
    （上限只约束金融组，非金融不设限，cap=0 即剔除金融）；mode='ind'→申万二级
    各组均设上限。cap=None 表示无上限。"""
    picked = []
    cnt = Counter()
    for s in pool_sorted:
        tk = s["tk"]
        if mode == "fin":
            grp = "fin" if tk in fin else "nonfin"
            if grp == "fin" and cap is not None and cnt[grp] >= cap:
                continue
        else:
            grp = ind.get(tk, "未分类")
            if cap is not None and cnt[grp] >= cap:
                continue
        picked.append(s)
        cnt[grp] += 1
        if len(picked) >= MAX_HOLDINGS:
            break
    return picked


def group_hhi(picked, fin, ind, mode="ind"):
    """行业/组集中度 HHI → 有效组数 N_eff。"""
    cnt = Counter()
    for s in picked:
        tk = s["tk"]
        if mode == "fin":
            grp = "金融" if tk in fin else "非金融"
        else:
            grp = ind.get(tk, "未分类")
        cnt[grp] += 1
    n = sum(cnt.values())
    if n == 0:
        return 1.0, 1.0
    hhi = sum((c / n) ** 2 for c in cnt.values())
    return hhi, 1.0 / hhi


def yearly_returns(nav_seq):
    """nav_seq: [{'date': 'YYYY-MM-DD', 'nav': float}] → {year: total_return}"""
    by_year = {}
    for r in nav_seq:
        y = r["date"][:4]
        by_year.setdefault(y, []).append(r)
    out = {}
    for y, rows in sorted(by_year.items()):
        if len(rows) < 2:
            continue
        out[y] = rows[-1]["nav"] / rows[0]["nav"] - 1.0
    return out


def main():
    print("=" * 88)
    print("  行业分散 / 降金融浓度对冲实验（g60 口径，full 基座，日频+复权）")
    print("=" * 88)

    univ = L.load_universe()
    cons = L.load_consensus()
    val = L.load_map(L.VAL_FILE)
    fac = L.load_map(L.FAC_FILE)
    fin = G.load_fin()
    ind = load_industry()
    print(f"  金融组: {len(fin)} 只 | 行业映射: {len(ind)} 只")

    # 每期 g60 池（PE 升序）
    print("\n[筛选] 逐期构建 g60 池 + 各约束变体 top40 …")
    pools = {}
    for month, as_of in PIT_DATES:
        m = univ[month]
        vv, ff, cc = val[month], fac[month], cons[month]
        pool = screen_decomp(month, m, vv, ff, cc, set(),
                             MV_FLOOR, G60_G, G60_PEG, True, True)
        pool.sort(key=lambda s: s["pe"])
        pools[month] = pool

    # 各变体选股
    picks = {v: {} for v in VARIANTS}
    fin_cnt = {v: [] for v in VARIANTS}
    ind_cnt = {v: [] for v in VARIANTS}   # 行业 HHI
    for v, (mode, cap) in VARIANTS.items():
        for month, as_of in PIT_DATES:
            pool = pools[month]
            sel = select_capped(pool, fin, ind, mode, cap)
            picks[v][month] = sel
            fin_cnt[v].append(sum(1 for s in sel if s["tk"] in fin))
            hhi, neff = group_hhi(sel, fin, ind, "ind")
            ind_cnt[v].append((hhi, neff))
        print(f"  {v:12s}: 金融/期均值 {sum(fin_cnt[v])/len(fin_cnt[v]):5.1f} | "
              f"行业HHI均值 {sum(h for h, _ in ind_cnt[v])/len(ind_cnt[v]):.3f}")

    # 价格装载 + 覆盖审计
    px_full = json.load(open("_bt_daily_px_full.json", encoding="utf-8"))
    bars, all_dates = load_bars(px_full)
    px_syms = set(px_full.keys())
    print(f"\n  复权 bar: {len(bars)} 只 | {all_dates[0]} ~ {all_dates[-1]}")

    miss = {}
    for v in VARIANTS:
        m = {}
        for month, as_of in PIT_DATES:
            mm = [s["tk"] for s in picks[v][month] if s["tk"] not in px_syms]
            if mm:
                m[month] = mm
        miss[v] = m
        tot = sum(len(x) for x in m.values())
        print(f"  [覆盖审计] {v:12s}: {tot:3d} 只-期 缺失 {'✓' if not tot else '⚠️'}")

    # 回测
    print("\n[回测] …")
    results = {}
    for v in VARIANTS:
        w_by_dt = {}
        for month, asof in PIT_DATES:
            sel = picks[v][month]
            n = len(sel)
            w = round(min(1.0 / max(n, 1), L.PER_NAME_CAP), 4)
            wgt = {s["tk"]: w for s in sel}
            trig = max(d for d in all_dates if d <= asof)
            w_by_dt[trig] = wgt
        r = G.run(v, w_by_dt, bars)
        r["fin_mean"] = sum(fin_cnt[v]) / len(fin_cnt[v])
        r["ind_hhi"] = sum(h for h, _ in ind_cnt[v]) / len(ind_cnt[v])
        r["ind_neff"] = sum(n for _, n in ind_cnt[v]) / len(ind_cnt[v])
        r["yearly"] = yearly_returns(r["nav"])
        r.pop("nav", None)
        results[v] = r
        print(f"  {v:12s}: 总 {r['total']:+7.2%} 年化 {r['ann']:+6.2%} "
              f"MDD {r['mdd']:6.2%} | 金融 {r['fin_mean']:4.1f}/期 "
              f"N_eff {r['ind_neff']:4.1f}")

    # 锚点
    audit = json.load(open("_bt_garp_audit_results.json", encoding="utf-8"))
    print(f"\n  [锚点] g60={results['g60']['total']:+.4f} (期望 +0.6701) | "
          f"fin_0={results['fin_0']['total']:+.4f} (期望 +0.3730=finex.g60)")

    # 基准
    ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))
    idx = json.load(open("_bt_daily_idx.json", encoding="utf-8"))
    idx_dts = sorted(d for d in idx if d >= "2021-06-01")
    idx_base = idx[idx_dts[0]]["close"]
    idx_total = idx[idx_dts[-1]]["close"] / idx_base - 1.0
    for v in VARIANTS:
        results[v]["excess_ew"] = results[v]["total"] - ew["total"]
        results[v]["excess_idx"] = results[v]["total"] - idx_total

    # 填充项行业构成（fin_le_10 vs g60 的非金融席位去向）
    fill = {}
    for v in ("g60", "fin_le_10", "fin_le_8", "fin_le_5", "fin_0"):
        c = Counter()
        for month, as_of in PIT_DATES:
            for s in picks[v][month]:
                if s["tk"] in fin:
                    continue
                c[ind.get(s["tk"], "未分类")] += 1
        fill[v] = dict(c.most_common(12))

    out = {
        "meta": {
            "run_at": datetime.datetime.now().isoformat()[:19],
            "base": "full (含金融)", "freq": "日频+复权",
            "params": {"g_ceil": G60_G, "peg_ceil": G60_PEG, "mv_floor_yi": MV_FLOOR},
            "industry_src": "_chip_industry_data.json (SW二级, 2026-07-31 快照)",
            "window": [all_dates[0], all_dates[-1]],
        },
        "benchmarks": {
            "ew_hold": ew["total"],
            "csi_all": idx_total,
        },
        "results": results,
        "fin_cnt_per_period": {v: fin_cnt[v] for v in VARIANTS},
        "coverage_miss": miss,
        "fill_industry": fill,
    }
    json.dump(out, open("_bt_garp_ind_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n结果 → _bt_garp_ind_results.json")


if __name__ == "__main__":
    main()
