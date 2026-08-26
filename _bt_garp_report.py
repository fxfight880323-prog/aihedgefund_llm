# -*- coding: utf-8 -*-
"""L5 增速门控放松实验报告 — 紫金矿业案例。
数据: _bt_garp_results.json (回测) + _bt_garp_now.json (当前时点) + 紫金档案。
"""
import json, os, html

os.chdir(os.path.dirname(os.path.abspath(__file__)))
BT = json.load(open("_bt_garp_results.json", encoding="utf-8"))
NOW = json.load(open("_bt_garp_now.json", encoding="utf-8"))

R = BT["results"]
IDX = BT["idx"]
VARIANT_META = {
    "core_finex": ("L5 增速≤25% + PEG≤2", "基线"),
    "g40": ("增速≤40% + PEG≤2", "适度放松"),
    "g60": ("增速≤60% + PEG≤2", "大放松"),
    "g99": ("增速≤99%(≈不限) + PEG≤2", "完全放开"),
    "garp": ("增速≤60% + PEG≤1", "★ 最优"),
    "peg_sort": ("增速≤60% + PEG≤2, PEG升序", "GARP排序"),
    "garp_q20": ("增速≤60% + PEG≤1, 80%PE+20%质量", "组合A"),
    "garp_q50": ("增速≤60% + PEG≤1, 50%PE+50%质量", "组合B"),
}

def esc(s):
    return html.escape(str(s)) if s is not None else "—"

def color(v, invert=False):
    """红涨绿跌；百分比收益红/绿，MDD 中性灰蓝。"""
    if v is None:
        return "#666"
    if invert:
        return "#1e8449" if v < 0 else "#c0392b"
    return "#c0392b" if v > 0 else "#1e8449"

# ---- 回测表 ----
rows_bt = ""
base = R["core_finex"]["total"]
order = ["core_finex", "g40", "g60", "g99", "garp", "peg_sort", "garp_q20", "garp_q50"]
for v in order:
    r = R[v]
    delta = r["total"] - base
    tag = "← 基线" if v == "core_finex" else f"{delta:+.2f}pp"
    hl = ' style="background:#eafaf1"' if v == "garp" else ""
    star = " ★" if v == "garp" else ""
    rows_bt += f"""<tr{hl}>
      <td class="l">{VARIANT_META[v][0]}{star}</td>
      <td class="l" style="color:#888">{VARIANT_META[v][1]}</td>
      <td style="color:{color(r['total'])};font-weight:700">{r['total']:+.2%}</td>
      <td>{r['ann']:+.2%}</td>
      <td style="color:{color(-r['mdd'])}">{r['mdd']:.2%}</td>
      <td style="color:{color(r['excess_idx'])}">{r['excess_idx']:+.2%}</td>
      <td style="color:{color(delta)}">{tag}</td></tr>"""

# ---- 当前时点名单 ----
def now_rows(v, zj_hl=False):
    d = NOW["variants"][v]
    out = ""
    for r in d["rows"]:
        hl = ' style="background:#fef9e7"' if (zj_hl and "601899" in r["code"]) else ""
        out += f"""<tr{hl}>
          <td>{r['rank']}</td><td class="l">{esc(r['code'])}</td>
          <td class="l"><b>{esc(r['name'])}</b></td>
          <td>{r['pe']}</td>
          <td>{esc(r['exp_g'])}</td>
          <td>{esc(r['peg'])}</td>
          <td>{esc(r['con_roe'])}</td>
          <td>{esc(r['gpm'])}</td>
          <td>{esc(r['cetop'])}</td>
          <td>{'✓' if r['in_gm'] else '—'}</td></tr>"""
    return out

# 紫金档案
zj = {
    "pe": 13.58, "pb": 4.81, "mv": 9184, "gpm": 31.06, "cetop": 10.42,
    "npyoy": 86.8, "dy": 1.16, "roe": 32.93, "g": 58.1, "peg": 0.31, "con_pe": 11.22,
}

