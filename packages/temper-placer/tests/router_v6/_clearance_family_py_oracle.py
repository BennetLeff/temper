"""Verbatim pre-migration oracle for the Phase E batch E3 clearance-family
orchestration (Rust Orchestration Engine plan 2026-08-09-001).

This file is a byte-exact snapshot of the ORCHESTRATION bodies of the five
clearance-family modules AS COMMITTED at the dispatch base (origin/main
cec171d7e), extracted verbatim:

- ``router_v6/clearance_engine.py`` — ``get_clearance`` (the five-standard
  candidates / max / internal-layer reduction orchestration)
- ``router_v6/creepage_check.py`` — ``verify_creepage`` + ``_find_clearance_violations``
  + ``_extract_segments`` (the HV-net pair-loop orchestration)
- ``router_v6/clearance_check.py`` — ``_verify_clearance_python`` + the
  reference-geometry helpers it drives (the pure-Python reference the
  Rust-backed production path is differential-tested against)
- ``placer/cp_sat/isolation_barrier.py`` — ``classify_domain_partition`` /
  ``evaluate_isolator_feasibility`` / ``_axis_gap`` / ``_best_rotation_for_barrier`` /
  ``_project_onto_barrier_axis`` / ``_pad_tuple`` (the barrier partition +
  isolator-feasibility orchestration)
- ``placer/cp_sat/domain_clearance.py`` — ``generate_domain_clearance_constraints`` /
  ``generate_unclassified_hv_keepaway_constraints`` /
  ``find_intra_footprint_domain_conflicts`` / ``audit_domain_clearance`` /
  ``required_margin_mm`` / ``MAX_IEC_MARGIN_MM`` / ``_HV_DOMAINS`` (the
  matrix-walk / dedup / keep-away / audit orchestration)

The leaf kernels these bodies call (``temper_geometry``, ``temper_drc_rs``,
``temper_constraints``, the ``VoltageClass`` pyclass) were already Rust and
are pinned by the existing differential suites; this oracle drives them
through the pre-migration PYTHON orchestration so the E3 differential can
compare the Rust orchestration against it field-by-field, bit-exactly.

Do NOT edit: it is the reference. The ``temper_placer`` imports at the top
resolve to the pinned pre-E3 modules (the pieces E3 did NOT migrate).

RE-PIN (2026-08-14, its own commit, separate from the behavioral fixes it
tracks): ``get_clearance``'s ``material_group`` discard (``vc.
get_creepage_mm()`` called with no argument, always the pyo3 bucket-2
default) and its internal-layer reduction's un-floored ``> 0.5`` cliff were
both confirmed defects in the pre-migration source itself, not merely
things the Rust port diverged from correctly. ``temper-orchestration/src/
clearance.rs::get_clearance_impl`` (commit 234ce918d, then a
non-monotonicity fix in this same re-pin's parent commit) and
``temper-drc-rs/src/router_clearance.rs::get_clearance`` were fixed first;
this oracle is re-pinned to match ONLY after exhaustively verifying (full
15,552-case sweep of ``get_clearance``'s public parameter space, plus 500
randomized ``verify_clearance`` route scenarios) that every resulting
divergence between the fixed Rust and the previously-frozen oracle body was
conservative-only (fixed >= frozen, never <) -- see
``test_oracle_body_matches_pinned_digest``'s docstring for why this is the
narrow, deliberate exception to "do not edit", and the commit message for
the full sweep evidence. The two changes are isolated to
``_oracle_material_group_bucket`` and the internal-layer-reduction line in
``get_clearance`` only; everything else in this file remains the original
byte-exact snapshot.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import temper_constraints as _tc
import temper_geometry as _tg

from temper_placer.core.net_types import VoltageClass
from temper_placer.core.pad_geometry import shape_code
from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.requirements.validators.clearance import (
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _components_in_domain,
    _domain_boundary_pairs,
    _nets_domain_map,
)
from temper_placer.router_v6.creepage_check import _calculate_required_creepage

# ---------------------------------------------------------------------------
# router_v6/clearance_engine.py — get_clearance (verbatim)
# ---------------------------------------------------------------------------

# IEC 60664-1 legacy constant (was in routing/constraints/drc_oracle.py)
INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30

_VC_FROM_VALUE = {
    VoltageClass.SELV.value: VoltageClass.SELV,
    VoltageClass.LOW_VOLTAGE.value: VoltageClass.LOW_VOLTAGE,
    VoltageClass.MAINS_120V.value: VoltageClass.MAINS_120V,
    VoltageClass.MAINS_240V.value: VoltageClass.MAINS_240V,
    VoltageClass.HIGH_VOLTAGE.value: VoltageClass.HIGH_VOLTAGE,
}


def _oracle_material_group_bucket(material_group: str) -> int:
    """Deliberate re-pin (2026-08-14): the pre-migration body this oracle
    pinned discarded `material_group` entirely (`vc.get_creepage_mm()` was
    always called with no argument, i.e. pyo3's bucket-2 "typical FR4"
    default). That discard is a confirmed defect, not a real reference
    behavior -- see `temper-orchestration/src/clearance.rs`'s
    `get_clearance_impl` fix (commit 234ce918d) and its own `MaterialGroup`
    doc comment for the full citation (`docs/specs/HIGH_VOLTAGE_CLEARANCE_
    SPEC.md` REQ-ELEC-04 Section 3.2: this board's declared Material Group
    is IIIb). This oracle is re-pinned to the corrected behavior rather than
    continuing to bless the discard, per this suite's own docstring: "a
    pre-migration module's source really changed upstream -- re-pin
    deliberately, in its own commit." Mirrors `MaterialGroup::parse` /
    `creepage_bucket` in `clearance.rs` exactly, including the hard error on
    an unrecognized label (no call site in this repo ever passes anything
    but the "IIIa" default, but the live code no longer accepts a silent
    fallback and the oracle should not either).
    """
    bucket = {"I": 1, "II": 2, "IIIa": 3, "IIIb": 3}.get(material_group.strip())
    if bucket is None:
        raise ValueError(
            f"unknown material_group {material_group!r}; expected one of "
            '"I", "II", "IIIa", "IIIb" (IEC 60335-1 cl. 29.2 CTI bands)'
        )
    return bucket


def get_clearance(
    net_class_a: str,
    net_class_b: str,
    voltage: float,
    layer_type: str = "external",
    pollution_degree: int = 2,
    material_group: str = "IIIa",
    overvoltage_category: int = 2,
    *,
    design_rule_creepage: float | None = None,
) -> float:
    """Return the most-conservative clearance (mm) across all applicable standards."""
    material_group_bucket = _oracle_material_group_bucket(material_group)
    candidates: list[float] = []

    # ---- IEC 60950-1 ---------------------------------------------------
    try:
        clearance_mm, creepage_mm, _voltage_v = _tg.safety_distances_py(
            voltage, pollution_degree, overvoltage_category
        )
        candidates.append(clearance_mm)
        candidates.append(creepage_mm)
    except Exception:
        pass  # Degrade gracefully if the table somehow fails

    # ---- IEC 60335-1 (VoltageClass tables) ----------------------------
    try:
        vc_a = _VC_FROM_VALUE[_tg.net_class_to_voltage_class_py(net_class_a)]
        vc_b = _VC_FROM_VALUE[_tg.net_class_to_voltage_class_py(net_class_b)]
        # Use the more demanding of the two net classes
        for vc in (vc_a, vc_b):
            candidates.append(vc.get_clearance_mm(pollution_degree))
            # Re-pin (2026-08-14): was `vc.get_creepage_mm()` (bucket-2
            # discard) -- see `_oracle_material_group_bucket`'s docstring.
            candidates.append(vc.get_creepage_mm(material_group_bucket))
    except Exception:
        pass

    # ---- IPC-2221 (generic PCB creepage table) ------------------------
    try:
        ipc = _calculate_required_creepage(voltage)
        candidates.append(ipc)
    except Exception:
        pass

    # ---- IEC 62368-1 (design-rule creepage from NetClassRules) --------
    if design_rule_creepage is not None and design_rule_creepage > 0.0:
        candidates.append(design_rule_creepage)

    # ---- Compute base conservative value -------------------------------
    if not candidates:
        # All standards failed — return a safe default
        return 0.5

    result = max(candidates)

    # ---- IEC 60664-1 internal-layer reduction -------------------------
    # Re-pin (2026-08-14): floored at `.max(0.5)` -- see
    # `temper-orchestration/src/clearance.rs::get_clearance_impl`'s inline
    # writeup for the full non-monotonicity diagnosis (a `> 0.5` reduction
    # gate with no floor lets a larger `result` produce a smaller output
    # once it crosses the boundary; exhaustively confirmed as the ONLY
    # divergence direction fixed by this floor, over the full 15,552-case
    # parameter space of this function). Not a threshold change -- `0.30`
    # and `0.5` both keep their pre-existing values.
    if layer_type == "internal" and result > 0.5:
        result = max(result * INTERNAL_LAYER_CREEPAGE_FACTOR, 0.5)

    return result


# ---------------------------------------------------------------------------
# router_v6/creepage_check.py — verify_creepage + helpers (verbatim)
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
class CreepageReport:
    """Report of clearance / creepage distance violations."""

    violations: list[CreepageViolation]
    total_checks: int
    errored: bool = False


def _oracle_extract_segments(route) -> list[tuple[float, float, float, float, str]]:
    segments: list[tuple[float, float, float, float, str]] = []

    def _ok(x1: float, y1: float, x2: float, y2: float) -> bool:
        return (
            math.isfinite(x1)
            and math.isfinite(y1)
            and math.isfinite(x2)
            and math.isfinite(y2)
        )

    if hasattr(route.path, "segments"):
        pts = route.path.segments
        for i in range(len(pts) - 1):
            x1, y1, layer1 = pts[i]
            x2, y2, layer2 = pts[i + 1]
            if layer1 == layer2 and _ok(x1, y1, x2, y2):
                segments.append((x1, y1, x2, y2, layer1))
    else:
        coords = route.path.coordinates
        layer = route.path.layer_name
        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            if _ok(x1, y1, x2, y2):
                segments.append((x1, y1, x2, y2, layer))

    return segments


def _oracle_find_clearance_violations(
    route1,
    route2,
    required_distance: float,
    hv_net: str,
    lv_net: str,
) -> list[CreepageViolation]:
    best_dist, best_x, best_y = _tg.min_clearance_distance_py(
        _oracle_extract_segments(route1),
        _oracle_extract_segments(route2),
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


def verify_creepage(
    routing_results,
    voltage_ratings: dict[str, float] | None = None,
    default_creepage: float | None = None,
) -> CreepageReport:
    """Verify clearance distances for high-voltage isolation."""
    violations: list[CreepageViolation] = []
    total_checks = 0

    if voltage_ratings is None:
        voltage_ratings = {}

    if default_creepage is not None and (
        math.isnan(default_creepage) or not math.isfinite(default_creepage)
    ):
        raise ValueError(f"default_creepage must be a finite number, got {default_creepage!r}")

    # Identify every HV net
    hv_nets = [
        net for net in routing_results.compiled_routes if _tg.is_high_voltage_net_py(net)
    ]

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
            pair_violations = _oracle_find_clearance_violations(
                hv_route,
                other_route,
                required_distance,
                hv_net,
                other_net,
            )
            violations.extend(pair_violations)

    return CreepageReport(violations=violations, total_checks=total_checks)


# ---------------------------------------------------------------------------
# router_v6/clearance_check.py — the pure-Python reference (verbatim)
# ---------------------------------------------------------------------------


@dataclass
class ClearanceViolation:
    """A clearance distance violation."""

    net1: str
    net2: str
    location: tuple[float, float]  # Violation location
    actual_clearance: float  # Actual spacing (mm); negative = overlap
    required_clearance: float  # Required minimum (mm)
    layer: str  # Layer where violation occurs

    @property
    def deficiency(self) -> float:
        """How much the clearance is under requirement."""
        return self.required_clearance - self.actual_clearance


@dataclass
class ClearanceReport:
    """Report of clearance violations."""

    violations: list[ClearanceViolation]
    total_checks: int
    errored: bool = False


def _oracle_all_routes(routing_results):
    routes: list[tuple[str, object]] = list(routing_results.compiled_routes.items())
    routes += list((getattr(routing_results, "tree_routes", None) or {}).items())
    routes += list((getattr(routing_results, "partial_tree_routes", None) or {}).items())
    return routes


def _oracle_extract_segments(route) -> list[tuple[float, float, float, float, str]]:
    segs = []
    geometry = getattr(route, "geometry", None)
    if geometry is not None and hasattr(geometry, "iter_segments"):
        for (x1, y1, l1), (x2, y2, l2) in geometry.iter_segments():
            if l1 == l2 and all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                segs.append((x1, y1, x2, y2, l1))
        return segs
    path = route.path
    if hasattr(path, "segments"):  # RoutePath3D
        for i in range(len(path.segments) - 1):
            p1, p2 = path.segments[i], path.segments[i + 1]
            if p1[2] == p2[2]:  # Same layer segment
                x1, y1, x2, y2 = p1[0], p1[1], p2[0], p2[1]
                if all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                    segs.append((x1, y1, x2, y2, p1[2]))
    elif hasattr(path, "coordinates"):  # RoutePath
        layer = getattr(path, "layer_name", "F.Cu")
        for i in range(len(path.coordinates) - 1):
            p1, p2 = path.coordinates[i], path.coordinates[i + 1]
            x1, y1, x2, y2 = p1[0], p1[1], p2[0], p2[1]
            if all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                segs.append((x1, y1, x2, y2, layer))
    return segs


def _oracle_extract_via_points(route) -> list[tuple[float, float, str, str]]:
    points = []
    geometry = getattr(route, "geometry", None)
    if geometry is not None and hasattr(geometry, "iter_segments"):
        for (x1, y1, l1), (_x2, _y2, l2) in geometry.iter_segments():
            if l1 != l2:
                points.append((x1, y1, l1, l2))
        return points
    path = route.path
    if hasattr(path, "segments"):
        for i in range(len(path.segments) - 1):
            p1, p2 = path.segments[i], path.segments[i + 1]
            if p1[2] != p2[2]:  # Layer change = via
                points.append((p1[0], p1[1], p1[2], p2[2]))
    return points


def _oracle_point_to_segment_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    ap = (p[0] - a[0], p[1] - a[1])
    len2 = ab[0] * ab[0] + ab[1] * ab[1]

    if len2 < 1e-12 or not math.isfinite(len2):
        dx = p[0] - a[0]
        dy = p[1] - a[1]
        return (dx * dx + dy * dy) ** 0.5, a, p

    t = (ap[0] * ab[0] + ap[1] * ab[1]) / len2
    t = max(0.0, min(1.0, t))
    cp = (a[0] + t * ab[0], a[1] + t * ab[1])
    dx = p[0] - cp[0]
    dy = p[1] - cp[1]
    return (dx * dx + dy * dy) ** 0.5, cp, p


def _oracle_segment_to_segment_dist(a, b, c, d):
    ab = (b[0] - a[0], b[1] - a[1])
    cd = (d[0] - c[0], d[1] - c[1])
    ac = (c[0] - a[0], c[1] - a[1])

    a_len2 = ab[0] * ab[0] + ab[1] * ab[1]
    c_len2 = cd[0] * cd[0] + cd[1] * cd[1]
    eps = 1e-12

    if a_len2 < eps and c_len2 < eps:
        dx = ac[0]
        dy = ac[1]
        return (dx * dx + dy * dy) ** 0.5, a, c

    if a_len2 < eps:
        d_pt, cp, _ = _oracle_point_to_segment_dist(a, c, d)
        return d_pt, a, cp

    if c_len2 < eps:
        d_pt, cp, _ = _oracle_point_to_segment_dist(c, a, b)
        return d_pt, cp, c

    ab_dot_cd = ab[0] * cd[0] + ab[1] * cd[1]
    ac_dot_ab = ac[0] * ab[0] + ac[1] * ab[1]
    ac_dot_cd = ac[0] * cd[0] + ac[1] * cd[1]

    det = a_len2 * c_len2 - ab_dot_cd * ab_dot_cd

    if det > eps:
        s = (ac_dot_ab * c_len2 + ab_dot_cd * (-ac_dot_cd)) / det
        t = (a_len2 * (-ac_dot_cd) + ab_dot_cd * ac_dot_ab) / det

        if 0.0 <= s <= 1.0 and 0.0 <= t <= 1.0:
            cp1 = (a[0] + s * ab[0], a[1] + s * ab[1])
            cp2 = (c[0] + t * cd[0], c[1] + t * cd[1])
            dx = cp1[0] - cp2[0]
            dy = cp1[1] - cp2[1]
            return (dx * dx + dy * dy) ** 0.5, cp1, cp2

    best_dist = float("inf")
    best_cp1 = a
    best_cp2 = c

    def _update(dist, p1, p2):
        nonlocal best_dist, best_cp1, best_cp2
        if dist < best_dist:
            best_dist = dist
            best_cp1 = p1
            best_cp2 = p2

    d0, cp, _ = _oracle_point_to_segment_dist(a, c, d)
    _update(d0, a, cp)

    d1, cp, _ = _oracle_point_to_segment_dist(b, c, d)
    _update(d1, b, cp)

    d2, cp, _ = _oracle_point_to_segment_dist(c, a, b)
    _update(d2, cp, c)

    d3, cp, _ = _oracle_point_to_segment_dist(d, a, b)
    _update(d3, cp, d)

    return best_dist, best_cp1, best_cp2


def _oracle_calculate_minimum_clearance_by_layer(route1, route2):
    layer_info: dict[str, tuple[float, tuple[float, float]]] = {}

    width1 = getattr(route1, "width_mm", 0.0)
    width2 = getattr(route2, "width_mm", 0.0)
    if not math.isfinite(width1):
        width1 = 0.0
    if not math.isfinite(width2):
        width2 = 0.0

    via_diameter_default = max(width1, 0.6)

    def _update_layer(layer: str, edge_dist: float, point: tuple[float, float]):
        if layer not in layer_info or edge_dist < layer_info[layer][0]:
            layer_info[layer] = (edge_dist, point)

    segs1 = _oracle_extract_segments(route1)
    segs2 = _oracle_extract_segments(route2)

    for s1 in segs1:
        for s2 in segs2:
            if s1[4] != s2[4]:
                continue

            seg_dist, cp1, cp2 = _oracle_segment_to_segment_dist(
                (s1[0], s1[1]),
                (s1[2], s1[3]),
                (s2[0], s2[1]),
                (s2[2], s2[3]),
            )

            edge_dist = seg_dist - (width1 / 2) - (width2 / 2)
            point = (
                (cp1[0] + cp2[0]) / 2,
                (cp1[1] + cp2[1]) / 2,
            )
            _update_layer(s1[4], edge_dist, point)

    def _check_via_against_segs(via, other_segs, other_width):
        via_x, via_y = via.position
        via_radius = via.diameter / 2.0
        via_layers = {via.from_layer, via.to_layer}

        for seg in other_segs:
            if seg[4] not in via_layers:
                continue
            pt_dist, _cp_on_seg, _ = _oracle_point_to_segment_dist(
                (via_x, via_y),
                (seg[0], seg[1]),
                (seg[2], seg[3]),
            )
            edge_dist = pt_dist - via_radius - (other_width / 2)
            _update_layer(seg[4], edge_dist, (via_x, via_y))

    for via in getattr(route1, "vias", []):
        _check_via_against_segs(via, segs2, width2)

    for via in getattr(route2, "vias", []):
        _check_via_against_segs(via, segs1, width1)

    def _check_via_point_against_segs(vx, vy, via_diam, layers, other_segs, other_width):
        via_radius = via_diam / 2.0
        for seg in other_segs:
            if seg[4] not in layers:
                continue
            pt_dist, _cp_on_seg, _ = _oracle_point_to_segment_dist(
                (vx, vy),
                (seg[0], seg[1]),
                (seg[2], seg[3]),
            )
            edge_dist = pt_dist - via_radius - (other_width / 2)
            _update_layer(seg[4], edge_dist, (vx, vy))

    for vx, vy, l1, l2 in _oracle_extract_via_points(route1):
        _check_via_point_against_segs(vx, vy, via_diameter_default, {l1, l2}, segs2, width2)

    for vx, vy, l1, l2 in _oracle_extract_via_points(route2):
        _check_via_point_against_segs(vx, vy, via_diameter_default, {l1, l2}, segs1, width1)

    return layer_info


_CLASSIFY_HV_KEYWORDS = (
    "AC",
    "HV",
    "HIGH_VOLTAGE",
    "MAINS",
    "LINE",
    "NEUTRAL",
    "PRIMARY",
    "HOT",
    "L1",
    "L2",
    "L3",
    "PHASE",
    "VBUS",
)


def _oracle_is_hv_keyword_match(upper: str) -> bool:
    for kw in _CLASSIFY_HV_KEYWORDS:
        if re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper):
            return True
    return bool(re.search(r"(?:^|_)B\+", upper))


@functools.lru_cache(maxsize=1)
def _oracle_load_manifest_hv_net_names() -> frozenset[str]:
    try:
        import yaml
    except ImportError:
        return frozenset()

    manifest_path = None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "elec" / "domain_manifest.yaml"
        if candidate.is_file():
            manifest_path = candidate
            break
    if manifest_path is None:
        return frozenset()

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()

    if not isinstance(data, dict):
        return frozenset()
    domains = data.get("domains")
    if not isinstance(domains, dict):
        return frozenset()
    hv_domain = domains.get("HV")
    if not isinstance(hv_domain, dict):
        return frozenset()
    nets = hv_domain.get("nets")
    if not isinstance(nets, list):
        return frozenset()
    return frozenset(str(n) for n in nets)


def _oracle_is_internal_layer(layer_name: str) -> bool:
    """Return True if *layer_name* designates an internal copper layer."""
    return layer_name.startswith("In") or "In" in layer_name


def _oracle_classify_net_class(net_name: str) -> str:
    if net_name in _oracle_load_manifest_hv_net_names():
        return "HV"
    upper = net_name.upper()
    if _oracle_is_hv_keyword_match(upper):
        return "HV"
    if any(
        re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper)
        for kw in ("GND", "VSS", "PGND", "CGND", "AGND")
    ):
        return "GND"
    if any(
        re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper) for kw in ("VCC", "VDD", "POWER")
    ) or re.search(r"^\+(?:3V3|5V|12V|15V)(?:$|_)", upper):
        return "POWER"
    return "SIGNAL"


def _oracle_get_required_clearance(
    net1: str,
    net2: str,
    default_clearance: float,
    voltage_ratings: dict[str, float] | None = None,
    *,
    layer: str = "F.Cu",
) -> float:
    if voltage_ratings is None:
        voltage_ratings = {}

    hv_manifest_nets = _oracle_load_manifest_hv_net_names()

    net1_upper = net1.upper()
    net2_upper = net2.upper()

    is_hv1 = _oracle_is_hv_keyword_match(net1_upper) or net1 in hv_manifest_nets
    is_hv2 = _oracle_is_hv_keyword_match(net2_upper) or net2 in hv_manifest_nets

    if is_hv1 or is_hv2:
        voltage = 0.0
        if is_hv1:
            v1 = voltage_ratings.get(net1, 230.0)
            voltage = max(voltage, v1) if math.isfinite(v1) else max(voltage, 230.0)
        if is_hv2:
            v2 = voltage_ratings.get(net2, 230.0)
            voltage = max(voltage, v2) if math.isfinite(v2) else max(voltage, 230.0)

        class_a = _oracle_classify_net_class(net1)
        class_b = _oracle_classify_net_class(net2)

        layer_type = "internal" if _oracle_is_internal_layer(layer) else "external"

        hv_required = get_clearance(
            class_a,
            class_b,
            voltage=voltage,
            layer_type=layer_type,
        )
        return max(default_clearance, hv_required)

    return default_clearance


def _verify_clearance_python(
    routing_results,
    min_clearance: float = 0.127,
    voltage_ratings: dict[str, float] | None = None,
) -> ClearanceReport:
    """Pure-Python reference implementation of :func:`verify_clearance`."""
    violations = []
    total_checks = 0

    if voltage_ratings is None:
        voltage_ratings = {}

    if math.isnan(min_clearance) or not math.isfinite(min_clearance):
        raise ValueError(f"min_clearance must be a finite number, got {min_clearance!r}")

    routes = _oracle_all_routes(routing_results)

    for i in range(len(routes)):
        net1, route1 = routes[i]

        for j in range(i + 1, len(routes)):
            net2, route2 = routes[j]

            if net1 == net2:
                continue

            total_checks += 1

            per_layer = _oracle_calculate_minimum_clearance_by_layer(
                route1,
                route2,
            )

            for layer, (min_dist, location) in per_layer.items():
                required = _oracle_get_required_clearance(
                    net1,
                    net2,
                    min_clearance,
                    voltage_ratings,
                    layer=layer,
                )

                if min_dist < required:
                    violations.append(
                        ClearanceViolation(
                            net1=net1,
                            net2=net2,
                            location=location,
                            actual_clearance=min_dist,
                            required_clearance=required,
                            layer=layer,
                        )
                    )

    return ClearanceReport(
        violations=violations,
        total_checks=total_checks,
    )


# ---------------------------------------------------------------------------
# placer/cp_sat/isolation_barrier.py — partition + feasibility (verbatim)
# ---------------------------------------------------------------------------


@dataclass
class DomainPartition:
    """Every board component classified into exactly one bucket."""

    hv_only: list[str] = field(default_factory=list)
    selv_only: list[str] = field(default_factory=list)
    isolators: list[str] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.hv_only) + len(self.selv_only) + len(self.isolators) + len(self.unclassified)


def classify_domain_partition(
    components,
    hv_nets: frozenset[str],
    selv_nets: frozenset[str],
) -> DomainPartition:
    """Classify every component by which domain(s) its pins touch."""
    partition = DomainPartition()
    for comp in components:
        touches_hv = any(p.net in hv_nets for p in comp.pins)
        touches_selv = any(p.net in selv_nets for p in comp.pins)
        if touches_hv and touches_selv:
            partition.isolators.append(comp.ref)
        elif touches_hv:
            partition.hv_only.append(comp.ref)
        elif touches_selv:
            partition.selv_only.append(comp.ref)
        else:
            partition.unclassified.append(comp.ref)
    return partition


@dataclass(frozen=True)
class Pad:
    """A pad's position and its exact declared shape."""

    x: float
    y: float
    width: float
    height: float
    shape: str = "circle"
    roundrect_ratio: float = 0.25

    def axis_radius(self, axis: int, rotation_rad: float = 0.0) -> float:
        from temper_placer.core.pad_geometry import pad_axis_radius

        return pad_axis_radius(self.width, self.height, self.shape, axis, rotation_rad, self.roundrect_ratio)


