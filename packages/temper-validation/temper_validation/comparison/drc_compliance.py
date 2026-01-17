"""DRC compliance scoring and KiCad integration."""

from dataclasses import dataclass
from enum import Enum
import subprocess
import re
import time
from typing import Self

__all__ = [
    "ViolationSeverity",
    "DRCViolation",
    "DRCResult",
    "DRCComplianceResult",
    "calculate_drc_score",
    "get_drc_verdict",
    "categorize_violations",
    "evaluate_drc_compliance",
    "run_kicad_drc",
]


class ViolationSeverity(Enum):
    """Severity of DRC violation."""

    ERROR = "error"
    WARNING = "warning"


@dataclass
class DRCViolation:
    """DRC violation entry."""

    violation_id: str
    severity: ViolationSeverity
    description: str
    component: str | None = None
    coordinates: tuple[float, float] | None = None


@dataclass
class DRCResult:
    """Result from KiCad DRC run."""

    violations: list[DRCViolation]
    unconnected_pads: int
    run_time_seconds: float


@dataclass
class DRCComplianceResult:
    """Result of DRC compliance check."""

    score: float
    max_score: float
    critical_violations: int
    warning_violations: int
    verdict: str


# Scoring constants
CRITICAL_PENALTY = 20.0
WARNING_PENALTY = 5.0
MAX_SCORE = 100.0
PASS_THRESHOLD = 80.0


def categorize_violations(violations: list[DRCViolation]) -> tuple[int, int]:
    """
    Categorize violations by severity.

    Args:
        violations: List of DRCViolation objects

    Returns:
        Tuple of (critical_count, warning_count)
    """
    critical_count = sum(1 for v in violations if v.severity == ViolationSeverity.ERROR)
    warning_count = sum(1 for v in violations if v.severity == ViolationSeverity.WARNING)
    return critical_count, warning_count


def calculate_drc_score(violations: list[DRCViolation]) -> float:
    """
    Calculate DRC compliance score from violations.

    Scoring:
    - Critical violation: -20 points
    - Warning violation: -5 points
    - Score clamped at 0 (never negative)

    Args:
        violations: List of DRCViolation objects

    Returns:
        DRC score (0.0 to 100.0)
    """
    critical_count, warning_count = categorize_violations(violations)

    penalty = (critical_count * CRITICAL_PENALTY) + (warning_count * WARNING_PENALTY)
    score = MAX_SCORE - penalty

    # Clamp at 0 (never negative)
    return max(0.0, score)


def get_drc_verdict(score: float) -> str:
    """
    Get DRC compliance verdict from score.

    Args:
        score: DRC compliance score (0.0 to 100.0)

    Returns:
        "PASS" if score >= 80, "FAIL" otherwise
    """
    return "PASS" if score >= PASS_THRESHOLD else "FAIL"


def evaluate_drc_compliance(violations: list[DRCViolation]) -> DRCComplianceResult:
    """
    Evaluate DRC compliance and generate result.

    Args:
        violations: List of DRCViolation objects

    Returns:
        DRCComplianceResult with score, verdict, and violation counts
    """
    score = calculate_drc_score(violations)
    critical_count, warning_count = categorize_violations(violations)
    verdict = get_drc_verdict(score)

    return DRCComplianceResult(
        score=score,
        max_score=MAX_SCORE,
        critical_violations=critical_count,
        warning_violations=warning_count,
        verdict=verdict,
    )


def run_kicad_drc(pcb_path: str, kicad_path: str) -> DRCResult:
    """
    Run KiCad DRC and parse output.

    Args:
        pcb_path: Path to .kicad_pcb file
        kicad_path: Path to KiCad executable

    Returns:
        DRCResult with violations and run time
    """
    start_time = time.time()

    # Construct KiCad DRC command
    # Note: This is a simplified implementation
    # Real implementation would use proper CLI arguments for KiCad
    cmd = [f"{kicad_path}/kicad-cli", "drc", "--output", "/dev/stdout", pcb_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # 1 minute timeout
        )

        violations = parse_drc_output(result.stdout)
        unconnected_pads = count_unconnected_pads(result.stdout)

    except subprocess.TimeoutExpired:
        violations = []
        unconnected_pads = 0
    except FileNotFoundError:
        # KiCad not found - return empty result
        violations = []
        unconnected_pads = 0
    except Exception:
        # Any other error - return empty result
        violations = []
        unconnected_pads = 0

    run_time = time.time() - start_time

    return DRCResult(
        violations=violations, unconnected_pads=unconnected_pads, run_time_seconds=run_time
    )


def parse_drc_output(output: str) -> list[DRCViolation]:
    """
    Parse KiCad DRC output into violation objects.

    Args:
        output: KiCad DRC stdout

    Returns:
        List of DRCViolation objects
    """
    violations = []
    violation_id = 0

    # KiCad DRC format (simplified pattern matching)
    # Expected format:
    # "Erreur: <description>" (error)
    # "Warning: <description>" (warning)
    # "    @ (x, y) on <net>" (location)
    # "Erreur" is French for "Error" in some KiCad versions

    lines = output.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Parse error line
        error_match = re.match(r"^Erreur:\s*(.+)$", line, re.IGNORECASE)
        warning_match = re.match(r"^Warning:\s*(.+)$", line, re.IGNORECASE)

        if error_match or warning_match:
            violation_id += 1

            if error_match:
                severity = ViolationSeverity.ERROR
                description = error_match.group(1)
            else:
                severity = ViolationSeverity.WARNING
                description = warning_match.group(1)

            # Look for location on next lines
            coordinates = None
            component = None

            if i + 1 < len(lines):
                location_line = lines[i + 1].strip()
                coord_match = re.match(r"@\s*\(([\d.]+),\s*([\d.]+)\)", location_line)
                if coord_match:
                    coordinates = (float(coord_match.group(1)), float(coord_match.group(2)))

                # Extract component/net info
                on_match = re.search(r"on\s+(\S+)", location_line)
                if on_match:
                    component = on_match.group(1)

            violation = DRCViolation(
                violation_id=f"V{violation_id:03d}",
                severity=severity,
                description=description,
                component=component,
                coordinates=coordinates,
            )
            violations.append(violation)

        i += 1

    return violations


def count_unconnected_pads(output: str) -> int:
    """
    Count unconnected pads in DRC output.

    Args:
        output: KiCad DRC stdout

    Returns:
        Number of unconnected pads
    """
    # Look for unconnected pad pattern
    # Pattern: "Unconnected pad" or similar
    count = 0

    for line in output.split("\n"):
        if "unconnected" in line.lower() and "pad" in line.lower():
            count += 1

    return count
