# -*- coding: utf-8 -*-
"""q20 排序 × 市值加权(cap) 组合实验报告。

承接 23 号「低PE价值风格稳健性边界」结论：单点依赖在风格层，内部调整全证伪，
唯一方向是引入正交收益源。本报告把其中两个已验证的方向（q20 + cap）落到 full 基座
组合验证，回答：组合能否既提收益、又填平 2021-2023 真空期。
"""
import json

D = json.load(open("_bt_q20_cap_results.json", encoding="utf-8"))
R = D["results"]
YEARS = ["2021", "2022", "2023", "2024", "2025", "2026"]

ORDER = ["g60_pe_ew", "q20_ew", "q20_cap8", "q20_cap10", "q20_cap15", "pe_cap10"]
LABELS = {
    "g60_pe_ew": "g60 基线（PE升序·等权）",
    "q20_ew": "q20 排序·等权",
    "q20_cap8": "q20 排序·市值加权 cap8",
    "q20_cap10": "q20 排序·市值加权 cap10",
    "q20_cap15": "q20 排序·市值加权 cap15",
    "pe_cap10": "PE升序·市值加权 cap10",
}


def pct(x):
    return f"{x*100:+.1f}%"


CSS = """
<style>
:root { --bg:#f5f6f8; --card:#fff; --ink:#1a1d24; --sub:#6b7280;
        --line:#e5e7eb; --red:#c0392b; --green:#1e8449; --blue:#1f5fa8; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
       background:var(--bg); color:var(--ink); padding:32px 20px; line-height:1.65; }
.wrap { max-width:1080px; margin:0 auto; }
h1 { font-size:26px; margin-bottom:6px; }
.sub { color:var(--sub); font-size:14px; margin-bottom:28px; }
h2 { font-size:20px; margin:34px 0 14px; padding-left:10px; border-left:4px solid var(--blue); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:20px 22px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
table { border-collapse:collapse; width:100%; font-size:13.5px; margin:10px 0; }
th, td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--line); }
th { background:#fafbfc; font-weight:600; color:var(--sub); white-space:nowrap; }
td:first-child, th:first-child { text-align:left; }
.pos { color:var(--red); font-weight:600; }
.neg { color:var(--green); font-weight:600; }
.hl { background:#fff7ed; }
.best { background:#eefaf1; }
.concl { background:#eef4fb; border-left:4px solid var(--blue); padding:16px 18px;
         border-radius:8px; margin:14px 0; }
.concl b { color:var(--blue); }
.warn { background:#fdf2f2; border-left:4px solid var(--red); padding:14px 18px;
        border-radius:8px; margin:14px 0; }
.warn b { color:var(--red); }
.small { color:var(--sub); font-size:12.5px; }
ul { margin:8px 0 8px 22px; }
li { margin:5px 0; }
</style>
"""


def summary_table():
    rows = []
    for k in ORDER:
        r = R[k]
        best = ' class="best"' if k == "q20_cap8" else (' class="hl"' if k == "g60_pe_ew" else "")
        rows.append(f"""
        <tr{best}>
          <td>{LABELS[k]}</td>
          <td class="pos">{pct(r['total'])}</td>
          <td>{pct(r['ann'])}</td>
          <td>{r['mdd']*100:.1f}%</td>
          <td>{r['dep']:.2f}</td>
          <td>{r['fin_avg']:.1f}</td>
        </tr>""")
    return f"""
    <div class="card">
      <h3>组合实验汇总（5年日频+复权，full 基座含金融）</h3>
      <table>
        <thead><tr><th>变体</th><th>总收益</th><th>年化</th><th>MDD</th><th>单点依赖度</th><th>金融/期</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">单点依赖度 = 1 − 去最好年后收益 ÷ 总收益（越低越分散）。
      绿底 = 最优组合 q20_cap8；橙底 = g60 基线。</p>
    </div>"""


def yearly_matrix():
    rows = []
    for k in ORDER:
        yl = R[k]["yearly"]
        cells = "".join(
            f"<td class=\"{'pos' if yl.get(y,0)>=0 else 'neg'}\">{yl.get(y,0)*100:+.1f}</td>"
            for y in YEARS)
        cls = ' class="best"' if k == "q20_cap8" else (' class="hl"' if k == "g60_pe_ew" else "")
        rows.append(f"<tr{cls}><td>{LABELS[k]}</td>{cells}</tr>")
    return f"""
    <div class="card">
      <h3>分年度收益矩阵（%）</h3>
      <table>
        <thead><tr><th>变体</th>{''.join(f'<th>{y}</th>' for y in YEARS)}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">关键：q20_cap8 把 2021-2023 从 g60 的「+6.6% 真空期」填到
      <b>+27.0%</b>，同时 2024-2026 也更高。2022 从 +3.4% → +11.6%（质量股抗跌）、
      2023 从 +3.1% → +10.6%（价值股中特估）。</p>
    </div>"""


