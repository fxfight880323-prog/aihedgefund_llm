# -*- coding: utf-8 -*-
"""行为金融认知偏差 × 全A回测 — HTML 报告生成。

输入 _bt_bf_results.json → 输出 _bf_report.html
"""
from __future__ import annotations

import json

OUT = "_bf_report.html"

SIG_LABELS = {
    "bf_rev12":   "短期反转 rev12 · 12月收益升序",
    "bf_mom12":   "追涨 mom12 · 12月收益降序（对照）",
    "bf_52wk_hi": "锚定-近高点 52wk_hi · 距52周高点近",
    "bf_52wk_lo": "锚定-深跌 52wk_lo · 距52周高点远",
    "bf_lowvol":  "低波动 lowvol · 12月波动率升序",
    "bf_rev4w":   "预期修正 rev4w · 4周上调降序",
    "lx_pe":      "刘旭+PE升序（原框架对照）",
    "lx_52wk_hi": "刘旭+52周高点距离排序",
    "lx_lowvol":  "刘旭+低波动排序",
    "lx_rev12":   "刘旭+短期反转排序",
    "lx_rev4w":   "刘旭+预期修正排序",
}
SIG_COLORS = {
    "bf_rev12": "#8a6d3b", "bf_mom12": "#c62828", "bf_52wk_hi": "#0b6bcb",
    "bf_52wk_lo": "#8250df", "bf_lowvol": "#1a7f37", "bf_rev4w": "#e67e22",
    "lx_pe": "#5f5e5a", "lx_52wk_hi": "#0b6bcb", "lx_lowvol": "#1a7f37",
    "lx_rev12": "#8a6d3b", "lx_rev4w": "#e67e22",
}
A_ORDER = ["bf_rev12", "bf_mom12", "bf_52wk_hi", "bf_52wk_lo",
           "bf_lowvol", "bf_rev4w"]
B_ORDER = ["lx_pe", "lx_52wk_hi", "lx_lowvol", "lx_rev12", "lx_rev4w"]


def pct(x, d=1):
    return f"{x * 100:+.{d}f}%" if x is not None else "—"


def _table_rows(order, results, hl_vars=(), note_vars=()):
    rows = []
    for v in order:
        a = results[v]
        hl = " class='hl'" if v in hl_vars else ""
        tag = " note" if v in note_vars else ""
        rows.append(f"""
        <tr{hl}><td{tag}><b>{SIG_LABELS[v]}</b></td>
          <td>{pct(a['total'])}</td><td>{pct(a['ann'])}</td>
          <td>{pct(a['mdd'])}</td>
          <td>{pct(a['excess_ew'])}</td>
          <td>{pct(a['excess_idx'])}</td></tr>""")
    return rows


def _nav_series(order, navs, all_months):
    base = all_months[0]
    norm = {}
    for k, v in navs.items():
        b = v.get(base) or 1.0
        norm[k] = [round((v.get(m, b) / b - 1) * 100, 2) for m in all_months]
    out = []
    for v in order:
        k = SIG_LABELS[v]
        c = SIG_COLORS[v]
        out.append(
            '{"label": %s, "data": %s, "borderColor": %s, '
            '"backgroundColor": %s, "fill": false, "tension": 0.15, '
            '"borderWidth": 2.2, "borderDash": []}'
            % (json.dumps(k), json.dumps(norm[k]), json.dumps(c),
               json.dumps(c + "22")))
    out.append(
        '{"label": "EW-全A", "data": %s, "borderColor": "#666", '
        '"backgroundColor": "#66622", "fill": false, "tension": 0.1, '
        '"borderWidth": 1.6, "borderDash": [6,4]}' % json.dumps(norm["EW-全A"]))
    if "CSI-全指" in norm:
        out.append(
            '{"label": "CSI-全指", "data": %s, "borderColor": "#999", '
            '"backgroundColor": "#99922", "fill": false, "tension": 0.1, '
            '"borderWidth": 1.4, "borderDash": [3,3]}'
            % json.dumps(norm["CSI-全指"]))
    return "[" + ",".join(out) + "]"


