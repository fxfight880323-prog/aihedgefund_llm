# -*- coding: utf-8 -*-
"""F-Score 基线 vs ROA 加权强化 对比报告"""
import json, math, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open("_bt_fscore_nav.json", encoding="utf-8") as f:
    base_nav = json.load(f)
with open("_bt_fscore_roaw_nav.json", encoding="utf-8") as f:
    roaw_nav = json.load(f)
with open("_bt_benchmark.json", encoding="utf-8") as f:
    bench = json.load(f)

CAP = 1_000_000.0

def series(nav_list):
    return {n["month"]: n["nav"] / CAP for n in nav_list}

base_s = series(base_nav)
roaw_s = series(roaw_nav)
months = sorted(base_s.keys())
bm_s = {}
b0 = bench.get(months[0])
for m in months:
    if m in bench and b0:
        bm_s[m] = bench[m] / b0

def stats(nav_dict):
    caps = [nav_dict[m] for m in sorted(nav_dict.keys())]
    ms = sorted(nav_dict.keys())
    ret = caps[-1] / caps[0] - 1
    y0, m0 = int(ms[0][:4]), int(ms[0][5:7])
    y1, m1 = int(ms[-1][:4]), int(ms[-1][5:7])
    span = max((y1 - y0) * 12 + (m1 - m0), 1)
    annual = (1 + ret) ** (12 / span) - 1
    rets = [math.log(caps[i] / caps[i - 1]) for i in range(1, len(caps))
            if caps[i - 1] > 0 and caps[i] > 0]
    mean_r = sum(rets) / len(rets) if rets else 0
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    sharpe = (mean_r - 0.02 / 12) / std_r * math.sqrt(12) if std_r > 0 else 0
    high = caps[0]; max_dd = 0.0
    for c in caps:
        if c >= high: high = c
        dd = c / high - 1
        if dd < max_dd: max_dd = dd
    yearly = {}
    for m in ms:
        yearly.setdefault(m[:4], []).append(nav_dict[m])
    yr = {}
    for y in sorted(yearly.keys()):
        vals = yearly[y]
        if len(vals) >= 2:
            yr[y] = vals[-1] / vals[0] - 1
    return {"ret": ret, "annual": annual, "sharpe": sharpe,
            "maxdd": max_dd, "yearly": yr}

st_b = stats(base_s)
st_r = stats(roaw_s)
st_bm = stats(bm_s)

# Common months for ROA variant
roaw_months = sorted(roaw_s.keys())
common = sorted(set(base_s.keys()) & set(roaw_s.keys()))

# Per-period excess comparison
import json as _json
sel = _json.load(open("_bt_fscore_selection.json", encoding="utf-8"))

PIT_DATES = [
    ("2021-08", "2021年中报"),
    ("2022-04", "2021年年报"),
    ("2022-08", "2022年中报"),
    ("2023-04", "2022年年报"),
    ("2023-08", "2023年中报"),
    ("2024-04", "2023年年报"),
    ("2024-08", "2024年中报"),
    ("2025-04", "2024年年报"),
    ("2025-08", "2025年中报"),
    ("2026-04", "2025年年报"),
]

# Per-period returns
def period_rets(nav_s, bench_s):
    results = []
    rebal = [d[0] for d in PIT_DATES]
    for i, rb in enumerate(rebal):
        if rb not in nav_s:
            continue
        nxt = rebal[i + 1] if i + 1 < len(rebal) else sorted(nav_s.keys())[-1]
        if nxt not in nav_s:
            nxt = sorted(nav_s.keys())[-1]
        ret = nav_s[nxt] / nav_s[rb] - 1
        br = bench_s.get(nxt, 0) / bench_s.get(rb, 1) - 1 if rb in bench_s else 0
        results.append({"month": rb, "ret": ret, "bench": br,
                         "excess": ret - br})
    return results

base_periods = period_rets(base_s, bm_s)
roaw_periods = period_rets(roaw_s, bm_s)

