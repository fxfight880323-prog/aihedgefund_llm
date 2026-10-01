#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V3对比报告HTML：主题指数 vs 申万一级行业"""
import pandas as pd
import numpy as np
import base64

BASE = '/Users/seanf/WorkBuddy/A股好难'
OUT = f'{BASE}/output'

def img64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

nav_v3 = pd.read_csv(f'{OUT}/nav_v3_R1and3_plus_杠杆_plus_大基金.csv', index_col=0, parse_dates=True)['nav']
nav_v2 = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆_plus_大基金.csv', index_col=0, parse_dates=True)['nav']
tr_v3 = pd.read_csv(f'{OUT}/trades_v3_R1and3_plus_杠杆_plus_大基金.csv', parse_dates=['date'])
v2 = pd.read_csv(f'{OUT}/v2_experiments.csv')
v3 = pd.read_csv(f'{OUT}/v3_experiments.csv')

def stats_row(nav, label):
    ret = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    total = nav.iloc[-1]/nav.iloc[0]-1
    annual = (nav.iloc[-1]/nav.iloc[0])**(1/years)-1
    sharpe = ret.mean()/ret.std()*np.sqrt(252) if ret.std() > 0 else 0
    mdd = (nav/nav.cummax()-1).min()
    return f"<tr><td>{label}</td><td><b>{total:.1%}</b></td><td>{annual:.1%}</td><td>{sharpe:.2f}</td><td>{mdd:.1%}</td></tr>"

def trades_table(tr):
    rows = []
    for _, t in tr.iterrows():
        cls = 'buy' if t['action'] == '买入' else 'sell'
        rr = f"{t['ret']:.1%}" if pd.notna(t['ret']) else '—'
        rrcls = ('pos' if t['ret'] > 0 else 'neg') if pd.notna(t['ret']) else ''
        hd = f"{int(t['hold_days'])}天" if pd.notna(t['hold_days']) else '—'
        rows.append(f"<tr><td>{t['date'].date()}</td><td class='{cls}'>{t['action']}</td><td>{t['name']}</td><td>{t['price']:.2f}</td><td class='{rrcls}'>{rr}</td><td>{hd}</td><td class='reason'>{t['reason'] if pd.notna(t['reason']) else '—'}</td></tr>")
    return '\n'.join(rows)

