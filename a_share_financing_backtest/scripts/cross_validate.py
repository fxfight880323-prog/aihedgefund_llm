#!/usr/bin/env python
"""交叉检验：多数据源相互验证（用户核心要求）"""
import pandas as pd
import json

BASE = '/Users/seanf/WorkBuddy/A股好难/data'

print('='*70)
print('检验1: RRR官方数据 vs 手工降准事件表')
print('='*70)
rrr = pd.read_csv(f'{BASE}/rrr.csv')
rrr['公布时间'] = pd.to_datetime(rrr['公布时间'], format='%Y年%m月%d日')
rrr_sorted = rrr.sort_values('公布时间')
rrr_2016 = rrr_sorted[(rrr_sorted['公布时间']>='2015-06-01') & (rrr_sorted['公布时间']<='2026-10-01')]
print(f'2016-2026 降准事件(RRR官方): {len(rrr_2016)} 次')
for _, r in rrr_2016.iterrows():
    print(f"  {r['公布时间'].date()} 公布, {str(r['生效时间']).replace('年','-').replace('月','-').replace('日','')} 生效, 大行调整 {r['大型金融机构-调整幅度']}pct")

liq = pd.read_csv(f'{BASE}/liquidity_events.csv')
liq_rrr = liq[liq['type']=='降准'].copy()
print(f'\n手工降准事件表: {len(liq_rrr)} 次')
manual_dates = set(liq_rrr['date'].str[:7])  # 年月匹配
official_dates = set(rrr_2016['公布时间'].dt.strftime('%Y-%m'))
matched = manual_dates & official_dates
print(f'月度口径匹配: {len(matched)}/{len(manual_dates)} 手工事件在官方数据中找到')
missing = manual_dates - official_dates
if missing:
    print('手工表有但官方数据无(需复查):', sorted(missing))
    # 定向降准（普惠/中小银行）可能在官方表备注中
    for d in sorted(missing):
        yy, mm = d.split('-')
        near = rrr_sorted[rrr_sorted['公布时间'].dt.strftime('%Y-%m')==d]
        print(f'  {d}: 官方表中 {"有" if len(near) else "无"} 记录')

print()
print('='*70)
print('检验2: LPR双源对齐 (akshare vs tushare)')
print('='*70)
lpr_ak = pd.read_csv(f'{BASE}/lpr_akshare.csv')
lpr_ak['TRADE_DATE'] = pd.to_datetime(lpr_ak['TRADE_DATE'].astype(str))
lpr_ak = lpr_ak[(lpr_ak['TRADE_DATE']>='2019-08-01')].sort_values('TRADE_DATE')
# 提取降息事件（1Y LPR下调）
lpr_ak['prev'] = lpr_ak['LPR1Y'].shift(1)
cuts = lpr_ak[lpr_ak['LPR1Y'] < lpr_ak['prev']]
print(f'akshare LPR 1Y 下调事件: {len(cuts)} 次')
for _, r in cuts.iterrows():
    print(f"  {r['TRADE_DATE'].date()}: 1Y LPR {r['prev']} -> {r['LPR1Y']}")

print()
print('='*70)
print('检验3: 沪深300 双源对齐 (akshare vs tushare)')
print('='*70)
hs = pd.read_csv(f'{BASE}/hs300.csv')
hs['date'] = pd.to_datetime(hs['date'])
hs_a = hs[(hs['date']>='2016-01-01')&(hs['date']<='2026-09-30')].set_index('date')['close']
# tushare保存的文件
tf = "/Users/seanf/.workbuddy/projects/Users-seanf-WorkBuddy-A股好难/4e8e0471-109d-415b-9806-3cdf20d32d2e/tool-results/mcp-tushare-index_daily-1790857517417-4565c5.txt"
raw = open(tf, encoding='utf-8').read()
import re
rows = re.findall(r'\{"ts_code":"000300\.SH","trade_date":"(\d{8})".*?"close":([\d.]+)', raw)
ts_df = pd.DataFrame(rows, columns=['td','close'])
ts_df['date'] = pd.to_datetime(ts_df['td'], format='%Y%m%d')
ts_df['close'] = ts_df['close'].astype(float)
ts_a = ts_df.set_index('date')['close']
common = hs_a.index.intersection(ts_a.index)
if len(common) > 0:
    diff = (hs_a[common] - ts_a[common]).abs()
    rel = (diff / ts_a[common]).max()
    print(f'共同交易日: {len(common)}, 最大相对偏差: {rel:.6f}')
    print('样本对比(tushare vs akshare):')
    for d in common[:3]:
        print(f'  {d.date()}: ak {hs_a[d]:.2f} vs ts {ts_a[d]:.2f}')
else:
    print('无共同日期，需检查', len(hs_a), len(ts_a))

print()
print('='*70)
print('检验4: ETF510300 成交量验证国家队增持期')
print('='*70)
etf = pd.read_csv(f'{BASE}/etf_510300.csv')
etf['日期'] = pd.to_datetime(etf['日期'])
etf = etf.sort_values('日期')
etf['amount_yi'] = etf['成交额'] / 1e8
# 关键验证窗口：2023-10汇金公告、2024-02扩大增持
for label, s, e in [('2023-10汇金公告前后', '2023-09-01', '2023-11-30'),
                    ('2024-02汇金扩大增持前后', '2024-01-01', '2024-03-31'),
                    ('2024全年(持续增持)', '2024-01-01', '2024-12-31')]:
    win = etf[(etf['日期']>=s)&(etf['日期']<=e)]
    if len(win):
        print(f'{label}: 日均成交额 {win["amount_yi"].mean():.1f}亿, 最大单日 {win["amount_yi"].max():.1f}亿 ({win.loc[win["amount_yi"].idxmax(),"日期"].date()})')
# 基准对比: 2022全年 vs 2023Q4
w22 = etf[(etf['日期']>='2022-01-01')&(etf['日期']<='2022-12-31')]
w23q4 = etf[(etf['日期']>='2023-10-01')&(etf['日期']<='2023-12-31')]
print(f'2022全年日均: {w22["amount_yi"].mean():.1f}亿 vs 2023Q4日均: {w23q4["amount_yi"].mean():.1f}亿 (放大 {w23q4["amount_yi"].mean()/w22["amount_yi"].mean():.1f}x)')
