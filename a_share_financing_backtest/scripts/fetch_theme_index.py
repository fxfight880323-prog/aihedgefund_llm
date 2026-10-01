#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下载主题指数历史并保存为data/theme_*.csv，同时输出深度报告"""
import akshare as ak
import pandas as pd
import warnings, json
warnings.filterwarnings('ignore')

# 最终主题池（代码, 保存名, 中文名, 对应SW一级行业[用于财务成熟度信号], Regime归属）
THEMES = [
    # R1 产业扶持主题
    ('H30184', 'theme_semi',    '中证全指半导体', '电子'),
    ('931151', 'theme_pv',      '光伏产业',       '电力设备'),
    ('930713', 'theme_ai',      'CS人工智能',     '计算机'),
    ('399976', 'theme_nev',     'CS新能车',       '电力设备'),
    ('399967', 'theme_mil',     '中证军工',       '国防军工'),
    ('930715', 'theme_5g',      '5G通信',         '通信'),
    ('931079', 'theme_semi_mat','半导体材料',     '电子'),
    # R2 消费吃药主题
    ('399997', 'theme_baijiu',  '中证白酒',       '食品饮料'),
    ('000932', 'theme_cons',    '中证消费',       '家用电器'),
    ('000933', 'theme_pharma',  '中证医药',       '医药生物'),
    ('930772', 'theme_med',     'CS医疗',         '医药生物'),
]

manifest = []
for code, fname, cname, sw, in THEMES:
    try:
        df = ak.stock_zh_index_hist_csindex(symbol=code, start_date="20150101", end_date="20260930")
        df = df.rename(columns={'日期':'date','收盘':'close','开盘':'open','最高':'high','最低':'low'})
        df['date'] = pd.to_datetime(df['date'])
        df = df[['date','close']].copy()
        df.to_csv(f'/Users/seanf/WorkBuddy/A股好难/data/{fname}.csv', index=False)
        n = len(df); s = df['date'].iloc[0].date(); e = df['date'].iloc[-1].date()
        # 2016-01-04前是否有数据（回测起点）
        early_ok = pd.Timestamp(s) <= pd.Timestamp('2016-01-04')
        print(f'{code:<8}{cname:<10} {s} ~ {e}  {n}天  起点前数据:{"✅" if early_ok else "⚠️ 从"+str(s)+"起"}')
        manifest.append({'code':code,'file':fname,'name':cname,'sw':sw,'start':str(s),'end':str(e),'days':n,'early':bool(early_ok)})
    except Exception as ex:
        print(f'{code:<8}{cname:<10} ❌ {str(ex)[:60]}')

json.dump(manifest, open('/tmp/theme_manifest.json','w'), ensure_ascii=False, indent=1)
print(f'\n已保存{len(manifest)}个主题指数到data/theme_*.csv')
