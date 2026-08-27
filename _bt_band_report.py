# -*- coding: utf-8 -*-
"""生成 _bt_band_report.html — LX-core 完整管线 5 年回测对比报告
三变体: core(基线) / core_finex(+金融剔除) / core_finex_band(+金融+PB band)
"""
import json, sys, html
sys.stdout.reconfigure(encoding="utf-8")

BASE = "D:/workspace/ai_fund_framework/"
d = json.load(open(BASE + "_bt_band_report_data.json", encoding="utf-8"))
names = json.load(open(BASE + "_bt_band_names.json", encoding="utf-8"))

stat, annual = d["stat"], d["annual"]
eng_nav, ew_nav, idx_nav = d["eng_nav"], d["ew_nav"], d["idx_nav"]
decomp, band_repl, fin_share, diag = d["decomp"], d["band_repl"], d["fin_share"], d["diag"]
periods = d["meta"]["periods"]

PCT = lambda x: f"{x:+.1%}"
PP = lambda x: f"{x*100:+.1f}pp"

# ---------- 名称辅助 ----------
def nm(c):
    return f"{names.get(c, c)}({c.split('.')[0]})"

# ---------- 数据序列 ----------
months = sorted(eng_nav["core"].keys())
nav_series = {
    "core": [round(eng_nav["core"][m], 4) for m in months],
    "finex": [round(eng_nav["core_finex"][m], 4) for m in months],
    "finex_band": [round(eng_nav["core_finex_band"][m], 4) for m in months],
    "ew": [round(ew_nav.get(m, 0), 4) for m in months],
    "idx": [round(idx_nav.get(m, 0), 4) for m in months],
}
fin_share_core = [fin_share[p]["n_fin"] for p in periods]

# ---------- 表格行 ----------
def stat_row(v, label, base=False, hl=False):
    s = stat[v]
    cls = "hl" if hl else ("base" if base else "")
    exc = s.get("excess_ew")
    exc_ew = PP(exc) if exc is not None else '<span class="na">—</span>'
    exc_idx = PP(s.get("excess_idx")) if s.get("excess_idx") is not None else '<span class="na">—</span>'
    return f"""<tr class="{cls}">
    <td>{label}</td><td>{PCT(s['total'])}</td><td>{PCT(s['ann'])}</td>
    <td>{s['mdd']:.1%}</td>
    <td>{exc_ew}</td><td>{exc_idx}</td></tr>"""

def annual_row(y):
    def cell(v):
        vv = annual[v].get(str(y))
        if vv is None:
            return '<td class="na">—</td>'
        cls = "pos" if vv > 0 else ("neg" if vv < 0 else "")
        return f'<td class="{cls}">{vv:+.1%}</td>'
    return f"<tr><td>{y}</td>{cell('core')}{cell('core_finex')}{cell('core_finex_band')}{cell('ew')}{cell('idx')}</tr>"

# ---------- band 替换表 ----------
band_rows = ""
n_repl = 0
for br in band_repl:
    if not br["removed"]:
        continue
    n_repl += len(br["removed"])
    removed = "<br>".join(f"<span class='rm'>{nm(c)}</span>" for c in br["removed"])
    added = "<br>".join(f"<span class='add'>{nm(c)}</span>" for c in br["added"])
    band_rows += f"<tr><td>{br['period']}</td><td>{removed}</td><td>{added}</td></tr>"

# ---------- 金融股 top 持仓 (2026-04) ----------
fin_set = set()
fin = json.load(open(BASE + "_bt_sw_fin_universe.json", encoding="utf-8"))
for sec, info in fin.items():
    if isinstance(info, dict) and isinstance(info.get("members"), list):
        fin_set.update(info["members"])
h264 = []
hold_r = json.load(open(BASE + "_bt_band_results.json", encoding="utf-8"))["holdings"]
fin_hold_264 = [(c, names.get(c, c)) for c in hold_r["2026-04"]["core"] if c in fin_set]
fin_chips = "".join(f"<span class='chip'>{n}({c.split('.')[0]})</span>" for c, n in fin_hold_264)

# ---------- 贡献拆解表 ----------
decomp_rows = ""
for v, label in [("core", "core（基线）"), ("core_finex", "core_finex（+金融剔除）"), ("core_finex_band", "core_finex_band（+band）")]:
    dc = decomp[v]
    decomp_rows += f"""<tr><td>{label}</td>
        <td>{PCT(dc['sum_fin'])}</td><td>{PCT(dc['sum_nfin'])}</td>
        <td>{PCT(dc['nav_fin_only'])}</td><td>{PCT(dc['nav_nfin_only'])}</td>
        <td>{PCT(stat[v]['total'])}</td></tr>"""

