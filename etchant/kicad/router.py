"""PCB trace routing using Freerouting autorouter.

Exports the board as Specctra DSN, runs Freerouting in headless mode,
and imports the routed session (SES) back into the KiCad board.

Requires: Java runtime and freerouting.jar in tools/ directory.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_FREEROUTING_JAR = Path(__file__).parent.parent.parent / "tools" / "freerouting.jar"

try:
    import pcbnew

    HAS_PCBNEW = True
except ImportError:
    HAS_PCBNEW = False


def check_freerouting_available() -> bool:
    """Check if Freerouting JAR and Java are available."""
    if not _FREEROUTING_JAR.exists():
        return False
    try:
        result = subprocess.run(
            ["java", "-version"], capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class FreeroutingRouter:
    """Routes PCB traces using the Freerouting autorouter."""

    def __init__(self, freerouting_jar: Path | None = None, max_passes: int = 20) -> None:
        self._jar = freerouting_jar or _FREEROUTING_JAR
        self._max_passes = max_passes

    def route_board(self, pcb_path: Path) -> Path:
        """Route all unconnected nets on a .kicad_pcb board.

        Exports DSN, runs Freerouting, imports SES result.
        Returns path to the routed board (modifies in place).
        """
        if not HAS_PCBNEW:
            raise RuntimeError("pcbnew not available")
        if not self._jar.exists():
            raise FileNotFoundError(f"Freerouting JAR not found: {self._jar}")

        dsn_path = pcb_path.with_suffix(".dsn")
        ses_path = pcb_path.with_suffix(".ses")

        # Step 1: Set design rules and export DSN
        logger.info("Exporting DSN: %s", dsn_path)
        board = pcbnew.LoadBoard(str(pcb_path))

        # Set clearance rules for Freerouting
        settings = board.GetDesignSettings()
        settings.SetCopperLayerCount(2)
        settings.m_MinClearance = pcbnew.FromMM(0.3)  # 0.3mm clearance
        settings.m_TrackMinWidth = pcbnew.FromMM(0.25)

        result = pcbnew.ExportSpecctraDSN(board, str(dsn_path))
        if not result:
            raise RuntimeError("Failed to export Specctra DSN")

        # Step 2: Run Freerouting
        logger.info("Running Freerouting (max %d passes)...", self._max_passes)
        cmd = [
            "java", "-jar", str(self._jar),
            "-de", str(dsn_path),
            "-do", str(ses_path),
            "-mp", str(self._max_passes),
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(self._jar.parent),
        )

        if not ses_path.exists():
            logger.error("Freerouting stderr: %s", proc.stderr[-500:] if proc.stderr else "")
            raise RuntimeError("Freerouting did not produce SES output")

        # Parse routing result from output
        unrouted = self._parse_unrouted(proc.stdout + proc.stderr)
        logger.info("Freerouting complete. Unrouted: %d", unrouted)

        # Step 3: Import SES back into board
        logger.info("Importing SES: %s", ses_path)
        board = pcbnew.LoadBoard(str(pcb_path))
        result = pcbnew.ImportSpecctraSES(board, str(ses_path))
        if not result:
            raise RuntimeError("Failed to import Specctra SES")

        board.Save(str(pcb_path))
        logger.info("Board saved with routes: %s", pcb_path)

        # Clean up temp files
        dsn_path.unlink(missing_ok=True)
        ses_path.unlink(missing_ok=True)

        return pcb_path

    def _parse_unrouted(self, output: str) -> int:
        """Parse the number of unrouted connections from Freerouting output."""
        import re

        # Look for last occurrence of "X unrouted"
        matches = re.findall(r"\((\d+) unrouted\)", output)
        if matches:
            return int(matches[-1])
        return -1
