"""Alpha model registry — all models register here on import.

TO ADD YOUR MODEL:
    1. Create your model file in src/signals/
    2. Import it here and add to ALPHA_MODEL_REGISTRY
    3. Reference by name in your strategy YAML

Example:
    from src.signals.my_momentum import MyMomentumModel
    ALPHA_MODEL_REGISTRY["my_momentum"] = MyMomentumModel
"""

from __future__ import annotations

from src.core.registry import ALPHA_MODEL_REGISTRY
from src.core.interfaces import AlphaModel, QuantModel, LLMAgent

# Built-in models
from src.signals.pead import PEADModel
from src.signals.buffett import BuffettAgent
from src.signals.ashare_value import AshareValueModel
from src.signals.bsadf import BSADFModel
from src.signals.tech_confluence import TechConfluenceModel
from src.signals.growth_loop import GrowthLoopAgent
from src.signals.rotation_growth import RotationGrowthModel
from src.signals.serenity_gate import SerenityGateModel

# Register built-in models
ALPHA_MODEL_REGISTRY["pead"] = PEADModel
ALPHA_MODEL_REGISTRY["buffett"] = BuffettAgent
ALPHA_MODEL_REGISTRY["ashare_value"] = AshareValueModel
ALPHA_MODEL_REGISTRY["bsadf"] = BSADFModel
ALPHA_MODEL_REGISTRY["tech_confluence"] = TechConfluenceModel
ALPHA_MODEL_REGISTRY["growth_loop"] = GrowthLoopAgent
ALPHA_MODEL_REGISTRY["rotation_growth"] = RotationGrowthModel

# ---- ADD YOUR MODELS HERE ----
# from src.signals.my_momentum import MyMomentumModel
# ALPHA_MODEL_REGISTRY["my_momentum"] = MyMomentumModel

# from src.signals.my_agent import MyAgent
# ALPHA_MODEL_REGISTRY["my_agent"] = MyAgent

# from src.signals.my_value_screen import MyValueScreen
# ALPHA_MODEL_REGISTRY["my_value_screen"] = MyValueScreen

__all__ = [
    "AlphaModel",
    "QuantModel",
    "LLMAgent",
    "ALPHA_MODEL_REGISTRY",
    "PEADModel",
    "BuffettAgent",
    "AshareValueModel",
    "BSADFModel",
    "TechConfluenceModel",
    "GrowthLoopAgent",
    "RotationGrowthModel",
]
