# -*- coding: utf-8 -*-
"""筹码结构 × 52周高点近距 — AI科技池推荐报告 (HTML)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "_ai_chip_52wk_top.json"), encoding="utf-8"))
TOP = rows[:25]


def fmt_pct(v):
    if v is None:
        return "-"
    cls = "up" if v > 0 else ("down" if v < 0 else "flat")
    return f'<span class="{cls}">{v:+.2f}%</span>'


def fmt_mv(v):
    if v is None:
        return "-"
    return f"{v:.0f}亿"


def fmt_z(v):
    return f"{v:.2f}"


def badge(txt, cls="tech"):
    return f'<span class="badge {cls}">{txt}</span>'


trs = []
for r in TOP:
    sectors = "/".join(r["sectors"][:2]) or "-"
    trs.append(f"""<tr>
      <td class="rk">{r['rank']}</td>
      <td><b>{r['name']}</b><div class="sub">{r['sym']}</div></td>
      <td class="num">{r['px_now'] if r['px_now'] else '-'}</td>
      <td class="num">{fmt_pct(r['pct_now'])}</td>
      <td class="num">{fmt_mv(r['mv_now'] or r['mv'])}</td>
      <td class="num"><b>{r['score']:.3f}</b></td>
      <td class="num">{r['chip_score']:.3f}</td>
      <td class="num">{r['p_dist52']:.3f}</td>
      <td class="num">{r['dist52']:.3f}</td>
      <td class="num">{fmt_z(r['conc'])}</td>
      <td class="num">{fmt_z(r['chip'])}</td>
      <td>{r['industry']}</td>
      <td class="sec">{sectors}</td>
    </tr>""")

groups = [
    ("大盘核心 (总市值 ≥ 200亿)", [r for r in TOP if (r.get("mv_now") or r.get("mv") or 0) >= 200]),
    ("中盘 (50 ~ 200亿)", [r for r in TOP if 50 <= (r.get("mv_now") or r.get("mv") or 0) < 200]),
    ("小盘弹性 (< 50亿)", [r for r in TOP if (r.get("mv_now") or r.get("mv") or 0) < 50]),
]
gl = []
for title, g in groups:
    names = "、".join(f"{x['name']}({x['sym']})" for x in g) or "—"
    gl.append(f'<div class="grp"><div class="grp-t">{title} <span class="cnt">{len(g)}只</span></div><div class="grp-b">{names}</div></div>')

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>筹码结构 × 52周高点近距 — AI科技池推荐 (2026-08-25)</title>
<style>
  body {{ font-family: "Microsoft YaHei", -apple-system, sans-serif; margin: 0; background: #f7f8fa; color: #1f2329; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .meta {{ color: #6b7280; font-size: 12.5px; margin-bottom: 18px; }}
  .cards {{ display: flex; gap: 12px; margin: 18px 0; flex-wrap: wrap; }}
  .card {{ flex: 1; min-width: 200px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; }}
  .card .t {{ font-size: 12px; color: #6b7280; margin-bottom: 6px; }}
  .card .v {{ font-size: 18px; font-weight: 700; }}
  .card .s {{ font-size: 12px; color: #9ca3af; margin-top: 4px; }}
  h2 {{ font-size: 16px; margin: 26px 0 10px; border-left: 4px solid #2563eb; padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); font-size: 13px; }}
  th {{ background: #f3f4f6; text-align: left; padding: 10px 8px; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 8px; border-top: 1px solid #f0f1f3; }}
  tr:hover td {{ background: #fafbfc; }}
  .rk {{ color: #6b7280; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .sub {{ color: #9ca3af; font-size: 11px; }}
  .up {{ color: #e03e2d; font-weight: 600; }}
  .down {{ color: #0a8f3c; font-weight: 600; }}
  .flat {{ color: #6b7280; }}
  .sec {{ color: #4b5563; font-size: 12px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; }}
  .badge.tech {{ background: #e0f2fe; color: #0369a1; }}
  .grp {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }}
  .grp-t {{ font-weight: 600; font-size: 13.5px; margin-bottom: 6px; }}
  .cnt {{ color: #2563eb; font-size: 12px; }}
  .grp-b {{ color: #374151; font-size: 13px; line-height: 1.9; }}
  .note {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 14px 18px; font-size: 12.5px; color: #78350f; line-height: 1.8; margin-top: 18px; }}
  .note b {{ color: #92400e; }}
  .method {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 18px; font-size: 13px; line-height: 1.9; color: #374151; }}
  .method li {{ margin-bottom: 4px; }}
  footer {{ color: #9ca3af; font-size: 11.5px; margin-top: 26px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>筹码结构 × 52周高点近距 — AI科技池推荐</h1>
  <div class="meta">数据日期: 筹码因子 2026-07-31 (申万金工 z-score) · 高点信号 2026-08-21 (月K口径) · 行情 2026-08-25 (腾讯) · 池子: AI产业链 12 概念板块 / 科技行业白名单 664 只</div>

  <div class="cards">
    <div class="card"><div class="t">池内合格样本</div><div class="v">664</div><div class="s">AI科技池 (剔ST/北交所/信号缺失)</div></div>
    <div class="card"><div class="t">综合分 Top1</div><div class="v">罗普特 <span style="font-size:13px">0.977</span></div><div class="s">机构筹码极集中 z=-2.98</div></div>
    <div class="card"><div class="t">创52周新高数</div><div class="v">{sum(1 for r in TOP if r['dist52'] >= 0.999)}</div><div class="s">Top25 中 dist52≥0.999</div></div>
    <div class="card"><div class="t">筹码极集中数</div><div class="v">{sum(1 for r in TOP if r['conc'] <= -2)}</div><div class="s">Top25 中集中度 z≤-2</div></div>
  </div>

  <h2>Top 25 综合排名</h2>
  <table>
    <tr><th>#</th><th>股票</th><th>现价</th><th>今涨跌</th><th>总市值</th><th>综合分</th><th>筹码分</th><th>高点分</th><th>dist52</th><th>集中度z</th><th>合成z</th><th>行业</th><th>概念板块</th></tr>
    {''.join(trs)}
  </table>

  <h2>按市值分组</h2>
  {''.join(gl)}

  <h2>方法论</h2>
  <div class="method">
    <ul>
      <li><b>筹码结构（两项负向因子，值越小越好）</b>：① 机构筹码集中度 — 申万金工最强筹码信号（IC≈-4.4%、IR-0.66），z 越小 = 机构筹码越集中 = 机构锁仓；② 筹码合成 — 集中度成分主导（全A IC≈-5.7%）。池内反向百分位取均值得筹码分。</li>
      <li><b>52周高点近距 dist52</b>：最新月收盘 / 过去12个月最高收盘，越接近 1 越贴近新高，是全A裸测唯一跑赢等权全A(+12.3pp)的行为信号（仅作辅助/规避层）。池内正向百分位得高点分。</li>
      <li><b>综合分 = 50%×筹码分 + 50%×高点分</b>，横截面排序；筹码仅用于<u>行业内/池内个股筛选</u>，不做行业配置。</li>
    </ul>
  </div>

  <div class="note">
    <b>⚠️ 风险与边界</b>：① IC≠alpha — 月频 IC 高不必然等于实盘组合收益，2026-07 曾现极端值污染筹码成本因子；本表为横截面筛选，非收益归因。② 52周高点近距为行为信号，仅作辅助，禁止单独重仓追高。③ 筹码集中逻辑仅限个股层（机构锁仓=好）；<b>行业层集中=拥挤过热（差）</b>，已实测证伪，严禁外推。④ 名单含微盘股（流动性风险），建议结合自身风控。⑤ 本报告由量化信号自动生成，仅供研究参考，<b>不构成投资建议</b>；市场有风险，投资需谨慎。
  </div>

  <footer>生成时间 2026-08-25 · 数据源: 申万宏源金工因子库 / 腾讯行情 · 依据项目回测铁律: 与等权全A对比后再下结论</footer>
</div>
</body>
</html>"""

out = os.path.join(HERE, "_ai_chip_52wk_report.html")
open(out, "w", encoding="utf-8").write(html)
print("报告已生成:", out)
