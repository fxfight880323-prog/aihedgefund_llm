# -*- coding: utf-8 -*-
"""低PE价值风格的稳健性边界报告。

串起三个实验：
  1. 10年单点依赖诊断（Q1分位 vs top40 vs 等权全A）
  2. 剔除极端低PE陷阱（no_trap5/8）
  3. 持仓规模（top40→120）
结论：低PE长期有效；单点依赖是"风格层面"的，内部结构调整三条路全证伪，
     唯一方向是引入正交收益源。
"""
import json

diag = json.load(open("_bt_lowpe_10y_diag.json", encoding="utf-8"))
nt = json.load(open("_bt_garp_notrap_results.json", encoding="utf-8"))
sz = json.load(open("_bt_garp_size_results.json", encoding="utf-8"))

YEARS10 = ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]
YEARS5 = ["2021", "2022", "2023", "2024", "2025", "2026"]


def pct(x):
    return f"{x*100:+.1f}%"


def pp(x):
    return f"{x*100:+.1f}"


CSS = """
<style>
:root { --bg:#f5f6f8; --card:#ffffff; --ink:#1a1d24; --sub:#6b7280;
        --line:#e5e7eb; --red:#c0392b; --green:#1e8449; --blue:#1f5fa8; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
       background:var(--bg); color:var(--ink); padding:32px 20px; line-height:1.65; }
.wrap { max-width:1080px; margin:0 auto; }
h1 { font-size:26px; margin-bottom:6px; }
.sub { color:var(--sub); font-size:14px; margin-bottom:28px; }
h2 { font-size:20px; margin:34px 0 14px; padding-left:10px; border-left:4px solid var(--blue); }
h3 { font-size:16px; margin:20px 0 10px; color:var(--ink); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:20px 22px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
table { border-collapse:collapse; width:100%; font-size:13.5px; margin:10px 0; }
th, td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--line); }
th { background:#fafbfc; font-weight:600; color:var(--sub); white-space:nowrap; }
td:first-child, th:first-child { text-align:left; }
.pos { color:var(--red); font-weight:600; }
.neg { color:var(--green); font-weight:600; }
.hl { background:#fff7ed; }
.concl { background:#eef4fb; border-left:4px solid var(--blue); padding:16px 18px;
         border-radius:8px; margin:14px 0; }
.concl b { color:var(--blue); }
.warn { background:#fdf2f2; border-left:4px solid var(--red); padding:14px 18px;
        border-radius:8px; margin:14px 0; }
.warn b { color:var(--red); }
.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:14px 0; }
.metric { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:16px; text-align:center; }
.metric .v { font-size:24px; font-weight:700; }
.metric .k { font-size:12px; color:var(--sub); margin-top:4px; }
.small { color:var(--sub); font-size:12.5px; }
.tag { display:inline-block; padding:2px 10px; border-radius:20px; font-size:12px;
       margin-right:6px; }
.tag.bad { background:#fdf2f2; color:var(--red); }
.tag.ok { background:#eefaf1; color:var(--green); }
ul { margin:8px 0 8px 22px; }
li { margin:5px 0; }
</style>
"""


def diag_table():
    rows = []
    labels = {"q1": "Q1 低PE(最低20%)", "top40": "top40 极端低PE",
              "ew": "等权全A", "csi": "中证全指"}
    for v in ["q1", "top40", "ew", "csi"]:
        m = diag[v]
        rows.append(f"""
        <tr>
          <td>{labels[v]}</td>
          <td class="pos">{pct(m['total'])}</td>
          <td>{pct(m['ann'])}</td>
          <td>{m['best_year']} {pct(m['best_ret'])}</td>
          <td>{pct(m['ex_best'])}</td>
          <td class="{'neg' if m['ex_best2'] < 0 else 'pos'}">{pct(m['ex_best2'])}</td>
          <td>{m['dep_best']:.2f}</td>
          <td>{m['pos_ratio']*100:.0f}%</td>
        </tr>""")
    return f"""
    <div class="card">
      <h3>各组合 10 年单点依赖度（2017-2026）</h3>
      <table>
        <thead><tr><th>组合</th><th>总收益</th><th>年化</th><th>最好年</th>
        <th>去最好年</th><th>去最好2年</th><th>依赖度</th><th>正收益年占比</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">依赖度 = 1 − 去最好年后收益 ÷ 总收益，越高=越靠单年撑起总收益。
      去最好2年为负 → 组合收益被两个大年撑起，其余年份整体亏钱。</p>
    </div>"""


