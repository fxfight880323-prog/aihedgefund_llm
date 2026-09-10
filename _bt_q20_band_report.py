# -*- coding: utf-8 -*-
"""q20 + PB band 规避层 对照回测报告（自包含 HTML）。"""
import json, sys, os, bisect

sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")
sys.path.insert(0, "D:/workspace/ai_fund_framework")

import _lx_allA_variant as L
import _bt_q20_pareto as P
from _bt_garp_decompose import load_all

d = json.load(open("_bt_q20_band_results.json", encoding="utf-8"))
res = d["results"]
ew = d["ew"]
diag = d["band_diag"]

# 重算被 band90 从 top40 剔除的票（归因）
univ, cons, val, fac, fin, names = load_all()
band = json.load(open("_bt_band_pb_pct.json", encoding="utf-8"))
dropped = []
for month, as_of in L.PIT_DATES:
    members = univ.get(month, [])
    vv, ff, cc = val.get(month, {}), fac.get(month, {}), cons.get(month, {})
    bp = P.screen_q20(month, members, vv, ff, cc)
    bmap = band.get(month, {})
    p40 = sorted(bp, key=lambda s: -s["blend"])[:40]
    for s in p40:
        r = bmap.get(s["tk"])
        if r and r.get("pb_pct") is not None and r["pb_pct"] > 90:
            dropped.append({"month": month, "tk": s["tk"],
                            "name": names.get(s["tk"], s["tk"]),
                            "pe": s["pe"], "pb_pct": r["pb_pct"]})

# 汇总被剔除票（跨期去重）
from collections import Counter, defaultdict
drop_agg = defaultdict(lambda: {"cnt": 0, "pe": [], "pb_pct": [], "months": []})
for x in dropped:
    k = x["tk"]
    drop_agg[k]["cnt"] += 1
    drop_agg[k]["pe"].append(x["pe"])
    drop_agg[k]["pb_pct"].append(x["pb_pct"])
    drop_agg[k]["months"].append(x["month"])
    drop_agg[k]["name"] = x["name"]

def fmt_pct(x):
    return f"{x*100:+.1f}%" if x is not None else "N/A"

def fmt_sharpe(x):
    return f"{x:.2f}" if x is not None else "N/A"

def fmt_calmar(x):
    return f"{x:.2f}" if x is not None else "N/A"

# 构建结果表
rows = []
for label in ["A_top40", "A_top40_band90", "A_top40_band80",
              "AD_top15", "AD_top15_band90", "AD_top15_band80"]:
    r = res[label]
    rows.append((label, r))

# 分组（保留 (label, r) 元组）
g40 = [(l, r) for l, r in rows if l.startswith("A_top40")]
g15 = [(l, r) for l, r in rows if l.startswith("AD_top15")]

# 被剔除票表格
drop_rows = []
for tk, a in sorted(drop_agg.items(), key=lambda x: -x[1]["cnt"]):
    drop_rows.append((tk, a))

def band_cell(tk):
    # 在 band 表里找该票最近的 pb_pct
    return ""

# SVG 柱状图：6 变体总收益对比
def bar_chart(items, title, color_map):
    labels = [l for l, _ in items]
    vals = [v for _, v in items]
    vmax = max(vals)
    vmin = min(vals)
    w = 640
    h = 260
    bar_w = 52
    gap = 24
    n = len(items)
    total_w = n * bar_w + (n - 1) * gap
    x0 = (w - total_w) / 2
    # y 范围
    if vmin < 0:
        ymin = vmin * 1.2
    else:
        ymin = 0
    ymax = vmax * 1.15
    def y(v):
        return h - 40 - (v - ymin) / (ymax - ymin) * (h - 80)
    svg = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<text x="{w/2}" y="20" text-anchor="middle" font-size="14" font-weight="700" fill="#333">{title}</text>')
    # 零线
    y0 = y(0)
    svg.append(f'<line x1="{x0-10}" y1="{y0}" x2="{x0+total_w+10}" y2="{y0}" stroke="#999" stroke-width="1"/>')
    for i, (label, v) in enumerate(items):
        bx = x0 + i * (bar_w + gap)
        bh = abs(y(v) - y0)
        by = min(y(v), y0)
        color = color_map.get(label, "#4a90d9")
        svg.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w}" height="{bh:.1f}" rx="3" fill="{color}"/>')
        svg.append(f'<text x="{bx+bar_w/2:.1f}" y="{by-6:.1f}" text-anchor="middle" font-size="12" font-weight="700" fill="#333">{v:+.1f}%</text>')
        # label 竖排简化：横排小字
        svg.append(f'<text x="{bx+bar_w/2:.1f}" y="{h-16:.1f}" text-anchor="middle" font-size="10" fill="#555">{label}</text>')
    svg.append("</svg>")
    return "".join(svg)

