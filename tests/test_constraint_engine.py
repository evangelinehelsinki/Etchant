"""Tests for the constraint engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from etchant.core.constraint_engine import ConstraintEngine, ConstraintViolation, Severity
from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)


@pytest.fixture
def engine(constraints_dir: Path) -> ConstraintEngine:
    return ConstraintEngine(constraints_dir)


class TestLoadRules:
    def test_load_manufacturing_rules(self, engine: ConstraintEngine) -> None:
        rules = engine.load_manufacturing_rules()
        assert rules["manufacturer"] == "JLCPCB"
        assert "capabilities" in rules
        assert "traces" in rules["capabilities"]

    def test_load_design_rules(self, engine: ConstraintEngine) -> None:
        rules = engine.load_design_rules()
        assert "trace_width" in rules
        assert "clearance" in rules

    def test_load_layout_rules_lm2596(self, engine: ConstraintEngine) -> None:
        rules = engine.load_layout_rules("lm2596")
        assert rules["ic"] == "LM2596"
        assert "placement_constraints" in rules
        assert "routing_rules" in rules

    def test_load_nonexistent_ic_raises(self, engine: ConstraintEngine) -> None:
        with pytest.raises(FileNotFoundError):
            engine.load_layout_rules("nonexistent_ic")

    def test_path_traversal_rejected(self, engine: ConstraintEngine) -> None:
        with pytest.raises(ValueError, match="escapes constraints directory"):
            engine.load_layout_rules("../../etc/passwd")


class TestValidateDesign:
    @pytest.fixture
    def valid_design(self, lm2596_spec: CircuitSpec) -> DesignResult:
        return DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="LM2596S-5",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
                ComponentSpec(
                    reference="C1",
                    category=ComponentCategory.CAPACITOR,
                    value="680uF",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="VIN", connections=(("C1", "1"), ("U1", "IN"))),
                NetSpec(name="GND", connections=(("C1", "2"), ("U1", "GND"))),
            ),
            placement_constraints=(
                PlacementConstraint(
                    component_ref="C1",
                    target_ref="U1",
                    max_distance_mm=50.0,
                    reason="test",
                ),
            ),
            design_notes=("test note",),
        )

    def test_valid_design_no_errors_or_warnings(
        self, engine: ConstraintEngine, valid_design: DesignResult
    ) -> None:
        violations = engine.validate_design(valid_design)
        errors_warnings = [v for v in violations if v.severity != Severity.INFO]
        assert errors_warnings == []

    def test_empty_design_has_violations(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        empty = DesignResult(
            spec=lm2596_spec,
            components=(),
            nets=(),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(empty)
        assert len(violations) > 0
        assert any(v.rule == "min_components" for v in violations)

    def test_placement_referencing_missing_component(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(),
            placement_constraints=(
                PlacementConstraint(
                    component_ref="MISSING",
                    target_ref="U1",
                    max_distance_mm=10.0,
                    reason="test",
                ),
            ),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        assert any(v.rule == "placement_component_exists" for v in violations)

    def test_net_referencing_missing_component(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="VIN", connections=(("MISSING", "1"), ("U1", "IN"))),
            ),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        assert any(v.rule == "net_component_exists" for v in violations)


class TestTraceWidthValidation:
    def test_high_current_warns_about_trace_width(
        self, engine: ConstraintEngine
    ) -> None:
        """A 5A design should get a warning about trace width requirements."""
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=5.0,
            description="test",
        )
        design = DesignResult(
            spec=spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="VIN", connections=(("U1", "IN"),)),
            ),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        trace_violations = [v for v in violations if v.rule == "trace_width_recommendation"]
        assert len(trace_violations) > 0
        assert any("5.0A" in v.message for v in trace_violations)

    def test_normal_current_gets_info(
        self, engine: ConstraintEngine
    ) -> None:
        """A 2A design should still get an info-level trace width note."""
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test",
        )
        design = DesignResult(
            spec=spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="VIN", connections=(("U1", "IN"),)),
            ),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        trace_info = [v for v in violations if v.rule == "trace_width_recommendation"]
        assert len(trace_info) > 0


class TestSinglePinNetDetection:
    def test_single_pin_net_warning(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        """A net with only one connection should produce a warning."""
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="DANGLING", connections=(("U1", "IN"),)),
            ),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        dangling = [v for v in violations if v.rule == "single_pin_net"]
        assert len(dangling) == 1
        assert "DANGLING" in dangling[0].message


class TestPowerNets:
    def test_missing_ground_warning(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="VIN", connections=(("U1", "IN"),)),
            ),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        assert any(v.rule == "ground_net_missing" for v in violations)

    def test_gnd_net_passes(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(
                NetSpec(name="GND", connections=(("U1", "GND"),)),
            ),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        assert not any(v.rule == "ground_net_missing" for v in violations)


class TestDuplicateReferences:
    def test_duplicate_reference_detected(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test2",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="duplicate",
                ),
            ),
            nets=(),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        assert any(v.rule == "duplicate_reference" for v in violations)

    def test_no_duplicates_passes(
        self, engine: ConstraintEngine, lm2596_spec: CircuitSpec
    ) -> None:
        design = DesignResult(
            spec=lm2596_spec,
            components=(
                ComponentSpec(
                    reference="U1",
                    category=ComponentCategory.IC,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
                ComponentSpec(
                    reference="C1",
                    category=ComponentCategory.CAPACITOR,
                    value="test",
                    footprint="test",
                    kicad_library="test",
                    kicad_symbol="test",
                    description="test",
                ),
            ),
            nets=(),
            placement_constraints=(),
            design_notes=(),
        )
        violations = engine.validate_design(design)
        dup_violations = [v for v in violations if v.rule == "duplicate_reference"]
        assert len(dup_violations) == 0


class TestConstraintViolation:
    def test_frozen(self) -> None:
        v = ConstraintViolation(
            rule="test",
            severity=Severity.ERROR,
            message="test message",
        )
        with pytest.raises(AttributeError):
            v.rule = "modified"  # type: ignore[misc]

    def test_optional_component_ref(self) -> None:
        v = ConstraintViolation(
            rule="test",
            severity=Severity.WARNING,
            message="test",
        )
        assert v.component_ref is None

    def test_severity_enum_values(self) -> None:
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"
