import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from .schemas import MatchResult, Trigger, Context

logger = logging.getLogger(__name__)


class TemplateMatcher:
    def __init__(self, templates_dir: str = "~/.tradingagents/templates"):
        self.templates_dir = Path(templates_dir).expanduser()
        self.templates: List[Dict[str, Any]] = []
        self._load_all()

    def _load_all(self):
        if not self.templates_dir.exists():
            return
        for f in self.templates_dir.glob("*.json"):
            try:
                tpl = json.loads(f.read_text())
                self.templates.append(tpl)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Failed to load template: %s", f)
        self.templates.sort(key=lambda t: t.get("use_count", 0), reverse=True)
        logger.info("Loaded %d templates", len(self.templates))

    def match(self, trigger: Trigger, context: Context) -> MatchResult:
        features = self._extract_features(trigger, context)
        best_template = None
        best_score = 0.0

        for tpl in self.templates:
            score = self._score_template(tpl, features)
            if score > best_score:
                best_score = score
                best_template = tpl

        if best_score >= 0.85:
            return MatchResult(mode="exact_match", template=best_template, confidence=best_score)
        elif best_score >= 0.50:
            return MatchResult(mode="fuzzy_match", template=best_template, confidence=best_score)
        return MatchResult(mode="no_match")

    def match_with_kb(self, trigger, context, kb_context) -> MatchResult:
        base = self.match(trigger, context)
        if base.mode == "exact_match" or not kb_context or not kb_context.results:
            return base

        coverage = kb_context.coverage_score if hasattr(kb_context, 'coverage_score') else kb_context.get('coverage_score', 0)

        if coverage >= 0.7:
            return MatchResult(mode="exact_match", confidence=0.9)
        if coverage >= 0.4:
            base.confidence += 0.1
            if base.confidence >= 0.85:
                base.mode = "exact_match"
        return base

    def _extract_features(self, trigger: Trigger, context: Context) -> Dict[str, Any]:
        msg = trigger.message
        return {
            "message_text": msg,
            "has_holdings": bool(context.portfolio_summary),
            "has_watchlist": bool(context.watchlist_summary),
            "has_ticker": bool(context.ticker),
            "is_scheduled_morning": trigger.task == "晨会",
            "is_scheduled_midday": trigger.task == "午评",
            "is_scheduled_closing": trigger.task == "收盘复盘",
            "is_scheduled_weekly": trigger.task == "周日选股",
            "industry": context.industry or "",
        }

    def _score_template(self, template: Dict, features: Dict) -> float:
        patterns = template.get("match_patterns", {})
        score = 0.0

        keywords = patterns.get("keywords", [])
        if keywords:
            hits = sum(1 for kw in keywords if kw in features["message_text"])
            score += 0.4 * (hits / len(keywords))

        neg_keywords = patterns.get("negative_keywords", [])
        neg_hits = sum(1 for kw in neg_keywords if kw in features["message_text"])
        if neg_hits > 0:
            score -= 0.3

        required = patterns.get("required_context", [])
        if required and not all(features.get(r, False) for r in required):
            return 0.0

        # Industry-aware scoring boost
        industry = features.get("industry")
        industry_keywords = patterns.get("industry_keywords")
        if industry and industry_keywords:
            if industry in industry_keywords or any(kw in industry for kw in industry_keywords):
                score += 0.15

        score += 0.1 * min(template.get("use_count", 0) / 50, 1.0)
        score += 0.1 * template.get("success_rate", 0.5)

        return max(0.0, min(1.0, score))

    def register(self, template: Dict):
        existing = [t for t in self.templates if t.get("template_id") == template.get("template_id")]
        if existing:
            idx = self.templates.index(existing[0])
            self.templates[idx] = template
        else:
            self.templates.append(template)
        self._save_template(template)

    def _save_template(self, template: Dict):
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        tid = template["template_id"]
        path = self.templates_dir / f"{tid}.json"
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2))

    def for_user(self, user_id: str):
        return self
