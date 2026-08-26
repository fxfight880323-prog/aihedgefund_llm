# -*- coding: utf-8 -*-
"""多重框架全景梳理报告生成器。

读取各框架最新推荐 JSON → 生成 _framework_overview_report.html
框架: LX-core / LX评分 / C-Score / C-Score剔除金融 / 筹码×52周高点 / dist52锚定
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_HTML = os.path.join(ROOT, "_framework_overview_report.html")


def load(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return None
    return json.loads(open(p, encoding="utf-8").read())


def fmt(x, nd=1, suffix=""):
    if x is None or x != x:
        return "—"
    try:
        return f"{float(x):.{nd}f}{suffix}"
    except Exception:
        return str(x)


def fmt_pct(x, nd=1):
    if x is None or x != x:
        return "—"
    return f"{float(x):.{nd}f}%"


# ---------------- 数据载入 ----------------
lx = load("_lx_now_results.json")
lx_scored = load("_lx_now_scored.json")
cs = load("_cs_now_results.json")
cs_exfin = load("_cs_now_exfin_results.json")
chip = load("_ai_chip_52wk_top.json") or []
dist52 = load("_lx_now_dist52.json")

# LX core top 20
lx_core_rows = []
if lx:
    for s in lx.get("core", [])[:20]:
        lx_core_rows.append(f"""<tr>
<td>{s['rank']}</td><td class="b">{s['name']}</td><td>{s['code']}</td>
<td>{fmt(s['pe'])}</td><td>{fmt(s['peg'],1)}</td><td>{fmt(s['con_roe'],1)}</td>
<td>{fmt(s['gpm'],1)}</td><td>{fmt(s['dy'],2)}</td><td>{fmt(s['mv_yi'],0)}</td></tr>""")

# LX gm top 12
lx_gm_rows = []
if lx:
    for s in lx.get("gm", [])[:12]:
        lx_gm_rows.append(f"""<tr>
<td>{s['rank']}</td><td class="b">{s['name']}</td><td>{s['code']}</td>
<td>{fmt(s['pe'])}</td><td>{fmt(s['peg'],1)}</td><td>{fmt(s['con_roe'],1)}</td>
<td>{fmt(s['gpm'],1)}</td><td>{fmt(s['dy'],2)}</td><td>{fmt(s['mv_yi'],0)}</td></tr>""")

# LX scored top 20
lx_score_rows = []
top40 = (lx_scored or {}).get("top40", [])
if isinstance(top40, list):
    for s in top40[:20]:
        lx_score_rows.append(f"""<tr>
<td>{s.get('score_rank')}</td><td class="b">{s['name']}</td><td>{s['code']}</td>
<td>{fmt(s.get('pe'))}</td><td>{fmt(s.get('peg'),1)}</td><td>{fmt(s.get('con_roe'),1)}</td>
<td>{fmt(s.get('score_value'),1)}</td><td>{fmt(s.get('score_quality'),1)}</td>
<td>{fmt(s.get('score_safety'),1)}</td><td>{fmt(s.get('score_total'),1)}</td></tr>""")

# C-Score recommend 17
cs_rows = []
if cs:
    for s in cs.get("recommend", [])[:17]:
        cs_rows.append(f"""<tr>
<td>{s.get('rank')}</td><td class="b">{s.get('name')}</td><td>{s.get('code')}</td>
<td>{fmt(s.get('pe'))}</td><td>{fmt(s.get('pb'),2)}</td><td>{fmt(s.get('con_roe'),1)}</td>
<td>{fmt(s.get('con_np_yoy'),1)}</td><td class="cscore">{s.get('c_score')}</td>
<td>{'银行/非银' if s.get('bm_tercile') else ''}{s.get('industry','')}</td></tr>""")

# C-Score 剔除金融
cs_exfin_rows = []
if cs_exfin:
    for s in cs_exfin.get("recommend", [])[:15]:
        cs_exfin_rows.append(f"""<tr>
