"""Tool executor for the LLM agent layer.

Maps tool call names to actual pipeline functions. The agent sends a tool name
and arguments; the executor runs the corresponding pipeline operation and returns
a structured result.

This is the bridge between the LLM's tool_use calls and the Etchant pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from etchant.circuits import get_generator, list_topologies
from etchant.core.bom import BOMGenerator, CostBreakdown
from etchant.core.component_selector import lookup_jlcpcb_part
from etchant.core.constraint_engine import ConstraintEngine, Severity
from etchant.core.manufacturing import check_assembly_compatibility, estimate_board_cost
from etchant.core.models import CircuitSpec
from etchant.core.topology_advisor import recommend_topology
from etchant.kicad.design_export import DesignExporter


class ToolExecutor:
    """Executes tool calls from the LLM agent."""

    def __init__(self, constraints_dir: Path | None = None, output_dir: Path | None = None) -> None:
        default_constraints = Path(__file__).parent.parent.parent / "constraints"
        self._constraints_dir = constraints_dir or default_constraints
        self._output_dir = output_dir or Path("./output")

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call and return the result as a dict."""
        handlers = {
            "list_topologies": self._list_topologies,
            "generate_circuit": self._generate_circuit,
            "validate_design": self._validate_design,
            "estimate_cost": self._estimate_cost,
            "lookup_jlcpcb_part": self._lookup_part,
            "suggest_topology": self._suggest_topology,
            "export_design": self._export_design,
        }

        handler = handlers.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return handler(arguments)
        except Exception as e:
            return {"error": str(e)}

    def _list_topologies(self, _args: dict[str, Any]) -> dict[str, Any]:
        return {"topologies": list(list_topologies())}

    def _generate_circuit(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self._make_spec(args)
        generator = get_generator(spec.topology)
        design = generator.generate(spec)

        return {
            "spec": {
                "name": design.spec.name,
                "topology": design.spec.topology,
                "input_voltage": design.spec.input_voltage,
                "output_voltage": design.spec.output_voltage,
                "output_current": design.spec.output_current,
            },
            "components": [
                {
                    "reference": c.reference,
                    "value": c.value,
                    "category": c.category.name,
                    "footprint": c.footprint,
                    "description": c.description,
                }
                for c in design.components
            ],
            "nets": [
                {"name": n.name, "connection_count": len(n.connections)}
                for n in design.nets
            ],
            "placement_constraints": len(design.placement_constraints),
            "design_notes": list(design.design_notes),
        }

    def _validate_design(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self._make_spec(args)
        generator = get_generator(spec.topology)
        design = generator.generate(spec)

        engine = ConstraintEngine(self._constraints_dir)
        violations = engine.validate_design(design)

        issues = check_assembly_compatibility(design, self._constraints_dir)

        return {
            "errors": [
                {"rule": v.rule, "message": v.message}
                for v in violations if v.severity == Severity.ERROR
            ],
            "warnings": [
                {"rule": v.rule, "message": v.message}
                for v in violations if v.severity == Severity.WARNING
            ],
            "info": [
                {"rule": v.rule, "message": v.message}
                for v in violations if v.severity == Severity.INFO
            ],
            "assembly_issues": issues,
        }

    def _estimate_cost(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self._make_spec(args)
        generator = get_generator(spec.topology)
        design = generator.generate(spec)

        bom_gen = BOMGenerator()
        bom = bom_gen.generate(design)
        cost = CostBreakdown.from_bom(bom)

        board_cost = estimate_board_cost(
            board_size_mm=(
                args.get("board_width_mm", 50.0),
                args.get("board_height_mm", 50.0),
            ),
            layers=2,
            quantity=args.get("quantity", 5),
        )

        return {
            "bom": {
                "total_parts": len(bom),
                "basic_parts": cost.basic_parts_count,
                "extended_parts": cost.extended_parts_count,
                "unknown_parts": cost.unknown_parts_count,
                "assembly_setup_fee_usd": cost.total_setup_fee_usd,
            },
            "board": board_cost,
            "summary": cost.summary(),
        }

    def _lookup_part(self, args: dict[str, Any]) -> dict[str, Any]:
        value = args.get("value", "")
        info = lookup_jlcpcb_part(value)
        if info is None:
            return {"found": False, "value": value}
        return {
            "found": True,
            "value": value,
            "part_number": info.part_number,
            "classification": info.classification.value,
            "description": info.description,
            "stock": info.stock,
            "setup_fee_usd": info.setup_fee_usd,
        }

    def _suggest_topology(self, args: dict[str, Any]) -> dict[str, Any]:
        vin = args.get("input_voltage")
        vout = args.get("output_voltage")
        iout = args.get("output_current")
        priority = args.get("priority", "balanced")

        if vin is not None and vout is not None and iout is not None:
            rec = recommend_topology(vin, vout, iout, priority=priority)
            return {
                "suggested_topology": rec.topology,
                "confidence": rec.confidence,
                "reason": rec.reason,
                "tradeoffs": list(rec.tradeoffs),
                "alternatives": list(rec.alternatives),
            }

        desc = args.get("description", "").lower()

        if any(w in desc for w in ("low noise", "ldo", "linear", "low dropout")):
            return {
                "suggested_topology": "ldo_regulator",
                "reason": "LDO regulators provide clean, low-noise output",
            }

        if any(w in desc for w in ("efficient", "high current", "step down", "buck")):
            return {
                "suggested_topology": "buck_converter",
                "reason": "Buck converters are highly efficient (85-95%)",
            }

        return {
            "suggested_topology": "buck_converter",
            "reason": "Default — use LDO if noise is critical",
            "available_topologies": list(list_topologies()),
        }

    def _export_design(self, args: dict[str, Any]) -> dict[str, Any]:
        spec = self._make_spec(args)
        generator = get_generator(spec.topology)
        design = generator.generate(spec)

        export_format = args.get("format", "both")
        out_dir = Path(args.get("output_dir", str(self._output_dir)))
        exporter = DesignExporter(out_dir)

        result: dict[str, Any] = {"exported": []}

        if export_format in ("json", "both"):
            json_path = exporter.export_json(design)
            result["exported"].append({"format": "json", "path": str(json_path)})

        if export_format in ("csv", "both"):
            csv_path = exporter.export_bom_csv(design)
            result["exported"].append({"format": "csv", "path": str(csv_path)})

        return result

    def _make_spec(self, args: dict[str, Any]) -> CircuitSpec:
        topology = args["topology"]
        vin = args["input_voltage"]
        vout = args["output_voltage"]
        iout = args["output_current"]
        return CircuitSpec(
            name=f"{topology}_{int(vin)}v_{int(vout)}v",
            topology=topology,
            input_voltage=vin,
            output_voltage=vout,
            output_current=iout,
            description=f"{topology}: {vin}V to {vout}V @ {iout}A",
        )
