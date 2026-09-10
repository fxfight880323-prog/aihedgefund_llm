# -*- coding: utf-8 -*-
"""Q20 持仓 × 研报证据报告 —— 调仓决策的 RAG 落地场景。

对 40 只持仓逐股时点检索研报观点(关键词情绪计分, 规则法非 LLM, 可无人值守),
并验证 band80 剔除票的研报风险证据。输出 _rag_holdings_<date>.html。

用法: python run.py rag holdings [--as-of 2026-08-26]
2027-04-30 调仓前跑: python run.py rag holdings --as-of 2027-04-23
"""
from __future__ import annotations

import html
import json
import os
from datetime import date

from rag import config, indexer, ingest

# band80 严格口径下剔除的票(2026-09-10 实证, 见 docs/research_log/q20_band80_landing)
# 名称用于检索; band90 实盘只剔了江苏银行, band80 额外剔 7 只
BAND_EXCLUDED: list[str] = [
    "江苏银行", "青岛银行", "齐鲁银行", "焦作万方", "中山公用",
    "长江证券", "电投能源", "新集能源",
]

POS_WORDS = ["增长", "提升", "超预期", "优于", "稳健", "向好", "高增", "改善",
             "回升", "看好", "低估值", "分红", "红利", "双位数", "企稳"]
NEG_WORDS = ["下滑", "低于预期", "承压", "恶化", "下降", "拖累", "压力",
             "高位", "回落", "风险", "减值", "收窄", "阵痛"]


def _sentiment(text: str) -> tuple[int, int]:
    """返回 (正词数, 负词数)。规则法, 不装 AI。"""
    t = text or ""
    return (sum(t.count(w) for w in POS_WORDS),
            sum(t.count(w) for w in NEG_WORDS))


def _evidence(name: str, as_of: str | None, top_k: int = 4) -> dict:
    """单股检索: 观点 + 风险两路, 汇总为证据卡。"""
    rows = []
    for q in (f"{name} 研报观点", f"{name} 风险 估值"):
        try:
            rows.extend(indexer.search(q, top_k=top_k, as_of=as_of,
                                       tickers=None))
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ search {name}: {e}")
    # 按报告去重(每报告至多2块), 最新优先
    seen: dict[str, int] = {}
    picked: list[dict] = []
    rows.sort(key=lambda r: (r.get("publish_date") or "", r["score"]), reverse=True)
    for r in rows:
        key = f"{r['source']}:{r['doc_id']}"
        if seen.get(key, 0) >= 2:
            continue
        seen[key] = seen.get(key, 0) + 1
        picked.append(r)
    if not picked:
        return {"hits": 0, "pos": 0, "neg": 0, "latest": None, "chunks": []}
    all_text = "\n".join(p["chunk_text"] or "" for p in picked[:6])
    pos, neg = _sentiment(all_text)
    return {"hits": len(picked), "pos": pos, "neg": neg,
            "latest": picked[0], "chunks": picked[:3]}


def _sent_label(pos: int, neg: int) -> str:
    if pos + neg == 0:
        return "中性"
    diff = (pos - neg) / (pos + neg)
    return "偏正面" if diff > 0.25 else "偏负面" if diff < -0.25 else "中性"


def run_holdings(as_of: str | None = None, out_path: str | None = None) -> str:
    today = date.today().strftime("%Y%m%d")
    out_path = out_path or os.path.join(
        config.BASE_DIR, f"_rag_holdings_{today}.html")
    if not os.path.exists(ingest.PORTFOLIO_PATH):
        raise SystemExit("未找到 _sim_q20_portfolio.json")
    pf = json.load(open(ingest.PORTFOLIO_PATH, encoding="utf-8"))
    positions = pf["positions"]
    st = indexer.stats()
    print(f"🎯 持仓×研报证据报告: {len(positions)} 只持仓"
          f"{' as_of=' + as_of if as_of else ''} (库 {st['chunks']} chunks)")

    cards = []
    for i, p in enumerate(positions, 1):
        ev = _evidence(p["name"], as_of)
        cards.append({**p, "ev": ev})
        lab = _sent_label(ev["pos"], ev["neg"]) if ev["hits"] else "无证据"
        print(f"  [{i:>2}/40] {p['name']:<6} 命中{ev['hits']:>2} "
              f"正{ev['pos']:>2}/负{ev['neg']:>2} → {lab}")

    print(f"  band80 剔除票风险验证: {len(BAND_EXCLUDED)} 只")
    band_cards = []
    for name in BAND_EXCLUDED:
        ev = _evidence(f"{name} 估值 风险", as_of, top_k=3)
        band_cards.append({"name": name, "ev": ev})

    _write_html(out_path, pf, cards, band_cards, as_of, st)
    n_pos = sum(1 for c in cards if c["ev"]["hits"])
    neg_names = [c["name"] for c in cards
                 if c["ev"]["hits"] and _sent_label(c["ev"]["pos"], c["ev"]["neg"]) == "偏负面"]
    print(f"✅ {out_path}  (证据覆盖 {n_pos}/40, 偏负面: {neg_names or '无'})")
    return out_path


