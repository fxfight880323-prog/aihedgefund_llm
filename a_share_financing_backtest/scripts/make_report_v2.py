#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V2报告：双Regime(消费吃药+杠杆率) + 条件优先级消融"""
import pandas as pd
import numpy as np
import base64

BASE = '/Users/seanf/WorkBuddy/A股好难'
OUT = f'{BASE}/output'

def img64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

# 数据
nav_dual = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆消费.csv', index_col=0, parse_dates=True)['nav']
nav_full = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆_plus_大基金.csv', index_col=0, parse_dates=True)['nav']
nav_v1s = pd.read_csv(f'{OUT}/nav_main.csv', index_col=0, parse_dates=True)['nav']
nav_v1e = pd.read_csv(f'{OUT}/nav_ext.csv', index_col=0, parse_dates=True)['nav']
tr_full = pd.read_csv(f'{OUT}/trades_v2_R1and3_plus_杠杆_plus_大基金.csv', parse_dates=['date'])
exp = pd.read_csv(f'{OUT}/v2_experiments.csv')
lev = pd.read_csv(f'{BASE}/data/household_leverage.csv')

hs = pd.read_csv(f'{BASE}/data/hs300.csv'); hs['date'] = pd.to_datetime(hs['date'])
hs = hs.set_index('date')['close'].reindex(nav_full.index).ffill()
hs_n = hs/hs.iloc[0]

def stats_row(nav, label, bench=False):
    ret = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    total = nav.iloc[-1]/nav.iloc[0]-1
    annual = (nav.iloc[-1]/nav.iloc[0])**(1/years)-1
    sharpe = ret.mean()/ret.std()*np.sqrt(252) if ret.std() > 0 else 0
    mdd = (nav/nav.cummax()-1).min()
    flat = (ret.abs() < 1e-9).mean()
    return f"<tr><td>{label}</td><td><b>{total:.1%}</b></td><td>{annual:.1%}</td><td>{sharpe:.2f}</td><td>{mdd:.1%}</td><td>{flat:.0%}</td></tr>"

def trades_table(tr):
    rows = []
    for _, t in tr.iterrows():
        cls = 'buy' if t['action'] == '买入' else 'sell'
        rr = f"{t['ret']:.1%}" if pd.notna(t['ret']) else '—'
        rrcls = ''
        if pd.notna(t['ret']):
            rrcls = 'pos' if t['ret'] > 0 else 'neg'
        hd = f"{int(t['hold_days'])}天" if pd.notna(t['hold_days']) else '—'
        rows.append(f"<tr><td>{t['date'].date()}</td><td class='{cls}'>{t['action']}</td><td>{t['name']}</td><td>{t['price']:.2f}</td><td class='{rrcls}'>{rr}</td><td>{hd}</td><td class='reason'>{t['reason'] if pd.notna(t['reason']) else '—'}</td></tr>")
    return '\n'.join(rows)

exp_rows = '\n'.join(
    f"<tr><td style='text-align:left'>{r['配置']}</td><td><b>{r['总收益']:.1%}</b></td><td>{r['年化']:.1%}</td><td>{r['夏普']:.2f}</td><td>{r['最大回撤']:.1%}</td><td>{int(r['交易笔数'])}</td></tr>"
    for _, r in exp.iterrows())

