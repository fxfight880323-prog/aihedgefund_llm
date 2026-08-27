# -*- coding: utf-8 -*-
"""筹码合成 × 行业聚合分析：按东财行业计算集中度排名."""
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "_chip_industry_data.json"), encoding="utf-8"))
rows = d["stocks"]
print(f"stocks: {len(rows)}, date: {d['date']}")

# 全市场底部 20% 阈值（筹码最集中端，因子为负向）
chips = sorted(r["chip"] for r in rows)
q20 = chips[int(len(chips) * 0.2)]
q80 = chips[int(len(chips) * 0.8)]
print(f"market q20={q20:.3f} q80={q80:.3f}")

# 行业聚合
groups = {}
for r in rows:
    groups.setdefault(r["industry"], []).append(r)

stats = []
for ind, rs in groups.items():
    vals = [r["chip"] for r in rows if r["industry"] == ind]
    vals = [r["chip"] for r in rs]
    n = len(rs)
    if n < 15:
        continue
    low_share = sum(1 for v in vals if v <= q20) / n
    # 代表股：筹码最集中（chip 最低）且非 ST
    reps = sorted(rs, key=lambda r: r["chip"])
    reps = [r for r in reps if "ST" not in r["name"].upper()][:5]
    stats.append({
        "industry": ind, "n": n,
        "mean": st.mean(vals), "median": st.median(vals),
        "low_share": low_share,
        "reps": [{"code": r["ts_code"], "name": r["name"], "chip": round(r["chip"], 2)}
                 for r in reps],
    })

stats.sort(key=lambda s: s["mean"])
print(f"\nindustries (n>=15): {len(stats)}")

print("\n===== TOP 15 筹码最集中行业（因子值越低越好）=====")
print(f"{'行业':<8}{'n':>4}{'均值':>8}{'中位':>8}{'低分占比':>8}  代表股")
for s in stats[:15]:
    reps = "/".join(r["name"] for r in s["reps"][:4])
    print(f"{s['industry']:<8}{s['n']:>4}{s['mean']:>8.2f}{s['median']:>8.2f}"
          f"{s['low_share']*100:>7.0f}%  {reps}")

print("\n===== BOTTOM 10 筹码最分散行业（回避）=====")
for s in stats[-10:]:
    print(f"{s['industry']:<8}{s['n']:>4}{s['mean']:>8.2f}{s['median']:>8.2f}"
          f"{s['low_share']*100:>7.0f}%")

json.dump({"date": d["date"], "q20": q20, "q80": q80, "stats": stats},
          open(os.path.join(HERE, "_chip_industry_stats.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nsaved -> _chip_industry_stats.json")
