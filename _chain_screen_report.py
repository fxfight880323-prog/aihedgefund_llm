# -*- coding: utf-8 -*-
"""AI/半导体产业链 筹码合成个股筛选报告"""
import json, statistics as st, sys, csv
sys.stdout.reconfigure(encoding='utf-8')

d = json.load(open('_chain_screen_data.json', encoding='utf-8'))
rows = d['rows']
have = [r for r in rows if r['chip'] is not None and 'ST' not in r['name'].upper()]
for r in have:
    r['chip'] = float(r['chip'])

# 全市场对照（拥挤度诊断）
mkt = [float(r['chip']) for r in
       json.load(open('_chip_industry_data.json', encoding='utf-8'))['stocks']
       if r['chip'] is not None]
pool_chip = [r['chip'] for r in have]
pct = lambda v, arr: sum(1 for x in arr if x <= v) / len(arr)
print(f'池内 {len(have)} 只 | 池内chip中位 {st.median(pool_chip):.3f} vs 全市场 {st.median(mkt):.3f}')
print(f'全市场chip分位<30%(集中端) 占比: 池内 {sum(1 for c in pool_chip if pct(c, mkt)<0.30)/len(pool_chip)*100:.0f}% vs 全市场 30%')

# 排序: chip 升序 = 筹码最集中 = 个股层最优
ranked = sorted(have, key=lambda r: r['chip'])

def fmt(r, i):
    dist = f"{r['dist52']*100:+.0f}%" if r['dist52'] is not None else '-'
    pe = f"{r['pe']:.0f}" if r['pe'] and r['pe'] > 0 else '-'
    mv = f"{r['mv']/1e8:.0f}" if r['mv'] else '-' 
    tag = r['tags'][:40] + ('…' if len(r['tags']) > 40 else '')
    return (f"<tr><td>{i}</td><td class='c'>{r['ts']}</td><td>{r['name']}</td>"
            f"<td>{r['industry']}</td><td class='n'>{r['chip']:.3f}</td>"
            f"<td class='n'>{pct(r['chip'], mkt)*100:.0f}</td>"
            f"<td class='n'>{mv}</td><td class='n'>{pe}</td><td class='n'>{dist}</td>"
            f"<td class='t'>{tag}</td></tr>")

top20 = ''.join(fmt(r, i + 1) for i, r in enumerate(ranked[:20]))
bot10 = ''.join(fmt(r, i + 1) for i, r in enumerate(ranked[-10:]))
mid = len(ranked) // 2
mid10 = ''.join(fmt(r, mid - 5 + i + 1) for i, r in enumerate(ranked[mid - 5:mid + 5]))

csv_rows = []
for i, r in enumerate(ranked):
    csv_rows.append([i + 1, r['ts'], r['name'], r['industry'], r['grp'],
                     f"{r['chip']:.4f}", f"{pct(r['chip'], mkt)*100:.1f}",
                     (round(r['mv']/1e8,1) if r['mv'] else ''), r['pe'] or '',
                     f"{r['dist52']*100:.1f}" if r['dist52'] is not None else '',
                     r['tags']])
with open('AI半导体产业链_筹码筛选.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['排名', '代码', '名称', '东财行业', '链条', '筹码合成', '全市场分位%',
                '总市值亿', 'PE', '距52周高点%', '概念标签'])
    w.writerows(csv_rows)

pool_med, mkt_med = st.median(pool_chip), st.median(mkt)
conc_share = sum(1 for c in pool_chip if pct(c, mkt) < 0.30) / len(pool_chip) * 100
d30 = [r for r in ranked if pct(r['chip'], mkt) >= 0.30]

