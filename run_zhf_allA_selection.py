"""zhanghongfan（章宏帆）策略 — wind 全A universe 满仓选股执行脚本。

流程（严格复用框架路径，不引入自定义逻辑）：
  1. 读取妙想选股器全A截面（2026-08-17，H1营收YoY>30% 且 Q1营收YoY>20%）
  2. parse_candidates → ScreenerAdapter（DataClient 协议，本地零额外查询）
  3. run_fund_cycle(rotation_full.yaml) —— 该 mandate 只含 rotation_growth
     一个模型（weight=1.0），blend=balanced_sharpness，gross_target=1.0 满仓
  4. 保存完整 CycleRecord 到 JSON（供报告生成）

Run:
    D:\\Python\\python.exe run_zhf_allA_selection.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from src.data.mx_data_client import parse_cn_number
from src.data.mx_mcp_client import market_of

AS_OF = "2026-08-17"
SCREENER_FILE = "_screener_allA_latest.json"
OUT_JSON = "zhf_allA_selection_result.json"


# ---------------------------------------------------------------------------
# 截面解析（与 examples/alla_rotation.py 同一套逻辑）
# ---------------------------------------------------------------------------

def _col(columns: list[str], *needles: str) -> int | None:
    for i, c in enumerate(columns):
        if all(n in c for n in needles):
            return i
    return None


def _val(row, i):
    if i is None or i >= len(row):
        return None
    return parse_cn_number(str(row[i]).split("|")[0])


def parse_candidates(sheet: dict) -> list[dict]:
    cols = sheet["columns"]
    i_code = _col(cols, "代码")
    i_name = _col(cols, "简称")
    i_px = _col(cols, "最新价")
    i_rev26h = _col(cols, "营业总收入", "2026.06.30") or _col(cols, "营业收入", "2026.06.30")
    i_rev25h = _col(cols, "营业总收入", "2025.06.30") or _col(cols, "营业收入", "2025.06.30")
    i_rev26q = _col(cols, "营业总收入", "2026.03.31") or _col(cols, "营业收入", "2026.03.31")
    i_rev25q = _col(cols, "营业总收入", "2025.03.31") or _col(cols, "营业收入", "2025.03.31")
    i_gm_h = _col(cols, "毛利率", "半年报") or _col(cols, "毛利率")
    i_gm_q = _col(cols, "毛利率", "一季报")
    i_pe = _col(cols, "市盈率")
    i_roe = _col(cols, "ROE") or _col(cols, "净资产收益率")
    i_ind = _col(cols, "东财行业")
    i_concept = _col(cols, "概念")

    out = []
    for row in sheet["items"]:
        code = str(row[i_code]).strip() if i_code is not None else ""
        if not code or not code[:6].isdigit():
            continue
        suffix = {"SH": ".SH", "SZ": ".SZ", "BJ": ".BJ"}.get(market_of(code))
        if not suffix:
            continue
        r26h, r25h = _val(row, i_rev26h), _val(row, i_rev25h)
        r26q, r25q = _val(row, i_rev26q), _val(row, i_rev25q)
        if not all(v and v > 0 for v in (r26h, r25h, r26q, r25q)):
            continue
        h1_yoy = r26h / r25h - 1.0
        q1_yoy = r26q / r25q - 1.0
        name = str(row[i_name]).strip() if i_name is not None else ""
        concept = str(row[i_concept]) if i_concept is not None and i_concept < len(row) else ""
        industry = str(row[i_ind]) if i_ind is not None and i_ind < len(row) else ""
        out.append({
            "ticker": code[:6] + suffix, "code": code, "name": name,
            "price": _val(row, i_px),
            "rev": {"2026-06-30": r26h, "2025-06-30": r25h,
                    "2026-03-31": r26q, "2025-03-31": r25q},
            "gm_h1": _val(row, i_gm_h), "gm_q1": _val(row, i_gm_q),
            "pe": _val(row, i_pe), "roe": _val(row, i_roe),
            "industry": industry, "concept": concept[:200],
            "h1_yoy": h1_yoy, "q1_yoy": q1_yoy,
            "accel": h1_yoy > q1_yoy,
        })
    return out


class ScreenerAdapter:
    """把选股器截面包装成 DataClient——fund cycle 全程本地计算。"""

    def __init__(self, cands: list[dict]):
        self.by_ticker = {c["ticker"]: c for c in cands}

    def get_prices(self, ticker, start_date, end_date):
        c = self.by_ticker.get(ticker)
        if not c or not c.get("price"):
            return []
        return [{"time": AS_OF, "open": c["price"], "high": c["price"],
                 "low": c["price"], "close": c["price"], "volume": 1e6,
                 "amount": 1e8}]

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        c = self.by_ticker.get(ticker)
        if not c:
            return []
        rows = []
        for d, rev in c["rev"].items():
            row = {"ticker": ticker, "date": d, "period": period,
                   "revenue": rev}
            if d == "2026-06-30":
                row["gross_margin"] = c["gm_h1"]
                row["pe_ratio"] = c["pe"]
                row["roe"] = c["roe"]
            elif d == "2026-03-31":
                row["gross_margin"] = c["gm_q1"]
            rows.append(row)
        return [r for r in rows if r["date"] <= end_date]

    def get_company_facts(self, ticker):
        c = self.by_ticker.get(ticker)
        if not c:
            return None
        return {"ticker": ticker, "name": c["name"],
                "sector": f"{c['industry']} {c['concept'][:80]}",
                "industry": c["industry"]}

    def get_earnings(self, ticker):
        return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    t0 = datetime.now()
    sheet = json.loads(open(SCREENER_FILE, encoding="utf-8").read())
    cands = parse_candidates(sheet)
    accel = [c for c in cands if c["accel"]]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 候选 {len(cands)} 只（全A截面）"
          f" → 加速中 {len(accel)} 只", flush=True)

    from src.workflow.runner import run_fund_cycle

    adapter = ScreenerAdapter(cands)
    record = run_fund_cycle(
        mandate_path="config/funds/rotation_full.yaml",
        tickers=[c["ticker"] for c in cands],
        as_of=AS_OF,
        data_client=adapter,
    )
    fw = record.final_weights
    n_pos = sum(1 for w in fw.values() if w > 0)
    gross = sum(w for w in fw.values() if w > 0)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 完成: {len(record.signals)}信号 "
          f"{n_pos}持仓 总仓位 {gross:.1%}", flush=True)

    # ---- 汇总报告数据结构 ----
    sig_by_tk = {s.ticker: s for s in record.signals}
    name_by_tk = {c["ticker"]: c["name"] for c in cands}
    info_by_tk = {c["ticker"]: c for c in cands}

    positions = []
    for tk, w in sorted(fw.items(), key=lambda kv: -kv[1]):
        if w <= 0:
            continue
        s = sig_by_tk.get(tk)
        m = s.metadata if s else {}
        info = info_by_tk.get(tk, {})
        positions.append({
            "ticker": tk, "name": name_by_tk.get(tk, ""),
            "weight": round(w, 4),
            "value": round(s.value, 4) if s else None,
            "asset_class": m.get("asset_class"),
            "link": m.get("link"),
            "link_score": m.get("link_score"),
            "growth": m.get("growth") if m else None,
            "h1_yoy": info.get("h1_yoy"),
            "q1_yoy": info.get("q1_yoy"),
            "pe": info.get("pe"),
            "gm_h1": info.get("gm_h1"),
            "roe": info.get("roe"),
            "industry": info.get("industry"),
            "concept": (info.get("concept") or "")[:120],
            "reasoning": s.reasoning if s else None,
        })

    by_link: dict[str, list] = {}
    for p in positions:
        by_link.setdefault(p["link"] or "自下而上/其他", []).append(p)
    link_summary = {
        link: {"names": len(items),
               "gross": round(sum(p["weight"] for p in items), 4),
               "avg_value": round(sum(p["value"] for p in items) / len(items), 4)}
        for link, items in by_link.items()
    }

    cls_gross = {}
    for p in positions:
        cls_gross[p["asset_class"]] = cls_gross.get(p["asset_class"], 0.0) + p["weight"]

    result = {
        "as_of": AS_OF,
        "run_at": datetime.now().isoformat(),
        "mandate": "config/funds/rotation_full.yaml",
        "models": ["rotation_growth (章宏帆, weight=1.0)"],
        "universe_size": len(cands),
        "candidates": [{"ticker": c["ticker"], "name": c["name"],
                        "h1_yoy": round(c["h1_yoy"], 4), "q1_yoy": round(c["q1_yoy"], 4),
                        "accel": c["accel"], "industry": c["industry"]}
                       for c in cands],
        "signal_count": len(record.signals),
        "abstain_count": sum(1 for s in record.signals if s.metadata.get("abstained")),
        "position_count": n_pos,
        "gross": round(gross, 4),
        "class_mix": {k: round(v, 4) for k, v in cls_gross.items()},
        "link_summary": link_summary,
        "positions": positions,
        "nav": record.nav,
        "orders": len(record.orders),
        "skipped": record.metadata.get("skipped", []),
        "errors": record.metadata.get("errors", []),
    }
    json.dump(result, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 结果已保存 -> {OUT_JSON}", flush=True)
    print(f"耗时 {(datetime.now() - t0).total_seconds():.0f}s")


if __name__ == "__main__":
    main()
