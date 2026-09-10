# -*- coding: utf-8 -*-
"""BM25(中文 2-gram) —— 混合检索的关键词臂。

RAG-Knowledge hybrid retrieval 原则: 向量召回语义近邻, BM25 召回字面精确命中
(代码/简称/数字, 如 "1Q26 净息差 1.51%"), RRF 融合。

零依赖, 纯 Python; 语料(千级 chunk)全量重算 <100ms, 用指纹缓存增量。
"""
from __future__ import annotations

import math
import re
from collections import Counter

import sqlite3

from rag import config

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """中文按字 2-gram, 英文数字按词, 全小写。"""
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer((text or "").lower()):
        tok = m.group(0)
        if tok[0].isascii():  # 英文/数字词
            tokens.append(tok)
        else:  # 中文字符 → 与前一个中文字符组成 2-gram
            tokens.append(tok)
            if tokens and len(tokens) >= 2 and _is_cjk(tokens[-2]) and tokens[-2] != tok:
                pass  # 下面统一处理
    # 上面逻辑混乱, 重写: 先切 run, 再 2-gram
    tokens = []
    runs = [(m.group(0), m.start()) for m in _TOKEN_RE.finditer((text or "").lower())]
    merged = []
    for tok, _ in runs:
        merged.append(tok)
    # 合并连续中文字符为 2-gram
    out: list[str] = []
    i = 0
    while i < len(merged):
        if len(merged[i]) == 1 and not merged[i].isascii():
            j = i
            zh = ""
            while j < len(merged) and len(merged[j]) == 1 and not merged[j].isascii():
                zh += merged[j]
                j += 1
            if len(zh) == 1:
                out.append(zh)
            else:
                out.extend(zh[k:k + 2] for k in range(len(zh) - 1))
            i = j
        else:
            out.append(merged[i])
            i += 1
    return out


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


class BM25:
    def __init__(self, docs_tokens: list[list[str]]):
        self.n = len(docs_tokens)
        self.doc_lens = [len(t) for t in docs_tokens]
        self.avgdl = sum(self.doc_lens) / max(self.n, 1)
        self.tfs: list[Counter] = [Counter(t) for t in docs_tokens]
        df: Counter = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        self.idf = {w: math.log((self.n - c + 0.5) / (c + 0.5) + 1)
                    for w, c in df.items()}
        self.k1, self.b = 1.5, 0.75

    def score(self, query_tokens: list[str], idx: int) -> float:
        tf, dl = self.tfs[idx], self.doc_lens[idx]
        s = 0.0
        for w in query_tokens:
            if w not in tf:
                continue
            idf = self.idf.get(w, 0.0)
            s += idf * tf[w] * (self.k1 + 1) / (tf[w] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def search(self, query: str, top_k: int = 50) -> list[tuple[int, float]]:
        """返回 [(doc 行号, score)] 降序。行号对应建库时传入顺序。"""
        if self.n == 0:
            return []
        q = tokenize(query)
        if not q:
            return []
        scored = [(i, self.score(q, i)) for i in range(self.n)]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


# ---------------- 库级缓存 ----------------
_CACHE: dict = {"fingerprint": None, "ids": [], "bm25": None}


def _fingerprint(conn: sqlite3.Connection) -> tuple:
    row = conn.execute("SELECT COUNT(*), MAX(chunk_id) FROM chunks").fetchone()
    return (row[0], row[1])


def get_bm25(conn: sqlite3.Connection) -> tuple[list[int], BM25]:
    """返回 (chunk_ids, BM25)。按 chunks 表顺序建, 指纹变化自动重建。"""
    fp = _fingerprint(conn)
    if _CACHE["fingerprint"] == fp and _CACHE["bm25"] is not None:
        return _CACHE["ids"], _CACHE["bm25"]
    rows = conn.execute("SELECT chunk_id, chunk_text FROM chunks ORDER BY chunk_id").fetchall()
    ids = [r["chunk_id"] for r in rows]
    bm25 = BM25([tokenize(r["chunk_text"] or "") for r in rows])
    _CACHE.update({"fingerprint": fp, "ids": ids, "bm25": bm25})
    return ids, bm25


def rrf_fuse(result_lists: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion: 多路结果(每路 chunk_id 有序列表)融合打分。"""
    scores: dict[int, float] = {}
    for lst in result_lists:
        for rank, cid in enumerate(lst, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


if __name__ == "__main__":
    demo = ["江苏银行净息差企稳 1.42%", "光模块 800G 订单饱满", "白酒去库存"]
    b = BM25([tokenize(d) for d in demo])
    for q in ["净息差", "光模块"]:
        print(q, "->", b.search(q))
