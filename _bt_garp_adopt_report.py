"""garp 门控采纳落地报告 — 回测最优解 → 当前名单正式生效
对比旧 L5(增速≤25%+PEG≤2) vs 新 L5-garp(增速≤60%+PEG≤1)
"""
import json, html, sys
sys.stdout.reconfigure(encoding='utf-8')

def esc(s):
    return html.escape(str(s)) if s not in (None, '') else '—'

# ---------- 数据 ----------
new_res = json.load(open('_lx_now_results.json', encoding='utf-8'))
final = json.load(open('_lx_now_final.json', encoding='utf-8'))
old_q = json.load(open('_bt_qrelax_now.json', encoding='utf-8'))
bt = json.load(open('_bt_garp_results.json', encoding='utf-8'))

stats = new_res['stats']
new_all = new_res['all']
new_pool = {r['code']: r for r in new_all}
old_base = {r['code']: r for r in old_q['base']}

new_top40 = new_all[:40]
new_codes = {r['code'] for r in new_top40}
old_codes = set(old_base)
kept = old_codes & new_codes
added = new_codes - old_codes
dropped = old_codes - new_codes

# 被踢出股票的 PEG（从 consensus 原始数据）
cons = json.load(open('_bt_lx_now_consensus.json', encoding='utf-8'))['records']
peg_map = {}
for r in cons:
    if r.get('stock_code') not in peg_map:
        peg_map[r['stock_code']] = (r.get('con_peg'), r.get('con_np_yoy'))

# 回测指标
def bt_row(v):
    x = bt['results'][v]
    return (x['total'], x['ann'], x['mdd'])

# 分年度
def yearly(v):
    nav = bt['results'][v]['nav']
    years = {}
    for pt in nav:
        years.setdefault(pt['date'][:4], []).append(pt['nav'])
    out = {}
    for y in sorted(years):
        seg = years[y]
        if len(seg) >= 2:
            out[y] = (seg[-1] / seg[0] - 1) * 100
    return out

base_y, garp_y = yearly('core_finex'), yearly('garp')
years_all = sorted(set(base_y) | set(garp_y))

# ---------- HTML ----------
def band_badge(flag):
    colors = {'安全边际': '#1e8449', '自身低位': '#2874a6', '中性': '#566573', '偏高': '#b9770e', '规避': '#c0392b'}
    c = colors.get(str(flag), '#566573')
    return f'<span style="background:{c};color:#fff;padding:2px 7px;border-radius:10px;font-size:11px">{esc(flag)}</span>'

final_rows = ''.join(
    f'<tr>'
    f'<td>{r.get("score_rank","—")}</td>'
    f'<td class="l"><b>{esc(r["name"])}</b></td>'
    f'<td class="mono">{esc(r["code"])}</td>'
    f'<td>{r.get("price","—")}</td>'
    f'<td>{r.get("mv_yi","—"):,.0f}</td>'
    f'<td class="pe"><b>{r.get("pe","—")}</b></td>'
    f'<td>{r.get("exp_g","—")}</td>'
    f'<td>{r.get("peg","—")}</td>'
    f'<td>{r.get("con_roe","—")}</td>'
    f'<td>{r.get("gpm","—")}</td>'
    f'<td>{r.get("score_total","—")}</td>'
    f'<td>{r.get("pb_pct","—") if r.get("pb_pct") is not None else "—"}</td>'
    f'<td>{band_badge(r.get("band_flag",""))}</td>'
    f'</tr>' for r in sorted(final['final'], key=lambda x: x.get('score_rank', 99))
)

# 新增（garp 回池）
added_rows = ''.join(
    f'<tr>'
    f'<td class="mono">{esc(r["code"])}</td>'
    f'<td class="l">{esc(r["name"])}</td>'
    f'<td class="pe">{r.get("pe","—")}</td>'
    f'<td>{r.get("exp_g","—")}</td>'
    f'<td>{r.get("peg","—")}</td>'
    f'<td>{r.get("con_roe","—")}</td>'
    f'<td>{r.get("gpm","—")}</td>'
    f'</tr>' for r in sorted([new_pool[c] for c in added], key=lambda x: x['pe'])
)

# 被踢出（PEG∈(1,2] 低增速）
drop_rows = ''.join(
    f'<tr>'
    f'<td class="mono">{esc(c)}</td>'
    f'<td class="l">{esc(old_base[c]["name"])}</td>'
    f'<td class="pe">{old_base[c].get("pe","—")}</td>'
    f'<td>{esc(peg_map.get(c, (None,None))[1])}</td>'
    f'<td><b style="color:#c0392b">{esc(round(peg_map.get(c,(0,0))[0],2))}</b></td>'
    f'<td>{old_base[c].get("con_roe","—")}</td>'
    f'</tr>' for c in sorted(dropped, key=lambda x: old_base[x]['pe'])
)

