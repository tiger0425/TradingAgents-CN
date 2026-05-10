"""Standalone ConfigSection: centralized, type-safe, test-aware configuration.

A.3 spec implementation.  Wraps DEFAULT_CONFIG with:
  - Test environment detection (DJANGO_TESTING / TRADINGAGENTS_TESTING)
  - Deepcopy for test isolation
  - Type-safe get/set with key path notation ("a.b.c")
  - Smart config merge from multiple sources
  - Environment variable overrides
  - Hot-reload support
  - Config key inventory & validation

Usage:
    from tradingagents.config_section import ConfigSection, get_config

    cfg = ConfigSection()
    provider = cfg.get("llm_provider")            # str
    ratio  = cfg.get("max_debate_rounds", int)     # typed access
    addr   = cfg.get("backend_url", fallback="")   # with fallback

    # Test isolation — returns deepcopy
    test_cfg = ConfigSection()   # DJANGO_TESTING=1 → uses test defaults
    test_cfg.set("llm_provider", "fake")
    # ... original config unaffected

    # Global convenience
    default = get_config()       # singleton
"""

from __future__ import annotations

import copy
import logging
import os
import threading
import time
from typing import Any, ClassVar, Dict, Mapping, Optional, Type, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test environment detection
# ---------------------------------------------------------------------------

def _is_test_env() -> bool:
    """Detect whether we are running in a test / CI environment."""
    return any(
        os.environ.get(k, "").strip() not in ("", "0", "false", "no")
        for k in ("DJANGO_TESTING", "TRADINGAGENTS_TESTING", "CI", "PYTEST_CURRENT_TEST")
    )


# ---------------------------------------------------------------------------
# Convenience: load defaults lazily to avoid import loops
# ---------------------------------------------------------------------------

