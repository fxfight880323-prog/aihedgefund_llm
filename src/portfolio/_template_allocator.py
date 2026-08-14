"""TEMPLATE: Custom Portfolio Allocator
============================================================================

Copy this file and implement your own blend policy.

IDEAS:
  - Risk-parity: weight by inverse volatility (equal risk contribution)
  - Kelly criterion: maximize long-run growth
  - Bayesian: update prior beliefs with signals
  - LLM meta-aggregator: an LLM reads all analyst signals and decides weights
  - Hierarchical Risk Parity (HRP): cluster-based diversification
  - Mean-variance optimization (Markowitz)
  - Black-Litterman: blend market priors with analyst views
  - Custom: your own theory of how to combine signals

REGISTRATION:
  In src/portfolio/__init__.py, add:
    from src.portfolio.my_allocator import MyAllocator
    BLEND_POLICY_REGISTRY["my_allocator"] = MyAllocator

USAGE IN STRATEGY YAML:
  blend:
    method: my_allocator
    gross_target: 1.0
    market_neutral: false
"""

from __future__ import annotations

from src.core.models import Signal, BlendResult
from src.core.interfaces import BlendPolicy


class TemplateAllocator(BlendPolicy):
    """BLANK TEMPLATE — implement your own portfolio construction logic.

    The blend() method takes all analyst signals and produces target weights.
    This is where you decide HOW to combine different analysts' views.

    EXAMPLE: Risk-Parity Allocator
    Instead of conviction-weighted, weight each ticker by inverse volatility
    so each position contributes equal risk to the portfolio.
    """

    def __init__(self, **params):
        """Accept params from strategy YAML."""
        # self.lookback = params.get("lookback", 60)
        self._params = params

    def blend(
        self,
        signals: list[Signal],
        model_weights: dict[str, float],
        gross_target: float = 1.0,
        market_neutral: bool = False,
    ) -> BlendResult:
        """Turn signals into target weights using YOUR method.

        TODO: Implement your allocation logic.

        Steps:
          1. Aggregate per-ticker conviction from signals
          2. Apply your weighting scheme
          3. Scale to gross_target
          4. Return BlendResult with convictions and weights
        """
        # ---- STEP 1: Aggregate convictions ----
        # (Same as conviction-weighted, but you could do it differently)
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

        # ---- STEP 2: Your custom weighting scheme ----
        # Example: Kelly criterion
        # kelly_fraction = win_prob - (1 - win_prob) / odds
        # weights = {t: kelly * conviction for t, conviction in convictions.items()}

        # Example: Risk-parity (needs volatility data)
        # vols = {t: get_volatility(t) for t in tickers}
        # raw_weights = {t: conviction / vols[t] for t in tickers}

        # Example: Bayesian update
        # prior = {t: 0.0 for t in tickers}  # neutral prior
        # posterior = {t: update_belief(prior[t], conviction) for t in tickers}

        # ---- STEP 3: Scale to gross_target ----
        gross = sum(abs(c) for c in convictions.values())
        if gross < 1e-9:
            weights = {t: 0.0 for t in tickers}
        else:
            weights = {t: c / gross * gross_target for t, c in convictions.items()}

        # ---- STEP 4: Return result ----
        return BlendResult(convictions=convictions, weights=weights)
