"""A-share quant value model — a Buffett-style fundamental screen.

Unlike `BuffettAgent` (which needs an LLM to reason over fundamentals),
this is a pure-math `QuantModel` that scores A-shares from the metrics the
妙想 (MX) data client returns: ROE, gross margin, net margin, PE, PB.

Scoring (each sub-score in [-1, +1], then weighted-summed):
  - quality    : ROE and gross/net margins reward durable, profitable businesses
  - valuation  : PE and PB reward cheapness, but penalize value traps (loss-makers)
  - growth     : revenue / net-income growth (when available) rewards expansion
The weighted sum is clamped to [-1, +1] and reported as the Signal value,
with the sub-scores exposed in `components` for transparency.

Designed to run on 妙想-backed `MXDataClient`, but it only relies on the
DataClient protocol (`get_financial_metrics`), so any data client that
returns the canonical metric keys works too.
"""

from __future__ import annotations

from typing import Any

from src.core.interfaces import QuantModel
from src.core.models import Signal


class AshareValueModel(QuantModel):
    """Buffett-style quant value screen for A-shares."""

    def __init__(
        self,
        quality_weight: float = 0.5,
        valuation_weight: float = 0.35,
        growth_weight: float = 0.15,
        # Valuation cutoffs used to map raw ratios to [-1, +1].
        pe_good: float = 15.0,
        pe_bad: float = 40.0,
        pb_good: float = 2.0,
        pb_bad: float = 8.0,
        roe_good: float = 15.0,   # %
        roe_bad: float = 5.0,
    ):
        self._qw = quality_weight
        self._vw = valuation_weight
        self._gw = growth_weight
        self._pe_good = pe_good
        self._pe_bad = pe_bad
        self._pb_good = pb_good
        self._pb_bad = pb_bad
        self._roe_good = roe_good
        self._roe_bad = roe_bad

    @property
    def name(self) -> str:
        return "ashare_value"

    # ------------------------------------------------------------------
    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        try:
            metrics = data_client.get_financial_metrics(
                ticker, date, limit=10
            )
        except Exception as exc:
            return self._abstain(ticker, date, f"data error: {exc}")

        if not metrics:
            return self._abstain(ticker, date, "no fundamentals returned")

        # 妙想 returns valuation (PE/PB, daily) and statement metrics
        # (ROE/margins/revenue, quarterly) on different rows. Merge them by
        # taking each field from the most recent row that actually has it.
        latest = self._merge_latest(metrics)
        quality = self._quality_score(latest)
        valuation = self._valuation_score(latest)
        growth = self._growth_score(metrics)

        value = (
            self._qw * quality
            + self._vw * valuation
            + self._gw * growth
        )
        value = max(-1.0, min(1.0, value))

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=round(value, 4),
            reasoning=self._reasoning(latest, quality, valuation, growth),
            components={
                "quality": round(quality, 4),
                "valuation": round(valuation, 4),
                "growth": round(growth, 4),
            },
            metadata={
                "pe_ratio": latest.get("pe_ratio"),
                "pb_ratio": latest.get("pb_ratio"),
                "roe": latest.get("roe"),
                "gross_margin": latest.get("gross_margin"),
                "net_margin": latest.get("net_margin"),
            },
        )

    # ------------------------------------------------------------------
    # Sub-scores
    # ------------------------------------------------------------------
    def _quality_score(self, m: dict[str, Any]) -> float:
        """Reward high ROE and strong margins."""
        roe = self._pct(m.get("roe"))
        gross = self._pct(m.get("gross_margin"))
        net = self._pct(m.get("net_margin"))

        score = 0.0
        n = 0
        if roe is not None:
            score += self._map_high_better(roe, self._roe_good, self._roe_bad)
            n += 1
        if gross is not None:
            # Gross margin > 50% is excellent, < 15% poor.
            score += self._map_high_better(gross, 50.0, 15.0)
            n += 1
        if net is not None:
            score += self._map_high_better(net, 25.0, 0.0)
            n += 1
        return score / n if n else 0.0

    def _valuation_score(self, m: dict[str, Any]) -> float:
        """Reward cheapness via PE and PB; penalize loss-makers."""
        pe = self._num(m.get("pe_ratio"))
        pb = self._num(m.get("pb_ratio"))

        # Negative or missing PE means the company loses money — penalize.
        if pe is None or pe <= 0:
            pe_score = -0.5
        else:
            pe_score = self._map_low_better(pe, self._pe_good, self._pe_bad)

        if pb is None or pb <= 0:
            pb_score = -0.5
        else:
            pb_score = self._map_low_better(pb, self._pb_good, self._pb_bad)

        return 0.6 * pe_score + 0.4 * pb_score

    def _growth_score(self, metrics: list[dict[str, Any]]) -> float:
        """Reward revenue / net-income growth across the most recent periods."""
        if len(metrics) < 2:
            return 0.0
        rev_growth = self._series_growth(metrics, "revenue")
        ni_growth = self._series_growth(metrics, "net_income")
        scores = [g for g in (rev_growth, ni_growth) if g is not None]
        if not scores:
            return 0.0
        avg = sum(scores) / len(scores)
        # Map -20%..+30% growth onto [-1, +1].
        return self._map_high_better(avg * 100.0, 30.0, -20.0)

    # ------------------------------------------------------------------
    # Numeric helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _merge_latest(metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge a metric series into one dict, taking each field from the
        most recent row where it is present.

        妙想 splits valuation (PE/PB, daily) and statement fields (ROE,
        margins, revenue) across different rows by date, so `metrics[0]`
        alone is usually missing the statement fields.
        """
        merged: dict[str, Any] = {}
        for row in metrics:  # already newest-first
            for k, v in row.items():
                if k in ("ticker", "date", "period"):
                    merged.setdefault(k, v)
                    continue
                if v is None or v == "":
                    continue
                if k not in merged or merged[k] in (None, ""):
                    merged[k] = v
        return merged

    @staticmethod
    def _num(v: Any) -> float | None:
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f

    def _pct(self, v: Any) -> float | None:
        """Parse a value that 妙想 may return as '51.47' (already percent) or 0.5147."""
        f = self._num(v)
        if f is None:
            return None
        # 妙想 returns ratios like ROE/margin as plain percent numbers (e.g. 51.47).
        # Ratios stored as fractions (<=1) get normalized to percent.
        return f * 100.0 if abs(f) <= 1.0 else f

    @staticmethod
    def _map_high_better(x: float, good: float, bad: float) -> float:
        """Map x onto [-1, +1] where higher is better. good -> +1, bad -> -1."""
        if good == bad:
            return 0.0
        t = (x - bad) / (good - bad)
        return max(-1.0, min(1.0, t))

    @staticmethod
    def _map_low_better(x: float, good: float, bad: float) -> float:
        """Map x onto [-1, +1] where lower is better. good -> +1, bad -> -1."""
        if good == bad:
            return 0.0
        t = (bad - x) / (bad - good)
        return max(-1.0, min(1.0, t))

    def _series_growth(
        self, metrics: list[dict[str, Any]], key: str
    ) -> float | None:
        """Earliest-vs-latest total growth rate for a metric series."""
        vals = [self._num(m.get(key)) for m in metrics]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return None
        latest, earliest = vals[0], vals[-1]
        if earliest in (0, None):
            return None
        return (latest - earliest) / abs(earliest)

    # ------------------------------------------------------------------
    def _reasoning(
        self, m: dict[str, Any], q: float, v: float, g: float
    ) -> str:
        pe = m.get("pe_ratio")
        pb = m.get("pb_ratio")
        roe = m.get("roe")
        return (
            f"A-share value screen: quality={q:+.2f} valuation={v:+.2f} "
            f"growth={g:+.2f} | PE={pe} PB={pb} ROE={roe}"
        )

    def _abstain(self, ticker: str, date: str, why: str) -> Signal:
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=0.0,
            reasoning=why,
            metadata={"abstained": True},
        )
