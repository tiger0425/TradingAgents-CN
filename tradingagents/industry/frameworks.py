"""Industry framework lookup — maps Chinese industry descriptions to evaluation frameworks.

Usage:
    fw = IndustryFramework()
    framework = fw.lookup("汽车制造")   # -> automotive framework dict
    framework = fw.lookup("白酒")       # -> consumer framework dict
    framework = fw.lookup("不存在的")   # -> None
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_FRAMEWORKS_FILE = _CONFIG_DIR / "industry_frameworks.json"


FrameworkDict = dict[str, Any]


class IndustryFramework:
    """Loads industry frameworks from JSON and provides fuzzy-name lookup."""

    def __init__(self, frameworks_path: str | Path | None = None) -> None:
        self._frameworks_path: Path = Path(frameworks_path) if frameworks_path else _FRAMEWORKS_FILE
        self._frameworks: dict[str, FrameworkDict] = {}
        self._load()

    # ── public API ──────────────────────────────────────────────────────

    def lookup(self, industry_name: str) -> FrameworkDict | None:
        """Fuzzy-match an industry string against known frameworks.

        Returns the full framework dict (including *correct_metrics*,
        *anti_patterns*, *peer_companies*, *context_instruction*) or
        ``None`` when no framework matches.
        """
        if not industry_name:
            return None

        name = industry_name.strip()

        # 1. Exact keyword match (fast path)
        for key, fw in self._frameworks.items():
            if name in fw.get("keywords", []):
                return fw

        # 2. Substring match — keyword is contained in the input
        #    e.g. "商用载货车龙头" contains "商用车" / "汽车" / "商用载货车"
        matched = []
        for key, fw in self._frameworks.items():
            for kw in fw.get("keywords", []):
                if kw and kw in name:
                    matched.append((len(kw), key, fw))

        # 3. Substring match — input is contained in a keyword
        #    e.g. "汽车" is contained in "新能源汽车" / "汽车零部件"
        if not matched:
            for key, fw in self._frameworks.items():
                for kw in fw.get("keywords", []):
                    if kw and name in kw:
                        matched.append((len(kw), key, fw))

        if matched:
            # Pick the framework with the longest keyword match (most specific)
            matched.sort(key=lambda t: -t[0])
            return matched[0][2]

        # 4. Partial token match — split input on common delimiters
        tokens = [t for sep in " /-–—,、;；" for part in [name.split(sep)] for t in part]
        if len(tokens) > 1:
            for token in tokens:
                token = token.strip()
                if not token:
                    continue
                for key, fw in self._frameworks.items():
                    if token in fw.get("keywords", []):
                        return fw
                    for kw in fw.get("keywords", []):
                        if kw and (kw in token or token in kw):
                            return fw

        return None

    def list_frameworks(self) -> list[FrameworkDict]:
        """Return all registered frameworks (sorted by key)."""
        return [self._frameworks[k] for k in sorted(self._frameworks)]

    # ── internals ───────────────────────────────────────────────────────

    def _load(self) -> None:
        path = self._frameworks_path
        if not path.exists():
            logger.warning("Industry frameworks file not found: %s", path)
            self._frameworks = {}
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw: Any = json.load(f)
            if not isinstance(raw, dict):
                raise TypeError("Expected JSON object at top level")
            self._frameworks = raw
            logger.info("Loaded %d industry frameworks from %s", len(raw), path)
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.error("Failed to load industry frameworks from %s: %s", path, exc)
            self._frameworks = {}
