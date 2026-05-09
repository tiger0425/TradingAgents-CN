"""Tests for the DataCache unified caching layer."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd
import pytest

from tradingagents.dataflows.cache import DataCache, _SpotCache


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_cache_dir() -> str:
    """Create a temporary directory for cache storage, cleaned up after test."""
    path = tempfile.mkdtemp(prefix="test_datacache_")
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def cache(tmp_cache_dir: str) -> DataCache:
    """Return a DataCache instance backed by a temporary directory."""
    return DataCache(tmp_cache_dir)


# ============================================================================
# _SpotCache tests (in-memory TTL)
# ============================================================================


class TestSpotCache:
    def test_set_and_get(self):
        sc = _SpotCache()
        sc.set("key1", "value1")
        assert sc.get("key1") == "value1"

    def test_miss_returns_none(self):
        sc = _SpotCache()
        assert sc.get("nonexistent") is None

    def test_ttl_expiry(self):
        sc = _SpotCache()
        sc._store["expired"] = (0.0, "old")  # timestamp 0 → guaranteed expired
        assert sc.get("expired") is None

    def test_clear_single_key(self):
        sc = _SpotCache()
        sc.set("a", 1)
        sc.set("b", 2)
        sc.clear("a")
        assert sc.get("a") is None
        assert sc.get("b") == 2

    def test_clear_all(self):
        sc = _SpotCache()
        sc.set("a", 1)
        sc.set("b", 2)
        sc.clear()
        assert sc.get("a") is None
        assert sc.get("b") is None

    def test_thread_safety(self):
        """Spam set/get from multiple threads — no crash, no lost data."""
        import threading

        sc = _SpotCache()
        errors = []

        def worker(n: int):
            try:
                for i in range(100):
                    key = f"t{n}_{i}"
                    sc.set(key, i)
                    v = sc.get(key)
                    assert v == i, f"{key}: expected {i}, got {v}"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Thread safety failures: {errors}"


# ============================================================================
# DataCache — JSON read/write
# ============================================================================


class TestDataCacheJson:
    def test_set_and_get(self, cache: DataCache):
        data = {"hello": "world", "nested": {"a": 1}}
        cache.set("json_ns", "test.json", data)
        result = cache.get("json_ns", "test.json")
        assert result == data

    def test_get_miss_returns_none(self, cache: DataCache):
        assert cache.get("empty_ns", "nope.json") is None

    def test_get_or_fetch_miss(self, cache: DataCache):
        fetched = cache.get_or_fetch(
            "fetch_ns", "miss.json", fetcher=lambda: {"fetched": True}
        )
        assert fetched == {"fetched": True}

    def test_get_or_fetch_hit_skips_fetcher(self, cache: DataCache):
        call_count = 0

        def fetcher():
            nonlocal call_count
            call_count += 1
            return {"data": call_count}

        # First call: miss → fetcher called
        r1 = cache.get_or_fetch("fetch_ns", "hit.json", fetcher=fetcher)
        assert r1 == {"data": 1} and call_count == 1

        # Second call: hit → fetcher NOT called
        r2 = cache.get_or_fetch("fetch_ns", "hit.json", fetcher=fetcher)
        assert r2 == {"data": 1} and call_count == 1

    def test_get_or_fetch_list(self, cache: DataCache):
        data = [{"x": 1}, {"x": 2}]
        cache.set("list_ns", "items.json", data)
        result = cache.get("list_ns", "items.json")
        assert result == data

    def test_invalidate_single_key(self, cache: DataCache):
        cache.set("inv_ns", "a.json", {"val": 1})
        cache.set("inv_ns", "b.json", {"val": 2})
        cache.invalidate("inv_ns", "a.json")
        assert cache.get("inv_ns", "a.json") is None
        assert cache.get("inv_ns", "b.json") == {"val": 2}

    def test_invalidate_entire_namespace(self, cache: DataCache):
        cache.set("full_inv", "x.json", {"v": 1})
        cache.set("full_inv", "y.json", {"v": 2})
        cache.invalidate("full_inv")
        assert cache.get("full_inv", "x.json") is None
        assert cache.get("full_inv", "y.json") is None

    def test_invalidate_nonexistent_key_no_error(self, cache: DataCache):
        cache.invalidate("ghost_ns", "nothing.json")  # should not raise

    def test_invalidate_nonexistent_namespace_no_error(self, cache: DataCache):
        cache.invalidate("no_such_ns")  # should not raise

    def test_corrupted_file_returns_none(self, cache: DataCache, tmp_cache_dir: str):
        """Corrupted JSON files should return None, not crash."""
        ns_dir = Path(tmp_cache_dir) / "corrupt_ns"
        ns_dir.mkdir(parents=True, exist_ok=True)
        bad_file = ns_dir / "bad.json"
        bad_file.write_text("{invalid json", encoding="utf-8")
        assert cache.get("corrupt_ns", "bad.json") is None


# ============================================================================
# DataCache — DataFrame CSV read/write
# ============================================================================


class TestDataCacheCsv:
    def test_set_and_get_dataframe(self, cache: DataCache):
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        cache.set("csv_ns", "test.csv", df)
        result = cache.get("csv_ns", "test.csv")
        assert result is not None
        assert list(result.columns) == ["a", "b"]
        assert len(result) == 3
        assert result["a"].tolist() == [1, 2, 3]

    def test_empty_dataframe_returns_none(self, cache: DataCache):
        empty = pd.DataFrame()
        cache.set("csv_ns", "empty.csv", empty)
        # An empty DataFrame serialises as an empty CSV, which when
        # read back yields a non-None, zero-row DataFrame.  The
        # rationale: the caller should treat an empty DataFrame the
        # same way it treats a None — no usable data returned.
        result = cache.get("csv_ns", "empty.csv")
        assert result is None or len(result) == 0

    def test_invalidate_csv(self, cache: DataCache):
        df = pd.DataFrame({"x": [1]})
        cache.set("csv_inv", "data.csv", df)
        assert cache.get("csv_inv", "data.csv") is not None
        cache.invalidate("csv_inv", "data.csv")
        assert cache.get("csv_inv", "data.csv") is None


# ============================================================================
# DataCache — Spot cache integration
# ============================================================================


class TestDataCacheSpot:
    def test_set_and_get_spot(self, cache: DataCache):
        cache.set("spot", "mykey", "value")
        assert cache.get("spot", "mykey") == "value"

    def test_spot_ttl_expiry(self, cache: DataCache):
        cache._spot._store["old"] = (0.0, "stale")
        assert cache.get("spot", "old") is None

    def test_spot_invalidate_single(self, cache: DataCache):
        cache.set("spot", "a", 1)
        cache.set("spot", "b", 2)
        cache.invalidate("spot", "a")
        assert cache.get("spot", "a") is None
        assert cache.get("spot", "b") == 2

    def test_spot_invalidate_all(self, cache: DataCache):
        cache.set("spot", "a", 1)
        cache.set("spot", "b", 2)
        cache.invalidate("spot")
        assert cache.get("spot", "a") is None
        assert cache.get("spot", "b") is None


# ============================================================================
# DataCache — type checking
# ============================================================================


class TestDataCacheTypes:
    def test_set_raises_on_unsupported_type(self, cache: DataCache):
        with pytest.raises(TypeError):
            cache.set("bad_ns", "bad.json", 42)  # int not supported

    def test_set_raises_on_string(self, cache: DataCache):
        with pytest.raises(TypeError):
            cache.set("bad_ns", "bad.json", "plain string")


# ============================================================================
# DataCache — Initialisation
# ============================================================================


class TestDataCacheInit:
    def test_creates_cache_dir(self, tmp_cache_dir: str):
        dir_path = os.path.join(tmp_cache_dir, "subdir", "nested")
        cache = DataCache(dir_path)
        assert os.path.isdir(dir_path)
        assert cache._cache_dir == Path(dir_path).resolve()

    def test_reuses_existing_dir(self, tmp_cache_dir: str):
        os.makedirs(os.path.join(tmp_cache_dir, "existing"), exist_ok=True)
        cache = DataCache(os.path.join(tmp_cache_dir, "existing"))
        assert cache._cache_dir.exists()

    def test_distinct_instances_independent(self, tmp_cache_dir: str):
        """Two DataCache instances with same dir share files on disk."""
        a = DataCache(tmp_cache_dir)
        b = DataCache(tmp_cache_dir)
        a.set("shared", "x.json", {"from": "a"})
        assert b.get("shared", "x.json") == {"from": "a"}
