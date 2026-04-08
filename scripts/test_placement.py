"""Test PCB placement end-to-end inside distrobox."""

import sys
sys.path.insert(0, "/home/evangeline/Projects/etchant")

from pathlib import Path

from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.core.models import CircuitSpec
from etchant.kicad.placement import ComponentPlacer, check_pcbnew_available

print(f"pcbnew available: {check_pcbnew_available()}")

if not check_pcbnew_available():
    print("Run inside distrobox with system python3")
    sys.exit(1)

# Generate a simple LDO design
spec = CircuitSpec(
    name="placement_test",
    topology="ldo_regulator",
    input_voltage=5.0,
    output_voltage=3.3,
    output_current=0.5,
    description="Placement test",
)
design = AMS1117LDORegulator().generate(spec)
print(f"Design: {len(design.components)} components")

# Place components
placer = ComponentPlacer()
output = Path("/tmp/etchant_placement_test.kicad_pcb")
result = placer.create_board(design, output)

print(f"Board created: {result}")
print(f"Size: {result.stat().st_size} bytes")
print("SUCCESS!")
