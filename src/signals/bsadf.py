"""BSADF 泡沫择时 alpha model — Phillips-Shi-Yu (2015) bubble & fear detector.

Ports the battle-tested engine from `D:\philosophy\bsadf` (v1 双向 + v3 骑泡沫)
into the framework as a point-in-time `QuantModel`. No changes to the workflow:
the engine discovers this model via the registry exactly like `pead` /
`buffett` / `ashare_value`.

Method
------
For each as-of date `e`, over the trailing window of log prices we run a
recursive ADF regression over every start point `s <= e - min_win`:

    Δy_t = a + b·y_{t-1} + ε_t      (DF(0), single lag)

and take the supremum of the t-statistic of b:

    BSADF(e) = sup_{s}  t_b([s, e])

Critical values come from a Monte-Carlo simulation under the null
(driftless random walk); BSADF(e) > CV95 ⇒ explosive root ⇒ bubble / 过热.
The mirror — BSADF(e) < CV05 ⇒ panic / 超卖 (from v1).

The conviction is NOT "bubble ⇒ bearish". It follows the v3 *ride-the-bubble*
phase machine:

    CALM       BSADF < CV95              → 0.0   abstain (不错过涨幅)
    IGNITION   BSADF 上穿 CV95           → +1.0  bullish, 骑泡沫
    RIDING     泡沫持续, BSADF 上升      → +1.0  bullish, 继续骑
    FADING     BSADF 从峰值回落          → +0.5→0  线性减仓 (still long)
    BURST      BSADF 跌破 CV90 / 破位    → -1.0  bearish, 崩盘在即
    PROBE_EXIT 试探期假泡沫             → -1.0  bearish
    FEAR       BSADF < CV05 (v1)         → +0.5  contrarian bullish (超卖反弹)

Point-in-time contract
----------------------
The framework calls `predict(ticker, date, data_client)` for ONE date, fresh
each cycle — there is no persistent state. The v3 engine is stateful
(`in_bubble`, `bsadf_peak`, `bubble_entry_price`...), so we replay the full
phase machine over the trailing window up to `as_of` every call. This is
lookahead-free (only bars with `time <= as_of` are used) and cheap thanks to
(a) the persisted `.npy` critical-value cache and (b) per-instance path
memoization keyed by (ticker, date).

References
----------
Phillips, Shi & Yu (2015), "Testing for Multiple Bubbles: Historical
Episodes of Exuberance and Collapse in the S&P 500", IER 56(4).
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from src.core.interfaces import QuantModel
from src.core.models import Signal

# ---------------------------------------------------------------------------
# Defaults — mirror bsadf_model_v3.py / bsadf_model.py
# ---------------------------------------------------------------------------

_WINDOW = 160        # trailing window length (trading days)
_N_SIM = 2000        # Monte-Carlo paths for the critical-value curve
_SEED = 42
_SIG_LEVELS = (0.05, 0.90, 0.95)   # (fear-lower, burst, bubble) quantiles

# v3 ride-the-bubble exit params (param_sweep optimum)
_FADE_THRESHOLD = 0.10   # BSADF peak drawdown that starts FADING
_FADE_FULL = 0.20        # BSADF peak drawdown that completes exit
_TRAILING_STOP = 0.15    # price drawdown from peak → hard exit
_PROBE_DAYS = 5          # adaptive-probe window after bubble entry
_PROBE_MIN_RET = -0.03   # probe-period return floor (below ⇒ fake bubble)
_PROFIT_GUARD = -0.02    # cumulative return since entry (below ⇒ exit)

_LOOKBACK_YEARS = 3.0    # how far back to fetch prices (≈ 1.5× window)

# Phase codes — keep in sync with bsadf_model_v3.generate_positions
_CALM, _IGNITION, _RIDING, _FADING, _BURST, _PROBE_EXIT = 0, 1, 2, 3, 4, 5
_PHASE_NAME = {
    _CALM: "CALM",
    _IGNITION: "IGNITION",
    _RIDING: "RIDING",
    _FADING: "FADING",
    _BURST: "BURST",
    _PROBE_EXIT: "PROBE_EXIT",
    "FEAR": "FEAR",
}

# Where Monte-Carlo critical-value tables are cached (regenerated on demand).
# Gitignored — the cache is reproducible from (T, mw, n_sim, seed).
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "_bsadf_cache")


# ===========================================================================
# Core BSADF math — ported verbatim from bsadf_model_v3.py / bsadf_model.py
# ===========================================================================

def min_window(T: int) -> int:
    """PSY rule for the shortest regression window.

    mw = max(12, ceil(T · (0.01 + 1.8/√T)))
    """
    return max(12, int(np.ceil(T * (0.01 + 1.8 / math.sqrt(T)))))


def adf_tstat_matrix(y: np.ndarray, mw: int) -> np.ndarray:
    """Full DF(0) t-statistic matrix over every window [s, e].

    Returns mat[s, e] = t-stat of the autoregressive coefficient b in
    Δy_t = a + b·y_{t-1} + ε_t  over observations t ∈ [s+1, e].
    Unused cells are -inf. Vectorized via prefix sums (O(T²) after the sums).

    This is the exact implementation from bsadf_model_v3.py / bsadf_model.py.
    """
    y = np.asarray(y, dtype=float)
    T = len(y)
    u = np.diff(y)                                  # u[t-1] = y[t]-y[t-1]
    v = y[:-1]                                      # v[t-1] = y[t-1]
    cu = np.concatenate([[0.0], np.cumsum(u)])
    cv = np.concatenate([[0.0], np.cumsum(v)])
    cuv = np.concatenate([[0.0], np.cumsum(u * v)])
    cuu = np.concatenate([[0.0], np.cumsum(u * u)])
    cvv = np.concatenate([[0.0], np.cumsum(v * v)])

    mat = np.full((T, T), -np.inf)
    for s in range(0, T - mw):
        e_arr = np.arange(s + mw, T)
        a = s
        m = (e_arr - s).astype(float)
        Su = cu[e_arr] - cu[a]
        Sv = cv[e_arr] - cv[a]
        Suv = cuv[e_arr] - cuv[a]
        Suu = cuu[e_arr] - cuu[a]
        Svv = cvv[e_arr] - cvv[a]
        mu_, mv_ = Su / m, Sv / m
        Sxy = Suv - m * mu_ * mv_
        Sxx = Svv - m * mv_ * mv_
        Sxx[Sxx <= 0] = np.nan
        b = Sxy / Sxx
        a_ = mu_ - b * mv_
        rss = Suu - 2 * a_ * Su + m * a_**2 - 2 * b * (Suv - a_ * Sv) + b**2 * Svv
        dof = m - 2
        dof[dof < 1] = np.nan
        sigma2 = rss / dof
        sigma2[sigma2 < 0] = 0.0
        se = np.sqrt(sigma2 / Sxx)
        with np.errstate(divide="ignore", invalid="ignore"):
            t_stat = b / se
        mat[s, e_arr] = t_stat
    return mat


def bsadf_sequence(y: np.ndarray, mw: int) -> np.ndarray:
    """BSADF(e) = sup over start points s <= e-mw of the window-[s,e] DF t-stat.

    Returns a length-T array; the first `mw` entries are NaN (undefined).
    """
    mat = adf_tstat_matrix(y, mw)
    T = len(y)
    bs = np.full(T, np.nan)
    for e in range(mw, T):
        col = mat[: e - mw + 1, e]
        valid = col[col > -np.inf]
        if len(valid) > 0:
            bs[e] = valid.max()
    return bs


def simulate_critical_values(
    T: int,
    mw: int,
    n_sim: int = _N_SIM,
    seed: int = _SEED,
    levels: tuple[float, ...] = _SIG_LEVELS,
    cache_dir: str = _CACHE_DIR,
) -> np.ndarray:
    """Monte-Carlo critical-value curves for BSADF under the driftless-RW null.

    Returns shape (len(levels), T): row k is the `levels[k]` quantile curve.
    Cached to `<cache_dir>/cv_T{T}_mw{mw}_sim{n_sim}_seed{seed}.npy`.
    """
    os.makedirs(cache_dir, exist_ok=True)
    key = f"cv_T{T}_mw{mw}_sim{n_sim}_seed{seed}.npy"
    fp = os.path.join(cache_dir, key)
    if os.path.exists(fp):
        return np.load(fp)

    rng = np.random.default_rng(seed)
    sims = np.empty((n_sim, T))
    for i in range(n_sim):
        rw = np.cumsum(rng.standard_normal(T))
        sims[i] = bsadf_sequence(rw, mw)

    cv = np.full((len(levels), T), np.nan)
    # Per-position quantile across sims, ignoring leading-NaN positions.
    for t in range(T):
        col = sims[:, t]
        finite = col[np.isfinite(col)]
        if finite.size == 0:
            continue
        for k, lv in enumerate(levels):
            cv[k, t] = np.percentile(finite, lv * 100)
    np.save(fp, cv)
    return cv


# ===========================================================================
# v3 phase machine — ported from bsadf_model_v3.generate_positions
# ===========================================================================

def replay_phase_machine(
    bs: np.ndarray,
    cv_burst: np.ndarray,     # CV90 — BURST trigger
    cv_bubble: np.ndarray,    # CV95 — IGNITION trigger
    prices: np.ndarray,
    *,
    fade_threshold: float = _FADE_THRESHOLD,
    fade_full: float = _FADE_FULL,
    trailing_stop: float = _TRAILING_STOP,
    probe_days: int = _PROBE_DAYS,
    probe_min_ret: float = _PROBE_MIN_RET,
    profit_guard: float = _PROFIT_GUARD,
    ride_bubble: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Replay the v3 ride-the-bubble phase machine over a BSADF path.

    Returns (phase[T], pos[T]) where phase codes are the _CALM.._PROBE_EXIT
    constants above and pos ∈ [0,1] is the v3 target weight. Identical logic
    to bsadf_model_v3.generate_positions.
    """
    T = len(bs)
    pos = np.ones(T)                 # CALM ⇒ 1.0 (full position, ride rallies)
    phase = np.zeros(T, dtype=int)

    in_bubble = False
    bsadf_peak = -np.inf
    price_peak = 0.0
    bubble_entry_price = 0.0
    bubble_entry_t = -1

    for t in range(T):
        if np.isnan(bs[t]):
            pos[t] = 1.0
            phase[t] = _CALM
            continue

        if not in_bubble:
            if bs[t] > cv_bubble[t]:
                in_bubble = True
                bsadf_peak = bs[t]
                price_peak = prices[t]
                bubble_entry_price = prices[t]
                bubble_entry_t = t
                pos[t] = 1.0
                phase[t] = _IGNITION
            else:
                pos[t] = 1.0
                phase[t] = _CALM
            continue

        # --- inside a bubble ---
        bsadf_peak = max(bsadf_peak, bs[t])
        price_peak = max(price_peak, prices[t])

        # adaptive probe: first PROBE_DAYS days after entry
        days_in = t - bubble_entry_t
        bubble_ret = prices[t] / bubble_entry_price - 1.0 if bubble_entry_price else 0.0
        if days_in <= probe_days and bubble_ret < probe_min_ret:
            in_bubble = False
            pos[t] = 0.0
            phase[t] = _PROBE_EXIT
            continue

        # profit guard: underwater since entry → bail
        if bubble_ret < profit_guard:
            in_bubble = False
            pos[t] = 0.0
            phase[t] = _BURST
            continue

        # BSADF crashes below the lower critical line → bubble burst
        if bs[t] < cv_burst[t]:
            in_bubble = False
            pos[t] = 0.0
            phase[t] = _BURST
            continue

        # price trailing stop
        price_dd = 1.0 - prices[t] / price_peak if price_peak > 0 else 0.0
        if price_dd > trailing_stop:
            in_bubble = False
            pos[t] = 0.0
            phase[t] = _BURST
            continue

        # FADING: linear ramp from full to zero as BSADF rolls off its peak.
        # Guard the divide: if bsadf_peak is non-finite (extreme synthetic
        # explosive series), skip FADING and treat as still RIDING.
        denom = bsadf_peak + 1e-10
        if not np.isfinite(denom) or denom <= 1e-10:
            pos[t] = 1.0
            phase[t] = _RIDING
            continue
        bsadf_dd = (bsadf_peak - bs[t]) / denom
        if bsadf_dd < fade_threshold:
            pos[t] = 1.0
            phase[t] = _RIDING
        elif bsadf_dd < fade_full:
            ratio = (bsadf_dd - fade_threshold) / (fade_full - fade_threshold)
            pos[t] = 1.0 - ratio
            phase[t] = _FADING
        else:
            in_bubble = False
            pos[t] = 0.0
            phase[t] = _BURST

    return phase, pos