def _write_html(out_path, pf, cards, band_cards, as_of, st):
    cfg = pf.get("config", {})
    css = """
body{font-family:'Microsoft YaHei',sans-serif;max-width:1120px;margin:24px auto;padding:0 16px;color:#222;background:#fafafa}
h1{font-size:20px;border-bottom:2px solid #35495e;padding-bottom:8px}
h2{font-size:16px;margin-top:26px;color:#35495e}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff}
th{background:#35495e;color:#fff;padding:7px 10px;text-align:left;font-weight:500}
td{border-bottom:1px solid #e8e8e8;padding:7px 10px;vertical-align:top}
tr:hover td{background:#f4f7fb}
.pos{color:#1a7a3a;font-weight:600}.neg{color:#b02a2a;font-weight:600}.neu{color:#777}
.ev{color:#555;font-size:12px;max-width:420px;line-height:1.6}
.flag-ok{background:#e8f4e8}.flag-mid{background:#fdf6e6}
.meta{color:#777;font-size:12px}
.snapshot{background:#eef7ee;border:1px solid #cde8cd;border-radius:8px;padding:10px 14px;font-size:13px;margin:10px 0}
.foot{margin-top:30px;color:#999;font-size:11px;border-top:1px solid #ddd;padding-top:8px}
"""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>Q20 持仓×研报证据 {date.today()}</title><style>{css}</style></head><body>",
        f"<h1>🎯 Q20 持仓 × 研报证据报告 · {date.today()}"
        + (f"（时点 as_of={as_of}）" if as_of else "") + "</h1>",
        f"<p class='meta'>知识库 {st['docs']} 报告 / {st['chunks']} chunks · "
        "bge-small 召回 + bge-reranker 精排 · 情绪为关键词规则法(正/负词频), 非模型判断</p>",
        f"<div class='snapshot'>💼 <b>{html.escape(cfg.get('name', ''))}</b> · "
        f"名单 as_of {cfg.get('list_as_of')} · 下次调仓 <b>{cfg.get('next_rebalance')}</b> · "
        f"{len(cards)} 只持仓 · 证据覆盖 {sum(1 for c in cards if c['ev']['hits'])}/{len(cards)}</div>",
    ]
    # 分组: band_flag 确认 / 中性
    for flag, label, cls in (("确认", "band 确认（PB 分位安全）", "flag-ok"),
                             ("中性", "band 中性（PB 分位偏高, 关注）", "flag-mid")):
        grp = [c for c in cards if c.get("band_flag") == flag]
        if not grp:
            continue
        parts.append(f"<h2>{label} · {len(grp)} 只</h2><table>")
        parts.append("<tr><th>股票</th><th>PE</th><th>q_score</th><th>blend</th>"
                     "<th>情绪</th><th>最新证据（标题/机构/日期 + 摘录）</th></tr>")
        for c in grp:
            ev = c["ev"]
            lab = _sent_label(ev["pos"], ev["neg"]) if ev["hits"] else "无证据"
            lab_cls = "pos" if lab == "偏正面" else "neg" if lab == "偏负面" else "neu"
            if ev["latest"]:
                lt = ev["latest"]
                meta = f"{lt.get('institution') or ''} · {lt.get('publish_date') or ''}"
                txt = (lt.get("chunk_text") or "").replace("\n", " ")
                txt = html.escape(txt[:260]) + ("…" if len(txt) > 260 else "")
                ev_html = (f"<b>《{html.escape((lt.get('title') or '')[:52])}》</b>"
                           f"<br><span class='meta'>{html.escape(meta)}</span>"
                           f"<div class='ev'>{txt}</div>")
            else:
                ev_html = "<span class='neu'>库内无该股研报</span>"
            parts.append(
                f"<tr class='{cls}'><td><b>{html.escape(c['name'])}</b><br>"
                f"<span class='meta'>{c['code']}</span></td>"
                f"<td>{c.get('pe', '')}</td><td>{c.get('q_score', '')}</td>"
                f"<td>{c.get('blend', '')}</td>"
                f"<td class='{lab_cls}'>{lab}<br><span class='meta'>正{ev['pos']}/负{ev['neg']}</span></td>"
                f"<td>{ev_html}</td></tr>")
        parts.append("</table>")
    # band80 剔除票
    parts.append(f"<h2>⚠️ band80 严格口径剔除票 · 研报风险证据 · {len(band_cards)} 只</h2>")
    parts.append("<p class='meta'>2027-04-30 调仓拟切换 band80 口径, 此处用研报库验证"
                 "「PB 高位假便宜」判断是否有基本面证据支撑</p><table>")
    parts.append("<tr><th>股票</th><th>情绪</th><th>风险证据摘录</th></tr>")
    for b in band_cards:
        ev = b["ev"]
        lab = _sent_label(ev["pos"], ev["neg"]) if ev["hits"] else "无证据"
        lab_cls = "pos" if lab == "偏正面" else "neg" if lab == "偏负面" else "neu"
        if ev["latest"]:
            lt = ev["latest"]
            txt = html.escape((lt.get("chunk_text") or "").replace("\n", " ")[:240])
            ev_html = (f"《{html.escape((lt.get('title') or '')[:48])}》"
                       f"<span class='meta'>{lt.get('publish_date') or ''}</span>"
                       f"<div class='ev'>{txt}</div>")
        else:
            ev_html = "<span class='neu'>—</span>"
        parts.append(f"<tr><td><b>{html.escape(b['name'])}</b></td>"
                     f"<td class='{lab_cls}'>{lab}</td><td>{ev_html}</td></tr>")
    parts.append("</table>")
    parts.append(
        "<div class='foot'>用法: 调仓前 python run.py rag holdings --as-of <调仓周日期> · "
        "情绪标签为词频规则法, 仅作初筛, 结论以研报原文为准 · "
        f"生成于 {date.today().isoformat()}</div></body></html>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


if __name__ == "__main__":
    run_holdings()
