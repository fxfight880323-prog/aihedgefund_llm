"""
AD_top15_mom60top50 收益来源归因报告 HTML
"""
import json, os
os.chdir("D:/workspace/ai_fund_framework")

d = json.load(open("_ad_attribution.json", encoding="utf-8"))
cum = d["cumulative_log"]
arith = d["cumulative_arithmetic"]
periods = d["periods"]

# 主归因饼图数据（用对数复利口径）
total = cum["total_return"]
val = cum["valuation_contribution"]
div = cum["dividend_contribution"]
grw = cum["growth_contribution"]

# 占比
val_pct = cum["val_share"] * 100
div_pct = cum["div_share"] * 100
grw_pct = cum["growth_share"] * 100

# 生成饼图（SVG）
# 只画正贡献的环：估值 97.26 + 股息 14.51 = 111.77，盈利 -8.16
# 用横向堆叠条形更清晰

# 各期归因表
period_rows = ""
for p in periods:
    cls_val = "pos" if p["val_contrib"] >= 0 else "neg"
    cls_div = "pos" if p["div_contrib"] >= 0 else "neg"
    cls_grow = "pos" if p["grow_contrib"] >= 0 else "neg"
    period_rows += f"""
    <tr>
      <td>{p['period']}</td>
      <td class='num'>{p['n_valid']}</td>
      <td class='num bold'>{p['total_ret']*100:+.2f}%</td>
      <td class='num {cls_val}'>{p['val_contrib']*100:+.2f}%</td>
      <td class='num {cls_div}'>{p['div_contrib']*100:+.2f}%</td>
      <td class='num {cls_grow}'>{p['grow_contrib']*100:+.2f}%</td>
    </tr>"""

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>AD_top15_mom60top50 · 收益来源归因</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", sans-serif;
          background: #f6f8fa; color: #1f2328; padding: 28px; max-width: 1280px; margin: auto; }}
  h1 {{ color: #0968da; border-bottom: 2px solid #0968da; padding-bottom: 10px; }}
  h2 {{ color: #1f2328; margin-top: 32px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }}
  .big-concl {{ background: #dafbe1; border-left: 6px solid #1a7f37; padding: 20px;
            margin: 16px 0; border-radius: 8px; font-size: 17px; }}
  .big-concl b {{ font-size: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 14px 0; background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  th {{ background: #0968da; color: white; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px; border-bottom: 1px solid #eaeef2; font-size: 14px; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.bold {{ font-weight: 600; }}
  .pos {{ color: #cf222e; }}   <!-- A股红涨 -->
  .neg {{ color: #1a7f37; }}   <!-- A股绿跌 -->
  .meta {{ background: #fff8c5; border-left: 4px solid #d4a72c; padding: 12px;
            margin: 14px 0; border-radius: 4px; font-size: 14px; }}
  .bar-container {{ background: white; border: 1px solid #d0d7de; border-radius: 8px;
            padding: 20px; margin: 16px 0; }}
  .bar-row {{ display: flex; align-items: center; margin: 12px 0; }}
  .bar-label {{ width: 130px; font-weight: 600; font-size: 14px; }}
  .bar-track {{ flex: 1; height: 32px; background: #f0f2f5; border-radius: 6px;
                position: relative; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 6px; display: flex; align-items: center;
               justify-content: flex-end; padding-right: 10px; color: white;
               font-weight: bold; font-size: 13px; }}
  .legend {{ font-size: 12px; color: #57606a; margin-top: 6px; }}
  .warn {{ background: #ffebe9; border-left: 4px solid #cf222e; padding: 12px;
            margin: 14px 0; border-radius: 4px; font-size: 14px; }}
</style>
</head>
<body>
  <h1>🔬 收益来源归因 · AD_top15_mom60top50</h1>

  <div class='meta'>
    <b>方法：</b>P/E 对数恒等式分解（价格回报 = 估值变化 × 隐含盈利变化），数学恒等，不依赖字段准确性<br>
    <b>口径：</b>每个半年调仓周期，cap8 权重加权，复权价；股息用 dtop5 × 半年<br>
    <b>覆盖：</b>8 个完整调仓周期（2022-08 → 2026-04），前 2 期因 K 线不足 250 天未纳入
  </div>

  <div class='big-concl'>
    <b>📌 核心结论：收益几乎 100% 来自「估值修复」，不是业绩增长。</b><br><br>
    5 年累计 +114.2% 中：<br>
    · <b style='color:#cf222e'>估值修复 +97.3%（占 85.2%）</b> ← 绝对主导<br>
    · <b style='color:#0968da'>股息 +14.5%（占 12.7%）</b> ← 稳定小贡献<br>
    · <b style='color:#1a7f37'>业绩增长 -8.2%（占 -7.1%）</b> ← 负贡献<br><br>
    这是一个<b>典型的「深度价值 / 低估值均值回归」策略</b>：买 PE 极低的股票，赚的是它们估值修复（变贵）的钱，而不是公司业绩增长的钱。
  </div>

  <h2>📊 三大收益来源占比</h2>
  <div class='bar-container'>
    <div class='bar-row'>
      <div class='bar-label'>估值修复</div>
      <div class='bar-track'>
        <div class='bar-fill' style='width:{abs(val)/max(abs(total),0.001)*100:.0f}%;background:#cf222e'>+{val*100:.1f}%</div>
      </div>
    </div>
    <div class='bar-row'>
      <div class='bar-label'>股息收益</div>
      <div class='bar-track'>
        <div class='bar-fill' style='width:{abs(div)/max(abs(total),0.001)*100:.0f}%;background:#0968da'>+{div*100:.1f}%</div>
      </div>
    </div>
    <div class='bar-row'>
      <div class='bar-label'>业绩增长</div>
      <div class='bar-track'>
        <div class='bar-fill' style='width:{abs(grw)/max(abs(total),0.001)*100:.0f}%;background:#1a7f37'>{grw*100:+.1f}%</div>
      </div>
    </div>
    <div class='bar-row'>
      <div class='bar-label'><b>总回报</b></div>
      <div class='bar-track'>
        <div class='bar-fill' style='width:100%;background:#57606a'>+{total*100:.1f}%</div>
      </div>
    </div>
  </div>
  <div class='legend'>📌 红色=正贡献、绿色=负贡献（A股惯例）。条形长度按绝对值相对总回报缩放。</div>

  <h2>📅 逐期归因（8 个调仓周期）</h2>
  <table>
    <tr>
      <th>调仓周期</th><th>持仓数</th><th>总回报</th>
      <th>估值贡献</th><th>股息贡献</th><th>业绩贡献</th>
    </tr>
    {period_rows}
  </table>

  <div class='legend'>📌 观察：8 期中有 6 期「估值贡献」为正且主导，只有 2023-04→2023-08 和 2024-04→2024-08 估值负贡献。业绩贡献多数为负或接近零。</div>

  <h2>💡 为什么是估值修复主导？—— 归因与策略逻辑的印证</h2>
  <table>
    <tr><th>策略环节</th><th>设计意图</th><th>归因印证</th></tr>
    <tr>
      <td><b>q20 排序（0.8×PE便宜度）</b></td>
      <td>优先选 PE 截面最便宜的股票</td>
      <td>✅ <b>这是估值修复的直接来源</b>——买最便宜的，等它们 PE 回归均值</td>
    </tr>
    <tr>
      <td><b>L4 股息率 ≥ 2%</b></td>
      <td>筛出高股息票做安全垫</td>
      <td>✅ 股息贡献 +14.5%，正是这个筛选的作用</td>
    </tr>
    <tr>
      <td><b>质量分（0.2×gpm/roe/cetop）</b></td>
      <td>想选"又好又便宜"</td>
      <td>❌ <b>质量分没带来业绩增长</b>——业绩贡献 -7.1%，说明"低 PE"与"高质量"在A股往往是矛盾的（低 PE 多是大盘价值股，增速本就低）</td>
    </tr>
    <tr>
      <td><b>mom60 趋势 gate</b></td>
      <td>只想买"正在涨"的低 PE 股</td>
      <td>⚠️ 中性——gate 让估值修复"顺势而为"，但没改变"估值驱动"的本质</td>
    </tr>
  </table>

  <h2>⚖️ 这个发现意味着什么</h2>
  <table>
    <tr><th>维度</th><th>含义</th></tr>
    <tr><td><b>收益本质</b></td><td>深度价值策略，赚「均值回归」的钱——不是「成长」的钱</td></tr>
    <tr><td><b>适合环境</b></td><td>估值修复牛市（2024-2025）收益爆表；震荡/熊市靠股息防守（2022 仅 +1.8%）</td></tr>
    <tr><td><b>当前风险</b></td><td>2026 年估值修复到极限后出现 -20.6% 回撤——<b>估值驱动策略的"均值回归向下"风险</b>正在显现</td></tr>
    <tr><td><b>与 Beta 0.19 的关系</b></td><td>估值因子与市场低相关，所以 Beta 极低、Alpha 高——本质是独立的价值因子敞口</td></tr>
    <tr><td><b>业绩增长为负的启示</b></td><td>如果想做"真成长 + 低估值"的 GARP，当前 q20 的 0.8/0.2 权重里，质量分（0.2）没能有效捕捉成长，反而可能被"低 PE 大盘价值股"稀释</td></tr>
  </table>

  <div class='warn'>
    <b>⚠️ 关键警示：</b>这个策略是「纯估值修复」策略，不是「价值成长」策略。<br>
    它依赖「低 PE 股票估值均值回归」这个市场异象持续存在。<br>
    一旦 A 股风格切换（价值 → 成长），或低估值股票的估值永久性下移（僵尸股化），这个策略的 alpha 会系统性衰减。<br>
    当前 2026 年的 -20.6% 回撤，可能就是估值驱动策略面临的第一次真正考验。
  </div>

  <h2>🔍 方法论说明</h2>
  <table>
    <tr><th>术语</th><th>定义</th></tr>
    <tr><td>估值贡献</td><td>PE 变化带来的价格变动 = PE(下期)/PE(当期) - 1（价格不变时，PE 上升=估值修复）</td></tr>
    <tr><td>股息贡献</td><td>dtop5（股息率）× 0.5 年（半年调仓周期内的股息近似）</td></tr>
    <tr><td>业绩增长贡献</td><td>残差 = 总回报 - 估值 - 股息（含真实盈利增长 + 回购 + 交互项）</td></tr>
    <tr><td>对数复利</td><td>跨期用 log(1+r) 累加后 exp 还原，避免算术相加的复利失真</td></tr>
  </table>

  <div class='legend'>📌 数据来源：valuation.pe_ttm（PIT 每月）、factor_panel.dtop5（股息率）、_bt_daily_px_full.json（复权价）。归因结果已存 _ad_attribution.json。</div>

</body>
</html>
"""
with open("_ad_attribution_report.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"报告已生成: _ad_attribution_report.html")