# -*- coding: utf-8 -*-
"""研报采集: 从 juzi-mcp / csc-mcp 拉研报 → 切块入库。

数据流:
  juzi: report_search_research_reports(主题 query) → chunk 文本(天然已切块)
  csc : research_search_reports(行业/主题) → 元数据+snippet → chunker 切块
        (--pdf 时: get_report_pdf → 分片 base64 → pymupdf 提全文)

主题集见 config.THEMES; q20_holdings 主题动态读 _sim_q20_portfolio.json 持仓。
幂等: source+doc_id 去重, 重复跑只增量。
"""
from __future__ import annotations

import base64
import json
import os
from datetime import date, timedelta

from rag import chunker, config, indexer
from rag.mcp_client import McpClient

PORTFOLIO_PATH = os.path.join(config.BASE_DIR, "_sim_q20_portfolio.json")


def _q20_holdings() -> list[dict]:
    """当前 Q20 持仓(股票代码+名称), 用于动态生成个股查询。"""
    if not os.path.exists(PORTFOLIO_PATH):
        return []
    pf = json.load(open(PORTFOLIO_PATH, encoding="utf-8"))
    out = []
    for pos in pf.get("positions", pf if isinstance(pf, list) else []):
        if isinstance(pos, dict) and pos.get("code"):
            out.append({"code": str(pos["code"]), "name": pos.get("name", "")})
    return out


def _today() -> str:
    return date.today().isoformat()


