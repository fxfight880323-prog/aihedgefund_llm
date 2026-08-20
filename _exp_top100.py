# -*- coding: utf-8 -*-
"""行业聚合层实验 · 阶段1：重筛每期全市场 top-100，存完整明细。

目的：原回测只把"行业截断后的 candidates"落盘，每期 top-100 原始
明细没存。要实施"删行业层直通"(plan1) 与 "s1 龙头质量分"(plan2)，
必须先拿到每期 top-100 完整名单（含行业/增速/ROE/上年同期营收）。

数据源：MX Screener（HTTP 直连，与连接器无关），历史报告期查询
已验证可复现（2021 中报 100 行完整返回）。

输出：_bt_top100.json = {month: {"as_of":..., "rows":[...]}}
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from src.data.mx_mcp_client import MXMCPClient, TOOL_SCREENER
from src.data.mx_data_client import parse_cn_number, sheet_to_indexed

OUT_FILE = "_bt_top100.json"

# (rebalance month, as_of, 报告期中文, 点时日期标签, 上年同期标签)
PIT_DATES = [
    ("2021-08", "2021-08-31", "2021年中报", "2021.06.30", "2020.06.30"),
    ("2022-04", "2022-04-30", "2022年一季报", "2022.03.31", "2021.03.31"),
    ("2022-08", "2022-08-31", "2022年中报", "2022.06.30", "2021.06.30"),
    ("2023-04", "2023-04-30", "2023年一季报", "2023.03.31", "2022.03.31"),
    ("2023-08", "2023-08-31", "2023年中报", "2023.06.30", "2022.06.30"),
    ("2024-04", "2024-04-30", "2024年一季报", "2024.03.31", "2023.03.31"),
    ("2024-08", "2024-08-31", "2024年中报", "2024.06.30", "2023.06.30"),
    ("2025-04", "2025-04-30", "2025年一季报", "2025.03.31", "2024.03.31"),
    ("2025-08", "2025-08-31", "2025年中报", "2025.06.30", "2024.06.30"),
    ("2026-04", "2026-04-30", "2026年一季报", "2026.03.31", "2025.03.31"),
]


def norm_ticker(code: str) -> str | None:
    c = str(code).strip().split(".")[0]
    if not re.fullmatch(r"\d{6}", c):
        return None
    if c[0] == "6":
        return f"{c}.SH"
    if c[0] in ("0", "3"):
        return f"{c}.SZ"
    return None


def _field(row: dict, *needles, exclude=()) -> str | None:
    for k, v in row.items():
        ks = str(k)
        if all(n in ks for n in needles) and not any(e in ks for e in exclude):
            return str(v)
    return None


def fetch_top100(cli, cn_period, ptag) -> list[dict]:
    q = (f"{cn_period}营业收入同比增速从高到低排名前100的A股，"
         f"总市值大于50亿元，显示申万行业分类、{cn_period}营业收入"
         f"同比增长率、{cn_period}净资产收益率ROE、上年同期营业收入")
    sheets = cli.query(TOOL_SCREENER, q, use_cache=True)
    rows: list[dict] = []
    for sh in sheets:
        for _rank, row in sheet_to_indexed(sh).items():
            code = _field(row, "代码")
            tk = norm_ticker(code or "")
            if not tk:
                continue
            name = (_field(row, "名称") or "").strip()
            if "ST" in name or "退" in name:
                continue
            sw = _field(row, "申万行业分类") or ""
            sw1 = sw.split("-")[0] if sw else "未知"
            g_raw = _field(row, "营业收入同比增长率", exclude=("元",))
            growth = (parse_cn_number(g_raw.split("|")[0])
                      if g_raw else None)
            r_raw = _field(row, "ROE")
            roe = (parse_cn_number(r_raw.split("|")[0]) if r_raw else None)
            prior_rev = None
            for k, v in row.items():
                ks = str(k)
                if ("营业收入" in ks and "元" in ks and "同比" not in ks
                        and ptag in ks):
                    raw = str(v).split("|")[0]
                    pv = parse_cn_number(raw)
                    if pv is not None:
                        if not re.search(r"[亿万]", raw):
                            pv = pv * 1e4
                        prior_rev = pv
            if growth is None or roe is None:
                continue
            rows.append({
                "tk": tk, "name": name, "sw1": sw1,
                "growth": growth / 100.0, "roe": roe,
                "prior_rev_yi": (prior_rev / 1e8 if prior_rev else None),
            })
    return rows


def main():
    cli = MXMCPClient()
    out: dict[str, dict] = {}
    for month, as_of, cn_period, _dtag, ptag in PIT_DATES:
        try:
            rows = fetch_top100(cli, cn_period, ptag)
        except Exception as e:
            print(f"  [{month}] 筛选失败: {e}", flush=True)
            continue
        out[month] = {"as_of": as_of, "rows": rows}
        print(f"  [{month}] {len(rows)} 行", flush=True)
        json.dump(out, open(OUT_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False)
    print(f"完成 → {OUT_FILE}（{len(out)} 期）")


if __name__ == "__main__":
    main()
