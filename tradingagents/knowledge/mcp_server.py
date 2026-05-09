"""MCP (Model Context Protocol) Server for TradingAgents knowledge base.

Exposes analysis archive and knowledge graph as JSON-RPC tools over stdio
for consumption by AI agents (Claude Desktop, OpenClaw, etc.).

Tools:
- query_analysis:    Query by ticker/date/keyword
- get_ticker_signals: Signal distribution for ticker
- search_patterns:   Search recurring market patterns
- get_lessons:       Get cross-ticker lessons
- get_confidence:    Get confidence assessment for ticker
- get_graph_neighbors: Query knowledge graph neighbors

Usage:
    # Direct module execution
    python -m tradingagents.knowledge.mcp_server

    # Via CLI
    tradingagents mcp serve

    # With env vars
    TRADINGAGENTS_ARCHIVE_DIR=~/.tradingagents/analysis-archive \\
        python -m tradingagents.knowledge.mcp_server

MCP configuration for external clients:
.. code-block:: json

    {
      "mcpServers": {
        "trading-knowledge": {
          "command": "python",
          "args": ["-m", "tradingagents.knowledge.mcp_server"],
          "env": {
            "TRADINGAGENTS_ARCHIVE_DIR": "~/.tradingagents/analysis-archive"
          }
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph.context_assembly import ContextAssembler

logger = logging.getLogger(__name__)


# ======================================================================
# Graph merge utility
# ======================================================================


def merge_graphs(
    code_graph_path: str,
    analysis_graph_path: str,
    output_path: str,
) -> str:
    """Merge code knowledge graph with analysis knowledge graph.

    Reads two graphify JSON files and merges them into a unified graph.
    Nodes are merged uniquely by node ID.  Edges are concatenated and
    duplicate edges (same source + target + type) are removed.

    Each node gets a ``merged_from`` metadata tag indicating its origin
    graph(s).

    Args:
        code_graph_path: Path to code knowledge graph JSON.
        analysis_graph_path: Path to analysis knowledge graph JSON.
        output_path: Path to write the unified graph JSON.

    Returns:
        The ``output_path`` on success.

    Raises:
        FileNotFoundError: If either input graph is missing.
        json.JSONDecodeError: If either input is not valid JSON.
    """
    code_graph = _load_graph(code_graph_path, "code")
    analysis_graph = _load_graph(analysis_graph_path, "analysis")

    # --- Merge nodes ---
    merged_nodes: Dict[str, dict] = {}
    for g in (code_graph, analysis_graph):
        for node in g.get("nodes", []):
            nid = node.get("id", "")
            if not nid:
                continue
            if nid in merged_nodes:
                # Node exists in both graphs — merge metadata
                existing = merged_nodes[nid]
                existing_sources = set(existing.get("merged_from", []))
                new_sources = set(node.get("merged_from", []))
                existing["merged_from"] = sorted(existing_sources | new_sources)
                # Merge other fields (newer values win for overlapping keys)
                for k, v in node.items():
                    if k not in ("id", "merged_from"):
                        existing[k] = v
            else:
                merged_nodes[nid] = dict(node)

    # --- Merge edges ---
    seen_edges: set = set()
    merged_edges: List[dict] = []

    for g in (code_graph, analysis_graph):
        for edge in g.get("edges", []):
            key = (
                edge.get("source", ""),
                edge.get("target", ""),
                edge.get("type", edge.get("label", "")),
            )
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_copy = dict(edge)
            edge_copy.setdefault("merged_from", [])
            if g is code_graph:
                edge_copy["merged_from"] = list(
                    set(edge_copy["merged_from"]) | {"code"}
                )
            else:
                edge_copy["merged_from"] = list(
                    set(edge_copy["merged_from"]) | {"analysis"}
                )
            merged_edges.append(edge_copy)

    # --- Write output ---
    unified = {
        "nodes": list(merged_nodes.values()),
        "edges": merged_edges,
        "_meta": {
            "code_graph": os.path.basename(code_graph_path),
            "analysis_graph": os.path.basename(analysis_graph_path),
            "total_nodes": len(merged_nodes),
            "total_edges": len(merged_edges),
        },
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(unified, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(output)


def _load_graph(path: str, source: str) -> dict:
    """Load a graph JSON file and tag its nodes/edges with merged_from."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    for node in raw.get("nodes", []):
        node.setdefault("merged_from", [source])
    for edge in raw.get("edges", []):
        edge.setdefault("merged_from", [source])
    return raw


# ======================================================================
# KnowledgeMCPServer
# ======================================================================


