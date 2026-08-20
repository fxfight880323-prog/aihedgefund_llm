"""万得全A全市场回测 — HTML 报告生成。

输入 _bt_winda_results.json → 输出 _zhf_winda_report.html
"""
from __future__ import annotations

import json
import os

OUT = "_zhf_winda_report.html"


def main():
    r = json.loads(open("_bt_winda_results.json", encoding="utf-8").read())
    zhf, c, ew = r["zhf"], r["c"], r["ew"]
    idx = r.get("idx")
    diag = r["diag"]
    contrib = r["contrib"]
    weights = r["weights_zhf"]

    # 名称映射（尽量给中文名 —— 用共识缓存里的股票代码，无名称字段则用代码）
    def pct(x, d=1):
        return f"{x * 100:+.{d}f}%"

    rows = []
    for x in (zhf, c, ew, idx):
        if x is None:
            continue
        rows.append(f"""
        <tr>
          <td class="{'hl' if x['name'].startswith('ZHF') else ''}">{x['name']}</td>
          <td>{pct(x['total'])}</td>
          <td>{pct(x['ann'])}</td>
          <td>{'—' if x.get('mdd') is None else pct(x['mdd'])}</td>
          <td>{'—' if x.get('excess_ew') is None else pct(x['excess_ew'])}</td>
          <td>{'—' if x.get('excess_idx') is None else pct(x['excess_idx'])}</td>
        </tr>""")

    # NAV 数据
    months = sorted(ew["nav"][0]["month"] for _ in [0])  # placeholder
    navs = {}
    for x in (zhf, c, ew, idx):
        if x and x.get("nav"):
            navs[x["name"]] = {d["month"]: d["nav"] for d in x["nav"]}
    all_months = sorted({m for v in navs.values() for m in v})
    # 归一化到各自起点（策略 NAV 以 100 万起，EW/指数已是 1）
    norm = {}
    for k, v in navs.items():
        if not v:
            continue
        base = v[all_months[0]] if all_months[0] in v else 1.0
        norm[k] = [round((v.get(m, 0) / base - 1) * 100, 2) if v.get(m) else None
                   for m in all_months]

    chart_labels = json.dumps(all_months)
    series = []
    colors = {"ZHF-cons 全市场": "#d33", "C-cons 全市场": "#e88",
              "EW-全A": "#666", "CSI-全指": "#2a6"}
    for k, v in norm.items():
        series.append(
            '{"label": %s, "data": %s, "borderColor": %s, '
            '"backgroundColor": %s, "fill": false, "tension": 0.15, "borderWidth": %s}'
            % (json.dumps(k), json.dumps(v), json.dumps(colors.get(k, "#333")),
               json.dumps(colors.get(k, "#333") + "22"),
               2.5 if k.startswith("ZHF") else 1.5))
    series_js = "[" + ",".join(series) + "]"

    # 逐期诊断表
    period_rows = []
    for m in sorted(diag.keys()):
        d = diag[m]
        cls = d.get("zhf_cls", {})
        cls_s = " ".join(f"{k}:{v}" for k, v in cls.items())
        period_rows.append(f"""
        <tr>
          <td>{m}</td><td>{d['univ']}</td><td>{d['cov']}</td>
          <td>{d['zhf_hold']}</td><td>{cls_s}</td><td>{d['c_hold']}</td>
        </tr>""")

    # ---- 新增：龙头池版对比 + 关键结论 ----
    pool_rows = """
        <tr><td>ZHF-cons（龙头池 58 只）</td><td>+329.1%</td><td>+30.7%</td><td>-27.0%</td></tr>
        <tr><td>C-cons（龙头池 58 只）</td><td>+434.0%</td><td>+38.3%</td><td>-30.4%</td></tr>
        <tr><td>龙头池等权（58 只）</td><td>+455.0%</td><td>+39.4%</td><td>—</td></tr>
        <tr class="sep"><td>ZHF-cons（万得全A）</td><td>-7.3%</td><td>-1.4%</td><td>-36.6%</td></tr>
        <tr><td>C-cons（万得全A）</td><td>+0.1%</td><td>+0.0%</td><td>-33.1%</td></tr>
        <tr><td>等权万得全A</td><td>+52.9%</td><td>+8.4%</td><td>—</td></tr>
        <tr><td>中证全指 000985.SH</td><td>+0.2%</td><td>+0.0%</td><td>—</td></tr>
    """
    # 板块分布（主板 vs 创业板/科创板）从权重反推
    def board_share(w: dict) -> str:
        tot = len(w)
        if not tot:
            return "-"
        cyb = sum(1 for t in w if t.split('.')[0].startswith(('300', '301')))
        kcb = sum(1 for t in w if t.split('.')[0].startswith('688'))
        return f"主板 {tot-cyb-kcb}/{tot} · 创 {cyb} · 科 {kcb}"

    diag_rows = []
    for m in sorted(weights.keys()):
        w = weights[m]
        cls = diag.get(m, {}).get("zhf_cls", {})
        cls_s = " ".join(f"{k}:{v}" for k, v in cls.items())
        diag_rows.append(f"""
        <tr><td>{m}</td><td>{board_share(w)}</td><td>{cls_s}</td></tr>""")

    # 持仓明细（最新一期 + 每期top贡献）
    last_p = sorted(weights.keys())[-1]
    hold_rows = []
    for tk, w in sorted(weights[last_p].items(), key=lambda kv: -kv[1]):
        hold_rows.append(f"<tr><td>{tk}</td><td>{w:.1%}</td></tr>")

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

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>章宏帆框架 × 一致预期 · 万得全A 全市场回测</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f7f8fa; color: #1c1e21; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }}
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
  tr.sep td {{ border-top: 2px solid #a00; background: #fdf0ef; }}
  .caveat {{ background: #fff8e6; border: 1px solid #f0d9a8; border-radius: 8px; padding: 14px 18px; margin-top: 14px; font-size: 13px; line-height: 1.7; }}
</style></head><body><div class="wrap">
<h1>章宏帆框架 × 分析师一致预期 — 万得全A 全市场回测</h1>
<h3>池子=万得全A(881001.WI) 每期PIT成分（4441→5503只）｜2021-08 ~ 2026-04 十期半年调仓｜成本 5bp+10bp｜vnpy 引擎</h3>

<div class="card">
<h2>总览（对比等权全A —— 方法论铁律）</h2>
<table>
<tr><th>策略</th><th>总收益</th><th>年化</th><th>最大回撤</th>
<th>超额(等权全A)</th><th>超额(中证全指)</th></tr>
{''.join(rows)}
</table>
</div>

<div class="card">
<h2>关键结论（先看这个）</h2>
<div class="concl">
<p><b>① 池子beta淹没alpha，在龙头池版得到实证。</b> 龙头池 58 只等权 5 年 +455%，而中证全指同期 +0.2% —— 池子本身即史诗级超额收益。章宏帆框架×一致预期在该池跑出的 +329%/+434%，绝大部分是<b>池子beta+幸存者偏差</b>，不是框架alpha。</p>
<p><b>② 全市场诚实回测：框架alpha≈0。</b> 同一套信号、同一引擎、同成本，把池子换成万得全A每期PIT成分后，ZHF-cons 全市场 <b>-7.3%</b>（超额等权全A <b>-60.2pp</b>）、C-cons <b>+0.1%</b>（超额 <b>-52.9pp</b>）。对照中证全指（分析师覆盖股票的市值加权代理），ZHF 仅跑输 7.5pp、C-cons 跑平 —— <b>一致预期信号在全市场没有创造正alpha</b>。</p>
<p><b>③ 主要失血=风格错配，不是选股。</b> ZHF 持仓长期 80-90% 主板大中盘（分析师覆盖集中区，2021期 92.5% 主板），而等权全A 的 +52.9% 主要来自创业板/科创板小盘。策略在 2022-04、2024-04 熊市月超额为正（+6.2pp/+3.5pp），2026 年小盘行情中连续超额为负（-3.8pp/-3.5pp）。</p>
<p><b>④ MDD 不降反升。</b> 全市场版 MDD -36.6% 远高于龙头池版 -27.0% —— 池子的质量过滤才是原框架真正的回撤防线，框架自身的 A/B/C 类配比+估值护栏在全市场不提供下行保护。</p>
</div>
</div>

<div class="card">
<h2>与龙头池版对比（窗口近似：池子版 2021-08~2026-04，全市场版 2021-06~2026-08）</h2>
<table>
<tr><th>策略</th><th>总收益</th><th>年化</th><th>最大回撤</th></tr>
{pool_rows}
</table>
</div>

<div class="card">
<h2>净值曲线（相对起点累计收益 %）</h2>
<canvas id="nav" style="width:100%;height:380px"></canvas>
</div>

<div class="card">
<h2>逐期筛选诊断</h2>
<table>
<tr><th>调仓期</th><th>万得全A成分</th><th>一致预期覆盖</th>
<th>ZHF持仓数</th><th>ZHF A/B/C/OFF</th><th>C-Score持仓数</th></tr>
{''.join(period_rows)}
</table>
</div>

<div class="card">
<h2>ZHF 持仓板块分布（主板/创业板/科创板）</h2>
<table>
<tr><th>调仓期</th><th>板块分布</th><th>A/B/C/OFF 类别</th></tr>
{''.join(diag_rows)}
</table>
</div>

<div class="card">
<h2>最新一期持仓（{last_p}）</h2>
<table><tr><th>代码</th><th>权重</th></tr>
{''.join(hold_rows)}
</table>
</div>

<div class="card">
<h2>逐期个股贡献（ZHF-cons，Top 8）</h2>
{contrib_html}
</div>

<div class="caveat">
<h3 style="margin-top:0">诚实声明（必须读）</h3>
1. <b>数据源</b>：成分股=juzi 万得全A(881001.WI) PIT 快照；一致预期=朝阳永续 con_forecast_stk PIT 快照（snapshot 日期≤调仓日，无未来函数）；价格=腾讯月K前复权。<br>
2. <b>万得全A指数本身无公开行情序列</b>，市值加权基准用中证全指(000985.SH) 替代；更严格的无池子偏差基准是<b>等权万得全A NAV</b>（用 PIT 成分+真实月K计算），超额以它为准。<br>
3. <b>幸存者偏差残余</b>：价格仅覆盖当期成分内股票；已退市股票当月不参与等权基准收益（轻微高估基准/低估策略超额）。<br>
4. <b>北交所缺失</b>：腾讯月K接口不支持北交所(bj)代码，310 只 BJ 成分无价格（每期缺失率 1.9%~5.6%，多为2023年后扩容）；其中仅 9 只曾被一致预期覆盖，对策略组合影响可忽略，对等权基准有轻微低估（北交所小盘涨幅未被计入）。<br>
5. <b>信号→成交时点</b>：调仓日数据快照与月末收盘同月（与龙头池版一致，保证可比）；严格做法应延后一个月执行，实际影响小但存在。<br>
6. <b>方法论适配</b>：全市场无产业链方向映射（link=None），方向轮动层退化为纯个股信念；A/B/C 分类、估值护栏、类配比、单票上限均保留原框架。组合构造由"方向内选龙头"改为"全市场信念 top-40 + 类配比约束"（龙头池版持仓 8-32 只，本版统一 ≤40 只）。<br>
7. 组合构造差异：C-cons 基线在龙头池版为全信号等权（≤10% 单票），全市场版改为与 ZHF 相同的 top-40 构造（口径一致才可比）。<br>
8. <b>龙头池对比窗口</b>：池子版为 2021-08~2026-04，全市场版为 2021-06~2026-08（63 个月），窗口不完全一致，对比仅作量级参考。
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
