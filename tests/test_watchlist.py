"""Tests for WatchlistManager."""

import json
import pytest
from tradingagents.watchlist import WatchlistManager


class TestWatchlistManager:
    """Tests for WatchlistManager data layer."""

    def test_init_default_path(self):
        """Default path is ~/.tradingagents/watchlist.json."""
        mgr = WatchlistManager()
        assert mgr._path.name == "watchlist.json"
        assert ".tradingagents" in str(mgr._path)

    def test_init_config_path(self, tmp_path):
        """Config 'watchlist_path' key overrides default path."""
        custom = tmp_path / "custom" / "my_watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(custom)})
        assert mgr._path == custom

    # ------------------------------------------------------------------
    # add
    # ------------------------------------------------------------------

    def test_add_new_stock(self, tmp_path):
        """Adding a new stock returns the entry dict."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        entry = mgr.add("600519", name="贵州茅台", priority=1)
        assert entry["ticker"] == "600519"
        assert entry["name"] == "贵州茅台"
        assert entry["priority"] == 1
        assert entry["alerts"] == {}

    def test_add_updates_existing(self, tmp_path):
        """Adding an existing ticker updates name and priority, merges alerts."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", name="茅台", priority=3, alerts={"price_above": 1600})
        mgr.add("600519", name="贵州茅台", priority=1, alerts={"price_below": 1500})

        entry = mgr.get("600519")
        assert entry["name"] == "贵州茅台"
        assert entry["priority"] == 1
        assert entry["alerts"]["price_above"] == 1600
        assert entry["alerts"]["price_below"] == 1500

    def test_add_with_alerts(self, tmp_path):
        """Adding a stock with alerts stores them correctly."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        entry = mgr.add("000001", alerts={"rsi_oversold": True, "volume_surge": 2.5})
        assert entry["alerts"]["rsi_oversold"] is True
        assert entry["alerts"]["volume_surge"] == 2.5

    def test_add_default_priority(self, tmp_path):
        """Default priority is 5 when not specified."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        entry = mgr.add("600519")
        assert entry["priority"] == 5

    def test_add_saves_to_disk(self, tmp_path):
        """add() persists the data to disk."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", name="贵州茅台")
        assert path.exists()

        raw = json.loads(path.read_text(encoding="utf-8"))
        assert len(raw["stocks"]) == 1
        assert raw["stocks"][0]["ticker"] == "600519"

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------

    def test_remove_existing(self, tmp_path):
        """Removing an existing ticker returns True and persists."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        assert mgr.remove("600519") is True
        assert mgr.get("600519") is None

    def test_remove_nonexistent(self, tmp_path):
        """Removing a non-existent ticker returns False."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.remove("000001") is False

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def test_list_sorted_by_priority(self, tmp_path):
        """list() returns stocks sorted by priority ascending."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("000001", priority=3)
        mgr.add("600519", priority=1)
        mgr.add("000002", priority=2)

        stocks = mgr.list()
        assert stocks[0]["ticker"] == "600519"
        assert stocks[1]["ticker"] == "000002"
        assert stocks[2]["ticker"] == "000001"

    def test_list_empty(self, tmp_path):
        """list() returns empty list when no stocks exist."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.list() == []

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def test_get_existing(self, tmp_path):
        """get() returns the stock entry for an existing ticker."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", name="贵州茅台", priority=2)
        entry = mgr.get("600519")
        assert entry is not None
        assert entry["ticker"] == "600519"
        assert entry["name"] == "贵州茅台"

    def test_get_nonexistent(self, tmp_path):
        """get() returns None for a non-existent ticker."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.get("000001") is None

    # ------------------------------------------------------------------
    # set_alert
    # ------------------------------------------------------------------

    def test_set_alert_existing(self, tmp_path):
        """Setting an alert on an existing ticker returns True."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        assert mgr.set_alert("600519", "price_above", 1600.0) is True
        entry = mgr.get("600519")
        assert entry["alerts"]["price_above"] == 1600.0

    def test_set_alert_nonexistent(self, tmp_path):
        """Setting an alert on a non-existent ticker returns False."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.set_alert("000001", "price_above", 100.0) is False

    def test_set_alert_overwrites(self, tmp_path):
        """Setting the same alert type overwrites the previous value."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", alerts={"price_above": 1600})
        mgr.set_alert("600519", "price_above", 1700)
        assert mgr.get("600519")["alerts"]["price_above"] == 1700

    # ------------------------------------------------------------------
    # remove_alert
    # ------------------------------------------------------------------

    def test_remove_alert_existing(self, tmp_path):
        """Removing an existing alert returns True."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", alerts={"price_above": 1600, "price_below": 1500})
        assert mgr.remove_alert("600519", "price_above") is True
        assert "price_above" not in mgr.get("600519")["alerts"]
        assert "price_below" in mgr.get("600519")["alerts"]

    def test_remove_alert_nonexistent_ticker(self, tmp_path):
        """Removing alert from non-existent ticker returns False."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.remove_alert("000001", "price_above") is False

    def test_remove_alert_nonexistent_type(self, tmp_path):
        """Removing a non-existent alert type returns False."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", alerts={"price_above": 1600})
        assert mgr.remove_alert("600519", "rsi_oversold") is False

    # ------------------------------------------------------------------
    # get_all_tickers
    # ------------------------------------------------------------------

    def test_get_all_tickers(self, tmp_path):
        """get_all_tickers() returns sorted ticker symbols."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        mgr.add("000001")
        assert mgr.get_all_tickers() == ["000001", "600519"]

    def test_get_all_tickers_empty(self, tmp_path):
        """get_all_tickers() returns empty list when no stocks."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.get_all_tickers() == []

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_corrupt_json_file(self, tmp_path):
        """Corrupt JSON is treated as an empty watchlist."""
        path = tmp_path / "watchlist.json"
        path.write_text("not valid json {{{", encoding="utf-8")
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.list() == []
        assert mgr.get("600519") is None

    def test_missing_file(self, tmp_path):
        """Missing file is treated as an empty watchlist."""
        path = tmp_path / "nonexistent.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        assert mgr.list() == []
        assert mgr.get_all_tickers() == []

    def test_empty_file(self, tmp_path):
        """Adding to a non-existent path creates the parent dirs and file."""
        path = tmp_path / "deep" / "nested" / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        assert path.exists()

    def test_add_name_empty_string(self, tmp_path):
        """Adding with empty string name works."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        entry = mgr.add("600519")
        assert entry["name"] == ""

    def test_add_negative_priority(self, tmp_path):
        """Negative priority values are accepted as-is."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        entry = mgr.add("600519", priority=-1)
        assert entry["priority"] == -1

    def test_duplicate_add_does_not_duplicate(self, tmp_path):
        """Adding the same ticker twice results in one entry."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        mgr.add("600519")
        assert len(mgr.list()) == 1

    def test_get_returns_copy(self, tmp_path):
        """get() returns a copy so mutations don't affect internal state."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519", alerts={"price_above": 1600})
        entry = mgr.get("600519")
        entry["alerts"]["price_above"] = 9999
        # Original should be unchanged
        reloaded = mgr.get("600519")
        assert reloaded["alerts"]["price_above"] == 1600

    def test_remove_persists(self, tmp_path):
        """Removing a ticker persists to disk."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        mgr.add("000001")
        mgr.remove("600519")

        # New manager reading same file
        mgr2 = WatchlistManager({"watchlist_path": str(path)})
        assert mgr2.get("600519") is None
        assert mgr2.get("000001") is not None

    def test_set_alert_bool_value(self, tmp_path):
        """Alert values can be boolean (e.g. rsi_oversold)."""
        path = tmp_path / "watchlist.json"
        mgr = WatchlistManager({"watchlist_path": str(path)})
        mgr.add("600519")
        mgr.set_alert("600519", "rsi_oversold", True)
        assert mgr.get("600519")["alerts"]["rsi_oversold"] is True
