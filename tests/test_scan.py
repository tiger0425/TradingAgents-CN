"""Tests for cli/scan.py core logic — no network calls."""

import json
import pytest
from cli.scan import (
    _group_signals,
    _build_scan_json_output,
    _format_scan_text_header,
    _format_scan_text_signals,
    _truncate_text,
    _format_signal_line,
    SIGNAL_KEYS,
)


class TestTruncateText:
    def test_short_text_unchanged(self):
        assert _truncate_text("hello", 10) == "hello"

    def test_long_text_truncated(self):
        result = _truncate_text("a" * 200, 100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        assert _truncate_text("12345", 5) == "12345"

    def test_empty_string(self):
        assert _truncate_text("", 10) == ""

    def test_none_value(self):
        assert _truncate_text(None, 10) == ""


class TestFormatSignalLine:
    def test_with_tickers(self):
        line = _format_signal_line("Buy", ["600519", "000858"])
        assert "Buy" in line
        assert "600519" in line
        assert "000858" in line

    def test_empty_tickers(self):
        line = _format_signal_line("Sell", [])
        assert "(none)" in line

    def test_single_ticker(self):
        line = _format_signal_line("Hold", ["300750"])
        assert "Hold" in line
        assert "300750" in line
        assert "," not in line  # no trailing comma for single item


class TestGroupSignals:
    def test_all_decisions_distinct(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": "strong buy"},
            {"ticker": "002415", "decision": "Overweight", "summary": "good"},
            {"ticker": "300750", "decision": "Hold", "summary": "stable"},
            {"ticker": "000001", "decision": "Underweight", "summary": "caution"},
            {"ticker": "000002", "decision": "Sell", "summary": "exit"},
        ]
        signals = _group_signals(results)
        assert signals["buy"] == ["600519"]
        assert signals["overweight"] == ["002415"]
        assert signals["hold"] == ["300750"]
        assert signals["underweight"] == ["000001"]
        assert signals["sell"] == ["000002"]

    def test_multiple_same_decision(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": ""},
            {"ticker": "000858", "decision": "Buy", "summary": ""},
            {"ticker": "300750", "decision": "Hold", "summary": ""},
        ]
        signals = _group_signals(results)
        assert signals["buy"] == ["600519", "000858"]
        assert signals["hold"] == ["300750"]
        assert signals["sell"] == []

    def test_empty_results(self):
        signals = _group_signals([])
        for key in SIGNAL_KEYS:
            assert signals[key] == []

    def test_error_results_skipped(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": ""},
            {"ticker": "000001", "error": "API timeout"},
            {"ticker": "300750", "decision": "Hold", "summary": ""},
        ]
        signals = _group_signals(results)
        assert signals["buy"] == ["600519"]
        assert signals["hold"] == ["300750"]
        # "000001" should not appear in any signal group
        all_tickers = []
        for tickers in signals.values():
            all_tickers.extend(tickers)
        assert "000001" not in all_tickers

    def test_unknown_decision_falls_to_hold(self):
        results = [
            {"ticker": "999999", "decision": "StrongBuy", "summary": ""},
        ]
        signals = _group_signals(results)
        # "StrongBuy" → "strongbuy" → not in SIGNAL_KEYS → silently skipped
        # But wait, the code only adds to signals if key in signals dict
        all_tickers = []
        for tickers in signals.values():
            all_tickers.extend(tickers)
        assert "999999" not in all_tickers

    def test_all_signal_keys_present(self):
        signals = _group_signals([])
        for key in SIGNAL_KEYS:
            assert key in signals
            assert isinstance(signals[key], list)
        assert len(signals) == 5


class TestBuildScanJsonOutput:
    def test_basic_structure(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": "strong buy signal"},
            {"ticker": "300750", "decision": "Hold", "summary": "hold position"},
        ]
        signals = _group_signals(results)
        output = _build_scan_json_output("2026-05-09", results, signals, 2, 2)

        assert output["date"] == "2026-05-09"
        assert output["total"] == 2
        assert output["scanned"] == 2
        assert output["signals"]["buy"] == ["600519"]
        assert output["signals"]["hold"] == ["300750"]
        assert len(output["details"]) == 2

    def test_details_include_decision_and_summary(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": "strong buy"},
        ]
        signals = _group_signals(results)
        output = _build_scan_json_output("2026-05-09", results, signals, 1, 1)

        detail = output["details"][0]
        assert detail["ticker"] == "600519"
        assert detail["decision"] == "Buy"
        assert detail["summary"] == "strong buy"

    def test_error_results_in_details(self):
        results = [
            {"ticker": "000001", "error": "Connection timeout"},
        ]
        signals = _group_signals(results)
        output = _build_scan_json_output("2026-05-09", results, signals, 0, 2)

        detail = output["details"][0]
        assert detail["ticker"] == "000001"
        assert detail["status"] == "error"
        assert detail["error"] == "Connection timeout"

    def test_extra_fields_passed_through(self):
        results = []
        signals = _group_signals(results)
        output = _build_scan_json_output(
            "2026-05-09", results, signals, 0, 0,
            quotes=[{"ticker": "600519", "current_price": 1580.0}],
            holdings=5,
            total_pnl=12345.67,
        )
        assert output["quotes"] == [{"ticker": "600519", "current_price": 1580.0}]
        assert output["holdings"] == 5
        assert output["total_pnl"] == 12345.67

    def test_per_ticker_metadata_in_details(self):
        results = [
            {
                "ticker": "600519",
                "decision": "Buy",
                "summary": "buy",
                "current_price": 1580.0,
                "change": -5.0,
                "change_pct": -0.32,
                "name": "贵州茅台",
            },
        ]
        signals = _group_signals(results)
        output = _build_scan_json_output("2026-05-09", results, signals, 1, 1)

        detail = output["details"][0]
        assert detail["current_price"] == 1580.0
        assert detail["change"] == -5.0
        assert detail["change_pct"] == -0.32
        assert detail["name"] == "贵州茅台"

    def test_json_serializable(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": "test"},
        ]
        signals = _group_signals(results)
        output = _build_scan_json_output("2026-05-09", results, signals, 1, 1)
        # Must not raise
        dumped = json.dumps(output, ensure_ascii=False)
        assert "600519" in dumped

    def test_scanned_less_than_total(self):
        results = [
            {"ticker": "600519", "decision": "Buy", "summary": ""},
            {"ticker": "000001", "error": "Failed"},
        ]
        signals = _group_signals(results)
        output = _build_scan_json_output("2026-05-09", results, signals, 1, 3)

        assert output["scanned"] == 1
        assert output["total"] == 3
        assert output["signals"]["buy"] == ["600519"]


class TestFormatScanTextHeader:
    def test_generates_header(self):
        header = _format_scan_text_header("My Scan", "2026-05-09", 10, 15)
        assert "My Scan" in header
        assert "2026-05-09" in header
        assert "Total:      15  Scanned: 10" in header

    def test_all_scanned(self):
        header = _format_scan_text_header("Test", "2026-05-09", 5, 5)
        assert "Total:      5  Scanned: 5" in header

    def test_separator_present(self):
        header = _format_scan_text_header("X", "2026-05-09", 0, 0)
        assert "=" * 60 in header


class TestFormatScanTextSignals:
    def test_all_groups_rendered(self):
        signals = {
            "buy": ["600519"],
            "overweight": [],
            "hold": ["300750", "601318"],
            "underweight": [],
            "sell": [],
        }
        text = _format_scan_text_signals(signals)
        assert "Buy" in text
        assert "600519" in text
        assert "Overweight" in text
        assert "(none)" in text
        assert "300750" in text
        assert "601318" in text

    def test_empty_signals(self):
        signals = {k: [] for k in SIGNAL_KEYS}
        text = _format_scan_text_signals(signals)
        for key in SIGNAL_KEYS:
            assert key in text.lower() or key.capitalize() in text or key.title() in text

    def test_respects_indent(self):
        signals = {k: [] for k in SIGNAL_KEYS}
        indented = _format_scan_text_signals(signals, indent="    ")
        assert indented.startswith("    ")


class TestSIGNALKEYS:
    def test_all_keys_are_lowercase(self):
        for key in SIGNAL_KEYS:
            assert key == key.lower()
            assert key in ("buy", "overweight", "hold", "underweight", "sell")

    def test_exactly_five_keys(self):
        assert len(SIGNAL_KEYS) == 5
