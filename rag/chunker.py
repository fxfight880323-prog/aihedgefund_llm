# -*- coding: utf-8 -*-
"""文本分块: 段落感知 + 大小上限 + 标题上下文前缀。

RAG-Knowledge chunking 原则: chunk 需可独立理解 —— 每个 chunk 以
「【标题|机构|行业|日期】」前缀开头, 检索命中片段不脱离报告语境。
"""
from __future__ import annotations

from rag import config


def _prefix(title: str, institution: str, industry: str, publish_date: str) -> str:
    parts = [title or "", institution or "", industry or "", publish_date or ""]
    return "【" + "|".join(p for p in parts if p) + "】"


def chunk_text(text: str, *, title: str = "", institution: str = "",
               industry: str = "", publish_date: str = "") -> list[str]:
    """把长文本切成 ≤CHUNK_MAX_CHARS 的块, 相邻块重叠 CHUNK_OVERLAP_CHARS。

    以段落(\\n\\n 或单\\n)为最小单元聚合, 单段超长则按字符硬切。
    """
    text = (text or "").strip()
    if not text:
        return []
    pre = _prefix(title, institution, industry, publish_date)
    budget = config.CHUNK_MAX_CHARS - len(pre)

    # 1. 拆段落
    paras: list[str] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if len(line) <= budget:
                paras.append(line)
            else:  # 超长段硬切
                for i in range(0, len(line), budget):
                    paras.append(line[i:i + budget])

    # 2. 聚合成块(带重叠)
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paras:
        if cur and cur_len + len(p) + 1 > budget:
            chunks.append(pre + "\n" + " ".join(cur))
            # 重叠: 保留尾部若干字符
            tail = " ".join(cur)
            tail = tail[-config.CHUNK_OVERLAP_CHARS:] if len(tail) > config.CHUNK_OVERLAP_CHARS else tail
            cur, cur_len = ([tail] if tail else []), len(tail)
        cur.append(p)
        cur_len += len(p) + 1
    if cur:
        chunks.append(pre + "\n" + " ".join(cur))
    return chunks
