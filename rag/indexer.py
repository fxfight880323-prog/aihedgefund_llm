# -*- coding: utf-8 -*-
"""索引与检索: sqlite 元数据 + faiss 向量。

- docs 表: 报告级元数据(去重主键 source+doc_id)
- chunks 表: chunk 文本 + 检索过滤字段(publish_date/source/industry/report_type/theme)
- faiss IndexIDMap2(IndexFlatIP): id=chunk_id, 余弦(归一化后内积)
- 检索: 向量召回 top(50*k) → SQL 元数据过滤(as_of 等) → top_k
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any

import numpy as np

from rag import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(
  source TEXT NOT NULL, doc_id TEXT NOT NULL,
  title TEXT, institution TEXT, report_type TEXT, industry TEXT, analyst TEXT,
  publish_date TEXT, tickers TEXT, strategy_meta TEXT,
  n_chunks INTEGER, ingested_at TEXT,
  PRIMARY KEY(source, doc_id));
CREATE TABLE IF NOT EXISTS chunks(
  chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL, doc_id TEXT NOT NULL, chunk_index INTEGER,
  title TEXT, institution TEXT, report_type TEXT, industry TEXT,
  publish_date TEXT, tickers TEXT, theme TEXT, chunk_text TEXT);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(source, doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_date ON chunks(publish_date);
CREATE INDEX IF NOT EXISTS idx_chunks_theme ON chunks(theme);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(config.STORE_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def get_model():
    """加载 embedding 模型(进程内缓存)。"""
    global _MODEL
    try:
        return _MODEL
    except NameError:
        pass
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet 后端在镜像下 401
    from sentence_transformers import SentenceTransformer
    _MODEL = SentenceTransformer(config.EMBED_MODEL)
    return _MODEL


def embed(texts: list[str]) -> np.ndarray:
    model = get_model()
    vecs = model.encode(texts, normalize_embeddings=True,
                        show_progress_bar=False, batch_size=32)
    return np.asarray(vecs, dtype="float32")


# ---------------- ingest 侧 ----------------
def upsert_docs(conn: sqlite3.Connection, docs: list[dict[str, Any]]) -> int:
    """插入新报告 + 切块, 返回新增 chunk 数。已存在(source+doc_id)的跳过。"""
    from rag import chunker
    new_chunks = 0
    for d in docs:
        cur = conn.execute("SELECT 1 FROM docs WHERE source=? AND doc_id=?",
                           (d["source"], d["doc_id"]))
        if cur.fetchone():
            continue
        conn.execute(
            "INSERT INTO docs(source,doc_id,title,institution,report_type,industry,"
            "analyst,publish_date,tickers,strategy_meta,n_chunks,ingested_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (d["source"], d["doc_id"], d.get("title"), d.get("institution"),
             d.get("report_type"), d.get("industry"), d.get("analyst"),
             d.get("publish_date"), json.dumps(d.get("tickers") or [], ensure_ascii=False),
             json.dumps(d.get("strategy_meta") or {}, ensure_ascii=False),
             len(d.get("chunks") or []), datetime.now().isoformat(timespec="seconds")))
        for ci, text in enumerate(d.get("chunks") or []):
            conn.execute(
                "INSERT INTO chunks(source,doc_id,chunk_index,title,institution,"
                "report_type,industry,publish_date,tickers,theme,chunk_text) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (d["source"], d["doc_id"], ci, d.get("title"), d.get("institution"),
                 d.get("report_type"), d.get("industry"), d.get("publish_date"),
                 json.dumps(d.get("tickers") or [], ensure_ascii=False),
                 d.get("theme"), text))
            new_chunks += 1
    conn.commit()
    return new_chunks


def rebuild_index(conn: sqlite3.Connection) -> int:
    """全量重建 faiss 索引(所有 chunks 重新 embed)。返回向量数。"""
    import faiss

    rows = conn.execute(
        "SELECT chunk_id, chunk_text FROM chunks ORDER BY chunk_id").fetchall()
    if not rows:
        return 0
    vecs = embed([r["chunk_text"] for r in rows])
    index = faiss.IndexIDMap2(faiss.IndexFlatIP(config.EMBED_DIM))
    ids = np.array([r["chunk_id"] for r in rows], dtype="int64")
    index.add_with_ids(vecs, ids)
    faiss.write_index(index, config.FAISS_PATH)
    return len(rows)


def incremental_index(conn: sqlite3.Connection) -> int:
    """增量: 只 embed 没有 faiss 记录的新 chunk。返回新增向量数。"""
    import faiss

    rows = conn.execute(
        "SELECT chunk_id, chunk_text FROM chunks ORDER BY chunk_id DESC LIMIT 2000"
    ).fetchall()
    if not rows:
        return 0
    if os.path.exists(config.FAISS_PATH):
        index = faiss.read_index(config.FAISS_PATH)
        have = set()
        n = index.ntotal
        if n:
            have = set(faiss.vector_to_array(index.id_map).tolist())
    else:
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(config.EMBED_DIM))
        have = set()
    new_rows = [r for r in rows if r["chunk_id"] not in have]
    if not new_rows:
        return 0
    vecs = embed([r["chunk_text"] for r in new_rows])
    ids = np.array([r["chunk_id"] for r in new_rows], dtype="int64")
    index.add_with_ids(vecs, ids)
    faiss.write_index(index, config.FAISS_PATH)
    return len(new_rows)


# ---------------- 检索侧 ----------------
def search(query: str, *, as_of: str | None = None, source: str | None = None,
           industry: str | None = None, report_type: str | None = None,
           tickers: list[str] | None = None, top_k: int = 8,
           recall_mult: int = 8) -> list[dict]:
    """时点语义检索。

    as_of: 'YYYY-MM-DD', 只返回 publish_date <= as_of 的 chunk(防未来数据)。
    """
    import faiss

    if not os.path.exists(config.FAISS_PATH):
        raise FileNotFoundError("faiss 索引不存在, 先跑 `python run.py rag index`")
    index = faiss.read_index(config.FAISS_PATH)
    if index.ntotal == 0:
        return []
    qv = embed([config.QUERY_INSTRUCTION + query])[0:1]
    k = min(index.ntotal, max(top_k * recall_mult, 40))
    scores, ids = index.search(qv, k)
    cand = [(int(i), float(s)) for s, i in zip(scores[0], ids[0]) if i >= 0]
    if not cand:
        return []
    conn = _connect()
    out: list[dict] = []
    for chunk_id, score in cand:
        r = conn.execute("SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,)).fetchone()
        if r is None:
            continue
        if as_of and (r["publish_date"] or "9999") > as_of:
            continue
        if source and r["source"] != source:
            continue
        if industry and (industry not in (r["industry"] or "")):
            continue
        if report_type and r["report_type"] != report_type:
            continue
        if tickers and not any(t in (r["tickers"] or "") for t in tickers):
            continue
        out.append({**dict(r), "score": round(score, 4)})
        if len(out) >= top_k:
            break
    conn.close()
    return out


def stats() -> dict:
    if not os.path.exists(config.DB_PATH):
        return {"docs": 0, "chunks": 0, "faiss_vectors": 0}
    conn = _connect()
    docs = conn.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
    chunks = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
    conn.close()
    vecs = 0
    if os.path.exists(config.FAISS_PATH):
        import faiss
        vecs = faiss.read_index(config.FAISS_PATH).ntotal
    return {"docs": docs, "chunks": chunks, "faiss_vectors": vecs}
