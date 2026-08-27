# -*- coding: utf-8 -*-
"""core(garp/全池) vs LX-gm(质量过滤版) 对比报告生成。"""
import json
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")

d = json.load(open("_bt_gm_daily_data.json", encoding="utf-8"))
fin = set(d["fin"])
names = json.load(open("_bt_band_names.json", encoding="utf-8"))
wc, wg = d["weights"]["core"], d["weights"]["gm"]
meta = d["meta"]

def nav_map(nav):
    return {r["date"]: r["nav"] for r in nav}

C, G, EW, IX = nav_map(d["core"]), nav_map(d["gm"]), nav_map(d["ew"]), nav_map(d["idx"])

def calc(m, w0="2021-08-31", w1="2026-08-24"):
    ks = [x for x in sorted(m) if w0 <= x <= w1]
    if not ks:
        return None
    tot = m[ks[-1]] / m[ks[0]] - 1
    yrs = len(ks) / 252.0
    ann = (1 + tot) ** (1 / yrs) - 1 if tot > -1 else -1.0
    peak = mdd = 0.0
    for k in ks:
        peak = max(peak, m[k])
        mdd = max(mdd, 1 - m[k] / peak)
    return tot, ann, mdd

r5 = {k: calc(m) for k, m in [("core", C), ("gm", G), ("ew", EW), ("idx", IX)]}
r3 = {k: calc(m, "2023-08-31") for k, m in [("core", C), ("gm", G), ("ew", EW), ("idx", IX)]}

def yearly(m):
    yrs = {}
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        seg = [dt for dt in sorted(m) if dt.startswith(y)]
        if len(seg) >= 2:
            yrs[y] = m[seg[-1]] / m[seg[0]] - 1
    return yrs

Y = {k: yearly(m) for k, m in [("core", C), ("gm", G), ("ew", EW), ("idx", IX)]}

# 重叠与银行占比
rows = []
for p in sorted(wc):
    c, g = set(wc[p]), set(wg[p])
    cb = sum(1 for t in c if t in fin)
    gb = sum(1 for t in g if t in fin)
    rows.append((p, len(c & g), cb, gb))
avg_overlap = statistics.mean(r[1] for r in rows)
avg_cb = statistics.mean(r[2] for r in rows)
avg_gb = statistics.mean(r[3] for r in rows)

# ---- SVG 净值曲线 ----
def series_svg(m, color):
    ks = sorted(m)
    n = len(ks)
    w, h = 1000, 320
    pad_l, pad_r, pad_t, pad_b = 55, 15, 15, 30
    v0, v1 = min(m[k] for k in ks), max(m[k] for k in ks)
    rng = v1 - v0 or 1.0
    def xy(i, k):
        x = pad_l + (w - pad_l - pad_r) * i / (n - 1)
        y = pad_t + (h - pad_t - pad_b) * (1 - (m[k] - v0) / rng)
        return x, y
    pts = "".join(f"{xy(i,k)[0]:.1f},{xy(i,k)[1]:.1f} " for i, k in enumerate(ks))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/>'

def ygrid(m):
    ks = sorted(m)
    v0, v1 = min(m[k] for k in ks), max(m[k] for k in ks)
    rng = v1 - v0 or 1.0
    out = []
    for i in range(6):
        val = v0 + rng * i / 5
        y = 15 + 275 * (1 - (val - v0) / rng)
        out.append(f'<line x1="55" y1="{y:.0f}" x2="985" y2="{y:.0f}" stroke="#e8e8e8" stroke-width="0.6"/><text x="48" y="{y+3:.0f}" text-anchor="end" font-size="10" fill="#888">{val:,.2f}</text>')
    return "".join(out)

def xlabels(ks):
    marks = {}
    for k in ks:
        marks.setdefault(k[:4], k)
    out = []
    for y, k in sorted(marks.items()):
        i = ks.index(k)
        x = 55 + 930 * i / (len(ks) - 1)
        out.append(f'<text x="{x:.0f}" y="325" text-anchor="middle" font-size="10" fill="#888">{y}</text>')
    return "".join(out)

