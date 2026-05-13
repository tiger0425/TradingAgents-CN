import logging

logger = logging.getLogger(__name__)


def setup_agent_viz(graph, config: dict):
    if not config.get("debug_viz", False):
        return graph
    try:
        from langray import visualize
        logger.info("LangRay agent visualization enabled at http://localhost:8080")
        return visualize(graph, port=8080, open_browser=False)
    except ImportError:
        logger.warning("LangRay not installed. pip install langray to enable agent visualization.")
        return graph
