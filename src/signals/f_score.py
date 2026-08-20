"""Piotroski F-Score + BM expectation gap model.

Based on:
  - Piotroski (2000): "Value Investing: The Use of Historical Financial
    Statement Information to Separate Winners from Losers"
  - Piotroski & So (2012): "Identifying the Best Performing Stocks: A
    Fundamental Analysis Approach" -- F-score x BM expectation matrix
  - Liu Xu (Dacheng Fund): PE<=20, PB<=2, ROA focus, low turnover,
    concentrated portfolio, semi-annual rebalancing

F-Score (0-9): 9 binary indicators across 3 dimensions:
  Profitability (4):
    F1  ROA > 0              (positive net income relative to assets)
    F2  dROA > 0             (ROA improving year-over-year)
    F3  CFO > 0              (positive operating cash flow)
    F4  CFO/TA > ROA         (earnings quality -- cash flow exceeds accruals)
  Leverage/Liquidity/Source (3):
    F5  dLever <= 0          (decreasing leverage -- debt ratio down)
    F6  dLiquidity > 0       (increasing current ratio)
    F7  dEQ <= 0             (no new equity issuance -- shares unchanged)
  Operating Efficiency (2):
    F8  dMargin > 0          (increasing gross margin)
    F9  dTurn > 0            (increasing asset turnover)

BM = 1/PB. Piotroski & So show the value/glamour effect is concentrated
in "incongruent" stocks -- high F-score + high BM (strong fundamentals,
cheap stock) => undervalued; low F-score + low BM => overvalued.

Liu Xu's A-share adaptations:
  - PE <= 20, PB <= 2 as hard valuation filters
  - ROA (not ROE) as primary quality metric (strip leverage)
  - Low turnover, concentrated portfolio (15-30 stocks)
  - Semi-annual rebalancing aligned with reporting periods
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import QuantModel
from src.core.models import Signal
from src.core.registry import register_alpha_model


# ---------------------------------------------------------------------------
# Pure functions (reusable in backtest without instantiating a model)
# ---------------------------------------------------------------------------

def _safe(v: Any) -> float | None:
    """Coerce to float, returning None for missing/invalid."""
    if v is None:
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def calculate_f_score(
    curr: dict[str, float | None],
    prev: dict[str, float | None],
) -> tuple[int, dict[str, int]]:
    """Calculate Piotroski F-Score (0-9) from current and previous year.

    Expected metric keys (same names used by MXDataClient.get_f_score_metrics):
      roa            -- total return on assets (%)
      cfo            -- operating cash flow (absolute, yuan)
      cfo_ta         -- CFO / total assets (%)
      debt_ratio     -- total liabilities / total assets (%)
      current_ratio  -- current assets / current liabilities
      shares         -- total shares outstanding (wan shares)
      gross_margin   -- gross margin (%)
      asset_turnover -- revenue / total assets
    """
    score = 0
    detail: dict[str, int] = {}

    # --- Profitability (4) ---

    # F1: ROA > 0
    roa = _safe(curr.get("roa"))
    detail["F1_roa_pos"] = 1 if (roa is not None and roa > 0) else 0
    score += detail["F1_roa_pos"]

    # F2: dROA > 0
    roa_prev = _safe(prev.get("roa"))
    detail["F2_droa_pos"] = 1 if (
        roa is not None and roa_prev is not None and roa > roa_prev
    ) else 0
    score += detail["F2_droa_pos"]

    # F3: CFO > 0
    cfo = _safe(curr.get("cfo"))
    detail["F3_cfo_pos"] = 1 if (cfo is not None and cfo > 0) else 0
    score += detail["F3_cfo_pos"]

    # F4: CFO/TA > ROA (earnings quality)
    cfo_ta = _safe(curr.get("cfo_ta"))
    if cfo_ta is not None and roa is not None:
        detail["F4_cfo_gt_roa"] = 1 if cfo_ta > roa else 0
    else:
        # Fallback: CFO > net_income proxy (if cfo_ta missing)
        ni = _safe(curr.get("net_income"))
        detail["F4_cfo_gt_roa"] = 1 if (
            cfo is not None and ni is not None and cfo > ni
        ) else 0
    score += detail["F4_cfo_gt_roa"]

    # --- Leverage / Liquidity / Source of Funds (3) ---

    # F5: dLever <= 0 (debt ratio decreasing or stable)
    debt = _safe(curr.get("debt_ratio"))
    debt_prev = _safe(prev.get("debt_ratio"))
    detail["F5_lever_down"] = 1 if (
        debt is not None and debt_prev is not None and debt <= debt_prev
    ) else 0
    score += detail["F5_lever_down"]

    # F6: dLiquidity > 0 (current ratio increasing)
    cr = _safe(curr.get("current_ratio"))
    cr_prev = _safe(prev.get("current_ratio"))
    detail["F6_liq_up"] = 1 if (
        cr is not None and cr_prev is not None and cr > cr_prev
    ) else 0
    score += detail["F6_liq_up"]

    # F7: dEQ <= 0 (no new equity issuance -- shares not increased)
    shares = _safe(curr.get("shares"))
    shares_prev = _safe(prev.get("shares"))
    # Tolerance: 0.1% for stock dividend / split rounding
    detail["F7_no_issuance"] = 1 if (
        shares is not None and shares_prev is not None
        and shares <= shares_prev * 1.001
    ) else 0
    score += detail["F7_no_issuance"]

    # --- Operating Efficiency (2) ---

    # F8: dMargin > 0 (gross margin increasing)
    gm = _safe(curr.get("gross_margin"))
    gm_prev = _safe(prev.get("gross_margin"))
    detail["F8_margin_up"] = 1 if (
        gm is not None and gm_prev is not None and gm > gm_prev
    ) else 0
    score += detail["F8_margin_up"]

    # F9: dTurn > 0 (asset turnover increasing)
    turn = _safe(curr.get("asset_turnover"))
    turn_prev = _safe(prev.get("asset_turnover"))
    detail["F9_turn_up"] = 1 if (
        turn is not None and turn_prev is not None and turn > turn_prev
    ) else 0
    score += detail["F9_turn_up"]

    return score, detail


def classify_expectation(f_score: int, bm_tercile: str) -> str:
    """Classify stock into Piotroski & So expectation matrix.

    Args:
        f_score: 0-9
        bm_tercile: "low", "mid", or "high"

    Returns:
        "undervalued"  -- strong fundamentals + cheap (BUY)
        "overvalued"   -- weak fundamentals + expensive (SHORT)
        "congruent"    -- fundamentals and valuation agree (no mispricing)
        "neutral"      -- middle ground, no strong signal
    """
    if f_score >= 7 and bm_tercile == "high":
        return "undervalued"
    if f_score <= 2 and bm_tercile == "low":
        return "overvalued"
    if f_score >= 7 and bm_tercile == "low":
        return "congruent"  # strong + expensive = fairly priced
    if f_score <= 2 and bm_tercile == "high":
        return "congruent"  # weak + cheap = value trap
    return "neutral"


def bm_tercile_from_pb(pb: float, pb_p33: float, pb_p67: float) -> str:
    """Classify BM tercile from PB ratio.

    BM = 1/PB, so:
      high BM (value) = low PB
      low BM (glamour) = high PB

    Args:
        pb: current PB ratio
        pb_p33: 33rd percentile of PB in universe (threshold for "high BM")
        pb_p67: 67th percentile of PB in universe (threshold for "low BM")
    """
    if pb <= 0:
        return "mid"
    if pb <= pb_p33:
        return "high"  # low PB = high BM = value
    if pb >= pb_p67:
        return "low"   # high PB = low BM = glamour
    return "mid"


# ---------------------------------------------------------------------------
# Registered alpha model (live mode)
# ---------------------------------------------------------------------------

@register_alpha_model("f_score")
class FScoreModel(QuantModel):
    """Piotroski F-Score + BM expectation gap model.

    In live mode, uses MXDataClient.get_f_score_metrics() to fetch the
    9 F-score components. In backtest, use calculate_f_score() directly
    with cached data (see examples/backtest_f_score.py).

    Liu Xu's valuation discipline is enforced as hard filters:
      - PE <= pe_max (default 20)
      - PB <= pb_max (default 2, implies BM >= 0.5)
    """

    def __init__(
        self,
        f_score_threshold: int = 7,
        pe_max: float = 20.0,
        pb_max: float = 2.0,
        min_conviction: float = 0.3,
        # BM tercile thresholds (optional; if None, use PB-based heuristic)
        bm_high_pb: float = 1.5,    # PB <= 1.5 = high BM (value)
        bm_low_pb: float = 4.0,     # PB >= 4.0 = low BM (glamour)
    ):
        self._f_thresh = f_score_threshold
        self._pe_max = pe_max
        self._pb_max = pb_max
        self._min_conv = min_conviction
        self._bm_high_pb = bm_high_pb
        self._bm_low_pb = bm_low_pb

    @property
    def name(self) -> str:
        return "f_score"

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        # Try F-score-specific data fetch first
        metrics: list[dict] = []
        try:
            if hasattr(data_client, "get_f_score_metrics"):
                metrics = data_client.get_f_score_metrics(
                    ticker, date, limit=10
                )
            else:
                metrics = data_client.get_financial_metrics(
                    ticker, date, limit=10
                )
        except Exception as exc:
            return self._abstain(ticker, date, f"data error: {exc}")

        if not metrics:
            return self._abstain(ticker, date, "no fundamentals returned")

        # Merge latest row for valuation (PE/PB are daily)
        latest = self._merge_latest(metrics)
        pe = _safe(latest.get("pe_ratio"))
        pb = _safe(latest.get("pb_ratio"))

        if pb is None or pb <= 0:
            return self._abstain(ticker, date, "no PB data")

        bm = 1.0 / pb

        # Liu Xu's hard valuation filters
        if pe is not None and pe > self._pe_max:
            return self._abstain(
                ticker, date,
                f"PE={pe:.1f} > {self._pe_max} (Liu Xu filter)"
            )
        if pb > self._pb_max:
            return self._abstain(
                ticker, date,
                f"PB={pb:.2f} > {self._pb_max} (Liu Xu filter)"
            )

        # Need at least 2 annual periods for YoY comparison
        curr, prev = self._extract_periods(metrics)
        if not curr:
            return self._abstain(ticker, date, "insufficient periods for F-score")

        f_score, detail = calculate_f_score(curr, prev)

        # BM tercile (heuristic: PB-based, not cross-sectional)
        if pb <= self._bm_high_pb:
            bm_tercile = "high"
        elif pb >= self._bm_low_pb:
            bm_tercile = "low"
        else:
            bm_tercile = "mid"

        expectation = classify_expectation(f_score, bm_tercile)

        # Signal value (conviction)
        if expectation == "undervalued":
            # High F-score + high BM: strong buy
            value = min(1.0, 0.5 + 0.1 * (f_score - 7))
        elif f_score >= self._f_thresh and bm_tercile in ("high", "mid"):
            # High F-score + reasonable BM: moderate buy
            value = self._min_conv + 0.05 * (f_score - self._f_thresh)
            value = min(0.5, value)
        elif f_score >= 5 and bm_tercile == "high":
            # Decent F-score + cheap: speculative buy
            value = self._min_conv * 0.5
        else:
            value = 0.0  # abstain

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=round(value, 4),
            reasoning=(
                f"F-score={f_score}/9 BM_tercile={bm_tercile} "
                f"PE={pe} PB={pb} BM={bm:.3f} "
                f"expectation={expectation}"
            ),
            components={
                "f_score": float(f_score),
                "bm": round(bm, 4),
                "pe": pe or 0.0,
                "pb": pb or 0.0,
            },
            metadata={
                "f_detail": detail,
                "expectation": expectation,
                "bm_tercile": bm_tercile,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_latest(metrics: list[dict]) -> dict[str, Any]:
        """Merge metric series into one dict, taking each field from
        the most recent row where it is present (same as AshareValueModel)."""
        merged: dict[str, Any] = {}
        for row in metrics:
            for k, v in row.items():
                if k in ("ticker", "date", "period"):
                    merged.setdefault(k, v)
                    continue
                if v is None or v == "":
                    continue
                if k not in merged or merged[k] in (None, ""):
                    merged[k] = v
        return merged

    @staticmethod
    def _extract_periods(
        metrics: list[dict],
    ) -> tuple[dict[str, float | None], dict[str, float | None]]:
        """Extract current-year and previous-year annual metrics.

        Expects metrics sorted newest-first. Matches by year to get
        the latest annual period and the same period one year prior.
        """
        if not metrics:
            return {}, {}

        # Find the latest annual period (Q4 / year-end)
        # MX returns period labels like "2024年报" or dates like "2024-12-31"
        by_year: dict[int, dict[str, float | None]] = {}
        for row in metrics:
            d = str(row.get("date", ""))
            # Try to extract year from date or period label
            year = None
            for prefix_len in (4,):
                try:
                    year = int(d[:prefix_len])
                except (ValueError, IndexError):
                    pass

            if year is None:
                # Try period label (e.g. "2024年报")
                p = str(row.get("period", ""))
                if p and p[:4].isdigit():
                    try:
                        year = int(p[:4])
                    except ValueError:
                        pass

            if year is None:
                continue

            if year not in by_year:
                by_year[year] = {}

            for k, v in row.items():
                if k in ("ticker", "date", "period"):
                    continue
                if v is None or v == "":
                    continue
                if k not in by_year[year] or by_year[year][k] in (None, ""):
                    by_year[year][k] = _safe(v)

        if not by_year:
            # Fallback: use first and last rows
            curr = {k: _safe(v) for k, v in metrics[0].items()
                    if k not in ("ticker", "date", "period")}
            prev = (curr.copy() if len(metrics) > 1
                    else {})
            if len(metrics) > 1:
                prev = {k: _safe(v) for k, v in metrics[-1].items()
                        if k not in ("ticker", "date", "period")}
            return curr, prev

        years_sorted = sorted(by_year.keys(), reverse=True)
        curr = by_year[years_sorted[0]]
        prev = by_year[years_sorted[1]] if len(years_sorted) > 1 else {}
        return curr, prev

    def _abstain(self, ticker: str, date: str, why: str) -> Signal:
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=0.0,
            reasoning=why,
            metadata={"abstained": True},
        )