ks_all = sorted(C)
svg_nav = f'''<svg viewBox="0 0 1000 345" style="width:100%;background:#fff">
{ygrid(C)}
{series_svg(G, "#d35400")}
{series_svg(EW, "#2471a3")}
{series_svg(IX, "#7d3c98")}
{series_svg(C, "#c0392b")}
{xlabels(ks_all)}
</svg>'''

# ---- 银行占比柱状图 ----
def bar_chart():
    ps = [r[0] for r in rows]
    cb = [r[2] for r in rows]
    gb = [r[3] for r in rows]
    n = len(ps)
    w, h = 1000, 240
    bw = 46
    gap = (930 - n * bw) / (n - 1) if n > 1 else 0
    maxv = 32
    out = []
    for i, p in enumerate(ps):
        x0 = 55 + i * (bw + gap)
        hc = 175 * cb[i] / maxv
        hg = 175 * gb[i] / maxv
        out.append(f'<rect x="{x0:.0f}" y="{205-hc:.0f}" width="{bw*0.42:.0f}" height="{hc:.0f}" fill="#c0392b" opacity="0.85"/>')
        out.append(f'<rect x="{x0+bw*0.52:.0f}" y="{205-hg:.0f}" width="{bw*0.42:.0f}" height="{hg:.0f}" fill="#d35400" opacity="0.85"/>')
        out.append(f'<text x="{x0+bw*0.21:.0f}" y="220" text-anchor="middle" font-size="9" fill="#888">{p[2:]}</text>')
    legend = ('<rect x="720" y="8" width="10" height="10" fill="#c0392b"/><text x="736" y="17" font-size="11" fill="#555">core 银行数</text>'
              '<rect x="840" y="8" width="10" height="10" fill="#d35400"/><text x="856" y="17" font-size="11" fill="#555">gm 银行数</text>')
    return f'<svg viewBox="0 0 1000 240" style="width:100%;background:#fff">{legend}{"".join(out)}</svg>'

# ---- HTML ----
def pct(x, signed=True):
    return f"{x:+.1%}" if signed else f"{x:.1%}"

rows5 = ""
for k, label, color in [("core", "LX-core（garp 门控 · 含金融）", "#c0392b"),
                        ("gm", "LX-gm 质量过滤版（core+毛利率≥中位）", "#d35400"),
                        ("ew", "等权全A（同口径基准）", "#2471a3"),
                        ("idx", "中证全指 000985.SH", "#7d3c98")]:
    t, a, m = r5[k]
    t3, a3, m3 = r3[k]
    rows5 += (f'<tr><td style="color:{color};font-weight:600">{label}</td>'
              f'<td style="color:{color};font-weight:700">{pct(t)}</td><td>{pct(a,False)}</td><td>{pct(-m)}</td>'
              f'<td>{pct(t3)}</td><td>{pct(a3,False)}</td><td>{pct(-m3)}</td></tr>')

# 分年度
ys = ["2021", "2022", "2023", "2024", "2025", "2026"]
yrows = ""
for k, label, color in [("core", "LX-core", "#c0392b"), ("gm", "LX-gm", "#d35400"),
                        ("ew", "等权全A", "#2471a3"), ("idx", "中证全指", "#7d3c98")]:
    tds = "".join(f"<td>{pct(Y[k].get(y, 0))}</td>" for y in ys)
    yrows += f'<tr><td style="color:{color};font-weight:600">{label}</td>{tds}</tr>'
# 超额行
exrows = ""
ex = ""
for y in ys:
    v = Y["core"].get(y, 0) - Y["gm"].get(y, 0)
    ex += f'<td style="color:{("red" if v>0 else "#2e8b57")};font-weight:700">{pct(v)}</td>'
