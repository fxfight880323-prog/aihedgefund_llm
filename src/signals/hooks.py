"""HOOK 层 — 数值化筛选触发器 (What Earns a Deep Dive).

GOAL→HOOK→LOOP 剧本的 HOOK 层实现。一只股票只有先触发某个**数值化**
hook 才有资格进入 LOOP 深研。剧本原则："A hook based on narrative alone
(no numeric trigger) is invalid" — 所以这里只做纯量化、可证伪的钩子：

  H1  Revenue Inflection    营收 YoY 增速连续 2 个季度加速
  H2  Margin Inflection     毛利率环比上行 + 营收增速 > 20%
  H3  Guidance Raise Chain  连续 ≥2 个季度 BEAT（earnings 历史含
                            eps_surprise 字段时才启用，否则 abstain）
  H6  Post-Drawdown Quality 距 1 年高点回撤 ≥30% 且最新营收 YoY ≥ 10%
                            （"预期下调 <10%" 的代理指标）

未实现的钩子（H4 新S曲线 / H5 范式顺风 / H7 内部人信号）需要分部数据、
独立测算的资本开支周期或内部人数据，留作扩展点；对应数据源接入后按
同样的 {id, evidence} 结构加入 `tripped` 即可。

全部计算 point-in-time：metrics 按 date ≤ as_of 过滤，prices 按
time ≤ as_of 过滤。数据源走 DataClient 协议（get_financial_metrics /
get_prices / get_earnings），MXDataClient 与 FinancialDatasetsClient
均适用。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Hook 配置
# ---------------------------------------------------------------------------

HOOK_NAMES = {
    "H1": "Revenue Inflection",
    "H2": "Margin Inflection",
    "H3": "Guidance Raise Chain",
    "H6": "Post-Drawdown Quality",
}

DEFAULT_HOOKS = ("H1", "H2", "H3", "H6")

_H2_MIN_GROWTH = 0.20      # H2: 营收增速门槛 (剧本: "while revenue >20%")
_H6_DRAWDOWN = 0.30        # H6: 距 1 年高点回撤门槛 (剧本: "-30%+ from high")
_H6_MIN_GROWTH = 0.10      # H6: 基本面未坏的代理 (剧本: "estimates cut <10%")
_H3_MIN_BEATS = 2          # H3: 连续 beat 次数 (剧本: "2+ consecutive")


# ---------------------------------------------------------------------------
# 规则求值 — 输入是已算好的指标（与取数解耦，批量/单票两条路径共用）
# ---------------------------------------------------------------------------

def evaluate_hooks(
    revenue_yoy: list[float] | None,
    gm_series: list[float | None] | None = None,
    drawdown: float | None = None,
    beats: int | None = None,
    enabled: tuple[str, ...] | list[str] | None = DEFAULT_HOOKS,
) -> dict[str, Any]:
    """对已计算好的指标运行数值 hook 规则。

    Args:
        revenue_yoy: 营收 YoY 增速序列，newest-first（H1 需 ≥3 个）
        gm_series:   毛利率序列，newest-first（H2 用前 2 个）
        drawdown:    距 1 年高点的回撤 (0-1)（H6）
        beats:       最近连续 earnings BEAT 次数；None = 数据不可得（H3 abstain）

    Returns:
        {"tripped": [{id, name, evidence}...], "computed": {...}}
    """
    enabled = tuple(enabled) if enabled else DEFAULT_HOOKS
    tripped: list[dict[str, Any]] = []
    computed: dict[str, Any] = {
        "revenue_yoy": [round(g, 4) for g in (revenue_yoy or [])],
    }

    # ---- H1: 营收增速连续 2 个季度加速（最近 3 个 YoY 严格递增） ----
    yoy = revenue_yoy or []
    if "H1" in enabled and len(yoy) >= 3:
        g0, g1, g2 = yoy[0], yoy[1], yoy[2]
        if g0 > g1 > g2:
            tripped.append({
                "id": "H1", "name": HOOK_NAMES["H1"],
                "evidence": f"YoY growth accelerating: "
                            f"{g2:.1%} → {g1:.1%} → {g0:.1%}",
            })

    # ---- H2: 毛利率环比上行 + 营收增速 > 20% ----
    gm = gm_series or []
    computed["gross_margin"] = gm[:2]
    if "H2" in enabled and len(gm) >= 2 and yoy:
        gm_now, gm_prev = gm[0], gm[1]
        if (gm_now is not None and gm_prev is not None
                and gm_now > gm_prev and yoy[0] > _H2_MIN_GROWTH):
            tripped.append({
                "id": "H2", "name": HOOK_NAMES["H2"],
                "evidence": f"gross margin {gm_prev:.1f}→{gm_now:.1f} "
                            f"while revenue YoY {yoy[0]:.1%} > 20%",
            })

    # ---- H3: 连续 ≥2 个季度 BEAT（仅当数据可得） ----
    computed["recent_beats"] = beats
    if "H3" in enabled and beats is not None and beats >= _H3_MIN_BEATS:
        tripped.append({
            "id": "H3", "name": HOOK_NAMES["H3"],
            "evidence": f"{beats} consecutive earnings BEATs",
        })

    # ---- H6: 回撤 ≥30% 且基本面未坏 ----
    if drawdown is not None:
        computed["drawdown_1y"] = round(drawdown, 4)
    if "H6" in enabled and drawdown is not None and yoy:
        if drawdown >= _H6_DRAWDOWN and yoy[0] >= _H6_MIN_GROWTH:
            tripped.append({
                "id": "H6", "name": HOOK_NAMES["H6"],
                "evidence": f"-{drawdown:.0%} from 1y high while revenue "
                            f"YoY still {yoy[0]:.1%} ≥ 10%",
            })

    return {"tripped": tripped, "computed": computed}


# ---------------------------------------------------------------------------
# 单标的筛选（DataClient 取数路径）
# ---------------------------------------------------------------------------

def screen_hooks(
    ticker: str,
    date: str,
    data_client: Any,
    enabled: tuple[str, ...] | list[str] = DEFAULT_HOOKS,
) -> dict[str, Any]:
    """对一个标的运行数值 hook 筛选。

    Returns:
        {
          "tripped":  [{"id": "H1", "name": ..., "evidence": "…"}, ...],
          "computed": {各钩子的中间计算值，便于审计},
          "data_ok":  bool  # 基本数据是否可得（False → C-priority discard）
        }
    """
    enabled = tuple(enabled) if enabled else DEFAULT_HOOKS

    metrics = _get_metrics(ticker, date, data_client)
    closes, high = _get_price_window(ticker, date, data_client)

    if not metrics and not closes:
        return {
            "tripped": [], "computed": {"error": "no metrics or price data returned"},
            "data_ok": False,
        }

    rev_yoy = _revenue_yoy_series(metrics) if metrics else []
    gm_series: list[float | None] = []
    if len(metrics) >= 2:
        gm_series = [
            _num(metrics[0].get("gross_margin")),
            _num(metrics[1].get("gross_margin")),
        ]
    drawdown = None
    if closes and high:
        drawdown = 1.0 - closes[-1] / high if high > 0 else 0.0
    beats = _consecutive_beats(ticker, date, data_client) if "H3" in enabled else None

    result = evaluate_hooks(rev_yoy, gm_series, drawdown, beats, enabled=enabled)
    result["data_ok"] = True
    return result


# ---------------------------------------------------------------------------
# Universe 筛选 (PROMPT H-1 等价物)
# ---------------------------------------------------------------------------

def screen_universe(
    tickers: list[str],
    date: str,
    data_client: Any,
    max_a_priority: int = 3,
    enabled: tuple[str, ...] | list[str] = DEFAULT_HOOKS,
) -> dict[str, list[dict[str, Any]]]:
    """对整个 universe 运行 hook 筛选并做 A/B/C 优先级排名。

    剧本规则：最多 {max_a_priority} 个 A 优先级（强制排名），A = 触发了
    数值 hook 的标的；B = 数据正常但无 hook（观察）；C = 数据缺失（丢弃）。

    Returns:
        {"A": [...], "B": [...], "C": [...]}
        每项含 ticker / hooks / 排名依据。
    """
    scored: list[dict[str, Any]] = []
    for tk in tickers:
        try:
            res = screen_hooks(tk, date, data_client, enabled=enabled)
        except Exception as exc:  # 筛选层 fail-soft：单标的失败不拖垮全屏
            res = {"tripped": [], "computed": {"error": str(exc)},
                   "data_ok": False}
        scored.append({
            "ticker": tk,
            "hooks": [h["id"] for h in res["tripped"]],
            "detail": res["tripped"],
            "data_ok": res["data_ok"],
            "computed": res["computed"],
            "latest_yoy": (res["computed"].get("revenue_yoy") or [0.0])[0],
        })

    # A 候选：触发 ≥1 个数值 hook。排名依据：hook 数量多者优先，
    # 其次最新营收 YoY 增速（成长性强的深研优先）。
    a_candidates = sorted(
        (s for s in scored if s["data_ok"] and s["hooks"]),
        key=lambda s: (-len(s["hooks"]), -_safe(s["latest_yoy"])),
    )
    a_list = a_candidates[:max_a_priority]
    a_overflow = a_candidates[max_a_priority:]

    b_list = [s for s in scored if s["data_ok"] and not s["hooks"]] + a_overflow
    c_list = [s for s in scored if not s["data_ok"]]

    return {"A": a_list, "B": b_list, "C": c_list}


# ---------------------------------------------------------------------------
# 内部：数据获取与计算（全部 point-in-time）
# ---------------------------------------------------------------------------

def _get_metrics(ticker: str, date: str, data_client: Any) -> list[dict]:
    """取 point-in-time 基本面指标行（newest-first，过滤 date ≤ as_of）。"""
    try:
        rows = data_client.get_financial_metrics(ticker, date, limit=12)
    except Exception:
        return []
    if not rows:
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = str(r.get("date") or "")[:10]
        if d and d > date[:10]:
            continue  # 未来数据 — 丢弃
        out.append(r)
    return out


def _get_price_window(
    ticker: str, date: str, data_client: Any
) -> tuple[list[float], float | None]:
    """取过去 1 年的收盘序列与最高价（point-in-time）。"""
    as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
    start = (as_of - timedelta(days=365)).isoformat()
    try:
        bars = data_client.get_prices(ticker, start, date)
    except Exception:
        return [], None
    closes = [
        float(b["close"]) for b in bars
        if (b.get("time") or "")[:10] <= date[:10] and _num(b.get("close"))
    ]
    highs = [
        float(b["high"]) for b in bars
        if (b.get("time") or "")[:10] <= date[:10] and _num(b.get("high"))
    ]
    return closes, (max(highs) if highs else None)


def _revenue_yoy_series(metrics: list[dict]) -> list[float]:
    """营收 YoY 增速序列（newest-first，同期对齐）。

    妙想报表是**年内累计值**（一季报=3个月/中报=6个月/三季报=9个月/
    年报=12个月），位置对齐 rev[i]/rev[i+4] 在混合周期下会严重失真
    （如 一季报 vs 上年年报 = -75%）。必须同季对上季：一季报 vs 上年
    一季报。日频估值行（月份非 03/06/09/12 锚点）自然排除。
    """
    rev_by_qp: dict[tuple[int, int], float] = {}
    for m in metrics:  # newest-first
        d = str(m.get("date") or "")[:10]
        if len(d) != 10 or not d[:4].isdigit():
            continue
        q = {"03": 1, "06": 2, "09": 3, "12": 4}.get(d[5:7])
        if q is None:
            continue
        v = _num(m.get("revenue"))
        if v is not None and v != 0:
            rev_by_qp.setdefault((int(d[:4]), q), v)
    yoy: list[float] = []
    for (y, q), v in sorted(rev_by_qp.items(), reverse=True):
        prev = rev_by_qp.get((y - 1, q))
        if prev and prev > 0:
            yoy.append(v / prev - 1.0)
    return yoy


def _consecutive_beats(ticker: str, date: str, data_client: Any) -> int | None:
    """最近的连续 BEAT 次数；earnings 无 eps_surprise 字段时返回 None。"""
    try:
        earnings = data_client.get_earnings(ticker)
    except Exception:
        return None
    if earnings is None:
        return None
    if isinstance(earnings, dict):
        records = earnings.get("earnings_history")
        if not isinstance(records, list):
            return None  # MX 的 series 格式无 surprise 字段 → H3 abstain
    elif isinstance(earnings, list):
        records = earnings
    else:
        return None

    as_of = date[:10]
    dated = []
    for e in records:
        fd = str(e.get("filing_date") or e.get("date") or "")[:10]
        if fd and fd <= as_of:
            dated.append((fd, e))
    dated.sort(key=lambda x: x[0], reverse=True)

    beats = 0
    for _, e in dated:
        if e.get("eps_surprise") == "BEAT":
            beats += 1
        else:
            break
    return beats


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _safe(v: Any) -> float:
    f = _num(v)
    return f if f is not None else 0.0
