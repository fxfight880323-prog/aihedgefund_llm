# -*- coding: utf-8 -*-
"""归因 v2: 金融组 vs 非金融组 收益贡献（对齐引擎 vnpy 时序）
引擎语义: 调仓月 t 下买单 → t+1 月撮合成交(价=min(委托×1.2, t+1价))
  → t+1 月组合无盈亏(±成本), t+2 月起按本期持仓价格变化计盈亏
  → 调仓月 t 本身仍按旧持仓估值(卖出单 t+1 才成交)
算法:
  m = 调仓月 t_p   : 用 active(旧持仓) 按 m 价计盈亏 → 更新 active = 本期
  m = t_p 的次月    : 买入月, 无盈亏, 只记录新持仓价格
  其他月            : active 按 m 价计盈亏
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


def _next_month(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    mm += 1
    if mm > 12:
        y, mm = y + 1, 1
    return f"{y}-{mm:02d}"


BUY_MONTHS = {_next_month(p) for p in periods}  # 各调仓月的次月
months = [m for m in px.index if m >= "2021-08"]
hold = r["holdings"]


def combo_nav(get_members):
    nav = 1.0
    hist: dict[str, float] = {}
    active: list[str] = []
    series: dict[str, float] = {}
    for m in months:
        if m in T_PERIOD:                 # 调仓月: 旧持仓计盈亏, 再换仓
            members = active
            active = list(get_members(m))
        elif m in BUY_MONTHS:             # 买入月: 无盈亏, 记新持仓价格
            members = []
            for tk in active:
                if tk in px.columns and m in px.index:
                    hist[tk] = px.at[m, tk]
        else:                             # 持有月: 当前持仓计盈亏
            members = active
        rs = []
        for tk in members:
            if tk not in px.columns or m not in px.index:
                continue
            cm = px.at[m, tk]
            pm = hist.get(tk)
            if pm and cm and pd.notna(pm) and pd.notna(cm) and pm > 0:
                rs.append(cm / pm - 1.0)
            hist[tk] = cm
        if rs:
            nav *= (1.0 + sum(rs) / len(rs))
        series[m] = nav
    return series


def stats(s):
    vals = [v for v in s.values() if v == v]
    return vals[-1] / vals[0] - 1 if len(vals) > 1 else 0


nav_core = combo_nav(lambda p: hold[p]["core"])
nav_fin = combo_nav(lambda p: [t for t in hold[p]["core"] if t in fin_set])
nav_nfin = combo_nav(lambda p: [t for t in hold[p]["core"] if t not in fin_set])
nav_fx = combo_nav(lambda p: hold[p]["core_finex"])
nav_fxb = combo_nav(lambda p: hold[p]["core_finex_band"])

print(f"{'组合':<16}{'总收益':>10}")
print(f"{'core 全组合':<16}{stats(nav_core):>+10.1%}")
print(f"{'core 金融组':<16}{stats(nav_fin):>+10.1%}")
print(f"{'core 非金融组':<16}{stats(nav_nfin):>+10.1%}")
print(f"{'core_finex':<16}{stats(nav_fx):>+10.1%}")
print(f"{'core_finex_band':<16}{stats(nav_fxb):>+10.1%}")

eng = {x["month"]: x["nav"] / 1e6 for x in r["results"]["core"]["nav"]}
print("\n对照引擎 core nav (仅关键月):")
for m in ["2021-08", "2021-09", "2021-10", "2022-08", "2023-08",
          "2024-08", "2025-08", "2026-04", "2026-08"]:
    if m in eng and m in nav_core:
        print(f"  {m} 引擎={eng[m]:.4f} 归因={nav_core[m]:.4f} 差={eng[m]-nav_core[m]:+.4f}")

json.dump({"core": nav_core, "fin": nav_fin, "nfin": nav_nfin,
           "finex": nav_fx, "finex_band": nav_fxb},
          open(BASE + "_bt_band_attribution.json", "w", encoding="utf-8"), indent=1)
print("\n输出 _bt_band_attribution.json")
