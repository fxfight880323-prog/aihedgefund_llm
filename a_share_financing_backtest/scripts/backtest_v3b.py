#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测V3b：V3审计修正版
======================
审计发现的修正：
1. [身份错误] 930715 实为"CS朝阳88"(超预期策略指数) → 剔除（非产业主题）
2. [身份错误] 930772 实为"中证A100两倍杠杆指数"(杠杆宽基) → 剔除，替补399989中证医疗(发布2014-10-31)
3. [名称+映射错误] 931079 实为"中证5G通信主题" → 映射从电子改为通信（信号跟随通信政策池+通信财务）
4. [新增] 931743 半导体材料设备主题（基日2018-12-28，约束2019年起可投）
5. [可投资性加固] 全部标的加 avail_from 约束（发布日/基日孰晚），发布前不可买入
发布日期核实（官网factsheet）：H30184=2013-07-15, 931151=2019-04-22, 930713=2015-07-31,
931079=2019-04-25, 399976=2014-11-28, 399967=2013-09-16, 399997=2015-01-21,
000932/000933=2013-07-15(800系列), 399989=2014-10-31, 931743基日2018-12-28
"""
import sys
sys.path.insert(0, '/Users/seanf/WorkBuddy/A股好难/scripts')
import pandas as pd
import numpy as np
from datetime import timedelta
from backtest import load_events, load_financials, perf_stats, P

BASE = '/Users/seanf/WorkBuddy/A股好难/data'
OUT = '/Users/seanf/WorkBuddy/A股好难/output'

# ---------- 修正后主题池：code → (名称, SW行业, avail_from发布/基日约束) ----------
THEMES_R1 = {
    'theme_semi':     ('全指半导体',       '电子',     '2013-07-15'),
    'theme_semi_eq':  ('半导体材料设备',   '电子',     '2018-12-28'),  # 新增931743
    'theme_ai':       ('CS人工智能',       '计算机',   '2015-07-31'),
    'theme_5g':       ('5G通信',           '通信',     '2019-04-25'),  # 修正：931079真身
    'theme_pv':       ('光伏产业',         '电力设备', '2019-04-22'),
    'theme_nev':      ('CS新能车',         '电力设备', '2014-11-28'),
    'theme_mil':      ('中证军工',         '国防军工', '2013-09-16'),
}
THEMES_R2 = {
    'theme_baijiu':   ('中证白酒',         '食品饮料', '2015-01-21'),
    'theme_cons':     ('中证主要消费',     '家用电器', '2013-07-15'),
    'theme_pharma':   ('中证医药卫生',     '医药生物', '2013-07-15'),
    'theme_med':      ('中证医疗',         '医药生物', '2014-10-31'),  # 替换A100两倍
}
ALL_THEMES = {**THEMES_R1, **THEMES_R2}
GROWTH = list(THEMES_R1.keys())
CONS_POOL = list(THEMES_R2.keys())
AVAIL_FROM = {tc: pd.Timestamp(v[2]) for tc, v in ALL_THEMES.items()}

SW2THEME = {}
for tc, (tname, sw, _) in ALL_THEMES.items():
    SW2THEME.setdefault(sw, []).append(tc)

def load_theme_prices():
    frames = {}
    for tc in ALL_THEMES:
        df = pd.read_csv(f'{BASE}/{tc}.csv')
        df['date'] = pd.to_datetime(df['date'])
        frames[tc] = df.set_index('date')['close'].rename(tc)
    px = pd.DataFrame(frames).sort_index()
    sw_dates = pd.read_csv(f'{BASE}/sw_801080.csv')
    sw_dates['日期'] = pd.to_datetime(sw_dates['日期'])
    cal = pd.DatetimeIndex(sw_dates['日期'])
    cal = cal[(cal >= px.index.min()) & (cal <= px.index.max())]
    px = px.reindex(cal).ffill()
    return px

LEV = pd.read_csv(f'{BASE}/household_leverage.csv')
LEV['avail'] = pd.to_datetime(LEV['year'].astype(int).map(lambda y: f'{int(y)+1}-03-31'))
LEV = LEV.dropna(subset=['delta'])

def lev_state(d, threshold=2.0):
    sub = LEV[LEV['avail'] <= d]
    if len(sub) == 0:
        return None, None
    row = sub.iloc[-1]
    return bool(row['delta'] >= threshold), row['avail']

def build_signals_v3b(dates, pol, liq, nt, fin, params):
    policy_pool = {tc: set() for tc in ALL_THEMES}
    for _, e in pol.iterrows():
        inds = str(e['industries']).split('|')
        valid = params['policy_valid_days'] if e['strength'] == '强' else int(params['policy_valid_days'] * 0.5)
        for d in pd.date_range(e['date'], e['date'] + timedelta(days=valid)):
            for name in inds:
                for tc in SW2THEME.get(name, []):
                    policy_pool[tc].add(d)
    liq_days, nt_days, nt_sell_days = set(), set(), set()
    for _, e in liq.iterrows():
        win = params['liquidity_window'] if e['strength'] == '强' else int(params['liquidity_window'] * 0.6)
        for d in pd.date_range(e['date'], e['date'] + timedelta(days=int(win))):
            liq_days.add(d)
    for _, e in nt.iterrows():
        if e['action'] == '买入':
            for d in pd.date_range(e['date'], e['date'] + timedelta(days=params['nt_window'])):
                nt_days.add(d)
        elif e['action'] == '卖出':
            nt_sell_days.add(e['date'])
    sig = pd.DataFrame(index=pd.Series(dates))
    sig['liq_open'] = [d in liq_days for d in dates]
    sig['nt_open'] = [d in nt_days for d in dates]
    sig['nt_sell'] = [d in nt_sell_days for d in dates]

    sw_codes = {'电子':'801080','计算机':'801750','通信':'801770','电力设备':'801730',
                '医药生物':'801150','机械设备':'801890','国防军工':'801740','汽车':'801880',
                '食品饮料':'801120','家用电器':'801110'}
    maturity = {}
    for sw_name, code in sw_codes.items():
        f = fin[fin['index_code'] == f'{code}.SI'].sort_values('avail_date').reset_index(drop=True)
        tl = []
        for i in range(len(f)):
            cur = f.iloc[i]
            reasons = []
            if i >= 1:
                prev = f.iloc[i-1]
                if pd.notna(cur['np_yoy']) and pd.notna(prev['np_yoy']):
                    if prev['np_yoy'] > params['profit_threshold'] and cur['np_yoy'] < prev['np_yoy']:
                        reasons.append(f"盈利兑现后增速减缓({prev['np_yoy']:.0f}%→{cur['np_yoy']:.0f}%,{cur['half']})")
                    elif cur['np_yoy'] < 0 and prev['np_yoy'] > 0:
                        reasons.append(f"盈利转负({prev['np_yoy']:.0f}%→{cur['np_yoy']:.0f}%,{cur['half']})")
                same_half = f[(f['half'] == cur['half'])]
                pos = same_half.index[same_half['avail_date'] == cur['avail_date']]
                if len(pos) and pos[0] >= 2:
                    roe_window = same_half.iloc[pos[0]-2:pos[0]+1]['roe']
                    if pd.notna(cur['roe']) and roe_window.max() - cur['roe'] >= params['roe_fall_pct']:
                        reasons.append(f"ROE峰值回落({roe_window.max():.1f}%→{cur['roe']:.1f}%,{cur['half']})")
            tl.append((cur['avail_date'], len(reasons) > 0, '; '.join(reasons)))
        maturity[sw_name] = tl

    def mature_at(theme_code, d):
        sw_name = ALL_THEMES[theme_code][1]
        tl = maturity[sw_name]
        cm, cr, la = False, '', None
        for ad, m, r in tl:
            if ad <= d:
                cm, cr, la = m, r, ad
        return cm, cr, la

    return policy_pool, mature_at, sig

def run_v3b(params, buy_mode='and3', use_lev=True, use_ext_nt=False, lev_threshold=2.0):
    px = load_theme_prices()
    pol, liq, nt = load_events()
    if use_ext_nt:
        nt2 = pd.read_csv(f'{BASE}/national_team_events_ext.csv')
        nt2 = nt2[nt2['date'].str.match(r'\d{4}-\d{2}-\d{2}')]
        nt2['date'] = pd.to_datetime(nt2['date'])
        nt = pd.concat([nt, nt2]).drop_duplicates(subset=['date','event']).sort_values('date')
    fin = load_financials()
    dates = px.index[(px.index >= '2016-01-01') & (px.index <= '2026-09-30')]
    policy_pool, mature_at, sig = build_signals_v3b(dates, pol, liq, nt, fin, params)

    holdings = {}
    cash = 1.0
    nav_series, trades = [], []
    pending_buys, pending_sells = [], []
    pending_clear_all = None
    last_avail_seen = {tc: None for tc in GROWTH}
    last_lev_avail = None
    date_list = list(dates)

    def r1_entry(tc, d, row):
        if d < AVAIL_FROM[tc]:   # 可投资性约束：发布/基日前不交易
            return False
        if buy_mode == 'and3':
            return row['liq_open'] and row['nt_open'] and d in policy_pool.get(tc, set())
        if buy_mode == 'no_nt':
            return row['liq_open'] and d in policy_pool.get(tc, set())
        if buy_mode == 'no_liq':
            return row['nt_open'] and d in policy_pool.get(tc, set())
        if buy_mode == 'no_pol':
            return row['liq_open'] and row['nt_open']
        if buy_mode == 'vote2':
            c = sum([d in policy_pool.get(tc, set()), bool(row['liq_open']), bool(row['nt_open'])])
            return c >= 2
        return False

    for d in date_list:
        row = sig.loc[d]
        if pending_clear_all is not None and d > pending_clear_all:
            for tc, h in holdings.items():
                price = px.at[d, tc]
                if pd.notna(price):
                    cash += h['sh'] * price * (1 - params['fee_rate'])
                    trades.append(dict(date=d, code=tc, name=ALL_THEMES[tc][0], action='清仓',
                                       price=price, ret=price/h['bp']-1, hold_days=(d-h['bd']).days,
                                       reason='国家队卖出→全部清仓'))
            holdings, pending_clear_all = {}, None
        for tc, sd, regime in list(pending_buys):
            if d > sd and tc not in holdings and len(holdings) < params['max_positions']:
                price = px.at[d, tc]
                if pd.notna(price) and price > 0:
                    spend = min(cash, 1.0 / params['max_positions'])
                    if spend > 0.01:
                        sh = spend * (1 - params['fee_rate']) / price
                        holdings[tc] = dict(sh=sh, bd=d, bp=price, regime=regime,
                                            via_pool=d in policy_pool.get(tc, set()))
                        cash -= spend
                        if tc in GROWTH:
                            last_avail_seen[tc] = mature_at(tc, d)[2]
                        if regime == 'R2':
                            last_lev_avail = lev_state(d, lev_threshold)[1]
                        rsn = ('三信号共振(政策+流动性+国家队)' if buy_mode == 'and3' else
                               f'Regime1[{buy_mode}]') if regime == 'R1' else '消费吃药行情(居民杠杆上行)'
                        trades.append(dict(date=d, code=tc, name=ALL_THEMES[tc][0], action='买入',
                                           price=price, ret=None, hold_days=None, reason=rsn))
            pending_buys.remove((tc, sd, regime))
        for tc, reason, sd in list(pending_sells):
            if d > sd and tc in holdings:
                h = holdings.pop(tc)
                price = px.at[d, tc]
                if pd.notna(price):
                    cash += h['sh'] * price * (1 - params['fee_rate'])
                    trades.append(dict(date=d, code=tc, name=ALL_THEMES[tc][0], action='卖出',
                                       price=price, ret=price/h['bp']-1, hold_days=(d-h['bd']).days,
                                       reason=reason))
            pending_sells.remove((tc, reason, sd))

        if row['nt_sell']:
            pending_clear_all = d
        for tc in list(holdings):
            if tc in GROWTH:
                m, reason, latest = mature_at(tc, d)
                if latest is not None and latest > (last_avail_seen[tc] or pd.Timestamp.min):
                    last_avail_seen[tc] = latest
                    if m:
                        pending_sells.append((tc, f'盈利成熟: {reason}', d))
        for tc, h in list(holdings.items()):
            if h['regime'] != 'R1':
                continue
            if h['via_pool']:
                if d not in policy_pool.get(tc, set()):
                    recent = any((d - timedelta(days=k)) in policy_pool[tc] for k in range(30))
                    if not recent:
                        pending_sells.append((tc, '产业政策扶持期结束', d))
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
                        pending_sells.append((tc, '共振窗口结束', d))
        lev_on, lev_avail = lev_state(d, lev_threshold)
        if lev_avail is not None and lev_avail > (last_lev_avail or pd.Timestamp.min):
            last_lev_avail = lev_avail
            if not lev_on:
                for tc, h in list(holdings.items()):
                    if h['regime'] == 'R2':
                        pending_sells.append((tc, f'居民杠杆增量跌破阈值(平台期,{lev_avail.date()}可得)', d))
        for tc in GROWTH:
            if r1_entry(tc, d, row) and tc not in holdings and len(holdings) + len(pending_buys) < params['max_positions'] \
               and not any(pb[0] == tc for pb in pending_buys):
                pending_buys.append((tc, d, 'R1'))
        if use_lev and lev_on:
            for tc in CONS_POOL:
                if d >= AVAIL_FROM[tc] and tc not in holdings and len(holdings) + len(pending_buys) < params['max_positions'] \
                   and not any(pb[0] == tc for pb in pending_buys):
                    pending_buys.append((tc, d, 'R2'))

        v = cash
        for tc, h in holdings.items():
            price = px.at[d, tc]
            if pd.notna(price):
                v += h['sh'] * price
        nav_series.append((d, v))

    nav = pd.Series(dict(nav_series)).sort_index()
    return nav, pd.DataFrame(trades)

if __name__ == '__main__':
    results = {}

    def run_and_record(name, **kw):
        nav, tr = run_v3b(P, **kw)
        s = perf_stats(nav, name)
        results[name] = (nav, tr, s)
        print(f"{name:32s} 总收益{s['total']:7.1%} 年化{s['annual']:6.1%} 夏普{s['sharpe']:5.2f} 回撤{s['mdd']:7.1%} 交易{len(tr):3d}笔")
        return nav, tr

    print('=== V3b审计修正版：核心配置 ===')
    run_and_record('R1and3 + 杠杆消费', buy_mode='and3', use_lev=True)
    run_and_record('R1and3 + 杠杆 + 大基金', buy_mode='and3', use_lev=True, use_ext_nt=True)
    run_and_record('R1vote2 + 杠杆 + 大基金', buy_mode='vote2', use_lev=True, use_ext_nt=True)

    print('\n=== 审计C：杠杆阈值敏感性 ===')
    for th, lbl in [(1.5, '阈值1.5pct'), (2.5, '阈值2.5pct')]:
        run_and_record(f'R1and3 + 杠杆 + 大基金 [{lbl}]', buy_mode='and3', use_lev=True, use_ext_nt=True, lev_threshold=th)

    for name in ['R1and3 + 杠杆 + 大基金', 'R1vote2 + 杠杆 + 大基金']:
        nav, tr, s = results[name]
        safe = name.replace(' ', '_').replace('+', 'plus').replace('/', '_')
        nav.to_frame('nav').to_csv(f'{OUT}/nav_v3b_{safe}.csv')
        tr.to_csv(f'{OUT}/trades_v3b_{safe}.csv', index=False)

    rows = [(k, v[2]['total'], v[2]['annual'], v[2]['sharpe'], v[2]['mdd'], len(v[1])) for k, v in results.items()]
    pd.DataFrame(rows, columns=['配置','总收益','年化','夏普','最大回撤','交易笔数']).to_csv(
        f'{OUT}/v3b_experiments.csv', index=False)
    print('\n结果已保存 output/v3b_experiments.csv')
