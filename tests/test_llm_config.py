"""Test temperature configuration injection in LLM clients.

RED phase (TDD) — all tests FAIL because the implementation does not
yet inject temperature into the LLM pipeline.

Tests cover:
1. DEFAULT_CONFIG entries for llm_temperature (0.0) and llm_debate_temperature (0.3)
2. bootstrap._create_llms() passing temperature kwarg to create_llm_client
3. Each LLM client (OpenAI, Anthropic, Google) forwarding temperature to the LLM instance
"""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.default_config import DEFAULT_CONFIG


# =========================================================================
#  Tests 1 & 2: DEFAULT_CONFIG temperature keys
# =========================================================================

class TestDefaultConfigTemperature:
    """Verify DEFAULT_CONFIG declares temperature keys.

    Expected to FAIL because llm_temperature and llm_debate_temperature
    are not yet part of DEFAULT_CONFIG.
    """

    def test_default_config_has_temperature_key(self):
        """Default LLM temperature should be 0.0 (deterministic reasoning)."""
        assert DEFAULT_CONFIG["llm_temperature"] == 0.0

    def test_default_config_has_debate_temperature(self):
        """Debate-specific temperature should be 0.3 (controlled creativity)."""
        assert DEFAULT_CONFIG["llm_debate_temperature"] == 0.3


# =========================================================================
#  Test 3: bootstrap injection path
# =========================================================================

class TestBootstrapTemperatureInjection:
    """Verify _create_llms() reads temperature from config and passes it on.

    Expected to FAIL because bootstrap._create_llms() does not yet
    extract llm_temperature from config into llm_kwargs.
    """

    @patch("tradingagents.llm_clients.create_llm_client")
    def test_bootstrap_injects_temperature(self, mock_create_llm: MagicMock):
        """create_llm_client must receive temperature kwarg during bootstrap."""
        config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4o",
            "quick_think_llm": "gpt-4o-mini",
            "backend_url": None,
            "llm_temperature": 0.0,
            "llm_debate_temperature": 0.3,
        }

        # Mock the client returned by create_llm_client so that
        # deep_client.get_llm() and quick_client.get_llm() work later.
        mock_client = MagicMock()
        mock_client.get_llm.return_value = MagicMock()
        mock_create_llm.return_value = mock_client

        from tradingagents.bootstrap import _create_llms
        _create_llms(config)

        # At least one create_llm_client call must include temperature=0.0
        for call_args, call_kwargs in mock_create_llm.call_args_list:
            if "temperature" in call_kwargs:
                assert call_kwargs["temperature"] == 0.0
                return

        pytest.fail(
            "No call to create_llm_client included temperature=0.0"
        )


# =========================================================================
#  Tests 4–6: Client-level temperature passthrough
# =========================================================================

class TestClientTemperaturePassthrough:
    """Verify each client's get_llm() forwards temperature to the LLM.

    Expected to FAIL because _PASSTHROUGH_KWARGS / inline kwarg lists
    do not yet include 'temperature'.
    """

    def test_openai_client_passes_temperature(self):
        """OpenAIClient.get_llm() returns an LLM with temperature == 0.0."""
        from tradingagents.llm_clients.openai_client import OpenAIClient

        client = OpenAIClient(model="gpt-4o", temperature=0.0)
        llm = client.get_llm()
        assert llm.temperature == 0.0

    def test_anthropic_client_passes_temperature(self):
        """AnthropicClient.get_llm() returns an LLM with temperature == 0.0."""
        from tradingagents.llm_clients.anthropic_client import AnthropicClient

        client = AnthropicClient(model="claude-sonnet-4-20250514", temperature=0.0)
        llm = client.get_llm()
        assert llm.temperature == 0.0

    def test_google_client_passes_temperature(self):
        """GoogleClient.get_llm() returns an LLM with temperature == 0.0."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(model="gemini-2.5-pro", temperature=0.0)
        llm = client.get_llm()
        assert llm.temperature == 0.0