def _pad_tuple(p: Pad) -> tuple[float, float, float, float, int, float]:
    return (p.x, p.y, p.width, p.height, shape_code(p.shape), p.roundrect_ratio)


def _axis_gap(hv_pads: list[Pad], selv_pads: list[Pad], axis_idx: int) -> float:
    return _tg.barrier_axis_gap_py(
        [_pad_tuple(p) for p in hv_pads], [_pad_tuple(p) for p in selv_pads], axis_idx
    )


def _best_rotation_for_barrier(
    hv_pads: list[Pad],
    selv_pads: list[Pad],
    barrier_axis: int,
) -> tuple[int, float, bool]:
    return _tg.best_rotation_for_barrier_py(
        [_pad_tuple(p) for p in hv_pads], [_pad_tuple(p) for p in selv_pads], barrier_axis
    )


def _project_onto_barrier_axis(local_x: float, local_y: float, rot_value: int, barrier_axis: int) -> float:
    """Global coordinate (along *barrier_axis*, 0=X/1=Y) a local pad offset
    maps to under one of the model's 4 axis-aligned rotations."""
    gx, gy = {
        0: (local_x, local_y),
        1: (local_y, -local_x),
        2: (-local_x, -local_y),
        3: (-local_y, local_x),
    }[rot_value]
    return gx if barrier_axis == 0 else gy