def early_late():
    rows = []
    for k in ORDER:
        yl = R[k]["yearly"]
        early = late = 1.0
        for y in YEARS:
            rr = 1 + yl.get(y, 0)
            if y <= "2023":
                early *= rr
            else:
                late *= rr
        cls = ' class="best"' if k == "q20_cap8" else (' class="hl"' if k == "g60_pe_ew" else "")
        rows.append(f"<tr{cls}><td>{LABELS[k]}</td>"
                    f"<td class=\"pos\">{early-1:+.1%}</td>"
                    f"<td class=\"pos\">{late-1:+.1%}</td>"
                    f"<td>{(early-1)/((early-1)+(late-1)):.0%}</td></tr>")
    return f"""
    <div class="card">
      <h3>早/后期收益拆分：真空期被填平了吗？</h3>
      <table>
        <thead><tr><th>变体</th><th>2021-2023</th><th>2024-2026</th><th>早期占比</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="small">g60 早期占比仅 ~10%（收益几乎全靠 2024-2026 后期），
      q20_cap8 早期占比提升到 ~27% —— 组合的收益来源明显更均衡，不再单点依赖 2024。</p>
    </div>"""


def main():
    m = D["meta"]
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>q20 × cap 组合实验</title>{CSS}</head>
<body><div class="wrap">

<h1>q20 排序 × 市值加权(cap) 组合实验</h1>
<div class="sub">承接 23 号「低PE价值风格稳健性边界」· 把 q20 + cap 两个正交源落到 full 基座组合验证 · 2026-09-02</div>

<div class="concl"><b>核心结论：</b>q20 排序 + cap8 市值加权 是这条线第一个
<b>既提收益、又填平 2021-2023 真空期</b>的组合 —— 总收益
<span class="pos">+118.5%</span>（g60 的 +67.0%），MDD 从 16.7% 降到
<b>15.6%</b>，单点依赖度从 0.62 降到 <b>0.46</b>，早期收益从 +6.6% 跃升到
<b>+27.0%</b>。两个方向叠加是「1+1&gt;2」，不是简单堆砌。</div>

<h2>一、组合实验汇总</h2>
{summary_table()}

<h2>二、分年度收益与单点依赖</h2>
{yearly_matrix()}
{early_late()}

<h2>三、三个关键洞察</h2>
<div class="card">
<ul>
  <li><b>① q20 排序在含金融口径下依然正贡献，但幅度收敛</b>：q20_ew +69.3% vs g60
      +67.0%（+2.3pp），比「剔金融口径」的 +3.40pp 略低。原因：含金融池里银行 PE 极低、
      pe_pct 近乎满分，q20 的质量分占比只有 20%，撬动有限。但方向一致、未证伪。</li>
  <li><b>② cap 市值加权才是收益主力，q20 让 cap 的效果更好</b>：q20_cap8 +118.5% vs
      q20_ew +69.3%（cap 贡献 +49pp），且 q20_cap8 比 pe_cap10(+107.0%) 更高、MDD 更低
      (15.6% vs 13.8%… 注：pe_cap10 MDD 13.8% 略优，但收益 −11.5pp)。
      本质：q20 排序把「低 PE 且质量更好」的大盘价值股排在前面，市值加权时重仓的是
      质量更高的价值龙头，而非单纯最大的低 PE 股。</li>
  <li><b>③ 金融浓度下降 + 结构健康</b>：q20_cap8 金融/期 16.8 只 vs g60 19.9 只，
      q20 排序让质量更高的非金融周期股（家电、白酒、保险等）挤进 top40，
      填补了 g60 的「纯银行」结构。top3 权重恒定 24%（3×8% 顶格）但仍是分散大盘龙头。</li>
</ul>
</div>

<h2>四、诚实边界</h2>
<div class="warn">
  <b>必须标注的局限：</b>
  <ul>
    <li>这是 <b>回测内优化</b>：q20 权重(0.8/0.2)和 cap 参数(8%) 都是在 2021-2026
        同一窗口内选择的，样本外（2026-08 之后）尚未验证。</li>
    <li>cap8 的 +118.5% 里，市值加权贡献占大头（+49pp），这部分在 22 号已确认为
        「低PE大盘价值风格的 beta 集中」，q20 只是让它变得更健康，<b>没有消除底层
        价值风格暴露</b> —— 2024 金融修复年仍是最大收益年。</li>
    <li>依赖度 0.46 仍不低：去掉 2024 仍会显著缩水。真正的反周期 alpha 还需
        <b>申万行业轮动</b>这个「唯一独立源」补齐，那是下一步。</li>
  </ul>
</div>

<div class="small" style="margin-top:24px;">
  数据：<code>_bt_q20_cap_results.json</code> · 脚本 <code>_bt_q20_cap.py</code><br>
  口径：full 基座(含金融)、日频复权、含成本 5bp+10bp、mv≥100亿、L4+L5 门控。
  锚点 g60 = +67.01% 精确复现（{m['anchor_g60']:+.4f}）。
</div>

</div></body></html>"""

    with open("_bt_q20_cap_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("报告 → _bt_q20_cap_report.html")


if __name__ == "__main__":
    main()
