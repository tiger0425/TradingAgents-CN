import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

USER_DATA_DIRS = [
    "portfolio",
    "analysis-archive",
    "memory",
    "templates",
]


class UserManager:
    def __init__(self, base_dir: str = "~/.tradingagents"):
        self.base_dir = Path(base_dir).expanduser()
        self.users_dir = self.base_dir / "users"

    def ensure_user_dir(self, user_id: str):
        user_dir = self.users_dir / user_id
        for sub in USER_DATA_DIRS:
            (user_dir / sub).mkdir(parents=True, exist_ok=True)
        return user_dir

    def get_active_users(self) -> List[str]:
        if not self.users_dir.exists():
            return ["default"]
        users = [d.name for d in self.users_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
        return users if users else ["default"]

    def user_exists(self, user_id: str) -> bool:
        return (self.users_dir / user_id).exists()

    def register_user(self, user_id: str) -> Path:
        return self.ensure_user_dir(user_id)
