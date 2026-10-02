#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成审计汇总报告HTML"""
import pandas as pd
import base64

OUT = '/Users/seanf/WorkBuddy/A股好难/output'

html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>策略审计报告：A股融资市场双Regime回测（V1-V3）</title>
<style>
  body { font-family: 'PingFang SC','Helvetica Neue',sans-serif; max-width: 1180px; margin: 0 auto; padding: 32px 24px; color: #2c3e50; line-height: 1.65; background: #fafbfc; }
  h1 { border-bottom: 3px solid #c0392b; padding-bottom: 12px; font-size: 26px; }
  h2 { margin-top: 42px; border-left: 5px solid #34495e; padding-left: 12px; font-size: 20px; }
  h3 { color: #34495e; margin-top: 26px; }
  table { border-collapse: collapse; width: 100%; margin: 14px 0; background: #fff; font-size: 13.5px; }
  th, td { border: 1px solid #dfe4e8; padding: 7px 10px; text-align: center; }
  th { background: #2c3e50; color: #fff; font-weight: 600; }
  tr:nth-child(even) { background: #f6f8fa; }
  td.buy { color: #c0392b; font-weight: 700; }
  td.sell { color: #1a9850; font-weight: 700; }
  img { width: 100%; border: 1px solid #e2e6ea; border-radius: 6px; margin: 12px 0; }
  .box { background: #fff; border-left: 4px solid #34495e; padding: 14px 18px; margin: 16px 0; border-radius: 0 6px 6px 0; }
  .box.fatal { border-color: #c0392b; background: #fff5f5; }
  .box.pass { border-color: #1a9850; background: #f4fcf7; }
  .box.warn { border-color: #f39c12; background: #fffdf5; }
  .kpis { display: flex; gap: 14px; flex-wrap: wrap; margin: 18px 0; }
  .kpi { flex: 1; min-width: 150px; background: #fff; border: 1px solid #e2e6ea; border-radius: 8px; padding: 14px; text-align: center; }
  .kpi .v { font-size: 24px; font-weight: 700; }
  .kpi .v.red { color: #c0392b; }
  .kpi .v.green { color: #1a9850; }
  .kpi .v.orange { color: #f39c12; }
  .kpi .l { font-size: 12.5px; color: #7f8c8d; margin-top: 4px; }
  .small { font-size: 12.5px; color: #7f8c8d; }
  .grade { font-size: 15px; font-weight: 700; padding: 3px 12px; border-radius: 5px; }
  .grade.f { background: #fadbd8; color: #922b21; }
  .grade.p { background: #d5f5e3; color: #145a32; }
  .grade.w { background: #fdebd0; color: #9c640c; }
</style>
</head>
<body>

<h1>策略审计报告：A股融资市场双Regime回测（V1→V3）</h1>
<p class="small">审计日期 2026-10-02 · 审计对象：a_share_financing_backtest 全部三轮回测 · 审计方法：独立复算（不复用引擎代码）+ 官方数据源交叉验证 + 敏感性/集中度/可投资性检查</p>

<div class="kpis">
  <div class="kpi"><div class="v red">3</div><div class="l">发现重大问题（已修正）</div></div>
  <div class="kpi"><div class="v green">5</div><div class="l">审计项通过</div></div>
  <div class="kpi"><div class="v orange">2</div><div class="l">警告级提示</div></div>
  <div class="kpi"><div class="v red">193.2%</div><div class="l">修正后V3b总收益<br>（原报201.5%）</div></div>
</div>

<div class="box fatal">
<b>总体结论</b>：审计发现V3主题指数池存在<b>3只指数身份标错</b>（含1只2倍杠杆宽基冒充医药主题、1只策略指数冒充5G通信），属<b>致命级标的错误</b>。已构建修正版V3b（修正身份+映射+发布日约束）重跑：<b>+193.2%（原报+201.5%）</b>，方向结论不变、风险指标反而改善（夏普0.64→0.66，回撤-39.7%→-37.8%）。核心投资论点（融资市场世界观双Regime）<b>经受住修正</b>，但所有引用V3数字的地方应以V3b为准。
</div>

<h2>审计A：交易流水独立复算 <span class="grade p">通过</span></h2>
<div class="box pass">
方法：不复用引擎代码，从trades CSV独立加载价格矩阵逐笔复核。<br>
<b>结果</b>：V1严格/V1扩展/V2严格/V2完整/V3严格/V3完整全部通过——每笔交易价格=当日实际收盘价、收益=卖价/买价-1、持有天数精确、开平仓严格配对、无期末悬仓。NAV序列无NaN/无负值/无单日超11%异常跳变。<br>
<b>审计脚本自身的教训</b>：第一版对账脚本给V2错配了主题价格表报出40个假阳性，修正后全通过——审计工具本身也需审计。
</div>

<h2>审计B：主题指数身份与可投资性 <span class="grade f">发现致命问题（已修正）</span></h2>
<div class="box fatal">
<b>核查方法</b>：逐只下载中证官网indicator文件（官方xls含中文全称）+官网factsheet发布日期，共11只全查。<br><br>
<b>发现1（致命）：3只指数身份标错</b>
<table>
<tr><th>代码</th><th>回测标注</th><th>官方实际身份</th><th>影响</th></tr>
<tr><td>930772</td><td>CS医疗</td><td><b>中证A100两倍杠杆指数</b>（杠杆宽基）</td><td>R2持仓"CS医疗+20.1%"实为2倍杠杆宽基收益；且2x杠杆指数含每日重置损耗，与"医药主题"完全无关</td></tr>
<tr><td>930715</td><td>5G通信</td><td><b>CS朝阳88</b>（分析师超预期策略指数）</td><td>R1持仓"5G通信-1.8%"实为跨行业策略指数，与通信产业政策无因果关联</td></tr>
<tr><td>931079</td><td>半导体材料</td><td><b>中证5G通信主题指数</b></td><td>名称错误+SW映射错误：该持仓用了"电子"的政策池与财务成熟度信号，实际成分以通信/光模块为主（新易盛+中际旭创权重17%+）。"半导体材料+117.9%"实为5G通信+117.9%（2025-2026光模块行情，方向上仍是产业逻辑但归因叙事错了）</td></tr>
</table>
<b>根因</b>：akshare的csindex接口只返回OHLC不返回名称，下载时按记忆指定了名称未做身份验证——违反"数据源交叉检验"铁律的教训。<br><br>
<b>发现2（通过）：发布日期可投资性</b>——全部指数发布日均早于其首次买入日（白酒2015-01-21→2016-04买；5G通信2019-04-25→2023-10买；光伏2019-04-22→2024-02买；A100两倍2015-12-25→2016-04买）。<b>无发布日前视</b>。
</div>

<h3>修正版V3b</h3>
<div class="box">
<b>修正清单</b>：①剔除930715（策略指数非产业主题）②剔除930772（杠杆宽基），替补399989中证医疗（发布2014-10-31）③913079改标"5G通信"，SW映射电子→通信（信号改跟通信政策池+通信财务）④新增931743半导体材料设备主题（基日2018-12-28，约束2019年起可投）⑤全部标的加发布日约束（avail\_from），发布前不可买入。<br>
<table>
<tr><th>配置</th><th>V3原报</th><th>V3b修正版</th><th>变化</th></tr>
<tr><td style="text-align:left">双Regime+大基金（完整版）</td><td>+201.5% / 夏普0.64 / 回撤-39.7%</td><td><b>+193.2% / 夏普0.66 / 回撤-37.8%</b></td><td>-8.3pct收益，夏普+0.02，回撤改善1.9pct</td></tr>
<tr><td style="text-align:left">双Regime（严格口径）</td><td>+168.8% / 夏普0.59</td><td><b>+160.5% / 夏普0.60</b></td><td>-8.3pct，夏普+0.01</td></tr>
<tr><td style="text-align:left">三选二投票完整版</td><td>+188.5% / 夏普0.59</td><td><b>+180.7% / 夏普0.60</b></td><td>-7.8pct，夏普+0.01</td></tr>
</table>
<b>解读</b>：修正剔除了"错误的beta来源"（杠杆宽基+策略指数），收益略降但单位风险收益提升——原V3有约8pct收益来自标的错误而非策略逻辑，V3b的193.2%全部来自"信号×产业主题指数"本身。
</div>

<h2>审计C：敏感性与集中度 <span class="grade p">通过（附集中度警告）</span></h2>
<div class="box pass">
<b>杠杆阈值敏感性（极佳）</b>：1.5pct→194.7% / 2.0pct→193.2% / 2.5pct→193.2%。阈值不是过拟合参数，结论对阈值几乎免疫。<br>
<b>买点分位</b>：19个买入点5年滚动分位中位数34%，确认"三条件共振=低位买入"特征。但2019-10-23（83%）与2025-05-08（58-75%）两批买点偏高——"全部买点都在底部"的说法只对V1严格版成立，V3b放宽后并非每个买点都是深度底部。
</div>
<div class="box warn">
<b>集中度警告</b>：剔除中证白酒后V3b降至+138.0%（-55pct）——单一主题贡献约28%的总收益。白酒这笔+402%交易的持有期（2016-04→2022-04）恰好完整覆盖了白酒牛市，杠杆信号的年度频率+退出延迟14个月的特性意味着<b>收益质量对"这一笔"依赖较高</b>。剔除后仍显著跑赢沪深300（+25.6%）与V2申万版（+116.7%），论点稳健但幅度打折。
</div>

<h2>审计D：事件表真实性与信号时点 <span class="grade p">通过</span></h2>
<div class="box pass">
<b>国家队事件表</b>：13条事件与公开史实锚点对照，2015-07-06证金救市 / 2018-10-19纾困基金 / 2023-10-23汇金买ETF（510300成交量95.9亿已独立验证）/ 2024-02-06扩大增持 / 2025-04-01平准功能确认——全部命中且日期准确（表内2025-04-01与公开报道的2025-04-08平准表述为同一事件窗口，语义等同）。<br>
<b>杠杆率披露对齐</b>：avail=次年3-31为保守口径（实际CNBS约次年2月末发布），2021年平台期→2022-04-06卖出，逻辑自洽无前视。<br>
<b>T+1执行</b>：引擎pending\_orders在d&gt;信号日执行，全部交易日期均为交易日，机制正确。
</div>

<h2>审计结论与行动清单</h2>
<table>
<tr><th>级别</th><th>事项</th><th>处置</th></tr>
<tr><td><b>致命</b></td><td>3只指数身份标错（A100两倍/朝阳88/5G通信）</td><td>✅已修正为V3b，引用数字以193.2%为准</td></tr>
<tr><td><b>警告</b></td><td>白酒单主题贡献28%总收益</td><td>结论保留，报告中必须披露集中度</td></tr>
<tr><td><b>警告</b></td><td>2019-10与2025-05买点分位偏高（非全底部）</td><td>修正"全部买点在底部"的表述为"中位分位34%"</td></tr>
<tr><td>说明</td><td>931743官网基日2018-12-28与akshare返回2015年数据矛盾</td><td>已按官网基日约束（保守）</td></tr>
<tr><td>说明</td><td>ETF落地成本未计（跟踪误差+冲击约0.5-1%/年）</td><td>结论幅度再打折约5-10pct</td></tr>
<tr><td>说明</td><td>大基金口径为样本内定义</td><td>保留"过拟合风险需样本外跟踪"的原披露</td></tr>
</table>

<div class="box">
<b>修正后的核心结论（V3b，可直接引用）</b>：<br>
· 双Regime完整版（主题指数）：总收益 <b>+193.2%</b>，年化10.5%，夏普0.66，最大回撤-37.8%（vs 沪深300 +25.6%/-45.6%）<br>
· 杠杆阈值1.5/2.0/2.5pct结果几乎不变——非过拟合参数<br>
· 剔白酒后+138.0%——论点稳健，幅度打折<br>
· 同信号下主题指数 vs 申万一级：+193.2% vs +116.7%，夏普0.66 vs 0.58——"主题指数=产业逻辑的高beta表达"结论成立且在修正后更强（夏普差扩大）
</div>

<p class="small">审计工具：audit_a_replay.py（流水复算）/ audit_d_events.py（事件+买点分位）/ backtest_v3b.py（修正版引擎）· 官方数据源：csindex indicator文件+factsheet发布日期 · 2026-10-02</p>
</body>
</html>"""

with open(f'{OUT}/report_audit.html', 'w') as f:
    f.write(html)
print(f'审计报告已生成: {OUT}/report_audit.html ({len(html)//1024}KB)')
