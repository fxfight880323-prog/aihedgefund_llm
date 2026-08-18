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
import re
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
    # 优先用户脚本刷新的最新截面（run_zhf_screener_refresh.py 的输出）
    for f in ("_screener_allA_latest.json", SCREENER_FILE):
        if os.path.exists(f):
            return json.loads(open(f, encoding="utf-8").read())
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


# 每环节龙头种子（显式点名——"买赢的环节里的龙头"的直取实现；
# 种子 = 章宏帆实际持仓 + 各环节公认龙头）
LEADER_SEEDS: dict[str, dict[str, str]] = {
    "光模块/光通信": {"中际旭创": "300308.SZ", "新易盛": "300502.SZ",
                   "天孚通信": "300394.SZ", "光迅科技": "002281.SZ",
                   "华工科技": "000988.SZ", "源杰科技": "688498.SH",
                   "剑桥科技": "603083.SH", "联特科技": "301205.SZ"},
    "PCB材料": {"沪电股份": "002463.SZ", "深南电路": "002916.SZ",
              "胜宏科技": "300476.SZ", "鹏鼎控股": "002938.SZ",
              "景旺电子": "603228.SH", "生益科技": "600183.SH",
              "生益电子": "688183.SH", "东山精密": "002384.SZ"},
    "CPU+光芯片": {"圣邦股份": "300661.SZ", "纳芯微": "688052.SH",
                "思瑞浦": "688536.SH", "卓胜微": "300782.SZ",
                "紫光国微": "002049.SZ"},
    "国产算力": {"寒武纪": "688256.SH", "海光信息": "688041.SH",
              "芯原股份": "688521.SH", "龙芯中科": "688047.SH"},
    "半导体设备": {"北方华创": "002371.SZ", "中微公司": "688012.SH",
                "华海清科": "688120.SH", "长川科技": "300604.SZ",
                "拓荆科技": "688072.SH", "盛美上海": "688082.SH"},
    "半导体材料": {"沪硅产业": "688126.SH", "安集科技": "688019.SH",
                "鼎龙股份": "300054.SZ", "中船特气": "688146.SH",
                "雅克科技": "002409.SZ"},
    "存储": {"兆易创新": "603986.SH", "江波龙": "301308.SZ",
           "佰维存储": "688525.SH", "聚辰股份": "688123.SH",
           "普冉股份": "688766.SH", "北京君正": "300223.SZ"},
    "电子制造/封测": {"立讯精密": "002475.SZ", "环旭电子": "601231.SH",
                 "顺络电子": "002138.SZ", "三环集团": "300408.SZ",
                 "长电科技": "600584.SH", "通富微电": "002156.SZ",
                 "伟测科技": "688372.SH", "闻泰科技": "600745.SH"},
}
LEADERS_FILE = "_screener_leaders.json"


def _norm_period(col: str):
    """列标签 -> (year, quarter)；兼容 中报/半年报/一季报/三季报/年报/日期。"""
    c = str(col)
    m = re.search(r"(\d{4})", c)
    if not m:
        return None
    y = int(m.group(1))
    md = re.search(r"[^\d](\d{2})[^\d]?(\d{2})?$", c) # 尾部 -MM-DD
    dm = re.search(r"(\d{4})(\d{2})(\d{2})", c)
    if "一季" in c or "Q1" in c:
        return (y, 1)
    if "中报" in c or "半年" in c:
        return (y, 2)
    if "三季" in c or "Q3" in c:
        return (y, 3)
    if "年报" in c or "年度" in c:
        return (y, 4)
    if dm:
        return (y, {3: 1, 6: 2, 9: 3, 12: 4}.get(int(dm.group(2))))
    return None


