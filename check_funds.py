import json
data=json.load(open(r'D:/workspace/ai_fund_framework/fund_manager_notes_v2.json','r',encoding='utf-8'))
# 统计有基金代码的
has_fund=[r for r in data if r.get('fund_codes')]
print(f'有基金代码的: {len(has_fund)}')
for r in has_fund:
    print(f"  {r['name']} ({r['org']}): {r['fund_codes']}")
