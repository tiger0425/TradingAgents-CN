import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class DataExporter:
    def __init__(self, portfolio_mgr, kb, archive=None, cost_tracker=None,
                 template_evolver=None, base_dir="~/.tradingagents"):
        self.portfolio = portfolio_mgr
        self.kb = kb
        self.archive = archive
        self.cost_tracker = cost_tracker
        self.template_evolver = template_evolver
        self.base_dir = Path(base_dir).expanduser()

    def export(self, user_id: str = "default") -> dict:
        data = {
            "updated_at": datetime.now().isoformat(),
            "user_id": user_id,
            "portfolio": self._export_portfolio(user_id),
            "kb_status": self.kb.get_freshness_summary() if self.kb else {},
            "costs": self.cost_tracker.get_monthly(user_id) if self.cost_tracker else {},
            "template_health": (
                self.template_evolver.get_stats(user_id)
                if self.template_evolver else []
            ),
            "recent_briefings": (
                self.archive.list_recent(user_id, limit=20)
                if self.archive else []
            ),
        }
        out_path = self.base_dir / "users" / user_id / "dashboard_data.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("Dashboard data exported for %s", user_id)
        return data

    def _export_portfolio(self, user_id: str) -> dict:
        p = self.portfolio.load(user_id)
        return {
            "holdings": p.get("holdings", []),
            "watchlist": p.get("watchlist", []),
            "risk_profile": p.get("risk_profile", {}),
        }
