"""Unit tests for ResilientLLM wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.llm_clients.resilient_llm import ResilientLLM


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def primary():
    """A mock primary LLM that succeeds by default."""
    mock = MagicMock()
    mock.content = "primary response"
    mock.invoke.return_value = mock
    return mock


@pytest.fixture
def fallback():
    """A mock fallback LLM that succeeds by default."""
    mock = MagicMock()
    mock.content = "fallback response"
    mock.invoke.return_value = mock
    return mock


def _make_structured_ok():
    """Return a MagicMock representing a successful `with_structured_output` runnable."""
    runnable = MagicMock()
    return runnable


# ---------------------------------------------------------------------------
# invoke — basic success
# ---------------------------------------------------------------------------


def test_primary_ok(primary, fallback):
    """Primary LLM succeeds on first call — no degradation, correct result."""
    r = ResilientLLM(primary=primary, fallback=fallback, max_retries=2)
    result = r.invoke("hello")

    assert result.content == "primary response"
    assert primary.invoke.call_count == 1
    assert fallback.invoke.call_count == 0
    assert not r.is_degraded


def test_primary_ok_no_fallback(primary):
    """Primary succeeds even without a fallback configured."""
    r = ResilientLLM(primary=primary, fallback=None)
    result = r.invoke("hello")

    assert result.content == "primary response"
    assert not r.is_degraded


# ---------------------------------------------------------------------------
# invoke — retry then fallback
# ---------------------------------------------------------------------------


def test_primary_fail_fallback_succeeds(primary, fallback):
    """Primary fails all retries → fallback invoked → degraded + disclaimer."""
    primary.invoke.side_effect = [
        ConnectionError("timeout"),
        ConnectionError("timeout again"),
    ]

    r = ResilientLLM(primary=primary, fallback=fallback, max_retries=2, retry_delay=0.0)
    result = r.invoke("hello")

    assert primary.invoke.call_count == 2
    assert fallback.invoke.call_count == 1
    assert r.is_degraded
    assert "⚠️ 深度分析模型不可用" in result.content


def test_primary_retry_succeeds(primary, fallback):
    """Primary fails once, succeeds on second attempt — no fallback, no degradation."""
    primary.invoke.side_effect = [
        ConnectionError("transient"),
        MagicMock(content="recovered response"),
    ]

    r = ResilientLLM(primary=primary, fallback=fallback, max_retries=2, retry_delay=0.0)
    result = r.invoke("hello")

    assert primary.invoke.call_count == 2
    assert fallback.invoke.call_count == 0
    assert result.content == "recovered response"
    assert not r.is_degraded


# ---------------------------------------------------------------------------
# invoke — NotImplementedError (DeepSeek-style)
# ---------------------------------------------------------------------------


def test_not_implemented_error_immediate_fallback(primary, fallback):
    """NotImplementedError → skip retries, fall back immediately."""
    primary.invoke.side_effect = NotImplementedError("deepseek-reasoner does not support tool_choice")

    r = ResilientLLM(primary=primary, fallback=fallback, max_retries=2, retry_delay=0.0)
    result = r.invoke("hello")

    assert primary.invoke.call_count == 1  # no retries
    assert fallback.invoke.call_count == 1
    assert r.is_degraded
    assert "⚠️ 深度分析模型不可用" in result.content


# ---------------------------------------------------------------------------
# invoke — both fail
# ---------------------------------------------------------------------------


def test_both_fail(primary, fallback):
    """Primary and fallback both fail → RuntimeError with primary + fallback messages."""
    primary.invoke.side_effect = [
        ConnectionError("primary boom"),
        ConnectionError("primary boom again"),
    ]
    fallback.invoke.side_effect = ConnectionError("fallback boom")

    r = ResilientLLM(primary=primary, fallback=fallback, max_retries=2, retry_delay=0.0)

    with pytest.raises(RuntimeError, match="Both primary and fallback"):
        r.invoke("hello")

    assert primary.invoke.call_count == 2
    assert fallback.invoke.call_count == 1
    assert r.is_degraded is False  # never succeeded


def test_no_fallback_raises(primary):
    """Primary fails with no fallback → RuntimeError."""
    primary.invoke.side_effect = [
        ConnectionError("boom"),
        ConnectionError("boom again"),
    ]

    r = ResilientLLM(primary=primary, fallback=None, max_retries=2, retry_delay=0.0)

    with pytest.raises(RuntimeError, match="no fallback configured"):
        r.invoke("hello")

    assert primary.invoke.call_count == 2


# ---------------------------------------------------------------------------
# with_structured_output
# ---------------------------------------------------------------------------


def test_with_structured_output_ok(primary, fallback):
    """Primary supports structured output — returned directly without degradation."""
    structured = _make_structured_ok()
    primary.with_structured_output.return_value = structured

    r = ResilientLLM(primary=primary, fallback=fallback)
    result = r.with_structured_output(dict)

    assert result is structured
    assert primary.with_structured_output.called
    assert fallback.with_structured_output.call_count == 0
    assert not r.is_degraded


def test_with_structured_output_not_implemented_fallback(primary, fallback):
    """Primary raises NotImplementedError → falls back to fallback's structured output."""
    primary.with_structured_output.side_effect = NotImplementedError("deepseek-reasoner")

    fallback_structured = _make_structured_ok()
    fallback.with_structured_output.return_value = fallback_structured

    r = ResilientLLM(primary=primary, fallback=fallback)
    result = r.with_structured_output(dict)

    assert result is fallback_structured
    assert fallback.with_structured_output.called
    assert r.is_degraded


def test_with_structured_output_general_error_fallback(primary, fallback):
    """Primary raises a generic exception → falls back."""
    primary.with_structured_output.side_effect = RuntimeError("gone")

    fallback_structured = _make_structured_ok()
    fallback.with_structured_output.return_value = fallback_structured

    r = ResilientLLM(primary=primary, fallback=fallback)
    result = r.with_structured_output(dict)

    assert result is fallback_structured
    assert r.is_degraded


def test_with_structured_output_not_implemented_no_fallback(primary):
    """Primary raises NotImplementedError with no fallback → re-raises."""
    primary.with_structured_output.side_effect = NotImplementedError("deepseek-reasoner")

    r = ResilientLLM(primary=primary, fallback=None)
    with pytest.raises(NotImplementedError):
        r.with_structured_output(dict)


# ---------------------------------------------------------------------------
# is_degraded property
# ---------------------------------------------------------------------------


def test_is_degraded_tracks_state(primary, fallback):
    """is_degraded correctly reflects fallback usage across invocations."""
    # First call succeeds on primary — not degraded
    r = ResilientLLM(primary=primary, fallback=fallback, max_retries=2, retry_delay=0.0)
    r.invoke("q1")
    assert not r.is_degraded

    # Second call: primary fails, fallback succeeds — becomes degraded
    primary.invoke.side_effect = [
        ConnectionError("fail1"),
        ConnectionError("fail2"),
    ]
    r.invoke("q2")
    assert r.is_degraded

    # Third call: primary recovers — back to normal
    primary.invoke.side_effect = None
    primary.invoke.reset_mock()
    r.invoke("q3")
    assert not r.is_degraded
