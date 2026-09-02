# -*- coding: utf-8 -*-
"""模拟持仓 vs 组合历史回测 对比报告生成器。
读 _cmp_hold_vs_bt.json → _cmp_hold_vs_bt_report.html
"""
import json, os, sys, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir("D:/workspace/ai_fund_framework")

R = json.load(open("_cmp_hold_vs_bt.json", encoding="utf-8"))
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def pct(x, nd=1, sign=True):
    if x is None:
        return "—"
    return f"{x*100:+.{nd}f}%" if sign else f"{x*100:.{nd}f}%"


def cls(x):
    if x is None or abs(x) < 1e-9:
        return ""
    return "pos" if x > 0 else "neg"


# ---------- 曲线数据（降采样） ----------
def series(tag, a, b, step=1):
    c = R["curves"][tag]
    nav, pts, peak = 1.0, [], 1.0
    for d in sorted(c):
        if d <= a:
            nav *= (1 + c[d]["r"])   # 起点前累计（用于对齐起点）
        elif d <= b:
            nav *= (1 + c[d]["r"])
            pts.append((d, nav))
    # 重归一化：起点 a 后第一点
    return pts


def build_curve(tag, a, b, step=6):
    """返回 [(i, nav)]，起点归一化 1.0，step 降采样。"""
    c = R["curves"][tag]
    nav, base, pts, peak = 1.0, None, [], 1.0
    for d in sorted(c):
        if d < a:
            continue
        if d > b:
            break
        nav *= (1 + c[d]["r"])
        if base is None:
            base = nav
        v = nav / base
        peak = max(peak, v)
        pts.append((d, v))
    out = [pts[i] for i in range(0, len(pts), step)]
    if pts and out[-1][0] != pts[-1][0]:
        out.append(pts[-1])
    return out, peak


def ew_curve(a, b, step=6):
    ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))["nav"]
    ds = sorted(d for d in ew if a <= d <= b)
    return [(d, ew[d]) for d in ds[::step]], max(ew[d] for d in ds)


def bm_curve(a, b):
    bm = json.load(open("_bt_benchmark.json", encoding="utf-8"))
    b0 = min(bm.values())
    return [(k + "-28", v / b0) for k, v in sorted(bm.items()) if a <= k + "-28" <= b]