exrows = f'<tr><td style="font-weight:600">core − gm 超额</td>{ex}</tr>'

# 每期明细
prows = ""
for p, ov, cb_, gb_ in rows:
    prows += (f'<tr><td>{p}</td><td>{cb_}</td><td>{gb_}</td>'
              f'<td style="color:{("red" if ov>=20 else "#c0392b" if ov>=10 else "#888")};font-weight:700">{ov}/40</td></tr>')

# 当前期名单对比
p_cur = "2026-04"
def cur_rows(ws, fl):
    out = ""
    for i, t in enumerate(ws[p_cur][:12], 1):
        tag = "🏦" if t in fin else ""
        nm = names.get(t, "")
        out += f'<tr><td>{i}</td><td>{t}</td><td>{nm}</td><td>{tag}</td></tr>'
    return out

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>LX-core vs 质量过滤版（LX-gm）日频回测对比</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,"Microsoft YaHei",sans-serif; background:#f5f6fa; color:#2c3e50; line-height:1.65; }}
.container {{ max-width:1120px; margin:0 auto; padding:26px; }}
h1 {{ font-size:23px; color:#1a1a2e; margin-bottom:6px; }}
.subtitle {{ color:#7f8c8d; font-size:13px; margin-bottom:18px; }}
h2 {{ font-size:18px; color:#1a1a2e; margin:30px 0 12px; border-left:4px solid #e74c3c; padding-left:12px; }}
.card {{ background:#fff; border-radius:10px; padding:18px 20px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
.concl {{ background:#fff8f6; border:1px solid #f5c6b8; border-left:5px solid #c0392b; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ padding:7px 10px; border-bottom:1px solid #eee; text-align:right; }}
th {{ background:#fafafa; color:#555; font-weight:600; }}
td.l,th.l {{ text-align:left; }}
tr:hover td {{ background:#fafcff; }}
.kpi {{ display:flex; gap:14px; flex-wrap:wrap; margin:10px 0 4px; }}
.kpi div {{ flex:1; min-width:200px; background:#fff; border-radius:8px; padding:14px 16px; border:1px solid #eee; }}
.kpi .n {{ font-size:22px; font-weight:700; }}
.kpi .t {{ font-size:12px; color:#888; margin-top:2px; }}
.up {{ color:#c0392b; }} .dn {{ color:#2e8b57; }}
.legend {{ font-size:12px; color:#555; margin:6px 2px; }}
.tag {{ display:inline-block; background:#eef3fb; color:#2c5282; border-radius:4px; padding:1px 7px; font-size:11px; margin-right:4px; }}
.warn {{ background:#fffbe9; border:1px solid #f0e0a0; border-left:5px solid #d68910; }}
</style></head><body><div class="container">

<h1>LX-core（含金融） vs 质量过滤版（LX-gm）—— 日频回测对比</h1>
<div class="subtitle">口径：万得全A PIT 成分 · garp 门控（增速≤60% 且 0&lt;PEG≤1）· PE 升序 top40 等权 · 日频复权 · 半年度调仓 · T+1 撮合 · 5bp+10bp · 2021-08 ~ 2026-08（锚点 +67.01% 精确对齐 garp 审计）</div>

<div class="card concl">
<h2 style="margin-top:0">核心结论</h2>
<div class="kpi">
  <div><div class="n up">+67.01%</div><div class="t">LX-core 总收益（年化 11.31% · MDD -16.67%）</div></div>
  <div><div class="n" style="color:#d35400">+45.07%</div><div class="t">LX-gm 质量过滤版（年化 8.08% · MDD -24.43%）</div></div>
  <div><div class="n dn">−21.94pp</div><div class="t">质量过滤的增量贡献（<b>负贡献</b>，MDD 反而恶化 7.8pp）</div></div>
</div>
<p style="margin-top:12px;font-size:14px">
<b>“毛利率≥全市场中位数”作为硬过滤层，在 garp 门控日频口径下是明确的负贡献</b>：
收益 −21.94pp、最大回撤从 16.67% 恶化到 24.43%。质量过滤的实际效果是把银行（core 每期 17~29 只 → gm 0~3 只）和低毛利周期股整批剔除，换成高毛利成长/消费——<b>2024 低估值修复大年直接踏空（core +33.1% vs gm +10.7%，单年差 −22.4pp）</b>。3 年窗口（2023-08 起）gm 甚至跑输等权全A −3.5pp，连超额都没有。
</p>
</div>

<h2>核心指标（双窗口）</h2>
<div class="card">
<table>
<tr><th class="l">组合</th><th>5年总收益</th><th>5年年化</th><th>5年MDD</th><th>3年总收益</th><th>3年年化</th><th>3年MDD</th></tr>
{rows5}
</table>
<div class="legend">3年窗口 = 2023-08-31 ~ 2026-08-24（与“过去3年回测”报告同窗）。</div>
</div>

<h2>净值曲线（2021-08 ~ 2026-08）</h2>
<div class="card">
{svg_nav}
<div class="legend">
<span style="color:#c0392b">■</span> LX-core　<span style="color:#d35400">■</span> LX-gm 质量版　<span style="color:#2471a3">■</span> 等权全A　<span style="color:#7d3c98">■</span> 中证全指
</div>
</div>

<h2>分年度收益</h2>
<div class="card">
<table>
<tr><th class="l">组合</th><th>2021(8-12)</th><th>2022</th><th>2023</th><th>2024</th><th>2025</th><th>2026(至8)</th></tr>
{yrows}
{exrows}
</table>
<div class="legend">
质量版仅在 2025（+5.9pp）与 2021（+3.3pp）跑赢 core；<b>2024 低估值修复年 −22.4pp 是全部差距来源</b>，2023/2026 各小幅跑输 3~4pp。
</div>
</div>

<h2>持仓结构：质量过滤换掉了什么</h2>
<div class="card">
{bar_chart()}
<div class="legend"><b>银行持仓数/期</b>：core 平均 {avg_cb:.1f} 只（占比 {avg_cb/40:.0%}），gm 平均 {avg_gb:.1f} 只——质量过滤本质 = 结构性剔除银行金融。</div>
<table style="margin-top:10px">
<tr><th class="l">调仓期</th><th>core 银行数</th><th>gm 银行数</th><th>gm∩core 重叠</th></tr>
{prows}
</table>
<div class="legend">两组合每期重叠仅 {avg_overlap:.0f}/40（2~13 只）——是<b>两个几乎完全不同的组合</b>，不是“core 的干净版”。质量版每期从全池 ~200~370 只命中里重新取 40 只，低毛利便宜股被高毛利标的整体替换。</div>
</div>

<h2>当前期（2026-04）名单对比</h2>
<div class="card" style="display:flex;gap:20px;flex-wrap:wrap">
<div style="flex:1;min-width:300px"><table>
<tr><th>#</th><th>code</th><th class="l">LX-core top12</th><th></th></tr>
{cur_rows(wc, True)}
</table></div>
<div style="flex:1;min-width:300px"><table>
<tr><th>#</th><th>code</th><th class="l">LX-gm top12</th><th></th></tr>
{cur_rows(wg, True)}
</table></div>
</div>

<h2>与旧口径结论（月频/旧 L5）的反转归因</h2>
<div class="card warn">
<p>此前 <code>_lx_gm_check.html</code>（2026-08-21，月频 + 旧 L5“增速≤25% 且 PEG≤2”）结论是 <b>“毛利率层的价值是回撤保护”（gm MDD −13.9% vs core −24.9%）</b>。本次日频 garp 口径结论完全反转：gm 收益 −21.94pp、MDD 反而更差。三个根源：</p>
<ul style="margin:8px 0 0 20px;font-size:13.5px">
<li><b>L5 门控不同</b>：garp（≤60% + 0&lt;PEG≤1）池子更宽（每期 ~200~370 只 vs 旧口径 ~180 只），质量过滤后补进的高毛利标的更多、更偏成长（医药/软件/消费），2022-2023 熊市跌得更深；旧口径窄池+低增速约束下剩余高毛利股偏防御消费。</li>
<li><b>2024 修复年驱动</b>：garp 全池 core 在 2024 +33.1%（银行+周期估值修复），质量版把银行滤掉只剩 +10.7%——单年 −22.4pp 决定胜负。</li>
<li><b>颗粒度</b>：月频撮合虚高且掩盖了 2022-2023 的日内回撤差异。</li>
</ul>
</div>

<h2>落地建议：质量该用在排序层，不是过滤层</h2>
<div class="card">
<table>
<tr><th class="l">用法</th><th>口径</th><th>收益增量</th><th>MDD 变化</th><th>换手</th><th class="l">结论</th></tr>
<tr><td class="l" style="font-weight:600">硬过滤 gm</td><td>core + 毛利率≥全市场中位数（剔除低毛利）</td><td class="dn">−21.94pp</td><td class="dn">−7.76pp（恶化）</td><td>换掉 ~30 只/期</td><td class="l">❌ 本回测证伪，废弃</td></tr>
<tr><td class="l" style="font-weight:600">软排序 q20</td><td>排序 = 0.8×PE百分位 + 0.2×质量分（不剔除任何人）</td><td class="up">+3.40pp</td><td>≈0</td><td>仅换 1~6 只/期</td><td class="l">✅ 已验证正贡献，落地</td></tr>
<tr><td class="l">质量优先排序</td><td>纯质量分排序</td><td class="dn">跑输基准</td><td>—</td><td>全换</td><td class="l">❌ 已证伪</td></tr>
</table>
<p style="margin-top:10px;font-size:13.5px">
<b>质量层的正确姿势是“微调”而非“门槛”</b>：q20 只在 PE 排序上给质量 +20% 权重（踢出“便宜但低质”边缘股，换成“稍贵但高质”股），每期仅换 1~6 只、收益 +3.40pp、回撤不变；而 gm 式硬过滤整批替换 30 只，等于把“低估+低毛利”的银行周期（本框架 alpha 的主要来源）全部扔掉——与“质量优先跑输基准”是同一个错误，只是换了层皮。
</p>
</div>

<div class="card">
<h2 style="margin-top:0">数据与审计</h2>
<table>
<tr><th class="l">项目</th><th class="l">值</th></tr>
<tr><td class="l">锚点校验</td><td class="l">core/全池 = +67.01% / MDD 16.67%，与 garp 审计（_bt_garp_audit_results.json full/g60）<b>逐位一致</b></td></tr>
<tr><td class="l">池子</td><td class="l">万得全A 881001.WI PIT 成分（10期，4441→5532 只），全池基座不剔金融</td></tr>
<tr><td class="l">价格</td><td class="l">_bt_daily_px_full.json 530 只日频复权（497 审计基座 + 本次补拉 33 只 gm 名单缺价股，腾讯 fqkline qfq）</td></tr>
<tr><td class="l">成本</td><td class="l">5bp 费率 + 10bp 滑点（15bp 单边），半年度调仓 T+1 撮合</td></tr>
<tr><td class="l">gm 口径</td><td class="l">L4+L5 命中池内 gpm≥全市场中位数（每期 ~23.0±0.9%），再 PE 升序取 40</td></tr>
<tr><td class="l">产物</td><td class="l">_bt_gm_daily.py / _bt_gm_fetch_px.py / _bt_gm_daily_data.json / _bt_gm_weights.json</td></tr>
</table>
</div>

</div></body></html>"""

open("_bt_gm_report.html", "w", encoding="utf-8").write(html)
print("saved _bt_gm_report.html")
