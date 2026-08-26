#!/usr/bin/env python3
"""批量查询基金经理基金的业绩和持仓数据"""
import subprocess
import json
import os

CLI_PATH = r"C:\Users\xfugm\AppData\Roaming\kimi-desktop\daimon-share\daimon\plugin-packages\wind-allskill\skills\wind-mcp-skill\scripts\cli.mjs"

def wind_call(server_type, tool_name, params):
    """调用Wind CLI"""
    cmd = ['node', CLI_PATH, 'call', server_type, tool_name, json.dumps(params, ensure_ascii=False)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding='utf-8')
        output = result.stdout.strip()
        # 尝试解析JSON输出
        try:
            return json.loads(output)
        except:
            return {'raw': output, 'stderr': result.stderr.strip()}
    except Exception as e:
        return {'error': str(e)}

# 有基金代码的基金经理
fund_managers = [
    {'name': '陈金伟', 'org': '鹏华基金', 'funds': ['005812.OF', '020884.OF', '160611.SZ']},
    {'name': '孟杰', 'org': '宏利基金', 'funds': ['000828.OF', '162204.OF', '003501.OF']},
    {'name': '姚艺', 'org': '宝盈基金', 'funds': ['009223.OF', '008227.OF', '001487.OF']},
    {'name': '乔海英', 'org': '景顺长城', 'funds': ['011876.OF']},
    {'name': '高付', 'org': '申万菱信', 'funds': ['001148.OF', '001724.OF']},
    {'name': '苗琦', 'org': '申万菱信', 'funds': ['005009.OF']},
    {'name': '毕凯', 'org': '贝莱德', 'funds': ['018101.OF']},
    {'name': '陈颖', 'org': '泰信基金', 'funds': ['013072.OF']},
    {'name': '马晓东', 'org': '安信基金', 'funds': ['022299.OF']},
    {'name': '江琦', 'org': '东方红', 'funds': ['015052.OF']},
]

# 先查询每个基金的基本信息和业绩
all_results = []

for fm in fund_managers:
    print(f"\n=== 查询 {fm['name']} ({fm['org']}) ===")
    fm_result = {'name': fm['name'], 'org': fm['org'], 'funds': []}
    
    for fund_code in fm['funds']:
        print(f"  查询 {fund_code}...")
        
        # 基金基本信息
        info = wind_call('fund_data', 'get_fund_info', {'windcode': fund_code})
        
        # 基金净值（最近1年）
        nav = wind_call('fund_data', 'get_fund_nav', {
            'windcode': fund_code,
            'begin_date': '20250801',
            'end_date': '20260825'
        })
        
        # 基金业绩指标
        perf = wind_call('fund_data', 'get_fund_performance', {'windcode': fund_code})
        
        fund_result = {
            'code': fund_code,
            'info': info,
            'nav': nav,
            'performance': perf
        }
        fm_result['funds'].append(fund_result)
        
        # 打印关键信息
        if info and info.get('ok'):
            data = info.get('data', {})
            print(f"    基金名: {data.get('基金简称', 'N/A')}")
            print(f"    类型: {data.get('投资类型', 'N/A')}")
            print(f"    规模: {data.get('基金规模', 'N/A')}")
        
        if perf and perf.get('ok'):
            data = perf.get('data', {})
            print(f"    近1年收益: {data.get('近1年收益率', 'N/A')}")
            print(f"    近3年收益: {data.get('近3年收益率', 'N/A')}")
    
    all_results.append(fm_result)

# 保存结果
output_path = r"D:\workspace\ai_fund_framework\fund_wind_data.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n\n所有结果保存到: {output_path}")