# ---------- SVG 折线图 ----------
def svg_chart(title, curves, ymin, ymax, step=6):
    """curves: [(label, [(d, v)], color)]"""
    W, H, L, R, T, B = 680, 320, 52, 14, 30, 44
    px0, px1 = L, W - R
    py0, py1 = T, H - B
    def sx(i, n): return px0 + (px1 - px0) * i / max(n - 1, 1)
    def sy(v): return py1 - (py1 - py0) * (v - ymin) / (ymax - ymin)
    # 网格
    grid = ""
    n_ticks = 5
    for k in range(n_ticks + 1):
        v = ymin + (ymax - ymin) * k / n_ticks
        grid += f'<line x1="{px0}" y1="{sy(v):.1f}" x2="{px1}" y2="{sy(v):.1f}" stroke="#e8e8e8" stroke-width="1"/>'
        grid += f'<text x="{px0-6}" y="{sy(v)+4:.1f}" text-anchor="end" font-size="11" fill="#888">{v*100:.0f}%</text>'
    # 日期轴
    n_dates = max(len(c[1]) for c in curves)
    xl = ""
    for i, lab in [(0, None), (n_dates // 3, None), (2 * n_dates // 3, None), (n_dates - 1, None)]:
        pass
    dlabels = ["" for _ in range(n_dates)]
    if n_dates:
        dlabels[0] = curves[0][1][0][0][:7]
        dlabels[-1] = curves[0][1][-1][0][:7]
    for i, lab in enumerate(dlabels):
        if lab:
            xl += f'<text x="{sx(i, n_dates):.1f}" y="{py1+18}" text-anchor="middle" font-size="11" fill="#555">{lab}</text>'
    polylines = ""
    dots = ""
    for label, pts, color in curves:
        if not pts:
            continue
        n = len(pts)
        s = " ".join(f"{sx(i, n):.1f},{sy(v):.1f}" for i, (d, v) in enumerate(pts))
        polylines += f'<polyline points="{s}" fill="none" stroke="{color}" stroke-width="2.4"/>'
        dots += f'<circle cx="{sx(n-1, n):.1f}" cy="{sy(pts[-1][1]):.1f}" r="3" fill="{color}"/>'
    legends = "".join(
        f'<line x1="{px0+ (i%2)*310}" y1="{py0-26 - (i//2)*0}" x2="{px0+26+(i%2)*310}" y2="{py0-26-(i//2)*0}" stroke="{c}" stroke-width="2.6"/>'
        f'<text x="{px0+32+(i%2)*310}" y="{py0-22-(i//2)*0}" font-size="11.5" fill="#444">{lb}</text>'
        for i, (lb, _, c) in enumerate(curves)
    )
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:760px">
<text x="{px0}" y="16" font-size="13.5" fill="#1f2328" font-weight="600">{title}</text>
{legends}
{grid}
<line x1="{px0}" y1="{sy(0):.1f}" x2="{px1}" y2="{sy(0):.1f}" stroke="#bbb" stroke-width="1" stroke-dasharray="4,3"/>
{polylines}{dots}{xl}
</svg>'''


# 全窗口曲线
full_a, full_b = "2021-06-01", "2026-08-24"
c_lx_full, pk_lx = build_curve("LX-40 现持", full_a, full_b, 8)
c_q20_full, pk_q20 = build_curve("Q20-40 现持", full_a, full_b, 8)
c_ew_full, _ = ew_curve(full_a, full_b, 8)
c_bm_full = bm_curve(full_a, full_b)
y_full_max = max(pk_lx, pk_q20, max(v for _, v in c_ew_full), max(v for _, v in c_bm_full))
y_full_max = max(y_full_max, 1.0) + 0.12
svg_full = svg_chart(
    "当前持仓静态持有 vs 基准 · 全窗口（2021-06 ~ 2026-08，等权·复权·权重漂移）",
    [("LX-40 现持（当前模拟持仓 40 只）", c_lx_full, "#c0392b"),
     ("Q20-40 现持", c_q20_full, "#e67e22"),
     ("半年调仓等权全A 基准", c_ew_full, "#8e44ad"),
     ("中证全指（月K）", c_bm_full, "#5b7c99")],
    0.0, y_full_max, 8)

# 近 1 年曲线
y_a, y_b = "2025-08-25", "2026-08-24"
c_lx_1y, _ = build_curve("LX-40 现持", y_a, y_b, 2)
c_q20_1y, _ = build_curve("Q20-40 现持", y_a, y_b, 2)
c_ew_1y, _ = ew_curve(y_a, y_b, 2)
all_v = [v for _, v in c_lx_1y + c_q20_1y + c_ew_1y]
y_min_1y = min(min(all_v), 0.8) - 0.05
y_max_1y = max(all_v) + 0.05
svg_1y = svg_chart(
    "近 1 年放大（2025-08 ~ 2026-08）",
    [("LX-40 现持", c_lx_1y, "#c0392b"),
     ("Q20-40 现持", c_q20_1y, "#e67e22"),
     ("半年调仓等权全A 基准", c_ew_1y, "#8e44ad")],
    y_min_1y, y_max_1y, 2)

# ---------- 数据表 ----------
w = R["windows"]
bt = R["bt"]
bw = R["bench_win"]
sim = R["sim"]

# 表 1：三口径总览
rows1 = []
def row(name, full, y1, m6, ann=None, mdd=None, note=""):
    rows1.append((name, full, y1, m6, ann, mdd, note))

row("LX-40 现持静态（当前持仓 40 只，固定持有）", w["LX-40 现持"]["full"]["total"], w["LX-40 现持"]["1Y"]["total"], w["LX-40 现持"]["6M"]["total"], w["LX-40 现持"]["full"]["ann"], w["LX-40 现持"]["full"]["mdd"], "固定持仓不换仓，未含成本")
row("Q20-40 现持静态", w["Q20-40 现持"]["full"]["total"], w["Q20-40 现持"]["1Y"]["total"], w["Q20-40 现持"]["6M"]["total"], w["Q20-40 现持"]["full"]["ann"], w["Q20-40 现持"]["full"]["mdd"], "固定持仓不换仓，未含成本")
row("回测 core（LX-core，增速≤25%+PEG≤2）", bt["core"]["total"], None, None, bt["core"]["ann"], bt["core"]["mdd"], "日频复权·半年换仓·含成本")
row("回测 g60（已采纳 garp 门控，增速≤60%+PEG≤1）", bt["g60"]["total"], None, None, bt["g60"]["ann"], bt["g60"]["mdd"], "日频复权·半年换仓·含成本")
row("回测 g30（增速≤30%，候选收紧）", bt["g30"]["total"], None, None, bt["g30"]["ann"], bt["g30"]["mdd"], "日频复权·半年换仓·含成本")
row("基准：半年调仓等权全A", bt["bm_ew"]["total"], bw["ew_1y"]["total"], bw["ew_6m"]["total"], bt["bm_ew"]["ann"], bt["bm_ew"]["mdd"], "同口径池子基准")
row("基准：中证全指 000985.SH", bt["bm_idx"]["total"], bw["bm_1y"]["total"], bw["bm_6m"]["total"], None, bt["bm_idx"]["mdd"], "价格指数；1Y/6M 为月K近似")

tbl1 = "".join(
    f'''<tr>
<td style="text-align:left">{n}</td>
<td class="{cls(f)}">{pct(f)}</td>
<td class="{cls(y1)}">{pct(y1) if y1 is not None else '—'}</td>
<td class="{cls(m6)}">{pct(m6) if m6 is not None else '—'}</td>
<td>{pct(a,1,False) if a else '—'}</td>
<td>{pct(md,1,False) if md else '—'}</td>
<td style="text-align:left;color:#888;font-size:11px">{nt}</td>
</tr>''' for n, f, y1, m6, a, md, nt in rows1)

# 表 2：模拟盘实盘
lx_last, q_last = sim["LX"][-1], sim["Q20"][-1]
rows_sim = [
    ("LX-top40 模拟组合", lx_last["date"], lx_last["nav"], lx_last["cum_ret"], lx_last["bm_cum"], lx_last["cum_ret"] - lx_last["bm_cum"], "2026-08-26 建仓"),
    ("Q20·质衡优选 模拟组合", q_last["date"], q_last["nav"], q_last["cum_ret"], q_last["bm_cum"], q_last["cum_ret"] - q_last["bm_cum"], "2026-08-27 建仓"),
]
tbl_sim = "".join(
    f'''<tr>
<td style="text-align:left">{n}</td><td>{d}</td><td>{nav:,.0f}</td>
<td class="{cls(r)}">{pct(r)}</td><td class="{cls(b)}">{pct(b)}</td>
<td class="{cls(e)}">{pct(e)}</td><td style="text-align:left;color:#888;font-size:11px">{nt}</td></tr>'''
    for n, d, nav, r, b, e, nt in rows_sim)

# 表 3：逐年
yr = R["windows"]
yrs = ["2021", "2022", "2023", "2024", "2025", "2026"]
tbl_yr = "".join(
    f'<td class="{cls(yr["LX-40 现持"]["yearly"].get(y, 0))}">{pct(yr["LX-40 现持"]["yearly"].get(y, 0))}</td>'
    f'<td class="{cls(yr["Q20-40 现持"]["yearly"].get(y, 0))}">{pct(yr["Q20-40 现持"]["yearly"].get(y, 0))}</td>'
    for y in yrs)

# 结论卡片
concl = [
    ("模拟盘 vs 回测：口径不同，不能直接比收益",
     f"模拟盘 LX {pct(lx_last['cum_ret'])} / Q20 {pct(q_last['cum_ret'])} 是建仓仅 2~3 天的实盘净值（含 15bp 成本、未复权现价）；回测 {pct(bt['g60']['total'])} 是 2021-06 ~ 2026-08 五年、日频复权、半年换仓的理论结果。短期实盘与长期回测的量纲不同，对比应看『当前持仓这批股票的历史画像』而非数字本身。"),
    ("LX 现持 5 年 +146%，远超回测 g60 +67%",
     "今天选出的 40 只（低 PE 升序信念）若 5 年前固定持有至今，累计 +146%（年化 19.6%），大幅跑赢动态换仓的回测。这符合『低估价值选股』框架——但需注意这是事后视角（幸存者偏差方向），且近 6M 已回调 -9.4%，当前名单正处深度回撤中。"),
    ("Q20 现持 5 年 +75%，与回测 g60 几乎一致",
     "质量混合版当前名单历史累计 +75.3%，与回测 g60 的 +67.0% 高度吻合——说明 Q20 名单与策略历史平均水平同构；近 6M 仅 -1.2%，质量层在回调中显著抗跌（vs LX -9.4%、等权全A -13.8%）。"),
    ("建仓时点观察",
     "等权全A 近 6M -13.8%：市场整体深度回调。模拟盘 LX 建仓 3 天 +1.04%（vs 基准 +1.15%）已企稳；Q20 建仓 2 天 -0.24%（vs -0.40%）跑赢基准。当前建仓恰好处于回调后半段，与回测『半年调仓低吸』的节奏一致。"),
]

concl_html = "".join(f'''<div class="concl-card">
<div class="concl-title">{t}</div><div class="concl-body">{b}</div></div>''' for t, b in concl)

html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>模拟持仓 vs 组合历史回测 · 对比报告</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#f6f7f9; color:#1f2328; font-family:"Segoe UI","Microsoft YaHei",sans-serif; padding:28px 20px 60px; }}
.wrap {{ max-width:900px; margin:0 auto; }}
h1 {{ font-size:22px; font-weight:700; }}
.sub {{ color:#777; font-size:12.5px; margin-top:6px; }}
.card {{ background:#fff; border:1px solid #e6e8eb; border-radius:12px; padding:18px 20px; margin-top:18px; box-shadow:0 1px 3px rgba(0,0,0,.04); }}
.card h2 {{ font-size:15.5px; margin-bottom:12px; display:flex; align-items:center; gap:8px; }}
.card h2 .tag {{ background:#eef1f5; color:#5a6472; font-size:11px; padding:2px 8px; border-radius:20px; font-weight:500; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th {{ text-align:right; padding:7px 8px; color:#5a6472; font-weight:600; border-bottom:2px solid #e6e8eb; white-space:nowrap; }}
td {{ text-align:right; padding:7px 8px; border-bottom:1px solid #f0f1f3; font-variant-numeric:tabular-nums; }}
tr:last-child td {{ border-bottom:none; }}
td:first-child, th:first-child {{ text-align:left; }}
.pos {{ color:#c0392b; font-weight:600; }}
.neg {{ color:#1a9c5c; font-weight:600; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-top:18px; }}
.kpi {{ background:#fff; border:1px solid #e6e8eb; border-radius:12px; padding:14px 16px; box-shadow:0 1px 3px rgba(0,0,0,.04); }}
.kpi .k-label {{ font-size:12px; color:#5a6472; }}
.kpi .k-val {{ font-size:22px; font-weight:700; margin-top:4px; font-variant-numeric:tabular-nums; }}
.kpi .k-sub {{ font-size:11.5px; color:#999; margin-top:3px; }}
.chart-box {{ margin-top:14px; }}
.concl-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:18px; }}
.concl-card {{ background:#fff; border:1px solid #e6e8eb; border-radius:12px; padding:14px 16px; box-shadow:0 1px 3px rgba(0,0,0,.04); }}
.concl-title {{ font-size:13px; font-weight:700; color:#1f2328; margin-bottom:6px; }}
.concl-body {{ font-size:12.5px; color:#4a5260; line-height:1.65; }}
.note {{ background:#fdf6e3; border-left:3px solid #e8c14a; padding:10px 14px; font-size:12.5px; color:#6b5d2a; border-radius:0 8px 8px 0; margin-top:14px; line-height:1.7; }}
.foot {{ color:#aaa; font-size:11.5px; margin-top:20px; text-align:center; }}
@media(max-width:640px) {{ .concl-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
<h1>模拟持仓 vs 组合历史回测 · 收益对比</h1>
<div class="sub">生成于 {NOW} ｜ 数据源：模拟盘账本（_sim_nav / _sim_q20_nav）· 回测审计（_bt_garp_audit_results）· 真实复权日K（_bt_daily_px_full + 腾讯补拉 6 只）</div>

<div class="kpis">
  <div class="kpi"><div class="k-label">LX-top40 模拟盘（建仓 3 天）</div><div class="k-val {cls(lx_last['cum_ret'])}">{pct(lx_last['cum_ret'])}</div><div class="k-sub">净值 {lx_last['nav']:,.0f} ｜ 中证全指 {pct(lx_last['bm_cum'])}</div></div>
  <div class="kpi"><div class="k-label">Q20·质衡 模拟盘（建仓 2 天）</div><div class="k-val {cls(q_last['cum_ret'])}">{pct(q_last['cum_ret'])}</div><div class="k-sub">净值 {q_last['nav']:,.0f} ｜ 中证全指 {pct(q_last['bm_cum'])}</div></div>
  <div class="kpi"><div class="k-label">LX-40 现持 · 5 年静态</div><div class="k-val {cls(w['LX-40 现持']['full']['total'])}">{pct(w['LX-40 现持']['full']['total'])}</div><div class="k-sub">年化 {pct(w['LX-40 现持']['full']['ann'],1,False)} ｜ 近 6M {pct(w['LX-40 现持']['6M']['total'])}</div></div>
  <div class="kpi"><div class="k-label">Q20-40 现持 · 5 年静态</div><div class="k-val {cls(w['Q20-40 现持']['full']['total'])}">{pct(w['Q20-40 现持']['full']['total'])}</div><div class="k-sub">年化 {pct(w['Q20-40 现持']['full']['ann'],1,False)} ｜ 近 6M {pct(w['Q20-40 现持']['6M']['total'])}</div></div>
  <div class="kpi"><div class="k-label">回测 g60（已采纳口径）</div><div class="k-val {cls(bt['g60']['total'])}">{pct(bt['g60']['total'])}</div><div class="k-sub">年化 {pct(bt['g60']['ann'],1,False)} ｜ MDD {pct(bt['g60']['mdd'],1,False)}</div></div>
  <div class="kpi"><div class="k-label">基准 · 等权全A</div><div class="k-val {cls(bt['bm_ew']['total'])}">{pct(bt['bm_ew']['total'])}</div><div class="k-sub">年化 {pct(bt['bm_ew']['ann'],1,False)} ｜ 中证全指 {pct(bt['bm_idx']['total'])}</div></div>
</div>

<div class="card">
<h2><span>① 三条口径 · 总览对比</span><span class="tag">现持静态=固定当前40只 · 回测=动态换仓 · 基准=同口径池子</span></h2>
<table>
<tr><th style="width:34%">口径 / 组合</th><th>5 年累计<br><span style="font-weight:400;color:#999">2021-06~2026-08</span></th><th>近 1 年</th><th>近 6M</th><th>年化</th><th>MDD</th><th style="text-align:left">说明</th></tr>
{tbl1}
</table>
<div class="note">⚠️ <b>不可直接互推</b>：「现持静态」是今天选出的 40 只股票固定持有 5 年的事后回看（含幸存者偏差方向）；「回测」是每半年按 PIT 因子重新选股、日频复权、含 15bp 成本的动态结果。两者算法不同，对照意义在于判断『当前名单的历史成色』与『策略均值』的差距。</div>
</div>

<div class="card">
<h2><span>② 模拟盘实盘（账本口径，未复权现价·含成本）</span></h2>
<table>
<tr><th style="text-align:left">组合</th><th>最新日期</th><th>净值(元)</th><th>累计收益</th><th>中证全指</th><th>超额</th><th style="text-align:left">建仓</th></tr>
{tbl_sim}
</table>
<div class="note">建仓当日扣除单边 15bp 成本（佣金 5bp + 冲击 10bp），故首日净值 ≈ 998,500。LX 首日 {pct(sim['LX'][0]['cum_ret'])}、Q20 首日 {pct(sim['Q20'][0]['cum_ret'])} 即费用所致。</div>
</div>

<div class="card">
<h2><span>③ 当前持仓 · 逐年收益（现持静态，复权日K）</span></h2>
<table>
<tr><th style="text-align:left">年份</th>{''.join(f'<th style="text-align:center">{y}</th>' for y in yrs)}</tr>
<tr><td style="text-align:left">LX-40 现持</td>{''.join(f'<td class="{cls(w["LX-40 现持"]["yearly"].get(y, 0))}" style="text-align:center">{pct(w["LX-40 现持"]["yearly"].get(y, 0))}</td>' for y in yrs)}</tr>
<tr><td style="text-align:left">Q20-40 现持</td>{''.join(f'<td class="{cls(w["Q20-40 现持"]["yearly"].get(y, 0))}" style="text-align:center">{pct(w["Q20-40 现持"]["yearly"].get(y, 0))}</td>' for y in yrs)}</tr>
</table>
<div class="note" style="margin-top:10px">LX 名单的历史弹性集中在 2024（+27.9%）与 2025（+37.3%）；Q20 名单 2022/2023 两年回撤显著更浅（-7.3%/-3.5% vs LX +2.2%/+10.1%），但弹性略逊——质量混合的『抗跌换弹性』特征在逐年数据上清晰可见。</div>
</div>

<div class="card">
<h2><span>④ 收益曲线</span></h2>
<div class="chart-box">{svg_full}</div>
<div class="chart-box" style="margin-top:24px">{svg_1y}</div>
</div>

<div class="card">
<h2><span>⑤ 结论</span></h2>
<div class="concl-grid">{concl_html}</div>
</div>

<div class="foot">口径提示：现持静态收益未扣成本、不含调仓；回测含成本、半年换仓；模拟盘为未复权现价实盘净值。中证全指 1Y/6M 为月K近似。仅供研究参考，不构成投资建议。</div>
</div>
</body>
</html>'''

open("_cmp_hold_vs_bt_report.html", "w", encoding="utf-8").write(html)
print("→ _cmp_hold_vs_bt_report.html  ", len(html), "bytes")
