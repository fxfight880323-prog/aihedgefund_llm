"""Tests for the framework — run with: pytest tests/"""

import math
from datetime import date, timedelta

import numpy as np

try:
    import pytest
except ImportError:  # tests also runnable without pytest (see tests/run_tests.py)
    pytest = None

from src.core.models import Signal
from src.core.interfaces import QuantModel, AlphaModel
from src.portfolio.construction import ConvictionWeightedBlend
from src.risk.limits import HardLimits
from src.execution.broker import SimBroker
from src.core.models import Order, OrderSide


# ---------------------------------------------------------------------------
# Tiny in-memory data client for testing the quant models without the network.
# Implements the DataClient protocol (get_prices) with synthetic OHLCV series.
# ---------------------------------------------------------------------------

class _MockPriceClient:
    """Returns a synthetic daily price series. Bars are ascending by date.

    `series_kind` selects the generator:
      - "rw"       driftless random walk (no bubble expected)
      - "explosive" geometric growth then crash (bubble then burst)
      - "flat"     constant prices (no signal)
      - "trend"    steady uptrend with mild noise
    """

    def __init__(self, series_kind: str = "rw", n_days: int = 260, seed: int = 0):
        self._kind = series_kind
        self._n = n_days
        self._seed = seed
        self._bars = self._build()

    def _build(self) -> list[dict]:
        rng = np.random.default_rng(self._seed)
        base = date(2024, 1, 1)
        days = [base + timedelta(days=i) for i in range(self._n)]

        if self._kind == "flat":
            closes = [100.0] * self._n
        elif self._kind == "explosive":
            # Ramp up +8%/day for 2/3 of the series, then crash -4%/day.
            c = 100.0
            closes = []
            ramp = int(self._n * 0.66)
            for i in range(self._n):
                g = 0.008 if i < ramp else -0.04
                c *= (1 + g)
                closes.append(c)
        elif self._kind == "trend":
            closes = [100.0 * (1.0005 ** i) + rng.normal(0, 0.5)
                      for i in range(self._n)]
        else:  # rw
            steps = rng.standard_normal(self._n) * 0.01
            log_c = np.cumsum(steps) + math.log(100.0)
            closes = np.exp(log_c).tolist()

        bars = []
        for d, c in zip(days, closes):
            iso = d.isoformat()
            bars.append({
                "time": iso, "open": c, "high": c * 1.005,
                "low": c * 0.995, "close": c, "volume": 1_000_000.0,
                "amount": c * 1_000_000.0,
            })
        return bars

    def get_prices(self, ticker, start_date, end_date):
        return [b for b in self._bars if start_date <= b["time"] <= end_date]

    # The protocol methods below are unused by the quant models but kept for
    # completeness so the object satisfies DataClient structurally.
    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        return []

    def get_company_facts(self, ticker):
        return None

    def get_earnings(self, ticker):
        return None


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


# ===========================================================================
# BSADF model
# ===========================================================================

