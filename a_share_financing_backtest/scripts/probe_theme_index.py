#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探测候选主题指数的数据可达性与历史深度（中证/国证主题指数）"""
import akshare as ak
import warnings
warnings.filterwarnings('ignore')

# 候选：代码, 名称, 需要覆盖的起始年份, 对应SW行业
CANDIDATES = [
    # R1 产业扶持主题
    ('980017', '国证芯片', '电子'),
    ('H30184', '中证全指半导体', '电子'),
    ('931151', '光伏产业', '电力设备'),
    ('930713', 'CS人工智能', '计算机'),
    ('399976', '新能源车', '电力设备'),
    ('399967', '中证军工', '国防军工'),
    ('931079', '半导体材料', '电子'),
    ('930715', '5G通信', '通信'),
    # R2 消费吃药主题
    ('399997', '中证白酒', '食品饮料'),
    ('000932', '中证消费', '家电'),
    ('000933', '中证医药', '医药生物'),
    ('930772', 'CS医疗', '医药生物'),
]

print(f"{'代码':<8}{'名称':<12}{'源':<10}{'起始':<12}{'终止':<12}{'天数':<7}{'状态'}")
results = []
for code, name, sw in CANDIDATES:
    ok = False
    # 尝试1: akshare中证指数官方接口
    try:
        df = ak.stock_zh_index_hist_csindex(symbol=code, start_date="20140101", end_date="20260930")
        if df is not None and len(df) > 500:
            start, end = df['日期'].iloc[0], df['日期'].iloc[-1]
            print(f"{code:<8}{name:<12}{'csindex':<10}{start:<12}{end:<12}{len(df):<7}✅")
            results.append((code, name, sw, 'csindex', start, end, len(df)))
            ok = True
    except Exception as e:
        pass
    if ok:
        continue
    # 尝试2: 东财通用历史（index_zh_a_hist 支持部分中证/国证代码）
    try:
        df = ak.index_zh_a_hist(symbol=code, period="daily", start_date="20140101", end_date="20260930")
        if df is not None and len(df) > 500:
            start, end = str(df['日期'].iloc[0]), str(df['日期'].iloc[-1])
            print(f"{code:<8}{name:<12}{'东财':<10}{start:<12}{end:<12}{len(df):<7}✅")
            results.append((code, name, sw, 'em', start, end, len(df)))
            ok = True
    except Exception as e:
        print(f"{code:<8}{name:<12}{'-':<10}{'-':<12}{'-':<12}{'-':<7}❌ {str(e)[:50]}")

import json
with open('/tmp/theme_probe.json', 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print('\n探测完成，结果已存/tmp/theme_probe.json')
