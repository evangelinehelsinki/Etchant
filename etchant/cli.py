"""CLI entry point for generating KiCad projects."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from etchant.circuits import get_generator, list_topologies
from etchant.core.bom import BOMGenerator, CostBreakdown
from etchant.core.constraint_engine import ConstraintEngine, Severity
from etchant.core.manufacturing import check_assembly_compatibility
from etchant.core.models import CircuitSpec
from etchant.kicad.design_export import DesignExporter
from etchant.kicad.netlist_builder import NetlistBuilder, check_skidl_available
from etchant.kicad.project_writer import ProjectWriter


@click.command()
@click.option("--output-dir", "-o", type=click.Path(), default="./output", help="Output directory")
@click.option(
    "--topology", "-t", type=str, default="buck_converter",
    help="Circuit topology (see --list-topologies)",
)
@click.option("--input-voltage", "-vin", type=float, default=12.0, help="Input voltage (V)")
@click.option("--output-voltage", "-vout", type=float, default=5.0, help="Output voltage (V)")
@click.option("--current", "-i", type=float, default=2.0, help="Output current (A)")
@click.option("--validate/--no-validate", default=True, help="Run constraint validation")
@click.option(
    "--list-topologies", "show_topologies", is_flag=True, help="List available topologies",
)
@click.option("--export-json", is_flag=True, help="Export design as JSON")
@click.option("--export-csv", is_flag=True, help="Export BOM as JLCPCB-compatible CSV")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(
    output_dir: str,
    topology: str,
    input_voltage: float,
    output_voltage: float,
    current: float,
    validate: bool,
    show_topologies: bool,
    export_json: bool,
    export_csv: bool,
    verbose: bool,
) -> None:
    """Generate a KiCad project for a power supply circuit."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    if show_topologies:
        click.echo("Available topologies:")
        for t in list_topologies():
            click.echo(f"  {t}")
        return

    try:
        generator = get_generator(topology)
    except KeyError as e:
        raise click.ClickException(str(e)) from e

    spec = CircuitSpec(
        name=f"{topology}_{int(input_voltage)}v_{int(output_voltage)}v",
        topology=topology,
        input_voltage=input_voltage,
        output_voltage=output_voltage,
        output_current=current,
        description=f"{topology}: {input_voltage}V to {output_voltage}V @ {current}A",
    )

    click.echo(f"Generating {spec.topology}: {spec.description}")

    try:
        design = generator.generate(spec)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"  Components: {len(design.components)}")
    click.echo(f"  Nets: {len(design.nets)}")

    constraints_dir = Path(__file__).parent.parent / "constraints"

    if validate and constraints_dir.exists():
        engine = ConstraintEngine(constraints_dir)
        all_results = engine.validate_design(design)
        errors_warnings = [v for v in all_results if v.severity != Severity.INFO]
        info_items = [v for v in all_results if v.severity == Severity.INFO]

        if errors_warnings:
            click.echo(f"  Violations: {len(errors_warnings)}")
            for v in errors_warnings:
                click.echo(f"    [{v.severity.value}] {v.rule}: {v.message}")
        else:
            click.echo("  Validation: PASS")

        for v in info_items:
            click.echo(f"  Note: {v.message}")

        # Assembly compatibility
        issues = check_assembly_compatibility(design, constraints_dir)
        for issue in issues:
            click.echo(f"  [{issue['severity']}] {issue['component']}: {issue['issue']}")

    # BOM and cost estimation
    bom_gen = BOMGenerator()
    bom = bom_gen.generate(design)
    cost = CostBreakdown.from_bom(bom)
    click.echo(f"  {cost.summary()}")

    out = Path(output_dir)

    # Export design files
    if export_json or export_csv:
        exporter = DesignExporter(out)
        if export_json:
            json_path = exporter.export_json(design)
            click.echo(f"  JSON: {json_path}")
        if export_csv:
            csv_path = exporter.export_bom_csv(design)
            click.echo(f"  BOM CSV: {csv_path}")

    # KiCad netlist generation
    if check_skidl_available():
        builder = NetlistBuilder(out)
        netlist_path = builder.build(design)
        click.echo(f"  Netlist: {netlist_path}")

        writer = ProjectWriter(out)
        pro_path = writer.write_project(design, netlist_path)
        click.echo(f"  Project: {pro_path}")
    else:
        click.echo("  SKiDL not available — skipping netlist generation.")
        click.echo("  Run inside distrobox for full output. See setup-distrobox.sh")


if __name__ == "__main__":
    main()
