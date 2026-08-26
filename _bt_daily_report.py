# -*- coding: utf-8 -*-
"""生成 _bt_daily_report.html — LX-core 三变体 日频颗粒度回测报告（v2 复权口径）
口径演进三层对比：月频+未复权(旧) → 日频+未复权(颗粒度修正) → 日频+复权(真实口径)
两个修正维度分开归因：颗粒度（成交时点）、复权（分红）。
基准：ew_hold 半年调仓等权全A（同口径）/ ew_daily 每日再平衡（参考）/ 中证全指价格指数。
"""
import json, sys, os
sys.stdout.reconfigure(encoding="utf-8")
BASE = "D:/workspace/ai_fund_framework/"

daily = json.load(open(BASE + "_bt_daily_results.json", encoding="utf-8"))       # 日频+复权
monthly = json.load(open(BASE + "_bt_band_report_data.json", encoding="utf-8"))  # 月频+未复权
unadj = json.load(open(BASE + "_bt_daily_results_unadj.json", encoding="utf-8")) # 日频+未复权（颗粒度修正版）
ew_hold = json.load(open(BASE + "_bt_daily_ew_hold_nav.json", encoding="utf-8")) # 半年调仓等权 日频复权
ew_daily = json.load(open(BASE + "_bt_daily_ew_nav.json", encoding="utf-8"))     # 每日再平衡 日频复权

res, idx = daily["results"], daily["idx"]
mstat = monthly["stat"]
ures = unadj["results"]
periods = daily["periods"]

PCT = lambda x: f"{x:+.1%}"
PP = lambda x: f"{x*100:+.1f}pp"

# 超额（日频复权口径）
for v in res:
    res[v]["excess_ew_hold"] = res[v]["total"] - ew_hold["total"]
    res[v]["excess_ew_daily"] = res[v]["total"] - ew_daily["total"]

# ---------- 表 1: 最终推荐口径（日频+复权）总览 ----------
def row(v, label, hl=False):
    s = res[v]
    cls = "hl" if hl else ""
    return f"""<tr class="{cls}">
    <td>{label}</td><td>{PCT(s['total'])}</td><td>{PCT(s['ann'])}</td>
    <td>{s['mdd']:.1%}</td><td>{PP(s['excess_ew_hold'])}</td><td>{PP(s['excess_idx'])}</td></tr>"""

t1 = ""
t1 += row("core", "core（基线，LX-core）", hl=True)
t1 += row("core_finex", "core_finex（+金融剔除）")
t1 += row("core_finex_band", "core_finex_band（+金融+PB band）", hl=True)
t1 += f"""<tr class="base"><td>等权全A·半年调仓（同口径基准）</td>
    <td>{PCT(ew_hold['total'])}</td><td>{PCT(ew_hold['ann'])}</td><td>{ew_hold['mdd']:.1%}</td>
    <td class="na">—</td><td class="na">—</td></tr>
<tr class="base"><td>等权全A·每日再平衡（参考，含再平衡收益）</td>
    <td>{PCT(ew_daily['total'])}</td><td>{PCT(ew_daily['ann'])}</td><td>{ew_daily['mdd']:.1%}</td>
    <td class="na">—</td><td class="na">—</td></tr>
<tr class="base"><td>中证全指 000985（市值加权，价格指数）</td>
    <td>{PCT(idx['total'])}</td><td>{PCT(idx['ann'])}</td><td>{idx['mdd']:.1%}</td>
    <td class="na">—</td><td class="na">—</td></tr>"""

