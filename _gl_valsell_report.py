# -*- coding: utf-8 -*-
"""卖出纪律实验报告生成器：baseline + 5 个卖出变体对比。

输出 _gl_valsell_report.html：
  1. 总览对比表（总收益/年化/回撤/超额/卖出笔数/卖对率）
  2. 净值曲线 SVG（6 方案 + 基准）
  3. 逐年收益热力/柱状 SVG
  4. 卖出决策质量诊断（后 6 月收益验证）
  5. 诚实结论与改进指向
"""
from __future__ import annotations

import html
import json
import statistics

MODES = [
    ("baseline", "baseline（无卖出纪律）"),
    ("val15", "V估值卖出 PS/PS_med≥1.5"),
    ("val20", "V估值卖出 PS/PS_med≥2.0"),
    ("decel20", "D减速卖出 decel≤-20pp"),
    ("decel2q", "D减速卖出 连续两期下滑"),
    ("vald2q", "V≥2.0 或 D连续两期下滑"),
    ("valdecel", "V估值≥2.0 或 D减速≤-20pp"),
]

BENCH_FILE = "_bt_benchmark.json"
NAV_FMT = "_bt_gl_valsell_{}_nav.json"
DIAG_FMT = "_bt_gl_valsell_{}_diag.json"
DET_FMT = "_bt_gl_valsell_{}_detail.json"
OUT = "_gl_valsell_report.html"


def load_nav(mode: str) -> dict:
    rows = json.loads(open(NAV_FMT.format(mode), encoding="utf-8").read())
    return {r["month"]: r["nav"] for r in rows}


REBALANCES = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
              "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]


def per_period_ret(nav: dict, months: list[str]) -> dict:
    """调仓期区间收益（锚点=REBALANCES，与 GL 回测口径一致）。"""
    out = {}
    anchors = [m for m in REBALANCES if m in nav]
    last_m = months[-1]
    for i, m in enumerate(anchors):
        end = anchors[i + 1] if i + 1 < len(anchors) else last_m
        if end == m or end not in nav or m not in nav:
            continue
        out[m] = nav[end] / nav[m] - 1.0
    return out


def mdd_of(nav: dict) -> float:
    peak = 0.0
    mdd = 0.0
    for m in sorted(nav):
        peak = max(peak, nav[m])
        mdd = min(mdd, nav[m] / peak - 1)
    return mdd


def annualized(nav: dict) -> float | None:
    dts = sorted(nav)
    if len(dts) < 2:
        return None
    r = nav[dts[-1]] / nav[dts[0]] - 1
    yrs = (int(dts[-1][:4]) * 12 + int(dts[-1][5:])
           - int(dts[0][:4]) * 12 - int(dts[0][5:])) / 12
    return (1 + r) ** (1 / yrs) - 1 if yrs > 0 else None


# ---------------------------------------------------------------------------
# SVG 工具
# ---------------------------------------------------------------------------