def _lookback(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


# ---------------- juzi 源 ----------------
def ingest_juzi(themes: list[str], top_k: int | None = None) -> list[dict]:
    """juzi 研报库: 语义检索返回的 chunk 直接入库(带报告元数据)。"""
    cli = McpClient("juzi-mcp")
    top_k = top_k or config.JUZI_TOP_K
    docs: dict[tuple, dict] = {}
    for theme in themes:
        queries = list(config.THEMES[theme]["queries"])
        if theme == "q20_holdings":
            queries = [f"{h['name']} 研报观点" for h in _q20_holdings()][:40]
        for q in queries:
            try:
                res = cli.call_tool("report_search_research_reports", {
                    "query": q, "top_k": top_k,
                    "date_from": _lookback(config.JUZI_LOOKBACK_DAYS),
                    "date_to": _today()})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ juzi query '{q}' failed: {e}")
                continue
            payload = res.get("data", res) if isinstance(res, dict) else {}
            for r in (payload or {}).get("results", []):
                doc_id = str(r.get("report_id"))
                key = ("juzi", doc_id)
                if key not in docs:
                    docs[key] = {
                        "source": "juzi", "doc_id": doc_id,
                        "title": r.get("report_title"),
                        "institution": r.get("institution"),
                        "report_type": r.get("report_type"),
                        "industry": None, "analyst": r.get("analyst"),
                        "publish_date": r.get("publish_date"),
                        "tickers": [], "theme": theme,
                        "strategy_meta": {
                            "has_strategy": r.get("has_strategy"),
                            "strategy_summary": r.get("strategy_summary"),
                            "strategy_universe": r.get("strategy_universe"),
                        } if r.get("has_strategy") else {},
                        "chunks": [r.get("chunk_text", "")],
                    }
                else:  # 同一报告的多个 chunk 追加
                    t = r.get("chunk_text", "")
                    if t and t not in docs[key]["chunks"]:
                        docs[key]["chunks"].append(t)
    return list(docs.values())


# ---------------- csc 源 ----------------
def ingest_csc(themes: list[str], with_pdf: bool = False,
               max_pdf: int = 3) -> list[dict]:
    """中信建投研报库: 检索元数据+snippet; --pdf 时拉全文 PDF。"""
    cli = McpClient("csc-mcp")
    theme_queries: list[tuple[str, str]] = []  # (theme, query) 保主题标签正确
    for theme in themes:
        for q in config.THEMES[theme]["queries"]:
            theme_queries.append((theme, q))
    if "q20_holdings" in themes:
        holdings = _q20_holdings()
        theme_queries.extend(("q20_holdings", h["name"]) for h in holdings[:25])
    docs: dict[tuple, dict] = {}
    for theme, q in theme_queries:
        try:
            res = cli.call_tool("csc-isai-lmznty-research-mcp_tools_research_search_reports", {
                "query": q, "top_k": config.CSC_TOP_K,
                "date_filter": config.CSC_DATE_FILTER})
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ csc query '{q}' failed: {e}")
            continue
        if not isinstance(res, dict):
            continue
        for r in res.get("items", []):
            doc_id = str(r.get("doc_id"))
            if doc_id in ("", "None"):
                continue
            key = ("csc", doc_id)
            if key in docs:
                continue
            industry = r.get("industry")
            docs[key] = {
                "source": "csc", "doc_id": doc_id,
                "title": r.get("title"),
                "institution": "中信建投",
                "report_type": r.get("report_type"),
                "industry": ",".join(industry) if isinstance(industry, list) else industry,
                "analyst": ",".join(r.get("analyst", [])) if isinstance(r.get("analyst"), list) else r.get("analyst"),
                "publish_date": r.get("publish_date") or r.get("publish_at"),
                "tickers": r.get("tickers") or [], "theme": theme,
                "strategy_meta": {}, "form_id": r.get("form_id"),
                "chunks": chunker.chunk_text(
                    r.get("snippet", ""),
                    title=r.get("title") or "", institution="中信建投",
                    industry=",".join(industry) if isinstance(industry, list) else (industry or ""),
                    publish_date=str(r.get("publish_date") or r.get("publish_at") or "")),
            }
    if with_pdf:
        _fetch_csc_pdfs(cli, docs, max_pdf)
    return list(docs.values())


def _fetch_pdf_chunks(cli: McpClient, doc_id: str, form_id: str,
                      title: str, industry: str, publish_date: str) -> tuple[str, list[str]]:
    """拉单篇 csc PDF → 本地保存 → pymupdf 提全文 → 重切块。返回 (pdf_path, chunks)。"""
    import base64

    import fitz  # pymupdf

    meta = cli.call_tool("csc-isai-lmznty-research-mcp_tools_research_get_report_pdf", {
        "doc_id": doc_id, "form_id": form_id})
    if not isinstance(meta, dict) or meta.get("status") != "ok":
        raise RuntimeError(f"get_report_pdf not ok: {meta}")
    tid, total = meta["transfer_id"], int(meta["total_chunks"])
    b64 = []
    for ci in range(total):
        part = cli.call_tool(
            "csc-isai-lmznty-research-mcp_tools_research_get_report_pdf_chunk",
            {"transfer_id": tid, "chunk_index": ci})
        if not isinstance(part, dict) or part.get("status") != "ok":
            raise RuntimeError(f"chunk {ci} failed")
        b64.append(part["file_base64"])
        if part.get("is_last_chunk"):
            break
    pdf_bytes = base64.b64decode("".join(b64))
    os.makedirs(config.RAW_DIR, exist_ok=True)
    raw_path = os.path.join(config.RAW_DIR, f"csc_{doc_id}.pdf")
    open(raw_path, "wb").write(pdf_bytes)
    with fitz.open(raw_path) as doc_pdf:
        full = "\n\n".join(p.get_text() for p in doc_pdf)
    chunks = chunker.chunk_text(
        full, title=title or "", institution="中信建投",
        industry=industry or "", publish_date=str(publish_date or ""))
    if not chunks:
        raise RuntimeError("PDF 提取文本为空(可能是扫描版)")
    return raw_path, chunks


def _fetch_csc_pdfs(cli: McpClient, docs: dict, max_pdf: int) -> None:
    """对新采集的深度报告拉 PDF 全文(ingest --pdf 路径)。"""
    picked = [d for d in docs.values()
              if d.get("report_type") == "深度" and d.get("form_id")][:max_pdf]
    for i, d in enumerate(picked):
        try:
            print(f"  📄 PDF {i+1}/{len(picked)}: {d['title'][:40]}")
            path, chunks = _fetch_pdf_chunks(
                cli, d["doc_id"], d["form_id"], d["title"],
                d.get("industry") or "", d.get("publish_date"))
            d["chunks"], d["pdf_path"] = chunks, path
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ PDF failed ({d['doc_id']}): {e}")


# ---------------- PDF 回填(存量库) ----------------
def run_backfill(limit: int = 5, only_pdf: bool = False) -> dict:
    """对库内已有 csc 深度报告回填 PDF 全文。

    需要先跑过一次 ingest(补齐 form_id)。回填后建议 `python run.py rag index` 清死向量。
    """
    cli = McpClient("csc-mcp")
    conn = indexer._connect()
    rows = conn.execute(
        "SELECT doc_id, form_id, title, industry, publish_date, pdf_path FROM docs "
        "WHERE source='csc' AND report_type='深度' AND form_id IS NOT NULL "
        "AND (pdf_path IS NULL OR pdf_path='') ORDER BY publish_date DESC LIMIT ?",
        (limit,)).fetchall()
    print(f"📄 PDF 回填: {len(rows)} 篇深度报告待回填")
    ok, failed = 0, 0
    for i, r in enumerate(rows):
        try:
            print(f"  [{i+1}/{len(rows)}] {r['title'][:44]} ({r['publish_date']})")
            path, chunks = _fetch_pdf_chunks(
                cli, r["doc_id"], r["form_id"], r["title"],
                r["industry"] or "", r["publish_date"])
            n = indexer.replace_doc_chunks(conn, "csc", r["doc_id"], chunks, pdf_path=path)
            ok += 1
            print(f"    ✅ {len(chunks)} chunks (原 snippet 替换为全文)")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"    ⚠️ failed: {e}")
    conn.close()
    if ok:
        n = _rebuild_after_backfill()
        print(f"✅ 回填完成: 成功 {ok} / 失败 {failed}; 索引重建 {n} 向量")
    else:
        print(f"回填结束: 成功 0 / 失败 {failed}")
    return {"ok": ok, "failed": failed}


