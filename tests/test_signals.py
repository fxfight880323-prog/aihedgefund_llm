"""Tests for the framework — run with: pytest tests/"""

import pytest
from src.core.models import Signal
from src.core.interfaces import QuantModel, AlphaModel
from src.portfolio.construction import ConvictionWeightedBlend
from src.risk.limits import HardLimits
from src.execution.broker import SimBroker
from src.core.models import Order, OrderSide


class TestSignal:
    def test_signal_creation(self):
        s = Signal(
            model_name="test", ticker="AAPL", date="2024-01-01",
            value=0.5, reasoning="test"
        )
        assert s.value == 0.5
        assert s.ticker == "AAPL"

    def test_signal_bounds(self):
        s = Signal(model_name="test", ticker="AAPL", date="2024-01-01", value=1.0)
        assert s.value == 1.0


class TestConvictionWeightedBlend:
    def test_blend_simple(self):
        signals = [
            Signal(model_name="a", ticker="AAPL", date="2024-01-01", value=0.5),
            Signal(model_name="b", ticker="AAPL", date="2024-01-01", value=0.3),
            Signal(model_name="a", ticker="MSFT", date="2024-01-01", value=-0.5),
            Signal(model_name="b", ticker="MSFT", date="2024-01-01", value=-0.3),
        ]
        blend = ConvictionWeightedBlend()
        result = blend.blend(signals, {"a": 1.0, "b": 1.0}, gross_target=1.0)
        assert "AAPL" in result.weights
        assert "MSFT" in result.weights
        assert result.weights["AAPL"] > 0
        assert result.weights["MSFT"] < 0

    def test_blend_abstained_excluded(self):
        signals = [
            Signal(model_name="a", ticker="AAPL", date="2024-01-01", value=0.5),
            Signal(model_name="b", ticker="AAPL", date="2024-01-01", value=0.0,
                   metadata={"abstained": True}),
        ]
        blend = ConvictionWeightedBlend()
        result = blend.blend(signals, {"a": 1.0, "b": 1.0}, gross_target=1.0)
        assert result.convictions["AAPL"] == 0.5  # only model "a" voted

    def test_all_neutral(self):
        signals = [
            Signal(model_name="a", ticker="AAPL", date="2024-01-01", value=0.0),
        ]
        blend = ConvictionWeightedBlend()
        result = blend.blend(signals, {"a": 1.0}, gross_target=1.0)
        assert result.weights["AAPL"] == 0.0


class TestHardLimits:
    def test_position_cap(self):
        limits = HardLimits(max_position_pct=0.10, max_gross_exposure=1.0)
        weights = {"AAPL": 0.25, "MSFT": 0.25}
        result = limits.apply(weights)
        assert abs(result.weights["AAPL"]) == 0.10
        assert abs(result.weights["MSFT"]) == 0.10
        assert len(result.clamps) == 2

    def test_gross_cap(self):
        limits = HardLimits(max_position_pct=0.50, max_gross_exposure=0.80)
        weights = {"AAPL": 0.50, "MSFT": 0.50}
        result = limits.apply(weights)
        assert sum(abs(w) for w in result.weights.values()) <= 0.80 + 1e-9

    def test_no_clamp_needed(self):
        limits = HardLimits(max_position_pct=0.50, max_gross_exposure=1.5)
        weights = {"AAPL": 0.10, "MSFT": 0.10}
        result = limits.apply(weights)
        assert result.weights == weights
        assert len(result.clamps) == 0


class TestSimBroker:
    def test_buy(self):
        broker = SimBroker(capital=10_000)
        fill = broker.place_order(Order(
            ticker="AAPL", side=OrderSide.BUY, shares=10, limit_price=150.0
        ))
        assert fill.shares == 10
        assert fill.price == 150.0
        assert broker.cash() == 10_000 - 1500
        assert "AAPL" in broker.positions()

    def test_sell(self):
        broker = SimBroker(capital=10_000)
        broker.place_order(Order(
            ticker="AAPL", side=OrderSide.BUY, shares=10, limit_price=150.0
        ))
        broker.place_order(Order(
            ticker="AAPL", side=OrderSide.SELL, shares=5, limit_price=160.0
        ))
        assert broker.positions()["AAPL"].shares == 5
        assert broker.cash() == 10_000 - 1500 + 800

    def test_insufficient_cash_scales(self):
        broker = SimBroker(capital=500)
        fill = broker.place_order(Order(
            ticker="AAPL", side=OrderSide.BUY, shares=10, limit_price=150.0
        ))
        assert fill.shares < 10  # scaled to what we can afford
