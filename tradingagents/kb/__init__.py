# Knowledge Base Module
# Background collectors write structured research into KB.
# Event-driven layer queries KB before launching agents.

from .knowledge_base import KnowledgeBase
from .freshness import FreshnessManager

__all__ = ["KnowledgeBase", "FreshnessManager"]