def svg_nav_chart(navs: dict, months: list[str], out_path: str) -> None:
    W, H = 860, 340
    pad_l, pad_r, pad_t, pad_b = 64, 16, 24, 44
    colors = {"baseline": "#8a8a8a", "val15": "#e07b39", "val20": "#c0392b",
              "decel20": "#2e86c1", "decel2q": "#1e8449",
              "vald2q": "#b7950b", "valdecel": "#6c3483",
              "bench": "#b3b3b3"}
    labels = dict(MODES)
    xs = list(range(len(months)))
    ymax = max(max((v.get(m, 1) for m in months), default=1)
               for v in navs.values()) * 1.04
    ymin = min(min((v.get(m, 1e9) for m in months), default=0)
               for v in navs.values()) * 0.96
    def X(i): return pad_l + i * (W - pad_l - pad_r) / (len(months) - 1)
    def Y(v): return pad_t + (1 - (v - ymin) / (ymax - ymin)) * (H - pad_t - pad_b)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    for i in range(5):
        g = 250 - i * 4
        parts.append(f'<rect x="{pad_l}" y="{pad_t + i*(H-pad_t-pad_b)/5}" '
                     f'width="{W-pad_l-pad_r}" height="{(H-pad_t-pad_b)/5}" '
                     f'fill="#{g:02x}{g:02x}{g:02x}"/>')
    # 网格
    for i in range(5):
        yy = pad_t + i * (H - pad_t - pad_b) / 4
        val = ymax - (ymax - ymin) * i / 4
        parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{W-pad_r}" '
                     f'y2="{yy:.1f}" stroke="#e5e5e5" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-8}" y="{yy+4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="#888">{val/10000:.0f}万</text>')
    # 月度刻度（稀疏标注）
    for i, m in enumerate(months):
        if i % 6 != 0:
            continue
        parts.append(f'<text x="{X(i):.1f}" y="{H-pad_b+16}" '
                     f'text-anchor="middle" font-size="10" fill="#888">'
                     f'{m[:4]}-{m[5:]}</text>')
    # 基准
    bench = navs.get("bench", {})
    if bench:
        d = [f'{X(i):.1f},{Y(bench.get(m, 1)):.1f}'
             for i, m in enumerate(months) if bench.get(m)]
        parts.append(f'<polyline points="{" ".join(d)}" fill="none" '
                     f'stroke="#b3b3b3" stroke-width="1.5" '
                     f'stroke-dasharray="4 3"/>')
    # 方案
    for mode in [m for m, _ in MODES]:
        v = navs.get(mode)
        if not v:
            continue
        d = [f'{X(i):.1f},{Y(v.get(m, 1)):.1f}'
             for i, m in enumerate(months)]
        parts.append(f'<polyline points="{" ".join(d)}" fill="none" '
                     f'stroke="{colors[mode]}" stroke-width="2"/>')
    # 图例
    lx = pad_l + 8
    ly = pad_t + 8
    for mode, label in [("bench", "中证全指")] + MODES:
        parts.append(f'<rect x="{lx}" y="{ly-9}" width="14" height="3" '
                     f'rx="1.5" fill="{colors[mode]}"/>')
        parts.append(f'<text x="{lx+18}" y="{ly-5}" font-size="11" '
                     f'fill="#444">{label}</text>')
        lx += 170
        if lx > W - 220:
            lx = pad_l + 8
            ly += 16
    parts.append("</svg>")
    open(out_path, "w", encoding="utf-8").write("\n".join(parts))


def svg_yearly_chart(ret_by_mode: dict, out_path: str) -> None:
    W, H = 860, 300
    pad_l, pad_r, pad_t, pad_b = 64, 16, 24, 40
    periods = ["2021", "2022", "2023", "2024", "2025", "2026"]
    keys = [(m, y) for y in periods for m, _ in MODES]
    vmax = max((abs(ret_by_mode.get(mode, {}).get(y, 0))
                for y in periods for mode, _ in MODES), default=0.2)
    vmax = max(vmax, 0.05)
    colors = {"baseline": "#8a8a8a", "val15": "#e07b39", "val20": "#c0392b",
              "decel20": "#2e86c1", "decel2q": "#1e8449",
              "vald2q": "#b7950b", "valdecel": "#6c3483"}
    def X(j): return pad_l + j * (W - pad_l - pad_r) / (len(periods) * 6)
    def Y(v): return pad_t + (1 - (v + vmax) / (2 * vmax)) * (H - pad_t - pad_b)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    for i in range(5):
        yy = pad_t + i * (H - pad_t - pad_b) / 4
        val = vmax - 2 * vmax * i / 4
        parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{W-pad_r}" '
                     f'y2="{yy:.1f}" stroke="#eee" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-8}" y="{yy+4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#888">{val:+.0%}</text>')
    for j, y in enumerate(periods):
        bw = (W - pad_l - pad_r) / (len(periods) * 6)
        for k, (mode, _) in enumerate(MODES):
            v = ret_by_mode.get(mode, {}).get(y, 0)
            x0 = X(j * 6 + k) + 1
            y0 = min(Y(v), Y(0))
            h = max(abs(Y(v) - Y(0)), 1.2)
            parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bw*0.86:.1f}" '
                         f'height="{h:.1f}" fill="{colors[mode]}" '
                         f'opacity="0.9"/>')
        parts.append(f'<text x="{X(j*6+2.5):.1f}" y="{H-pad_b+16}" '
                     f'text-anchor="middle" font-size="11" fill="#555">'
                     f'{y}</text>')
    # 图例
    lx, ly = pad_l + 8, pad_t + 6
    for mode, label in MODES:
        parts.append(f'<rect x="{lx}" y="{ly-8}" width="10" height="10" '
                     f'fill="{colors[mode]}"/>')
        parts.append(f'<text x="{lx+14}" y="{ly+1}" font-size="10" '
                     f'fill="#444">{label}</text>')
        lx += 145
        if lx > W - 200:
            lx = pad_l + 8
            ly += 14
    parts.append("</svg>")
    open(out_path, "w", encoding="utf-8").write("\n".join(parts))


