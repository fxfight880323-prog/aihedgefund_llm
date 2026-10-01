#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成回测图表"""
import sys
sys.path.insert(0, '/Users/seanf/WorkBuddy/A股好难/scripts')
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 中文字体
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

BASE = '/Users/seanf/WorkBuddy/A股好难/data'
OUT = '/Users/seanf/WorkBuddy/A股好难/output'
COLOR_UP = '#d43a3a'   # 中国股市涨=红
COLOR_DOWN = '#1a9850' # 跌=绿

# 数据
nav_strict = pd.read_csv(f'{OUT}/nav_main.csv', index_col=0, parse_dates=True)['nav']
nav_ext = pd.read_csv(f'{OUT}/nav_ext.csv', index_col=0, parse_dates=True)['nav']
trades_main = pd.read_csv(f'{OUT}/trades_main.csv', parse_dates=['date'])
trades_ext = pd.read_csv(f'{OUT}/trades_ext.csv', parse_dates=['date'])
hs = pd.read_csv(f'{BASE}/hs300.csv'); hs['date'] = pd.to_datetime(hs['date'])
hs = hs.set_index('date')['close']
zz = pd.read_csv(f'{BASE}/zz500.csv'); zz['date'] = pd.to_datetime(zz['date'])
zz = zz.set_index('date')['close']

idx = nav_strict.index
hs_n = (hs.reindex(idx).ffill() / hs.reindex(idx).ffill().iloc[0])
zz_n = (zz.reindex(idx).ffill() / zz.reindex(idx).ffill().iloc[0])

# ===== 图1: NAV对比 =====
fig, ax = plt.subplots(figsize=(13, 6.5), dpi=110)
ax.plot(nav_strict.index, nav_strict.values, color='#c0392b', lw=2, label=f'策略·严格口径 (终值{nav_strict.iloc[-1]:.3f})')
ax.plot(nav_ext.index, nav_ext.values, color='#8e44ad', lw=2, alpha=0.9, label=f'策略·扩展口径含大基金 (终值{nav_ext.iloc[-1]:.3f})')
ax.plot(hs_n.index, hs_n.values, color='#7f8c8d', lw=1.2, label=f'沪深300 (终值{hs_n.iloc[-1]:.3f})')
ax.plot(zz_n.index, zz_n.values, color='#bdc3c7', lw=1.2, label=f'中证500 (终值{zz_n.iloc[-1]:.3f})')
# 买入事件标注（扩展口径）
buys = trades_ext[trades_ext['action']=='买入']
for _, b in buys.iterrows():
    ax.axvline(b['date'], color='#e67e22', alpha=0.3, lw=1)
ax.set_title('A股融资市场逻辑回测 2016-2026：策略 vs 基准（橙线=三信号共振买入时点）', fontsize=13)
ax.set_ylabel('净值（起点=1）')
ax.legend(loc='upper left', fontsize=10)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_nav.png', bbox_inches='tight')
plt.close()

# ===== 图2: 买入时点=市场底部特征（在沪深300上标注）=====
fig, ax = plt.subplots(figsize=(13, 5), dpi=110)
ax.plot(hs.index[(hs.index>='2016-01-01')], hs[hs.index>='2016-01-01'].values, color='#2c3e50', lw=1.2, label='沪深300')
bgroups = buys.groupby('date')['name'].apply(lambda x: '+'.join(x))
for dt, names in bgroups.items():
    v = hs.asof(dt)
    ax.scatter(dt, v, color='#c0392b', s=48, zorder=5, marker='^')
    ax.annotate(names, (dt, v), textcoords='offset points', xytext=(0, -18),
                fontsize=8.5, color='#c0392b', ha='center', rotation=0)
ax.set_title('三信号共振买入时点全部出现在市场底部区域（沪深300标注）', fontsize=13)
ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_buy_points.png', bbox_inches='tight')
plt.close()

