# -*- coding: utf-8 -*-
"""日期工具：自动推导候选交易日、缓存新鲜度体检。

关键设计：A 股节假日不在此处硬编码——候选日期交给 _lx_now_fetch.py 的
"逐个测试 count>0" 机制自动跳过，本模块只负责生成"最近 N 个工作日"。
"""
from __future__ import annotations

import datetime
import json
import os

from . import config


def candidate_dates(n: int = 6) -> list[str]:
    """最近 n 个工作日（跳过周末，最新在前），格式 YYYY-MM-DD。"""
    today = datetime.date.today()
    out: list[str] = []
    d = today
    while len(out) < n:
        if d.weekday() < 5:          # 周一~周五
            out.append(d.isoformat())
        d -= datetime.timedelta(days=1)
    return out


def _norm_date(v):
    """YYYYMMDD -> YYYY-MM-DD；已 ISO 格式或 None 原样返回。"""
    if v and isinstance(v, str) and len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    return v


def _cache_asof(path: str):
    """读缓存 JSON 的 as_of 字段（不存在/无字段返回 None）。"""
    try:
        d = json.load(open(path, encoding="utf-8"))
        return d.get("as_of") or (d[0].get("as_of") if isinstance(d, list) and d else None)
    except Exception:
        return None


def _nav_last_date(path: str):
    """读净值序列最后一条的 date（YYYYMMDD）。"""
    try:
        arr = json.load(open(path, encoding="utf-8"))
        if isinstance(arr, list) and arr:
            return arr[-1].get("date", "")
    except Exception:
        return None


def freshness_status() -> list[dict]:
    """数据新鲜度体检，返回 [{key, file, as_of, fresh, note}]。

    新鲜度口径：A 股数据 T 日收盘后 / T+1 上午才落地，故允许缓存滞后
    1 个工作日（as_of >= 最近第 2 个工作日 即视为 fresh）。
    """
    B = config.ROOT + os.sep
    today = datetime.date.today().isoformat()
    work = candidate_dates(2)                # [今天(工作日), 昨天(工作日)]
    min_fresh = work[1] if len(work) > 1 else work[0]
    rows = []
    checks = [
        # (key, 文件, as_of 提取, 判定函数, is_state)  is_state=无日期语义的账本类
        ("universe PIT成分", "_bt_lx_now_universe.json", _cache_asof, None, False),
        ("估值面板", "_bt_lx_now_valuation.json", _cache_asof, None, False),
        ("HF因子(健康日)", "_bt_lx_now_factors.json", _cache_asof, None, False),
        ("一致预期", "_bt_lx_now_consensus.json", _cache_asof, None, False),
        ("LX-top40 净值", "_sim_nav.json", _nav_last_date, None, False),
        ("Q20 净值", "_sim_q20_nav.json", _nav_last_date, None, False),
        ("LX 组合账本", "_sim_portfolio.json",
         lambda p: f"持仓 {len(json.load(open(p, encoding='utf-8')).get('positions', []))} 只", None, True),
        ("Q20 组合账本", "_sim_q20_portfolio.json",
         lambda p: f"持仓 {len(json.load(open(p, encoding='utf-8')).get('positions', []))} 只", None, True),
    ]
    for key, fn, extract, judge, is_state in checks:
        path = B + fn
        if not os.path.exists(path):
            rows.append({"key": key, "file": fn, "as_of": None, "fresh": False,
                         "note": "文件不存在"})
            continue
        v = extract(path)
        if is_state:
            fresh, note = True, v
        elif judge is not None:
            note = judge(v, today)
            fresh = (v == today)
        else:
            nv = _norm_date(v)
            fresh = bool(nv and nv >= min_fresh and nv <= today)
            if fresh:
                note = "最新" if nv >= today else f"截至 {nv}（T+1 落地，属正常）"
            else:
                note = f"缓存截至 {nv}"
                if key == "HF因子(健康日)":
                    note += "（08-20 起服务端污染，回退健康日属预期）"
        rows.append({"key": key, "file": fn, "as_of": _norm_date(v) if v else None,
                     "fresh": fresh, "note": note})
    return rows
