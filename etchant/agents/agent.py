"""Simple agent loop for Claude API integration.

A minimal agent that takes a natural language circuit request, uses Claude
with tool_use to select and call the right pipeline tools, and returns a
complete design. This is the Week 2 prototype — production version will
add RAG context, multi-turn conversation, and design iteration.

Usage:
    agent = EtchantAgent(api_key="sk-ant-...")
    result = agent.design("I need a 5V to 3.3V regulator for my ESP32")

Requires: anthropic package (pip install anthropic)
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


class EtchantAgent:
    """Simple agent that uses Claude to design circuits."""

    def __init__(
        self,
        api_key: str | None = None,
        constraints_dir: Path | None = None,
        output_dir: Path | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._model = model
        self._executor = ToolExecutor(
            constraints_dir=constraints_dir,
            output_dir=output_dir,
        )
        self._tools = get_tool_definitions_for_api()
        self._client: Any = None
        self._api_key = api_key

    def _get_client(self) -> Any:
        """Lazy-init the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise RuntimeError(
                    "anthropic package required. Install with: pip install anthropic"
                ) from e
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def design(self, request: str, max_turns: int = 10) -> dict[str, Any]:
        """Process a natural language design request.

        Returns a dict with the conversation history and final design result.
        """
        client = self._get_client()

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": request},
        ]

        results: list[dict[str, Any]] = []

        for turn in range(max_turns):
            logger.info("Agent turn %d", turn + 1)

            response = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=self._tools,
                messages=messages,
            )

            # Check if the model wants to use tools
            if response.stop_reason == "tool_use":
                # Process all tool calls in the response
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
                # Model is done — extract final text
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
