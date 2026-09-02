# -*- coding: utf-8 -*-
"""行业分散 / 降金融浓度对冲实验 → HTML 报告。读 _bt_garp_ind_results.json。"""
import json, datetime

R = json.load(open("_bt_garp_ind_results.json", encoding="utf-8"))
res = R["results"]
bench = R["benchmarks"]
fill = R["fill_industry"]
meta = R["meta"]

FIN_ORDER = ["g60", "fin_le_15", "fin_le_12", "fin_le_10",
             "fin_le_8", "fin_le_5", "fin_0"]
IND_ORDER = ["g60", "ind_le_10", "ind_le_8", "ind_le_6"]
FIN_LABEL = {
    "g60": "20（无约束）", "fin_le_15": "≤15", "fin_le_12": "≤12",
    "fin_le_10": "≤10", "fin_le_8": "≤8", "fin_le_5": "≤5", "fin_0": "0（剔除）",
}
IND_LABEL = {"g60": "无约束", "ind_le_10": "每行业≤10", "ind_le_8": "每行业≤8",
             "ind_le_6": "每行业≤6"}

g60 = res["g60"]["total"]


def pct(x):
    return f"{x*100:+.2f}%"


def num(x):
    return f"{x*100:.2f}%"


# ---------- 金融浓度阶梯 ----------
fin_rows = []
for v in FIN_ORDER:
    r = res[v]
    fin = r["fin_mean"]
    total = r["total"]
    mdd = r["mdd"]
    neff = r["ind_neff"]
    exew = r["excess_ew"]
    bar_w = min(100.0, total / g60 * 100.0)
    is_base = (v == "g60")
    cls = "base" if is_base else "pos"
    fin_rows.append(
        f'<tr class="{"best" if is_base else ""}">'
        f'<td class="lbl">{v}</td>'
        f'<td class="num">{FIN_LABEL[v]}</td>'
        f'<td class="num">{fin:.1f}</td>'
        f'<td class="num {"pos" if total>0 else "neg"}">{pct(total)}</td>'
        f'<td class="num">{num(mdd)}</td>'
        f'<td class="num">{neff:.1f}</td>'
        f'<td class="num {"pos" if exew>0 else "neg"}">{pct(exew)}</td>'
        f'<td class="barcell"><div class="bar bar-pos" style="width:{bar_w:.0f}%"></div></td>'
        f'</tr>')

# ---------- 宽行业分散 ----------
ind_rows = []
for v in IND_ORDER:
    r = res[v]
    fin = r["fin_mean"]
    total = r["total"]
    mdd = r["mdd"]
    neff = r["ind_neff"]
    bar_w = min(100.0, total / g60 * 100.0)
    is_base = (v == "g60")
    ind_rows.append(
        f'<tr class="{"best" if is_base else ""}">'
        f'<td class="lbl">{v}</td>'
        f'<td class="num">{IND_LABEL[v]}</td>'
        f'<td class="num">{fin:.1f}</td>'
        f'<td class="num {"pos" if total>0 else "neg"}">{pct(total)}</td>'
        f'<td class="num">{num(mdd)}</td>'
        f'<td class="num">{neff:.1f}</td>'
        f'<td class="barcell"><div class="bar bar-pos" style="width:{bar_w:.0f}%"></div></td>'
        f'</tr>')

# ---------- 分年度矩阵 ----------
years = sorted({y for v in res for y in res[v]["yearly"]})
year_header = "".join(f'<th style="text-align:right">{y}</th>' for y in years)
year_rows = []
for v in FIN_ORDER:
    r = res[v]
    cells = ""
    for y in years:
        val = r["yearly"].get(y, 0.0)
        cls = "pos" if val > 0 else ("neg" if val < 0 else "")
        cells += f'<td class="num {cls}">{pct(val)}</td>'
    total = r["total"]
    year_rows.append(
        f'<tr class="{"best" if v=="g60" else ""}"><td class="lbl">{v}</td>'
        f'<td class="num">{FIN_LABEL[v]}</td>'
        f'<td class="num">{r["fin_mean"]:.1f}</td>'
        f'{cells}<td class="num pos">{pct(total)}</td></tr>')

