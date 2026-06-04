"""TDD RED/verification tests: anti-hallucination and degradation instructions.

Tests 1-4 verify the existing prompt_constants module works for both
Chinese and English (GREEN phase — the module was already created by Task 15).
Test 5 proves the English degradation bug still exists (RED phase):
`get_degradation_instruction()` returns "" when output_language is "English",
leaving English users without degradation guidance.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from tradingagents.agents.utils.agent_utils import get_degradation_instruction


# ── Helper ──────────────────────────────────────────────────────────────


@contextmanager
def _mock_config(output_language: str):
    """Override get_config() at all import sites to return a specific output_language.

    prompt_constants.py imports get_config at module level (compile-time),
    so patching the source module only isn't enough — the local reference
    in prompt_constants is bound to the original function object.
    agent_utils.get_degradation_instruction imports inside the function body
    (run-time), so the source-module patch suffices there.
    """
    mock_cfg = {"output_language": output_language}
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "tradingagents.dataflows.config.get_config",
                return_value=mock_cfg,
            )
        )
        stack.enter_context(
            patch(
                "tradingagents.agents.utils.prompt_constants.get_config",
                return_value=mock_cfg,
            )
        )
        yield


# ── Anti-hallucination instruction (module exists from Task 15) ────────


def test_chinese_anti_hallucination_nonempty():
    """get_anti_hallucination_instruction(Chinese) returns non-empty str.

    Default config output_language is 'Chinese', so the function returns
    Chinese anti-hallucination content.
    """
    from tradingagents.agents.utils.prompt_constants import (
        get_anti_hallucination_instruction,
    )

    result = get_anti_hallucination_instruction(agent_type="analyst")
    assert result and len(result) > 50, (
        f"Chinese anti-hallucination instruction should be non-empty "
        f"with meaningful content, got {repr(result[:60])}"
    )


def test_english_anti_hallucination_nonempty():
    """get_anti_hallucination_instruction(English) returns non-empty str.

    English mode must also get anti-hallucination guidance.
    """
    from tradingagents.agents.utils.prompt_constants import (
        get_anti_hallucination_instruction,
    )

    with _mock_config("English"):
        result = get_anti_hallucination_instruction(agent_type="analyst")
    assert result and len(result) > 50, (
        f"English anti-hallucination instruction should be non-empty, "
        f"got {repr(result[:60])}"
    )


def test_contains_keyword_data_unavailable():
    """Result must contain '[数据不可用]' or '[Data Unavailable]'."""
    from tradingagents.agents.utils.prompt_constants import (
        get_anti_hallucination_instruction,
    )

    zh = get_anti_hallucination_instruction(agent_type="analyst")
    with _mock_config("English"):
        en = get_anti_hallucination_instruction(agent_type="analyst")

    assert "[数据不可用]" in zh, (
        f"Chinese instruction should contain '[数据不可用]', "
        f"got: {repr(zh[:100])}"
    )
    assert "[Data Unavailable]" in en, (
        f"English instruction should contain '[Data Unavailable]', "
        f"got: {repr(en[:100])}"
    )


def test_contains_tool_only_constraint():
    """Result must contain '只使用' or 'only use tools' constraint."""
    from tradingagents.agents.utils.prompt_constants import (
        get_anti_hallucination_instruction,
    )

    zh = get_anti_hallucination_instruction(agent_type="analyst")
    with _mock_config("English"):
        en = get_anti_hallucination_instruction(agent_type="analyst")

    assert "只使用" in zh, (
        f"Chinese instruction should contain '只使用', "
        f"got: {repr(zh[:100])}"
    )
    assert "only use tools" in en.lower(), (
        f"English instruction should contain 'only use tools', "
        f"got: {repr(en[:100])}"
    )


# ── Degradation instruction (known bug: English returns "") ────────────


def test_degradation_english_nonempty():
    """RED: get_degradation_instruction(English) should return non-empty.

    Current behavior (bug): returns "" when output_language == "English".
    Expected after fix: returns an English degradation prompt similar to
    the existing Chinese version at agent_utils.py L63-67.

    This is the ONE test that should fail RED — the other 4 verify
    already-implemented functionality.
    """
    with _mock_config("English"):
        result_en = get_degradation_instruction()
    assert result_en and len(result_en) > 30, (
        f"English degradation instruction should be non-empty, "
        f"got {repr(result_en[:60])}. "
        "Bug: agent_utils.get_degradation_instruction() returns '' for English."
    )
