# Etchant

AI-powered PCB design agent that generates KiCad projects from natural language circuit specifications.

## Architecture

```
etchant/
  core/           # Data models, component selection, constraint engine
  kicad/          # SKiDL netlist builder, project writer, placement helpers
  circuits/       # Circuit generators (one per topology: buck, boost, LDO, etc.)
  data/           # RAG ingestion scripts, JLCPCB parts DB (week 2+)
  agents/         # LLM orchestration (week 2+)
constraints/      # Manufacturing rules, design rules as YAML (data, not code)
tests/            # Unit + integration tests with golden reference comparisons
  golden/         # Known-good design outputs for regression testing
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
1. Create `etchant/circuits/<topology>.py`
2. Implement the protocol
3. Add constraint YAML in `constraints/<ic>_layout.yaml`
4. Add golden reference in `tests/golden/<spec>.json`
5. Add tests in `tests/test_<topology>.py`

## Constraint System

Constraints are structured YAML in `constraints/`, not hardcoded logic:
- `jlcpcb_manufacturing.yaml` - DFM rules (trace widths, drill sizes, etc.)
- `design_rules.yaml` - Electrical rules (trace width vs current, via limits)
- `<ic>_layout.yaml` - Per-IC placement/routing constraints from datasheets

The `ConstraintEngine` loads these and validates `DesignResult` objects against them.

## Data Models

All core data types are frozen dataclasses in `etchant/core/models.py`:
- `CircuitSpec` - Input specification (voltage, current, topology)
- `ComponentSpec` - Single component (reference, value, footprint, JLCPCB part number)
- `NetSpec` - Named net with pin connections
- `PlacementConstraint` - Physical placement rule
- `DesignResult` - Complete generator output

Collections use `tuple` (not `list`) to enforce immutability.

## Development

```bash
# Install dependencies
uv sync --all-extras

# Run unit tests (works outside distrobox)
uv run pytest tests/ -k "not requires_skidl"

# Run all tests (inside distrobox with KiCad)
uv run pytest tests/ -v --cov

# Generate a buck converter project
uv run etchant -o ./output --input-voltage 12 --output-voltage 5 --current 2

# Lint and type check
uv run ruff check etchant/ tests/
uv run mypy etchant/
```

## Testing

Golden reference pattern: each supported circuit has a known-good output in `tests/golden/`.
Tests compare generated designs against golden references on:
- Component count and values
- Net names and connectivity
- Placement constraint count
- Design notes presence

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
