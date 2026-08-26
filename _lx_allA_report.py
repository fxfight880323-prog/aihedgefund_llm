"""刘旭式框架全A回测 — HTML 报告生成（9 变体：5 主变体 + 4 市值诊断）。

输入 _bt_lx_allA_results.json → 输出 _lx_allA_report.html
"""
from __future__ import annotations

import json

OUT = "_lx_allA_report.html"

VAR_NAMES = {
    "core": "LX-core · 不贵+低预期（L4+L5）",
    "qual": "LX-qual · +预期ROE≥12%（质量通道）",
    "cf":   "LX-cf · +现金流质量（OCF/市值>0）",
    "gm":   "LX-gm · +毛利率≥市场中位数",
    "full": "LX-full · 完整刘旭式近似",
}
VAR_COLORS = {
    "core": "#8a6d3b", "qual": "#1a7f37", "cf": "#0b6bcb",
    "gm": "#8250df", "full": "#c62828",
}
# 市值诊断组：名称 -> (标签, 颜色)
MV_GROUPS = [
    ("core_mv0", "LX-core · 无市值下限", "#7f8c8d"),
    ("core_mv30", "LX-core · 市值≥30亿", "#f39c12"),
    ("core", "LX-core · 市值≥100亿", "#8a6d3b"),
    ("full_mv0", "LX-full · 无市值下限", "#5d6d7e"),
    ("full_mv30", "LX-full · 市值≥30亿", "#e67e22"),
    ("full", "LX-full · 市值≥100亿", "#c62828"),
]


def pct(x, d=1):
    return f"{x * 100:+.{d}f}%" if x is not None else "—"


