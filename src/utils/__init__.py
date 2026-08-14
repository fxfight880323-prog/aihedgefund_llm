"""Utility functions."""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any


def parse_date(s: str) -> date:
    """Parse a date string (YYYY-MM-DD or ISO datetime)."""
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def trading_days(start: str, end: str) -> list[str]:
    """Generate weekday dates between start and end (no holiday calendar)."""
    d1 = parse_date(start)
    d2 = parse_date(end)
    days: list[str] = []
    current = d1
    while current <= d2:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert to float, returning default for NaN/None/errors."""
    if value is None:
        return default
    try:
        f = float(value)
        return default if (f != f or f in (float("inf"), float("-inf"))) else f
    except (ValueError, TypeError):
        return default


def format_currency(value: float) -> str:
    """Format a number as currency."""
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif abs(value) >= 1_000:
        return f"${value/1_000:.1f}K"
    else:
        return f"${value:.2f}"


def format_pct(value: float) -> str:
    """Format a fraction as percentage."""
    return f"{value*100:.1f}%"
