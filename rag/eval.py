# -*- coding: utf-8 -*-
"""检索质量评估: hit@5 / MRR, 三模式对比(vector / bm25 / hybrid)。

python run.py rag eval   (或 python -m rag.eval)
标注原则: expect 是期望命中报告的标题特征子串(库内唯一可辨识)。
"""
from __future__ import annotations

from rag import indexer

# (query, expect_title_substring) —— 覆盖持仓个股/行业/金工/宏观/全文PDF报告
EVAL_SET: list[tuple[str, str]] = [
    # --- 行业综述与深度(含 PDF 全文) ---
    ("上市银行一季报净息差环比变化", "银行业2026年一季报综述"),
    ("美元流动性对9月资产配置的影响", "关键在美元流动性"),
    ("保险业上半年业绩表现", "保险业业绩综述"),
    ("证券行业投资业务与科创股权", "证券业业绩综述"),
    ("银行理财权益转型和产品拐点", "银行理财"),
    # --- 持仓个股简评 ---
    ("宁波银行最新业绩怎么样", "宁波银行"),
    ("江苏银行营收和资产质量", "江苏银行"),
    ("招商银行财富管理和营收", "招商银行"),
    ("成都银行息差和拨备", "成都银行"),
    ("常熟银行不良率", "常熟银行"),
    ("渝农商行利润增速", "渝农商行"),
    ("中银香港股东回报规划", "中银香港"),
    ("中国平安高股息低估值", "中国平安"),
    ("中金公司投行和自营业务", "中金公司"),
    # --- 金工方法论 ---
    ("量价因子和基本面因子统一挖掘框架", "量价X基本面因子挖掘统一框架"),
    ("美债利率怎么择时", "美债择时框架"),
    ("行业轮动的估值比较视角", "估值比较视角下的行业轮动策略"),
    ("普林格周期当前阶段资产配置", "普林格周期"),
    ("最近哪些风格因子表现好", "因子跟踪"),
    ("分钟级因子模型怎么做", "分钟因子模型"),
    ("隔夜和日内收益的领先滞后关系", "隔夜-日内异象因子"),
    ("黄金白银的择时策略", "黄金白银择时"),
    ("筹码分布怎么构建因子", "筹码分布因子"),
    ("基金仓位结构对后市的指示", "基金仓位结构"),
    ("分析师预期修正选股", "分析师预期"),
    ("豆粕怎么择时", "豆粕择时"),
    ("ETF 资金流择时轮动", "ETF投资全景"),
    ("多维度择时体系", "多维度择时体系"),
    ("FOF 增强策略 基金经理拥挤度", "多因子选基"),
    ("跨境配置欧日市场", "跨境投资全景洞察"),
    # --- 宏观/策略/其他行业 ---
    ("焦煤焦炭动力煤价格走势", "煤炭开采"),
    ("政治局会议下半年政策定调", "政治局会议"),
    ("房地产销售量价数据点评", "统计局房地产数据"),
    ("北向资金新阶段", "北向资金"),
    ("央行流动性投放收紧了吗", "央行短期流动性投放"),
    ("煤炭发电容量电价机制", "容量电价"),
    ("船舶发动机和燃气轮机订单", "中国动力"),
    ("香港交易所一季度业绩", "香港交易所"),
    ("盐津铺子电商和大单品", "盐津铺子"),
]

MODES = ["vector", "vector+rr", "hybrid", "bm25"]
TOP_K = 5


def _search(query: str, mode: str) -> list[dict]:
    """按模式检索: vector+rr = 纯向量召回 + bge-reranker 精排。"""
    kwargs: dict = {"top_k": TOP_K}
    if mode == "vector+rr":
        kwargs.update({"mode": "vector", "rerank": True})
    else:
        kwargs.update({"mode": mode, "rerank": False})
    return indexer.search(query, **kwargs)


def _hit_rank(results: list[dict], expect: str) -> int:
    """返回首个命中排名(1-based); 0=未命中。"""
    for i, r in enumerate(results, 1):
        if expect in (r.get("title") or ""):
            return i
    return 0


def run_eval() -> dict:
    table: dict[str, dict] = {m: {"hits": 0, "mrr": 0.0} for m in MODES}
    for query, expect in EVAL_SET:
        line = f"Q: {query[:22]:<24} →"
        for mode in MODES:
            rows = _search(query, mode)
            rank = _hit_rank(rows, expect)
            if rank:
                table[mode]["hits"] += 1
                table[mode]["mrr"] += 1.0 / rank
            line += f"  {mode}={'#'+str(rank) if rank else '✗':<10}"
        print(line)
    n = len(EVAL_SET)
    print("\n" + "=" * 70)
    print(f"{'模式':<10}{'hit@5':<10}{'MRR':<10}")
    print("-" * 40)
    summary = {}
    for mode in MODES:
        t = table[mode]
        hit = t["hits"] / n
        mrr = t["mrr"] / n
        summary[mode] = {"hit@5": round(hit, 3), "MRR": round(mrr, 3)}
        print(f"{mode:<10}{t['hits']}/{n} ({hit:.0%})  {mrr:.3f}")
    return summary


if __name__ == "__main__":
    run_eval()
