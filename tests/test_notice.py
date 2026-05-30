"""Tests for cli/notice.py and akshare.py get_individual_notices."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from tradingagents.dataflows.akshare import get_individual_notices, get_research_reports


class TestGetIndividualNotices:
    """Tests for get_individual_notices() in akshare.py."""

    @patch("tradingagents.dataflows.a_stock_data.get_cninfo_announcements")
    def test_notices_returned(self, mock_cninfo):
        """Returns Markdown with notice titles."""
        mock_cninfo.return_value = (
            "# 巨潮公告 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "| announcementTitle | announcementTime | secName | adjunctUrl |\n"
            "|---|---|---|---|\n"
            "| 贵州茅台2025年度利润分配预案公告 | 2026-05-08 00:00:00 | 贵州茅台 | https://example.com/ann1 |\n"
            "| 关于召开2025年度股东大会的通知 | 2026-05-07 00:00:00 | 贵州茅台 | https://example.com/ann2 |\n"
        )
        result = get_individual_notices("600519", days_back=7)
        assert "600519" in result
        assert "利润分配预案" in result or "公告" in result
        assert "股东大会" in result

    @patch("tradingagents.dataflows.a_stock_data.get_cninfo_announcements")
    def test_empty_notices(self, mock_cninfo):
        """No notices returns appropriate message."""
        mock_cninfo.return_value = (
            "# 巨潮公告 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "无数据\n"
        )
        result = get_individual_notices("600519", days_back=3)
        assert "未找到" in result or "no" in result.lower() or "无数据" in result

    @patch("tradingagents.dataflows.a_stock_data.get_cninfo_announcements")
    def test_notice_type_filter(self, mock_cninfo):
        """Type filter is passed (symbol forwarded to cninfo)."""
        mock_cninfo.return_value = (
            "# 巨潮公告 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "| announcementTitle | announcementTime | secName | adjunctUrl |\n"
            "|---|---|---|---|\n"
            "| 贵州茅台2025年度利润分配预案公告 | 2026-05-08 00:00:00 | 贵州茅台 | https://example.com/ann1 |\n"
        )
        result = get_individual_notices("600519", days_back=7, notice_type="财务报告")
        assert mock_cninfo.call_count == 1
        assert mock_cninfo.call_args[0][0] == "600519"
        assert mock_cninfo.call_args[1]["page_size"] == 21

    @patch("tradingagents.dataflows.a_stock_data.get_cninfo_announcements")
    def test_days_back_passed(self, mock_cninfo):
        """Days back is converted to page_size parameter."""
        mock_cninfo.return_value = (
            "# 巨潮公告 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "| announcementTitle | announcementTime | secName | adjunctUrl |\n"
            "|---|---|---|---|\n"
            "| 贵州茅台2025年度利润分配预案公告 | 2026-05-08 00:00:00 | 贵州茅台 | https://example.com/ann1 |\n"
        )
        result = get_individual_notices("600519", days_back=3)
        assert mock_cninfo.call_args[1]["page_size"] == 9


class TestGetResearchReports:
    """Tests for get_research_reports() in akshare.py."""

    @patch("tradingagents.dataflows.a_stock_data.get_research_reports")
    def test_reports_returned(self, mock_rpt):
        """Returns Markdown with report titles."""
        mock_rpt.return_value = (
            "# 研报列表 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "| title | publishDate | orgSName | predictThisYearEps | predictNextYearEps | emRatingName |\n"
            "|---|---|---|---|---|---|\n"
            "| 贵州茅台：强者恒强，目标价2000元 | 2026-05-09 | 中信证券 | 62.00 | 70.00 | 买入 |\n"
            "| 贵州茅台：Q1业绩超预期 | 2026-05-07 | 华泰证券 | 58.00 | 65.00 | 增持 |\n"
        )
        result = get_research_reports("600519", top_n=5)
        assert "600519" in result
        assert "中信证券" in result
        assert "目标价" in result

    @patch("tradingagents.dataflows.a_stock_data.get_research_reports")
    def test_empty_reports(self, mock_rpt):
        """No reports returns appropriate message."""
        mock_rpt.return_value = (
            "# 研报列表 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "无数据\n"
        )
        result = get_research_reports("600519")
        assert "未找到" in result or "no" in result.lower() or "无数据" in result

    @patch("tradingagents.dataflows.a_stock_data.get_research_reports")
    def test_top_n_limit(self, mock_rpt):
        """top_n is converted to max_pages parameter."""
        rows = "".join(
            f"| Report {i} | 2026-05-{i:02d} |\n"
            for i in range(1, 11)
        )
        mock_rpt.return_value = (
            "# 研报列表 — 600519\n"
            "# 数据来源: a-stock-data\n"
            "# 请求时间: 2026-05-30 12:00:00\n"
            "\n"
            "| title | publishDate |\n"
            "|---|---|\n"
            f"{rows}"
        )
        result = get_research_reports("600519", top_n=3)
        assert mock_rpt.call_args[1]["max_pages"] == 1
        lines = [l for l in result.split("\n") if "Report" in l]
        assert len(lines) >= 3
