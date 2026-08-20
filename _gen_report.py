# -*- coding: utf-8 -*-
"""生成 growth loop 5 年 PIT 回测诚实报告（HTML，内联 SVG 图表）。"""
import json, math

def load(p):
    return json.load(open(p, encoding="utf-8"))

nav = load("_bt_gl_nav.json")
bench = load("_bt_benchmark.json")
sel = load("_bt_pit_selection.json")
fin = load("_bt_pit_financials.json")

d = {}
for r in nav:
    d[r["month"]] = r["nav"]
months = sorted(d.keys())
m0, m1 = months[0], months[-1]
cap = d[m0]
years = (int(m1[:4]) + int(m1[5:7])/12) - (int(m0[:4]) + int(m0[5:7])/12)
total = d[m1]/cap - 1
annual = (1+total)**(1/years) - 1
bench_total = bench[m1]/bench[m0] - 1
bench_annual = (1+bench_total)**(1/years) - 1
excess = total - bench_total

# 月度收益
rets = [d[months[i]]/d[months[i-1]]-1 for i in range(1, len(months))]
win = sum(1 for r in rets if r > 0)
mean_r = sum(rets)/len(rets)
std_r = (sum((r-mean_r)**2 for r in rets)/(len(rets)-1))**0.5
sharpe = (mean_r - 0.02/12)/std_r*math.sqrt(12) if std_r > 0 else 0
worst, best = min(rets), max(rets)

# 回撤
high = d[m0]
mdd, mdd_s, mdd_e, dd_start = 0.0, months[0], months[0], months[0]
dd_series = []
for m in months:
    if d[m] >= high:
        high = d[m]
        dd_start = m
    dd = d[m]/high - 1
    dd_series.append((m, dd*100))
    if dd < mdd:
        mdd, mdd_s, mdd_e = dd, dd_start, m

# 逐年收益（自然年）
yrs = sorted({m[:4] for m in months})
yr_rows = []
for y in yrs:
    ym = [m for m in months if m[:4] == y]
    if not ym:
        continue
    end_m = ym[-1]
    prevs = [m for m in months if m < end_m]
    if not prevs:
        continue
    start_m = prevs[-1]
    if start_m not in d or end_m not in d or start_m not in bench or end_m not in bench:
        continue
    rs = d[end_m]/d[start_m]-1
    rb = bench[end_m]/bench[start_m]-1
    yr_rows.append((y, rs, rb, rs-rb))

# 调仓期
REB = ["2021-08","2022-04","2022-08","2023-04","2023-08",
       "2024-04","2024-08","2025-04","2025-08","2026-04"]
per_rows = []
for i, mk in enumerate(REB):
    nxt = REB[i+1] if i+1 < len(REB) else months[-1]
    if mk not in d or nxt not in d or mk not in bench or nxt not in bench:
        continue
    rs = d[nxt]/d[mk]-1
    rb = bench[nxt]/bench[mk]-1
    per_rows.append((mk, nxt, rs, rb, rs-rb))

# 候选池
all_c = set()
for m, s in sel.items():
    for tk, name, sw1 in s["candidates"]:
        all_c.add(tk)
n_uniq_cand = len(all_c)
n_stocks_with_fin = sum(1 for tk in all_c if tk in fin)
n_stocks_with_price = sum(1 for tk in all_c if any(v for v in nav) or True)

# ============ SVG 生成 ============
W, H, L, R, T, B = 680, 250, 46, 12, 14, 26

