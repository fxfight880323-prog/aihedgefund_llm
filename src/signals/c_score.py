"""Consensus Score (C-Score) -- analyst expectation based quality signal.

Replaces/augments the backward-looking Piotroski F-Score with forward-looking
analyst consensus data (朝阳永续 con_forecast_stk via juzi-mcp):

  C1  con_roe > 12%          expected ROE above quality threshold
  C2  con_np_yoy > 0         expected net-profit growth (forward momentum)
  C3  np_revision_4w > 0     4-week consensus revision up  (short-term)
  C4  np_revision_13w > 0    13-week consensus revision up (medium-term)

C-Score in [0, 4]. Combined with BM = 1/PB terciles in a Piotroski-So
style expectation matrix:

              High BM   Mid BM   Low BM
  C >= 3      underval  moderate  congruent
  C == 2      spec.buy  neutral   neutral
  C <= 1      congruent neutral   overvalued

Rationale (user's idea, 2026-08): F-Score uses actual reports (lagged,
backward-looking). Consensus forecasts are forward-looking and continuously
updated -- the market prices expectations, so matching *expected*
fundamentals against current valuation is a more timely expectation-gap
signal.

Only the SIGN of revision fields is used (binary), which is robust to the
extreme percentage outliers in raw revision data.
"""
from __future__ import annotations

from typing import Any

# Thresholds
CON_ROE_MIN = 12.0      # C1: expected ROE threshold (%)
CON_NP_YOY_MIN = 0.0    # C2: expected growth threshold (%)
C_SCORE_BUY = 3         # C >= 3 = strong consensus


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def calculate_c_score(consensus: dict) -> tuple[int, dict]:
    """Compute C-Score from a consensus forecast snapshot record.

    consensus keys: con_roe, con_np_yoy, np_revision_4w, np_revision_13w
    (values may be None; missing data scores 0 for that component).
    """
    roe = _num(consensus.get("con_roe"))
    npg = _num(consensus.get("con_np_yoy"))
    rev4 = _num(consensus.get("np_revision_4w"))
    rev13 = _num(consensus.get("np_revision_13w"))

    d = {
        "c1_roe": 1 if (roe is not None and roe > CON_ROE_MIN) else 0,
        "c2_growth": 1 if (npg is not None and npg > CON_NP_YOY_MIN) else 0,
        "c3_rev4w": 1 if (rev4 is not None and rev4 > 0) else 0,
        "c4_rev13w": 1 if (rev13 is not None and rev13 > 0) else 0,
    }
    return sum(d.values()), d


def classify_consensus_expectation(c_score: int, bm_tercile: str) -> str:
    """Piotroski-So style matrix on consensus quality x BM valuation."""
    if c_score >= C_SCORE_BUY:
        if bm_tercile == "high":
            return "undervalued"
        if bm_tercile == "mid":
            return "moderate"
        return "congruent"
    if c_score == 2:
        if bm_tercile == "high":
            return "speculative"
        return "neutral"
    # C <= 1
    if bm_tercile == "high":
        return "congruent"
    if bm_tercile == "low":
        return "overvalued"
    return "neutral"


def consensus_conviction(c_score: int, bm_tercile: str) -> float:
    """Signal value for C-Score x BM, mirroring F-Score conviction scale."""
    if c_score >= C_SCORE_BUY and bm_tercile == "high":
        # 0.5 for C=3, 0.7 for C=4
        return round(min(0.7, 0.5 + 0.2 * (c_score - C_SCORE_BUY)), 4)
    if c_score >= C_SCORE_BUY and bm_tercile == "mid":
        # 0.3 for C=3, 0.4 for C=4
        return round(min(0.4, 0.3 + 0.1 * (c_score - C_SCORE_BUY)), 4)
    if c_score == 2 and bm_tercile == "high":
        return 0.15
    return 0.0


def consensus_multiplier(c_score: int) -> float:
    """C-Score as a forward-looking modifier on F-Score conviction.

    Used by the F+C hybrid: base conviction from F x BM, multiplied by
    how well forward expectations confirm the backward-looking quality.
    """
    return {
        4: 1.30,   # expectations strongly confirm: boost
        3: 1.15,
        2: 1.00,   # neutral
        1: 0.70,   # expectations contradict: dampen
        0: 0.40,   # strong contradiction: heavy dampen (not veto)
    }.get(c_score, 1.0)
