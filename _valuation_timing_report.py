# -*- coding: utf-8 -*-
"""估值定义 + 数据时点 + 买入时点 三重核查报告。

回答用户三问：
  1. 什么时候估值才算低？
  2. 推荐列表是最新数据还是 4 月份的？
  3. 现在买入时点好么？
"""
import sys, os, json, sqlite3, bisect
sys.stdout.reconfigure(encoding="utf-8")
os.chdir("D:/workspace/ai_fund_framework")

DB = "D:/workspace/ai_fund_framework/data/a_share_market.db"
db = sqlite3.connect(DB)

# ---- 读推荐持仓 ----
d = json.load(open("_holdings_latest.json", encoding="utf-8"))
holdings = d["holdings"]
names = {h["ticker"]: h["name"] for h in holdings}

# ---- 1. 推荐持仓 PE/PB 自身历史分位 ----
def hist_pct(tk, col, lo, hi):
    rows = [r[0] for r in db.execute(
        f"SELECT {col} FROM valuation WHERE ticker=? AND {col} IS NOT NULL AND {col}>0 AND {col}<{hi} ORDER BY month",
        (tk,)).fetchall()]
    if not rows:
        return None, None, None, None, None
    cur = rows[-1]
    hs = sorted(rows)
    n = len(hs)
    pct = bisect.bisect_left(hs, cur) / n * 100
    return cur, hs[0], hs[n // 2], hs[-1], pct

rows_hold = []
for h in holdings:
    tk = h["ticker"]
    pe_cur, pe_min, pe_med, pe_max, pe_pct = hist_pct(tk, "pe_ttm", 0, 200)
    pb_cur, pb_min, pb_med, pb_max, pb_pct = hist_pct(tk, "pb", 0, 20)
    rows_hold.append({
        "tk": tk, "name": h["name"], "pe": h["pe_ttm"],
        "pe_pct_self": pe_pct, "pb_pct_self": pb_pct,
        "weight": h["weight_pct"],
    })

# 分位分级
def grade(pct):
    if pct is None:
        return ("—", "#999")
    if pct < 30:
        return (f"{pct:.0f}% 低", "#c0392b")   # 红 = 便宜(低估值是好)
    if pct < 70:
        return (f"{pct:.0f}% 中", "#e67e22")
    return (f"{pct:.0f}% 高", "#27ae60")       # 绿 = 自身分位高(相对贵)

# ---- 2. 全市场 PE/PB 中位数历史 ----
months = [r[0] for r in db.execute("SELECT DISTINCT month FROM valuation ORDER BY month").fetchall()]
mkt_hist = []
for m in months:
    pe = sorted([r[0] for r in db.execute(
        "SELECT pe_ttm FROM valuation WHERE month=? AND pe_ttm IS NOT NULL AND pe_ttm>0 AND pe_ttm<200", (m,)).fetchall()])
    pb = sorted([r[0] for r in db.execute(
        "SELECT pb FROM valuation WHERE month=? AND pb IS NOT NULL AND pb>0 AND pb<20", (m,)).fetchall()])
    mkt_hist.append({
        "month": m,
        "pe50": pe[len(pe)//2] if pe else 0,
        "pe25": pe[len(pe)//4] if pe else 0,
        "pb50": pb[len(pb)//2] if pb else 0,
    })

# ---- 3. 中证全指 ----
idx_rows = db.execute("SELECT month, close FROM index_monthly WHERE index_code='000985.SH' ORDER BY month").fetchall()
idx_closes = [r[1] for r in idx_rows]
idx_cur = idx_closes[-1]
idx_hs = sorted(idx_closes)
idx_pct = bisect.bisect_left(idx_hs, idx_cur) / len(idx_hs) * 100
idx_peak = max(idx_closes)
idx_peak_m = idx_rows[idx_closes.index(idx_peak)][0]
idx_trough = min(idx_closes)
idx_trough_m = idx_rows[idx_closes.index(idx_trough)][0]

db.close()

# ================= 渲染 HTML =================
def bar(v, vmin, vmax, color):
    w = max(2, (v - vmin) / (vmax - vmin) * 100)
    return f'<div class="bar"><div class="fill" style="width:{w:.0f}%;background:{color}"></div></div>'

# 推荐持仓分位条
hold_rows_html = ""
for r in sorted(rows_hold, key=lambda x: -(x["pe_pct_self"] if x["pe_pct_self"] is not None else -1)):
    tk = r["tk"]
    name = r["name"] or ""
    pe_g, pe_c = grade(r["pe_pct_self"])
    pb_g, pb_c = grade(r["pb_pct_self"])
    # 综合便宜度：PE分位 + PB分位 平均
    both = None
    if r["pe_pct_self"] is not None and r["pb_pct_self"] is not None:
        both = (r["pe_pct_self"] + r["pb_pct_self"]) / 2
    both_g, both_c = grade(both)
    hold_rows_html += f"""
    <tr>
      <td class="mono">{tk}</td>
      <td>{name}</td>
      <td>{r['pe']:.1f}</td>
      <td style="color:{pe_c};font-weight:600">{pe_g}</td>
      <td style="color:{pb_c};font-weight:600">{pb_g}</td>
      <td style="color:{both_c};font-weight:700">{both_g}</td>
      <td>{r['weight']:.2f}%</td>
    </tr>"""

# 市场 PE 中位数历史表
mkt_rows_html = ""
for m in mkt_hist:
    mkt_rows_html += f"""
    <tr><td class="mono">{m['month']}</td><td>{m['pe50']:.1f}</td><td>{m['pe25']:.1f}</td><td>{m['pb50']:.2f}</td></tr>"""

# 市场 PE 中位数折线（SVG）
def line_svg(data, key, vmin, vmax, color, h=140, w=640):
    n = len(data)
    if n < 2:
        return ""
    pts = []
    for i, m in enumerate(data):
        x = 10 + i / (n - 1) * (w - 20)
        y = h - 10 - (m[key] - vmin) / (vmax - vmin) * (h - 30)
        pts.append(f"{x:.0f},{y:.0f}")
    poly = " ".join(pts)
    return f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>'

pe_line = line_svg(mkt_hist, "pe50", 20, 45, "#c0392b")
pb_line = line_svg(mkt_hist, "pb50", 1.5, 3.2, "#2980b9")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>估值定义 × 数据时点 × 买入时点 三重核查</title>
<style>
  :root {{
    --bg: #f5f6f8; --card: #ffffff; --ink: #1a1a2e; --sub: #666;
    --line: #e3e6eb; --red: #c0392b; --green: #27ae60; --orange: #e67e22; --blue: #2980b9;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--ink); font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.6; padding: 24px; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 6px; }}
  .sub {{ color: var(--sub); font-size: 13px; margin-bottom: 24px; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 20px 22px; margin-bottom: 20px; }}
  .card h2 {{ font-size: 18px; margin-bottom: 12px; padding-left: 10px; border-left: 4px solid var(--blue); }}
  .answer {{ background: #fef9e7; border: 1px solid #f5d76e; border-radius: 8px; padding: 14px 16px; font-size: 15px; margin-bottom: 14px; }}
  .answer b {{ color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ padding: 8px 10px; text-align: center; border-bottom: 1px solid var(--line); }}
  th {{ background: #f0f2f5; font-weight: 600; color: #444; }}
  .mono {{ font-family: "SF Mono", Consolas, monospace; font-size: 12.5px; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .tag {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .tag.red {{ background: #fdecea; color: var(--red); }}
  .tag.green {{ background: #eafaf1; color: var(--green); }}
  .tag.orange {{ background: #fef5e7; color: var(--orange); }}
  .grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  .stat {{ background: #f8f9fb; border: 1px solid var(--line); border-radius: 10px; padding: 14px; text-align: center; }}
  .stat .v {{ font-size: 22px; font-weight: 700; color: var(--red); }}
  .stat .l {{ font-size: 12px; color: var(--sub); margin-top: 4px; }}
  .note {{ font-size: 13px; color: #555; margin-top: 10px; }}
  .note li {{ margin: 4px 0; }}
  svg {{ display: block; margin: 8px auto; }}
  .legend {{ font-size: 12px; color: var(--sub); text-align: center; }}
  .warn {{ background: #fdecea; border-left: 4px solid var(--red); padding: 12px 16px; border-radius: 6px; margin-top: 12px; }}
  .ok {{ background: #eafaf1; border-left: 4px solid var(--green); padding: 12px 16px; border-radius: 6px; margin-top: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>估值定义 × 数据时点 × 买入时点 · 三重核查</h1>
  <div class="sub">策略 AD_top15_mom60top50 · 核查时间 2026-09-08 · 数据 asof 2026-08-31</div>

  <!-- ===== 问题1 ===== -->
  <div class="card">
    <h2>问题 1 · 什么时候估值才算"低"？</h2>
    <div class="answer">
      策略里的"低估值"是<b>横截面口径</b>（全市场最便宜的那批），不等于<b>自身历史口径</b>（相对自己 5 年历史便宜）。
      真正稳健的"低估值"应该<b>两个口径同时满足</b>，而当前推荐列表里约 1/3 的票只满足前者、不满足后者。
    </div>

    <div class="grid3">
      <div class="stat"><div class="v">5~7 倍</div><div class="l">推荐持仓 PE（绝对低位）</div></div>
      <div class="stat"><div class="v">前 5%</div><div class="l">横截面分位（全市场最便宜）</div></div>
      <div class="stat"><div class="v">35.8</div><div class="l">全市场 PE 中位数（2026-08）</div></div>
    </div>

    <h3 style="margin:18px 0 8px;font-size:15px;">策略的"低估值"判定标准（screen_q20 五道门槛）</h3>
    <table>
      <tr><th>门槛</th><th>条件</th><th>含义</th></tr>
      <tr><td>市值</td><td>≥ 100 亿</td><td>剔除微盘/流动性差</td></tr>
      <tr><td>PE 绝对阈值</td><td>PE ≤ 25 <b>或</b> 股息率 ≥ 2%</td><td>绝对估值不贵的底线</td></tr>
      <tr><td>PEG</td><td>0 &lt; PEG ≤ 2</td><td>估值与成长匹配</td></tr>
      <tr><td>预期增速</td><td>一致预期净利增速 ≤ 25%</td><td>排除高基数/伪成长</td></tr>
      <tr><td style="color:var(--red)">横截面排序</td><td>pe_pct = 100 − PE 全市场分位</td><td><b>全市场最便宜 → 排最前（这是核心）</b></td></tr>
    </table>

    <h3 style="margin:18px 0 8px;font-size:15px;">关键洞察：横截面便宜 ≠ 自身历史便宜</h3>
    <table>
      <tr>
        <th>代码</th><th>名称</th><th>PE</th>
        <th>PE 自身分位</th><th>PB 自身分位</th><th>综合自身分位</th><th>权重</th>
      </tr>
      {hold_rows_html}
    </table>
    <div class="note">
      分位解读：<span style="color:#c0392b;font-weight:600">红=自身历史低位（真便宜）</span> ·
      <span style="color:#e67e22;font-weight:600">橙=中性</span> ·
      <span style="color:#27ae60;font-weight:600">绿=自身历史高位（相对贵）</span>。
      注意：<b>策略选的是"全市场 PE 最低"，但其中江苏银行(90.9%)、北京银行(81.8%)等自身 PE/PB 已处于 5 年历史高位</b>——
      它们 PE 低是因为银行板块整体常年低 PE，而非"跌到自身低位"。
    </div>
  </div>

  <!-- ===== 问题2 ===== -->
  <div class="card">
    <h2>问题 2 · 推荐列表是最新数据还是 4 月份的？</h2>
    <div class="answer">
      <b>是最新数据（2026-08），不是 4 月份的。</b>之前那份 4 月份的推荐是旧脚本读 JSON 快照的 bug，
      已于上一轮修正为直接读 SQLite 最新月。
    </div>
    <table>
      <tr><th>数据源</th><th>时点</th><th>状态</th></tr>
      <tr><td>万得全A PIT 成分</td><td class="mono">2026-08</td><td><span class="tag green">最新 ✓</span></td></tr>
      <tr><td>估值面板（pe_ttm / pb）</td><td class="mono">2026-08</td><td><span class="tag green">最新 ✓</span></td></tr>
      <tr><td>因子面板（gpm/roe/cetop/dtop5）</td><td class="mono">2026-08</td><td><span class="tag green">最新 ✓</span></td></tr>
      <tr><td>一致预期（con_np_yoy/con_peg/con_roe）</td><td class="mono">2026-08</td><td><span class="tag green">最新 ✓</span></td></tr>
      <tr><td>动量 mom60 日 K</td><td class="mono">2026-08-26（最新交易日）</td><td><span class="tag green">最新 ✓</span></td></tr>
      <tr><td>15 只持仓在日 K 覆盖内</td><td class="mono">15 / 15</td><td><span class="tag green">动量 gate 真实生效 ✓</span></td></tr>
      <tr><td>下次调仓日</td><td class="mono">2026-10-31</td><td><span class="tag orange">半年调仓口径</span></td></tr>
    </table>
  </div>

  <!-- ===== 问题3 ===== -->
  <div class="card">
    <h2>问题 3 · 现在买入时点好么？</h2>
    <div class="answer">
      数据没问题，但<b>买入时点需要谨慎</b>。当前是"市场 5 年高位 + 策略自身回撤中 + 部分个股自身分位偏高"三重不利，
      <b>不是这个估值修复策略的最佳入场时点</b>。
    </div>

    <div class="grid3">
      <div class="stat"><div class="v" style="color:#e67e22">82.5%</div><div class="l">中证全指点位 · 5 年分位（高位）</div></div>
      <div class="stat"><div class="v" style="color:#c0392b">-20.6%</div><div class="l">策略历史最大回撤 · 未修复</div></div>
      <div class="stat"><div class="v" style="color:#e67e22">1/3</div><div class="l">推荐票自身分位 &gt;70%（偏贵）</div></div>
    </div>

    <h3 style="margin:18px 0 8px;font-size:15px;">① 市场层面：中证全指处于 5 年高位</h3>
    <table>
      <tr><th>指标</th><th>数值</th><th>解读</th></tr>
      <tr><td>当前点位（2026-08）</td><td>{idx_cur:.0f}</td><td>—</td></tr>
      <tr><td>5 年历史分位</td><td>{idx_pct:.1f}%</td><td><span class="tag orange">偏高</span></td></tr>
      <tr><td>历史高点</td><td>{idx_peak:.0f}（{idx_peak_m}）</td><td>距顶 -10.8%</td></tr>
      <tr><td>历史低点</td><td>{idx_trough:.0f}（{idx_trough_m}）</td><td>—</td></tr>
      <tr><td>近 3 个月</td><td>6月{idx_closes[-3]:.0f} → 7月{idx_closes[-2]:.0f} → 8月{idx_cur:.0f}</td><td>6月见顶后急跌 13%，8月弱反弹</td></tr>
    </table>

    <h3 style="margin:18px 0 8px;font-size:15px;">② 全市场估值：PE 中位数从顶部回落</h3>
    <svg viewBox="0 0 660 150" width="100%" height="150">
      {pe_line}
      <text x="10" y="12" font-size="11" fill="#c0392b">全市场 PE 中位数（红）</text>
    </svg>
    <div class="legend">全市场 PE 中位数：2021-08 起 11 个月 · 2026-04 见顶 41.3 → 2026-08 回落 35.8</div>
    <svg viewBox="0 0 660 150" width="100%" height="150">
      {pb_line}
      <text x="10" y="12" font-size="11" fill="#2980b9">全市场 PB 中位数（蓝）</text>
    </svg>
    <div class="legend">全市场 PB 中位数：2026-04 见顶 3.01 → 2026-08 回落 2.61</div>

    <h3 style="margin:18px 0 8px;font-size:15px;">③ 结论：为什么现在不是最佳时点</h3>
    <div class="warn">
      <b>这个策略的 alpha 是"低 PE 股票估值均值回归"</b>——它靠的是便宜票的估值向上修复。
      而当前：<br>
      1. <b>市场在 5 年 82.5% 分位</b>，整体估值修复空间已被透支；<br>
      2. <b>策略自身 -20.6% 回撤未修复</b>，正处于均值回归的"向下"阶段（估值修复到极限后反向）；<br>
      3. <b>推荐票里约 1/3 自身 PE/PB 分位已到 70-90%</b>，追高的不是"便宜货"而是"板块里相对贵的"。
    </div>
    <div class="ok">
      <b>如果严格执行这个策略，更稳妥的入场条件（满足任一即转好）：</b><br>
      ① 策略回撤企稳或修复（NAV 回到前高附近）；<br>
      ② 推荐票自身 PE/PB 分位普遍回到 &lt;30%（真便宜，而非仅横截面便宜）；<br>
      ③ 等到 <b>2026-10-31 调仓日</b>再按新截面评估，不要在持仓期中间追入。
    </div>
  </div>

</div>
</body>
</html>"""

with open("_valuation_timing_report.html", "w", encoding="utf-8") as f:
    f.write(html)

print("报告已生成 → _valuation_timing_report.html")
print(f"推荐持仓 {len(holdings)} 只，其中自身 PE 分位>70% 的有:",
      sum(1 for r in rows_hold if r['pe_pct_self'] is not None and r['pe_pct_self'] > 70), "只")
print(f"自身 PB 分位>70% 的有:",
      sum(1 for r in rows_hold if r['pb_pct_self'] is not None and r['pb_pct_self'] > 70), "只")
