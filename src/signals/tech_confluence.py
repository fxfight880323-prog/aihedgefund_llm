"""技术共振 alpha model — 机械式卖出信号库 (Technical Confluence).

Ports the signal library from `D:\philosophy\bsadf\signals.py` into the
framework as a point-in-time `QuantModel`. Designed to layer with `bsadf`:
where BSADF detects the statistical bubble regime, this model supplies the
*mechanical* exit timing inside the FADING window — the precise "今天卖" that
BSADF (a daily close-log statistic) cannot resolve on its own.

Signal library (from research_sell_signals.md Part 2):
  S1  macd_area_divergence   MACD 红柱面积顶背离
  S2  rsi_overbought_flag    RSI 超买钝化状态 (状态乘子)
  S3  volume_divergence      缩量创新高 (需成交额 amount)
  S4  chandelier_breach      Chandelier Exit 硬地板破位
  S5  macd_dead_cross        MACD 死叉 (决胜项, ×0.5)

confluence_score = S1 + S2 + S3 + S4 + 0.5·S5   (range 0–4.5)

This is a **downside-only** model: it only ever emits bearish or neutral
conviction. Blend it with `bsadf` (which emits the bullish ride) via model
weights in the strategy YAML:

    models:
      - name: bsadf
        weight: 0.7
      - name: tech_confluence
        weight: 0.3

Conviction mapping (confluence_score → value):
  score ≥ 3   → -1.0   强共振, clear sell
  score ≥ 2   → -0.5   共振 building
  score ≥ 1   → -0.25  early warning
  score  0    →  0.0   abstain (no exit signal)

All data comes from the DataClient `get_prices` OHLCV bars. The volume-
divergence sub-signal (S3) needs `amount` (成交额); if the data client does
not supply it (US tickers, or MXDataClient before the amount edit), S3
gracefully abstains and the other four signals still fire.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.core.interfaces import QuantModel
from src.core.models import Signal


# ===========================================================================
# Base indicators — ported verbatim from signals.py
# ===========================================================================

def ema(series, period):
    """指数移动平均 (pandas ewm 等价, alpha=2/(period+1))."""
    s = pd.Series(series, dtype=float)
    return s.ewm(span=period, adjust=False).mean().values


def atr(high, low, close, period=22):
    """Wilder ATR. TR = max(H-L, |H-prevC|, |L-prevC|)."""
    high = np.asarray(high, float); low = np.asarray(low, float)
    close = np.asarray(close, float)
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
    a = pd.Series(tr).ewm(alpha=1 / period, adjust=False).mean().values
    return a


def rsi(close, period=14):
    """Wilder RSI."""
    close = pd.Series(close, dtype=float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out.iloc[:period] = np.nan
    return out.values


def macd(close, fast=12, slow=26, signal=9):
    """标准 MACD. 返回 (dif, dea, hist). hist 含中文惯例 ×2."""
    c = np.asarray(close, float)
    dif = ema(c, fast) - ema(c, slow)
    dea = ema(dif, signal)
    hist = 2 * (dif - dea)
    return dif, dea, hist


def rolling_max(arr, window):
    s = pd.Series(arr)
    return s.rolling(window, min_periods=1).max().values


def rolling_mean(arr, window):
    s = pd.Series(arr)
    return s.rolling(window, min_periods=1).mean().values


# ===========================================================================
# S4: Chandelier Exit 硬地板
# ===========================================================================

def chandelier_exit(high, low, close, period=22, mult=3.5):
    """Chandelier Exit (多头). exit = HHV(high, period) - mult * ATR(period)."""
    hh = rolling_max(high, period)
    a = atr(high, low, close, period)
    return hh - mult * a


def chandelier_breach(high, low, close, period=22, mult=3.5):
    """返回 1/0 数组: close < chandelier_exit 当日为 1."""
    ex = chandelier_exit(high, low, close, period, mult)
    close = np.asarray(close, float)
    return (close < ex).astype(int)


# ===========================================================================
# S1: MACD 柱面积顶背离
# ===========================================================================

def _hist_segments(hist):
    """把 hist 序列按符号变化切分为同号段. 返回 list of (start, end, sign, area)."""
    hist = np.asarray(hist, float)
    n = len(hist)
    segs = []
    i = 0
    while i < n and (np.isnan(hist[i]) or hist[i] == 0):
        i += 1
    if i >= n:
        return segs
    cur_sign = 1 if hist[i] > 0 else -1
    seg_start = i
    seg_area = 0.0
    for j in range(i, n):
        if np.isnan(hist[j]):
            if j > seg_start:
                segs.append((seg_start, j - 1, cur_sign, seg_area))
            seg_start = j + 1
            seg_area = 0.0
            cur_sign = 0
            continue
        s = 1 if hist[j] > 0 else (-1 if hist[j] < 0 else cur_sign)
        if cur_sign == 0:
            cur_sign = s
            seg_start = j
            seg_area = 0.0
        if s == cur_sign or hist[j] == 0:
            seg_area += hist[j]
        else:
            segs.append((seg_start, j - 1, cur_sign, seg_area))
            seg_start = j
            seg_area = hist[j]
            cur_sign = s
    if seg_start < n and cur_sign != 0:
        segs.append((seg_start, n - 1, cur_sign, seg_area))
    return segs


def macd_area_divergence(close, high_lookback=60, area_ratio=0.8,
                         fast=12, slow=26, signal=9):
    """MACD 红柱面积顶背离. 返回 1/0 数组 (在死叉日标记)."""
    close = np.asarray(close, float)
    n = len(close)
    _, _, hist = macd(close, fast, slow, signal)
    segs = _hist_segments(hist)
    out = np.zeros(n, int)
    red_segs = [(s, e, a) for (s, e, sign, a) in segs if sign > 0 and e - s >= 1]
    for k in range(1, len(red_segs)):
        s0, e0, a0 = red_segs[k - 1]
        s1, e1, a1 = red_segs[k]
        if a0 <= 0 or a1 >= area_ratio * a0:
            continue
        p0 = close[s0:e0 + 1].max()
        p1 = close[s1:e1 + 1].max()
        if p1 <= p0:
            continue
        lb_start = max(0, e1 - high_lookback)
        ref = np.quantile(close[lb_start:e1 + 1], 0.9)
        if p1 < ref:
            continue
        if e1 < n:
            out[e1] = 1
    return out


# ===========================================================================
# S2: RSI 超买钝化状态
# ===========================================================================

def rsi_overbought_flag(close, period=14, ob_threshold=80, min_days=5):
    """RSI 钝化状态标志. RSI>阈值 连续≥min_days → 1. 返回 1/0 数组."""
    r = rsi(close, period)
    n = len(close)
    out = np.zeros(n, int)
    count = 0
    armed = False
    for i in range(n):
        if np.isnan(r[i]):
            continue
        if r[i] > ob_threshold:
            count += 1
            if count >= min_days:
                armed = True
        else:
            count = 0
            armed = False
        out[i] = 1 if armed else 0
    return out


# ===========================================================================
# S3: 缩量创新高 (volume divergence) — needs amount
# ===========================================================================

def volume_divergence(high, amount, close, open_, period=20, vol_ratio=0.7,
                      limit_up_tol=0.005):
    """缩量创新高. HIGH == HHV(HIGH, period) AND amount < ratio * MA(amount).
    涨停日禁用. amount 用成交额(元). 返回 1/0 数组.

    Gracefully returns all-zeros if `amount` is None/empty.
    """
    if amount is None:
        return np.zeros(len(close) if hasattr(close, '__len__') else 0, int)
    high = np.asarray(high, float)
    amount = np.asarray(amount, float)
    close = np.asarray(close, float)
    open_ = np.asarray(open_, float)
    n = len(close)
    out = np.zeros(n, int)
    if n == 0 or np.all(np.isnan(amount)) or np.all(amount == 0):
        return out
    hh = rolling_max(high, period)
    amt_ma = rolling_mean(amount, period)
    for i in range(period, n):
        gain = (close[i] / open_[i] - 1) if open_[i] > 0 else 0
        if gain >= 0.095:
            continue
        if (high[i] >= hh[i] - 1e-9 and amt_ma[i] > 0
                and not np.isnan(amount[i])
                and amount[i] < vol_ratio * amt_ma[i]):
            out[i] = 1
    return out


# ===========================================================================
# S5: MACD 死叉 (决胜项)
# ===========================================================================

def macd_dead_cross(close, fast=12, slow=26, signal=9):
    """DIF 下穿 DEA 当日为 1."""
    dif, dea, _ = macd(close, fast, slow, signal)
    n = len(close)
    out = np.zeros(n, int)
    for i in range(1, n):
        if (np.isnan(dif[i]) or np.isnan(dea[i])
                or np.isnan(dif[i - 1]) or np.isnan(dea[i - 1])):
            continue
        if dif[i - 1] >= dea[i - 1] and dif[i] < dea[i]:
            out[i] = 1
    return out


# ===========================================================================
# Combined confluence score
# ===========================================================================

def confluence_score(high, low, close, open_, amount,
                     ch_period=22, ch_mult=3.5,
                     macd_lookback=60, macd_area_ratio=0.8,
                     rsi_period=14, rsi_ob=80, rsi_min_days=5,
                     vol_period=20, vol_ratio=0.7):
    """每日共振分 = S1+S2+S3+S4+0.5*S5. 返回 (score[T], components dict)."""
    s1 = macd_area_divergence(close, macd_lookback, macd_area_ratio)
    s2 = rsi_overbought_flag(close, rsi_period, rsi_ob, rsi_min_days)
    s3 = volume_divergence(high, amount, close, open_, vol_period, vol_ratio)
    s4 = chandelier_breach(high, low, close, ch_period, ch_mult)
    s5 = macd_dead_cross(close)
    score = (s1.astype(float) + s2.astype(float) + s3.astype(float)
             + s4.astype(float) + 0.5 * s5.astype(float))
    comps = {"s1_macd_div": s1, "s2_rsi_ob": s2, "s3_vol_div": s3,
             "s4_chandelier": s4, "s5_macd_x": s5, "score": score}
    return score, comps


# ===========================================================================
# Alpha model
# ===========================================================================

class TechConfluenceModel(QuantModel):
    """Technical confluence sell-signal model → bearish conviction.

    Downside-only: emits negative conviction proportional to the confluence
    score, or 0.0 (abstain) when no sell signal is present. Reads OHLCV from
    `data_client.get_prices`; the volume-divergence sub-signal (S3) also
    uses `amount` when the data client provides it (see MXDataClient).
    """

    def __init__(
        self,
        lookback_days: int = 250,
        ch_period: int = 22,
        ch_mult: float = 3.5,
        macd_lookback: int = 60,
        macd_area_ratio: float = 0.8,
        rsi_period: int = 14,
        rsi_ob: float = 80.0,
        rsi_min_days: int = 5,
        vol_period: int = 20,
        vol_ratio: float = 0.7,
        strong_threshold: float = 3.0,   # score ≥ this → -1.0
        mid_threshold: float = 2.0,      # score ≥ this → -0.5
        weak_threshold: float = 1.0,     # score ≥ this → -0.25
        strong_conv: float = -1.0,
        mid_conv: float = -0.5,
        weak_conv: float = -0.25,
        **kwargs,
    ):
        self._lookback_days = lookback_days
        self._cfg = dict(
            ch_period=ch_period, ch_mult=ch_mult,
            macd_lookback=macd_lookback, macd_area_ratio=macd_area_ratio,
            rsi_period=rsi_period, rsi_ob=rsi_ob, rsi_min_days=rsi_min_days,
            vol_period=vol_period, vol_ratio=vol_ratio,
        )
        self._strong_threshold = strong_threshold
        self._mid_threshold = mid_threshold
        self._weak_threshold = weak_threshold
        self._strong_conv = strong_conv
        self._mid_conv = mid_conv
        self._weak_conv = weak_conv
        self._cache: dict[str, tuple[str, list[dict]]] = {}

    @property
    def name(self) -> str:
        return "tech_confluence"

    # ------------------------------------------------------------------

    def predict(self, ticker: str, date: str, data_client: Any) -> Signal:
        bars = self._load_bars(ticker, date, data_client)
        if len(bars) < 40:   # need enough history for MACD(26)+lookbacks
            return self._abstain(ticker, date, "insufficient OHLCV history")

        close = np.array([b["close"] for b in bars], float)
        high = np.array([b.get("high", b["close"]) for b in bars], float)
        low = np.array([b.get("low", b["close"]) for b in bars], float)
        open_ = np.array([b.get("open", b["close"]) for b in bars], float)
        # amount is optional — S3 abstains if missing.
        amount = None
        if any(b.get("amount") not in (None, 0) for b in bars):
            amount = np.array([b.get("amount") or np.nan for b in bars], float)

        score, comps = confluence_score(
            high, low, close, open_, amount, **self._cfg,
        )
        last_score = float(score[-1])

        value = self._score_to_conviction(last_score)

        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=date,
            value=round(value, 4),
            reasoning=self._reasoning(last_score, comps),
            components={
                "score": round(last_score, 2),
                "s1_macd_div": int(comps["s1_macd_div"][-1]),
                "s2_rsi_ob": int(comps["s2_rsi_ob"][-1]),
                "s3_vol_div": int(comps["s3_vol_div"][-1]),
                "s4_chandelier": int(comps["s4_chandelier"][-1]),
                "s5_macd_x": int(comps["s5_macd_x"][-1]),
            },
            metadata={
                "amount_available": amount is not None,
            },
        )

    # ------------------------------------------------------------------

    def _score_to_conviction(self, score: float) -> float:
        if score >= self._strong_threshold:
            return self._strong_conv
        if score >= self._mid_threshold:
            return self._mid_conv
        if score >= self._weak_threshold:
            return self._weak_conv
        return 0.0

    @staticmethod
    def _reasoning(score: float, comps: dict) -> str:
        parts = []
        for key, label in (
            ("s1_macd_div", "MACD背离"), ("s2_rsi_ob", "RSI钝化"),
            ("s3_vol_div", "缩量新高"), ("s4_chandelier", "破位"),
            ("s5_macd_x", "MACD死叉"),
        ):
            if int(comps[key][-1]):
                parts.append(label)
        fired = "+".join(parts) if parts else "无信号"
        return f"共振分={score:.1f} ({fired})"

    # ------------------------------------------------------------------
    # Data loading — point-in-time
    # ------------------------------------------------------------------

    def _load_bars(
        self, ticker: str, date: str, data_client: Any
    ) -> list[dict]:
        cached_date, cached = self._cache.get(ticker, ("", []))
        if cached and cached_date >= date:
            return cached

        as_of = datetime.strptime(date[:10], "%Y-%m-%d").date()
        start = (as_of - timedelta(days=int(self._lookback_days * 1.6))).isoformat()
        try:
            raw = data_client.get_prices(ticker, start, date)
        except Exception:
            return []

        bars = sorted(
            (b for b in raw if (b.get("time") or "")[:10] <= date
             and _is_number(b.get("close"))),
            key=lambda b: (b.get("time") or "")[:10],
        )
        self._cache[ticker] = (date, bars)
        return bars

    def _abstain(self, ticker: str, date: str, why: str) -> Signal:
        return Signal(
            model_name=self.name, ticker=ticker, date=date,
            value=0.0, reasoning=why, metadata={"abstained": True},
        )


def _is_number(v: Any) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))
