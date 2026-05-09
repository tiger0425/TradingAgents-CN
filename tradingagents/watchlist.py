"""Persistent watchlist management for TradingAgents.

Stores a list of watched stocks with priorities and alert conditions
as a JSON file. Uses atomic writes to prevent corruption.

File: ~/.tradingagents/watchlist.json

Structure:
{
    "stocks": [
        {
            "ticker": "600519",
            "name": "贵州茅台",
            "priority": 1,
            "alerts": {
                "price_above": 1600.0,
                "price_below": 1500.0,
                "rsi_oversold": true
            }
        }
    ]
}
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class WatchlistManager:
    """Manages a persistent watchlist of stocks with alerts.

    The watchlist file is a JSON object containing a "stocks" array.
    Each stock entry has ticker, name, priority, and optional alerts.
    """

    def __init__(self, config: dict = None):
        """Initialize with config dict.

        Reads path from config.get("watchlist_path", default).
        Default path: ~/.tradingagents/watchlist.json
        Creates parent directory if needed.
        """
        cfg = config or {}
        path = cfg.get("watchlist_path")
        if path:
            self._path = Path(path).expanduser()
        else:
            self._path = Path(os.path.expanduser("~/.tradingagents/watchlist.json"))
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        """Load the full watchlist from disk.

        Returns {"stocks": [...]}. Never raises on missing/corrupt file.
        """
        if not self._path.exists():
            return {"stocks": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "stocks" not in data:
                return {"stocks": []}
            return data
        except (json.JSONDecodeError, ValueError):
            return {"stocks": []}

    def _save(self, data: Dict[str, Any]) -> None:
        """Atomically write the watchlist to disk."""
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)

    def _find_index(self, ticker: str, stocks: List[dict]) -> int:
        """Return index of ticker in stocks list, or -1 if not found."""
        for i, entry in enumerate(stocks):
            if entry.get("ticker") == ticker:
                return i
        return -1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, ticker: str, name: str = "", priority: int = 5,
            alerts: dict = None) -> dict:
        """Add a stock to the watchlist.

        If the ticker already exists, updates name, priority and merges alerts.
        Returns the stock entry dict.
        """
        data = self._load()
        stocks = data["stocks"]

        idx = self._find_index(ticker, stocks)
        if idx >= 0:
            # Update existing entry
            entry = stocks[idx]
            if name:
                entry["name"] = name
            entry["priority"] = int(priority)
            if alerts:
                entry.setdefault("alerts", {}).update(alerts)
        else:
            # New entry
            entry = {
                "ticker": ticker,
                "name": name,
                "priority": int(priority),
                "alerts": alerts or {},
            }
            stocks.append(entry)

        self._save(data)
        return dict(entry)

    def remove(self, ticker: str) -> bool:
        """Remove a stock from the watchlist.

        Returns True if the ticker existed and was removed.
        """
        data = self._load()
        stocks = data["stocks"]
        idx = self._find_index(ticker, stocks)
        if idx < 0:
            return False
        stocks.pop(idx)
        self._save(data)
        return True

    def list(self) -> List[dict]:
        """Return all stocks sorted by priority (ascending).

        Lower priority number = higher importance.
        """
        data = self._load()
        stocks = data["stocks"]
        return sorted(stocks, key=lambda e: e.get("priority", 999))

    def get(self, ticker: str) -> Optional[dict]:
        """Return a single stock entry by ticker, or None if not found."""
        data = self._load()
        for entry in data["stocks"]:
            if entry.get("ticker") == ticker:
                return dict(entry)
        return None

    def set_alert(self, ticker: str, alert_type: str, value) -> bool:
        """Set an alert condition for a stock.

        Returns True if the ticker exists and the alert was set.
        """
        data = self._load()
        idx = self._find_index(ticker, data["stocks"])
        if idx < 0:
            return False
        entry = data["stocks"][idx]
        entry.setdefault("alerts", {})[alert_type] = value
        self._save(data)
        return True

    def remove_alert(self, ticker: str, alert_type: str) -> bool:
        """Remove an alert condition from a stock.

        Returns True if the ticker existed and the alert was removed.
        """
        data = self._load()
        idx = self._find_index(ticker, data["stocks"])
        if idx < 0:
            return False
        entry = data["stocks"][idx]
        alerts = entry.get("alerts", {})
        if alert_type in alerts:
            del alerts[alert_type]
            self._save(data)
            return True
        return False

    def get_all_tickers(self) -> List[str]:
        """Return sorted list of all ticker symbols in the watchlist."""
        data = self._load()
        return sorted(entry["ticker"] for entry in data["stocks"])
