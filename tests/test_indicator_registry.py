"""RED 阶段 — 测试 indicator_registry 模块（预期全部 FAIL）。"""

import pytest
from tradingagents.agents.utils.indicator_registry import (
    INDICATORS,
    IndicatorInfo,
    get_indicator_description,
    canonical_name,
    get_indicator,
)


class TestIndicatorRegistry:
    """12 个核心指标注册表测试。"""

    # ── 预期数据 ──────────────────────────────────────────────
    _CORE_INDICATORS = {
        "close_50_sma",
        "close_200_sma",
        "close_10_ema",
        "macd",
        "macds",
        "macdh",
        "rsi",
        "boll",
        "boll_ub",
        "boll_lb",
        "atr",
        "vwma",
        "mfi",
    }

    def test_registry_has_all_indicators(self):
        """INDICATORS 注册表包含全部 12 个核心指标。"""
        names = {ind.name for ind in INDICATORS}
        assert names == self._CORE_INDICATORS, (
            f"期望 12 个核心指标，"
            f"缺少: {self._CORE_INDICATORS - names}, "
            f"多余: {names - self._CORE_INDICATORS}"
        )

    def test_get_indicator_description(self):
        """每个指标都有非空 description 字段。"""
        for name in self._CORE_INDICATORS:
            desc = get_indicator_description(name)
            assert isinstance(desc, str), f"{name} 的 description 应为 str"
            assert len(desc) > 10, f"{name} 的 description 太短: {desc!r}"

    def test_canonical_name(self):
        """canonical_name 大小写不敏感，返回规范名。"""
        # 全大写
        assert canonical_name("BB_UPPER") == "boll_ub"
        # 全小写
        assert canonical_name("boll_ub") == "boll_ub"
        # 混合大小写
        assert canonical_name("Boll_Ub") == "boll_ub"
        # 其他指标
        assert canonical_name("RSI") == "rsi"
        assert canonical_name("MACD") == "macd"

    def test_invalid_indicator_raises(self):
        """不存在的指标名抛出 ValueError。"""
        with pytest.raises(ValueError, match="nonexistent"):
            get_indicator("nonexistent")

    # ── 完整性校验 ──────────────────────────────────────────

    def test_indicator_info_is_namedtuple(self):
        """INDICATORS 元素为 NamedTuple 结构。"""
        for ind in INDICATORS:
            assert isinstance(ind, tuple)
            # NamedTuple 应有 _fields
            assert hasattr(ind, "_fields"), f"{ind.name} 不是 NamedTuple"
            assert "name" in ind._fields
            assert "description" in ind._fields

    def test_get_indicator_returns_indicator_info(self):
        """get_indicator 返回 IndicatorInfo NamedTuple。"""
        ind = get_indicator("close_50_sma")
        assert isinstance(ind, IndicatorInfo)
        assert ind.name == "close_50_sma"
        assert isinstance(ind.description, str)
        assert len(ind.description) > 10

    def test_get_indicator_description_invalid_raises(self):
        """对不存在指标调用 get_indicator_description 抛 ValueError。"""
        with pytest.raises(ValueError, match="nonexistent"):
            get_indicator_description("nonexistent")