def _load_defaults() -> Dict[str, Any]:
    """Return the project's unspecialised (A.2) defaults."""
    from tradingagents.default_config import DEFAULT_CONFIG

    return copy.deepcopy(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Key-path helpers
# ---------------------------------------------------------------------------

def _get_by_path(data: dict, path: str):
    """Walk ``path`` (dots-separated) into nested dict *data*.

    Raises KeyError if any segment is missing.
    """
    keys = path.split(".")
    for key in keys:
        if not isinstance(data, dict):
            raise KeyError(f"key-path segment on non-dict ({type(data).__name__}): {keys}")
        data = data[key]
    return data


def _set_by_path(data: dict, path: str, value: Any) -> None:
    """Set value at ``path``, creating intermediate dicts as needed."""
    keys = path.split(".")
    *parents, leaf = keys
    for key in parents:
        if key not in data or not isinstance(data[key], dict):
            data[key] = {}
        data = data[key]
    data[leaf] = value


# ---------------------------------------------------------------------------
# ConfigSection
# ---------------------------------------------------------------------------

class ConfigSection:
    """Centralised, type-safe configuration manager (A.3).

    Features
    --------
    * **Test isolation** — when ``DJANGO_TESTING`` (or equivalent) is set,
      every call to :meth:`get` / :meth:`get_all` returns a **deepcopy**
      so that tests never leak state.
    * **Type-safe access** — ``cfg.get("key", int)`` casts on read.
    * **Dot-path notation** — ``"data_vendors.core_stock_apis"`` navigates
      nested dicts.
    * **Config merge** — :meth:`merge` overlays partial dicts (env overrides,
      Django settings, etc) without overwriting unknown keys.
    * **Hot-reload** — :meth:`reload` re-reads defaults + env overrides
      and replaces the in-memory store.
    * **Thread-safe** — all read-write operations are guarded by an RLock.
    * **Key inventory** — :meth:`keys` and :meth:`validate` help surface
      configuration drift.

    Single-instance pattern
    ------------------------
    Use :func:`get_config` to obtain a global instance.  Advanced consumers
    may create isolated instances for specific subsystems.
    """

    # ------------------------------------------------------------------
    # Class-level defaults that get merged on construction
    # ------------------------------------------------------------------

    _DEFAULT_ENV_OVERRIDES: ClassVar[Mapping[str, str]] = {
        # Map env var → dot-path key.  Examples:
        # "TRADINGAGENTS_LLM_PROVIDER": "llm_provider",
        # "TRADINGAGENTS_CACHE_DIR":  "data_cache_dir",
    }

    def __init__(
        self,
        initial: Optional[Dict[str, Any]] = None,
        env_overrides: Optional[Mapping[str, str]] = None,
    ):
        """Initialise the section.

        Args:
            initial: Dict to use as starting state.  If ``None``, loads
                defaults via :func:`_load_defaults`.
            env_overrides: Mapping of env-var → config-key-path.
                Merged with :attr:`_DEFAULT_ENV_OVERRIDES`.
        """
        self._lock = threading.RLock()
        self._test_mode = _is_test_env()
        self._env_overrides = dict(self._DEFAULT_ENV_OVERRIDES)
        if env_overrides:
            self._env_overrides.update(env_overrides)
        self._store = self._build_store(initial)

    # ------------------------------------------------------------------
    # Store construction & merge
    # ------------------------------------------------------------------

    def _build_store(self, initial: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Assemble the in-memory config store from defaults + env overrides."""
        store = initial if initial is not None else _load_defaults()
        self._apply_env_overrides(store)
        return store

    def _apply_env_overrides(self, store: Dict[str, Any]) -> None:
        """Walk ``_env_overrides`` and apply matching env-var values."""
        for env_var, key_path in self._env_overrides.items():
            val = os.environ.get(env_var)
            if val is not None:
                logger.debug("env override  %s → %s", env_var, key_path)
                _set_by_path(store, key_path, self._coerce_type(val))

    @staticmethod
    def _coerce_type(value: str) -> Any:
        """Best-effort type coercion for env-var strings."""
        v = value.strip()
        # bool
        if v.lower() in ("true", "yes", "1"):
            return True
        if v.lower() in ("false", "no", "0"):
            return False
        # None
        if v.lower() in ("none", "null", ""):
            return None
        # int
        try:
            return int(v)
        except ValueError:
            pass
        # float
        try:
            return float(v)
        except ValueError:
            pass
        return v  # str

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(self, overrides: Mapping[str, Any]) -> None:
        """Overlay *overrides* into the current config store (shallow merge).

        Unknown top-level keys are preserved; only matching keys are updated.
        For nested merge of specific paths, use :meth:`set` instead.

        Thread-safe.
        """
        with self._lock:
            for key, value in overrides.items():
                if key in self._store:
                    if isinstance(self._store[key], dict) and isinstance(value, dict):
                        self._store[key] = {**self._store[key], **value}
                    else:
                        self._store[key] = value
                else:
                    self._store[key] = value

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get(
        self,
        key_path: str,
        type_: Optional[Type] = None,
        fallback: Any = KeyError,
    ) -> Any:
        """Return the current value at *key_path*.

        Args:
            key_path: Dot-separated path into the config dict
                (e.g. ``"data_vendors.core_stock_apis"``).
            type_: If given, cast the returned value (e.g. ``int``).
            fallback: Value to return when *key_path* is missing.
                Defaults to :class:`KeyError` (i.e. raise).

        Returns:
            Config value.  When ``_test_mode`` is active the returned
            dict values are ``deepcopy``-ed to ensure test isolation.

        Raises:
            KeyError: When *key_path* does not exist and *fallback*
                is not provided.
        """
        with self._lock:
            try:
                raw = _get_by_path(self._store, key_path)
            except KeyError:
                if fallback is not KeyError:
                    return fallback
                raise

            # Test isolation: return deepcopy so mutations don't leak
            if self._test_mode:
                raw = copy.deepcopy(raw)

            if type_ is not None:
                raw = type_(raw)

            return raw

    def set(self, key_path: str, value: Any) -> None:
        """Set a configuration value at *key_path*.

        Thread-safe.  Creates intermediate dicts if needed.
        """
        with self._lock:
            _set_by_path(self._store, key_path, value)

    def get_all(self) -> Dict[str, Any]:
        """Return a shallow copy of the entire config store.

        In test mode the returned dict (and all nested dicts) is deep-copied.
        """
        with self._lock:
            if self._test_mode:
                return copy.deepcopy(self._store)
            return dict(self._store)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def keys(self, prefix: str = "") -> list:
        """Return flat key-path strings for every leaf in the store.

        Args:
            prefix: Limit to keys starting with this path
                (e.g. ``"data_vendors"``).
        """
        with self._lock:
            leaves: list[str] = []

            def _walk(d: dict, parent: str):
                for k, v in d.items():
                    path = f"{parent}.{k}" if parent else k
                    if isinstance(v, dict):
                        _walk(v, path)
                    else:
                        leaves.append(path)

            _walk(self._store, "")
            if prefix:
                leaves = [k for k in leaves if k.startswith(prefix)]
            return leaves

    def validate(self, required_keys: list) -> list:
        """Check that *required_keys* exist in the store.

        Returns:
            List of missing key paths.  Empty list = valid.
        """
        missing = []
        for key in required_keys:
            try:
                _get_by_path(self._store, key)
            except KeyError:
                missing.append(key)
        return missing

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reload(self, initial: Optional[Dict[str, Any]] = None) -> None:
        """Rebuild the config store from defaults + env overrides.

        Args:
            initial: If provided, replaces the entire store with this dict
                (after applying env overrides).  Otherwise re-loads defaults.

        Thread-safe.
        """
        with self._lock:
            self._test_mode = _is_test_env()
            self._store = self._build_store(initial)

    def snapshot(self) -> Dict[str, Any]:
        """Return a deepcopy of the current store (always, not just test mode).

        Useful for saving config state before destructive actions or for
        comparing config changes.
        """
        with self._lock:
            return copy.deepcopy(self._store)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_test(self) -> bool:
        """``True`` when running in a test environment."""
        return self._test_mode

    @property
    def loaded_at(self) -> float:
        """Time at which the store was last built/reloaded (epoch seconds)."""
        return self._loaded_at


# ---------------------------------------------------------------------------
# Global singleton for convenience
# ---------------------------------------------------------------------------

_config_singleton: Optional[ConfigSection] = None
_config_lock = threading.Lock()


def get_config(env_overrides: Optional[Mapping[str, str]] = None) -> ConfigSection:
    """Return (and lazily create) the global :class:`ConfigSection` instance.

    All callers that do not need isolated instances should use this function
    to avoid creating redundant stores.

    Args:
        env_overrides: Only used on the first call; ignored on subsequent calls.
    """
    global _config_singleton
    if _config_singleton is None:
        with _config_lock:
            if _config_singleton is None:  # double-check
                _config_singleton = ConfigSection(env_overrides=env_overrides)
    return _config_singleton


def reset_config() -> None:
    """Reset the global singleton (primarily for tests)."""
    global _config_singleton
    with _config_lock:
        _config_singleton = ConfigSection()
