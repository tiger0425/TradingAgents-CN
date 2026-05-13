import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class UserDashboard:
    def __init__(self, portfolio_mgr, kb, archive, cost_tracker=None,
                 template_evolver=None, base_dir="~/.tradingagents"):
        self.portfolio_mgr = portfolio_mgr
        self.kb = kb
        self.archive = archive
        self.cost_tracker = cost_tracker
        self.template_evolver = template_evolver
        self.base_dir = Path(base_dir).expanduser()

    def export_data(self, user_id: str = "default") -> dict:
        portfolio = self.portfolio_mgr.load(user_id)
        data = {
            "updated_at": datetime.now().isoformat(),
            "user_id": user_id,
            "portfolio": {
                "holdings": portfolio.get("holdings", []),
                "watchlist": portfolio.get("watchlist", []),
                "risk_profile": portfolio.get("risk_profile", {}),
            },
            "kb_status": self.kb.get_freshness_summary() if self.kb else {},
            "recent_briefings": self.archive.list_recent(user_id, limit=20) if self.archive else [],
            "template_health": (
                self.template_evolver.get_stats(user_id)
                if self.template_evolver else []
            ),
        }
        if self.cost_tracker:
            data["costs"] = self.cost_tracker.get_monthly(user_id)

        export_path = self.base_dir / "users" / user_id / "dashboard_data.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("Dashboard data exported for user %s", user_id)
        return data

    def render_html(self, user_id: str = "default") -> str:
        data = self.export_data(user_id)
        p = data["portfolio"]
        kb = data.get("kb_status", {})
        costs = data.get("costs", {})
        templates = data.get("template_health", [])

        holdings_rows = "".join(
            f"<tr><td>{h.get('ticker','')}</td><td>{h.get('name','')}</td>"
            f"<td>{h.get('cost_price',0)}</td><td>{h.get('quantity',0)}</td></tr>"
            for h in p.get("holdings", [])
        )
        watchlist_rows = "".join(
            f"<tr><td>{w.get('ticker','')}</td><td>{w.get('name','')}</td><td>{w.get('reason','')}</td></tr>"
            for w in p.get("watchlist", [])
        )
        template_rows = "".join(
            f"<tr><td>{t.get('template_id','')}</td><td>{t.get('description','')}</td>"
            f"<td>{t.get('use_count',0)}</td><td>{t.get('success_rate',0)*100:.0f}%</td>"
            f"<td>{t.get('status','')}</td></tr>"
            for t in templates[:5]
        )
        kb_rows = "".join(
            f"<tr><td>{name}</td><td>{info.get('freshness','?')}</td><td>{info.get('count',0)}条</td></tr>"
            for name, info in kb.items()
        )

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>华创量化研究院</title>
<style>
body{{font-family:system-ui;max-width:1000px;margin:auto;padding:20px;background:#f5f5f5}}
.card{{background:#fff;border-radius:12px;padding:20px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
h2{{margin-top:0;color:#1a1a2e}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#f8f9fa;font-weight:600}}
.verified{{color:#22c55e}}.unverified{{color:#f59e0b}}.deprecated{{color:#ef4444}}
.fresh{{color:#22c55e}}.stale{{color:#f59e0b}}.expired{{color:#ef4444}}
</style></head><body>
<h1>华创量化研究院</h1>
<p>用户: {user_id} | 更新: {data['updated_at']}</p>
<div class="card"><h2>持仓概览</h2>
<table><tr><th>代码</th><th>名称</th><th>成本</th><th>数量</th></tr>{holdings_rows}</table></div>
<div class="card"><h2>自选股</h2>
<table><tr><th>代码</th><th>名称</th><th>理由</th></tr>{watchlist_rows}</table></div>
<div class="card"><h2>知识库状态</h2>
<table><tr><th>类型</th><th>新鲜度</th><th>数量</th></tr>{kb_rows}</table></div>
<div class="card"><h2>模板健康度</h2>
<table><tr><th>模板ID</th><th>描述</th><th>使用次数</th><th>准确率</th><th>状态</th></tr>{template_rows}</table></div>
{f'<div class="card"><h2>本月成本: ¥{costs.get("total",0):.2f}</h2><p>采集层: ¥{costs.get("collector",0):.2f} | 事件层: ¥{costs.get("event",0):.2f}</p></div>' if costs else ''}
</body></html>"""
