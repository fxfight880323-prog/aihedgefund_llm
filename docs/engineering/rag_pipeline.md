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
python run.py rag ingest [--theme all|q20_holdings|...]   # 采集入库（幂等去重）
python run.py rag index                                    # 全量重建索引
python run.py rag query "银行净息差" [--as-of 2026-08-26]  # 时点语义检索
python run.py rag report                                   # 生成投研跟踪文档 _rag_track_<date>.html
```

## 已知边界

- csc PDF 全文拉取按需（大文件），v1 默认 ingest 元数据+snippet，`--pdf` 开全文
- juzi 语义检索天然排除日报/周报（include_routine=False），回溯历史时注意
- 检索质量评估（RAG-Knowledge §evaluation）v1 靠人工 spot check，v2 加 hit@k 标注集
