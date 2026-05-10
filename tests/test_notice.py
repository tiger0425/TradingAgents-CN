"""Tests for cli/notice.py and akshare.py get_individual_notices."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from tradingagents.dataflows.akshare import get_individual_notices, get_research_reports


def _fake_notices() -> pd.DataFrame:
    """Return fake announcement DataFrame."""
    return pd.DataFrame([
        {
            "股票代码": "600519",
            "股票简称": "贵州茅台",
            "公告标题": "贵州茅台2025年度利润分配预案公告",
            "公告分类": "财务报告",
            "公告时间": "2026-05-08",
            "公告内容": "公司拟以总股本为基数，向全体股东每10股派发现金红利250元。",
        },
        {
            "股票代码": "600519",
            "股票简称": "贵州茅台",
            "公告标题": "关于召开2025年度股东大会的通知",
            "公告分类": "重大事项",
            "公告时间": "2026-05-07",
            "公告内容": "公司董事会决定于2026年6月召开2025年度股东大会。",
        },
    ])


class TestGetIndividualNotices:
    """Tests for get_individual_notices() in akshare.py."""

    @patch("tradingagents.dataflows.akshare.ak.stock_individual_notice_report", return_value=_fake_notices())
    def test_notices_returned(self, mock_ak):
        """Returns Markdown with notice titles."""
        result = get_individual_notices("600519", days_back=7)
        assert "600519" in result
        assert "利润分配预案" in result or "公告" in result
        assert "股东大会" in result

    @patch("tradingagents.dataflows.akshare.ak.stock_individual_notice_report", return_value=pd.DataFrame())
    def test_empty_notices(self, mock_ak):
        """No notices returns appropriate message."""
        result = get_individual_notices("600519", days_back=3)
        assert "未找到" in result or "no" in result.lower()

    @patch("tradingagents.dataflows.akshare.ak.stock_individual_notice_report", return_value=_fake_notices())
    def test_notice_type_filter(self, mock_ak):
        """Type filter is passed to akshare."""
        result = get_individual_notices("600519", days_back=7, notice_type="财务报告")
        # The filtering is done server-side by akshare
        assert mock_ak.call_count == 1
        call_args = mock_ak.call_args[1]
        assert call_args.get("symbol") == "财务报告"

    @patch("tradingagents.dataflows.akshare.ak.stock_individual_notice_report", return_value=_fake_notices())
    def test_days_back_passed(self, mock_ak):
        """Days back is converted to begin_date parameter."""
        result = get_individual_notices("600519", days_back=3)
        call_kwargs = mock_ak.call_args[1]
        assert "begin_date" in call_kwargs


class TestGetResearchReports:
    """Tests for get_research_reports() in akshare.py."""

    @patch("tradingagents.dataflows.akshare.ak.stock_research_report_em")
    def test_reports_returned(self, mock_ak):
        """Returns Markdown with report titles."""
        mock_ak.return_value = pd.DataFrame([
            {"标题": "贵州茅台：强者恒强，目标价2000元", "日期": "2026-05-09",
             "机构": "中信证券", "评级": "买入"},
            {"标题": "贵州茅台：Q1业绩超预期", "日期": "2026-05-07",
             "机构": "华泰证券", "评级": "增持"},
        ])
        result = get_research_reports("600519", top_n=5)
        assert "600519" in result
        assert "中信证券" in result
        assert "目标价" in result

    @patch("tradingagents.dataflows.akshare.ak.stock_research_report_em", return_value=pd.DataFrame())
    def test_empty_reports(self, mock_ak):
        """No reports returns appropriate message."""
        result = get_research_reports("600519")
        assert "未找到" in result or "no" in result.lower()

    @patch("tradingagents.dataflows.akshare.ak.stock_research_report_em")
    def test_top_n_limit(self, mock_ak):
        """Only top_n reports appear in output."""
        mock_ak.return_value = pd.DataFrame([
            {"标题": f"Report {i}", "日期": f"2026-05-{i:02d}"}
            for i in range(1, 11)
        ])
        result = get_research_reports("600519", top_n=3)
        # Should contain report 1 and 2 and 3 (at least 3 items)
        lines = [l for l in result.split("\n") if "Report" in l]
        assert len(lines) >= 3
        assert "Report 4" not in result  # Beyond top_n
