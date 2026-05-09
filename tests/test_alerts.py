"""Tests for cli/alerts.py core alert logic — no network calls."""

import json
import pytest
import pandas as pd
from cli.alerts import (
    _check_price,
    _check_rsi,
    _check_volume_surge,
    _check_ma_cross,
    _check_stock_alerts,
    VALID_ALERT_TYPES,
    PRICE_ALERTS,
    RSI_ALERTS,
)


# ---------------------------------------------------------------------------
# _check_price
# ---------------------------------------------------------------------------

class TestCheckPrice:
    def test_price_above_triggered(self):
        ok, result = _check_price(current_price=1600.0, alert_type="price_above", threshold=1500.0)
        assert ok is True
        assert result["alert"] == "price_above"
        assert result["current"] == 1600.0
        assert result["threshold"] == 1500.0

    def test_price_above_not_triggered(self):
        ok, result = _check_price(current_price=1400.0, alert_type="price_above", threshold=1500.0)
        assert ok is False
        assert result is None

    def test_price_below_triggered(self):
        ok, result = _check_price(current_price=1400.0, alert_type="price_below", threshold=1500.0)
        assert ok is True
        assert result["alert"] == "price_below"
        assert result["current"] == 1400.0
        assert result["threshold"] == 1500.0

    def test_price_below_not_triggered(self):
        ok, result = _check_price(current_price=1600.0, alert_type="price_below", threshold=1500.0)
        assert ok is False
        assert result is None

    def test_price_equal_not_triggered(self):
        ok_a, _ = _check_price(1500.0, "price_above", 1500.0)
        ok_b, _ = _check_price(1500.0, "price_below", 1500.0)
        assert ok_a is False
        assert ok_b is False


# ---------------------------------------------------------------------------
# _check_rsi
# ---------------------------------------------------------------------------

class TestCheckRSI:
    def test_rsi_oversold_triggered_default(self):
        ok, result = _check_rsi(rsi_value=25.0, alert_type="rsi_oversold", threshold=True)
        assert ok is True
        assert result["alert"] == "rsi_oversold"
        assert result["current"] == 25.0
        assert result["threshold"] == 30.0

    def test_rsi_oversold_not_triggered(self):
        ok, result = _check_rsi(rsi_value=35.0, alert_type="rsi_oversold", threshold=True)
        assert ok is False
        assert result is None

    def test_rsi_oversold_custom_threshold(self):
        ok, result = _check_rsi(rsi_value=22.0, alert_type="rsi_oversold", threshold=25.0)
        assert ok is True
        assert result["threshold"] == 25.0

    def test_rsi_overbought_triggered_default(self):
        ok, result = _check_rsi(rsi_value=75.0, alert_type="rsi_overbought", threshold=True)
        assert ok is True
        assert result["alert"] == "rsi_overbought"
        assert result["threshold"] == 70.0

    def test_rsi_overbought_not_triggered(self):
        ok, result = _check_rsi(rsi_value=65.0, alert_type="rsi_overbought", threshold=True)
        assert ok is False
        assert result is None

    def test_rsi_overbought_custom_threshold(self):
        ok, result = _check_rsi(rsi_value=82.0, alert_type="rsi_overbought", threshold=80.0)
        assert ok is True
        assert result["threshold"] == 80.0

    def test_rsi_boundary_exact_30(self):
        ok, result = _check_rsi(rsi_value=30.0, alert_type="rsi_oversold", threshold=True)
        assert ok is False  # strictly less than

    def test_rsi_boundary_exact_70(self):
        ok, result = _check_rsi(rsi_value=70.0, alert_type="rsi_overbought", threshold=True)
        assert ok is False  # strictly greater than


# ---------------------------------------------------------------------------
# _check_volume_surge
# ---------------------------------------------------------------------------

