"""全A（万得全A等价）轮动选股 — 妙想选股器截面 + rotation fund cycle。

数据效率路径：一次 mx_stocks_screener 查询拿到 ~950 只"增速>30% 且
上期>20%"候选的截面（四期营收真实水平 + 两期毛利率 + PE/ROE/行业/
概念/最新价），本地构造 ScreenerAdapter（DataClient 协议），然后跑
完整 LangGraph fund cycle（满仓版 rotation_full.yaml）——后续全程
本地计算，不再消耗妙想查询。

同期对齐：H1 YoY = rev(2026H1)/rev(2025H1)-1；Q1 YoY 同理；
加速 = H1 YoY > Q1 YoY（真数据，非位置对齐）。

Run:
    python examples/alla_rotation.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.data.mx_data_client import parse_cn_number
from src.data.mx_mcp_client import market_of, TOOL_SCREENER

AS_OF = "2026-08-17"
SCREENER_FILE = "_screener_allA.json"
SCREENER_Q = (
    "全部A股中，最新报告期(2026半年报)营业收入同比增速大于30%且2026一季报"
    "营收同比增速大于20%的股票，输出：股票代码、简称、最新价、"
    "2026半年报营收同比增速、2026一季报营收同比增速、2026半年报销售毛利率、"
    "2026一季报销售毛利率、市盈率TTM、ROE、东财行业总分类、所属概念，"
    "按2026半年报营收同比增速从高到低"
)


def load_screener() -> dict:
    if os.path.exists(SCREENER_FILE):
        return json.loads(open(SCREENER_FILE, encoding="utf-8").read())
    from src.data.mx_mcp_client import MXMCPClient
    sheets = MXMCPClient().query(TOOL_SCREENER, SCREENER_Q, use_cache=False)
    json.dump(sheets[0], open(SCREENER_FILE, "w", encoding="utf-8"),
              ensure_ascii=False)
    return sheets[0]


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
    i_mcap = _col(cols, "总市值")

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
            "mcap_yi": (lambda v: v / 1e8 if v and v > 1e6 else v)(_val(row, i_mcap)),
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
                row["market_cap"] = c.get("mcap_yi")
            elif d == "2026-03-31":
                row["gross_margin"] = c["gm_q1"]
            rows.append(row)
        return [r for r in rows if r["date"] <= end_date]

    def get_company_facts(self, ticker):
        c = self.by_ticker.get(ticker)
        if not c:
            return None
        # 行业是干净的匹配面；概念标签只进 description（不再参与匹配
        # ——概念 blob 会把 PCB 厂匹配进光模块）
        return {"ticker": ticker, "name": c["name"],
                "sector": c["industry"], "industry": c["industry"],
                "description": c["concept"][:200]}

    def get_earnings(self, ticker):
        return None


def main():
    sheet = load_screener()
    cands = parse_candidates(sheet)
    # 第二队列：大市值高质量中速（他的 B 类/龙头池——单一增速过滤会
    # 把中芯国际/圣邦这类 20-30% 增长的质量龙头挡在外面）
    if os.path.exists("_screener_quality_mid.json"):
        sheet2 = json.loads(open("_screener_quality_mid.json",
                                 encoding="utf-8").read())
        seen = {c["ticker"] for c in cands}
        for c in parse_candidates(sheet2):
            if c["ticker"] not in seen:
                cands.append(c)
    accel = [c for c in cands if c["accel"]]
    print(f"候选 {len(cands)} 只（选股器截面）→ 加速中 {len(accel)} 只", flush=True)

    from src.workflow.runner import run_fund_cycle
    adapter = ScreenerAdapter(cands)
    record = run_fund_cycle(
        mandate_path="config/funds/rotation_full.yaml",
        tickers=[c["ticker"] for c in cands],
        as_of=AS_OF, data_client=adapter,
    )
    fw = record.final_weights
    n_pos = sum(1 for w in fw.values() if w > 0)
    print(f"完成: {len(record.signals)}信号 {n_pos}持仓 "
          f"总仓位 {sum(w for w in fw.values() if w > 0):.1%}", flush=True)

    # ---- 报告 ----
    sig_by_tk = {s.ticker: s for s in record.signals}
    name_by_tk = {c["ticker"]: c["name"] for c in cands}
    by_link: dict[str, list] = {}
    for tk, w in sorted(fw.items(), key=lambda kv: -kv[1]):
        if w <= 0:
            continue
        s = sig_by_tk.get(tk)
        if not s or not s.metadata.get("link"):
            by_link.setdefault("自下而上/其他", []).append((tk, w, s))
        else:
            by_link.setdefault(s.metadata["link"], []).append((tk, w, s))

    print("\n方向 → 龙头持仓（每方向信念前6）")
    for link, items in sorted(by_link.items(), key=lambda kv: -sum(w for _, w, _ in kv[1])):
        lw = sum(w for _, w, _ in items)
        print(f"\n▶ {link}  方向合计 {lw:.1%}")
        for tk, w, s in items:
            m = s.metadata if s else {}
            print(f"   {tk} {name_by_tk.get(tk, ''):8s} [{m.get('asset_class','?')}]"
                  f" 权重={w:.1%} 信念={s.value:+.2f}" if s else f"   {tk} {w:.1%}")

    cls_gross = {}
    for tk, w in fw.items():
        if w <= 0:
            continue
        c = (sig_by_tk.get(tk).metadata or {}).get("asset_class") if sig_by_tk.get(tk) else None
        cls_gross[c] = cls_gross.get(c, 0) + w
    print("\n类配比: " + "  ".join(f"{k}={v:.1%}" for k, v in sorted(cls_gross.items())))
    print(f"总仓位 {sum(w for w in fw.values() if w > 0):.1%} / 满仓目标 100%")
    print(f"NAV ¥{record.nav:,.0f}   订单 {len(record.orders)} 笔")


if __name__ == "__main__":
    main()
