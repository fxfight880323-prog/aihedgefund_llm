#!/usr/bin/env python3
"""深度阅读关键基金经理纪要PDF"""
import os
import json
import pymupdf

pdf_dir = r"D:\24年以来纪要"

# 选择关键基金经理的PDF文件 - 用名字关键词匹配
target_managers = [
    "孟杰",
    "苗琦", 
    "陈金伟",
    "乔海英",
    "毕凯",
    "姚艺",
    "江琦",
    "高付",
    "王明旭",
    "冯自力",
]

results = {}
all_files = os.listdir(pdf_dir)

for name in target_managers:
    # 找到匹配的PDF
    matched = [f for f in all_files if name in f]
    if not matched:
        print(f"找不到 {name} 的文件")
        continue
    
    filepath = os.path.join(pdf_dir, matched[0])
    
    try:
        doc = pymupdf.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        # 提取关键段落
        key_sections = []
        for line in text.split('\n'):
            line = line.strip()
            if len(line) > 20 and len(line) < 500:
                score = 0
                keywords = ['投资', '选股', '策略', '框架', '理念', '方法', '逻辑', '风格', '配置', '仓位', '行业', '个股', '估值', '盈利', '景气', '周期', '成长', '价值', '红利']
                for kw in keywords:
                    if kw in line:
                        score += 1
                if score >= 3:
                    key_sections.append(line)
        
        results[name] = {
            'filename': matched[0],
            'text_length': len(text),
            'key_sections': key_sections[:15],
            'full_text': text[:8000]
        }
        print(f"\n=== {name} ({matched[0]}) ===")
        for s in key_sections[:8]:
            print(f"  {s[:120]}...")
    except Exception as e:
        print(f"Error reading {name}: {e}")

# 保存
output = r"D:\workspace\ai_fund_framework\key_manager_notes.json"
with open(output, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n\n结果保存到: {output}")
