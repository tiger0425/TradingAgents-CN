"""Tests for KnowledgeMCPServer and graph merge utility.

Coverage:
- MCP server initialization (with/without graph)
- All 6 MCP tools (query_analysis, get_ticker_signals, search_patterns,
  get_lessons, get_confidence, get_graph_neighbors)
- Edge cases (empty archive, missing graph, unknown node)
- Graph merge (code + analysis graphs)
- stdio serve request routing
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.knowledge.mcp_server import (
    KnowledgeMCPServer,
    merge_graphs,
)
from tradingagents.analysis_archive import AnalysisArchive


# ===================================================================
# Shared helpers
# ===================================================================

def build_sample_result(
    ticker: str = "600519",
    date: str = "2026-05-09",
    decision: str = "hold",
) -> dict:
    return {
        "request": {
            "ticker": ticker,
            "date": date,
            "analysts": ["market", "technical"],
            "llm_provider": "openai",
            "config_snapshot": {"market_type": "A_SHARE"},
        },
        "analysis": {
            "signals": {
                "market": {
                    "direction": "cautious",
                    "summary": "市场谨慎",
                },
            },
            "final_decision": decision,
            "rating": decision,
            "reasoning": "综合看多空因素...",
        },
        "tags": [],
    }


def make_entry_meta(
    entry_id: str = "2026/05/09/morning-scan_600519",
    ticker: str = "600519",
    date: str = "2026-05-09",
    decision: str = "Hold",
    entry_type: str = "morning-scan",
) -> dict:
    return {
        "id": entry_id,
        "date": date,
        "type": entry_type,
        "ticker": ticker,
        "decision": decision,
        "rating": decision,
        "analysts": ["market", "technical"],
        "tags": [],
    }


# ===================================================================
# TestMCPServerInit
# ===================================================================

class TestMCPServerInit:

    def test_init_with_archive_only(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)
        assert server.archive is archive
        assert server.graph is None

    def test_init_with_graph_path(self, tmp_path):
        graph_path = tmp_path / "test-graph.json"
        graph_data = {
            "nodes": [{"id": "n1", "label": "Node 1"}],
            "edges": [{"source": "n1", "target": "n2", "type": "related"}],
        }
        graph_path.write_text(json.dumps(graph_data), encoding="utf-8")

        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive, graph_path=str(graph_path))
        assert server.graph is not None
        assert len(server.graph["nodes"]) == 1
        assert len(server.graph["edges"]) == 1

    def test_init_with_nonexistent_graph_path(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(
            archive,
            graph_path="/nonexistent/path/graph.json",
        )
        assert server.graph is None


# ===================================================================
# TestMCPTools
# ===================================================================

class TestMCPTools:

    def test_query_analysis_by_ticker(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09", decision="buy")
        archive.save(result, "morning-scan")

        server = KnowledgeMCPServer(archive)
        results = server.tool_query_analysis(ticker="600519")
        assert len(results) >= 1
        assert results[0]["ticker"] == "600519"

    def test_query_analysis_by_date(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09")
        archive.save(result, "morning-scan")

        result2 = build_sample_result("000001", "2026-05-08")
        archive.save(result2, "morning-scan")

        server = KnowledgeMCPServer(archive)
        results = server.tool_query_analysis(date="2026-05-09")
        assert len(results) >= 1
        for r in results:
            assert r["date"] == "2026-05-09"

    def test_query_analysis_by_keyword(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09")
        result["tags"] = ["放量突破", "MACD金叉"]
        archive.save(result, "morning-scan")

        server = KnowledgeMCPServer(archive)
        # Wait — search() searches inside the full JSON, not just metadata
        # Need to use a keyword that appears in the entry content
        results = server.tool_query_analysis(keyword="综合看多空因素")
        assert len(results) >= 1

    def test_query_analysis_empty(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)
        results = server.tool_query_analysis(ticker="nonexistent")
        assert results == []

    def test_query_analysis_keyword_with_ticker(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09", decision="buy")
        result["tags"] = ["放量突破"]
        archive.save(result, "morning-scan")

        result2 = build_sample_result("000001", "2026-05-09", decision="buy")
        result2["tags"] = ["放量突破"]
        archive.save(result2, "morning-scan")

        server = KnowledgeMCPServer(archive)
        results = server.tool_query_analysis(
            keyword="放量突破", ticker="600519"
        )
        for r in results:
            assert r["ticker"] == "600519"

    def test_get_ticker_signals(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        # Save multiple entries to build signal distribution
        archive.save(
            build_sample_result("600519", "2026-05-09", decision="buy"),
            "morning-scan",
        )
        archive.save(
            build_sample_result("600519", "2026-05-08", decision="buy"),
            "evening-review",
        )
        archive.save(
            build_sample_result("600519", "2026-05-07", decision="sell"),
            "morning-scan",
        )

        server = KnowledgeMCPServer(archive)
        signals = server.tool_get_ticker_signals("600519", days=90)
        assert signals["ticker"] == "600519"
        assert signals["total_entries"] >= 3
        assert "buy" in signals["by_decision"]
        assert "sell" in signals["by_decision"]
        assert "confidence" in signals
        assert signals["confidence"]["overall"] in (
            "CONFIRMED", "SINGLE", "CONFLICTING", "STALE",
        )

    def test_get_ticker_signals_no_entries(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)
        signals = server.tool_get_ticker_signals("nonexistent")
        assert signals["ticker"] == "nonexistent"
        assert signals["total_entries"] == 0

    def test_search_patterns(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        for i in range(3):
            result = build_sample_result("600519", f"2026-05-0{9-i}", "buy")
            result["tags"] = ["缩量突破"]
            archive.save(result, "morning-scan")

        server = KnowledgeMCPServer(archive)
        patterns = server.tool_search_patterns("缩量突破")
        assert len(patterns) >= 1
        assert patterns[0]["count"] >= 1
        assert "pattern" in patterns[0]

    def test_search_patterns_no_match(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)
        patterns = server.tool_search_patterns("不存在的模式")
        assert patterns == []

    def test_get_lessons(self, tmp_path):
        server = KnowledgeMCPServer(AnalysisArchive.__new__(AnalysisArchive))
        server.archive = MagicMock()
        lessons = server.tool_get_lessons()
        assert isinstance(lessons, list)

    def test_get_lessons_filter_by_ticker(self):
        from tradingagents.agents.utils.memory import TradingMemoryLog

        with patch.object(TradingMemoryLog, "load_entries") as mock_load:
            mock_load.return_value = [
                {
                    "date": "2026-05-09",
                    "ticker": "600519",
                    "rating": "Buy",
                    "pending": False,
                    "reflection": "MACD金叉有效，放量突破前高",
                    "decision": "Buy: 技术面强势突破",
                },
                {
                    "date": "2026-05-08",
                    "ticker": "000001",
                    "rating": "Sell",
                    "pending": False,
                    "reflection": "基本面恶化，止损出局",
                    "decision": "Sell: 财务预警",
                },
            ]
            server = KnowledgeMCPServer(
                AnalysisArchive.__new__(AnalysisArchive)
            )
            lessons = server.tool_get_lessons(ticker="600519")
            assert len(lessons) == 1
            assert lessons[0]["ticker"] == "600519"
            assert lessons[0]["rating"] == "Buy"
            assert "reflection" not in lessons[0]
            assert "lesson" in lessons[0]

    def test_get_confidence(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        archive.save(
            build_sample_result("600519", "2026-05-09", decision="buy"),
            "morning-scan",
        )

        server = KnowledgeMCPServer(archive)
        confidence = server.tool_get_confidence("600519")
        assert confidence["overall"] in (
            "CONFIRMED", "SINGLE", "CONFLICTING", "STALE",
        )
        assert "label" in confidence
        assert "signal_distribution" in confidence

    def test_get_confidence_no_entries(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)
        confidence = server.tool_get_confidence("nonexistent")
        assert confidence["overall"] == "SINGLE"
        assert confidence["label"] == "无历史分析记录"

    def test_get_graph_neighbors_no_graph(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)
        result = server.tool_get_graph_neighbors("node1")
        assert result["graph_loaded"] is False
        assert result["node"] is None
        assert result["neighbors"] == []

    def test_get_graph_neighbors_with_graph(self, tmp_path):
        graph_path = tmp_path / "test-graph.json"
        graph_data = {
            "nodes": [
                {"id": "n1", "label": "600519"},
                {"id": "n2", "label": "Buy Signal"},
                {"id": "n3", "label": "MACD金叉"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "has_signal"},
                {"source": "n2", "target": "n3", "type": "based_on"},
            ],
        }
        graph_path.write_text(json.dumps(graph_data), encoding="utf-8")

        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive, graph_path=str(graph_path))
        result = server.tool_get_graph_neighbors("n2")
        assert result["graph_loaded"] is True
        assert result["node"] is not None
        assert result["node"]["id"] == "n2"
        assert len(result["neighbors"]) == 2

    def test_get_graph_neighbors_unknown_node(self, tmp_path):
        graph_path = tmp_path / "test-graph.json"
        graph_data = {
            "nodes": [{"id": "n1", "label": "600519"}],
            "edges": [],
        }
        graph_path.write_text(json.dumps(graph_data), encoding="utf-8")

        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive, graph_path=str(graph_path))
        result = server.tool_get_graph_neighbors("nonexistent")
        assert result["graph_loaded"] is True
        assert result["node"] is None
        assert "error" in result


# ===================================================================
# TestGraphMerge
# ===================================================================

class TestGraphMerge:

    def test_merge_two_graphs(self, tmp_path):
        code_path = tmp_path / "code-graph.json"
        analysis_path = tmp_path / "analysis-graph.json"
        output_path = tmp_path / "unified-graph.json"

        code_graph = {
            "nodes": [
                {"id": "n1", "label": "TradingAgentsGraph"},
                {"id": "n2", "label": "propagate"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "contains"},
            ],
        }
        analysis_graph = {
            "nodes": [
                {"id": "n1", "label": "TradingAgentsGraph"},
                {"id": "a1", "label": "600519 Analysis"},
            ],
            "edges": [
                {"source": "a1", "target": "n1", "type": "analyzed_by"},
            ],
        }

        code_path.write_text(json.dumps(code_graph), encoding="utf-8")
        analysis_path.write_text(json.dumps(analysis_graph), encoding="utf-8")

        result_path = merge_graphs(
            str(code_path), str(analysis_path), str(output_path)
        )
        assert result_path == str(output_path)
        assert output_path.exists()

        unified = json.loads(output_path.read_text(encoding="utf-8"))
        assert "nodes" in unified
        assert "edges" in unified
        assert "_meta" in unified

        # 3 unique nodes: n1 (shared), n2 (code-only), a1 (analysis-only)
        assert len(unified["nodes"]) == 3

        # 2 unique edges (no duplicates)
        assert len(unified["edges"]) == 2

        # Shared node n1 should have merged_from from both
        n1 = next(n for n in unified["nodes"] if n["id"] == "n1")
        assert "merged_from" in n1

    def test_merge_empty_graphs(self, tmp_path):
        code_path = tmp_path / "empty-code.json"
        analysis_path = tmp_path / "empty-analysis.json"
        output_path = tmp_path / "unified-empty.json"

        code_path.write_text(
            json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
        )
        analysis_path.write_text(
            json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
        )

        result_path = merge_graphs(
            str(code_path), str(analysis_path), str(output_path)
        )
        assert output_path.exists()
        unified = json.loads(output_path.read_text(encoding="utf-8"))
        assert len(unified["nodes"]) == 0
        assert len(unified["edges"]) == 0


# ===================================================================
# TestStdIOServe
# ===================================================================

class TestStdIOServe:

    def test_stdin_request_route(self, tmp_path):
        """Test that requests are properly routed via the internal router."""
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09", decision="buy")
        archive.save(result, "morning-scan")

        server = KnowledgeMCPServer(archive)

        # Route a tools/list request
        list_result = server._route_request({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
        })
        assert "tools" in list_result
        assert len(list_result["tools"]) == 6

    def test_route_initialize(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)

        result = server._route_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": 1,
        })
        assert result["serverInfo"]["name"] == "trading-knowledge"
        assert result["protocolVersion"] == "2024-11-05"

    def test_route_tool_call(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        archive.save(
            build_sample_result("600519", "2026-05-09", decision="buy"),
            "morning-scan",
        )

        server = KnowledgeMCPServer(archive)

        result = server._route_request({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "query_analysis",
                "arguments": {"ticker": "600519"},
            },
            "id": 2,
        })
        assert "content" in result
        assert not result.get("isError")
        content_text = result["content"][0]["text"]
        parsed = json.loads(content_text)
        assert len(parsed) >= 1
        assert parsed[0]["ticker"] == "600519"

    def test_route_tool_call_error(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)

        result = server._route_request({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "nonexistent_tool",
                "arguments": {},
            },
            "id": 3,
        })
        assert result.get("isError")

    def test_route_unknown_method(self, tmp_path):
        archive = AnalysisArchive(tmp_path)
        server = KnowledgeMCPServer(archive)

        result = server._route_request({
            "jsonrpc": "2.0",
            "method": "unknown/thing",
            "id": 4,
        })
        assert "error" in result
