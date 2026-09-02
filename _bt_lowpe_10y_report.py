# -*- coding: utf-8 -*-
"""低PE因子10年稳健性检验 — HTML 报告。"""
import json
import datetime

D = json.load(open("_bt_lowpe_10y_results.json", encoding="utf-8"))
R = D["results"]
EXC = D["q1_vs_ew_excess"]
LS = D["longshort_q1q5"]
SEG = D["segments"]
FC = D["fin_conc"]
FST = D["fin_split_top40"]
TC = D["trap_check"]
CAL = D["calib"]

years = sorted({y for k in R for y in R[k]["yearly"]})
order = ["q1", "q2", "q3", "q4", "q5", "top40", "ew", "csi"]
labels = {
    "q1": "Q1 低PE(最低20%)", "q2": "Q2 次低PE", "q3": "Q3 中PE",
    "q4": "Q4 次高PE", "q5": "Q5 高PE(最高20%)", "top40": "top40 极端低PE",
    "ew": "等权全A", "csi": "中证全指",
}


def pct(x, plus=True):
    s = f"{x*100:+.1f}%" if plus else f"{x*100:.1f}%"
    return s


def color(x):
    # 涨红跌绿（A股习惯）
    return "#c0392b" if x >= 0 else "#1a7a3c"


# 逐年收益矩阵
matrix_rows = ""
for k in order:
    r = R[k]
    tds = ""
    for y in years:
        v = r["yearly"].get(y, 0)
        tds += f'<td style="color:{color(v)}">{pct(v)}</td>'
    matrix_rows += (f'<tr><td class="lbl">{labels[k]}</td>{tds}'
                    f'<td class="total" style="color:{color(r["total"])}">{pct(r["total"])}</td></tr>')

# Q1 vs 等权 逐年超额 bar
max_exc = max(abs(v) for v in EXC.values()) or 1
exc_bars = ""
for y in years:
    v = EXC.get(y, 0)
    w = abs(v) / max_exc * 100
    bar_color = color(v)
    exc_bars += (f'<div class="bar-row"><span class="bar-year">{y}</span>'
                 f'<span class="bar-track"><span class="bar-fill" style="width:{w:.0f}%;background:{bar_color}"></span></span>'
                 f'<span class="bar-val" style="color:{bar_color}">{v*100:+.1f}pp</span></div>')

# Q1-Q5 多空
ls_bars = ""
for y in sorted(LS):
    v = LS[y]
    bar_color = color(v)
    ls_bars += (f'<div class="bar-row"><span class="bar-year">{y}</span>'
                f'<span class="bar-track"><span class="bar-fill" style="width:{min(abs(v)/40*100,100):.0f}%;background:{bar_color}"></span></span>'
                f'<span class="bar-val" style="color:{bar_color}">{v*100:+.1f}pp</span></div>')

# 分段对比表
seg_rows = ""
for k in order:
    s = SEG[k]
    a = s["2016-2020"]
    b = s["2021-2026"]
    a_s = pct(a) if a is not None else "—"
    b_s = pct(b) if b is not None else "—"
    seg_rows += (f'<tr><td class="lbl">{labels[k]}</td>'
                 f'<td style="color:{color(a or 0)}">{a_s}</td>'
                 f'<td style="color:{color(b or 0)}">{b_s}</td></tr>')

# 金融浓度趋势
fc_rows = ""
for m in sorted(FC):
    f = FC[m]
    fc_rows += (f'<tr><td class="lbl">{m}</td>'
                f'<td>{f["top40_fin"]*100:.0f}%</td>'
                f'<td>{f["q1_fin"]*100:.0f}%</td></tr>')

