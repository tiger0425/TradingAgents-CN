"""Indicator registry — 指标名单一真理源。

解决 market_analyst system prompt、technical_indicators_tools schema、
akshare._INDICATOR_DESCRIPTIONS、a_stock_data.col_map 各自硬编码指标名的问题。
"""

from typing import NamedTuple


class IndicatorInfo(NamedTuple):
    """单个指标的元数据。"""

    name: str
    description: str
    category: str


# ── 别名映射: 常用替代名 → 规范名 ──────────────────────────────
_ALIASES: dict[str, str] = {
    "bb_upper": "boll_ub",
    "bb_lower": "boll_lb",
    "bb_middle": "boll",
    "bb": "boll",
}

# ── 13 个核心指标描述（从 akshare._INDICATOR_DESCRIPTIONS 提取） ──
_INDICATOR_DESCRIPTIONS: dict[str, str] = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume "
        "to measure buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength "
        "of trends or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI "
        "can indicate potential reversals."
    ),
}

# ── 分类映射 ──────────────────────────────────────────────────
_CATEGORIES: dict[str, str] = {
    "close_50_sma": "moving_avg",
    "close_200_sma": "moving_avg",
    "close_10_ema": "moving_avg",
    "macd": "momentum",
    "macds": "momentum",
    "macdh": "momentum",
    "rsi": "momentum",
    "boll": "volatility",
    "boll_ub": "volatility",
    "boll_lb": "volatility",
    "atr": "volatility",
    "vwma": "volume",
    "mfi": "momentum",
}

# ── 构建注册表 ─────────────────────────────────────────────────
_registry: dict[str, IndicatorInfo] = {}
for _name, _desc in _INDICATOR_DESCRIPTIONS.items():
    _cat = _CATEGORIES.get(_name, "other")
    _registry[_name] = IndicatorInfo(name=_name, description=_desc, category=_cat)

INDICATORS: list[IndicatorInfo] = list(_registry.values())
"""所有核心指标的列表。"""


def canonical_name(name: str) -> str:
    """返回指标的规范名称（大小写不敏感，支持别名）。

    Args:
        name: 指标名称（如 "BB_UPPER", "rsi", "Boll_Ub"）。

    Returns:
        规范名称（全小写）。

    Raises:
        ValueError: 如果指标名称无效。
    """
    cleaned = name.strip().lower()

    # 1) 直接匹配规范名
    if cleaned in _registry:
        return cleaned

    # 2) 别名查找
    if cleaned in _ALIASES:
        return _ALIASES[cleaned]

    # 3) 枚举可用指标
    valid = ", ".join(sorted(_registry))
    raise ValueError(
        f"Unknown indicator: {name!r}. Valid indicators: {valid}"
    )


def get_indicator(name: str) -> IndicatorInfo:
    """根据名称查找 IndicatorInfo（大小写不敏感）。

    Args:
        name: 指标名称。

    Returns:
        IndicatorInfo NamedTuple。

    Raises:
        ValueError: 如果指标不存在。
    """
    key = canonical_name(name)
    return _registry[key]


def get_indicator_description(name: str) -> str:
    """获取指标的描述文本（大小写不敏感）。

    Args:
        name: 指标名称。

    Returns:
        描述文本字符串。

    Raises:
        ValueError: 如果指标不存在。
    """
    return get_indicator(name).description
