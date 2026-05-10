"""Tests for cli/monitor.py alert monitoring logic."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest
import json

from cli.monitor import _parse_price_from_quotes, _check_price_alert


class TestParsePriceFromQuotes:
    """Tests for _parse_price_from_quotes()."""

    def test_single_stock_table(self):
        """Parse price from single stock markdown table."""
        md = """# 实时行情: 600519 (贵州茅台)

| 指标 | 值 |
|------|-----|
| **最新价** | 1580.0 |
| **涨跌额** | 12.5 |
"""
        price = _parse_price_from_quotes(md)
        assert price == 1580.0

    def test_single_stock_different_format(self):
        """Handle different table formatting."""
        md = "| 最新价 | 100.5 |"
        price = _parse_price_from_quotes(md)
        assert price == 100.5

    def test_no_price(self):
        """No price in output returns None."""
        md = "# No data available"
        price = _parse_price_from_quotes(md)
        assert price is None


class TestCheckPriceAlert:
    """Tests for _check_price_alert()."""

    def test_price_above_triggered(self):
        alerts = {"price_above": 1500.0}
        result = _check_price_alert("600519", 1580.0, alerts)
        assert len(result) == 1
        assert result[0]["alert"] == "price_above"
        assert result[0]["current"] == 1580.0

    def test_price_above_not_triggered(self):
        alerts = {"price_above": 1600.0}
        result = _check_price_alert("600519", 1580.0, alerts)
        assert len(result) == 0

    def test_price_below_triggered(self):
        alerts = {"price_below": 1600.0}
        result = _check_price_alert("600519", 1580.0, alerts)
        assert len(result) == 1
        assert result[0]["alert"] == "price_below"

    def test_price_below_not_triggered(self):
        alerts = {"price_below": 1500.0}
        result = _check_price_alert("600519", 1580.0, alerts)
        assert len(result) == 0

    def test_both_alerts(self):
        alerts = {"price_above": 1550.0, "price_below": 1600.0}
        result = _check_price_alert("600519", 1580.0, alerts)
        assert len(result) == 2  # 1580 > 1550 triggers above, 1580 < 1600 triggers below

    def test_no_matching_alerts(self):
        alerts = {"rsi_oversold": 30}
        result = _check_price_alert("600519", 1580.0, alerts)
        assert len(result) == 0
