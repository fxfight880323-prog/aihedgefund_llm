"""Registry — the plugin system for alpha models.

Every alpha model (quant or LLM) registers here. The fund mandate YAML
references models by name, and the registry instantiates them.

TO REGISTER YOUR MODEL:
    # In src/signals/__init__.py
    from src.signals.my_model import MyModel
    ALPHA_MODEL_REGISTRY["my_model"] = MyModel

Then in your strategy YAML:
    models:
      - name: my_model
        weight: 1.0
"""

from __future__ import annotations

from typing import Any

# This dict is populated by src/signals/__init__.py on import.
# Key = model name (string), Value = model class (subclass of AlphaModel)
ALPHA_MODEL_REGISTRY: dict[str, type[Any]] = {}

# Blend policy registry
BLEND_POLICY_REGISTRY: dict[str, type[Any]] = {}

# Risk model registry
RISK_MODEL_REGISTRY: dict[str, type[Any]] = {}

# Data client registry
DATA_CLIENT_REGISTRY: dict[str, type[Any]] = {}


def register_alpha_model(name: str):
    """Decorator to register an alpha model.

    Usage:
        @register_alpha_model("my_momentum")
        class MyMomentumModel(QuantModel):
            ...
    """
    def decorator(cls):
        ALPHA_MODEL_REGISTRY[name] = cls
        return cls
    return decorator


def register_blend_policy(name: str):
    """Decorator to register a blend policy."""
    def decorator(cls):
        BLEND_POLICY_REGISTRY[name] = cls
        return cls
    return decorator


def register_risk_model(name: str):
    """Decorator to register a risk model."""
    def decorator(cls):
        RISK_MODEL_REGISTRY[name] = cls
        return cls
    return decorator


def register_data_client(name: str):
    """Decorator to register a data client."""
    def decorator(cls):
        DATA_CLIENT_REGISTRY[name] = cls
        return cls
    return decorator


def get_alpha_model(name: str, **params) -> Any:
    """Instantiate a registered alpha model by name."""
    if name not in ALPHA_MODEL_REGISTRY:
        raise ValueError(
            f"Unknown alpha model '{name}'. "
            f"Available: {sorted(ALPHA_MODEL_REGISTRY.keys())}"
        )
    return ALPHA_MODEL_REGISTRY[name](**params)