def fetch_leaders() -> list[dict]:
    """每环节逐股直取龙头全指标（环节归属由查询给定，形态无关解析）。"""
    if os.path.exists(LEADERS_FILE):
        return json.loads(open(LEADERS_FILE, encoding="utf-8").read())
    from src.data.mx_mcp_client import MXMCPClient, TOOL_ASHARE
    from src.data.mx_data_client import sheet_to_indexed
    cli = MXMCPClient()
    out = []
    for link, seeds in LEADER_SEEDS.items():
        got = 0
        for name, ticker in seeds.items():
            q = (f"{name}({ticker}) 最近4个报告期的营业收入同比增速、"
                 f"销售毛利率，以及最新的市盈率、ROE、总市值、最新收盘价")
            try:
                sheets = cli.query(TOOL_ASHARE, q, use_cache=False)
            except Exception:
                continue
            yoy_map: dict = {}
            gm_map: dict = {}
            lev_map: dict = {}
            scalars: dict = {}
            for sh in sheets:
                for metric, by_col in sheet_to_indexed(sh).items():
                    ms = str(metric)
                    for col, val in by_col.items():
                        pk = _norm_period(col)
                        v = parse_cn_number(str(val).split("|")[0])
                        if v is None:
                            continue
                        if pk:
                            if "同比" in ms and "营业收入" in ms:
                                if abs(v) > 1.5:
                                    v /= 100.0
                                yoy_map.setdefault(pk, v)
                            elif "营业收入" in ms:
                                lev_map.setdefault(pk, v)
                            elif "毛利率" in ms:
                                gm_map.setdefault(pk, v)
                            elif ("ROE" in ms or "净资产收益率" in ms):
                                scalars.setdefault("roe", v)  # 首个=最新期
                        else:
                            if "市盈" in ms:
                                scalars.setdefault("pe", v)
                            elif "市值" in ms:
                                scalars.setdefault("mcap", v)
                            elif "ROE" in ms or "净资产收益率" in ms:
                                scalars.setdefault("roe", v)
                            elif "收盘" in ms or "最新" in ms:
                                scalars.setdefault("price", v)
            if not yoy_map and lev_map:
                for (y, qq), v in lev_map.items():
                    prev = lev_map.get((y - 1, qq))
                    if prev and prev > 0:
                        yoy_map[(y, qq)] = v / prev - 1.0
            if not yoy_map:
                continue
            # 取最新两个已披露同比点（中报未必已披露——妙想序列可能
            # 最新只到一季报；YoY 本身已是同期对齐值，跨窗口比较方向性成立）
            points = sorted(yoy_map.items(), reverse=True)
            (g_h1, g_q1) = (points[0][1],
                            points[1][1] if len(points) > 1
                            else points[0][1] - 0.01)
            gm_points = sorted(gm_map.items(), reverse=True)
            gm_h1 = gm_points[0][1] if gm_points else None
            gm_q1 = (gm_points[1][1] if len(gm_points) > 1
                     else gm_h1)
            mcap = scalars.get("mcap")
            if mcap and mcap > 1e6:
                mcap /= 1e8
            out.append({
                "ticker": ticker, "code": ticker[:6], "name": name,
                "price": scalars.get("price"),
                "rev": {"2026-06-30": 1 + g_h1, "2025-06-30": 1.0,
                        "2026-03-31": 1 + g_q1, "2025-03-31": 1.0},
                "gm_h1": gm_h1, "gm_q1": gm_q1, "pe": scalars.get("pe"),
                "roe": scalars.get("roe"), "mcap_yi": mcap,
                "industry": "", "concept": "",
                "h1_yoy": g_h1, "q1_yoy": g_q1, "accel": g_h1 > g_q1,
                "leader_link": link,
            })
            got += 1
        print(f"  [{link}] {got}/{len(seeds)} 只龙头", flush=True)
    json.dump(out, open(LEADERS_FILE, "w", encoding="utf-8"),
              ensure_ascii=False)
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
        # 龙头直取的环节由查询给定（assigned_link 优先于关键词匹配）
        return {"ticker": ticker, "name": c["name"],
                "sector": c["industry"], "industry": c["industry"],
                "description": c["concept"][:200],
                "link": c.get("leader_link")}

    def get_earnings(self, ticker):
        return None


def main():
    sheet = load_screener()
    cands = parse_candidates(sheet)
    # 第二队列：大市值高质量中速（他的 B 类/龙头池——单一增速过滤会
    # 把中芯国际/圣邦这类 20-30% 增长的质量龙头挡在外面）；文件缺失
    # 自动补查（并行脚本可能清理中间文件）
    q2 = "_screener_quality_mid.json"
    try:
        if not os.path.exists(q2):
            from src.data.mx_mcp_client import MXMCPClient
            sheets = MXMCPClient().query(TOOL_SCREENER,
                "全部A股中，总市值大于150亿、ROE大于12%、销售毛利率大于30%、"
                "2026半年报营业收入同比增速大于8%的股票，输出：股票代码、"
                "简称、最新价、2026半年报营收同比增速、2026一季报营收同比"
                "增速、2026半年报销售毛利率、2026一季报销售毛利率、市盈率"
                "TTM、ROE、东财行业总分类、总市值，按总市值从大到小",
                use_cache=False)
            json.dump(sheets[0], open(q2, "w", encoding="utf-8"),
                      ensure_ascii=False)
        sheet2 = json.loads(open(q2, encoding="utf-8").read())
        seen = {c["ticker"] for c in cands}
        for c in parse_candidates(sheet2):
            if c["ticker"] not in seen:
                cands.append(c)
    except Exception as exc:
        print(f"  [队列2 高质量中速] 跳过: {exc}", flush=True)
    # 第三队列：电子制造/元件/封测域（B 类 sleeve 的候选面——
    # 前两个队列的增速口径把它们挡在外面）
    q3 = "_screener_elec_mfg.json"
    try:
        if not os.path.exists(q3):
            from src.data.mx_mcp_client import MXMCPClient
            sheets = MXMCPClient().query(TOOL_SCREENER,
                "全部A股中属于消费电子、电子元件、半导体封测行业的股票，"
                "总市值大于80亿，2026半年报或最新报告期营业收入同比增速"
                "大于5%，输出：股票代码、简称、最新价、2026半年报营收同比"
                "增速、2026一季报营收同比增速、2026半年报销售毛利率、"
                "2026一季报销售毛利率、市盈率TTM、ROE、总市值、东财行业"
                "总分类，按总市值从大到小", use_cache=False)
            json.dump(sheets[0], open(q3, "w", encoding="utf-8"),
                      ensure_ascii=False)
        sheet3 = json.loads(open(q3, encoding="utf-8").read())
        seen3 = {c["ticker"] for c in cands}
        for c in parse_candidates(sheet3):
            if c["ticker"] not in seen3:
                cands.append(c)
    except Exception as exc:
        print(f"  [队列3 电子制造域] 跳过: {exc}", flush=True)
    # 龙头直取（主池）：环节归属由查询给定，龙头全指标
    print("龙头直取:", flush=True)
    leaders = fetch_leaders()
    ld = {c["ticker"]: c for c in leaders}
    cands = [ld.get(c["ticker"], c) if c["ticker"] not in ld else ld[c["ticker"]]
             for c in cands] + [c for t, c in ld.items()
                               if not any(x["ticker"] == t for x in cands)]
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
