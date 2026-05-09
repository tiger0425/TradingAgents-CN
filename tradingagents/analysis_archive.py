"""Analysis result archiving system for TradingAgents.

Persists CLI analysis results (morning-scan, evening-review, batch,
scan-watchlist output) into a structured file-system archive with
index-based search.

Archive layout:
    ~/.tradingagents/analysis-archive/
    ├── index.json                     # Root index (all entries)
    ├── 2026/
    │   ├── 05/
    │   │   ├── index.json             # Month-level index
    │   │   ├── 09/
    │   │   │   ├── index.json         # Day-level index
    │   │   │   ├── morning-scan_600519.json
    │   │   │   └── ...

Config key (for default_config.py):
    "analysis_archive_dir": os.path.join(_TRADINGAGENTS_HOME, "analysis-archive")
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class AnalysisArchive:
    """Persistent archive of CLI analysis results with index-based lookup.

    Stores structured analysis JSON files in a year/month/day directory
    hierarchy, maintaining index.json files at each level for fast
    filtered queries.  All writes are atomic (tmp + os.replace).
    """

    _INDEX_VERSION = 1

    def __init__(self, archive_dir: str | Path | dict | None = None):
        """Initialise the archive.

        Args:
            archive_dir: One of:
                - ``None`` → default ``~/.tradingagents/analysis-archive/``
                - ``str`` / ``Path`` → explicit directory path
                - ``dict``  → config dict; reads key ``"analysis_archive_dir"``,
                  falling back to the default above.
        """
        if archive_dir is None:
            self.archive_dir = Path(
                os.path.expanduser("~/.tradingagents/analysis-archive/")
            )
        elif isinstance(archive_dir, dict):
            path = archive_dir.get("analysis_archive_dir")
            if path:
                self.archive_dir = Path(path).expanduser()
            else:
                self.archive_dir = Path(
                    os.path.expanduser("~/.tradingagents/analysis-archive/")
                )
        else:
            self.archive_dir = Path(archive_dir).expanduser()

        self.archive_dir.mkdir(parents=True, exist_ok=True)

    # ==================================================================
    # Entry ID helpers
    # ==================================================================

    def _entry_path(self, entry_id: str) -> Path:
        """Map an entry ID to its on-disk file path.

        ``2026/05/09/morning-scan_600519`` →
        ``{archive_dir}/2026/05/09/morning-scan_600519.json``
        """
        return self.archive_dir / f"{entry_id}.json"

    @staticmethod
    def _date_from_id(entry_id: str) -> str:
        """Extract date string from an entry ID.

        ``2026/05/09/morning-scan_600519`` → ``2026-05-09``
        """
        parts = entry_id.split("/")
        if len(parts) >= 3:
            return f"{parts[0]}-{parts[1]}-{parts[2]}"
        return ""

    @staticmethod
    def _build_entry_id(date_str: str, entry_type: str, ticker: str) -> str:
        """Build an entry ID from its components.

        ``2026-05-09``, ``morning-scan``, ``600519`` →
        ``2026/05/09/morning-scan_600519``
        """
        normalized = date_str.replace("-", "/")
        return f"{normalized}/{entry_type}_{ticker}"

    # ==================================================================
    # Atomic write
    # ==================================================================

    def _atomic_write(self, path: Path, data: dict) -> None:
        """Write *data* to *path* atomically via tmp + os.replace()."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    # ==================================================================
    # Index file helpers
    # ==================================================================

    @staticmethod
    def _empty_index() -> dict:
        """Return a fresh, empty index dict."""
        return {
            "version": AnalysisArchive._INDEX_VERSION,
            "updated_at": "",
            "total_entries": 0,
            "by_ticker": {},
            "by_decision": {},
            "entries": [],
        }

    def _load_index(self, path: Path) -> dict:
        """Load an index.json file from *path*, returning a valid index
        dict even when the file is missing or corrupted."""
        if not path.exists():
            return self._empty_index()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return self._empty_index()

        data.setdefault("version", self._INDEX_VERSION)
        data.setdefault("total_entries", len(data.get("entries", [])))
        data.setdefault("by_ticker", {})
        data.setdefault("by_decision", {})
        data.setdefault("entries", [])
        return data

    def _save_index(self, path: Path, index: dict) -> None:
        """Atomically write an index dict to *path*."""
        self._atomic_write(path, index)

    def _rebuild_lookups(self, index: dict) -> dict:
        """Rebuild the ``by_ticker`` and ``by_decision`` lookup maps
        from the current ``entries`` list, and refresh metadata."""
        by_ticker: Dict[str, List[str]] = {}
        by_decision: Dict[str, List[str]] = {}

        for entry in index["entries"]:
            ticker = entry.get("ticker", "")
            if ticker:
                by_ticker.setdefault(ticker, []).append(entry["id"])

            decision = entry.get("decision", "").lower()
            if decision:
                by_decision.setdefault(decision, []).append(entry["id"])

        index["by_ticker"] = by_ticker
        index["by_decision"] = by_decision
        index["total_entries"] = len(index["entries"])
        index["updated_at"] = datetime.now().isoformat()
        return index

    def _index_paths_for_entry(self, date_str: str) -> tuple:
        """Return the three index paths (root, month, day) for *date_str*."""
        parts = date_str.split("-")
        if len(parts) != 3:
            # Best-effort: only return root
            return (
                self.archive_dir / "index.json",
                self.archive_dir / "index.json",
                self.archive_dir / "index.json",
            )
        year, month, day = parts
        root = self.archive_dir / "index.json"
        month_idx = self.archive_dir / year / month / "index.json"
        day_idx = self.archive_dir / year / month / day / "index.json"
        return root, month_idx, day_idx

    # ==================================================================
    # Entry metadata extraction
    # ==================================================================

    @staticmethod
    def _extract_meta(entry_id: str, data: dict) -> dict:
        """Build index-entry metadata from a full analysis dict."""
        request = data.get("request", {})
        analysis = data.get("analysis", {})
        meta_section = data.get("_meta", {})
        return {
            "id": entry_id,
            "date": request.get("date")
            or AnalysisArchive._date_from_id(entry_id),
            "type": meta_section.get("source_command", ""),
            "ticker": request.get("ticker", ""),
            "decision": analysis.get("final_decision", ""),
            "rating": analysis.get("rating", ""),
            "analysts": request.get("analysts", []),
            "tags": data.get("tags", []),
        }

    # ==================================================================
    # Index update (incremental)
    # ==================================================================

    def _update_index(
        self, entry_meta: dict, action: str = "add"
    ) -> None:
        """Incrementally update all three index levels after a save or delete.

        Args:
            entry_meta: Metadata dict for the entry.
            action: ``"add"`` (insert / update) or ``"remove"`` (delete).
        """
        date_str = entry_meta["date"]
        root_path, month_path, day_path = self._index_paths_for_entry(date_str)

        for idx_path in (root_path, month_path, day_path):
            idx = self._load_index(idx_path)
            entries: List[dict] = idx["entries"]

            if action == "add":
                replaced = False
                for i, e in enumerate(entries):
                    if e.get("id") == entry_meta["id"]:
                        entries[i] = entry_meta
                        replaced = True
                        break
                if not replaced:
                    entries.append(entry_meta)
            elif action == "remove":
                entries[:] = [
                    e for e in entries if e.get("id") != entry_meta["id"]
                ]

            idx = self._rebuild_lookups(idx)
            self._save_index(idx_path, idx)

    # ==================================================================
    # Rebuild (full from scratch)
    # ==================================================================

    def _build_index(self) -> int:
        """Walk the entire archive tree, read every entry JSON, and
        rebuild all index.json files from scratch.

        Returns:
            Total number of entries indexed.
        """
        # Remove existing index files so rebuild is truly fresh
        for idx_path in self.archive_dir.rglob("index.json"):
            try:
                idx_path.unlink()
            except OSError:
                pass

        all_entries: List[dict] = []
        for json_file in sorted(self.archive_dir.rglob("*.json")):
            if json_file.name == "index.json":
                continue

            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                continue

            entry_id = data.get("_meta", {}).get("id", "")
            if not entry_id:
                # Derive from relative path
                try:
                    rel = json_file.relative_to(self.archive_dir)
                    entry_id = str(rel.with_suffix(""))
                except ValueError:
                    continue

            meta = self._extract_meta(entry_id, data)
            if meta["date"]:
                all_entries.append(meta)

        if not all_entries:
            return 0

        # --- Root index ---
        root_idx = self._empty_index()
        root_idx["entries"] = list(all_entries)
        root_idx = self._rebuild_lookups(root_idx)
        self._save_index(self.archive_dir / "index.json", root_idx)

        # --- Group by month and day ---
        by_month: Dict[str, List[dict]] = {}
        by_day: Dict[str, List[dict]] = {}

        for entry in all_entries:
            date = entry["date"]
            parts = date.split("-")
            if len(parts) != 3:
                continue
            year, month, day = parts
            month_key = f"{year}/{month}"
            day_key = f"{year}/{month}/{day}"
            by_month.setdefault(month_key, []).append(entry)
            by_day.setdefault(day_key, []).append(entry)

        # --- Month indexes ---
        for month_key, entries in by_month.items():
            idx_path = self.archive_dir / month_key / "index.json"
            idx_path.parent.mkdir(parents=True, exist_ok=True)
            idx = self._empty_index()
            idx["entries"] = list(entries)
            idx = self._rebuild_lookups(idx)
            self._save_index(idx_path, idx)

        # --- Day indexes ---
        for day_key, entries in by_day.items():
            idx_path = self.archive_dir / day_key / "index.json"
            idx_path.parent.mkdir(parents=True, exist_ok=True)
            idx = self._empty_index()
            idx["entries"] = list(entries)
            idx = self._rebuild_lookups(idx)
            self._save_index(idx_path, idx)

        return len(all_entries)

    def rebuild_index(self) -> int:
        """Rebuild all index.json files from entry JSON files on disk.

        Public alias for ``_build_index()``.
        """
        return self._build_index()

    # ==================================================================
    # Public API
    # ==================================================================

    def save(self, result: dict, entry_type: str) -> str:
        """Persist an analysis result dict and return its entry ID.

        The entry ID is derived from ``result["request"]["date"]`` (or
        today), ``entry_type`` (e.g. ``"morning-scan"``), and
        ``result["request"]["ticker"]``.

        Updates all three index levels (root, month, day).
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        request = result.get("request", {})
        ticker = request.get("ticker", "unknown")
        date_str = request.get("date") or today_str

        # Ensure _meta section
        meta = result.setdefault("_meta", {})
        entry_id = self._build_entry_id(date_str, entry_type, ticker)
        meta["id"] = entry_id
        meta.setdefault("archived_at", now.isoformat())
        meta.setdefault("source_command", entry_type)
        meta.setdefault("cli_version", "0.2.5")

        # Write entry file
        entry_path = self._entry_path(entry_id)
        self._atomic_write(entry_path, result)

        # Build index metadata and update indexes
        entry_meta = self._extract_meta(entry_id, result)
        self._update_index(entry_meta, action="add")

        return entry_id

    def get(self, entry_id: str) -> Optional[dict]:
        """Load a full analysis entry by its entry ID.

        Returns ``None`` when the entry does not exist.
        """
        entry_path = self._entry_path(entry_id)
        if not entry_path.exists():
            return None
        try:
            return json.loads(entry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return None

    def list(
        self,
        ticker: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        decision: Optional[str] = None,
        entry_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        """Query entries from the root index with optional filters.

        Returns a list of entry metadata dicts (not full content),
        sorted by date descending.

        Args:
            ticker:      Filter by stock ticker.
            date_from:   Include entries on or after this date (ISO).
            date_to:     Include entries on or before this date (ISO).
            decision:    Match ``final_decision`` (case-insensitive).
            entry_type:  Match source command type.
            limit:       Maximum results to return (default 20).
        """
        root_idx = self._load_index(self.archive_dir / "index.json")
        entries: List[dict] = root_idx["entries"]

        if ticker:
            entries = [e for e in entries if e.get("ticker") == ticker]
        if date_from:
            entries = [e for e in entries if e.get("date", "") >= date_from]
        if date_to:
            entries = [e for e in entries if e.get("date", "") <= date_to]
        if decision:
            dec_lower = decision.lower()
            entries = [
                e
                for e in entries
                if e.get("decision", "").lower() == dec_lower
            ]
        if entry_type:
            entries = [
                e for e in entries if e.get("type") == entry_type
            ]

        # Sort by date descending
        entries.sort(key=lambda e: e.get("date", ""), reverse=True)
        return entries[:limit]

    def search(self, query: str, limit: int = 20) -> List[dict]:
        """Full-text search across archived entry files.

        Searches all string fields of every entry JSON by loading each
        file and performing case-insensitive substring matching.

        Args:
            query: Substring to search for.
            limit: Maximum results to return (default 20).

        Returns:
            List of matching entry metadata dicts.
        """
        root_idx = self._load_index(self.archive_dir / "index.json")
        query_lower = query.lower()
        results: List[dict] = []

        for entry_meta in root_idx["entries"]:
            if len(results) >= limit:
                break
            try:
                entry_path = self._entry_path(entry_meta["id"])
                if not entry_path.exists():
                    continue
                data = json.loads(entry_path.read_text(encoding="utf-8"))
                # Search in the serialised JSON text
                text = json.dumps(data, ensure_ascii=False).lower()
                if query_lower in text:
                    results.append(entry_meta)
            except (json.JSONDecodeError, ValueError, OSError):
                continue

        return results[:limit]

    def summary(self, ticker: str, days: int = 90) -> dict:
        """Produce a signal distribution summary for *ticker* over the
        last *days* calendar days.

        Returns a dict with keys:
            - ticker
            - period_days
            - total_entries
            - by_decision  (dict: decision → count)
            - by_type      (dict: entry_type → count)
            - trend        (list of {date, decision, rating} chronologically)
        """
        root_idx = self._load_index(self.archive_dir / "index.json")
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )

        ticker_entries = [
            e
            for e in root_idx["entries"]
            if e.get("ticker") == ticker and e.get("date", "") >= cutoff_date
        ]

        by_decision: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        trend: List[dict] = []

        sorted_entries = sorted(ticker_entries, key=lambda e: e.get("date", ""))
        for e in sorted_entries:
            d = e.get("decision", "unknown").lower()
            by_decision[d] = by_decision.get(d, 0) + 1

            t = e.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

            trend.append({
                "date": e.get("date", ""),
                "decision": e.get("decision", ""),
                "rating": e.get("rating", ""),
            })

        return {
            "ticker": ticker,
            "period_days": days,
            "total_entries": len(ticker_entries),
            "by_decision": by_decision,
            "by_type": by_type,
            "trend": trend,
        }

    def delete(self, entry_id: str) -> bool:
        """Remove an entry and update all indexes.

        Returns:
            ``True`` if the entry existed and was removed, ``False``
            otherwise.
        """
        entry_path = self._entry_path(entry_id)
        if not entry_path.exists():
            return False

        # Read metadata before deleting so we can update indexes
        try:
            data = json.loads(entry_path.read_text(encoding="utf-8"))
            entry_meta = self._extract_meta(entry_id, data)
        except (json.JSONDecodeError, ValueError):
            # Minimal meta from entry_id alone
            entry_meta = {
                "id": entry_id,
                "date": self._date_from_id(entry_id),
                "type": "",
                "ticker": "",
                "decision": "",
                "rating": "",
                "analysts": [],
                "tags": [],
            }

        try:
            entry_path.unlink()
        except OSError:
            pass

        self._update_index(entry_meta, action="remove")

        return True
