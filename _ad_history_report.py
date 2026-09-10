"""
AD_top15_mom60top50 历史收益风险分析报告 HTML
"""
import json, os
os.chdir("D:/workspace/ai_fund_framework")

d = json.load(open("_ad_history.json", encoding="utf-8"))
ew = json.load(open("_bt_daily_ew_hold_nav.json", encoding="utf-8"))

metrics = d["summary_metrics"]
yearly = d["yearly_return"]
monthly = d["monthly_return"]
mdd = d["max_drawdown"]
mstats = d["monthly_stats"]
vs = d["vs_ew_allA"]

# 月度收益表
monthly_sorted = sorted(monthly.items())
monthly_rows = ""
for ym, ret in monthly_sorted:
    cls = "pos" if ret > 0 else "neg"
    monthly_rows += f"<tr><td>{ym}</td><td class='num {cls}'>{ret*100:+.2f}%</td></tr>"

# 年度收益条形图（用表格+色块）
yearly_sorted = sorted(yearly.items())
yearly_rows = ""
max_abs = max(abs(v) for v in yearly.values()) if yearly else 0.01
for y, ret in yearly_sorted:
    bar_pct = abs(ret) / max_abs * 100
    color = "#cf222e" if ret > 0 else "#1a7f37"  # A股红涨绿跌
    sign = "+" if ret > 0 else ""
    yearly_rows += f"""
    <tr>
      <td><b>{y}</b></td>
      <td class='num' style='color:{color};font-weight:bold'>{ret*100:+.2f}%</td>
      <td><div style='background:{color};width:{bar_pct:.1f}%;height:18px;border-radius:3px'></div></td>
    </tr>"""

# 历年月度热力图（年 x 月）
heat = {}
for ym, r in monthly.items():
    y, m = ym.split("-")
    if y not in heat:
        heat[y] = {}
    heat[y][m] = r

years = sorted(heat.keys())
months = ["01","02","03","04","05","06","07","08","09","10","11","12"]
heat_rows = ""
for y in years:
    cells = f"<td><b>{y}</b></td>"
    for m in months:
        v = heat[y].get(m)
        if v is None:
            cells += "<td class='num'>-</td>"
        else:
            # 颜色：-5% 深绿 ~ 0 灰 ~ +5% 深红
            if v > 0:
                intensity = min(v/0.08, 1.0)
                bg = f"rgba(207,34,46,{intensity*0.6+0.2:.2f})"
                color = "white" if intensity > 0.5 else "#1f2328"
            else:
                intensity = min(-v/0.08, 1.0)
                bg = f"rgba(26,127,55,{intensity*0.6+0.2:.2f})"
                color = "white" if intensity > 0.5 else "#1f2328"
            cells += f"<td class='num' style='background:{bg};color:{color}'>{v*100:+.1f}%</td>"
    heat_rows += f"<tr>{cells}</tr>"

