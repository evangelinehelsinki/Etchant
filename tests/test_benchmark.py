"""Tests for the benchmark module (structure only, no API calls)."""

from __future__ import annotations

from etchant.agents.benchmark import (
    _TEST_CASES,
    BenchmarkResult,
    format_results,
)


class TestTestCases:
    def test_has_cases(self) -> None:
        assert len(_TEST_CASES) >= 5

    def test_cases_have_required_fields(self) -> None:
        for case in _TEST_CASES:
            assert "prompt" in case
            assert "expected_tools" in case
            assert "description" in case


class TestFormatResults:
    def test_format_empty(self) -> None:
        output = format_results([])
        assert output == ""

    def test_format_with_results(self) -> None:
        results = [
            BenchmarkResult(
                model="test/model",
                test_case="test case",
                tools_called=["list_topologies"],
                expected_tools=["list_topologies"],
                tool_match=True,
                topology_match=None,
                response_length=100,
                turns=2,
                elapsed_seconds=1.5,
            ),
        ]
        output = format_results(results)
        assert "test/model" in output
        assert "PASS" in output
        assert "100%" in output
