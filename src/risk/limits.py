"""Risk limits — hard caps the analysts cannot override.

"Conviction requests, risk disposes."
Portfolio construction proposes target weights, and this stage clamps them.
Exposure removed by a clamp stays in cash — it's NOT redistributed.
"""

from __future__ import annotations

from src.core.models import RiskResult, ClampEvent
from src.core.interfaces import RiskModel


class HardLimits(RiskModel):
    """Per-position cap + gross exposure cap.

    Order matters and makes the pair idempotent:
    1. Per-ticker: |weight| capped at max_position_pct
    2. Gross: if sum(|weights|) > max_gross_exposure, scale all down
    """

    def __init__(self, max_position_pct: float = 0.10, max_gross_exposure: float = 1.5):
        self._max_pos = max_position_pct
        self._max_gross = max_gross_exposure

    def apply(self, weights: dict[str, float]) -> RiskResult:
        clamped: dict[str, float] = {}
        clamps: list[ClampEvent] = []

        # 1. Per-ticker cap
        for ticker in sorted(weights):
            w = weights[ticker]
            if abs(w) > self._max_pos:
                new_w = self._max_pos if w > 0 else -self._max_pos
                clamps.append(ClampEvent(
                    limit="max_position_pct", ticker=ticker,
                    before=w, after=new_w,
                ))
                clamped[ticker] = new_w
            else:
                clamped[ticker] = w

        # 2. Gross cap
        gross = sum(abs(w) for w in clamped.values())
        if gross > self._max_gross:
            scale = self._max_gross / gross
            clamped = {t: w * scale for t, w in clamped.items()}
            clamps.append(ClampEvent(
                limit="max_gross_exposure", before=gross, after=self._max_gross,
            ))

        return RiskResult(weights=clamped, clamps=clamps)
