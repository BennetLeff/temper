"""
Ground plane continuity validation functions.

These functions check if a PCB layout meets EMC/EMI ground plane requirements
per REQ-EMC-01.
"""

from dataclasses import dataclass

from ._geometry import _distance, _polylines_intersect


@dataclass
class GroundPlaneViolation:
    """A ground plane continuity violation."""

    code: str
    message: str
    location: tuple[float, float] | None = None
    severity: str = "error"  # error, warning


@dataclass
class GroundPlaneResult:
    """Result of ground plane validation."""

    passed: bool
    violations: list[GroundPlaneViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_slot_lengths(ground_plane_geometry, max_slot_mm: float = 30.0) -> GroundPlaneResult:
    """
    Check that no slots in ground plane exceed maximum length.

    Slots act as antennas at frequencies where slot length ≈ λ/2.
    For 150 MHz harmonics (λ = 2m), slots >10cm are problematic.
    Conservative limit: 30mm.

    Args:
        ground_plane_geometry: Ground plane geometry (slots, cutouts)
        max_slot_mm: Maximum allowed slot length

    Returns:
        GroundPlaneResult with violations
    """
    violations: list[GroundPlaneViolation] = []
    slots = ground_plane_geometry.get("slots", []) if ground_plane_geometry else []

    for slot in slots:
        length = _distance(slot["start"], slot["end"])
        if length > max_slot_mm:
            violations.append(
                GroundPlaneViolation(
                    code="GP-001",
                    message=(
                        f"Ground plane slot is {length:.1f}mm long, exceeding the "
                        f"{max_slot_mm}mm slot-antenna limit"
                    ),
                    location=slot["start"],
                    severity="error",
                )
            )

    return GroundPlaneResult(passed=len(violations) == 0, violations=violations)


def check_signal_ground_reference(traces, ground_plane) -> GroundPlaneResult:
    """
    Verify each signal trace has solid ground return path.

    Critical for EMI - signals without ground reference radiate.

    Args:
        traces: Signal trace geometry
        ground_plane: Ground plane geometry

    Returns:
        GroundPlaneResult with violations for traces without ground reference
    """
    violations: list[GroundPlaneViolation] = []
    slots = ground_plane.get("slots", []) if ground_plane else []

    for trace in traces:
        path = trace.get("path", [])
        net = trace.get("net", "<unknown>")
        for slot in slots:
            slot_line = [slot["start"], slot["end"]]
            if _polylines_intersect(path, slot_line):
                violations.append(
                    GroundPlaneViolation(
                        code="GP-002",
                        message=(
                            f"Signal {net} crosses a ground plane slot -- loses solid "
                            "ground reference at the crossing"
                        ),
                        location=path[0] if path else None,
                        severity="error",
                    )
                )
                break  # one violation per trace is enough; don't double-count multi-slot crossings

    return GroundPlaneResult(passed=len(violations) == 0, violations=violations)


def check_star_ground_point(ground_domains) -> GroundPlaneResult:
    """
    Verify single connection point between PGND and CGND (star ground).

    Multiple connections create ground loops and EMI issues.

    Args:
        ground_domains: Ground domain definitions (PGND, CGND, ISOGND)

    Returns:
        GroundPlaneResult with violations if multiple connection points found
    """
    # A domain is treated as *isolated* (an isolation-barrier side, not a
    # same-domain split-plane) either because its own entry says so
    # (``{"isolated": True}``) or because it is named like one (contains
    # "ISO", matching the ``ISOGND`` convention this function's own
    # docstring and the pre-existing test fixtures use).
    #
    # Two different failure modes live in this one check, and conflating
    # them is exactly the bug this validator must not re-introduce (see
    # docs/hardware/SELV_ISOLATION_REDESIGN.md -- the removed
    # `power_return ~ gnd` star join shorted a 4.2kVAC isolation barrier):
    #
    #   * Between two *non-isolated* domains (e.g. a plain PGND/CGND split
    #     within one electrical system), a single direct tie is the correct
    #     "star ground" pattern; more than one creates a ground loop.
    #   * Into an *isolated* domain, a bare/direct connection is a barrier
    #     violation regardless of how many there are -- ONE unmarked direct
    #     tie is exactly what shorted the barrier here. Any coupling across
    #     that boundary must be tagged as going through a real isolation
    #     device (``component_type`` such as "capacitor"/"transformer"/
    #     "optocoupler"/"relay", or an explicit ``isolated_via`` marker).
    domains = {k: v for k, v in ground_domains.items() if k != "connections"}
    connections = ground_domains.get("connections", [])

    def _is_isolated(domain_name: str) -> bool:
        meta = domains.get(domain_name, {})
        if isinstance(meta, dict) and meta.get("isolated"):
            return True
        return "iso" in domain_name.lower()

    _ISOLATION_MARKERS = {"capacitor", "transformer", "optocoupler", "opto", "relay"}

    def _has_isolation_marker(conn: dict) -> bool:
        if conn.get("isolated_via"):
            return True
        component_type = conn.get("component_type")
        return bool(component_type) and str(component_type).lower() in _ISOLATION_MARKERS

    violations: list[GroundPlaneViolation] = []
    pair_connections: dict[tuple[str, str], list[dict]] = {}
    for conn in connections:
        pair = tuple(sorted((conn["from"], conn["to"])))
        pair_connections.setdefault(pair, []).append(conn)

    for (dom_a, dom_b), conns in pair_connections.items():
        barrier = _is_isolated(dom_a) or _is_isolated(dom_b)
        if barrier:
            for conn in conns:
                if not _has_isolation_marker(conn):
                    violations.append(
                        GroundPlaneViolation(
                            code="SG-003",
                            message=(
                                f"Direct (non-isolated) connection between {dom_a} and "
                                f"{dom_b} crosses an isolation-barrier domain -- must go "
                                "through a real isolation device, not a bare tie"
                            ),
                            location=conn.get("location"),
                            severity="error",
                        )
                    )
        elif len(conns) > 1:
            violations.append(
                GroundPlaneViolation(
                    code="SG-001",
                    message=(
                        f"Multiple ({len(conns)}) connections between {dom_a} and "
                        f"{dom_b} -- star ground requires a single connection point, "
                        "not a ground loop"
                    ),
                    location=conns[0].get("location"),
                    severity="error",
                )
            )

    return GroundPlaneResult(passed=len(violations) == 0, violations=violations)


def check_via_stitching(boundary_geometry, max_spacing_mm: float = 5.0) -> GroundPlaneResult:
    """
    Check via stitching along ground plane split boundaries.

    Via stitching connects L2 and L4 ground pours to minimize impedance.

    Args:
        boundary_geometry: Ground split boundary geometry
        max_spacing_mm: Maximum spacing between stitching vias

    Returns:
        GroundPlaneResult with violations for gaps exceeding max spacing
    """
    start = boundary_geometry["start"]
    end = boundary_geometry["end"]
    vias = boundary_geometry.get("vias", [])
    boundary_length = _distance(start, end)

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    len2 = dx * dx + dy * dy

    def _project(via: tuple[float, float]) -> float:
        """Fraction of the boundary length a via projects onto, clamped to [0, 1]."""
        if len2 < 1e-12:
            return 0.0
        t = ((via[0] - start[0]) * dx + (via[1] - start[1]) * dy) / len2
        return max(0.0, min(1.0, t))

    positions = sorted(_project(v) * boundary_length for v in vias)
    checkpoints = [0.0, *positions, boundary_length]

    violations: list[GroundPlaneViolation] = []
    epsilon = 1e-6  # float-projection slack; avoids flagging an exact-spacing via as "too far"
    for i in range(len(checkpoints) - 1):
        gap = checkpoints[i + 1] - checkpoints[i]
        if gap > max_spacing_mm + epsilon:
            violations.append(
                GroundPlaneViolation(
                    code="GP-003",
                    message=(
                        f"Via stitching gap of {gap:.1f}mm exceeds the "
                        f"{max_spacing_mm}mm maximum spacing"
                    ),
                    severity="error",
                )
            )

    return GroundPlaneResult(passed=len(violations) == 0, violations=violations)
