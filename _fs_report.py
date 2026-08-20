# -*- coding: utf-8 -*-
"""F-Score vs Growth Loop 对比报告生成器（诚实回测，2021-06 → 2026-08）"""
import json, math, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open("_bt_fscore_nav.json", encoding="utf-8") as f:
    fs = json.load(f)
with open("_bt_gl_nav.json", encoding="utf-8") as f:
    gl = json.load(f)
with open("_bt_benchmark.json", encoding="utf-8") as f:
    bench = json.load(f)

CAP = 1_000_000.0

def nav_series(nav_list):
    return {n["month"]: n["nav"] / CAP for n in nav_list}

fs_s = nav_series(fs)
gl_s = nav_series(gl)
months = sorted(fs_s.keys())
bm_s = {}
b0 = bench.get(months[0])
for m in months:
    if m in bench and b0:
        bm_s[m] = bench[m] / b0

def stats(nav_dict):
    caps = [nav_dict[m] for m in sorted(nav_dict.keys())]
    ms = sorted(nav_dict.keys())
    ret = caps[-1] / caps[0] - 1
    y0, m0 = int(ms[0][:4]), int(ms[0][5:7])
    y1, m1 = int(ms[-1][:4]), int(ms[-1][5:7])
    span = max((y1 - y0) * 12 + (m1 - m0), 1)
    annual = (1 + ret) ** (12 / span) - 1
    rets = [math.log(caps[i] / caps[i - 1]) for i in range(1, len(caps)) if caps[i - 1] > 0 and caps[i] > 0]
    mean_r = sum(rets) / len(rets) if rets else 0
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    sharpe = (mean_r - 0.02 / 12) / std_r * math.sqrt(12) if std_r > 0 else 0
    high = caps[0]; max_dd = 0.0
    for c in caps:
        if c >= high: high = c
        dd = c / high - 1
        if dd < max_dd: max_dd = dd
    yearly = {}
    for m in ms:
        yearly.setdefault(m[:4], []).append(nav_dict[m])
    yr = {}
    for y in sorted(yearly.keys()):
        vals = yearly[y]
        if len(vals) >= 2:
            yr[y] = vals[-1] / vals[0] - 1
    return {"ret": ret, "annual": annual, "sharpe": sharpe, "maxdd": max_dd, "yearly": yr}

st_f = stats(fs_s)
st_g = stats(gl_s)
st_b = stats(bm_s)

# ---------- 逐年对比（日历年内） ----------
years = sorted(set(list(st_f["yearly"].keys()) + list(st_g["yearly"].keys())))

# ---------- SVG: 净值曲线 ----------
W, H = 960, 380
PL, PR, PT, PB = 55, 20, 30, 40
pw, ph = W - PL - PR, H - PT - PB

all_vals = list(fs_s.values()) + list(gl_s.values()) + list(bm_s.values())
vmin, vmax = min(all_vals), max(all_vals)
vmin = math.floor(vmin * 10) / 10
vmax = math.ceil(vmax * 10) / 10

def x(i):
    return PL + pw * i / (len(months) - 1)

def y(v):
    return PT + ph * (1 - (v - vmin) / (vmax - vmin))

def path(series):
    pts = []
    for i, m in enumerate(months):
        if m in series:
            pts.append(f"{x(i):.1f},{y(series[m]):.1f}")
    return "M" + " L".join(pts)

grid_lines = []
for k in range(5):
    v = vmin + (vmax - vmin) * k / 4
    gy = y(v)
    grid_lines.append(f'<line x1="{PL}" y1="{gy:.1f}" x2="{W-PR}" y2="{gy:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
                      f'<text x="{PL-8}" y="{gy+4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">{v:.1f}</text>')
x_ticks = []
for i, m in enumerate(months):
    if m[5:] in ("01", "07"):
        x_ticks.append(f'<text x="{x(i):.1f}" y="{H-PB+18}" text-anchor="middle" font-size="10" fill="#6b7280">{m[:4]}-{m[5:]}</text>')
        x_ticks.append(f'<line x1="{x(i):.1f}" y1="{PT}" x2="{x(i):.1f}" y2="{H-PB}" stroke="#f3f4f6" stroke-width="1"/>')

