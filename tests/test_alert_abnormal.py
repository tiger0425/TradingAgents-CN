"""Tests for a_share_anomalies.py anomaly detection logic."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_akshare():
    """Replace a_share_anomalies.ak with a mock module."""
    fake_ak = MagicMock()
    fake_ak.stock_zt_pool_em = MagicMock()
    fake_ak.stock_zt_pool_dtgc_em = MagicMock()
    fake_ak.stock_zt_pool_zbgc_em = MagicMock()
    fake_ak.stock_zt_pool_strong_em = MagicMock()
    fake_ak.stock_zt_pool_previous_em = MagicMock()
    with patch("tradingagents.dataflows.a_share_anomalies.ak", fake_ak):
        yield fake_ak


def _fake_limit_up_df() -> pd.DataFrame:
    """Fake limit-up pool DataFrame."""
    return pd.DataFrame([
        {"代码": "600519", "名称": "贵州茅台", "最新价": 1700.0,
         "涨跌幅": 10.0, "涨停统计": 3},
        {"代码": "000858", "名称": "五粮液", "最新价": 160.0,
         "涨跌幅": 10.0, "涨停统计": 1},
        {"代码": "601318", "名称": "中国平安", "最新价": 55.0,
         "涨跌幅": 10.0, "涨停统计": 2},
    ])


def _fake_limit_down_df() -> pd.DataFrame:
    """Fake limit-down pool DataFrame."""
    return pd.DataFrame([
        {"代码": "002456", "名称": "欧菲光", "最新价": 8.5,
         "涨跌幅": -10.0},
        {"代码": "600519", "名称": "贵州茅台", "最新价": 1400.0,
         "涨跌幅": -10.0},
    ])


def _fake_zhaban_df() -> pd.DataFrame:
    """Fake 炸板 pool DataFrame."""
    return pd.DataFrame([
        {"代码": "300750", "名称": "宁德时代", "最新价": 220.0,
         "涨跌幅": 5.0, "炸板次数": 2},
    ])


class TestAksharePoolFunctions:
    """Tests for individual pool getters."""

    def test_get_limit_up_pool(self, mock_akshare):
        mock_akshare.stock_zt_pool_em.return_value = _fake_limit_up_df()
        from tradingagents.dataflows.a_share_anomalies import get_limit_up_pool
        result = get_limit_up_pool("2026-05-09")
        assert len(result) == 3
        assert result[0]["code"] == "600519"
        assert result[0]["limit_count"] == 3

    def test_get_limit_up_pool_empty(self, mock_akshare):
        mock_akshare.stock_zt_pool_em.return_value = pd.DataFrame()
        from tradingagents.dataflows.a_share_anomalies import get_limit_up_pool
        result = get_limit_up_pool("2026-05-09")
        assert result == []

    def test_get_limit_down_pool(self, mock_akshare):
        mock_akshare.stock_zt_pool_dtgc_em.return_value = _fake_limit_down_df()
        from tradingagents.dataflows.a_share_anomalies import get_limit_down_pool
        result = get_limit_down_pool("2026-05-09")
        assert len(result) == 2

    def test_get_zhaban_pool(self, mock_akshare):
        mock_akshare.stock_zt_pool_zbgc_em.return_value = _fake_zhaban_df()
        from tradingagents.dataflows.a_share_anomalies import get_zhaban_pool
        result = get_zhaban_pool("2026-05-09")
        assert len(result) == 1
        assert result[0]["code"] == "300750"


class TestDetectionFunctions:
    """Tests for higher-level detection functions."""

    def test_detect_limit_moves(self, mock_akshare):
        mock_akshare.stock_zt_pool_em.return_value = _fake_limit_up_df()
        mock_akshare.stock_zt_pool_dtgc_em.return_value = _fake_limit_down_df()

        from tradingagents.dataflows.a_share_anomalies import detect_limit_moves
        result = detect_limit_moves("2026-05-09")
        assert result["count_up"] == 3
        assert result["count_down"] == 2

    def test_detect_tiandiban(self, mock_akshare):
        """600519 appears in both up and down pools = 天地板."""
        mock_akshare.stock_zt_pool_em.return_value = _fake_limit_up_df()
        mock_akshare.stock_zt_pool_dtgc_em.return_value = _fake_limit_down_df()

        from tradingagents.dataflows.a_share_anomalies import detect_tiandiban
        result = detect_tiandiban("2026-05-09")
        assert len(result) == 1
        assert result[0]["code"] == "600519"

    def test_detect_consecutive_limits(self, mock_akshare):
        mock_akshare.stock_zt_pool_em.return_value = _fake_limit_up_df()

        from tradingagents.dataflows.a_share_anomalies import detect_consecutive_limits
        result = detect_consecutive_limits("2026-05-09", min_days=3)
        assert len(result) == 1
        assert result[0]["code"] == "600519"

    def test_detect_all_anomalies(self, mock_akshare):
        mock_akshare.stock_zt_pool_em.return_value = _fake_limit_up_df()
        mock_akshare.stock_zt_pool_dtgc_em.return_value = _fake_limit_down_df()
        mock_akshare.stock_zt_pool_zbgc_em.return_value = _fake_zhaban_df()
        mock_akshare.stock_zt_pool_strong_em.return_value = pd.DataFrame()
        mock_akshare.stock_zt_pool_previous_em.return_value = pd.DataFrame()

        from tradingagents.dataflows.a_share_anomalies import detect_all_anomalies
        result = detect_all_anomalies("2026-05-09")
        assert "date" in result
        assert "limit_moves" in result
        assert "zhaban" in result
        assert result["limit_moves"]["count_up"] == 3
