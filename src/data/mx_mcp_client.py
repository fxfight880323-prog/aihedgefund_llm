"""妙想(MX) MCP data client — East Money 妙想 data service over MCP.

This module provides access to the 妙想 (MX) MCP Server
(https://mxapi.eastmoney.com/mxds/mcp), which exposes a natural-language
`query` interface to East Money's financial database covering A-shares,
HK stocks, US stocks, funds, bonds, indices, macro data, news, and filings.

Two layers are provided:

  1. `MXMCPClient`  — low-level client. One method, `query(tool, question)`,
     returns the raw parsed sheet(s). This is the efficient, confirmed-working
     pattern and the primary thing everything else builds on.
  2. `MXDataClient` — DataClient-protocol adapter (get_prices /
     get_financial_metrics / get_company_facts / get_earnings) so 妙想 drops
     straight into the fund workflow graph like `FinancialDatasetsClient`.

CONFIRMED HIGH-EFFICIENCY PATTERN (always used internally):
  - JSON-RPC over POST to the MCP URL.
  - Header `em_api_key`.
  - json.dumps(..., ensure_ascii=True)  ← CRITICAL: raw UTF-8 Chinese in the
    body triggers HTTP 400 "Invalid message format" from the server.
  - tools/call arguments = {"query": "<natural-language sentence>"}. There is
    exactly one parameter; do NOT pass `symbol` / `ticker` / `limit`.
  - Stateless StreamableHttp transport: each request may use its own session.

API key resolution order: constructor arg → EM_API_KEY env var → .env file.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from src.data.cache import DiskCache

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MX_MCP_URL = "https://mxapi.eastmoney.com/mxds/mcp"

# Fallback API key: only from the environment / .env (EM_API_KEY). 密钥不进
# 源码——把你的妙想 key 放进项目根目录的 .env 文件即可（该文件被
# .gitignore 忽略，不会进入版本库）。
DEFAULT_EM_API_KEY = os.environ.get("EM_API_KEY") or None

# Canonical tool names exposed by the 妙想 MCP server.
TOOL_ASHARE = "mx_ashare_finance_data"            # A股
TOOL_HK = "mx_hk_finance_data"                    # 港股
TOOL_US = "mx_us_finance_data"                    # 美股
TOOL_FUND = "mx_fund_finance_data"                # 基金
TOOL_BOND = "mx_bond_finance_data"                # 债券
TOOL_INDEX = "mx_index_block_finance_data"        # 指数 / 板块
TOOL_MACRO = "mx_macro_data"                      # 宏观 / 行业 / 商品
TOOL_SCREENER = "mx_stocks_screener"              # 选股 / 选基 / 选债
TOOL_NEWS = "mx_finance_search_news"              # 新闻 / 研报
TOOL_NOTICE = "mx_finance_search_notice"          # 公告 / 披露
TOOL_COMPREHENSIVE = "mx_comprehensive_finance_data"  # 非上市 / 发行人 / 兜底

ALL_TOOLS = (
    TOOL_ASHARE, TOOL_HK, TOOL_US, TOOL_FUND, TOOL_BOND, TOOL_INDEX,
    TOOL_MACRO, TOOL_SCREENER, TOOL_NEWS, TOOL_NOTICE, TOOL_COMPREHENSIVE,
)

# Suffix on a market identifier selects which 妙想 tool handles it.
_MARKET_TOOL = {
    "SH": TOOL_ASHARE, "SZ": TOOL_ASHARE, "BJ": TOOL_ASHARE,  # A股
    "HK": TOOL_HK,
    "O": TOOL_US, "N": TOOL_US, "A": TOOL_US,                 # 美股 (.O/.N/.A)
    "OF": TOOL_FUND,
    "IB": TOOL_BOND, "SHF": TOOL_BOND,
    "FXR": TOOL_COMPREHENSIVE,                                # 非上市企业
}

# Very small Chinese-number parser: "1.691万亿" -> 1.691e12, "1355.29元" -> 1355.29
_CN_UNIT = {"万": 1e4, "亿": 1e8, "万亿": 1e12, "千万": 1e7, "百万": 1e6}
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


# ---------------------------------------------------------------------------
# Low-level MCP client
# ---------------------------------------------------------------------------

class MXMCPError(RuntimeError):
    """Raised when the 妙想 MCP call fails or returns isError=true."""


class MXMCPClient:
    """Low-level 妙想 MCP client.

    Example:
        cli = MXMCPClient()                              # reads EM_API_KEY
        sheets = cli.query(TOOL_ASHARE,
                           "贵州茅台(600519)最新收盘价、市盈率、市净率")
        for s in sheets:
            print(s["sheetName"], s["columns"], s["items"])
    """

    def __init__(
        self,
        api_key: str | None = None,
        url: str = MX_MCP_URL,
        timeout: float = 120.0,
        cache: DiskCache | None = None,
        session: requests.Session | None = None,
    ):
        self._api_key = (
            api_key
            or os.environ.get("EM_API_KEY")
            or _load_dotenv_key("EM_API_KEY")
            or DEFAULT_EM_API_KEY  # hardcore fallback
        )
        self._url = url
        self._timeout = timeout
        self._cache = cache or DiskCache()
        # A short-lived session pool is fine; transport is stateless.
        self._session = session or requests.Session()
        self._session.trust_env = False  # avoid leaking through system proxies

    # -- public API ---------------------------------------------------------

    def query(
        self,
        tool: str,
        question: str,
        *,
        use_cache: bool = True,
        retries: int = 2,
    ) -> list[dict[str, Any]]:
        """Run a natural-language query against one 妙想 tool.

        Returns a list of "sheets", each:
            {"columns": [...], "items": [[...], ...], "sheetName": str}
        Empty list means the service matched the question but has no data.
        Raises MXMCPError on infrastructure failure or server-side error.
        """
        if tool not in ALL_TOOLS:
            raise ValueError(
                f"Unknown 妙想 tool: {tool!r}. Valid: {ALL_TOOLS}"
            )

        cache_key = ("mx", tool, question)
        if use_cache:
            cached = self._cache.get(*cache_key)
            if cached is not None:
                return cached

        sheets = self._call_tool(tool, question, retries=retries)
        if use_cache:
            self._cache.put(sheets, *cache_key)
        return sheets

    def query_text(
        self, tool: str, question: str, **kwargs
    ) -> str:
        """Convenience: return the joined raw text content of a query.

        Useful for news / filings where the structured sheet is less
        important than the prose.
        """
        # News & notices return text blobs rather than sheets, so fall back
        # to the raw content text when there are no sheets.
        sheets = self.query(tool, question, **kwargs)
        if sheets:
            return json.dumps({"data": sheets}, ensure_ascii=False)
        # Re-fetch without cache to access raw content for text-type tools.
        raw = self._call_tool_raw(tool, question)
        return raw

    # -- transport ----------------------------------------------------------

    def _call_tool_raw(self, tool: str, question: str) -> str:
        """POST one tools/call and return the raw content text (or raise)."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": {"query": question}},
        }
        # CRITICAL: ensure_ascii=True — raw UTF-8 Chinese => 400.
        body = json.dumps(payload, ensure_ascii=True)
        headers = {
            "em_api_key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        resp = self._session.post(
            self._url, data=body, headers=headers, timeout=self._timeout
        )
        if resp.status_code != 200:
            raise MXMCPError(
                f"HTTP {resp.status_code} from 妙想 MCP for "
                f"tool={tool}: {self._short_error(resp.text)}"
            )
        data = resp.json()
        if "error" in data:
            raise MXMCPError(f"JSON-RPC error: {data['error']}")
        result = data.get("result", {})
        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", [])]
            raise MXMCPError(
                f"妙想 tool {tool} returned isError: {' '.join(texts)[:300]}"
            )
        contents = result.get("content", [])
        return "".join(c.get("text", "") for c in contents)

    def _call_tool(self, tool: str, question: str, retries: int = 2) -> list[dict]:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                text = self._call_tool_raw(tool, question)
                return _parse_sheets(text)
            except (MXMCPError, ValueError, requests.RequestException) as exc:
                last_exc = exc
                # back off briefly before retrying transport blips
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _short_error(text: str) -> str:
        """Extract a one-line reason from a framework 400 error body."""
        try:
            data = json.loads(text)
            return str(data.get("message") or data)[:300]
        except (ValueError, TypeError):
            return text[:300]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dotenv_key(key: str) -> str | None:
    """Read a key from a local .env file if python-dotenv isn't available."""
    # Try python-dotenv first (it's a project dependency).
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        val = os.environ.get(key)
        return val
    except Exception:
        pass
    # Fall back to a tiny manual parser.
    for env_path in (".env", os.path.join(os.getcwd(), ".env")):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    if k.strip() == key:
                        return v.strip().strip('"').strip("'")
        except OSError:
            continue
    return None