# garp 新增股票 (从回测结果提取, 写死常驻新增 10 只)
garp_adds = [
    ("601975.SH", "招商南油", 14.4, 42.5, 0.49, 29.4, 13.8, "航运"),
    ("600123.SH", "兰花科创", 4.6, 52.9, 0.17, 54.8, 22.5, "煤炭"),
    ("601699.SH", "潞安环能", 5.1, 52.9, 0.18, 49.9, 23.2, "煤炭"),
    ("600985.SH", "淮北矿业", 6.3, 46.8, 0.20, 20.7, 21.2, "煤炭"),
    ("002128.SZ", "电投能源", 12.4, 38.9, 0.45, 39.8, 16.3, "煤炭/电解铝"),
    ("600248.SH", "陕建股份", 5.2, 48.7, 0.15, 12.0, 12.2, "建筑"),
    ("601058.SH", "赛轮轮胎", 12.9, 32.6, 0.38, 25.2, 17.7, "轮胎"),
    ("600938.SH", "中国海防", 10.0, 21.1, 0.74, 51.2, 19.0, "军工电子"),
    ("000498.SZ", "山东路桥", 5.9, 25.6, 0.21, 11.7, 16.8, "建筑"),
    ("600801.SH", "华新水泥", 13.8, 30.4, 0.53, 31.2, 10.4, "水泥"),
]
adds_html = "".join(
    f"""<tr><td class="l">{esc(a[1])}</td><td class="l mono">{a[0]}</td>
    <td>{a[6]}</td><td>{a[2]}</td><td>{a[3]}</td><td>{a[4]}</td>
    <td>{a[5]}</td><td>{a[7]}</td></tr>""" for a in garp_adds)

