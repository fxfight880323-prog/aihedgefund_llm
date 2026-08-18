"""刷新全A选股器截面 — 获取最新的 wind 全A 高增长候选（妙想选股器）。

Run:
    D:\\Python\\python.exe run_zhf_screener_refresh.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from src.data.mx_mcp_client import MXMCPClient, TOOL_SCREENER

SCREENER_Q = (
    "全部A股中，最新报告期(2026半年报)营业收入同比增速大于30%且2026一季报"
    "营收同比增速大于20%的股票，输出：股票代码、简称、最新价、"
    "2026半年报营收同比增速、2026一季报营收同比增速、2026半年报销售毛利率、"
    "2026一季报销售毛利率、市盈率TTM、ROE、东财行业总分类、所属概念，"
    "按2026半年报营收同比增速从高到低"
)

OUT = "_screener_allA_latest.json"


def main():
    cli = MXMCPClient()
    sheets = cli.query(TOOL_SCREENER, SCREENER_Q, use_cache=False)
    if not sheets:
        print("ERROR: 妙想选股器无返回")
        sys.exit(1)
    sheet = sheets[0]
    n = len(sheet.get("items") or [])
    print(f"返回行数: {n}  sheetName: {sheet.get('sheetName')}")
    if n == 0:
        print("ERROR: 空数据")
        sys.exit(1)
    json.dump(sheet, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"已保存 -> {OUT}")


if __name__ == "__main__":
    main()