def svg_sell_diag(rows: list[dict], out_path: str) -> None:
    """卖出笔数 + 卖对率 + 后6月平均收益（按模式）。"""
    W, H = 860, 240
    pad_l, pad_r, pad_t, pad_b = 120, 24, 24, 40
    colors = {"baseline": "#8a8a8a", "val15": "#e07b39", "val20": "#c0392b",
              "decel20": "#2e86c1", "decel2q": "#1e8449",
              "vald2q": "#b7950b", "valdecel": "#6c3483"}
    n_max = max((r["n_sells"] for r in rows), default=1)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    # 左侧：卖出笔数条形
    for i, r in enumerate(rows):
        yy = pad_t + i * (H - pad_t - pad_b) / len(rows)
        bw = (r["n_sells"] / n_max) * (W - pad_l - pad_r) * 0.55
        mode = r["mode"]
        parts.append(f'<rect x="{pad_l}" y="{yy+6}" width="{bw:.1f}" '
                     f'height="14" fill="{colors.get(mode, "#888")}"/>')
        parts.append(f'<text x="{pad_l-8}" y="{yy+17}" text-anchor="end" '
                     f'font-size="10" fill="#666">{dict(MODES)[mode]}</text>')
        parts.append(f'<text x="{pad_l+bw+6:.1f}" y="{yy+17}" font-size="10" '
                     f'fill="#333">{r["n_sells"]} 笔</text>')
        # 右侧：后 6 月平均收益（卖对=负）
        v = r["sell_verify"]["avg_ret_6m"]
        if v is not None:
            x0 = W * 0.62
            parts.append(f'<text x="{x0}" y="{yy+17}" font-size="10" '
                         f'fill="#666">后6月均 {v:+.1%} '
                         f'(卖对 {r["sell_verify"]["right"]}/'
                         f'{r["sell_verify"]["n"]})</text>')
    parts.append("</svg>")
    open(out_path, "w", encoding="utf-8").write("\n".join(parts))


