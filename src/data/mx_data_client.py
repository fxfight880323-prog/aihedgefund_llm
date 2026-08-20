"""DataClient-protocol adapter for the 妙想 (MX) MCP service.

`MXDataClient` implements the four `DataClient` methods
(get_prices / get_financial_metrics / get_company_facts / get_earnings)
by translating each call into a natural-language 妙想 query, so a 妙想-backed
data source drops into the fund workflow graph exactly like
`FinancialDatasetsClient`.

The 妙想 service speaks natural language and returns Chinese-mixed strings
("1.691万亿", "6.254倍"), so this adapter also normalizes values into plain
floats where it can.

Note: 妙想 is strongest for A-shares / HK / China macro. For US tickers it
still works via the mx_us tool but field names come back in Chinese.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.interfaces import DataClient  # structural protocol, for docs
from src.data.cache import DiskCache
from src.data.mx_mcp_client import (
    MXMCPClient,
    TOOL_ASHARE,
    parse_cn_number,
    sheet_to_indexed,
    tool_for_ticker,
)


class MXDataClient:
    """DataClient implementation backed by 妙想 MCP.

    Methods follow the same contract as FinancialDatasetsClient:
      - get_prices(ticker, start_date, end_date) -> list[{time, open, ...}]
      - get_financial_metrics(ticker, end_date, period, limit) -> list[dict]
      - get_company_facts(ticker) -> dict | None
      - get_earnings(ticker) -> dict | None

    Use the low-level `client` attribute (an MXMCPClient) for arbitrary
    natural-language queries, news, filings, screeners, etc.
    """

    def __init__(
        self,
        api_key: str | None = None,
        cache: DiskCache | None = None,
        client: MXMCPClient | None = None,
    ):
        self.client = client or MXMCPClient(api_key=api_key, cache=cache)
        self._cache = cache or self.client._cache

    # ------------------------------------------------------------------
    # DataClient protocol
    # ------------------------------------------------------------------

    def get_prices(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Return daily OHLCV bars as
        {"time", "open", "high", "low", "close", "volume"}.
        """
        sheets = self.client.query(
            tool_for_ticker(ticker),
            f"{ticker} 从 {start_date} 到 {end_date} 每个交易日的"
            f"开盘价、最高价、最低价、收盘价、成交量、成交额",
        )
        bars: list[dict[str, Any]] = []
        for sheet in sheets:
            indexed = sheet_to_indexed(sheet)
            # Build a {date: value} map per metric.
            opens = _row_by_date(indexed, _is_open)
            highs = _row_by_date(indexed, _is_high)
            lows = _row_by_date(indexed, _is_low)
            closes = _row_by_date(indexed, _is_close)
            vols = _row_by_date(indexed, _is_volume)
            amounts = _row_by_date(indexed, _is_amount)
            dates = sorted(
                set(closes) | set(opens) | set(highs) | set(lows)
                | set(vols) | set(amounts)
            )
            for d in dates:
                # Skip non-date header columns (e.g. the ticker column).
                if not _looks_like_date(d):
                    continue
                bars.append(
                    {
                        "time": _normalize_date(d),
                        "open": parse_cn_number(opens.get(d, "")),
                        "high": parse_cn_number(highs.get(d, "")),
                        "low": parse_cn_number(lows.get(d, "")),
                        "close": parse_cn_number(closes.get(d, "")),
                        "volume": parse_cn_number(vols.get(d, "")),
                        "amount": parse_cn_number(amounts.get(d, "")),
                    }
                )
        bars.sort(key=lambda b: b["time"])
        return bars

    def get_financial_metrics(
        self, ticker: str, end_date: str, period: str = "ttm", limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return fundamental metrics (PE, PB, ROE, margins, ...).

        妙想 splits valuation (PE/PB — daily, from the market) and statement
        metrics (ROE / margins / revenue — quarterly, from filings) across
        different responses, so we issue two queries and merge them by date.
        We then keep the most recent `limit` dates.
        """
        # Query 1: daily valuation series.
        val_sheets = self.client.query(
            tool_for_ticker(ticker),
            f"{ticker} 截至 {end_date} 的市盈率PE(TTM)、市净率PB",
        )
        # Query 2: quarterly statement series (ROE, margins, revenue, income).
        fin_sheets = self.client.query(
            tool_for_ticker(ticker),
            f"{ticker} 最近{limit}个报告期的净资产收益率ROE、销售毛利率、"
            f"销售净利率、营业收入、净利润",
        )

        # Build {date: {metric_key: value}} across both result sets.
        by_date: dict[str, dict[str, Any]] = {}

        for sheet in val_sheets + fin_sheets:
            cols = sheet.get("columns", [])
            date_cols = [c for c in cols if _looks_like_date(c)]
            if not date_cols:
                continue
            for row in sheet.get("items", []):
                if not row:
                    continue
                metric = str(row[0])
                key = _metric_key(metric)
                for col, val in zip(cols[1:], row[1:]):
                    if not _looks_like_date(col):
                        continue
                    d = _normalize_date(col)
                    by_date.setdefault(d, {})
                    if key not in by_date[d]:
                        parsed = parse_cn_number(val)
                        by_date[d][key] = parsed if parsed is not None else val

        # Keep the most recent `limit` dates that carry at least one metric.
        kept = sorted(by_date.keys(), reverse=True)[:limit]
        metrics_list: list[dict[str, Any]] = []
        for d in kept:
            row = {"ticker": ticker, "date": d, "period": period}
            row.update(by_date[d])
            metrics_list.append(row)
        return metrics_list

    def get_company_facts(self, ticker: str) -> dict[str, Any] | None:
        """Return company description, sector, industry, etc.

        妙想 spreads company facts across multiple sheets, each shaped like a
        key/value table (label column + value column). We aggregate every
        label/value pair we can find, then lift the common fields into
        canonical keys. The 「公司基本信息」cell embeds more fields as inline
        【字段】值 text, which we also parse.
        """
        sheets = self.client.query(
            tool_for_ticker(ticker),
            f"{ticker} 的公司基本资料：公司简称、所属行业、上市日期、"
            f"公司简介、主营业务、注册地址、办公地址、实际控制人、公司基本信息",
        )

        # 1. Collect label -> value pairs from every key/value-style sheet.
        # A facts sheet has exactly two non-date columns (label + value);
        # multi-column tables like 主营构成分析 must be skipped.
        raw: dict[str, str] = {}
        header_name: str | None = None  # e.g. "贵州茅台(600519.SH)"
        for sheet in sheets:
            cols = sheet.get("columns", [])
            value_cols = [c for c in cols if not _looks_like_date(c)]
            if len(value_cols) != 2:
                continue
            # The first column header usually carries the entity name.
            if header_name is None and cols:
                header_name = str(cols[0])
            for row in sheet.get("items", []):
                if not row:
                    continue
                label, val = row[0], row[1] if len(row) > 1 else ""
                if label and val not in (None, ""):
                    raw[str(label)] = str(val)

        if not raw:
            return None

        # 2. Parse the inline 【字段】值 text if present.
        info_blob = raw.get("公司基本信息") or ""
        inline = _parse_bracket_fields(info_blob)
        raw.update(inline)

        def pick(*keys: str) -> str | None:
            for k in keys:
                if raw.get(k):
                    return raw[k]
            return None

        # 3. Fall back to the sheet header for the entity name, and strip the
        # trailing (code) suffix: "贵州茅台(600519.SH)" -> "贵州茅台".
        resolved_name = pick("股票简称", "公司简称", "机构简称")
        if resolved_name is None and header_name:
            resolved_name = re.sub(r"[(（].*?[)）]\s*$", "", header_name).strip()

        return {
            "ticker": ticker,
            "name": resolved_name,
            "sector": pick("所属行业", "行业") or pick("国民经济行业分类"),
            "industry": pick("国民经济行业分类", "所属行业", "行业"),
            "listing_date": pick("首发上市日", "上市日期", "成立日期"),
            "description": pick("公司简介", "主营业务", "主营产品"),
            "controller": pick("实际控制人"),
            "address": pick("办公地址", "注册地址"),
            "raw": raw,
        }

    def get_earnings(self, ticker: str) -> dict[str, Any] | None:
        """Return earnings data (announcements / actuals)."""
        sheets = self.client.query(
            tool_for_ticker(ticker),
            f"{ticker} 最近4个报告期的营业收入、净利润及同比增速",
        )
        series: dict[str, dict[str, Any]] = {}
        for sheet in sheets:
            for metric, by_date in sheet_to_indexed(sheet).items():
                series.setdefault(metric, {}).update(by_date)
        if not series:
            return None
        return {"ticker": ticker, "series": series}

    # ------------------------------------------------------------------
    # Optional capability beyond the DataClient protocol: L1 深研需要的
    # 主营构成 / 客户集中度。growth_loop 的 build_data_packet 通过
    # hasattr 探测调用；其他 data client 可不实现。
    # ------------------------------------------------------------------

    def get_segment_breakdown(self, ticker: str) -> str | None:
        """主营构成文本块：各产品/业务收入、占比、毛利率 + 前五大客户占比。"""
        try:
            sheets = self.client.query(
                tool_for_ticker(ticker),
                f"{ticker} 最新报告期主营构成：各产品/业务板块的营业收入、"
                f"收入占比、毛利率，以及前五大客户合计收入占比",
            )
        except Exception:
            return None
        lines: list[str] = []
        for sheet in sheets:
            cols = [c for c in sheet.get("columns", [])]
            if "证券代码" in cols or len(cols) < 2:
                # key/value 型 sheet（如前五大客户占比）
                for row in sheet.get("items", []):
                    if row and len(row) >= 2 and row[1] not in (None, ""):
                        lines.append(f"  {row[0]}: {row[1]}")
                continue
            lines.append(f"  [{' | '.join(str(c) for c in cols[:4])}]")
            for row in sheet.get("items", [])[:12]:
                if row:
                    lines.append("  " + " | ".join(str(c) for c in row[:4]))
        return "\n".join(lines) if lines else None

    # ------------------------------------------------------------------
    # 数据完整性原则的取数层落地：L3/L5/L6 必需的利润表/现金流/
    # 资产负债表明细。带绕缓存重试；仍取不到的字段由 build_data_packet
    # 显式声明为 DATA GAP（禁止静默缺失）。
    # ------------------------------------------------------------------

    def get_financial_detail(self, ticker: str) -> str | None:
        """财务明细文本块（季度序列 + 快照）— L3/L5/L6 的核心输入。

        序列: 营业利润、研发/销售/管理费用、经营现金流净额、资本开支
        快照: 总股本、总市值、货币资金、有息负债、股份支付费用
        """
        tool = tool_for_ticker(ticker)
        q_series = (
            f"{ticker} 最近8个报告期的营业利润、研发费用、销售费用、"
            f"管理费用、经营活动产生的现金流量净额、购建固定资产、"
            f"无形资产和其他长期资产支付的现金"
        )
        q_snapshot = (
            f"{ticker} 最新的总股本、总市值、货币资金、短期借款、"
            f"长期借款、股份支付费用"
        )

        lines: list[str] = []
        for label, q in (("SERIES", q_series), ("SNAPSHOT", q_snapshot)):
            sheets = []
            for attempt in (1, 2):  # 完整性原则：空响应绕缓存重试一次
                try:
                    sheets = self.client.query(tool, q, use_cache=(attempt == 1))
                except Exception:
                    sheets = []
                if sheets:
                    break
            if not sheets:
                lines.append(f"  [{label}] FETCH-UNAVAILABLE")
                continue
            lines.append(f"  [{label}]")
            for sheet in sheets:
                for metric, by_col in sheet_to_indexed(sheet).items():
                    pairs = sorted(
                        ((c, v) for c, v in by_col.items()
                         if v not in (None, "") and _looks_like_date(c)),
                        key=lambda cv: _normalize_date(cv[0]),
                        reverse=True,
                    )
                    if not pairs:
                        continue
                    shown = " | ".join(f"{c}={v}" for c, v in pairs[:8])
                    lines.append(f"    {metric}: {shown}")
        return "\n".join(lines) if len(lines) > 2 else None

    # ------------------------------------------------------------------
    # F-Score data: fetch all 9 Piotroski components + valuation metrics.
    # Used by FScoreModel (src/signals/f_score.py) in live mode.
    # ------------------------------------------------------------------

    def get_f_score_metrics(
        self, ticker: str, end_date: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return F-Score component metrics for Piotroski & So (2012).

        Fetches both daily valuation (PE, PB) and annual statement
        metrics (ROA, CFO, debt ratio, current ratio, asset turnover,
        shares, gross margin, revenue, net income, total assets),
        merged by date/period.

        Returns a list of dicts sorted newest-first, each containing:
          ticker, date, period, pe_ratio, pb_ratio,
          roa, cfo, cfo_ta, debt_ratio, current_ratio,
          shares, gross_margin, asset_turnover,
          revenue, net_income, total_assets
        """
        tool = tool_for_ticker(ticker)

        # Query 1: daily valuation (PE/PB) -- reuse existing pattern
        val_sheets = self.client.query(
            tool,
            f"{ticker} 截至 {end_date} 的市盈率PE(TTM)、市净率PB",
        )

        # Query 2: annual statement series for F-score components
        # ROA, CFO, debt ratio, current ratio, asset turnover, shares,
        # gross margin, revenue, net income, total assets
        fin_sheets = self.client.query(
            tool,
            f"{ticker} 最近{limit}个年度的"
            f"总资产收益率ROA、"
            f"经营活动产生的现金流量净额、"
            f"资产负债率、"
            f"流动比率、"
            f"总资产周转率、"
            f"总股本、"
            f"销售毛利率、"
            f"营业收入、"
            f"净利润、"
            f"总资产",
        )

        # Build {date: {metric_key: value}} across both result sets
        by_date: dict[str, dict[str, Any]] = {}

        for sheet in val_sheets + fin_sheets:
            cols = sheet.get("columns", [])
            date_cols = [c for c in cols if _looks_like_date(c)]
            if not date_cols:
                continue
            for row in sheet.get("items", []):
                if not row:
                    continue
                metric = str(row[0])
                key = _f_score_metric_key(metric)
                for col, val in zip(cols[1:], row[1:]):
                    if not _looks_like_date(col):
                        continue
                    d = _normalize_date(col)
                    by_date.setdefault(d, {})
                    if key not in by_date[d]:
                        parsed = parse_cn_number(val)
                        by_date[d][key] = (parsed if parsed is not None
                                           else val)

        # Also compute cfo_ta (CFO / total assets) as a derived field
        for d, row in by_date.items():
            cfo = row.get("cfo")
            ta = row.get("total_assets")
            if cfo is not None and ta is not None and ta > 0:
                # CFO is in yuan, total_assets may be in yuan or wan yuan
                # MX returns both in yuan typically
                row["cfo_ta"] = (float(cfo) / float(ta)) * 100.0

        kept = sorted(by_date.keys(), reverse=True)[:limit]
        metrics_list: list[dict[str, Any]] = []
        for d in kept:
            row = {"ticker": ticker, "date": d, "period": "annual"}
            row.update(by_date[d])
            metrics_list.append(row)
        return metrics_list


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

# Row-label matchers for OHLCV. 妙想 uses Chinese labels.
def _is_open(label: str) -> bool:
    return "开盘" in label


def _is_high(label: str) -> bool:
    return "最高" in label


def _is_low(label: str) -> bool:
    return "最低" in label


def _is_close(label: str) -> bool:
    return "收盘" in label


def _is_volume(label: str) -> bool:
    return "成交量" in label or "手数" in label


def _is_amount(label: str) -> bool:
    return "成交额" in label or "成交金额" in label


_DATE_RES = (
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),                 # 2026-08-13
    re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"),                 # 2026/08/13
    re.compile(r"(\d{4})(\d{2})(\d{2})"),                       # 20260813
)