@dataclass
class IsolatorFeasibility:
    ref: str
    gap_x_mm: float
    gap_y_mm: float
    corridor_width_mm: float
    barrier_axis: int
    achievable_gap_mm: float
    chosen_rotation: int
    feasible_axis: int | None
    hv_is_lo: bool

    @property
    def feasible(self) -> bool:
        return self.achievable_gap_mm >= self.corridor_width_mm


def evaluate_isolator_feasibility(
    pad_groups,
    corridor_width_mm: float,
    barrier_axis: int = 0,
) -> IsolatorFeasibility:
    """Can this isolator's HV/SELV pad clusters straddle a corridor this wide?"""
    if not pad_groups.hv_pads or not pad_groups.selv_pads:
        raise ValueError(
            f"{pad_groups.ref}: not a real isolator -- missing an HV or SELV pad "
            "(caller should not have classified this as an isolator)"
        )
    gap_x = _axis_gap(pad_groups.hv_pads, pad_groups.selv_pads, 0)
    gap_y = _axis_gap(pad_groups.hv_pads, pad_groups.selv_pads, 1)

    rot_value, achievable_gap, hv_is_lo = _best_rotation_for_barrier(
        pad_groups.hv_pads, pad_groups.selv_pads, barrier_axis
    )
    feasible_axis = 0 if rot_value in (0, 2) else 1

    return IsolatorFeasibility(
        ref=pad_groups.ref,
        gap_x_mm=gap_x,
        gap_y_mm=gap_y,
        corridor_width_mm=corridor_width_mm,
        barrier_axis=barrier_axis,
        achievable_gap_mm=achievable_gap,
        chosen_rotation=rot_value,
        feasible_axis=feasible_axis if achievable_gap >= corridor_width_mm else None,
        hv_is_lo=hv_is_lo,
    )