def _parse_sheets(content_text: str) -> list[dict[str, Any]]:
    """Parse the 妙想 content text into a list of sheet dicts.

    妙想 returns content[].text as a JSON string shaped like:
        {"data": [{"columns": [...], "items": [[...], ...], "sheetName": "..."}]}
    Returns [] if there is no embedded data (e.g. text-type tools).
    """
    text = content_text.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    sheets: list[dict[str, Any]] = []
    for block in data:
        if not isinstance(block, dict):
            continue
        cols = block.get("columns") or []
        items = block.get("items") or []
        if not cols and not items:
            continue
        sheets.append(
            {
                "columns": [str(c) for c in cols],
                "items": [[_cell(c) for c in row] for row in items],
                "sheetName": block.get("sheetName", ""),
            }
        )
    return sheets


def _cell(value: Any) -> Any:
    """Leave lists/dicts as-is; coerce scalars to str (妙想 returns strings)."""
    return value


def sheet_to_records(sheet: dict[str, Any]) -> list[dict[str, Any]]:
    """Transpose a sheet {columns, items} into a list of row dicts.

    The first column is usually a label and the rest are dates/values, so this
    is mostly useful for the column-oriented sheets 妙想 favors. When the first
    column holds row labels (typical), use `sheet_to_indexed` instead.
    """
    cols = sheet.get("columns", [])
    records: list[dict[str, Any]] = []
    for row in sheet.get("items", []):
        records.append(dict(zip(cols, row)))
    return records


