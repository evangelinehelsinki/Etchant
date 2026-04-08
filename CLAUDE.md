# Etchant

AI-powered PCB design agent that generates KiCad projects from natural language circuit specifications.

## Architecture

```
etchant/
  core/
    models.py             # Frozen dataclasses: CircuitSpec, ComponentSpec, DesignResult, etc.
    constraint_engine.py  # YAML-backed design validation (structural + electrical)
    component_selector.py # JLCPCB-first part lookup with basic/extended classification
    bom.py                # BOM generation with JLCPCB cost breakdown
    manufacturing.py      # Manufacturing capability checks (THT detection, board cost)
  kicad/
    netlist_builder.py    # SKiDL wrapper (requires distrobox for KiCad libraries)
    project_writer.py     # .kicad_pro project output
    placement.py          # pcbnew placement stub (requires distrobox)
    design_export.py      # JSON and CSV export (works without KiCad)
  circuits/
    __init__.py           # Generator registry (register_generator, get_generator)
    base.py               # CircuitGenerator protocol
    buck_converter.py     # LM2596 12V->5V 2A
  data/                   # RAG ingestion scripts, JLCPCB parts DB (week 2+)
  agents/                 # LLM orchestration (week 2+)
  cli.py                  # Click CLI with topology dispatch and BOM output
constraints/
  jlcpcb_manufacturing.yaml  # DFM capabilities
  design_rules.yaml          # Trace width vs current, clearances
  lm2596_layout.yaml         # LM2596-specific placement/routing from TI datasheet
tests/
  golden/                 # Known-good design outputs for regression testing
```

## Circuit Generator Pattern

Every circuit type implements the `CircuitGenerator` protocol from `etchant/circuits/base.py`:

```python
class CircuitGenerator(Protocol):
    @property
    def topology(self) -> str: ...
    def generate(self, spec: CircuitSpec) -> DesignResult: ...
    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]: ...
```

To add a new circuit type:
1. Create `etchant/circuits/<topology>.py` implementing the protocol
2. Register it in `etchant/circuits/__init__.py`
3. Add constraint YAML in `constraints/<ic>_layout.yaml`
4. Add JLCPCB parts to `component_selector.py` static lookup table
5. Add golden reference in `tests/golden/<spec>.json`
6. Add tests in `tests/test_<topology>.py`

## Key Modules

### Constraint Engine (`core/constraint_engine.py`)
Validates designs against YAML rules:
- Structural checks (component existence, net connectivity)
- Trace width recommendations from `design_rules.yaml`
- Single-pin net detection (dangling pins)
- Severity levels: ERROR, WARNING, INFO

### Component Selector (`core/component_selector.py`)
JLCPCB-first part matching:
- Basic parts: no setup fee (resistors, common diodes)
- Extended parts: $3 per unique part (ICs, specialty components)
- Static lookup table for Week 1; live API via mixelpixx MCP in Week 2

### BOM Generator (`core/bom.py`)
Produces BOM with cost breakdown showing basic vs extended parts
and total JLCPCB assembly setup fees.

### Design Export (`kicad/design_export.py`)
- JSON: Full design state for LLM validation and review
- CSV: JLCPCB-compatible BOM with part numbers

## Development

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v --cov

# Generate a buck converter
uv run etchant -o ./output -vin 12 -vout 5 -i 2

# List available topologies
uv run etchant --list-topologies

# Lint
uv run ruff check etchant/ tests/
```

## Testing

Golden reference pattern: each circuit has a known-good output in `tests/golden/`.
Tests verify component values, net connectivity, placement constraints, and cost data.

Tests marked `@pytest.mark.requires_skidl` need KiCad + SKiDL (run inside distrobox).

## Environment

Full toolchain requires distrobox container (see `setup-distrobox.sh`):
- KiCad 9+ with symbol/footprint libraries
- Python 3.11+ with uv
- ngspice for SPICE simulation
- SKiDL needs `KICAD_SYMBOL_DIR` env var pointing to KiCad libraries

## Gotchas

- SKiDL uses module-level global state. Call `skidl.reset()` between test runs.
- `generate_schematic()` is experimental/broken. Use `generate_netlist()` only.
- KiCad footprint strings must match `fp-lib-table` exactly.
- pcbnew Python module only available inside KiCad's Python environment.
- KiCad 7 broke SKiDL; use KiCad 8+.
- `ComponentSpec.properties` uses `MappingProxyType` for true immutability.
