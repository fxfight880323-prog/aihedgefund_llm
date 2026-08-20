# -*- coding: utf-8 -*-
"""2021-2024 业绩差归因报告生成"""
import json

# ---------- 数据 ----------
nav = json.load(open('_bt_gl_nav.json', encoding='utf-8'))
bench = json.load(open('_bt_benchmark.json', encoding='utf-8'))
det = json.load(open('_bt_gl_valsell_baseline_detail.json', encoding='utf-8'))
wts, dets = det['weights_by_dt'], det['detail_by_dt']
prices = json.load(open('_bt_pit_prices.json', encoding='utf-8'))
fin = json.load(open('_bt_pit_financials.json', encoding='utf-8'))

starts = sorted(wts.keys())
def month_add(m, d):
    y, mo = int(m[:4]), int(m[5:])
    t = y * 12 + (mo - 1) + d
    return f"{t // 12}-{t % 12 + 1:02d}"

# 逐年收益（净值口径）
nav_d = {r['month']: r['nav'] for r in nav}
years = {}
for m in sorted(nav_d):
    y = m[:4]
    years.setdefault(y, []).append(nav_d[m])
year_ret = {}
for y, vs in sorted(years.items()):
    if len(vs) > 1:
        year_ret[y] = vs[-1] / vs[0] - 1
bench_years = {}
for m in sorted(bench):
    y = m[:4]
    bench_years.setdefault(y, []).append(bench[m])
bench_ret = {}
for y, vs in sorted(bench_years.items()):
    if len(vs) > 1:
        bench_ret[y] = vs[-1] / vs[0] - 1

# 每调仓期组合收益（等权价格）与超额
period_rows = []
for i, m0 in enumerate(starts):
    m1 = starts[i + 1] if i + 1 < len(starts) else '2026-08'
    tks = list(wts[m0].keys())
    rets = []
    for tk in tks:
        p0, p1 = prices.get(tk, {}).get(m0), prices.get(tk, {}).get(m1)
        if p0 and p1 and p0 > 0:
            rets.append(p1 / p0 - 1.0)
    if not rets:
        continue
    pr = sum(rets) / len(rets)
    br = bench.get(m1, 1) / bench.get(m0, 1) - 1
    period_rows.append((m0, m1, pr, br, pr - br, len(tks)))

# Growth Trap 案例（买入时 YoY → 后续）
gts = [
    ("富满微", "电子", "2021-08 买入", "芯片缺货涨价", "+239%", "+130% / +64% / +4%", "-51.1%"),
    ("明微电子", "电子", "2021-08 买入", "芯片缺货涨价", "+238%", "+233% / +138% / +28%", "-70.6%"),
    ("九安医疗", "医药生物", "2022-04 买入", "疫情检测一次性红利", "+6647%", "+3990% / +3011% / +998%", "-37.7%"),
    ("德方纳米", "电力设备", "2022-08 买入", "锂电材料价格暴涨", "+493%", "+535% / +366% / +47%", "-48.9%"),
    ("天齐锂业", "有色金属", "2022-08 买入", "碳酸锂价格顶部", "+508%", "+536% / +428% / +118%", "-37.6%"),
    ("博腾股份", "医药生物", "2022-08 买入", "CXO 大单脉冲", "+212%", "+157% / +127% / -5%", "-43.7%"),
    ("宏微科技", "电子", "2023-04 买入", "功率半导体景气回落", "+137%", "+130% / +85% / +63%", "-54.4%"),
]