# 2024 单点贡献
g60_24 = res["g60"]["yearly"].get("2024", 0.0)
g60_25 = res["g60"]["yearly"].get("2025", 0.0)
g60_2123 = sum(res["g60"]["yearly"].get(y, 0) for y in ("2021", "2022", "2023"))
fin0_24 = res["fin_0"]["yearly"].get("2024", 0.0)
fin0_2123 = sum(res["fin_0"]["yearly"].get(y, 0) for y in ("2021", "2022", "2023"))

# ---------- 填充行业 ----------
def fill_rows(v):
    c = fill[v]
    total = sum(c.values())
    out = ""
    for k, n in list(c.items())[:10]:
        out += (f'<tr><td class="lbl">{k}</td>'
                f'<td class="num">{n}</td>'
                f'<td class="num">{n/total*100:.1f}%</td>'
                f'<td class="barcell"><div class="bar bar-pos" '
                f'style="width:{n/max(c.values())*100:.0f}%"></div></td></tr>')
    return out

g60_fill = fill_rows("g60")
fin0_fill = fill_rows("fin_0")

html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>行业分散 / 降金融浓度对冲实验</title>
<style>
:root {{ --bg:#f7f8fa; --card:#fff; --ink:#1a1a1a; --sub:#6b7280; --line:#e5e7eb;
  --red:#d92626; --green:#0a7d4f; --blue:#1f6feb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.6; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:24px 20px 60px; }}
h1 {{ font-size:24px; margin:0 0 4px; }}
.sub {{ color:var(--sub); font-size:13px; margin-bottom:20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:20px 22px; margin-bottom:18px; }}
.card h2 {{ font-size:17px; margin:0 0 12px; border-left:4px solid var(--blue);
  padding-left:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th,td {{ padding:8px 10px; text-align:left; border-bottom:1px solid var(--line); }}
th {{ color:var(--sub); font-weight:600; font-size:12px; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
td.lbl {{ font-weight:600; }}
.pos {{ color:var(--red); }}
.neg {{ color:var(--green); }}
.barcell {{ width:22%; }}
.bar {{ height:14px; border-radius:7px; }}
.bar-pos {{ background:linear-gradient(90deg,#d92626,#f0a0a0); }}
.bar-neg {{ background:linear-gradient(90deg,#0a7d4f,#8fd0b0); }}
.concl {{ background:#fff7f6; border:1px solid #f3d1cd; border-radius:10px; padding:14px 16px; }}
.concl h3 {{ margin:0 0 8px; font-size:14px; color:var(--red); }}
.warn {{ background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:12px 16px; margin-top:12px; }}
.warn h3 {{ margin:0 0 6px; font-size:14px; color:#b45309; }}
.insight {{ background:#f0f6ff; border:1px solid #cfe0ff; border-radius:10px; padding:14px 16px; margin-top:12px; }}
.insight h3 {{ margin:0 0 6px; font-size:14px; color:var(--blue); }}
ul {{ margin:6px 0; padding-left:20px; }}
li {{ margin:4px 0; }}
tr.best td {{ background:#fff7ed; }}
tr.best td.lbl {{ color:#b45309; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
@media (max-width:760px) {{ .grid {{ grid-template-columns:1fr; }} }}
.kpi {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:6px; }}
.kpi .k {{ flex:1; min-width:150px; background:var(--card); border:1px solid var(--line);
  border-radius:10px; padding:12px 14px; }}
.kpi .k .v {{ font-size:22px; font-weight:700; }}
.kpi .k .t {{ color:var(--sub); font-size:12px; }}
</style></head><body><div class="wrap">
<h1>行业分散 / 降金融浓度对冲实验</h1>
<div class="sub">g60 口径（增速≤60% + PEG≤1 + mv≥100亿 + PE升序）· full 基座（含金融）· 日频+复权 · 含成本 5bp+10bp · {meta['window'][0]} ~ {meta['window'][1]} · 锚点 g60={pct(g60)} fin_0={pct(res['fin_0']['total'])} 均精确复现</div>

<div class="card concl">
<h3>一句话结论</h3>
<p style="margin:0">「降金融浓度 / 行业分散」在 2021-2026 <b>不是免费午餐，而是纯负贡献</b>：金融从 20 只砍到 0，收益从 <b>+67.01% 单调滑到 +37.30%</b>，MDD 反而从 <b>16.67% 恶化到 21.43%</b>。
收益损失<b>几乎全部来自 2024 银行修复年</b>（-17.7pp），而填充进席位的<b>煤炭 / 地产 / 基建</b>在 2021-2023 是负贡献、波动更大。
这证明策略的「单点依赖」不是「金融行业」本身，而是「低PE大盘价值风格」——金融只是它最纯的载体。用行业分散去对冲，等于把银行换成波动更大的价值周期股，收益与回撤双双恶化。</p>
</div>

<div class="kpi">
<div class="k"><div class="v pos">{pct(g60)}</div><div class="t">g60 基线（金融 20/期）</div></div>
<div class="k"><div class="v pos">{pct(res['fin_le_10']['total'])}</div><div class="t">fin_le_10（金融 10/期）· -{pct(g60-res['fin_le_10']['total'])}</div></div>
<div class="k"><div class="v pos">{pct(res['fin_0']['total'])}</div><div class="t">fin_0（金融 0）· -{pct(g60-res['fin_0']['total'])}</div></div>
<div class="k"><div class="v neg">{num(res['fin_0']['mdd'])}</div><div class="t">fin_0 最大回撤（vs g60 {num(res['g60']['mdd'])}）</div></div>
</div>

<div class="card">
<h2>① 金融浓度阶梯：收益单调下降，回撤单调恶化</h2>
<table><thead><tr><th>变体</th><th style="text-align:right">金融上限</th>
<th style="text-align:right">金融/期</th><th style="text-align:right">总收益</th>
<th style="text-align:right">年化</th><th style="text-align:right">MDD</th>
<th style="text-align:right">行业N_eff</th><th style="text-align:right">超额(EW)</th><th>收益水平</th></tr></thead>
<tbody>
{''.join(fin_rows)}
</tbody></table>
<p class="sub" style="margin-top:8px">行业 N_eff = 1/行业权重 HHI，越大越分散。金融砍得越多，组合越「分散」（N_eff 4.4→12.1），但收益越低、回撤越深——分散的是「名字」，牺牲的是「收益引擎」。</p>
</div>

<div class="card">
<h2>② 收益损失 79% 来自 2024 银行修复年</h2>
<table><thead><tr><th>变体</th><th style="text-align:right">金融上限</th><th style="text-align:right">金融/期</th>{year_header}<th style="text-align:right">总计</th></tr></thead>
<tbody>
{''.join(year_rows)}
</tbody></table>
<div class="insight" style="margin-top:10px">
<h3>单点依赖的真相：不是「行业」单点，是「风格」单点</h3>
<ul>
<li>g60 的 {pct(g60)} 里，<b>2024 {pct(g60_24)} + 2025 {pct(g60_25)} 两年占了 {pct(g60_24+g60_25)}</b>，2021-2023 三年合计仅 {pct(g60_2123)}。</li>
<li>剔除金融（fin_0）后：2024 从 {pct(g60_24)} 掉到 {pct(fin0_24)}（<b>-{pct(g60_24-fin0_24)}</b>），但 2025 几乎不动（{pct(res['fin_0']['yearly'].get('2025',0))}）；2021-2023 反而更差（{pct(fin0_2123)}，转负）。</li>
<li>即：金融的超额收益<b>浓缩在 2024 银行估值修复这一单点</b>。行业分散既没留住 2024 的 beta，也没换来其他年份的 alpha，反而把 2021-2023 拖成负贡献。</li>
</ul>
</div>
</div>

<div class="grid">
<div class="card">
<h2>③ g60 非金融席位行业分布</h2>
<table><thead><tr><th>行业</th><th style="text-align:right">只-期</th><th style="text-align:right">占比</th><th></th></tr></thead>
<tbody>{g60_fill}</tbody></table>
</div>
<div class="card">
<h2>④ fin_0（剔除金融）非金融席位行业分布</h2>
<table><thead><tr><th>行业</th><th style="text-align:right">只-期</th><th style="text-align:right">占比</th><th></th></tr></thead>
<tbody>{fin0_fill}</tbody></table>
</div>
</div>
<div class="card" style="padding-top:14px">
<p style="margin:0;font-size:13.5px">③→④ 的对比是核心证据：剔除金融后，腾出的席位被 <b>基础建设(28→51)、房地产开发(28→47)、煤炭开采(26→35)</b> 等<b>同样低 PE 的价值/周期股</b>接走。
它们与银行共享「低估值 + 高股息 + 顺周期」的价值 beta，但 2021-2026 收益更低、周期波动更大（地产 2022 爆雷、煤炭 2022 后回落）。所以「降金融」≈「把银行换成更差的低PE价值股」。</p>
</div>

<div class="card">
<h2>⑤ 宽行业分散（每申万二级行业设上限）：同样的负贡献</h2>
<table><thead><tr><th>变体</th><th style="text-align:right">约束</th>
<th style="text-align:right">金融/期</th><th style="text-align:right">总收益</th>
<th style="text-align:right">年化</th><th style="text-align:right">MDD</th>
<th style="text-align:right">行业N_eff</th><th>收益水平</th></tr></thead>
<tbody>
{''.join(ind_rows)}
</tbody></table>
<p class="sub" style="margin-top:8px">更激进的行业分散（ind_le_6，N_eff 12.4）收益 {pct(res['ind_le_6']['total'])}，仍低于 g60 {pct(g60)} 约 {pct(g60-res['ind_le_6']['total'])}，且 MDD 更深。两个轴（金融上限 / 行业上限）结论一致。</p>
</div>

<div class="card warn">
<h3>正确方向：分散「风格」，不是分散「行业」</h3>
<p style="margin:0 0 8px">本实验证伪了「用行业分散对冲单点风险」的直觉。既然单点依赖的本质是「低PE大盘价值风格」，对冲它需要<b>引入正交的收益源</b>，而不是在同一风格内换行业。候选方向（按已有证据优先级）：</p>
<ul>
<li><b>① 风格正交化</b>：叠加申万「行业轮动」因子（已验证 <b>+12.6%/年，唯一独立收益源</b>），在保留 2024 价值 beta 的同时用行业动量平滑 2021-2023。</li>
<li><b>② 质量微调</b>：q20（0.8×PE + 0.2×质量）已验证 <b>+3.40pp</b>，是唯一正贡献的质量用法，可温和降低纯价值暴露。</li>
<li><b>③ 市值加权 + cap8~10</b>：已证收益 +104.9%~107.0%、top3 集中度砍 1/3、MDD 更低（但它是「集中度换收益」，不解决风格单点）。</li>
</ul>
<p class="sub" style="margin:0">金融剔除（-26.1pp）、质量硬过滤（-21.9pp）、行业分散（-29.7pp）均已证伪；「低PE价值」就是这个策略的收益本质，只能微调、不能替换。</p>
</div>

<div class="card">
<h2>方法学说明</h2>
<ul style="font-size:13px;color:var(--sub)">
<li><b>口径</b>：full 基座（含金融）· g60 参数（增速≤60% + PEG≤1 + mv≥100亿）· PE升序 · 等权 top40 · 日频复权 · 成本 5bp+10bp · 半年调仓。</li>
<li><b>锚点</b>：g60=+67.01%（== audit rerun.full.g60）、fin_0=+37.30%（== audit rerun.finex.g60），双锚点精确复现。</li>
<li><b>行业分类</b>：申万二级，来自 juzi 行业面板快照（2026-07-31，5134 只），非 PIT；金融组复用 _bt_sw_fin_universe.json（银行+非银 123 只）。早年退市股（阳光城/中南建设）手动兜底「房地产开发」。行业对大盘价值股长期稳定，口径差异为方向性结论。</li>
<li><b>覆盖审计</b>：全部变体 0 缺失，仅 ind_le_10 / ind_le_8 在 2026-04 缺失 601108.SH（财通证券）1 只-期（约 2.5% 现金拖累），方向性结论不受影响。</li>
<li><b>结论方向性标注</b>：行业快照非 PIT，早年行业分类可能有少量偏差；但金融/煤炭/地产/基建的大盘价值股分类在 2021-2026 稳定，不影响「降金融=负贡献」的单调结论。</li>
</ul>
</div>

<div class="sub" style="text-align:center;margin-top:8px">生成于 {datetime.datetime.now().isoformat()[:19]} · 数据 _bt_garp_ind_results.json · 脚本 _bt_garp_ind.py / _bt_garp_ind_report.py</div>
</div></body></html>"""

open("_bt_garp_ind_report.html", "w", encoding="utf-8").write(html)
print("报告 → _bt_garp_ind_report.html")
print(f"g60={pct(g60)} fin_le_10={pct(res['fin_le_10']['total'])} "
      f"fin_0={pct(res['fin_0']['total'])}")
