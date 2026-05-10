"""Tests for cli/research_report.py CLI wiring (minimal)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestResearchReportCli:
    """Integration tests for research_report CLI (mocked data layer)."""

    @patch("tradingagents.dataflows.akshare.ak.stock_research_report_em")
    def test_research_report_command_exists(self, mock_ak):
        """CLI module can be imported and has expected function."""
        from cli.research_report import research_report_command
        assert callable(research_report_command)
        assert research_report_command.__doc__ is not None

    @patch("tradingagents.dataflows.akshare.ak.stock_research_report_em")
    def test_research_report_scan_watchlist_exists(self, mock_ak):
        """Scan-watchlist option is wired."""
        from cli.research_report import _scan_watchlist
        assert callable(_scan_watchlist)
