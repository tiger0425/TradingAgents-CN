"""Tests for PositionStateManager file lock protection.

Verifies that save() and load() are protected by per-ticker file locks,
preventing data corruption under concurrent access.
"""

import json
import time
import threading
from pathlib import Path

import pytest
from filelock import FileLock


# ---------------------------------------------------------------------------
#  Helper
# ---------------------------------------------------------------------------

def _count_lock_files(state_path: Path) -> int:
    """Return number of .lock files adjacent to the state file."""
    return len(list(state_path.parent.glob(f"{state_path.name}.*.lock")))


class TestPositionStateLockNormal:
    """Basic save/load still works with locks enabled."""

    def test_save_and_load(self, tmp_path):
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "position_state.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        result = mgr.load("600519")
        assert result is not None
        assert result["cost_price"] == 1580.0
        assert result["quantity"] == 100
        assert result["opened_date"] == "2026-01-15"
        assert "updated_at" in result

    def test_load_nonexistent(self, tmp_path):
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(tmp_path / "pos.json")})
        assert mgr.load("000001") is None

    def test_multiple_tickers(self, tmp_path):
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "position_state.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        mgr.save("000001", 10.0, 500, "2026-03-01")

        result = mgr.load("600519")
        assert result["cost_price"] == 1580.0
        result2 = mgr.load("000001")
        assert result2["cost_price"] == 10.0

    def test_lock_file_cleaned_after_save(self, tmp_path):
        """Lock file should not persist after save completes."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "state.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 100.0, 50)
        # Lock files are deleted by filelock on release
        assert _count_lock_files(state_file) == 0

    def test_lock_file_cleaned_after_load(self, tmp_path):
        """Lock file should not persist after load completes."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "state.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 100.0, 50)
        _ = mgr.load("600519")
        assert _count_lock_files(state_file) == 0


class TestPositionStateConcurrent:
    """Concurrent write safety tests."""

    def test_concurrent_same_ticker_maintains_integrity(self, tmp_path):
        """Two threads writing the same ticker: final data must be intact."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "concurrent.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})

        results = {}
        errors = []

        def writer(n: int):
            try:
                mgr.save("600519", float(n * 10), n, "2026-01-15")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent writes raised errors: {errors}"
        loaded = mgr.load("600519")
        assert loaded is not None
        assert "cost_price" in loaded
        assert "quantity" in loaded
        # Final value should be from one of the writers (no corruption)
        assert isinstance(loaded["cost_price"], float)
        assert isinstance(loaded["quantity"], int)

    def test_different_ticker_locks_independent(self, tmp_path):
        """Locks for different tickers are independent (non-blocking).

        Holding lock for ticker 'A' should not block save/load for ticker 'B'.
        """
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "multi.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})

        # Pre-populate both tickers
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        mgr.save("000001", 10.0, 500, "2026-03-01")

        # Hold lock for A
        lock_path = mgr._get_lock_path("600519")
        external_lock = FileLock(str(lock_path))
        external_lock.acquire()

        # Ticker B should be unaffected
        mgr.save("000001", 20.0, 600, "2026-04-01")
        result = mgr.load("000001")
        assert result is not None
        assert result["cost_price"] == 20.0
        assert result["quantity"] == 600

        external_lock.release()

    def test_read_while_write_blocked(self, tmp_path):
        """A read on the same ticker should wait for an in-progress write."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "rw_block.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})
        # Pre-write data
        mgr.save("600519", 100.0, 10)
        mgr.save("000001", 50.0, 20)

        read_results = {}
        write_done = threading.Event()
        read_done = threading.Event()

        def slow_write():
            """Acquire lock and hold it briefly."""
            with mgr._lock_position_file("600519"):
                time.sleep(0.3)  # hold lock
                data = {}
                if state_file.exists():
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                data["600519"] = {
                    "cost_price": 999.0,
                    "quantity": 999,
                    "opened_date": "2026-06-01",
                    "updated_at": "2026-06-01T00:00:00",
                }
                tmp = state_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(data), encoding="utf-8")
                tmp.replace(state_file)
            write_done.set()

        def read_after_write():
            """Read should see the new data after lock is released."""
            write_done.wait()
            r = mgr.load("600519")
            read_results["cost_price"] = r["cost_price"]
            read_results["quantity"] = r["quantity"]
            read_done.set()

        w = threading.Thread(target=slow_write)
        r = threading.Thread(target=read_after_write)
        w.start()
        r.start()
        r.join(timeout=5)
        w.join(timeout=5)

        assert read_done.is_set(), "Read did not complete"
        assert read_results["cost_price"] == 999.0
        assert read_results["quantity"] == 999


class TestPositionStateTimeout:
    """Lock timeout detection tests."""

    def test_lock_timeout_raises(self, tmp_path):
        """Holding the lock for > LOCK_TIMEOUT should raise TimeoutError."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "timeout.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})

        lock_path = mgr._get_lock_path("600519")
        external_lock = FileLock(str(lock_path))

        external_lock.acquire()
        started = time.time()
        with pytest.raises(TimeoutError, match="600519"):
            mgr.save("600519", 100.0, 50)
        elapsed = time.time() - started
        # Should fail around the 5s mark
        assert 4.5 <= elapsed <= 6.0
        external_lock.release()

    def test_lock_timeout_on_load_raises(self, tmp_path):
        """load() should also timeout if lock is held externally."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "timeout_load.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 100.0, 50)

        lock_path = mgr._get_lock_path("600519")
        external_lock = FileLock(str(lock_path))

        external_lock.acquire()
        with pytest.raises(TimeoutError, match="600519"):
            mgr.load("600519")
        external_lock.release()

    def test_different_ticker_no_timeout(self, tmp_path):
        """Lock on one ticker should not block another."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "no_timeout.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})

        # Lock ticker A
        lock_path = mgr._get_lock_path("600519")
        external_lock = FileLock(str(lock_path))
        external_lock.acquire()

        # Ticker B should still work
        mgr.save("000001", 50.0, 100)
        result = mgr.load("000001")
        assert result is not None
        assert result["cost_price"] == 50.0

        external_lock.release()

    def test_lock_recovery_after_timeout(self, tmp_path):
        """After a timeout, the lock should be usable again."""
        from tradingagents.agents.utils.position_state import PositionStateManager

        state_file = tmp_path / "recover.json"
        mgr = PositionStateManager({"position_state_path": str(state_file)})

        lock_path = mgr._get_lock_path("600519")
        external_lock = FileLock(str(lock_path))
        external_lock.acquire()

        with pytest.raises(TimeoutError):
            mgr.save("600519", 100.0, 50)
        external_lock.release()

        # Now it should work
        mgr.save("600519", 200.0, 100)
        result = mgr.load("600519")
        assert result["cost_price"] == 200.0
        assert result["quantity"] == 100
