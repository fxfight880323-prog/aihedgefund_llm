"""Fund specification — a fund's mandate as serializable data.

The hierarchy mirrors a real hedge fund:

    FUND      = capital slices over STRATEGIES  (master risk on the netted book)
    STRATEGY  = a blend policy over MODELS      (a "pod")
    MODEL     = an alpha model -> Signal

A mandate is the DESK — its strategies, staff, risk limits, capital.
It never names tickers; which names to trade is a run-time input.

Example mandate YAML (config/funds/my_fund.yaml):

    name: My Alpha Fund
    capital: 100000
    rebalance: weekly
    benchmark: SPY
    strategies:
      - name: value
        weight: 0.5
        models:
          - name: buffett
            weight: 1.0
          - name: graham
            weight: 1.0
        blend:
          method: conviction_weighted
          gross_target: 1.0
          market_neutral: false
      - name: quant
        weight: 0.5
        models:
          - name: pead
            weight: 1.0
        blend:
          method: conviction_weighted
          gross_target: 0.8
          market_neutral: true
    risk:
      max_position_pct: 0.10
      max_gross_exposure: 1.5
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelSpec(BaseModel):
    """One signal model in a strategy."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="key into ALPHA_MODEL_REGISTRY, e.g. 'buffett'")
    weight: float = Field(default=1.0, gt=0, description="blend weight")
    params: dict[str, Any] = Field(
        default_factory=dict, description="constructor kwargs for the model"
    )


class BlendPolicySpec(BaseModel):
    """How a strategy's model views combine into one sleeve."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(
        default="conviction_weighted",
        description="key into BLEND_POLICY_REGISTRY, e.g. "
                    "'conviction_weighted', 'balanced_sharpness'",
    )
    gross_target: float = Field(default=1.0, gt=0)
    market_neutral: bool = Field(default=False)
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="constructor kwargs for the blend policy",
    )

    @field_validator("method")
    @classmethod
    def _known_blend_method(cls, v: str) -> str:
        from src.core.registry import BLEND_POLICY_REGISTRY
        # 惰性导入触发注册（src.signals → 各模型/策略模块）。
        import src.signals  # noqa: F401
        import src.portfolio  # noqa: F401
        if v not in BLEND_POLICY_REGISTRY:
            raise ValueError(
                f"Unknown blend policy '{v}'. "
                f"Available: {sorted(BLEND_POLICY_REGISTRY.keys())}"
            )
        return v


class StrategySpec(BaseModel):
    """A strategy ("pod"): signal models + blend policy + capital slice."""

    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str | None = None
    weight: float = Field(default=1.0, gt=0)
    models: list[ModelSpec] = Field(min_length=1)
    blend: BlendPolicySpec = Field(default_factory=BlendPolicySpec)

    @property
    def model_weights(self) -> dict[str, float]:
        return {m.name: m.weight for m in self.models}


class RiskSpec(BaseModel):
    """The fund's hard limits."""

    model_config = ConfigDict(extra="forbid")

    max_position_pct: float = Field(
        gt=0, le=1.0, description="max |weight| per ticker"
    )
    max_gross_exposure: float = Field(
        gt=0, description="max sum of |weights| (1.0 = unlevered)"
    )


class FundSpec(BaseModel):
    """A fund's complete mandate. Ticker-free by design."""

    model_config = ConfigDict(extra="forbid")

    name: str
    strategies: list[StrategySpec] = Field(min_length=1)
    risk: RiskSpec
    capital: float = Field(default=100_000.0, gt=0)
    rebalance: Literal["daily", "weekly", "monthly"] = "weekly"
    benchmark: str = "SPY"

    @field_validator("benchmark")
    @classmethod
    def _uppercase_benchmark(cls, v: str) -> str:
        return v.upper()

    @field_validator("strategies")
    @classmethod
    def _unique_strategy_names(cls, strategies: list[StrategySpec]) -> list[StrategySpec]:
        names = [s.name for s in strategies]
        dups = {n for n in names if names.count(n) > 1}
        if dups:
            raise ValueError(f"duplicate strategy names: {sorted(dups)}")
        return strategies


def load_fund(path: str | Path) -> FundSpec:
    """Load a fund mandate from YAML."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return FundSpec(**data)


def load_strategy(path: str | Path) -> StrategySpec:
    """Load a standalone strategy from YAML."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return StrategySpec(**data)
