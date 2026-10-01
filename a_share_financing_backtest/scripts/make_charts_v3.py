#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V3图表：主题指数 vs 申万一级行业 对比"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

BASE = '/Users/seanf/WorkBuddy/A股好难/data'
OUT = '/Users/seanf/WorkBuddy/A股好难/output'

# ===== 图1: 净值对比（同信号双Regime完整版）=====
nav_v3 = pd.read_csv(f'{OUT}/nav_v3_R1and3_plus_杠杆_plus_大基金.csv', index_col=0, parse_dates=True)['nav']
nav_v3dual = pd.read_csv(f'{OUT}/nav_v3_R1and3_plus_杠杆消费.csv', index_col=0, parse_dates=True)['nav']
nav_v2 = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆_plus_大基金.csv', index_col=0, parse_dates=True)['nav']
nav_v2dual = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆消费.csv', index_col=0, parse_dates=True)['nav']
hs = pd.read_csv(f'{BASE}/hs300.csv'); hs['date'] = pd.to_datetime(hs['date']); hs = hs.set_index('date')['close']
idx = nav_v3.index
hs_n = hs.reindex(idx).ffill(); hs_n = hs_n/hs_n.iloc[0]

fig, ax = plt.subplots(figsize=(13, 6.5), dpi=110)
ax.plot(nav_v3.index, nav_v3.values, color='#8e44ad', lw=2.2, label=f'V3主题指数·双Regime+大基金 终值{nav_v3.iloc[-1]:.2f}')
ax.plot(nav_v2.index, nav_v2.values, color='#c0392b', lw=2, label=f'V2申万一级·双Regime+大基金 终值{nav_v2.iloc[-1]:.2f}')
ax.plot(nav_v3dual.index, nav_v3dual.values, color='#9b59b6', lw=1.5, ls='--', label=f'V3主题·双Regime(严格口径) 终值{nav_v3dual.iloc[-1]:.2f}')
ax.plot(nav_v2dual.index, nav_v2dual.values, color='#e67e22', lw=1.5, ls='--', label=f'V2申万·双Regime(严格口径) 终值{nav_v2dual.iloc[-1]:.2f}')
ax.plot(hs_n.index, hs_n.values, color='#7f8c8d', lw=1.2, label=f'沪深300 终值{hs_n.iloc[-1]:.2f}')
ax.axvspan(pd.Timestamp('2016-01-04'), pd.Timestamp('2022-04-06'), color='#f1c40f', alpha=0.10)
ax.text(pd.Timestamp('2018-06'), 2.6, '居民加杠杆期\n(消费吃药Regime)', fontsize=10, color='#b7950b', ha='center')
ax.text(pd.Timestamp('2024-10'), 2.6, '国家队共振期\n(产业扶持Regime)', fontsize=10, color='#c0392b', ha='center')
ax.set_title('同一双Regime信号：主题指数 vs 申万一级行业指数 标的对比 2016-2026', fontsize=13)
ax.set_ylabel('净值（起点=1）')
ax.legend(loc='upper left', fontsize=10)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_v3_vs_v2.png', bbox_inches='tight')
plt.close()

# ===== 图2: 白酒 vs 食品饮料SW（集中度放大效应）=====
bj = pd.read_csv(f'{BASE}/theme_baijiu.csv'); bj['date'] = pd.to_datetime(bj['date'])
fd = pd.read_csv(f'{BASE}/sw_801120.csv'); fd['日期'] = pd.to_datetime(fd['日期'])
fig, axes = plt.subplots(1, 1, figsize=(13, 5.5), dpi=110)
ax = axes
bj_s = bj[(bj['date']>='2015-01-01')&(bj['date']<='2025-12-31')]
fd_s = fd[(fd['日期']>='2015-01-01')&(fd['日期']<='2025-12-31')]
ax.plot(bj_s['date'], bj_s['close']/bj_s['close'].iloc[0]*100, color='#8e44ad', lw=1.6, label='中证白酒(主题指数)')
ax.plot(fd_s['日期'], fd_s['收盘']/fd_s['收盘'].iloc[0]*100, color='#c0392b', lw=1.6, label='申万食品饮料(一级行业)')
ax.axvspan(pd.Timestamp('2016-03-31'), pd.Timestamp('2022-03-31'), color='#f1c40f', alpha=0.13)
ax.annotate('策略持有区间 2016-04~2022-04\n白酒 +402% vs 食品饮料 +243%', (pd.Timestamp('2019-03'), 130),
            fontsize=11, color='#4a235a', ha='center', fontweight='bold')
ax.set_title('集中度放大效应：同一Regime信号下 主题指数弹性显著高于一级行业指数', fontsize=13)
ax.set_ylabel('归一化价格(2015-01=100)')
ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_v3_baijiu.png', bbox_inches='tight')
plt.close()

# ===== 图3: 全配置对比柱状图 =====
v2 = pd.read_csv(f'{OUT}/v2_experiments.csv')
v3 = pd.read_csv(f'{OUT}/v3_experiments.csv')
cfgs = [('and3 三条件AND(基准)', '三条件AND\n(单Regime)'),
        ('vote2 三选二投票', '三选二投票\n(单Regime)'),
        ('R1and3 + 杠杆消费', '双Regime\n(严格口径)'),
        ('R1and3 + 杠杆 + 大基金', '双Regime+大基金\n(完整版)')]
labels = [c[1] for c in cfgs]
v2_vals = [float(v2[v2['配置']==c[0]]['总收益'].iloc[0])*100 for c in cfgs]
v3_vals = [float(v3[v3['配置']==c[0]]['总收益'].iloc[0])*100 for c in cfgs]
v2_sh = [float(v2[v2['配置']==c[0]]['夏普'].iloc[0]) for c in cfgs]
v3_sh = [float(v3[v3['配置']==c[0]]['夏普'].iloc[0]) for c in cfgs]
x = np.arange(len(cfgs)); w = 0.36
fig, ax = plt.subplots(figsize=(12, 5.8), dpi=110)
b1 = ax.bar(x-w/2, v2_vals, w, color='#c0392b', alpha=0.85, label='V2 申万一级行业指数')
b2 = ax.bar(x+w/2, v3_vals, w, color='#8e44ad', alpha=0.85, label='V3 行业主题指数')
for i in range(len(cfgs)):
    ax.text(x[i]-w/2, v2_vals[i]+3, f'{v2_vals[i]:.1f}%\n夏普{v2_sh[i]:.2f}', ha='center', fontsize=9.5, fontweight='bold', color='#c0392b')
    ax.text(x[i]+w/2, v3_vals[i]+3, f'{v3_vals[i]:.1f}%\n夏普{v3_sh[i]:.2f}', ha='center', fontsize=9.5, fontweight='bold', color='#6c3483')
    ax.text(x[i], max(v2_vals[i], v3_vals[i])+38, f'Δ+{v3_vals[i]-v2_vals[i]:.0f}pct', ha='center', fontsize=10, color='#1a9850', fontweight='bold')
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10.5)
ax.set_ylabel('总收益(%)')
ax.set_title('标的更换实验：同一双Regime信号框架，主题指数 vs 申万一级行业（2016-2026）', fontsize=13)
ax.legend(fontsize=11)
ax.grid(alpha=0.3, axis='y')
ax.set_ylim(0, max(v3_vals)*1.22)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_v3_compare.png', bbox_inches='tight')
plt.close()
print('V3对比图表已生成: chart_v3_vs_v2.png / chart_v3_baijiu.png / chart_v3_compare.png')