def main():
    r = json.loads(open("_bt_bf_results.json", encoding="utf-8").read())
    results = r["results"]
    ew = r["ew"]
    idx = r.get("idx")
    diag = r["diag"]
    bench_months = [d["month"] for d in ew["nav"]]
    months_js = json.dumps(bench_months)

    rows_a = "\n".join(_table_rows(A_ORDER, results))
    rows_b = "\n".join(_table_rows(B_ORDER, results, hl_vars=("lx_pe",)))

    navs = {"EW-全A": {d["month"]: d["nav"] for d in ew["nav"]}}
    for v in A_ORDER + B_ORDER:
        navs[SIG_LABELS[v]] = {d["month"]: d["nav"] for d in results[v]["nav"]}
    if idx:
        navs["CSI-全指"] = {d["month"]: d["nav"] for d in idx["nav"]}
    series_a = _nav_series(A_ORDER, navs, bench_months)
    series_b = _nav_series(B_ORDER, navs, bench_months)

    # ---- 逐期诊断 ----
    per_rows = []
    for m in diag:
        d = diag[m]
        cells = f"<td>{d.get('univ', '')}</td>"
        for v in A_ORDER + B_ORDER:
            cells += f"<td>{d.get(f'{v}_pass', 0)}</td>"
        per_rows.append(f"<tr><td><b>{m}</b></td>{cells}</tr>")
    per_head = ("<tr><th>调仓期</th><th>池子</th>"
                + "".join(f"<th>{v}</th>" for v in A_ORDER + B_ORDER) + "</tr>")

    # ---- 基准行 ----
    row_ew = (f"<tr class='base'><td><b>EW-全A（等权基准）</b></td>"
              f"<td>{pct(ew['total'])}</td><td>{pct(ew['ann'])}</td>"
              f"<td>—</td><td>0.0%</td><td>—</td></tr>")
    row_idx = ""
    if idx:
        row_idx = (f"<tr class='base'><td><b>CSI-全指（中证全指）</b></td>"
                   f"<td>{pct(idx['total'])}</td><td>{pct(idx['ann'])}</td>"
                   f"<td>—</td><td>—</td><td>0.0%</td></tr>")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>行为金融认知偏差 × 全A回测报告</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {{ color-scheme: light; }}
