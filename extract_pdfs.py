#!/usr/bin/env python3
"""批量提取基金经理调研纪要PDF中的关键信息"""
import os
import re
import json

try:
    import pymupdf
except ImportError:
    print("Installing PyMuPDF...")
    os.system("python -m pip install pymupdf -q")
    import pymupdf

# PDF文件夹路径 - 使用环境变量或绝对路径
pdf_dir = r"D:\24年以来纪要"
if not os.path.exists(pdf_dir):
    # 尝试Unix风格路径
    pdf_dir = "/d/24年以来纪要"

print(f"目录: {pdf_dir}")
print(f"存在: {os.path.exists(pdf_dir)}")

files = os.listdir(pdf_dir)
pdf_files = [os.path.join(pdf_dir, f) for f in files if f.endswith('.pdf')]
pdf_files.sort()
print(f"共找到 {len(pdf_files)} 个PDF文件")

# 提取信息
results = []

for pdf_path in pdf_files:
    try:
        doc = pymupdf.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        filename = os.path.basename(pdf_path)
        
        # 尝试从文件名提取机构名和姓名
        match = re.search(r'【天天基金机构通】(.+?)(\w+)调研纪要(\d{8})', filename)
        if match:
            org = match.group(1)
            name = match.group(2)
            date_str = match.group(3)
        else:
            org = "未知"
            name = "未知"
            date_str = ""
        
        # 从内容提取基金代码
        fund_pattern = re.findall(r'(\d{6}\.OF|\d{6}\.SH|\d{6}\.SZ)', text[:5000])
        
        # 找投资风格关键词
        keywords = []
        kw_list = ['价值', '成长', '均衡', '周期', '量化', '主题', '行业轮动', '自上而下', '自下而上', 
                   'GARP', '低估值', '高景气', '景气度', '龙头', '中小盘', '大盘', '核心资产',
                   '左侧', '右侧', '逆向', '趋势', '动量', '反转', '深度价值', '景气成长',
                   '宏观', '中观', '微观', '护城河', '现金流', '股息', '红利', '质量', '景气',
                   '估值', '盈利', 'ROE', 'PB', 'PE', 'PEG', 'DCF', '博弈', '事件驱动',
                   '可转债', '固收+', '绝对收益', '相对收益', '偏债', '偏股', '灵活配置',
                   '医药', '消费', '科技', '新能源', '半导体', 'AI', '人工智能', '高端制造',
                   '出海', '红利', '高股息', '制造业', 'TMT', '通信', '电子', '机械',
                   '化工', '有色', '资源', '金融', '地产', '汽车', '电力', '公用事业']
        text_head = text[:8000]
        for kw in kw_list:
            if kw in text_head:
                keywords.append(kw)
        
        # 找投资理念相关段落
        idea_paras = []
        for line in text.split('\n'):
            line = line.strip()
            if len(line) > 15 and any(kw in line for kw in ['投资', '选股', '策略', '框架', '理念', '逻辑', '方法']):
                if len(line) < 300 and len(line) > 30:
                    idea_paras.append(line)
        idea_paras = idea_paras[:5]
        
        results.append({
            'filename': filename,
            'org': org,
            'name': name,
            'date': date_str,
            'text_length': len(text),
            'funds_found': list(set(fund_pattern))[:10],
            'keywords': keywords,
            'idea_snippets': idea_paras,
            'first_3000_chars': text[:3000]
        })
        
    except Exception as e:
        print(f"Error processing {os.path.basename(pdf_path)}: {e}")
        results.append({
            'filename': os.path.basename(pdf_path),
            'error': str(e)
        })

# 保存结果
output_path = r"D:\workspace\ai_fund_framework\fund_manager_notes_extracted.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n提取完成，结果保存到: {output_path}")
print(f"\n基金经理列表:")
for r in results:
    if 'org' in r:
        funds_str = ', '.join(r['funds_found'][:3]) if r['funds_found'] else '无'
        print(f"  {r['org']} - {r['name']} ({r['date']}) - 基金: {funds_str} - 关键词: {', '.join(r['keywords'][:8])}")
