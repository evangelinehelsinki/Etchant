"""CLI entry point for generating KiCad projects."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.constraint_engine import ConstraintEngine
from etchant.core.models import CircuitSpec
from etchant.kicad.netlist_builder import NetlistBuilder, check_skidl_available
from etchant.kicad.project_writer import ProjectWriter


@click.command()
@click.option("--output-dir", "-o", type=click.Path(), default="./output", help="Output directory")
@click.option("--input-voltage", "-vin", type=float, default=12.0, help="Input voltage (V)")
@click.option("--output-voltage", "-vout", type=float, default=5.0, help="Output voltage (V)")
@click.option("--current", "-i", type=float, default=2.0, help="Output current (A)")
@click.option("--validate/--no-validate", default=True, help="Run constraint validation")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(
    output_dir: str,
    input_voltage: float,
    output_voltage: float,
    current: float,
    validate: bool,
    verbose: bool,
) -> None:
    """Generate a KiCad project for an LM2596 buck converter."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    spec = CircuitSpec(
        name=f"lm2596_buck_{int(input_voltage)}v_{int(output_voltage)}v",
        topology="buck_converter",
        input_voltage=input_voltage,
        output_voltage=output_voltage,
        output_current=current,
        description=(
            f"LM2596 buck converter: {input_voltage}V to {output_voltage}V @ {current}A"
        ),
    )

    generator = LM2596BuckConverter()
    click.echo(f"Generating {spec.topology}: {spec.description}")

    try:
        design = generator.generate(spec)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"  Components: {len(design.components)}")
    click.echo(f"  Nets: {len(design.nets)}")

    if validate:
        constraints_dir = Path(__file__).parent.parent / "constraints"
        if constraints_dir.exists():
            engine = ConstraintEngine(constraints_dir)
            violations = engine.validate_design(design)
            if violations:
                click.echo(f"  Violations: {len(violations)}")
                for v in violations:
                    click.echo(f"    [{v.severity}] {v.rule}: {v.message}")
            else:
                click.echo("  Validation: PASS")

    out = Path(output_dir)

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
