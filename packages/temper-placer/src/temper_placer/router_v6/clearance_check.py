"""
Router V6 Stage 5.7: Verify Clearance

Validates clearance distances between all conductors.
Part of temper-8vjm (Stage 5 - Manufacturing DRC)

.. note:: **Bug history (2026-08-13), URGENT.** `_is_hv_keyword_match`'s
   word boundary was `_` or start/end of string ONLY -- `-` was never a
   boundary character. This is "Family C" of the hyphen-boundary
   net-classification defect (see PR #1145/#1162's "Family A"/"Family B"
   fixes in ``temper_io_types::placer_core::netclass`` and
   ``temper_design_bundle::design_rules``): atopile's compiled net names
   use ``-`` and ``_`` interchangeably as within-segment word separators
   (``hb-gnd``, ``safety.uvlo_logic-line``, ...) -- 85 of the 162 net names
   on the real production board contain a hyphen, and every one was
   invisible to the HV keyword matcher whenever
   the matching keyword sat on the hyphen side of a boundary. FIXED: ``-``
   is now an equivalent boundary character to ``_`` on both sides.

   **Over-match found and mitigated**: widening the boundary uniformly
   would reclassify 14 real, confirmed-SELV nets
   (``safety-line``/``safety-line-1..7``, ``safety.ocp-line``,
   ``safety.ocp2-line``, ``safety.ovp-line``, ``safety.thermal-line``,
   ``safety.coil_thermal-line``, ``safety.uvlo_logic-line``) from
   ``Default``/``SIGNAL`` to ``HV`` via the ``"LINE"`` keyword now matching
   their trailing ``-line`` suffix -- the same false-positive shape the
   2026-07-27 fix already fought to remove for ``_`` (see
   ``_is_hv_keyword_match``'s own bug-history docstring below), now
   reappearing for ``-``. All 14 are independently confirmed SELV
   (``elec/domain_manifest.yaml``'s own declaration for
   ``safety.uvlo_logic-line``; PR #1164's per-net trace for the rest, all
   "power_3v3-bound SafetyInterlock fault-tree logic"; PR #1123's
   independent trace for ``safety.ocp2-line``; 4 of the 14
   (``safety-line-4..7``) additionally carry zero connected pads per PR
   #1164's Sec C, so they pose no physical creepage risk regardless of
   classification). Mitigated by ``_SELV_LINE_NET_OVERRIDES`` below (an
   explicit denylist consulted before the keyword cascade), NOT by
   narrowing the boundary back down for ``"LINE"`` -- narrowing would
   silently reintroduce the hyphen-boundary defect for the next hyphenated
   LINE-adjacent net, the same reasoning PR #1162 already applied to its
   own ``"COIL"`` over-match. See
   docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass
from pathlib import Path

from temper_placer.router_v6._check_report_base import BaseCheckReport
from temper_placer.router_v6.routing_results import RoutingResults

try:
    import temper_drc_rs as _temper_drc_rs

    _HAS_RUST_CLEARANCE = hasattr(_temper_drc_rs, "verify_route_clearance")
except ImportError:  # pragma: no cover - exercised only without the Rust wheel
    _temper_drc_rs = None
    _HAS_RUST_CLEARANCE = False

try:
    import temper_orchestration as _to

    _HAS_RUN_CLEARANCE_CHECK = hasattr(_to, "run_clearance_check")
except ImportError:  # pragma: no cover - exercised only without the orchestration wheel
    _to = None
    _HAS_RUN_CLEARANCE_CHECK = False


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
class ClearanceReport(BaseCheckReport):
    """Report of clearance violations."""

    violations: list[ClearanceViolation]
    total_checks: int
    # True iff the check crashed, OR the anti-vacuous-truth guard fired
    # (total_checks == 0 on a board with routed copper -- METHODOLOGY.md
    # Sec 5). Clearance carries HV safety meaning, so ManufacturingReport
    # folds `errored` into critical_violations/total_violations as a
    # fail-closed sentinel rather than reading this as "0 violations
    # found". See
    # docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md.
    errored: bool = False


def verify_clearance(
    routing_results: RoutingResults,
    min_clearance: float = 0.127,  # 5mil standard
    voltage_ratings: dict[str, float] | None = None,
    *,
    backend: str = "auto",
) -> ClearanceReport:
    """
    Verify clearance distances between all conductors.

    Clearance is the straight-line distance through air between
    conductors. Critical for preventing shorts and ensuring reliability.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        min_clearance: Minimum clearance distance (mm)
        voltage_ratings: Optional dict of net_name -> voltage (V).
            Used to determine voltage-dependent HV clearance.
        backend: Compatibility selector. ``"auto"`` (default) and
            ``"rust"`` both use the Rust engine
            (``temper_orchestration.run_clearance_check`` backed by
            ``temper_drc_rs.verify_route_clearance``). ``"python"`` is
            retired and raises ``RuntimeError``. Any missing Rust symbol
            also raises ``RuntimeError`` rather than silently weakening this
            safety check.

    Returns:
        ClearanceReport with violations

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = verify_clearance(results)
        >>> report.violation_count >= 0
        True
    """
    if backend not in ("auto", "python", "rust"):
        raise ValueError(f"backend must be 'auto', 'python', or 'rust', got {backend!r}")

    if backend == "python":
        raise RuntimeError(
            "backend='python' was retired; clearance verification is Rust-only"
        )

    if not (_HAS_RUST_CLEARANCE and _HAS_RUN_CLEARANCE_CHECK):
        raise RuntimeError(
            "Rust clearance engine is required but unavailable: both "
            "temper_drc_rs.verify_route_clearance and "
            "temper_orchestration.run_clearance_check must be present. "
            "Install/build the temper-drc-rs and temper-orchestration wheels."
        )

    return _verify_clearance_rust(routing_results, min_clearance, voltage_ratings)


def _all_routes(routing_results: RoutingResults) -> list[tuple[str, object]]:
    """Every net's route object this check must inspect.

    ``verify_clearance`` used to walk only ``routing_results.compiled_routes``
    -- ``RoutingResults.tree_routes`` / ``.partial_tree_routes`` hold
    ``CompiledTreeRoute`` objects (Steiner/multi-terminal routes), which are
    NOT part of ``compiled_routes`` and carry their own copper geometry
    (``.geometry: TreeRouteGeometry``) and their own ``.vias`` list. The
    U7 exporter (``_adapter_convert.py``) folds tree-routed nets in when
    writing real ``(segment ...)``/``(via ...)`` s-expressions, but this
    check never did -- on a board where a net is tree-routed instead of
    point-to-point, its copper was invisible to clearance checking
    entirely (same class of bug as the ``annular_ring`` tree-route gap
    fixed in docs/evidence/2026-07-27-drc-checks-repaired.md; see
    docs/evidence/2026-07-27-clearance-copper-balance.md for this fix).

    Returns ``(net_name, route)`` pairs from ``compiled_routes``,
    ``tree_routes``, and ``partial_tree_routes`` combined. ``_extract_segments``
    / ``_extract_via_points`` below duck-type on the route object (``.path``
    for ``CompiledRoute``, ``.geometry`` for ``CompiledTreeRoute``).
    """
    routes: list[tuple[str, object]] = list(routing_results.compiled_routes.items())
    routes += list((getattr(routing_results, "tree_routes", None) or {}).items())
    routes += list((getattr(routing_results, "partial_tree_routes", None) or {}).items())
    return routes


def _route_to_rust_tuple(
    net_name: str, route
) -> tuple[
    str,
    float,
    list[tuple[float, float, float, float, str]],
    list[tuple[float, float, float, str, str]],
    list[tuple[float, float, str, str]],
]:
    """Flatten one route into the plain-tuple shape
    ``temper_drc_rs.verify_route_clearance`` expects.

    Uses the shared :func:`_extract_segments` / :func:`_extract_via_points`
    helpers so every Rust invocation sees identical geometry. Explicit
    ``route.vias`` are flattened to
    ``(x, y, diameter, from_layer, to_layer)`` tuples here (diameter
    resolved on the Python side, matching ``via.diameter`` directly).
    """
    width_mm = getattr(route, "width_mm", 0.0)
    segments = _extract_segments(route)
    path_vias = _extract_via_points(route)
    explicit_vias = [
        (
            via.position[0],
            via.position[1],
            via.diameter,
            via.from_layer,
            via.to_layer,
        )
        for via in getattr(route, "vias", [])
    ]
    return (net_name, width_mm, segments, explicit_vias, path_vias)


def _verify_clearance_rust(
    routing_results: RoutingResults,
    min_clearance: float = 0.127,
    voltage_ratings: dict[str, float] | None = None,
) -> ClearanceReport:
    """Rust-backed implementation of :func:`verify_clearance`.

    Phase E batch E3 (plan 2026-08-09-001): the production orchestration —
    min-clearance validation, the ``temper_drc_rs.verify_route_clearance``
    delegation and the ``total_checks`` accounting — runs in
    ``temper-orchestration``'s ``clearance::run_clearance_check`` (the
    ``ClearanceCheckStage``). This function keeps the duck-typed route
    marshalling (:func:`_route_to_rust_tuple`) and the report construction;
    the flat violation tuples returned are wrapped in the dataclasses
    unchanged. See docs/evidence/2026-07-26-clearance-rust-port.md for the
    differential-equivalence evidence and
    docs/evidence/2026-07-27-clearance-copper-balance.md for the manifest
    HV-net-name fix (Part B) that the ``hv_net_names`` argument carries.
    """
    if voltage_ratings is None:
        voltage_ratings = {}

    routes = [_route_to_rust_tuple(net_name, route) for net_name, route in _all_routes(routing_results)]

    raw_violations, total_checks = _to.run_clearance_check(
        routes, min_clearance, voltage_ratings, sorted(_load_manifest_hv_net_names())
    )

    violations = [
        ClearanceViolation(
            net1=net1,
            net2=net2,
            location=(loc_x, loc_y),
            actual_clearance=actual_clearance,
            required_clearance=required_clearance,
            layer=layer,
        )
        for (net1, net2, loc_x, loc_y, actual_clearance, required_clearance, layer) in raw_violations
    ]

    return ClearanceReport(violations=violations, total_checks=total_checks)


def _extract_segments(route) -> list[tuple[float, float, float, float, str]]:
    """Extract same-layer segments ``(x1, y1, x2, y2, layer)`` from a route.

    Shared by the Rust-backend adapter (:func:`_route_to_rust_tuple`) and
    retained as the route-geometry boundary for the production check.

    Handles both ``CompiledRoute`` (``.path``: ``RoutePath``/``RoutePath3D``)
    and ``CompiledTreeRoute`` (``.geometry: TreeRouteGeometry``, no
    ``.path`` attribute at all -- a tree route has multiple independent
    branch paths, so segments must come from
    ``TreeRouteGeometry.iter_segments()`` rather than a single serial
    ``.coordinates``/``.segments`` list, to avoid fabricating a false
    connecting segment between unrelated branches).
    """
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


def _extract_via_points(route) -> list[tuple[float, float, str, str]]:
    """Extract cross-layer via points ``(x, y, from_layer, to_layer)`` from
    a route's path (``RoutePath3D`` layer-changing segments only).

    Shared by the Rust-backend adapter and retained as the route-geometry
    boundary for the production check.
    Deliberately has no finite-value guard, matching the original Python
    behavior exactly (NaN/inf via coordinates propagate rather than being
    filtered here).

    Handles ``CompiledTreeRoute`` (``.geometry``) the same way
    :func:`_extract_segments` does -- see its docstring.
    """
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


@functools.lru_cache(maxsize=1)
def _load_manifest_hv_net_names() -> frozenset[str]:
    """Real HV-domain net names from ``elec/domain_manifest.yaml``.

    The retired Python clearance implementation used to classify a net as HV purely by
    matching 4 hardcoded substrings (``"AC_"``, ``"HV_"``,
    ``"HIGH_VOLTAGE"``, ``"MAINS"``) against the net's own spelling. On
    this board's actual net names that matched **only** ``ac_l``/``ac_n``
    (via the ``"AC_"`` substring after ``.upper()``) -- every other real
    HV-domain net (``DC_BUS_RTN``, ``+170V_BUS``, ``PWR_RTN``,
    ``SW_NODE``, ``GATE_HS``, ``GATE_LS``, ``+15V_LS``, ``w1_1``,
    ``w1_2``, ``zcd``, ``a``) was silently treated as a plain
    default-clearance (0.127mm) net pair instead of the true IEC 60335
    3-14mm mains/DC-bus requirement -- on a mains-connected board, this
    is the single most safety-relevant gap found in this check. See
    docs/evidence/2026-07-27-clearance-copper-balance.md.

    ``elec/domain_manifest.yaml`` is this project's own canonical,
    human-reviewed HV/SELV declaration (``scripts/check_domain_partition.py``
    uses the identical file to answer the identical question at the
    netlist level). Reusing it here means this check's HV/SELV boundary
    cannot silently drift from the project's single declared source of
    truth the way a second hand-maintained keyword list would.

    Self-contained parse (mirrors ``scripts/check_copper_net_consistency.py``'s
    own stated reasoning for not depending on another script's internal
    representation) -- deliberately forgiving: this is a reporting-only
    DRC check, not a hard gate, so a missing/malformed/unreadable manifest
    degrades to an **empty** result (falling back to the substring
    heuristic alone) rather than raising and taking down the router
    pipeline over a file this check has never depended on before.
    """
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


# Word-boundary HV keywords for the HV matcher, delimited by "_"/"-"
# (widened from "_"-only 2026-08-13, see this module's own top-of-file
# bug-history note) or start/end of the (uppercased) net name -- "AC_"/"HV_"
# collapse to bare "AC"/"HV" here because the boundary regex below already
# requires a trailing "_"/"-"/digit/end, making an explicit trailing "_" in
# the keyword itself redundant (and, unlike the literal-substring form, this
# version also recognises a bare trailing "AC"/"HV" with no underscore, e.g.
# a net literally named "HV").
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

# ADDED 2026-08-13 (URGENT hyphen-boundary net-classification defect; see
# this module's own top-of-file bug-history note and
# docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md).
# These 14 real, compiled nets on the production board
# (elec/build/default.net) all end in a hyphenated "-line" suffix and would
# be newly reclassified HV by the "LINE" keyword once "-" becomes a word
# boundary -- the same false-positive shape the 2026-07-27 fix already
# removed for "_". All 14 are independently confirmed SELV:
# elec/domain_manifest.yaml's own declaration for safety.uvlo_logic-line;
# PR #1164's per-net trace for the other 13 ("power_3v3-bound
# SafetyInterlock fault-tree logic", 4 of which -- safety-line-4..7 --
# additionally carry zero connected pads so they pose no physical creepage
# risk regardless of classification); PR #1123's independent trace for
# safety.ocp2-line. Declared here (checked before the keyword cascade)
# rather than narrowing the boundary fix back down for "LINE" -- narrowing
# would silently reintroduce the hyphen-boundary defect for the next
# hyphenated LINE-adjacent net. Uppercased because callers only ever pass
# this module's own `.upper()`'d net name into `_is_hv_keyword_match`.
_SELV_LINE_NET_OVERRIDES = frozenset(
    name.upper()
    for name in (
        "safety-line",
        "safety-line-1",
        "safety-line-2",
        "safety-line-3",
        "safety-line-4",
        "safety-line-5",
        "safety-line-6",
        "safety-line-7",
        "safety.ocp-line",
        "safety.ocp2-line",
        "safety.ovp-line",
        "safety.thermal-line",
        "safety.coil_thermal-line",
        "safety.uvlo_logic-line",
    )
)


def _is_hv_keyword_match(upper: str) -> bool:
    """Match HV keywords at word boundaries.

    Bug history (2026-07-27): this function's predecessor matched
    ``hv_keywords`` (including ``"L1"``, ``"L2"``, ``"L3"``, ``"LINE"``)
    as plain substrings (``kw in upper``) -- the *identical* defect class
    already fixed once in this same codebase, in
    ``creepage_check._is_high_voltage_net`` (merge ``5076e715``). On this
    board's real net names, plain-substring ``"L1"``/``"L2"``/``"LINE"``
    matched ``discharge.k_dis1-coil1``/``...-coil2``,
    ``power_in.bypass_relay-coil1``/``...-coil2`` (all four declared SELV
    "coil drive" nets in ``elec/domain_manifest.yaml``) and
    ``safety.uvlo_logic-line``/``safety.ovp-line`` (declared SELV,
    entirely referenced to ``power_3v3``) -- reclassifying confirmed-SELV
    nets as HV, the same false-positive shape as the creepage bug this
    fix mirrors. See ``docs/evidence/2026-07-27-net-classification-gate.md``
    for the full before/after proof against every net name in the
    manifest.

    2026-08-13: the matching *mechanism* (``re.search(rf"(?:^|_){{kw}}
    (?:$|[\\d_])", upper)`` per keyword) was itself a hand-typed, independent
    copy of the boundary-regex shape this docstring already names as "the
    identical defect class ... fixed once" -- ``clearance_engine.
    _kw_boundary_match`` already delegates the identical mechanism to
    ``temper_geometry.kw_boundary_match_py`` (differentially pinned by
    ``tests/router_v6/test_via_clearance_tier2_rust_differential.py``), so
    this function widened its own boundary to "_"/"-" (Family C) rather than widening the shared kernel, which stays "_"-only for its own pinned differential and its audited-zero live exposure path. ``_CLASSIFY_HV_KEYWORDS`` stays local -- its vocabulary is specific to physical-clearance classification, not the IEC 60335-1 voltage-class vocabulary ``clearance_engine`` uses -- only the matching mechanism is shared, not the keyword data. The widened "LINE" keyword's over-match on 14 real confirmed-SELV "-line" nets is guarded by :data:`_SELV_LINE_NET_OVERRIDES`, checked first. The pinned oracle copy of this function
    (``tests/router_v6/_clearance_family_py_oracle.py::
    _oracle_is_hv_keyword_match``) is deliberately left untouched -- it is
    registered in ``scripts/oracle_hashes.json`` and exists precisely to be
    an independent implementation for the Rust-port differential suite.
    """
    if upper in _SELV_LINE_NET_OVERRIDES:
        return False
    for kw in _CLASSIFY_HV_KEYWORDS:
        if re.search(rf"(?:^|[_-]){re.escape(kw)}(?:$|[\d_-])", upper):
            return True
    # "B+" has no alphanumeric trailing boundary to anchor on; anchored
    # on the leading "_"/"-"/start side only (mirrors
    # creepage_check._is_high_voltage_net's identical special case).
    return bool(re.search(r"(?:^|[_-])B\+", upper))
