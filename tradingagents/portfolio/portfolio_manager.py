import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_PORTFOLIO = {
    "holdings": [],
    "watchlist": [],
    "risk_profile": {
        "max_single_stock_pct": 20,
        "max_drawdown_tolerance": -15,
        "holding_period": "2-4周",
    },
}


class PortfolioManager:
    def __init__(self, base_dir: str = "~/.tradingagents"):
        self.base_dir = Path(base_dir).expanduser()

    def _portfolio_path(self, user_id: str) -> Path:
        return self.base_dir / "users" / user_id / "portfolio" / "portfolio.yaml"

    def load(self, user_id: str = "default") -> Dict[str, Any]:
        path = self._portfolio_path(user_id)
        if not path.exists():
            return DEFAULT_PORTFOLIO
        with open(path) as f:
            return yaml.safe_load(f) or DEFAULT_PORTFOLIO

    def save(self, data: Dict[str, Any], user_id: str = "default"):
        path = self._portfolio_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def add_holding(self, ticker: str, name: str, cost_price: float,
                    quantity: int, entry_date: str, user_id: str = "default",
                    notes: str = ""):
        portfolio = self.load(user_id)
        existing = [h for h in portfolio.get("holdings", []) if h.get("ticker") == ticker]
        if existing:
            existing[0].update({
                "cost_price": cost_price, "quantity": quantity,
                "entry_date": entry_date, "notes": notes,
            })
        else:
            portfolio.setdefault("holdings", []).append({
                "ticker": ticker, "name": name, "cost_price": cost_price,
                "quantity": quantity, "entry_date": entry_date, "notes": notes,
            })
        self.save(portfolio, user_id)
        logger.info("Holding %s: %s (%s股 @ %.2f)", "updated" if existing else "added", ticker, quantity, cost_price)

    def remove_holding(self, ticker: str, user_id: str = "default"):
        portfolio = self.load(user_id)
        portfolio["holdings"] = [h for h in portfolio.get("holdings", []) if h.get("ticker") != ticker]
        self.save(portfolio, user_id)

    def add_to_watchlist(self, ticker: str, name: str, reason: str = "",
                         user_id: str = "default"):
        portfolio = self.load(user_id)
        existing = [w for w in portfolio.get("watchlist", []) if w.get("ticker") == ticker]
        if not existing:
            portfolio.setdefault("watchlist", []).append({
                "ticker": ticker, "name": name, "added_date": "",
                "reason": reason,
            })
        self.save(portfolio, user_id)

    def summary_for_planner(self, user_id: str = "default") -> str:
        portfolio = self.load(user_id)
        lines = []
        for h in portfolio.get("holdings", []):
            lines.append(f"{h['ticker']} {h.get('name','')}: 成本{h.get('cost_price',0)}/{h.get('quantity',0)}股")
        for w in portfolio.get("watchlist", []):
            lines.append(f"[自选] {w['ticker']} {w.get('name','')}: {w.get('reason','')}")
        return "\n".join(lines) if lines else "无持仓"

    def alerts_for_briefing(self, user_id: str = "default") -> List[Dict]:
        return []

    def get_holdings_list(self, user_id: str = "default") -> list:
        return self.load(user_id).get("holdings", [])

    def get_watchlist(self, user_id: str = "default") -> list:
        return self.load(user_id).get("watchlist", [])