def _rebuild_after_backfill() -> int:
    conn = indexer._connect()
    n = indexer.rebuild_index(conn)
    conn.close()
    return n


# ---------------- 总入口 ----------------
def run_ingest(themes: list[str] | None = None, with_pdf: bool = False,
               max_pdf: int = 3) -> dict:
    themes = themes or list(config.THEMES)
    unknown = [t for t in themes if t not in config.THEMES]
    if unknown:
        raise SystemExit(f"未知主题: {unknown}, 可选: {list(config.THEMES)}")
    print(f"📥 RAG ingest 开始, 主题: {themes}, PDF: {with_pdf}")
    docs = []
    try:
        n0 = len(docs)
        docs.extend(ingest_juzi(themes))
        print(f"  juzi: {len(docs)-n0} 篇报告")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ juzi 整体失败: {e}")
    try:
        n0 = len(docs)
        docs.extend(ingest_csc(themes, with_pdf=with_pdf, max_pdf=max_pdf))
        print(f"  csc : {len(docs)-n0} 篇报告")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ csc 整体失败: {e}")
    # 持久化 raw
    os.makedirs(config.RAW_DIR, exist_ok=True)
    raw_path = os.path.join(config.RAW_DIR, f"ingest_{_today()}.json")
    json.dump(docs, open(raw_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 入库 + 增量索引
    conn = indexer._connect()
    new_chunks = indexer.upsert_docs(conn, docs)
    new_vecs = indexer.incremental_index(conn)
    conn.close()
    st = indexer.stats()
    print(f"✅ 入库完成: 本次新增 {new_chunks} chunks / {new_vecs} 向量; "
          f"库内共 {st['docs']} docs, {st['chunks']} chunks, {st['faiss_vectors']} 向量")
    return {"new_docs": len(docs), "new_chunks": new_chunks, "stats": st}