# ---------- 金融占比表 ----------
share_rows = ""
for p in periods:
    fs = fin_share[p]
    core_sh = fs["n_fin"] / 40 * 100
    share_rows += f"<tr><td>{p}</td><td>{fs['n_fin']}/40</td><td>{core_sh:.0f}%</td>" \
                   f"<td>{fs['n_finex']}/40</td><td>{fs['n_finex_band']}/40</td></tr>"

# ---------- diag 表 ----------
diag_rows = ""
for p in periods:
    dd = diag[p]
    diag_rows += f"<tr><td>{p}</td><td>{dd['univ']}</td><td>{dd['fin']}</td><td>{dd['band_high']}</td>" \
                 f"<td>{dd['core_finex_fin_drop']}</td><td>{dd['core_finex_band_fin_drop']}</td></tr>"

# ---------- 贡献堆叠图数据 ----------
stack = json.dumps({
    "labels": ["core", "core_finex", "core_finex_band"],
    "fin": [round(decomp["core"]["sum_fin"], 4), 0, 0],
    "nfin": [round(decomp["core"]["sum_nfin"], 4),
             round(decomp["core_finex"]["sum_nfin"], 4),
             round(decomp["core_finex_band"]["sum_nfin"], 4)],
})

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>LX-core 完整管线 5 年回测 — 金融剔除 + PB band 规避层</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
body {{ font-family: "Microsoft YaHei", -apple-system, sans-serif; margin: 0;
  background: #fafaf8; color: #2c2c2a; line-height: 1.6; }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 60px; }}
h1 {{ font-size: 24px; margin: 8px 0 4px; }}
h2 {{ font-size: 18px; margin: 32px 0 12px; border-left: 4px solid #0c447c; padding-left: 10px; }}
.sub {{ color: #6b6a64; font-size: 13px; margin-bottom: 20px; }}
.card {{ background: #fff; border: 1px solid #e3e1d8; border-radius: 10px; padding: 16px 18px; margin: 14px 0; }}
.chartbox {{ background: #fff; border: 1px solid #e3e1d8; border-radius: 10px; padding: 14px; margin: 14px 0; }}
.verdict {{ background: #fdf6e3; border: 1px solid #ef9f27; border-left: 5px solid #ef9f27; border-radius: 8px;
  padding: 14px 18px; margin: 16px 0; }}
.verdict b {{ color: #8a5a00; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0; }}
th, td {{ border: 1px solid #e3e1d8; padding: 6px 10px; text-align: right; }}
th {{ background: #f1efe8; font-weight: 600; text-align: center; }}
td:first-child {{ text-align: left; font-weight: 600; }}
tr.hl td {{ background: #eef4fb; }}
tr.base td {{ background: #f6f5f1; color: #6b6a64; }}
.pos {{ color: #c0392b; font-weight: 600; }}
.neg {{ color: #1e8449; font-weight: 600; }}
.na {{ color: #bbb; }}
.rm {{ color: #c0392b; }} .add {{ color: #1e8449; }}
.chip {{ display: inline-block; background: #eef4fb; border: 1px solid #c9d8ea; border-radius: 12px;
  padding: 2px 10px; margin: 2px 4px 2px 0; font-size: 12px; }}
.note {{ color: #6b6a64; font-size: 12px; margin-top: 6px; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
@media (max-width: 800px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
.kpi {{ display: inline-block; min-width: 130px; margin: 4px 10px 4px 0; }}
.kpi .v {{ font-size: 22px; font-weight: 700; color: #0c447c; }}
.kpi .l {{ font-size: 12px; color: #6b6a64; }}
.kpi .delta {{ font-size: 13px; font-weight: 600; }}
</style></head><body><div class="wrap">

<h1>LX-core 完整管线 5 年回测：金融剔除 + PB band 规避层</h1>
<div class="sub">回测区间 2021-06 ~ 2026-08（调仓日 2021-08 ~ 2026-04，10 期半年度）｜池子：万得全A PIT 成分｜成本：5bp+10bp｜vnpy 撮合时序</div>

<div class="verdict">
<b>三个核心结论</b>
<ol style="margin:6px 0 0; padding-left:20px;">
<li><b>金融剔除是负贡献（-18.2pp）</b>：core +60.0% → core_finex +41.8%。PE 升序天然聚集低估值银行股，金融股 5 年 +60.0%，非金融股仅 +0.6%——金融是这套框架的主要收益来源，不是拖累。</li>
<li><b>PB band 层是正贡献（+5.4pp）</b>：core_finex +41.8% → core_finex_band +47.2%，10 期仅 11 次替换，被剔除股票（厦门象屿、四川路桥、电投能源等周期/公用类）后续表现偏差，规避层有效。</li>
<li><b>金融暴露不可消除</b>：剔除金融后组合被迫递补次优 PE 股，2024 年银行大行情（core +41.9% vs finex +26.8%）大幅跑输；band 层无法弥补金融剔除的损失。</li>
</ol>
</div>

<h2>1. 三变体业绩总览</h2>
<div class="card">
<table>
<tr><th>变体</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额等权全A</th><th>超额中证全指</th></tr>
{stat_row('core', 'core（基线，LX-core）', hl=True)}
{stat_row('core_finex', 'core_finex（+金融剔除）')}
{stat_row('core_finex_band', 'core_finex_band（+金融+PB band）', hl=True)}
{stat_row('ew', '等权全A（池子基准）', base=True)}
{stat_row('idx', '中证全指 000985（市值加权）', base=True)}
</table>
<div class="note">核心对比：金融剔除 -18.2pp（正收益变负超额）｜band 层 +5.4pp（负超额收窄）｜基线超额等权全A +7.1pp 是当前最强基准。</div>
</div>

<h2>2. 净值曲线</h2>
<div class="chartbox"><canvas id="navChart" height="90"></canvas></div>

<h2>3. 分年度收益</h2>
<div class="card">
<table>
<tr><th>年度</th><th>core</th><th>core_finex</th><th>core_finex_band</th><th>等权全A</th><th>中证全指</th></tr>
{''.join(annual_row(y) for y in range(2021, 2027))}
</table>
<div class="note">2021 年含 6 月起 7 个月；2026 年为 1-8 月。2024 年银行/高股息行情是 core 超额核心来源（+41.9% vs 等权 +3.0%）；2025 年等权全A大牛市（+38.9%）中 core 仅 +15.3%。</div>
</div>

<h2>4. 金融 vs 非金融：收益贡献拆解</h2>
<div class="grid2">
<div class="card">
<table>
<tr><th>组合</th><th>金融线性贡献</th><th>非金融线性贡献</th><th>金融独存</th><th>非金融独存</th><th>引擎实际</th></tr>
{decomp_rows}
</table>
<div class="note">线性贡献 = Σ(组内权重×组内月收益)；独存 = 仅保留该组收益复利。恒等式校验：逐月 r_core = (n_fin/40)·r_fin + (n_nfin/40)·r_nfin，最大单月差异 0.0000。</div>
</div>
<div class="chartbox"><canvas id="stackChart" height="240"></canvas></div>
</div>

<h2>5. PB band 规避层机制与替换明细</h2>
<div class="card">
<p style="margin:4px 0 8px; font-size:13px;"><b>机制</b>：调仓日向前 5 年计算个股 PB 分位（窗口 &lt; 60 交易日视为 band 无效不剔除），PB &gt; 90% 分位剔除，按排序递补。10 期共 <b>{n_repl} 次替换</b>（8 个调仓日触发）。</p>
<table>
<tr><th>调仓日</th><th>被 band 剔除（PB&gt;90%）</th><th>递补入选</th></tr>
{band_rows}
</table>
<div class="note">被剔除股票集中在能源/公用/交运/建筑等周期高位行业——band 层捕获的是 PB 处于 5 年高位的周期股，而非成长股。</div>
</div>

<h2>6. 持仓金融占比（core）</h2>
<div class="chartbox"><canvas id="shareChart" height="80"></canvas></div>
<div class="card">
<table>
<tr><th>调仓日</th><th>core 金融数</th><th>占比</th><th>finex 金融数</th><th>finex_band 金融数</th></tr>
{share_rows}
</table>
<div class="note">PE 升序 + 低估值约束使金融股占比从 45% 升至 80%——这是框架的系统性暴露，2026-04 期 32/40 为金融股：{fin_chips}</div>
</div>

<h2>7. 候选池与剔除诊断</h2>
<div class="card">
<table>
<tr><th>调仓日</th><th>候选池</th><th>金融股</th><th>band 高分位(&gt;90%)</th><th>finex 金融剔除</th><th>finex_band 金融剔除</th></tr>
{diag_rows}
</table>
<div class="note">band 高分位数量随市场波动（2022-04 仅 16 只 vs 2021-08 达 135 只）；finex 变体剔除金融后递补，finex_band 在递补后再次剔除 band 高分位股，故剔除数更多。</div>
</div>

<h2>8. 方法论说明</h2>
<div class="card" style="font-size:13px;">
<ul style="margin:4px 0; padding-left:20px;">
<li><b>池子</b>：万得全A（881001.WI）PIT 成分，10 期 4441→5503 只；回测/筛选一律从 SQLite 读，禁止手工精选池。</li>
<li><b>筛选管线</b>：横截面 PE 升序 → 市值≥100亿 → PE&gt;0 → L4（PE≤25 或股息率≥2%）→ L5（预期增速≤25% 且 PEG≤2）→ top40 等权，单票 5% 上限。</li>
<li><b>金融剔除层</b>：银行/非银金融/综合金融 123 只名单（申万分类，`_bt_sw_fin_universe.json`）。</li>
<li><b>PB band 层</b>：PB 5 年前置分位（2016-08 起日频估值，10 年窗口），&gt;90% 剔除，窗口样本&lt;60 日不剔除。</li>
<li><b>vnpy 撮合时序</b>：调仓月 t 下买单 → t+1 月撮合（成交价=min(委托×1.2, 次月价)）；调仓月按旧持仓估值，买入月无盈亏；成本 5bp+10bp。</li>
<li><b>归因口径</b>：归因模拟未含成本/buffer，绝对收益与引擎有差距（core 归因 +38.0% vs 引擎 +60.0%），但金融/非金融相对关系与逐月恒等式已校验。</li>
</ul>
</div>

</div>
<script>
const months = {json.dumps(months)};
const navData = {json.dumps(nav_series)};
new Chart(document.getElementById('navChart'), {{
  type: 'line',
  data: {{
    labels: months,
    datasets: [
      {{ label: 'core 基线', data: navData.core, borderColor: '#0c447c', backgroundColor: 'rgba(12,68,124,.08)', fill: true, tension: .25, borderWidth: 2.5 }},
      {{ label: 'core_finex +金融剔除', data: navData.finex, borderColor: '#d68910', borderDash: [6,3], tension: .25, borderWidth: 2 }},
      {{ label: 'core_finex_band +band', data: navData.finex_band, borderColor: '#8e44ad', tension: .25, borderWidth: 2 }},
      {{ label: '等权全A', data: navData.ew, borderColor: '#95a5a6', borderDash: [2,4], tension: .25, borderWidth: 1.5 }},
      {{ label: '中证全指', data: navData.idx, borderColor: '#27ae60', borderDash: [2,2], tension: .25, borderWidth: 1.5 }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top' }}, tooltip: {{ callbacks: {{ label: c => c.dataset.label + ': ' + c.parsed.y.toFixed(3) }} }} }},
    scales: {{ y: {{ title: {{ display: true, text: '净值 (起点=1.0)' }} }} }}
  }}
}});

const stackData = {stack};
new Chart(document.getElementById('stackChart'), {{
  type: 'bar',
  data: {{
    labels: stackData.labels,
    datasets: [
      {{ label: '金融贡献(线性Σ)', data: stackData.fin, backgroundColor: '#0c447c' }},
      {{ label: '非金融贡献(线性Σ)', data: stackData.nfin, backgroundColor: '#e0a458' }},
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'top' }}, tooltip: {{ callbacks: {{ label: c => c.dataset.label + ': ' + (c.parsed.y*100).toFixed(1) + '%' }} }} }},
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, ticks: {{ callback: v => (v*100).toFixed(0) + '%' }} }} }}
  }}
}});

new Chart(document.getElementById('shareChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(periods)},
    datasets: [{{ label: 'core 持仓中金融股数 /40', data: {json.dumps(fin_share_core)}, backgroundColor: '#0c447c' }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ min: 0, max: 40, ticks: {{ stepSize: 10 }} }} }}
  }}
}});
</script>
</body></html>"""

open(BASE + "_bt_band_report.html", "w", encoding="utf-8").write(HTML)
print("已生成 _bt_band_report.html, 大小:", len(HTML))
