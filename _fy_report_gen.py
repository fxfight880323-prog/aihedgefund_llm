"""Generate comprehensive stock selection report with 福耀玻璃 as reference."""
import json, html

results = json.load(open('_lx_now_results.json', encoding='utf-8'))
final = json.load(open('_lx_now_final.json', encoding='utf-8'))

stats = results['stats']
fy = [s for s in results['all'] if '600660' in s['code']][0]
final_stocks = final['final']
dropped = final.get('dropped', [])
as_of = final['as_of']


def esc(s):
    return html.escape(str(s)) if s else '\u2014'


def band_badge(flag):
    colors = {
        '安全边际': '#1e8449', '自身低位': '#2874a6',
        '中性': '#566573', '偏高': '#b9770e', '规避': '#c0392b',
        '池内但PE偏高': '#7d3c98'
    }
    c = colors.get(flag, '#566573')
    return (f'<span style="background:{c};color:#fff;padding:2px 7px;'
            f'border-radius:10px;font-size:11px">{esc(flag)}</span>')


def fmt(v, suffix=''):
    if v is None or v == '':
        return '\u2014'
    try:
        return f'{float(v):.1f}{suffix}'
    except (ValueError, TypeError):
        return str(v)


def metric_row(r, highlight=False):
    hl = ' style="background:#fff8e1"' if highlight else ''
    name = str(r.get('name', '\u2014')).strip()
    sr = r.get('score_rank', '\u2014')
    pe = r.get('pe')
    pe_s = f'{pe:.1f}' if isinstance(pe, (int, float)) else str(pe)
    dy = r.get('dy')
    dy_s = f'{dy:.2f}' if isinstance(dy, (int, float)) else '\u2014'
    eg = r.get('exp_g')
    eg_s = f'{eg:.1f}' if isinstance(eg, (int, float)) else '\u2014'
    peg = r.get('peg')
    peg_s = f'{peg:.2f}' if isinstance(peg, (int, float)) else '\u2014'
    roe = r.get('con_roe')
    roe_s = f'{roe:.1f}' if isinstance(roe, (int, float)) else '\u2014'
    gpm = r.get('gpm')
    gpm_s = f'{gpm:.1f}' if isinstance(gpm, (int, float)) else '\u2014'
    cet = r.get('cetop')
    cet_s = f'{cet:.1f}' if isinstance(cet, (int, float)) else '\u2014'
    st = r.get('score_total')
    st_s = f'{st:.1f}' if isinstance(st, (int, float)) else str(st)
    pp = r.get('pb_pct')
    pp_s = f'{pp:.1f}' if isinstance(pp, (int, float)) else str(pp)
    ep = r.get('pe_pct')
    ep_s = f'{ep:.1f}' if isinstance(ep, (int, float)) else '\u2014'
    mv = r.get('mv_yi')
    mv_s = f'{mv:,.0f}' if isinstance(mv, (int, float)) else '\u2014'
    pr = r.get('price')
    pr_s = f'{pr:.2f}' if isinstance(pr, (int, float)) else '\u2014'
    return f"""<tr{hl}>
      <td>{sr}</td>
      <td class="l"><b>{esc(name)}</b></td>
      <td class="mono">{esc(r.get('code',''))}</td>
      <td>{pr_s}</td>
      <td>{mv_s}</td>
      <td class="pe"><b>{pe_s}</b></td>
      <td>{dy_s}</td>
      <td>{eg_s}</td>
      <td>{peg_s}</td>
      <td>{roe_s}</td>
      <td>{gpm_s}</td>
      <td>{cet_s}</td>
      <td class="score">{st_s}</td>
      <td>{pp_s}</td>
      <td>{ep_s}</td>
      <td>{band_badge(r.get('band_flag',''))}</td>
    </tr>"""


# 福耀玻璃 reference row
fy_row = {
    'score_rank': '132/226',
    'code': fy['code'],
    'name': fy['name'],
    'price': fy['price'],
    'mv_yi': fy['mv_yi'],
    'pe': fy['pe'],
    'dy': fy['dy'],
    'exp_g': fy['exp_g'],
    'peg': fy['peg'],
    'con_roe': fy['con_roe'],
    'gpm': fy['gpm'],
    'cetop': fy['cetop'],
    'score_total': '未入Top40',
    'pb_pct': '\u2014(未评分)',
    'pe_pct': '\u2014',
    'band_flag': '池内但PE偏高',
}

