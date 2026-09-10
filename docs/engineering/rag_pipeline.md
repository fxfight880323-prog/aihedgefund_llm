# 投研 RAG 管线（rag/）

> 建立日期: 2026-09-10 · 参考方法论: [microsoft/RAG-Knowledge](https://github.com/microsoft/RAG-Knowledge)
> 目标: 把 MCP 研报源(csc/juzi)的内容沉淀为**本地**知识库+向量库, 围绕 q20/LX-top40 策略做可追溯的投研检索与跟踪。

## 架构总览

```
MCP 研报源 ──ingest──▶ raw JSON ──chunker──▶ chunks ──embed──▶ faiss + sqlite
   csc-mcp (PDF全文,    (rag/store/raw/)   (段落感知+512tok   (IndexIDMap2 +      ──query──▶ 语义检索
   juzi-mcp (chunk文本+                      +80tok重叠+       元数据/时点过滤)      (as_of 防未来)    │
   策略卡片)                                 标题上下文前缀)                                          ▼
                                                                               report: 策略主题跟踪文档(HTML+Obsidian)
```

## 设计决策表

| 组件 | 选择 | 理由 |
|---|---|---|
| 数据源 | juzi-mcp + csc-mcp（Python 直连，见 `rag/mcp_client.py`） | 无人值守；westock 是 WorkBuddy connector 无法脚本直连，预留 manual 导入 |
| 文本提取 | juzi 天然 chunk；csc PDF → base64 切片拼接 → pymupdf | RAG-Knowledge §数据预处理 |
| 分块 | 段落聚合 ≤450 字符 + 标题前缀（标题/机构/行业/日期） | chunk 带上下文，检索片段可独立理解 |
| Embedding | `BAAI/bge-small-zh-v1.5`（512 维, 本地 CPU, HF 镜像） | 中文检索质量好；模型已缓存到本地 HF cache |
| 向量库 | faiss `IndexIDMap2(IndexFlatIP)` + SQLite 元数据 | 全部现成依赖；<10万 chunk 精确检索足够 |
| 检索 | 向量召回 top50 → SQL 过滤（as_of/source/industry/report_type/tickers）→ top_k | 混合检索的过滤式实现，v2 可加 FTS5+RRF |
| 时点过滤 | chunk 元数据带 `publish_date`，query 传 `as_of` 只取 ≤as_of | 回测铁律的 RAG 版：无未来数据 |
| 跟踪文档 | 固定策略主题集检索 → HTML 简报（引用溯源到报告标题+机构+日期） | 投研整合交付物 |

## 主题集（围绕当前策略, `rag/config.py::THEMES`）

1. `q20_holdings` — 当前 Q40 持仓个股研报观点（从 `_sim_q20_portfolio.json` 动态读取）
2. `bank_nonbank` — 银行/非银行业观点（当前 11+8 只金融持仓的核心风险面）
3. `value_dividend` — 红利/低波/价值因子拥挤度
4. `strategy_methodology` — 金工策略方法论（因子挖掘、量价×基本面）
5. `macro_rate` — 宏观利率与流动性
6. `band_risk` — PB 高位「假便宜」规避证据（band80 决策依据）

## 使用

```bash
python run.py rag ingest [--theme all|q20_holdings|...]   # 采集入库（幂等去重, 全量~11分钟）
python run.py rag backfill [--limit 5]                    # 深度报告 PDF 全文回填（snippet→全文）
python run.py rag index                                    # 全量重建索引
python run.py rag query "银行净息差" [--as-of 2026-08-26] [--mode vector|hybrid|bm25]
python run.py rag eval                                     # 检索质量评估(hit@5/MRR)
python run.py rag report                                   # 投研跟踪文档 _rag_track_<date>.html
```

## v2 增量（2026-09-10 下午）

1. **PDF 全文回填**（`rag backfill`）：库内 csc 深度报告 snippet → PDF 全文。
   5 篇验证：608 个全文 chunks（单篇 79-174），库 747→1349 向量。
   首批全文：美元流动性 9 月配置 / 银行业中报综述 / 保险+证券 26H1 综述 / 朗姿股份。
2. **混合检索**（`rag/bm25.py`）：中文 2-gram BM25（零依赖）+ 加权 RRF（向量:BM25 = 2.5:1）。
   `--mode hybrid` 用于字面精确命中（代码/数字/报告名）兜底。
3. **评估集**（`rag/eval.py`，39 题标注，覆盖持仓个股/行业综述/金工方法论/宏观）：

| 模式 | hit@5 | MRR | 结论 |
|---|---|---|---|
| **vector（默认）** | **36/39 (92%)** | **0.847** | bge-small-zh 语义检索本场景最优 |
| hybrid | 33/39 (85%) | 0.575 | 加权 RRF 后仍略逊，留作字面命中兜底 |
| bm25 | 15/39 (38%) | 0.271 | 中文 2-gram 对口语查询噪声大 |

> 实证修正 RAG-Knowledge 的"hybrid 默认更优"：该结论多来自英文+专用分词器场景。
> 3 个 vector miss 均为真实边界：①「多维度择时体系」——报告内容碎片(隐波斜率/衍生品持仓)与标题型查询的语义 gap；②「跨境配置欧日市场」——返回《日股择时框架》属合理次优；③「基金仓位结构」同类。标题型查询是 hybrid 的价值场景（bm25 对②命中）。

## v3 增量（2026-09-10 傍晚）：全文库 + rerank 精排

1. **全部深度报告 PDF 回填完成**：28/29 篇成功（1 篇服务端 30s 超时，下期 automation 补），
   库 1349→**5879 向量**（33 篇深度报告全文，单篇 77-474 chunks）。
2. **语料扩容的精度稀释**：5879 向量后 vector hit@5 从 92%→82%（top5 竞争稀释，全文 chunk 挤掉 snippet 答案）。
3. **解法：bge-reranker-base 交叉编码器精排**（`rag/store/reranker/`，1.1GB，gitignore）——
   向量召回 top24-32 → reranker 精排 → top_k。`search(rerank=True)` 默认开启，模型缺失自动跳过。

| 模式 | hit@5 | MRR |
|---|---|---|
| **vector+rerank（默认）** | **35/39 (90%)** | **0.853** |
| vector 纯召回 | 32/39 (82%) | 0.770 |
| hybrid | 31/39 (79%) | 0.722 |
| bm25 | 8/39 (21%) | 0.188 |

CLI: `python run.py rag query "..." [--mode vector|hybrid|bm25] [--no-rerank]`

## 已知边界

- csc 每次 search API ~10s（服务端耗时），全量 ingest ~11 分钟属正常，前台跑注意 Bash 超时
- csc PDF 回填的旧向量成死键（检索时自动跳过），回填后 `rag index` 全量重建清理
- juzi 语义检索天然排除日报/周报（include_routine=False），回溯历史时注意
- westock connector 无法脚本直连，预留 manual 导入接口
- 评估集 39 题（持仓个股/行业综述/金工方法论/宏观），后续随真实使用扩充
- rerank 在 CPU 上每次查询 ~1-3s（24-32 候选），批量场景可 --no-rerank
