# -*- coding: utf-8 -*-
"""毛利率质量层 · 阈值实现差异专题报告（juzi 版修正后交叉验证）。

问题：juzi 版 LX-gm（毛利率≥全市场中位数, 动态）结论"有效(收益持平MDD砍半)"，
     申万版 sw_gm（毛利率≥30% 固定阈值）结论"拖累(+3.5%, 2022暴亏)"。
修正：juzi 版新增 gm25/gm30/gm35 固定阈值变体，与申万 sw_gm 设定对齐，
     验证"动态中位数 vs 固定阈值"是否是结论不一致的根源。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lx_sw_data import SW_RESULTS, SW_NAV, SW_NAV_BENCH

BASE = os.path.dirname(os.path.abspath(__file__))
JUZI_FILE = os.path.join(BASE, "_bt_lx_allA_results.json")
OUT = os.path.join(BASE, "_lx_gm_check.html")

ORDER = ["core", "gm", "gm25", "gm30", "gm35", "full"]


def pct(x, nd=1):
    if x is None:
        return "—"
    return f"{x * 100:+.{nd}f}%"


def annual_from_nav(nav):
    by_month = {r["month"]: r["nav"] for r in nav}
    months = sorted(by_month)
    out = {}
    years = sorted({m[:4] for m in months})
    for i, y in enumerate(years):
        ym = [m for m in months if m[:4] == y]
        if not ym:
            continue
        end = by_month[ym[-1]]
        start = by_month[ym[0]] if i == 0 else by_month[[m for m in months if m[:4] == years[i - 1]][-1]]
        out[int(y)] = end / start - 1.0
    return out


def main():
    j = json.load(open(JUZI_FILE, encoding="utf-8"))
    results = j["results"]
    diag = j["diag"]
    bench_ew = j["bench_ew"]

    # ---- ① 绩效对比表 ----
    rows = []
    for k in ORDER:
        r = results[k]
        hl = ' class="hl"' if k in ("gm", "gm30") else ""
        rows.append(f"""
        <tr{hl}><td><b>{k.upper() if k != 'core' else 'LX-core'}</b>
          <span class="sub">{'毛利率≥市场中位数(动态)' if k == 'gm' else ('毛利率≥%s%%(固定)' % k[2:] if k.startswith('gm') and k != 'gm' else ('完整近似' if k == 'full' else '基准(无质量层)'))}</span></td>
          <td class="num">{pct(r['total'])}</td>
          <td class="num">{pct(r['ann'])}</td>
          <td class="num">{pct(r['mdd'])}</td>
          <td class="num">{pct(r['excess_ew'])}</td></tr>""")
    rows.append(f"""
        <tr><td>EW-全A（等权基准）</td><td class="num">{pct(j['ew']['total'])}</td>
          <td class="num">{pct(j['ew']['ann'])}</td><td class="num">—</td>
          <td class="num">0.0%</td></tr>""")

    # ---- ② 申万版对照行 ----
    sw_rows = []
    for sw_k, label in [("sw_core", "LX-core近似"), ("sw_gm", "LX-gm近似(固定30%)")]:
        s = SW_RESULTS[sw_k]
        sw_rows.append(f"""
        <tr><td><b>{label}</b></td>
          <td class="num">{pct(s['total_return'])}</td>
          <td class="num">{pct(s['annual_return'])}</td>
          <td class="num">{pct(s['max_drawdown'])}</td>
          <td class="num">{pct(s['total_return'] - (-0.0257))}</td></tr>""")

    # ---- ③ 每期 gpm 中位数 vs 阈值（直接从因子面板计算）----
    import statistics
    fac = json.load(open(os.path.join(BASE, "_bt_lx_allA_factors.json"),
                         encoding="utf-8"))
    gpm_rows = []
    for m in sorted(diag.keys()):
        recs = fac.get(m, {}).get("records", [])
        g = [r["gpm"] for r in recs
             if r.get("gpm") is not None and r["gpm"] == r["gpm"]]
        gmed = statistics.median(g) if g else None
        gm_pass = d.get("gm_pass", 0) if (d := diag.get(m)) else 0
        g30_pass = d.get("gm30_pass", 0)
        gmed_s = f"{gmed:.1f}%" if gmed is not None else "—"
        pos = ("30%高于中位数" if (gmed is not None and gmed < 30.0)
               else "30%≤中位数")
        gpm_rows.append(f"""
        <tr><td>{m}</td><td class="num">{gmed_s}</td>
          <td class="num">{pos}</td>
          <td class="num">{gm_pass}</td><td class="num">{g30_pass}</td></tr>""")

    # ---- ④ 净值对比（juzi 版 gm vs gm30 vs core）----
    months = [r["month"] for r in results["core"]["nav"]]
    base_m = months[0]
    series = []
    def series_js(label, nav, color, dash=None):
        b = {r["month"]: r["nav"] for r in nav}[base_m]
        data = [round(({r["month"]: r["nav"] for r in nav}[m] / b - 1) * 100, 2)
                for m in months]
        dash_js = f',"borderDash": {dash}' if dash else ""
        return ('{"label": %s, "data": %s, "borderColor": %s, "fill": false, '
                '"tension": 0.15, "borderWidth": 2%s}'
                % (json.dumps(label), json.dumps(data), json.dumps(color), dash_js))
    s = [series_js("LX-core", results["core"]["nav"], "#8a6d3b"),
         series_js("LX-gm(≥市场中位)", results["gm"]["nav"], "#1a7f37"),
         series_js("LX-gm30(≥30%固定)", results["gm30"]["nav"], "#8250df", "[5,3]"),
         series_js("LX-full", results["full"]["nav"], "#c62828")]
    s.append('{"label": "EW-全A", "data": %s, "borderColor": "#666", "fill": false, '
             '"tension": 0.1, "borderWidth": 1.6, "borderDash": [6,4]}'
             % json.dumps([round((bench_ew[m] / bench_ew[base_m] - 1) * 100, 2)
                           for m in months]))

    # ---- ⑤ 年度收益（juzi gm vs gm30）----
    ann = {k: annual_from_nav(results[k]["nav"]) for k in ["core", "gm", "gm30", "gm35"]}
    ew_ann = annual_from_nav([{"month": m, "nav": v} for m, v in bench_ew.items()])
    y_rows = []
    for y in [2022, 2023, 2024, 2025, 2026]:
        y_rows.append(f"""
        <tr><td>{y}</td>
          <td class="num">{pct(ann['core'].get(y))}</td>
          <td class="num">{pct(ann['gm'].get(y))}</td>
          <td class="num">{pct(ann['gm30'].get(y))}</td>
          <td class="num">{pct(ann['gm35'].get(y))}</td>
          <td class="num">{pct(ew_ann.get(y))}</td></tr>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>毛利率质量层 · 阈值实现差异归因</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 body {{ font-family: "Microsoft YaHei", sans-serif; margin: 24px 40px;
        background: #fafafa; color: #222; }}
 h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; margin-top: 30px;
        border-left: 4px solid #8250df; padding-left: 10px; }}
 .sub {{ color: #666; font-size: 13px; margin-top: -8px; }}
 table {{ border-collapse: collapse; margin: 12px 0; font-size: 13.5px;
         background: #fff; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 12px; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 th {{ background: #f0f0f0; }} td:first-child {{ text-align: left; }}
 tr.hl {{ background: #f3e8ff; }}
 .pos {{ color: #c62828; }} .neg {{ color: #1b5e20; }}
 .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
         padding: 14px 18px; margin: 10px 0; font-size: 13.5px; line-height: 1.75; }}
 .verdict {{ border-left: 4px solid #1a7f37; background: #f1f8e9; }}
 .warn {{ border-left: 4px solid #e65100; background: #fff8e1; }}
 .note {{ color: #888; font-size: 12px; }}
 canvas {{ background: #fff; border: 1px solid #eee; }}
 .sub2 {{ display:block; font-size: 11px; color: #888; font-weight: 400; }}
</style></head><body>

<h1>毛利率质量层 · 阈值实现差异归因（juzi 版修正后交叉验证）</h1>
<p class="sub">池子 = 万得全A(881001.WI) PIT 成分 · 半年度调仓 · 2021-08 ~ 2026-06 ·
成本 5bp+10bp · juzi 真实数据（估值面板 / HF因子 / 一致预期 / 腾讯月K）· 2026-08-21 生成</p>

<div class="card verdict">
<b>核心结论：</b>juzi 版加入与申万版一致的 <b>固定 30% 阈值</b> 变体后，两数据源结论<b>收敛统一</b>：
① 毛利率层的价值是<b>回撤保护</b>，保护强度依赖<b>动态中位数阈值</b>（gm MDD -13.9% vs gm30 -21.0%）；
② 固定 30% 本身不亏钱（juzi gm30 总收益 +62.5% 正常），申万版暴亏（+3.5%）的主因是
<b>月度调仓 + 缺 L5 低预期过滤</b>，阈值差异只是放大器。
</div>

<h2>① juzi 版绩效对比（修正后, 半年度调仓, 超额对等权全A）</h2>
<table>
<tr><th>变体</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额 vs 等权全A</th></tr>
{''.join(rows)}
</table>

<h2>② 申万版对照（月度调仓, 零成本, 超额对沪深300）</h2>
<table>
<tr><th>变体</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额 vs 沪深300</th></tr>
{''.join(sw_rows)}
</table>
<p class="note">两版超额基准不同不可直接横比；对比重点是<b>同一版内 gm 相对 core 的增量贡献方向</b>。</p>

<h2>③ 每期全市场 gpm 中位数 vs 固定30% 阈值位置（juzi 版）</h2>
<table>
<tr><th>调仓期</th><th>全市场 gpm 中位数</th><th>30% 相对位置</th>
<th>gm(≥中位)命中</th><th>gm30(≥30%)命中</th></tr>
{''.join(gpm_rows)}
</table>

<h2>④ 净值对比（juzi 版, 累计收益 %）</h2>
<canvas id="nav" height="110"></canvas>

<h2>⑤ 年度收益（juzi 版）</h2>
<table>
<tr><th>年度</th><th>core</th><th>gm(≥中位)</th><th>gm30(≥30%)</th><th>gm35(≥35%)</th><th>等权全A</th></tr>
{''.join(y_rows)}
</table>

<h2>⑥ 归因结论（修正后）</h2>
<div class="card warn">
<b>1. 阈值实现影响的是"回撤保护强度"，不是收益方向</b> — juzi 版固定 30% 没有暴亏：
gm30 总收益 +62.5%（超额 +9.6%，甚至略高于 core 的 +7.1%），但 MDD 从 gm 的 -13.9%
恶化到 -21.0%（接近 core 的 -24.9%）。2022 熊市 gm30 -16.4% vs gm -10.3% vs core -8.9%，
2023 反弹 gm30 +26.8% 最强 —— 固定阈值把高毛利板块（医药/软件/出版/消费）集中度抬高，
波动加大、熊市防御变差。毛利率层的价值在于<b>回撤保护</b>，而保护强度依赖
<b>动态中位数（每期自适应）</b>：固定阈值越高保护越弱。
</div>
<div class="card warn">
<b>2. 申万版 sw_gm 暴亏的主因是月度调仓 + 缺 L5，而非固定 30% 本身</b> —
juzi 版在相同固定 30% 阈值、但<b>半年度调仓 + 保留 L5 低预期过滤</b>下总收益 +62.5% 正常；
申万版月度调仓 + 无 L5 → +3.5%、2022 年 -21.6%。月度重选每月买入"高毛利+低估值"，
2022 年医药/出版杀跌时<b>持续接刀、反复反向轮动</b>，亏损被高频调仓放大；
L5（预期增速≤25% 且 0&lt;PEG≤2）拦截了高预期接盘，是 juzi 版没暴亏的第二道防线。
</div>
<div class="card verdict">
<b>3. 跨数据源结论统一</b> — 修正前"两版 gm 结论相反"的真相：
不是数据源矛盾，而是<b>三个实现参数未对齐</b>（阈值形态 / 调仓频率 / L5 有无）。
对齐后收敛为：<b>毛利率质量层仅在"半年度持有 + 动态中位数阈值"组合下稳健（MDD 砍半）</b>；
换成固定阈值→回撤保护消失；再叠加月度高频→退化为亏损。
</div>
<div class="card warn">
<b>4. 方法论铁律升级</b> — 任何质量层变体做跨数据源验证，必须<b>先对齐三要素</b>：
①阈值形态（动态分位 vs 固定值）②调仓频率 ③前置过滤层（L5 等）。否则差异可能全部
来自实现细节而非策略本质。申万版如无一致预期数据，gm 层应改跑"全市场毛利率分位≥50%"
的动态形态，而非固定 30%。
</div>

<p class="note">本报告为研究参考，不构成投资建议。juzi 版数据：_bt_lx_allA_results.json（2026-08-21 修正版, 12 变体）；申万版数据：_lx_sw_data.py。</p>

<script>
const labels = {json.dumps(months)};
new Chart(document.getElementById('nav'), {{
  type: 'line',
  data: {{ labels: labels, datasets: [{','.join(s)}] }},
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
    print("报告 →", OUT)


if __name__ == "__main__":
    main()
