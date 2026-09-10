# -*- coding: utf-8 -*-
"""投研跟踪文档: 围绕策略主题集检索 → HTML 简报(证据卡片 + 引用溯源)。

输出: _rag_track_<YYYYMMDD>.html (仓库根)
设计: 每主题 3 个代表 query × top6, 按报告去重; 时点过滤默认今天。
"""
from __future__ import annotations

import html
import json
import os
from datetime import date

from rag import config, indexer, ingest

# 每主题的跟踪问题集(检索词)
TRACK_QUERIES: dict[str, list[str]] = {
    "bank_nonbank": ["银行 净息差 资产质量 2026", "银行股 估值 修复 空间", "券商 业绩 展望"],
    "value_dividend": ["红利低波 拥挤度 风险", "价值因子 超额收益 持续性", "股息率 策略 回撤"],
    "strategy_methodology": ["量价 基本面 因子 联合", "中证500 选股 月频", "PB-ROE 估值 质量 结合"],
    "macro_rate": ["货币政策 利率 A股", "流动性 宽松 风格", "财政 刺激 影响"],
    "band_risk": ["银行 估值 历史高位 风险", "周期 股 景气 顶部", "PB 分位 高 回撤"],
}


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _collect(top_k: int = 6) -> dict[str, list[dict]]:
    """每主题检索并按报告去重(每报告至多 2 chunk)。"""
    as_of = date.today().isoformat()
    out: dict[str, list[dict]] = {}
    for theme, queries in TRACK_QUERIES.items():
        seen_docs: dict[str, int] = {}
        cards: list[dict] = []
        for q in queries:
            try:
                rows = indexer.search(q, top_k=top_k)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ search '{q}': {e}")
                continue
            for r in rows:
                dkey = f"{r['source']}:{r['doc_id']}"
                if seen_docs.get(dkey, 0) >= 2:
                    continue
                seen_docs[dkey] = seen_docs.get(dkey, 0) + 1
                r["_query"] = q
                cards.append(r)
        cards.sort(key=lambda r: -r["score"])
        out[theme] = cards[: top_k * 2]
    return out


def _theme_title(t: str) -> str:
    return {
        "bank_nonbank": "🏦 银行/非银 · 持仓核心风险面",
        "value_dividend": "📉 红利/低波/价值因子 · 拥挤度与持续性",
        "strategy_methodology": "🧪 金工策略方法论 · 新证据",
        "macro_rate": "🌐 宏观利率与流动性",
        "band_risk": "⚠️ band80 规避 · PB 高位「假便宜」证据",
    }.get(t, t)


def _portfolio_snapshot() -> str:
    if not os.path.exists(ingest.PORTFOLIO_PATH):
        return "（未找到 _sim_q20_portfolio.json）"
    pf = json.load(open(ingest.PORTFOLIO_PATH, encoding="utf-8"))
    cfg = pf.get("config", {})
    nav_path = os.path.join(config.BASE_DIR, "_sim_q20_nav.json")
    nav_note = ""
    if os.path.exists(nav_path):
        try:
            nav = json.load(open(nav_path, encoding="utf-8"))
            last = nav[-1] if isinstance(nav, list) else nav
            if isinstance(last, dict):
                nav_note = f"最新净值 {last.get('nav', '?')}（{last.get('date', '?')}）"
        except Exception:  # noqa: BLE001
            pass
    return (f"{cfg.get('name', 'Q20')} · {len(pf.get('positions', []))} 只持仓 · "
            f"名单 as_of {cfg.get('list_as_of', '?')} · 下次调仓 {cfg.get('next_rebalance', '?')} · {nav_note}")


def run_report(out_path: str | None = None) -> str:
    today = date.today().strftime("%Y%m%d")
    out_path = out_path or os.path.join(
        config.BASE_DIR, f"{config.REPORT_PATH_PREFIX}_{today}.html")
    st = indexer.stats()
    print(f"📊 生成投研跟踪文档 (库: {st['docs']} docs / {st['chunks']} chunks)...")
    data = _collect()

    css = """
body{font-family:'Microsoft YaHei',sans-serif;max-width:1080px;margin:24px auto;padding:0 16px;color:#222;background:#fafafa}
h1{font-size:20px;border-bottom:2px solid #35495e;padding-bottom:8px}
h2{font-size:16px;margin-top:28px;color:#35495e}
.meta{color:#777;font-size:12px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:8px;padding:12px 14px;margin:10px 0}
.card .hd{display:flex;justify-content:space-between;font-size:13px;color:#35495e;font-weight:600}
.card .meta{margin:2px 0 6px;font-size:12px}
.card .txt{font-size:13px;line-height:1.7;color:#333}
.score{background:#eef4ff;padding:1px 8px;border-radius:10px;font-weight:400;color:#185fa5}
.query{background:#f4f4f4;border-radius:4px;padding:0 6px;font-size:11px;color:#666}
.snapshot{background:#eef7ee;border:1px solid #cde8cd;border-radius:8px;padding:10px 14px;font-size:13px}
.foot{margin-top:30px;color:#999;font-size:11px;border-top:1px solid #ddd;padding-top:8px}
"""

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>投研跟踪 {today}</title><style>{css}</style></head><body>",
        f"<h1>📚 投研 RAG 跟踪文档 · {today}</h1>",
        f"<p class='meta'>知识库: {st['docs']} 篇报告 / {st['chunks']} chunks / "
        f"{st['faiss_vectors']} 向量 · 检索模型 bge-small-zh-v1.5(本地) · 数据源 juzi-mcp + csc-mcp</p>",
        f"<div class='snapshot'>💼 <b>组合快照</b> · {_esc(_portfolio_snapshot())}</div>",
    ]
    total = 0
    for theme, cards in data.items():
        parts.append(f"<h2>{_theme_title(theme)}</h2>")
        if not cards:
            parts.append("<p class='meta'>（本主题暂无证据 —— 先跑 ingest）</p>")
            continue
        for r in cards:
            total += 1
            meta_bits = [b for b in [r.get("institution"), r.get("publish_date"),
                                     r.get("report_type"), r.get("industry")] if b]
            parts.append(
                "<div class='card'>"
                f"<div class='hd'><span>《{_esc(r.get('title'))}》</span>"
                f"<span class='score'>{r['score']:.3f}</span></div>"
                f"<div class='meta'>{_esc(' · '.join(meta_bits))} · "
                f"source={_esc(r.get('source'))} · 命中查询 <span class='query'>{_esc(r.get('_query'))}</span></div>"
                f"<div class='txt'>{_esc((r.get('chunk_text') or '')[:600])}</div>"
                "</div>")
    parts.append(
        f"<div class='foot'>共 {total} 条证据 · 生成于 {date.today().isoformat()} · "
        "流程: python run.py rag ingest → index → report · 引用溯源见每卡片 source/doc_id</div>"
        "</body></html>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"✅ 跟踪文档: {out_path} ({total} 条证据)")
    return out_path


if __name__ == "__main__":
    run_report()