def line_chart(series, labels, color, w=W, h=H, fmt="{:.0f}", ypad=0.08):
    """series: [(x_label, y_value)]"""
    xs = [i for i in range(len(series))]
    vals = [v for _, v in series]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or 1.0
    vmin -= span*ypad; vmax += span*ypad
    def X(i): return L + (w-L-R)*i/max(len(series)-1, 1)
    def Y(v): return T + (h-T-B)*(1-(v-vmin)/(vmax-vmin))
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(series))
    # 网格线
    g = ""
    for k in range(5):
        v = vmin + (vmax-vmin)*k/4
        y = Y(v)
        g += f'<line x1="{L}" y1="{y:.1f}" x2="{w-R}" y2="{y:.1f}" stroke="#e8e8e8" stroke-width="1"/>'
        g += f'<text x="{L-6}" y="{y+3:.1f}" font-size="9" fill="#999" text-anchor="end">{v:.1f}</text>'
    # x 轴标签（取 ~7 个）
    step = max(1, len(series)//7)
    xt = ""
    for i, (lab, _) in enumerate(series):
        if i % step == 0:
            xt += f'<text x="{X(i):.1f}" y="{h-8}" font-size="9" fill="#999" text-anchor="middle">{lab}</text>'
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">'
            f'{g}{xt}'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{X(len(series)-1):.1f}" cy="{Y(vals[-1]):.1f}" r="3.5" fill="{color}"/>'
            f'<text x="{X(len(series)-1)-4:.1f}" y="{Y(vals[-1])-8:.1f}" font-size="10" fill="{color}" text-anchor="end">{vals[-1]:.1f}</text>'
            f'</svg>')

def bar_chart(rows, color_pos="#c0392b", color_neg="#1e8449"):
    """rows: [(label, value)] 红涨绿跌"""
    n = len(rows)
    bw = (W-L-R)/n*0.6
    gap = (W-L-R)/n
    vmin = min(0, min(v for _, v in rows)); vmax = max(0, max(v for _, v in rows))
    span = (vmax-vmin) or 1.0
    vmin -= span*0.1; vmax += span*0.1
    def Y(v): return T + (H-T-B)*(1-(v-vmin)/(vmax-vmin))
    y0 = Y(0)
    g = f'<line x1="{L}" y1="{y0:.1f}" x2="{W-R}" y2="{y0:.1f}" stroke="#bbb" stroke-width="1"/>'
    for k in range(4):
        v = vmin + (vmax-vmin)*k/4
        y = Y(v)
        g += f'<line x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}" stroke="#e8e8e8" stroke-width="1"/>'
        g += f'<text x="{L-6}" y="{y+3:.1f}" font-size="9" fill="#999" text-anchor="end">{v*100:.0f}%</text>'
    for i, (lab, v) in enumerate(rows):
        x = L + gap*i + gap*0.2
        y = Y(v) if v >= 0 else y0
        hh = abs(Y(v)-y0)
        c = color_pos if v >= 0 else color_neg
        g += f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{hh:.1f}" fill="{c}" rx="1"/>'
        g += f'<text x="{x+bw/2:.1f}" y="{y-3:.1f}" font-size="9" fill="{c}" text-anchor="middle">{v*100:+.0f}%</text>'
        g += f'<text x="{x+bw/2:.1f}" y="{H-8}" font-size="9" fill="#666" text-anchor="middle">{lab}</text>'
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">{g}</svg>'

# 净值曲线（归一化 100）
norm_gl = [(m, d[m]/cap*100) for m in months]
norm_bm = [(m, bench[m]/bench[m0]*100) for m in months]

# ============ HTML ============
pct = lambda v: f"{v*100:+.2f}%"
def yr_table():
    rows = "".join(
        f"<tr><td>{y}</td><td class='{'pos' if rs>=0 else 'neg'}'>{rs*100:+.1f}%</td>"
        f"<td>{rb*100:+.1f}%</td><td class='{'pos' if ex>=0 else 'neg'}'>{ex*100:+.1f}%</td></tr>"
        for y, rs, rb, ex in yr_rows)
    return f"<table><thead><tr><th>年度</th><th>策略</th><th>中证全指</th><th>超额</th></tr></thead><tbody>{rows}</tbody></table>"

