"""Benchmark script to evaluate LLM models for Etchant tool use.

Tests each model against a set of standard prompts and grades them on:
- Tool selection accuracy (did it pick the right tool?)
- Argument correctness (did it pass valid parameters?)
- Response quality (did the final answer make sense?)
- Cost per query

Default models to benchmark (all free or cheap via OpenRouter):
- openai/gpt-oss-120b:free       (free, agentic-optimized)
- meta-llama/llama-3.3-70b-instruct:free  (free, Meta flagship)
- deepseek/deepseek-chat-v3-0324 (cheap, strong tool use)
- qwen/qwen3-235b-a22b           (large, good reasoning)

Usage:
    python -m etchant.agents.benchmark --api-key sk-or-...
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from etchant.agents.agent import EtchantAgent

logger = logging.getLogger(__name__)

BENCHMARK_MODELS = [
    "openai/gpt-oss-120b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-chat-v3-0324",
    "qwen/qwen3-235b-a22b",
]

# Standard test prompts with expected tool calls
_TEST_CASES: tuple[dict[str, Any], ...] = (
    {
        "prompt": "I need a 5V to 3.3V power supply for an ESP32, about 500mA",
        "expected_tools": ["suggest_topology", "generate_circuit"],
        "expected_topology": "ldo_regulator",
        "description": "Simple LDO recommendation",
    },
    {
        "prompt": "Design a 12V to 5V 2A buck converter for my Arduino project",
        "expected_tools": ["generate_circuit"],
        "expected_topology": "buck_converter",
        "description": "Direct buck converter request",
    },
    {
        "prompt": "What circuit topologies can you design?",
        "expected_tools": ["list_topologies"],
        "expected_topology": None,
        "description": "Topology listing query",
    },
    {
        "prompt": "How much would a 12V to 5V power supply cost to manufacture at JLCPCB?",
        "expected_tools": ["estimate_cost"],
        "expected_topology": None,
        "description": "Cost estimation query",
    },
    {
        "prompt": (
            "I need a low-noise 3.3V supply from a 5V USB input for a precision ADC. "
            "Noise is the top priority."
        ),
        "expected_tools": ["suggest_topology"],
        "expected_topology": "ldo_regulator",
        "description": "Noise-priority LDO recommendation",
    },
)


@dataclass
class BenchmarkResult:
    """Result from running one test case against one model."""

    model: str
    test_case: str
    tools_called: list[str]
    expected_tools: list[str]
    tool_match: bool
    topology_match: bool | None
    response_length: int
    turns: int
    elapsed_seconds: float
    error: str | None = None


def run_benchmark(
    api_key: str,
    models: list[str],
    base_url: str = "https://openrouter.ai/api/v1",
    constraints_dir: Path | None = None,
    output_dir: Path | None = None,
) -> list[BenchmarkResult]:
    """Run all test cases against all models and return results."""
    results: list[BenchmarkResult] = []

    for model in models:
        agent = EtchantAgent(
            api_key=api_key,
            base_url=base_url,
            model=model,
            constraints_dir=constraints_dir,
            output_dir=output_dir,
        )

        for case in _TEST_CASES:
            logger.info("Testing %s: %s", model, case["description"])
            start = time.monotonic()

            try:
                result = agent.design(case["prompt"], max_turns=5)
                elapsed = time.monotonic() - start

                tools_called = [tc["tool"] for tc in result["tool_calls"]]

                # Check if at least one expected tool was called
                tool_match = any(
                    t in tools_called for t in case["expected_tools"]
                )

                # Check topology if applicable
                topology_match = None
                if case["expected_topology"] is not None:
                    for tc in result["tool_calls"]:
                        if tc["tool"] in ("generate_circuit", "suggest_topology"):
                            output = tc["output"]
                            if isinstance(output, dict):
                                actual_topology = output.get(
                                    "suggested_topology",
                                    output.get("spec", {}).get("topology"),
                                )
                                topology_match = (
                                    actual_topology == case["expected_topology"]
                                )
                                break

                results.append(BenchmarkResult(
                    model=model,
                    test_case=case["description"],
                    tools_called=tools_called,
                    expected_tools=case["expected_tools"],
                    tool_match=tool_match,
                    topology_match=topology_match,
                    response_length=len(result["response"]),
                    turns=result["turns"],
                    elapsed_seconds=round(elapsed, 2),
                ))

            except Exception as e:
                elapsed = time.monotonic() - start
                results.append(BenchmarkResult(
                    model=model,
                    test_case=case["description"],
                    tools_called=[],
                    expected_tools=case["expected_tools"],
                    tool_match=False,
                    topology_match=False,
                    response_length=0,
                    turns=0,
                    elapsed_seconds=round(elapsed, 2),
                    error=str(e),
                ))

    return results


def format_results(results: list[BenchmarkResult]) -> str:
    """Format benchmark results as a readable table."""
    lines: list[str] = []

    # Group by model
    models = sorted({r.model for r in results})

    for model in models:
        model_results = [r for r in results if r.model == model]
        tool_hits = sum(1 for r in model_results if r.tool_match)
        topology_results = [r for r in model_results if r.topology_match is not None]
        topology_hits = sum(1 for r in topology_results if r.topology_match)
        errors = sum(1 for r in model_results if r.error)
        avg_time = sum(r.elapsed_seconds for r in model_results) / len(model_results)

        lines.append(f"\n=== {model} ===")
        lines.append(
            f"  Tool accuracy: {tool_hits}/{len(model_results)} "
            f"({100 * tool_hits / len(model_results):.0f}%)"
        )
        if topology_results:
            lines.append(
                f"  Topology accuracy: {topology_hits}/{len(topology_results)} "
                f"({100 * topology_hits / len(topology_results):.0f}%)"
            )
        lines.append(f"  Avg response time: {avg_time:.1f}s")
        if errors:
            lines.append(f"  Errors: {errors}")

        for r in model_results:
            status = "PASS" if r.tool_match else "FAIL"
            if r.error:
                status = "ERROR"
            lines.append(
                f"  [{status}] {r.test_case} "
                f"(tools: {r.tools_called}, {r.elapsed_seconds}s)"
            )

    return "\n".join(lines)