# ===== 图3: 电力设备产业周期实例（用户逻辑全周期可视化）=====
fig, axes = plt.subplots(2, 1, figsize=(13, 8), dpi=110, sharex=True,
                         gridspec_kw={'height_ratios': [2, 1.2]})
px = pd.read_csv(f'{BASE}/sw_801730.csv')
px['日期'] = pd.to_datetime(px['日期'])
px = px[(px['日期']>='2019-01-01')&(px['日期']<='2025-12-31')]
axes[0].plot(px['日期'], px['收盘'], color='#c0392b', lw=1.5)
axes[0].set_title('电力设备（新能源）产业周期实例：政策扶持→国家队→盈利兑现→增速减缓→周期结束', fontsize=13)
ann = [('2020-09-22','双碳目标(政策)', 4800, 'top'),
       ('2020-04-15','疫情后流动性宽松', 4000, 'bottom'),
       ('2022-08-31','中报增速+124%见顶', 11000, 'top'),
       ('2024-02-06','汇金扩大增持(国家队)', 5500, 'bottom')]
for dt, txt, y, pos in ann:
    axes[0].axvline(pd.Timestamp(dt), color='#7f8c8d', ls='--', alpha=0.6)
    axes[0].annotate(txt, (pd.Timestamp(dt), y), fontsize=9.5, color='#2c3e50', ha='center')
fin = pd.read_csv(f'{BASE}/industry_financials.csv')
f = fin[fin['index_code']=='801730.SI'].sort_values(['year','half'])
xpos = f['year'] + (f['half']=='Q2')*0.5
axes[1].bar(xpos, f['np_yoy'], width=0.38,
            color=[COLOR_UP if v>0 else COLOR_DOWN for v in f['np_yoy']], alpha=0.85)
axes[1].axhline(50, color='#f39c12', ls='--', lw=1, label='盈利兑现阈值50%')
axes[1].set_ylabel('归母净利润同比(%)')
axes[1].set_title('行业盈利周期：2020-2022扶持期高速增长 → 2023增速骤减 → 2024转负（卖出信号链）', fontsize=12)
axes[1].legend(); axes[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f'{OUT}/chart_cycle.png', bbox_inches='tight')
plt.close()

# ===== 图4: 年度收益对比 =====
def yearly(nav):
    ye = nav.resample('YE').last()
    ye.iloc[0] = nav.iloc[0]
    return ye.pct_change().dropna() * 100

fig, ax = plt.subplots(figsize=(13, 5), dpi=110)
yr_s = yearly(nav_ext); yr_h = yearly(hs_n); yr_z = yearly(zz_n)
years = sorted(set(yr_s.index.year) | set(yr_h.index.year))
w = 0.27
x = np.arange(len([y for y in years if y <= 2026]))
def getv(series, y):
    try: return series[series.index.year == y].iloc[0]
    except: return 0
vals_s = [getv(yr_s, y) for y in years if y <= 2026]
vals_h = [getv(yr_h, y) for y in years if y <= 2026]
vals_z = [getv(yr_z, y) for y in years if y <= 2026]
xs = [str(y) for y in years if y <= 2026]
ax.bar(x-w, vals_s, w, color='#c0392b', label='策略·扩展口径')
ax.bar(x,   vals_h, w, color='#7f8c8d', label='沪深300')
ax.bar(x+w, vals_z, w, color='#bdc3c7', label='中证500')
ax.set_xticks(x); ax.set_xticklabels(xs)
ax.set_ylabel('年度收益率(%)')
ax.axhline(0, color='k', lw=0.8)
ax.set_title('年度收益对比：策略在2019/2024/2025结构性成长行情中占优，2017/2020白马牛市中空仓跑输', fontsize=12)
ax.legend(); ax.grid(alpha=0.3, axis='y')
fig.tight_layout()
fig.savefig(f'{OUT}/chart_yearly.png', bbox_inches='tight')
plt.close()

print('图表已生成:', [f for f in ['chart_nav','chart_buy_points','chart_cycle','chart_yearly']])
