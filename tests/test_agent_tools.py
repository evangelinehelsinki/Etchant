"""Tests for agent tool definitions."""

from __future__ import annotations

from etchant.agents.tools import TOOLS, get_tool_definitions_for_api


class TestToolDefinitions:
    def test_tools_not_empty(self) -> None:
        assert len(TOOLS) > 0

    def test_all_tools_have_names(self) -> None:
        for tool in TOOLS:
            assert tool.name
            assert tool.description

    def test_generate_circuit_tool_exists(self) -> None:
        names = {t.name for t in TOOLS}
        assert "generate_circuit" in names
        assert "validate_design" in names
        assert "estimate_cost" in names

    def test_required_params_subset_of_params(self) -> None:
        for tool in TOOLS:
            for req in tool.required_params:
                assert req in tool.parameters, (
                    f"Tool '{tool.name}': required param '{req}' not in parameters"
                )


class TestAPIFormat:
    def test_produces_valid_api_format(self) -> None:
        api_tools = get_tool_definitions_for_api()
        assert len(api_tools) == len(TOOLS)

        for tool in api_tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "properties" in tool["input_schema"]
            assert "required" in tool["input_schema"]

    def test_generate_circuit_schema(self) -> None:
        api_tools = get_tool_definitions_for_api()
        gen_tool = next(t for t in api_tools if t["name"] == "generate_circuit")
        props = gen_tool["input_schema"]["properties"]
        assert "topology" in props
        assert "input_voltage" in props
        assert "output_voltage" in props
        assert "output_current" in props