# ---------- 表 2: 口径演进三层对比 ----------
VARIANT_LABEL = [("core", "core 基线"), ("core_finex", "+金融剔除"), ("core_finex_band", "+金融+PB band")]
# 月频未复权：mstat；日频未复权：unadj；日频复权：res
t2 = ""
for v, label in VARIANT_LABEL:
    m = mstat[v]                      # 月频+未复权
    d1 = ures[v]                      # 日频+未复权
    d2 = res[v]                       # 日频+复权
    # 颗粒度修正：月频→日频（同为未复权）
    g_d = d1["total"] - m["total"]; g_m = d1["mdd"] - abs(m["mdd"])
    # 复权修正：日频未复权→日频复权
    a_d = d2["total"] - d1["total"]; a_m = d2["mdd"] - d1["mdd"]
    # 净变化：月频未复权→日频复权
    n_d = d2["total"] - m["total"]; n_m = d2["mdd"] - abs(m["mdd"])
    def cls(x): return "pos" if x > 0 else ("neg" if x < 0 else "")
    t2 += f"""<tr class="hd"><td rowspan="4">{label}</td><td>月频 + 未复权（旧口径）</td>
        <td>{PCT(m['total'])}</td><td>{PCT(m['ann'])}</td><td>{abs(m['mdd']):.1%}</td></tr>
    <tr class="d1"><td>日频 + 未复权（颗粒度修正）</td>
        <td>{PCT(d1['total'])}</td><td class="na">—</td><td>{d1['mdd']:.1%}</td></tr>
    <tr class="d2"><td>日频 + 复权（真实口径 ✓）</td>
        <td>{PCT(d2['total'])}</td><td>{PCT(d2['ann'])}</td><td>{d2['mdd']:.1%}</td></tr>
    <tr class="delta"><td>颗粒度影响（月频→日频）</td>
        <td class="{cls(g_d)}">{PP(g_d)}</td><td class="na">—</td>
        <td class="{cls(g_m)}">{PP(g_m)}</td></tr>
    <tr class="delta"><td>复权影响（未复权→复权）</td>
        <td class="{cls(a_d)}">{PP(a_d)}</td><td class="na">—</td>
        <td class="{cls(a_m)}">{PP(a_m)}</td></tr>
    <tr class="delta"><td>净变化（旧→真实）</td>
        <td class="{cls(n_d)}">{PP(n_d)}</td><td class="na">—</td>
        <td class="{cls(n_m)}">{PP(n_m)}</td></tr>"""

# ---------- 图数据 ----------
days = [n["date"] for n in res["core"]["nav"]]
nav_series = {
    "core": [round(n["nav"] / 1_000_000, 4) for n in res["core"]["nav"]],
    "finex": [round(n["nav"] / 1_000_000, 4) for n in res["core_finex"]["nav"]],
    "finex_band": [round(n["nav"] / 1_000_000, 4) for n in res["core_finex_band"]["nav"]],
    "ew_hold": [round(ew_hold["nav"][d], 4) for d in days if d in ew_hold["nav"]],
    "ew_daily": [round(ew_daily["nav"][d], 4) for d in days if d in ew_daily["nav"]],
    "idx": [round(idx["nav"][d], 4) for d in days],
}
# 口径对比柱状（core 为例，展示三维）
evol = {
    "labels": ["月频+未复权\n(旧口径)", "日频+未复权\n(颗粒度)", "日频+复权\n(真实)"],
    "total": [round(mstat["core"]["total"] * 100, 1),
              round(ures["core"]["total"] * 100, 1),
              round(res["core"]["total"] * 100, 1)],
    "mdd": [round(abs(mstat["core"]["mdd"]) * 100, 1),
            round(ures["core"]["mdd"] * 100, 1),
            round(res["core"]["mdd"] * 100, 1)],
}
# band 增量对比（月频 vs 日频复权）
band_delta = {
    "labels": ["月频口径", "日频+复权口径"],
    "finex": [round(mstat["core_finex"]["total"] * 100, 1), round(res["core_finex"]["total"] * 100, 1)],
    "band": [round(mstat["core_finex_band"]["total"] * 100, 1), round(res["core_finex_band"]["total"] * 100, 1)],
}

