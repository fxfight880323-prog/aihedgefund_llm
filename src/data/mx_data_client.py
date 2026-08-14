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
            f"开盘价、最高价、最低价、收盘价、成交量",
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
            dates = sorted(
                set(closes) | set(opens) | set(highs) | set(lows) | set(vols)
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
