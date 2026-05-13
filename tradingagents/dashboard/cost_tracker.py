import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    timestamp TEXT NOT NULL,
    agent TEXT,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    category TEXT DEFAULT 'event'
);
CREATE INDEX IF NOT EXISTS idx_costs_user ON costs(user_id);
CREATE INDEX IF NOT EXISTS idx_costs_month ON costs(user_id, substr(timestamp,1,7));
"""


class CostTracker:
    def __init__(self, db_path: str = "~/.tradingagents/costs.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def record(self, user_id: str, agent: str, model: str,
               input_tokens: int, output_tokens: int, cost_usd: float,
               category: str = "event"):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO costs (user_id, timestamp, agent, model, input_tokens, output_tokens, cost_usd, category) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, datetime.now().isoformat(), agent, model, input_tokens, output_tokens, cost_usd, category)
            )
            conn.commit()

    def get_monthly(self, user_id: str = "default") -> dict:
        month = datetime.now().strftime("%Y-%m")
        with sqlite3.connect(str(self.db_path)) as conn:
            collector = conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) FROM costs WHERE user_id=? AND substr(timestamp,1,7)=? AND category='collector'",
                (user_id, month)
            ).fetchone()[0]
            event = conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) FROM costs WHERE user_id=? AND substr(timestamp,1,7)=? AND category='event'",
                (user_id, month)
            ).fetchone()[0]
        return {"collector": round(collector, 4), "event": round(event, 4), "total": round(collector + event, 4)}

    def get_daily(self, user_id: str = "default", days: int = 30) -> list:
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT substr(timestamp,1,10) as day, category, SUM(cost_usd) FROM costs WHERE user_id=? GROUP BY day, category ORDER BY day DESC LIMIT ?",
                (user_id, days * 2)
            ).fetchall()
        return [{"day": r[0], "category": r[1], "cost": round(r[2], 4)} for r in rows]
