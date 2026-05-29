from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Trigger:
    type: str  # "scheduled" | "customer_message"
    task: str = ""
    message: str = ""
    timeout_minutes: int = 10


@dataclass
class Context:
    user_id: str = "default"
    ticker: str = ""
    industry: str = ""
    portfolio_summary: str = ""
    watchlist_summary: str = ""
    market_state: str = ""


@dataclass
class KBContext:
    results: List[Dict[str, Any]] = field(default_factory=list)
    coverage_score: float = 0.0
    coverage_detail: Dict[str, Any] = field(default_factory=dict)
    missing_aspects: List[str] = field(default_factory=list)


@dataclass
class MatchResult:
    mode: str = "no_match"  # "exact_match" | "fuzzy_match" | "no_match"
    template: Optional[Dict[str, Any]] = None
    confidence: float = 0.0


@dataclass
class WorkflowStep:
    step: int
    agent: str
    task: str
    context: List[str] = field(default_factory=list)
    depends_on: List[int] = field(default_factory=list)
    expected_output: str = ""


@dataclass
class WorkflowPlan:
    intent: str = ""
    reasoning: str = ""
    workflow: List[WorkflowStep] = field(default_factory=list)
    final_output_type: str = "report"
    urgency: str = "medium"
    estimated_cost_usd: float = 0.5
    estimated_time_seconds: int = 120
    kb_results: Optional[KBContext] = None
    _generation_mode: str = "template_exact"
    _template_id: str = ""