# Reporting-period labels: 2025年报 / 2026一季报 / 2025中报 / 2025三季报 / 2025半年报.
# Map the Chinese period name to a (month, day) anchor used for sorting +
# normalization. 年报 sorts latest (12-31), 一季报 earliest (03-31).
_PERIOD_ANCHOR = {
    "年报": (12, 31),
    "三季报": (9, 30),
    "中报": (6, 30),
    "半年报": (6, 30),
    "二季报": (6, 30),
    "一季报": (3, 31),
}
_PERIOD_RE = re.compile(r"(\d{4})\s*(年报|三季报|中报|半年报|二季报|一季报)")


def _looks_like_date(col: str) -> bool:
    c = str(col)
    if "(日)" in c or "(周)" in c or "(月)" in c or "(季)" in c or "(年)" in c:
        return True
    if _PERIOD_RE.search(c):
        return True
    return any(pat.search(c) for pat in _DATE_RES)


def _normalize_date(col: str) -> str:
    """Return a YYYY-MM-DD-ish anchor for sorting from a 妙想 column label.

    For real dates this is the date itself; for reporting-period labels like
    '2025年报' it returns the period's anchor date (2025-12-31), so periods
    sort in chronological order.
    """
    c = str(col)
    m = _PERIOD_RE.search(c)
    if m:
        y = int(m.group(1))
        mo, d = _PERIOD_ANCHOR[m.group(2)]
        return f"{y:04d}-{mo:02d}-{d:02d}"
    for pat in _DATE_RES:
        m = pat.search(c)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return c


