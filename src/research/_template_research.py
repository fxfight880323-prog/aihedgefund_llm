"""TEMPLATE: Custom Research Module
============================================================================

Copy this file and build your own research workflows.

IDEAS FOR RESEARCH MODULES:
  - Strategy optimizer: search parameter space for best config
  - Factor research: test new alpha factors before promoting to production
  - Regime analysis: how does the fund perform in different market regimes?
  - Attribution: decompose returns by strategy, model, sector
  - Combinatorial Purged Cross-Validation (CPCV): detect overfitting
  - Probability of Backtest Overfitting (PBO): validate robustness
  - Monte Carlo: simulate path dependencies
  - Walk-forward analysis: rolling window backtest
  - Sensitivity analysis: how sensitive is performance to parameter changes?
  - Signal correlation: detect redundant analysts
  - Custom: your own research question

The research lab runs alongside the production fund. You test ideas here,
and promote winners into the live mandate.
"""

from __future__ import annotations

from typing import Any
from src.core.models import CycleRecord


class TemplateResearch:
    """BLANK TEMPLATE — implement your own research workflow.

    The research lab is where you test new ideas before promoting them
    to the production fund. It uses the same engine but with different
    configurations, parameters, or data.
    """

    def __init__(self, **params):
        """Initialize research parameters."""
        # self.window_size = params.get("window_size", 252)
        # self.n_splits = params.get("n_splits", 10)
        self._params = params

    def run(self, mandate_path: str, tickers: list[str], **kwargs) -> dict:
        """Run your research workflow.

        TODO: Implement your research logic.

        Example: Walk-forward analysis
            1. Split history into rolling windows
            2. Optimize parameters on each training window
            3. Test on the out-of-sample window
            4. Aggregate results

        Example: Factor research
            1. Define candidate factors
            2. Compute IC (information coefficient) for each
            3. Test factor combinations
            4. Promote winners to alpha models

        Example: Overfitting detection
            1. Run combinatorial purged CV
            2. Compute PBO (probability of backtest overfitting)
            3. Report if strategy is robust or overfit
        """
        # TODO: Implement your research
        return {
            "status": "not_implemented",
            "message": "Template research module — implement run() method",
        }

    # ---- HELPER METHODS ----

    def _compute_ic(
        self, signals: list[dict], forward_returns: list[dict]
    ) -> float:
        """Information Coefficient — correlation between signal and returns.

        IC > 0 means the signal has predictive power.
        IC > 0.05 is generally considered useful.
        """
        # TODO: Implement
        raise NotImplementedError

    def _compute_turnover(self, records: list[CycleRecord]) -> float:
        """Average portfolio turnover per rebalance.

        High turnover = more trading costs. Useful for evaluating
        whether a strategy is practical after costs.
        """
        # TODO: Implement
        raise NotImplementedError

    def _decompose_returns(
        self, records: list[CycleRecord]
    ) -> dict[str, float]:
        """Attribution: decompose returns by strategy/model.

        How much did each alpha model contribute to total return?
        """
        # TODO: Implement
        raise NotImplementedError