rows_html = ''.join(metric_row(r) for r in final_stocks)
fy_html = metric_row(fy_row, highlight=True)
dropped_html = ''.join(metric_row(r) for r in dropped)

# Funnel
funnel_steps = [
    ('万得全A PIT成分', stats['univ'] + stats['fin_removed'], '\u2014'),
    ('剔除银行/非银金融(铁律)', stats['univ'], f'-{stats["fin_removed"]}'),
    ('市值\u2265100亿', stats['univ'] - stats.get('mv_missing',0) - stats.get('mv_low',0),
     f'-{stats.get("mv_low",0)}'),
    ('PE>0', stats['univ'] - stats.get('mv_missing',0) - stats.get('mv_low',0) - stats.get('pe_nonpos',0),
     f'-{stats.get("pe_nonpos",0)}'),
    ('L4 估值安全边际(PE\u226425或股息率\u22652%)',
     stats['core_pass'] + stats.get('l5',0) + stats.get('gpm_missing',0),
     f'-{stats.get("l4",0)}'),
    ('L5 低预期逆向(增速\u226425%且0<PEG\u22642)',
     stats['core_pass'] + stats.get('gpm_missing',0),
     f'-{stats.get("l5",0)}'),
    ('Core 通过(全部命中)', stats['core_pass'], f'-{stats.get("gpm_missing",0)}'),
    ('评分 Top40', 40, f'从{stats["core_pass"]}中选40'),
    ('Band规避(PB 5y分位>90%剔除)', len(final_stocks), f'-{len(dropped)}'),
]

funnel_html = ''
for i, (label, remaining, eliminated) in enumerate(funnel_steps):
    funnel_html += f"""<tr><td>{i+1}</td><td class="l">{label}</td>
    <td><b>{remaining:,}</b></td><td>{eliminated}</td></tr>"""

# Quality comparison: stocks in final with gpm >= 38 (similar to 福耀)
quality_picks = sorted(
    [s for s in final_stocks if (s.get('gpm') or 0) >= 30],
    key=lambda x: x.get('gpm', 0), reverse=True)
quality_html = ''.join(metric_row(r) for r in quality_picks[:15])

# High ROE picks (similar to 福耀 ROE=22.4)
roe_picks = sorted(
    [s for s in final_stocks if (s.get('con_roe') or 0) >= 15],
    key=lambda x: x.get('con_roe', 0), reverse=True)
roe_html = ''.join(metric_row(r) for r in roe_picks[:15])

html_out = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>选股报告 - 福耀玻璃参照（{as_of}）</title>
<style>
body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:0;padding:0;
     background:#f5f5f5;color:#222;line-height:1.6}}
