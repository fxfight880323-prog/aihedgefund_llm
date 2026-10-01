#!/usr/bin/env python
"""数据拉取：申万行业指数行情 + RRR + LPR + 沪深300基准（tushare解析）"""
import akshare as ak
import pandas as pd
import json, time, os

BASE = '/Users/seanf/WorkBuddy/A股好难/data'
os.makedirs(BASE, exist_ok=True)

# 1. 申万一级行业指数行情（8个核心成长行业）
industries = {
    '801080': '电子', '801750': '计算机', '801770': '通信', '801730': '电力设备',
    '801150': '医药生物', '801890': '机械设备', '801740': '国防军工', '801880': '汽车',
}
for code, name in industries.items():
    out = f'{BASE}/sw_{code}.csv'
    if os.path.exists(out):
        print(f'skip {name} (cached)')
        continue
    try:
        hist = ak.index_hist_sw(symbol=code, period='day')
        hist.to_csv(out, index=False)
        print(f'{name} {code}: {len(hist)}行 {hist["日期"].min()}~{hist["日期"].max()}')
    except Exception as e:
        print(f'{name} FAIL: {repr(e)[:150]}')
    time.sleep(1)

# 2. 存款准备金率（RRR）
try:
    rrr = ak.macro_china_reserve_requirement_ratio()
    rrr.to_csv(f'{BASE}/rrr.csv', index=False)
    print('\nRRR:', rrr.shape, list(rrr.columns))
    print(rrr.tail(10).to_string())
except Exception as e:
    print('RRR FAIL:', repr(e)[:200])

# 3. LPR（akshare源，交叉验证tushare）
try:
    lpr = ak.macro_china_lpr()
    lpr.to_csv(f'{BASE}/lpr_akshare.csv', index=False)
    print('\nLPR(akshare):', lpr.shape, list(lpr.columns))
except Exception as e:
    print('LPR FAIL:', repr(e)[:200])

# 4. 沪深300 + 中证500 基准（akshare）
for sym, fn in [('sh000300', 'hs300'), ('sh000905', 'zz500')]:
    out = f'{BASE}/{fn}.csv'
    if os.path.exists(out): continue
    try:
        df = ak.stock_zh_index_daily(symbol=sym)
        df.to_csv(out, index=False)
        print(f'\n{fn}: {len(df)}行 {df["date"].min()}~{df["date"].max()}')
    except Exception as e:
        print(f'{fn} FAIL:', repr(e)[:150])

# 5. 沪深300 ETF行情（510300，验证汇金增持期的量价）
try:
    etf = ak.fund_etf_hist_em(symbol="510300", period="daily",
                              start_date="20120101", end_date="20260930", adjust="")
    etf.to_csv(f'{BASE}/etf_510300.csv', index=False)
    print(f'\nETF510300: {len(etf)}行 {etf["日期"].min()}~{etf["日期"].max()}')
except Exception as e:
    print('ETF FAIL:', repr(e)[:200])
print('\n完成')