# ---------------------------------------------------------------------------
# placer/cp_sat/domain_clearance.py — constraint generation + audit (verbatim)
# ---------------------------------------------------------------------------


def _oracle_required_margin_mm(requirements: dict[str, float]) -> float:
    return _tc.required_margin_mm_py(
        requirements["min_clearance_mm"], requirements["min_creepage_mm"]
    )


MAX_IEC_MARGIN_MM = max(
    max(row["min_clearance_mm"], row["min_creepage_mm"])
    for row in IEC60335_REQUIREMENTS.values()
)

_HV_DOMAINS = {VoltageDomain.MAINS, VoltageDomain.DC_BUS, VoltageDomain.BOOTSTRAP}


def generate_domain_clearance_constraints(
    placement: dict,
    voltage_domains: dict,
    component_refs: set[str] | None = None,
) -> list[SeparatedConstraint]:
    """Generate one HARD SeparatedConstraint per domain-crossing component pair."""
    nets_domain = _nets_domain_map(placement, voltage_domains)

    pair_margin: dict[tuple[str, str], float] = {}
    pair_reasons: dict[tuple[str, str], list[str]] = {}

    for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items():
        margin = _oracle_required_margin_mm(requirements)
        for comp_a, comp_b in _domain_boundary_pairs(placement, domain_a, domain_b, nets_domain):
            ra, rb = comp_a.get("ref"), comp_b.get("ref")
            if not isinstance(ra, str) or not isinstance(rb, str):
                continue
            if component_refs is not None and (ra not in component_refs or rb not in component_refs):
                continue
            key = (ra, rb) if ra <= rb else (rb, ra)
            if margin > pair_margin.get(key, 0.0):
                pair_margin[key] = margin
            reason = (
                f"IEC 60335-2-6 {domain_a.value}<->{domain_b.value} "
                f"({insulation_type.value}): {margin}mm "
                f"(max of clearance={requirements['min_clearance_mm']}mm, "
                f"creepage={requirements['min_creepage_mm']}mm)"
            )
            reasons = pair_reasons.setdefault(key, [])
            if reason not in reasons:
                reasons.append(reason)

    constraints: list[SeparatedConstraint] = []
    for (ra, rb), margin in sorted(pair_margin.items()):
        constraints.append(
            SeparatedConstraint(
                a=ra,
                b=rb,
                min_distance_mm=margin,
                tier=ConstraintTier.HARD,
                because="; ".join(pair_reasons[(ra, rb)]),
                id=f"domain_clearance_{ra}_{rb}",
            )
        )

    return constraints