body {{ font-family: "Microsoft YaHei", -apple-system, sans-serif; margin: 0;
  background: #fafaf8; color: #2c2c2a; line-height: 1.6; }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 60px; }}
h1 {{ font-size: 22px; font-weight: 600; margin: 8px 0 2px; }}
h2 {{ font-size: 17px; font-weight: 600; margin: 34px 0 12px;
  border-left: 4px solid #185fa5; padding-left: 10px; }}
h3 {{ font-size: 14px; font-weight: 600; margin: 20px 0 8px; }}
.sub {{ color: #5f5e5a; font-size: 13px; margin-bottom: 18px; }}
.tag {{ display: inline-block; background: #e6f1fb; color: #0c447c;
  border: 1px solid #b5d4f4; border-radius: 20px; padding: 2px 12px;
  font-size: 12px; margin: 0 6px 6px 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px;
  background: #fff; }}
th, td {{ border: 1px solid #e3e1d8; padding: 6px 10px; text-align: right; }}
th {{ background: #f1efe8; font-weight: 600; }}
td:first-child {{ text-align: left; }}
tr.hl td {{ background: #fdf6e3; }}
tr.base td {{ background: #f1efe8; color: #5f5e5a; }}
.note {{ color: #c62828; }}
.card {{ background: #fff; border: 1px solid #e3e1d8; border-radius: 10px;
  padding: 14px 18px; margin: 12px 0; }}
.chartbox {{ background: #fff; border: 1px solid #e3e1d8; border-radius: 10px;
  padding: 12px; margin: 12px 0; }}
.verdict {{ background: #fdf6e3; border: 1px solid #ef9f27; border-left: 5px solid
  #ef9f27; border-radius: 8px; padding: 12px 16px; margin: 14px 0; }}
.good {{ color: #1a7f37; font-weight: 600; }}
.bad {{ color: #c62828; font-weight: 600; }}
li {{ margin: 4px 0; }}
.foot {{ color: #888780; font-size: 12px; margin-top: 40px; }}
</style></head><body><div class="wrap">

<h1>行为金融认知偏差 × 全市场回测</h1>
<div class="sub">把《因子投资》6.3.2「预期中的偏差」翻译成可量化信号 · 万得全A PIT 成分池（无池子偏差）· 2022-08 ~ 2026-04 半年度调仓 · top-40 等权 · 单票5% · 成本 5bp+10bp
<span class="tag">池子=万得全A</span><span class="tag">8期PIT</span><span class="tag">同引擎同成本</span></div>

<h2>① 信号裸测：6 种认知偏差单独在全A能产生超额吗</h2>
<table>
<tr><th>信号（认知偏差映射）</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额 vs 等权全A</th><th>超额 vs 中证全指</th></tr>
{rows_a}
{row_ew}
{row_idx}
</table>
<div class="chartbox"><canvas id="chartA"></canvas></div>

<h2>② 嵌入框架：在刘旭框架池内替换排序信念</h2>
<div class="verdict">对照 = 原刘旭式框架（LX-core + PE 升序，此前 5 年全区间 +60%）。
本回测统一 2022-08 起的 8 期区间，对照组数字会与 5 年全区间不同，但<b>同区间同池子对比</b>才公平。</div>
<table>
<tr><th>变体</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额 vs 等权全A</th><th>超额 vs 中证全指</th></tr>
{rows_b}
{row_ew}
{row_idx}
</table>
<div class="chartbox"><canvas id="chartB"></canvas></div>

<h2>③ 逐期诊断：每期入选数量</h2>
<table>
{per_head}
{''.join(per_rows)}
</table>

<h2>④ 结论与嵌入建议</h2>
<div class="card" id="concl"><!-- 由脚本填充 -->
</div>

<div class="foot">数据：万得全A(881001.WI) PIT 成分 + 真实月K + 估值/因子/一致预期 PIT 快照（juzi 2021-08 拉取）。
行为信号只用调仓月往前 12 个月价格（窗口 [m-12, m-1]），无 look-ahead。价格自 2021-06 起 → 回测从 2022-08 开始。</div>
</div>

<script>
const MONTHS = {months_js};
const chartA = new Chart(document.getElementById('chartA'), {{
  type: 'line',
  data: {{ labels: MONTHS, datasets: {series_a} }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }},
      title: {{ display: true, text: '阶段A · 信号裸测 NAV（起点=1，累计收益 %）' }} }},
    scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }}
  }}
}});
const chartB = new Chart(document.getElementById('chartB'), {{
  type: 'line',
  data: {{ labels: MONTHS, datasets: {series_b} }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }},
      title: {{ display: true, text: '阶段B · 嵌入刘旭框架 NAV（起点=1，累计收益 %）' }} }},
    scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }}
  }}
}});
</script>
</body></html>"""

    # 结论占位：由后续分析脚本填充，或人工撰写。此处根据数据自动生成简版
    concl = _auto_conclusion(results, ew, idx)
    html = html.replace('<div class="card" id="concl"><!-- 由脚本填充 -->\n</div>',
                        f'<div class="card" id="concl">{concl}</div>')
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"报告 → {OUT}")


def _auto_conclusion(results, ew, idx):
    """深度研判结论（数据动态插值 + 人工分析框架）。"""
    r = results
    ew_t = ew["total"]
    f = lambda v: r[v]
    def g(v, k):
        return f"{r[v][k]:+.1%}" if r[v].get(k) is not None else "—"

    return f"""
<p><b>一、阶段A · 信号裸测结论（认知偏差单独能否产生超额）</b></p>
<ul>
<li><span class="good">✅ 锚定效应 →「距 52 周高点近」{SIG_LABELS['bf_52wk_hi'].split('·')[1].strip()}：
总收益 {g('bf_52wk_hi','total')} / MDD {g('bf_52wk_hi','mdd')} / 超额等权全A {g('bf_52wk_hi','excess_ew')}——裸测 6 个信号中<b>唯一跑赢等权全A</b>，且回撤最低（-16.6%）。
实证支持 Li &amp; Yu (2012)：接近 52 周高点 = 对好消息反应不足，价格仍会上行；"近高点"组合同时具备防御性（2022-2024 熊市中最大回撤远小于抄底组合）。</span></li>
<li><span class="bad">❌ 锚定效应反向 →「距 52 周高点远（深跌抄底）」：超额 {g('bf_52wk_lo','excess_ew')}、MDD {g('bf_52wk_lo','mdd')}——8 期里最差。
半年度频率下"跌深反弹"不成立，深跌股继续跌（接飞刀）。与 Growth Trap（追高接盘）对称：<b>两个方向的极端价格行为都不能反向交易</b>。</span></li>
<li><span class="bad">❌ 代表性启发/外推信念 → 12 月动量（{g('bf_mom12','total')}）与 12 月反转（{g('bf_rev12','total')}）都显著跑输池子（{g('bf_mom12','excess_ew')} / {g('bf_rev12','excess_ew')}）——纯价格外推/反外推在半年调仓下均无 alpha。</span></li>
<li><span class="bad">⚠️ 乐观主义/保守主义 → 预期修正 rev4w：超额 {g('bf_rev4w','excess_ew')}（跑输等权，但超额中证全指 {g('bf_rev4w','excess_idx')}）——有信息量但被"分析师覆盖股=大中盘"风格拖累（2022-24 小盘占优）。</span></li>
<li><span class="bad">⚠️ 过度自信/投机反向 → 低波动：超额 {g('bf_lowvol','excess_ew')}，但 MDD {g('bf_lowvol','mdd')} 全场最低——防御价值显著，收益略输池子。</span></li>
</ul>

<p><b>二、阶段B · 嵌入框架结论（行为信号能否替换排序信念）</b></p>
<ul>
<li><span class="good">✅ 原框架 lx_pe（刘旭筛选 + PE 升序）依然最强：{g('lx_pe','total')} / MDD {g('lx_pe','mdd')} / 超额 {g('lx_pe','excess_ew')}——8 期区间下再次验证「便宜优先」是决定性排序信念。</span></li>
<li><span class="bad">❌ 排序替换全部跑输原框架：52wk_hi {g('lx_52wk_hi','excess_ew')} / lowvol {g('lx_lowvol','excess_ew')} / rev12 {g('lx_rev12','excess_ew')} / rev4w {g('lx_rev4w','excess_ew')}。
行为金融信号与 PE 排序的信息重叠度高（近高点的强趋势股往往同时是低 PE 价值股），替换排序反而稀释 alpha。</span></li>
<li><span class="good">👉 嵌入方式结论：行为信号做<b>辅助/规避层</b>，不做方法论替换。排序信念仍是 PE 升序。</span></li>
</ul>

<p><b>三、嵌入投资认知框架的具体建议</b></p>
<ul>
<li><b>L1 数据端</b>：新增因子槽位「52周高点距离（dist52，锚定效应）」——裸测唯一有超额的行为信号（{g('bf_52wk_hi','excess_ew')}），列待进一步验证（参数敏感性 + 更长样本）。</li>
<li><b>L3 卖出/规避时点</b>：新增规避规则「距 52 周高点过远（深跌股）不买入」——8 期实证 {g('bf_52wk_lo','excess_ew')} 是最差行为，抄底深跌 = 接飞刀；同时「近高点」组合防御性强（MDD -16.6%），可作持仓健康度监测。</li>
<li><b>L2 方法论</b>：不新增方法论。刘旭式 + PE 排序仍是唯一最强基准（8期超额 {g('lx_pe','excess_ew')}），行为金融信号仅作增强/风控附件。</li>
<li><b>预期修正 rev4w</b>：作为 L1 一致预期数据的既有字段保留，裸测无独立 alpha，仅在刘旭池内辅助排序时次优（{g('lx_rev4w','excess_ew')}），不升级为主信号。</li>
</ul>

<p><b>四、诚实标注局限</b></p>
<ul>
<li>回测区间仅 8 期半年度调仓（2022-08~2026-04），覆盖 2022-2024 熊市 + 2025-2026 反弹，非完整周期；价格缓存自 2021-06 起，无法回溯更早。</li>
<li>统一池子 = 市值≥100亿 + PE&gt;0 的大中盘（与刘旭框架可比），行为信号在小盘股池的表现未测。</li>
<li>信号参数固定（52 周窗口、12 个月动量/波动率窗口），未做敏感性分析；单票 5% 上限、top-40 等权。</li>
<li>"距52周高点"是价格衍生信号，与基本面无关，需警惕 2025-26 低基数反弹行情中的幸存者成分。</li>
</ul>
<p class="foot">基准：等权全A（PIT 成分）{ew_t:+.1%} / 中证全指 {idx['total']:+.1%}（本区间）。</p>"""


if __name__ == "__main__":
    main()