# 2021-2024 各期 Top 拖累（脚本 2 输出手工整理）
drag = [
    ("2021-08→2022-04", "半导体芯片×5、锂电材料、光伏硅片", "明微电子 -70.6%、晶丰明源 -66.7%、弘元绿能 -61.9%、国科微 -53.7%"),
    ("2022-04→2022-08", "疫苗/CXO/检测、锂电材料", "康泰生物 -48.0%、富瀚微 -43.9%、亚辉龙 -40.8%、九安医疗 -37.7%"),
    ("2022-08→2023-04", "锂矿×4、锂电材料×3、CXO×2（满手锂电）", "德方纳米 -48.9%、瑞可达 -46.3%、博腾股份 -43.7%、融捷/盛新/天齐 -38~-41%"),
    ("2023-04→2023-08", "半导体、猪周期、医药", "瑞迈特 -48.0%、国科微 -31.0%、宏微科技 -27.6%、新五丰 -20.8%"),
    ("2023-08→2024-04", "光伏×3、房地产×4", "宏微科技 -54.4%、钧达股份 -49.2%、首开股份 -38.5%、双良节能 -37.6%"),
    ("2024-04→2024-08", "创新药、光伏设备", "荣昌生物 -53.9%、中信博 -43.1%、普冉股份 -37.2%、帝科股份 -34.7%"),
]

# ---------- SVG ----------
def svg_year_chart():
    W, H = 680, 300
    pad_l, pad_r, pad_t, pad_b = 52, 16, 34, 40
    inner_w, inner_h = W - pad_l - pad_r, H - pad_t - pad_b
    yrs = [y for y in ['2021', '2022', '2023', '2024', '2025', '2026'] if y in year_ret]
    n = len(yrs)
    gw = inner_w / n
    vals = [(year_ret[y], bench_ret.get(y, 0)) for y in yrs]
    allv = [v for pair in vals for v in pair]
    vmax = max(max(allv), 0) * 1.15
    vmin = min(min(allv), 0) * 1.3
    def y(v): return pad_t + inner_h * (vmax - v) / (vmax - vmin)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Segoe UI, Microsoft YaHei, sans-serif">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    # 零线
    parts.append(f'<line x1="{pad_l}" y1="{y(0)}" x2="{W-pad_r}" y2="{y(0)}" stroke="#666" stroke-width="1"/>')
    # 网格
    for i in range(5):
        f = vmin + (vmax - vmin) * i / 4
        yy = y(f)
        parts.append(f'<line x1="{pad_l}" y1="{yy}" x2="{W-pad_r}" y2="{yy}" stroke="#eee"/>')
        parts.append(f'<text x="{pad_l-6}" y="{yy+4}" font-size="11" fill="#999" text-anchor="end">{f*100:+.0f}%</text>')
    for i, yr in enumerate(yrs):
        cx = pad_l + gw * i + gw / 2
        bw = gw * 0.30
        for j, (v, c) in enumerate([(vals[i][0], '#c0392b' if vals[i][0] >= 0 else '#1e8449'),
                                    (vals[i][1], '#b3b3b3')]):
            x0 = cx - bw + j * bw
            y0, y1 = y(v), y(0)
            if y0 > y1: y0, y1 = y1, y0
            parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bw*0.8:.1f}" height="{max(y1-y0,1):.1f}" fill="{c}" rx="2"/>')
            if abs(v) > 0.02:
                vy = y(v) - (12 if v >= 0 else 18)
                parts.append(f'<text x="{x0+bw*0.4:.1f}" y="{vy:.1f}" font-size="11" fill="{c}" text-anchor="middle">{v*100:+.1f}%</text>')
        parts.append(f'<text x="{cx:.1f}" y="{H-pad_b+18}" font-size="12" fill="#444" text-anchor="middle">{yr}</text>')
    # 图例
    parts.append(f'<rect x="{W-190}" y="8" width="12" height="12" fill="#c0392b" rx="2"/><text x="{W-173}" y="18" font-size="11" fill="#666">策略（涨红跌绿）</text>')
    parts.append(f'<rect x="{W-330}" y="8" width="12" height="12" fill="#b3b3b3" rx="2"/><text x="{W-313}" y="18" font-size="11" fill="#666">市场基准</text>')
    parts.append('</svg>')
    return ''.join(parts)