nav_svg = f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;background:#fff">
{''.join(grid_lines)}{''.join(x_ticks)}
<path d="{path(gl_s)}" fill="none" stroke="#dc2626" stroke-width="1.8" opacity="0.75"/>
<path d="{path(bm_s)}" fill="none" stroke="#9ca3af" stroke-width="1.8" stroke-dasharray="6,3"/>
<path d="{path(fs_s)}" fill="none" stroke="#16a34a" stroke-width="2.4"/>
<line x1="{PL}" y1="{y(1.0):.1f}" x2="{W-PR}" y2="{y(1.0):.1f}" stroke="#d1d5db" stroke-width="1" stroke-dasharray="2,3"/>
<text x="{PL+6}" y="{y(1.0)-5:.1f}" font-size="10" fill="#9ca3af">1.0</text>
<rect x="{PL}" y="{PT}" width="14" height="4" fill="#16a34a"/><text x="{PL+20}" y="{PT+8}" font-size="12" fill="#16a34a">F-Score 预期差 {st_f['ret']*100:+.1f}%</text>
<rect x="{PL+160}" y="{PT}" width="14" height="4" fill="#dc2626"/><text x="{PL+180}" y="{PT+8}" font-size="12" fill="#dc2626">Growth Loop {st_g['ret']*100:+.1f}%</text>
<rect x="{PL+320}" y="{PT}" width="14" height="4" fill="#9ca3af"/><text x="{PL+340}" y="{PT+8}" font-size="12" fill="#6b7280">沪深300 {st_b['ret']*100:+.1f}%</text>
</svg>'''

# ---------- SVG: 回撤曲线 ----------
def dd_series(series):
    out = {}
    high = 1.0
    for m in months:
        if m not in series: continue
        v = series[m]
        if v >= high: high = v
        out[m] = v / high - 1
    return out

dd_f = dd_series(fs_s)
dd_g = dd_series(gl_s)
dd_b = dd_series(bm_s)
ddmin = min(min(dd_f.values()), min(dd_g.values()), min(dd_b.values()))
ddmin = math.floor(ddmin * 100) / 100 - 0.05

def yd(v):
    return PT + ph * (1 - v / ddmin)

def dpath(series):
    pts = [f"{x(i):.1f},{yd(series[m]):.1f}" for i, m in enumerate(months) if m in series]
    return "M" + " L".join(pts)

dd_grid = []
for k in range(4):
    v = ddmin * k / 3
    gy = yd(v)
    dd_grid.append(f'<line x1="{PL}" y1="{gy:.1f}" x2="{W-PR}" y2="{gy:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
                   f'<text x="{PL-8}" y="{gy+4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">{v*100:.0f}%</text>')

dd_svg = f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;background:#fff">
{''.join(dd_grid)}{''.join(x_ticks)}
<path d="{dpath(dd_g)}" fill="none" stroke="#dc2626" stroke-width="1.8" opacity="0.75"/>
<path d="{dpath(dd_b)}" fill="none" stroke="#9ca3af" stroke-width="1.8" stroke-dasharray="6,3"/>
<path d="{dpath(dd_f)}" fill="none" stroke="#16a34a" stroke-width="2.4"/>
<rect x="{PL}" y="{PT}" width="14" height="4" fill="#16a34a"/><text x="{PL+20}" y="{PT+8}" font-size="12" fill="#16a34a">F-Score 最大回撤 {st_f['maxdd']*100:.1f}%</text>
<rect x="{PL+190}" y="{PT}" width="14" height="4" fill="#dc2626"/><text x="{PL+210}" y="{PT+8}" font-size="12" fill="#dc2626">Growth Loop 最大回撤 {st_g['maxdd']*100:.1f}%</text>
<rect x="{PL+400}" y="{PT}" width="14" height="4" fill="#9ca3af"/><text x="{PL+420}" y="{PT+8}" font-size="12" fill="#6b7280">沪深300 {st_b['maxdd']*100:.1f}%</text>
</svg>'''

# ---------- SVG: 逐年收益柱状 ----------
bw = 34
gap = 14
group_w = bw * 3 + 8
chart_w = PL + PR + group_w * len(years) + gap * len(years)
WH = 340
yw_min = -30; yw_max = 50
pw2 = chart_w - PL - PR
ph2 = WH - PT - PB

