# -*- coding: utf-8 -*-
"""RAG 模块配置: 路径、模型、策略主题集。"""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ai_fund_framework/
STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
RAW_DIR = os.path.join(STORE_DIR, "raw")
DB_PATH = os.path.join(STORE_DIR, "rag.sqlite")
FAISS_PATH = os.path.join(STORE_DIR, "faiss.index")

# embedding: 512 维中文检索模型, 已下载到本地 rag/store/model
# (HF 镜像下载需 HF_HUB_DISABLE_XET=1 —— xet 后端 401, 见 docs/engineering/rag_pipeline.md)
EMBED_MODEL = os.path.join(STORE_DIR, "model")
EMBED_DIM = 512
# bge 系列 query 侧指令前缀
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# 分块参数
CHUNK_MAX_CHARS = 450       # 段落聚合上限(bge-small 512 token 安全余量)
CHUNK_OVERLAP_CHARS = 80

# 采集主题集: name -> {"queries": juzi/csc 检索词, "note": 用途}
THEMES: dict[str, dict] = {
    "q20_holdings": {
        "queries": [],  # 动态: 从 _sim_q20_portfolio.json 持仓生成(见 ingest.py)
        "note": "当前 Q20·质衡优选 40 只持仓的个股研报观点",
    },
    "bank_nonbank": {
        "queries": ["银行 净息差 资产质量", "银行业投资策略", "券商 非银金融 业绩",
                    "保险 投资价值", "银行股 估值修复"],
        "note": "金融持仓(银行11+非银8)核心风险面",
    },
    "value_dividend": {
        "queries": ["红利低波因子 拥挤度", "价值因子 表现", "股息率 策略",
                    "低估值 策略 超额收益", "银行 红利 风险"],
        "note": "红利/低波/价值因子拥挤度与持续性",
    },
    "strategy_methodology": {
        "queries": ["量价因子 基本面因子 联合挖掘", "中证500 月频选股策略",
                    "红利低波 因子构建", "小市值 因子", "组合优化 风险预算",
                    "PB-ROE 策略", "估值分位 因子"],
        "note": "金工策略方法论(因子挖掘/风格轮动)",
    },
    "macro_rate": {
        "queries": ["宏观利率 流动性 A股", "货币政策 债券收益率", "LPR 降息",
                    "财政政策 A股影响", "美元 人民币汇率 A股"],
        "note": "宏观利率与流动性",
    },
    "band_risk": {
        "queries": ["银行股 估值 风险", "周期股 景气顶部", "PB 历史高位 风险",
                    "煤炭 火电 盈利持续性", "券商股 波动风险"],
        "note": "band80 规避的 PB 高位「假便宜」证据",
    },
}

# juzi 采集参数
JUZI_TOP_K = 10        # 每个检索词取多少 chunk
JUZI_LOOKBACK_DAYS = 540  # 采集窗口(自然日)
# csc 采集参数
CSC_TOP_K = "15"
CSC_DATE_FILTER = "recent_180d"

REPORT_PATH_PREFIX = "_rag_track"   # 跟踪文档输出前缀(仓库根)
