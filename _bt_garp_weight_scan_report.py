# -*- coding: utf-8 -*-
"""GARP 权重扫描报告：收益 / 回撤 / 夏普 随 value 权重 w 变化的曲线。"""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

d = json.load(open("_bt_garp_weight_scan_results.json", encoding="utf-8"))
res = d["results"]
modes = d["meta"]["score_modes"]
xs = [float(w) for w in sorted(res[modes[0]].keys(), key=float)]

MODE_META = {
    "quality":    {"label": "原质量分 (gpm+ROE+资本效率)", "color": "#94a3b8", "dash": "6 4"},
    "con_np_yoy": {"label": "一致预期净利增速",          "color": "#2563eb", "dash": ""},
    "oryoy":      {"label": "营收同比增速",              "color": "#16a34a", "dash": ""},
    "npyoy":      {"label": "净利同比增速",              "color": "#ea580c", "dash": ""},
}


def line_chart(series, ylabel, y_min, y_max, y_fmt="{:.0f}", y_ticks=None,
               width=680, height=330):
    """series: [(mode, ys)]  用 MODE_META 取颜色。返回 SVG 字符串。"""
    left, right = 70, width - 26
    top, bottom = 26, height - 46
    y_min -= (y_max - y_min) * 0.06
    y_max += (y_max - y_min) * 0.06

    def X(x):
        return left + (x - xs[0]) / (xs[-1] - xs[0]) * (right - left)

    def Y(v):
        return bottom - (v - y_min) / (y_max - y_min) * (bottom - top)

    parts = []
    # 水平网格 + y 轴刻度
    if y_ticks is None:
        n = 6
        y_ticks = [y_min + (y_max - y_min) * i / (n - 1) for i in range(n)]
    for yv in y_ticks:
        yy = Y(yv)
        parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" '
                     f'stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{left-8}" y="{yy+4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="#64748b">{y_fmt.format(yv)}</text>')
    # 垂直网格（w 刻度）
    for x in xs:
        xx = X(x)
        parts.append(f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{bottom}" '
                     f'stroke="#f1f5f9" stroke-width="1"/>')
    # x 轴标签
    for x in xs:
        xx = X(x)
        parts.append(f'<text x="{xx:.1f}" y="{bottom+18:.1f}" text-anchor="middle" '
                     f'font-size="10" fill="#64748b">{x:.1f}</text>')
    # 折线
    for mode, ys in series:
        meta = MODE_META[mode]
        pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(xs, ys))
        dash = f' stroke-dasharray="{meta["dash"]}"' if meta["dash"] else ""
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{meta["color"]}" '
                     f'stroke-width="2.2"{dash}/>')
        # 数据点
        for x, y in zip(xs, ys):
            parts.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.6" '
                         f'fill="{meta["color"]}"/>')
    # y 轴标题
    parts.append(f'<text x="14" y="{(top+bottom)/2:.1f}" text-anchor="middle" '
                 f'font-size="11" fill="#64748b" transform="rotate(-90 14 {(top+bottom)/2:.1f})">'
                 f'{ylabel}</text>')
    return "".join(parts)


def legend():
    items = []
    for mode in modes:
        meta = MODE_META[mode]
        dash = f' stroke-dasharray="{meta["dash"]}"' if meta["dash"] else ""
        items.append(
            f'<span style="display:inline-flex;align-items:center;margin-right:18px;'
            f'font-size:12px;color:#334155">'
            f'<svg width="26" height="10" style="margin-right:5px">'
            f'<line x1="0" y1="5" x2="26" y2="5" stroke="{meta["color"]}" '
            f'stroke-width="2.5"{dash}/></svg>{meta["label"]}</span>'
        )
    return "".join(items)


# 提取序列
total_series = [(m, [res[m][str(w)]["total"] * 100 for w in xs]) for m in modes]
mdd_series = [(m, [res[m][str(w)]["mdd"] * 100 for w in xs]) for m in modes]
sharpe_series = [(m, [res[m][str(w)]["sharpe"] if res[m][str(w)]["sharpe"] is not None else 0
                       for w in xs]) for m in modes]
ann_series = [(m, [res[m][str(w)]["ann"] * 100 for w in xs]) for m in modes]

