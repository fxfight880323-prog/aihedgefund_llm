"""AI 产业链 × 距52周高点距离(dist52) 排序报告生成。

输入: _ai_52wk_rank.json (全部排序)
输出: AI产业链_距52周高点排序_TOP50.html + AI产业链_距52周高点排序_全部.csv
"""
from __future__ import annotations

import csv
import json
import sys
import datetime

sys.stdout.reconfigure(encoding="utf-8")

OUT_HTML = "AI产业链_距52周高点排序_TOP50.html"
OUT_CSV = "AI产业链_距52周高点排序_全部.csv"
N_SHOW = 50

rows = json.loads(open("_ai_52wk_rank.json", encoding="utf-8").read())
rows = [r for r in rows if r["dist52"] is not None]
print(f"有效 dist52: {len(rows)} 只")

today = datetime.date.today().isoformat()

# ---- CSV 全部 ----
with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["排名", "代码", "名称", "最新价", "当日涨跌%", "总市值(亿)",
                "dist52(距52周高点)", "距52周高点回撤%", "52周最高收盘", "数据月", "细分板块"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, r["code"], r["name"], r["price"], r["pct"], r["mv"],
                    round(r["dist52"], 4), round((r["dd52"] or 0) * 100, 2),
                    r["hi52"], r["month"], "/".join(r["sectors"])])

# ---- HTML Top50 ----
trs = []
for i, r in enumerate(rows[:N_SHOW], 1):
    d52 = r["dist52"]
    pct = r["pct"] or 0
    mv = r["mv"] or 0
    dd = (r["dd52"] or 0) * 100
    bar_w = int(d52 * 100)
    bar_color = "#A32D2D" if d52 >= 0.90 else ("#D85A30" if d52 >= 0.75 else "#888780")
    pct_cls = "up" if pct >= 0 else "down"
    mv_tag = " <span class='mv'>大</span>" if mv >= 100 else ""
    secs = "/".join(r["sectors"][:3])
    trs.append(f"""<tr>
<td class="c">{i}</td>
<td class="mono">{r['code']}</td>
<td class="nm">{r['name']}{mv_tag}</td>
<td class="num">{r['price']:.2f}</td>
<td class="num {pct_cls}">{pct:+.2f}%</td>
<td class="num">{mv:.0f}</td>
<td class="num"><div class="bar"><div class="fill" style="width:{bar_w}%;background:{bar_color}"></div></div><b>{d52:.3f}</b></td>
<td class="num {('up' if dd >= -10 else 'down')}">{dd:+.1f}%</td>
<td class="num mono">{r['hi52']:.2f}</td>
<td class="sec">{secs}</td>
</tr>""")

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>AI 产业链 × 距52周高点排序</title>
<style>
body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;margin:0;background:#f7f7f5;color:#222}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 24px 60px}}
h1{{font-size:22px;font-weight:600;margin:0 0 4px}}
.meta{{color:#666;font-size:13px;margin:8px 0 22px;line-height:1.7}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:22px}}
.card{{background:#fff;border:1px solid #e6e4dc;border-radius:12px;padding:14px 16px}}
.card .k{{font-size:12px;color:#888}}
.card .v{{font-size:22px;font-weight:600;margin-top:4px}}
.card .s{{font-size:12px;color:#666;margin-top:2px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;font-size:13px}}
th{{background:#f1efe8;text-align:left;padding:10px 10px;font-weight:600;font-size:12px;color:#444;border-bottom:1px solid #e6e4dc;white-space:nowrap}}
td{{padding:9px 10px;border-bottom:1px solid #f0eee6;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.c{{color:#888;width:36px}}
.mono{{font-family:Consolas,monospace;font-size:12px}}
.nm{{font-weight:500}}
.up{{color:#A32D2D}}
.down{{color:#0F6E56}}
.mv{{background:#FCEBEB;color:#A32D2D;font-size:10px;padding:1px 5px;border-radius:6px;margin-left:4px;vertical-align:1px}}
.sec{{color:#555;font-size:12px;max-width:150px}}
.bar{{display:inline-block;width:52px;height:6px;background:#f0eee6;border-radius:3px;margin-right:8px;vertical-align:1px}}
.fill{{height:6px;border-radius:3px}}
.note{{background:#fff;border:1px solid #e6e4dc;border-radius:12px;padding:16px 18px;margin-top:22px;font-size:13px;line-height:1.8;color:#333}}
.note b{{color:#111}}
.note .tag{{display:inline-block;background:#E6F1FB;color:#0C447C;border-radius:6px;padding:1px 8px;font-size:12px;margin-right:6px}}
.foot{{color:#999;font-size:12px;margin-top:18px;line-height:1.7}}
</style>
</head>
<body><div class="wrap">
<h1>AI 产业链 × 距52周高点距离 排序榜</h1>
<div class="meta">数据日期 2026-08-21 收盘 · 池子=12 个 AI 产业链概念板块合并去重 {len(rows)} 只 · 口径=腾讯月K(qfq)，dist52 = 最新月收盘 ÷ 过去12个月最高收盘（与回测 bf_52wk_hi 同口径）</div>
<div class="grid">
<div class="card"><div class="k">排序信号</div><div class="v">dist52 降序</div><div class="s">距52周高点越近越靠前（锚定→反应不足）</div></div>
<div class="card"><div class="k">池子规模</div><div class="v">{len(rows)} 只</div><div class="s">人工智能/算力/CPO/AIGC/AI应用/大模型/智能体/语料/AIPC/AI眼镜/华为算力/算力租赁</div></div>
<div class="card"><div class="k">回测依据</div><div class="v">+63% · MDD -16.6%</div><div class="s">bf_52wk_hi 全A裸测唯一跑赢等权全A(+12.3pp)</div></div>
</div>
<table>
<thead><tr>
<th>#</th><th>代码</th><th>名称</th><th>最新价</th><th>当日涨跌</th><th>总市值(亿)</th>
<th>dist52</th><th>距高点回撤</th><th>52周高点</th><th>AI细分板块</th>
</tr></thead>
<tbody>
{''.join(trs)}
</tbody>
</table>
<div class="note">
<b>信号含义</b>：dist52 = 当前价 ÷ 过去52周最高价，越接近 1 说明越"贴着52周高点"。按此降序排列 = 优先买强势股，赌 <span class="tag">锚定效应</span> 造成的反应不足继续修复（Li &amp; Yu 2012：价格离52周高点越近 → 对好消息反应越不足，突破后仍有空间）。
<b>实测</b>：该信号在全A池（2022-08~2026-04，8期）裸测 <b>5年 +63.1%、MDD -16.6%</b>，是行为金融 7 信号中唯一跑赢等权全A的（超额 +12.3pp）；反向"距高点远"（深跌抄底）超额 <b>-36.9pp</b>（接飞刀）。
<b>注意</b>：本榜仅为 dist52 单一排序，<b>不是买卖建议</b>。追高意味着买在趋势半山腰，需要叠加估值(PE)与基本面筛选；距高点过远（dist52 低）的股票按框架 L3 规则应规避，而非抄底。
</div>
<div class="foot">数据：聚源产业概念成分(2026-08-20) · 腾讯月K qfq(2025-07~2026-08) · qt.gtimg.cn 行情快照 · 生成 {today}。52周高点为月度口径(月K收盘最高)，与回测 dist52 一致；当日涨跌/市值来自实时行情。</div>
</div></body></html>"""

open(OUT_HTML, "w", encoding="utf-8").write(html)
print(f"已生成: {OUT_HTML} / {OUT_CSV}")