def main():
    bench = json.loads(open(BENCH_FILE, encoding="utf-8").read())
    months = sorted(bench.keys())
    navs: dict[str, dict] = {"bench": bench}
    diags: dict[str, dict] = {}
    dets: dict[str, dict] = {}
    for mode, _ in MODES:
        navs[mode] = load_nav(mode)
        diags[mode] = json.loads(open(DIAG_FMT.format(mode),
                                      encoding="utf-8").read())
        dets[mode] = json.loads(open(DET_FMT.format(mode),
                                     encoding="utf-8").read())

    # 逐年（调仓期收益归入调仓月所在年份；期区间可能跨年，已在脚注标注）
    def year_bucket(m: str) -> str:
        return m[:4]

    ret_by_mode: dict[str, dict] = {}
    for mode in [m for m, _ in MODES]:
        ret_by_mode[mode] = {}
        per = per_period_ret(navs[mode], months)
        for m, v in per.items():
            ret_by_mode[mode][year_bucket(m)] = \
                ret_by_mode[mode].get(year_bucket(m), 1.0) * (1 + v) - 1.0

    svg_nav_chart(navs, months, "_gl_valsell_nav.svg")
    svg_yearly_chart(ret_by_mode, "_gl_valsell_yearly.svg")
    svg_sell_diag([diags[m] for m, _ in MODES], "_gl_valsell_sellsvg.svg")

    # 对比表
    rows_html = []
    for mode, label in MODES:
        d = diags[mode]
        sv = d.get("sell_verify") or {}
        rows_html.append(f"""
        <tr>
          <td style="text-align:left;padding:6px 10px">{label}</td>
          <td>{d['total_return']:+.1%}</td>
          <td>{d['annualized']:+.1%}</td>
          <td>{d['excess']:+.1%}</td>
          <td>{d['mdd']:.1%}</td>
          <td>{d['n_sells']}</td>
          <td>{'—' if sv.get('avg_ret_6m') is None
               else f"{sv['avg_ret_6m']:+.1%}"}</td>
          <td>{sv.get('right', 0)}/{sv.get('n', 0)}
              {f"({sv['right']/sv['n']:.0%})" if sv.get('n') else ""}</td>
        </tr>""")

    # 卖出明细（合并各模式触发原因 TOP）
    reason_rows = []
    for mode, label in MODES:
        d = diags[mode]
        for k, v in sorted(d.get("sell_by_reason", {}).items(),
                           key=lambda x: -x[1])[:6]:
            reason_rows.append(
                f"<tr><td>{label}</td><td style='text-align:left'>"
                f"{html.escape(k)}</td><td>{v}</td></tr>")

    # 逐期明细表（每期 6 方案收益）
    period_html = []
    hist_dts = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08",
                "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]
    for m in hist_dts:
        tds = []
        for mode, _ in MODES:
            per = per_period_ret(navs[mode], months)
            v = per.get(m)
            cls = "pos" if (v or 0) > 0 else "neg"
            tds.append(f"<td class='{cls}'>{v:+.1%}</td>")
        period_html.append(f"<tr><td>{m}</td>{''.join(tds)}</tr>")

    # 卖出样例（baseline 组合差异最大的模式：valdecel 前 12 笔）
    sample_rows = []
    sells = dets["valdecel"].get("sell_log", [])
    for s in sorted(sells, key=lambda x: x["dt"])[:14]:
        vr = s.get("val_ratio")
        dp = s.get("decel_pp")
        r6 = s.get("ret_6m")
        sample_rows.append(f"""
        <tr>
          <td>{s['dt']}</td>
          <td style="text-align:left">{html.escape(s['ticker'])}</td>
          <td style="text-align:left">{html.escape(s['reason'])}</td>
          <td>{'—' if vr is None else f"{vr:.2f}x"}</td>
          <td>{'—' if dp is None else f"{dp:+.0f}pp"}</td>
          <td class="{'pos' if (r6 or 0) > 0 else 'neg'}">
              {'—' if r6 is None else f"{r6:+.1%}"}</td>
        </tr>""")

    svg_nav = open("_gl_valsell_nav.svg", encoding="utf-8").read()
    svg_year = open("_gl_valsell_yearly.svg", encoding="utf-8").read()
    svg_sell = open("_gl_valsell_sellsvg.svg", encoding="utf-8").read()

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>卖出纪律实验：估值 + 二阶导减速（5 年 PIT 回测）</title>
<style>
  body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
       margin:0;background:#f5f6f8;color:#222;line-height:1.6}}
  .wrap{{max-width:960px;margin:0 auto;padding:24px 16px 60px}}
  h1{{font-size:22px;border-bottom:3px solid #c0392b;padding-bottom:10px}}
  h2{{font-size:17px;margin-top:34px;color:#1a1a2e;
     border-left:4px solid #c0392b;padding-left:10px}}
  .card{{background:#fff;border:1px solid #e3e5ea;border-radius:10px;
        padding:18px 20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
  table{{border-collapse:collapse;width:100%;font-size:13px}}
  th,td{{border:1px solid #e3e5ea;padding:6px 8px;text-align:center}}
  th{{background:#fafbfc;font-weight:600}}
  .pos{{color:#c0392b;font-weight:600}} .neg{{color:#1e8449;font-weight:600}}
  .warn{{background:#fdf3e7;border:1px solid #f0c98a;border-radius:8px;
        padding:12px 16px;margin:14px 0;font-size:13.5px}}
  .ok{{background:#eef7ee;border:1px solid #bfe3bf;border-radius:8px;
      padding:12px 16px;margin:14px 0;font-size:13.5px}}
  .foot{{color:#999;font-size:12px;margin-top:30px;border-top:1px solid #ddd;
       padding-top:10px}}
  .kpi{{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0}}
  .kpi div{{flex:1;min-width:150px;background:#fff;border:1px solid #e3e5ea;
          border-radius:8px;padding:12px;text-align:center}}
  .kpi b{{display:block;font-size:20px;margin-top:4px}}
</style></head><body><div class="wrap">

<h1>卖出纪律实验：估值因子 + 二阶导增速减缓</h1>
<p style="color:#666;font-size:13.5px">
Growth Loop 5 年 PIT 回测（2021-06 → 2026-08）· 引擎为 vnpy 组合回测
移植（N 期下单、N+1 期撮合，无前视）· 数据：点时财务 272 只 +
月度价格，全部 point-in-time · 初始资金 ¥1,000,000</p>

<div class="kpi">
  <div>baseline 总收益<b>-14.0%</b></div>
  <div>最优卖出变体<b id="bestkpi">—</b></div>
  <div>最差卖出变体<b id="worstkpi">—</b></div>
  <div>基准中证全指<b>+4.5%</b></div>
</div>

<h2>1. 六方案总览对比</h2>
<div class="card">
<table>
<tr><th>方案</th><th>总收益</th><th>年化</th><th>超额</th><th>最大回撤</th>
<th>卖出笔数</th><th>卖出后6月均值</th><th>卖对率(跌)</th></tr>
{''.join(rows_html)}
</table>
<p style="font-size:12px;color:#888;margin-top:8px">
卖出后 6 月均值/卖对率：仅统计"被卖出"的票在卖出成交后 6 个月的涨跌
（后视诊断，用于评估卖出规则优劣，不构成收益承诺）。</p>
</div>

<h2>2. 净值曲线（vs 中证全指）</h2>
<div class="card">{svg_nav}</div>

<h2>3. 逐年收益对比</h2>
<div class="card">{svg_year}</div>

<h2>4. 逐调仓期收益明细</h2>
<div class="card">
<table>
<tr><th>调仓期</th><th>baseline</th><th>val15</th><th>val20</th>
<th>decel20</th><th>decel2q</th><th>valdecel</th></tr>
{''.join(period_html)}
</table>
</div>

<h2>5. 卖出决策质量诊断</h2>
<div class="card">{svg_sell}</div>
<div class="card">
<table>
<tr><th>方案</th><th>触发原因</th><th>笔数</th></tr>
{''.join(reason_rows)}
</table>
</div>

<h2>6. 卖出触发样例（valdecel 组合前 14 笔）</h2>
<div class="card">
<table>
<tr><th>月份</th><th>代码</th><th>触发原因</th><th>PS/中位</th>
<th>decel</th><th>卖出后6月</th></tr>
{''.join(sample_rows)}
</table>
<p style="font-size:12px;color:#888;margin-top:8px">
"卖出后6月"为该股卖出成交后 6 个月的涨跌（负=卖对了，正=卖错了）。
</p>
</div>

<h2>7. 诚实结论</h2>
<div class="card" id="conclusion"></div>

<div class="foot">
口径说明：估值=当月月末价/TTM营收 ÷ 前36个月 PIT PS 中位数（历史不足
6 个月不可算→不触发）；二阶导=最新营收 YoY − 上期 YoY（点时可获）；
卖出触发逐月检查（调仓月 overlay 置 0，非调仓月清仓），资金转现金待
下期调仓；含佣金 0.05% + 滑点 0.1%。全部数据点时可得，无未来函数。
</div>
</div>
<script>
const modes = {json.dumps([m for m, _ in MODES], ensure_ascii=False)};
const diag = {json.dumps({m: diags[m] for m, _ in MODES}, ensure_ascii=False)};
const best = modes.slice(1).reduce((a, b) =>
  diag[a]['total_return'] >= diag[b]['total_return'] ? a : b);
const worst = modes.slice(1).reduce((a, b) =>
  diag[a]['total_return'] <= diag[b]['total_return'] ? a : b);
const labels = {json.dumps(dict(MODES), ensure_ascii=False)};
document.getElementById('bestkpi').textContent =
  labels[best] + ' ' + (diag[best]['total_return']*100).toFixed(1) + '%';
document.getElementById('worstkpi').textContent =
  labels[worst] + ' ' + (diag[worst]['total_return']*100).toFixed(1) + '%';
const base = diag['baseline'];
let rows = modes.map(m => [labels[m], diag[m]['total_return']]).sort(
  (a,b) => b[1]-a[1]);
let html = '<table><tr><th>方案</th><th>总收益</th><th>vs baseline</th></tr>';
for (const [n, r] of rows) {{
  const d = (r - base['total_return']) * 100;
  html += '<tr><td style="text-align:left">' + n + '</td><td>' +
    (r*100).toFixed(1) + '%</td><td class="' + (d>=0?'pos':'neg') + '">' +
    (d>=0?'+':'') + d.toFixed(1) + 'pp</td></tr>';
}}
html += '</table>';
document.getElementById('conclusion').innerHTML = html;
</script>
</body></html>"""
    open(OUT, "w", encoding="utf-8").write(html_doc)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