# 找出各 mode 最优 w
best = {}
for m in modes:
    best[m] = max(xs, key=lambda w: res[m][str(w)]["total"])

# w=1.0 纯价值基准
pure_value = res["quality"]["1.0"]
pure_total = pure_value["total"] * 100
pure_mdd = pure_value["mdd"] * 100
pure_sharpe = pure_value["sharpe"]

# 原 q20 (w=0.8 quality) 参考
q20 = res["quality"]["0.8"]

# 生成表格行
def table_rows():
    rows = []
    for w in xs:
        cells = []
        for m in modes:
            r = res[m][str(w)]
            cells.append(f"{r['total']*100:+7.1f}% / {r['mdd']*100:4.1f}%")
        row = (f"<tr><td class='mono'>{w:.1f}</td>"
               + "".join(f"<td class='mono'>{c}</td>" for c in cells) + "</tr>")
        rows.append(row)
    return "\n".join(rows)


html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GARP 权重扫描 · 真成长 × 低估值</title>
<style>
:root {{ --bg:#f8fafc; --card:#ffffff; --ink:#0f172a; --sub:#64748b;
  --line:#e2e8f0; --accent:#2563eb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }}
.wrap {{ max-width:960px; margin:0 auto; padding:28px 20px 60px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.sub {{ color:var(--sub); font-size:13px; margin-bottom:20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:20px 22px; margin-bottom:20px; }}
.card h2 {{ font-size:15px; margin:0 0 12px; }}
.verdict {{ background:linear-gradient(135deg,#1e293b,#334155); color:#f8fafc;
  border-radius:12px; padding:20px 22px; margin-bottom:20px; }}
.verdict .big {{ font-size:15px; line-height:1.7; }}
.verdict b {{ color:#fbbf24; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:14px 16px; }}
.kpi .k {{ font-size:11px; color:var(--sub); }}
.kpi .v {{ font-size:20px; font-weight:700; margin-top:4px; }}
.kpi .d {{ font-size:11px; color:var(--sub); margin-top:2px; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th,td {{ padding:6px 8px; text-align:center; border-bottom:1px solid var(--line); }}
th {{ background:#f1f5f9; color:#334155; font-weight:600; }}
.mono {{ font-family:ui-monospace,"SFMono-Regular",Consolas,monospace; }}
.note {{ color:var(--sub); font-size:12px; line-height:1.7; margin-top:8px; }}
.tag {{ display:inline-block; background:#eff6ff; color:#1d4ed8; border-radius:6px;
  padding:1px 7px; font-size:11px; margin-right:6px; }}
</style></head><body><div class="wrap">

<h1>GARP 权重扫描 · 「真成长 × 低估值」</h1>
<div class="sub">评分 = w×PE便宜度 + (1-w)×非价值分 &nbsp;|&nbsp; 框架：top15 + mom60_top50 gate + cap8 + 半年调仓 &nbsp;|&nbsp; 2021-08 ~ 2026-04</div>

<div class="verdict"><div class="big">
  <b>结论：这是纯估值策略，成长因子 5 年样本内全为负贡献。</b><br>
  无论用哪种「成长」口径（营收增速 / 净利增速 / 一致预期增速），权重越低（越偏成长）收益越差：
  纯成长（w=0）收益仅 <b>+7.7%~+19.8%</b>，纯价值（w=1）<b>+123.7%</b>。
  最优权重落在 <b>w=0.9~1.0</b>（价值占 90%~100%），「真成长」只能做 10% 以内微调，
  其中 <b>营收增速(oryoy)</b> 是唯一能带来正边际（w=0.9 时 +128.6% vs 纯价值 +123.7%）的口径。
</div></div>

<div class="grid">
  <div class="kpi"><div class="k">纯成长 w=0（最优口径）</div><div class="v">+19.8%</div><div class="d">quality · 仍是 4 口径里最高</div></div>
  <div class="kpi"><div class="k">纯价值 w=1.0</div><div class="v">+123.7%</div><div class="d">夏普 1.03 · MDD 19.8%</div></div>
  <div class="kpi"><div class="k">最优解（oryoy w=0.9）</div><div class="v">+128.6%</div><div class="d">夏普 1.06 · MDD 19.3%</div></div>
  <div class="kpi"><div class="k">原 q20（quality w=0.8）</div><div class="v">+117.5%</div><div class="d">夏普 1.00 · MDD 20.6%</div></div>
</div>

<div class="card">
  <h2>总收益（5 年累计，%）随 value 权重 w 变化</h2>
  {legend()}
  <svg viewBox="0 0 680 330" style="width:100%;height:auto">
    {line_chart(total_series, "总收益 %", -10, 140, "{:.0f}", [-20, 0, 20, 40, 60, 80, 100, 120, 140])}
  </svg>
  <div class="note">x 轴 w 越大 = 越偏「低估值」；w 越小 = 越偏「成长」。4 条线在 w=1.0 处收敛（评分维度不再参与）。</div>
</div>

<div class="card">
  <h2>最大回撤（MDD，%）随 value 权重 w 变化</h2>
  {legend()}
  <svg viewBox="0 0 680 330" style="width:100%;height:auto">
    {line_chart(mdd_series, "回撤 %", 15, 40, "{:.0f}", [15, 20, 25, 30, 35, 40])}
  </svg>
  <div class="note">越往上回撤越深（越差）。纯成长（w 小）回撤普遍 24%~36%，纯价值（w→1）压到 17%~20%。</div>
</div>

<div class="card">
  <h2>夏普比率随 value 权重 w 变化</h2>
  {legend()}
  <svg viewBox="0 0 680 330" style="width:100%;height:auto">
    {line_chart(sharpe_series, "夏普", -0.1, 1.15, "{:.2f}", [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])}
  </svg>
  <div class="note">夏普从 w=0 的 ~0.1 一路抬升到 w=1 的 1.03，成长因子对风险调整后收益是净拖累。</div>
</div>

<div class="card">
  <h2>全量数据表（每格：总收益 / MDD）</h2>
  <table>
    <thead><tr><th>w<br><span style="font-weight:400">价值权重</span></th>
      <th>原质量分<br>quality</th><th>预期净利增速<br>con_np_yoy</th>
      <th>营收增速<br>oryoy</th><th>净利增速<br>npyoy</th></tr></thead>
    <tbody>{table_rows()}</tbody>
  </table>
</div>

<div class="card">
  <h2>关键洞察</h2>
  <p style="font-size:13px;line-height:1.8">
  <span class="tag">1</span><b>成长方向 5 年内不成立</b>：三种「真成长」口径（营收 oryoy / 净利 npyoy / 预期 con_np_yoy）在 w&lt;0.5 时收益全部 &lt;+45%，远低于纯价值。低 PE 的「便宜」里，高增速票多为周期/基数效应伪成长，成长分位越高反而越差。<br>
  <span class="tag">2</span><b>营收增速是唯一正边际</b>：oryoy 在 w=0.9 处 +128.6%（vs 纯价值 +123.7%），是 4 口径中唯一在「10% 微调」位带来改善的；净利增速 npyoy 同位置反而 -7.6pp。营收端（top-line）比利润端（bottom-line）更适合做 GARP 的 G。<br>
  <span class="tag">3</span><b>原 0.8/0.2 权重非最优</b>：quality w=0.8 得 +117.5%，把权重调到 0.9 就升到 +124.3%——原来那 20% 质量分是在「优中砍优」。<br>
  <span class="tag">4</span><b>风险提示</b>：w=0.9 相对 w=1.0 的 +4.9pp 属样本内边际差异，5 年窗口 + 单一 gate 不足以证明营收因子的稳健性，需样本外（2026-04 之后）持续验证。
  </p>
</div>

</div></body></html>"""

open("_bt_garp_weight_scan_report.html", "w", encoding="utf-8").write(html)
print("报告 → _bt_garp_weight_scan_report.html")
print(f"纯价值 w=1.0: 总 {pure_total:.1f}%  MDD {pure_mdd:.1f}%  夏普 {pure_sharpe:.2f}")
print(f"最优: oryoy w=0.9 总 {res['oryoy']['0.9']['total']*100:.1f}%  "
      f"MDD {res['oryoy']['0.9']['mdd']*100:.1f}%  夏普 {res['oryoy']['0.9']['sharpe']:.2f}")
