import json
d=json.load(open(r'D:/workspace/ai_fund_framework/fund_wind_data.json','r',encoding='utf-8'))
# 打印第一个基金经理的第一个基金的结果
print("=== 第一个基金经理 ===")
print(json.dumps(d[0], ensure_ascii=False, indent=2)[:5000])
