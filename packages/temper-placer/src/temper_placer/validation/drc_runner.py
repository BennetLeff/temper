"""
KiCad DRC runner - programmatic interface to kicad-cli DRC.

This module wraps kicad-cli to run Design Rule Checks on PCB files
and parse the results into structured data.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


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
    """

    error_count: int
    warning_count: int
    errors: list[DrcError] = field(default_factory=list)
    warnings: list[DrcWarning] = field(default_factory=list)


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

    except subprocess.TimeoutExpired as e:
        raise DrcRunnerError("DRC timed out after 60 seconds") from e
    except subprocess.SubprocessError as e:
        raise DrcRunnerError(f"Failed to run kicad-cli: {e}") from e
    finally:
        # Clean up JSON file
        if json_path.exists():
            with contextlib.suppress(OSError):
                json_path.unlink()


# =========================================================================
#  CheckRunner — delegates to the Rust DRC engine (temper_drc_rs)
#
#  Formerly in temper_drc.core.runner.  Preserves the same public
#  interface but calls ``temper_drc_rs.run_drc()`` under the hood.
#  Converts Python ``Placement`` / ``ConstraintSet`` objects into the
#  K1-schema dict format that the Rust engine expects, then maps
#  returned violation dicts back to Python ``CheckResult`` / ``Issue``
#  objects.
# =========================================================================

import time as _time
from dataclasses import dataclass as _dataclass
from typing import TYPE_CHECKING as _TYPE_CHECKING, Any as _Any

from temper_placer.validation.drc_result import (
    CheckResult as _CheckResult,
    Check as _Check,
    Issue as _Issue,
    Location as _Location,
    RunResult as _RunResult,
    Severity as _Severity,
)

if _TYPE_CHECKING:
    from temper_placer.validation.drc_types import ConstraintSet as _ConstraintSet
    from temper_placer.validation.drc_types import Placement as _Placement

# Severity string → Severity enum
_SEVERITY_MAP: dict[str, _Severity] = {
    "INFO": _Severity.INFO,
    "WARNING": _Severity.WARNING,
    "ERROR": _Severity.ERROR,
    "CRITICAL": _Severity.CRITICAL,
}


def _placement_to_board_dict(placement: _Placement) -> dict[str, _Any]:
    """Convert a ``Placement`` to the K1-schema board dict."""
    components: list[dict[str, _Any]] = []
    for ref, comp in placement.components.items():
        side = "bottom" if comp.layer and "B" in (comp.layer or "") else "top"
        components.append(
            {
                "ref": comp.ref,
                "x": comp.x,
                "y": comp.y,
                "rot": comp.rotation,
                "side": side,
                "width": comp.width,
                "height": comp.height,
                "net_class": comp.net_class,
                "voltage_domain": comp.voltage_domain,
                "package_type": "smd",
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "vent_direction": None,
                "footprint_polygon": None,
            }
        )

    zones_list: list[dict[str, _Any]] = []
    for name, bounds in placement.zones.items():
        zones_list.append({"name": name, "bounds": list(bounds)})

    board_dict: dict[str, _Any] = {
        "board": {
            "width_mm": placement.board_width,
            "height_mm": placement.board_height,
            "margin_mm": 3.0,
        },
        "components": components,
        "nets": dict(placement.nets),
        "net_classes": dict(placement.net_classes),
        "zones": zones_list,
    }

    if placement.via_placement is not None:
        via_list: list[dict[str, _Any]] = []
        for via in placement.via_placement.vias:
            via_list.append(
                {
                    "position": list(via.position),
                    "from_layer": via.from_layer,
                    "to_layer": via.to_layer,
                    "diameter": via.diameter,
                    "drill": via.drill,
                    "net_name": via.net_name,
                }
            )
        board_dict["vias"] = via_list

    if placement.trace_placement is not None:
        seg_list: list[dict[str, _Any]] = []
        for seg in placement.trace_placement.segments:
            seg_list.append(
                {
                    "net_name": seg.net_name,
                    "layer": seg.layer,
                    "width": seg.width,
                    "start": list(seg.start),
                    "end": list(seg.end),
                }
            )
        board_dict["traces"] = seg_list

    return board_dict


def _constraints_to_dict(constraints: _ConstraintSet) -> dict[str, _Any]:
    """Convert a ``ConstraintSet`` to the dict format expected by ``temper_drc_rs``."""
    return {
        "clearances": [
            {
                "from_class": r.from_class,
                "to_class": r.to_class,
                "clearance_mm": r.min_mm,
                "description": r.description,
            }
            for r in constraints.clearances
        ],
        "zones": [
            {
                "name": z.name,
                "bounds": list(z.bounds),
                "net_classes": z.net_classes,
                "components": z.components,
            }
            for z in constraints.zones
        ],
        "critical_loops": [
            {
                "name": l.name,
                "nets": l.nets,
                "max_area_mm2": l.max_area_mm2,
                "weight": l.weight,
                "description": l.description,
            }
            for l in constraints.critical_loops
        ],
        "thermal_constraints": [
            {
                "components": t.components,
                "prefer_edge": t.prefer_edge,
                "min_spacing_mm": t.min_spacing_mm,
                "max_distance_from_edge_mm": t.max_distance_from_edge_mm,
                "description": t.description,
            }
            for t in constraints.thermal_constraints
        ],
        "component_groups": [
            {
                "name": g.name,
                "components": g.components,
                "max_spread_mm": g.max_spread_mm,
                "zone": g.zone,
                "description": g.description,
            }
            for g in constraints.component_groups
        ],
        "net_classes": dict(constraints.net_classes),
        "voltage_domains": dict(constraints.voltage_domains),
        "hv_clearance_mm": constraints.hv_clearance_mm,
        "board": {
            "width_mm": constraints.board_width,
            "height_mm": constraints.board_height,
        },
    }