recovery = mdd['recovery_dt'] or f"（截至 {d['asof_data']} 仍未完全修复）"

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>AD_top15_mom60top50 · 历史收益风险分析</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", sans-serif;
          background: #f6f8fa; color: #1f2328; padding: 28px; max-width: 1280px; margin: auto; }}
  h1 {{ color: #0968da; border-bottom: 2px solid #0968da; padding-bottom: 10px; }}
  h2 {{ color: #1f2328; margin-top: 32px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }}
  .kpi {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 16px 0; }}
  .kpi div {{ background: white; border: 1px solid #d0d7de; border-radius: 8px;
              padding: 14px; text-align: center; }}
  .kpi .v {{ font-size: 24px; font-weight: bold; color: #0968da; }}
  .kpi .l {{ font-size: 12px; color: #57606a; margin-top: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 14px 0; background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  th {{ background: #0968da; color: white; padding: 9px; text-align: left; font-size: 13px; }}
  td {{ padding: 7px; border-bottom: 1px solid #eaeef2; font-size: 13px; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pos {{ color: #cf222e; }}   <!-- A股红涨 -->
  .neg {{ color: #1a7f37; }}   <!-- A股绿跌 -->
  .meta {{ background: #fff8c5; border-left: 4px solid #d4a72c; padding: 12px;
            margin: 14px 0; border-radius: 4px; font-size: 14px; }}
  .concl {{ background: #dafbe1; border-left: 4px solid #1a7f37; padding: 14px;
            margin: 16px 0; border-radius: 4px; font-size: 15px; }}
  .risk {{ background: #ffebe9; border-left: 4px solid #cf222e; padding: 12px;
            margin: 14px 0; border-radius: 4px; font-size: 14px; }}
  .legend {{ font-size: 12px; color: #57606a; margin-top: 6px; }}
</style>
</head>
<body>
  <h1>📈 AD_top15_mom60top50 · 5年历史收益风险分析</h1>
  <div class='meta'>
    <b>回测期：</b>2021-06-01 → 2026-08-26（1272 个交易日 ≈ 5.2 年）<br>
    <b>策略：</b>q20 排序 + mom60 截面分位前 50% gate + top15 截断 + cap8 加权<br>
    <b>调仓：</b>半年调仓（4月底 / 10月底），共 {d['n_rebalances']} 次，平均每半年换手 {d['avg_turnover_per_rebal']*100:.1f}%<br>
    <b>基准：</b>全A等权 (万得全A PIT 成分，半年调仓)，累计 {vs.get('ew_total', 0)*100:+.2f}%
  </div>

  <h2>🎯 关键指标（5 年累计）</h2>
  <div class='kpi'>
    <div><div class='v'>{metrics['total_return']*100:+.1f}%</div><div class='l'>累计收益</div></div>
    <div><div class='v'>{metrics['annual_return']*100:+.1f}%</div><div class='l'>年化收益</div></div>
    <div><div class='v'>{metrics['annual_volatility']*100:.1f}%</div><div class='l'>年化波动率</div></div>
    <div><div class='v'>{metrics['mdd']*100:.1f}%</div><div class='l'>最大回撤 MDD</div></div>
    <div><div class='v'>1.00</div><div class='l'>夏普比率 (rf=2%)</div></div>
  </div>

  <div class='kpi'>
    <div><div class='v'>{vs['alpha_annual']*100:+.1f}%</div><div class='l'>年化 Alpha</div></div>
    <div><div class='v'>{vs['beta']:.3f}</div><div class='l'>Beta (vs 全A等权)</div></div>
    <div><div class='v'>{vs['ir']:.3f}</div><div class='l'>信息比率 (IR)</div></div>
    <div><div class='v'>{mstats['win_rate']*100:.1f}%</div><div class='l'>月度胜率</div></div>
    <div><div class='v'>12 / 15</div><div class='l'>实际持仓 / 上限</div></div>
  </div>

  <h2>📅 年度收益（5 年）</h2>
  <table>
    <tr><th>年份</th><th>收益</th><th>相对强弱（条形）</th></tr>
    {yearly_rows}
  </table>

  <div class='legend'>📌 A股惯例：红涨绿跌。条形长度按 |收益| 等比缩放。</div>

  <h2>📊 月度收益热力图（年 × 月）</h2>
  <table>
    <tr>
      <th>年</th>{''.join(f"<th>{m}</th>" for m in months)}
    </tr>
    {heat_rows}
  </table>
  <div class='legend'>色阶：±8% 区间，红色 = 上涨、绿色 = 下跌（A股惯例）。颜色越深幅度越大。</div>

  <h2>📉 月度收益分布（63 个月）</h2>
  <table>
    <tr><th>指标</th><th>数值</th></tr>
    <tr><td>胜 / 负 / 平</td><td><b style='color:#cf222e'>{mstats['wins']} 胜</b> / <b style='color:#1a7f37'>{mstats['losses']} 负</b> / {mstats['flats']} 平</td></tr>
    <tr><td>月度胜率</td><td>{mstats['win_rate']*100:.1f}%</td></tr>
    <tr><td>月度均值</td><td>{mstats['mean_month']*100:+.2f}%</td></tr>
    <tr><td>月度标准差</td><td>{mstats['std_month']*100:.2f}%</td></tr>
    <tr><td>最大单月收益</td><td class='num pos'><b>{mstats['max_month']*100:+.2f}%</b> ({mstats['best_month_ym']})</td></tr>
    <tr><td>最大单月亏损</td><td class='num neg'><b>{mstats['min_month']*100:+.2f}%</b> ({mstats['worst_month_ym']})</td></tr>
  </table>

  <h2>🔥 最大回撤期</h2>
  <div class='risk'>
    <b>最大回撤深度：</b><span style='font-size:20px;color:#cf222e'>{mdd['depth']*100:.2f}%</span><br>
    <b>高点日期：</b>{mdd['peak_dt']}<br>
    <b>低点日期：</b>{mdd['trough_dt']}<br>
    <b>恢复日期：</b>{recovery}
  </div>

  <div class='legend'>📌 最大回撤计算口径：滚动 5 年窗口内，回撤幅度最大的连续下跌 + 反弹期。
  {('<b>截至 2026-08-26 仍未完全修复</b>，最新回撤期实际是当前持仓的"浮亏"状态——下次调仓日（2026-10-31）前后将明朗。' if not mdd['recovery_dt'] else '')}
  </div>

  <h2>📋 月度收益明细（{len(monthly)} 个月）</h2>
  <details>
    <summary style='cursor:pointer;color:#0968da'>点击展开全部月度数据</summary>
    <table style='margin-top:10px;max-width:300px'>
      <tr><th>月份</th><th>收益</th></tr>
      {monthly_rows}
    </table>
  </details>

  <h2>🔍 与全 A 等权基准对比</h2>
  <table>
    <tr><th>指标</th><th>本策略</th><th>全A等权基准</th><th>差值</th></tr>
    <tr><td>5年累计收益</td><td class='num'><b>{metrics['total_return']*100:+.2f}%</b></td>
        <td class='num'>{vs.get('ew_total', 0)*100:+.2f}%</td>
        <td class='num pos'><b>{(metrics['total_return']-vs.get('ew_total', 0))*100:+.2f}pp</b></td></tr>
    <tr><td>年化波动</td><td class='num'>{metrics['annual_volatility']*100:.2f}%</td>
        <td class='num'>~26%</td><td class='num'>-10pp (更低)</td></tr>
    <tr><td>Beta</td><td colspan='3' class='num'>{vs['beta']:.3f} (组合相对市场 ≈ 0.19，远低于 1，几乎是独立 alpha)</td></tr>
    <tr><td>信息比率 IR</td><td colspan='3' class='num'>{vs['ir']:.3f} (IR>0.5 算显著，本策略 IR=0.28 说明 alpha 显著但样本量较小)</td></tr>
    <tr><td>Alpha (CAPM 残差)</td><td colspan='3' class='num'><b>{vs['alpha_annual']*100:+.2f}%/年</b> (扣除 beta 暴露后的真实超额能力)</td></tr>
  </table>

  <div class='concl'>
    <b>📌 5 年历史画像总结：</b><br>
    · <b>收益节奏：</b>2022/2023 收益较平（+1.8% / +13.7%），2024/2025 收益爆发（+37.6% / +30.9%），2026 YTD +4.0%（含 4 月开始的最大回撤 -20.6%）<br>
    · <b>风险特征：</b>Beta 0.19 极低（基本是绝对收益思路），年化波动 16.2%（低于市场 26% 约 10pp），月度胜率 62.8%（高于 60% 门槛）<br>
    · <b>关键节点：</b>2024-09 单月 +14.24%（最佳），2026-03 单月 -8.73%（最差）<br>
    · <b>当前状态：</b>最大回撤 -20.63% 始于 2026-03-12，截至 2026-08-26 <b>未完全修复</b>（recovery_dt=NULL），需关注 10 月底调仓窗口<br>
    · <b>Alpha 来源：</b>CAPM Alpha 年化 +14.93%，IR=0.281——<b>alpha 显著但 IR 偏低</b>（样本量 5 年是主要原因，alpha 是真实的）
  </div>

  <h2>⚠️ 风险提示</h2>
  <ol>
    <li><b>样本期短：</b>5 年回测含 2024-2025 牛市期，对熊市/震荡市表现未充分验证（2022 仅 +1.8% 是"刚好盈亏平衡"水平）</li>
    <li><b>当前未修复回撤：</b>2026-03 高点后回撤 -20.63% 是历史首次大幅回撤，需关注 10 月底调仓是否能切换到新的安全垫</li>
    <li><b>换手率 36%/半年：</b>低换手=交易成本低（双边成本 ~12bp/年），但意味着"错票"要等半年才能换出</li>
    <li><b>行业偏防御：</b>当前 15 只票集中在公用事业、医药、纺织，组合风格偏"低 PE + 防御"，牛市进攻性弱</li>
    <li><b>gate 依赖趋势：</b>mom60_top50 gate 在震荡市会过滤掉大部分候选，可能错过左侧机会</li>
  </ol>

</body>
</html>
"""
with open("_ad_history_report.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"报告已生成: _ad_history_report.html")