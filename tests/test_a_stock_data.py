"""冒烟测试：A 股数据供应商 — a-stock-data 封装的 9 个端点。

数据来源: a-stock-data

测试策略:
  - 正例: 用 600519（贵州茅台）调用，验证返回 str 且含关键字段和数据来源标记
  - 负例: 用无效代码/空参数调用，验证返回错误 str 而非异常
"""

from typing import Any, Dict, List, Tuple

import pytest
from tradingagents.dataflows.a_stock_data import (
    get_dragon_tiger_stock,
    get_dragon_tiger_market,
    get_margin_trading,
    get_block_trade,
    get_lockup_expiry,
    get_shareholder_count,
    get_dividend_history,
    get_cls_flash,
    get_cninfo_announcements,
    get_concept_blocks,
    get_hot_stock_reasons,
)

# 数据来源标记 — 所有正例应包含该字符串
_DATA_SOURCE = "数据来源: a-stock-data"

# ===========================================================================
# 正例（600519 贵州茅台）
# ===========================================================================


@pytest.mark.smoke
def test_margin_trading_moutai():
    """融资融券明细 — 正例"""
    r = get_margin_trading("600519", 5)
    assert isinstance(r, str)
    assert _DATA_SOURCE in r
    assert "融资余额" in r


@pytest.mark.smoke
def test_cls_flash():
    """财联社快讯 — 正例（无 code 参数）"""
    r = get_cls_flash(5)
    assert isinstance(r, str)
    assert _DATA_SOURCE in r
    assert any(kw in r for kw in ["财联社", "无数据", "快讯"])


@pytest.mark.smoke
def test_block_trade_moutai():
    """大宗交易 — 正例"""
    r = get_block_trade("600519", 5)
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_shareholder_count_moutai():
    """股东户数变化 — 正例"""
    r = get_shareholder_count("600519")
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_dividend_history_moutai():
    """分红送转历史 — 正例"""
    r = get_dividend_history("600519", 5)
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_lockup_expiry_moutai():
    """限售解禁日历 — 正例（该函数使用内联格式，不含统一数据来源标记）"""
    r = get_lockup_expiry("600519", "2026-05-20")
    assert isinstance(r, str)
    assert "限售解禁" in r


@pytest.mark.smoke
def test_dragon_tiger_stock_moutai():
    """龙虎榜个股席位 — 正例"""
    r = get_dragon_tiger_stock("600519", "2026-05-20")
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_dragon_tiger_market():
    """全市场龙虎榜 — 正例（无 code 参数）"""
    r = get_dragon_tiger_market("2026-05-20")
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_cninfo_announcements_moutai():
    """巨潮公告 — 正例"""
    r = get_cninfo_announcements("600519", 5)
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


# ===========================================================================
# 负例（无效代码 / 空参数）
# ===========================================================================


@pytest.mark.smoke
def test_margin_trading_invalid_code():
    """融资融券 — 无效股票代码应返回错误 str"""
    r = get_margin_trading("000000")
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error"])


@pytest.mark.smoke
def test_block_trade_invalid_code():
    """大宗交易 — 无效股票代码应返回错误 str"""
    r = get_block_trade("000000", 3)
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error"])


@pytest.mark.smoke
def test_shareholder_count_invalid_code():
    """股东户数 — 无效股票代码应返回错误 str"""
    r = get_shareholder_count("000000", 3)
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error"])


@pytest.mark.smoke
def test_dividend_history_invalid_code():
    """分红送转 — 无效股票代码应返回错误 str"""
    r = get_dividend_history("000000", 3)
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error"])


@pytest.mark.smoke
def test_lockup_expiry_invalid_code():
    """限售解禁 — 无效股票代码返回空结果（API 无异常）"""
    r = get_lockup_expiry("000000", "2026-05-20")
    assert isinstance(r, str)
    # 该函数内联格式，无效代码返回"无历史解禁记录"或显式错误
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error", "无历史解禁记录"])


@pytest.mark.smoke
def test_dragon_tiger_stock_invalid():
    """龙虎榜个股席位 — 无效股票代码应返回错误 str"""
    r = get_dragon_tiger_stock("000000", "2026-05-20")
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error"])


@pytest.mark.smoke
def test_dragon_tiger_market_empty_date():
    """全市场龙虎榜 — 空日期参数应正常工作（默认当天）"""
    r = get_dragon_tiger_market("")
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_cls_flash_minimal():
    """财联社快讯 — 最小请求 1 条"""
    r = get_cls_flash(1)
    assert isinstance(r, str)
    assert _DATA_SOURCE in r


@pytest.mark.smoke
def test_cninfo_announcements_invalid_code():
    """巨潮公告 — 无效股票代码应返回错误 str"""
    r = get_cninfo_announcements("000000", 3)
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据", "Error"])


@pytest.mark.smoke
def test_invalid_code_comprehensive():
    """多个端点 — 无效股票代码 000000 均不抛异常（综合验证）"""
    fns: List[Tuple[Any, Tuple[Any, ...], Dict[str, Any]]] = [
        (get_block_trade, ("000000",), {}),
        (get_margin_trading, ("000000",), {}),
        (get_shareholder_count, ("000000",), {}),
        (get_dividend_history, ("000000",), {}),
        (get_lockup_expiry, ("000000", "2026-05-20"), {}),
    ]
    for fn, args, kwargs in fns:
        try:
            r = fn(*args, **kwargs)
            assert isinstance(r, str), f"{fn.__name__} 未返回字符串"
        except Exception as e:
            assert False, f"{fn.__name__} 抛异常而非返回 str: {e}"


# ===========================================================================
# 新增：概念板块 + 涨停原因
# ===========================================================================


@pytest.mark.smoke
def test_concept_blocks_moutai():
    """概念板块归属 — 正例"""
    r = get_concept_blocks("600519")
    assert isinstance(r, str)


@pytest.mark.smoke
def test_concept_blocks_invalid_code():
    """概念板块归属 — 无效股票代码应返回错误 str"""
    r = get_concept_blocks("000000")
    assert isinstance(r, str)
    assert any(kw in r for kw in ["错误", "失败", "无数据"])


@pytest.mark.smoke
def test_hot_stock_reasons():
    """涨停原因 — 正例（默认当天）"""
    r = get_hot_stock_reasons()
    assert isinstance(r, str)


@pytest.mark.smoke
def test_hot_stock_reasons_invalid_date():
    """涨停原因 — 无效日期不抛异常（API 回退当日数据）"""
    r = get_hot_stock_reasons("2000-01-01")
    assert isinstance(r, str)