html_doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>L5 增速门控放松实验 · 紫金矿业案例（{NOW['as_of']}）</title>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 28px 40px;
        background: #fafafa; color: #222; line-height: 1.65; }}
 h1 {{ font-size: 23px; margin-bottom: 4px; }}
 h2 {{ font-size: 16px; margin-top: 32px; border-left: 4px solid #b8860b;
        padding-left: 10px; }}
 h3 {{ font-size: 14px; margin-top: 20px; }}
 .sub {{ color: #666; font-size: 13px; }}
 table {{ border-collapse: collapse; margin: 12px 0; font-size: 13px;
          background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 5px 9px; text-align: right;
           white-space: nowrap; }}
 th {{ background: #f0f0f0; position: sticky; top: 0; }}
 td.l {{ text-align: left; }} .mono {{ font-family: Consolas, monospace; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
          padding: 14px 18px; margin: 12px 0; font-size: 13.5px; }}
 .kpi {{ font-size: 21px; font-weight: 800; }}
 .good {{ color: #c0392b; }} .bad {{ color: #1e8449; }}
 .warn {{ color: #b9770e; }}
 .note {{ color: #888; font-size: 12px; margin-top: 20px;
          border-top: 1px dashed #ccc; padding-top: 10px; }}
 .tag {{ display: inline-block; background: #b8860b; color: #fff;
         border-radius: 4px; padding: 1px 8px; font-size: 11px; }}
 .tag-r {{ background: #c62828; }}
 .grid {{ display: flex; gap: 14px; flex-wrap: wrap; }}
 .box {{ flex: 1; min-width: 280px; background: #fff; border: 1px solid #e0e0e0;
         border-radius: 8px; padding: 12px 16px; }}
 .big {{ font-size: 15px; font-weight: 700; }}
</style></head><body>

<h1>L5 增速门控放松实验 · "紫金矿业这种公司"该不该放进来</h1>
<p class="sub">数据截至 <b>{NOW['as_of']}</b> · 回测 2021-08 ~ 2026-08 日频+复权 ·
池子 = 万得全A PIT 成分剔除金融（core_finex 口径）· 半年调仓 · 5bp+10bp 成本</p>

<div class="card">
<b>核心发现：紫金矿业不是"贵"，是被 L5 增速门控冤枉了。</b><br>
福耀玻璃的失败模式是"中 PE 中质量排不进 top40"（排序问题）；紫金矿业完全不同——
PE_TTM <b>13.6</b>（便宜）、预期 ROE <b>32.9%</b>（顶级）、毛利率 <b>31.1%</b>（过质量层）、
PEG <b>0.31</b>（极便宜），但一致预期净利增速 <b>58%</b> 撞上 L5 的 <b>增速≤25%</b> 上限，
在筛选层被直接剔除。它属于"GARP 型公司"——高增长，但价格相对于增长仍然便宜。
</div>

<h2>① 紫金矿业档案（2026-08-24）</h2>
<table>
<tr><th>指标</th><th>数值</th><th>解读</th></tr>
<tr><td class="l">PE_TTM / 预期PE</td><td><b>{zj['pe']}</b> / {zj['con_pe']}</td>
<td class="l">不贵——低于 L4 上限 25</td></tr>
<tr><td class="l">预期 ROE</td><td><b>{zj['roe']}%</b></td>
<td class="l">池内顶级（top ~5%）</td></tr>
<tr><td class="l">毛利率</td><td>{zj['gpm']}%</td>
<td class="l">高于全市场中位数 26.4%，过 gm 质量层</td></tr>
<tr><td class="l">一致预期净利增速</td><td><b class="warn">{zj['g']}%</b></td>
<td class="l">🔥 撞 L5 上限 25%，被剔除的直接原因</td></tr>
<tr><td class="l">PEG</td><td><b>{zj['peg']}</b></td>
<td class="l">增速虽高，估值相对增长极便宜</td></tr>
<tr><td class="l">PB / 总市值</td><td>{zj['pb']} / {zj['mv']}亿</td>
<td class="l">PB 4.8 不便宜，但 ROE 33% 支撑</td></tr>
<tr><td class="l">OCF/市值 / 股息率</td><td>{zj['cetop']}% / {zj['dy']}%</td>
<td class="l">现金流健康</td></tr>
</table>

<h2>② 回测：增速门控放松 8 变体（日频+复权，等权全A/中证全指对比）</h2>
<table>
<tr><th>门控口径</th><th>类别</th><th>总收益</th><th>年化</th><th>MDD</th>
<th>超额(中证全指)</th><th>vs 基线</th></tr>
{rows_bt}
</table>
<div class="card">
<b>倒 U 型规律：门控不是越松越好，存在最优区间。</b><br>
<span class="good">增速≤25%（基线）</span> → <span class="good">≤40%（+4.98pp）</span> →
<span class="warn">≤60%（-1.12pp）</span> → <span class="bad">≈不限（-3.35pp）</span>：
完全放开混入高增速高 PEG 的投机股。<br>
<span class="tag">最优解</span> <b>garp（增速≤60% + PEG≤1 + PE升序）</b>：
总收益 <span class="good">+34.57%</span>（vs 基线 <span class="good">+5.12pp</span>），
MDD <span class="good">18.54%</span>（vs 基线 22.12%，<b>-3.6pp</b>）——<b>收益更高、回撤更低，双赢</b>。
它的机制：允许高增速，但用 <b>PEG≤1</b> 严格补偿（增速可以高，估值必须匹配）。
</div>

<h3>排序实验：PEG 排序与混合排序都稀释收益</h3>
<div class="card">
<b>PE 升序信念在 garp 池里依然成立，甚至更强：</b>
PEG 升序（peg_sort）<span class="bad">-22.55pp</span> 灾难——PEG 排序把"增速高但 PE 高"的股票
优先，直接违背便宜优先信念；混合排序（garp_q20 +2.69pp / garp_q50 -5.61pp）都低于
纯 PE 排序的 garp（+5.12pp）。<b>在 garp 池里，质量信息已隐含在 PEG≤1 门控中，
排序层不需要再叠加质量权重。</b>
</div>

<h2>③ garp 换入了什么（回测常驻新增，≥2 期）</h2>
<table>
<tr><th>名称</th><th>代码</th><th>行业</th><th>PE</th><th>增速%</th><th>PEG</th>
<th>毛利%</th><th>ROE%</th></tr>
{adds_html}
</table>
<div class="card">
<b>全部是"紫金同类"：高增速周期资源/制造龙头</b>——煤炭（兰花科创、潞安环能、淮北矿业、
电投能源）、航运（招商南油）、水泥（华新水泥）、轮胎（赛轮轮胎）等。
它们是 core（增速≤25%）池里被误杀、garp 池里以 PE 个位数~13 的便宜价进入的组合成员。
<b>这就是"包括紫金矿业这种公司"的正解：不是为紫金开后门，而是修正门控，让整个
"高增长+便宜"类别（紫金是其中一员）回到池子里。</b>
</div>

<h2>④ 当前时点三名单对比（{NOW['as_of']}，top40 等权 2.5%）</h2>
<h3>garp 名单（推荐落地版 · 回测最优）· 池 {NOW['variants']['garp']['n_pool']} 只 ·
紫金矿业排 <b>{NOW['variants']['garp']['zj_rank']}/183</b> <span class="warn">❌ 差 7 名未进</span></h3>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>PE</th><th>增速%</th><th>PEG</th>
<th>ROE%</th><th>毛利%</th><th>OCF%</th><th>过gm</th></tr>
{now_rows('garp')}
</table>

<h3>garp + q20 混合排序（为纳入紫金的变通版）· 紫金排 39/183 <span class="tag tag-r">✅ 进 top40</span></h3>
<p class="sub">代价：回测收益从 garp 的 +5.12pp 降至 +2.69pp——为纳入紫金单票付约 2.4pp 超额成本。</p>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>PE</th><th>增速%</th><th>PEG</th>
<th>ROE%</th><th>毛利%</th><th>OCF%</th><th>过gm</th></tr>
{now_rows('garp_q20', zj_hl=True)}
</table>
<p class="sub" style="color:#b9770e">黄底 = 紫金矿业（601899.SH）</p>

<h2>⑤ 结论：紫金矿业怎么才能进名单</h2>
<div class="grid">
<div class="box">
<span class="big">方案 A · 采纳 garp 门控（推荐）</span><br>
增速≤60% + PEG≤1 + PE 升序。<br>
回测 <span class="good">+5.12pp / MDD -3.6pp</span> 双赢，池内已有一整批"紫金同类"
（煤炭/航运/有色）以更便宜价格入选。<br>
<b>紫金本身差 7 名不进</b>——PE 13.6 略高于 top40 截止线 13.0。这是框架的诚实暴露：
它修正了"增速门控误杀"，但"PE 升序"依然把它排在更便宜的高增长股之后。
</div>
<div class="box">
<span class="big">方案 B · garp + q20 混合排序</span><br>
紫金当前排 39 恰好进名单。<br>
代价：回测超额从 +5.12pp 降到 +2.69pp（每期换入的质量倾斜在 garp 池里是净稀释）。<br>
<b>适合"我就想要紫金"的主观偏好，代价是 ~2.4pp 回测超额。</b>
</div>
<div class="box">
<span class="big">方案 C · 白名单插队</span><br>
在 garp top40 之上人工放行 1-2 只超高质量龙头（如紫金）。<br>
单票权重 2.5% 的扰动很小，但<b>超出回测证据</b>，属于主观判断层。<br>
建议仅用于"质量确信度极高+当前处于周期盈利上行"的标的。
</div>
</div>

<div class="card">
<b>方法论备忘：</b>① garp 门控 = L5 从"增速≤25% 且 PEG≤2"改为"增速≤60% 且 PEG≤1"，
其他层（市值/PE>0/L4/金融剔除/PE升序）全部不变；② 紫金档案中增速 58% > 60% 上限?
不——58% ≤ 60%，它 <b>在</b> garp 池内（183 只），只是 PE 排序 47 未进 top40；
③ 若未来紫金增速预期继续上调超过 60%（当前分析师仍在大幅上调：4w 修正 +81%），
将滑出 garp 池——这是"高增长+高预期"的固有风险；④ 回测区间 2021-08~2026-08，
过去表现不代表未来。</div>

<p class="note">数据来源：juzi 估值面板 / HF 因子 / 朝阳永续一致预期（PIT 快照）+ 腾讯行情，
无合成数据。本报告由数值化筛选器+回测引擎产生，不构成投资建议。</p>

</body></html>"""

open("_bt_garp_report.html", "w", encoding="utf-8").write(html_doc)
print(f"报告 → _bt_garp_report.html ({len(html_doc):,} bytes)")
