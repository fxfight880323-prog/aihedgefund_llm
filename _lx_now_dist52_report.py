# -*- coding: utf-8 -*-
"""生成 刘旭框架推荐名单 × 距52周高点 报告"""
import json

import os
BASE = os.path.dirname(os.path.abspath(__file__)) + "/"
rows = json.load(open(BASE + "_lx_now_dist52.json", encoding="utf-8"))["rows"]
sc = json.load(open(BASE + "_lx_now_scored.json", encoding="utf-8"))

# 估值 band 标记（_band_all.json: 5年日频 PE/PB 自身分位）
band = {r["code"]: r for r in json.load(open(BASE + "_band_all.json", encoding="utf-8"))["rows"]}

tier_color = {"贴近高点": "#c0392b", "较近": "#e67e22", "中等": "#7f8c8d", "过远": "#27ae60", "?": "#999"}
tier_bg = {"贴近高点": "#fdecea", "较近": "#fdf2e9", "中等": "#f4f6f7", "过远": "#eaf7ef"}
band_color = {"规避": "#c0392b", "安全边际": "#1e8449", "自身低位": "#2874a6", "偏高": "#b9770e", "中性": "#566573"}

def band_cell(code):
    b = band.get(code)
    if not b or b.get("pb_pct") is None:
        return "<td class='mono'>—</td><td class='note'>—</td>"
    c = band_color.get(b["flag"], "#566573")
    return (f"<td class='mono'>{b['pb_pct']:.0f}%</td>"
            f"<td><span style='color:{c}'>● {b['flag']}</span></td>")

n = {t: sum(1 for r in rows if r["tier"] == t) for t in ["贴近高点", "较近", "中等", "过远"]}
dual = [r for r in rows if (r["score_rank"] or 99) <= 20 and (r["dist52"] or 0) >= 0.85]
conflict = [r for r in rows if (r["score_rank"] or 99) <= 10 and (r["dist52"] or 0) < 0.70]
dual.sort(key=lambda r: -(r["dist52"] or 0))

def fmt(v, suf=""):
    return ("—" if v is None else f"{v}{suf}")

trs = []
for r in rows:
    trs.append(f"""<tr style="background:{tier_bg.get(r['tier'],'#fff')}">
<td class="mono">{r['code']}</td><td><b>{r['name']}</b></td>
<td>{r['layer']}</td><td class="mono">{fmt(r['score_rank'])}</td><td class="mono">{fmt(r['score_total'])}</td>
<td class="mono">{fmt(r['pe'])}</td><td class="mono">{fmt(r['peg'])}</td><td class="mono">{fmt(r['dy'])}</td>
{band_cell(r['code'])}
<td class="mono">{r['price']:.2f}</td><td class="mono">{r['hi52']:.2f}</td>
<td class="mono"><b style="color:{tier_color[r['tier']]}">{r['dist52']:.2f}</b></td>
<td class="mono">{r['off52_pct']:.1f}%</td>
<td><span style="color:{tier_color[r['tier']]}">● {r['tier']}</span></td></tr>""")

dual_trs = "".join(
    f"<tr><td class='mono'>{r['code']}</td><td><b>{r['name']}</b></td>"
    f"<td class='mono'>{r['score_rank']}</td><td class='mono'>{r['score_total']}</td>"
    f"<td class='mono'>{r['pe']}</td><td class='mono'><b style='color:#c0392b'>{r['dist52']:.2f}</b></td>"
    f"<td class='mono'>{r['off52_pct']:.1f}%</td></tr>" for r in dual)

conflict_trs = "".join(
    f"<tr><td class='mono'>{r['code']}</td><td><b>{r['name']}</b></td>"
    f"<td class='mono'>{r['score_rank']}</td><td class='mono'>{r['pe']}</td>"
    f"<td class='mono'><b style='color:#27ae60'>{r['dist52']:.2f}</b></td>"
    f"<td class='mono'>{r['off52_pct']:.1f}%</td></tr>" for r in conflict)

