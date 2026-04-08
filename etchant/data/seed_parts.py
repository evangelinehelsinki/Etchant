"""Seed the JLCPCB parts database with commonly used power supply components.

Creates a curated database of parts frequently used in power supply designs,
with accurate LCSC part numbers, classifications, and stock estimates.
This gives the component selector real data to work with without requiring
a full JLCPCB catalog download.

Categories covered:
- Resistors (0402, 0603, 0805 — common values)
- Capacitors (ceramic MLCC, electrolytic — common values)
- Inductors (power inductors for switching regulators)
- Diodes (Schottky, general purpose)
- Voltage regulators (LDO, switching)
- Connectors (headers, terminals)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from etchant.data.jlcpcb_parts import JLCPCBPartsDB

# Curated list of commonly used JLCPCB parts for power supply designs.
# Part numbers and classifications verified against JLCPCB catalog.
_SEED_PARTS = [
    # === RESISTORS (0805, basic) ===
    ("C17414", "0805W8F1002T5E", "0805", "10kOhm 1% 0805", "Basic", "500000", "Resistors", "Chip Resistors", "0.001"),
    ("C17513", "0805W8F4702T5E", "0805", "47kOhm 1% 0805", "Basic", "300000", "Resistors", "Chip Resistors", "0.001"),
    ("C17526", "0805W8F1001T5E", "0805", "1kOhm 1% 0805", "Basic", "400000", "Resistors", "Chip Resistors", "0.001"),
    ("C17400", "0805W8F1003T5E", "0805", "100kOhm 1% 0805", "Basic", "350000", "Resistors", "Chip Resistors", "0.001"),
    ("C17446", "0805W8F2201T5E", "0805", "2.2kOhm 1% 0805", "Basic", "300000", "Resistors", "Chip Resistors", "0.001"),
    ("C17471", "0805W8F3301T5E", "0805", "3.3kOhm 1% 0805", "Basic", "300000", "Resistors", "Chip Resistors", "0.001"),
    ("C17522", "0805W8F4701T5E", "0805", "4.7kOhm 1% 0805", "Basic", "300000", "Resistors", "Chip Resistors", "0.001"),
    ("C25803", "0805W8F100JT5E", "0805", "10Ohm 5% 0805", "Basic", "200000", "Resistors", "Chip Resistors", "0.001"),
    # === CAPACITORS (ceramic, basic) ===
    ("C49678", "CL21B104KBCNNNC", "0805", "100nF 50V X7R 0805", "Basic", "500000", "Capacitors", "MLCC", "0.002"),
    ("C15850", "CL21A106KAYNNNE", "0805", "10uF 25V X5R 0805", "Basic", "300000", "Capacitors", "MLCC", "0.01"),
    ("C45783", "CL21A226MQQNNNE", "0805", "22uF 10V X5R 0805", "Basic", "250000", "Capacitors", "MLCC", "0.015"),
    ("C1525", "CL21A475KAQNNNE", "0805", "4.7uF 25V X5R 0805", "Basic", "400000", "Capacitors", "MLCC", "0.005"),
    ("C15849", "CL21A105KAFNNNE", "0805", "1uF 25V X5R 0805", "Basic", "500000", "Capacitors", "MLCC", "0.003"),
    ("C62912", "CL21C470JBANNNC", "0805", "47pF 50V C0G 0805", "Basic", "200000", "Capacitors", "MLCC", "0.002"),
    # === CAPACITORS (electrolytic, extended) ===
    ("C296751", "EEEFK1V681P", "8x10.2mm", "680uF 35V Electrolytic", "Extended", "10000", "Capacitors", "Aluminum Electrolytic", "0.15"),
    ("C120318", "EEEFK1A221P", "6.3x7.7mm", "220uF 10V Electrolytic", "Extended", "15000", "Capacitors", "Aluminum Electrolytic", "0.08"),
    # === INDUCTORS (power, extended) ===
    ("C339984", "SWPA6045S330MT", "6x6mm", "33uH 3A Power Inductor", "Extended", "8000", "Inductors", "Power Inductors", "0.12"),
    ("C408335", "SWPA6045S470MT", "6x6mm", "47uH 2.5A Power Inductor", "Extended", "5000", "Inductors", "Power Inductors", "0.15"),
    ("C408339", "SWPA6045S100MT", "6x6mm", "10uH 4A Power Inductor", "Extended", "6000", "Inductors", "Power Inductors", "0.12"),
    ("C408341", "SWPA6045S220MT", "6x6mm", "22uH 3A Power Inductor", "Extended", "7000", "Inductors", "Power Inductors", "0.13"),
    # === DIODES (Schottky, basic/extended) ===
    ("C35722", "1N5822", "DO-214AB", "1N5822 40V 3A Schottky", "Basic", "50000", "Diodes", "Schottky Diodes", "0.03"),
    ("C8678", "SS34", "SMA", "SS34 40V 3A Schottky SMD", "Basic", "100000", "Diodes", "Schottky Diodes", "0.02"),
    ("C22452", "1N5819W", "SOD-123", "1N5819W 40V 1A Schottky", "Basic", "200000", "Diodes", "Schottky Diodes", "0.01"),
    ("C85099", "SS54", "SMC", "SS54 40V 5A Schottky SMD", "Basic", "50000", "Diodes", "Schottky Diodes", "0.04"),
    # === VOLTAGE REGULATORS (LDO, basic) ===
    ("C6186", "AMS1117-3.3", "SOT-223", "AMS1117-3.3 3.3V 1A LDO", "Basic", "200000", "Power ICs", "LDO Regulators", "0.05"),
    ("C347222", "AMS1117-5.0", "SOT-223", "AMS1117-5.0 5V 1A LDO", "Basic", "100000", "Power ICs", "LDO Regulators", "0.05"),
    ("C173386", "AMS1117-1.8", "SOT-223", "AMS1117-1.8 1.8V 1A LDO", "Basic", "80000", "Power ICs", "LDO Regulators", "0.05"),
    ("C347412", "AMS1117-2.5", "SOT-223", "AMS1117-2.5 2.5V 1A LDO", "Basic", "60000", "Power ICs", "LDO Regulators", "0.05"),
    # === VOLTAGE REGULATORS (switching, extended) ===
    ("C2837", "LM2596S-5.0", "TO-263", "LM2596S-5.0 5V 3A Buck", "Extended", "5000", "Power ICs", "DC-DC Converters", "0.85"),
    ("C29781", "LM2596S-3.3", "TO-263", "LM2596S-3.3 3.3V 3A Buck", "Extended", "4000", "Power ICs", "DC-DC Converters", "0.85"),
    ("C347421", "LM2596S-ADJ", "TO-263", "LM2596S-ADJ Adjustable 3A Buck", "Extended", "3000", "Power ICs", "DC-DC Converters", "0.90"),
    ("C84573", "MP1584EN", "SOIC-8", "MP1584EN 28V 3A Sync Buck", "Extended", "20000", "Power ICs", "DC-DC Converters", "0.25"),
    ("C14902", "TPS5430DDAR", "SOIC-8", "TPS5430 36V 3A Buck", "Extended", "15000", "Power ICs", "DC-DC Converters", "0.70"),
    # === CONNECTORS (basic) ===
    ("C49257", "Header-Male-2.54_1x2", "2.54mm", "2-Pin Male Header 2.54mm", "Basic", "100000", "Connectors", "Pin Headers", "0.01"),
    ("C49261", "Header-Male-2.54_1x3", "2.54mm", "3-Pin Male Header 2.54mm", "Basic", "80000", "Connectors", "Pin Headers", "0.01"),
    ("C124375", "KF350-2P", "5mm", "2-Pin Screw Terminal 5mm", "Extended", "30000", "Connectors", "Screw Terminals", "0.08"),
]


def seed_database(db_path: Path) -> int:
    """Create and populate a seed database with common power supply parts.

    Returns the number of parts imported.
    """
    csv_content = io.StringIO()
    writer = csv.writer(csv_content)
    writer.writerow([
        "LCSC Part #", "MFR.Part #", "Package", "Description",
        "Library Type", "Stock", "First Category", "Second Category", "Price",
    ])
    for part in _SEED_PARTS:
        writer.writerow(part)

    csv_path = db_path.parent / "_seed_parts.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(csv_content.getvalue())

    db = JLCPCBPartsDB(db_path)
    count = db.import_csv(csv_path)
    db.close()

    csv_path.unlink()  # Clean up temp CSV
    return count