# top40 金融 vs 非金融 分段收益
fst_rows = ""
for seg in FST:
    fin = seg["fin_ret"]
    nf = seg["nonfin_ret"]
    fin_s = pct(fin) if fin is not None else "—"
    nf_s = pct(nf) if nf is not None else "—"
    a0 = seg["a0"][:7]
    a1 = seg["a1"][:7]
    fst_rows += (f'<tr><td class="lbl">{a0}~{a1}</td>'
                 f'<td style="color:{color(fin or 0)}">{fin_s}<span class="n">(n={seg["fin_n"]})</span></td>'
                 f'<td style="color:{color(nf or 0)}">{nf_s}<span class="n">(n={seg["nonfin_n"]})</span></td></tr>')

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>低PE因子10年稳健性检验（2016-2026）</title>
<style>
  :root {{ --red:#c0392b; --green:#1a7a3c; --bg:#f5f6f8; --card:#fff; --ink:#1f2329; --sub:#6b7280; --line:#e5e7eb; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--ink); margin:0; padding:24px; line-height:1.6; }}
  .wrap {{ max-width:1080px; margin:0 auto; }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  .sub {{ color:var(--sub); font-size:13px; margin-bottom:20px; }}
  h2 {{ font-size:18px; margin:28px 0 12px; border-left:4px solid #c0392b; padding-left:10px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin-bottom:16px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; text-align:center; }}
  .kpi .num {{ font-size:26px; font-weight:700; }}
  .kpi .lbl {{ font-size:12px; color:var(--sub); margin-top:4px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th,td {{ padding:7px 10px; text-align:center; border-bottom:1px solid var(--line); }}
  th {{ background:#fafafa; font-weight:600; color:#374151; }}
  td.lbl {{ text-align:left; font-weight:500; white-space:nowrap; }}
  td.total {{ font-weight:700; }}
  td .n {{ color:var(--sub); font-size:11px; margin-left:3px; }}
  .bar-row {{ display:flex; align-items:center; gap:8px; margin:4px 0; font-size:13px; }}
  .bar-year {{ width:48px; color:var(--sub); flex-shrink:0; }}
  .bar-track {{ flex:1; background:#f0f1f3; border-radius:4px; height:18px; overflow:hidden; }}
  .bar-fill {{ display:block; height:100%; border-radius:4px; }}
  .bar-val {{ width:80px; text-align:right; font-weight:600; flex-shrink:0; }}
  .concl {{ background:#fef6f0; border:1px solid #f5d0b8; border-radius:10px; padding:16px 20px; margin-bottom:16px; }}
  .concl b {{ color:#b03a1e; }}
  .note {{ background:#fffbe6; border:1px solid #f0e3a8; border-radius:10px; padding:14px 18px; font-size:13px; color:#6b5d1e; }}
  .note b {{ color:#8a6d1a; }}
  .tag {{ display:inline-block; font-size:11px; padding:2px 8px; border-radius:4px; margin-right:4px; }}
  .tag.red {{ background:#fdecea; color:#c0392b; }}
  .tag.green {{ background:#e8f5ee; color:#1a7a3c; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>低PE因子10年稳健性检验 <span class="tag red">2016-08 ~ 2026-04</span></h1>
  <div class="sub">回答：「银行金融低估值PE的收益，是时代给予（2021后价值回归），还是长期有效？」| 前复权月K · 半年调仓 · 等权 · 无成本 · 万得全A PIT成分</div>

  <div class="concl">
    <b>结论：低PE因子的收益是「长期有效」的，不是「时代给予」的。</b><br>
    低PE分位(Q1) 10年累计 <b>+264.4%</b>，是等权全A(+108.3%)的 2.4 倍、中证全指(+44.1%)的 6 倍。超额并非来自 2021 后的价值回归——<b>前5年(2016-2020)超额 +58.3pp，反而大于后5年(2021-2026)的 +6.0pp</b>。低PE是「防御性价值」alpha：在价值回归年(2017/2021)与熊市(2018/2022/2024)持续跑赢，只在极致成长题材年(2019/2025)回吐。
  </div>

  <div class="kpis">
    <div class="kpi"><div class="num" style="color:#c0392b">+264.4%</div><div class="lbl">低PE分位 Q1 10年累计</div></div>
    <div class="kpi"><div class="num" style="color:#c0392b">+156pp</div><div class="lbl">Q1 超额等权全A</div></div>
    <div class="kpi"><div class="num">+58.3pp</div><div class="lbl">前5年超额(2016-2020)</div></div>
    <div class="kpi"><div class="num">+6.0pp</div><div class="lbl">后5年超额(2021-2026)</div></div>
  </div>

  <h2>一、逐年收益矩阵（10年）</h2>
  <div class="card">
    <table>
      <thead><tr><th style="text-align:left">组合</th>{''.join(f'<th>{y}</th>' for y in years)}<th>10年累计</th></tr></thead>
      <tbody>{matrix_rows}</tbody>
    </table>
  </div>

  <h2>二、Q1（低PE）相对等权全A的逐年超额</h2>
  <div class="card">
    <p style="margin-top:0;font-size:13px;color:var(--sub)">红柱=低PE跑赢，绿柱=低PE跑输。超额集中在价值回归年(2017/2021)与熊市(2018/2022/2024)，回吐于成长题材年(2019/2025)。</p>
    {exc_bars}
  </div>

  <h2>三、低PE − 高PE 多空收益（因子有效性）</h2>
  <div class="card">
    <p style="margin-top:0;font-size:13px;color:var(--sub)">Q1 − Q5 多空：10年中有 7 年为正，证明低PE是长期因子，不是单点红利。</p>
    {ls_bars}
  </div>

  <h2>四、前5年 vs 后5年分段对比</h2>
  <div class="card">
    <table>
      <thead><tr><th style="text-align:left">组合</th><th>前5年(2016-2020)</th><th>后5年(2021-2026)</th></tr></thead>
      <tbody>{seg_rows}</tbody>
    </table>
    <p style="font-size:13px;color:var(--sub)">注意：等权全A 的前5年(+20.3%)与后5年(+86.5%)差距巨大，说明2021后是普涨行情；低PE在前5年(弱市)反而提供了更大的相对超额。</p>
  </div>

  <h2>五、价值陷阱检验：「越低越好」不成立</h2>
  <div class="card">
    <table>
      <thead><tr><th style="text-align:left">组合</th><th>10年累计</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td class="lbl">top40（PE最低40只）</td><td style="color:#1a7a3c">+55.7%</td><td style="text-align:left">极端低PE=ST/暴雷/一次性收益，价值陷阱，跑输等权</td></tr>
        <tr><td class="lbl">Q1（低PE最低20%）</td><td style="color:#c0392b">+264.3%</td><td style="text-align:left">含陷阱，仍大幅跑赢</td></tr>
        <tr><td class="lbl">Q1 剔除 top40（健康低PE）</td><td style="color:#c0392b">+282.4%</td><td style="text-align:left">剔除最极端40只陷阱后，收益反而更高</td></tr>
        <tr><td class="lbl">Q2（次低PE 20%）</td><td style="color:#c0392b">+129.5%</td><td style="text-align:left">次低PE同样跑赢等权</td></tr>
      </tbody>
    </table>
    <p style="font-size:13px;color:var(--sub)">有效的是「适度低估值」（PE 5-15倍的银行/周期/地产），不是「极端低PE」。这正是 g60 需要 garp 门控(PEG≤1)的原因——筛掉价值陷阱。</p>
  </div>

  <h2>六、银行金融的角色</h2>
  <div class="card">
    <p style="margin-top:0;font-size:13px;color:var(--sub)">top40 里金融浓度从 2016 年 40% 升至 2025 年 78%（地产/周期暴雷后 PE 崩塌退出，银行成为低PE主力）。银行是低PE最纯、最稳的载体。</p>
    <table style="max-width:420px">
      <thead><tr><th style="text-align:left">调仓期</th><th>top40金融占比</th><th>Q1金融占比</th></tr></thead>
      <tbody>{fc_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2 style="margin-top:0">top40 内：金融 vs 非金融 分段收益</h2>
    <p style="font-size:13px;color:var(--sub)">金融(银行)在多数时段跑赢非金融（非金融=价值陷阱，波动大）。</p>
    <table style="max-width:620px">
      <thead><tr><th style="text-align:left">时段</th><th>金融</th><th>非金融</th></tr></thead>
      <tbody>{fst_rows}</tbody>
    </table>
  </div>

  <h2>七、口径诚实标注</h2>
  <div class="note">
    <b>本报告口径边界（引用须注意）：</b><br>
    ① 价格=前复权月K(qfqmonth)、月末撮合，非日频 T+1；绝对收益与 g60 日频口径不可直接互推。<br>
    ② 无交易成本、等权；分位多空是横截面相对比较，对成本/撮合不敏感，<b>方向性结论稳健</b>。<br>
    ③ 校准：top40月频5年 +34.8% vs g60日频5年 +67.0%，差 -32.2pp <b>主要来自选股差异（纯PE升序 vs garp门控+mv≥100亿）</b>，非口径偏差。<br>
    ④ 幸存者偏差：310只北交所股票无月K（均为2021后上市小盘，对低PE分位影响可忽略）；静态金融名单(123只)标记。<br>
    ⑤ 低PE的alpha是「风格beta的时序暴露」——它在价值/防御年系统性兑现，在成长题材年系统性回吐，<b>不是稳定的横截面选股能力</b>（与申万估值因子月频全市场IC≈0一致）。
  </div>

  <p class="sub" style="margin-top:20px">生成于 {datetime.datetime.now().isoformat()[:19]} · 数据源：juzi估值面板(PE/PB) + juzi万得全A PIT成分 + 腾讯前复权月K · 脚本 _bt_lowpe_10y.py</p>
</div>
</body>
</html>"""

open("_bt_lowpe_10y_report.html", "w", encoding="utf-8").write(html)
print("报告已生成: _bt_lowpe_10y_report.html")