def matrix10():
    rows = []
    labels = {"q1": "Q1 低PE", "top40": "top40", "ew": "等权全A", "csi": "中证全指"}
    for v in ["q1", "top40", "ew", "csi"]:
        yl = diag[v]["yearly"]
        cells = "".join(
            f"<td class=\"{'pos' if yl[y]>=0 else 'neg'}\">{pp(yl[y])}</td>" for y in YEARS10)
        rows.append(f"<tr><td>{labels[v]}</td>{cells}</tr>")
    return f"""
    <div class="card">
      <h3>10 年逐年收益矩阵（%）</h3>
      <table>
        <thead><tr><th>组合</th>{''.join(f'<th>{y}</th>' for y in YEARS10)}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


def excess10():
    rows = []
    labels = {"q1": "Q1 低PE", "top40": "top40"}
    for v in ["q1", "top40"]:
        ex = diag[v]["excess_vs_ew"]
        cells = "".join(
            f"<td class=\"{'pos' if ex[y]>=0 else 'neg'}\">{pp(ex[y])}</td>" for y in YEARS10)
        rows.append(f"<tr><td>{labels[v]}</td>{cells}</tr>")
    return f"""
    <div class="card">
      <h3>逐年超额 vs 等权全A（pp）</h3>
      <table>
        <thead><tr><th>组合</th>{''.join(f'<th>{y}</th>' for y in YEARS10)}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">Q1 超额集中在价值年(2017 +54.8 / 2021 +15.1)与熊市抗跌(2024 +10.8)，
      成长题材年(2019 −5.8 / 2025 −21.7)回吐 —— 风格 beta 的时序暴露，非稳定横截面选股。</p>
    </div>"""


def notrap_table():
    rows = []
    labels = {"g60": "g60 基线", "no_trap5": "剔PE<5非金融", "no_trap8": "剔PE<8非金融"}
    for v in ["g60", "no_trap5", "no_trap8"]:
        r = nt["results"][v]
        yl = r["yearly"]
        cells = "".join(
            f"<td class=\"{'pos' if yl.get(y,0)>=0 else 'neg'}\">{pp(yl.get(y,0))}</td>"
            for y in YEARS5)
        total_cls = "pos" if r["total"] >= 0 else "neg"
        rows.append(f"<tr><td>{labels[v]}</td>{cells}<td class=\"{total_cls}\">{pct(r['total'])}</td></tr>")
    return f"""
    <div class="card">
      <h3>剔除「极端低PE陷阱」= 负贡献（5年日频+复权）</h3>
      <table>
        <thead><tr><th>变体</th>{''.join(f'<th>{y}</th>' for y in YEARS5)}<th>总收益</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">假设：g60 的 top40 混入 PE&lt;5 地产/周期陷阱，剔除后早期收益应改善。
      实测相反 —— no_trap5 总收益 −6.7pp，且 2023 年从 +3.1% 掉到 −1.6%（踏空中特估行情）。
      说明 garp 门控(PEG≤1)已筛掉 ST/暴雷真陷阱，剩下的 PE&lt;5 非金融是健康价值周期股。</p>
    </div>"""


def size_table():
    rows = []
    for n in ["40", "60", "80", "100", "120"]:
        r = sz["results"][n]
        hl = ' class="hl"' if n == "40" else ""
        rows.append(f"""
        <tr{hl}>
          <td>top{n}</td>
          <td class="pos">{pct(r['total'])}</td>
          <td>{r['mdd']*100:.1f}%</td>
          <td>{r['dep']:.2f}</td>
        </tr>""")
    return f"""
    <div class="card">
      <h3>扩大持仓 = 稀释 alpha，且摊不平单点（5年日频+复权）</h3>
      <table>
        <thead><tr><th>持仓规模</th><th>总收益</th><th>MDD</th><th>单点依赖度</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">top40→top120 收益从 +67.0% 单调降到 +42.5%（−24.5pp），
      但依赖度纹丝不动(0.62→0.60)。因为 2024 金融修复年是「低PE价值风格」整体的大年，
      无论持 40 只还是 120 只都吃满 —— 单点依赖在风格层，不在个股层。</p>
    </div>"""


def main():
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>低PE价值风格的稳健性边界</title>{CSS}</head>
<body><div class="wrap">

<h1>低PE价值风格的稳健性边界</h1>
<div class="sub">单点依赖诊断 + 内部结构调整三连证伪 · 日频+复权口径 · 2026-09-02</div>

<div class="concl"><b>一句话结论：</b>银行金融的低PE收益<b>长期有效</b>（10年 Q1 低PE
<span class="pos">+264%</span> vs 等权全A +108%，前5年超额更大）。但它的单点依赖
（2024 金融修复年）是<b>「低PE价值风格」本身的时序暴露</b>，不是个股或结构问题 ——
剔除陷阱、扩大持仓、降金融浓度三条内部调整路全部证伪。唯一方向是<b>引入正交收益源</b>。</div>

<h2>一、10年单点依赖诊断</h2>
{diag_table()}
{excess10()}
{matrix10()}

<h2>二、内部结构调整三连证伪</h2>
<div class="warn"><b>证伪的直觉：</b>「g60 的 top40 结构（极端低PE + 高金融浓度）造成单点依赖，
只要调整结构就能摊平」—— 三条路全走不通：</div>
{notrap_table()}
{size_table()}

<div class="card">
  <h3>第三条（已证伪）：降金融浓度 / 行业分散</h3>
  <table>
    <thead><tr><th>金融/期</th><th>总收益</th><th>MDD</th></tr></thead>
    <tbody>
      <tr class="hl"><td>20（g60基线）</td><td class="pos">+67.01%</td><td>16.67%</td></tr>
      <tr><td>10</td><td class="pos">+55.26%</td><td>19.70%</td></tr>
      <tr><td>0（剔除）</td><td class="pos">+37.30%</td><td>21.43%</td></tr>
    </tbody>
  </table>
  <p class="small">金融砍得越多收益越低、回撤越高（详见 21 号笔记）。
  剔金融后席位被基础建设/房地产/煤炭等同样低PE价值周期股接走 —— 换汤不换药，还更差。</p>
</div>

<h2>三、为什么内部调整都无效</h2>
<div class="card">
  <ul>
    <li><b>门控已筛真陷阱</b>：g60 的 PEG≤1 门控已把 ST/暴雷/负增长股筛掉，
        剩下的 PE&lt;5 非金融（地产/基建/煤炭）是「有正预期的健康价值周期股」，
        它们 2021/2023 贡献正收益，剔除反而踏空。</li>
    <li><b>alpha 来自排序纯度</b>：低PE 的超额集中在「最便宜」的一端，
        top40 纯度最高，扩大持仓引入「不那么便宜」的股票只会稀释 alpha。</li>
    <li><b>单点依赖在风格层</b>：2024 金融修复年是「低PE大盘价值」整个风格的 beta，
        与持 40 只还是 120 只无关。这不是选股结构能解决的风险，是风格暴露的固有属性。</li>
  </ul>
</div>

<h2>四、正确方向：正交收益源</h2>
<div class="concl">
  既然单点依赖是「低PE价值风格」的固有 beta，正确的对冲不是调整价值股内部结构，
  而是<b>引入与价值风格正交的独立 alpha 源</b>，按已有验证的优先级：
  <ul>
    <li>① <b>申万「行业轮动」因子</b>（+12.6%/年，IC 全景中唯一独立收益源）</li>
    <li>② <b>q20 质量微调</b>（0.8×PE便宜度 + 0.2×质量分，已验证 +3.40pp）</li>
    <li>③ <b>市值加权 + cap8~10</b>（集中度换收益，逐年稳健，非单点）</li>
  </ul>
  本质：价值底仓提供长期防御性 beta，正交源提供成长/题材年的反周期 alpha，
  两者组合才能在保留 2024 修复收益的同时平滑 2021-2023 的真空期。
</div>

<div class="small" style="margin-top:24px;">
  数据：<code>_bt_lowpe_10y_diag.json</code>（10年诊断）· <code>_bt_garp_notrap_results.json</code>（剔陷阱）
  · <code>_bt_garp_size_results.json</code>（持仓规模）。锚点：g60 = +67.01% 精确复现。<br>
  口径：10年=月频前复权无成本（方向性结论）；5年=日频复权含成本5bp+10bp。
</div>

</div></body></html>"""

    with open("_bt_lowpe_robust_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("报告 → _bt_lowpe_robust_report.html")


if __name__ == "__main__":
    main()
