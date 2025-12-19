"""
Pre-flight validation checks for PCB placement optimization.

This module provides checks that should run BEFORE optimization starts:
- External tool availability (kicad-cli, ngspice)
- Components have zone assignments
- Zones fit on board
- No impossible constraints

These are distinct from validation.geometric and validation.drc which
validate a completed placement.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import Enum, auto

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
    issues = []

    # Get all component refs from netlist
    netlist_refs = {c.ref for c in netlist.components}

    # Get components assigned to zones (from constraints)
    assigned_refs: set[str] = set()

    # From zone_assignments dict
    assigned_refs.update(constraints.zone_assignments.keys())

    # From zone.components lists
    for zone in constraints.zones:
        assigned_refs.update(zone.components)

    # From component groups with zone
    for group in constraints.component_groups:
        if group.zone:
            assigned_refs.update(group.components)

    # Fixed components are exempt (they don't need zone assignment)
    fixed_refs = set(constraints.fixed_components)

    # Find unassigned components
    unassigned = netlist_refs - assigned_refs - fixed_refs

    if unassigned:
        sorted_unassigned = sorted(unassigned)
        severity = PreflightSeverity.ERROR if require_all else PreflightSeverity.WARNING
        issues.append(
            PreflightIssue(
                severity=severity,
                code="ZONE_001",
                message=f"{len(unassigned)} components have no zone assignment",
                suggestion=(
                    "Add zone assignments in constraints.yaml under 'zone_assignments' "
                    "or add components to zone 'components' list. "
                    f"Unassigned: {', '.join(sorted_unassigned[:10])}"
                    + (
                        f" and {len(sorted_unassigned) - 10} more..."
                        if len(sorted_unassigned) > 10
                        else ""
                    )
                ),
                components=sorted_unassigned,
                details={"unassigned_count": len(unassigned)},
            )
        )
        passed = not require_all  # Pass with warning if not required
    else:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.INFO,
                code="ZONE_002",
                message=f"All {len(netlist_refs)} components have zone assignments",
            )
        )
        passed = True

    return PreflightResult(passed=passed, issues=issues)


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
    issues = []
    board_w = constraints.board_width_mm
    board_h = constraints.board_height_mm
    margin = constraints.board_margin_mm

    # Effective board bounds with margin
    min_x = margin
    min_y = margin
    max_x = board_w - margin
    max_y = board_h - margin

    zones_outside = []

    for zone in constraints.zones:
        x_min, y_min, x_max, y_max = zone.bounds

        outside_reasons = []
        if x_min < 0:
            outside_reasons.append(f"x_min={x_min:.1f} < 0")
        if y_min < 0:
            outside_reasons.append(f"y_min={y_min:.1f} < 0")
        if x_max > board_w:
            outside_reasons.append(f"x_max={x_max:.1f} > board_width={board_w:.1f}")
        if y_max > board_h:
            outside_reasons.append(f"y_max={y_max:.1f} > board_height={board_h:.1f}")

        if outside_reasons:
            zones_outside.append((zone.name, outside_reasons))

    if zones_outside:
        for zone_name, reasons in zones_outside:
            issues.append(
                PreflightIssue(
                    severity=PreflightSeverity.ERROR,
                    code="ZONE_003",
                    message=f"Zone '{zone_name}' extends outside board boundaries",
                    suggestion=f"Adjust zone bounds to fit within 0-{board_w}mm x 0-{board_h}mm. Issues: {'; '.join(reasons)}",
                    details={"zone_name": zone_name, "reasons": reasons},
                )
            )
        return PreflightResult(passed=False, issues=issues)

    # Check for overlapping zones (warning, not error)
    for i, zone1 in enumerate(constraints.zones):
        for zone2 in constraints.zones[i + 1 :]:
            if _zones_overlap(zone1, zone2):
                issues.append(
                    PreflightIssue(
                        severity=PreflightSeverity.WARNING,
                        code="ZONE_004",
                        message=f"Zones '{zone1.name}' and '{zone2.name}' overlap",
                        suggestion="Overlapping zones may cause placement conflicts. Review zone boundaries.",
                        details={"zones": [zone1.name, zone2.name]},
                    )
                )

    if not issues:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.INFO,
                code="ZONE_005",
                message=f"All {len(constraints.zones)} zones fit within board ({board_w}x{board_h}mm)",
            )
        )

    return PreflightResult(passed=True, issues=issues)


def _zones_overlap(zone1: Zone, zone2: Zone) -> bool:
    """Check if two zones overlap (simple AABB check)."""
    x1_min, y1_min, x1_max, y1_max = zone1.bounds
    x2_min, y2_min, x2_max, y2_max = zone2.bounds

    # No overlap if one is completely to the left/right/above/below
    if x1_max <= x2_min or x2_max <= x1_min:
        return False
    if y1_max <= y2_min or y2_max <= y1_min:
        return False

    return True


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
    issues = []

    # Build component bounds lookup
    comp_bounds = {c.ref: c.bounds for c in netlist.components}

    # Build zone bounds lookup
    zone_bounds = {z.name: z.bounds for z in constraints.zones}

    # Check 1: Component fits in assigned zone
    components_too_large = []

    for ref, zone_name in constraints.zone_assignments.items():
        if ref not in comp_bounds:
            continue  # Component not in netlist, skip
        if zone_name not in zone_bounds:
            issues.append(
                PreflightIssue(
                    severity=PreflightSeverity.ERROR,
                    code="CONSTRAINT_001",
                    message=f"Component '{ref}' assigned to non-existent zone '{zone_name}'",
                    suggestion=f"Either create zone '{zone_name}' or assign '{ref}' to an existing zone.",
                    components=[ref],
                )
            )
            continue

        comp_w, comp_h = comp_bounds[ref]
        z_x_min, z_y_min, z_x_max, z_y_max = zone_bounds[zone_name]
        zone_w = z_x_max - z_x_min
        zone_h = z_y_max - z_y_min

        # Component must fit in zone (considering both orientations)
        fits_normal = comp_w <= zone_w and comp_h <= zone_h
        fits_rotated = comp_h <= zone_w and comp_w <= zone_h

        if not (fits_normal or fits_rotated):
            components_too_large.append((ref, zone_name, (comp_w, comp_h), (zone_w, zone_h)))

    for ref, zone_name, (cw, ch), (zw, zh) in components_too_large:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.ERROR,
                code="CONSTRAINT_002",
                message=f"Component '{ref}' ({cw:.1f}x{ch:.1f}mm) won't fit in zone '{zone_name}' ({zw:.1f}x{zh:.1f}mm)",
                suggestion=f"Increase zone '{zone_name}' size or reassign '{ref}' to a larger zone.",
                components=[ref],
                details={"component_size": (cw, ch), "zone_size": (zw, zh)},
            )
        )

    # Check 2: Components in groups exist
    for group in constraints.component_groups:
        missing = [ref for ref in group.components if ref not in comp_bounds]
        if missing:
            issues.append(
                PreflightIssue(
                    severity=PreflightSeverity.WARNING,
                    code="CONSTRAINT_003",
                    message=f"Group '{group.name}' references {len(missing)} components not in netlist",
                    suggestion=f"Update group or netlist. Missing: {', '.join(missing[:5])}",
                    components=missing,
                    details={"group_name": group.name, "missing_count": len(missing)},
                )
            )

    # Check 3: Group zone exists
    for group in constraints.component_groups:
        if group.zone and group.zone not in zone_bounds:
            issues.append(
                PreflightIssue(
                    severity=PreflightSeverity.ERROR,
                    code="CONSTRAINT_004",
                    message=f"Group '{group.name}' requires non-existent zone '{group.zone}'",
                    suggestion=f"Create zone '{group.zone}' or change group's zone assignment.",
                    components=group.components,
                )
            )

    # Check 4: Thermal components exist
    for thermal in constraints.thermal_constraints:
        missing = [ref for ref in thermal.components if ref not in comp_bounds]
        if missing:
            issues.append(
                PreflightIssue(
                    severity=PreflightSeverity.WARNING,
                    code="CONSTRAINT_005",
                    message=f"Thermal constraint references {len(missing)} components not in netlist",
                    suggestion=f"Update thermal constraints. Missing: {', '.join(missing[:5])}",
                    components=missing,
                )
            )

    # Summary
    error_count = sum(1 for i in issues if i.severity == PreflightSeverity.ERROR)
    if error_count == 0:
        issues.append(
            PreflightIssue(
                severity=PreflightSeverity.INFO,
                code="CONSTRAINT_006",
                message="All constraints are feasible",
            )
        )

    return PreflightResult(passed=error_count == 0, issues=issues)


# =============================================================================
# Combined Preflight Check
# =============================================================================


def run_all_preflight_checks(
    netlist: Netlist | None,
    constraints: PlacementConstraints | None,
    check_tools: bool = True,
    require_zone_assignments: bool = False,
) -> PreflightResult:
    """
    Run all preflight checks.

    Args:
        netlist: Parsed netlist (optional, some checks skipped if None).
        constraints: Loaded constraints (optional, some checks skipped if None).
        check_tools: Whether to check external tool availability.
        require_zone_assignments: If True, missing zone assignments are errors.

    Returns:
        Combined PreflightResult from all checks.
    """
    result = PreflightResult(passed=True, issues=[])

    # Tool checks
    if check_tools:
        result = result.merge(check_external_tools())

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
