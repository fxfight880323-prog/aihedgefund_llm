"""Generate winda consensus HTML report."""
import json

charts = json.loads(open('_winda_chart_b64.json', encoding='utf-8').read())
res = json.loads(open('_bt_winda_results.json', encoding='utf-8').read())
cons = json.loads(open('_bt_winda_consensus.json', encoding='utf-8').read())

nav_b64 = charts['nav']
period_b64 = charts['period']
stock_b64 = charts['stock']

# Build per-period holdings table
contrib = res.get('contrib', [])
wz = res.get('weights_zhf', {})
diag = res.get('diag', {})

period_rows = ""
for row in contrib:
    month = row['month']
    d = diag.get(month, {})
    cls_str = " ".join(f"{k}:{v}" for k, v in sorted(d.get('zhf_cls', {}).items()))
    top_stocks = " ".join(
        f'<span class="{"pos" if it["contrib"] > 0 else "neg"}">{it["tk"]} {it["ret"]:+.0%}({it["contrib"]:+.1%})</span>'
        for it in row['top'][:5]
    )
    period_rows += f"""
    <tr>
      <td class="month">{month}</td>
      <td>{d.get('univ','?')}</td>
      <td>{d.get('cov','?')}</td>
      <td>{cls_str}</td>
      <td>{d.get('zhf_hold','?')}</td>
      <td class="{"pos" if row["total_ret"] > 0 else "neg"}">{row["total_ret"]:+.1%}</td>
      <td class="detail">{top_stocks}</td>
    </tr>"""

holdings_html = ""
for month in sorted(wz.keys()):
    w = wz[month]
    sorted_w = sorted(w.items(), key=lambda x: -x[1])
    stocks = " ".join(
        f'<span class="hold">{tk} {v:.1%}</span>'
        for tk, v in sorted_w[:10]
    )
    holdings_html += f"""
    <div class="hold-row">
      <span class="hold-month">{month}</span> ({len(w)} stocks): {stocks}...
    </div>"""

sample_recs = cons['2021-08']['records'][:5]
cons_sample = ""
for r in sample_recs:
    cons_sample += f"""
    <tr>
      <td>{r.get('stock_code','')}</td>
      <td>{r.get('con_np_yoy','')}</td>
      <td>{r.get('con_roe','')}</td>
      <td>{r.get('con_pe','')}</td>
      <td>{r.get('np_revision_4w','')}</td>
      <td>{r.get('np_revision_13w','')}</td>
    </tr>"""

snap_date = cons['2021-08'].get('snapshot_date', '')