def _violations_to_run_result(
    violation_dicts: list[dict[str, _Any]],
    elapsed_ms: float = 0.0,
) -> _RunResult:
    """Convert a list of Rust DRC violation dicts to a ``RunResult``."""
    grouped: dict[str, list[dict[str, _Any]]] = {}
    for v in violation_dicts:
        name = v.get("check_name", "unknown")
        grouped.setdefault(name, []).append(v)

    check_results: list[_CheckResult] = []
    for check_name, violations in sorted(grouped.items()):
        issues: list[_Issue] = []
        has_failure = False
        for v in violations:
            severity_str = v.get("severity", "ERROR").upper()
            severity = _SEVERITY_MAP.get(severity_str, _Severity.ERROR)
            if severity in (_Severity.ERROR, _Severity.CRITICAL):
                has_failure = True

            loc_dict = v.get("location")
            location = None
            if loc_dict is not None and isinstance(loc_dict, dict):
                location = _Location(
                    x=loc_dict.get("x"),
                    y=loc_dict.get("y"),
                    layer=loc_dict.get("layer"),
                )

            issue = _Issue(
                severity=severity,
                code=v.get("code", "DRC_RS_000"),
                message=v.get("message", ""),
                category=v.get("category", "drc"),
                check_name=check_name,
                affected_items=v.get("affected_items", []),
                location=location,
                details=v.get("details", {}),
            )
            issues.append(issue)

        check_results.append(
            _CheckResult(
                check_name=check_name,
                passed=not has_failure,
                issues=issues,
            )
        )

    return _RunResult(check_results=check_results, total_elapsed_ms=elapsed_ms)


@_dataclass
class CheckRunner:
    """
    Orchestrates running multiple checks — delegates to the Rust DRC engine.

    The runner preserves the same public interface as before but ignores
    the Python ``Check`` subclasses (they are kept as import-compatibility
    stubs).  Actual check execution is done by ``temper_drc_rs.run_drc()``.

    Example::

        runner = CheckRunner()
        result = runner.run(placement, constraints)

        if not result.passed:
            for issue in result.all_issues:
                print(f"[{issue.code}] {issue.message}")
    """

    checks: list[_Check] = field(default_factory=list)

    def add_check(self, check: _Check) -> CheckRunner:
        """Add a single check (for import-compatibility; ignored by run)."""
        self.checks.append(check)
        return self

    def add_checks(self, checks: list[_Check]) -> CheckRunner:
        """Add multiple checks (for import-compatibility; ignored by run)."""
        self.checks.extend(checks)
        return self

    def clear(self) -> CheckRunner:
        """Remove all checks from the runner."""
        self.checks.clear()
        return self

    def get_checks_by_category(self, category: str) -> list[_Check]:
        """Get all checks in a specific category."""
        return [c for c in self.checks if c.category == category]

    def run(
        self,
        placement: _Placement,
        constraints: _ConstraintSet,
        categories: list[str] | None = None,
        check_names: list[str] | None = None,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> _RunResult:
        """
        Run DRC checks via the Rust engine.

        Converts ``Placement`` / ``ConstraintSet`` to dicts, calls
        ``temper_drc_rs.run_drc()``, and maps the returned violation dicts
        to Python ``CheckResult`` objects.
        """
        try:
            import temper_drc_rs  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "The temper-drc Rust engine is required. "
                "Install it with: pip install temper-drc-rs"
            ) from exc

        board_dict = _placement_to_board_dict(placement)
        constraints_dict = _constraints_to_dict(constraints)

        start_time = _time.time()

        kwargs: dict[str, _Any] = {}
        if categories is not None:
            kwargs["categories"] = categories
        if check_names is not None:
            kwargs["check_names"] = check_names

        violation_dicts: list[dict[str, _Any]] = temper_drc_rs.run_drc(
            board_dict,
            constraints_dict,
            **kwargs,
        )

        elapsed_ms = (_time.time() - start_time) * 1000
        return _violations_to_run_result(violation_dicts, elapsed_ms=elapsed_ms)

    def run_single(
        self,
        check_name: str,
        placement: _Placement,
        constraints: _ConstraintSet,
    ) -> _CheckResult | None:
        """Run a single check by name via the Rust engine."""
        result = self.run(
            placement,
            constraints,
            check_names=[check_name],
        )
        for cr in result.check_results:
            if cr.check_name == check_name:
                return cr
        return None

    @property
    def check_names(self) -> list[str]:
        """List of all check names in this runner."""
        return [c.name for c in self.checks]

    @property
    def categories(self) -> set[str]:
        """Set of all categories represented in this runner."""
        return {c.category for c in self.checks}

    def summary(self) -> str:
        """Get a summary of registered checks."""
        lines = [f"CheckRunner with {len(self.checks)} checks:"]

        by_category: dict[str, list[str]] = {}
        for check in self.checks:
            if check.category not in by_category:
                by_category[check.category] = []
            by_category[check.category].append(check.name)

        for category, names in sorted(by_category.items()):
            lines.append(f"  {category.upper()}: {', '.join(names)}")

        return "\n".join(lines)