def _row_by_date(
    indexed: dict[str, dict[str, Any]], matcher
) -> dict[str, Any]:
    """Flatten all rows whose label matches `matcher` into {date: value}."""
    out: dict[str, Any] = {}
    for metric, by_date in indexed.items():
        if matcher(metric):
            for d, v in by_date.items():
                if _looks_like_date(d):
                    out.setdefault(d, v)
    return out


# Map 妙想 Chinese metric names to canonical DataClient keys.
_METRIC_MAP = [
    (("市盈率", "PE"), "pe_ratio"),
    (("市净率", "PB"), "pb_ratio"),
    (("净资产收益率", "ROE"), "roe"),
    ("毛利率", "gross_margin"),
    ("净利率", "net_margin"),
    ("营业收入", "revenue"),
    ("净利润", "net_income"),
]


def _metric_key(metric: str) -> str:
    m = str(metric)
    for needles, key in _METRIC_MAP:
        if isinstance(needles, tuple):
            if any(n in m for n in needles):
                return key
        elif needles in m:
            return key
    return m


# F-Score specific metric mapping (Piotroski 9 components + valuation)
_F_SCORE_METRIC_MAP = [
    (("市盈率", "PE"), "pe_ratio"),
    (("市净率", "PB"), "pb_ratio"),
    (("总资产收益率", "ROA"), "roa"),
    (("经营", "现金流量净额", "CFO"), "cfo"),
    ("资产负债率", "debt_ratio"),
    ("流动比率", "current_ratio"),
    ("总资产周转率", "asset_turnover"),
    (("总股本", "股本"), "shares"),
    ("毛利率", "gross_margin"),
    ("营业收入", "revenue"),
    ("净利润", "net_income"),
    ("总资产", "total_assets"),
]


