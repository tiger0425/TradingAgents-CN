import copy
import tradingagents.default_config as default_config
from typing import Dict

# Frozen configuration: initialized once from DEFAULT_CONFIG, never mutated.
_config: Dict = {}


def initialize_config():
    """Initialize the configuration from DEFAULT_CONFIG (called once at import)."""
    global _config
    if not _config:
        _config = copy.deepcopy(default_config.DEFAULT_CONFIG)


def get_config() -> Dict:
    """Return a snapshot of the read-only configuration.

    The returned dict is a shallow copy so callers cannot mutate the global.
    Use this for read access only — there is no set_config().
    If you need per-instance config, pass it explicitly via constructor/propagate args.
    """
    if not _config:
        initialize_config()
    return _config.copy()


# Initialize on import — afterwards _config is effectively read-only.
initialize_config()
