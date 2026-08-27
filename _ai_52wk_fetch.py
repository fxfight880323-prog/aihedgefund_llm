"""AI 产业链 × 距52周高点距离(dist52) — 数据拉取与计算。

股票池: 12 个聚源产业概念板块合并去重 (_ai_pool.json, ~1400 只)
价格:   腾讯月K qfq (2025-07 ~ 2026-08)
行情:   qt.gtimg.cn 批量快照(名称/最新价/涨跌幅/总市值)
信号:   dist52 = 最新月收盘 / 过去12个月(含当月)月K最高收盘
输出:   _ai_52wk_rank.json (全部排序) + _ai_52wk_quote.json + _ai_52wk_kline.json
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

POOL_FILE = "_ai_pool.json"
KLINE_FILE = "_ai_52wk_kline.json"
QUOTE_FILE = "_ai_52wk_quote.json"
OUT_FILE = "_ai_52wk_rank.json"

START, END = "2025-07-01", "2026-08-21"
HOSTS = ["https://ifzq.gtimg.cn", "https://web.ifzq.gtimg.cn"]
TIMEOUT = 15
WORKERS = 12

SECTOR_CN = {
    "pt02003800": "人工智能",
    "pt02GN2006": "东数西算/算力",
    "pt02GN2196": "AIGC",
    "pt02GN2211": "CPO",
    "pt02GN2222": "AI算力芯片",
    "pt02GN2228": "人工智能大模型",
    "pt02GN2234": "算力租赁",
    "pt02GN2266": "华为算力",
    "pt02GN2287": "AIPC",
    "pt02GN2298": "AI语料",
    "pt02GN2313": "AI眼镜",
    "pt02GN2343": "AI应用",
    "pt02GN2354": "AI智能体",
}


def fetch_monthly(sym: str) -> dict[str, float] | None:
    """腾讯月K qfq → {YYYY-MM: close}。sym 形如 sz301259。"""
    for host in HOSTS:
        url = (f"{host}/appstock/app/fqkline/get"
               f"?param={sym},month,{START},{END},24,qfq")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = json.loads(
                urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8"))
            data = raw.get("data") or {}
            sub = data.get(sym, {}) if isinstance(data, dict) else {}
            rows = sub.get("qfqmonth") or sub.get("month") or []
            out = {}
            for r in rows:
                if len(r) >= 3 and r[0] and float(r[2]) > 0:
                    out[r[0][:7]] = float(r[2])
            if out:
                return out
        except Exception:
            pass
    return None


def fetch_quotes(syms: list[str]) -> dict[str, dict]:
    """qt.gtimg.cn 批量行情 → {code: {name, price, pct, mv}}."""
    out: dict[str, dict] = {}
    for i in range(0, len(syms), 60):
        batch = syms[i:i + 60]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            txt = urllib.request.urlopen(req, timeout=15).read().decode("gbk", "ignore")
            for line in txt.split(";"):
                line = line.strip()
                if not line.startswith("v_"):
                    continue
                key, _, rest = line.partition("=")
                code = key[2:].strip()
                f = rest.strip('"').split("~")
                if len(f) < 46:
                    continue
                out[code] = {
                    "name": f[1],
                    "price": float(f[3] or 0),
                    "pct": float(f[32] or 0),
                    "mv": float(f[45] or 0),   # 总市值(亿)
                    "mvc": float(f[44] or 0),  # 流通市值(亿)
                }
        except Exception as e:
            print(f"  quote batch {i} 失败: {str(e)[:80]}")
        time.sleep(0.3)
    return out


def compute_dist52(kline: dict[str, float]) -> dict | None:
    """月度口径 dist52: 最新月收盘 / 过去12个月(含当月)最高收盘."""
    if not kline:
        return None
    months = sorted(kline)
    if len(months) < 12:
        return None
    cur_m = months[-1]
    px = kline[cur_m]
    win = [kline[m] for m in months[-12:]]
    hi = max(win)
    if hi <= 0:
        return None
    return {"month": cur_m, "close": px, "hi52": hi,
            "dist52": px / hi, "drawdown": px / hi - 1.0}


def main():
    pool = json.loads(open(POOL_FILE, encoding="utf-8").read())
    syms = sorted(pool.keys())
    print(f"AI产业链池: {len(syms)} 只")

    # 板块标签: code -> [中文板块名]
    tags: dict[str, list[str]] = {}
    for code, secs in pool.items():
        names = []
        for s in secs:
            short = s.replace("comp_indus_", "").replace("comp_", "")
            names.append(SECTOR_CN.get(short, short))
        tags[code] = sorted(names)

    # ---- 1. 月K ----
    kline = {}
    if os.path.exists(KLINE_FILE):
        kline = json.loads(open(KLINE_FILE, encoding="utf-8").read())
        print(f"  月K缓存 {len(kline)} 只")
    todo = [s for s in syms if s not in kline]
    if todo:
        t0 = time.time()
        ok = 0
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(fetch_monthly, s): s for s in todo}
            for i, fut in enumerate(cf.as_completed(futs), 1):
                s = futs[fut]
                try:
                    m = fut.result()
                except Exception:
                    m = None
                if m:
                    kline[s] = m
                    ok += 1
                if i % 300 == 0:
                    print(f"  {i}/{len(todo)} 完成 ok={ok} 耗时{time.time()-t0:.0f}s", flush=True)
                    json.dump(kline, open(KLINE_FILE, "w", encoding="utf-8"))
        print(f"  月K完成: {ok}/{len(todo)}, 耗时 {time.time()-t0:.0f}s")
        json.dump(kline, open(KLINE_FILE, "w", encoding="utf-8"))

    # ---- 2. 行情快照 ----
    quotes = {}
    if os.path.exists(QUOTE_FILE):
        quotes = json.loads(open(QUOTE_FILE, encoding="utf-8").read())
    miss = [s for s in syms if s not in quotes]
    if miss:
        q = fetch_quotes(miss)
        quotes.update(q)
        json.dump(quotes, open(QUOTE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  行情快照: {len(quotes)} 只")

    # ---- 3. 计算 dist52 ----
    rows = []
    for s in syms:
        d52 = compute_dist52(kline.get(s, {}))
        q = quotes.get(s, {})
        rows.append({
            "code": s[2:],
            "sym": s,
            "name": q.get("name", s),
            "price": q.get("price"),
            "pct": q.get("pct"),
            "mv": q.get("mv"),
            "mvc": q.get("mvc"),
            "month": d52["month"] if d52 else None,
            "close": d52["close"] if d52 else None,
            "hi52": d52["hi52"] if d52 else None,
            "dist52": d52["dist52"] if d52 else None,
            "dd52": d52["drawdown"] if d52 else None,
            "sectors": tags.get(s, []),
            "n_sector": len(tags.get(s, [])),
        })

    rows.sort(key=lambda r: (r["dist52"] is not None, -(r["dist52"] or 0)))
    json.dump(rows, open(OUT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = len([r for r in rows if r["dist52"] is not None])
    print(f"\n完成: {n}/{len(rows)} 只有 dist52, 已写 {OUT_FILE}")

    print("\nTop 15 距52周高点近:")
    for r in rows[:15]:
        print(f"  {r['sym']} {r['name']:8s} dist52={r['dist52']:.3f} "
              f"dd={r['dd52']:+.1%} price={r['price']} mv={r['mv']:.0f}亿 {'/'.join(r['sectors'][:2])}")


if __name__ == "__main__":
    main()
