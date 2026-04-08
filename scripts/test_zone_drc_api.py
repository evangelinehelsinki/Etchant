"""Check pcbnew API for zones and DRC."""
import pcbnew

print("=== Zone API ===")
for name in ["ZONE", "ZONE_FILLER", "FillAllZones", "ZONE_SETTINGS"]:
    print(f"  {name}: {hasattr(pcbnew, name)}")

print("\n=== DRC API ===")
for name in ["DRC", "DRC_ENGINE", "DRC_ITEM", "BOARD_DRC_ITEMS_PROVIDER"]:
    print(f"  {name}: {hasattr(pcbnew, name)}")

print("\n=== Net API ===")
board = pcbnew.BOARD()
ni = board.GetNetInfo()
print(f"  GetNetInfo: {type(ni)}")
for name in ["NETINFO_ITEM", "NETINFO_LIST"]:
    print(f"  {name}: {hasattr(pcbnew, name)}")

# Try creating a zone
print("\n=== Zone creation test ===")
try:
    zone = pcbnew.ZONE(board)
    print(f"  Zone created: {type(zone)}")
    print(f"  SetLayer: {hasattr(zone, 'SetLayer')}")
    print(f"  SetNetCode: {hasattr(zone, 'SetNetCode')}")
    print(f"  AppendCorner: {hasattr(zone, 'AppendCorner')}")
    print(f"  SetIsFilled: {hasattr(zone, 'SetIsFilled')}")
    zone.SetLayer(pcbnew.F_Cu)
    print("  Layer set to F.Cu")
except Exception as e:
    print(f"  Error: {e}")

# Try DSN export for Freerouting
print("\n=== DSN Export ===")
for name in ["ExportSpecctraFile", "ImportSpecctraFile"]:
    print(f"  Board.{name}: {hasattr(board, name)}")