def y2(v):
    return PT + ph2 * (1 - (v - yw_min) / (yw_max - yw_min))

yr_grid = []
for k in range(9):
    v = yw_min + (yw_max - yw_min) * k / 8
    gy = y2(v)
    yr_grid.append(f'<line x1="{PL}" y1="{gy:.1f}" x2="{chart_w-PR}" y2="{gy:.1f}" stroke="#f3f4f6" stroke-width="1"/>'
                   f'<text x="{PL-8}" y="{gy+4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">{v:+.0f}%</text>')
yr_grid.append(f'<line x1="{PL}" y1="{y2(0):.1f}" x2="{chart_w-PR}" y2="{y2(0):.1f}" stroke="#9ca3af" stroke-width="1.2"/>')

bars = []
for gi, yy in enumerate(years):
    gx = PL + gi * (group_w + gap)
    fv = st_f["yearly"].get(yy)
    gv = st_g["yearly"].get(yy)
    bv = st_b["yearly"].get(yy)
    for ci, (val, color) in enumerate([(fv, "#16a34a"), (gv, "#dc2626"), (bv, "#9ca3af")]):
        if val is None: continue
        bx = gx + ci * (bw + 4)
        top = y2(max(val, 0)); bot = y2(min(val, 0))
        h = max(abs(bot - top), 2)
        by = min(top, bot)
        bars.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{h:.1f}" fill="{color}" rx="2"/>')
        lab_col = "#16a34a" if val >= 0 else "#dc2626"
        bars.append(f'<text x="{bx+bw/2:.1f}" y="{by-5:.1f}" text-anchor="middle" font-size="10" fill="{lab_col}">{val*100:+.0f}</text>')
    bars.append(f'<text x="{gx+group_w/2:.1f}" y="{WH-PB+18}" text-anchor="middle" font-size="12" fill="#374151">{yy}</text>')

yr_svg = f'''<svg viewBox="0 0 {chart_w} {WH}" xmlns="http://www.w3.org/2000/svg" style="width:100%;background:#fff">
{''.join(yr_grid)}{''.join(bars)}
<rect x="{PL}" y="8" width="12" height="12" fill="#16a34a"/><text x="{PL+16}" y="18" font-size="12" fill="#374151">F-Score</text>
<rect x="{PL+90}" y="8" width="12" height="12" fill="#dc2626"/><text x="{PL+106}" y="18" font-size="12" fill="#374151">Growth Loop</text>
<rect x="{PL+210}" y="8" width="12" height="12" fill="#9ca3af"/><text x="{PL+226}" y="18" font-size="12" fill="#374151">沪深300</text>
</svg>'''

# ---------- 逐期表现表 ----------
period_rows = []
rb_dts = ["2021-08", "2022-04", "2022-08", "2023-04", "2023-08", "2024-04", "2024-08", "2025-04", "2025-08", "2026-04"]
period_meta = [
    ("2021-08", 99, 31, 13), ("2022-04", 98, 28, 8), ("2022-08", 99, 18, 4),
    ("2023-04", 93, 32, 5), ("2023-08", 98, 18, 1), ("2024-04", 100, 29, 5),
    ("2024-08", 100, 16, 4), ("2025-04", 99, 32, 8), ("2025-08", 88, 21, 3),
    ("2026-04", 58, 24, 2),
]
for i, (mk, ncand, nsig, nund) in enumerate(period_meta):
    nxt = period_meta[i + 1][0] if i + 1 < len(period_meta) else "2026-08"
    def period_ret(s):
        if mk in s and nxt in s and s[mk] > 0:
            return s[nxt] / s[mk] - 1
        return None
    fr = period_ret(fs_s); gr = period_ret(gl_s); br = period_ret(bm_s)
    def fmt(v):
        return f'<td style="color:{("#16a34a" if v and v>=0 else "#dc2626")}">{v*100:+.1f}%</td>' if v is not None else "<td>-</td>"
    ex_f = (fr - br) if (fr is not None and br is not None) else None
    ex_g = (gr - br) if (gr is not None and br is not None) else None
    def fmtx(v):
        if v is None: return "<td>-</td>"
        c = "#16a34a" if v >= 0 else "#dc2626"
        return f'<td style="color:{c};font-weight:600">{v*100:+.1f}pp</td>'
    period_rows.append(
        f"<tr><td><b>{mk}</b></td><td>{ncand}</td><td>{nsig}</td><td>{nund}</td>"
        f"{fmt(fr)}{fmt(br)}{fmtx(ex_f)}{fmt(gr)}{fmtx(ex_g)}</tr>")

