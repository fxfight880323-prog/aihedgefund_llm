# -*- coding: utf-8 -*-
"""高质量放松PE排序实验报告生成器"""
import json, os, sys, html
sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"

d = json.load(open(BASE + "_bt_qrelax_results.json", encoding="utf-8"))
r = d["results"]
holdings = d.get("holdings", {})

# --- data prep ---
variants = ["core_finex", "q20", "q40", "q50", "two_bucket", "qadj_pe"]
labels = {
    "core_finex": "纯PE升序(基线)",
    "q20": "80%PE+20%质量",
    "q40": "60%PE+40%质量",
    "q50": "50%PE+50%质量",
    "two_bucket": "30便宜+10质量",
    "qadj_pe": "质量调整PE",
}
base = r["core_finex"]

# NAV series for chart (subsample to ~200 points)
def sample_nav(nav_list, n=200):
    if len(nav_list) <= n:
        return nav_list
    step = len(nav_list) / n
    return [nav_list[int(i * step)] for i in range(n)] + [nav_list[-1]]

nav_data = {}
for v in variants:
    nav_data[v] = sample_nav(r[v]["nav"])

# q20 swap detail
swap_detail = []
for month in sorted(holdings.get("core_finex", {})):
    core_map = {h["tk"]: h for h in holdings["core_finex"][month]}
    q20_map = {h["tk"]: h for h in holdings["q20"][month]}
    q20_in = set(q20_map) - set(core_map)
    core_out = set(core_map) - set(q20_map)
    for tk in sorted(q20_in):
        h = q20_map[tk]
        swap_detail.append({"month": month, "type": "in", "tk": tk,
                            "pe": h["pe"], "gpm": h["gpm"], "roe": h["roe"], "q": h["q_score"]})
    for tk in sorted(core_out):
        h = core_map[tk]
        swap_detail.append({"month": month, "type": "out", "tk": tk,
                            "pe": h["pe"], "gpm": h["gpm"], "roe": h["roe"], "q": h["q_score"]})

# --- HTML ---
def esc(s):
    return html.escape(str(s)) if s else "—"

rows = []
for v in variants:
    rr = r[v]
    delta_ret = rr["total"] - base["total"]
    delta_mdd = rr["mdd"] - base["mdd"]
    ra = rr["total"] / rr["mdd"] if rr["mdd"] > 0 else 0
    delta_ra = ra - base["total"] / base["mdd"]
    tag = " ← 基线" if v == "core_finex" else ""
    arrow = "▲" if delta_ret > 0.5 else ("▼" if delta_ret < -0.5 else "≈")
    color = "#c0392b" if delta_ret < -0.5 else ("#1e8449" if delta_ret > 0.5 else "#566573")
    rows.append(f"""
    <tr style="{'background:#fff3cd' if v == 'core_finex' else ''}">
      <td><b>{esc(labels[v])}</b>{tag}</td>
      <td class="mono" style="color:{color}">{arrow} {rr['total']:+.2%}</td>
      <td class="mono">{rr['ann']:+.2%}</td>
      <td class="mono">{rr['mdd']:.2%}</td>
      <td class="mono" style="color:{color}">{delta_ret:+.2%}</td>
      <td class="mono" style="color:{'green' if delta_mdd < -0.3 else ('red' if delta_mdd > 0.3 else '')}">{delta_mdd:+.2%}</td>
      <td class="mono"><b>{ra:.2f}</b></td>
      <td class="mono" style="color:{'green' if delta_ra > 0.05 else ('red' if delta_ra < -0.05 else '')}">{delta_ra:+.2f}</td>
    </tr>""")

rows_html = "\n".join(rows)

# swap detail table
swap_rows = []
for s in swap_detail:
    bg = "#eaf7ea" if s["type"] == "in" else "#fdedec"
    arrow = "↗ 新增" if s["type"] == "in" else "↘ 踢出"
    swap_rows.append(f"""
    <tr style="background:{bg}">
      <td class="mono">{esc(s['month'])}</td>
      <td>{arrow}</td>
      <td class="mono">{esc(s['tk'])}</td>
      <td class="mono">{s['pe']:.1f}</td>
      <td class="mono">{s['gpm']:.1f}%</td>
      <td class="mono">{s['roe']:.1f}%</td>
      <td class="mono"><b>{s['q']:.1f}</b></td>
    </tr>""")
