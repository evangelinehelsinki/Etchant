"""End-to-end integration tests exercising the full pipeline.

These tests verify that the complete flow works from CLI invocation
through design generation, validation, BOM, and export.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from etchant.agents.executor import ToolExecutor
from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.cli import cli
from etchant.core.bom import BOMGenerator, CostBreakdown
from etchant.core.comparison import compare_designs
from etchant.core.constraint_engine import ConstraintEngine, Severity
from etchant.core.models import CircuitSpec
from etchant.core.serialization import load_design, save_design
from etchant.core.topology_advisor import recommend_topology


class TestFullPipelineBuck:
    """End-to-end test for the buck converter pipeline."""

    def test_generate_validate_cost_export(
        self, tmp_path: Path, constraints_dir: Path
    ) -> None:
        spec = CircuitSpec(
            name="integration_buck",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="Integration test buck converter",
        )

        # Generate
        design = LM2596BuckConverter().generate(spec)
        assert len(design.components) == 6

        # Validate
        engine = ConstraintEngine(constraints_dir)
        violations = engine.validate_design(design)
        errors = [v for v in violations if v.severity == Severity.ERROR]
        assert len(errors) == 0

        # BOM + Cost
        bom = BOMGenerator().generate(design)
        cost = CostBreakdown.from_bom(bom)
        assert cost.total_setup_fee_usd == 12.0  # 4 extended parts

        # Save and reload
        path = tmp_path / "buck.json"
        save_design(design, path)
        loaded = load_design(path)
        result = compare_designs(loaded, design)
        assert result.matches


class TestFullPipelineLDO:
    """End-to-end test for the LDO pipeline."""

    def test_generate_validate_cost_export(
        self, tmp_path: Path, constraints_dir: Path
    ) -> None:
        spec = CircuitSpec(
            name="integration_ldo",
            topology="ldo_regulator",
            input_voltage=5.0,
            output_voltage=3.3,
            output_current=0.5,
            description="Integration test LDO",
        )

        design = AMS1117LDORegulator().generate(spec)
        # 3 active parts (U1, C1, C2) + J1 (VIN input) + J2 (VOUT output)
        assert len(design.components) == 5

        engine = ConstraintEngine(constraints_dir)
        violations = engine.validate_design(design)
        errors = [v for v in violations if v.severity == Severity.ERROR]
        assert len(errors) == 0

        bom = BOMGenerator().generate(design)
        cost = CostBreakdown.from_bom(bom)
        # 3 basic SMD parts + 2 pin headers (not in JLCPCB basic parts table
        # → counted as unknown → $3 setup each).
        assert cost.total_setup_fee_usd == 6.0

        path = tmp_path / "ldo.json"
        save_design(design, path)
        loaded = load_design(path)
        result = compare_designs(loaded, design)
        assert result.matches


class TestTopologyAdvisorToGeneration:
    """Test that the advisor's recommendation leads to successful generation."""

    def test_advisor_to_generate_5v_to_3v3(self) -> None:
        rec = recommend_topology(5.0, 3.3, 0.5)
        spec = CircuitSpec(
            name="advisor_test",
            topology=rec.topology,
            input_voltage=5.0,
            output_voltage=3.3,
            output_current=0.5,
            description="Advisor integration test",
        )

        from etchant.circuits import get_generator

        generator = get_generator(rec.topology)
        design = generator.generate(spec)
        assert len(design.components) > 0

    def test_advisor_to_generate_12v_to_5v(self) -> None:
        rec = recommend_topology(12.0, 5.0, 2.0)
        assert rec.topology == "buck_converter"

        spec = CircuitSpec(
            name="advisor_test",
            topology=rec.topology,
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="Advisor integration test",
        )

        from etchant.circuits import get_generator

        generator = get_generator(rec.topology)
        design = generator.generate(spec)
        # 6 active parts (U1, C1, C2, L1, R1, R2) + J1 (VIN) + J2 (VOUT)
        assert len(design.components) == 8


class TestExecutorIntegration:
    """Test the agent executor with real pipeline calls."""

    def test_full_workflow(self, constraints_dir: Path, tmp_path: Path) -> None:
        executor = ToolExecutor(
            constraints_dir=constraints_dir, output_dir=tmp_path
        )

        # Step 1: Suggest topology
        suggestion = executor.execute("suggest_topology", {
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 2.0,
        })
        assert suggestion["suggested_topology"] == "buck_converter"

        # Step 2: Generate circuit
        design = executor.execute("generate_circuit", {
            "topology": "buck_converter",
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 2.0,
        })
        assert "error" not in design
        # 6 active parts + J1 (VIN) + J2 (VOUT)
        assert len(design["components"]) == 8

        # Step 3: Validate
        validation = executor.execute("validate_design", {
            "topology": "buck_converter",
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 2.0,
        })
        assert len(validation["errors"]) == 0

        # Step 4: Estimate cost
        cost = executor.execute("estimate_cost", {
            "topology": "buck_converter",
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 2.0,
        })
        # 4 extended SMD parts ($3 each) + 2 pin headers (unknown, $3 each) = $18
        assert cost["bom"]["assembly_setup_fee_usd"] == 18.0

        # Step 5: Export
        export = executor.execute("export_design", {
            "topology": "buck_converter",
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 2.0,
            "format": "both",
            "output_dir": str(tmp_path),
        })
        assert len(export["exported"]) == 2


class TestCLIIntegration:
    """Test CLI end-to-end with file output verification."""

    def test_generate_and_compare_roundtrip(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            # Generate two identical designs
            r1 = runner.invoke(cli, ["generate", "--save", "a.json"])
            assert r1.exit_code == 0

            r2 = runner.invoke(cli, ["generate", "--save", "b.json"])
            assert r2.exit_code == 0

            # Compare — should match
            r3 = runner.invoke(cli, ["compare", "a.json", "b.json"])
            assert r3.exit_code == 0

    def test_export_json_produces_valid_file(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["generate", "--export-json", "-o", "."]
            )
            assert result.exit_code == 0

            # Find the JSON file
            json_files = list(Path(".").glob("*.json"))
            assert len(json_files) >= 1

            with open(json_files[0]) as f:
                data = json.load(f)
            assert "components" in data
            assert "nets" in data