class TestCheckVolumeSurge:
    def test_surge_triggered(self):
        ok, result = _check_volume_surge(current_volume=300000, avg_volume=100000, multiplier=2.0)
        assert ok is True
        assert result["alert"] == "volume_surge"
        assert result["current"] == 300000
        assert result["avg_volume"] == 100000
        assert result["multiplier"] == 2.0
        assert result["surge_ratio"] == 3.0

    def test_surge_not_triggered(self):
        ok, result = _check_volume_surge(current_volume=150000, avg_volume=100000, multiplier=2.0)
        assert ok is False
        assert result is None

    def test_surge_default_multiplier(self):
        ok, result = _check_volume_surge(current_volume=250000, avg_volume=100000, multiplier=True)
        assert ok is True
        assert result["multiplier"] == 2.0

    def test_surge_zero_avg_volume(self):
        ok, result = _check_volume_surge(current_volume=1000, avg_volume=0, multiplier=2.0)
        assert ok is False
        assert result is None

    def test_surge_exact_multiplier_boundary(self):
        ok, result = _check_volume_surge(current_volume=200000, avg_volume=100000, multiplier=2.0)
        assert ok is False  # strictly greater than (not >=)


# ---------------------------------------------------------------------------
# _check_ma_cross
# ---------------------------------------------------------------------------

class TestCheckMACross:
    def _make_ohlcv_df(self, rows: list) -> pd.DataFrame:
        """Build a DataFrame with Date, Open, High, Low, Close, Volume columns."""
        df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"])
        return df

    def test_golden_cross(self):
        df = self._make_ohlcv_df([
            ("2026-05-06", 10, 11, 9, 9.5, 1000),
            ("2026-05-07", 10, 12, 9.5, 11.0, 1200),
        ])
        # Manually add MA(5) column to simulate golden cross:
        # prev: close=9.5 <= ma=10.0, curr: close=11.0 > ma=10.5
        df["ma_5"] = [10.0, 10.5]

        ok, result = _check_ma_cross(df, {"type": "golden", "period": 5})
        assert ok is True
        assert result["cross_type"] == "golden_cross"
        assert result["period"] == 5

    def test_death_cross(self):
        df = self._make_ohlcv_df([
            ("2026-05-06", 12, 13, 11, 12.0, 1000),
            ("2026-05-07", 11, 12, 10, 10.0, 1200),
        ])
        df["ma_5"] = [11.0, 11.5]

        ok, result = _check_ma_cross(df, {"type": "death", "period": 5})
        assert ok is True
        assert result["cross_type"] == "death_cross"
        assert result["period"] == 5

    def test_no_cross(self):
        df = self._make_ohlcv_df([
            ("2026-05-06", 10, 12, 9, 11.0, 1000),
            ("2026-05-07", 10, 12, 9, 12.0, 1200),
        ])
        df["ma_5"] = [10.0, 11.0]  # close always above MA
        ok, result = _check_ma_cross(df, {"type": "golden", "period": 5})
        assert ok is False
        assert result is None

    def test_ma_cross_with_string_type(self):
        df = self._make_ohlcv_df([
            ("2026-05-06", 10, 11, 9, 9.5, 1000),
            ("2026-05-07", 10, 12, 9.5, 11.0, 1200),
        ])
        df["ma_20"] = [10.0, 10.5]

        ok, result = _check_ma_cross(df, "golden")
        assert ok is True
        assert result["cross_type"] == "golden_cross"
        assert result["period"] == 20  # default period when type is just a string

    def test_ma_cross_with_boolean_default(self):
        df = self._make_ohlcv_df([
            ("2026-05-06", 10, 11, 9, 9.5, 1000),
            ("2026-05-07", 10, 12, 9.5, 11.0, 1200),
        ])
        df["ma_20"] = [10.0, 10.5]

        ok, result = _check_ma_cross(df, True)
        assert ok is True
        assert result["cross_type"] == "golden_cross"
        assert result["period"] == 20

    def test_ma_cross_too_few_rows(self):
        df = self._make_ohlcv_df([("2026-05-06", 10, 11, 9, 10.0, 1000)])
        ok, result = _check_ma_cross(df, True)
        assert ok is False
        assert result is None

    def test_ma_cross_missing_ma_column(self):
        df = self._make_ohlcv_df([
            ("2026-05-06", 10, 11, 9, 10.0, 1000),
            ("2026-05-07", 10, 12, 9, 11.0, 1200),
        ])
        ok, result = _check_ma_cross(df, True)
        assert ok is False
        assert result is None


