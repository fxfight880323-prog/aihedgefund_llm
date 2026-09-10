"""Semantica 试点 v1 — 验证三件事:
1. parse 模块对中文金融文本(HTML / MD)的解析质量
2. normalize 模块对中文实体/数字/日期的稳定性
3. 在没有外部 embedding 服务的情况下,模块是否完整可用(不依赖 embeddings)

设计: 只跑 parse + normalize,不引入 embeddings/vector_store(下一步才接)
"""
import sys
import json
import time
from pathlib import Path

ROOT = Path("D:/workspace/ai_fund_framework")
OUT = ROOT / "_semantica_pilot_log.json"

results = {}

# ========== 测 1: DocumentParser 解析 MD 文档 ==========
print("=" * 70)
print("[1] parse.DocumentParser  → docs/投资认知框架.md")
print("=" * 70)

try:
    from semantica.parse import DocumentParser
    parser = DocumentParser()
    f = ROOT / "docs/投资认知框架.md"
    t0 = time.time()
    text = parser.extract_text(str(f))
    meta = parser.extract_metadata(str(f))
    elapsed = time.time() - t0
    results["parse_md_text_len"] = len(text) if text else 0
    results["parse_md_meta"] = str(meta)[:300] if meta else None
    results["parse_md_elapsed_s"] = round(elapsed, 3)
    print(f"   文本长度: {len(text) if text else 0} chars")
    print(f"   元数据: {str(meta)[:200]}")
    print(f"   耗时: {elapsed*1000:.1f}ms")
    if text:
        print(f"   前 200 字: {text[:200]}")
except Exception as e:
    print(f"   ❌ 失败: {type(e).__name__}: {e}")
    results["parse_md_error"] = str(e)


# ========== 测 2: HTMLParser 解析 1 个回测报告 ==========
print()
print("=" * 70)
print("[2] parse.HTMLParser → _bt_garp_audit_report.html (30K)")
print("=" * 70)

try:
    from semantica.parse import HTMLParser
    parser = HTMLParser()
    f = ROOT / "_bt_garp_audit_report.html"
    if not f.exists():
        f = next((ROOT / ".").glob("*_report.html"))
    t0 = time.time()
    html_data = parser.parse(str(f))
    elapsed = time.time() - t0
    text = html_data.text if hasattr(html_data, "text") else ""
    meta = html_data.metadata if hasattr(html_data, "metadata") else {}
    results["parse_html_text_len"] = len(text) if text else 0
    results["parse_html_meta_keys"] = list(meta.keys()) if isinstance(meta, dict) else None
    results["parse_html_elapsed_s"] = round(elapsed, 3)
    print(f"   文本长度: {len(text) if text else 0} chars (原文 ~30K)")
    print(f"   元数据 keys: {list(meta.keys()) if isinstance(meta, dict) else 'N/A'}")
    print(f"   耗时: {elapsed*1000:.1f}ms")
    if text:
        # 找一段带数字的连续段落看看中文报告的实际抽取质量
        sample = text[2000:2400] if len(text) > 2400 else text[:400]
        print(f"   样本 2000-2400 字符: {sample}")
except Exception as e:
    print(f"   ❌ 失败: {type(e).__name__}: {e}")
    results["parse_html_error"] = str(e)


# ========== 测 3: TextNormalizer 清洗中文金融文本 ==========
print()
print("=" * 70)
print("[3] normalize.TextNormalizer → 中文片段")
print("=" * 70)

try:
    from semantica.normalize import TextNormalizer
    n = TextNormalizer()
    samples = [
        "中证全指 000985.SH 累计净值 +67.01%,   最大回撤 -16.67%",
        "PE_TTM  <  15  且   PEG  ≤  1.0  ",
        "平安银行 / 000001.SZ / PAYH / 平安銀行股份有限公司"
    ]
    out = []
    for s in samples:
        for method in ["normalize_text", "clean_text"]:
            try:
                kw = {"case": "lower"} if method == "normalize_text" else {}
                v = getattr(n, method)(s, **kw)
                out.append({"in": s, "method": method, "out": v})
                print(f"   [{method}] {s!r} → {v!r}")
            except Exception as e2:
                out.append({"in": s, "method": method, "error": str(e2)})
                print(f"   [{method}] {s!r} → ❌ {e2}")
    results["normalize_text"] = out
