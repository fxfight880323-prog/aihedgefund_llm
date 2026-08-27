# -*- coding: utf-8 -*-
"""刘旭框架 5 年回测 · juzi(全A诚实版) vs 申万MCP(近似版) 交叉验证报告."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lx_sw_data import (SW_RESULTS, SW_BENCH, SW_NAV, SW_NAV_BENCH, JUZI_MAP)

BASE = os.path.dirname(os.path.abspath(__file__))
JUZI_FILE = os.path.join(BASE, "_bt_lx_allA_results.json")


def load_juzi():
    d = json.load(open(JUZI_FILE, encoding="utf-8"))
    return d


def annual_from_nav(nav: list[dict]) -> dict:
    """从 [{month,nav}] 计算年度收益: 12月/上年12月 - 1; 首年用起始月。"""
    by_month = {r["month"]: r["nav"] for r in nav}
    months = sorted(by_month)
    out = {}
    years = sorted({m[:4] for m in months})
    for i, y in enumerate(years):
        ym = [m for m in months if m[:4] == y]
        if not ym:
            continue
        end = by_month[ym[-1]]
        if i == 0:
            start = by_month[ym[0]]
        else:
            prev_y = years[i - 1]
            prev_ym = [m for m in months if m[:4] == prev_y]
            start = by_month[prev_ym[-1]]
        out[int(y)] = end / start - 1.0
    return out


def pct(x, nd=1):
    if x is None:
        return "—"
    return f"{x * 100:+.{nd}f}%"


def main():
    j = load_juzi()
    juzi_res = j["results"]
    ew_total = j["ew"]["total"]
    idx_total = j["idx"]["total"]

    # juzi 年度收益
    juzi_ann = {k: annual_from_nav(v["nav"]) for k, v in juzi_res.items()}
    ew_nav = j["bench_ew"]
    ew_ann = annual_from_nav([{"month": m, "nav": v} for m, v in ew_nav.items()])

    # 申万版年度收益（已在 SW_RESULTS 里）
    sw_ann = {k: v["annual_table"] for k, v in SW_RESULTS.items()}

    # ---------- 汇总指标行 ----------
    rows = []
    for k, v in SW_RESULTS.items():
        jk = JUZI_MAP[k]
        jr = juzi_res[jk]
        rows.append({
            "sw_key": k, "jz_key": jk,
            "sw_name": v["name"], "jz_name": f"LX-{jk}",
            "sw_desc": v["desc"],
            "sw_total": v["total_return"], "jz_total": jr["total"],
            "sw_ann": v["annual_return"], "jz_ann": jr["ann"],
            "sw_mdd": v["max_drawdown"], "jz_mdd": jr["mdd"],
            "sw_sharpe": v["sharpe"],
            "sw_exc": v["total_return"] - SW_BENCH["total_return"],
            "jz_exc": jr.get("excess_ew"),
        })

    # ---------- 净值 SVG ----------
    def flatten(by_year):
        pts = []
        for y_vals in by_year:
            for x in y_vals:
                pts.append(x)
        return pts

    series = [
        ("LX-core近似", flatten(SW_NAV["sw_core"]), "#c0392b"),
        ("LX-纯便宜", flatten(SW_NAV["sw_nomv"]), "#e67e22"),
        ("LX-gm近似", flatten(SW_NAV["sw_gm"]), "#8e44ad"),
        ("沪深300", flatten(SW_NAV_BENCH), "#95a5a6"),
    ]
    n = len(series[0][1])
    W, H, PAD_L, PAD_R, PAD_T, PAD_B = 900, 340, 60, 16, 24, 30
    all_v = [x for _, s, _ in series for x in s]
    vmin, vmax = min(all_v), max(all_v)
    vmin = min(vmin, 0.6)
    vmax = max(vmax, 1.5)
    def X(i): return PAD_L + i * (W - PAD_L - PAD_R) / (n - 1)
    def Y(v): return PAD_T + (vmax - v) / (vmax - vmin) * (H - PAD_T - PAD_B)

    svg = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           'style="width:100%;height:auto;background:#fff;border-radius:10px">']
    # 网格
    for g in [0.6, 0.8, 1.0, 1.2, 1.4]:
        svg.append(f'<line x1="{PAD_L}" y1="{Y(g)}" x2="{W - PAD_R}" y2="{Y(g)}" '
                   f'stroke="#eceff1" stroke-width="1"/>')
        svg.append(f'<text x="{PAD_L - 6}" y="{Y(g) + 4}" font-size="11" '
                   f'fill="#90a4ae" text-anchor="end">{g:.1f}</text>')
    # x 轴年刻度
    year_marks = [(2021, 9), (2022, 0), (2023, 0), (2024, 0), (2025, 0), (2026, 0)]
    for y, m in year_marks:
        idx = (y - 2021) * 12 + m
        if idx >= n:
            continue
        svg.append(f'<text x="{X(idx)}" y="{H - 8}" font-size="11" fill="#90a4ae" '
                   f'text-anchor="middle">{y}</text>')
    # 折线
    for name, pts, color in series:
        d = "M" + " L".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(pts))
        svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" '
                   f'stroke-linejoin="round"/>')
    # 图例
    lx = PAD_L + 8
    for name, pts, color in series:
        svg.append(f'<rect x="{lx}" y="{PAD_T - 16}" width="14" height="4" rx="2" '
                   f'fill="{color}"/>')
        svg.append(f'<text x="{lx + 18}" y="{PAD_T - 12}" font-size="11" '
                   f'fill="#37474f">{name}</text>')
        lx += 26 + len(name) * 11
    svg.append("</svg>")
    nav_svg = "".join(svg)

    # ---------- 年度收益条形 ----------
    years_bar = [2022, 2023, 2024, 2025, 2026]
    bar_html = []
    for y in years_bar:
        bar_html.append(
            f'<tr><td class="y">{y}</td>'
            f'<td>{pct(sw_ann["sw_core"].get(y))}</td>'
            f'<td>{pct(juzi_ann["core"].get(y))}</td>'
            f'<td>{pct(sw_ann["sw_gm"].get(y))}</td>'
            f'<td>{pct(juzi_ann["gm"].get(y))}</td>'
            f'<td>{pct(ew_ann.get(y))}</td></tr>')
    bar_body = "".join(bar_html)

    # ---------- 指标表 ----------
    rows_html = ""
    for r in rows:
        rows_html += f"""
        <tr>
          <td><b>{r['sw_name']}</b><br><span class="sub">{r['sw_desc']}</span></td>
          <td>{r['jz_name']}</td>
          <td class="num">{pct(r['sw_total'])}<span class="sub">/{pct(r['jz_total'])}</span></td>
          <td class="num">{pct(r['sw_ann'])}<span class="sub">/{pct(r['jz_ann'])}</span></td>
          <td class="num">{pct(r['sw_mdd'])}<span class="sub">/{pct(r['jz_mdd'])}</span></td>
          <td class="num">{pct(r['sw_exc'])}<span class="sub">/{pct(r['jz_exc'])}</span></td>
          <td class="num">{r['sw_sharpe']:.2f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>刘旭框架 5 年回测 · 双数据源交叉验证</title>
<style>
  body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
       background:#f5f7fa;color:#263238;margin:0;padding:24px}}
  .wrap{{max-width:980px;margin:0 auto}}
  h1{{font-size:22px;margin:0 0 4px}}
  .meta{{color:#78909c;font-size:12px;margin-bottom:18px}}
  h2{{font-size:16px;margin:28px 0 10px;border-left:4px solid #c0392b;
     padding-left:10px}}
  .card{{background:#fff;border-radius:10px;padding:18px 20px;
        box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:14px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th,td{{padding:8px 10px;border-bottom:1px solid #eceff1;text-align:left}}
  th{{color:#607d8b;font-weight:600;font-size:12px;background:#fafbfc}}
  td.num{{text-align:right;font-variant-numeric:tabular-nums}}
  .sub{{display:block;font-size:11px;color:#90a4ae;font-weight:400}}
  .tag{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;
       margin-right:6px}}
  .ok{{background:#e8f5e9;color:#2e7d32}}
  .warn{{background:#fff3e0;color:#e65100}}
  .diff{{background:#fce4ec;color:#c62828}}
  .note{{font-size:12px;color:#546e7a;line-height:1.7}}
  .kpi{{display:flex;gap:14px;flex-wrap:wrap}}
  .kpi .box{{flex:1;min-width:150px;background:#fff;border-radius:10px;
            padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
  .kpi .v{{font-size:20px;font-weight:700}}
  .kpi .l{{font-size:11px;color:#90a4ae;margin-top:2px}}
  .red{{color:#c0392b}} .green{{color:#27ae60}}
  .concl{{border-left:4px solid #2e7d32;background:#f1f8e9;padding:12px 16px;
          border-radius:0 8px 8px 0;font-size:13px;line-height:1.8}}
  .concl.warn{{border-color:#e65100;background:#fff8e1}}
</style></head><body><div class="wrap">

<h1>刘旭选股框架 · 过去 5 年回测</h1>
<div class="meta">双数据源交叉验证 · juzi(万得全A PIT成分, 半年度调仓) vs 申万金工MCP(全A, 月度调仓) ·
2026-08-21 生成</div>

<div class="card">
<h2 style="margin-top:0">① 核心结论（摘要）</h2>
<div class="kpi">
  <div class="box"><div class="v red">+23.7%</div><div class="l">申万版 LX-core 5年总收益</div></div>
  <div class="box"><div class="v red">+60.0%</div><div class="l">juzi版 LX-core 5年总收益</div></div>
  <div class="box"><div class="v red">+26.3pp</div><div class="l">申万版超额(沪深300)</div></div>
  <div class="box"><div class="v red">+7.1pp</div><div class="l">juzi版超额(等权全A)</div></div>
  <div class="box"><div class="v">-22.6%</div><div class="l">申万版最大回撤</div></div>
</div>
</div>

<div class="card">
<h2 style="margin-top:0">② 方法论对比</h2>
<table>
<tr><th style="width:16%">维度</th><th>juzi 全A诚实版（基准实验）</th><th>申万MCP 近似版（本次交叉验证）</th></tr>
<tr><td>股票池</td><td>万得全A 881001.WI PIT 成分（4441→5500只）</td><td>全A universe（~5617只, 2026-07-31）</td></tr>
<tr><td>调仓频率</td><td>半年度（2021-08 起 10 期）</td><td>月度（59 个月, 每月末重选）</td></tr>
<tr><td>筛选器</td><td>L4(PE≤25或股息率≥2%) + L5(预期增速≤25%且0&lt;PEG≤2) + 市值≥100亿 + PE&gt;0</td><td>PE≤25 + 市值≥100亿 + 估值因子top40（<b>缺 L5 一致预期约束</b>, 申万无预期数据）</td></tr>
<tr><td>排序信念</td><td>PE 升序（便宜优先）</td><td>估值因子高分前40（官方正向: 值大=估值低=便宜）→ 等价</td></tr>
<tr><td>组合</td><td>top-40 等权, 单票5%, 成本5bp+10bp</td><td>top-40 等权, 零交易成本（工具固定）</td></tr>
<tr><td>基准</td><td>等权万得全A NAV（PIT成分+真实月K）+52.9% / 中证全指 +0.2%</td><td>沪深300（申万自动对标）-2.6%</td></tr>
<tr><td>数据源</td><td>juzi 估值面板 + HF因子 + 一致预期（PIT快照）</td><td>申万月度指标 + 16因子（z-score横截面）</td></tr>
</table>
</div>

<div class="card">
<h2 style="margin-top:0">③ 核心指标对比（申万版 / juzi版）</h2>
<table>
<tr><th>变体</th><th>juzi 对应</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>超额</th><th>夏普(申万)</th></tr>
{rows_html}
</table>
<p class="note">超额口径不同不可直接横比：申万版超额对沪深300，juzi版超额对等权全A（+52.9%）。同一行内"申万/juzi"两值可比。</p>
</div>

<div class="card">
<h2 style="margin-top:0">④ 净值曲线（申万版, 2021-09 ~ 2026-07）</h2>
{nav_svg}
</div>

<div class="card">
<h2 style="margin-top:0">⑤ 年度收益对比</h2>
<table>
<tr><th>年度</th><th>申万 core</th><th>juzi core</th><th>申万 gm</th><th>juzi gm</th><th>等权全A</th></tr>
{bar_body}
</table>
<p class="note">juzi版 2026 仅至 2026-04；申万版 2026 至 2026-07。2021 各版本起始月不同故省略。</p>
</div>

<div class="card">
<h2 style="margin-top:0">⑥ 交叉验证结论</h2>
<div class="concl">
<b>1. 核心alpha在独立数据源上复现 ✅</b> — "便宜优先 + 大市值保护"的深度价值筛选，无论用 juzi 半年度还是申万月度，5年都显著跑赢沪深300（申万版超额 +26.3pp）。深度价值逻辑不是单一数据源的产物。
</div>
<div class="concl warn" style="margin-top:10px">
<b>2. 市值保护结论一致 ✅</b> — 申万版 加市值≥100亿 比不加好（+23.7% vs +16.1%, MDD -22.6% vs -24.2%）；juzi版同样 mv100(+7.1pp) &gt; mv30(-5.8pp) &gt; mv0(-3.1pp)。两个独立实现都指向：100亿下限是质量保护而非风格暴露。
</div>
<div class="concl warn" style="margin-top:10px">
<b>3. 毛利率质量层结论已修正，两版统一 ✅</b> — juzi 版新增 gm25/gm30/gm35 固定阈值变体后（详见 <code>_lx_gm_check.html</code>），原"gm 结论相反"澄清为三个实现参数未对齐：①阈值形态：juzi gm(≥动态中位数) MDD -13.9% 砍半 vs gm30(≥固定30%) -21.0% 保护消失，但 gm30 总收益 +62.5% 并不亏损；②调仓频率：申万月度调仓 2022 年反复接刀高毛利板块（医药/出版）杀跌，才是 sw_gm 暴亏(+3.5%)的主因；③L5 缺失：申万无一致预期过滤，拦截不了高预期接盘。<b>统一结论：毛利率层仅在"半年度持有 + 动态中位数阈值"组合下稳健；固定阈值→回撤保护消失；再叠加月度高频→退化为亏损。跨数据源验证必须先对齐 阈值形态/调仓频率/前置过滤 三要素。</b>
</div>
<div class="concl warn" style="margin-top:10px">
<b>4. 绝对收益差 -36pp 的方法论归因</b> — 申万版年化+4.4% vs juzi版+9.4%：①月度调仓换手频繁（每月重选便宜股≈追跌杀跌的反向轮动）vs 半年度持有；②申万缺 L5 一致预期低预期过滤（juzi 版关键层, 拦截高预期接盘）；③基准/池子口径差异。月度+零成本是申万工具的固定设定，非刘旭框架本身参数。
</div>
</div>

<div class="card">
<h2 style="margin-top:0">⑦ 备注与数据来源</h2>
<p class="note">
- juzi版：<code>_bt_lx_allA_results.json</code>（2026-08-20 跑, 万得全A PIT成分, 半年度调仓, 成本5bp+10bp）<br>
- 申万版：<code>backtest_strategy</code> 3变体（2026-08-21 跑, 月度调仓等权, 零成本, 59个月）<br>
- 申万版映射为"近似"：缺一致预期(con_roe/con_np_yoy/con_peg)，故 qual 层(ROE≥12%)无法实现；gm 层用固定30%近似动态中位数<br>
- 本报告仅供研究参考，不构成投资建议。
</p>
</div>

</div></body></html>"""
    out = os.path.join(BASE, "_lx_sw_crosscheck.html")
    open(out, "w", encoding="utf-8").write(html)
    print("报告 →", out)
    print(f"juzi EW 基准年度收益: {ew_ann}")


if __name__ == "__main__":
    main()