cfgs = ['and3 三条件AND(基准)','vote2 三选二投票','R1and3 + 杠杆消费','R1and3 + 杠杆 + 大基金','R1vote2 + 杠杆 + 大基金']
cmp_rows = ''
for c in cfgs:
    r2 = v2[v2['配置']==c]; r3 = v3[v3['配置']==c]
    if len(r2) and len(r3):
        t2, t3 = float(r2['总收益'].iloc[0]), float(r3['总收益'].iloc[0])
        s2, s3 = float(r2['夏普'].iloc[0]), float(r3['夏普'].iloc[0])
        m2, m3 = float(r2['最大回撤'].iloc[0]), float(r3['最大回撤'].iloc[0])
        cmp_rows += f"<tr><td style='text-align:left'>{c}</td><td>{t2:.1%}</td><td><b>{t3:.1%}</b></td><td class='pos'>+{(t3-t2)*100:.0f}pct</td><td>{s2:.2f}</td><td><b>{s3:.2f}</b></td><td>{m2:.1%}</td><td>{m3:.1%}</td></tr>"

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>V3报告：主题指数 vs 申万一级行业 标的更换实验 2016-2026</title>
<style>
  body {{ font-family: 'PingFang SC','Helvetica Neue',sans-serif; max-width: 1180px; margin: 0 auto; padding: 32px 24px; color: #2c3e50; line-height: 1.65; background: #fafbfc; }}
  h1 {{ border-bottom: 3px solid #8e44ad; padding-bottom: 12px; font-size: 26px; }}
  h2 {{ margin-top: 42px; border-left: 5px solid #8e44ad; padding-left: 12px; font-size: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 14px 0; background: #fff; font-size: 13.5px; }}
  th, td {{ border: 1px solid #dfe4e8; padding: 7px 10px; text-align: center; }}
  th {{ background: #2c3e50; color: #fff; font-weight: 600; }}
  tr:nth-child(even) {{ background: #f6f8fa; }}
  td.buy {{ color: #c0392b; font-weight: 700; }}
  td.sell {{ color: #1a9850; font-weight: 700; }}
  td.pos {{ color: #c0392b; font-weight: 600; }}
  td.neg {{ color: #1a9850; font-weight: 600; }}
  td.reason {{ text-align: left; font-size: 12.5px; color: #556; }}
  img {{ width: 100%; border: 1px solid #e2e6ea; border-radius: 6px; margin: 12px 0; }}
  .box {{ background: #fff; border-left: 4px solid #8e44ad; padding: 14px 18px; margin: 16px 0; border-radius: 0 6px 6px 0; }}
  .box.red {{ border-color: #c0392b; }}
  .box.blue {{ border-color: #2980b9; }}
  .box.green {{ border-color: #27ae60; }}
  .box.warn {{ border-color: #f39c12; background: #fffdf5; }}
  .kpis {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 18px 0; }}
  .kpi {{ flex: 1; min-width: 150px; background: #fff; border: 1px solid #e2e6ea; border-radius: 8px; padding: 14px; text-align: center; }}
  .kpi .v {{ font-size: 24px; font-weight: 700; color: #8e44ad; }}
  .kpi .v.red {{ color: #c0392b; }}
  .kpi .l {{ font-size: 12.5px; color: #7f8c8d; margin-top: 4px; }}
  .small {{ font-size: 12.5px; color: #7f8c8d; }}
</style>
</head>
<body>

<h1>V3报告：择时信号不变，标的换成行业主题指数</h1>
<p class="small">回测区间 2016-01 ~ 2026-03 · 主题池11只（中证/国证官方指数）· 信号/事件/财务成熟度与V2完全一致 · T+1收盘执行 · 无未来数据</p>

<div class="kpis">
  <div class="kpi"><div class="v red">+201.5%</div><div class="l">V3主题·完整版总收益</div></div>
  <div class="kpi"><div class="v">+85pct</div><div class="l">较V2申万一级版提升</div></div>
  <div class="kpi"><div class="v">0.64</div><div class="l">夏普（V2=0.58）</div></div>
  <div class="kpi"><div class="v red">-39.7%</div><div class="l">最大回撤（V2=-33.2%）</div></div>
</div>

<h2>一、实验设计</h2>
<div class="box">
<b>控制变量法</b>：双Regime信号框架（政策/流动性/国家队事件表、杠杆率状态、财务成熟度规则、T+1执行）与V2<b>完全相同</b>，唯一变量=可投标的。<br>
<b>标的池</b>（11只中证官方主题指数，映射回SW行业财务）：<br>
· R1产业扶持：全指半导体 / 半导体材料 / CS人工智能 / 5G通信 / 光伏产业 / CS新能车 / 中证军工<br>
· R2消费吃药：中证白酒 / 中证消费 / 中证医药 / CS医疗
</div>

<img src="data:image/png;base64,{img64(f'{OUT}/chart_v3_compare.png')}">

<h2>二、核心结果：同信号下主题指数全面放大</h2>
<table>
<tr><th>配置</th><th>V2申万一级 收益</th><th>V3主题指数 收益</th><th>提升</th><th>V2夏普</th><th>V3夏普</th><th>V2回撤</th><th>V3回撤</th></tr>
{cmp_rows}
</table>

<div class="box green">
<b>结论</b>：信号相同的情况下，主题指数在所有配置下都跑赢申万一级行业——收益提升 +21~+85pct，夏普同步上升（0.36→0.47 / 0.58→0.64）。代价是回撤放大（-33.2%→-39.7%）。主题指数=同一产业逻辑的高beta表达。
</div>

<img src="data:image/png;base64,{img64(f'{OUT}/chart_v3_vs_v2.png')}">

<h2>三、集中度放大效应的两个代表</h2>
<div class="box red">
<b>上行放大</b>：中证白酒 2016-04→2022-04（杠杆Regime）<b>+402%</b> vs 申万食品饮料 +243%（同一买卖日！）。中证消费 +186% vs 申万家电 +53%。半导体材料 2025-05→2026-03 <b>+118%</b> vs 申万电子同期+40%。<br>
<b>下行也放大</b>：光伏产业/CS新能车在2024年抄底段 -15.7%/-16.2%，同期申万电力设备仅-1.7%。2024-09盈利成熟退出时点相同，但主题回撤更深。
</div>

<img src="data:image/png;base64,{img64(f'{OUT}/chart_v3_baijiu.png')}">

<h2>四、V3完整版交易明细</h2>
<table>
<tr><th>日期</th><th>动作</th><th>主题指数</th><th>点位</th><th>收益</th><th>持有</th><th>理由</th></tr>
{trades_table(tr_v3)}
</table>

<h2>五、方法论说明</h2>
<div class="box blue">
<b>数据</b>：中证指数官方接口（csindex），11只全部覆盖2015-01起；交易日对齐申万日历（缺失日前值填充=保守）。<br>
<b>财务成熟度桥接</b>：主题指数无行业财务→用对应申万一级行业财务（全指半导体/半导体材料→电子；光伏/新能车→电力设备；白酒→食品饮料等），信号时点规则不变。<br>
<b>公平性</b>：max_positions=5、等权分仓、fee=0，与V2一致。<br>
<b>局限</b>：①主题指数可交易性需用ETF落地（跟踪误差+流动性成本未计）；②2016年前多数主题ETF未上市，实操上2016-2018段只能近似（当时可用分级基金/场外指数基金）；③高beta属性使结果对退出信号延迟更敏感（杠杆年频信号延迟14个月的代价被放大）。
</div>

<p class="small">生成时间：2026-10-01 · 数据源：中证指数官网(csindex) / CNBS / 申万行业指数(akshare) · 工具：backtest_v3.py（复用V2信号框架）</p>
</body>
</html>"""

with open(f'{OUT}/report_v3.html', 'w') as f:
    f.write(html)
print(f'V3报告已生成: {OUT}/report_v3.html ({len(html)//1024}KB)')
