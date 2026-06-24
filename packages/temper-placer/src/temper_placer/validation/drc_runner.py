"""
KiCad DRC runner - programmatic interface to kicad-cli DRC.

This module wraps kicad-cli to run Design Rule Checks on PCB files
and parse the results into structured data.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class DrcRunnerError(Exception):
    """Error running DRC."""

    pass


class DrcStatus(Enum):
    """Three-state status for a DRC measurement.

    ``PASS`` is a measured-clean result; ``FAIL`` is a measured result
    with violations; ``UNVERIFIED`` means the tool was missing or the
    invocation errored — no measurement exists, so the value is honest
    about the unknown. The default for an uninitialized ``DrcResult`` is
    ``UNVERIFIED`` so callers cannot accidentally read a passing value
    when no measurement has been recorded.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


class FencePosture(Enum):
    """Role of the kicad-cli invocation at the call site.

    The posture declares how ``run_drc`` should treat a missing or
    errored tool:

    - ``GATE`` raises ``DrcRunnerError`` on missing tool — the call site
      is a merge gate and a missing measurement is a hard failure.
    - ``FENCE`` returns a ``DrcResult(drc_status=UNVERIFIED, ...)`` and
      logs a WARNING — the fence role logs the missing measurement but
      does not break the build.
    - ``REPORT`` returns a ``DrcResult(drc_status=UNVERIFIED, ...)`` and
      logs at INFO — the report role includes the missing measurement
      in its output but does not warn the user.

    A static lint test enforces that every call site of ``run_drc`` in
    production code carries a ``posture=`` keyword.  Adding a new call
    site without a posture is a build break by design.
    """

    GATE = "GATE"
    FENCE = "FENCE"
    REPORT = "REPORT"


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
    location: tuple[float, float]
    message: str
    components: list[str] = field(default_factory=list)


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
    location: tuple[float, float]
    message: str
    components: list[str] = field(default_factory=list)


@dataclass
class DrcResult:
    """
    Result of running DRC on a PCB file.

    Attributes:
        error_count: Total number of errors.
        warning_count: Total number of warnings.
        errors: List of DrcError objects.
        warnings: List of DrcWarning objects.
        drc_status: Three-state status (PASS / FAIL / UNVERIFIED).
            Default is ``UNVERIFIED`` so an uninitialized ``DrcResult``
            cannot be misread as a measured PASS.
        cache_hit: ``True`` when the result was served from the
            regression cache (see :class:`temper_placer.validation.
            drc_cache.DrcCache`); ``False`` for a fresh measurement.
            Default is ``False``; the cache layer sets this flag on
            hits, never the runner itself.
    """

    error_count: int
    warning_count: int
    errors: list[DrcError] = field(default_factory=list)
    warnings: list[DrcWarning] = field(default_factory=list)
    drc_status: DrcStatus = DrcStatus.UNVERIFIED
    cache_hit: bool = False


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

    errors: list[DrcError] = []
    warnings: list[DrcWarning] = []

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
        drc_status=DrcStatus.PASS if len(errors) == 0 else DrcStatus.FAIL,
    )


def run_drc(
    pcb_path: Path,
    *,
    posture: FencePosture = FencePosture.GATE,
) -> DrcResult:
    """
    Run KiCad DRC on a PCB file.

    Args:
        pcb_path: Path to .kicad_pcb file.
        posture: Role of this invocation.  ``FencePosture.GATE``
            (default) raises ``DrcRunnerError`` on missing tool —
            the call site is a merge gate and a missing measurement
            is a hard failure.  ``FencePosture.FENCE`` and
            ``FencePosture.REPORT`` return a
            ``DrcResult(drc_status=UNVERIFIED, ...)`` and log at
            WARNING / INFO respectively.  The static lint test
            ``test_run_drc_call_sites_have_posture`` enforces that
            every production call site declares a posture explicitly.

    Returns:
        DrcResult with all errors and warnings.  When the tool is
        missing and the posture is ``FENCE`` or ``REPORT``, the
        returned result has ``drc_status == DrcStatus.UNVERIFIED``,
        ``error_count == 0``, and ``warning_count == 0`` — an honest
        "no measurement" result that downstream gates can distinguish
        from a real PASS.

    Raises:
        FileNotFoundError: If PCB file doesn't exist.
        DrcRunnerError: If kicad-cli is not available and the posture
            is ``GATE`` (or if the kicad-cli invocation itself fails
            regardless of posture).
    """
    pcb_path = Path(pcb_path)

    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    if not is_kicad_cli_available():
        if posture is FencePosture.GATE:
            raise DrcRunnerError(
                "kicad-cli is not available. Install KiCad 8+ and "
                "ensure kicad-cli is in PATH. (POSTURE=GATE)"
            )
        # FENCE / REPORT: return an honest UNVERIFIED result.  The
        # caller's gate / fence / report then handles the missing
        # measurement per its own semantics.
        if posture is FencePosture.FENCE:
            _LOGGER.warning(
                "DRC: kicad-cli not available; returning "
                "DrcResult(drc_status=UNVERIFIED) (POSTURE=FENCE) "
                "for pcb=%s",
                pcb_path,
            )
        else:
            _LOGGER.info(
                "DRC: kicad-cli not available; returning "
                "DrcResult(drc_status=UNVERIFIED) (POSTURE=REPORT) "
                "for pcb=%s",
                pcb_path,
            )
        return DrcResult(
            error_count=0,
            warning_count=0,
            errors=[],
            warnings=[],
            drc_status=DrcStatus.UNVERIFIED,
        )

    # Get output path for JSON report
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json_path = Path(tmp.name)

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
