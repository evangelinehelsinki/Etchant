"""Tests for the agent module.

Tests the agent's structure and executor integration without requiring
an actual API key. Uses mocked API clients for both providers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from etchant.agents.agent import (
    _SYSTEM_PROMPT,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    EtchantAgent,
    _convert_tools_to_openai_format,
)


class TestAgentInit:
    def test_defaults_to_openrouter(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(constraints_dir=constraints_dir)
        assert agent._provider == "openai"
        assert agent._model == DEFAULT_MODEL
        assert agent._base_url == DEFAULT_BASE_URL

    def test_anthropic_provider(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(provider="anthropic", constraints_dir=constraints_dir)
        assert agent._provider == "anthropic"

    def test_system_prompt_mentions_jlcpcb(self) -> None:
        assert "JLCPCB" in _SYSTEM_PROMPT

    def test_system_prompt_mentions_topologies(self) -> None:
        assert "buck" in _SYSTEM_PROMPT.lower()
        assert "ldo" in _SYSTEM_PROMPT.lower()


class TestToolFormatConversion:
    def test_converts_anthropic_to_openai(self) -> None:
        anthropic_tools = [{
            "name": "test_tool",
            "description": "A test tool",
            "input_schema": {
                "type": "object",
                "properties": {"x": {"type": "number"}},
                "required": ["x"],
            },
        }]
        openai_tools = _convert_tools_to_openai_format(anthropic_tools)
        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert openai_tools[0]["function"]["name"] == "test_tool"
        assert openai_tools[0]["function"]["parameters"]["type"] == "object"


class TestAgentWithoutAPI:
    def test_openai_raises_without_package(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)
        with patch.dict("sys.modules", {"openai": None}), pytest.raises(
            RuntimeError, match="openai package required"
        ):
            agent._get_client()

    def test_anthropic_raises_without_package(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(
            api_key="fake", provider="anthropic", constraints_dir=constraints_dir,
        )
        with patch.dict("sys.modules", {"anthropic": None}), pytest.raises(
            RuntimeError, match="anthropic package required"
        ):
            agent._get_client()


class TestOpenAIAgentWithMock:
    def test_simple_text_response(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)

        mock_message = MagicMock()
        mock_message.content = "I recommend an LDO regulator."
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        agent._client = mock_client

        result = agent.design("I need a 3.3V supply")
        assert result["response"] == "I recommend an LDO regulator."
        assert result["turns"] == 1

    def test_tool_use_then_response(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)

        # Turn 1: tool call
        mock_fn = MagicMock()
        mock_fn.name = "list_topologies"
        mock_fn.arguments = "{}"

        mock_tool_call = MagicMock()
        mock_tool_call.function = mock_fn
        mock_tool_call.id = "call_123"

        mock_msg1 = MagicMock()
        mock_msg1.content = None
        mock_msg1.tool_calls = [mock_tool_call]

        mock_choice1 = MagicMock()
        mock_choice1.finish_reason = "tool_calls"
        mock_choice1.message = mock_msg1

        mock_resp1 = MagicMock()
        mock_resp1.choices = [mock_choice1]

        # Turn 2: text response
        mock_msg2 = MagicMock()
        mock_msg2.content = "Available: buck_converter, ldo_regulator"
        mock_msg2.tool_calls = None

        mock_choice2 = MagicMock()
        mock_choice2.finish_reason = "stop"
        mock_choice2.message = mock_msg2

        mock_resp2 = MagicMock()
        mock_resp2.choices = [mock_choice2]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [mock_resp1, mock_resp2]
        agent._client = mock_client

        result = agent.design("What topologies are available?")
        assert result["turns"] == 2
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "list_topologies"


class TestAnthropicAgentWithMock:
    def test_simple_text_response(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(
            api_key="fake", provider="anthropic", constraints_dir=constraints_dir,
        )

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "I recommend an LDO."
        mock_response.content = [mock_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        agent._client = mock_client

        result = agent.design("I need a 3.3V supply")
        assert result["response"] == "I recommend an LDO."
        assert result["turns"] == 1


class TestMaxTurns:
    def test_openai_max_turns(self, constraints_dir: Path) -> None:
        agent = EtchantAgent(api_key="fake", constraints_dir=constraints_dir)

        mock_fn = MagicMock()
        mock_fn.name = "list_topologies"
        mock_fn.arguments = "{}"

        mock_tool_call = MagicMock()
        mock_tool_call.function = mock_fn
        mock_tool_call.id = "call_loop"

        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tool_call]

        mock_choice = MagicMock()
        mock_choice.finish_reason = "tool_calls"
        mock_choice.message = mock_msg

        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        agent._client = mock_client

        result = agent.design("loop forever", max_turns=3)
        assert result["turns"] == 3
        assert "Max turns" in result["response"]