# 分年度表格
yr_rows = ''.join(
    f'<tr><td class="l">{y}</td>'
    f'<td>{base_y.get(y,0):+.1f}%</td>'
    f'<td>{garp_y.get(y,0):+.1f}%</td>'
    f'<td style="color:{("#1e8449" if garp_y.get(y,0)>base_y.get(y,0) else "#c0392b")}">{garp_y.get(y,0)-base_y.get(y,0):+.1f}pp</td></tr>'
    for y in years_all
)

bt_rows = ''.join(
    f'<tr><td class="l">{label}</td><td>{desc}</td>'
    f'<td class="pe">{t*100:+.1f}%</td><td>{a*100:+.2f}%</td><td>{m*100:.1f}%</td>'
    f'<td>{"✅" if v in ("garp",) else ""}{"⚠️" if v in ("g40","garp_q20") else ""}{"❌" if v in ("g60","g99","peg_sort","garp_q50") else ""}</td></tr>'
    for v, label, desc in [
        ('core_finex', '基线 core_finex', '增速≤25% + PEG≤2（旧 L5）'),
        ('g40', 'g40', '增速≤40% + PEG≤2'),
        ('garp', 'garp ★ 已采纳', '增速≤60% + PEG≤1'),
        ('g60', 'g60', '增速≤60% + PEG≤2'),
        ('g99', 'g99', '增速≤99%（≈不限）'),
        ('peg_sort', 'peg_sort', 'PEG 升序排序'),
        ('garp_q20', 'garp_q20', 'garp + 80%PE+20%质量'),
        ('garp_q50', 'garp_q50', 'garp + 50%PE+50%质量'),
    ] for t, a, m in [bt_row(v)]
)

zj_rank = next((i+1 for i, r in enumerate(new_all) if '601899' in r['code']), None)
zj = next((r for r in new_all if '601899' in r['code']), None)
fy_in_pool = any('600660' in r['code'] for r in new_all)

