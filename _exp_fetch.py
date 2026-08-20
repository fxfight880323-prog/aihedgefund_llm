# -*- coding: utf-8 -*-
"""行业聚合层实验 · 阶段3：增量取数（plan1 并集 446 只，一份数据三方案共用）。

复用旧缓存（_bt_pit_financials.json + _bt_uni_financials.json 财务、
_bt_pit_prices.json + _bt_uni_prices.json 价格、_bt_pit_warmup.json 预热），
只拉缺失标的。输出：
  _bt_exp_financials.json / _bt_exp_prices.json / _bt_exp_warmup.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE
from src.data.mx_data_client import parse_cn_number, sheet_to_indexed
from src.data.cache import DiskCache

# 用项目内缓存目录（沙箱可写；~/.ai_fund 在后台任务里无写权限）
_MX_CACHE = DiskCache(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "_mx_cache"))

OUT_FIN = "_bt_exp_financials.json"
OUT_PRICES = "_bt_exp_prices.json"
OUT_WARMUP = "_bt_exp_warmup.json"

# 旧缓存（合并复用）
FIN_SRC = ["_bt_pit_financials.json", "_bt_uni_financials.json"]
PRICE_SRC = ["_bt_pit_prices.json", "_bt_uni_prices.json"]
WARMUP_SRC = ["_bt_pit_warmup.json"]


def load_merged(paths):
    out = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        d = json.loads(open(p, encoding="utf-8").read())
        for tk, v in d.items():
            out.setdefault(tk, v)
    return out


def main():
    cli = MXMCPClient(cache=_MX_CACHE)
    sel = json.loads(open("_bt_sel_plan1.json", encoding="utf-8").read())
    name_of: dict[str, str] = {}
    for v in sel.values():
        for tk, name, _ in v["candidates"]:
            name_of.setdefault(tk, name)
    todo = list(name_of.keys())
    print(f"plan1 候选并集 {len(todo)} 只", flush=True)

    fin = load_merged(FIN_SRC)
    prices = load_merged(PRICE_SRC)
    warmup = load_merged(WARMUP_SRC)
    print(f"已有缓存: 财务 {len(fin)} | 价格 {len(prices)} | 预热 {len(warmup)}",
          flush=True)

    # ---------- 财务（缺失的） ----------
    todo_fin = [tk for tk in todo if tk not in fin]
    print(f"缺财务 {len(todo_fin)} 只，开始增量…", flush=True)
    for i, tk in enumerate(todo_fin):
        name = name_of[tk]
        q = (f"{name}({tk}) 2020年中报到2026年中报每个报告期的"
             f"营业收入、销售毛利率、净资产收益率ROE")
        try:
            sheets = cli.query(TOOL_ASHARE, q, use_cache=True)
        except Exception as e:
            print(f"  财务失败 {tk}: {str(e)[:80]}", flush=True)
            continue
        periods: dict[str, dict] = {}
        for sh in sheets:
            for metric, by_col in sheet_to_indexed(sh).items():
                ms = str(metric)
                for col, val in by_col.items():
                    cs = str(col)
                    ym = re.search(r"(\d{4})", cs)
                    if not ym:
                        continue
                    y = int(ym.group(1))
                    qn = (1 if "一季" in cs else
                          2 if "中报" in cs or "半年" in cs else
                          3 if "三季" in cs else
                          4 if "年报" in cs or "年度" in cs else None)
                    if qn is None:
                        continue
                    pk = f"{y}-{qn}"
                    v = parse_cn_number(str(val).split("|")[0])
                    if v is None:
                        continue
                    if "营业收入" in ms and "同比" not in ms:
                        periods.setdefault(pk, {})["revenue"] = v
                    elif "毛利率" in ms:
                        periods.setdefault(pk, {})["gross_margin"] = v
                    elif "ROE" in ms or "净资产收益率" in ms:
                        periods.setdefault(pk, {})["roe"] = v
        if periods:
            fin[tk] = periods
        if (i + 1) % 10 == 0:
            json.dump(fin, open(OUT_FIN, "w", encoding="utf-8"),
                      ensure_ascii=False)
            print(f"    … 财务 {i+1}/{len(todo_fin)}", flush=True)
    json.dump(fin, open(OUT_FIN, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"财务就绪 {len(fin)} 只", flush=True)

    # ---------- BSADF 预热价格（2019-01→2021-05） ----------
    from examples.fill_winter_prices import parse_monthly
    todo_w = [tk for tk in todo if tk not in warmup]
    print(f"缺预热 {len(todo_w)} 只，开始增量…", flush=True)
    for i, tk in enumerate(todo_w):
        name = name_of[tk]
        q = f"{name}({tk}) 2019年1月到2021年5月每月末的收盘价"
        try:
            got = parse_monthly(cli.query(TOOL_ASHARE, q, use_cache=True))
            if got:
                warmup[tk] = {k: v for k, v in got.items() if k < "2021-06"}
        except Exception:
            pass
        if (i + 1) % 10 == 0:
            json.dump(warmup, open(OUT_WARMUP, "w", encoding="utf-8"))
            print(f"    … 预热 {i+1}/{len(todo_w)}", flush=True)
    json.dump(warmup, open(OUT_WARMUP, "w", encoding="utf-8"))
    print(f"预热就绪 {len(warmup)} 只", flush=True)

    # ---------- 主区间价格（2021-06→2026-08） ----------
    todo_p = [tk for tk in todo
              if tk not in prices or len(prices[tk]) < 50]
    print(f"缺价格 {len(todo_p)} 只，开始增量…", flush=True)
    for i, tk in enumerate(todo_p):
        name = name_of[tk]
        acc: dict[str, float] = prices.get(tk, {})
        queries = [
            f"{name}({tk}) 2021年6月到2023年11月每月末的收盘价",
            f"{name}({tk}) 2023年12月至2025年5月各月末的收盘价，"
            f"以及2024年12月至2025年5月各月末的收盘价",
            f"{name}({tk}) 2025年6月到2026年8月每月末的收盘价",
        ]
        for q in queries:
            try:
                got = parse_monthly(cli.query(TOOL_ASHARE, q,
                                              use_cache=True))
                acc.update(got)
            except Exception:
                continue
        if acc:
            prices[tk] = acc
        if (i + 1) % 5 == 0:
            json.dump(prices, open(OUT_PRICES, "w", encoding="utf-8"))
            print(f"    … 价格 {i+1}/{len(todo_p)}", flush=True)
    json.dump(prices, open(OUT_PRICES, "w", encoding="utf-8"))
    print(f"价格就绪 {len(prices)} 只", flush=True)

    print("\n全部完成", flush=True)


if __name__ == "__main__":
    main()