def sheet_to_indexed(sheet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a column-oriented sheet by its row-label column.

    妙想 sheets commonly look like:
        columns: ["贵州茅台(600519.SH)", "2026-08-13", "2026-08-12", ...]
        items:   [["总市值", "1.694万亿", "1.679万亿", ...],
                  ["市净率PB", "6.254倍", ...]]
    Here each row's first cell is a metric name and the rest are date columns.
    This returns {metric: {column: value}}.
    """
    cols = sheet.get("columns", [])
    out: dict[str, dict[str, Any]] = {}
    for row in sheet.get("items", []):
        if not row:
            continue
        metric = str(row[0])
        out[metric] = {col: val for col, val in zip(cols[1:], row[1:])}
    return out


def parse_cn_number(text: str) -> float | None:
    """Parse a Chinese-mixed numeric string into a float.

    Examples: "1.691万亿" -> 1.691e12, "6.254倍" -> 6.254,
              "1355.29元" -> 1355.29, "15.04%" -> 15.04.
    Returns None if no number is found.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    num = float(m.group())
    # Match the longest unit suffix that appears before/after the number.
    for unit, mult in sorted(_CN_UNIT.items(), key=lambda kv: -len(kv[0])):
        if unit in s:
            return num * mult
    return num


def market_of(ticker: str) -> str:
    """Infer the market suffix from a ticker code.

    Accepts forms like "600519.SH", "600519", "00700.HK", "AAPL.O".
    Returns the uppercase suffix, or "" if unknown.
    """
    t = ticker.strip().upper()
    if "." in t:
        return t.rsplit(".", 1)[1]
    # Bare A-share codes: 6xxxxx -> SH, 0/3xxxxx -> SZ, 8/4xxxxx -> BJ
    digits = re.sub(r"\D", "", t)
    if len(digits) == 6:
        if digits.startswith(("60", "68", "90", "11", "13", "50", "51", "56", "58")):
            return "SH"
        if digits.startswith(("00", "30", "12", "15", "16", "18")):
            return "SZ"
        if digits.startswith(("43", "83", "87", "92")):
            return "BJ"
    return ""


def tool_for_ticker(ticker: str) -> str:
    """Pick the right 妙想 tool for a given ticker."""
    mkt = market_of(ticker)
    return _MARKET_TOOL.get(mkt, TOOL_COMPREHENSIVE)
