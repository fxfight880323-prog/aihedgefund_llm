"""Portfolio construction policies — all register into BLEND_POLICY_REGISTRY.

TO ADD YOUR OWN BLEND POLICY:
    1. Subclass BlendPolicy in a new module here
    2. Decorate with @register_blend_policy("your_name")
    3. Reference it from a strategy YAML: blend: method: your_name
"""

from src.portfolio.construction import ConvictionWeightedBlend
from src.portfolio.balanced_sharpness import BalancedSharpnessBlend

__all__ = ["ConvictionWeightedBlend", "BalancedSharpnessBlend"]
