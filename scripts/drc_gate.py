"""Run kicad-cli drc on generated boards and enforce regression ceilings.

Usage (inside distrobox):
    python scripts/drc_gate.py [--update]

Exits with status 0 if every board's error/warning/unconnected counts are
at or below the ceilings in tests/golden/drc_ceilings.json. Exits 1 on
any regression. Pass --update to overwrite the ceilings with the current
counts (use when you've fixed bugs and want to lock in the new floor).

Assumes the boards already exist under output/demo/<name>/<name>/. Run
scripts/full_pipeline.py first if they don't.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from etchant.kicad.drc_report import parse_drc_report  # noqa: E402

CEILINGS_PATH = REPO / "tests" / "golden" / "drc_ceilings.json"
OUTPUT_DIR = REPO / "output" / "demo"


def run_kicad_drc(pcb_path: Path, report_path: Path) -> None:
    """Run kicad-cli pcb drc against a board, writing the report."""
    result = subprocess.run(
        [
            "kicad-cli", "pcb", "drc",
            "--severity-all",
            "--output", str(report_path),
            str(pcb_path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if not report_path.exists():
        raise RuntimeError(
            f"kicad-cli drc produced no report for {pcb_path}: {result.stderr}"
        )


def measure_board(name: str) -> dict[str, int]:
    """Run DRC on a single named board and return measured counts."""
    pcb = OUTPUT_DIR / name / name / f"{name}.kicad_pcb"
    if not pcb.exists():
        raise FileNotFoundError(f"Missing board: {pcb}. Run full_pipeline.py first.")

    report_path = pcb.with_suffix(".drc.rpt")
    run_kicad_drc(pcb, report_path)
    report = parse_drc_report(report_path)
    return {
        "errors": report.errors_only,
        "warnings": report.warnings_only,
        "unconnected_pads": report.unconnected_pads,
    }


def check_against_ceiling(
    name: str, measured: dict[str, int], ceiling: dict[str, int],
) -> list[str]:
    """Return a list of human-readable regression messages (empty = pass)."""
    regressions: list[str] = []
    for key in ("errors", "warnings", "unconnected_pads"):
        m = measured.get(key, 0)
        c = ceiling.get(key, 0)
        if m > c:
            regressions.append(f"{name}.{key}: {m} > ceiling {c}")
    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true",
        help="Overwrite ceilings with current measured counts",
    )
    args = parser.parse_args()

    with open(CEILINGS_PATH) as f:
        ceilings = json.load(f)

    topologies = ceilings["topologies"]
    measured_all: dict[str, dict[str, int]] = {}
    regressions: list[str] = []

    for name in topologies:
        measured = measure_board(name)
        measured_all[name] = measured
        ceiling = topologies[name]
        delta = check_against_ceiling(name, measured, ceiling)
        regressions.extend(delta)

        status = "PASS" if not delta else "FAIL"
        print(
            f"  {name:22s} errors={measured['errors']:2d}/{ceiling['errors']:<2d}  "
            f"warnings={measured['warnings']:2d}/{ceiling['warnings']:<2d}  "
            f"unconn={measured['unconnected_pads']}/{ceiling['unconnected_pads']}  "
            f"[{status}]"
        )

    if args.update:
        for name, measured in measured_all.items():
            topologies[name].update(measured)
        with open(CEILINGS_PATH, "w") as f:
            json.dump(ceilings, f, indent=2)
        print(f"\nCeilings updated in {CEILINGS_PATH.relative_to(REPO)}")
        return 0

    if regressions:
        print("\nDRC REGRESSION DETECTED:")
        for r in regressions:
            print(f"  - {r}")
        print("\nFix the regression or run with --update to lock in a new floor.")
        return 1

    print("\nAll boards within DRC ceilings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
