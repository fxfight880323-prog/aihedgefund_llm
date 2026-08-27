# -*- coding: utf-8 -*-
"""统一配置：根目录、解释器、资金参数（所有步骤共用，勿散落硬编码）。"""
from __future__ import annotations

import os
import sys

# 项目根目录（pipeline/ 的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 解释器：优先管理 venv（pandas/numpy 已装），可用环境变量 AIFF_PYTHON 覆盖
_DEFAULT_PY = r"C:\Users\xfugm\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
PY = os.environ.get("AIFF_PYTHON") or (_DEFAULT_PY if os.path.exists(_DEFAULT_PY) else sys.executable)

# 模拟组合资金参数（权威口径，与 _sim_engine.py / _sim_q20_engine.py 一致）
CAPITAL = 1_000_000        # 100 万
HOLDINGS = 40              # 40 只等权
COST_BPS = 15              # 单边 15bp

# 回测基准口径说明（写进报告摘要用）
BENCH_NOTES = {
    "ew": "半年调仓等权全A（881001.WI PIT 成分，日频复权，_bt_daily_ew_hold.py）",
    "mkt": "中证全指 000985.SH（价格指数，市值加权基准）",
}

# 数据源凭证
JUZI_CREDS = "examples.fetch_consensus"