def generate_unclassified_hv_keepaway_constraints(
    placement: dict,
    voltage_domains: dict,
    component_refs: set[str],
    exempt_pairs: set[frozenset[str]] | None = None,
    hv_domains: set[VoltageDomain] | None = None,
    margin_mm: float | None = None,
) -> list[SeparatedConstraint]:
    """One HARD SeparatedConstraint per (unclassified ref, HV ref) pair."""
    exempt: set[frozenset[str]] = exempt_pairs if exempt_pairs is not None else set()
    domains: set[VoltageDomain] = hv_domains if hv_domains is not None else _HV_DOMAINS
    margin = margin_mm if margin_mm is not None else MAX_IEC_MARGIN_MM

    nets_domain = _nets_domain_map(placement, voltage_domains)
    classified_refs: set[str] = set()
    hv_refs: set[str] = set()
    for comp in placement.get("components", []):
        ref = comp.get("ref")
        if not isinstance(ref, str):
            continue
        classified_refs.add(ref)
        if any(nets_domain.get(net) in domains for net in comp.get("nets", [])):
            hv_refs.add(ref)

    unclassified_refs = sorted(component_refs - classified_refs)
    constraints: list[SeparatedConstraint] = []
    for u_ref in unclassified_refs:
        for h_ref in sorted(hv_refs):
            if u_ref == h_ref:
                continue
            if frozenset({u_ref, h_ref}) in exempt:
                continue
            constraints.append(
                SeparatedConstraint(
                    a=u_ref,
                    b=h_ref,
                    min_distance_mm=margin,
                    tier=ConstraintTier.HARD,
                    because=(
                        f"unclassified {u_ref} must stay {margin}mm (largest IEC "
                        f"margin) from HV-classified {h_ref}: no classified net "
                        f"gives the domain-clearance generator a handle on it, "
                        f"so this keep-away is the only hard guarantee that a "
                        f"repair solve does not regress the fail-closed "
                        f"unclassified-near-HV proximity check"
                    ),
                    id=f"keepaway_unclassified_{u_ref}_{h_ref}",
                )
            )
    return constraints


