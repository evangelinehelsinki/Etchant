"""Model-agnostic agent loop supporting OpenRouter, Anthropic, and OpenAI-compatible APIs.

Uses the OpenAI SDK format by default (works with OpenRouter, local models, etc.).
Falls back to Anthropic SDK when using Claude models directly.

Usage:
    # OpenRouter (recommended for testing — cheap OSS models)
    agent = EtchantAgent(
        api_key="sk-or-...",
        base_url="https://openrouter.ai/api/v1",
        model="qwen/qwen3-235b-a22b",
    )

    # Anthropic direct
    agent = EtchantAgent(
        api_key="sk-ant-...",
        provider="anthropic",
        model="claude-sonnet-4-6",
    )

    result = agent.design("I need a 5V to 3.3V regulator for my ESP32")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from etchant.agents.executor import ToolExecutor
from etchant.agents.tools import get_tool_definitions_for_api

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Etchant, an AI PCB design assistant. You help users design \
power supply circuits by selecting the right topology and generating complete, \
manufacturable designs optimized for JLCPCB assembly.

Your workflow:
1. Understand the user's power requirements (input voltage, output voltage, current)
2. Use suggest_topology to recommend the best circuit type
3. Use generate_circuit to create the design
4. Use validate_design to check for issues
5. Use estimate_cost to show JLCPCB manufacturing costs

Always prefer JLCPCB basic parts over extended parts to minimize assembly costs.
When the user's requirements are ambiguous, ask clarifying questions.
For noise-sensitive applications, recommend LDO regulators.
For high-efficiency or high-current needs, recommend buck converters."""

# Default model for testing — free, designed for agentic tool use
DEFAULT_MODEL = "openai/gpt-oss-120b:free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Good alternatives (update benchmark to test these):
# "meta-llama/llama-3.3-70b-instruct:free"  — free, solid structured output
# "deepseek/deepseek-chat-v3-0324"           — cheap, strong tool use
# "qwen/qwen3-235b-a22b"                    — large, good reasoning


class EtchantAgent:
    """Model-agnostic agent for circuit design."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str = "openai",
        constraints_dir: Path | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._provider = provider
        self._model = model or DEFAULT_MODEL
        self._base_url = base_url or DEFAULT_BASE_URL
        self._api_key = api_key
        self._executor = ToolExecutor(
            constraints_dir=constraints_dir,
            output_dir=output_dir,
        )
        self._tools_anthropic = get_tool_definitions_for_api()
        self._tools_openai = _convert_tools_to_openai_format(self._tools_anthropic)
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-init the API client."""
        if self._client is not None:
            return self._client

        if self._provider == "anthropic":
            try:
                import anthropic
            except ImportError as e:
                raise RuntimeError(
                    "anthropic package required. Install with: uv sync --extra agent"
                ) from e
            self._client = anthropic.Anthropic(api_key=self._api_key)
        else:
            try:
                import openai
            except ImportError as e:
                raise RuntimeError(
                    "openai package required. Install with: pip install openai"
                ) from e
            self._client = openai.OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )

        return self._client

    def design(self, request: str, max_turns: int = 10) -> dict[str, Any]:
        """Process a natural language design request."""
        if self._provider == "anthropic":
            return self._design_anthropic(request, max_turns)
        return self._design_openai(request, max_turns)

    def _design_openai(self, request: str, max_turns: int) -> dict[str, Any]:
        """Agent loop using OpenAI-compatible API (OpenRouter, local, etc.)."""
        client = self._get_client()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": request},
        ]

        results: list[dict[str, Any]] = []

        for turn in range(max_turns):
            logger.info("Agent turn %d (openai)", turn + 1)

            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=self._tools_openai,
                max_tokens=4096,
            )

            choice = response.choices[0]
            message = choice.message

            if choice.finish_reason == "tool_calls" and message.tool_calls:
                # Process tool calls
                messages.append(message.model_dump())

                for tool_call in message.tool_calls:
                    fn = tool_call.function
                    logger.info("Tool call: %s(%s)", fn.name, fn.arguments)

                    try:
                        args = json.loads(fn.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    result = self._executor.execute(fn.name, args)
                    results.append({
                        "tool": fn.name,
                        "input": args,
                        "output": result,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })

            elif choice.finish_reason == "stop":
                return {
                    "request": request,
                    "response": message.content or "",
                    "tool_calls": results,
                    "turns": turn + 1,
                }
            else:
                # Unknown finish reason — treat as done
                return {
                    "request": request,
                    "response": message.content or "",
                    "tool_calls": results,
                    "turns": turn + 1,
                }

        return {
            "request": request,
            "response": "Max turns reached without completion",
            "tool_calls": results,
            "turns": max_turns,
        }

    def _design_anthropic(self, request: str, max_turns: int) -> dict[str, Any]:
        """Agent loop using Anthropic API."""
        client = self._get_client()

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": request},
        ]

        results: list[dict[str, Any]] = []

        for turn in range(max_turns):
            logger.info("Agent turn %d (anthropic)", turn + 1)

            response = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=self._tools_anthropic,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("Tool call: %s(%s)", block.name, block.input)
                        result = self._executor.execute(block.name, block.input)
                        results.append({
                            "tool": block.name,
                            "input": block.input,
                            "output": result,
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            elif response.stop_reason == "end_turn":
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text

                return {
                    "request": request,
                    "response": final_text,
                    "tool_calls": results,
                    "turns": turn + 1,
                }

        return {
            "request": request,
            "response": "Max turns reached without completion",
            "tool_calls": results,
            "turns": max_turns,
        }


def _convert_tools_to_openai_format(
    anthropic_tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert Anthropic tool format to OpenAI function calling format."""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        })
    return openai_tools
