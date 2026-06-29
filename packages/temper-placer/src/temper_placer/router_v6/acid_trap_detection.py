"""
Router V6 Stage 5.1: Detect and Fix Acid Traps

Detects acute angles in traces that can trap etchant during manufacturing.
Part of temper-vm3g (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

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
            "min_angle_threshold is NaN — no angles can be below NaN. "
            "Returning empty report.",
            stacklevel=2,
        )
        return AcidTrapReport(acid_traps=[])

    if not math.isfinite(min_angle_threshold) and min_angle_threshold < 0:
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
        # Analyze path for acute angles
        path_coords = compiled_route.path.coordinates

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

                acid_traps.append(AcidTrap(
                    net_name=net_name,
                    position=curr_point,
                    angle_degrees=angle,
                    severity=severity,
                ))

        # ---- Endpoint approach angles (if pin locations available) ----------
        # Check the angle where the first/last trace segment meets a pad.
        if (
            hasattr(compiled_route, 'start_pin_location')
            and hasattr(compiled_route, 'end_pin_location')
        ):
            start_pin = compiled_route.start_pin_location  # type: ignore[attr-defined]
            end_pin = compiled_route.end_pin_location      # type: ignore[attr-defined]

            # Start approach: angle at path_coords[0] formed by
            #   (start_pin_location, path_coords[0], path_coords[1])
            angle_start = _calculate_angle(start_pin, path_coords[0], path_coords[1])
            if not math.isnan(angle_start) and angle_start < min_angle_threshold:
                severity = _classify_severity(angle_start, trace_width_mm)
                acid_traps.append(AcidTrap(
                    net_name=net_name,
                    position=path_coords[0],
                    angle_degrees=angle_start,
                    severity=severity,
                ))

            # End approach: angle at path_coords[-1] formed by
            #   (path_coords[-2], path_coords[-1], end_pin_location)
            angle_end = _calculate_angle(path_coords[-2], path_coords[-1], end_pin)
            if not math.isnan(angle_end) and angle_end < min_angle_threshold:
                severity = _classify_severity(angle_end, trace_width_mm)
                acid_traps.append(AcidTrap(
                    net_name=net_name,
                    position=path_coords[-1],
                    angle_degrees=angle_end,
                    severity=severity,
                ))

    return AcidTrapReport(acid_traps=acid_traps)


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
    # Vectors from p2 to p1 and p3
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])

    # Calculate dot product and magnitudes
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
    mag2 = math.sqrt(v2[0]**2 + v2[1]**2)

    if mag1 == 0 or mag2 == 0:
        return 180.0  # Degenerate case

    # Calculate angle
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp to [-1, 1]

    angle_rad = math.acos(cos_angle)

    # Floating-point edge case: acos may still produce NaN
    if math.isnan(angle_rad):
        return 180.0

    angle_deg = math.degrees(angle_rad)

    # Round to eliminate floating-point noise (e.g. acos may return
    # 59.99999999999999° for a mathematically exact 60° angle, which
    # would shift the severity classification at the boundary).
    angle_deg = round(angle_deg, 9)

    return angle_deg


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
    if angle < 45:
        base = "high"      # Very acute - critical
    elif angle < 60:
        base = "medium"    # Moderate concern
    else:
        base = "low"       # Minor issue

    # Narrow traces are less susceptible to etchant trapping.
    # Non-finite / negative widths are physically meaningless — treat as
    # if no demotion applies (the angle-based classification stands).
    if not math.isfinite(trace_width_mm) or trace_width_mm < 0:
        return base

    if trace_width_mm < 0.2:
        if base == "high":
            return "medium"
        elif base == "medium":
            return "low"
        # "low" stays "low"

    return base