@dataclass
class IntraFootprintDomainConflict:
    """One component whose OWN pads straddle a matrix-covered domain boundary."""

    ref: str
    domain_a: VoltageDomain
    domain_b: VoltageDomain
    margin_mm: float
    reason: str


def find_intra_footprint_domain_conflicts(
    placement: dict,
    voltage_domains: dict,
    component_refs: set[str] | None = None,
) -> list[IntraFootprintDomainConflict]:
    """Enumerate components that the generator structurally cannot protect."""
    nets_domain = _nets_domain_map(placement, voltage_domains)
    worst: dict[str, IntraFootprintDomainConflict] = {}

    for (domain_a, domain_b, insulation_type), requirements in IEC60335_REQUIREMENTS.items():
        if domain_a == domain_b:
            continue
        margin = _oracle_required_margin_mm(requirements)
        group_a = _components_in_domain(placement, domain_a, nets_domain)
        group_b_refs = {
            c.get("ref") for c in _components_in_domain(placement, domain_b, nets_domain)
        }
        for comp in group_a:
            ref = comp.get("ref")
            if not isinstance(ref, str) or ref not in group_b_refs:
                continue
            if component_refs is not None and ref not in component_refs:
                continue
            prior = worst.get(ref)
            if prior is None or margin > prior.margin_mm:
                worst[ref] = IntraFootprintDomainConflict(
                    ref=ref,
                    domain_a=domain_a,
                    domain_b=domain_b,
                    margin_mm=margin,
                    reason=(
                        f"{ref} carries a net classified {domain_a.value} and a net "
                        f"classified {domain_b.value} on the same footprint -- "
                        f"IEC 60335-2-6 {domain_a.value}<->{domain_b.value} "
                        f"({insulation_type.value}) requires {margin}mm, which no "
                        f"placement can supply between two pads of one rigid part."
                    ),
                )

    return sorted(worst.values(), key=lambda c: c.ref)