# ---------- HTML ----------
W = 1100
html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F-Score 基线 vs ROA 加权强化 对比报告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 20px; background: #f8f9fa; color: #333; }}
  h1 {{ text-align: center; color: #1a1a2e; margin-bottom: 5px; }}
  .sub {{ text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
  .card {{ background: white; border-radius: 10px; padding: 20px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ padding: 8px 12px; text-align: right; }}
  th {{ background: #1a1a2e; color: white; font-weight: 500; }}
  td:first-child, th:first-child {{ text-align: left; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .pos {{ color: #c0392b; font-weight: 600; }}
  .neg {{ color: #27ae60; font-weight: 600; }}
  .highlight {{ background: #fff3cd !important; }}
  .verdict {{ background: #e74c3c; color: white; padding: 15px 25px;
             border-radius: 8px; text-align: center; font-size: 18px;
             font-weight: 600; margin: 20px 0; }}
  .note {{ background: #e8f4fd; border-left: 4px solid #3498db; padding: 12px 16px;
          margin: 15px 0; font-size: 13px; line-height: 1.7; }}
  .analysis {{ background: white; border-radius: 10px; padding: 25px;
              box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 20px 0;
              line-height: 1.8; font-size: 14px; }}
  .analysis h3 {{ color: #1a1a2e; border-bottom: 2px solid #3498db;
                 padding-bottom: 8px; }}
  svg {{ display: block; margin: 0 auto; }}
</style>
</head>
<body>

<h1>F-Score 基线 vs ROA 加权强化</h1>
<div class="sub">
  Piotroski &amp; So (2012) + 刘旭纪律 | 2021-06 → 2026-08 | 5 年 PIT 全市场回测<br>
  undervalued 组（F≥7 + 高 BM）按 ROA 归一化加权 vs 基线 conviction
</div>

<div class="verdict">
  结论：ROA 加权 -3.7pp（+8.9% vs +12.6%）｜ 改进无效
</div>

<div class="grid">
  <div class="card">
    <h3>核心指标对比</h3>
    <table>
      <tr><th>指标</th><th>基线 F-Score</th><th>ROA 加权</th><th>差异</th></tr>
      <tr><td>总收益</td>
        <td class="{'pos' if st_b['ret'] > 0 else 'neg'}">{st_b['ret']:+.1%}</td>
        <td class="{'pos' if st_r['ret'] > 0 else 'neg'}">{st_r['ret']:+.1%}</td>
        <td class="{'pos' if st_r['ret']-st_b['ret'] > 0 else 'neg'}">{st_r['ret']-st_b['ret']:+.1%}pp</td></tr>
      <tr><td>年化收益</td>
        <td>{st_b['annual']:+.1%}</td>
        <td>{st_r['annual']:+.1%}</td>
        <td class="{'pos' if st_r['annual']-st_b['annual'] > 0 else 'neg'}">{st_r['annual']-st_b['annual']:+.1%}pp</td></tr>
      <tr><td>最大回撤</td>
        <td class="neg">{st_b['maxdd']:.1%}</td>
        <td class="neg">{st_r['maxdd']:.1%}</td>
        <td>{st_r['maxdd']-st_b['maxdd']:+.1%}pp</td></tr>
      <tr><td>夏普比率</td>
        <td>{st_b['sharpe']:.2f}</td>
        <td>{st_r['sharpe']:.2f}</td>
        <td class="{'pos' if st_r['sharpe']-st_b['sharpe'] > 0 else 'neg'}">{st_r['sharpe']-st_b['sharpe']:+.2f}</td></tr>
      <tr><td>超额（vs 沪深300）</td>
        <td class="pos">+{st_b['ret']-st_bm['ret']:.1%}</td>
        <td class="pos">+{st_r['ret']-st_bm['ret']:.1%}</td>
        <td class="neg">{(st_r['ret']-st_bm['ret'])-(st_b['ret']-st_bm['ret']):+.1%}pp</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>逐年收益对比</h3>
    <table>
      <tr><th>年份</th><th>基线</th><th>ROA 加权</th><th>差异</th></tr>"""

years = sorted(set(list(st_b["yearly"].keys()) + list(st_r["yearly"].keys())))
for y in years:
    b = st_b["yearly"].get(y, 0)
    r = st_r["yearly"].get(y, 0)
    diff = r - b
    html += f"""
      <tr><td>{y}</td>
        <td class="{'pos' if b > 0 else 'neg'}">{b:+.1%}</td>
        <td class="{'pos' if r > 0 else 'neg'}">{r:+.1%}</td>
        <td class="{'pos' if diff > 0 else 'neg'}">{diff:+.1%}pp</td></tr>"""

html += f"""
    </table>
  </div>
</div>

<div class="card">
  <h3>净值曲线对比（2021-06 → 2026-08）</h3>"""

# SVG chart
cw, ch = 1050, 400
pl, pr, pt, pb = 60, 30, 30, 40
pw, ph = cw - pl - pr, ch - pt - pb

all_vals = list(base_s.values()) + list(roaw_s.values()) + list(bm_s.values())
vmin = math.floor(min(all_vals) * 10) / 10
vmax = math.ceil(max(all_vals) * 10) / 10

def x(i):
    return pl + pw * i / (len(months) - 1)

def y(v):
    return pt + ph * (1 - (v - vmin) / (vmax - vmin))

def path(series):
    pts = []
    for i, m in enumerate(months):
        if m in series:
            pts.append(f"{x(i):.1f},{y(series[m]):.1f}")
    return " ".join(pts)

# Grid lines
html += f'<svg width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}">'
for g in range(5):
    gv = vmin + (vmax - vmin) * g / 4
    gy = y(gv)
    html += f'<line x1="{pl}" y1="{gy:.1f}" x2="{cw-pr}" y2="{gy:.1f}" stroke="#e0e0e0" stroke-width="1"/>'
    html += f'<text x="{pl-5}" y="{gy+4:.1f}" text-anchor="end" font-size="11" fill="#888">{gv:.1f}</text>'

# Benchmark
html += f'<polyline points="{path(bm_s)}" fill="none" stroke="#95a5a6" stroke-width="1.5" stroke-dasharray="4,3"/>'
# Baseline
html += f'<polyline points="{path(base_s)}" fill="none" stroke="#2c3e50" stroke-width="2"/>'
# ROA weighted
html += f'<polyline points="{path(roaw_s)}" fill="none" stroke="#e74c3c" stroke-width="2"/>'

# X axis labels
for i in range(0, len(months), 6):
    html += f'<text x="{x(i):.1f}" y="{ch-pb+15}" text-anchor="middle" font-size="11" fill="#888">{months[i]}</text>'

# Legend
html += f'<rect x="{cw-200}" y="{pt}" width="180" height="55" fill="white" stroke="#ddd" rx="5"/>'
html += f'<line x1="{cw-190}" y1="{pt+12}" x2="{cw-165}" y2="{pt+12}" stroke="#2c3e50" stroke-width="2"/>'
html += f'<text x="{cw-160}" y="{pt+16}" font-size="12" fill="#333">基线 F-Score ({st_b["ret"]:+.1%})</text>'
html += f'<line x1="{cw-190}" y1="{pt+30}" x2="{cw-165}" y2="{pt+30}" stroke="#e74c3c" stroke-width="2"/>'
html += f'<text x="{cw-160}" y="{pt+34}" font-size="12" fill="#333">ROA 加权 ({st_r["ret"]:+.1%})</text>'
html += f'<line x1="{cw-190}" y1="{pt+48}" x2="{cw-165}" y2="{pt+48}" stroke="#95a5a6" stroke-width="1.5" stroke-dasharray="4,3"/>'
html += f'<text x="{cw-160}" y="{pt+52}" font-size="12" fill="#666">沪深300 ({st_bm["ret"]:+.1%})</text>'

html += '</svg>'
html += '</div>'

# Per-period comparison table
html += """
<div class="card">
  <h3>逐调仓期超额收益对比</h3>
  <table>
    <tr><th>调仓月</th><th>报告期</th><th>基线收益</th><th>基线超额</th>
    <th>ROA 收益</th><th>ROA 超额</th><th>差异</th></tr>"""

for i in range(len(base_periods)):
    bp = base_periods[i]
    rp = roaw_periods[i] if i < len(roaw_periods) else {}
    diff = rp.get("excess", 0) - bp["excess"]
    month_label = bp["month"]
    period_label = PIT_DATES[i][1] if i < len(PIT_DATES) else ""
    html += f"""
    <tr>
      <td>{month_label}</td>
      <td>{period_label}</td>
      <td class="{'pos' if bp['ret'] > 0 else 'neg'}">{bp['ret']:+.1%}</td>
      <td class="{'pos' if bp['excess'] > 0 else 'neg'}">{bp['excess']:+.1%}</td>
      <td class="{'pos' if rp.get('ret', 0) > 0 else 'neg'}">{rp.get('ret', 0):+.1%}</td>
      <td class="{'pos' if rp.get('excess', 0) > 0 else 'neg'}">{rp.get('excess', 0):+.1%}</td>
      <td class="{'pos' if diff > 0 else 'neg'}">{diff:+.1%}pp</td>
    </tr>"""

html += """
  </table>
</div>

<div class="analysis">
  <h3>为什么 ROA 加权反而更差？</h3>
  <p><b>核心问题：高 ROA 在 undervalued 组内系统性地偏向周期股盈利峰值。</b></p>
  <p>在 Piotroski &amp; So 框架中，undervalued = F≥7 + 高 BM（低 PB）。这组股票已经通过
  F-score 的 9 个二值指标筛选出基本面改善的标的。再用 ROA 加权，等价于在"已经便宜且改善"
  的标的中，进一步向<b>当前盈利能力最高</b>的票倾斜。问题在于：</p>
  <ol>
    <li><b>周期股 ROA 峰值 = 买入陷阱</b>：钢铁（宝钢 ROA=8.81%）、化工（新乡化纤 ROA=19.39%）、
      煤炭（电投能源 ROA=14.19%）等周期股在盈利峰值时 ROA 极高，但此时往往是行业景气顶点。
      ROA 加权使组合在这些时点超配周期股，随后周期下行导致大幅回撤。</li>
    <li><b>2022-04 期典型</b>：ROA 加权将新乡化纤（ROA=19.39%）和宝钢（ROA=8.81%）顶到最大仓位，
      但随后 2022 年下半年化工和钢铁价格暴跌，该期超额 -8.9pp。</li>
    <li><b>2025-04 期典型</b>：电投能源（ROA=14.19%）、中远海控（ROA=13.26%）获得最大仓位，
      但这些是周期高点，随后超额 -11.3pp。</li>
    <li><b>F-score 已含 ROA 信息</b>：F1（ROA>0）和 F2（dROA>0）已经将 ROA 的方向和趋势纳入。
      再用 ROA 绝对值加权，信息重叠且引入了周期偏差。</li>
  </ol>
  <p style="color: #e74c3c;"><b>结论：ROA 加权强化 = 无效改进。</b> 与之前测试的 IRR 门控、BSADF 叠加、
  减速清仓一样，属于"看似合理但实测拖累"的变体。F-Score 基线 +12.6% 仍是最优配置。</p>
</div>

<div class="note">
  <b>实验记录</b>：这是 F-Score 策略的第 4 次变体测试。截至 2026-08-19 的变体结果汇总：<br>
  ✅ 有效：估值卖出（+11pp）<br>
  ❌ 无效：IRR 门控 / BSADF 叠加 / 减速清仓 / <b>ROA 加权（-3.7pp）</b><br><br>
  <b>方法论教训</b>：在 F-score 已有的信息维度上叠加同源因子（ROA 被 F1/F2 覆盖），
  不仅信息增益有限，反而引入周期股偏误。下一步应探索正交维度（如行业中性化、
  动量叠加、或质量变化率而非水平值）。
</div>

</body>
</html>"""

with open("_fs_roaw_report.html", "w", encoding="utf-8") as f:
    f.write(html)

print("报告已生成: _fs_roaw_report.html")
print(f"基线: {st_b['ret']:+.1%} / {st_b['maxdd']:.1%} / Sharpe {st_b['sharpe']:.2f}")
print(f"ROAW: {st_r['ret']:+.1%} / {st_r['maxdd']:.1%} / Sharpe {st_r['sharpe']:.2f}")
print(f"差异: {st_r['ret']-st_b['ret']:+.1%}pp")
