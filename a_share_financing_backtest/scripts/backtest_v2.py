#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测V2：双regime + 条件优先级消融
====================================
Regime 1（产业扶持，原策略）: 产业政策+流动性+国家队三条件共振买成长行业
Regime 2（消费吃药+房地产杠杆，新增）: 居民杠杆率年增量≥2pct(加杠杆上行期)
        → 买消费池(食品饮料/家电/医药)，无需国家队/流动性条件
        → 杠杆增量<2pct(平台期) → 卖出
优先级消融: 三条件逐一去除 / 2-of-3投票，测各条件贡献
四项铁律不变：数据对齐 / 披露日对齐+T+1 / 分段验证 / 逻辑可溯源
"""
import sys
sys.path.insert(0, '/Users/seanf/WorkBuddy/A股好难/scripts')
import pandas as pd
import numpy as np
from datetime import timedelta
from backtest import load_events, load_financials, build_signals, perf_stats, P

BASE = '/Users/seanf/WorkBuddy/A股好难/data'
OUT = '/Users/seanf/WorkBuddy/A股好难/output'

# 10行业全集（8成长 + 2消费）
IND_ALL = {
    '801080': '电子', '801750': '计算机', '801770': '通信', '801730': '电力设备',
    '801150': '医药生物', '801890': '机械设备', '801740': '国防军工', '801880': '汽车',
    '801120': '食品饮料', '801110': '家电',
}
GROWTH = ['801080','801750','801770','801730','801150','801890','801740','801880']
CONS_POOL = ['801120', '801110', '801150']  # 消费吃药池（医药双regime共享）

def load_prices2():
    frames = {}
    for code in IND_ALL:
        df = pd.read_csv(f'{BASE}/sw_{code}.csv')
        df['日期'] = pd.to_datetime(df['日期'])
        frames[code] = df.set_index('日期')[['收盘']].rename(columns={'收盘': code})[code]
    return pd.DataFrame(frames).sort_index().dropna(how='all')

# ---------- 杠杆率状态 ----------
LEV = pd.read_csv(f'{BASE}/household_leverage.csv')
# 补2014基期（CNBS公开值），使2015年增量可算
if not (LEV['year'] == 2014).any():
    LEV = pd.concat([pd.DataFrame([{'year': 2014, 'household_leverage': 36.0, 'delta': np.nan}]), LEV],
                    ignore_index=True).sort_values('year')
    LEV['delta'] = LEV['household_leverage'].diff().round(1)
    LEV.to_csv(f'{BASE}/household_leverage.csv', index=False)
LEV['avail'] = pd.to_datetime(LEV['year'].astype(int).map(lambda y: f'{int(y)+1}-03-31'))  # CNBS次年Q1发布，保守
LEV = LEV.dropna(subset=['delta'])

def lev_state(d):
    """d日最新可得杠杆年增量状态。返回 (is_on, latest_avail)"""
    sub = LEV[LEV['avail'] <= d]
    if len(sub) == 0:
        return None, None  # 回测起点前无数据（不会发生：2016起2015增量已可得）
    row = sub.iloc[-1]
    return bool(row['delta'] >= 2.0), row['avail']

# ---------- 双Regime引擎 ----------
def run_v2(params, buy_mode='and3', use_lev=True, use_ext_nt=False, verbose=False):
    """
    buy_mode: 'and3'(三条件AND) | 'no_nt' | 'no_liq' | 'no_pol' | 'vote2'
    use_lev: 是否启用Regime2(消费吃药+杠杆)
    """
    px = load_prices2()
    pol, liq, nt = load_events()
    if use_ext_nt:
        nt2 = pd.read_csv(f'{BASE}/national_team_events_ext.csv')
        nt2 = nt2[nt2['date'].str.match(r'\d{4}-\d{2}-\d{2}')]
        nt2['date'] = pd.to_datetime(nt2['date'])
        nt = pd.concat([nt, nt2]).drop_duplicates(subset=['date','event']).sort_values('date')
    fin = load_financials()
    dates = px.index[(px.index >= '2016-01-01') & (px.index <= '2026-09-30')]
    policy_pool, maturity_tl, mature_at, sig = build_signals(dates, pol, liq, nt, fin, params)

    holdings = {}   # code -> dict(sh, bd, bp, regime, via_pool)
    cash = 1.0
    nav_series, trades = [], []
    pending_buys = []   # (code, signal_date, regime)
    pending_sells = []  # (code, reason, signal_date)
    pending_clear_all = None
    last_avail_seen = {code: None for code in GROWTH}
    last_lev_avail = None
    date_list = list(dates)

    def r1_entry(code, d, row):
        if buy_mode == 'and3':
            return row['liq_open'] and row['nt_open'] and d in policy_pool.get(code, set())
        if buy_mode == 'no_nt':
            return row['liq_open'] and d in policy_pool.get(code, set())
        if buy_mode == 'no_liq':
            return row['nt_open'] and d in policy_pool.get(code, set())
        if buy_mode == 'no_pol':
            return row['liq_open'] and row['nt_open']
        if buy_mode == 'vote2':
            c = sum([d in policy_pool.get(code, set()), bool(row['liq_open']), bool(row['nt_open'])])
            return c >= 2
        return False

    for d in date_list:
        row = sig.loc[d]
        # ---- 1. 执行T+1挂单 ----
        if pending_clear_all is not None and d > pending_clear_all:
            for code, h in holdings.items():
                price = px.at[d, code]
                if pd.notna(price):
                    cash += h['sh'] * price * (1 - params['fee_rate'])
                    trades.append(dict(date=d, code=code, name=IND_ALL[code], action='清仓',
                                       price=price, ret=price/h['bp']-1, hold_days=(d-h['bd']).days,
                                       reason='国家队卖出→全部清仓'))
            holdings, pending_clear_all = {}, None
        for code, sd, regime in list(pending_buys):
            if d > sd and code not in holdings and len(holdings) < params['max_positions']:
                price = px.at[d, code]
                if pd.notna(price) and price > 0:
                    spend = min(cash, 1.0 / params['max_positions'])
                    if spend > 0.01:
                        sh = spend * (1 - params['fee_rate']) / price
                        holdings[code] = dict(sh=sh, bd=d, bp=price, regime=regime,
                                              via_pool=d in policy_pool.get(code, set()))
                        cash -= spend
                        if code in GROWTH:
                            last_avail_seen[code] = mature_at(code, d)[2]
                        if regime == 'R2':
                            last_lev_avail = lev_state(d)[1]
                        rsn = ('三信号共振(政策+流动性+国家队)' if buy_mode == 'and3' else
                               f'Regime1[{buy_mode}]') if regime == 'R1' else '消费吃药行情(居民杠杆上行)'
                        trades.append(dict(date=d, code=code, name=IND_ALL[code], action='买入',
                                           price=price, ret=None, hold_days=None, reason=rsn))
            pending_buys.remove((code, sd, regime))
        for code, reason, sd in list(pending_sells):
            if d > sd and code in holdings:
                h = holdings.pop(code)
                price = px.at[d, code]
                if pd.notna(price):
                    cash += h['sh'] * price * (1 - params['fee_rate'])
                    trades.append(dict(date=d, code=code, name=IND_ALL[code], action='卖出',
                                       price=price, ret=price/h['bp']-1, hold_days=(d-h['bd']).days,
                                       reason=reason))
            pending_sells.remove((code, reason, sd))

        # ---- 2. 收盘后信号 ----
        if row['nt_sell']:
            pending_clear_all = d
        # 盈利成熟（有财务数据的8行业）
        for code in list(holdings):
            if code in GROWTH:
                m, reason, latest = mature_at(code, d)
                if latest is not None and latest > (last_avail_seen[code] or pd.Timestamp.min):
                    last_avail_seen[code] = latest
                    if m:
                        pending_sells.append((code, f'盈利成熟: {reason}', d))
        # R1持仓退出: 池过期(30天宽限) 或 非池持仓共振过期
        for code, h in list(holdings.items()):
            if h['regime'] != 'R1':
                continue
            if h['via_pool']:
                if d not in policy_pool.get(code, set()):
                    recent = any((d - timedelta(days=k)) in policy_pool[code] for k in range(30))
                    if not recent:
                        pending_sells.append((code, '产业政策扶持期结束', d))
            else:
                res = row['liq_open'] and row['nt_open']
                if not res:
                    recent = False
                    for k in range(30):
                        dd = d - timedelta(days=k)
                        if dd in sig.index and sig.loc[dd, 'liq_open'] and sig.loc[dd, 'nt_open']:
                            recent = True
                            break
                    if not recent:
                        pending_sells.append((code, '共振窗口结束', d))
        # R2持仓退出: 杠杆状态新数据到达且转OFF
        lev_on, lev_avail = lev_state(d)
        if lev_avail is not None and lev_avail > (last_lev_avail or pd.Timestamp.min):
            was_on = (last_lev_avail is not None and lev_state(lev_avail - timedelta(days=1))[0]) or \
                     (last_lev_avail is None and True)
            last_lev_avail = lev_avail
            if not lev_on:
                for code, h in list(holdings.items()):
                    if h['regime'] == 'R2':
                        pending_sells.append((code, f'居民杠杆增量跌破阈值(平台期,{lev_avail.date()}可得)', d))
        # 买入信号
        for code in GROWTH:
            if r1_entry(code, d, row) and code not in holdings and len(holdings) + len(pending_buys) < params['max_positions'] \
               and not any(pb[0] == code for pb in pending_buys):
                pending_buys.append((code, d, 'R1'))
        if use_lev and lev_on:
            for code in CONS_POOL:
                if code not in holdings and len(holdings) + len(pending_buys) < params['max_positions'] \
                   and not any(pb[0] == code for pb in pending_buys):
                    pending_buys.append((code, d, 'R2'))

        # ---- 3. NAV ----
        v = cash
        for code, h in holdings.items():
            price = px.at[d, code]
            if pd.notna(price):
                v += h['sh'] * price
        nav_series.append((d, v))

    nav = pd.Series(dict(nav_series)).sort_index()
    return nav, pd.DataFrame(trades)

# ================= 实验矩阵 =================
if __name__ == '__main__':
    results = {}

    def run_and_record(name, **kw):
        nav, tr = run_v2(P, **kw)
        s = perf_stats(nav, name)
        results[name] = (nav, tr, s)
        print(f"{name:28s} 总收益{s['total']:7.1%} 年化{s['annual']:6.1%} 夏普{s['sharpe']:5.2f} 回撤{s['mdd']:7.1%} 交易{len(tr):3d}笔")
        return nav, tr

    print('=== 1. 条件优先级消融（仅Regime1，统一框架复跑）===')
    run_and_record('and3 三条件AND(基准)', buy_mode='and3', use_lev=False)
    run_and_record('no_nt 去国家队', buy_mode='no_nt', use_lev=False)
    run_and_record('no_liq 去流动性', buy_mode='no_liq', use_lev=False)
    run_and_record('no_pol 去产业政策', buy_mode='no_pol', use_lev=False)
    run_and_record('vote2 三选二投票', buy_mode='vote2', use_lev=False)

    print('\n=== 2. 双Regime（消费吃药+杠杆率）===')
    run_and_record('R1and3 + 杠杆消费', buy_mode='and3', use_lev=True)
    run_and_record('R1and3 + 杠杆 + 大基金', buy_mode='and3', use_lev=True, use_ext_nt=True)

    print('\n=== 3. 最优组合探索 ===')
    run_and_record('R1no_liq + 杠杆 + 大基金', buy_mode='no_liq', use_lev=True, use_ext_nt=True)
    run_and_record('R1vote2 + 杠杆 + 大基金', buy_mode='vote2', use_lev=True, use_ext_nt=True)

    # 保存主结果
    for name in ['R1and3 + 杠杆消费', 'R1and3 + 杠杆 + 大基金', 'R1vote2 + 杠杆 + 大基金']:
        nav, tr, s = results[name]
        safe = name.replace(' ', '_').replace('+', 'plus').replace('/', '_')
        nav.to_frame('nav').to_csv(f'{OUT}/nav_v2_{safe}.csv')
        tr.to_csv(f'{OUT}/trades_v2_{safe}.csv', index=False)

    # 汇总表
    rows = [(k, v[2]['total'], v[2]['annual'], v[2]['sharpe'], v[2]['mdd'], len(v[1])) for k, v in results.items()]
    pd.DataFrame(rows, columns=['配置','总收益','年化','夏普','最大回撤','交易笔数']).to_csv(
        f'{OUT}/v2_experiments.csv', index=False)
    print('\n结果已保存 output/v2_experiments.csv')