html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>AI·半导体产业链 筹码合成个股筛选</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:24px;color:#1a1a1a;background:#fff;max-width:1180px}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:28px;border-left:4px solid #c0392b;padding-left:8px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:10px}}
th,td{{border:1px solid #ddd;padding:5px 7px;text-align:left}}
th{{background:#f5f5f5}} .n{{text-align:right;font-variant-numeric:tabular-nums}} .c{{font-family:Consolas,monospace}}
.t{{font-size:11px;color:#666}} .warn{{background:#fff3e0;border:1px solid #f0c070;padding:10px 14px;border-radius:6px;font-size:13px;line-height:1.7}}
.ok{{background:#e8f5e9;border:1px solid #a5d6a7;padding:10px 14px;border-radius:6px;font-size:13px;line-height:1.7}}
.meta{{color:#888;font-size:12px}} .up{{color:#c0392b}} .down{{color:#0a7d3b}}
</style></head><body>
<h1>AI · 半导体产业链 — 筹码合成个股筛选</h1>
<p class="meta">因子截面 2026-07-31（申万筹码合成，负向：值越低=筹码越集中）｜行情快照 2026-08-24 收盘｜池子：东财概念板块 19 个（AI 12 + 半导体 7），合计 {len(rows)} 只，有因子值且非ST {len(have)} 只</p>

<div class="warn"><b>⚠️ 用法边界（上周刚验证过的教训）</b>：筹码合成只在<b>个股层</b>有效（行业内选股/负面清单），<b>行业/板块配置层已证伪</b>——行业层筹码集中=拥挤度崩塌风险（2026-06 光学光电子案例：最集中行业次月 −29%）。实测本池整体拥挤度仅轻度偏高（见下表①），真正反常的是链内大市值龙头（中际旭创、北方华创等）筹码最分散——筹码散在散户手里的高位股是本因子最强的回避信号。本报告回答"这条链里怎么挑"，不回答"这条链该不该配"（属 L1 前瞻判断）。</div>

<h2>① 池子拥挤度诊断</h2>
<table>
<tr><th>指标</th><th>池内（AI+半导体）</th><th>全市场</th><th>解读</th></tr>
<tr><td>筹码合成中位数</td><td class="n">{pool_med:.3f}</td><td class="n">{mkt_med:.3f}</td><td>池内显著更低=筹码显著更集中</td></tr>
<tr><td>处于全市场集中端(前30%)占比</td><td class="n">{conc_share:.0f}%</td><td class="n">30%</td><td>拥挤度约为全市场基准的 {conc_share/30:.1f} 倍</td></tr>
</table>

<h2>② 筹码最集中 TOP 20（因子选出的"链内最优"）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>东财行业</th><th>筹码合成</th><th>全市场分位</th><th>总市值(亿)</th><th>PE</th><th>距52周高点</th><th>概念标签</th></tr>
{top20}
</table>

<h2>③ 池子中位段（对照组，10只）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>东财行业</th><th>筹码合成</th><th>全市场分位</th><th>总市值(亿)</th><th>PE</th><th>距52周高点</th><th>概念标签</th></tr>
{mid10}
</table>

<h2>④ 筹码最分散 BOTTOM 10（链内负面清单）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>东财行业</th><th>筹码合成</th><th>全市场分位</th><th>总市值(亿)</th><th>PE</th><th>距52周高点</th><th>概念标签</th></tr>
{bot10}
</table>

<div class="ok"><b>怎么用</b>：①表 是链内筹码结构最好的票（机构锁仓逻辑）；④表 是链内筹码已散掉、反弹即有解套抛压的票，<b>无论故事多好听都别碰</b>。"距52周高点"列参考既有 L3 规则：过远（&lt;-50%）的慎买，贴近高点的不用怕（近距52周高点是全市场验证过的正向信号）。</div>
<p class="meta">数据源：申万金工 MCP（筹码合成）+ 东方财富（概念成分/行情/行业）。因子为月频截面，反映 7 月末状态；PE 为动态口径，市值单位亿元。</p>
</body></html>"""

open('AI半导体产业链_筹码筛选报告.html', 'w', encoding='utf-8').write(html)
print('report -> AI半导体产业链_筹码筛选报告.html, csv rows:', len(csv_rows))

# 终端摘要
print('\n=== TOP20 筹码最集中 ===')
for i, r in enumerate(ranked[:20]):
    print(f"{i+1:2d}. {r['ts']} {r['name']:<6} {r['industry']:<6} chip={r['chip']:.3f} 分位{pct(r['chip'], mkt)*100:.0f}% mv={r['mv']/1e8:.0f}亿")
print('\n=== BOTTOM10 筹码最分散(负面清单) ===')
for i, r in enumerate(ranked[-10:]):
    print(f"{i+1:2d}. {r['ts']} {r['name']:<6} {r['industry']:<6} chip={r['chip']:.3f} 分位{pct(r['chip'], mkt)*100:.0f}% mv={r['mv']/1e8:.0f}亿")
