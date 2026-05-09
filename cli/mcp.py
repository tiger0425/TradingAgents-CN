"""CLI command for MCP (Model Context Protocol) server.

Provides:
    tradingagents mcp serve — Start MCP server in stdio mode.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def serve(
    archive_dir: Optional[str] = None,
    graph_path: Optional[str] = None,
) -> None:
    """Start the Knowledge MCP Server in stdio mode.

    Reads JSON-RPC 2.0 requests from stdin and writes responses to stdout.
    Intended for use with MCP clients (Claude Desktop, OpenClaw, etc.).

    When ``archive_dir`` is not provided, the server reads the
    ``TRADINGAGENTS_ARCHIVE_DIR`` environment variable or falls back to
    ``~/.tradingagents/analysis-archive``.

    Args:
        archive_dir: Path to the analysis archive directory (optional).
        graph_path: Path to a unified knowledge graph JSON (optional).
    """
    from tradingagents.knowledge.mcp_server import KnowledgeMCPServer
    from tradingagents.analysis_archive import AnalysisArchive

    if archive_dir is None:
        archive_dir = os.environ.get(
            "TRADINGAGENTS_ARCHIVE_DIR",
            os.path.expanduser("~/.tradingagents/analysis-archive"),
        )

    logger.info("Starting Knowledge MCP Server...")
    logger.info("Archive directory: %s", archive_dir)
    if graph_path:
        logger.info("Graph path: %s", graph_path)

    archive = AnalysisArchive(archive_dir)
    server = KnowledgeMCPServer(archive, graph_path=graph_path)
    server.serve_stdio()