def svg_period_chart():
    W, H = 680, 360
    pad_l, pad_r, pad_t, pad_b = 130, 16, 30, 20
    inner_w, inner_h = W - pad_l - pad_r, H - pad_t - pad_b
    rows = period_rows
    n = len(rows)
    rh = inner_h / n
    exs = [r[4] for r in rows]
    mx = max(max(exs), 0) * 1.15
    mn = min(min(exs), 0) * 1.3
    def x(v): return pad_l + inner_w * (v - mn) / (mx - mn)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Segoe UI, Microsoft YaHei, sans-serif">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    parts.append(f'<line x1="{x(0)}" y1="{pad_t}" x2="{x(0)}" y2="{H-pad_b}" stroke="#666" stroke-width="1"/>')
    for i in range(6):
        f = mn + (mx - mn) * i / 5
        xx = x(f)
        parts.append(f'<line x1="{xx}" y1="{pad_t}" x2="{xx}" y2="{H-pad_b}" stroke="#eee"/>')
        parts.append(f'<text x="{xx}" y="{H-pad_b-6}" font-size="11" fill="#999" text-anchor="middle">{f*100:+.0f}%</text>')
    for i, (m0, m1, pr, br, ex, ntk) in enumerate(rows):
        yc = pad_t + rh * i + rh / 2
        c = '#c0392b' if ex >= 0 else '#1e8449'
        x0, x1 = x(0), x(ex)
        if x0 > x1: x0, x1 = x1, x0
        parts.append(f'<rect x="{x0:.1f}" y="{yc-rh*0.28:.1f}" width="{max(x1-x0,2):.1f}" height="{rh*0.56:.1f}" fill="{c}" rx="2"/>')
        lbl = f'{m0[2:]}+{m1[2:]}' if m0[:4] == m1[:4] else f'{m0}→{m1}'
        parts.append(f'<text x="{pad_l-8}" y="{yc+4}" font-size="11" fill="#444" text-anchor="end">{m0}</text>')
        anch = 'start' if ex >= 0 else 'end'
        parts.append(f'<text x="{x(ex)+(8 if ex>=0 else -8)}" y="{yc+4}" font-size="11" fill="{c}" text-anchor="{anch}">{ex*100:+.0f}pp</text>')
    parts.append('</svg>')
    return ''.join(parts)

def svg_growth_trap():
    W, H = 680, 330
    pad_l, pad_r, pad_t, pad_b = 60, 20, 30, 20
    inner_w, inner_h = W - pad_l - pad_r, H - pad_t - pad_b
    n = len(gts)
    rh = inner_h / n
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Segoe UI, Microsoft YaHei, sans-serif">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    # 买入时 YoY 条（红）
    mx = 7000
    for i, (nm, ind, buy, why, yoy_buy, yoy_after, ret) in enumerate(gts):
        yc = pad_t + rh * i + rh / 2
        w0 = inner_w * (float(yoy_buy.replace('%','').replace('+','')) / mx)
        parts.append(f'<rect x="{pad_l}" y="{yc-rh*0.24:.1f}" width="{w0:.1f}" height="{rh*0.48:.1f}" fill="#e07b39" rx="2"/>')
        parts.append(f'<text x="{pad_l-8}" y="{yc+4}" font-size="11" fill="#444" text-anchor="end">{nm}</text>')
        parts.append(f'<text x="{pad_l+w0+6:.1f}" y="{yc+4}" font-size="11" fill="#e07b39">买入时 YoY {yoy_buy}</text>')
        parts.append(f'<text x="{W-pad_r}" y="{yc+4}" font-size="11" fill="#1e8449" text-anchor="end">买入后 1-3 季: {yoy_after}</text>')
    parts.append(f'<text x="{pad_l}" y="14" font-size="12" fill="#666">买入时的营收同比 vs 买入后 1-3 个季度的实际营收同比 —— 全部在峰值附近买入，随后增速系统性回落</text>')
    parts.append('</svg>')
    return ''.join(parts)

# ---------- HTML ----------
gt_rows = ''.join(
    f'<tr><td>{nm}</td><td>{ind}</td><td>{buy}</td><td style="color:#e07b39">{yoy_buy}</td>'
    f'<td style="color:#1e8449">{yoy_after}</td><td style="color:#1e8449">{ret}</td></tr>'
    for nm, ind, buy, why, yoy_buy, yoy_after, ret in gts)
drag_rows = ''.join(
    f'<tr><td><b>{p}</b></td><td>{inds}</td><td style="text-align:left">{losers}</td></tr>'
    for p, inds, losers in drag)

