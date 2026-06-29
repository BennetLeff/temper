"""
KiCad DRC runner utility for feedback loop.

Executes kicad-cli DRC and returns the report path.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class KiCadDRCRunner:
    """Runs KiCad DRC checks and returns violation report."""

    def __init__(self, kicad_pcb_path: str, output_dir: str | None = None):
        """
        Initialize DRC runner.

        Args:
            kicad_pcb_path: Path to the .kicad_pcb file to check
            output_dir: Directory to store DRC reports (defaults to temp)
        """
        self.kicad_pcb_path = Path(kicad_pcb_path)
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir())
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> str:
        """
        Execute DRC check.

        Returns:
            Path to DRC report JSON file

        Raises:
            RuntimeError: If kicad-cli is not available or DRC fails
        """
        # Check if kicad-cli is available
        try:
            subprocess.run(["kicad-cli", "--version"], check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                "kicad-cli not available. Install KiCad 7.0+ and ensure kicad-cli is in PATH."
            ) from e

        # Generate output path
        report_name = f"drc_report_{self.kicad_pcb_path.stem}.json"
        report_path = self.output_dir / report_name

        # Run DRC
        logger.info(f"Running DRC on {self.kicad_pcb_path}...")
        try:
            result = subprocess.run(
                [
                    "kicad-cli",
                    "pcb",
                    "drc",
                    "--format",
                    "json",
                    "--output",
                    str(report_path),
                    str(self.kicad_pcb_path),
                ],
                check=False,  # DRC may "fail" if violations found
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
            )

            # kicad-cli drc returns non-zero if violations found, but still writes report
            if result.returncode not in [0, 1]:
                logger.error(f"DRC command failed: {result.stderr}")
                raise RuntimeError(f"DRC execution failed: {result.stderr}")

            if not report_path.exists():
                raise RuntimeError(f"DRC report not generated at {report_path}")

            logger.info(f"DRC report written to {report_path}")
            return str(report_path)

        except subprocess.TimeoutExpired as e:
            raise RuntimeError("DRC execution timed out after 120 seconds") from e


def run_drc_check(pcb_path: str, output_dir: str | None = None) -> str:
    """
    Convenience function to run DRC check.

    Args:
        pcb_path: Path to .kicad_pcb file
        output_dir: Optional output directory for reports

    Returns:
        Path to DRC report JSON file
    """
    runner = KiCadDRCRunner(pcb_path, output_dir)
    return runner.run()
