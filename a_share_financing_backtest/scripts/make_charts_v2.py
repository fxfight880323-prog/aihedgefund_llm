#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V2图表：双regime净值 + 消费吃药杠杆可视化 + 条件消融"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

BASE = '/Users/seanf/WorkBuddy/A股好难/data'
OUT = '/Users/seanf/WorkBuddy/A股好难/output'

# ===== 图1: V2净值全景 =====
nav_v1s = pd.read_csv(f'{OUT}/nav_main.csv', index_col=0, parse_dates=True)['nav']
nav_v1e = pd.read_csv(f'{OUT}/nav_ext.csv', index_col=0, parse_dates=True)['nav']
nav_dual = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆消费.csv', index_col=0, parse_dates=True)['nav']
nav_full = pd.read_csv(f'{OUT}/nav_v2_R1and3_plus_杠杆_plus_大基金.csv', index_col=0, parse_dates=True)['nav']
hs = pd.read_csv(f'{BASE}/hs300.csv'); hs['date'] = pd.to_datetime(hs['date']); hs = hs.set_index('date')['close']
idx = nav_dual.index
hs_n = hs.reindex(idx).ffill(); hs_n = hs_n/hs_n.iloc[0]

fig, ax = plt.subplots(figsize=(13, 6.5), dpi=110)
ax.plot(nav_full.index, nav_full.values, color='#8e44ad', lw=2.2, label=f'双Regime完整版(含大基金) 终值{nav_full.iloc[-1]:.2f}')
ax.plot(nav_dual.index, nav_dual.values, color='#c0392b', lw=2, label=f'双Regime(产业扶持+杠杆消费) 终值{nav_dual.iloc[-1]:.2f}')
ax.plot(nav_v1e.index, nav_v1e.values, color='#e67e22', lw=1.5, label=f'V1严格+大基金 终值{nav_v1e.iloc[-1]:.2f}')
ax.plot(nav_v1s.index, nav_v1s.values, color='#16a085', lw=1.5, label=f'V1严格 终值{nav_v1s.iloc[-1]:.2f}')
ax.plot(hs_n.index, hs_n.values, color='#7f8c8d', lw=1.2, label=f'沪深300 终值{hs_n.iloc[-1]:.2f}')
# 消费regime窗口
ax.axvspan(pd.Timestamp('2016-01-04'), pd.Timestamp('2022-04-06'), color='#f1c40f', alpha=0.10)
ax.text(pd.Timestamp('2018-06'), 1.62, '居民加杠杆期\n(消费吃药Regime)', fontsize=10, color='#b7950b', ha='center')
ax.text(pd.Timestamp('2024-10'), 1.62, '国家队共振期\n(产业扶持Regime)', fontsize=10, color='#c0392b', ha='center')
ax.set_title('双Regime策略 2016-2026：消费吃药(杠杆驱动) + 产业扶持(三条件驱动) 完整捕捉两轮行情', fontsize=13)
ax.set_ylabel('净值（起点=1）')
ax.legend(loc='upper left', fontsize=10)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_v2_nav.png', bbox_inches='tight')
plt.close()

# ===== 图2: 杠杆率与消费吃药行情 =====
fig, axes = plt.subplots(2, 1, figsize=(13, 8), dpi=110, sharex=False,
                         gridspec_kw={'height_ratios': [2, 1.3]})
fd = pd.read_csv(f'{BASE}/sw_801120.csv'); fd['日期'] = pd.to_datetime(fd['日期'])
fd = fd[(fd['日期']>='2015-01-01')&(fd['日期']<='2025-12-31')]
axes[0].plot(fd['日期'], fd['收盘'], color='#c0392b', lw=1.5, label='申万食品饮料指数')
axes[0].axvspan(pd.Timestamp('2016-03-31'), pd.Timestamp('2022-03-31'), color='#f1c40f', alpha=0.15)
axes[0].annotate('策略持有区间\n2016-04 ~ 2022-04\n(+243%)', (pd.Timestamp('2019-03'), 19000), fontsize=11,
                 color='#7d6608', ha='center', fontweight='bold')
axes[0].annotate('2021-02抱团顶', (pd.Timestamp('2021-02-10'), 29000), fontsize=9.5, color='#555',
                 xytext=(30, -10), textcoords='offset points')
axes[0].set_title('消费吃药行情 = 居民加杠杆的镜像：食品饮料指数 vs 杠杆率上行窗口（黄色区间）', fontsize=13)
axes[0].legend(); axes[0].grid(alpha=0.3)

lev = pd.read_csv(f'{BASE}/household_leverage.csv')
axes[1].bar(lev['year']-2015, lev['household_leverage'], width=0.55, color='#95a5a6', alpha=0.6, label='居民杠杆率(%,左)')
ax2 = axes[1].twinx()
ax2.plot(lev['year']-2015, lev['delta'], 'o-', color='#c0392b', lw=2, label='年增量(pct,右)')
ax2.axhline(2.0, color='#e67e22', ls='--', lw=1.2, label='信号阈值2pct')
ax2.set_ylabel('年增量(pct)')
axes[1].set_xticks(lev['year']-2015); axes[1].set_xticklabels(lev['year'].astype(int))
axes[1].set_ylabel('杠杆率(%)')
axes[1].set_title('居民部门杠杆率：2016-2020快速加杠杆(+2.9~6.1pct/年) → 2021起平台期(<2pct) = 消费行情资金源枯竭', fontsize=12)
h1,l1 = axes[1].get_legend_handles_labels(); h2,l2 = ax2.get_legend_handles_labels()
axes[1].legend(h1+h2, l1+l2, loc='upper left', fontsize=9)
axes[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_v2_leverage.png', bbox_inches='tight')
plt.close()

# ===== 图3: 条件消融（优先级量化）=====
exp = pd.read_csv(f'{OUT}/v2_experiments.csv')
abl = exp[exp['配置'].isin(['and3 三条件AND(基准)','no_nt 去国家队','no_liq 去流动性','no_pol 去产业政策','vote2 三选二投票'])].copy()
order = ['and3 三条件AND(基准)','no_pol 去产业政策','no_nt 去国家队','no_liq 去流动性','vote2 三选二投票']
abl['配置'] = pd.Categorical(abl['配置'], categories=order, ordered=True)
abl = abl.sort_values('配置')
labels = ['三条件AND\n(基准26.8%)','去产业政策\n(51.2%)','去国家队\n(47.5%)','去流动性\n(27.1%)','三选二投票\n(77.2%)']
fig, ax = plt.subplots(figsize=(12, 5.5), dpi=110)
colors = ['#7f8c8d', '#c0392b', '#e67e22', '#16a085', '#8e44ad']
bars = ax.bar(range(len(abl)), abl['总收益']*100, color=colors, alpha=0.85, width=0.6)
for i, (v, s) in enumerate(zip(abl['总收益']*100, abl['夏普'])):
    ax.text(i, v+1.5, f'{v:.1f}%\n夏普{s:.2f}', ha='center', fontsize=10, fontweight='bold')
ax.axhline(26.8, color='#7f8c8d', ls='--', lw=1)
ax.set_xticks(range(len(abl))); ax.set_xticklabels(labels, fontsize=10.5)
ax.set_ylabel('总收益(%)')
ax.set_title('买入条件优先级消融实验：去掉哪个条件伤害最大 = 该条件优先级最高', fontsize=13)
ax.grid(alpha=0.3, axis='y')
fig.tight_layout()
fig.savefig(f'{OUT}/chart_v2_ablation.png', bbox_inches='tight')
plt.close()
print('V2图表已生成')