period_tbl = ''.join(
    f'<tr><td>{m0} → {m1}</td><td>{ntk}</td><td style="color:{("#c0392b" if pr>=0 else "#1e8449")}">{pr:+.1%}</td>'
    f'<td>{br:+.1%}</td><td style="color:{("#c0392b" if ex>=0 else "#1e8449")}"><b>{ex:+.1f}pp</b></td></tr>'
    for m0, m1, pr, br, ex, ntk in period_rows)

year_tbl = ''.join(
    f'<tr><td>{y}</td><td style="color:{("#c0392b" if year_ret[y]>=0 else "#1e8449")}">{year_ret[y]:+.1%}</td>'
    f'<td>{bench_ret.get(y,0):+.1%}</td>'
    f'<td style="color:{("#c0392b" if year_ret[y]-bench_ret.get(y,0)>=0 else "#1e8449")}">{year_ret[y]-bench_ret.get(y,0):+.1f}pp</td></tr>'
    for y in ['2021','2022','2023','2024','2025','2026'] if y in year_ret)

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Growth Loop 2021-2024 亏损归因</title>
<style>
 body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:#f6f7f9;color:#222;margin:0;padding:24px}}
 .wrap{{max-width:960px;margin:0 auto}}
 h1{{font-size:24px;margin:0 0 4px}}
 .sub{{color:#666;font-size:13px;margin-bottom:20px}}
 .card{{background:#fff;border:1px solid #e3e5e8;border-radius:10px;padding:20px 22px;margin-bottom:18px}}
 h2{{font-size:17px;margin:0 0 12px;border-left:4px solid #c0392b;padding-left:10px}}
 h3{{font-size:14px;color:#444;margin:14px 0 8px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th,td{{padding:7px 8px;border-bottom:1px solid #eceef1;text-align:center}}
 th{{background:#f4f5f7;color:#555;font-weight:600}}
 .verdict{{background:#fff8f0;border:1px solid #f0dcc0;border-radius:10px;padding:16px 20px;margin-bottom:18px}}
 .verdict b{{color:#a4551c}}
 .tag{{display:inline-block;background:#fdf0e9;color:#c0392b;border-radius:4px;padding:1px 8px;font-size:12px;margin-right:6px}}
 .concl{{font-size:14px;line-height:1.8}}
 .concl li{{margin-bottom:8px}}
 .num{{font-weight:700;color:#c0392b}}
 .green{{color:#1e8449}}
</style></head><body><div class="wrap">

<h1>Growth Loop 策略 2021-2024 亏损归因</h1>
<div class="sub">PIT 回测 · 2021-06 → 2026-08 · 无未来数据 · 所有数字来自真实回测记录</div>

<div class="verdict">
<b>一句话结论：</b>亏损不是市场 beta，是选股 alpha 的负贡献。<b>策略在 2021-2024 连续 6 个调仓期都跑输基准（累计超额约 -44pp）</b>，根因是「营收加速」选股因子在 A 股 2021-2024 的成长股熊市里系统性追在景气峰值——买入时营收同比 +130%~+6600%，买入后 1-3 个季度增速无一例外回落，股价随之下杀 40%-70%。这不是运气差，是因子在特定市场环境下的结构性失效。
</div>

<div class="card">
<h2>一、逐年收益 vs 市场基准</h2>
{svg_year_chart()}
<table>
<tr><th>年份</th><th>策略</th><th>市场基准</th><th>超额</th></tr>
{year_tbl}
</table>
<p style="font-size:13px;color:#777">2022 与 2023 是全部亏损的主体：两年各跑输基准 12-13pp。<b>2021-2024 累计：策略约 -46% vs 基准约 -11%</b>。2025 年风格反转后策略大幅反超（+47% vs +28%），说明因子不是死了，是<u>只在成长牛市有效</u>。</p>
</div>

<div class="card">
<h2>二、每个调仓期的超额（等权持仓收益 − 基准）</h2>
{svg_period_chart()}
<table>
<tr><th>区间</th><th>持仓数</th><th>组合</th><th>基准</th><th>超额</th></tr>
{period_tbl}
</table>
<p style="font-size:13px;color:#777">最惨的一期 <b>2022-08 → 2023-04：基准几乎平盘（-0.4%），组合却亏 20.5%</b>——满手锂矿+锂电材料+CXO，恰逢碳酸锂价格见顶暴跌。其余各期超额 -3 到 -9pp，每半年稳定跑输一次。</p>
</div>

<div class="card">
<h2>三、Top 拖累行业与个股（2021-2024）</h2>
<table>
<tr><th>区间</th><th>重仓行业（当时的景气赛道）</th><th>最大拖累个股</th></tr>
{drag_rows}
</table>
<p style="font-size:13px;color:#777">观察：拖累股高度集中于<b>「涨价/扩产/一次性红利」驱动的周期成长股</b>——芯片缺货（2021）、疫情检测与 CXO 大单（2022）、锂价暴涨（2022）、猪周期（2023）、光伏产能扩张（2023-2024）。每期换仓都在买入「上一轮景气高峰」的残骸。</p>
</div>

<div class="card">
<h2>四、Growth Trap 验证：买入时 YoY vs 买入后实际 YoY</h2>
{svg_growth_trap()}
<table>
<tr><th>个股</th><th>行业</th><th>买入点</th><th>买入时 YoY</th><th>买入后 1-3 季 YoY</th><th>区间股价</th></tr>
{gt_rows}
</table>
<p style="font-size:13px;color:#777">7 个代表案例全部命中同一模式：<b>策略的买入点恰好是 YoY 的局部峰值</b>。财报同比峰值的来源是周期/一次性因素（缺货涨价、疫情红利、商品价格、扩产），而 A 股的股价在增速见顶前就提前定价。营收加速因子的「高度」在周期股上是陷阱——增速最高的那一刻，往往就是该股未来 12 个月最贵的时刻。</p>
</div>

<div class="card">
<h2>五、根因与改进方向</h2>
<div class="concl">
<h3>三个根因（按重要性）</h3>
<ol>
<li><b>因子结构：营收加速 = 景气动量追高。</b> HOOK 层按 YoY 高度/加速选股，天然偏爱「过去一年增速最高的股票」。在 A 股这些超高增速多来自周期性因素，选入时点=增速峰值，买入后均值回归。</li>
<li><b>市场环境：2021-2024 是成长/景气投资最差的三年。</b> 核心资产与赛道股系统性杀估值，高增速高估值风格连续 3 年跑输。策略在成长牛市（2025+）大幅跑赢，说明因子有「环境依赖」，不是完全失效。</li>
<li><b>无估值护栏 + 低频换仓。</b> 半年一次调仓，下跌段全程暴露无止损；估值卖出纪律（此前实验 +11pp）直到 2025 才被加入变体验证，正式策略没有估值约束。</li>
</ol>
<h3>改进方向（诚实评估）</h3>
<ol>
<li><b>增速「质量」优先于「高度」</b>：排除 YoY&gt;300% 的疑似周期/一次性暴增（缺货、疫情、价格顶）；要求增速的环比斜率仍在抬升（而非已见顶回落）。</li>
<li><b>估值护栏</b>：已实测有效（PS/历史中位数≥2.0 卖出，总收益 -14%→-2.6%），应纳入正式策略。</li>
<li><b>环境开关</b>：识别市场风格（成长 vs 价值），成长风格熊市降低仓位或切换到防御因子，避免满仓硬扛 3 年 -45%。</li>
<li><b>增速见顶 = 减仓信号而非买入信号</b>：减速因子在熊市避雷有效（11/11 卖对），问题在清仓后资金闲置——改为降权+再配置。</li>
</ol>
</div>
</div>

<p style="color:#999;font-size:12px;text-align:center;margin-top:20px">归因基于 _bt_gl_nav.json / _bt_gl_valsell_baseline_detail.json / _bt_pit_financials.json 等回测数据，2026-08-19 生成。</p>
</div></body></html>"""

open('_gl_attrib_report.html', 'w', encoding='utf-8').write(html)
print('written', len(html), 'bytes')
