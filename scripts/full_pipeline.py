"""Run the full Etchant pipeline: spec -> design -> netlist -> PCB -> zip."""

import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, "/home/evangeline/Projects/etchant")

os.environ["KICAD_SYMBOL_DIR"] = "/usr/share/kicad/symbols"
os.environ["KICAD8_SYMBOL_DIR"] = "/usr/share/kicad/symbols"
os.environ["KICAD9_SYMBOL_DIR"] = "/usr/share/kicad/symbols"

from etchant.circuits.generative_buck import GenerativeBuckConverter
from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.core.bom import BOMGenerator, CostBreakdown
from etchant.core.constraint_engine import ConstraintEngine, Severity
from etchant.core.models import CircuitSpec
from etchant.core.serialization import save_design
from etchant.kicad.design_export import DesignExporter
from etchant.kicad.placement import ComponentPlacer

# Patch SKiDL before import
exec(open("/home/evangeline/Projects/etchant/scripts/patch_skidl.py").read())

import skidl
skidl.lib_search_paths[skidl.KICAD].append("/usr/share/kicad/symbols")

from etchant.kicad.netlist_builder import NetlistBuilder
from etchant.kicad.project_writer import ProjectWriter

OUTPUT_BASE = Path("/home/evangeline/Projects/etchant/output/demo")


def run_design(name, topology_cls, vin, vout, iout):
    print(f"\n{'='*60}")
    print(f"  {name}: {vin}V -> {vout}V @ {iout}A")
    print(f"{'='*60}")

    spec = CircuitSpec(
        name=name,
        topology=topology_cls().topology,
        input_voltage=vin,
        output_voltage=vout,
        output_current=iout,
        description=f"{name}: {vin}V to {vout}V @ {iout}A",
    )

    out_dir = OUTPUT_BASE / name

    # Generate design
    gen = topology_cls()
    design = gen.generate(spec)
    print(f"  Components: {len(design.components)}")
    print(f"  Nets: {len(design.nets)}")

    # Validate
    constraints_dir = Path("/home/evangeline/Projects/etchant/constraints")
    engine = ConstraintEngine(constraints_dir)
    violations = engine.validate_design(design)
    errors = [v for v in violations if v.severity == Severity.ERROR]
    print(f"  Validation: {'PASS' if not errors else f'{len(errors)} errors'}")

    # BOM
    bom = BOMGenerator().generate(design)
    cost = CostBreakdown.from_bom(bom)
    print(f"  BOM: {cost.basic_parts_count} basic, {cost.extended_parts_count} extended")
    print(f"  Setup fee: ${cost.total_setup_fee_usd:.2f}")

    # Save design JSON
    save_design(design, out_dir / f"{name}.json")
    print(f"  Design JSON: {out_dir / f'{name}.json'}")

    # Export BOM CSV
    exporter = DesignExporter(out_dir)
    csv_path = exporter.export_bom_csv(design)
    print(f"  BOM CSV: {csv_path}")

    # Generate netlist
    builder = NetlistBuilder(out_dir)
    netlist_path = builder.build(design)
    print(f"  Netlist: {netlist_path} ({netlist_path.stat().st_size} bytes)")

    # Create KiCad project
    writer = ProjectWriter(out_dir)
    pro_path = writer.write_project(design, netlist_path)
    print(f"  Project: {pro_path}")

    # Place components on PCB
    placer = ComponentPlacer()
    pcb_path = out_dir / name / f"{name}.kicad_pcb"
    placer.create_board(design, pcb_path)
    print(f"  PCB: {pcb_path} ({pcb_path.stat().st_size} bytes)")

    # Autoroute with Freerouting
    from etchant.kicad.router import FreeroutingRouter, check_freerouting_available
    if check_freerouting_available():
        router = FreeroutingRouter(max_passes=20)
        try:
            router.route_board(pcb_path)
            print(f"  Routed: {pcb_path.stat().st_size} bytes (Freerouting)")
        except Exception as e:
            print(f"  Routing failed: {e}")
    else:
        print("  Routing skipped: Freerouting not available")

    # Render PCB as SVG for visual inspection
    svg_path = pcb_path.with_suffix(".svg")
    try:
        import subprocess
        subprocess.run([
            "kicad-cli", "pcb", "export", "svg",
            "--layers", "F.Cu,B.Cu,Edge.Cuts,F.SilkS",
            "--fit-page-to-board",
            "--exclude-drawing-sheet",
            "-o", str(svg_path),
            str(pcb_path),
        ], capture_output=True, timeout=30)
        if svg_path.exists():
            print(f"  Render: {svg_path} ({svg_path.stat().st_size} bytes)")
    except Exception as e:
        print(f"  Render skipped: {e}")

    # Design notes
    for note in design.design_notes:
        print(f"  Note: {note}")

    return out_dir


# Run demo designs
dirs = []

dirs.append(run_design(
    "ldo_5v_to_3v3",
    AMS1117LDORegulator,
    5.0, 3.3, 0.5,
))

dirs.append(run_design(
    "buck_12v_to_5v",
    GenerativeBuckConverter,
    12.0, 5.0, 2.0,
))

from etchant.circuits.led_driver import LEDDriverCircuit
dirs.append(run_design(
    "led_5v_20ma",
    LEDDriverCircuit,
    5.0, 2.0, 0.02,
))

from etchant.circuits.mcu_breakout import ESP32C3Breakout
dirs.append(run_design(
    "esp32c3_breakout",
    ESP32C3Breakout,
    5.0, 3.3, 0.5,
))

# Zip everything
zip_path = OUTPUT_BASE / "etchant_demo.zip"
print(f"\n{'='*60}")
print(f"  Creating zip: {zip_path}")
print(f"{'='*60}")

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for d in dirs:
        for root, _, files in os.walk(d):
            for f in files:
                filepath = Path(root) / f
                arcname = filepath.relative_to(OUTPUT_BASE)
                zf.write(filepath, arcname)

print(f"  Zip size: {zip_path.stat().st_size} bytes")
print(f"\n  Done! Copy {zip_path} to your main machine and open in KiCad.")