except Exception as e:
    print(f"   ❌ 失败: {type(e).__name__}: {e}")
    results["normalize_text_error"] = str(e)


# ========== 测 4: EntityNormalizer 中英文实体 ==========
print()
print("=" * 70)
print("[4] normalize.EntityNormalizer → 平安银行变体 / Apple 变体")
print("=" * 70)

try:
    from semantica.normalize import EntityNormalizer
    n = EntityNormalizer()
    variants = [
        ("平安银行", "Organization"),
        ("000001.SZ", "Ticker"),
        ("PAYH", "Ticker"),
        ("平安银行股份有限公司", "Organization"),
        ("平安銀行", "Organization"),
    ]
    out = []
    for v, t in variants:
        try:
            r = n.normalize_entity(v, entity_type=t)
            out.append({"in": v, "type": t, "out": r, "repr": repr(r)[:200]})
            print(f"   [{t}] {v!r} → {repr(r)[:150]}")
        except Exception as e2:
            out.append({"in": v, "type": t, "error": str(e2)})
            print(f"   [{t}] {v!r} → ❌ {e2}")
    results["normalize_entity"] = out
except Exception as e:
    print(f"   ❌ 失败: {type(e).__name__}: {e}")
    results["normalize_entity_error"] = str(e)


# ========== 测 5: DateNormalizer 中文日期变体 ==========
print()
print("=" * 70)
print("[5] normalize.DateNormalizer → 多种日期格式")
print("=" * 70)

try:
    from semantica.normalize import DateNormalizer
    n = DateNormalizer()
    samples = ["2024-01-15", "2024/01/15", "2024.01.15", "15-Jan-2024", "2024年1月15日", "2024-01"]
    out = []
    for s in samples:
        try:
            r = n.normalize_date(s)
            out.append({"in": s, "out": str(r)})
            print(f"   {s!r} → {r}")
        except Exception as e2:
            out.append({"in": s, "error": str(e2)})
            print(f"   {s!r} → ❌ {e2}")
    results["normalize_date"] = out
except Exception as e:
    print(f"   ❌ 失败: {type(e).__name__}: {e}")
    results["normalize_date_error"] = str(e)


# ========== 测 6: NumberNormalizer ==========
print()
print("=" * 70)
print("[6] normalize.NumberNormalizer → 财务数字")
print("=" * 70)

try:
    from semantica.normalize import NumberNormalizer
    n = NumberNormalizer()
    samples = ["1,000", "1.5亿", "1.5M", "¥100", "50%", "3.14e2", "1,000.00元"]
    out = []
    for s in samples:
        try:
            r = n.normalize_number(s)
            out.append({"in": s, "out": str(r)})
            print(f"   {s!r} → {r}")
        except Exception as e2:
            out.append({"in": s, "error": str(e2)})
            print(f"   {s!r} → ❌ {e2}")
    results["normalize_number"] = out
except Exception as e:
    print(f"   ❌ 失败: {type(e).__name__}: {e}")
    results["normalize_number_error"] = str(e)


# ========== 测 7: Listing available modules ==========
print()
print("=" * 70)
print("[7] 模块发现")
print("=" * 70)
try:
    import semantica
    print(f"   semantica version: {getattr(semantica, '__version__', 'unknown')}")
    print(f"   location: {semantica.__file__}")
    results["version"] = getattr(semantica, "__version__", "unknown")
    results["location"] = str(semantica.__file__)
    for sub in ["parse", "normalize", "ingest", "semantic_extract", "embeddings",
                "vector_store", "kg", "ontology", "reasoning", "pipeline", "core"]:
        try:
            __import__(f"semantica.{sub}")
            results[f"module_{sub}"] = "OK"
            print(f"   semantica.{sub}: ✅")
        except Exception as e:
            results[f"module_{sub}"] = f"❌ {type(e).__name__}: {str(e)[:80]}"
            print(f"   semantica.{sub}: ❌ {type(e).__name__}: {str(e)[:80]}")
except Exception as e:
    print(f"   ❌ import semantica 失败: {e}")
    results["semantica_import_error"] = str(e)


# ========== 输出 ==========
print()
print("=" * 70)
print(f"[done] 结果写入 {OUT}")
print("=" * 70)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))