class KnowledgeMCPServer:
    """Exposes analysis knowledge base as MCP (Model Context Protocol) tools.

    Communicates via JSON-RPC 2.0 over stdio.  Reads one JSON object per
    line from stdin, processes the request, and writes one JSON response
    per line to stdout.

    Tools:
    - ``query_analysis``:    Query analysis records by ticker/date/keyword.
    - ``get_ticker_signals``: Signal distribution and trend for a ticker.
    - ``search_patterns``:   Search for recurring market patterns.
    - ``get_lessons``:       Get cross-ticker lessons from memory log.
    - ``get_confidence``:    Get confidence assessment for a ticker.
    - ``get_graph_neighbors``: Query knowledge graph neighbors.
    """

    def __init__(
        self,
        archive: AnalysisArchive,
        graph_path: Optional[str] = None,
    ):
        """Initialize the MCP server.

        Args:
            archive: AnalysisArchive instance for data lookups.
            graph_path: Optional path to a unified knowledge graph JSON.
        """
        self.archive = archive
        self.graph: Optional[dict] = None
        if graph_path:
            self.graph = self._load_graph(graph_path)

        # Cache ContextAssembler for confidence computation
        self._assembler: Optional[ContextAssembler] = None

    # ------------------------------------------------------------------
    # Graph loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_graph(graph_path: str) -> Optional[dict]:
        """Load a graph JSON file, returning None on failure."""
        try:
            path = Path(graph_path).expanduser()
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # MCP Tool implementations
    # ------------------------------------------------------------------

    def tool_query_analysis(
        self,
        ticker: Optional[str] = None,
        date: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """Query analysis records by ticker, date, and/or keyword.

        Args:
            ticker: Filter by stock ticker (e.g., "600519").
            date: Filter by analysis date (ISO format, e.g., "2026-05-09").
            keyword: Full-text keyword search across archived entries.
            limit: Maximum results (default 10).

        Returns:
            List of matching entry metadata dicts.
        """
        if keyword:
            # Full-text search with optional ticker filter
            results = self.archive.search(query=keyword, limit=limit)
            if ticker:
                results = [r for r in results if r.get("ticker") == ticker]
            return results[:limit]

        # Index-based lookup
        return self.archive.list(
            ticker=ticker,
            date_from=date,
            date_to=date,
            limit=limit,
        )

    def tool_get_ticker_signals(
        self,
        ticker: str,
        days: int = 90,
    ) -> dict:
        """Get signal distribution and trend for a specific ticker.

        Includes confidence assessment computed from the ContextAssembler.

        Args:
            ticker: Stock ticker (e.g., "600519").
            days: Look-back window in calendar days (default 90).

        Returns:
            Dict with signal distribution, trend, and confidence tag.
        """
        summary = self.archive.summary(ticker, days=days)

        # Add confidence tag
        confidence = self.tool_get_confidence(ticker)
        summary["confidence"] = confidence

        return summary

    def tool_search_patterns(
        self,
        description: str,
        limit: int = 5,
    ) -> list:
        """Search for recurring market patterns in analysis history.

        Performs keyword search across archived entries and groups results
        by their decision direction.

        Args:
            description: Pattern description (e.g., "缩量突破", "MACD金叉").
            limit: Maximum pattern groups to return (default 5).

        Returns:
            List of pattern group dicts, each with: pattern description,
            count, examples.
        """
        results = self.archive.search(query=description, limit=limit * 3)

        if not results:
            return []

        # Group by decision direction as pattern clusters
        groups: Dict[str, dict] = {}
        for entry in results:
            decision = (entry.get("decision") or "unknown").lower()
            key = decision if decision in ("buy", "sell", "hold") else "other"
            if key not in groups:
                groups[key] = {
                    "pattern": f"{description} → {decision.title()}",
                    "count": 0,
                    "examples": [],
                }
            groups[key]["count"] += 1
            if len(groups[key]["examples"]) < 3:
                groups[key]["examples"].append({
                    "date": entry.get("date", ""),
                    "ticker": entry.get("ticker", ""),
                    "decision": entry.get("decision", ""),
                    "rating": entry.get("rating", ""),
                })

        patterns = sorted(
            groups.values(), key=lambda g: g["count"], reverse=True
        )
        return patterns[:limit]

    def tool_get_lessons(
        self,
        ticker: Optional[str] = None,
        market: Optional[str] = None,
    ) -> list:
        """Get cross-ticker lessons from the trading memory log.

        Args:
            ticker: Optional filter for specific ticker lessons.
            market: Market type filter (e.g., "A_SHARE"). Currently unused
                but reserved for future market-level lesson filtering.

        Returns:
            List of lesson dicts, each containing ticker, date, rating,
            decision, and reflection summary.  Most recent first.
        """
        from tradingagents.agents.utils.memory import TradingMemoryLog

        memory = TradingMemoryLog()
        entries = memory.load_entries()

        lessons = []
        for entry in entries:
            if entry.get("pending"):
                continue

            if ticker and entry.get("ticker") != ticker:
                continue

            reflection = entry.get("reflection", "")
            decision = entry.get("decision", "")
            # Build lesson with reflection or decision as fallback
            summary = (
                reflection[:200] + ("..." if len(reflection) > 200 else "")
                if reflection
                else decision[:200] + ("..." if len(decision) > 200 else "")
            )

            if summary:
                lessons.append({
                    "ticker": entry.get("ticker", ""),
                    "date": entry.get("date", ""),
                    "rating": entry.get("rating", ""),
                    "decision": decision[:300],
                    "lesson": summary,
                })

        # Most recent first
        lessons.sort(key=lambda x: x.get("date", ""), reverse=True)
        return lessons[:10]

    def tool_get_confidence(self, ticker: str) -> dict:
        """Get confidence assessment for a ticker's current signal.

        Uses ContextAssembler's rule-based confidence computation:
        - CONFIRMED: 3+ same-direction signals in last 30 days
        - SINGLE: only 1 analysis found
        - CONFLICTING: mixed buy/sell signals recently
        - STALE: last analysis > 90 days ago

        Args:
            ticker: Stock ticker (e.g., "600519").

        Returns:
            Dict with overall confidence tag, level, signal distribution,
            and label.
        """
        # Get archived entries for this ticker
        entries = self.archive.list(ticker=ticker, limit=20)

        if not entries:
            return {
                "overall": "SINGLE",
                "entries": {},
                "signal_distribution": {"buy": 0, "sell": 0, "hold": 0},
                "label": "无历史分析记录",
                "level": 3,
            }

        # Use ContextAssembler's compute method
        assembler = self._get_assembler()
        return assembler._compute_confidence(ticker, entries)

    def tool_get_graph_neighbors(
        self,
        node_id: str,
        depth: int = 1,
    ) -> dict:
        """Query knowledge graph for a node and its neighbors.

        Traverses the loaded unified-graph.json to find a node by ID
        and collect its directly connected neighbors.

        Args:
            node_id: Node identifier in the knowledge graph.
            depth: How many hops to traverse (currently only depth=1
                is supported, defaults to 1).

        Returns:
            Dict with ``node`` info and ``neighbors`` list, or empty dict
            when no graph is loaded or node is not found.
        """
        if not self.graph:
            return {"node": None, "neighbors": [], "graph_loaded": False}

        nodes = self.graph.get("nodes", [])
        edges = self.graph.get("edges", [])

        # Find the node
        target_node = None
        for node in nodes:
            if node.get("id") == node_id:
                target_node = dict(node)
                break

        if not target_node:
            return {
                "node": None,
                "neighbors": [],
                "graph_loaded": True,
                "error": f"Node '{node_id}' not found",
            }

        # Find edges connected to this node
        neighbor_ids: set = set()
        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            if source == node_id and target:
                neighbor_ids.add(target)
            elif target == node_id and source:
                neighbor_ids.add(source)

        # Collect neighbor node info
        neighbors = [
            dict(n)
            for n in nodes
            if n.get("id") in neighbor_ids
        ]

        # Limit to one hop for now
        return {
            "node": target_node,
            "neighbors": neighbors[:50],
            "graph_loaded": True,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_assembler(self) -> ContextAssembler:
        """Lazily build a ContextAssembler for confidence computation."""
        if self._assembler is None:
            self._assembler = ContextAssembler()
        return self._assembler

    def _route_request(self, request: dict) -> dict:
        """Route a JSON-RPC request to the correct tool method.

        Handles:
        - ``tools/list``: Return the list of available tools.
        - ``tools/call``: Dispatch to the named tool.
        - ``initialize``:  Return server capabilities.
        """
        method = request.get("method", "")
        params = request.get("params", {})
        rpc_id = request.get("id", 0)

        # --- tools/list ---
        if method == "tools/list":
            return self._handle_list_tools()

        # --- tools/call ---
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return self._handle_tool_call(tool_name, arguments)

        # --- initialize ---
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "trading-knowledge",
                    "version": "0.2.5",
                },
                "capabilities": {
                    "tools": {},
                },
            }

        # --- unknown method ---
        return {"error": f"Unknown method: {method}"}

    def _handle_list_tools(self) -> dict:
        """Return the list of available MCP tools with their schemas."""
        return {
            "tools": [
                {
                    "name": "query_analysis",
                    "description": "查询分析记录。可按标的、日期、关键词过滤。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "股票代码，如 600519",
                            },
                            "date": {
                                "type": "string",
                                "description": "分析日期，ISO 格式 YYYY-MM-DD",
                            },
                            "keyword": {
                                "type": "string",
                                "description": "全文搜索关键词",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "最大返回数（默认10）",
                                "default": 10,
                            },
                        },
                    },
                },
                {
                    "name": "get_ticker_signals",
                    "description": "获取某标的的历史信号分布和趋势，含置信度评估。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "股票代码，如 600519",
                            },
                            "days": {
                                "type": "integer",
                                "description": "回溯天数（默认90）",
                                "default": 90,
                            },
                        },
                        "required": ["ticker"],
                    },
                },
                {
                    "name": "search_patterns",
                    "description": "搜索反复出现的市场行为模式。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "模式描述，如 缩量突破 或 MACD金叉",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "最大返回模式数（默认5）",
                                "default": 5,
                            },
                        },
                        "required": ["description"],
                    },
                },
                {
                    "name": "get_lessons",
                    "description": "获取跨标的经验教训，来自交易记忆日志。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "可选过滤：只返回指定标的的教训",
                            },
                            "market": {
                                "type": "string",
                                "description": "可选过滤：按市场类型筛选",
                            },
                        },
                    },
                },
                {
                    "name": "get_confidence",
                    "description": "获取某标的当前信号的置信度评估。返回 CONFIRMED/SINGLE/CONFLICTING/STALE 标签。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "股票代码，如 600519",
                            },
                        },
                        "required": ["ticker"],
                    },
                },
                {
                    "name": "get_graph_neighbors",
                    "description": "查询知识图谱中的相邻节点。需要先加载统一图。",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "节点ID",
                            },
                            "depth": {
                                "type": "integer",
                                "description": "跳数（默认1）",
                                "default": 1,
                            },
                        },
                        "required": ["node_id"],
                    },
                },
            ],
        }

    def _handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Dispatch a tool call to the correct handler method.

        Returns a dict with a ``content`` key containing the tool result.
        """
        tool_map = {
            "query_analysis": self.tool_query_analysis,
            "get_ticker_signals": self.tool_get_ticker_signals,
            "search_patterns": self.tool_search_patterns,
            "get_lessons": self.tool_get_lessons,
            "get_confidence": self.tool_get_confidence,
            "get_graph_neighbors": self.tool_get_graph_neighbors,
        }

        handler = tool_map.get(tool_name)
        if handler is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": f"Unknown tool: {tool_name}"},
                            ensure_ascii=False,
                        ),
                    }
                ],
                "isError": True,
            }

        try:
            result = handler(**arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, default=str),
                    }
                ],
                "isError": False,
            }
        except Exception as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": str(exc)},
                            ensure_ascii=False,
                        ),
                    }
                ],
                "isError": True,
            }

    # ------------------------------------------------------------------
    # stdio transport
    # ------------------------------------------------------------------

    def serve_stdio(self) -> None:
        """Run the MCP server in stdio mode.

        Reads JSON-RPC 2.0 requests from stdin (one JSON object per line),
        routes them to the appropriate tool handler, and writes JSON-RPC
        responses to stdout.

        Intended for use with MCP clients like Claude Desktop, OpenClaw,
        and other AI orchestrators that support the MCP stdio transport.

        The server runs until stdin is closed.
        """
        logger.info("Knowledge MCP Server starting (stdio mode)...")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32700,
                        "message": "Parse error",
                    },
                    "id": None,
                }
                sys.stdout.write(
                    json.dumps(error_response, ensure_ascii=False) + "\n"
                )
                sys.stdout.flush()
                continue

            rpc_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})

            try:
                # Handle notifications (no id) silently
                if rpc_id is None and method.startswith("notifications/"):
                    continue

                result = self._route_request(request)

                response: dict = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                }

                if isinstance(result, dict) and "error" in result:
                    response["error"] = {
                        "code": -32603,
                        "message": str(result["error"]),
                    }
                else:
                    response["result"] = result

                sys.stdout.write(
                    json.dumps(response, ensure_ascii=False) + "\n"
                )
                sys.stdout.flush()

            except Exception as exc:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": str(exc),
                    },
                    "id": rpc_id,
                }
                sys.stdout.write(
                    json.dumps(error_response, ensure_ascii=False) + "\n"
                )
                sys.stdout.flush()

        logger.info("Knowledge MCP Server stopped.")


# ======================================================================
# Module-level entry point
# ======================================================================


def _main() -> None:
    """Entry point for ``python -m tradingagents.knowledge.mcp_server``."""
    import logging

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    archive_dir = os.environ.get(
        "TRADINGAGENTS_ARCHIVE_DIR",
        os.path.expanduser("~/.tradingagents/analysis-archive"),
    )
    graph_path = os.environ.get("GRAPH_PATH", "")

    archive = AnalysisArchive(archive_dir)
    server = KnowledgeMCPServer(
        archive,
        graph_path=graph_path if os.path.exists(graph_path) else None,
    )
    server.serve_stdio()


if __name__ == "__main__":
    _main()