lev_rows = '\n'.join(
    f"<tr><td>{int(r['year'])}</td><td>{r['household_leverage']:.1f}</td><td class='{'pos' if r['delta']>=2 else 'neg'}'>{r['delta']:+.1f}</td><td>{'ON 加杠杆' if r['delta']>=2 else 'OFF 平台期'}</td></tr>"
    for _, r in lev.iterrows())

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>V2报告：消费吃药×房地产杠杆率 + 买入条件优先级 2016-2026</title>
<style>
  body {{ font-family: 'PingFang SC','Helvetica Neue',sans-serif; max-width: 1180px; margin: 0 auto; padding: 32px 24px; color: #2c3e50; line-height: 1.65; background: #fafbfc; }}
  h1 {{ border-bottom: 3px solid #8e44ad; padding-bottom: 12px; font-size: 26px; }}
  h2 {{ margin-top: 42px; border-left: 5px solid #8e44ad; padding-left: 12px; font-size: 20px; }}
  h3 {{ color: #34495e; margin-top: 26px; }}
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
  .tag {{ display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }}
  .tag.on {{ background: #fdebd0; color: #b9770e; }}
  .tag.off {{ background: #eafaf1; color: #1a9850; }}
</style>
</head>
<body>

<h1>V2报告：消费吃药 × 房地产杠杆率 + 买入条件优先级消融</h1>
<p class="small">回测区间 2016-01 ~ 2026-03 · 申万一级行业指数 · 状态型信号 + T+1收盘执行 · 无未来数据（杠杆率披露日=次年3-31对齐）· 仓位等权、现金0收益</p>

<div class="kpis">
  <div class="kpi"><div class="v red">+116.7%</div><div class="l">双Regime完整版总收益</div></div>
  <div class="kpi"><div class="v">0.58</div><div class="l">夏普比率（V1=0.28）</div></div>
  <div class="kpi"><div class="v red">+90pct</div><div class="l">较V1严格口径提升</div></div>
  <div class="kpi"><div class="v">40笔</div><div class="l">交易笔数（V1=26）</div></div>
</div>

<h2>一、研究问题</h2>
<div class="box">
<b>问题1</b>：如果把"消费吃药行情"与<b>居民房地产杠杆率</b>结合（加杠杆=居民财富效应→消费/医药受益），能否补上V1在2016-2021白马牛市空仓跑输的缺口？<br>
<b>问题2</b>：原买入三条件（产业扶持政策、流动性政策、国家队入金）是否存在优先级排序，可以增强效果？
</div>

<h2>二、双Regime策略总览</h2>
<table>
<tr><th>配置</th><th>总收益</th><th>年化</th><th>夏普</th><th>最大回撤</th><th>空仓占比</th></tr>
{stats_row(nav_full, '双Regime完整版（产业扶持+杠杆消费+大基金）')}
{stats_row(nav_dual, '双Regime（产业扶持+杠杆消费，严格国家队口径）')}
{stats_row(nav_v1e, 'V1严格+大基金（单Regime）')}
{stats_row(nav_v1s, 'V1严格（单Regime）')}
{stats_row(hs_n, '沪深300基准')}
</table>

<div class="box green">
<b>核心结论</b>：消费吃药×杠杆率假设<b>验证成功</b>。双Regime把总收益从 +26.8%（V1严格）提升到 <b>+92.7%</b>；若国家队口径扩展至大基金注资（国家资本入金），达到 <b>+116.7%</b>，夏普从 0.28 → 0.58。V1最大的缺口——2016-2021白马牛市全程空仓——被杠杆Regime完整填补。
</div>

<img src="data:image/png;base64,{img64(f'{OUT}/chart_v2_nav.png')}">

<h2>三、消费吃药 = 居民加杠杆的镜像</h2>
<div class="box blue">
<b>机制逻辑</b>：居民部门快速加杠杆（年增量≥2pct）→ 房价上行 + 财富效应 + 消费升级 → 食品饮料/家电/医药（消费吃药池）基本面与估值双升；
杠杆进入平台期（增量&lt;2pct）→ 财富效应消失 → 抱团瓦解。<br>
<b>规则</b>：年增量≥2pct → 等权买入 801120食品饮料 / 801110家电 / 801150医药生物；增量跌破2pct（次年3-31数据可得后）→ 清仓消费池。买入无需国家队/流动性条件。
</div>

<img src="data:image/png;base64,{img64(f'{OUT}/chart_v2_leverage.png')}">

<h3>居民杠杆率信号表（CNBS口径）</h3>
<table>
<tr><th>年份</th><th>杠杆率(%)</th><th>年增量(pct)</th><th>Regime状态</th></tr>
{lev_rows}
</table>

<div class="box red">
<b>标志性交易</b>：食品饮料 2016-04-01 买入 → 2022-04-06 杠杆平台期退出，持有2196天，<b>+243%</b>——完整穿越白马牛市并在抱团瓦解后第一时间离场（2021-02见顶后杠杆确认数据2022-03-31到达，延迟约14个月，代价为回吐部分涨幅）。同期家电 +52.8%、医药 +7.5%。
</div>

<h2>四、买入条件优先级：消融实验</h2>
<div class="box">
<b>方法论</b>：在V1单Regime框架内逐一拆除条件——<b>去掉哪个条件收益降幅最大，该条件优先级越高</b>；同时测试放松版（三选二投票）。全部配置在同一数据、同一执行规则下对比。
</div>

<img src="data:image/png;base64,{img64(f'{OUT}/chart_v2_ablation.png')}">

<table>
<tr><th>消融配置（单Regime）</th><th>总收益</th><th>年化</th><th>夏普</th><th>最大回撤</th><th>笔数</th></tr>
{exp_rows}
</table>

<h3>优先级排序结论</h3>
<table>
<tr><th>排序</th><th>条件</th><th>证据</th><th>解读</th></tr>
<tr><td><b>P0 冗余</b></td><td>流动性政策</td><td>去掉后 27.1% vs 基准26.8%（≈不变，26笔=26笔）</td><td>降准降息与国家队入金几乎总是同框出现，条件信息被覆盖，<b>可移除</b>以简化</td></tr>
<tr><td><b>P1 纪律性</b></td><td>产业政策 / 国家队</td><td>去掉任一条件收益反而升（51.2% / 47.5%）但夏普也升（0.44 / 0.32）</td><td>两条件各自过滤掉部分机会（错过2016-2021白马）——它们的价值是<b>把买入锁死在市场底部</b>，不是提高收益</td></tr>
<tr><td><b>P2 放松</b></td><td>三选二投票</td><td>77.2% / 夏普0.43 / 94笔</td><td>多数投票大幅放松入场，捕捉更多行情，但买入点质量下降（不再全是底部）</td></tr>
<tr><td><b>P3 增强</b></td><td>杠杆率双Regime</td><td>+92.7%~+117.0%，夏普0.52~0.58</td><td><b>最强增强项</b>——不放松R1纪律，另开一条独立行情通道</td></tr>
</table>

<div class="box warn">
<b>推荐组合</b>：<span class="tag on">R1 = 产业政策 + 国家队（去掉流动性）</span> <span class="tag on">+ R2 = 杠杆率消费吃药</span> <span class="tag on">+ 大基金口径</span> → 总收益 117.0%、夏普 0.58，与三条件AND版（116.7%）几乎无差，但条件更少、更可执行。流动性条件在所有配置中均为零增量，正式判定为冗余。
</div>

<h2>五、双Regime完整版交易明细</h2>
<table>
<tr><th>日期</th><th>动作</th><th>行业</th><th>价格</th><th>收益</th><th>持有</th><th>理由</th></tr>
{trades_table(tr_full)}
</table>

<h2>六、方法论与铁律</h2>
<div class="box blue">
<b>无未来数据</b>：杠杆率为年度数据，披露对齐至次年3-31（保守口径，实际CNBS季度公布提前于该日）；行业财务披露日对齐（Q2→8-31，Q4→次年4-30）；信号T+1收盘执行。<br>
<b>数据交叉检验</b>：杠杆率走势与国房景气指数交叉验证（快速加杠杆期均值100.9 vs 平台期95.1）；申万行业指数双源核对；与V1共用全部已验证事件表。<br>
<b>状态型卖出</b>：杠杆平台期为状态信号——新数据到达日触发清仓，不依赖盘中事件，规避V1曾出现的事件型死循环。<br>
<b>局限</b>：①杠杆信号年度频率低，退出延迟约14个月（食品饮料2021-02顶→2022-04退出）；②消费池仅3行业等权，未做行业内选股；③国家队扩展口径（大基金）样本内定义，存在过拟合风险，需样本外跟踪。
</div>

<p class="small">生成时间：2026-10-01 · 数据源：CNBS居民杠杆率 / 申万行业指数(akshare) / tushare / neodata交叉验证 · 工具：backtest_v2.py</p>
</body>
</html>"""

with open(f'{OUT}/report_v2.html', 'w') as f:
    f.write(html)
print(f'V2报告已生成: {OUT}/report_v2.html ({len(html)//1024}KB)')