@dataclass
class DomainClearanceAuditViolation:
    """A post-solve mismatch between the encoded bound and the real distance."""

    ref_a: str
    ref_b: str
    required_mm: float
    actual_mm: float
    reason: str


def audit_domain_clearance(
    constraints: list[SeparatedConstraint],
    resolved_positions_mm: dict[str, tuple[float, float]],
) -> list[DomainClearanceAuditViolation]:
    """Recompute real Euclidean center distance for every generated constraint."""
    violations: list[DomainClearanceAuditViolation] = []
    for c in constraints:
        if not c.id.startswith("domain_clearance_"):
            continue
        pos_a = resolved_positions_mm.get(c.a)
        pos_b = resolved_positions_mm.get(c.b)
        if pos_a is None or pos_b is None:
            violations.append(
                DomainClearanceAuditViolation(
                    ref_a=c.a,
                    ref_b=c.b,
                    required_mm=c.min_distance_mm,
                    actual_mm=float("nan"),
                    reason=f"missing resolved position for {c.a if pos_a is None else c.b}",
                )
            )
            continue
        actual = _tg.dist_py(pos_a[0], pos_a[1], pos_b[0], pos_b[1])
        if actual < c.min_distance_mm:
            violations.append(
                DomainClearanceAuditViolation(
                    ref_a=c.a,
                    ref_b=c.b,
                    required_mm=c.min_distance_mm,
                    actual_mm=actual,
                    reason=c.because,
                )
            )
    return violations
