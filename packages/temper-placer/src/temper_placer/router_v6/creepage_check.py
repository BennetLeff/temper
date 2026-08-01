"""
Router V6 Stage 5.6: Verify Creepage / Clearance

Validates clearance distances for high-voltage isolation.

.. note::

   This module currently measures **straight-line clearance**
   (air-gap distance) between conductor segments — not true
   surface creepage.  True creepage requires a pathfinding
   approach along the PCB surface that routes around isolation
   slots, board edges, and other obstacles.

   **Isolation slots are not modeled.**

The pure geometry (point/segment distance, segment intersection,
same-layer min-clearance aggregation, the IPC-2221 voltage table, and
the HV-net word-boundary classifier) lives in the ``temper-geometry``
Rust crate (``creepage_check.rs``); route extraction and the per-net
report orchestration stay here.

Part of temper-ytm8 (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import temper_geometry as _tg

from temper_placer.router_v6._check_report_base import BaseCheckReport
from temper_placer.router_v6.routing_results import RoutingResults

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CreepageViolation:
    """A clearance / creepage distance violation."""

    hv_net: str
    lv_net: str
    location: tuple[float, float]  # Closest approach point (midpoint)
    actual_distance: float  # Actual clearance distance (mm)
    required_distance: float  # Required minimum distance (mm)

    @property
    def deficiency(self) -> float:
        """How much the distance is under requirement."""
        return self.required_distance - self.actual_distance


@dataclass
class CreepageReport(BaseCheckReport):
    """Report of clearance / creepage distance violations."""

    violations: list[CreepageViolation]
    total_checks: int
    # True iff the check crashed, OR the anti-vacuous-truth guard fired
    # (total_checks == 0 on a board with routed copper -- METHODOLOGY.md
    # Sec 5). Creepage carries HV safety meaning, so ManufacturingReport
    # folds `errored` into critical_violations/total_violations as a
    # fail-closed sentinel rather than reading this as "0 violations
    # found". See
    # docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md.
    errored: bool = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def verify_creepage(
    routing_results: RoutingResults,
    voltage_ratings: dict[str, float] | None = None,
    default_creepage: float | None = None,
) -> CreepageReport:
    """
    Verify clearance distances for high-voltage isolation.

    .. warning::

       This measures **straight-line (air-gap) clearance**, not true
       surface creepage.  True creepage requires a pathfinding
       approach along the PCB surface.  Isolation slots are **not**
       modelled.

    Args:
        routing_results: Compiled routing results from Stage 4.9.
        voltage_ratings: Optional dict mapping net name to working
            voltage (V).  Defaults to 230 V for unrecognised nets.
        default_creepage: When set, overrides the voltage-table
            lookup and uses this single value (mm) as the required
            distance for **every** HV net.

    Returns:
        CreepageReport with all violations.

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = verify_creepage(results)
        >>> report.violation_count >= 0
        True
    """
    violations: list[CreepageViolation] = []
    total_checks = 0

    if voltage_ratings is None:
        voltage_ratings = {}

    if default_creepage is not None and (
        math.isnan(default_creepage) or not math.isfinite(default_creepage)
    ):
        raise ValueError(f"default_creepage must be a finite number, got {default_creepage!r}")

    # Identify every HV net
    hv_nets = [net for net in routing_results.compiled_routes if _is_high_voltage_net(net)]

    for hv_net in hv_nets:
        hv_route = routing_results.compiled_routes[hv_net]

        for other_net, other_route in routing_results.compiled_routes.items():
            if other_net == hv_net:
                continue

            total_checks += 1

            # ---- required distance -----------------------------------
            if default_creepage is not None:
                required_distance = default_creepage
            else:
                hv_voltage = voltage_ratings.get(hv_net, 230.0)
                required_distance = _calculate_required_creepage(hv_voltage)

            # ---- find *all* violating segment pairs ------------------
            pair_violations = _find_clearance_violations(
                hv_route,
                other_route,
                required_distance,
                hv_net,
                other_net,
            )
            violations.extend(pair_violations)

    return CreepageReport(violations=violations, total_checks=total_checks)


# ---------------------------------------------------------------------------
# HV net detection
# ---------------------------------------------------------------------------


def _is_high_voltage_net(net_name: str) -> bool:
    """
    Check whether *net_name* designates a high-voltage net.

    Matches a broad set of keywords commonly used in power-electronics
    schematics.  Every keyword is matched on word boundaries (delimited
    by ``_`` or start/end of the name) so that ``AC1``, ``HV_BUS``,
    ``_AC`` are recognised but ``TRACE`` is not.

    .. note:: **Bug history (2026-07-27).** Before this fix, only the
       ``AC``/``HV`` checks below were word-bounded; ``broad_keywords``
       used plain substring matching (``kw in name_upper``), which
       silently matched ``"L1"``/``"L2"`` inside ``"COIL1"``/``"COIL2"``
       (SELV relay-coil-drive nets, e.g. ``discharge.k_dis1-coil2``,
       ``power_in.bypass_relay-coil2``) and ``"LINE"`` inside
       ``"...-line"`` (internal safety-interlock fault signals, e.g.
       ``safety.ovp-line``, ``safety.uvlo_logic-line`` -- the latter is
       explicitly documented as SELV in ``elec/domain_manifest.yaml``,
       with a multi-paragraph justification). On the live production
       board this meant **14 of the 16** net names the check treated as
       ``hv_net`` were false positives, and **all 24** of one measured
       run's creepage violations involved one of those 14 -- zero
       involved a genuine HV/mains conductor. Real HV nets in this
       design happen to be delimited by ``_`` (``discharge.k_dis1-coil2``
       uses ``-``, not ``_``, before ``coil2``), so word-bounding on
       ``_`` -- the same discipline the AC/HV regex already used --
       removes every one of these collisions without narrowing intended
       matches (a net genuinely named e.g. ``PHASE_L1`` or ``BUS_L1``
       still matches; ``COIL1``/``...-LINE`` no longer do, because ``L1``/
       ``LINE`` are not preceded by ``_`` or string-start there). See
       ``docs/evidence/2026-07-27-creepage-burndown.md`` Sec 4 for the
       full derivation and the live before/after violation counts.

       This fix does **not** add coverage for the real HV nets the old
       heuristic also missed entirely (``+170V_BUS``, ``SW_NODE``,
       ``DC_BUS_RTN``, ``GATE_HS``/``GATE_LS``, ``w1_1``/``w1_2``,
       ``+15V_LS``, ``zcd``, ``a`` -- everything in
       ``elec/domain_manifest.yaml``'s HV domain except ``ac_l``/
       ``ac_n``). That is a separate, "Missing" (not "Wrong") gap in this
       heuristic's design -- a name-pattern classifier structurally
       cannot recognise nets whose *name* gives no voltage hint -- and is
       out of scope for this fix, which only removes proven false
       positives. Flagged as a ranked follow-up in the evidence doc:
       driving this check's HV-net set from ``elec/domain_manifest.yaml``
       (the same SSOT ``domain_clearance.py`` already reuses for the
       placement-side clearance check) would close it properly, at the
       cost of coupling this otherwise project-agnostic module to one
       project's manifest file -- a real design decision, not made here.

    Classified in the ``temper-geometry`` Rust crate
    (``creepage_check.rs``) with the exact word-boundary semantics and
    keyword order of the former regexes (pinned bit-exactly by
    ``tests/router_v6/test_creepage_check_rust_differential.py``,
    including the 14 known false positives).

    Args:
        net_name: Net name from the schematic / layout.

    Returns:
        ``True`` if the net is classified as high-voltage.
    """
    return _tg.is_high_voltage_net_py(net_name)


# ---------------------------------------------------------------------------
# Clearance-distance helpers
# ---------------------------------------------------------------------------


def _extract_segments(
    route,
) -> list[tuple[float, float, float, float, str]]:
    """
    Extract line segments with layer information from a compiled route.

    Handles both ``RoutePath`` (single-layer) and ``RoutePath3D``
    (per-segment layers).

    Segments that contain NaN or infinite coordinates are silently
    skipped so they cannot poison downstream distance calculations.

    Returns:
        List of ``(x1, y1, x2, y2, layer)`` tuples.
    """
    segments: list[tuple[float, float, float, float, str]] = []

    def _ok(*values: float) -> bool:
        """True when all values are finite (no NaN, no inf)."""
        return all(math.isfinite(v) for v in values)

    if hasattr(route.path, "segments"):
        # RoutePath3D  – (x, y, layer) triples
        pts = route.path.segments
        for i in range(len(pts) - 1):
            x1, y1, layer1 = pts[i]
            x2, y2, layer2 = pts[i + 1]
            if layer1 == layer2 and _ok(x1, y1, x2, y2):
                segments.append((x1, y1, x2, y2, layer1))
    else:
        # RoutePath – flat coordinates + single layer name
        coords = route.path.coordinates
        layer = route.path.layer_name
        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            if _ok(x1, y1, x2, y2):
                segments.append((x1, y1, x2, y2, layer))

    return segments


def _point_to_segment_distance(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Minimum distance from point *(px, py)* to segment *(x1,y1)-(x2,y2)*.

    Computed in the ``temper-geometry`` Rust crate (``creepage_check.rs``)
    with the exact f64 operation order of the former pure-Python body,
    including CPython ``math.hypot`` (Dekker vector_norm) and builtin
    ``min``/``max`` NaN semantics (pinned bit-exactly by
    ``tests/router_v6/test_creepage_check_rust_differential.py``).
    """
    return _tg.point_to_segment_distance_py(px, py, x1, y1, x2, y2)


