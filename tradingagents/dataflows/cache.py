"""Unified data caching layer for TradingAgents.

File-system based caching with zero external dependencies beyond the
standard library and pandas.  Provides namespace-scoped storage for
benchmark data, fundamentals, OHLCV, and in-memory spot quotes with TTL.

Usage::

    cache = DataCache("~/.tradingagents/cache/dataflows")
    df = cache.get_or_fetch("benchmark", "000300_2026-05-09", fetcher=lambda: ...)

Namespaces (directories under cache_dir):
- ``ohlcv/{ticker}_{start}_{end}.csv``
- ``benchmark/{ticker}_{date}.csv``
- ``fundamentals/{ticker}_{type}_{date}.csv``
- ``spot/``  (in-memory TTL, 30 second default expiry)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import pandas as pd


class _SpotCache:
    """In-memory TTL cache for spot-quote data.  Thread-safe."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: int = 30) -> Optional[Any]:
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        """Store value with current timestamp."""
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self, key: Optional[str] = None) -> None:
        """Clear a single key or all entries."""
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


class DataCache:
    """Unified data caching layer. File-system based, zero external dependencies.

    Namespaces (directories under cache_dir):

    - ``ohlcv/{ticker}_{start}_{end}.csv``
    - ``benchmark/{ticker}_{date}.csv``
    - ``fundamentals/{ticker}_{type}_{date}.csv``
    - ``spot/`` — in-memory TTL cache (30 second default expiry)
    """

    _DEFAULT_SPOT_TTL = 30
    _CSV_EXT = ".csv"
    _JSON_EXT = ".json"

    def __init__(self, cache_dir: str) -> None:
        """Initialize with *cache_dir* path.  Create if not exists."""
        self._cache_dir = Path(cache_dir).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._spot = _SpotCache()

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Read from cache. Returns ``None`` on cache miss.

        For namespace ``"spot"``, reads from the in-memory TTL cache
        (default expiry 30 s).

        For other namespaces, reads from ``{cache_dir}/{namespace}/{key}``.
        CSV files return as ``pd.DataFrame``; JSON files as ``dict``.
        """
        if namespace == "spot":
            return self._spot.get(key, self._DEFAULT_SPOT_TTL)

        path = self._cache_path(namespace, key)
        if not path.exists():
            return None

        try:
            if path.suffix == self._CSV_EXT:
                df = pd.read_csv(path, encoding="utf-8")
                return df if not df.empty else None
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    def set(self, namespace: str, key: str, data: Any) -> None:
        """Write to cache.  Atomic write (tmp + os.replace).

        For namespace ``"spot"``, stores in-memory with current timestamp.

        For other namespaces:
        - ``pd.DataFrame`` → CSV (``index=False``)
        - ``dict`` / ``list`` → JSON (``ensure_ascii=False, indent=2``)
        """
        if namespace == "spot":
            self._spot.set(key, data)
            return

        path = self._cache_path(namespace, key)
        self._atomic_write(path, data)

    def get_or_fetch(
        self,
        namespace: str,
        key: str,
        fetcher: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """Cache-first: try cache, on miss call *fetcher()* and store result.

        *ttl* is in seconds.  ``None`` means never expire for disk-based
        caches.  For the ``"spot"`` namespace *ttl* defaults to 30 seconds.
        """
        if namespace == "spot":
            effective_ttl = ttl if ttl is not None else self._DEFAULT_SPOT_TTL
            cached = self._spot.get(key, effective_ttl)
            if cached is not None:
                return cached
            data = fetcher()
            self._spot.set(key, data)
            return data

        cached = self.get(namespace, key)
        if cached is not None:
            return cached
        data = fetcher()
        self.set(namespace, key, data)
        return data

    def invalidate(self, namespace: str, key: Optional[str] = None) -> None:
        """Invalidate cache entry.

        If *key* is ``None``, invalidates the entire namespace directory
        (removes all files recursively).  For ``"spot"`` namespace,
        clears the in-memory cache.
        """
        if namespace == "spot":
            self._spot.clear(key)
            return

        if key is None:
            ns_dir = self._cache_dir / namespace
            if ns_dir.exists():
                shutil.rmtree(ns_dir)
        else:
            path = self._cache_path(namespace, key)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    def _cache_path(self, namespace: str, key: str) -> Path:
        """Return ``Path`` for ``{cache_dir}/{namespace}/{key}``.

        The *key* should already include a file extension (``.csv`` or
        ``.json``) so the read/write path can distinguish the format.
        """
        return self._cache_dir / namespace / key

    def _is_expired(self, timestamp: float, ttl: int) -> bool:
        """Check if *ttl* seconds have elapsed since *timestamp*."""
        return (time.time() - timestamp) > ttl

    def _atomic_write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, pd.DataFrame):
            tmpfd, tmpname = tempfile.mkstemp(
                suffix=self._CSV_EXT, prefix=".tmp_", dir=str(path.parent))
            try:
                os.close(tmpfd)
                data.to_csv(tmpname, index=False, encoding="utf-8")
                os.replace(tmpname, str(path))
            except Exception:
                try:
                    os.unlink(tmpname)
                except OSError:
                    pass
                raise

        elif isinstance(data, (dict, list)):
            tmpfd, tmpname = tempfile.mkstemp(
                suffix=self._JSON_EXT,
                prefix=".tmp_",
                dir=str(path.parent),
            )
            try:
                with os.fdopen(tmpfd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmpname, str(path))
            except Exception:
                try:
                    os.unlink(tmpname)
                except OSError:
                    pass
                raise

        else:
            raise TypeError(
                f"DataCache.set() expects pd.DataFrame, dict, or list; "
                f"got {type(data).__name__}"
            )