.container{{max-width:1400px;margin:0 auto;padding:20px 28px}}
h1{{font-size:24px;margin:8px 0 4px}}
h2{{font-size:17px;margin-top:32px;border-left:4px solid #c62828;padding-left:10px}}
.sub{{color:#666;font-size:13px;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:12.5px;
       background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.08)}}
th,td{{border:1px solid #e8e8e8;padding:5px 7px;text-align:center;white-space:nowrap}}
th{{background:#eef2f6;font-weight:600;position:sticky;top:0;z-index:1}}
td.l{{text-align:left}} td.mono{{font-family:Consolas,monospace;font-size:12px}}
td.pe{{color:#c62828;font-weight:700}} td.score{{font-weight:700}}
tr:hover{{background:#f0f7ff}}
.kpi-row{{display:flex;gap:14px;margin:16px 0;flex-wrap:wrap}}
.kpi{{background:#fff;border-radius:8px;padding:10px 18px;
      box-shadow:0 1px 3px rgba(0,0,0,0.08);min-width:120px}}
.kpi b{{font-size:24px;display:block}} .kpi span{{font-size:12px;color:#666}}
.kpi.red b{{color:#c62828}} .kpi.green b{{color:#1e8449}}
.card{{background:#fff;border-radius:8px;padding:14px 20px;margin:12px 0;
      box-shadow:0 1px 3px rgba(0,0,0,0.08);font-size:14px;line-height:1.8}}
.card.warn{{background:#fef9e7;border:1px solid #f5cba7}}
.card.fy{{background:#f4ecf7;border:1px solid #d2b4de}}
.note{{color:#888;font-size:12px;margin-top:18px;border-top:1px dashed #ccc;
       padding-top:10px;line-height:1.8}}
.highlight-box{{background:#fff8e1;border:1px solid #ffe082;border-radius:8px;
               padding:12px 18px;margin:14px 0;font-size:14px}}
.tag{{display:inline-block;background:#e8eaf6;color:#3f51b5;
      border-radius:4px;padding:1px 8px;font-size:12px;margin:2px}}
</style></head><body>
<div class="container">

<h1>刘旭式框架 \u00b7 当前推荐 A 股</h1>
<p class="sub">数据截至 <b>{as_of}</b>（最新交易日）\u00b7 池子 = 万得全A(881001.WI) PIT 成分
\u00b7 管线 = fetch \u2192 screen \u2192 score \u2192 band \u2192 apply
\u00b7 已剔除银行/非银金融（铁律）</p>

<div class="card fy">
<b>福耀玻璃（600660.SH）在管线中的位置：</b><br>
\u2713 通过全部筛选条件（市值1474亿\u2265100亿\u2192 PE 17.4>0 \u2192 L4: PE\u226425 \u2192 L5: 增速5.8%\u226425%, PEG 1.3\u22642）<br>
\u2713 通过 gm 质量层（毛利率 38.1% \u2265 中位数 27.0%）<br>
\u2717 <b>未入评分 Top40</b>：PE 升序排第 132/226 位，PE 17.4 高于最终 39 只的全部区间（6.6~15.6）<br>
\u2192 <b>框架核心信念 = PE 升序（便宜优先）</b>，回测证实这是决定成败的关键：同一筛选器 PE 升序 +55.6% vs 质量优先 -12%。
福耀玻璃是好公司，但当前估值不在框架的"便宜"区间内。
</div>

<div class="kpi-row">
  <div class="kpi"><b>5,529</b><span>万得全A PIT成分</span></div>
  <div class="kpi"><b>5,406</b><span>剔除金融后池子</span></div>
  <div class="kpi green"><b>226</b><span>Core 通过</span></div>
  <div class="kpi green"><b>113</b><span>GM 质量层通过</span></div>
  <div class="kpi red"><b>39</b><span>最终推荐（Band 后）</span></div>
  <div class="kpi"><b>2.56%</b><span>等权权重</span></div>
</div>

<h2>\u2460 筛选漏斗</h2>
<table>
<tr><th>#</th><th class="l">步骤</th><th>剩余</th><th>淘汰</th></tr>
{funnel_html}
</table>

<h2>\u2462 最终推荐名单（39 只，按评分降序）</h2>
<p class="sub">评分 = 价值50%(PE30%+PEG20%) + 质量25%(ROE15%+毛利率10%) + 安全25%(股息率15%+OCF/市值10%)
\u00b7 Band 规避: PB 5年分位>90% 剔除</p>
<table>
<tr>
  <th>评分排名</th><th class="l">名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
  <th>PE</th><th>股息率%</th><th>预期增速%</th><th>PEG</th><th>预期ROE%</th>
  <th>毛利率%</th><th>OCF/MV%</th><th>总分</th><th>PB分位%</th><th>PE分位%</th><th>Band</th>
</tr>
{rows_html}
</table>

<h2>\u2463 福耀玻璃 vs 最终名单（黄色高亮 = 福耀玻璃参照行）</h2>
<table>
<tr>
  <th>评分排名</th><th class="l">名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
  <th>PE</th><th>股息率%</th><th>预期增速%</th><th>PEG</th><th>预期ROE%</th>
  <th>毛利率%</th><th>OCF/MV%</th><th>总分</th><th>PB分位%</th><th>PE分位%</th><th>Band</th>
</tr>
{fy_html}
{rows_html}
</table>

<h2>\u2464 Band 规避剔除（{len(dropped)} 只）</h2>
<table>
<tr>
  <th>原排名</th><th class="l">名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
  <th>PE</th><th>股息率%</th><th>预期增速%</th><th>PEG</th><th>预期ROE%</th>
  <th>毛利率%</th><th>OCF/MV%</th><th>总分</th><th>PB分位%</th><th>PE分位%</th><th>剔除原因</th>
</tr>
{dropped_html}
</table>

<h2>\u2465 与福耀玻璃类似的高质量标的（毛利率\u226530%，按毛利率降序）</h2>
<p class="sub">福耀玻璃 毛利率=38.1%\u00b7预期ROE=22.4%\u00b7PE=17.4。
以下标的质量可比但估值更低（PE 全部 < 16）</p>
<table>
<tr>
  <th>评分排名</th><th class="l">名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
  <th>PE</th><th>股息率%</th><th>预期增速%</th><th>PEG</th><th>预期ROE%</th>
  <th>毛利率%</th><th>OCF/MV%</th><th>总分</th><th>PB分位%</th><th>PE分位%</th><th>Band</th>
</tr>
{quality_html}
</table>

<h2>\u2466 高 ROE 标的（预期ROE\u226515%，按ROE降序）</h2>
<p class="sub">福耀玻璃 预期ROE=22.4%。以下标的ROE更高或相当，且估值更低</p>
<table>
<tr>
  <th>评分排名</th><th class="l">名称</th><th>代码</th><th>现价</th><th>市值(亿)</th>
  <th>PE</th><th>股息率%</th><th>预期增速%</th><th>PEG</th><th>预期ROE%</th>
  <th>毛利率%</th><th>OCF/MV%</th><th>总分</th><th>PB分位%</th><th>PE分位%</th><th>Band</th>
</tr>
{roe_html}
</table>

<div class="card warn">
<b>结论：</b>福耀玻璃是优质公司（毛利率38.1%、ROE 22.4%、PEG 1.3），<b>通过了框架全部筛选条件</b>，
但因 PE 17.4 排第 132/226 位（偏中后），未进入评分 Top40。框架回测证据显示
<b>"PE 升序（便宜优先）"是核心 alpha 来源</b>——同一筛选器 PE 升序超额 +14.4pp，质量优先反而跑输。
因此名单中选择了质量可比但更便宜的标的，如：
<span class="tag">新和成 PE11.3 毛利43.7% ROE21.3%</span>
<span class="tag">华润三九 PE12.0 毛利51.8% ROE14.9%</span>
<span class="tag">吉比特 PE12.2 毛利94.3% ROE28.5%</span>
<span class="tag">宇通客车 PE12.3 ROE35.4%</span>
<span class="tag">中原传媒 PE8.9 毛利42.6%</span>
</div>

<p class="note">
<b>方法诚实性：</b>\u2460 数据来自 juzi 估值面板/HF因子/一致预期 PIT 快照 + 腾讯实时行情，无合成数据；
\u2461 剔除金融是用户指定偏好约束（2026-08-25 定稿），回测口径含银行股，本名单属"策略+行业约束"衍生口径；
\u2462 con_roe/con_np_yoy/con_peg 为分析师一致预期，小盘无覆盖股在 L5 层即被剔除；
\u2463 毛利率中位数用全市场口径（非行业中位数），与回测一致；
\u2464 Band 规避以 PB 5年分位为准（PE 被盈利下滑污染）；
\u2465 本名单由数值化筛选器产生，<b>不构成投资建议</b>；
\u2466 框架回测区间 2021-08~2026-06 超额等权全A +14.4pp（core），过去表现不代表未来。
</p>

</div></body></html>"""

with open('_fy_report.html', 'w', encoding='utf-8') as f:
    f.write(html_out)
print(f'Report generated: _fy_report.html ({len(html_out)} chars)')
print(f'Final stocks: {len(final_stocks)}')
print(f'Dropped: {len(dropped)}')
print(f'Quality picks (gpm>=30): {len(quality_picks)}')
print(f'High ROE picks (ROE>=15): {len(roe_picks)}')