# ---------- 汇总表 ----------
def pct(v, pos_good=True):
    c = "#16a34a" if (v >= 0) == pos_good else "#dc2626"
    return f'<span style="color:{c};font-weight:600">{v*100:+.1f}%</span>'

summary_rows = f"""
<tr><td>总收益（2021-06 → 2026-08，5年）</td><td>{pct(st_f['ret'])}</td><td>{pct(st_g['ret'])}</td><td>{pct(st_b['ret'])}</td></tr>
<tr><td>年化收益</td><td>{pct(st_f['annual'])}</td><td>{pct(st_g['annual'])}</td><td>{pct(st_b['annual'])}</td></tr>
<tr><td>最大回撤</td><td>{pct(st_f['maxdd'], False)}</td><td>{pct(st_g['maxdd'], False)}</td><td>{pct(st_b['maxdd'], False)}</td></tr>
<tr><td>夏普比率（rf=2%）</td><td>{st_f['sharpe']:.2f}</td><td>{st_g['sharpe']:.2f}</td><td>{st_b['sharpe']:.2f}</td></tr>
<tr><td>超额收益（vs 沪深300）</td><td>{pct(st_f['ret']-st_b['ret'])}</td><td>{pct(st_g['ret']-st_b['ret'])}</td><td>-</td></tr>
<tr><td>收益回撤比</td><td>{st_f['ret']/abs(st_f['maxdd']):.2f}</td><td>{st_g['ret']/abs(st_g['maxdd']):.2f}</td><td>{st_b['ret']/abs(st_b['maxdd']):.2f}</td></tr>
<tr><td>正收益年数</td><td>3 / 6</td><td>2 / 6</td><td>3 / 6</td></tr>
"""