def metrics_chart(items, title):
    # 三个指标并排：总收益 / MDD / 夏普
    labels = [l for l, _ in items]
    totals = [r["total"]*100 for _, r in items]
    mdds = [r["mdd"]*100 for _, r in items]
    sharpes = [(r["sharpe"] or 0) for _, r in items]
    w = 640
    h = 240
    panel_w = 200
    x_off = [10, 220, 430]
    def y(v, vmin, vmax, pad_b=30, pad_t=25):
        return h - pad_b - (v - vmin) / (vmax - vmin) * (h - pad_b - pad_t)
    svg = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<text x="{w/2}" y="18" text-anchor="middle" font-size="14" font-weight="700" fill="#333">{title}</text>')
    panels = [
        ("总收益 %", totals, "#c0392b"),
        ("MDD %", mdds, "#2c3e50"),
        ("夏普", sharpes, "#1a7f37"),
    ]
    for pi, (pname, pvals, pcolor) in enumerate(panels):
        px = x_off[pi]
        vmin = min(pvals)
        vmax = max(pvals)
        if vmax - vmin < 1e-9:
            vmax = vmin + 1
        svg.append(f'<text x="{px+panel_w/2}" y="34" text-anchor="middle" font-size="11" font-weight="600" fill="#555">{pname}</text>')
        bw = 26
        for i, v in enumerate(pvals):
            bx = px + i * 34
            yy = y(v, vmin, vmax)
            svg.append(f'<rect x="{bx:.1f}" y="{yy:.1f}" width="{bw}" height="{h-30-yy:.1f}" rx="2" fill="{pcolor}" opacity="0.85"/>')
            svg.append(f'<text x="{bx+bw/2:.1f}" y="{yy-4:.1f}" text-anchor="middle" font-size="9" fill="#333">{v:.2f}</text>')
    # 底部标签
    for i, label in enumerate(labels):
        for px in x_off:
            pass
    svg.append("</svg>")
    return "".join(svg)

bar40 = bar_chart([(l, r["total"]*100) for l, r in g40], "top40 口径 · 总收益（PB band 层增益）",
                  {"A_top40": "#95a5a6", "A_top40_band90": "#e67e22", "A_top40_band80": "#c0392b"})
bar15 = bar_chart([(l, r["total"]*100) for l, r in g15], "top15 口径 · 总收益（PB band 层）",
                  {"AD_top15": "#95a5a6", "AD_top15_band90": "#e67e22", "AD_top15_band80": "#c0392b"})

# 结论亮点
a40 = res["A_top40"]; a40b90 = res["A_top40_band90"]; a40b80 = res["A_top40_band80"]
a15 = res["AD_top15"]; a15b90 = res["AD_top15_band90"]; a15b80 = res["AD_top15_band80"]
gain90 = a40b90["total"] - a40["total"]
gain80 = a40b80["total"] - a40["total"]

# 被剔除票表格行
drop_html = []
for tk, a in sorted(drop_agg.items(), key=lambda x: -x[1]["cnt"]):
    nm = a["name"]
    pe = a["pe"][-1]
    pb = a["pb_pct"][-1]
    cnt = a["cnt"]
    months = ",".join(m[-5:] for m in a["months"])
    # 归类
    if nm and any(k in nm for k in ["银行", "保险", "金融"]):
        cat = "金融高位"
    elif tk in ("000656.SZ",):
        cat = "PE陷阱(地产暴雷前)"
    elif any(k in (nm or "") for k in ["能源", "高速", "化工", "煤", "电投", "中创"]):
        cat = "周期高位"
    else:
        cat = "其他"
    drop_html.append(f"<tr><td>{tk}</td><td>{nm}</td><td class='r'>{pe:.1f}</td>"
                     f"<td class='r'>{pb:.1f}%</td><td class='c'>{cnt}</td><td>{months}</td><td>{cat}</td></tr>")

