# -*- coding: utf-8 -*-
"""光模块 + 半导体 dist52 报告"""
import json

BASE = "C:/Users/xfugm/.workbuddy/workspace/files/199120/04e4ceba-d58a-4c80-b97b-91489245c977/"
d = json.load(open(BASE + "_sector_dist52.json", encoding="utf-8"))
lx_rows = json.load(open(BASE + "_lx_now_dist52.json", encoding="utf-8"))["rows"]
lx_med = sorted(r["dist52"] for r in lx_rows)[len(lx_rows) // 2]

tier_color = {"贴近高点": "#c0392b", "较近": "#e67e22", "中等": "#7f8c8d", "过远": "#27ae60"}
tier_bg = {"贴近高点": "#fdecea", "较近": "#fdf2e9", "中等": "#f4f6f7", "过远": "#eaf7ef"}

def stat_line(s):
    return (f"共 {s['n']} 只 · 中位 dist52 = <b>{s['median']:.2f}</b> · "
            f"贴近高点 {s['贴近高点']} / 较近 {s['较近']} / 中等 {s['中等']} / "
            f"<b style='color:#27ae60'>过远 {s['过远']}</b>")


def table(rows, core_only_note=False):
    trs = []
    for r in rows:
        core = "<b style='color:#c0392b'>★</b>" if r["is_core"] else ""
        pe = "亏损" if (r["pe"] is not None and r["pe"] < 0) else (
            "—" if r["pe"] is None else f"{r['pe']:.1f}")
        lx = ("<span style='color:#c0392b'>PASS</span>" if r["lx_pass"] else
              f"<span style='color:#95a5a6'>{r['lx_stage']}</span>")
        trs.append(f"""<tr style="background:{tier_bg[r['tier']]}">
<td class="mono">{r['code']}</td><td>{core}<b>{r['name']}</b></td>
<td class="mono">{r['price']:.2f}</td><td class="mono">{r['hi52']:.2f}</td>
<td class="mono"><b style="color:{tier_color[r['tier']]}">{r['dist52']:.2f}</b></td>
<td class="mono">{r['dist52']*100-100:.0f}%</td>
<td class="mono">{pe}</td><td class="mono">{r['mv_yi']:.0f}</td><td>{lx}</td></tr>""")
    return ("<tr><th>代码</th><th>名称</th><th>现价</th><th>52周高</th><th>dist52</th>"
            "<th>距高点</th><th>PE(TTM)</th><th>市值亿</th><th>刘旭LX-core</th></tr>"
            + "".join(trs))


opt, semi = d["sector_optical"], d["sector_semi"]
opt_core = [r for r in opt["rows"] if r["is_core"]]
semi_top = [r for r in semi["rows"] if (r["mv_yi"] or 0) >= 800][:25]

html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>光模块 + 半导体 · 距52周高点锚定扫描</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#2c3e50;background:#fff}}
h1{{font-size:22px;border-bottom:3px solid #34495e;padding-bottom:8px}}
h2{{font-size:17px;margin-top:30px}}
h2.red{{color:#c0392b}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{border:1px solid #dfe6e9;padding:4px 7px;text-align:right}}
th{{background:#34495e;color:#fff;font-weight:500}}
td:nth-child(2),th:nth-child(2){{text-align:left}}
.mono{{font-family:Consolas,monospace}}
.box{{background:#f8f9fa;border-left:4px solid #34495e;padding:12px 16px;margin:14px 0;font-size:14px;line-height:1.9}}
.warn{{border-left-color:#c0392b;background:#fdecea}}
.note{{color:#7f8c8d;font-size:12px}}
.grid{{display:flex;gap:14px;flex-wrap:wrap}}
.card{{flex:1;min-width:300px;border:1px solid #dfe6e9;border-radius:6px;padding:12px 16px}}
</style></head><body>
<h1>光模块 + 半导体 · 距52周高点锚定扫描</h1>
<p class="note">成分：光通信概念（聚源产业概念，81只，★=光模块主链核心）+ 申万二级行业半导体（180只）。
行情：腾讯前复权日K + 实时快照，截至 2026-08-21 收盘；刘旭面板 as_of 2026-08-20。全部真实数据。</p>

<div class="box warn">
<b>一句话结论：两个板块整体都在深跌区。</b>光模块中位 dist52 = {opt['stats']['median']:.2f}，
半导体中位 dist52 = {semi['stats']['median']:.2f}——作为对照，刘旭便宜名单的中位 dist52 = {lx_med:.2f}。
按锚定效应的解读（Li &amp; Yu 2012）：价格远离 52 周高点 = 市场对坏消息的<b>过度反应</b>，
此时买入属于"接飞刀"区间（回测中最差信号，-36.9pp）；两个板块均无一只通过刘旭 LX-core 筛选
（全部卡在估值层 L4 / PE≤0）——便宜优先框架在这两个高估值成长板块结构性缺位。
</div>

<div class="grid">
<div class="card"><b>光模块 / 光通信（81只）</b><br>{stat_line(opt['stats'])}<br>
刘旭LX-core 通过：<b>0 只</b></div>
<div class="card"><b>半导体（申万二级，180只）</b><br>{stat_line(semi['stats'])}<br>
刘旭LX-core 通过：<b>0 只</b></div>
</div>

<h2>一、光模块主链核心股（★20只，按 dist52 降序）</h2>
<div class="box">相对最"扛跌"的是源杰科技（光芯片，-19%）和仕佳光子（-24%）；
三大龙头 天孚通信 -27%、新易盛 -29%、<b>中际旭创 -33%</b>；
跌幅最深的是德科立 -49%、亨通光电 -50%、烽火通信 -53%。
板块内<b>没有一只</b>进入"贴近高点/较近"区——最强的源杰科技也只有 0.81。</div>
<table>{table(opt_core)}</table>

<h2>二、半导体：大市值龙头（市值≥800亿，前25，按 dist52 降序）</h2>
<div class="box">最接近高点的是<b>长鑫科技（0.94，-6%）</b>——存储新贵是板块内唯一接近锚的巨头；
思瑞浦 0.83、纳芯微 0.80（模拟芯片）；设备双雄 北方华创 0.74、中微公司 0.72；
中芯国际 0.71（-29%）、寒武纪 0.64（-36%）、海光信息 0.62（-38%）、华虹宏力 0.56（-44%）。
AI 算力主线（寒武纪/海光/澜起）回撤普遍 36-53%，比光模块龙头更深。</div>
<table>{table(semi_top)}</table>

<h2>三、光通信概念全名单（81只，按 dist52 降序）</h2>
<table>{table(opt['rows'])}</table>

<h2>四、半导体全名单（180只，按 dist52 降序）</h2>
<table>{table(semi['rows'])}</table>

<div class="box">
<b>怎么用这份扫描</b>：① 锚定/L3 规避规则视角——两板块中位数都落在"过远"（&lt;0.70），
左侧抄底整体不在规则允许的买点内；若要做右侧确认，应等 dist52 修复回 0.85+（如长鑫科技现在就是板块内唯一站上 0.9 的）。
② 刘旭框架视角——0 只通过不是数据问题，是风格边界：L4 要求 PE≤25 或息率≥2%，
而这两板块即便深跌 30-50%，PE 仍在 50-200 倍。框架在成长板块的正确用法不是选股，而是回答"什么时候轮到我可以买"。
③ 行为金融视角——当前状态正是教材 6.3.2 的"过度反应"阶段：深跌+高估值，外推信念（"还会跌"）与可得性偏差（近期亏损记忆）主导定价。
</div>
<p class="note">PE 为腾讯快照 TTM 口径（亏损=PE≤0）；刘旭 LX-core = 市值≥100亿 + PE&gt;0 + L4(PE≤25或息率≥2%) + L5(预期增速≤25%且0&lt;PEG≤2)。
"无数据"= 2026-08-20 面板缺失（多为近期上市新股）。</p>
</body></html>"""

open(BASE + "_sector_dist52_report.html", "w", encoding="utf-8").write(html)
print("saved _sector_dist52_report.html")
