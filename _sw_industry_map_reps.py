# -*- coding: utf-8 -*-
"""
建立「行业轮动因子值 -> 申万一级行业名」映射
用 westock data_profile 查代表股票的 industry 字段（申万一级行业），多数投票
"""
import json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'C:/Users/xfugm/.workbuddy/binaries/python/envs/default/Lib/site-packages')

from collections import defaultdict
import urllib.request

# westock MCP 通过 http 直连（找它的 endpoint）
# 但更简单：直接用之前已知的申万一级行业代码+名称，配合代表股票名称人工/程序化推断

d = json.load(open('_sw_industry_rotation_values.json', encoding='utf-8'))
recs = d['records']
byval = defaultdict(list)
for r in recs:
    byval[r['行业轮动']].append(r['ts_code'])

uniq = sorted(byval.keys(), reverse=True)

# 申万一级行业标准代码 -> 名称（从 westock data_sector list 拿到的 31 个）
SW1 = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁", "801050": "有色金属",
    "801080": "电子", "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务", "801230": "综合",
    "801710": "建筑材料", "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备", "801950": "煤炭",
    "801960": "石油石化", "801970": "环保", "801980": "美容护理",
}

print("共", len(uniq), "个唯一因子值")
print("需要确定每个值对应的申万一级行业")
print()
print("westock data_profile 会返回 industry 字段（申万一级），逐个查代表股票")
print()

# 输出每个值的前若干代表股票代码，供后续 data_profile 查询
reps = {}
for v in uniq:
    codes = byval[v]
    # 优先选 000/600/601/603 主板
    main = [c for c in codes if c[:3] in ('000','600','601','603','002')]
    rep_list = (main + codes)[:4]
    reps[v] = rep_list
    print(f'{v:+.4f}: {rep_list}')

# 保存
json.dump({'uniq_values': uniq, 'reps': reps}, open('_sw_industry_rotation_reps.json','w',encoding='utf-8'), ensure_ascii=False)
print()
print('已保存代表股票 _sw_industry_rotation_reps.json')
