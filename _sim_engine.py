# -*- coding: utf-8 -*-
"""LX-top40 模拟组合引擎 — 本地权威账本。

口径（对齐 LX-core 日频复权回测）:
  - 初始资金 100 万，推荐名单 top40 等权建仓（碎股口径，与回测一致）
  - 单边成本 15bp（佣金5bp+冲击10bp），与回测成本假设一致
  - 半年调仓：每年 4 月末 / 8 月末（对齐回测 PIT_DATES），按新名单等权重置
  - 净值 = Σ 持股×腾讯实时价 + 现金（未复权现价，模拟盘真实口径）
  - 基准 = 中证全指 000985.SH（价格指数，不含分红）

文件:
  _sim_portfolio.json  持仓 + 配置（权威）
  _sim_nav.json        每日净值序列
  _sim_trades.json     交易流水
  _sim_report.html     报告（_sim_report.gen_report 生成）

用法:
  python _sim_init.py        # 以 _lx_now_final.json 建仓
  python _sim_daily.py       # 每日净值跟踪（幂等；非交易日/盘前自动跳过）
  python _sim_rebalance.py   # 半年调仓到新名单（先重跑名单管线）
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
PORT_FILE = os.path.join(BASE, "_sim_portfolio.json")
NAV_FILE = os.path.join(BASE, "_sim_nav.json")
TRADE_FILE = os.path.join(BASE, "_sim_trades.json")

CAPITAL = 1_000_000.0
FEE = 0.0015                      # 单边 15bp（佣金5bp + 冲击10bp，与回测一致）
BM_CODE = "sh000985"              # 中证全指（价格指数）
BM_NAME = "中证全指"


def tx_code(code: str) -> str:
    """'002170.SZ' -> 'sz002170'"""
    c, suf = code.split(".")
    return ("sh" if suf.upper().startswith("SH") else "sz") + c


def disp_code(t: str) -> str:
    """'sz002170' -> '002170.SZ'"""
    return t[2:] + (".SH" if t.startswith("sh") else ".SZ")


def _f(x):
    try:
        return float(x)
    except Exception:
        return None


def fetch_quotes(tcodes, retries=3):
    """腾讯实时行情 qt.gtimg.cn。返回 {tcode: {name, price, prev, pct, ts, ts_date}}"""
    out = {}
    codes = list(dict.fromkeys(tcodes))
    for i in range(0, len(codes), 50):
        chunk = codes[i:i + 50]
        url = "https://qt.gtimg.cn/q=" + ",".join(chunk)
        raw = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                raw = urllib.request.urlopen(req, timeout=20).read().decode("gbk", errors="replace")
                break
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(1.5)
        for line in raw.split(";"):
            line = line.strip()
            if not line or '="' not in line:
                continue
            head, body = line.split('="', 1)
            tc = head.replace("v_", "").strip()
            f = body.rstrip('"').split("~")
            if len(f) < 33:
                continue
            price = _f(f[3])
            if price is None or price <= 0:
                continue
            ts = f[30] if len(f) > 30 else ""
            out[tc] = {
                "name": f[1],
                "price": price,
                "prev": _f(f[4]),
                "pct": _f(f[32]),
                "ts": ts,
                "ts_date": ts[:8],
            }
    return out


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def jdump(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)


def port_value(port, quotes):
    """返回 (市值, 净值, 缺行情代码列表)"""
    mv = 0.0
    missing = []
    for p in port["positions"]:
        q = quotes.get(p["tcode"])
        if q is None:
            missing.append(p["tcode"])
            mv += p["shares"] * p["cost"]
        else:
            mv += p["shares"] * q["price"]
    return mv, mv + port["cash"], missing


def upsert_nav(nav_list, entry):
    d = entry["date"]
    nav_list = [e for e in nav_list if e["date"] != d]
    nav_list.append(entry)
    nav_list.sort(key=lambda e: e["date"])
    return nav_list


def next_rebalance(yyyymmdd: str, min_gap_days: int = 90) -> str:
    """下一个调仓边界（4-30 / 8-31）。

    建仓/刚调仓后跳过本周期边界（至少隔 min_gap_days 天）：
    2026-08-26 建仓 = 2026-08 期组合 → 下次 2027-04-30；
    2027-04-30 调仓 → 下次 2027-08-31。
    """
    import datetime as _dt
    d0 = _dt.date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
    earliest = d0 + _dt.timedelta(days=min_gap_days)
    y = earliest.year
    for _ in range(3):
        for bd in (_dt.date(y, 4, 30), _dt.date(y, 8, 31)):
            if bd >= earliest:
                return f"{bd:%Y-%m-%d}"
        y += 1
    return f"{d0.year + 1}-04-30"