def _closest_point_on_segment(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[float, float]:
    """Closest point on segment *(x1,y1)-(x2,y2)* to point *(px, py)*.

    Computed in the ``temper-geometry`` Rust crate (``creepage_check.rs``);
    bit-exact delegation, see ``_point_to_segment_distance``.
    """
    return _tg.closest_point_on_segment_py(px, py, x1, y1, x2, y2)


def _segments_intersect(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> tuple[bool, float, float]:
    """
    Check whether two line segments intersect (proper intersection).

    Returns:
        ``(intersects, ix, iy)`` where *(ix, iy)* is the intersection
        point when ``intersects`` is ``True``.

    Computed in the ``temper-geometry`` Rust crate (``creepage_check.rs``);
    bit-exact delegation (strict ``< 0.0`` orientation products, so
    shared endpoints and collinear overlaps do not count as proper
    intersections).
    """
    return _tg.segments_intersect_py(x1, y1, x2, y2, x3, y3, x4, y4)


def _segment_to_segment_info(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
) -> tuple[float, tuple[float, float], tuple[float, float]]:
    """
    Minimum distance between two line segments and the closest points.

    Returns:
        ``(distance, (cx1, cy1), (cx2, cy2))``.

    Computed in the ``temper-geometry`` Rust crate (``creepage_check.rs``)
    with the exact evaluation order of the former pure-Python body
    (intersection shortcut, then seg1 endpoints vs seg2, then seg2
    endpoints vs seg1, strict ``<`` so NaN distances never displace a
    finite best); bit-exact delegation.
    """
    dist, cx1, cy1, cx2, cy2 = _tg.segment_to_segment_info_py(x1, y1, x2, y2, x3, y3, x4, y4)
    return dist, (cx1, cy1), (cx2, cy2)


def _find_clearance_violations(
    route1,
    route2,
    required_distance: float,
    hv_net: str,
    lv_net: str,
) -> list[CreepageViolation]:
    """
    Find the worst-case (closest-approach) clearance violation, if any,
    between two routes.

    A routed net is typically decomposed internally into many short
    (~0.1 mm grid-step) segments. Two nets running parallel for any
    distance therefore have many segment-pairs that are all closer than
    ``required_distance`` -- but they represent a *single* isolation
    defect for this ``(hv_net, lv_net)`` pair, not one defect per
    segment-pair. Returning one ``CreepageViolation`` per segment-pair
    (the previous behaviour) produced counts in the hundreds of
    thousands that could not be interpreted as a count of real board
    defects (see docs/evidence/2026-07-27-drc-checks-repaired.md).

    This mirrors ``clearance_check._calculate_minimum_clearance_by_layer``,
    which already aggregates to one violation per (net-pair, layer) via
    the same reasoning -- the worst-case (minimum) approach distance is
    the number that determines pass/fail against a safety standard;
    every closer segment-pair along the same parallel run is evidence of
    the same defect, not a second one.

    Only segments residing on the **same layer** are compared.
    Cross-layer (via-to-via) creepage requires a separate pathfinding
    approach and is not computed here.

    Returns:
        A single-element list with the closest-approach
        ``CreepageViolation`` if the minimum same-layer distance between
        the two routes is under ``required_distance``, else an empty
        list. Never more than one element -- this keeps
        ``violation_count`` bounded by ``total_checks`` (one check per
        net pair), so the two numbers stay comparable.

    The same-layer min-aggregation loop is computed in the
    ``temper-geometry`` Rust crate (``creepage_check.rs``
    ``min_clearance_distance``) with the exact f64 operation order of
    the former pure-Python loop (strict ``<`` update, midpoint
    ``(p1 + p2) / 2.0``); bit-exact delegation.
    """
    best_dist, best_x, best_y = _tg.min_clearance_distance_py(
        _extract_segments(route1),
        _extract_segments(route2),
    )

    if best_dist < required_distance:
        return [
            CreepageViolation(
                hv_net=hv_net,
                lv_net=lv_net,
                location=(best_x, best_y),
                actual_distance=best_dist,
                required_distance=required_distance,
            )
        ]

    return []


# ---------------------------------------------------------------------------
# Voltage → required creepage table
# ---------------------------------------------------------------------------


def _calculate_required_creepage(voltage: float) -> float:
    """
    Required creepage distance per IPC-2221 (simplified).

    ===========  =====
    Voltage (V)  mm
    ===========  =====
      0 –  15    0.13
     16 –  30    0.25
     31 –  50    0.50
     51 – 100    0.80
    101 – 150    1.25
    151 – 170    1.60
    171 – 250    3.20
    251 – 300    6.40
    301 – 600    8.00
    601 –1000   12.00
    ===========  =====

    Args:
        voltage: Working voltage (V).

    Returns:
        Required creepage distance (mm).

    Raises:
        ValueError: If *voltage* is NaN or not finite.

    Computed in the ``temper-geometry`` Rust crate (``creepage_check.rs``)
    with the exact IPC-2221 bracket table of the reference; the NaN/inf
    ``ValueError`` (message included) is raised from Rust and surfaces
    unchanged.
    """
    return _tg.calculate_required_creepage_py(voltage)
