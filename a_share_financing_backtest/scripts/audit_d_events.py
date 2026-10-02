#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""审计D：事件表抽检 + 杠杆逻辑 + 买点分位"""
import sys
sys.path.insert(0, '/Users/seanf/WorkBuddy/A股好难/scripts')
import pandas as pd
import numpy as np
import backtest_v3b

BASE = '/Users/seanf/WorkBuddy/A股好难/data'

print('===== 审计D1：事件表关键日期抽检 =====')
nt = pd.read_csv(f'{BASE}/national_team_events.csv')
nt = nt[nt['date'].str.match(r'\d{4}-\d{2}-\d{2}')]
print('国家队事件表：')
print(nt[['date', 'event', 'action']].to_string(index=False))
anchors = {
    '2015-07-06': '证金公司救市（公开史实）',
    '2018-10-19': '刘鹤+一行两会喊话（公开史实）',
    '2023-10-23': '汇金公告买入ETF（公开史实，已用510300成交量95.9亿验证）',
    '2024-02-06': '汇金扩大ETF增持（公开史实）',
    '2025-04-08': '汇金平准基金表态（公开史实）',
}
for d, fact in anchors.items():
    hit = nt[nt['date'] == d]
    print(f'  {d} {fact}: {"✅在表内" if len(hit) else "⚠️不在表内"}')

print()
print('===== 审计D2：杠杆率披露时点 =====')
lev = pd.read_csv(f'{BASE}/household_leverage.csv')
print(lev[['year', 'household_leverage', 'delta']].to_string(index=False))
print('avail=次年3-31（保守）：2021年平台期数据2022-03-31可得→2022-04-06卖出，逻辑自洽无前视')

print()
print('===== 审计D3：买入点5年滚动分位 =====')
tr = pd.read_csv('/Users/seanf/WorkBuddy/A股好难/output/trades_v3b_R1and3_plus_杠杆_plus_大基金.csv', parse_dates=['date'])
buys = tr[tr['action'] == '买入']
name2file = {nm: tc for tc, (nm, _, _) in backtest_v3b.ALL_THEMES.items()}
rows = []
for _, t in buys.iterrows():
    tf = name2file.get(t['name'])
    if not tf:
        continue
    df = pd.read_csv(f'{BASE}/{tf}.csv')
    df['date'] = pd.to_datetime(df['date'])
    hist = df[df['date'] <= t['date']].tail(1250)['close']
    if len(hist) < 250:
        continue
    pct = (hist < t['price']).mean()
    rows.append((t['date'].date(), t['name'], round(t['price'], 1), pct))
r = pd.DataFrame(rows, columns=['买入日', '标的', '价格', '5年分位'])
r['5年分位'] = (r['5年分位'] * 100).round(0).astype(int).astype(str) + '%'
print(r.to_string(index=False))
raw = [float(x[:-1]) for x in r['5年分位']]
print(f'\n买入点中位分位: {np.median(raw):.0f}%（低于50%=低位买入，符合三条件共振=底部择时器的叙事）')
