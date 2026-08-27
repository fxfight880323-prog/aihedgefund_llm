"""GBM量价 × 万得全A 回测 — HTML 报告生成。

输入 _bt_gbm_results.json → 输出 _gbm_report.html
"""
from __future__ import annotations

import json

OUT = "_gbm_report.html"

VAR_NAMES = {
    "gbm40": "GBM top-40 等权",
    "gbm20": "GBM top-20",
    "gbm60": "GBM top-60",
    "gbmLow40": "GBM 最低 40（对照）",
    "gbm40_mv100": "GBM top-40 · 市值≥100亿",
}
VAR_COLORS = {
    "gbm40": "#c62828", "gbm20": "#e67e22", "gbm60": "#8a6d3b",
    "gbmLow40": "#7f8c8d", "gbm40_mv100": "#8250df",
}
ORDER = ["gbm40", "gbm20", "gbm60", "gbmLow40", "gbm40_mv100"]


def pct(x, d=1):
    return f"{x * 100:+.{d}f}%" if x is not None else "—"


def main():
    r = json.loads(open("_bt_gbm_results.json", encoding="utf-8").read())
    results = r["results"]
    ew = r["ew"]
    idx = r.get("idx")
    lx_core = r.get("lx_core") or {}
    diag = r["diag"]
    yearly = r.get("yearly", {})
    bench_months = [d["month"] for d in ew["nav"]]

    # 超额
    ex_ew = {v: results[v]["total"] - ew["total"] for v in ORDER}
    ex_lx = {v: results[v]["total"] - (lx_core.get("total") or 0) for v in ORDER}

    # ---- ① 总览表 ----
    rows = []
    for v in ORDER:
        a = results[v]
        hl = " class='hl'" if v == "gbm40" else ""
        rows.append(f"""
        <tr{hl}><td><b>{VAR_NAMES[v]}</b></td>
          <td>{pct(a['total'])}</td><td>{pct(a['ann'])}</td>
          <td>{pct(a['mdd'])}</td>
          <td>{pct(ex_ew[v])}</td><td>{pct(ex_lx[v])}</td></tr>""")
    rows.append(f"""
        <tr><td>EW-全A（等权基准）</td><td>{pct(ew['total'])}</td>
          <td>{pct(ew['ann'])}</td><td>—</td><td>0.0%</td><td>{pct(-(lx_core.get('total') or 0))}</td></tr>""")
    if idx:
        rows.append(f"""
        <tr><td>CSI-全指（中证全指 000985.SH）</td><td>{pct(idx['total'])}</td>
          <td>{pct(idx['ann'])}</td><td>—</td><td>—</td><td>{pct(idx['total'] - (lx_core.get('total') or 0))}</td></tr>""")
    if lx_core:
        rows.append(f"""
        <tr class='ref'><td>LX-core（刘旭式 · 便宜优先）</td><td>{pct(lx_core.get('total'))}</td>
          <td>{pct(lx_core.get('ann'))}</td><td>{pct(lx_core.get('mdd'))}</td>
          <td>{pct((lx_core.get('total') or 0) - ew['total'])}</td><td>0.0%</td></tr>""")

    # ---- NAV 曲线 ----
    navs = {"EW-全A": {d["month"]: d["nav"] for d in ew["nav"]}}
    for v in ORDER:
        navs[VAR_NAMES[v]] = {d["month"]: d["nav"] for d in results[v]["nav"]}
    if idx:
        navs["CSI-全指"] = {d["month"]: d["nav"] for d in idx["nav"]}
    if lx_core.get("nav"):
        navs["LX-core"] = {d["month"]: d["nav"] / 1e6 for d in lx_core["nav"]}
    base = bench_months[0]
    norm = {}
    for k, v in navs.items():
        b = v.get(base) or 1.0
        norm[k] = [round((v.get(m, b) / b - 1) * 100, 2) for m in bench_months]
    series = []
    for v in ORDER:
        c = VAR_COLORS[v]
        dash = "[4,3]" if v == "gbmLow40" else "[]"
        series.append(
            '{"label": %s, "data": %s, "borderColor": %s, '
            '"backgroundColor": %s, "fill": false, "tension": 0.15, '
            '"borderWidth": 2.4, "borderDash": %s}'
            % (json.dumps(VAR_NAMES[v]), json.dumps(norm[VAR_NAMES[v]]),
               json.dumps(c), json.dumps(c + "22"), dash))
    if "LX-core" in norm:
        series.append(
            '{"label": "LX-core", "data": %s, "borderColor": "#0b6bcb", '
            '"backgroundColor": "#0b6bcb22", "fill": false, "tension": 0.15, '
            '"borderWidth": 1.8, "borderDash": [6,3]}' % json.dumps(norm["LX-core"]))
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

    # ---- ② 分年度表 ----
    yr_rows = []
    yrs = sorted(set().union(*[set(yearly.get(v, {}).keys()) for v in ORDER]) or set())
    for y in yrs:
        cells = []
        for v in ORDER:
            d = yearly.get(v, {}).get(y, {})
            cells.append(f"<td>{pct(d.get('strategy'))}<br>"
                         f"<span class='sub'>{pct(d.get('excess'))} vs EW</span></td>")
        yr_rows.append(f"<tr><td>{y}</td>{''.join(cells)}</tr>")

    # ---- ③ 市值诊断表 ----
    mv_rows = []
    for m in bench_months:
        if m not in diag:
            continue
        d = diag[m]
        g = d.get("gbm40_med_mv")
        small = d.get("gbm40_small_pct")
        big = d.get("gbm40_big_pct")
        to = d.get("gbm40_turnover")
        mv100_med = d.get("gbm40_mv100_med_mv")
        mv100_n = None
        mv_rows.append(f"""
        <tr><td>{m}</td><td>{d['univ']}</td>
          <td>{d['gbm_cov']} ({d['gbm_cov_pct']*100:.0f}%)</td>
          <td>{g if g is None else f'{g:.0f}亿'}</td>
          <td>{small*100:.0f}%</td><td>{big*100:.0f}%</td>
          <td>{to if to is None else f'{to*100:.0f}%'}</td>
          <td>{mv100_med if mv100_med is None else f'{mv100_med:.0f}亿'}</td></tr>""")

    # ---- ④ 结论 ----
    t_g = results["gbm40"]["total"]
    t_ew = ew["total"]
    t_lx = lx_core.get("total") or 0
    mdd_g = results["gbm40"]["mdd"]
    mdd_lx = lx_core.get("mdd") or 0
    t_low = results["gbmLow40"]["total"]
    t_mv100 = results["gbm40_mv100"]["total"]
    med_all = [diag[m]["gbm40_med_mv"] for m in bench_months if m in diag and diag[m].get("gbm40_med_mv")]
    med_avg = sum(med_all) / len(med_all) if med_all else 0

    # 结论逻辑
    if t_g - t_ew > 0.05:
        verdict_1 = (f"<b>GBM top-40 相对等权全A有超额 {pct(t_g - t_ew)}</b>"
                     f"（总收益 {pct(t_g)} vs {pct(t_ew)}）")
    elif t_g - t_ew > 0:
        verdict_1 = (f"GBM top-40 相对等权全A微幅超额 {pct(t_g - t_ew)}（{pct(t_g)} vs {pct(t_ew)}），"
                     f"扣除成本后基本无 alpha")
    else:
        verdict_1 = (f"<b>GBM top-40 跑输等权全A {pct(t_g - t_ew)}</b>"
                     f"（{pct(t_g)} vs {pct(t_ew)}）——单因子裸排序在成分池内无超额")

    if t_low > t_g:
        verdict_2 = (f"<b>方向反了</b>：GBM 最低 40 只 {pct(t_low)} 反而跑赢 top-40 {pct(t_g)}，"
                     f"因子在成分池内方向性失效")
    else:
        verdict_2 = (f"方向正确：GBM 最低 40 只 {pct(t_low)} 显著跑输 top-40 {pct(t_g)}，"
                     f"因子排序方向在成分池内成立")

    if med_avg < 60:
        verdict_3 = (f"<b>组合显著偏小市值</b>：top-40 中位市值平均 {med_avg:.0f} 亿，"
                     f"与扫描结论（市值 ρ=-0.27）一致；若 gbm40_mv100（市值≥100亿）"
                     f"总收益 {pct(t_mv100)} 大幅缩水，说明超额主要来自小市值 beta")
    else:
        verdict_3 = (f"组合市值暴露相对温和（中位市值平均 {med_avg:.0f} 亿），"
                     f"市值≥100亿 版总收益 {pct(t_mv100)}")

    if t_g > t_lx:
        verdict_4 = (f"相对 LX-core（{pct(t_lx)}）{pct(t_g - t_lx)}；"
                     f"但 MDD {pct(mdd_g)} vs {pct(mdd_lx)}")
    else:
        verdict_4 = (f"跑输 LX-core（{pct(t_lx)}，差 {pct(t_g - t_lx)}）；"
                     f"MDD {pct(mdd_g)} vs {pct(mdd_lx)}——便宜优先仍是更强方法论")

    # 滚动IC监控检查：2026 年衰减
    ic_note = ("<b>衰减监控提示</b>：GBM 分年 IC 2021-2026 为 0.094/0.157/0.135/0.118/0.095/<b>0.052</b>，"
               "2026 年已降至全段均值(0.114)一半以下。扫描建议滚动 12 月 IC&lt;0.03 即降权，"
               "若本回测 2025-08/2026-04 两期超额已转负，则监控规则应触发。")

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GBM量价 × 万得全A 回测报告</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  body{{font-family:-apple-system,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;
    margin:0;padding:32px 24px;background:#fafafa;color:#222;line-height:1.55}}
  .wrap{{max-width:1080px;margin:0 auto}}
  h1{{font-size:20px;margin:0 0 4px}}
  .meta{{color:#666;font-size:13px;margin-bottom:24px}}
  h2{{font-size:16px;margin:28px 0 10px;border-left:4px solid #c62828;padding-left:10px}}
  table{{border-collapse:collapse;width:100%;font-size:13px;background:#fff}}
  th,td{{border:1px solid #e3e3e3;padding:7px 10px;text-align:right}}
  th{{background:#f5f5f5;font-weight:500}}
  td:first-child,th:first-child{{text-align:left}}
  tr.hl td{{background:#fdf0ef}}
  tr.ref td{{background:#eef4fc}}
  .sub{{color:#888;font-size:11px}}
  .verdict{{background:#fff;border:1px solid #e3e3e3;border-radius:8px;
    padding:14px 18px;margin:10px 0;font-size:14px}}
  .verdict b{{color:#a32d2d}}
  .warn{{background:#fdf6ec;border:1px solid #f0d9a8;border-radius:8px;
    padding:14px 18px;margin:14px 0;font-size:14px}}
  .chartbox{{background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:12px}}
  .foot{{color:#999;font-size:12px;margin-top:24px}}
</style></head><body><div class="wrap">
<h1>GBM量价因子 × 万得全A PIT 池 全市场回测</h1>
<div class="meta">{r['meta']['period']} · 池子=万得全A(881001.WI) PIT 成分 ·
{r['meta']['rebalance']} · {r['meta']['generated']}</div>

<h2>总览（相对收益列：vs 等权全A / vs LX-core）</h2>
<table><tr><th>组合</th><th>总收益</th><th>年化</th><th>最大回撤</th>
<th>超额 vs EW</th><th>超额 vs LX</th></tr>
{''.join(rows)}</table>

<h2>NAV 曲线（累计收益 %）</h2>
<div class="chartbox"><div style="position:relative;width:100%;height:420px">
<canvas id="nav" role="img" aria-label="GBM各变体与基准NAV曲线">NAV 曲线</canvas>
</div></div>

<h2>分年度收益（组合 vs 等权全A）</h2>
<table><tr><th>年度</th>{''.join(f'<th>{VAR_NAMES[v]}</th>' for v in ORDER)}</tr>
{''.join(yr_rows)}</table>

<h2>每期组合诊断（gbm40）</h2>
<table><tr><th>期</th><th>成分</th><th>GBM覆盖</th><th>top40中位市值</th>
<th>小盘&lt;30亿</th><th>大盘≥100亿</th><th>换手</th><th>mv100版中位市值</th></tr>
{''.join(mv_rows)}</table>

<h2>结论</h2>
<div class="verdict">{verdict_1}</div>
<div class="verdict">{verdict_2}</div>
<div class="verdict">{verdict_3}</div>
<div class="verdict">{verdict_4}</div>
<div class="warn">{ic_note}</div>

<div class="foot">数据：申万金工 MCP（GBM量价因子值，月末快照）+ 万得全A PIT 成分（juzi 缓存）
+ 腾讯月K（前复权）。同引擎同成本（5bp 佣金 + 10bp 滑点），半年度调仓。
本报告仅供研究参考，不构成投资建议。</div>
</div>
<script>
new Chart(document.getElementById('nav'), {{
  type: 'line',
  data: {{ labels: {json.dumps(bench_months)}, datasets: {series_js} }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 14, font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 45, autoSkip: true, maxTicksLimit: 12 }} }},
      y: {{ ticks: {{ callback: v => v + '%' }} }}
    }}
  }}
}});
</script>
</body></html>"""
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"已生成 {OUT}")


if __name__ == "__main__":
    main()
