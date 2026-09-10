# -*- coding: utf-8 -*-
"""RAG 检索 CLI 与 Python API。

python -m rag.query "银行净息差" --as-of 2026-08-26 --top 5
"""
from __future__ import annotations

import argparse
import json
import sys

from rag import indexer


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="投研知识库时点语义检索")
    ap.add_argument("query", help="自然语言查询")
    ap.add_argument("--as-of", default=None, help="时点过滤 YYYY-MM-DD(只取 ≤ 该日发布的研报)")
    ap.add_argument("--source", default=None, choices=["juzi", "csc"], help="限定数据源")
    ap.add_argument("--industry", default=None, help="行业关键词过滤")
    ap.add_argument("--report-type", default=None, help="研报类型(深度/动态/简评/金工...)")
    ap.add_argument("--tickers", default=None, help="股票代码过滤, 逗号分隔")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--mode", default="vector", choices=["hybrid", "vector", "bm25"],
                    help="检索模式: vector 纯语义(默认) | hybrid 向量+BM25 融合 | bm25 纯关键词")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args(argv)

    results = indexer.search(
        a.query, as_of=a.as_of, source=a.source, industry=a.industry,
        report_type=a.report_type,
        tickers=[t.strip() for t in a.tickers.split(",")] if a.tickers else None,
        top_k=a.top, mode=a.mode)

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0
    if not results:
        print("无结果(检查是否已 ingest/index)")
        return 1
    print(f"🔍 query='{a.query}' mode={a.mode}" +
          (f" as_of={a.as_of}" if a.as_of else "") +
          f" → {len(results)} 条\n" + "-" * 88)
    for i, r in enumerate(results, 1):
        meta = f"{r['institution'] or '?'} · {r['publish_date'] or '?'} · {r['report_type'] or '?'}"
        if r["industry"]:
            meta += f" · {r['industry']}"
        print(f"[{i}] score={r['score']:.4f}  《{r['title'] or '无标题'}》  {meta}")
        print(f"    theme={r['theme']} source={r['source']} doc={r['doc_id']}")
        text = (r["chunk_text"] or "").replace("\n", " ")
        print(f"    {text[:220]}{'...' if len(text) > 220 else ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
