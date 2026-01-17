"""
KiCad DRC (Design Rule Check) validator wrapper.

This module provides:
- KiCadDRCValidator: Run KiCad DRC via kicad-cli and parse results
- DRCViolation: Structured representation of DRC violations
- Penalty computation for validation-in-the-loop optimization

Requires KiCad 7+ with kicad-cli available in PATH or at standard location.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    Validator,
)


class DRCSeverity(Enum):
    """DRC violation severity levels from KiCad."""

    ERROR = "error"
    WARNING = "warning"
    EXCLUSION = "exclusion"  # User-excluded violations


class DRCViolationType(Enum):
    """Common DRC violation types from KiCad."""

    # Clearance violations
    CLEARANCE = "clearance"
    SILK_CLEARANCE = "silk_clearance"
    COURTYARD_OVERLAP = "courtyard_overlap"
    HOLE_CLEARANCE = "hole_clearance"

    # Connection violations
    UNCONNECTED_ITEMS = "unconnected_items"
    TRACK_DANGLING = "track_dangling"
    VIA_DANGLING = "via_dangling"

    # Manufacturing violations
    TRACK_WIDTH = "track_width"
    ANNULAR_WIDTH = "annular_width"
    DRILL_OUT_OF_RANGE = "drill_out_of_range"
    VIA_DIAMETER = "via_diameter"

    # Zone violations
    ZONE_UNCONNECTED = "zone_unconnected"
    ZONE_COPPER_POUR = "zone_copper_pour"

    # Other
    FOOTPRINT_TYPE_MISMATCH = "footprint_type_mismatch"
    MISSING_FOOTPRINT = "missing_footprint"
    DUPLICATE_FOOTPRINT = "duplicate_footprint"
    EXTRA_FOOTPRINT = "extra_footprint"
    SCHEMATIC_PARITY = "schematic_parity"
    LIB_FOOTPRINT_ISSUES = "lib_footprint_issues"

    # Catch-all
    OTHER = "other"


@dataclass
class DRCViolation(ValidationIssue):
    """
    A DRC violation from KiCad.

    Extends ValidationIssue with DRC-specific information.

    Attributes:
        violation_type: Type of DRC violation.
        rule_name: KiCad rule that was violated.
        position: (x, y) position in mm where violation occurred.
        affected_items: List of affected component refs or net names.
        description: Human-readable description of the violation.
    """

    violation_type: DRCViolationType = DRCViolationType.OTHER
    rule_name: str = ""
    position: tuple[float, float] | None = None
    affected_items: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base = {
            "severity": self.severity.name.lower(),  # Use name for string
            "code": self.code,
            "message": self.message,
            "violation_type": self.violation_type.value,
            "rule_name": self.rule_name,
            "position": self.position,
            "affected_items": self.affected_items,
            "description": self.description,
        }
        if self.component_refs:
            base["component_refs"] = self.component_refs
        if self.location:
            base["location"] = self.location
        return base


@dataclass
class DRCResult:
    """
    Result from running KiCad DRC.

    Attributes:
        success: Whether DRC ran successfully (not necessarily violation-free).
        violations: List of DRC violations found.
        error_count: Number of error-level violations.
        warning_count: Number of warning-level violations.
        exclusion_count: Number of excluded violations.
        elapsed_ms: Time taken for DRC check.
        kicad_version: Version of KiCad used.
        raw_output: Raw output from kicad-cli.
    """

    success: bool
    violations: list[DRCViolation] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    exclusion_count: int = 0
    elapsed_ms: float = 0.0
    kicad_version: str = ""
    raw_output: str = ""

    @property
    def has_errors(self) -> bool:
        """Check if any error-level violations exist."""
        return self.error_count > 0

    @property
    def total_violations(self) -> int:
        """Total number of violations (excluding exclusions)."""
        return self.error_count + self.warning_count

    def summary(self) -> str:
        """Get a human-readable summary."""
        status = "PASS" if not self.has_errors else "FAIL"
        lines = [f"DRC {status}: {self.error_count} errors, {self.warning_count} warnings"]

        if self.violations:
            lines.append("\nTop violations:")
            for v in self.violations[:5]:
                lines.append(f"  [{v.severity.value}] {v.violation_type.value}: {v.message}")

        lines.append(f"\nElapsed: {self.elapsed_ms:.1f}ms")
        return "\n".join(lines)


# Standard locations for kicad-cli on different platforms
KICAD_CLI_PATHS = [
    # macOS
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    "/Applications/KiCad 8.0/KiCad.app/Contents/MacOS/kicad-cli",
    "/Applications/KiCad 7.0/KiCad.app/Contents/MacOS/kicad-cli",
    # Linux (common locations)
    "/usr/bin/kicad-cli",
    "/usr/local/bin/kicad-cli",
    # Windows
    "C:\\Program Files\\KiCad\\8.0\\bin\\kicad-cli.exe",
    "C:\\Program Files\\KiCad\\7.0\\bin\\kicad-cli.exe",
]


def find_kicad_cli() -> str | None:
    """
    Find kicad-cli executable.

    Checks:
    1. PATH via shutil.which()
    2. Standard installation locations

    Returns:
        Path to kicad-cli or None if not found.
    """
    # First check PATH
    cli_path = shutil.which("kicad-cli")
    if cli_path:
        return cli_path

    # Check standard locations
    for path in KICAD_CLI_PATHS:
        if Path(path).exists():
            return path

    return None


class KiCadDRCValidator(Validator):
    """
    Validator that runs KiCad DRC for design rule checking.

    Uses kicad-cli (KiCad 7+) to run DRC in batch mode and parse
    the JSON output for violations.

    Example usage:
        validator = KiCadDRCValidator()

        if validator.is_available():
            result = validator.run_drc(Path("board.kicad_pcb"))
            print(result.summary())

            # Compute penalty for optimization
            penalty = validator.compute_penalty(result)
    """

    def __init__(
        self,
        kicad_cli_path: str | None = None,
        timeout_seconds: float = 120.0,
        severity_weights: dict[str, float] | None = None,
        violation_weights: dict[str, float] | None = None,
    ):
        """
        Initialize KiCad DRC validator.

        Args:
            kicad_cli_path: Path to kicad-cli binary. If None, auto-detect.
            timeout_seconds: Maximum time for DRC check.
            severity_weights: Penalty weights by severity (default: error=10, warning=1).
            violation_weights: Penalty weights by violation type (optional overrides).
        """
        self.kicad_cli_path = kicad_cli_path or find_kicad_cli()
        self.timeout_seconds = timeout_seconds

        # Default severity weights
        self.severity_weights = severity_weights or {
            "error": 10.0,
            "warning": 1.0,
            "exclusion": 0.0,
        }

        # Optional per-violation-type weights (multiply with severity weight)
        # Higher weights for safety-critical violations
        self.violation_weights = violation_weights or {
            "clearance": 2.0,  # Critical for HV-LV isolation
            "hole_clearance": 1.5,
            "unconnected_items": 1.5,
            "track_width": 1.2,
            "courtyard_overlap": 1.0,
            "silk_clearance": 0.5,  # Less critical
        }

        self._kicad_version: str | None = None

    @property
    def name(self) -> str:
        return "KiCadDRCValidator"

    def is_available(self) -> bool:
        """Check if kicad-cli is available."""
        if not self.kicad_cli_path:
            return False
        return Path(self.kicad_cli_path).exists()

    def get_version(self) -> str:
        """Get KiCad version string."""
        if self._kicad_version:
            return self._kicad_version

        if not self.is_available() or not self.kicad_cli_path:
            return "unknown"

        try:
            result = subprocess.run(
                [self.kicad_cli_path, "version"],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            self._kicad_version = result.stdout.strip()
            return self._kicad_version
        except Exception:
            return "unknown"

    def validate(
        self,
        state: PlacementState,
        netlist: Netlist,
        board: Board,
    ) -> ValidationResult:
        """
        Run DRC validation.

        Note: This requires a PCB file to exist. For validation-in-the-loop,
        you need to first export the current placement to a temp PCB file.

        For now, this just checks if kicad-cli is available.
        Use run_drc() directly for actual DRC checking.

        Args:
            state: Current placement state.
            netlist: Component netlist.
            board: Board definition.

        Returns:
            ValidationResult.
        """
        start_time = time.time()
        issues: list[ValidationIssue] = []
        metrics: dict[str, float] = {}

        if not self.is_available():
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="KICAD_NOT_AVAILABLE",
                    message="kicad-cli is not available - skipping DRC validation",
                )
            )
            return ValidationResult(
                valid=True,  # Not invalid, just skipped
                issues=issues,
                metrics=metrics,
                elapsed_ms=(time.time() - start_time) * 1000,
                validator_name=self.name,
            )

        metrics["kicad_available"] = 1.0
        metrics["kicad_version"] = hash(self.get_version()) % 1000000  # Numeric representation

        return ValidationResult(
            valid=True,
            issues=issues,
            metrics=metrics,
            elapsed_ms=(time.time() - start_time) * 1000,
            validator_name=self.name,
        )

    def run_drc(
        self,
        pcb_path: Path,
        severity_all: bool = True,
        schematic_parity: bool = False,
        units: str = "mm",
    ) -> DRCResult:
        """
        Run DRC on a PCB file.

        Args:
            pcb_path: Path to the .kicad_pcb file.
            severity_all: Report all severity levels.
            schematic_parity: Check parity with schematic.
            units: Units for positions (mm, in, mils).

        Returns:
            DRCResult with violations and statistics.
        """
        if not self.is_available():
            return DRCResult(
                success=False,
                raw_output="kicad-cli not available",
            )

        if not pcb_path.exists():
            return DRCResult(
                success=False,
                raw_output=f"PCB file not found: {pcb_path}",
            )

        start_time = time.time()

        # Get output path for JSON report
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            output_path = Path(tmp.name).absolute()

        try:
            # Build command with absolute paths
            cmd = [
                self.kicad_cli_path,
                "pcb",
                "drc",
                "--format",
                "json",
                "--output",
                str(output_path),
                "--units",
                units,
            ]

            if severity_all:
                cmd.append("--severity-all")
            if schematic_parity:
                cmd.append("--schematic-parity")

            cmd.append(str(pcb_path.absolute()))

            # Run DRC
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=pcb_path.parent.absolute(),
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # Parse JSON output
            if output_path.exists():
                with open(output_path) as f:
                    drc_data = json.load(f)
                violations = self._parse_violations(drc_data)
            else:
                violations = []
                drc_data = {}

            # Count by severity
            error_count = sum(1 for v in violations if v.severity == ValidationSeverity.ERROR)
            warning_count = sum(1 for v in violations if v.severity == ValidationSeverity.WARNING)
            exclusion_count = sum(
                1
                for v in violations
                if v.violation_type == DRCViolationType.OTHER and "exclusion" in v.code.lower()
            )

            return DRCResult(
                success=True,
                violations=violations,
                error_count=error_count,
                warning_count=warning_count,
                exclusion_count=exclusion_count,
                elapsed_ms=elapsed_ms,
                kicad_version=self.get_version(),
                raw_output=proc.stdout + proc.stderr,
            )

        except subprocess.TimeoutExpired:
            return DRCResult(
                success=False,
                elapsed_ms=self.timeout_seconds * 1000,
                raw_output=f"DRC timed out after {self.timeout_seconds}s",
            )
        except Exception as e:
            return DRCResult(
                success=False,
                elapsed_ms=(time.time() - start_time) * 1000,
                raw_output=f"DRC error: {str(e)}",
            )
        finally:
            # Clean up temp file
            if output_path.exists():
                output_path.unlink()

    def _parse_violations(self, drc_data: dict[str, Any]) -> list[DRCViolation]:
        """Parse violations from KiCad DRC JSON output."""
        violations = []

        # KiCad DRC JSON structure has "violations" array
        for item in drc_data.get("violations", []):
            violation = self._parse_single_violation(item)
            if violation:
                violations.append(violation)

        return violations

    def _parse_single_violation(self, item: dict[str, Any]) -> DRCViolation | None:
        """Parse a single violation from JSON."""
        try:
            # Get severity
            severity_str = item.get("severity", "warning").lower()
            if severity_str == "error":
                severity = ValidationSeverity.ERROR
            else:
                severity = ValidationSeverity.WARNING

            # Get violation type
            type_str = item.get("type", "").lower().replace(" ", "_").replace("-", "_")
            try:
                violation_type = DRCViolationType(type_str)
            except ValueError:
                violation_type = DRCViolationType.OTHER

            # Get position
            position = None
            pos_data = item.get("pos", {})
            if pos_data:
                x = pos_data.get("x", 0)
                y = pos_data.get("y", 0)
                position = (float(x), float(y))

            # Get affected items
            affected_items = []
            for affected in item.get("items", []):
                if isinstance(affected, dict):
                    ref = affected.get("reference", affected.get("net", ""))
                    if ref:
                        affected_items.append(str(ref))
                elif isinstance(affected, str):
                    affected_items.append(affected)

            # Build message
            description = item.get("description", "")
            message = description or f"{violation_type.value} violation"

            return DRCViolation(
                severity=severity,
                code=f"DRC_{violation_type.value.upper()}",
                message=message,
                violation_type=violation_type,
                rule_name=item.get("rule", ""),
                position=position,
                affected_items=affected_items,
                description=description,
            )
        except Exception:
            return None

    def compute_penalty(self, result: DRCResult) -> float:
        """
        Compute a penalty value from DRC results.

        Used for validation-in-the-loop optimization.
        Higher penalty = more/worse violations.

        Args:
            result: DRCResult from run_drc().

        Returns:
            Scalar penalty value (0 = no violations).
        """
        if not result.success:
            return 100.0  # High penalty for failed DRC

        penalty = 0.0

        for violation in result.violations:
            # Base weight from severity (use name for lookup)
            severity_key = violation.severity.name.lower()
            base_weight = self.severity_weights.get(severity_key, 1.0)

            # Optional type-specific multiplier
            type_key = violation.violation_type.value
            type_mult = self.violation_weights.get(type_key, 1.0)

            penalty += base_weight * type_mult

        return penalty

    def to_validation_result(self, result: DRCResult) -> ValidationResult:
        """
        Convert DRCResult to ValidationResult.

        Useful for integrating with CompositeValidator.
        """
        issues: list[ValidationIssue] = list(result.violations)
        metrics: dict[str, float] = {
            "drc_errors": float(result.error_count),
            "drc_warnings": float(result.warning_count),
            "drc_penalty": self.compute_penalty(result),
        }

        return ValidationResult(
            valid=not result.has_errors,
            issues=issues,
            metrics=metrics,
            elapsed_ms=result.elapsed_ms,
            validator_name=self.name,
        )
