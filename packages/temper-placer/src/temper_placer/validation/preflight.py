"""
Pre-flight validation checks for PCB placement optimization.

This module provides checks that should run BEFORE optimization starts:
- External tool availability (kicad-cli, ngspice)
- Components have zone assignments
- Zones fit on board
- No impossible constraints

These are distinct from validation.geometric and validation.drc which
validate a completed placement.

Wave 4 Phase 4: the decision compute — the zone AABB predicate
(``_zones_overlap``), the zone-fit boundary checks and reason-string
selection, the have-zones set arithmetic, and the impossible-constraints
bounds/set checks — is implemented in Rust as the ``validation`` submodule
of ``temper_design_bundle_python`` (``temper-design-bundle/src/validation.rs``)
and delegated to here. This module keeps the dataclasses
(``PreflightIssue``/``PreflightResult``/``PreflightSeverity``), the
tool-availability checks (``shutil.which`` / ``find_kicad_cli`` are I/O
boundaries), the netlist<->board reconciliation check (an orchestration
over the reconciliation surface, itself migrated), and the message
assembly wherever a no-format ``str(float)`` interpolation is involved
(ZONE_003's suggestion and ZONE_005's message — Rust ``Display`` renders
``10.0`` as ``10``; CPython renders ``10.0``).

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/validation/test_preflight_rust_differential.py`` (oracle:
``tests/validation/_preflight_py_oracle.py``); the structural proof lives
in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import temper_design_bundle_python as _tdb

from temper_placer.core.board import Zone
from temper_placer.core.netlist import Netlist
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.validation.drc import find_kicad_cli


class PreflightSeverity(Enum):
    """Severity levels for preflight issues."""

    INFO = auto()  # Informational (e.g., optional tool available)
    WARNING = auto()  # Potential issue but can proceed
    ERROR = auto()  # Problem that should be fixed before optimization


@dataclass
class PreflightIssue:
    """A single issue found during preflight checks."""

    severity: PreflightSeverity
    code: str  # Machine-readable code (e.g., "ZONE_001")
    message: str  # Human-readable description
    suggestion: str = ""  # Actionable suggestion for fixing
    components: list[str] = field(default_factory=list)  # Affected components
    details: dict = field(default_factory=dict)  # Additional data


@dataclass
class PreflightResult:
    """Result of running all preflight checks."""

    passed: bool  # True if no ERROR-level issues
    issues: list[PreflightIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == PreflightSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == PreflightSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == PreflightSeverity.INFO)

    def merge(self, other: PreflightResult) -> PreflightResult:
        """Merge another result into this one."""
        return PreflightResult(
            passed=self.passed and other.passed,
            issues=self.issues + other.issues,
        )


# =============================================================================
# External Tool Checks
# =============================================================================


def check_kicad_cli() -> PreflightResult:
    """
    Check if kicad-cli is available.

    Returns:
        PreflightResult with info about kicad-cli availability.
    """
    issues = []
    cli_path = find_kicad_cli()

    if cli_path:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.INFO,
                code="TOOL_001",
                message=f"kicad-cli found at: {cli_path}",
            )
        )
        return PreflightResult(passed=True, issues=issues)
    else:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.WARNING,
                code="TOOL_002",
                message="kicad-cli not found - DRC validation will be skipped",
                suggestion=(
                    "Install KiCad 7+ to enable DRC validation. "
                    "On macOS: brew install --cask kicad. "
                    "On Linux: apt install kicad. "
                    "Or download from https://www.kicad.org/download/"
                ),
            )
        )
        return PreflightResult(passed=True, issues=issues)  # Warning, not error


def check_ngspice() -> PreflightResult:
    """
    Check if ngspice is available.

    Returns:
        PreflightResult with info about ngspice availability.
    """
    issues = []
    ngspice_path = shutil.which("ngspice")

    if ngspice_path:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.INFO,
                code="TOOL_003",
                message=f"ngspice found at: {ngspice_path}",
            )
        )
        return PreflightResult(passed=True, issues=issues)
    else:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.WARNING,
                code="TOOL_004",
                message="ngspice not found - SPICE validation will be skipped",
                suggestion=(
                    "Install ngspice for electrical validation. "
                    "On macOS: brew install ngspice. "
                    "On Linux: apt install ngspice. "
                    "On Windows: download from https://ngspice.sourceforge.io/"
                ),
            )
        )
        return PreflightResult(passed=True, issues=issues)  # Warning, not error


def check_external_tools() -> PreflightResult:
    """
    Check availability of all external tools.

    Returns:
        Combined PreflightResult for all tool checks.
    """
    result = check_kicad_cli()
    result = result.merge(check_ngspice())
    return result


# =============================================================================
# Zone Assignment Checks
# =============================================================================

#: Map the Rust kernel's severity strings back onto the enum.
_SEVERITY = {
    "INFO": PreflightSeverity.INFO,
    "WARNING": PreflightSeverity.WARNING,
    "ERROR": PreflightSeverity.ERROR,
}


def _wrap_issues(raw_issues: list[dict]) -> list[PreflightIssue]:
    """Wrap the Rust kernels' ``{severity, code, message, suggestion,
    components, details}`` dicts into ``PreflightIssue`` dataclasses."""
    return [
        PreflightIssue(
            severity=_SEVERITY[i["severity"]],
            code=i["code"],
            message=i["message"],
            suggestion=i["suggestion"],
            components=list(i["components"]),
            details=dict(i["details"]),
        )
        for i in raw_issues
    ]


def check_components_have_zones(
    netlist: Netlist,
    constraints: PlacementConstraints,
    require_all: bool = False,
) -> PreflightResult:
    """
    Check that components in netlist have zone assignments.

    Args:
        netlist: Parsed netlist from KiCad PCB.
        constraints: Loaded constraint configuration.
        require_all: If True, ERROR if any component lacks zone. If False, WARNING.

    Returns:
        PreflightResult with unassigned component issues.
    """
    netlist_refs = [c.ref for c in netlist.components]

    # Get components assigned to zones (from constraints) — set semantics
    # (dedup) are applied on the Rust side, so list order here is irrelevant.
    assigned_refs: list[str] = list(constraints.zone_assignments.keys())
    for zone in constraints.zones:
        assigned_refs.extend(zone.components)
    for group in constraints.component_groups:
        if group.zone:
            assigned_refs.extend(group.components)

    fixed_refs = list(constraints.fixed_components)

    passed, raw_issues = _tdb.validation.preflight_unassigned(
        netlist_refs, assigned_refs, fixed_refs, require_all
    )
    return PreflightResult(passed=passed, issues=_wrap_issues(raw_issues))


# =============================================================================
# Zone Geometry Checks
# =============================================================================


def check_zones_fit_on_board(
    constraints: PlacementConstraints,
) -> PreflightResult:
    """
    Check that all zones fit within board boundaries.

    Args:
        constraints: Loaded constraint configuration.

    Returns:
        PreflightResult with zone boundary issues.
    """
    board_w = constraints.board_width_mm
    board_h = constraints.board_height_mm

    passed, outside, overlaps = _tdb.validation.preflight_zones_fit(
        [(z.name, tuple(z.bounds)) for z in constraints.zones],
        board_w,
        board_h,
    )

    issues = []

    # ZONE_003 — the suggestion interpolates no-format str(float) board
    # dimensions, so it is assembled here (Rust Display renders 10.0 as 10).
    for zone_name, reasons in outside:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.ERROR,
                code="ZONE_003",
                message=f"Zone '{zone_name}' extends outside board boundaries",
                suggestion=(
                    f"Adjust zone bounds to fit within 0-{board_w}mm x 0-{board_h}mm. "
                    f"Issues: {'; '.join(reasons)}"
                ),
                details={"zone_name": zone_name, "reasons": list(reasons)},
            )
        )

    if outside:
        return PreflightResult(passed=False, issues=issues)

    # Overlapping zones (warning, not error) — pairs in the oracle's
    # enumerate order, from the kernel.
    for zone1, zone2 in overlaps:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.WARNING,
                code="ZONE_004",
                message=f"Zones '{zone1}' and '{zone2}' overlap",
                suggestion="Overlapping zones may cause placement conflicts. Review zone boundaries.",
                details={"zones": [zone1, zone2]},
            )
        )

    if not issues:
        # ZONE_005's message interpolates no-format str(float) dimensions.
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.INFO,
                code="ZONE_005",
                message=f"All {len(constraints.zones)} zones fit within board ({board_w}x{board_h}mm)",
            )
        )

    return PreflightResult(passed=True, issues=issues)


def _zones_overlap(zone1: Zone, zone2: Zone) -> bool:
    """Check if two zones overlap (simple AABB check) — the Rust kernel."""
    # ``bounds`` may be a ``Rect`` pyclass (iterable, tuple-compatible) or a
    # bare 4-tuple; the kernel consumes plain floats.
    a = tuple(zone1.bounds)
    b = tuple(zone2.bounds)
    return _tdb.validation.zones_overlap(a, b)


# =============================================================================
# Constraint Feasibility Checks
# =============================================================================


def check_impossible_constraints(
    netlist: Netlist,
    constraints: PlacementConstraints,
) -> PreflightResult:
    """
    Check for impossible or conflicting constraints.

    Checks for:
    - Components constrained to zones smaller than component bounds
    - Circular dependencies in component groups
    - Mutual exclusion conflicts

    Args:
        netlist: Parsed netlist from KiCad PCB.
        constraints: Loaded constraint configuration.

    Returns:
        PreflightResult with constraint issues.
    """
    passed, raw_issues = _tdb.validation.preflight_impossible(
        [(c.ref, c.bounds[0], c.bounds[1]) for c in netlist.components],
        [(z.name, tuple(z.bounds)) for z in constraints.zones],
        list(constraints.zone_assignments.items()),
        [(g.name, g.zone or "", list(g.components)) for g in constraints.component_groups],
        [list(t.components) for t in constraints.thermal_constraints],
    )
    return PreflightResult(passed=passed, issues=_wrap_issues(raw_issues))


# =============================================================================
# Netlist <-> Board Reconciliation Check
# =============================================================================


def check_netlist_board_reconciliation(
    board_path: Path | str,
    design_netlist_path: Path | str,
) -> PreflightResult:
    """Reconcile the netlist extracted from the actual board file against the
    compiled design netlist, keyed by instance path and net membership (R16).

    Produces an ERROR-level ``PreflightIssue`` per reconciliation finding
    (MISSING / EXTRA / RENUMBERED / REUSE / UNKEYABLE / NET-MISSING /
    NET-EXTRA / NET-MEMBERSHIP). A fail-closed condition (missing or
    unparseable board/netlist) is reported as an ERROR issue with code
    ``RECON_GATE_ERROR`` -- never as a silent pass.

    This is the identity authority. ``preflight_identity``'s 95% refdes
    overlap check stays in the preflight surface but is demoted to a
    secondary signal -- it is structurally blind to a wholesale renumber
    (KTD3/KTD4 of plan 2026-08-02-021).

    Args:
        board_path: Path to the ``.kicad_pcb`` board file.
        design_netlist_path: Path to the compiled design netlist
            (``elec/build/default.net``).
    """
    from temper_placer.validation.netlist_reconciliation import (
        ReconciliationGateError,
        extract_board_netlist,
        parse_design_netlist,
        reconcile,
    )

    try:
        board = extract_board_netlist(board_path)
        design = parse_design_netlist(design_netlist_path)
        report = reconcile(board, design)
    except ReconciliationGateError as exc:
        return PreflightResult(
            passed=False,
            issues=[
                PreflightIssue(
                    severity=PreflightSeverity.ERROR,
                    code="RECON_GATE_ERROR",
                    message=f"Netlist<->board reconciliation could not run: {exc}",
                )
            ],
        )

    if report.passed:
        return PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(
                    severity=PreflightSeverity.INFO,
                    code="RECON_000",
                    message=(
                        f"Netlist<->board reconciliation passed: "
                        f"{report.matched_paths} component(s) matched by "
                        f"instance path, {report.design_nets_nonempty} design "
                        f"net(s) / {report.board_nets} board net(s) reconciled, "
                        f"0 findings"
                    ),
                )
            ],
        )

    issues = []
    for finding in report.findings:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.ERROR,
                code=f"RECON_{finding.kind}",
                message=finding.detail,
                components=list(finding.refs),
                details={"kind": finding.kind, "paths": list(finding.paths)},
            )
        )
    return PreflightResult(passed=False, issues=issues)


# =============================================================================
# Combined Preflight Check
# =============================================================================


def run_all_preflight_checks(
    netlist: Netlist | None,
    constraints: PlacementConstraints | None,
    check_tools: bool = True,
    require_zone_assignments: bool = False,
    board_path: Path | str | None = None,
    design_netlist_path: Path | str | None = None,
) -> PreflightResult:
    """
    Run all preflight checks.

    Args:
        netlist: Parsed netlist (optional, some checks skipped if None).
        constraints: Loaded constraints (optional, some checks skipped if None).
        check_tools: Whether to check external tool availability.
        require_zone_assignments: If True, missing zone assignments are errors.
        board_path: Optional path to the ``.kicad_pcb`` board file. When given
            together with ``design_netlist_path``, runs the netlist<->board
            reconciliation oracle (R16) as part of the preflight surface.
        design_netlist_path: Optional path to the compiled design netlist
            (``elec/build/default.net``) for the reconciliation check.

    Returns:
        Combined PreflightResult from all checks.
    """
    result = PreflightResult(passed=True, issues=[])

    # Tool checks
    if check_tools:
        result = result.merge(check_external_tools())

    # Netlist <-> board reconciliation oracle (R16): the identity authority,
    # keyed by instance path and net membership -- not refdes overlap.
    if board_path is not None and design_netlist_path is not None:
        result = result.merge(
            check_netlist_board_reconciliation(board_path, design_netlist_path)
        )

    # Constraint checks (require both netlist and constraints)
    if constraints:
        result = result.merge(check_zones_fit_on_board(constraints))

        if netlist:
            result = result.merge(
                check_components_have_zones(
                    netlist, constraints, require_all=require_zone_assignments
                )
            )
            result = result.merge(check_impossible_constraints(netlist, constraints))

    return result
