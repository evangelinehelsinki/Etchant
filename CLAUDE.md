# Etchant

AI-powered PCB design agent that generates KiCad projects from natural language circuit specifications.

## Architecture

```
etchant/
  core/
    models.py             # Frozen dataclasses: CircuitSpec, ComponentSpec, DesignResult
    constraint_engine.py  # YAML-backed design validation (structural + electrical)
    component_selector.py # JLCPCB-first part lookup (static table + live DB fallback)
    bom.py                # BOM generation with JLCPCB cost breakdown
    manufacturing.py      # THT detection, board cost estimation
    serialization.py      # Save/load designs as JSON
    comparison.py         # Structured design diff for verification
  kicad/
    netlist_builder.py    # SKiDL wrapper (requires distrobox for KiCad libraries)
    project_writer.py     # .kicad_pro project output
    placement.py          # pcbnew placement stub (requires distrobox)
    design_export.py      # JSON and CSV export (works without KiCad)
  circuits/
    __init__.py           # Generator registry (register_generator, get_generator)
    base.py               # CircuitGenerator protocol
    buck_converter.py     # LM2596 12V->5V 2A (6 components, $12 setup)
    ldo_regulator.py      # AMS1117 5V->3.3V 1A (3 components, $0 setup)
  data/
    jlcpcb_parts.py       # SQLite-backed JLCPCB parts database with CSV import
  agents/
    tools.py              # 7 tool definitions for Claude API
    executor.py           # Tool executor bridging LLM tool calls to pipeline
  cli.py                  # Click CLI: generate, topologies, compare subcommands
constraints/              # Manufacturing rules, design rules as YAML
tests/                    # 167 tests, 91% coverage
  golden/                 # Known-good design outputs for regression testing
```

## CLI Usage

```bash
# Generate a buck converter
etchant generate -t buck_converter -vin 12 -vout 5 -i 2 -o ./output

# Generate and save an LDO design
etchant generate -t ldo_regulator -vin 5 -vout 3.3 -i 0.5 --save design.json

# Export BOM as JLCPCB CSV
etchant generate --export-csv --export-json -o ./output

# List available topologies
etchant topologies

# Compare two designs
etchant compare design_a.json design_b.json
```

## Circuit Generator Pattern

Every circuit type implements the `CircuitGenerator` protocol:

```python
class CircuitGenerator(Protocol):
    @property
    def topology(self) -> str: ...
    def generate(self, spec: CircuitSpec) -> DesignResult: ...
    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]: ...
```

To add a new circuit type:
1. Create `etchant/circuits/<topology>.py` implementing the protocol
2. Register in `etchant/circuits/__init__.py`
3. Add constraint YAML in `constraints/<ic>_layout.yaml`
4. Add JLCPCB parts to `component_selector.py` static lookup
5. Add golden reference in `tests/golden/<spec>.json`
6. Add tests in `tests/test_<topology>.py`

## Key Design Decisions

- **Frozen dataclasses** with tuple collections enforce immutability
- **ComponentSpec.properties** uses `MappingProxyType` for true immutability
- **Constraints as YAML** data, not hardcoded logic
- **JLCPCB-first**: basic parts ($0 setup) preferred over extended ($3/part)
- **Severity enum**: ERROR blocks, WARNING flags, INFO recommends
- **SKiDL patched**: scripts/patch_skidl.py fixes circular import in v2.2.2
- **KiCad 9 pin names**: Use actual names (VIN not IN, ~{ON}/OFF not ON_OFF)

## Development

```bash
uv sync --all-extras            # Install deps
uv run pytest tests/ -v --cov   # Run tests
uv run ruff check etchant/ tests/  # Lint
```

## Distrobox Environment

```bash
./setup-distrobox.sh            # Create container with KiCad 9 + SKiDL
distrobox enter etchant-dev     # Enter container
```

KiCad 9.0.8, pcbnew, ngspice all verified working inside distrobox.
Full pipeline: CircuitSpec -> DesignResult -> SKiDL netlist -> KiCad project.

## Gotchas

- SKiDL uses module-level global state. Call `skidl.reset()` between operations.
- `generate_schematic()` is experimental/broken. Use `generate_netlist()` only.
- KiCad footprint strings must match `fp-lib-table` exactly.
- pcbnew Python module only available inside KiCad's Python environment.
- SKiDL 2.2.2 circular import: run `scripts/patch_skidl.py` after install.
- KiCad 9 1N5824 doesn't exist — use 1N5822 instead.