# ===========================================================================
# Alpha model
# ===========================================================================

class BSADFModel(QuantModel):
    """BSADF bubble / overheat / panic detector → conviction in [-1, +1].

    See module docstring for the full method and phase→conviction mapping.
    All constructor params arrive from the strategy YAML `params:` block.
    """

    def __init__(
        self,
        window: int = _WINDOW,
        min_win: int | None = None,       # None ⇒ PSY rule
        n_sim: int = _N_SIM,
        seed: int = _SEED,
        sig_levels: tuple[float, ...] | None = None,   # (fear, burst, bubble)
        fade_threshold: float = _FADE_THRESHOLD,
        fade_full: float = _FADE_FULL,
        trailing_stop: float = _TRAILING_STOP,
        probe_days: int = _PROBE_DAYS,
        probe_min_ret: float = _PROBE_MIN_RET,
        profit_guard: float = _PROFIT_GUARD,
        ride_bubble: bool = True,
        fear_strength: float = 0.5,       # conviction when BSADF < CV05
        lookback_years: float = _LOOKBACK_YEARS,
        min_history: int | None = None,   # absolute floor on bar count; default = window
        cache_dir: str | None = None,
        verbose: bool = False,
        **kwargs,
    ):
        self._window = window
        self._min_win = min_win
        self._n_sim = n_sim
        self._seed = seed
        # Normalize: ensure exactly (fear-lower, burst, bubble) ordering.
        if sig_levels is None:
            sig_levels = _SIG_LEVELS
        self._sig_levels = tuple(sig_levels)
        self._fade_threshold = fade_threshold
        self._fade_full = fade_full
        self._trailing_stop = trailing_stop
        self._probe_days = probe_days
        self._probe_min_ret = probe_min_ret
        self._profit_guard = profit_guard
        self._ride_bubble = ride_bubble
        self._fear_strength = fear_strength
        self._lookback_years = lookback_years
        # Absolute minimum bar count. The PSY mw alone (~25 for T=160) is too
        # thin to be statistically meaningful, so floor at the full window by
        # default — the model abstains until it has a complete window.
        self._min_history = min_history if min_history is not None else self._window
        self._cache_dir = cache_dir or _CACHE_DIR
        self._verbose = verbose

        # Memoize the computed path per (ticker, date) within a process.
        # The BSADF sequence + MC sim are the expensive bits; within one
        # fund cycle the same (ticker, date) is queried exactly once.
        self._path_cache: dict[tuple[str, str], dict[str, Any]] = {}
        # Cache the raw price series per ticker (refetched only if date moves).
        self._series_cache: dict[str, tuple[str, list[float]]] = {}

    @property
    def name(self) -> str:
        return "bsadf"

    # ------------------------------------------------------------------
    # AlphaModel contract
    # ------------------------------------------------------------------

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        cache_key = (ticker, date)
        if cache_key not in self._path_cache:
            try:
                built = self._build(ticker, date, data_client)
            except Exception as exc:
                return self._abstain(ticker, date, f"BSADF build error: {exc}")
            if built is None:
                # Insufficient history — already returned an abstain signal.
                return self._abstain(ticker, date, "insufficient price history")
            self._path_cache[cache_key] = built
        snap = self._path_cache[cache_key]
        return self._emit(ticker, date, snap)

    # ------------------------------------------------------------------
    # Build: fetch data → BSADF path → phase machine → snapshot at as_of
    # ------------------------------------------------------------------

    def _build(
        self, ticker: str, date: str, data_client: Any
    ) -> dict[str, Any] | None:
        closes = self._load_closes(ticker, date, data_client)
        if len(closes) < self._min_history:
            return None

        closes_arr = np.asarray(closes, dtype=float)
        T = len(closes_arr)

        # Take the trailing window (or full history if shorter).
        window = min(self._window, T)
        idx = T - window
        win_close = closes_arr[idx:]
        win_T = len(win_close)

        mw = self._min_win if self._min_win is not None else min_window(win_T)
        if win_T <= mw:
            return None

        logp = np.log(win_close[win_close > 0])
        if len(logp) < mw + 1:
            return None

        bs = bsadf_sequence(logp, mw)

        # Critical-value curves: (fear-lower, burst, bubble) quantile rows.
        cv = simulate_critical_values(
            win_T, mw,
            n_sim=self._n_sim, seed=self._seed,
            levels=self._sig_levels, cache_dir=self._cache_dir,
        )
        # Three named curves, forward-filled over leading NaNs.
        cv_fear = self._ffill(cv[0])
        cv_burst = self._ffill(cv[1])
        cv_bubble = self._ffill(cv[2])

        # Replay the v3 phase machine over the window.
        phase, pos = replay_phase_machine(
            bs, cv_burst, cv_bubble, win_close,
            fade_threshold=self._fade_threshold,
            fade_full=self._fade_full,
            trailing_stop=self._trailing_stop,
            probe_days=self._probe_days,
            probe_min_ret=self._probe_min_ret,
            profit_guard=self._profit_guard,
            ride_bubble=self._ride_bubble,
        )

        last = win_T - 1
        return {
            "bsadf": float(bs[last]) if not np.isnan(bs[last]) else float("nan"),
            "cv_fear": float(cv_fear[last]),
            "cv_burst": float(cv_burst[last]),
            "cv_bubble": float(cv_bubble[last]),
            "phase": int(phase[last]),
            "pos": float(pos[last]),
            "price": float(win_close[last]),
            # window-edge stats for reasoning transparency
            "bsadf_peak": float(np.nanmax(bs)) if np.isfinite(bs).any() else float("nan"),
        }

    # ------------------------------------------------------------------
    # Emit: map the window-edge snapshot to a Signal
    # ------------------------------------------------------------------

    def _emit(self, ticker: str, date: str, snap: dict[str, Any]) -> Signal:
        bs = snap["bsadf"]
        cv_fear = snap["cv_fear"]
        cv_burst = snap["cv_burst"]
        cv_bubble = snap["cv_bubble"]
        phase = snap["phase"]
        pos = snap["pos"]

        # --- conviction mapping ---
        value = 0.0
        tag = _PHASE_NAME.get(phase, f"P{phase}")

        if not math.isnan(bs) and bs < cv_fear:
            # v1 fear / panic bottom — contrarian bullish.
            value = self._fear_strength
            tag = "FEAR"
        else:
            value = self._phase_to_conviction(phase, pos)

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=round(max(-1.0, min(1.0, value)), 4),
            reasoning=self._reasoning(snap, tag),
            components={
                "bsadf": round(bs, 4) if not math.isnan(bs) else 0.0,
                "cv_fear": round(cv_fear, 4),
                "cv_burst": round(cv_burst, 4),
                "cv_bubble": round(cv_bubble, 4),
                "phase": float(phase),
                "pos": round(pos, 4),
            },
            metadata={
                "phase_name": tag,
                "in_bubble": phase in (_IGNITION, _RIDING, _FADING),
                "ride_bubble": self._ride_bubble,
                "bsadf_peak": round(snap["bsadf_peak"], 4)
                              if not math.isnan(snap["bsadf_peak"]) else None,
            },
        )

    @staticmethod
    def _phase_to_conviction(phase: int, pos: float) -> float:
        """Map the v3 phase/position to a conviction in [-1, +1].

        CALM → abstain; IGNITION/RIDING → full bullish; FADING → decaying
        bullish (mirrors the 1.0→0.0 position ramp); BURST/PROBE_EXIT → bearish.
        """
        if phase == _CALM:
            return 0.0
        if phase in (_IGNITION, _RIDING):
            return 1.0
        if phase == _FADING:
            # FADING position ramps 1.0→0.0; conviction ramps +0.5→0.0.
            return 0.5 * pos
        # _BURST, _PROBE_EXIT
        return -1.0

    @staticmethod
    def _reasoning(snap: dict[str, Any], tag: str) -> str:
        bs = snap["bsadf"]
        cv_b = snap["cv_bubble"]
        cv_90 = snap["cv_burst"]
        pos = snap["pos"]
        bs_s = f"{bs:.2f}" if not math.isnan(bs) else "nan"
        over = "explosive" if (not math.isnan(bs) and bs > cv_b) else "normal"
        return (
            f"BSADF={bs_s} vs CV95={cv_b:.2f} CV90={cv_90:.2f} "
            f"({over}) | phase={tag} pos={pos:.0%}"
        )

    # ------------------------------------------------------------------
    # Data loading — point-in-time
    # ------------------------------------------------------------------

    def _load_closes(
        self, ticker: str, date: str, data_client: Any
    ) -> list[float]:
        """Fetch daily closes up to `date` (point-in-time), chronological.

        Mirrors the pead.py pattern: only bars with time <= as_of are used.
        The series is cached per ticker and refetched when `date` moves past
        what we already hold.
        """
        cached_date, cached = self._series_cache.get(ticker, ("", []))
        if cached and cached_date >= date:
            return cached

        as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
        start = (as_of - timedelta(days=int(365 * self._lookback_years))).isoformat()
        try:
            bars = data_client.get_prices(ticker, start, date)
        except Exception:
            return []

        closes = [
            float(b["close"])
            for b in sorted(
                (x for x in bars
                 if (x.get("time") or "")[:10] <= date
                 and _is_positive_number(x.get("close"))),
                key=lambda x: (x.get("time") or "")[:10],
            )
        ]
        self._series_cache[ticker] = (date, closes)
        return closes

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ffill(arr: np.ndarray) -> np.ndarray:
        """Forward-fill leading NaNs with the first finite value (or 0)."""
        out = np.asarray(arr, dtype=float).copy()
        finite = np.where(np.isfinite(out))[0]
        if len(finite) == 0:
            out[:] = 0.0
            return out
        first = finite[0]
        if first > 0:
            out[:first] = out[first]
        return out

    def _abstain(self, ticker: str, date: str, why: str) -> Signal:
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=0.0,
            reasoning=why,
            metadata={"abstained": True},
        )


def _is_positive_number(v: Any) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf")) and f > 0
