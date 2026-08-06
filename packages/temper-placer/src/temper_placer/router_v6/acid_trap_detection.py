"""
Router V6 Stage 5.1: Detect and Fix Acid Traps

Detects acute angles in traces that can trap etchant during manufacturing.
Part of temper-vm3g (Stage 5 - Manufacturing DRC)

Wave 4 Phase B (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``_calculate_angle`` and ``_classify_severity`` delegate to ``temper_drc_rs``
(``dfm_calculate_angle_py`` / ``dfm_classify_severity_py``, PR #749) -- pure
scalar math with no gap between the kernel's contract and this module's.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import temper_drc_rs as _drc

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class AcidTrap:
    """An acid trap location in a trace."""

    net_name: str
    position: tuple[float, float]  # (x, y) of acute angle
    angle_degrees: float  # Angle at this vertex
    severity: str  # "low", "medium", "high"


@dataclass
class AcidTrapReport:
    """Report of all detected acid traps."""

    acid_traps: list[AcidTrap]
    # True iff the check crashed and this report is a substituted
    # empty/fallback report rather than a real result. See
    # docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md --
    # a crashed check must be visibly distinct from a clean run.
    errored: bool = False

    @property
    def trap_count(self) -> int:
        """Total number of acid traps."""
        return len(self.acid_traps)

    @property
    def critical_count(self) -> int:
        """Number of critical acid traps (< 45°)."""
        return sum(1 for trap in self.acid_traps if trap.severity == "high")

    @property
    def medium_count(self) -> int:
        """Number of medium-severity acid traps (45°–60°)."""
        return sum(1 for trap in self.acid_traps if trap.severity == "medium")

    @property
    def low_count(self) -> int:
        """Number of low-severity acid traps (60°–90°)."""
        return sum(1 for trap in self.acid_traps if trap.severity == "low")


def detect_acid_traps(
    routing_results: RoutingResults,
    min_angle_threshold: float = 90.0,
) -> AcidTrapReport:
    """
    Detect acid traps in routed traces.

    Acid traps are acute angles (< 90°) that can trap etchant
    during PCB manufacturing, leading to over-etching.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        min_angle_threshold: Minimum acceptable angle (degrees).
            Values above 90° are clamped to 90° with a warning
            (acid traps are defined as angles < 90°).

    Returns:
        AcidTrapReport with all detected acid traps

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = detect_acid_traps(results)
        >>> report.trap_count >= 0
        True
    """
    # ---- Validate and clamp threshold --------------------------------------
    if math.isnan(min_angle_threshold):
        # NaN threshold makes every ``angle < NaN`` False → zero traps.
        # Return early with an explicit warning rather than relying on the
        # implicit behaviour of NaN comparisons.
        warnings.warn(
            "min_angle_threshold is NaN — no angles can be below NaN. Returning empty report.",
            stacklevel=2,
        )
        return AcidTrapReport(acid_traps=[])

    # Any negative threshold -- finite or -inf -- means no angle can qualify.
    # This was `not math.isfinite(t) and t < 0`, which only -inf satisfies, so
    # a finite negative like -5.0 fell through and silently produced an empty
    # report with no warning (issue #752 defect 9). The predicate is NOT
    # `not isfinite(t) or t < 0`: that would swallow +inf, which must instead
    # reach the clamp below and become 90.0. NaN is already handled above.
    if min_angle_threshold < 0:
        warnings.warn(
            f"min_angle_threshold={min_angle_threshold}° is negative — "
            f"all angles are ≥ 0°, returning empty report.",
            stacklevel=2,
        )
        return AcidTrapReport(acid_traps=[])

    if min_angle_threshold > 90.0:
        warnings.warn(
            f"min_angle_threshold={min_angle_threshold}° exceeds 90° — "
            f"clamping to 90°. The acid-trap detector identifies acute "
            f"angles (< 90°), not obtuse bends.",
            stacklevel=2,
        )
        min_angle_threshold = 90.0

    acid_traps = []

    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Analyze path for acute angles.
        #
        # ``compiled_route.path`` is ``RoutePath | RoutePath3D`` (see
        # ``routing_results.CompiledRoute``). ``RoutePath`` exposes 2D
        # ``.coordinates``; ``RoutePath3D`` (used whenever the router takes
        # a multi-layer/via detour -- i.e. any board with vias, such as
        # this one's 48) instead exposes ``.segments`` as
        # ``list[(x, y, layer)]`` triples and has no ``.coordinates``
        # attribute at all. Accessing ``.coordinates`` unconditionally
        # raised ``AttributeError`` on every net that used a via, which is
        # why this check has never produced a real result on a routed
        # board (see docs/evidence/2026-07-27-committed-route.md).
        path_coords = _extract_2d_coordinates(compiled_route.path)

        # ---- Filter duplicate consecutive points ---------------------------
        filtered: list[tuple[float, float]] = []
        for pt in path_coords:
            if not filtered or pt != filtered[-1]:
                filtered.append(pt)
        path_coords = filtered

        if len(path_coords) < 3:
            # Need at least 3 points to form an angle
            continue

        # ---- Build via-position set for this route -------------------------
        via_positions: set[tuple[float, float]] = set()
        if compiled_route.vias:
            for via in compiled_route.vias:
                via_positions.add(via.position)

        trace_width_mm = compiled_route.width_mm

        # ---- Interior vertices (indices 1 .. n-2) --------------------------
        for i in range(1, len(path_coords) - 1):
            curr_point = path_coords[i]

            # Skip via-transition vertices — those are layer changes,
            # not trace bends that could trap etchant.
            if curr_point in via_positions:
                continue

            prev_point = path_coords[i - 1]
            next_point = path_coords[i + 1]

            angle = _calculate_angle(prev_point, curr_point, next_point)

            # Guard against NaN (floating-point edge cases)
            if math.isnan(angle):
                continue

            if angle < min_angle_threshold:
                severity = _classify_severity(angle, trace_width_mm)

                acid_traps.append(
                    AcidTrap(
                        net_name=net_name,
                        position=curr_point,
                        angle_degrees=angle,
                        severity=severity,
                    )
                )

        # ---- Endpoint approach angles (if pin locations available) ----------
        # Check the angle where the first/last trace segment meets a pad.
        if hasattr(compiled_route, "start_pin_location") and hasattr(
            compiled_route, "end_pin_location"
        ):
            start_pin = compiled_route.start_pin_location  # type: ignore[attr-defined]
            end_pin = compiled_route.end_pin_location  # type: ignore[attr-defined]

            # Start approach: angle at path_coords[0] formed by
            #   (start_pin_location, path_coords[0], path_coords[1])
            angle_start = _calculate_angle(start_pin, path_coords[0], path_coords[1])
            if not math.isnan(angle_start) and angle_start < min_angle_threshold:
                severity = _classify_severity(angle_start, trace_width_mm)
                acid_traps.append(
                    AcidTrap(
                        net_name=net_name,
                        position=path_coords[0],
                        angle_degrees=angle_start,
                        severity=severity,
                    )
                )

            # End approach: angle at path_coords[-1] formed by
            #   (path_coords[-2], path_coords[-1], end_pin_location)
            angle_end = _calculate_angle(path_coords[-2], path_coords[-1], end_pin)
            if not math.isnan(angle_end) and angle_end < min_angle_threshold:
                severity = _classify_severity(angle_end, trace_width_mm)
                acid_traps.append(
                    AcidTrap(
                        net_name=net_name,
                        position=path_coords[-1],
                        angle_degrees=angle_end,
                        severity=severity,
                    )
                )

    return AcidTrapReport(acid_traps=acid_traps)


def _extract_2d_coordinates(path: object) -> list[tuple[float, float]]:
    """Return a path's vertex coordinates as plain ``(x, y)`` tuples.

    Handles both ``RoutePath`` (2D, has ``.coordinates``) and
    ``RoutePath3D`` (per-segment layer info, has ``.segments`` as
    ``(x, y, layer)`` triples and no ``.coordinates`` attribute).

    Raises:
        AttributeError: if ``path`` has neither attribute -- surfaced
            rather than silently swallowed, since a check that can't see
            its own input should fail loudly, not report a false zero.
    """
    coordinates = getattr(path, "coordinates", None)
    if coordinates is not None:
        return list(coordinates)

    segments = getattr(path, "segments", None)
    if segments is not None:
        return [(seg[0], seg[1]) for seg in segments]

    raise AttributeError(
        f"{type(path).__name__!r} has neither '.coordinates' nor '.segments' "
        "-- cannot extract path geometry for acid-trap detection."
    )


def _calculate_angle(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> float:
    """
    Calculate angle at p2 formed by p1-p2-p3.

    Args:
        p1: First point
        p2: Vertex point
        p3: Third point

    Returns:
        Angle in degrees (0-180)
    """
    return _drc.dfm_calculate_angle_py(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])


def _classify_severity(angle: float, trace_width_mm: float = 0.2) -> str:
    """
    Classify acid trap severity based on angle and trace width.

    Narrow traces (< 0.2 mm) are less likely to trap etchant, so their
    severity is demoted by one level.

    Args:
        angle: Angle in degrees
        trace_width_mm: Trace width in mm (default 0.2)

    Returns:
        Severity: "low", "medium", or "high"
    """
    return _drc.dfm_classify_severity_py(angle, trace_width_mm)
