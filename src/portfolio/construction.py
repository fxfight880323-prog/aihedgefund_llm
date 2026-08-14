"""Portfolio construction — blend analyst views into target weights.

This is the fund's portfolio manager: it takes every analyst's Signal and
produces one target weight per ticker. Pure arithmetic, no I/O.

Default: conviction_weighted. Capital flows to tickers in proportion to
their blended conviction, scaled so the whole book deploys gross_target.

TO ADD YOUR OWN BLEND POLICY:
  See _template_allocator.py for a blank template.
  Ideas:
    - Bayesian updating (prior + signals)
    - Risk-parity (weight by inverse volatility)
    - LLM meta-aggregator (LLM reads all signals and decides weights)
    - Kelly criterion sizing
"""

from __future__ import annotations

from src.core.models import Signal, BlendResult
from src.core.interfaces import BlendPolicy


class ConvictionWeightedBlend(BlendPolicy):
    """Conviction-weighted blending — the default portfolio policy.

    conviction_t = sum(w_m * value_mt) / sum(w_m) for each ticker
    weight_t = conviction_t / sum(|convictions|) * gross_target

    With market_neutral: demean convictions cross-sectionally first.
    """

    def blend(
        self,
        signals: list[Signal],
        model_weights: dict[str, float],
        gross_target: float = 1.0,
        market_neutral: bool = False,
    ) -> BlendResult:
        # Per-ticker weighted conviction
        weighted_sum: dict[str, float] = {}
        weight_total: dict[str, float] = {}

        for signal in signals:
            if signal.metadata.get("abstained"):
                continue
            w = model_weights.get(signal.model_name, 1.0)
            weighted_sum[signal.ticker] = weighted_sum.get(signal.ticker, 0.0) + w * signal.value
            weight_total[signal.ticker] = weight_total.get(signal.ticker, 0.0) + w

        tickers = sorted({s.ticker for s in signals})
        convictions = {
            t: (weighted_sum[t] / weight_total[t]) if weight_total.get(t) else 0.0
            for t in tickers
        }

        scaled = convictions
        if market_neutral and tickers:
            mean = sum(convictions.values()) / len(convictions)
            scaled = {t: c - mean for t, c in convictions.items()}

        # Normalize to gross target
        gross = sum(abs(c) for c in scaled.values())
        if gross < 1e-9:
            weights = {t: 0.0 for t in tickers}
        else:
            weights = {t: c / gross * gross_target for t, c in scaled.items()}

        return BlendResult(convictions=convictions, weights=weights)