swap_html = "\n".join(swap_rows)

# NAV chart data
nav_series = []
colors_chart = {"core_finex": "#566573", "q20": "#e74c3c", "q40": "#f39c12",
                "q50": "#2980b9", "two_bucket": "#8e44ad", "qadj_pe": "#27ae60"}
for v in variants:
    pts = nav_data[v]
    series = {"name": labels[v], "color": colors_chart[v],
              "data": [{"date": p["date"], "nav": round(p["nav"] / 1000000, 4)} for p in pts]}
    nav_series.append(series)

nav_json = json.dumps(nav_series, ensure_ascii=False)

# Bar chart data
bar_data = []
for v in variants:
    bar_data.append({"label": labels[v], "ret": round(r[v]["total"] * 100, 2),
                     "mdd": round(r[v]["mdd"] * 100, 2)})
bar_json = json.dumps(bar_data, ensure_ascii=False)

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>高质量放松PE排序实验</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2c3e50; line-height: 1.6; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size: 24px; color: #1a1a2e; margin-bottom: 8px; }}
h2 {{ font-size: 18px; color: #1a1a2e; margin: 28px 0 12px; border-left: 4px solid #e74c3c; padding-left: 12px; }}
h3 {{ font-size: 15px; color: #34495e; margin: 16px 0 8px; }}
.subtitle {{ color: #7f8c8d; font-size: 13px; margin-bottom: 20px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin: 12px 0; }}
th {{ background: #2c3e50; color: #fff; padding: 10px 8px; text-align: center; font-size: 13px; font-weight: 600; }}
td {{ padding: 8px; text-align: center; font-size: 13px; border-bottom: 1px solid #ecf0f1; }}
td.l {{ text-align: left; }}
.mono {{ font-family: "Cascadia Code", "Consolas", monospace; }}
.card {{ background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 16px 0; }}
.highlight {{ background: #fff3cd; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; color: #fff; }}
.badge-win {{ background: #1e8449; }}
.badge-lose {{ background: #c0392b; }}
.badge-neutral {{ background: #566573; }}
.chart-box {{ background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 12px 0; height: 420px; }}
.insight {{ background: #fff; border-left: 4px solid #e74c3c; padding: 14px 18px; margin: 12px 0; border-radius: 0 8px 8px 0; font-size: 14px; }}
.insight strong {{ color: #c0392b; }}
.formula {{ background: #1a1a2e; color: #e8e8e8; padding: 12px 16px; border-radius: 8px; font-family: monospace; font-size: 13px; margin: 8px 0; }}
.summary-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin: 16px 0; }}
.summary-card {{ background: #fff; border-radius: 10px; padding: 16px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }}
.summary-card .num {{ font-size: 28px; font-weight: 700; font-family: monospace; }}
.summary-card .label {{ font-size: 12px; color: #7f8c8d; margin-top: 4px; }}
.positive {{ color: #c0392b; }}
.negative {{ color: #1e8449; }}
footer {{ text-align: center; color: #95a5a6; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #ecf0f1; }}
</style>
</head>
<body>
<div class="container">
  <h1>高质量放松 PE 排序实验</h1>
  <p class="subtitle">日频 + 复权口径 · core_finex 基线 · 10 期半年度调仓 · 2021-08 ~ 2026-08 · 万得全A PIT 池</p>

  <div class="insight">
    <strong>核心问题：</strong>福耀玻璃（PE 17.4, gpm 38%, ROE 22%）通过了全部质量筛选但 PE 排名第 132/226，无法进入最终名单。
    能否对高质量公司放松 PE 排序，让它们进入组合？答案是：<strong>小幅质量倾斜有效（+3.4pp），大幅放松或强制纳入有害（-4~-13pp）</strong>。
  </div>

  <h2>① 六变体总览</h2>
  <table>
    <thead>
      <tr>
        <th>变体</th><th>总收益</th><th>年化</th><th>MDD</th>
        <th>Δ收益(vs基线)</th><th>ΔMDD</th><th>收益/MDD</th><th>Δ风险调整</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="num positive">+3.40pp</div>
      <div class="label">q20 收益提升</div>
    </div>
    <div class="summary-card">
      <div class="num positive">-3.07pp</div>
      <div class="label">q50 MDD 降低</div>
    </div>
    <div class="summary-card">
      <div class="num negative">-13.16pp</div>
      <div class="label">two_bucket 灾难</div>
    </div>
  </div>

  <h2>② NAV 曲线对比</h2>
  <div class="chart-box"><canvas id="navChart"></canvas></div>

  <h2>③ 收益与回撤对比</h2>
  <div class="chart-box"><canvas id="barChart"></canvas></div>

  <h2>④ 关键发现</h2>

  <div class="card">
    <h3>✅ q20（80%PE + 20%质量）= 最优增量</h3>
    <div class="formula">blend_rank = 0.80 × pe_percentile + 0.20 × quality_percentile</div>
    <p style="font-size: 14px; margin-top: 8px;">
      收益 <span class="positive">+32.85%</span> vs 基线 +29.45%（<b>+3.40pp</b>）<br>
      MDD 22.03% vs 22.12%（几乎不变）<br>
      风险调整收益 1.49 vs 1.33（<b>+12%</b> 提升）<br>
      每期仅替换 1~6 只股票，与基线重叠 34~39/40
    </p>
  </div>

  <div class="card">
    <h3>⚠️ q50 = 最佳风险控制器</h3>
    <p style="font-size: 14px;">
      收益 +30.53%（仅 +1.08pp），但 MDD 降至 <b>19.05%</b>（-3.07pp）<br>
      风险调整收益 1.60 = 全场最高<br>
      适合追求低波动的配置需求
    </p>
  </div>

  <div class="card">
    <h3>❌ two_bucket（30便宜 + 10质量）= 灾难</h3>
    <p style="font-size: 14px;">
      收益 <span class="negative">仅 +16.29%</span>（-13.16pp）<br>
      原因：从"最便宜30只"之外选"最高质量10只" = 选了 PE 最高的质量股<br>
      这本质上是"质量优先"排序的退化版——而回测已证实质量优先跑输等权全A
    </p>
  </div>

  <div class="card">
    <h3>❌ qadj_pe（PE×质量折扣）= 负贡献</h3>
    <div class="formula">adj_pe = PE × (1 - 0.15 × quality_z_score)</div>
    <p style="font-size: 14px;">
      收益 +25.13%（-4.33pp）<br>
      乘法调整过度放大利高质量因子，把太多贵股拉入组合
    </p>
  </div>

  <h2>⑤ q20 的选股逻辑：替换了什么？</h2>
  <p style="font-size: 14px; margin-bottom: 12px;">
    q20 每期替换 1~6 只，替换方向一致：<b>踢出"便宜但低质"的边缘股，换成"稍贵但高质"的股票</b>。
  </p>
  <table>
    <thead>
      <tr><th>调仓期</th><th>方向</th><th>代码</th><th>PE</th><th>毛利率</th><th>ROE</th><th>质量分</th></tr>
    </thead>
    <tbody>{swap_html}</tbody>
  </table>

  <h2>⑥ 福耀玻璃为什么没被救回来？</h2>
  <div class="insight">
    <p style="font-size: 14px;">
      福耀玻璃在 <strong>所有变体、所有 10 期</strong> 中均未进入 top 40。原因：
    </p>
    <ol style="margin-left: 20px; font-size: 14px; margin-top: 8px;">
      <li><strong>池子太大</strong>：每期通过筛选的候选池 173~312 只，PE 排名 ~130/200+</li>
      <li><strong>PE 差距太大</strong>：top40 的 PE 在 6~14 区间，福耀 PE 17.4，差距 >3pp</li>
      <li><strong>质量分不突出</strong>：gpm 38% / ROE 22% 是"好"但不是"极好"——池内有 gpm 50-90% / ROE 25-35% 的股票质量分更高</li>
      <li><strong>即使 50% 质量权重</strong>：PE 百分位 ~35% × 0.5 + 质量分 ~65% × 0.5 = 50，仍低于 top40 阈值 ~55</li>
    </ol>
    <p style="font-size: 14px; margin-top: 8px;">
      <strong>结论</strong>：质量放松是对 top40 边缘股的微调，不是对 PE 中段股的拯救。福耀属于"中PE中质量"——比 top40 贵，但质量在池内也不拔尖。
    </p>
  </div>

  <h2>⑦ 实操建议</h2>
  <div class="card">
    <table>
      <thead><tr><th>方案</th><th>排序公式</th><th>收益</th><th>MDD</th><th>适用场景</th></tr></thead>
      <tbody>
        <tr style="background:#eaf7ea">
          <td><b>推荐 q20</b></td>
          <td class="mono">0.8×PE分位 + 0.2×质量分</td>
          <td class="mono positive">+32.85%</td>
          <td class="mono">22.03%</td>
          <td>默认增强层</td>
        </tr>
        <tr>
          <td>备选 q50</td>
          <td class="mono">0.5×PE分位 + 0.5×质量分</td>
          <td class="mono">+30.53%</td>
          <td class="mono">19.05%</td>
          <td>低波动需求</td>
        </tr>
        <tr>
          <td>基线 core</td>
          <td class="mono">纯 PE 升序</td>
          <td class="mono">+29.45%</td>
          <td class="mono">22.12%</td>
          <td>最简实现</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="insight">
    <p style="font-size: 14px;">
      <strong>落地方式</strong>：在现有管线 <code>_lx_now_score.py</code> 的评分函数中，将排序权重从
      <code>sort_by = pe_asc</code> 改为 <code>sort_by = 0.8*pe_pct + 0.2*q_score</code>。
      筛选/质量层/band 规避层不变。福耀玻璃仍不会入选——但那是正确的行为：它的 PE 确实不在 alpha 区间。
    </p>
  </div>

  <footer>
    高质量放松PE排序实验 · 数据截至 2026-08-24 · 日频+复权口径 · core_finex 基线<br>
    回测引擎: vnpy BacktestingEngine · 成本 5bp+10bp · 半年度调仓 · 单票5%上限
  </footer>
</div>

<script>
const navData = {nav_json};
const barData = {bar_json};

// NAV chart
new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{
    datasets: navData.map(s => ({{
      label: s.name,
      data: s.data.map(p => ({{x: p.date, y: p.nav}})),
      borderColor: s.color,
      borderWidth: s.name.includes('基线') || s.name.includes('20%') ? 2.5 : 1.5,
      pointRadius: 0,
      tension: 0.1,
      fill: false,
    }})),
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }},
      tooltip: {{ mode: 'index', intersect: false }},
    }},
    scales: {{
      x: {{ type: 'time', time: {{ unit: 'year' }}, title: {{ display: true, text: '日期' }} }},
      y: {{ title: {{ display: true, text: 'NAV (百万)' }}, ticks: {{ callback: v => v.toFixed(1) }} }},
    }},
  }},
}});

// Bar chart
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: barData.map(d => d.label),
    datasets: [
      {{ label: '总收益 %', data: barData.map(d => d.ret), backgroundColor: '#e74c3c', borderRadius: 4 }},
      {{ label: 'MDD %', data: barData.map(d => d.mdd), backgroundColor: '#3498db', borderRadius: 4 }},
    ],
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom' }} }},
    scales: {{
      y: {{ title: {{ display: true, text: '%' }}, ticks: {{ callback: v => v + '%' }} }},
    }},
  }},
}});
</script>
</body>
</html>
"""

out_path = BASE + "_bt_qrelax_report.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"报告 → {out_path}")
