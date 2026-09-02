# -*- coding: utf-8 -*-
"""低PE 10年单点依赖诊断：Q1分位 vs top40 vs 等权全A

回答：哪个组合的收益是"单一年份单点贡献"出来的，哪个是逐年分散的。
指标：
  1. total / ann(年化)
  2. best_year / best2 收益
  3. ex_best 去最好年后收益、ex_best2 去最好两年后收益
  4. 单点依赖度 = 1 - ex_best_ret / total_ret （越高越依赖单年）
  5. 2024贡献（去2024后收益，检验"金融修复单点"假设）
  6. 正收益年占比（胜率）
  7. 逐年超额(vs ew)稳定性
"""
import json, math

d = json.load(open("_bt_lowpe_10y_results.json", encoding="utf-8"))
R = d["results"]
years = sorted({y for v in R.values() for y in v["yearly"]})
years = [y for y in years if y != "2016"]  # 2016 是首期基线=0

def nav_factor(ret):
    return 1.0 + ret

def cum(ret_dict, exclude=()):
    n = 1.0
    for y in years:
        if y in exclude:
            continue
        n *= (1.0 + ret_dict.get(y, 0.0))
    return n - 1.0

def metrics(name, r):
    total = r["total"]
    yearly = r["yearly"]
    nav = 1.0 + total
    # 实际年份数（2017~2026 = 9.33年，用周期数近似 9.33）
    ny = 9.3333
    ann = nav ** (1.0 / ny) - 1.0
    # 排序年份（按收益降序）
    ranked = sorted(years, key=lambda y: -yearly.get(y, 0.0))
    best_y = ranked[0]
    best2 = ranked[:2]
    ex_best = cum(yearly, exclude=[best_y])
    ex_best2 = cum(yearly, exclude=best2)
    ex_2024 = cum(yearly, exclude=["2024"])
    ex_2025 = cum(yearly, exclude=["2025"])
    pos_years = [y for y in years if yearly.get(y, 0.0) > 0]
    dep_best = 1.0 - (ex_best / total) if total > 0 else float("nan")
    dep_2024 = 1.0 - (ex_2024 / total) if total > 0 else float("nan")
    # 收益集中度 HHI（各年收益占总收益比例平方和，衡量分布均衡度）
    hhi = sum((yearly.get(y, 0.0) / total) ** 2 for y in years) if total > 0 else float("nan")
    return {
        "name": name,
        "total": total,
        "ann": ann,
        "best_year": best_y,
        "best_ret": yearly.get(best_y, 0.0),
        "best2": best2,
        "ex_best": ex_best,
        "ex_best2": ex_best2,
        "ex_2024": ex_2024,
        "ex_2025": ex_2025,
        "dep_best": dep_best,
        "dep_2024": dep_2024,
        "hhi": hhi,
        "pos_ratio": len(pos_years) / len(years),
        "yearly": {y: yearly.get(y, 0.0) for y in years},
    }

out = {}
for v in ["q1", "top40", "ew", "csi"]:
    out[v] = metrics(v, R[v])

# 逐年超额 vs ew（q1 和 top40）
ew_y = R["ew"]["yearly"]
for v in ["q1", "top40"]:
    out[v]["excess_vs_ew"] = {
        y: R[v]["yearly"].get(y, 0.0) - ew_y.get(y, 0.0) for y in years
    }

# 多空 q1-q5
out["longshort"] = d.get("longshort_q1q5", {})

json.dump(out, open("_bt_lowpe_10y_diag.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# 打印摘要
print("=" * 78)
print("低PE 10年单点依赖诊断（2017~2026，10个自然年）")
print("=" * 78)
hdr = f"{'组合':<8}{'总收益':>9}{'年化':>8}{'最好年':>8}{'去最好年':>9}{'去最好2年':>10}{'依赖度':>8}{'2024依赖':>9}{'正收益占比':>10}"
print(hdr)
for v in ["q1", "top40", "ew", "csi"]:
    m = out[v]
    print(f"{m['name']:<8}{m['total']*100:>8.1f}%{m['ann']*100:>7.1f}%"
          f"{m['best_year']:>8}{m['ex_best']*100:>8.1f}%{m['ex_best2']*100:>9.1f}%"
          f"{m['dep_best']:>7.2f}{m['dep_2024']*100:>8.1f}%{m['pos_ratio']*100:>9.0f}%")

print()
print("依赖度 dep_best 解读：1 - 去最好年后收益/总收益，越高=越靠单年撑起总收益")
print()
print("逐年收益矩阵（%）:")
print(f"{'年份':<6}" + "".join(f"{y:>8}" for y in years))
for v in ["q1", "top40", "ew", "csi"]:
    print(f"{v:<6}" + "".join(f"{out[v]['yearly'][y]*100:>8.1f}" for y in years))

print()
print("逐年超额 vs 等权全A（pp）:")
print(f"{'组合':<8}" + "".join(f"{y:>8}" for y in years))
for v in ["q1", "top40"]:
    ex = out[v]["excess_vs_ew"]
    print(f"{v:<8}" + "".join(f"{ex[y]*100:>8.1f}" for y in years))