<td>{s.get('rank')}</td><td class="b">{s.get('name')}</td><td>{s.get('code')}</td>
<td>{fmt(s.get('pe'))}</td><td>{fmt(s.get('pb'),2)}</td><td>{fmt(s.get('con_roe'),1)}</td>
<td>{fmt(s.get('con_np_yoy'),1)}</td><td class="cscore">{s.get('c_score')}</td></tr>""")

# 筹码×52周高点 top 20
chip_rows = []
for s in chip[:20]:
    chip_rows.append(f"""<tr>
<td>{chip.index(s)+1}</td><td class="b">{s.get('name')}</td><td>{s.get('sym')}</td>
<td>{fmt(s.get('mv'),0)}</td><td>{fmt(s.get('dist52'),2)}</td><td>{fmt(s.get('conc'),2)}</td>
<td>{fmt(s.get('chip'),2)}</td><td>{s.get('industry','')}</td><td>{fmt(s.get('score'),3)}</td></tr>""")

# dist52 双信号交集
dual_rows = []
if dist52:
    for r in dist52.get("rows", []):
        if r.get("score_rank") is not None and r.get("score_rank") <= 20 and r.get("dist52", 0) >= 0.85:
            dual_rows.append(f"""<tr>
<td class="b">{r['name']}</td><td>{r['code']}</td><td>{fmt(r.get('dist52'),2)}</td>
<td>{r.get('score_rank')}</td><td>{fmt(r.get('score_total'),1)}</td><td>{fmt(r.get('pe'))}</td></tr>""")

# ---------------- 统计 ----------------
n_lx_core = len(lx["core"]) if lx else 0
n_lx_gm = len(lx["gm"]) if lx else 0
n_cs = len(cs.get("recommend", [])) if cs else 0
n_cs_exfin = len(cs_exfin.get("recommend", [])) if cs_exfin else 0
n_chip = len(chip)

# 各框架 Top 股票名（去重看交叉）
def names(field):
    out = []
    for s in (lx or {}).get(field, []):
        out.append(s["name"])
    return out

lx_names = set(names("core")[:40])
cs_names = set(s.get("name") for s in (cs or {}).get("recommend", []))
chip_names = set(s.get("name") for s in chip)
overlap_lx_cs = lx_names & cs_names
overlap_lx_chip = lx_names & chip_names
overlap_cs_chip = cs_names & chip_names

# 交叉重叠（预计算成 HTML 字符串）
def pill_text(s):
    return f'<span class="pill">{s}</span>'

overlap_lx_cs_html = "".join(pill_text(s) for s in sorted(overlap_lx_cs)) if overlap_lx_cs else '<span class="pill">无直接重叠（排序逻辑不同，池子差异大）</span>'
overlap_lx_chip_html = "".join(pill_text(s) for s in sorted(overlap_lx_chip)) if overlap_lx_chip else '<span class="pill">无重叠——刘旭池(低估值价值)与AI科技池天然互斥，正是"不同角度"的体现</span>'

# ---------------- HTML ----------------
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Fund Framework · 多重框架全景梳理</title>
<style>
  :root {{
    --red: #d6333b; --red-bg: #fff0f0; --blue: #1a5fb4; --blue-bg: #eef4fb;
    --green: #2e7d32; --green-bg: #eef7ee; --amber: #b45309; --amber-bg: #fdf3e3;
    --gray: #6b7280; --line: #e5e7eb; --bg: #ffffff; --card: #fafbfc; --text: #1f2328;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         color: var(--text); background: var(--bg); line-height: 1.6; padding: 24px 16px 60px; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin-bottom: 4px; }}
  h2 {{ font-size: 20px; margin: 36px 0 14px; padding-left: 10px; border-left: 4px solid var(--red); }}
  h3 {{ font-size: 15.5px; margin: 22px 0 10px; color: var(--blue); }}
  .sub {{ color: var(--gray); font-size: 13.5px; margin-bottom: 18px; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px;
            font-weight: 600; margin-right: 6px; }}
  .b-red {{ background: var(--red-bg); color: var(--red); }}
  .b-blue {{ background: var(--blue-bg); color: var(--blue); }}
  .b-green {{ background: var(--green-bg); color: var(--green); }}
  .b-amber {{ background: var(--amber-bg); color: var(--amber); }}
  .b-gray {{ background: #f1f3f5; color: var(--gray); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }}
  .card h4 {{ font-size: 14.5px; margin-bottom: 6px; }}
  .card .tag {{ font-size: 12px; color: var(--gray); margin-bottom: 8px; }}
  .card p {{ font-size: 13px; color: #374151; }}
  .evid {{ font-size: 12.5px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line); color: #4b5563; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
  th, td {{ padding: 6px 8px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
  th {{ background: #f3f4f6; font-weight: 600; position: sticky; top: 0; }}
  td.b {{ font-weight: 600; }}
  td.cscore {{ text-align: center; color: var(--red); font-weight: 700; }}
  tr:hover td {{ background: #f8fafc; }}
  .tbl-scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }}
  .note {{ font-size: 12.5px; color: var(--gray); margin-top: 6px; }}
  .kv {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap: 10px; margin: 10px 0 4px; }}
  .kv .item {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; }}
  .kv .num {{ font-size: 18px; font-weight: 700; color: var(--red); }}
  .kv .lbl {{ font-size: 12px; color: var(--gray); }}
  .flow {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }}
  .flow .step {{ background: var(--blue-bg); border: 1px solid #c9d8ec; color: var(--blue);
                 padding: 6px 12px; border-radius: 6px; font-size: 12.5px; font-weight: 600; }}
  .flow .arrow {{ color: var(--gray); }}
  ul.tight {{ margin: 6px 0 6px 18px; font-size: 13.5px; }}
  ul.tight li {{ margin: 4px 0; }}
  .pri {{ display: inline-block; width: 16px; height: 16px; border-radius: 4px; color: #fff;
          text-align: center; line-height: 16px; font-size: 11px; font-weight: 700; margin-right: 6px; }}
  .p1 {{ background: var(--red); }} .p2 {{ background: var(--amber); }} .p3 {{ background: var(--blue); }}
  .sec {{ margin: 8px 0; padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); }}
  .sec .h {{ font-weight: 700; font-size: 14px; margin-bottom: 4px; }}
  .sec .why {{ font-size: 12.5px; color: var(--gray); margin-bottom: 8px; }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  @media (max-width: 860px) {{ .two {{ grid-template-columns: 1fr; }} }}
  .pill {{ display:inline-block; background:#f1f3f5; border-radius:4px; padding:1px 7px; font-size:12px; color:#374151; margin:2px 3px 2px 0; }}
  .warn {{ background: var(--amber-bg); border-left: 3px solid var(--amber); padding: 10px 14px;
          border-radius: 0 6px 6px 0; font-size: 13px; margin: 10px 0; }}
  .ok {{ background: var(--green-bg); border-left: 3px solid var(--green); padding: 10px 14px;
        border-radius: 0 6px 6px 0; font-size: 13px; margin: 10px 0; }}
  footer {{ margin-top: 40px; color: var(--gray); font-size: 12px; border-top: 1px solid var(--line); padding-top: 12px; }}
</style>
</head>
<body><div class="wrap">

<h1>🎯 AI Fund Framework · 多重框架全景梳理</h1>
<div class="sub">六种推荐角度 → 同一市场给出不同股票池 | 数据截至 <b>2026-08-20/21</b>（万得全A PIT 5529 只成分） | 生成于 2026-08-25</div>

<!-- ============ 0. 总览 ============ -->
<h2>0. 一句话总览</h2>
<p style="font-size:14.5px; margin-bottom:8px;">
本框架的核心认知：<b style="color:var(--red)">投资收益 = 基准(池子) + 数据端(因子) + 方法论 + 卖出时点</b>。
当前有 <b>6 个活跃推荐角度</b>，各自锚定不同的信息源与回测证据，相互独立、可交叉验证：
</p>
<div class="grid">
  <div class="card"><h4>① 刘旭式 · 便宜优先</h4><span class="badge b-red">L2 方法论</span><span class="badge b-green">最强基准</span>
    <p>市值≥100亿 → PE升序（排序信念=价值完胜，72pp差距）→ 40只核心 + 毛利中位保护层</p>
    <div class="evid">回测 +60.0% / 超额+7.1pp / MDD-24.9% <b>（当前最强方法论）</b></div></div>
  <div class="card"><h4>② 刘旭式 · 六因子评分</h4><span class="badge b-red">L2 方法论</span>
    <p>在226只通过筛选的股票里，按 价值50% + 质量25% + 安全25% 百分位打分</p>
    <div class="evid">排序信念仍是 PE 升序；评分用于"同池内择优"而非换排序</div></div>
  <div class="card"><h4>③ C-Score 一致预期</h4><span class="badge b-blue">L1 数据层</span><span class="badge b-green">核心资产</span>
    <p>分析师一致预期<b>方向性上修</b>（否决>打分，+4.7pp）→ 低估值池 440 只 → 17 只推荐</p>
    <div class="evid">回测 +30.7% / 超额 +26.2pp（10期跑赢8期）</div></div>
  <div class="card"><h4>④ 筹码 × 52周高点</h4><span class="badge b-blue">L1 数据层</span><span class="badge b-amber">AI 科技池</span>
    <p>AI产业链池内：机构筹码集中（锁仓度）+ 价格贴近52周高点（反应不足）双信号打分</p>
    <div class="evid">筹码 Q1 +6.8%/年单调；dist52 近高点裸测 +12.3pp</div></div>
  <div class="card"><h4>⑤ dist52 锚定检查</h4><span class="badge b-amber">L3 行为金融</span><span class="badge b-gray">规避层</span>
    <p>距52周高点近=反应不足（买）；过远=接飞刀（-36.9pp，禁买）。叠加在刘旭名单上过滤</p>
    <div class="evid">近高点 +12.3pp / 深跌 -36.9pp（8期最差）→ 只做规避与辅助</div></div>
  <div class="card"><h4>⑥ 一致预期 beat</h4><span class="badge b-blue">L1 数据层</span><span class="badge b-gray">待运行</span>
    <p>近4周一致预期净利润上修 + 增速降序 top20（剔除银行/非银）</p>
    <div class="evid">脚本已就绪（_consensus_beat_screen.py），结果未生成 → 待跑</div></div>
</div>

<!-- ============ 1. LX ============ -->
<h2>1. 刘旭式框架（便宜优先）→ 深度价值角度</h2>
<div class="flow">
  <span class="step">万得全A PIT 5529</span><span class="arrow">→</span>
  <span class="step">剔除 PE≤0 / 毛利缺失 36</span><span class="arrow">→</span>
  <span class="step">市值 ≥ 100亿（3723只被剔）</span><span class="arrow">→</span>
  <span class="step">L4 质量(890) → L5(420)</span><span class="arrow">→</span>
  <span class="step">PE 升序 top40</span>
</div>
<div class="kv">
  <div class="item"><div class="num">{n_lx_core}</div><div class="lbl">core 核心名单</div></div>
  <div class="item"><div class="num">{n_lx_gm}</div><div class="lbl">gm 毛利保护层（113只过筛）</div></div>
  <div class="item"><div class="num">+60.0%</div><div class="lbl">5年回测（vs EW全A +52.9%）</div></div>
  <div class="item"><div class="num">-24.9%</div><div class="lbl">MDD（gm层砍半至-13.9%）</div></div>
</div>
<div class="two">
  <div><h3>core 核心 40 只（PE 升序 · 前20）</h3>
  <div class="tbl-scroll"><table>
    <tr><th>#</th><th>名称</th><th>代码</th><th>PE</th><th>PEG</th><th>ROE</th><th>毛利%</th><th>股息%</th><th>市值亿</th></tr>
    {''.join(lx_core_rows)}
  </table></div>
  <div class="note">特征：全部 PE≤10.4、清一色低估值周期/公用/基建/传媒——这就是"便宜优先"的形状。</div></div>
  <div><h3>gm 毛利保护层（毛利≥市场中位27.6% · 前12）</h3>
  <div class="tbl-scroll"><table>
    <tr><th>#</th><th>名称</th><th>代码</th><th>PE</th><th>PEG</th><th>ROE</th><th>毛利%</th><th>股息%</th><th>市值亿</th></tr>
    {''.join(lx_gm_rows)}
  </table></div>
  <div class="note">特征：高毛利质量股（新和成43.7%、瀚蓝34.5%、老板电器50.4%）——回测证明此层回撤砍半、收益持平。</div></div>
</div>

<!-- ============ 2. LX 评分 ============ -->
<h2>2. 刘旭式 · 六因子评分 → 价值质量安全平衡角度</h2>
<p style="font-size:13.5px; color:#374151; margin-bottom:6px;">
在通过 L4/L5 的 <b>226 只</b>股票内做百分位打分（不是新排序逻辑，而是同池择优）：
价值50% = PE 30% + PEG 20%；质量25% = ROE 15% + 毛利 10%；安全25% = 股息 15% + 经营现金流/市值 10%。</p>
<div class="tbl-scroll"><table>
  <tr><th>评分</th><th>名称</th><th>代码</th><th>PE</th><th>PEG</th><th>ROE</th><th>价值分</th><th>质量分</th><th>安全分</th><th>总分</th></tr>
  {''.join(lx_score_rows)}
</table></div>
<div class="note">Top 特征：南京高科/新奥股份/周大生/宇通客车——价值分都 >80，同时质量或安全分也不拖后腿。</div>

<!-- ============ 3. C-Score ============ -->
<h2>3. C-Score 一致预期 → 预期差角度</h2>
<div class="flow">
  <span class="step">万得全A 5529</span><span class="arrow">→</span>
  <span class="step">剔 PE≤0(424)/高PB(3638)/高PE(856)/小市值(129)</span><span class="arrow">→</span>
  <span class="step">低估值池 440</span><span class="arrow">→</span>
  <span class="step">C-Score 否决制（预期方向性上修）</span><span class="arrow">→</span>
  <span class="step">{n_cs} 只推荐</span>
</div>
<div class="kv">
  <div class="item"><div class="num">{n_cs}</div><div class="lbl">推荐（含金融）</div></div>
  <div class="item"><div class="num">{n_cs_exfin}</div><div class="lbl">剔除银行/非银版</div></div>
  <div class="item"><div class="num">+30.7%</div><div class="lbl">回测（超额 +26.2pp）</div></div>
  <div class="item"><div class="num">+4.7pp</div><div class="lbl">否决制 vs 打分制</div></div>
</div>
<div class="two">
  <div><h3>推荐 {n_cs} 只（一致预期上修 + 低估值）</h3>
  <div class="tbl-scroll"><table>
    <tr><th>#</th><th>名称</th><th>代码</th><th>PE</th><th>PB</th><th>ROE</th><th>预期YoY%</th><th>C分</th></tr>
    {''.join(cs_rows)}
  </table></div>
  <div class="note">⚠️ 注意：C-Score 天然偏向低估值+预期上修，银行/建筑占大头（低PB + 稳定预期）。</div></div>
  <div><h3>剔除金融版（前15）</h3>
  <div class="tbl-scroll"><table>
    <tr><th>#</th><th>名称</th><th>代码</th><th>PE</th><th>PB</th><th>ROE</th><th>预期YoY%</th><th>C分</th></tr>
    {''.join(cs_exfin_rows)}
  </table></div>
  <div class="note">剔除后更均衡：建筑/交运/制造/消费；中国建筑、隧道股份仍在列（高 C 分 + 低估值）。</div></div>
</div>

<!-- ============ 4. 筹码×52周 ============ -->
<h2>4. 筹码结构 × 52周高点 → AI 科技池 · 筹码+行为角度</h2>
<div class="flow">
  <span class="step">AI 产业链 1406 只（12概念板块）</span><span class="arrow">→</span>
  <span class="step">剔 ST/北交所/信号缺失 → 1359</span><span class="arrow">→</span>
  <span class="step">科技行业白名单 664</span><span class="arrow">→</span>
  <span class="step">筹码分(集中度+合成) 50% + dist52 50%</span><span class="arrow">→</span>
  <span class="step">Top {n_chip}</span>
</div>
<div class="kv">
  <div class="item"><div class="num">{n_chip}</div><div class="lbl">Top 30</div></div>
  <div class="item"><div class="num">{sum(1 for s in chip if s.get('mv',0)>=100)}</div><div class="lbl">市值≥100亿</div></div>
  <div class="item"><div class="num">{sum(1 for s in chip if s.get('mv',0)<100)}</div><div class="lbl">小盘弹性</div></div>
  <div class="item"><div class="num">+6.8%/年</div><div class="lbl">筹码集中端 Q1（90月单调）</div></div>
</div>
<div class="tbl-scroll"><table>
  <tr><th>#</th><th>名称</th><th>代码</th><th>市值亿</th><th>dist52</th><th>集中度z</th><th>筹码合成</th><th>行业</th><th>综合分</th></tr>
  {''.join(chip_rows)}
</table></div>
<div class="note">
逻辑：<b>机构筹码集中 = 聪明钱锁仓、抛压小</b>（个股层正信号，IC -0.054 八年全负方向极稳）；
<b>贴近52周高点 = 锚定反应不足</b>（Li&Yu 2012，+12.3pp）。两者合成在 AI 科技池内选出"机构锁仓 + 趋势健康"标的。<br>
⚠️ 行业层筹码集中方向反转（拥挤过热）→ 本信号<b>只用于行业内选股，禁止行业配置</b>；小盘弹性标的（罗普特/安凯微/苏州科达等）需注意流动性风险。
</div>

<!-- ============ 5. dist52 ============ -->
<h2>5. dist52 锚定检查 → 行为金融 · 规避层</h2>
<p style="font-size:13.5px; margin-bottom:6px;">
对刘旭 78 只并集（core40 + gm40 + 评分top40）做 52 周高点距离检查（腾讯前复权日K 250根，as_of 2026-08-21 收盘）：</p>
<div class="warn"><b>核心教训</b>：便宜（低PE）与贴近高点天然冲突——评分前10 中 中材国际(0.69)/菜百股份(0.61)/中创智领(0.56) 都是深跌区，是"深度价值"的形状而非缺陷；dist52 只作<b>规避层与辅助确认</b>，不替换 PE 排序。</div>
<h3>双信号交集（评分前20 ∩ dist52 ≥ 0.85）—— 便宜 × 趋势健康 的少数派</h3>
<div class="tbl-scroll"><table>
  <tr><th>名称</th><th>代码</th><th>dist52</th><th>评分名次</th><th>总分</th><th>PE</th></tr>
  {''.join(dual_rows)}
</table></div>
<div class="note">近高点(≥0.95) 4只 / 较近(0.85-0.95) 9只 / 中等 38 / 过远(&lt;0.70) 27——多数深度价值股都在深跌区，这是风格特征。</div>

<!-- ============ 6. 交叉 ============ -->
<h2>6. 跨框架交叉：重叠与冲突</h2>
<div class="two">
  <div class="sec"><div class="h">🔗 多框架重叠（交叉验证）</div>
    <div class="why">同一只股票被两个独立角度同时选中 = 证据增强</div>
    <div><b>LX-core ∩ C-Score：</b>
      {overlap_lx_cs_html}
    </div>
    <div style="margin-top:8px"><b>LX-core ∩ 筹码×52周：</b>
      {overlap_lx_chip_html}
    </div>
  </div>
  <div class="sec"><div class="h">⚖️ 角度互补关系</div>
    <div class="why">三个角度覆盖三个互斥的收益来源</div>
    <ul class="tight">
      <li><b>刘旭式</b> = 买得便宜（价值回归）→ 偏周期/公用/基建/消费</li>
      <li><b>C-Score</b> = 买预期改善（分析师方向性上修）→ 偏金融/建筑/交运</li>
      <li><b>筹码×52周</b> = 买筹码锁定+趋势健康（供给端）→ 偏 AI 科技成长</li>
      <li><b>dist52</b> = 不接飞刀（行为规避）→ 叠加在任何名单上</li>
    </ul>
    <div class="why" style="margin-top:6px">三者组合 ≈ 价值底仓 + 预期催化 + 科技成长 + 行为风控 的哑铃结构。</div>
  </div>
</div>

<!-- ============ 7. 可拓展 ============ -->
<h2>7. 你可以继续更新与拓展的方向</h2>

<h3>A. 维护更新（让现有框架滚动起来）</h3>
<div class="tbl-scroll"><table>
  <tr><th style="width:40px">优先级</th><th style="width:150px">事项</th><th>说明</th><th style="width:110px">节奏</th></tr>
  <tr><td><span class="pri p1">P1</span></td><td>跑通 <b>一致预期beat 筛选</b></td><td>_consensus_beat_screen.py 已就绪但结果未生成（np_revision_4w>0 + con_np_yoy 降序 top20 剔金融）——补跑并出报告，框架的第 6 个角度立即生效</td><td>即时</td></tr>
  <tr><td><span class="pri p1">P1</span></td><td><b>alpha_ledger 补记账</b></td><td>账本停在 2026-08-20；8/24-8/25 的 GBM 证伪、筹码×行业层证伪、dist52 结论、申万因子扫描都未入账——补记后报告才反映真实框架状态</td><td>即时</td></tr>
  <tr><td><span class="pri p1">P1</span></td><td>推荐名单 <b>持仓追踪</b></td><td>用 holdings-tracker 记录每次推荐 → 实际检验框架"事后表现"，形成推荐-验证闭环（目前只验证了回测，没验证实盘推荐）</td><td>每期调仓</td></tr>
  <tr><td><span class="pri p2">P2</span></td><td>SQLite 追加新因子</td><td>筹码合成/机构集中度/dist52/申万T1因子（成长/行业轮动）入库 → 后续筛选/回测全部从 a_share_market.db 读，不再翻 JSON</td><td>随用随加</td></tr>
  <tr><td><span class="pri p2">P2</span></td><td>刷新流程固化</td><td>把 _lx_now_fetch→screen→score + _cs_now_recommend + dist52 串成一条命令/一个自动化任务，每月/每季一键刷新（当前是半年度调仓节奏）</td><td>月/季</td></tr>
  <tr><td><span class="pri p3">P3</span></td><td>fund 008272 持仓对照</td><td>刘旭实盘持仓（2026Q2 已拉取）vs 框架推荐 → 检视框架与真人的方法论偏差，校准 L4/L5 门槛</td><td>季报后</td></tr>
</table></div>

<h3>B. 研究拓展（按三层归因，全部先跑 benchmark 再下结论）</h3>
<div class="two">
  <div>
  <div class="sec"><div class="h">L1 数据层 · 新信息源</div>
    <ul class="tight">
      <li><b>三个已连接 MCP 未鉴别</b>：westock(腾讯自选股)、mx-ds-mcp(东财妙想)、wind-finance 都处于 connected——按 A/B 鉴别协议跑同一方法论对比基线，通过才入账</li>
      <li><b>一致预期拥挤度监控</b>：若预期上修因子拥挤化 → 标记 DEGRADING 降权（框架已留槽位）</li>
      <li><b>资金流数据</b>：北向/龙虎榜/融资融券（westock/MX 可拉）→ 事件驱动信号</li>
      <li><b>主题池方法论</b>：AI 科技链池已有雏形（1406 只），补"池子景气度监控"（成分股一致预期上修占比）</li>
      <li><b>财报 PIT 对齐</b>：确保每期快照用当时已披露数据（防前视）</li>
    </ul>
  </div>
  <div class="sec"><div class="h">L3 数量信号 · 卖出/规避</div>
    <ul class="tight">
      <li><b>52周高点卖出侧回测</b>：近高点持仓"突破新高后"的反应过度卖出（买入侧已验证+12.3pp，卖出侧是文档留的下一题）</li>
      <li><b>估值卖出在 LX-core 复验</b>：估值卖出 +11pp 只在 F-Score 验证过，需在最强基准 LX-core 上重测</li>
      <li><b>风格分歧信号</b>：成长/价值指数价差分位数 → 均值回归卖出（用户认知登记待测）</li>
      <li><b>舆论/换手过热</b>：同花顺热度、一致预期分歧度、换手率过热 → 卖出</li>
    </ul>
  </div>
  </div>
  <div>
  <div class="sec"><div class="h">L2 方法论 · 组合与增强</div>
    <ul class="tight">
      <li><b>LX 行业中性化/分散化</b>：便宜优先导致银行/建筑/煤炭聚集（当前 40 只里基建占比高）——加行业上限或行业中性，测是否牺牲收益换分散</li>
      <li><b>LX × 行业轮动组合</b>：行业轮动是唯一完全独立信息源(|ρ|<0.03, 多空+12.6%)，做行业层配置 + 刘旭行业内选股</li>
      <li><b>成长因子作增强层</b>：成长低IC高兑现(+12.4%/年、8年IC全正)——行业内叠加或门控，不做替换排序</li>
      <li><b>筹码合成行业内选股</b>：已验证个股层有效(锁仓度) → 在刘旭行业内或 AI 科技池内做第 2 排序维度</li>
      <li><b>风格 beta 剥离</b>：把 LX-core 的收益分解为 风格暴露 vs 选股 alpha，防止把风格 beta 当 alpha</li>
      <li><b>调仓频率实验</b>：半年频 vs 月频 vs 季频对比（GBM 换手~100% 的教训：低频信号才有稳定 alpha）</li>
    </ul>
  </div>
  <div class="sec"><div class="h">🛠 工程基建</div>
    <ul class="tight">
      <li><b>批量拉取模板复用</b>：_gbm_pull.py 直连申万 MCP 模板（0.6s/次、120/批硬上限）已验证，任何新因子全市场拉取直接改模板</li>
      <li><b>回测引擎扩展</b>：vnpy 式 union-of-dates 引擎已稳定，可加费用敏感性/滑点压力测试</li>
      <li><b>报告统一出口</b>：每框架一份 HTML → 整合为一个 dashboard（本项目文档已多，建议建 docs/ 索引）</li>
      <li><b>自动化</b>：若需要，可配置定期任务（如每周五刷新 dist52 监控、每月初刷 C-Score）</li>
    </ul>
  </div>
  </div>
</div>

<div class="ok"><b>优先级建议</b>：先做 P1 三项（beat 筛选补跑、账本补记、持仓追踪闭环）——它们不产生新研究但让框架"闭环可用"；
再攻 <b>LX×行业轮动</b> 与 <b>52周高点卖出侧</b>——前者是唯一独立信息源组合，后者是文档里明确留出的下一题。</div>

<footer>生成：_framework_overview_report.py | 数据：_lx_now_results.json / _lx_now_scored.json / _cs_now_results.json / _cs_now_exfin_results.json / _ai_chip_52wk_top.json / _lx_now_dist52.json | 框架文档：docs/投资认知框架.md + docs/ALPHA_LAYERS.md + docs/STRATEGIES.md</footer>
</div></body></html>"""

open(OUT_HTML, "w", encoding="utf-8").write(html)
print("written:", OUT_HTML, f"({os.path.getsize(OUT_HTML)} bytes)")
print("lx_core:", n_lx_core, "| lx_gm:", n_lx_gm, "| cs:", n_cs, "| cs_exfin:", n_cs_exfin, "| chip:", n_chip)
print("overlap lx∩cs:", overlap_lx_cs, "| lx∩chip:", overlap_lx_chip)
