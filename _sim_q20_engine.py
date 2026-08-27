# -*- coding: utf-8 -*-
"""Q20·质衡优选 模拟组合引擎 — 本地权威账本。

策略: q20 混合排序 = 0.8×PE便宜度 + 0.2×质量分（池内百分位），top40 等权。
池子: 万得全A PIT 含金融 core-pass（KFIN 221 只），band 规避剔除（PB 5年分位>90%）+ 替补递补。

口径（对齐回测日频复权）:
  - 初始资金 100 万，推荐名单 final top40 等权建仓（碎股口径，与回测一致）
  - 单边成本 15bp（佣金5bp+冲击10bp），与回测成本假设一致
  - 半年调仓：每年 4 月末 / 8 月末（对齐回测 PIT_DATES），按新名单等权重置
  - 净值 = Σ 持股×腾讯实时价 + 现金（未复权现价，模拟盘真实口径）
  - 基准 = 中证全指 000985.SH（价格指数，不含分红）

文件:
  _sim_q20_portfolio.json  持仓 + 配置（权威）
  _sim_q20_nav.json        每日净值序列
  _sim_q20_trades.json     交易流水
  _sim_q20_report.html     报告（_sim_q20_report.gen_report 生成）

用法:
  python _sim_q20_init.py        # 以 _bt_q20_kfin.json final 建仓
  python _sim_q20_daily.py       # 每日净值跟踪（幂等；非交易日/盘前自动跳过）
  python _sim_q20_rebalance.py   # 半年调仓（先重跑 _bt_q20_kfin.py 名单管线）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_engine as E  # 复用腾讯行情/账本工具

BASE = E.BASE
PORT_FILE = os.path.join(BASE, "_sim_q20_portfolio.json")
NAV_FILE = os.path.join(BASE, "_sim_q20_nav.json")
TRADE_FILE = os.path.join(BASE, "_sim_q20_trades.json")
REPORT_PATH = os.path.join(BASE, "_sim_q20_report.html")
LIST_FILE = os.path.join(BASE, "_bt_q20_kfin.json")   # q20 名单（final 数组）

CAPITAL = E.CAPITAL
FEE = E.FEE
BM_CODE = E.BM_CODE
BM_NAME = E.BM_NAME

tx_code = E.tx_code
fetch_quotes = E.fetch_quotes
jload = E.jload
jdump = E.jdump
port_value = E.port_value
upsert_nav = E.upsert_nav
next_rebalance = E.next_rebalance
