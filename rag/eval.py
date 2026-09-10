# -*- coding: utf-8 -*-
"""检索质量评估: hit@5 / MRR, 三模式对比(vector / bm25 / hybrid)。

python run.py rag eval   (或 python -m rag.eval)
标注原则: expect 是期望命中报告的标题特征子串(库内唯一可辨识)。
"""
from __future__ import annotations

from rag import indexer

# (query, expect_title_substring) —— 覆盖持仓个股/行业/金工/宏观/全文PDF报告
EVAL_SET: list[tuple[str, str]] = [
    ("上市银行一季报净息差环比变化", "银行业2026年一季报综述"),
    ("美元流动性对9月资产配置的影响", "关键在美元流动性"),
    ("保险业上半年业绩表现", "保险业业绩综述"),
    ("证券行业投资业务与科创股权", "证券业业绩综述"),
    ("量价因子和基本面因子统一挖掘框架", "量价X基本面因子挖掘统一框架"),
    ("美债利率怎么择时", "美债择时框架"),
    ("行业轮动的估值比较视角", "估值比较视角下的行业轮动策略"),
    ("宁波银行最新业绩怎么样", "宁波银行"),
    ("普林格周期当前阶段资产配置", "普林格周期"),
    ("最近哪些风格因子表现好", "因子跟踪"),
    ("焦煤焦炭动力煤价格走势", "煤炭开采"),
    ("中金公司投行和自营业务", "中金公司"),
]

MODES = ["vector", "bm25", "hybrid"]
TOP_K = 5


def _hit_rank(results: list[dict], expect: str) -> int:
    """返回首个命中排名(1-based); 0=未命中。"""
    for i, r in enumerate(results, 1):
        if expect in (r.get("title") or ""):
            return i
    return 0


def run_eval() -> dict:
    table: dict[str, dict] = {m: {"hits": 0, "mrr": 0.0, "ranks": []} for m in MODES}
    for query, expect in EVAL_SET:
        line = f"Q: {query[:22]:<24} →"
        for mode in MODES:
            rows = indexer.search(query, top_k=TOP_K, mode=mode)
            rank = _hit_rank(rows, expect)
            table[mode]["ranks"].append(rank)
            if rank:
                table[mode]["hits"] += 1
                table[mode]["mrr"] += 1.0 / rank
            line += f"  {mode}={'#'+str(rank) if rank else '✗':<8}"
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
