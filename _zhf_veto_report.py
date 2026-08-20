"""ZHF-veto（预期只否决 + 卖出纪律）— HTML 报告生成。

输入 _bt_zhf_veto_results.json → 输出 _zhf_veto_report.html
"""
from __future__ import annotations

import json
import os

OUT = "_zhf_veto_report.html"


def pct(x, d=1):
    return f"{x * 100:+.{d}f}%" if x is not None else "—"


def main():
    r = json.loads(open("_bt_zhf_veto_results.json", encoding="utf-8").read())
    arms = r["arms"]
    ew = r["ew"]
    zhf_old = r["zhf_cons_old"]
    diag = r["diag"]
    veto_all = r["veto_all"]
    contrib = r["contrib"]
    weights = r["weights_by_dt"]
    bench_months = r["bench_months"]

    arm_by_name = {a["name"]: a for a in arms}
    arm2 = arm_by_name["ZHF-veto-sell"]

    # ---- 总览表 ----
    rows = []
    for a in arms:
        hl = " class='hl'" if a["name"] == "ZHF-veto-sell" else ""
        rows.append(f"""
        <tr{hl}>
          <td>{a['name']}</td>
          <td>{pct(a['total'])}</td>
          <td>{pct(a['ann'])}</td>
          <td>{pct(a['mdd'])}</td>
          <td>{pct(a['excess_ew'])}</td>
          <td>{a['n_sells']}</td>
        </tr>""")
    rows.append(f"""
        <tr><td>EW-全A（等权基准）</td><td>{pct(ew['total'])}</td>
        <td>{pct(ew['ann'])}</td><td>—</td><td>0.0%</td><td>—</td></tr>""")
    rows.append(f"""
        <tr><td>ZHF-cons（上轮：预期打分，无否决无卖出）</td>
        <td>{pct(zhf_old['total'])}</td><td>{pct(zhf_old['ann'])}</td>
        <td>{pct(zhf_old['mdd'])}</td><td>—</td><td>—</td></tr>""")

    # ---- NAV ----
    navs = {}
    for a in arms + [ew]:
        if a.get("nav"):
            navs[a["name"]] = {d["month"]: d["nav"] for d in a["nav"]}
    navs["ZHF-cons(上轮)"] = {d["month"]: d["nav"]
                              for d in json.loads(
                                  open("_bt_winda_results.json",
                                       encoding="utf-8").read())["zhf"]["nav"]}
    all_months = sorted({m for v in navs.values() for m in v})
    base = all_months[0]
    norm = {}
    for k, v in navs.items():
        if not v:
            continue
        b = v[base] if base in v else 1.0
        norm[k] = [round((v.get(m, 0) / b - 1) * 100, 2) if v.get(m) else None
                   for m in all_months]

    chart_labels = json.dumps(all_months)
    colors = {"ZHF-veto": "#c96", "ZHF-veto-sell": "#d33",
              "ZHF-veto-switch": "#a00", "ZHF-veto-sell-strict": "#e68",
              "EW-全A": "#666", "ZHF-cons(上轮)": "#999"}
    series = []
    order = ["ZHF-veto", "ZHF-veto-sell", "ZHF-veto-sell-strict",
             "ZHF-veto-switch", "EW-全A", "ZHF-cons(上轮)"]
    for k in order:
        if k not in norm:
            continue
        c = colors.get(k, "#333")
        series.append(
            '{"label": %s, "data": %s, "borderColor": %s, '
            '"backgroundColor": %s, "fill": false, "tension": 0.15, '
            '"borderWidth": %s, "borderDash": %s}'
            % (json.dumps(k), json.dumps(norm[k]), json.dumps(c),
               json.dumps(c + "22"),
               2.8 if "sell" in k else (2.0 if "veto" in k else 1.4),
               json.dumps([] if "veto" in k
                          else ([6, 4] if (k == "ZHF-cons(上轮)" or k == "EW-全A")
                                else []))))
    series_js = "[" + ",".join(series) + "]"

    # ---- 逐期诊断 ----
    period_rows = []
    for m in bench_months:
        if m not in diag:
            continue
        d = diag[m]
        veto = d["veto"]
        veto_s = " ".join(f"{k}:{v}" for k, v in sorted(veto.items(),
                                                        key=lambda x: -x[1]))
        cls = d["cls"]
        cls_s = " ".join(f"{k}:{v}" for k, v in sorted(cls.items()))
        period_rows.append(f"""
        <tr><td>{m}</td><td>{d['univ']}</td><td>{d['cov']}</td>
        <td>{d['pass']}</td><td>{veto_s}</td><td>{cls_s}</td>
        <td>{d['hold']}</td></tr>""")

    # ---- 逐期收益 + 超额 ----
    per_rows = []
    for a in arms:
        pr = a.get("per_period_ret", {})
        for m in sorted(pr.keys()):
            ret = pr[m]
            ex = ret - (ew["nav"][[d["month"] for d in ew["nav"]].index(m) + 1]["nav"] /
                        ew["nav"][[d["month"] for d in ew["nav"]].index(m)]["nav"] - 1) \
                if m != bench_months[-1] else None
            ex_s = f"<span class='{'pos' if (ex or 0) >= 0 else 'neg'}'>" \
                   f"{pct(ex)}</span>" if ex is not None else "—"
            per_rows.append(
                f"<tr><td>{a['name']}</td><td>{m}</td><td>{pct(ret)}</td>"
                f"<td>{ex_s}</td></tr>")

    # ---- 卖出统计（arm2/arm3）----
    # 从 NAV 期结果中没有卖单明细；用 arm2 的 per_period 无卖单 —— 补读 detail？
    # 诚实起见：卖单明细在运行日志，这里显示汇总（n_sells）。

    # ---- 个股贡献（arm2 权重即否决后权重）----
    contrib_html = ""
    for row in contrib:
        tops = "".join(
            f"<div class='ct'><b>{it['tk']}</b> w={it['w']:.1%} "
            f"<span class='{'pos' if it['ret'] >= 0 else 'neg'}'>"
            f"{it['ret']:+.1%}</span> → {it['contrib']:+.2%}</div>"
            for it in row["top"])
        contrib_html += f"""
        <div class="period">
          <h4>{row['month']} → {row['end']} &nbsp;组合 {pct(row['total_ret'])}（{row['n']}只）</h4>
          {tops}
        </div>"""

    last_p = sorted(weights.keys())[-1]
    hold_rows = "".join(
        f"<tr><td>{tk}</td><td>{w:.1%}</td></tr>"
        for tk, w in sorted(weights[last_p].items(), key=lambda kv: -kv[1]))

    veto_s = " ".join(f"{k}: {v}" for k, v in sorted(veto_all.items(),
                                                     key=lambda x: -x[1]))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZHF × 预期只否决 + 卖出纪律 · 万得全A 回测</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f7f8fa; color: #1c1e21; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 60px; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; border-left: 4px solid #d33; padding-left: 10px; margin-top: 36px; }}
  h3 {{ font-size: 14px; color: #555; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }}
  th, td {{ border: 1px solid #e3e6ea; padding: 6px 10px; text-align: right; }}
  th {{ background: #f0f2f5; }} td:first-child {{ text-align: left; }}
  tr.hl td {{ background: #fdf0ef; font-weight: 600; }}
  .card {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 8px; padding: 16px; margin-top: 14px; }}
  .ct {{ font-size: 12px; color: #444; padding: 2px 0; }}
  .pos {{ color: #d33; }} .neg {{ color: #1a7f37; }}
  .period {{ margin-bottom: 10px; }}
  .period h4 {{ margin: 6px 0; font-size: 13px; }}
  .concl {{ font-size: 13px; line-height: 1.75; }}
  .concl p {{ margin: 8px 0; }}
  .concl b {{ color: #a00; }}
  .caveat {{ background: #fff8e6; border: 1px solid #f0d9a8; border-radius: 8px; padding: 14px 18px; margin-top: 14px; font-size: 13px; line-height: 1.7; }}
  .scroll {{ max-height: 360px; overflow: auto; }}
</style></head><body><div class="wrap">
<h1>章宏帆框架 × v3rec 化（预期只否决）+ 卖出纪律 — 万得全A 全市场回测</h1>
<h3>池子=万得全A(881001.WI) 每期PIT成分（4441→5503只）｜2021-08~2026-08 十期半年调仓｜成本 5bp+10bp｜vnpy 引擎</h3>

<div class="card">
<h2>总览（对比等权全A —— 方法论铁律）</h2>
<table>
<tr><th>策略</th><th>总收益</th><th>年化</th><th>最大回撤</th>
<th>超额(等权全A)</th><th>卖出笔数</th></tr>
{''.join(rows)}
</table>
</div>

<div class="card">
<h2>关键结论</h2>
<div class="concl">
<p id="concl1">① 预期数据降级为纯否决后，全市场 ZHF 框架：……（回测后填充）</p>
<p id="concl2">② 卖出纪律（预期恶化 + 回撤止损）的边际贡献：……</p>
<p id="concl3">③ 风格开关（熊市降仓）……</p>
<p id="concl4">④ 与 ZHF-cons 上轮（预期打分 -7.3%）对比：……</p>
</div>
</div>

<div class="card">
<h2>净值曲线（相对起点累计收益 %）</h2>
<canvas id="nav" style="width:100%;height:380px"></canvas>
</div>

<div class="card">
<h2>逐期筛选诊断</h2>
<table>
<tr><th>调仓期</th><th>万得全A成分</th><th>预期覆盖</th><th>通过否决</th>
<th>否决明细</th><th>ZHF 类分布</th><th>持仓数</th></tr>
{''.join(period_rows)}
</table>
<p style="font-size:12px;color:#666">否决闸门汇总（10 期合计）：{veto_s}</p>
</div>

<div class="card">
<h2>逐期收益与超额（vs 等权全A）</h2>
<div class="scroll"><table>
<tr><th>策略</th><th>区间</th><th>区间收益</th><th>超额(等权全A)</th></tr>
{''.join(per_rows)}
</table></div>
</div>

<div class="card">
<h2>个股贡献（ZHF-veto-sell 每期 Top 8）</h2>
{contrib_html}
</div>

<div class="card">
<h2>最新一期持仓（{last_p}，否决后）</h2>
<table><tr><th>代码</th><th>权重</th></tr>{hold_rows}</table>
</div>

<div class="caveat">
<h3 style="margin-top:0">诚实声明（必须读）</h3>
1. <b>数据约束（重要）</b>：全市场(万得全A 4441~5503只) PIT <b>实际财务数据不可得</b>
（juzi 财务接口单股粒度 5500×10 次调用不可行；妙想/自选股为当前快照，对 2021 调仓日即未来函数）。
全市场唯一 PIT 可得 = 一致预期快照（朝阳永续 con_forecast_stk，snapshot 日期 ≤ 调仓日，无未来函数）。<br>
2. <b>因此本次"预期只否决"的执行是数据约束下的最近似版</b>：预期数据先做绝对否决闸门
（预期增速&gt;0 / 预期动量&gt;0 / PEG∈(0,2)），ZHF 决策树的打分层因无实际财务输入，
仍基于 con_* 字段（类配比/集中度纪律保留）。若未来补齐全市场实际财务，"
打分层用实际财务 + 预期只否决"才是 v3rec 的严格类比，本结果需重测。<br>
3. <b>卖出纪律的实现差异</b>：v3rec 的 PS/PS_med≥2 卖出需要实际营收（全市场无）→
本实验用替代信号：调仓月预期恶化 overlay（rev4w≤0 / PEG≥2 / 预期增速环比下滑）
+ 非调仓月价格回撤止损（持有期峰值回撤 ≥40%）。两者均为 PIT，无未来函数，但与原版 PS 卖出不同质。<br>
4. <b>窗口</b>：2021-06 基准起点 ~ 2026-08 数据末月（63 个月），策略首个持仓月 2021-08。
与 ZHF-cons 上轮同窗口可比。<br>
5. <b>幸存者偏差残余</b>：价格仅覆盖当期成分内股票；已退市股票当月不参与等权基准收益
（轻微高估基准/低估策略超额）。<br>
6. <b>北交所缺失</b>：腾讯月K不支持北交所(bj)代码，BJ 成分无价格（每期缺失 1.9%~5.6%），
对策略组合影响可忽略，对等权基准有轻微低估。<br>
7. <b>信号→成交时点</b>：调仓日数据快照与月末收盘同月（与龙头池版一致，保证可比）；
严格做法应延后一个月执行，实际影响小但存在。<br>
8. <b>组合构造</b>：全市场无产业链方向映射（link=None），方向轮动层退化为纯个股信念；
A/B/C 类配比(60/35/5) + 单票5% + top-40 集中度。
</div>

</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const labels = {chart_labels};
const series = {series_js};
new Chart(document.getElementById('nav'), {{
  type: 'line',
  data: {{ labels, datasets: series }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ labels: {{ boxWidth: 14, font: {{ size: 12 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 12 }} }},
      y: {{ ticks: {{ callback: v => v + '%' }} }}
    }}
  }}
}});
</script></body></html>"""

    open(OUT, "w", encoding="utf-8").write(html)
    print(f"报告 → {OUT} ({os.path.getsize(OUT)/1024:.0f}KB)")


if __name__ == "__main__":
    main()
