"""Quick test of pcbnew API availability."""

import os
import tempfile

import pcbnew

print(f"pcbnew version: {pcbnew.Version()}")

board = pcbnew.BOARD()
print("Board created")

# Check API presence
for name in [
    "NETLIST", "BOARD_NETLIST_UPDATER", "PCB_SHAPE",
    "VECTOR2I", "FromMM", "ToMM", "Edge_Cuts",
    "FOOTPRINT", "LoadBoard",
]:
    print(f"  {name}: {hasattr(pcbnew, name)}")

# Try basic placement
fp = pcbnew.FOOTPRINT(board)
fp.SetReference("R1")
pos = pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(15))
fp.SetPosition(pos)
x = pcbnew.ToMM(fp.GetPosition().x)
y = pcbnew.ToMM(fp.GetPosition().y)
print(f"Footprint R1 placed at ({x}, {y})")

# Try board outline
shape = pcbnew.PCB_SHAPE(board)
shape.SetLayer(pcbnew.Edge_Cuts)
shape.SetStart(pcbnew.VECTOR2I(0, 0))
shape.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(30), 0))
shape.SetWidth(pcbnew.FromMM(0.1))
board.Add(shape)
print("Board outline added")

# Save
tmp = tempfile.mktemp(suffix=".kicad_pcb")
board.Save(tmp)
size = os.path.getsize(tmp)
print(f"Board saved: {size} bytes at {tmp}")
os.unlink(tmp)

# Try loading a netlist
has_netlist_api = hasattr(pcbnew, "NETLIST")
print(f"\nNetlist import available: {has_netlist_api}")
if not has_netlist_api:
    print("Will need alternative netlist import method")
    # Check for kicad-cli or other options
    print(f"LoadBoard available: {hasattr(pcbnew, 'LoadBoard')}")

print("\npcbnew API test complete!")
