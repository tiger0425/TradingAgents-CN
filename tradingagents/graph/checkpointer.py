"""LangGraph checkpoint support for resumable analysis runs.

Per-ticker SQLite databases so concurrent tickers don't contend.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import logging

logger = logging.getLogger(__name__)

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    try:
        from langgraph.checkpoint.memory import MemorySaver as SqliteSaver
        logger.debug("SqliteSaver unavailable, using MemorySaver as fallback")
    except ImportError:
        SqliteSaver = None
        logger.debug("No checkpoint saver available — resume disabled")

from tradingagents.dataflows.utils import safe_ticker_component


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """Return the SQLite checkpoint DB path for a ticker."""
    # Reject ticker values that would escape the checkpoints directory.
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(ticker: str, date: str) -> str:
    """Deterministic thread ID for a ticker+date pair."""
    return hashlib.sha256(f"{ticker.upper()}:{date}".encode()).hexdigest()[:16]


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str) -> Generator:
    if SqliteSaver is None:
        raise RuntimeError(
            "Checkpointing requires langgraph-checkpoint-sqlite. "
            "Install with: pip install langgraph-checkpoint-sqlite"
        )
    db = _db_path(data_dir, ticker)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def has_checkpoint(data_dir: str | Path, ticker: str, date: str) -> bool:
    """Check whether a resumable checkpoint exists for ticker+date."""
    return checkpoint_step(data_dir, ticker, date) is not None


def checkpoint_step(data_dir: str | Path, ticker: str, date: str) -> int | None:
    """Return the step number of the latest checkpoint, or None if none exists."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, date)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = saver.get_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


# ------------------------------------------------------------------
# Generic (non-ticker) checkpoint support
# ------------------------------------------------------------------


def _db_path_for_task(data_dir: str | Path, task_id_str: str) -> Path:
    """Return the SQLite checkpoint DB path for a generic task ID.

    Uses a hash of the task_id_str so the filename is always safe and
    deterministic.
    """
    safe = hashlib.sha256(task_id_str.encode()).hexdigest()[:16]
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"task_{safe}.db"


def thread_id_for_task(task_id_str: str) -> str:
    """Deterministic thread ID for an arbitrary task identifier string."""
    return hashlib.sha256(task_id_str.encode()).hexdigest()[:16]


@contextmanager
def get_checkpointer_for_task(
    data_dir: str | Path, task_id_str: str
) -> Generator:
    """Get a SqliteSaver for a generic task (not tied to a ticker name)."""
    if SqliteSaver is None:
        raise RuntimeError(
            "Checkpointing requires langgraph-checkpoint-sqlite. "
            "Install with: pip install langgraph-checkpoint-sqlite"
        )
    db = _db_path_for_task(data_dir, task_id_str)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def clear_checkpoint_for_task(
    data_dir: str | Path, task_id_str: str, thread_id_str: str
) -> None:
    """Remove checkpoint rows for a specific task thread."""
    db = _db_path_for_task(data_dir, task_id_str)
    if not db.exists():
        return
    conn = sqlite3.connect(str(db))
    try:
        for table in ("writes", "checkpoints"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id_str,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """Remove all checkpoint DBs. Returns number of files deleted."""
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
    return len(dbs)


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str) -> None:
    """Remove checkpoint for a specific ticker+date by deleting the thread's rows."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, date)
    conn = sqlite3.connect(str(db))
    try:
        for table in ("writes", "checkpoints"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
