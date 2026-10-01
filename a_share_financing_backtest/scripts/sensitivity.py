#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""敏感性测试 + 样本外分段验证 + 国家队双口径"""
import sys, os
sys.path.insert(0, '/Users/seanf/WorkBuddy/A股好难/scripts')
import pandas as pd
import numpy as np
from backtest import run_backtest, perf_stats, P, load_prices, load_events, load_financials, build_signals
from datetime import timedelta

BASE = '/Users/seanf/WorkBuddy/A股好难/data'

# 基准加载
def bench_navs():
    hs = pd.read_csv(f'{BASE}/hs300.csv'); hs['date'] = pd.to_datetime(hs['date'])
    hs = hs.set_index('date')['close']
    zz = pd.read_csv(f'{BASE}/zz500.csv'); zz['date'] = pd.to_datetime(zz['date'])
    zz = zz.set_index('date')['close']
    return hs, zz

def seg_stats(nav, start, end, label):
    seg = nav[(nav.index >= start) & (nav.index <= end)]
    if len(seg) < 10: return None
    s = perf_stats(seg, label)
    return s

results = []

# ===== 1. 参数敏感性矩阵 =====
grid = {
    'liquidity_window': [60, 90, 120],
    'profit_threshold': [30.0, 50.0, 70.0],
    'policy_valid_days': [270, 365, 545],
    'nt_window': [90, 120, 180],
}
print('=== 参数敏感性（每次只动一个参数，其余默认）===')
nav_base, trades_base, _ = run_backtest(P, verbose=False)
s_base = perf_stats(nav_base, '基准参数')
print(f"默认: 总收益{s_base['total']:.1%} 年化{s_base['annual']:.1%} 夏普{s_base['sharpe']:.2f} 回撤{s_base['mdd']:.1%}")
results.append(('默认', s_base['total'], s_base['annual'], s_base['sharpe'], s_base['mdd']))
for pname, values in grid.items():
    for v in values:
        pp = dict(P); pp[pname] = v
        nav, trades, _ = run_backtest(pp, verbose=False)
        s = perf_stats(nav, f'{pname}={v}')
        results.append((f'{pname}={v}', s['total'], s['annual'], s['sharpe'], s['mdd']))
        print(f"{pname}={v}: 总收益{s['total']:.1%} 年化{s['annual']:.1%} 夏普{s['sharpe']:.2f} 回撤{s['mdd']:.1%} 交易{len(trades)}笔")

# ===== 2. 国家队扩展口径（大基金注资也算国家资金入场）=====
print('\n=== 国家队口径敏感性 ===')
# 扩展口径：大基金一/二/三期注资 = 国家资本直接入金
import shutil
nt_ext = f'{BASE}/national_team_events_ext.csv'
if not os.path.exists(nt_ext):
    shutil.copy(f'{BASE}/national_team_events.csv', nt_ext)
    with open(nt_ext, 'a') as fp:
        fp.write("""2014-09-24,大基金一期注资集成电路(国家资本入金),买入,国家队扩展
2019-10-22,大基金二期注资(国家资本入金),买入,国家队扩展
2024-05-24,大基金三期注资3440亿(国家资本入金),买入,国家队扩展
""")

# monkey-patch load_events 使用扩展表
import backtest as bt
orig_load = bt.load_events
def load_events_ext():
    pol, liq, nt = orig_load()
    nt2 = pd.read_csv(nt_ext)
    nt2 = nt2[nt2['date'].str.match(r'\d{4}-\d{2}-\d{2}')]
    nt2['date'] = pd.to_datetime(nt2['date'])
    return pol, liq, nt2
bt.load_events = load_events_ext
nav_ext, trades_ext, _ = run_backtest(P, verbose=False)
s_ext = perf_stats(nav_ext, '扩展口径(含大基金)')
print(f"扩展口径: 总收益{s_ext['total']:.1%} 年化{s_ext['annual']:.1%} 夏普{s_ext['sharpe']:.2f} 回撤{s_ext['mdd']:.1%} 交易{len(trades_ext)}笔")
results.append(('国家队=扩展口径(含大基金注资)', s_ext['total'], s_ext['annual'], s_ext['sharpe'], s_ext['mdd']))
nav_ext.to_frame('nav').to_csv('/Users/seanf/WorkBuddy/A股好难/output/nav_ext.csv')
trades_ext.to_csv('/Users/seanf/WorkBuddy/A股好难/output/trades_ext.csv', index=False)
bt.load_events = orig_load

# ===== 3. 样本内/样本外分段（默认口径）=====
print('\n=== 样本外分段验证（事件表客观、无参数拟合，分段仅供参考）===')
for start, end, label in [('2016-01-01','2021-06-30','前段2016-2021H1'),
                           ('2021-07-01','2026-09-30','后段2021H2-2026')]:
    s = seg_stats(nav_base, start, end, label)
    if s:
        print(f"{label}: 总收益{s['total']:.1%} 年化{s['annual']:.1%} 夏普{s['sharpe']:.2f} 回撤{s['mdd']:.1%}")
        results.append((label, s['total'], s['annual'], s['sharpe'], s['mdd']))

# 基准分段
hs, zz = bench_navs()
for start, end, label in [('2016-01-01','2021-06-30','沪深300前段'), ('2021-07-01','2026-09-30','沪深300后段')]:
    b = hs[(hs.index>=start)&(hs.index<=end)]
    b = b/b.iloc[0]
    s = perf_stats(b, label)
    print(f"{label}: 总收益{s['total']:.1%} 年化{s['annual']:.1%} 回撤{s['mdd']:.1%}")
    results.append((label, s['total'], s['annual'], s['sharpe'], s['mdd']))

# 保存敏感性结果
df = pd.DataFrame(results, columns=['配置','总收益','年化','夏普','最大回撤'])
df.to_csv('/Users/seanf/WorkBuddy/A股好难/output/sensitivity.csv', index=False)
print('\n敏感性结果已保存 output/sensitivity.csv')