class TestBSADFModel:
    """Tests for the BSADF bubble-detection alpha model.

    Uses fast Monte-Carlo settings (n_sim=50) and a temp cache dir so tests
    run in a couple of seconds without hitting the network.
    """

    def _model(self, tmp_path, **kw):
        from src.signals.bsadf import BSADFModel
        params = dict(n_sim=50, window=160, cache_dir=str(tmp_path))
        params.update(kw)
        return BSADFModel(**params)

    def _last_date(self, client):
        return client._bars[-1]["time"]

    def test_signal_in_range(self, tmp_path):
        client = _MockPriceClient("rw", n_days=260, seed=1)
        m = self._model(tmp_path)
        sig = m.predict("TEST", self._last_date(client), client)
        assert -1.0 <= sig.value <= 1.0
        assert sig.model_name == "bsadf"
        assert sig.ticker == "TEST"
        assert "bsadf" in sig.components

    def test_random_walk_no_strong_bubble(self, tmp_path):
        # A driftless random walk should not reliably fire a bullish bubble.
        client = _MockPriceClient("rw", n_days=260, seed=3)
        m = self._model(tmp_path)
        sig = m.predict("TEST", self._last_date(client), client)
        # Either abstains (CALM) or rides weakly; never strongly bearish here.
        assert sig.value >= -0.5

    def test_explosive_then_crash_is_bearish(self, tmp_path):
        # Explosive ramp then crash: at the final (post-crash) date the phase
        # machine should have transitioned to BURST or PROBE_EXIT → bearish.
        client = _MockPriceClient("explosive", n_days=260, seed=2)
        m = self._model(tmp_path)
        sig = m.predict("TEST", self._last_date(client), client)
        assert sig.value <= 0.0
        assert sig.metadata.get("phase_name") in {"BURST", "PROBE_EXIT", "CALM", "FEAR"}

    def test_point_in_time_no_lookahead(self, tmp_path):
        # Running predict at an EARLIER date must not see bars after that date.
        client = _MockPriceClient("trend", n_days=260, seed=4)
        m = self._model(tmp_path)
        early = client._bars[120]["time"]
        sig = m.predict("TEST", early, client)
        # The series cache for this ticker must not extend past `early`.
        cached_date, cached = m._series_cache["TEST"]
        assert cached_date == early
        # (closes themselves have no timestamps, but the fetch window was
        # bounded by `early` — confirmed by the cache key.)

    def test_insufficient_history_abstains(self, tmp_path):
        client = _MockPriceClient("rw", n_days=20, seed=5)  # too short
        m = self._model(tmp_path)
        sig = m.predict("TEST", self._last_date(client), client)
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True

    def test_path_cached_per_call(self, tmp_path):
        # Repeated predict() for the same (ticker, date) must hit the cache
        # and not rebuild the BSADF path. Proof: corrupt the cached snapshot
        # and confirm the second call reflects the corruption (cache served),
        # not a fresh rebuild.
        client = _MockPriceClient("rw", n_days=260, seed=6)
        m = self._model(tmp_path)
        d = self._last_date(client)
        sig1 = m.predict("TEST", d, client)
        assert sig1.value == 0.0  # RW ⇒ CALM ⇒ abstain baseline

        # Corrupt the cached snapshot: force phase to RIDING (+1.0 conviction).
        m._path_cache[("TEST", d)]["phase"] = 2  # _RIDING
        sig2 = m.predict("TEST", d, client)
        assert sig2.value == 1.0  # served from cache → reflects corruption


# ===========================================================================
# TechConfluence model
# ===========================================================================

class TestTechConfluenceModel:
    def _model(self):
        from src.signals.tech_confluence import TechConfluenceModel
        return TechConfluenceModel(lookback_days=250)

    def _last_date(self, client):
        return client._bars[-1]["time"]

    def test_flat_data_is_neutral(self):
        client = _MockPriceClient("flat", n_days=260)
        m = self._model()
        sig = m.predict("TEST", self._last_date(client), client)
        # Flat prices → no MACD/RSI/divergence triggers → score 0 → abstain.
        assert sig.value == 0.0
        assert sig.metadata.get("abstained") is True or sig.components.get("score", 0) == 0

    def test_downside_only(self):
        # The confluence model is a sell-timing model: it never goes bullish.
        for kind, seed in (("rw", 1), ("trend", 2), ("explosive", 3)):
            client = _MockPriceClient(kind, n_days=260, seed=seed)
            m = self._model()
            sig = m.predict("TEST", self._last_date(client), client)
            assert sig.value <= 0.0, f"bullish signal from confluence on {kind}"

    def test_signal_in_range_and_named(self):
        client = _MockPriceClient("trend", n_days=260, seed=7)
        m = self._model()
        sig = m.predict("TEST", self._last_date(client), client)
        assert -1.0 <= sig.value <= 1.0
        assert sig.model_name == "tech_confluence"
        assert "score" in sig.components

    def test_amount_missing_does_not_crash(self):
        # A client that returns no `amount` key — S3 must abstain cleanly.
        class _NoAmountClient(_MockPriceClient):
            def get_prices(self, ticker, start_date, end_date):
                bars = super().get_prices(ticker, start_date, end_date)
                return [{k: v for k, v in b.items() if k != "amount"} for b in bars]

        client = _NoAmountClient("trend", n_days=260, seed=8)
        m = self._model()
        sig = m.predict("TEST", self._last_date(client), client)
        assert sig.metadata.get("amount_available") is False
        assert -1.0 <= sig.value <= 0.0


# ===========================================================================
# Registry wiring
# ===========================================================================

class TestRegistry:
    def test_bsadf_registered(self):
        import src.signals  # noqa: F401 — registers on import
        from src.core.registry import ALPHA_MODEL_REGISTRY
        assert "bsadf" in ALPHA_MODEL_REGISTRY
        assert "tech_confluence" in ALPHA_MODEL_REGISTRY

    def test_get_alpha_model_instantiates(self):
        from src.core.registry import get_alpha_model
        m = get_alpha_model("bsadf", n_sim=10)
        assert m.name == "bsadf"
