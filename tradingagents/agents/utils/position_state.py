"""Persistent position state tracking for TradingAgents.

Stores current position (cost_price, quantity, opened_date) per ticker
as a JSON file. Uses atomic writes to prevent corruption.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


class PositionStateManager:
    """Manages persistent position state per ticker.

    The state file is a flat JSON object keyed by ticker symbol:
    {
        "600519": {
            "cost_price": 1580.0,
            "quantity": 100,
            "opened_date": "2026-01-15",
            "updated_at": "2026-05-06T10:00:00"
        }
    }
    """

    def __init__(self, config: dict = None):
        """Initialize with config dict.

        Reads state_path from config.get("position_state_path", default).
        Default path: ~/.tradingagents/memory/position_state.json
        Creates parent directory if needed.
        """
        cfg = config or {}
        self._state_path = None
        path = cfg.get("position_state_path")
        if path:
            self._state_path = Path(path).expanduser()
        else:
            from tradingagents.default_config import DEFAULT_CONFIG

            base = cfg.get("data_cache_dir") or DEFAULT_CONFIG.get(
                "data_cache_dir", os.path.expanduser("~/.tradingagents/cache")
            )
            self._state_path = Path(base).parent / "memory" / "position_state.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, ticker: str) -> Optional[dict]:
        """Load position state for ticker.

        Returns dict with keys: cost_price, quantity, opened_date, updated_at
        Returns None if ticker not found or file doesn't exist.
        Never raises FileNotFoundError.
        """
        if not self._state_path or not self._state_path.exists():
            return None
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            entry = data.get(ticker)
            if entry is None:
                return None
            return {
                "cost_price": float(entry.get("cost_price", 0.0)),
                "quantity": int(entry.get("quantity", 0)),
                "opened_date": str(entry.get("opened_date", "")),
                "updated_at": str(entry.get("updated_at", "")),
            }
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def save(self, ticker: str, cost_price: float, quantity: int,
             opened_date: str = "") -> None:
        """Save position state for ticker using atomic write.

        Uses tmp file + os.replace() to prevent corruption.
        Sets updated_at to current ISO timestamp.
        """
        if not self._state_path:
            return

        data = {}
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                data = {}

        data[ticker] = {
            "cost_price": round(float(cost_price), 2),
            "quantity": int(quantity),
            "opened_date": str(opened_date) if opened_date else "",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

        # Atomic write
        tmp_path = self._state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._state_path)

    def reset(self, ticker: str) -> None:
        """Remove position state for ticker.

        If removing leaves the file empty, writes {}.
        No-op if file doesn't exist.
        """
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            data.pop(ticker, None)
            tmp_path = self._state_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._state_path)
        except (json.JSONDecodeError, ValueError):
            pass

    def get_all(self) -> Dict[str, dict]:
        """Return all position states. Returns empty dict if no file."""
        if not self._state_path or not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}