def _f_score_metric_key(metric: str) -> str:
    """Map MX Chinese metric names to F-score canonical keys."""
    m = str(metric)
    for needles, key in _F_SCORE_METRIC_MAP:
        if isinstance(needles, tuple):
            if any(n in m for n in needles):
                return key
        elif needles in m:
            return key
    return m


_BRACKET_RE = re.compile(r"【([^】]+)】")


def _parse_bracket_fields(blob: str) -> dict[str, str]:
    """Parse inline 【字段】值...【字段】值 text into {field: value}.

    妙想 embeds structured fields inside prose like:
        "【股票代码】600519.SH【公司简介】...【办公地址】..."
    Each 【marker】 is followed by its value up to the next 【marker】.
    """
    if not blob:
        return {}
    marks = list(_BRACKET_RE.finditer(blob))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        key = m.group(1).strip()
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(blob)
        val = blob[start:end].strip().rstrip("，,。.")
        if key and val:
            out[key] = val
    return out


def _sheet_records(sheet: dict) -> list[dict[str, Any]]:
    cols = sheet.get("columns", [])
    return [dict(zip(cols, row)) for row in sheet.get("items", [])]


# Make structural typing explicit (DataClient is a runtime_checkable Protocol).
_: DataClient = None  # type: ignore[assignment]