html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>garp 门控采纳落地报告</title>
<style>
  body {{ font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; margin: 0; background: #f5f6fa; color: #2c3e50; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }}
  h1 {{ font-size: 24px; margin: 8px 0 4px; }}
  h2 {{ font-size: 18px; margin: 32px 0 12px; border-left: 4px solid #2980b9; padding-left: 10px; }}
  .sub {{ color: #7f8c8d; font-size: 13px; margin-bottom: 20px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .badge {{ display: inline-block; background: #27ae60; color: #fff; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin-right: 6px; }}
  .badge.blue {{ background: #2980b9; }}
  .badge.red {{ background: #c0392b; }}
  .badge.amber {{ background: #b9770e; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th {{ background: #2c3e50; color: #fff; padding: 8px 10px; text-align: center; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #ecf0f1; text-align: center; }}
  tr:hover td {{ background: #f8f9fa; }}
  td.l {{ text-align: left; }}
  td.mono {{ font-family: Consolas, monospace; font-size: 12px; color: #555; }}
  td.pe {{ font-weight: 700; color: #c0392b; }}
  .kpi {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 16px 0; }}
  .kpi-box {{ flex: 1; min-width: 150px; background: #fff; border-radius: 10px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.06); text-align: center; }}
  .kpi-box .n {{ font-size: 22px; font-weight: 700; color: #2980b9; }}
  .kpi-box .t {{ font-size: 12px; color: #7f8c8d; margin-top: 4px; }}
  .callout {{ background: #eaf7ef; border-left: 4px solid #27ae60; padding: 12px 16px; border-radius: 0 8px 8px 0; font-size: 13px; margin: 12px 0; }}
  .callout.red {{ background: #fdecea; border-color: #c0392b; }}
  .callout.amber {{ background: #fef5e7; border-color: #b9770e; }}
  .mini {{ font-size: 12px; color: #7f8c8d; }}
  .flex2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 800px) {{ .flex2 {{ grid-template-columns: 1fr; }} }}
</style></head><body><div class="wrap">

<h1>garp 门控采纳落地报告</h1>
<div class="sub">数据截至 2026-08-24 ｜ 回测区间 2021-08 ~ 2026-06（日频+复权，万得全A PIT 成分）｜ 2026-08-26 正式切换</div>

<div class="kpi">
  <div class="kpi-box"><div class="n">+34.57%</div><div class="t">garp 回测总收益（旧 L5 +29.45%）</div></div>
  <div class="kpi-box"><div class="n" style="color:#27ae60">18.54%</div><div class="t">garp 最大回撤（旧 L5 22.12%）</div></div>
  <div class="kpi-box"><div class="n">+5.12pp</div><div class="t">超额收益（vs 旧门控）</div></div>
  <div class="kpi-box"><div class="n" style="color:#8e44ad">182</div><div class="t">新池 core_pass（旧 226）</div></div>
  <div class="kpi-box"><div class="n" style="color:#c0392b">62.5%</div><div class="t">top40 换手（保留 15/换 25）</div></div>
</div>

<h2>① 回测验证：为什么 garp 是 8 变体最优</h2>
<div class="card">
<table>
<tr><th>变体</th><th>门控参数</th><th>总收益</th><th>年化</th><th>MDD</th><th>裁决</th></tr>
{bt_rows}
</table>
<div class="callout">✅ <b>garp = 收益+风险双维最优</b>：总收益 +34.57%（最高）、MDD 18.54%（第二低）。机制：增速可以高到 60%，但 <b>PEG≤1</b> 强制估值匹配，过滤掉"高增速高估值"和"低增速高 PEG"两类陷阱。完全放开（g99）或 PEG 排序（peg_sort）都大幅退化——PE 升序信念不可动摇。</div>
</div>

<h2>② 分年度稳健性：超额来自熊市防御，非风格押注</h2>
<div class="card">
<table>
<tr><th>年度</th><th>旧 L5（core_finex）</th><th>garp</th><th>差值</th></tr>
{yr_rows}
</table>
<div class="callout">garp 的最大增量在 <b>2022 熊市少亏 6.2pp</b>（-0.1% vs -6.3%）和 2023 震荡市少亏 1.8pp——PEG≤1 提前避开了高估低质股；2021 煤炭大牛年反而略输（-0.4pp），说明超额不是靠押中资源股风格，而是风控红利，可持续性更强。</div>
</div>

<h2>③ 当前名单变化（2026-08-24 生效）</h2>
<div class="card">
<table>
<tr><th>维度</th><th>旧 L5（增速≤25%+PEG≤2）</th><th>新 L5-garp（增速≤60%+PEG≤1）</th></tr>
<tr><td class="l">core 池</td><td>226 只</td><td><b>182 只</b>（-44）</td></tr>
<tr><td class="l">池子构成</td><td>低增速便宜股为主</td><td>低增速+PEG≤1 + 高增速资源股回池</td></tr>
<tr><td class="l">top40 换手</td><td>—</td><td>保留 15 / 新增 25 / 踢出 25</td></tr>
<tr><td class="l">紫金矿业</td><td>L5 门控剔除（增速 58%）</td><td><b>进池</b>，排 47/182（PE 13.6，top40 截止 13.0，差 7 名）</td></tr>
<tr><td class="l">福耀玻璃</td><td>过全部条件但排序 132/226</td><td><b>被踢出池</b>（PEG 1.3 &gt; 1）</td></tr>
</table>
</div>

<div class="flex2">
<div class="card">
<h2 style="margin-top:0">🆕 新增 25 只（garp 回池，增速 25-60% + PEG≤1）</h2>
<table>
<tr><th>代码</th><th>名称</th><th>PE</th><th>增速%</th><th>PEG</th><th>ROE%</th><th>毛利%</th></tr>
{added_rows}
</table>
<div class="mini">清一色"紫金同类"：有色（明泰铝业/腾远钴业/南山铝业/新集能源）、运输（圆通/招商南油）、化工（宝丰/芭田/新奥）、重卡（江铃/山推/中国重汽）——正是被旧增速门控误杀的类别。</div>
</div>

<div class="card">
<h2 style="margin-top:0">❌ 踢出 25 只（PEG ∈ (1,2] 低增速）</h2>
<table>
<tr><th>代码</th><th>名称</th><th>PE</th><th>增速%</th><th>PEG</th><th>ROE%</th></tr>
{drop_rows}
</table>
<div class="mini">共同特征：增速 ≤8.4% 甚至负增长（格力 3.6%、海尔 3.5%、TCL智家 -0.9%、物产中大 2.0%），PEG 1.16-1.97——"低增速但估值不便宜"，被 PEG≤1 硬门槛剔除。回测证实这批是拖累项。</div>
</div>
</div>

<h2>④ 最终推荐名单（40 只，评分 top40 + band 层，等权 2.5%）</h2>
<div class="card">
<table>
<tr><th>名次</th><th>名称</th><th>代码</th><th>价</th><th>市值亿</th><th>PE</th><th>增速%</th><th>PEG</th><th>ROE%</th><th>毛利%</th><th>评分</th><th>PB分位</th><th>Band</th></tr>
{final_rows}
</table>
<div class="callout red">⚠️ 名单变化须知：<b>格力电器、海尔智家、TCL智家、中原传媒、华润双鹤</b>等旧名单白马被踢出（PEG&gt;1）；新增以高增速资源/制造为主。这是回测验证过的正确方向（garp +5.12pp），但持仓风格从"纯低估值白马"转向"低估值+成长匹配"。若对某只被踢股票有执念（如格力），可作白名单单独评估，不进框架。</div>
</div>

<div class="callout amber">📌 <b>落地方式</b>：`_lx_now_screen.py` 第 25-26 行门控参数已改为 `EXP_G_CEIL=60.0, PEG_CEIL=1.0`（注释同步更新）；筛选→评分→band→apply 全管线已用新门控重跑并生成 `_lx_now_final.json`。回测脚本 `_bt_garp.py` 为可复现实验。</div>

</div></body></html>"""

with open('_bt_garp_adopt_report.html', 'w', encoding='utf-8') as f:
    f.write(html_doc)
print('OK -> _bt_garp_adopt_report.html')
print(f'保留 {len(kept)} | 新增 {len(added)} | 踢出 {len(dropped)} | 紫金 rank {zj_rank}')
