"""CLI entry point for generating and comparing KiCad projects."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from etchant.circuits import get_generator, list_topologies
from etchant.core.bom import BOMGenerator, CostBreakdown
from etchant.core.comparison import compare_designs
from etchant.core.constraint_engine import ConstraintEngine, Severity
from etchant.core.manufacturing import check_assembly_compatibility
from etchant.core.models import CircuitSpec
from etchant.core.serialization import load_design, save_design
from etchant.kicad.design_export import DesignExporter
from etchant.kicad.netlist_builder import NetlistBuilder, check_skidl_available
from etchant.kicad.project_writer import ProjectWriter


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Etchant — AI-powered PCB design agent."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--output-dir", "-o", type=click.Path(), default="./output", help="Output directory")
@click.option(
    "--topology", "-t", type=str, default="buck_converter",
    help="Circuit topology (see 'etchant topologies')",
)
@click.option("--input-voltage", "-vin", type=float, default=12.0, help="Input voltage (V)")
@click.option("--output-voltage", "-vout", type=float, default=5.0, help="Output voltage (V)")
@click.option("--current", "-i", type=float, default=2.0, help="Output current (A)")
@click.option("--validate/--no-validate", default=True, help="Run constraint validation")
@click.option("--export-json", is_flag=True, help="Export design as JSON")
@click.option("--export-csv", is_flag=True, help="Export BOM as JLCPCB-compatible CSV")
@click.option("--save", "save_path", type=click.Path(), help="Save design to JSON file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def generate(
    output_dir: str,
    topology: str,
    input_voltage: float,
    output_voltage: float,
    current: float,
    validate: bool,
    export_json: bool,
    export_csv: bool,
    save_path: str | None,
    verbose: bool,
) -> None:
    """Generate a power supply circuit design."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

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

        issues = check_assembly_compatibility(design, constraints_dir)
        for issue in issues:
            click.echo(f"  [{issue['severity']}] {issue['component']}: {issue['issue']}")

    # BOM and cost estimation
    bom_gen = BOMGenerator()
    bom = bom_gen.generate(design)
    cost = CostBreakdown.from_bom(bom)
    click.echo(f"  {cost.summary()}")

    out = Path(output_dir)

    # Save design
    if save_path:
        save_design(design, Path(save_path))
        click.echo(f"  Saved: {save_path}")

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


@cli.command()
def topologies() -> None:
    """List available circuit topologies."""
    for t in list_topologies():
        click.echo(f"  {t}")


@cli.command()
@click.argument("design_a", type=click.Path(exists=True))
@click.argument("design_b", type=click.Path(exists=True))
def compare(design_a: str, design_b: str) -> None:
    """Compare two saved designs and show differences."""
    a = load_design(Path(design_a))
    b = load_design(Path(design_b))

    result = compare_designs(a, b)
    click.echo(result.summary())

    if not result.matches:
        raise SystemExit(1)


# Backwards-compatible entry point for pyproject.toml [project.scripts]
def main() -> None:
    cli()
