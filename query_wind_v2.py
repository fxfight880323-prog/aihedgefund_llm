#!/usr/bin/env python3
"""批量查询基金经理基金的业绩和持仓数据 - 修正版"""
import subprocess
import json
import os
import time

CLI_DIR = r"C:\Users\xfugm\AppData\Roaming\kimi-desktop\daimon-share\daimon\plugin-packages\wind-allskill\skills\wind-mcp-skill"

def wind_call(server_type, tool_name, params):
    """调用Wind CLI"""
    cmd = ['node', 'scripts/cli.mjs', 'call', server_type, tool_name, json.dumps(params, ensure_ascii=False)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding='utf-8', cwd=CLI_DIR)
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
        
        # 基金基本信息 - NL工具用question
        info = wind_call('fund_data', 'get_fund_info', {'question': f'{fund_code}基金档案'})
        time.sleep(0.5)
        
        # 基金业绩
        perf = wind_call('fund_data', 'get_fund_performance', {'question': f'{fund_code}近1年业绩排名'})
        time.sleep(0.5)
        
        # 基金重仓股
        holdings = wind_call('fund_data', 'get_fund_holdings', {'question': f'{fund_code}最新一期重仓股'})
        time.sleep(0.5)
        
        # 基金K线（近1年）
        kline = wind_call('fund_data', 'get_fund_kline', {
            'windcode': fund_code,
            'begin_date': '20250801',
            'end_date': '20260825',
            'period': '10'
        })
        time.sleep(0.5)
        
        fund_result = {
            'code': fund_code,
            'info': info,
            'performance': perf,
            'holdings': holdings,
            'kline': kline
        }
        fm_result['funds'].append(fund_result)
        
        # 打印关键信息
        if info and info.get('ok'):
            print(f"    info: OK")
        else:
            print(f"    info: {info.get('error', {}).get('code', 'ERR') if isinstance(info, dict) else 'ERR'}")
        
        if perf and perf.get('ok'):
            print(f"    perf: OK")
        else:
            print(f"    perf: {perf.get('error', {}).get('code', 'ERR') if isinstance(perf, dict) else 'ERR'}")
        
        if holdings and holdings.get('ok'):
            print(f"    holdings: OK")
        else:
            print(f"    holdings: {holdings.get('error', {}).get('code', 'ERR') if isinstance(holdings, dict) else 'ERR'}")
    
    all_results.append(fm_result)

# 保存结果
output_path = r"D:\workspace\ai_fund_framework\fund_wind_data_v2.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n\n所有结果保存到: {output_path}")
