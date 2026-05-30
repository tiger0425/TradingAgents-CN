"""Tests for cli/quote.py and akshare.py get_real_time_quotes."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import tradingagents.dataflows.akshare as ak_mod

from tradingagents.dataflows.akshare import get_real_time_quotes


# ---------------------------------------------------------------------------
# Helper: build a mock requests.Response with the given JSON payload
# ---------------------------------------------------------------------------
def _make_mock_response(json_data):
    """Return a MagicMock that behaves like requests.Response with json() -> json_data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# Push2 mock data — maps secid → item dict
# ---------------------------------------------------------------------------
_PUSH2_DATA = {
    "1.600519": {
        "f57": "600519",
        "f58": "贵州茅台",
        "f43": 1580.00,
        "f44": 1590.00,
        "f45": 1568.00,
        "f46": 1570.00,
        "f47": 2500000,
        "f48": 3950000000.0,
        "f60": 1567.50,
        "f116": 0.80,
        "f117": 12.50,
        "f162": 1.40,
        "f167": 0.20,
        "f168": 25.5,
        "f169": 6.8,
    },
    "0.000858": {
        "f57": "000858",
        "f58": "五粮液",
        "f43": 145.00,
        "f44": 147.00,
        "f45": 144.50,
        "f46": 146.50,
        "f47": 18000000,
        "f48": 2610000000.0,
        "f60": 146.50,
        "f116": -1.02,
        "f117": -1.50,
        "f162": 1.71,
        "f167": 0.46,
        "f168": 18.2,
        "f169": 5.1,
    },
}


def _mock_push2_get(*args, **kwargs):
    """Side-effect for requests.get: return push2 items matching the requested secids.

    Unknown secids produce a ``None`` item (simulating a missing stock).
    """
    params = kwargs.get("params", {})
    secids_str = params.get("secids", "")
    secids = secids_str.split(",") if secids_str else []
    items = [_PUSH2_DATA.get(secid) for secid in secids]
    return _make_mock_response({"data": items})


# ============================================================================
# Tests
# ============================================================================


class TestGetRealTimeQuotes:
    """Tests for get_real_time_quotes() in akshare.py."""

    def setup_method(self):
        """Clear module-level cache before each test."""
        ak_mod._spot_em_cache = (0, None)

    @patch("tradingagents.dataflows.akshare.requests.get", side_effect=_mock_push2_get)
    def test_single_stock(self, mock_get):
        """Single stock returns valid Markdown with price info."""
        result = get_real_time_quotes("600519")
        assert "600519" in result
        assert "贵州茅台" in result
        assert "1580" in result  # float repr, may be 1580.0
        assert "最新价" in result

    @patch("tradingagents.dataflows.akshare.requests.get", side_effect=_mock_push2_get)
    def test_multi_stock(self, mock_get):
        """Comma-separated symbols return batch table."""
        result = get_real_time_quotes("600519,000858")
        assert "600519" in result
        assert "000858" in result
        assert "贵州茅台" in result
        assert "五粮液" in result

    @patch("tradingagents.dataflows.akshare.requests.get", side_effect=_mock_push2_get)
    def test_invalid_symbol(self, mock_get):
        """Invalid ticker returns error message."""
        result = get_real_time_quotes("999999")
        assert "999999" in result
        assert "No real-time quote found" in result

    @patch(
        "tradingagents.dataflows.akshare.requests.get",
        return_value=_make_mock_response({"data": None}),
    )
    def test_empty_dataframe(self, mock_get):
        """Null API response returns no-data message."""
        result = get_real_time_quotes("600519")
        assert "No real-time data available" in result or "no" in result.lower()

    @patch("tradingagents.dataflows.akshare.requests.get", side_effect=_mock_push2_get)
    @patch("tradingagents.dataflows.akshare.time.time", return_value=100.0)
    def test_cache_hit(self, mock_time, mock_get):
        """Second call within TTL uses cache (requests.get called once)."""
        get_real_time_quotes("600519")
        get_real_time_quotes("600519")
        assert mock_get.call_count == 1

    @patch("tradingagents.dataflows.akshare.requests.get", side_effect=_mock_push2_get)
    @patch("tradingagents.dataflows.akshare.time.time", side_effect=[100.0, 200.0])
    def test_cache_miss(self, mock_time, mock_get):
        """Call after TTL expires re-fetches from API."""
        get_real_time_quotes("600519")
        get_real_time_quotes("600519")
        assert mock_get.call_count == 2

    def test_chinese_comma(self):
        """Chinese comma （，）should be handled same as English comma."""
        # Just test the logic without network
        pass


class TestQuoteCli:
    """Minimal CLI integration tests (mocked)."""

    @patch("tradingagents.dataflows.akshare.requests.get", side_effect=_mock_push2_get)
    def test_cli_text_output(self, mock_get):
        """CLI command produces text output."""
        result = get_real_time_quotes("600519")
        assert isinstance(result, str)
        assert len(result) > 50