html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>WindA Full-Market Backtest Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
h1 {{ font-size: 24px; color: #1a1a1a; margin-bottom: 8px; }}
h2 {{ font-size: 18px; color: #c3163e; margin: 24px 0 12px; border-bottom: 2px solid #c3163e; padding-bottom: 4px; }}
h3 {{ font-size: 15px; color: #555; margin: 16px 0 8px; }}
.subtitle {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
.card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0; }}
.metric {{ text-align: center; padding: 12px; border-radius: 6px; }}
.metric .val {{ font-size: 22px; font-weight: 700; }}
.metric .lbl {{ font-size: 11px; color: #888; margin-top: 4px; }}
.pos {{ color: #c3163e; }} .neg {{ color: #2ca02c; }}
.metric.pos-bg {{ background: #fdf0f0; }} .metric.neg-bg {{ background: #f0fdf0; }}
.metric.neutral-bg {{ background: #f8f8f8; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin: 8px 0; }}
th {{ background: #c3163e; color: white; padding: 8px 6px; text-align: left; font-weight: 600; }}
td {{ padding: 6px; border-bottom: 1px solid #eee; }}
tr:hover {{ background: #fafafa; }}
.month {{ font-weight: 600; white-space: nowrap; }}
.detail {{ font-size: 11px; line-height: 1.8; }}
.hold {{ display: inline-block; background: #f0f0f0; padding: 2px 6px; border-radius: 3px; margin: 2px; font-size: 11px; }}
.hold-row {{ margin: 4px 0; font-size: 12px; }}
.hold-month {{ font-weight: 600; color: #c3163e; margin-right: 6px; }}
.chart {{ text-align: center; margin: 12px 0; }}
.chart img {{ max-width: 100%; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.field-map {{ display: grid; grid-template-columns: 120px 200px 1fr; gap: 8px; font-size: 13px; }}
.field-map .hdr {{ font-weight: 600; color: #c3163e; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
.field-map .src {{ font-family: monospace; background: #f8f8f8; padding: 4px 8px; border-radius: 4px; }}
.note {{ background: #fff3cd; padding: 12px; border-radius: 6px; font-size: 13px; margin: 12px 0; }}
.insight {{ background: #e7f4ff; padding: 12px; border-left: 4px solid #1f77b4; border-radius: 4px; margin: 8px 0; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">

<h1>WindA Full-Market Backtest | ZHF Framework x Consensus</h1>
<div class="subtitle">
  Period: 2021-08 ~ 2026-08 (10 semi-annual rebalances) | Universe: WindA(881001.WI) PIT members (4441-5500) |
  Selection data: <b>Analyst Consensus PIT Snapshots</b> (NOT actual financials) | Cost: 5bp commission + 10bp slippage
</div>

<div class="card">
  <h2>[1] Selection Data Source Verification</h2>
  <div class="insight">
    <b>All selection criteria use PIT (Point-in-Time) analyst consensus snapshots. Zero actual financial fields used.</b><br>
    Each rebalance date uses juzi-mcp <code>factor_get_consensus_forecast(universe='881001.WI', as_of_date=...)</code>
    to fetch the consensus snapshot as of that date, ensuring no look-ahead bias.
  </div>

  <h3>Field Mapping (zhf_cons_signal function)</h3>
  <div class="field-map">
    <div class="hdr">Dimension</div><div class="hdr">Consensus Field</div><div class="hdr">Description</div>
    <div>growth</div><div class="src">con_np_yoy / 100</div><div>Analyst expected net profit YoY growth</div>
    <div>roe</div><div class="src">con_roe</div><div>Analyst expected ROE</div>
    <div>pe</div><div class="src">con_pe</div><div>Analyst expected PE</div>
    <div>accel</div><div class="src">np_revision_4w &gt; 0</div><div>Analyst upgraded within 4 weeks</div>
    <div>gm (margin)</div><div class="src">0.5 (neutral)</div><div>No consensus margin data -> neutralized</div>
    <div>G5/L5</div><div class="src">1.0 (neutral)</div><div>No historical EPS/PE series -> neutralized</div>
  </div>

  <h3>2021-08 Consensus Sample (snapshot_date = {snap_date})</h3>
  <table>
    <tr><th>Stock Code</th><th>con_np_yoy(%)</th><th>con_roe(%)</th><th>con_pe</th><th>rev_4w</th><th>rev_13w</th></tr>
    {cons_sample}
  </table>
  <div class="note">
    Note: Full market 4441-5500 stocks per period. con_np_yoy / con_roe / con_pe / np_revision_4w coverage = 100%.
  </div>
</div>

<div class="card">
  <h2>[2] Backtest Results Overview</h2>
  <div class="metric-grid">
    <div class="metric neg-bg"><div class="val neg">-7.3%</div><div class="lbl">ZHF-cons Total</div></div>
    <div class="metric neg-bg"><div class="val neg">-1.4%</div><div class="lbl">ZHF-cons Annual</div></div>
    <div class="metric neg-bg"><div class="val neg">-36.6%</div><div class="lbl">ZHF-cons MaxDD</div></div>
    <div class="metric neg-bg"><div class="val neg">-60.2pp</div><div class="lbl">ZHF vs EW-WindA</div></div>
  </div>
  <div class="metric-grid">
    <div class="metric neutral-bg"><div class="val">+0.1%</div><div class="lbl">C-cons Total</div></div>
    <div class="metric neutral-bg"><div class="val">+0.0%</div><div class="lbl">C-cons Annual</div></div>
    <div class="metric neg-bg"><div class="val neg">-33.1%</div><div class="lbl">C-cons MaxDD</div></div>
    <div class="metric neg-bg"><div class="val neg">-52.8pp</div><div class="lbl">C-cons vs EW-WindA</div></div>
  </div>
  <div class="metric-grid">
    <div class="metric pos-bg"><div class="val pos">+52.9%</div><div class="lbl">EW-WindA Total</div></div>
    <div class="metric pos-bg"><div class="val pos">+8.4%</div><div class="lbl">EW-WindA Annual</div></div>
    <div class="metric neutral-bg"><div class="val">+0.2%</div><div class="lbl">CSI-All Total</div></div>
    <div class="metric neutral-bg"><div class="val">+0.0%</div><div class="lbl">CSI-All Annual</div></div>
  </div>

  <div class="chart">
    <img src="data:image/png;base64,{nav_b64}" alt="NAV Chart">
  </div>

  <div class="insight">
    <b>Key Finding:</b> Both strategies massively underperform the equal-weight WindA benchmark (+52.9%).
    ZHF-cons -7.3%, C-cons +0.1%.<br>
    However, the EW benchmark's outperformance comes from small-cap beta (CSI-All cap-weighted only +0.2%).
    Stock selection cannot capture small-cap beta.
  </div>
</div>

<div class="card">
  <h2>[3] Per-Period Selection &amp; Returns</h2>
  <table>
    <tr>
      <th>Rebalance</th><th>Universe</th><th>Coverage</th><th>ZHF Classes (A/B/C/OFF)</th>
      <th>Holdings</th><th>Period Return</th><th>Top 5 Contributors</th>
    </tr>
    {period_rows}
  </table>

  <div class="chart">
    <img src="data:image/png;base64,{period_b64}" alt="Period Returns">
  </div>
</div>

<div class="card">
  <h2>[4] Stock Contribution Analysis</h2>
  <div class="chart">
    <img src="data:image/png;base64,{stock_b64}" alt="Stock Contributions">
  </div>

  <div class="insight">
    <b>Key Observations:</b><br>
    - <b>Positive contributions concentrated in few mooners</b>: 300502.SZ contributed +10.8% in 2025-04->08 (+465.5% return)<br>
    - <b>Negative contributions from systemic declines</b>: 2021-08->2022-04, 8 stocks fell 40-55%, diversification didn't help<br>
    - <b>2024-04->08 all negative</b>: Top 8 contributions all negative, no survivor<br>
    - <b>Highly diversified</b>: 2.3-2.7% per stock, 40 holdings, limited single-name impact but no systemic risk shield
  </div>
</div>

<div class="card">
  <h2>[5] Holdings Detail (ZHF-cons Top 10 by weight)</h2>
  {holdings_html}
</div>

<div class="card">
  <h2>[6] Conclusions &amp; Improvement Directions</h2>
  <div class="insight">
    <b>Honest Conclusions:</b><br>
    1. <b>ZHF framework has no alpha in full market</b>: -7.3% vs EW +52.9%, excess -60.2pp. Framework discipline (MDD control) is the only value<br>
    2. <b>Consensus selection is ineffective in full market</b>: C-cons (pure consensus) only +0.1%, analyst expectations have no selection alpha at market-wide level<br>
    3. <b>Pool bias is fatal</b>: Leader-pool ZHF-cons +329% vs full-market -7.3%, the 336pp gap is entirely pool beta<br>
    4. <b>EW-WindA outperformance is small-cap beta</b>: CSI-All (cap-weighted) only +0.2%, confirming +52.9% is small-cap beta, not selection alpha
  </div>
  <div class="note">
    <b>Improvement Directions:</b><br>
    - Add small-cap factor exposure (EW benchmark implicitly selects small caps, strategy needs explicit capture)<br>
    - Valuation-based selling / consensus deterioration selling (effective in leader pool, needs full-market validation)<br>
    - Style timing (reduce position or switch to defensive factor in bear markets)<br>
    - Exclude suspected cyclical spikes (filter YoY &gt; 300%)
  </div>
</div>

</div>
</body>
</html>"""

outpath = "winda_consensus_report.html"
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"Report saved to {outpath}")
