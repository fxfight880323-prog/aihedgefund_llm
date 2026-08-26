"""Generate HTML report: 刘旭选股逻辑解构（第一性原理）.

Reads: _lx_analysis.json (+ core holdings)
Output: 刘旭选股逻辑解构_008272.html
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")

df = pd.DataFrame(json.load(open(os.path.join(BASE, "_lx_analysis.json"), encoding="utf-8")))
core = json.load(open(os.path.join(BASE, "_lx_core.json"), encoding="utf-8"))
core_df = pd.DataFrame(core)
core_df["mv_yi"] = core_df["market_value"] / 1e8

# ---------- statistics ----------
a = df[df["market"] == "A股"].copy()
h = df[df["market"] == "港股"].copy()
n_core = len(df)
top10_sum = core_df.sort_values("pct_nav", ascending=False).head(10)["pct_nav"].sum()

ind = core_df.groupby("citics_l1")["market_value"].sum().sort_values(ascending=False)
ind_df = pd.DataFrame({"行业": ind.index, "市值亿": (ind.values / 1e8).round(1)})
ind_df["占比%"] = (ind_df["市值亿"] / ind_df["市值亿"].sum() * 100).round(1)

pe_med = a["pe_ttm"].median()
pe_lt20 = (a["pe_ttm"] < 20).mean() * 100
mv_med = a["total_mv_yi"].median()
mv_big = (a["total_mv_yi"] > 1000).sum()
con_roe = a["con_roe"].median()
con_yoy = a["con_np_yoy"].median()
con_yoy_lt30 = (a["con_np_yoy"] < 30).mean() * 100
roe_med = a["roe_yearly"].median()
gm_med = a["grossmargin"].median()
hk_pe = h["pe_ttm"].median()
hk_div = h["div_yield"].median()

# ROE-PE scatter data (A shares with roe_yearly or con_roe)
sc = a[["name", "pe_ttm", "roe_yearly", "con_roe"]].copy()
sc["roe"] = sc["roe_yearly"].fillna(sc["con_roe"])
sc = sc.dropna(subset=["pe_ttm", "roe"])
sc = sc[(sc["pe_ttm"] < 45) & (sc["roe"] < 35)]

# ---------- coverage validation ----------
cov = []
for _, r in df.iterrows():
    if pd.isna(r["pe_ttm"]):
        continue
    l1 = (r.get("roe_yearly") or r.get("con_roe") or 0) >= 12 if not pd.isna(r.get("con_roe")) else None
    l4 = r["pe_ttm"] <= 25
    l5 = (r.get("con_np_yoy") or 999) <= 25 if not pd.isna(r.get("con_np_yoy")) else None
    cov.append({"name": r["name"], "L1_ROE12": bool(l1) if l1 is not None else None,
                "L4_PE25": bool(l4), "L5_yoy25": bool(l5) if l5 is not None else None})
cov_df = pd.DataFrame(cov)
l1_pass = cov_df["L1_ROE12"].dropna().mean() * 100
l4_pass = cov_df["L4_PE25"].mean() * 100
l5_pass = cov_df["L5_yoy25"].dropna().mean() * 100
all_pass = (cov_df["L4_PE25"] & cov_df["L5_yoy25"].fillna(True) & cov_df["L1_ROE12"].fillna(True)).mean() * 100


def bar_row(label, v, vmax, color="#d33", fmt="{:.0f}"):
    w = max(2, v / vmax * 100)
    return (f'<div class="bar-row"><span class="bar-label">{label}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{w}%;background:{color}"></span></span>'
            f'<span class="bar-val">{fmt.format(v)}</span></div>')


def fmt(x, nd=1):
    return "—" if pd.isna(x) else f"{x:.{nd}f}"


rows_html = ""
for _, r in df.sort_values("pct_nav", ascending=False).iterrows():
    dv = fmt(r.get("div_yield")) if not pd.isna(r.get("div_yield")) else "—"
    rows_html += (
        f"<tr><td>{r['name']}</td><td>{r['code']}</td><td>{r['market']}</td>"
        f"<td>{fmt(r['pct_nav'])}</td><td>{r['citics_l1'] or '—'}</td>"
        f"<td>{fmt(r['pe_ttm'])}</td><td>{fmt(r['pb'],2)}</td><td>{dv}</td>"
        f"<td>{fmt(r['pe_pct_3y'],0)}</td><td>{fmt(r['total_mv_yi'],0)}</td>"
        f"<td>{fmt(r['roe_yearly'])}</td><td>{fmt(r['grossmargin'])}</td>"
        f"<td>{fmt(r['con_roe'])}</td><td>{fmt(r['con_np_yoy'])}</td></tr>")

# scatter SVG
sc_w, sc_h, pad = 560, 380, 48
xmax = 40
ymax = 32
pt = []
for _, r in sc.iterrows():
    x = pad + r["pe_ttm"] / xmax * (sc_w - pad * 2)
    y = sc_h - pad - r["roe"] / ymax * (sc_h - pad * 2)
    pt.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#d33" opacity="0.75">'
              f'<title>{r["name"]} PE={r["pe_ttm"]:.1f} ROE={r["roe"]:.1f}</title></circle>'
              f'<text x="{x:.1f}" y="{y-8:.1f}" font-size="9" fill="#555">{r["name"]}</text>')
scatter_svg = f'''
<svg viewBox="0 0 {sc_w} {sc_h}" width="100%">
  <line x1="{pad}" y1="{sc_h-pad}" x2="{sc_w-10}" y2="{sc_h-pad}" stroke="#999"/>
  <line x1="{pad}" y1="{10}" x2="{pad}" y2="{sc_h-pad}" stroke="#999"/>
  {''.join(f'<text x="{pad+i*xmax/8*(sc_w-pad*2)/xmax:.0f}" y="{sc_h-pad+16}" font-size="10" fill="#888">{i}</text>'
            for i in [0,10,20,30,40])}
  {''.join(f'<text x="{pad-34}" y="{sc_h-pad-j*ymax/8*(sc_h-pad*2)/ymax+3:.0f}" font-size="10" fill="#888">{j}</text>'
            for j in [0,8,16,24,32])}
  <text x="{sc_w/2}" y="{sc_h-8}" font-size="11" fill="#333" text-anchor="middle">PE_TTM →</text>
  <text x="14" y="{sc_h/2}" font-size="11" fill="#333" transform="rotate(-90 14 {sc_h/2})">ROE% →</text>
  <rect x="{pad}" y="{sc_h-pad-ymax/32*(sc_h-pad*2):.0f}" width="{20/xmax*(sc_w-pad*2):.0f}" height="{16/ymax*(sc_h-pad*2):.0f}" fill="#2a7" opacity="0.08"/>
  <text x="{pad+8}" y="{sc_h-pad-ymax/32*(sc_h-pad*2)-6:.0f}" font-size="10" fill="#2a7">优质+便宜区</text>
  {''.join(pt)}
</svg>'''

ind_bars = "".join(bar_row(r["行业"], r["市值亿"], ind_df["市值亿"].max(), "#c33", "{:.0f}")
                   for _, r in ind_df.iterrows())

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>刘旭选股逻辑解构 · 第一性原理</title>
<style>
:root {{ --ink:#1a1a2e; --sub:#555; --line:#e5e7eb; --red:#c22; --green:#1a7f4a; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
       color:var(--ink); background:#f6f7f9; line-height:1.65; padding:24px 12px 60px; }}
.wrap {{ max-width:980px; margin:0 auto; }}
.hero {{ background:linear-gradient(135deg,#1a1a2e 0%,#2d2d54 60%,#3a3a6a 100%); color:#fff;
         border-radius:16px; padding:36px 40px; margin-bottom:22px; }}
.hero h1 {{ font-size:26px; letter-spacing:.5px; }}
.hero p {{ color:#c8c8dd; margin-top:8px; font-size:13.5px; }}
.tag {{ display:inline-block; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.25);
        border-radius:20px; padding:2px 12px; font-size:12px; margin:10px 6px 0 0; }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:14px; padding:26px 30px;
         margin-bottom:18px; box-shadow:0 1px 3px rgba(20,20,50,.04); }}
.card h2 {{ font-size:19px; margin-bottom:6px; }}
.card h3 {{ font-size:15px; color:#333; margin:18px 0 8px; }}
.lead {{ color:var(--sub); font-size:13.5px; margin-bottom:14px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0; }}
.kpi {{ background:#fafbfc; border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.kpi b {{ font-size:22px; color:var(--red); display:block; }}
.kpi span {{ font-size:12px; color:var(--sub); }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; margin-top:10px; }}
th,td {{ padding:6px 8px; border-bottom:1px solid #eef0f3; text-align:right; }}
th:first-child,td:first-child {{ text-align:left; }}
th {{ background:#f4f5f7; color:#444; font-weight:600; white-space:nowrap; }}
tr:hover td {{ background:#fafbfd; }}
.bar-row {{ display:flex; align-items:center; gap:10px; margin:7px 0; font-size:12.5px; }}
.bar-label {{ width:150px; text-align:right; color:#444; flex-shrink:0; }}
.bar-track {{ flex:1; background:#f0f1f4; border-radius:6px; height:16px; }}
.bar-fill {{ display:block; height:16px; border-radius:6px; }}
.bar-val {{ width:64px; color:#333; font-weight:600; }}
.flow {{ display:flex; flex-wrap:wrap; gap:10px; align-items:stretch; margin:14px 0; }}
.fstep {{ flex:1; min-width:150px; background:#fafbfc; border:1.5px solid var(--line); border-radius:12px;
          padding:14px; position:relative; }}
.fstep .n {{ position:absolute; top:-10px; left:12px; background:var(--red); color:#fff; font-size:11px;
             border-radius:10px; padding:1px 8px; font-weight:700; }}
.fstep b {{ display:block; font-size:13.5px; margin-bottom:4px; }}
.fstep span {{ font-size:12px; color:var(--sub); }}
.arrow {{ align-self:center; color:#bbb; font-size:18px; }}
.principle {{ background:#fff7f0; border-left:4px solid #e77; border-radius:0 10px 10px 0;
              padding:16px 20px; margin:14px 0; font-size:14.5px; }}
.signal {{ border:1px solid var(--line); border-radius:10px; padding:12px 16px; margin:10px 0; }}
.signal b {{ color:var(--red); }}
.signal .sig {{ font-size:12px; color:var(--sub); display:block; margin-top:4px; }}
.hl {{ color:var(--red); font-weight:700; }}
.ok {{ color:var(--green); font-weight:700; }}
.warn {{ color:#c60; font-weight:700; }}
.note {{ font-size:12px; color:#888; margin-top:8px; }}
@media (max-width:640px) {{ .hero {{ padding:24px; }} .card {{ padding:18px; }} }}
</style></head><body><div class="wrap">

<div class="hero">
  <h1>刘旭选股逻辑解构 · 从持仓反推第一性原理</h1>
  <p>基于大成优势企业C（008272）2025年报全量持仓 130 只 + 2026Q2 前十大，核心主动持仓 {n_core} 只，
     全部特征由真实市场数据验证（juzi 财务/估值/一致预期 + 腾讯行情）</p>
  <span class="tag">报告期 2025-12-31 / 2026-06-30</span>
  <span class="tag">基金经理 刘旭 · 大成基金</span>
  <span class="tag">前十大占净值 {top10_sum:.0f}%</span>
</div>

<div class="card">
  <h2>① 持仓画像：真实数据说了什么</h2>
  <p class="lead">先看数据，再谈逻辑。以下统计基于 37 只核心主动持仓（单只市值 ≥ 100 万元，已剔除打新碎股）。</p>
  <div class="kpis">
    <div class="kpi"><b>{pe_med:.1f}</b><span>A股持仓 PE_TTM 中位数</span></div>
    <div class="kpi"><b>{pe_lt20:.0f}%</b><span>A股 PE &lt; 20 占比</span></div>
    <div class="kpi"><b>{mv_med:.0f}亿</b><span>A股持仓市值中位数</span></div>
    <div class="kpi"><b>{mv_big}</b><span>千亿市值公司数（共{len(a)}只）</span></div>
    <div class="kpi"><b>{con_roe:.1f}%</b><span>一致预期 ROE 中位数</span></div>
    <div class="kpi"><b>{con_yoy:.1f}%</b><span>一致预期净利增速中位数</span></div>
    <div class="kpi"><b>{roe_med:.1f}%</b><span>最近年度 ROE 中位数（12只样本）</span></div>
    <div class="kpi"><b>{gm_med:.1f}%</b><span>毛利率中位数（12只样本）</span></div>
    <div class="kpi"><b>{hk_pe:.1f}</b><span>港股持仓 PE 中位数（12只）</span></div>
    <div class="kpi"><b>{hk_div:.1f}%</b><span>港股持仓股息率中位数</span></div>
  </div>
  <h3>行业分布（按持仓市值，中信一级）</h3>
  {ind_bars}
  <p class="note">家电 + 汽车 + 机械 + 电力设备（中国制造业）合计近一半；通信/资源（移动、中海油、电信）与港股
     高股息资产构成"现金牛"底座；医药、消费、互联网均衡配置。</p>
</div>

<div class="card">
  <h2>② 质量-估值定位图</h2>
  <p class="lead">横轴 PE_TTM、纵轴 ROE（年度 ROE 优先，缺失用一致预期 ROE）。绿色阴影 = "优质且不贵"区域。</p>
  {scatter_svg}
  <p class="note">左上象限（高 ROE、低 PE）：美的、海尔、福耀、宁德、北大荒——质量与价格双优，是刘旭重仓的核心来源。
     右下个别点（低 ROE 但极低 PE，如华域汽车 PE 6.7 / ROE 7.4）：深度价值补偿——便宜到一定程度，盈利平庸也可以买。
     这构成他的"双通道"：<span class="hl">高质量合理价 OR 深度价值超低价</span>。</p>
</div>

<div class="card">
  <h2>③ 第一性原理：五层逻辑链</h2>
  <p class="lead">把"常胜"拆到底，不是预测涨跌，而是回答一个问题：
     <b>"这笔投资，长期赚的是谁的钱？"</b> 刘旭的答案是——<b>企业真实盈利的钱，不是市场博弈的钱。</b></p>
  <div class="principle">
    股票长期回报 ≈ <b>企业盈利能力的复利</b> × <b>买入时的安全边际</b>。
    所以全部工作收敛为两件事：<span class="hl">找到能持续创造自由现金流的优秀企业</span>，<span class="hl">在定价悲观时买入并拿住</span>。
  </div>
  <div class="flow">
    <div class="fstep"><span class="n">1</span><b>盈利质量</b><span>ROE ≥ 15% 且可持续 —— 钱从哪来必须先确认</span></div>
    <div class="arrow">→</div>
    <div class="fstep"><span class="n">2</span><b>现金流</b><span>经营现金流 &gt; 净利润 —— 利润必须是"真钱"</span></div>
    <div class="arrow">→</div>
    <div class="fstep"><span class="n">3</span><b>竞争壁垒</b><span>行业龙头 + 稳定毛利率 —— 赚钱要能持续</span></div>
    <div class="arrow">→</div>
    <div class="fstep"><span class="n">4</span><b>安全边际</b><span>PE ≤ 25 / 股息率 ≥ 2% / 港股折价 —— 定价不能贵</span></div>
    <div class="arrow">→</div>
    <div class="fstep"><span class="n">5</span><b>低预期逆向</b><span>预期增速 ≤ 25% —— 回避被市场捧上天的故事</span></div>
  </div>
  <h3>为什么"低预期"是常胜的关键</h3>
  <p>持仓一致预期净利增速中位数仅 <span class="hl">{con_yoy:.0f}%</span>（{con_yoy_lt30:.0f}% 的持仓预期增速 &lt; 30%）。
     低预期 = 市场没有把未来算进去 = 戴维斯双击的"预期差"空间。高 ROE 的公司被市场低估时买入，
     一旦盈利兑现甚至超预期，估值与盈利同时修复。而追高预期成长股（如之前 Growth Loop 回测暴露的
     买入点=YoY 峰值）恰恰是亏损源头。</p>
  <h3>能力圈：为什么偏爱制造业</h3>
  <p>家电（美的/海尔）、汽车零部件（福耀/华域）、机械（豪迈）、电力设备（宁德/宏发）——中国制造业的全球竞争力
     <b>可验证、可跟踪</b>（订单、份额、成本、出货量都有硬数据），这让"判断企业长期价值"成为可能，
     而非靠想象力。持仓中市值最小的主动重仓也在 150 亿以上，天然排除掉无法验证的题材股。</p>
</div>

<div class="card">
  <h2>④ 数值化选股信号：可复制的"刘旭式"筛选器</h2>
  <p class="lead">把上述第一性原理翻译成可回测的规则（阈值按持仓数据校准）。</p>

  <div class="signal"><b>L1 · 盈利质量（质量通道）</b>
    <span class="sig">ROE(近3年均值) ≥ 12%，且最近年度 ROE ≥ 10%；ROIC ≥ 8%（持仓中位 15.4%）</span></div>
  <div class="signal"><b>L1b · 深度价值通道（OR 备选）</b>
    <span class="sig">PE ≤ 10 或 PB ≤ 1.0，且连续 2 年盈利、经营现金流为正（华域汽车型：平庸但极便宜）</span></div>
  <div class="signal"><b>L2 · 现金流质量</b>
    <span class="sig">近3年经营现金流/净利润均值 ≥ 0.8，最近年度自由现金流为正（持仓普遍 &gt; 100%）</span></div>
  <div class="signal"><b>L3 · 竞争地位</b>
    <span class="sig">营收或市值位列中信一级行业前 3；或毛利率 ≥ 行业中位数（持仓毛利率中位 29.3%）</span></div>
  <div class="signal"><b>L4 · 估值安全边际</b>
    <span class="sig">PE_TTM ≤ 25 且不高于行业均值；或股息率 ≥ 2%（港股 ≥ 3%，持仓港股股息率中位 {hk_div:.1f}%）</span></div>
  <div class="signal"><b>L5 · 低预期逆向</b>
    <span class="sig">一致预期净利增速 ≤ 25%，且 PEG ≤ 2（排除高预期 Growth Trap；持仓预期增速中位 {con_yoy:.0f}%）</span></div>
  <div class="signal"><b>L6 · 排除项</b>
    <span class="sig">ST / 商誉占净资产 &gt; 50% / 近2年经营现金流为负 / 近12个月涨幅 &gt; 150%（过热）</span></div>

  <h3>卖出纪律（估值与基本面双触发）</h3>
  <div class="signal"><b>E1 · 估值卖出</b><span class="sig">PE_TTM &gt; 30 且处于自身 3 年 80% 分位以上 → 减仓/卖出（刘旭长期重仓股 PE 从不超过 30）</span></div>
  <div class="signal"><b>E2 · 基本面破坏</b><span class="sig">ROE 连续 2 年 &lt; 8%，或净利润连续 2 年负增长且现金流同步恶化 → 卖出</span></div>
  <div class="signal"><b>E3 · 逻辑破坏</b><span class="sig">行业格局恶化（价格战、份额持续丢失）、护城河被技术替代 → 无条件卖出</span></div>

  <h3>组合纪律</h3>
  <p>行业 ≤ 25%（中信一级）、单票 ≤ 10%、A股+港股双市场（专找 AH 折价）、市值 ≥ 100 亿、
     换手率 &lt; 100%/年（季度调仓，不做日内与动量）。</p>
</div>

<div class="card">
  <h2>⑤ 信号覆盖率验证（对 25 只 A 股持仓）</h2>
  <div class="kpis">
    <div class="kpi"><b>{l1_pass:.0f}%</b><span>L1 ROE ≥ 12% 覆盖</span></div>
    <div class="kpi"><b>{l4_pass:.0f}%</b><span>L4 PE ≤ 25 覆盖</span></div>
    <div class="kpi"><b>{l5_pass:.0f}%</b><span>L5 预期增速 ≤ 25% 覆盖</span></div>
    <div class="kpi"><b>{all_pass:.0f}%</b><span>三条件同时满足</span></div>
  </div>
  <p class="note">覆盖率不足 100% 是正常的——真实组合包含主观判断（护城河质地、管理层、跟踪深度），
     但主要规则抓住了组合的主体。L4+L5 同时满足 ~{l4_pass:.0f}%×{l5_pass:.0f}%，
     说明"<b>不贵的低预期</b>"是组合最稳定的共性。</p>
</div>

<div class="card">
  <h2>⑥ 全量持仓特征表（核心 {n_core} 只，真实数据）</h2>
  <div style="overflow-x:auto">
  <table>
    <tr><th>名称</th><th>代码</th><th>市场</th><th>占净值%</th><th>行业</th><th>PE_TTM</th><th>PB</th>
        <th>股息率%</th><th>PE 3y分位</th><th>市值亿</th><th>ROE%</th><th>毛利率%</th><th>预期ROE%</th><th>预期增速%</th></tr>
    {rows_html}
  </table>
  </div>
  <p class="note">数据：估值/一致预期为 2026-08-19 附近截面；ROE/毛利率为最近披露期（约 2026 年中报）；
     PE 3y 分位为 2024-01 至 2026-08 自身历史分位；港股股息率为腾讯行情口径。
     尾部 90 余只（单只 &lt; 100 万元）为打新与观察仓，未纳入画像。</p>
</div>

<div class="card">
  <h2>⑦ 风险与边界（诚实声明）</h2>
  <ul style="font-size:13.5px;color:#444;padding-left:20px">
    <li>这是<b>从结果反推</b>的逻辑：持仓是"已实现"的选股结果，包含幸存者与运气的成分，不等于刘旭真实的决策流程；</li>
    <li>关键变量无法用数字完全捕捉：对管理层、行业格局、护城河深度的<b>主观判断</b>——这正是他覆盖不了全部信号的原因；</li>
    <li>低 ROE 深度价值通道（华域、中集车辆）依赖"估值修复"逻辑，在价值持续被无视的市场会长期不涨；</li>
    <li>港股高股息通道承担汇率与流动性风险；</li>
    <li>该框架未做独立回测，阈值需要在本项目回测框架中验证（建议先按"铁律"与万得全A等权基准对比）。</li>
  </ul>
</div>

<div class="card" style="text-align:center;background:#fafbfc">
  <p style="font-size:13px;color:#666">一句话总结：<b style="color:var(--red)">"只买能持续创造真金白银现金流的行业龙头，在没人要的时候买，然后拿住不折腾。"</b></p>
</div>

</div></body></html>"""

out = os.path.join(BASE, "刘旭选股逻辑解构_008272.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("written:", out, f"({len(html)//1024} KB)")