def main():
    r = json.loads(open("_bt_lx_allA_results.json", encoding="utf-8").read())
    results = r["results"]
    ew = r["ew"]
    idx = r.get("idx")
    diag = r["diag"]
    bench_months = [d["month"] for d in ew["nav"]]
    order = ["core", "qual", "cf", "gm", "full"]

    # ---- ① 总览表 ----
    rows = []
    for v in order:
        a = results[v]
        hl = " class='hl'" if v == "full" else ""
        rows.append(f"""
        <tr{hl}><td><b>{VAR_NAMES[v]}</b></td>
          <td>{pct(a['total'])}</td><td>{pct(a['ann'])}</td>
          <td>{pct(a['mdd'])}</td>
          <td>{pct(a['excess_ew'])}</td>
          <td>{pct(a['excess_idx'])}</td></tr>""")
    rows.append(f"""
        <tr><td>EW-全A（等权基准）</td><td>{pct(ew['total'])}</td>
          <td>{pct(ew['ann'])}</td><td>—</td><td>0.0%</td><td>—</td></tr>""")
    if idx:
        rows.append(f"""
        <tr><td>CSI-全指（中证全指 000985.SH）</td><td>{pct(idx['total'])}</td>
          <td>{pct(idx['ann'])}</td><td>—</td><td>—</td><td>0.0%</td></tr>""")

    # ---- ② 市值诊断表 ----
    mv_rows = []
    for v, label, _c in MV_GROUPS:
        a = results[v]
        hl = " class='hl'" if v in ("core", "full") else ""
        mv_rows.append(f"""
        <tr{hl}><td><b>{label}</b></td>
          <td>{pct(a['total'])}</td><td>{pct(a['ann'])}</td>
          <td>{pct(a['mdd'])}</td>
          <td>{pct(a['excess_ew'])}</td>
          <td>{pct(a['excess_idx'])}</td></tr>""")

    # ---- NAV（累计收益 %）----
    navs = {"EW-全A": {d["month"]: d["nav"] for d in ew["nav"]}}
    for v in order:
        navs[VAR_NAMES[v]] = {d["month"]: d["nav"] for d in results[v]["nav"]}
    if idx:
        navs["CSI-全指"] = {d["month"]: d["nav"] for d in idx["nav"]}
    all_months = bench_months
    base = all_months[0]
    norm = {}
    for k, v in navs.items():
        b = v.get(base) or 1.0
        norm[k] = [round((v.get(m, b) / b - 1) * 100, 2) for m in all_months]
    series = []
    for v in order:
        k = VAR_NAMES[v]
        c = VAR_COLORS[v]
        series.append(
            '{"label": %s, "data": %s, "borderColor": %s, '
            '"backgroundColor": %s, "fill": false, "tension": 0.15, '
            '"borderWidth": 2.4, "borderDash": []}'
            % (json.dumps(k), json.dumps(norm[k]), json.dumps(c),
               json.dumps(c + "22")))
    # 市值诊断线（core_mv0 虚线对比）
    k0 = "LX-core · 无市值下限"
    if k0 in norm:
        series.append(
            '{"label": %s, "data": %s, "borderColor": "#7f8c8d", '
            '"backgroundColor": "#7f8c8d22", "fill": false, "tension": 0.15, '
            '"borderWidth": 1.8, "borderDash": [4,3]}'
            % (json.dumps(k0), json.dumps(norm[k0])))
    series.append(
        '{"label": "EW-全A", "data": %s, "borderColor": "#666", '
        '"backgroundColor": "#66622", "fill": false, "tension": 0.1, '
        '"borderWidth": 1.6, "borderDash": [6,4]}' % json.dumps(norm["EW-全A"]))
    if idx:
        series.append(
            '{"label": "CSI-全指", "data": %s, "borderColor": "#999", '
            '"backgroundColor": "#99922", "fill": false, "tension": 0.1, '
            '"borderWidth": 1.4, "borderDash": [3,3]}'
            % json.dumps(norm["CSI-全指"]))
    series_js = "[" + ",".join(series) + "]"

    # ---- ③ 逐期诊断 ----
    period_rows = []
    for m in bench_months:
        if m not in diag:
            continue
        d = diag[m]
        drop = d.get("core_drop", {})
        drop_s = " ".join(f"{k.replace('drop_', '')}:{v}"
                          for k, v in sorted(drop.items(), key=lambda x: -x[1])
                          if v)
        passes = " ".join(f"{v}:{d.get(v + '_pass', 0)}" for v in order)
        period_rows.append(f"""
        <tr><td>{m}</td><td>{d['univ']}</td>
          <td>{d['val_cov']}/{d['fac_cov']}/{d['cons_cov']}</td>
          <td>{passes}</td><td>{drop_s}</td></tr>""")

    # ---- ④ 逐层贡献 + 市值缺口归因 ----
    def perf(v):
        a = results[v]
        return a["total"], a["ann"], a["mdd"], a["excess_ew"]

    t_core, _, mdd_core, ex_core = perf("core")
    t_full, _, mdd_full, ex_full = perf("full")
    ex_qual = results["qual"]["excess_ew"]
    ex_cf = results["cf"]["excess_ew"]
    ex_gm = results["gm"]["excess_ew"]
    best_v = max(order, key=lambda v: results[v]["total"])
    worst_v = min(order, key=lambda v: results[v]["total"])

    # 市值缺口归因
    ex_core_mv0 = results["core_mv0"]["excess_ew"]
    ex_full_mv0 = results["full_mv0"]["excess_ew"]
    gap_core = ex_core - ex_core_mv0          # >0 说明市值下限反而是正贡献
    gap_full = ex_full - ex_full_mv0
    if gap_core > 0.05:
        mv_verdict = (f"市值下限不是缺口来源：100亿版超额 {pct(ex_core)} 反超"
                      f"无下限版 {pct(ex_core_mv0)}（差 {pct(gap_core)}）。"
                      f"市值下限扮演<b>质量保护</b>角色——PE 升序下大市值深度价值股"
                      f"（银行/公用/建筑等）表现优于小盘廉价股（后者多为价值陷阱），"
                      f"缺口主要来自 L4+L5 筛选相对等权池的暴露差异")
    elif gap_core > -0.05:
        mv_verdict = (f"市值下限影响有限（100亿 vs 无下限差 {pct(gap_core)}），"
                      f"超额缺口主要来自 L4+L5 筛选逻辑本身相对等权池的暴露差异")
    else:
        mv_verdict = (f"放松市值下限后超额改善（{pct(ex_core)} → {pct(ex_core_mv0)}，"
                      f"差 {pct(gap_core)}），缺口部分来自市值风格暴露："
                      f"≥100亿剔除小盘，而 2021-2026 小盘显著跑赢大盘")

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>刘旭式框架 · 万得全A 全市场回测</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js">
</script>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px 40px;
        background: #fafafa; color: #222; }}
 h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; margin-top: 32px;
        border-left: 4px solid #c62828; padding-left: 10px; }}
 .sub {{ color: #666; font-size: 13px; margin-top: -8px; }}
 table {{ border-collapse: collapse; margin: 12px 0; font-size: 13.5px;
         background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 12px; text-align: right; }}
 th {{ background: #f0f0f0; }} td:first-child {{ text-align: left; }}
 tr.hl {{ background: #fff3e0; }}
 .pos {{ color: #c62828; }} .neg {{ color: #1b5e20; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
         padding: 14px 18px; margin: 10px 0; font-size: 13.5px; line-height: 1.7; }}
 .kpi {{ font-size: 24px; font-weight: 700; }}
 canvas {{ background: #fff; border: 1px solid #eee; }}
 .note {{ color: #888; font-size: 12px; }}
</style></head><body>

<h1>刘旭式框架 × 万得全A 全市场回测</h1>
<p class="sub">池子 = 万得全A(881001.WI) PIT 成分 · 半年度调仓 · 2021-08 ~ 2026-06 ·
成本 5bp+10bp · 全部真实数据（估值面板 / HF因子 / 一致预期 / 腾讯月K）</p>

<div class="card">
<b>结论速览：</b>
LX-{best_v} 是全变体最佳（总收益 {pct(perf(best_v)[0])}），LX-{worst_v} 最弱
（{pct(perf(worst_v)[0])}）。框架"不贵+低预期"核心 LX-core 总收益 {pct(t_core)} /
年化 {pct(perf("core")[1])} / MDD {pct(mdd_core)}，超额等权全A
<span class="{'pos' if ex_core >= 0 else 'neg'}">{pct(ex_core)}</span>；
完整近似 LX-full {pct(t_full)} / 超额
<span class="{'pos' if ex_full >= 0 else 'neg'}">{pct(ex_full)}</span>。
<b>回撤亮点：</b>LX-gm（+毛利率≥市场中位数）总收益 {pct(perf('gm')[0])} 几乎追平 core，
但 <b>MDD 仅 {pct(perf('gm')[2])}</b>（core 为 {pct(mdd_core)}）——毛利率过滤是唯一
既保值又显著降险的质量层。
<b>市值归因：</b>{mv_verdict}。
</div>

<h2>① 绩效总览（2021-08 → 2026-06，约 4.8 年）· 市值≥100亿</h2>
<table>
<tr><th>策略变体</th><th>总收益</th><th>年化</th><th>最大回撤</th>
<th>超额 vs 等权全A</th><th>超额 vs 中证全指</th></tr>
{''.join(rows)}
</table>

<h2>② 市值诊断（超额缺口来自风格还是选股？）</h2>
<table>
<tr><th>策略变体</th><th>总收益</th><th>年化</th><th>最大回撤</th>
<th>超额 vs 等权全A</th><th>超额 vs 中证全指</th></tr>
{''.join(mv_rows)}
</table>
<div class="card">
市值下限从 100亿 → 30亿 → 无下限：LX-core 超额从 {pct(ex_core)}
变化到 {pct(results['core_mv30']['excess_ew'])} / {pct(ex_core_mv0)}
（100亿 vs 无下限差 {pct(gap_core)}），LX-full 从 {pct(ex_full)}
变化到 {pct(results['full_mv30']['excess_ew'])} / {pct(ex_full_mv0)}
（差 {pct(gap_full)}）。
</div>

<h2>③ 净值走势（累计收益 %）</h2>
<canvas id="nav" height="110"></canvas>

<h2>④ 逐期筛选诊断</h2>
<table>
<tr><th>调仓期</th><th>成分数</th><th>val/fac/cons 覆盖</th>
<th>各变体命中数</th><th>core 淘汰分布</th></tr>
{''.join(period_rows)}
</table>

<h2>⑤ 逐层贡献分解（市值≥100亿口径）</h2>
<div class="card">
叠加质量层 vs 核心：qual 超额 {pct(ex_qual)} → 贡献
<span class="{'pos' if ex_qual - ex_core >= 0 else 'neg'}">{pct(ex_qual - ex_core)}</span><br>
叠加现金流层 vs 核心：cf 超额 {pct(ex_cf)} → 贡献
<span class="{'pos' if ex_cf - ex_core >= 0 else 'neg'}">{pct(ex_cf - ex_core)}</span><br>
叠加毛利率层 vs 核心：gm 超额 {pct(ex_gm)} → 贡献
<span class="{'pos' if ex_gm - ex_core >= 0 else 'neg'}">{pct(ex_gm - ex_core)}</span><br>
完整近似 vs 核心：full 超额 {pct(ex_full)} → 合计贡献
<span class="{'pos' if ex_full - ex_core >= 0 else 'neg'}">{pct(ex_full - ex_core)}</span>
（正=质量层增强选股；负=质量层收窄后暴露风格/覆盖偏差）
</div>

<p class="note">方法诚实性：juzi 财务宽表为单股接口（全市场逐只不可行），
ROE 用一致预期 ROE 代理、现金流用 cetop(OCF/市值) 代理、毛利率用全市场中位数
代替行业中位数。con_roe 缺失（小盘无分析师覆盖）的股票在 qual/full 变体被剔除，
这是框架在全A的真实暴露。等权全A NAV 由 PIT 成分 + 真实月K 计算。</p>

<script>
const labels = {json.dumps(all_months)};
new Chart(document.getElementById('nav'), {{
  type: 'line',
  data: {{ labels: labels, datasets: {series_js} }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});
</script>
</body></html>"""

    open(OUT, "w", encoding="utf-8").write(html)
    print(f"报告 → {OUT}")


if __name__ == "__main__":
    main()
