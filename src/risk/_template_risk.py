"""TEMPLATE: Custom Risk Model
============================================================================

Copy this file and implement your own risk management logic.

IDEAS:
  - Volatility targeting: scale positions by inverse volatility
  - Drawdown-based: deleverage when fund drawdown exceeds threshold
  - Sector limits: cap exposure per sector/industry
  - Correlation-based: limit correlated positions
  - VaR/CVaR: constrain value-at-risk
  - Kelly fraction: cap position sizes to a fraction of Kelly optimal
  - Dynamic: adjust limits based on market regime
  - BSADF bubble detection: reduce exposure when泡沫 detected
  - Your own: custom risk theory

REGISTRATION:
  In src/risk/__init__.py, add:
    from src.risk.my_risk import MyRiskModel
    RISK_MODEL_REGISTRY["my_risk"] = MyRiskModel
"""

from __future__ import annotations

from src.core.models import RiskResult, ClampEvent
from src.core.interfaces import RiskModel


class TemplateRiskModel(RiskModel):
    """BLANK TEMPLATE — implement your own risk management.

    The apply() method receives target weights from portfolio construction
    and returns clamped weights. Everything removed stays in cash.

    IMPORTANT: risk can only SHRINK positions, never grow them.
    """

    def __init__(self, **params):
        """Accept params from fund mandate YAML."""
        # self.max_drawdown = params.get("max_drawdown", 0.15)
        # self.target_vol = params.get("target_volatility", 0.12)
        self._params = params

    def apply(self, weights: dict[str, float]) -> RiskResult:
        """Clamp target weights against YOUR risk limits.

        TODO: Implement your risk logic.

        Example: volatility targeting
            vol = estimate_volatility(ticker)
            if vol > threshold:
                reduce position

        Example: drawdown-based deleveraging
            current_drawdown = compute_drawdown()
            if current_drawdown > max_drawdown:
                scale = 1 - (current_drawdown - max_drawdown) / max_drawdown
                weights = {t: w * scale for t, w in weights.items()}
        """
        clamps: list[ClampEvent] = []

        # TODO: Replace with your risk logic
        # For now, just pass through unchanged
        clamped = dict(weights)

        return RiskResult(weights=clamped, clamps=clamps)
