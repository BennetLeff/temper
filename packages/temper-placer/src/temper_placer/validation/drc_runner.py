"""
KiCad DRC runner - programmatic interface to kicad-cli DRC.

This module wraps kicad-cli to run Design Rule Checks on PCB files
and parse the results into structured data.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


class DrcRunnerError(Exception):
    """Error running DRC."""

    pass


@dataclass
class DrcError:
    """
    A DRC error.

    Attributes:
        rule: Rule that was violated (e.g., 'clearance', 'courtyard_overlap').
        severity: Severity level ('error', 'warning').
        location: (x, y) position in mm.
        message: Human-readable description.
        components: List of component references involved.
    """

    rule: str
    severity: str
    location: Tuple[float, float]
    message: str
    components: List[str] = field(default_factory=list)


@dataclass
class DrcWarning:
    """
    A DRC warning (same structure as DrcError).

    Attributes:
        rule: Rule that was violated.
        severity: Should be 'warning'.
        location: (x, y) position in mm.
        message: Human-readable description.
        components: List of component references involved.
    """

    rule: str
    severity: str
    location: Tuple[float, float]
    message: str
    components: List[str] = field(default_factory=list)


@dataclass
class DrcResult:
    """
    Result of running DRC on a PCB file.

    Attributes:
        error_count: Total number of errors.
        warning_count: Total number of warnings.
        errors: List of DrcError objects.
        warnings: List of DrcWarning objects.
    """

    error_count: int
    warning_count: int
    errors: List[DrcError] = field(default_factory=list)
    warnings: List[DrcWarning] = field(default_factory=list)


def is_kicad_cli_available() -> bool:
    """
    Check if kicad-cli is available in PATH.

    Returns:
        True if kicad-cli is found, False otherwise.
    """
    return shutil.which("kicad-cli") is not None


def _get_drc_json_path(pcb_path: Path) -> Path:
    """
    Get the path where DRC JSON output will be written.

    This is a helper function that can be mocked in tests.
    """
    return pcb_path.parent / f"{pcb_path.stem}_drc_report.json"


def _parse_drc_json(json_path: Path) -> DrcResult:
    """
    Parse kicad-cli DRC JSON output.

    Args:
        json_path: Path to JSON report file.

    Returns:
        DrcResult with parsed errors and warnings.
    """
    with open(json_path) as f:
        data = json.load(f)

    errors: List[DrcError] = []
    warnings: List[DrcWarning] = []

    for violation in data.get("violations", []):
        rule = violation.get("type", "unknown")
        severity = violation.get("severity", "error")
        message = violation.get("description", "")

        pos = violation.get("pos", {})
        location = (pos.get("x", 0.0), pos.get("y", 0.0))

        # Extract component refs from items
        components = []
        for item in violation.get("items", []):
            ref = item.get("reference")
            if ref:
                components.append(ref)

        if severity == "warning":
            warnings.append(
                DrcWarning(
                    rule=rule,
                    severity=severity,
                    location=location,
                    message=message,
                    components=components,
                )
            )
        else:
            errors.append(
                DrcError(
                    rule=rule,
                    severity=severity,
                    location=location,
                    message=message,
                    components=components,
                )
            )

    return DrcResult(
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
    )


def run_drc(pcb_path: Path) -> DrcResult:
    """
    Run KiCad DRC on a PCB file.

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        DrcResult with all errors and warnings.

    Raises:
        FileNotFoundError: If PCB file doesn't exist.
        DrcRunnerError: If kicad-cli is not available or DRC fails.
    """
    pcb_path = Path(pcb_path)

    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    if not is_kicad_cli_available():
        raise DrcRunnerError(
            "kicad-cli is not available. Install KiCad 8+ and ensure kicad-cli is in PATH."
        )

    # Get output path for JSON report
    json_path = _get_drc_json_path(pcb_path)

    try:
        # Run kicad-cli DRC
        result = subprocess.run(
            [
                "kicad-cli",
                "pcb",
                "drc",
                "--format",
                "json",
                "--output",
                str(json_path),
                str(pcb_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # kicad-cli returns 0 even with DRC errors (errors are in the report)
        # Non-zero means the command itself failed

        if not json_path.exists():
            raise DrcRunnerError(
                f"DRC did not produce output file. stdout: {result.stdout}, stderr: {result.stderr}"
            )

        return _parse_drc_json(json_path)

    except subprocess.TimeoutExpired:
        raise DrcRunnerError("DRC timed out after 60 seconds")
    except subprocess.SubprocessError as e:
        raise DrcRunnerError(f"Failed to run kicad-cli: {e}")
    finally:
        # Clean up JSON file
        if json_path.exists():
            try:
                json_path.unlink()
            except OSError:
                pass
