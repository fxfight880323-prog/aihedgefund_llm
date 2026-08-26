#!/usr/bin/env python3
"""批量提取基金经理调研纪要PDF中的关键信息 - 改进版"""
import os
import re
import json
import pymupdf

pdf_dir = r"D:\24年以来纪要"
files = os.listdir(pdf_dir)
pdf_files = sorted([os.path.join(pdf_dir, f) for f in files if f.endswith('.pdf')])
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
        
        # 改进：从文件名提取 - 匹配中文姓名
        # 格式: 【天天基金机构通】机构名姓名调研纪要日期.pdf
        # 姓名通常在"调研纪要"之前
        match = re.search(r'【天天基金机构通】(.+?)调研纪要(\d{8})', filename)
        if match:
            middle = match.group(1)
            date_str = match.group(2)
            # 从中间部分分离机构名和姓名
            # 姓名通常是2-4个中文字，在"基金"或"管理"之后
            # 尝试匹配：机构名(可能包含基金/资产/管理/投资等) + 姓名
            org_name_match = re.match(r'(.+?[基金|资产|管理|投资|证券|公司|信|银|华|安|南|国|中|东|西|北|上|下]+)([\u4e00-\u9fa5]{2,4})', middle)
            if org_name_match:
                org = org_name_match.group(1)
                name = org_name_match.group(2)
            else:
                # 备选：直接取前几个字作为机构，后几个字作为姓名
                # 通常机构名较长
                if len(middle) > 6:
                    org = middle[:-2] if len(middle) > 8 else middle[:-2]
                    name = middle[-2:]
                else:
                    org = middle
                    name = ""
        else:
            org = "未知"
            name = "未知"
            date_str = ""
        
        # 从内容提取基金代码 - 更广泛的模式
        fund_codes = re.findall(r'\b(\d{6}\.(?:OF|SH|SZ))\b', text[:10000])
        fund_names = re.findall(r'([\u4e00-\u9fa5]{2,10}(?:混合|股票|债券|指数|ETF|LOF|QDII)[\w\u4e00-\u9fa5]{0,20})', text[:10000])
        
        # 找投资风格关键词（扩大范围）
        keywords = []
        kw_list = ['价值', '成长', '均衡', '周期', '量化', '主题', '行业轮动', '自上而下', '自下而上', 
                   'GARP', '低估值', '高景气', '景气度', '龙头', '中小盘', '大盘', '核心资产',
                   '左侧', '右侧', '逆向', '趋势', '动量', '反转', '深度价值', '景气成长',
                   '宏观', '中观', '微观', '护城河', '现金流', '股息', '红利', '质量', '景气',
                   '估值', '盈利', 'ROE', 'PB', 'PE', 'PEG', 'DCF', '博弈', '事件驱动',
                   '可转债', '固收+', '绝对收益', '相对收益', '偏债', '偏股', '灵活配置',
                   '医药', '消费', '科技', '新能源', '半导体', 'AI', '人工智能', '高端制造',
                   '出海', '高股息', '制造业', 'TMT', '通信', '电子', '机械',
                   '化工', '有色', '资源', '金融', '地产', '汽车', '电力', '公用事业',
                   '港股', '美股', 'A股', '沪深', '中证']
        text_head = text[:10000]
        for kw in kw_list:
            if kw in text_head:
                keywords.append(kw)
        keywords = list(set(keywords))
        
        # 找核心投资理念（更精确的提取）
        # 找包含"投资"、"策略"、"选股"等关键词的较长句子
        core_ideas = []
        sentences = re.split(r'[。！？\n]', text[:15000])
        for s in sentences:
            s = s.strip()
            if len(s) > 30 and len(s) < 500:
                score = 0
                if '投资' in s: score += 2
                if '选股' in s: score += 2
                if '策略' in s: score += 2
                if '框架' in s: score += 2
                if '理念' in s: score += 2
                if '方法' in s: score += 1
                if '逻辑' in s: score += 1
                if '风格' in s: score += 1
                if '配置' in s: score += 1
                if '仓位' in s: score += 1
                if '行业' in s: score += 1
                if '个股' in s: score += 1
                if '估值' in s: score += 1
                if '盈利' in s: score += 1
                if score >= 3:
                    core_ideas.append((score, s))
        
        core_ideas.sort(reverse=True)
        core_ideas = [s for _, s in core_ideas[:8]]
        
        # 找持仓/重仓股信息
        holdings = re.findall(r'([\u4e00-\u9fa5]{2,8})\s*(?:持仓|重仓|持股|买入|增持|看好)', text[:10000])
        
        results.append({
            'filename': filename,
            'org': org,
            'name': name,
            'date': date_str,
            'text_length': len(text),
            'fund_codes': list(set(fund_codes))[:10],
            'fund_names': list(set(fund_names))[:10],
            'keywords': keywords,
            'core_ideas': core_ideas,
            'holdings_mentioned': list(set(holdings))[:10],
            'text_preview': text[:5000]
        })
        
    except Exception as e:
        print(f"Error processing {os.path.basename(pdf_path)}: {e}")
        results.append({
            'filename': os.path.basename(pdf_path),
            'error': str(e)
        })

# 保存结果
output_path = r"D:\workspace\ai_fund_framework\fund_manager_notes_v2.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n提取完成，结果保存到: {output_path}")
print(f"\n=== 基金经理摘要 ===")
for r in results:
    if 'org' in r and not r.get('error'):
        funds_str = ', '.join(r['fund_codes'][:3]) if r['fund_codes'] else '无'
        print(f"\n【{r['org']} - {r['name']}】({r['date']})")
        print(f"  基金代码: {funds_str}")
        print(f"  关键词: {', '.join(r['keywords'][:10])}")
        if r['core_ideas']:
            print(f"  核心理念: {r['core_ideas'][0][:100]}...")
