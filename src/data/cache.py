"""Disk cache for data responses — makes reruns fast, free, and offline.

All API responses cache to disk. The cache key is (method, ticker, params).
This means a backtest that hits the same ticker/date twice pays once.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class DiskCache:
    """Simple JSON-on-disk cache for data responses."""

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".ai_fund" / "cache"
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, *parts) -> str:
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, *parts) -> Any | None:
        path = self._dir / f"{self._key(*parts)}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def put(self, value: Any, *parts) -> None:
        path = self._dir / f"{self._key(*parts)}.json"
        with open(path, "w") as f:
            json.dump(value, f, default=str)

    def get_or_fetch(self, fetch_fn, *parts, **kwargs):
        """Return cached value if exists, else call fetch_fn and cache."""
        cached = self.get(*parts)
        if cached is not None:
            return cached
        result = fetch_fn(**kwargs)
        self.put(result, *parts)
        return result
