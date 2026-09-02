# -*- coding: utf-8 -*-
import json, sys, statistics, math
sys.stdout.reconfigure(encoding='utf-8')
with open('_factor_ic_all.json',encoding='utf-8') as f:
    data = json.load(f)

FACTORS = ["估值","低波","低流动性","分析师","动量","反转","市值","成长","盈利","红利",
           "筹码成本差","筹码成本","机构筹码集中度","筹码合成","行业轮动","GBM量价"]

def yearly_ic(records):
    by_year = {}
    for r in records:
        y = r['date'][:4]
        by_year.setdefault(y, []).append(r['ic'])
    return {y: statistics.mean(v) for y,v in sorted(by_year.items())}

def ar1(vals):
    n = len(vals)
    if n < 3: return None
    m = statistics.mean(vals)
    num = sum((vals[i]-m)*(vals[i+1]-m) for i in range(n-1))
    den = sum((v-m)**2 for v in vals)
    return num/den if den>0 else 0.0

rows = []
for f in FACTORS:
    d = data.get(f)
    if not d: continue
    m = d['metadata']
    recs = d['records']
    ics = [r['ic'] for r in recs]
    n = len(ics)
    ic_mean = m['ic_mean']; ic_std = m['ic_std']; ir = m['ir']
    t = ir * math.sqrt(n)
    yic = yearly_ic(recs)
    a = ar1(ics)
    rows.append((f, ic_mean, ic_std, ir, t, m['positive_ratio'], a, yic))

# 按 |IR| 排序
rows.sort(key=lambda x: -abs(x[3]))

print("="*120)
print(f"{'因子':<10}{'IC均值':>8}{'ICstd':>8}{'IR':>8}{'t值':>7}{'正占比':>7}{'AR(1)':>8}")
print("="*120)
for f, m_, s, ir, t, pos, a, yic in rows:
    print(f"{f:<10}{m_:>8.4f}{s:>8.4f}{ir:>8.4f}{t:>7.2f}{pos:>7.2f}{a:>8.3f}")

print("\n" + "="*120)
print("分年度 IC（行=因子，列=年份）")
years = sorted(set(y for f,_,_,_,_,_,_,yic in rows for y in yic))
print(f"{'因子':<10}" + "".join(f"{y:>9}" for y in years))
for f, m_, s, ir, t, pos, a, yic in rows:
    line = f"{f:<10}"
    for y in years:
        v = yic.get(y)
        line += f"{v:>9.3f}" if v is not None else f"{'':>9}"
    print(line)

print("\n" + "="*120)
print("显著性判定（|t|>2 显著；IR>0.5 优秀；IR>0.3 良好）")
for f, m_, s, ir, t, pos, a, yic in rows:
    tag = "★★★ 显著" if abs(t)>=2 else ("★ 边缘" if abs(t)>=1.5 else "  不显著")
    print(f"  {f:<10} t={t:>6.2f}  {tag}")
