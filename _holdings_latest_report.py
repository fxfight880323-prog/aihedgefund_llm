# -*- coding: utf-8 -*-
"""最新持仓报告：修正口径 + 最新数据（2026-08）。对比旧推荐的错误。"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

d = json.load(open("_holdings_latest.json", encoding="utf-8"))
holdings = d["holdings"]

# 旧推荐（2026-04，错误口径）用于对比
old = [
    ("600033.SH", "公用事业", 10.4), ("002818.SZ", "半导体", 11.4),
    ("000828.SZ", "公用事业", 12.1), ("600062.SH", "医药", 11.4),
    ("002393.SZ", "医药", 12.5), ("600211.SH", "中药", 13.5),
]

# 补充名字 + 行业
EXTRA_NAME = {"000612.SZ": "焦作万方"}
IND = {
    "601601.SH": "保险", "601838.SH": "银行", "601169.SH": "银行",
    "600919.SH": "银行", "600926.SH": "银行", "601009.SH": "银行",
    "601077.SH": "银行", "601318.SH": "保险", "601319.SH": "保险",
    "601117.SH": "建筑", "601665.SH": "银行", "002948.SZ": "银行",
    "601128.SH": "银行", "000612.SZ": "有色", "002839.SZ": "银行",
}

rows = ""
for h in holdings:
    tk = h["ticker"]
    nm = h["name"] or EXTRA_NAME.get(tk, "")
    ind = IND.get(tk, "—")
    rows += f"""<tr>
      <td class="mono">{tk}</td><td>{nm}</td><td>{ind}</td>
      <td class="mono">{h['pe_ttm']:.1f}</td>
      <td class="mono">{h['total_mv_yi']:.0f}</td>
      <td class="mono">{h['pe_pct']:.1f}</td>
      <td class="mono">{h['blend']:.1f}</td>
      <td class="mono">{h['mom60']:+.1f}%</td>
      <td class="mono">{h['mom60_pct']:.0f}%</td>
      <td class="mono">{h['weight_pct']:.2f}%</td></tr>"""

bank = sum(1 for h in holdings if IND.get(h["ticker"]) == "银行")
ins = sum(1 for h in holdings if IND.get(h["ticker"]) == "保险")

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>最新持仓 · 修正口径 + 2026-08</title>
<style>
:root {{ --bg:#f8fafc; --card:#fff; --ink:#0f172a; --sub:#64748b; --line:#e2e8f0;
  --red:#dc2626; --amber:#d97706; --green:#16a34a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }}
.wrap {{ max-width:920px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:21px; margin:0 0 4px; }}
.sub {{ color:var(--sub); font-size:13px; margin-bottom:18px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:20px 22px; margin-bottom:18px; }}
.card h2 {{ font-size:15px; margin:0 0 12px; }}
.alert {{ background:#fef2f2; border:1px solid #fecaca; border-radius:12px;
  padding:18px 20px; margin-bottom:18px; }}
.alert h2 {{ color:var(--red); font-size:15px; margin:0 0 10px; }}
.alert li {{ font-size:13px; line-height:1.8; color:#7f1d1d; }}
.ok {{ background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px;
  padding:16px 20px; margin-bottom:18px; }}
.ok h2 {{ color:var(--green); font-size:15px; margin:0 0 8px; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th,td {{ padding:7px 8px; text-align:center; border-bottom:1px solid var(--line); }}
th {{ background:#f1f5f9; color:#334155; font-weight:600; }}
.mono {{ font-family:ui-monospace,Consolas,monospace; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.kpi .k {{ font-size:11px; color:var(--sub); }}
.kpi .v {{ font-size:20px; font-weight:700; margin-top:4px; }}
.tag {{ display:inline-block; background:#eff6ff; color:#1d4ed8; border-radius:6px;
  padding:1px 8px; font-size:11px; margin-right:6px; }}
p {{ font-size:13px; line-height:1.8; }}
</style></head><body><div class="wrap">

<h1>最新持仓建议 · AD_top15_mom60top50（修正版）</h1>
<div class="sub">asof = 2026-08-31（最新已收盘月度 PIT）· 严格复用回测框架 screen_q20 口径</div>

<div class="alert"><h2>⚠️ 之前那份持仓推荐有误，已修正</h2>
<ul>
  <li><b>口径不一致</b>：旧脚本把 q20 的质量分写成了 <code>(npyoy + roes + gpm)/3</code> 原始值相加，
      而回测框架是 <code>(gpm_pct + con_roe_pct + cetop_pct)/3</code> 的截面分位；且漏掉了
      市值≥100亿、PE≤25或股息≥2%、PEG≤1、预期增速≤60% 这 5 道门槛。
      结果把「银行股」错误地排除了，选出了医药/公用事业。</li>
  <li><b>数据不是最新</b>：旧脚本读的是只到 2026-04 的 JSON 快照，而数据库已有 2026-08
      （5529 只成分 + 估值/因子/预期面板全部齐）。</li>
</ul>
</div>

<div class="ok"><h2>✅ 修正后：15 只几乎全是低 PE 银行/保险</h2>
<p>这才是「纯估值策略」真实会选出的持仓——PE 5~7 的银行股是 PE 便宜度分位最高的票，
与之前收益归因结论（估值修复贡献 85%）完全自洽。</p></div>

<div class="kpis">
  <div class="kpi"><div class="k">PIT 成分（2026-08）</div><div class="v">5529</div></div>
  <div class="kpi"><div class="k">screen_q20 后 base pool</div><div class="v">222</div></div>
  <div class="kpi"><div class="k">动量 gate 后</div><div class="v">83</div></div>
  <div class="kpi"><div class="k">最终持仓</div><div class="v">15</div></div>
</div>

<div class="card"><h2>推荐持仓（cap8 加权 · 按权重降序）</h2>
<table><thead><tr>
  <th>代码</th><th>名称</th><th>行业</th><th>PE</th><th>市值(亿)</th>
  <th>PE便宜度%</th><th>q20分</th><th>动量60日</th><th>动量分位</th><th>权重</th>
</tr></thead><tbody>{rows}</tbody></table>
<p style="color:var(--sub);margin-top:10px">行业构成：银行 {bank} 只 · 保险 {ins} 只 · 其他 {15-bank-ins} 只。
cap8 上限 8%，大盘股（中国平安/太保/人保/江苏银行）触发上限，小盘银行股自然降到 2%~7%。</p></div>

<div class="card"><h2>验证：口径才是根因（不是时点）</h2>
<p>用<b>严格口径</b>回看 2026-04 那期，选出的同样是 15 只银行股（长沙银行/成都银行/江苏银行/杭州银行…）。
所以旧推荐选成医药/公用事业，是<b>口径写错</b>导致的，不是数据时点问题。修正口径后，
无论 2026-04 还是 2026-08，选出的都是低 PE 银行股。</p>
<table><thead><tr><th>旧推荐（错误口径 2026-04）</th><th>严格口径 2026-04</th><th>严格口径 2026-08（本次）</th></tr></thead>
<tbody><tr>
  <td style="text-align:left">公用事业 600033<br>半导体 002818<br>公用事业 000828<br>医药 600062…</td>
  <td style="text-align:left">长沙银行<br>成都银行<br>江苏银行<br>杭州银行…</td>
  <td style="text-align:left">中国太保<br>成都银行<br>张家港行<br>北京银行…</td>
</tr></tbody></table></div>

<div class="card"><h2>操作提示</h2>
<p>
<span class="tag">1</span>下次调仓日 <b>2026-10-31</b>，届时重新跑 <code>_holdings_latest.py</code> 生成新截面持仓。<br>
<span class="tag">2</span>这 15 只银行/保险股是「纯估值」的必然结果——若要真 GARP，仍需从成长因子定义上改，而不是调权重（见权重扫描报告）。<br>
<span class="tag">3</span>银行股集中度高（13/15 金融），历史结论「金融剔除 = 负贡献」说明这恰是策略 alpha 来源，但单行业集中是实盘需注意的风险。
</p></div>

</div></body></html>"""

open("_holdings_latest_report.html", "w", encoding="utf-8").write(html)
print("报告 → _holdings_latest_report.html")
print(f"银行 {bank} / 保险 {ins} / 其他 {15-bank-ins}")
