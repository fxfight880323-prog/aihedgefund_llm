#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A股融资市场逻辑回测引擎
========================
策略（用户逻辑，不可更改）：
  买入三条件：1.产业扶持政策 2.流动性支持政策 3.国家队入金行动
  卖出：行业盈利兑现+增速减缓（成长股变周期股）；国家队卖出→立即全部清仓
四项铁律：数据对齐 / 无未来数据（T+1执行+披露日对齐）/ 样本外验证 / 逻辑可溯源
"""
import pandas as pd
import numpy as np
from datetime import timedelta
import json, os

BASE = '/Users/seanf/WorkBuddy/A股好难/data'

# ---------------- 参数 ----------------
P = dict(
    policy_valid_days=365,      # 产业政策有效期（天）
    liquidity_window=90,        # 流动性事件后窗口（天）
    nt_window=120,              # 国家队入金信号有效期（天）
    profit_threshold=50.0,      # "开始大规模盈利"阈值（同比%）
    roe_fall_pct=2.0,           # ROE从峰值回落阈值（pct）
    max_positions=5,            # 最大同时持有行业数
    fee_rate=0.0,               # 费率（指数直算=0；敏感性测试用0.1%）
)

# ---------------- 数据加载 ----------------
INDUSTRIES = {
    '801080': '电子', '801750': '计算机', '801770': '通信', '801730': '电力设备',
    '801150': '医药生物', '801890': '机械设备', '801740': '国防军工', '801880': '汽车',
}

def load_prices():
    """申万行业指数收盘价矩阵（统一交易日对齐=数据对齐铁律）"""
    frames = {}
    for code in INDUSTRIES:
        df = pd.read_csv(f'{BASE}/sw_{code}.csv')
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.set_index('日期')[['收盘']].rename(columns={'收盘': code})
        frames[code] = df[code]
    px = pd.DataFrame(frames).sort_index()
    # 剔除全部缺失日（非共同交易日）
    px = px.dropna(how='all')
    # 个别行业2014-02起才有数据：2016起回测，均满足
    return px

def load_events():
    """信号事件表（全部用公布日，T+1执行——无未来数据铁律）"""
    # 1. 产业政策（手工整理的公开史实）
    pol = pd.read_csv(f'{BASE}/industry_policy_events.csv')
    pol['date'] = pd.to_datetime(pol['date'])
    # 2. 流动性：官方RRR公布日（akshare官方表，已交叉验证）+ LPR降息（双源一致）+ 证监会事件
    rrr = pd.read_csv(f'{BASE}/rrr.csv')
    rrr['date'] = pd.to_datetime(rrr['公布时间'], format='%Y年%m月%d日')
    rrr = rrr[(rrr['date'] >= '2015-06-01')].copy()
    rrr['type'] = '降准'
    rrr['strength'] = np.where(rrr['大型金融机构-调整幅度'].abs() >= 0.5, '强', '中')

    lpr = pd.read_csv(f'{BASE}/lpr_akshare.csv')
    lpr['date'] = pd.to_datetime(lpr['TRADE_DATE'].astype(str))
    lpr = lpr.sort_values('date').reset_index(drop=True)
    lpr['prev1y'] = lpr['LPR1Y'].shift(1)
    lpr['prev5y'] = lpr['LPR5Y'].shift(1)
    cut = lpr[(lpr['LPR1Y'] < lpr['prev1y']) | (lpr['LPR5Y'] < lpr['prev5y'])].copy()
    cut['type'] = '降息'
    cut['chg1y'] = (cut['LPR1Y'] - cut['prev1y']).abs()
    cut['chg5y'] = (cut['LPR5Y'] - cut['prev5y']).abs()
    cut['strength'] = np.where((cut['chg1y'] >= 0.2) | (cut['chg5y'] >= 0.2), '强', '中')

    liq_man = pd.read_csv(f'{BASE}/liquidity_events.csv')
    liq_man['date'] = pd.to_datetime(liq_man['date'])
    csrc = liq_man[liq_man['type'] == '证监会'][['date', 'event', 'type', 'strength']]

    liq = pd.concat([
        rrr[['date', 'type', 'strength']].assign(event='央行降准(官方RRR表)'),
        cut[['date', 'type', 'strength']].assign(event='LPR降息(双源验证)'),
        csrc[['date', 'event', 'type', 'strength']],
    ]).sort_values('date').reset_index(drop=True)

    # 3. 国家队（公告事件表，ETF成交量已验证2023-10-23等关键日期）
    nt = pd.read_csv(f'{BASE}/national_team_events.csv')
    nt = nt[nt['date'].str.match(r'\d{4}-\d{2}-\d{2}')]  # 过滤区间说明行
    nt['date'] = pd.to_datetime(nt['date'])
    return pol, liq, nt

def load_financials():
    """行业财务（neodata，双频率）→ 卖出信号评估表。
    披露日对齐（保守无未来数据）：半年报最晚当年8-31可得；年报最晚次年4-30可得。"""
    fin = pd.read_csv(f'{BASE}/industry_financials.csv')
    # avail_date: Q2→当年8-31; Q4→次年4-30
    fin['avail_date'] = fin.apply(
        lambda r: pd.to_datetime(f"{int(r['year'])}-08-31") if r['half'] == 'Q2'
        else pd.to_datetime(f"{int(r['year'])+1}-04-30"), axis=1)
    fin['np_yoy'] = pd.to_numeric(fin['np_yoy'], errors='coerce')
    fin['roe'] = pd.to_numeric(fin['roe'], errors='coerce')
    return fin

# ---------------- 信号构建 ----------------
def build_signals(dates, pol, liq, nt, fin, params):
    """对每个交易日，生成三个买入窗口状态 + 卖出信号"""
    idx = pd.Series(dates)
    sig = pd.DataFrame(index=idx)

    # A. 产业政策池（行业→在池日期集合）
    policy_pool = {code: set() for code in INDUSTRIES}
    for _, e in pol.iterrows():
        inds = str(e['industries']).split('|')
        strength = e['strength']
        valid = params['policy_valid_days'] if strength == '强' else int(params['policy_valid_days'] * 0.5)
        for d in pd.date_range(e['date'], e['date'] + timedelta(days=valid)):
            for name in inds:
                if name in INDUSTRIES.values():
                    code = [c for c, n in INDUSTRIES.items() if n == name][0]
                    policy_pool[code].add(d)
    # 回测起点的历史政策也需计入（2016-01前的近一年事件：大基金一期2014-09强事件有效期到2015-09已过；
    # 中国制造2025 2015-05强事件有效期到2016-05——正确包含）

    # B. 流动性窗口
    liq_days = set()
    for _, e in liq.iterrows():
        win = params['liquidity_window'] if e['strength'] == '强' else int(params['liquidity_window'] * 0.6)
        for d in pd.date_range(e['date'], e['date'] + timedelta(days=int(win))):
            liq_days.add(d)

    # C. 国家队窗口 + 卖出日
    nt_days = set()
    nt_sell_days = set()
    for _, e in nt.iterrows():
        if e['action'] == '买入':
            for d in pd.date_range(e['date'], e['date'] + timedelta(days=params['nt_window'])):
                nt_days.add(d)
        elif e['action'] == '卖出':
            nt_sell_days.add(e['date'])

    sig['liq_open'] = [d in liq_days for d in dates]
    sig['nt_open'] = [d in nt_days for d in dates]
    sig['nt_sell'] = [d in nt_sell_days for d in dates]

    # D. 行业盈利成熟状态时间线（双频率：Q2@8-31 / Q4@次年4-30）
    # 语义（状态型，非事件型）：
    #   mature=True 的行业 → 不可买入；持有的行业在"新披露到达"时若转mature → 卖出
    # 规则（用户逻辑：公司开始盈利、盈利增速减缓=卖出）：
    #   触发1: 上期同比增速>阈值(开始大规模盈利) 且 本期增速 < 上期（增速减缓）
    #   触发2: 盈利转负（产业周期结束）
    #   触发3: ROE从3期峰值回落超过 roe_fall_pct（成长股变周期股）
    # 比较序列：按avail_date排序的全部期（Q2/Q4混合），同比增速直接可比（均为同比动能）
    maturity_tl = {code: [] for code in INDUSTRIES}  # [(avail_date, is_mature, reason)]
    for code in INDUSTRIES:
        f = fin[fin['index_code'] == f'{code}.SI'].sort_values('avail_date').reset_index(drop=True)
        for i in range(len(f)):
            cur = f.iloc[i]
            reasons = []
            if i >= 1:
                prev = f.iloc[i-1]
                # np_yoy跨频率可比（均为同比增速）；ROE仅同频率比较（半年/全年口径不同）
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
            maturity_tl[code].append((cur['avail_date'], len(reasons) > 0, '; '.join(reasons)))

    def mature_at(code, d):
        """d日（含）之前最新披露下的成熟状态；同时返回新到披露的评估"""
        tl = maturity_tl[code]
        cur_mature, cur_reason, latest_avail = False, '', None
        for ad, m, r in tl:
            if ad <= d:
                cur_mature, cur_reason, latest_avail = m, r, ad
        return cur_mature, cur_reason, latest_avail

    return policy_pool, maturity_tl, mature_at, sig

# ---------------- 回测引擎 ----------------
def run_backtest(params, verbose=True):
    px = load_prices()
    pol, liq, nt = load_events()
    fin = load_financials()
    dates = px.index[(px.index >= '2016-01-01') & (px.index <= '2026-09-30')]
    policy_pool, maturity_tl, mature_at, sig = build_signals(dates, pol, liq, nt, fin, params)

    # 状态
    holdings = {}      # code -> (shares, buy_date, buy_price)
    cash = 1.0
    nav_series = []
    trades = []        # 交易明细
    pending_buys = []  # (code, signal_date) T+1执行
    pending_sells = [] # (code, reason, signal_date)
    pending_clear_all = None
    last_avail_seen = {code: None for code in INDUSTRIES}  # 每个行业已评估过的最新披露日

    date_list = list(dates)
    pos_dates = {d: i for i, d in enumerate(date_list)}

    def next_td(d):
        i = pos_dates.get(d)
        if i is None:
            i = np.searchsorted([x.value for x in date_list], d.value)
            i = min(i, len(date_list)-1)
        return date_list[min(i+1, len(date_list)-1)] if i+1 < len(date_list) else date_list[-1]

    for d in date_list:
        # ---- 1. 执行昨日挂单（T+1收盘成交）----
        if pending_clear_all is not None and d >= pending_clear_all:
            for code, (sh, bd, bp) in holdings.items():
                price = px.at[d, code]
                if pd.notna(price):
                    cash += sh * price * (1 - params['fee_rate'])
                    trades.append(dict(date=d, code=code, name=INDUSTRIES[code], action='清仓',
                                       price=price, ret=price/bp-1, hold_days=(d-bd).days,
                                       reason='国家队卖出→全部清仓'))
            holdings = {}
            pending_clear_all = None
        for code, sd in list(pending_buys):
            if d > sd and code not in holdings and len(holdings) < params['max_positions']:
                price = px.at[d, code]
                if pd.notna(price) and price > 0:
                    alloc = 1.0 / params['max_positions']
                    spend = min(cash, alloc)
                    if spend > 0.01:
                        sh = spend * (1 - params['fee_rate']) / price
                        holdings[code] = (sh, d, price)
                        cash -= spend
                        # 建仓时锁定当前披露基线：只对持有期内的新披露反应（买入不看盈利=用户逻辑）
                        last_avail_seen[code] = mature_at(code, d)[2]
                        trades.append(dict(date=d, code=code, name=INDUSTRIES[code], action='买入',
                                           price=price, ret=None, hold_days=None,
                                           reason=f'三信号共振(政策+流动性+国家队)'))
            pending_buys.remove((code, sd))
        for code, reason, sd in list(pending_sells):
            if d > sd and code in holdings:
                sh, bd, bp = holdings.pop(code)
                price = px.at[d, code]
                if pd.notna(price):
                    cash += sh * price * (1 - params['fee_rate'])
                    trades.append(dict(date=d, code=code, name=INDUSTRIES[code], action='卖出',
                                       price=price, ret=price/bp-1, hold_days=(d-bd).days, reason=reason))
            pending_sells.remove((code, reason, sd))

        # ---- 2. 收盘后生成明日信号（无未来数据：今日收盘信息→明日收盘执行）----
        row = sig.loc[d]
        # 2a. 国家队卖出 → 全清仓
        if row['nt_sell']:
            pending_clear_all = d
        # 2b. 行业卖出：持有行业 + 新披露到达 + 最新状态mature → 卖出（事件型触发）
        for code in list(holdings):
            m, reason, latest = mature_at(code, d)
            if latest is not None and latest > (last_avail_seen[code] or pd.Timestamp.min):
                last_avail_seen[code] = latest
                if m:
                    pending_sells.append((code, f'盈利成熟: {reason}', d))
            # 政策池过期 → 卖出（连续30天不在池）
            if code in holdings and d not in policy_pool[code]:
                recent = any((d - timedelta(days=k)) in policy_pool[code] for k in range(30))
                if not recent:
                    pending_sells.append((code, '产业政策扶持期结束', d))
        # 2c. 买入信号（三条件共振；买入不看盈利=用户逻辑"不能看盈利"）
        if row['liq_open'] and row['nt_open']:
            for code in INDUSTRIES:
                if (d in policy_pool[code] and code not in holdings
                        and len(holdings) + len(pending_buys) < params['max_positions']
                        and not any(pb[0] == code for pb in pending_buys)):
                    pending_buys.append((code, d))

        # ---- 3. 计算NAV ----
        v = cash
        for code, (sh, bd, bp) in holdings.items():
            price = px.at[d, code]
            if pd.notna(price):
                v += sh * price
        nav_series.append((d, v))

    nav = pd.Series(dict(nav_series)).sort_index()
    trades_df = pd.DataFrame(trades)
    return nav, trades_df, px

# ---------------- 绩效统计 ----------------
def perf_stats(nav, label=''):
    ret = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    total = nav.iloc[-1] / nav.iloc[0] - 1
    annual = (nav.iloc[-1] / nav.iloc[0]) ** (1/years) - 1
    sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
    dd = (nav / nav.cummax() - 1).min()
    return dict(label=label, total=total, annual=annual, sharpe=sharpe, mdd=dd, years=years)

def yearly_returns(nav, label):
    yr = nav.resample('YE').last()
    first = nav.resample('YE').first()
    r = (yr / first.shift(1).fillna(nav.iloc[0]) - 1)
    return r

if __name__ == '__main__':
    nav, trades, px = run_backtest(P)
    print(f'回测区间: {nav.index[0].date()} ~ {nav.index[-1].date()}')
    print(f'交易笔数: {len(trades)}')
    stats = perf_stats(nav, '策略(融资市场逻辑)')
    print(f"总收益: {stats['total']:.1%} | 年化: {stats['annual']:.1%} | 夏普: {stats['sharpe']:.2f} | 最大回撤: {stats['mdd']:.1%}")

    # 基准
    hs = pd.read_csv(f'{BASE}/hs300.csv'); hs['date'] = pd.to_datetime(hs['date'])
    hs = hs.set_index('date')['close'].reindex(nav.index).ffill()
    zz = pd.read_csv(f'{BASE}/zz500.csv'); zz['date'] = pd.to_datetime(zz['date'])
    zz = zz.set_index('date')['close'].reindex(nav.index).ffill()
    for bench, name in [(hs, '沪深300'), (zz, '中证500')]:
        b = bench / bench.iloc[0]
        s = perf_stats(b, name)
        print(f"{name}: 总收益 {s['total']:.1%} | 年化 {s['annual']:.1%} | 夏普 {s['sharpe']:.2f} | 最大回撤 {s['mdd']:.1%}")

    # 保存
    nav.to_frame('nav').to_csv(f'{BASE}/../output/nav_main.csv')
    trades.to_csv(f'{BASE}/../output/trades_main.csv', index=False)
    print('\n=== 交易明细 ===')
    for _, t in trades.iterrows():
        rr = f"{t['ret']:.1%}" if pd.notna(t['ret']) else '-'
        hd = f"{t['hold_days']}天" if pd.notna(t['hold_days']) else '-'
        print(f"{t['date'].date()} {t['action']:2s} {t['name']:4s} @ {t['price']:9.2f} 收益{rr:>7s} 持有{hd:>7s} | {t['reason']}")