method = f"""<ul style="margin:4px 0; padding-left:20px;">
<li><b>颗粒度修正（月频→日频）</b>：月频引擎调仓月 t 下买单、t+1 <b>月末</b>才撮合 → 每个调仓周期多持旧仓 1 个月，收益虚高（core +60.0%→+17.9% 未复权口径下 -42.1pp）；日频 T+1 日开盘成交才是真实交易口径。调仓触发日 = ≤ as_of 的最近交易日（2022-04-30 等非交易日映射）。</li>
<li><b>复权修正（未复权→复权）</b>：日频引擎原用未复权 close（缺分红），core 持仓 80% 金融高分红股被系统性低估（工行 adj/close=2.55）；改用 adj 折算 OHLC 复权价后 core +17.9%→+55.55%（+37.7pp）。<b>分红是真实持有收益，必须计入</b>。</li>
<li><b>MDD 口径</b>：标准 (peak−trough)/peak，按日频全序列计算。月频采样丢失月内回撤（finex 未复权口径 -27.0%→日频 -35.4%）；复权后分红平滑回撤（core -35.4%→-19.1%）。</li>
<li><b>基准构造差异（重要）</b>：半年调仓等权全A（+41.1%）= 每期调仓日等权买入 PIT 成分持有至下期，与策略严格同口径；每日再平衡等权全A（+93.5%）= 每日按成分等权再平衡，含巨大再平衡收益（volatility harvesting），<b>不能直接作为半年调仓策略的超额基准</b>。月频基准（+52.9%）为月度再平衡，介于两者之间。</li>
<li><b>数据源</b>：242 只持仓股日频 = juzi return_panel parquet（308,863 行，含 open/high/low/close/adj_close/daily_return）；全市场 = 6 段 parquet（6,621,011 行，5730 只，1288 天）；中证全指 = 腾讯日K（价格指数，不含分红）。</li>
<li><b>成本</b>：5bp 佣金 + 10bp 滑点，annual_periods=252。</li>
</ul>"""

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>LX-core 日频颗粒度回测 — 真实口径业绩（日频+复权）</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
body {{ font-family: "Microsoft YaHei", -apple-system, sans-serif; margin: 0;
  background: #fafaf8; color: #2c2c2a; line-height: 1.6; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding: 24px 20px 60px; }}
h1 {{ font-size: 24px; margin: 8px 0 4px; }}
h2 {{ font-size: 18px; margin: 32px 0 12px; border-left: 4px solid #0c447c; padding-left: 10px; }}
.sub {{ color: #6b6a64; font-size: 13px; margin-bottom: 20px; }}
.card {{ background: #fff; border: 1px solid #e3e1d8; border-radius: 10px; padding: 16px 18px; margin: 14px 0; }}
.chartbox {{ background: #fff; border: 1px solid #e3e1d8; border-radius: 10px; padding: 14px; margin: 14px 0; }}
.verdict {{ background: #fdf6e3; border: 1px solid #ef9f27; border-left: 5px solid #ef9f27; border-radius: 8px;
  padding: 14px 18px; margin: 16px 0; }}
.verdict b {{ color: #8a5a00; }}
.warn {{ background: #eaf4ee; border: 1px solid #27ae60; border-left: 5px solid #27ae60; border-radius: 8px;
  padding: 14px 18px; margin: 16px 0; }}
.warn b {{ color: #1e8449; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0; }}
th, td {{ border: 1px solid #e3e1d8; padding: 6px 10px; text-align: right; }}
th {{ background: #f1efe8; font-weight: 600; text-align: center; }}
td:first-child {{ text-align: left; font-weight: 600; }}
tr.hl td {{ background: #eef4fb; }}
tr.base td {{ background: #f6f5f1; color: #6b6a64; }}
tr.hd td {{ background: #f1efe8; }}
tr.d2 td {{ background: #eef8f1; }}
tr.delta td {{ background: #fdf6e3; color: #8a6d1a; font-weight: 700; }}
.pos {{ color: #c0392b; font-weight: 600; }}
.neg {{ color: #1e8449; font-weight: 600; }}
.na {{ color: #bbb; }}
.note {{ color: #6b6a64; font-size: 12px; margin-top: 6px; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
@media (max-width: 800px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
.kpi {{ display: inline-block; min-width: 150px; margin: 4px 14px 4px 0; }}
.kpi .v {{ font-size: 22px; font-weight: 700; color: #0c447c; }}
.kpi .l {{ font-size: 12px; color: #6b6a64; }}
.kpi .delta {{ font-size: 13px; font-weight: 600; }}
</style></head><body><div class="wrap">

<h1>LX-core 三变体回测：收益统计颗粒度确定（日频）+ 复权口径修正</h1>
<div class="sub">回测区间 2021-06 ~ 2026-08（1270 个交易日）｜调仓 2021-08 ~ 2026-04（10 期半年度）｜池子：万得全A PIT 成分｜成本：5bp+10bp｜vnpy 撮合（T+1 日开盘成交）</div>

<div class="warn">
<b>✅ 确定口径：日频 + 复权（真实收益口径）</b>
<ol style="margin:6px 0 0; padding-left:20px;">
<li><b>颗粒度=日频</b>：月频引擎 T+1 月末撮合，每调仓周期多持旧仓 1 个月，收益虚高。日频 T+1 日开盘成交才是真实交易口径。</li>
<li><b>价格=复权</b>：未复权 close 缺分红，core 持仓 80% 金融高分红股被系统性低估（+37.7pp）。分红是真实持有收益，必须计入。</li>
<li><b>真实业绩（日频+复权）</b>：core <b>+55.55%</b>（年化 +9.16%，MDD -19.13%）｜finex +29.45%（-26.1pp，金融剔除仍负贡献）｜finex_band +34.48%（+5.03pp，band 层仍正贡献）。</li>
<li><b>同口径超额</b>：core 超额半年调仓等权全A <b>+14.4pp</b>（月频旧口径 +7.1pp 被低估）；超额中证全指 +55.4pp。旧口径 +60.0% 与真实 +55.55% 相近纯属两个偏差抵消（颗粒度虚高 +42.1pp ≈ 分红缺口 +37.7pp）。</li>
</ol>
</div>

<div class="kpi"><div class="v">{PCT(res['core']['total'])}</div><div class="l">core 真实总收益(日频+复权)</div>
<div class="delta neg">{PP(res['core']['total'] - mstat['core']['total'])} vs 旧口径</div></div>
<div class="kpi"><div class="v">{PCT(res['core']['ann'])}</div><div class="l">core 年化</div></div>
<div class="kpi"><div class="v">{res['core']['mdd']:.1%}</div><div class="l">core 最大回撤(日频)</div>
<div class="delta pos">{PP(res['core']['mdd'] - abs(mstat['core']['mdd']))} vs 旧口径</div></div>
<div class="kpi"><div class="v">{PP(res['core']['excess_ew_hold'])}</div><div class="l">core 超额同口径等权全A</div></div>
<div class="kpi"><div class="v">{PP(res['core_finex_band']['total'] - res['core_finex']['total'])}</div><div class="l">band 层增量(日频复权)</div></div>

<h2>1. 最终推荐口径业绩总览（日频 + 复权）</h2>
<div class="card">
<table>
<tr><th>组合</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额等权全A·半年调仓</th><th>超额中证全指</th></tr>
{t1}
</table>
<div class="note">超额 = 同期总收益差。半年调仓等权全A 与策略同口径（期初等权买入 PIT 成分持有半年）；每日再平衡基准含再平衡收益仅作参考；中证全指为价格指数（不含分红）。</div>
</div>

<h2>2. 口径演进三层对比（本报告核心）</h2>
<div class="card">
<table>
<tr><th>变体</th><th>口径</th><th>总收益</th><th>年化</th><th>最大回撤</th></tr>
{t2}
</table>
<div class="note">颗粒度影响（月频→日频，同为未复权）：core -42.1pp（不再多持旧仓）｜复权影响（未复权→复权，同为日频）：core +37.7pp（补分红）｜净变化：core -4.5pp。MDD 复权后显著收窄（分红平滑回撤）。</div>
</div>

<h2>3. 净值曲线（日频 + 复权）</h2>
<div class="chartbox"><canvas id="navChart" height="100"></canvas></div>

<h2>4. core 口径演进：收益与回撤分解</h2>
<div class="grid2">
<div class="chartbox"><canvas id="evolTotChart" height="220"></canvas></div>
<div class="chartbox"><canvas id="evolMddChart" height="220"></canvas></div>
</div>

<h2>5. band 层增量：月频 vs 日频复权</h2>
<div class="chartbox"><canvas id="bandChart" height="220"></canvas></div>

<h2>6. 方法论说明</h2>
<div class="card" style="font-size:13px;">{method}</div>

</div>
<script>
const days = {json.dumps(days)};
const navData = {json.dumps(nav_series)};
new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{
    labels: days,
    datasets: [
      {{ label: 'core 基线', data: navData.core, borderColor: '#0c447c', backgroundColor: 'rgba(12,68,124,.08)', fill: true, tension: .2, borderWidth: 2.5, pointRadius: 0 }},
      {{ label: 'core_finex +金融剔除', data: navData.finex, borderColor: '#d68910', borderDash: [6,3], tension: .2, borderWidth: 2, pointRadius: 0 }},
      {{ label: 'core_finex_band +band', data: navData.finex_band, borderColor: '#8e44ad', tension: .2, borderWidth: 2, pointRadius: 0 }},
      {{ label: '等权全A·半年调仓(同口径)', data: navData.ew_hold, borderColor: '#95a5a6', borderDash: [2,4], tension: .2, borderWidth: 1.5, pointRadius: 0 }},
      {{ label: '等权全A·每日再平衡(参考)', data: navData.ew_daily, borderColor: '#7f8c8d', borderDash: [1,3], tension: .2, borderWidth: 1, pointRadius: 0 }},
      {{ label: '中证全指', data: navData.idx, borderColor: '#27ae60', borderDash: [2,2], tension: .2, borderWidth: 1.5, pointRadius: 0 }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top' }}, tooltip: {{ callbacks: {{ label: c => c.dataset.label + ': ' + c.parsed.y.toFixed(3) }} }} }},
    scales: {{ y: {{ title: {{ display: true, text: '净值 (起点=1.0)' }} }} }}
  }}
}});

const evol = {json.dumps(evol)};
new Chart(document.getElementById('evolTotChart'), {{
  type: 'bar',
  data: {{
    labels: evol.labels,
    datasets: [{{ label: '总收益 %', data: evol.total, backgroundColor: ['#d5c9a3', '#e0a458', '#0c447c'] }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => c.parsed.y.toFixed(1) + '%' }} }} }},
    scales: {{ y: {{ title: {{ display: true, text: '总收益 %' }}, ticks: {{ callback: v => v + '%' }} }} }}
  }}
}});
new Chart(document.getElementById('evolMddChart'), {{
  type: 'bar',
  data: {{
    labels: evol.labels,
    datasets: [{{ label: '最大回撤 %', data: evol.mdd, backgroundColor: ['#f5cba7', '#e67e22', '#e74c3c'] }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => '-' + c.parsed.y.toFixed(1) + '%' }} }} }},
    scales: {{ y: {{ title: {{ display: true, text: '回撤深度 %' }}, ticks: {{ callback: v => v + '%' }} }} }}
  }}
}});

const band = {json.dumps(band_delta)};
new Chart(document.getElementById('bandChart'), {{
  type: 'bar',
  data: {{
    labels: band.labels,
    datasets: [
      {{ label: 'core_finex（无 band）', data: band.finex, backgroundColor: '#d68910' }},
      {{ label: 'core_finex_band（+band）', data: band.band, backgroundColor: '#8e44ad' }},
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'top' }}, tooltip: {{ callbacks: {{ label: c => c.parsed.y.toFixed(1) + '%' }} }} }},
    scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }}
  }}
}});
</script>
</body></html>"""

open(BASE + "_bt_daily_report.html", "w", encoding="utf-8").write(HTML)
print(f"已生成 _bt_daily_report.html ({len(HTML)//1024}KB)")
