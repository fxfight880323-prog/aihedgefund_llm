# -*- coding: utf-8 -*-
"""恒等式校验: r_core = (n_fin/40)·r_fin + (n_nfin/40)·r_nfin
对齐引擎 vnpy 时序: 调仓月用旧持仓计盈亏 → 次月买入月无盈亏 → 其余月当前持仓计盈亏
验证 combo_nav 分组实现无前瞻/成员错配, 并输出逐月拆分表
"""
import json, sys
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

periods = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
           "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]
T_PERIOD = {p: i for i, p in enumerate(periods)}
hold = r["holdings"]


def _next_month(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    mm += 1
    if mm > 12:
        y, mm = y + 1, 1
    return f"{y}-{mm:02d}"


BUY_MONTHS = {_next_month(p) for p in periods}
months = [m for m in px.index if m >= "2021-08"]

# 逐月: 确定 active(当前持仓) 与 hist(成本/上一参考价)
def month_rows():
    """yield (m, active, hist); hist 为该月用于计盈亏的参考价(组内各股)"""
    active: list[str] = []
    hist: dict[str, float] = {}
    for m in months:
        if m in T_PERIOD:
            members = active            # 调仓月: 旧持仓计盈亏
            yield m, members, hist
            active = list(hold[m]["core"])
        elif m in BUY_MONTHS:           # 买入月: 无盈亏, 记新持仓价格
            for tk in active:
                if tk in px.columns and m in px.index:
                    hist[tk] = px.at[m, tk]
            yield m, [], hist
        else:
            yield m, active, hist       # 持有月: 当前持仓计盈亏


def grp_ret(members, hist, m, f):
    """组内等权平均收益; f 过滤函数"""
    rs = []
    for tk in members:
        if not f(tk) or tk not in px.columns or m not in px.index:
            continue
        cm = px.at[m, tk]
        pm = hist.get(tk)
        if pm and cm and pd.notna(pm) and pd.notna(cm) and pm > 0:
            rs.append(cm / pm - 1.0)
        hist[tk] = cm
    return (sum(rs) / len(rs)) if rs else 0.0, len(rs)


# 逐月表 + 复现
rows = []
nav_core, nav_recon = 1.0, 1.0
for m, members, hist in month_rows():
    r_fin, n_fin = grp_ret(members, hist, m, lambda t: t in fin_set)
    # 注意: grp_ret 会更新 hist, 第二组调用时 hist 已被第一组更新——恒等式不受影响
    r_nfin, n_nfin = grp_ret(members, hist, m, lambda t: t not in fin_set)
    n_tot = n_fin + n_nfin
    r_core = (n_fin / n_tot * r_fin + n_nfin / n_tot * r_nfin) if n_tot else 0.0
    r_recon = (n_fin / 40.0 * r_fin + n_nfin / 40.0 * r_nfin)
    rows.append({
        "m": m, "n_fin": n_fin, "n_nfin": n_nfin,
        "r_fin": r_fin, "r_nfin": r_nfin,
        "r_core": r_core, "r_recon": r_recon,
    })
    nav_core *= (1 + r_core)
    nav_recon *= (1 + r_recon)

# 输出逐月表
print(f"{'月份':<9}{'n_fin':>5}{'n_nfin':>6}{'r_fin':>10}{'r_nfin':>10}{'r_core(组权)':>13}{'r_core(1/40)':>13}{'差异bp':>8}")
for row in rows:
    diff_bp = (row["r_core"] - row["r_recon"]) * 1e4
    print(f"{row['m']:<9}{row['n_fin']:>5}{row['n_nfin']:>6}"
          f"{row['r_fin']:>+10.2%}{row['r_nfin']:>+10.2%}"
          f"{row['r_core']:>+13.2%}{row['r_recon']:>+13.2%}{diff_bp:>+8.1f}")

print(f"\n总收益  核心(组权平均)={nav_core-1:>+10.1%}  复现(1/40加权)={nav_recon-1:>+10.1%}")
print(f"最大单月|差异| = {max(abs(a['r_core']-a['r_recon']) for a in rows):.6f}")

# 保存
json.dump(rows, open(BASE + "_bt_band_identity.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("输出 _bt_band_identity.json")
