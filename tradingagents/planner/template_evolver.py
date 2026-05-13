import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TemplateEvolver:
    def __init__(self, templates_dir: str = "~/.tradingagents/templates"):
        self.templates_dir = Path(templates_dir).expanduser()
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def after_execution(self, plan, template_used: Optional[Dict] = None):
        generation_mode = plan.get("_generation_mode", "llm_full")
        template_id = plan.get("_template_id", "")

        if generation_mode == "template_exact" and template_id:
            self._increment_use_count(template_id)

        elif generation_mode == "template_refined" and template_used:
            self._consider_update(template_used, plan.get("workflow", []))

        elif generation_mode == "llm_full":
            self._save_as_new(plan)

    def _increment_use_count(self, template_id: str):
        path = self.templates_dir / f"{template_id}.json"
        if not path.exists():
            return
        tpl = json.loads(path.read_text())
        tpl["use_count"] = tpl.get("use_count", 0) + 1
        tpl["last_used"] = datetime.now().isoformat()
        path.write_text(json.dumps(tpl, ensure_ascii=False, indent=2))

    def _consider_update(self, original: Dict, refined_workflow: list):
        orig_workflow = original.get("workflow", [])
        diff_ratio = self._calc_diff(orig_workflow, refined_workflow)

        if diff_ratio < 0.2:
            return
        elif diff_ratio < 0.5:
            new_tpl = deepcopy(original)
            new_tpl["version"] = original.get("version", 1) + 1
            new_tpl["workflow"] = refined_workflow
            self._save(new_tpl)
            logger.info("Template updated: %s v%d", original.get("template_id"), new_tpl["version"])
        else:
            self._save_as_new({
                "workflow": refined_workflow,
                "match_patterns": {
                    **original.get("match_patterns", {}),
                    "derived_from": original.get("template_id", ""),
                },
                "_generation_mode": "llm_full",
            })

    def _save_as_new(self, plan: Dict):
        template_id = f"tpl_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tpl = {
            "template_id": template_id,
            "version": 1,
            "status": "unverified",
            "created": datetime.now().isoformat(),
            "use_count": 0,
            "success_rate": 0.5,
            "match_patterns": plan.get("match_patterns", {}),
            "workflow": plan.get("workflow", []),
            "estimated_cost_usd": plan.get("estimated_cost_usd", 1.0),
            "estimated_time_seconds": plan.get("estimated_time_seconds", 300),
        }
        self._save(tpl)
        logger.info("New template saved: %s (unverified)", template_id)

    def _save(self, tpl: Dict):
        path = self.templates_dir / f"{tpl['template_id']}.json"
        path.write_text(json.dumps(tpl, ensure_ascii=False, indent=2))

    def periodic_review(self):
        now = datetime.now()
        for f in self.templates_dir.glob("tpl_*.json"):
            tpl = json.loads(f.read_text())
            created = datetime.fromisoformat(tpl.get("created", "2000-01-01"))
            use_count = tpl.get("use_count", 0)
            success_rate = tpl.get("success_rate", 0.5)

            if use_count == 0 and (now - created).days > 30:
                tpl["status"] = "deprecated"
            elif use_count >= 10 and success_rate >= 0.8:
                tpl["status"] = "verified"
            elif use_count >= 10 and success_rate < 0.3:
                tpl["status"] = "deprecated"

            f.write_text(json.dumps(tpl, ensure_ascii=False, indent=2))

    def get_stats(self, user_id: str = "default") -> list:
        stats = []
        for f in self.templates_dir.glob("tpl_*.json"):
            tpl = json.loads(f.read_text())
            stats.append({
                "template_id": tpl["template_id"],
                "description": tpl.get("match_patterns", {}).get("description", ""),
                "use_count": tpl.get("use_count", 0),
                "success_rate": tpl.get("success_rate", 0.5),
                "status": tpl.get("status", "unverified"),
                "last_used": tpl.get("last_used", ""),
            })
        return sorted(stats, key=lambda s: s["use_count"], reverse=True)

    @staticmethod
    def _calc_diff(orig: list, refined: list) -> float:
        if not orig:
            return 1.0
        orig_agents = {s.get("agent") for s in orig if s.get("agent")}
        refined_agents = {s.get("agent") for s in refined if s.get("agent")}
        if not orig_agents:
            return 1.0
        common = orig_agents & refined_agents
        new_agents = refined_agents - orig_agents
        removed = orig_agents - refined_agents
        return (len(new_agents) + len(removed)) / len(orig_agents)