# band 每期剔除明细表
diag_rows = []
for label in ["A_top40_band90", "A_top40_band80", "AD_top15_band90", "AD_top15_band80"]:
    dd = diag[label]
    cells = "".join(f"<td class='r'>{dd[m]['n_band_drop']}</td>" for m, _ in L.PIT_DATES)
    tot_drop = sum(dd[m]['n_band_drop'] for m, _ in L.PIT_DATES)
    diag_rows.append(f"<tr><td>{label}</td>{cells}<td class='r'><b>{tot_drop}</b></td></tr>")
month_heads = "".join(f"<th>{m}</th>" for m, _ in L.PIT_DATES)

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>q20 + PB band 规避层 · 对照回测报告</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f6f8; color: #1c2733; line-height: 1.55; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }}
  h1 {{ font-size: 24px; margin: 0 0 6px; }}
  .sub {{ color: #6b7683; font-size: 13px; margin-bottom: 20px; }}
  .concl {{ background: #fff; border-left: 5px solid #c0392b; padding: 18px 20px;
           border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 20px; }}
  .concl h2 {{ margin: 0 0 10px; font-size: 18px; color: #c0392b; }}
  .concl p {{ margin: 6px 0; font-size: 14px; }}
  .card {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
          padding: 20px; margin-bottom: 20px; }}
  .card h2 {{ font-size: 17px; margin: 0 0 14px; color: #1c2733; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #e3e8ee; padding: 7px 9px; text-align: left; }}
  th {{ background: #f0f3f7; font-weight: 600; }}
  .r {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .c {{ text-align: center; }}
  .up {{ color: #c0392b; font-weight: 700; }}
  .down {{ color: #1a7f37; font-weight: 700; }}
  .muted {{ color: #8895a3; font-size: 12px; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px;
         background: #eef1f5; color: #4a5568; margin: 1px 2px; }}
  .tag.cycle {{ background: #fdebd0; color: #b9770e; }}
  .tag.fin {{ background: #e8f0fe; color: #2b6cb0; }}
  .tag.trap {{ background: #fadbd8; color: #c0392b; }}
  .grid {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .grid .card {{ flex: 1 1 460px; }}
  svg {{ display: block; margin: 0 auto; }}
  .foot {{ color: #8895a3; font-size: 12px; margin-top: 24px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>q20 管线 + PB band 规避层 · 对照回测</h1>
  <div class="sub">方法：q20 排序（0.8×PE便宜度 + 0.2×质量）× 可选 mom60 gate × cap8 加权 × 可选 PB band 规避 |
  区间 2021-08 ~ 2026-04（10 期）| 日频 + 复权 | 含成本 5bp+10bp | band 数据源 _bt_band_pb_pct.json（日频 5 年自身分位）</div>

  <div class="concl">
    <h2>结论：band 层在 40 只 Q20 口径上强正贡献（+11~16pp），建议实盘 Q20·质衡优选加 band 规避层</h2>
    <p>① <b>40 只口径（= 实盘 Q20·质衡优选）</b>：PB&gt;90% 规避 → <b class="up">+11.4pp</b>（+118.5% → +129.9%），夏普 0.96→1.03；PB&gt;80% 规避 → <b class="up">+16.5pp</b>（→ +135.0%），夏普 1.05 且 MDD 反而从 15.6% 降到 <b class="up">14.5%</b>（全组最优）。</p>
    <p>② <b>15 只口径（Pareto 最优 AD_top15）</b>：band 层<b>中性偏负</b>（-0.7pp ~ -5.0pp），因为 mom60 gate 已经过滤了"正在跌"的周期顶股，与 band 功能重叠。</p>
    <p>③ 被 band 剔除的票 = <span class="tag cycle">周期高位</span>甘肃能源/电投能源/中原高速 + <span class="tag fin">金融高位</span>江苏银行/中国人保/渝农商行 + <span class="tag trap">PE陷阱</span>金科股份（PE 0.5 但 PB 分位 99.4%，地产暴雷前）。</p>
  </div>

  <div class="grid">
    <div class="card">
      <h2>top40 口径（实盘 Q20·质衡优选）</h2>
      {bar40}
      <table>
        <tr><th>变体</th><th class='r'>总收益</th><th class='r'>年化</th><th class='r'>MDD</th>
            <th class='r'>夏普</th><th class='r'>Calmar</th><th class='r'>超额EW</th></tr>
        <tr><td>A_top40（锚点）</td><td class='r'>{fmt_pct(a40["total"])}</td><td class='r'>{fmt_pct(a40["ann"])}</td>
            <td class='r'>{a40["mdd"]*100:.1f}%</td><td class='r'>{fmt_sharpe(a40["sharpe"])}</td>
            <td class='r'>{fmt_calmar(a40["calmar"])}</td><td class='r'>+81.6pp</td></tr>
        <tr><td>A_top40_band90（PB&gt;90%）</td><td class='r'><b class='up'>{fmt_pct(a40b90["total"])}</b></td><td class='r'>{fmt_pct(a40b90["ann"])}</td>
            <td class='r'>{a40b90["mdd"]*100:.1f}%</td><td class='r'>{fmt_sharpe(a40b90["sharpe"])}</td>
            <td class='r'>{fmt_calmar(a40b90["calmar"])}</td><td class='r'>+93.0pp</td></tr>
        <tr><td>A_top40_band80（PB&gt;80%）</td><td class='r'><b class='up'>{fmt_pct(a40b80["total"])}</b></td><td class='r'>{fmt_pct(a40b80["ann"])}</td>
            <td class='r'><b class='up'>{a40b80["mdd"]*100:.1f}%</b></td><td class='r'>{fmt_sharpe(a40b80["sharpe"])}</td>
            <td class='r'>{fmt_calmar(a40b80["calmar"])}</td><td class='r'>+98.1pp</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>top15 口径（Pareto 最优 AD）</h2>
      {bar15}
      <table>
        <tr><th>变体</th><th class='r'>总收益</th><th class='r'>年化</th><th class='r'>MDD</th>
            <th class='r'>夏普</th><th class='r'>Calmar</th><th class='r'>超额EW</th></tr>
        <tr><td>AD_top15（锚点）</td><td class='r'>{fmt_pct(a15["total"])}</td><td class='r'>{fmt_pct(a15["ann"])}</td>
            <td class='r'>{a15["mdd"]*100:.1f}%</td><td class='r'>{fmt_sharpe(a15["sharpe"])}</td>
            <td class='r'>{fmt_calmar(a15["calmar"])}</td><td class='r'>+80.5pp</td></tr>
        <tr><td>AD_top15_band90</td><td class='r'>{fmt_pct(a15b90["total"])}</td><td class='r'>{fmt_pct(a15b90["ann"])}</td>
            <td class='r'>{a15b90["mdd"]*100:.1f}%</td><td class='r'>{fmt_sharpe(a15b90["sharpe"])}</td>
            <td class='r'>{fmt_calmar(a15b90["calmar"])}</td><td class='r'>+79.9pp</td></tr>
        <tr><td>AD_top15_band80</td><td class='r'>{fmt_pct(a15b80["total"])}</td><td class='r'>{fmt_pct(a15b80["ann"])}</td>
            <td class='r'>{a15b80["mdd"]*100:.1f}%</td><td class='r'>{fmt_sharpe(a15b80["sharpe"])}</td>
            <td class='r'>{fmt_calmar(a15b80["calmar"])}</td><td class='r'>+75.6pp</td></tr>
      </table>
    </div>
  </div>

  <div class="card">
    <h2>band 层每期剔除数量</h2>
    <table>
      <tr><th>变体</th>{month_heads}<th class='r'>累计</th></tr>
      {''.join(diag_rows)}
    </table>
    <p class="muted">注：top40 口径每期池子约 200-370 只，band 剔除后仍有余量补齐 40 只（每期最终持仓均 40 只）；top15 口径 2021-08/2022-04 因 mom60 gate 历史不足 250 交易日而空仓（gate 固有属性，两变体同受影响）。</p>
  </div>

  <div class="card">
    <h2>被 band90 从 top40 剔除的票（归因）</h2>
    <p class="muted">这些票本来会被 q20「PE 便宜度」排进 top40，但 PB 自身 5 年分位 &gt;90%，属于"假便宜"（盈利塌陷/周期顶部导致 PE 失真极低）。</p>
    <table>
      <tr><th>代码</th><th>名称</th><th class='r'>PE</th><th class='r'>PB分位</th><th class='c'>出现期数</th><th>月份</th><th>归类</th></tr>
      {''.join(drop_html)}
    </table>
  </div>

  <div class="card">
    <h2>关键洞察：为什么 band 在 top40 强、在 top15 中性</h2>
    <table>
      <tr><th>维度</th><th>top40（纯 q20 排序）</th><th>top15（q20 + mom60 gate）</th></tr>
      <tr><td>候选筛选</td><td>仅 PE 便宜度 + 质量</td><td>PE 便宜度 + 质量 + 60日趋势 gate</td></tr>
      <tr><td>band 高位票暴露</td><td><b>高</b>——周期顶股 PE 失真极低，被排进前 40</td><td><b>低</b>——周期顶股通常已转跌，被 mom60 gate 提前过滤</td></tr>
      <tr><td>band 层边际价值</td><td><b class='up'>+11~16pp（强正贡献）</b></td><td>-0.7~-5.0pp（中性偏负）</td></tr>
      <tr><td>机制</td><td>band 精准剔除"PE 陷阱"（金科 PE 0.5/PB 99.4%）与周期顶</td><td>band 与 gate 功能重叠，且 15 只太集中，剔除后只能选次优票</td></tr>
    </table>
    <p class="muted">这与历史结论一致：LX-core 管线 band 层 +5.4pp（捕获能源/公用/交运周期高位股）；q20 管线 band 层增益更大（+11~16pp），因为 q20 的 PE 便宜度排序比 LX-core 的纯 PE 升序更容易纳入"盈利塌陷型 PE 陷阱"。</p>
  </div>

  <div class="card">
    <h2>铁律对齐（docs/prompt_template_fund_framework.md）</h2>
    <table>
      <tr><th>#</th><th>铁律</th><th>本实验落实</th></tr>
      <tr><td>1</td><td>真实数据</td><td>band 分位来自日频估值 parquet（非合成）</td></tr>
      <tr><td>2</td><td>池子 = 万得全A PIT</td><td>L.PIT_DATES 10 期 PIT 成分</td></tr>
      <tr><td>3/4</td><td>日频 + 复权</td><td>日频 bar，复权价（load_bars）</td></tr>
      <tr><td>5/8</td><td>同口径基准 + 先对比</td><td>等权 PIT 基准 +36.9%，超额 75~98pp</td></tr>
      <tr><td>6</td><td>零未来函数</td><td>band 窗口 [as_of-5y, as_of]，锚点 ≤ as_of 最近交易日</td></tr>
      <tr><td>9</td><td>MDD 日频标准口径</td><td>日频全序列 (peak-trough)/peak</td></tr>
      <tr><td>10</td><td>金融不剔除</td><td>回测管线含金融，band 只做规避层（金融高位股也被 band 捕获）</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>行动建议</h2>
    <p>① <b>立即</b>：实盘 Q20·质衡优选（40 只）应在下次调仓日 <b>2027-04-30</b> 加 band 规避层（PB 自身 5 年分位 &gt;90% 剔除），预期超额 +11~16pp 且 MDD 不恶化。可选更严的 &gt;80% 阈值（+16.5pp / MDD 14.5%）。</p>
    <p>② <b>不用改</b>：若未来切换到 AD_top15 集中版本，无需 band 层（mom60 gate 已覆盖该功能）。</p>
    <p>③ <b>数据缺口</b>：q20 候选有 202 只票无日频 PB 历史（本实验按"不规避"保守处理，占最终持仓仅 5%）。若需 100% 覆盖，可用 juzi 补拉这 202 只的 5 年日频估值。</p>
  </div>

  <div class="foot">数据源：valuation 表 / _bt_band_pb_pct.json（日频 5 年自身分位）· 生成于 2026-09-08</div>
</div>
</body>
</html>"""

open("_bt_q20_band_report.html", "w", encoding="utf-8").write(html)
print("报告 → _bt_q20_band_report.html")
print(f"  band90 增益: {gain90*100:+.1f}pp | band80 增益: {gain80*100:+.1f}pp")
print(f"  被 band90 剔除的票: {len(dropped)} 条 / {len(drop_agg)} 只去重")