html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>刘旭框架推荐名单 × 距52周高点（锚定检查）</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#2c3e50;background:#fff}}
h1{{font-size:22px;border-bottom:3px solid #34495e;padding-bottom:8px}}
h2{{font-size:17px;margin-top:28px;color:#c0392b}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{border:1px solid #dfe6e9;padding:5px 7px;text-align:right}}
th{{background:#34495e;color:#fff;font-weight:500}}
td:nth-child(2),th:nth-child(2){{text-align:left}}
.mono{{font-family:Consolas,monospace}}
.box{{background:#f8f9fa;border-left:4px solid #34495e;padding:12px 16px;margin:14px 0;font-size:14px;line-height:1.8}}
.warn{{border-left-color:#c0392b;background:#fdecea}}
.note{{color:#7f8c8d;font-size:12px}}
</style></head><body>
<h1>刘旭框架推荐名单 × 距52周高点检查（锚定-近高点）</h1>
<p class="note">名单来源：2026-08-21 筛选（as_of 2026-08-20，全A 5529 → core 226 → top40 + gm层40 + 评分top40 并集）；
行情：腾讯前复权日K，截至 2026-08-21 收盘，真实数据。</p>

<div class="box">
<b>指标定义</b>：<code>dist52 = 当前收盘价 ÷ 过去52周(250个交易日)最高价</code>，恒 ≤ 1。<br>
<b>为什么它重要</b>（Li and Yu 2012，道琼斯指数实证）：投资者把"过去52周高点"当作估值的<b>锚</b>——
价格越贴近这个锚，说明市场对个股好消息的<b>反应越不足</b>，后续补涨概率更高；价格离锚越远、跌得越深，
往往是坏消息被<b>过度反应</b>，抄底=接飞刀。全A回测中，"距52周高点近"是 11 个行为信号里
<b>唯一裸测跑赢等权全A（+12.3pp / 回撤 -16.6%）</b>的信号；对应 L3 规避规则：<b>距52周高点过远（&lt;0.70）不买入</b>。
</div>

<h2>分档分布（{len(rows)} 只）</h2>
<table><tr><th>分档</th><th>dist52 区间</th><th>只数</th><th>含义</th></tr>
<tr style="background:#fdecea"><td>贴近高点</td><td class="mono">≥ 0.95</td><td class="mono">{n['贴近高点']}</td><td>锚定信号最强，反应不足→看多</td></tr>
<tr style="background:#fdf2e9"><td>较近</td><td class="mono">0.85 – 0.95</td><td class="mono">{n['较近']}</td><td>信号偏正面</td></tr>
<tr style="background:#f4f6f7"><td>中等</td><td class="mono">0.70 – 0.85</td><td class="mono">{n['中等']}</td><td>中性</td></tr>
<tr style="background:#eaf7ef"><td>过远</td><td class="mono">&lt; 0.70</td><td class="mono">{n['过远']}</td><td>L3规避规则：不买入（接飞刀风险）</td></tr>
</table>

<h2>双信号交集：评分前20 且 距高点≥0.85（便宜 × 贴近高点）</h2>
<div class="box">这两个信号天然冲突——"便宜优先"选出的深度价值股往往深跌远离高点。同时满足两者的股票是名单中的稀缺品：</div>
<table><tr><th>代码</th><th>名称</th><th>评分排名</th><th>综合评分</th><th>PE</th><th>dist52</th><th>距高点</th></tr>{dual_trs}</table>
<p class="note">共 {len(dual)} 只。</p>

<h2>冲突警示：评分前10 但 距高点&lt;0.70（便宜但深跌）</h2>
<div class="box warn">这些股票在六因子评分里名列前茅，但价格距 52 周高点跌幅超过 30%，属于"便宜但被市场持续抛售"——
按锚定规避规则应<b>降权或不买</b>，等价格重新接近高点（右侧确认）再介入：</div>
<table><tr><th>代码</th><th>名称</th><th>评分排名</th><th>PE</th><th>dist52</th><th>距高点</th></tr>{conflict_trs}</table>

<h2>完整名单（按 dist52 降序，距高点由近到远）</h2>
<table>
<tr><th>代码</th><th>名称</th><th>层级</th><th>评分排名</th><th>综合评分</th><th>PE</th><th>PEG</th><th>息率%</th>
<th>PB分位</th><th>band判定</th><th>现价</th><th>52周高</th><th>dist52</th><th>距高点</th><th>分档</th></tr>
{''.join(trs)}
</table>
<p class="note">band 列：该股 5 年日频 PE/PB 自身历史分位（2021-08~2026-08，PB 为准）。<b style="color:#c0392b">规避</b>=PB 分位&gt;90%（周期顶/泡沫顶风险，横截面便宜但自身历史高位）；<b style="color:#1e8449">安全边际</b>=PE&amp;PB 分位均&lt;30%。</p>

<p class="note">说明：① dist52 用前复权价计算，与回测口径一致；② 52周高点为区间最高价（含盘中），非收盘价口径；
③ 本表是 L1 因子槽位 dist52 在当前名单上的应用演示，"距52周高点近"信号在回测中为裸测正超额、
但作为排序替换时跑输 PE 升序，故仅作辅助/规避层使用，不改变主排序。</p>
</body></html>"""

open(BASE + "_lx_now_dist52_report.html", "w", encoding="utf-8").write(html)
print("saved _lx_now_dist52_report.html")
print("dual:", [(r["name"], r["dist52"]) for r in dual])
print("conflict:", [(r["name"], r["dist52"]) for r in conflict])
