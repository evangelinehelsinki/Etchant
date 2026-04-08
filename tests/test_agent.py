"""Tests for the agent module.

Tests the agent's structure and executor integration without requiring
an actual Claude API key. The full agent loop is tested via mocking.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from etchant.agents.agent import _SYSTEM_PROMPT, EtchantAgent


class TestAgentInit:
    def test_creates_without_api_key(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(constraints_dir=constraints_dir)
        assert agent._executor is not None

    def test_system_prompt_mentions_jlcpcb(self) -> None:
        assert "JLCPCB" in _SYSTEM_PROMPT

    def test_system_prompt_mentions_topologies(self) -> None:
        assert "buck" in _SYSTEM_PROMPT.lower()
        assert "ldo" in _SYSTEM_PROMPT.lower()


class TestAgentWithoutAPI:
    def test_raises_without_anthropic_package(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)
        with patch.dict("sys.modules", {"anthropic": None}), pytest.raises(
            RuntimeError, match="anthropic package required"
        ):
            agent._get_client()


class TestAgentWithMockedAPI:
    def test_simple_text_response(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)

        # Mock a simple end_turn response (no tool use)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "I recommend an LDO regulator."
        mock_response.content = [mock_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        agent._client = mock_client

        result = agent.design("I need a 3.3V supply")
        assert result["response"] == "I recommend an LDO regulator."
        assert result["turns"] == 1
        assert result["tool_calls"] == []

    def test_tool_use_then_response(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)

        # Turn 1: tool_use response
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "list_topologies"
        mock_tool_block.input = {}
        mock_tool_block.id = "tool_123"

        mock_response_1 = MagicMock()
        mock_response_1.stop_reason = "tool_use"
        mock_response_1.content = [mock_tool_block]

        # Turn 2: end_turn response
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Available: buck_converter, ldo_regulator"
        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = "end_turn"
        mock_response_2.content = [mock_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]
        agent._client = mock_client

        result = agent.design("What topologies are available?")
        assert result["turns"] == 2
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "list_topologies"

    def test_max_turns_limit(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)

        # Always return tool_use to hit max turns
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "list_topologies"
        mock_tool_block.input = {}
        mock_tool_block.id = "tool_loop"

        mock_response = MagicMock()
        mock_response.stop_reason = "tool_use"
        mock_response.content = [mock_tool_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        agent._client = mock_client

        result = agent.design("loop forever", max_turns=3)
        assert result["turns"] == 3
        assert "Max turns" in result["response"]
