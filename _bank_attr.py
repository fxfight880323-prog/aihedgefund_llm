# -*- coding: utf-8 -*-
"""LX-core 金融/银行贡献归因 + '择时买银行'命题独立检验。
口径：日频复权价、半年调仓（与 _bt_daily_bt.py 同触发日）、成本 0（归因层）+ 含费对照。
输出 _bank_attr_report.html
"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

PIT_DATES = [
    ("2021-08", "2021-08-31"), ("2022-04", "2022-04-30"),
    ("2022-08", "2022-08-31"), ("2023-04", "2023-04-30"),
    ("2023-08", "2023-08-31"), ("2024-04", "2024-04-30"),
    ("2024-08", "2024-08-31"), ("2025-04", "2025-04-30"),
    ("2025-08", "2025-08-31"), ("2026-04", "2026-04-30"),
]

def mdd_of(seq):
    peak, mdd = seq[0], 0.0
    for v in seq:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd

def main():
    px = json.load(open("_bt_daily_px.json", encoding="utf-8"))
    fin = json.load(open("_bt_sw_fin_universe.json", encoding="utf-8"))
    banks = set(fin["银行"]["members"]); nonbk = set(fin["非银金融"]["members"])
    w_core = json.load(open("_bt_band_results.json", encoding="utf-8"))["weights"]["core"]

    # 复权日频 close / open（open 用 adj 折算）
    close, opan = {}, {}
    for tk, d in px.items():
        mc, mo = {}, {}
        for dt, r in d.items():
            c, a = r.get("close"), r.get("adj")
            if c and a and c > 0 and a > 0 and dt >= "2021-05-01":
                ratio = a / c
                mc[dt] = a
                mo[dt] = (r.get("open") or c) * ratio
        if mc:
            close[tk] = mc; opan[tk] = mo
    all_dates = sorted({dt for m in close.values() for dt in m})
    dts = [d for d in all_dates if d >= "2021-06-01"]

    def trig_of(asof):
        return max(d for d in all_dates if d <= asof)

    trigs = {trig_of(asof): month for month, asof in PIT_DATES}

    # ---------- 1) core 逐股 P&L 归因 ----------
    # 撮合语义对齐官方引擎：触发日收盘下目标单 → 次日开盘成交（含费率+滑点 15bp 近似），
    # 日终以收盘 mark-to-market。
    FEE = 0.0015
    shares = {}
    pending = None          # (weights, equity_at_trig) 待次日开盘执行
    equity = 1_000_000.0
    contrib = {}          # tk -> pnl 累计（元）
    contrib_yr = {}       # (tk, year) -> pnl
    nav_seq = []
    prev_px_today = {}
    for i, dt in enumerate(dts):
        # 次日开盘执行调仓
        if pending is not None:
            weights, _eq = pending
            pending = None
            new_shares = {}
            for tk, wgt in weights.items():
                po = opan[tk].get(dt)
                if po and po > 0:
                    new_shares[tk] = wgt * equity / po
            traded = sum(abs(new_shares.get(tk, 0.0) - shares.get(tk, 0.0))
                         * opan[tk].get(dt, 0.0) for tk in set(new_shares) | set(shares))
            equity -= FEE * traded
            # 重算权重扣费后的目标股数（近似按比例缩放）
            scale = equity / (equity + FEE * traded) if traded > 0 else 1.0
            shares = {tk: sh * scale for tk, sh in new_shares.items()}
            for tk in shares:
                po = opan[tk].get(dt)
                if po:
                    prev_px_today[tk] = po   # 当日 PnL 从成交价（开盘）起算
        # 当日损益
        day_pnl = 0.0
        for tk, sh in shares.items():
            p0 = prev_px_today.get(tk)
            p1 = close[tk].get(dt)
            if p0 and p1 and sh > 0:
                pnl = sh * (p1 - p0)
                contrib[tk] = contrib.get(tk, 0.0) + pnl
                contrib_yr[(tk, dt[:4])] = contrib_yr.get((tk, dt[:4]), 0.0) + pnl
                day_pnl += pnl
        equity += day_pnl
        nav_seq.append(equity)
        # 收盘价缓存
        for tk in shares:
            p = close[tk].get(dt)
            if p:
                prev_px_today[tk] = p
        # 调仓（触发日收盘挂单）
        if dt in trigs:
            pending = (w_core[trigs[dt]], equity)

    total_ret = nav_seq[-1] / nav_seq[0] - 1.0
    years = len(dts) / 252.0

    def grp(tk):
        return "银行" if tk in banks else ("非银金融" if tk in nonbk else "其他")

    grp_pnl = {}
    for tk, v in contrib.items():
        grp_pnl[grp(tk)] = grp_pnl.get(grp(tk), 0.0) + v
    # 分组贡献 = pnl / 初始资金
    grp_contrib = {g: v / 1_000_000.0 for g, v in grp_pnl.items()}

    # 分年度：银行 vs 非银 vs 其他 贡献（各年 pnl / 当年初净值）
    yr_grp = {}
    yr_start_nav = {}
    for (tk, yr), v in contrib_yr.items():
        yr_grp.setdefault(yr, {}).setdefault(grp(tk), 0.0)
        yr_grp[yr][grp(tk)] += v
    # 每年初净值
    seen = set()
    for i, dt in enumerate(dts):
        y = dt[:4]
        if y not in seen:
            seen.add(y); yr_start_nav[y] = nav_seq[i]

    # ---------- 2) 银行等权组合（独立检验） ----------
    bank_list = sorted(banks & set(close))
    n_miss = len(banks) - len(bank_list)
    # 半年调仓等权（同 PIT 日期，与等权全A基准口径一致）
    def run_ew(code_list, rebalance=True):
        sh = {}; eq = 1_000_000.0; navs = []
        prev = {}
        for dt in dts:
            day = 0.0
            for tk, s in sh.items():
                p0, p1 = prev.get(tk), close[tk].get(dt)
                if p0 and p1 and s > 0:
                    day += s * (p1 - p0)
            eq += day; navs.append(eq)
            for tk in sh:
                p = close[tk].get(dt)
                if p: prev[tk] = p
            if rebalance and dt in trigs:
                live = [c for c in code_list if close[c].get(dt)]
                sh = {}
                for c in live:
                    sh[c] = (1.0 / len(live)) * eq / close[c][dt]
        return navs, len(live) if rebalance else len(code_list)

    bank_navs, bank_n = run_ew(bank_list)
    bank_ret = bank_navs[-1] / bank_navs[0] - 1.0
    bank_mdd = mdd_of(bank_navs)
    bank_ann = (1 + bank_ret) ** (1 / years) - 1

    # 银行等权 分年度收益
    bank_yr = {}
    seen = set()
    for i, dt in enumerate(dts):
        y = dt[:4]
        if y not in seen:
            seen.add(y); bank_yr[y] = {"start": bank_navs[i]}
        bank_yr[y]["end"] = bank_navs[i]

    # 基准
    ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))["nav"]
    ew_dts = sorted(d for d in ew if d >= "2021-06-01")
    ew_ret = ew[ew_dts[-1]] / ew[ew_dts[0]] - 1.0
    ew_mdd = mdd_of([ew[d] for d in ew_dts])
    idx_res = json.load(open("_bt_daily_results.json", encoding="utf-8"))["idx"]
    ew_yr = {}
    seen = set()
    for d in ew_dts:
        y = d[:4]
        if y not in seen:
            seen.add(y); ew_yr[y] = {"start": ew[d]}
        ew_yr[y]["end"] = ew[d]

    daily = json.load(open("_bt_daily_results.json", encoding="utf-8"))["results"]
    core = daily["core"]; finex = daily["core_finex"]

    # ---------- 3) core 里银行仓位与收益对比 ----------
    rows = []
    for month, asof in PIT_DATES:
        holds = set(w_core[month])
        b = holds & banks; nb = holds & nonbk
        rows.append((month, len(holds), len(b), len(nb),
                     f"{len(b)/len(holds):.0%}"))

    # ---------- 报告 ----------
    out = {
        "period": f"{dts[0]} ~ {dts[-1]} ({years:.2f}年)",
        "core_total": total_ret, "core_mdd": mdd_of(nav_seq),
        "core_official": core["total"], "finex_total": finex["total"],
        "fin_gap": core["total"] - finex["total"],
        "grp_contrib": grp_contrib,
        "bank_n": bank_n, "bank_miss": n_miss,
        "bank_ew": {"total": bank_ret, "ann": bank_ann, "mdd": bank_mdd},
        "ew_allA": {"total": ew_ret, "mdd": ew_mdd},
        "idx": {"total": idx_res["total"], "mdd": idx_res["mdd"]},
        "yearly": {
            y: {
                "bank_contrib": yr_grp.get(y, {}).get("银行", 0.0) / yr_start_nav[y],
                "nonbk_contrib": yr_grp.get(y, {}).get("非银金融", 0.0) / yr_start_nav[y],
                "other_contrib": yr_grp.get(y, {}).get("其他", 0.0) / yr_start_nav[y],
                "bank_idx_ret": bank_yr[y]["end"] / bank_yr[y]["start"] - 1.0,
                "ew_allA_ret": ew_yr[y]["end"] / ew_yr[y]["start"] - 1.0,
            } for y in sorted(yr_grp)
        },
        "holdings": rows,
        "top_bank_contrib": sorted(
            ((tk, v / 1_000_000.0) for tk, v in contrib.items() if tk in banks),
            key=lambda x: -x[1])[:10],
        "top_other_contrib": sorted(
            ((tk, v / 1_000_000.0) for tk, v in contrib.items() if tk not in banks),
            key=lambda x: -x[1])[:10],
    }
    json.dump(out, open("_bank_attr_data.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 控制台摘要
    print("=" * 60)
    print(f"区间 {out['period']}")
    print(f"LX-core(含费)      {core['total']:+.2%}  MDD {core['mdd']:.2%}")
    print(f"LX-core(归因层无费) {total_ret:+.2%}")
    print(f"LX-finex(剔金融)   {finex['total']:+.2%}  → 组合层差 {out['fin_gap']:+.2%}pp")
    print("-" * 60)
    print("分组贡献（占初始资金，加总≈无费总收益）:")
    for g, v in sorted(grp_contrib.items(), key=lambda x: -x[1]):
        print(f"  {g:8s} {v:+.2%}")
    print("-" * 60)
    print(f"银行等权组合({bank_n}只,缺{n_miss}): 总 {bank_ret:+.2%} 年化 {bank_ann:+.2%} MDD {bank_mdd:.2%}")
    print(f"等权全A:            总 {ew_ret:+.2%} MDD {ew_mdd:.2%}")
    print(f"中证全指:           总 {idx_res['total']:+.2%} MDD {idx_res['mdd']:.2%}")
    print("-" * 60)
    print("分年度 | 银行贡献(core内) | 非银 | 其他 | 银行等权指数 | 等权全A")
    for y, v in out["yearly"].items():
        print(f"  {y} | {v['bank_contrib']:+7.2%} | {v['nonbk_contrib']:+6.2%} | "
              f"{v['other_contrib']:+7.2%} | {v['bank_idx_ret']:+7.2%} | {v['ew_allA_ret']:+7.2%}")
    print("-" * 60)
    print("Top 银行贡献:", [(tk, f"{v:+.1%}") for tk, v in out["top_bank_contrib"][:6]])
    print("Top 非银行贡献:", [(tk, f"{v:+.1%}") for tk, v in out["top_other_contrib"][:6]])


if __name__ == "__main__":
    main()