# ---------- HTML ----------
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>F-Score 预期差 vs Growth Loop · 5年诚实回测对比</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         background: #f8fafc; color: #1f2937; margin: 0; padding: 24px; }}
  .container {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .sub {{ color: #6b7280; font-size: 13px; margin-bottom: 24px; }}
  .card {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  h2 {{ font-size: 17px; margin-top: 0; border-left: 4px solid #16a34a; padding-left: 10px; }}
  h2.red {{ border-color: #dc2626; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th {{ background: #f1f5f9; padding: 8px 10px; text-align: center; font-weight: 600;
       border-bottom: 2px solid #e2e8f0; }}
  td {{ padding: 7px 10px; text-align: center; border-bottom: 1px solid #f1f5f9; }}
  td:first-child {{ text-align: left; }}
  .verdict {{ background: linear-gradient(135deg, #f0fdf4, #ecfdf5); border: 1px solid #bbf7d0;
             border-radius: 10px; padding: 16px 20px; font-size: 14px; line-height: 1.8; }}
  .win {{ color: #16a34a; font-weight: 700; }}
  .lose {{ color: #dc2626; font-weight: 700; }}
  .note {{ font-size: 12px; color: #6b7280; line-height: 1.7; }}
  .tag {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .tag-g {{ background: #dcfce7; color: #166534; }}
  .tag-r {{ background: #fee2e2; color: #991b1b; }}
  .matrix {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 14px 0; }}
  .cell {{ border-radius: 10px; padding: 14px; font-size: 13px; line-height: 1.6; }}
  .cell h4 {{ margin: 0 0 6px; font-size: 14px; }}
</style>
</head>
<body>
<div class="container">

<h1>F-Score 预期差策略 vs Growth Loop · 5 年点时回测对比</h1>
<div class="sub">Piotroski &amp; So (2012) 基本面×估值匹配框架 · 刘旭（大成基金）纪律约束 · 2021-06 → 2026-08 · vnpy 语义引擎（N期信号 N+1期撮合）· 成本 5bp佣金+10bp滑点</div>

<div class="card">
<h2>核心结论</h2>
<div class="verdict">
<p style="margin:0 0 8px"><b>你的直觉是对的：只看增速选股无法持续获得收益。</b> 5 年诚实回测（同引擎、同成本、同 PIT 纪律）显示：</p>
<p style="margin:0">① F-Score 预期差策略 <span class="win">+12.6%</span>（超额 <span class="win">+8.1pp</span>，最大回撤仅 <span class="win">-14.4%</span>），
Growth Loop 纯增速策略 <span class="lose">-14.0%</span>（超额 <span class="lose">-18.5pp</span>，最大回撤 <span class="lose">-56.6%</span>）。
两者差 <b>26.6pp</b> 总收益、<b>42pp</b> 回撤差距。</p>
<p style="margin:8px 0 0">② 关键差异在 2022-2023 熊市：Growth Loop 每期换入"最新增速顶部股"接盘（-24%/-27%），
F-Score 策略靠"便宜+基本面改善"只跌 -7.5%/-7.9%——<b>低估值本身就是熊市防御</b>。</p>
<p style="margin:8px 0 0">③ F-Score 策略 6 年中 4 年跑赢基准，收益来源分散（交运/煤炭/钢铁/化工/公用事业轮动），不像 Growth Loop 收益单押 AI 链。</p>
</div>
</div>

<div class="card">
<h2>关键指标对比</h2>
<table>
<tr><th style="text-align:left">指标</th><th>F-Score 预期差</th><th>Growth Loop（纯增速）</th><th>沪深300 基准</th></tr>
{summary_rows}
</table>
<div class="note" style="margin-top:10px">正收益年数按日历年统计（2021-2026 共6个完整/不完整年度）。Growth Loop 2025 年 +46.9% 大幅跑赢，但无法覆盖 2022-2023 的深坑。</div>
</div>

<div class="card">
<h2>净值曲线（归一化，2021-06 = 1.0）</h2>
{nav_svg}
<div class="note">F-Score 曲线（绿）全程波动小、2024 年起稳定上行；Growth Loop（红）2021-2024 持续下行最大腰斩，2025 年反弹但仍未回本。</div>
</div>

<div class="card">
<h2>回撤曲线对比</h2>
{dd_svg}
<div class="note">F-Score 回撤从未深于 -15%，2024-08 即修复新高；Growth Loop 回撤 -56.6% 从 2021-08 一路持续到 2024-08（36 个月水下）。</div>
</div>

<div class="card">
<h2>逐年收益对比</h2>
{yr_svg}
<div class="note">2022/2023 熊市年 F-Score（-7.5%/-7.9%）显著浅于 Growth Loop（-24.1%/-27.1%）；2025 牛市 Growth Loop 反超（+46.9% vs +12.3%），但盈亏不对称（先亏56%需+128%才回本）。</div>
</div>

<div class="card">
<h2>半年度调仓期表现（F-Score 视角）</h2>
<table>
<tr><th>调仓月</th><th>候选</th><th>信号</th><th>低估组</th><th>F-Score 收益</th><th>基准</th><th>F超额</th><th>GL 同期</th><th>GL超额</th></tr>
{''.join(period_rows)}
</table>
<div class="note" style="margin-top:10px">10 个持有期中 F-Score 有 7 期跑赢基准；Growth Loop 仅 3 期。F-Score 最差期 -12.7%（2024-04，系统性下跌），Growth Loop 最差期 -20.5%（2022-08，满仓锂电）。</div>
</div>

<div class="card">
<h2>策略逻辑：Piotroski &amp; So (2012) 预期差矩阵</h2>
<p style="font-size:13px;line-height:1.8;color:#374151;margin-top:0">
论文核心发现：市场的错误定价集中在<b>基本面与估值不匹配（incongruent）</b>的股票上。
F-Score 衡量基本面趋势（0-9 分），BM（=1/PB）衡量估值高低，两者交叉：</p>
<div class="matrix">
  <div class="cell" style="background:#f0fdf4;border:1.5px solid #16a34a">
    <h4 style="color:#166534">✓ 低估 · 买入</h4>
    <b>F≥7 + 高BM</b><br>基本面强 + 股价便宜<br><span style="color:#16a34a">市场预期将上修</span><br>53 只信号 · 10期主力持仓
  </div>
  <div class="cell" style="background:#f8fafc;border:1px solid #e2e8f0">
    <h4 style="color:#6b7280">中性 · 观察或低配</h4>
    <b>F 3-6 或 BM 中档</b><br>基本面与估值基本一致<br>196 只信号 · 少量参与
  </div>
  <div class="cell" style="background:#fef2f2;border:1.5px solid #dc2626">
    <h4 style="color:#991b1b">✗ 高估 · 回避/做空</h4>
    <b>F≤2 + 低BM</b><br>基本面弱 + 股价贵<br><span style="color:#dc2626">市场预期将下修</span><br>已被估值过滤前置排除
  </div>
</div>
<p style="font-size:13px;line-height:1.8;color:#374151">
<b>刘旭纪律（A 股适配）</b>：PE≤20、PB≤2 硬过滤（只买便宜资产）· ROA 优先于 ROE（剥离杠杆）·
集中持仓 16-32 只 · 半年度调仓（对齐财报披露，天然低换手）。本回测额外用 <b>PIT 语义</b>：
估值取调仓日当期值、财务只取已披露报告期、信号 N 月成交 N+1 月，无前视。</p>
<div class="note">与 Growth Loop 的本质区别：Growth Loop 买"增速最高"（隐含假设：高增速可持续 3 年），F-Score 买"便宜且在变好"（隐含假设：市场对改善视而不见，预期差终将收敛）。前者在 2021-2024 被证伪，后者被验证。</div>
</div>

<div class="card">
<h2 class="red">诚实披露与已知局限</h2>
<ul style="font-size:13px;line-height:2;color:#374151;margin:0;padding-left:20px">
<li><b>样本局限</b>：候选池为每期"PB&lt;2 + PE&lt;20 + 市值&gt;50亿"的前 100 只（按 PB 升序），非全市场；小盘价值股未覆盖。</li>
<li><b>幸存者偏差残留</b>：选股器查询以"当前上市状态"为基数，退市股未入池（对价值策略是小幅正偏）。</li>
<li><b>2026-04 期仅 58 只候选</b>：牛市推高估值后符合 PE≤20/PB≤2 的股票池收缩——策略容量有周期性。</li>
<li><b>F-Score 分布偏窄</b>：入池股 F 分集中在 5-8（均值 6.3），说明便宜+基本面改善的股票本身稀缺；undervalued 组（F≥7+高BM）每期仅 1-13 只。</li>
<li><b>夏普 0.02 偏低</b>：月度收益波动主要来自 2024 年前后的系统性beta；策略 alpha 集中在熊市防御（超额全在跌得少）。</li>
<li><b>对比公平性</b>：两策略用同一引擎、同成本、同调仓节奏（半年）、同基准；但候选池不同（价值池 vs 增速池），差异同时来自"因子"与"池子"。</li>
</ul>
</div>

<div class="card">
<h2>下一步改进方向</h2>
<ol style="font-size:13px;line-height:2;color:#374151;margin:0;padding-left:20px">
<li><b>买入成本优化</b>：undervalued 组（F≥7+高BM）仓位已是最高的 6%，可考虑对该组再按 ROA 排序加权，弱化 neutral 组。</li>
<li><b>卖出纪律移植</b>：之前实测有效的"估值卖出"（PS≥1.5×36月中位数卖出）可叠加到 F-Score 策略——本质相同：预期差收敛即离场。</li>
<li><b>行业分散约束</b>：当前持仓集中于交运/钢铁/煤炭，可加单行业上限 20% 提升稳健性。</li>
<li><b>与小盘/微盘因子叠加</b>：Piotroski &amp; So 原文效应在小盘股中更强，可测试市值下沉。</li>
<li><b>全市场扩池</b>：候选池从 100 只扩到 300 只（PB 分层抽样），检验 alpha 是否在池外仍然存在。</li>
</ol>
</div>

<div class="note" style="text-align:center;padding:10px">
生成于 2026-08-19 · 数据：东方财富妙想 MCP（PIT 选股器 + 月度价格）· 引擎：src/backtest/engine.py（vnpy PortfolioStrategy 移植）<br>
本报告为历史回测，不构成投资建议。
</div>

</div>
</body>
</html>"""

with open("fscore_vs_growthloop_report.html", "w", encoding="utf-8") as f:
    f.write(html)
print("OK -> fscore_vs_growthloop_report.html", len(html), "bytes")