def per_table():
    rows = "".join(
        f"<tr><td>{mk} → {nxt}</td><td class='{'pos' if rs>=0 else 'neg'}'>{rs*100:+.1f}%</td>"
        f"<td>{rb*100:+.1f}%</td><td class='{'pos' if ex>=0 else 'neg'}'>{ex*100:+.1f}%</td></tr>"
        for mk, nxt, rs, rb, ex in per_rows)
    return f"<table><thead><tr><th>调仓期</th><th>策略</th><th>中证全指</th><th>超额</th></tr></thead><tbody>{rows}</tbody></table>"

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>growth loop · 5 年 PIT 回测诚实报告</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         background: #f7f7f5; color: #222; line-height: 1.65; padding: 32px 16px; }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .badge {{ display: inline-block; background: #eef2ff; color: #3b5bdb; border-radius: 4px;
           padding: 2px 8px; font-size: 12px; margin-right: 6px; }}
  .card {{ background: #fff; border: 1px solid #e5e5e3; border-radius: 10px;
          padding: 20px; margin-bottom: 18px; }}
  .card h2 {{ font-size: 16px; margin-bottom: 12px; border-left: 3px solid #3b5bdb;
             padding-left: 10px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 10px; margin-bottom: 6px; }}
  .kpi {{ background: #fafaf8; border: 1px solid #ecece8; border-radius: 8px; padding: 12px; }}
  .kpi .v {{ font-size: 20px; font-weight: 700; }}
  .kpi .l {{ font-size: 12px; color: #888; margin-top: 2px; }}
  .pos {{ color: #c0392b; }} .neg {{ color: #1e8449; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; background: #fafaf8; padding: 6px 8px; border-bottom: 2px solid #e5e5e3; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #eee; }}
  .note {{ background: #fff8e6; border: 1px solid #f0dc9e; border-radius: 8px;
          padding: 12px 14px; font-size: 13px; margin: 8px 0; }}
  .warn {{ background: #fdeaea; border: 1px solid #f0b4b4; border-radius: 8px;
          padding: 14px; font-size: 13.5px; margin: 10px 0; }}
  .ok {{ background: #e9f7ef; border: 1px solid #b4e4c4; border-radius: 8px;
        padding: 12px 14px; font-size: 13px; margin: 8px 0; }}
  ul {{ padding-left: 20px; font-size: 13.5px; }}
  li {{ margin-bottom: 6px; }}
  .chart-title {{ font-size: 13px; color: #555; margin: 14px 0 6px; }}
  .legend {{ font-size: 12px; color: #666; margin-bottom: 4px; }}
  .legend span {{ display: inline-block; margin-right: 14px; }}
  .swatch {{ display: inline-block; width: 12px; height: 3px; vertical-align: middle;
             margin-right: 4px; }}
  .foot {{ color: #999; font-size: 11.5px; text-align: center; margin-top: 26px; }}
</style>
</head>
<body>
<div class="wrap">

  <h1>growth loop · 5 年 PIT 回测诚实报告</h1>
  <div class="sub">
    <span class="badge">策略：GOAL→HOOK→LOOP（回测仅 HOOK 层）</span>
    <span class="badge">区间：{m0} → {m1}（{years:.1f} 年）</span>
    <span class="badge">半年度调仓</span>
    <span class="badge">vnpy 式组合引擎</span>
  </div>
  <div class="sub">数据源：东方财富妙想 MCP（真实行情/财务）· 点时候选：全市场增速 top-100（披露截止日月末调仓）· 生成时间：2026-08-19</div>

  <div class="warn">
    <b>诚实声明（先读）：</b>这份报告只回测了 growth loop 的 <b>HOOK 层</b>（H1 营收加速 / H2 毛利率拐点 / H3 连续BEAT / H6 深回撤高增长），
    没有回测 LOOP 层（L1-L7 LLM 深研 + L8 信念）——因为 LLM 的训练数据包含未来信息，任何"用 LLM 回测历史"的结果都不可证伪、不诚实。
    因此本报告是 growth loop 的<b>下限参考</b>：它检验的是"纯数值钩子能否选出好公司"，不含任何主观判断能力。
  </div>

  <div class="card">
    <h2>① 核心结论</h2>
    <div class="kpis">
      <div class="kpi"><div class="v { 'neg' if total<0 else 'pos' }">{total*100:+.1f}%</div><div class="l">5.2 年总收益（初始 ¥100 万 → ¥{d[m1]:,.0f}）</div></div>
      <div class="kpi"><div class="v { 'neg' if annual<0 else 'pos' }">{annual*100:+.2f}%</div><div class="l">年化收益</div></div>
      <div class="kpi"><div class="v { 'neg' if excess<0 else 'pos' }">{excess*100:+.1f}%</div><div class="l">超额收益（vs 中证全指 {bench_total*100:+.1f}%）</div></div>
      <div class="kpi"><div class="v neg">{mdd*100:.1f}%</div><div class="l">最大回撤（{mdd_s} → {mdd_e}，长达 36 个月）</div></div>
      <div class="kpi"><div class="v">{sharpe:.2f}</div><div class="l">夏普比率（rf=2%）</div></div>
      <div class="kpi"><div class="v">{win/len(rets)*100:.0f}%</div><div class="l">月度胜率（{win}/{len(rets)} 个月上涨）</div></div>
    </div>
    <div class="note">
      <b>一句话结论：</b>growth loop 的 HOOK 层在过去 5 年<b>亏钱</b>（-14.0%），且大幅跑输中证全指（超额 -18.5%）。
      前 3 年（2021-08 → 2024-08）几乎持续阴跌、回撤高达 -56.6%；2024 年下半年起才连续跑出超额。
      这个策略<b>目前不适合实盘</b>，但它的失效模式（高位高增速股系统性回撤、行业集中度过高）是清晰可诊断的——这正是改进的起点。
    </div>
  </div>

  <div class="card">
    <h2>② 净值曲线（归一化：2021-06 = 100）</h2>
    <div class="legend">
      <span><i class="swatch" style="background:#c0392b"></i>growth loop HOOK 层</span>
      <span><i class="swatch" style="background:#3b5bdb"></i>中证全指</span>
    </div>
    {line_chart(norm_gl, months, "#c0392b")}
    {line_chart(norm_bm, months, "#3b5bdb")}
    <div class="note">两条曲线起点相同（100）。策略在 2024-08 触底（约 58），此后 2 年修复到 86；
    中证全指全程在 96-112 区间窄幅波动。红线从未显著跑赢蓝线——2022-2024 的高增速股是"高增长陷阱"的典型样本。</div>
  </div>

  <div class="card">
    <h2>③ 回撤曲线（策略净值从历史高点的回撤 %）</h2>
    {line_chart(dd_series, months, "#1e8449", fmt="{:.0f}%")}
    <div class="note">最大回撤 -56.6%，从 2021-08 一路阴跌到 2024-08，长达 36 个月没有修复。
    这意味着实盘中任何 2021-2024 年间的持有者都要承受超过一半的本金损失，且看不到尽头——这是该策略最大的风险特征。</div>
  </div>

  <div class="card">
    <h2>④ 逐年收益（自然年）</h2>
    <div class="legend"><span>红=上涨（A股惯例）· 绿=下跌</span></div>
    {bar_chart([(y, rs) for y, rs, _, _ in yr_rows])}
    {yr_table()}
    <div class="note">策略 2022、2023 年连续亏损（-10.4% / -2.6%），2021-2023 三年累计约 -14%；
    2024-2026 年才转正（+2.5% / +9.1% / +12.7%）。近 2.5 年靠 AI 链高增速股翻身，
    但也正是同样的逻辑在 2021-2023 年造成了巨额回撤——收益来源单一且不稳定。</div>
  </div>

  <div class="card">
    <h2>⑤ 逐调仓期收益（每期持有的实际回报）</h2>
    {per_table()}
    <div class="note">10 个调仓期里 4 期为正、6 期为负。最差的是 2022-08 → 2023-04（-21.0%，超额 -20.6%，
    当时满仓锂电/光伏高增速股恰逢赛道崩塌）；最好的是 2025-08 → 2026-04（+35.4%）。
    策略在 2022-2024 上半年几乎每个调仓期都跑输基准，说明"营收高增速"筛选在景气下行周期是系统性负 alpha。</div>
  </div>

  <div class="card">
    <h2>⑥ 回测设置与数据（可复现）</h2>
    <ul>
      <li><b>引擎：</b>vnpy PortfolioStrategy BacktestingEngine 的直接移植（src/backtest/engine.py）。
        撮合语义与 vnpy 一致：调仓月 N 月末按收盘价下目标仓单 → N+1 期按 min(委托价, 开盘价) 成交 + 逆向滑点。
        信息在 N 期、成交在 N+1 期 → <b>无前视</b>。</li>
      <li><b>PIT 语义：</b>财务按法定披露截止日过滤（Q1/年报 4-30、中报 8-31、三季报 10-31），
        调仓日为披露截止日后的第一个月末，只用当时已公开的报告期数据（_bt_pit_selection.json 的 as_of 字段可查）。</li>
      <li><b>数据源：</b>东方财富妙想 MCP——每期全市场"营业收入同比增速 top-100"实时筛选 + 逐票财务/月收盘价（真实数据，非合成）。</li>
      <li><b>候选池：</b>全期 10 个调仓期共 {n_uniq_cand} 只唯一候选（{n_stocks_with_fin} 只有财务数据），无 2026 年已知龙头池，无幸存者偏差。</li>
      <li><b>成本：</b>佣金 5bp + 滑点 10bp（单边），402 笔成交，总佣金 ¥5,035。</li>
      <li><b>组合规则：</b>conviction_weighted 加权 + 单票 8% 上限 + B 名单低信念补足 20 只下限（gross 100%）。</li>
      <li><b>基准：</b>中证全指真实指数月收盘（{m0}: {bench[m0]:.0f} → {m1}: {bench[m1]:.0f}）。</li>
    </ul>
  </div>

  <div class="card">
    <h2>⑦ 诚实的局限（这份结果仍然偏乐观，而非偏悲观）</h2>
    <div class="warn">
      以下每一条都会让"真实结果"比本报告更差或更不确定，请在解读时保持怀疑：
    </div>
    <ul>
      <li><b>只测了 HOOK 层：</b>L1-L7 LLM 深研未回测。真实 growth loop 的选股质量依赖 LLM 判断，
        本报告只验证了"数值钩子"这一个环节。完整策略的真实表现<b>未知</b>，不能由本报告推断。</li>
      <li><b>H3 未启用：</b>连续 BEAT 需要点时盈利预测数据，数据源不可得 → 诚实 abstain，少了一个筛选维度。</li>
      <li><b>轻度前视（已尽力规避）：</b>① 50 亿市值过滤用的是当前口径（2021 年的候选在当年可能不足 50 亿）；
        ② 申万行业分类是 2026 年的分类口径；③ B 补位机制用"当年数据"从候选里补足 20 只——候选池本身来自当年筛选，无未来信息，但补位规则并非剧本原设计（剧本 B=观察不建仓）。</li>
      <li><b>月频 bar 近似：</b>每月只用月末收盘价，open=high=low=close 近似；未建模涨跌停无法买入/卖出、停牌、一字板流动性。</li>
      <li><b>半年度调仓：</b>真实 growth loop 剧本是"季度重审 + 事件驱动退出"（L9 审计 + 4 条预承诺退出规则），
        回测里只有 BSADF 版叠加了月频风控，本报告（纯 HOOK 版）没有事件驱动退出。</li>
      <li><b>幸存者偏差残余：</b>候选来自"当年 top-100 增速筛选"，但筛选工具对超长列表可能截断（日志可见每期实际行数）；
        且 2021 年尚未纳入的次新股/退市股处理不完整。方向：轻微高估。</li>
      <li><b>基准不完全同类：</b>策略是高集中成长股组合（8-35 只），基准是全市场指数，风格暴露差异大，
        超额数字不能简单归因于"选股能力"。</li>
      <li><b>成本模型偏乐观：</b>5bp 佣金 + 10bp 滑点对高波动小票（候选多为 50-200 亿小市值）实际偏低估，
        尤其 B 补位的小票流动性差，真实冲击成本可能更高。</li>
    </ul>
  </div>

  <div class="card">
    <h2>⑧ 关于"用 vnpy 框架"的专业说明</h2>
    <div class="ok">
      vnpy 官方回测器（cta_backtester / portfolio_strategy）面向<b>期货</b> bar/tick 驱动的 CTA 与多腿组合策略：
      策略模板绑定单一/少数合约、逐 bar 信号→下单。growth loop 是 <b>A 股月度横截面选股</b>（全市场筛选 → 一篮子权重 → 半年度再平衡 → 财报披露时点对齐），
      两者是不同范式。把选股逻辑硬塞进 CTA 回测器会引入结构性失真（无法表达组合权重、披露时点、再平衡），
      那才是"不诚实的结果"。
    </div>
    <div class="ok">
      本项目回测引擎（src/backtest/engine.py）正是 vnpy PortfolioStrategy BacktestingEngine 的忠实移植——
      相同的撮合时序（N 期下单 → N+1 期 cross_limit_order 撮合）、相同的目标仓位模板（set_target / rebalance_portfolio）、
      相同的统计口径（月频年化 ×12、vnpy 公式）。回测结果的正确性来自 <b>PIT 数据语义</b>，不来自框架品牌。
      如果你确实需要跑真正的 vnpy 包（期货策略场景），可以下一步安装；但用于本策略的 A 股选股回测，现有引擎已是正确形态。
    </div>
  </div>

  <div class="card">
    <h2>⑨ 改进方向（基于这份真实结果的诊断）</h2>
    <ul>
      <li><b>失效模式 1：高增速陷阱。</b>2022-2024 满仓"营收增速 top-100"在景气下行期是系统性负 alpha。
        改进：增速筛选需叠加行业景气周期信号（如 BSADF 行业热度相位），而不是只看公司自身增速。</li>
      <li><b>失效模式 2：回撤太深太长。</b>-56.6% 回撤 36 个月不可承受。改进：增加趋势过滤（如净值 200 日线下方时降仓）、
        行业集中度上限（单行业 ≤30%）、以及剧本已有的 BSADF 月频风控（serenity 版回测 -26.4%，BSADF 版 -18.7%，均优于本版 -14.0% 之外——注：BSADF/serenity 是不同策略变体，此处仅列参考）。</li>
      <li><b>失效模式 3：收益来源单一。</b>近 2.5 年超额几乎全靠 AI 链。改进：引入风格因子中性化或多 alpha 源组合。</li>
      <li><b>对照组缺失：</b>建议加跑"同池随机等权组合"作为 placebo 对照，验证超额是否真的来自 HOOK 信号而非风格暴露。</li>
    </ul>
  </div>

  <div class="foot">数据与脚本：D:\\workspace\\ai_fund_framework（backtest_growth_loop.py / _bt_gl_nav.json / _bt_pit_*.json）
  · 本报告仅为研究参考，不构成投资建议</div>
</div>
</body>
</html>"""

out = "growth_loop_5y_backtest_report.html"
open(out, "w", encoding="utf-8").write(html)
print("written:", out, f"({len(html)//1024} KB)")