# ---------------------------------------------------------------------------
# _check_stock_alerts — integration
# ---------------------------------------------------------------------------

class TestCheckStockAlerts:
    def _make_ohlcv_df(self, rows: list) -> pd.DataFrame:
        df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"])
        return df

    def test_price_alert_only(self):
        alerts = {"price_above": 1500.0}
        triggered = _check_stock_alerts(
            ticker="600519", alerts=alerts, date="2026-05-09",
            spot_price=1600.0, ohlcv_data=None, wrapped_df=None,
        )
        assert len(triggered) == 1
        assert triggered[0]["alert"] == "price_above"

    def test_price_alert_not_triggered(self):
        alerts = {"price_below": 1500.0}
        triggered = _check_stock_alerts(
            ticker="600519", alerts=alerts, date="2026-05-09",
            spot_price=1600.0, ohlcv_data=None, wrapped_df=None,
        )
        assert len(triggered) == 0

    def test_no_alerts(self):
        triggered = _check_stock_alerts(
            ticker="600519", alerts={}, date="2026-05-09",
            spot_price=None, ohlcv_data=None, wrapped_df=None,
        )
        assert len(triggered) == 0

    def test_invalid_alert_type_skipped(self):
        alerts = {"price_above": 1500.0, "unknown_alert": 100}
        triggered = _check_stock_alerts(
            ticker="600519", alerts=alerts, date="2026-05-09",
            spot_price=1600.0, ohlcv_data=None, wrapped_df=None,
        )
        assert len(triggered) == 1
        assert triggered[0]["alert"] == "price_above"

    def test_rsi_alerts_need_ohlcv_but_none(self):
        alerts = {"rsi_oversold": True}
        triggered = _check_stock_alerts(
            ticker="600519", alerts=alerts, date="2026-05-09",
            spot_price=1600.0, ohlcv_data=None, wrapped_df=None,
        )
        # ohlcv_data is None, so RSI check returns None → no trigger
        assert triggered == []

    def test_multiple_alerts(self):
        alerts = {"price_above": 1500.0, "price_below": 2000.0}
        triggered = _check_stock_alerts(
            ticker="000858", alerts=alerts, date="2026-05-09",
            spot_price=1800.0, ohlcv_data=None, wrapped_df=None,
        )
        assert len(triggered) == 2
        alert_types = {t["alert"] for t in triggered}
        assert alert_types == {"price_above", "price_below"}

    def test_check_without_spot_price(self):
        alerts = {"price_above": 1500.0}
        triggered = _check_stock_alerts(
            ticker="600519", alerts=alerts, date="2026-05-09",
            spot_price=None, ohlcv_data=None, wrapped_df=None,
        )
        assert triggered == []


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestAlertConstants:
    def test_valid_alert_types(self):
        assert "price_above" in VALID_ALERT_TYPES
        assert "price_below" in VALID_ALERT_TYPES
        assert "rsi_oversold" in VALID_ALERT_TYPES
        assert "rsi_overbought" in VALID_ALERT_TYPES
        assert "volume_surge" in VALID_ALERT_TYPES
        assert "ma_cross" in VALID_ALERT_TYPES
        assert len(VALID_ALERT_TYPES) == 6

    def test_price_alerts_set(self):
        assert PRICE_ALERTS == {"price_above", "price_below"}

    def test_rsi_alerts_set(self):
        assert RSI_ALERTS == {"rsi_oversold", "rsi_overbought"}


# ---------------------------------------------------------------------------
# CLI registration smoke test
# ---------------------------------------------------------------------------

class TestCLIRegistration:
    def test_check_alerts_command_registered(self):
        from cli.main import app
        names = [c.name for c in app.registered_commands if c.name is not None]
        assert "check-alerts" in names

    def test_check_alerts_import(self):
        from cli.alerts import check_alerts
        assert callable(check_alerts)
