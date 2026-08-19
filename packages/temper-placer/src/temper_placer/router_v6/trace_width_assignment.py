"""
Router V6 Stage 4.4: Assign Trace Widths

Assigns trace widths based on net class and current requirements.
Part of temper-eixu (Stage 4 - Geometric Realization)

Wave 4 migration note: the per-net classification (``_kw_boundary_match`` /
``_determine_trace_width``) now delegates to ``temper_geometry``'s
``trace_width_assignment`` kernels
(``packages/temper-geometry/src/trace_width_assignment.rs``); the
``PathfindingResult``-driven orchestration (``assign_trace_widths``) and the
``TraceWidth``/``TraceWidthAssignment`` dataclasses stay here.  See
``packages/temper-geometry/VERIFICATION.md`` for the full writeup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import temper_drc_rs as _tdrc
import temper_geometry as _tg

from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.tree_route_geometry import TreeRouteGeometry

if TYPE_CHECKING:
    from temper_placer.router_v6.stage0_data import StackupInfo

logger = logging.getLogger(__name__)

# ``DesignRules.get_rules_for_net`` never returns ``None``: its last tier is a
# synthesized catch-all ``NetClassRules(name="Default", ...)`` built from the
# board's ``default_trace_width`` (``packages/temper-design-bundle/src/
# design_rules.rs::default_net_class_rules``).  "This net has no class" is
# therefore spelled as "the resolved class is the catch-all", not as a null
# check -- the distinction the pre-fix code had no way to make at all.
_CATCH_ALL_CLASS_NAME = "Default"


# PR #1195 copper-weight/layer-awareness fix
# (docs/evidence/2026-08-13-router-nlayer-routing.md SS4): the router can now
# place copper on ANY declared signal layer (F.Cu/In3.Cu/In4.Cu/B.Cu), and
# PR #1178's stackup declares outer layers 2oz, inner layers 1oz -- so a
# width picked without knowing which layer a segment lands on is silently
# wrong once that segment can land internal. `_EXTERNAL_COPPER_LAYERS` is
# the one hardcoded fact this module still carries: KiCad's own board-format
# convention that the outermost two copper layers are always named "F.Cu"/
# "B.Cu" (true of every board in this repo, not a per-board assumption) --
# every OTHER layer name is treated as internal, sourced from the board's
# own stackup declaration, never a second hardcoded "In1.Cu"/"In2.Cu" list
# that a future stackup edit (adding In5.Cu, say) could silently miss.
_EXTERNAL_COPPER_LAYERS = frozenset({"F.Cu", "B.Cu"})

# 1oz copper = 35um. Universal IPC copper-weight unit conversion (not a
# per-board figure) -- matches docs/hardware/TRACE_WIDTH_CALCULATIONS.md's
# own "1oz (35µm)" design parameter and stage0_data.LayerInfo's own doc
# comment ("thickness_um: Copper thickness in micrometers (35µm = 1oz)").
_OZ_THICKNESS_UM = 35.0

# The reference copper weight/layer role docs/hardware/
# TRACE_WIDTH_CALCULATIONS.md SS1 and this repo's own
# check_stackup_copper_weight_gate.py assume the pre-PR-#1195
# `power_width`/`hv_width`/`power_width*0.6` constants were calibrated
# against: 2oz, external. Used ONLY to back-derive the current those
# legacy constants implicitly assumed (see
# `_implied_legacy_current_a` below) -- not a new assumption, a citation
# of the documented one.
_LEGACY_CONSTANT_COPPER_OZ = 2.0
_LEGACY_CONSTANT_INTERNAL = False


def _kw_boundary_match(upper: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by "_" or start/end of the
    uppercased net name.

    Bug history (2026-07-27): ``_determine_trace_width`` used to match
    ``"AC_"``/``"HV_"``/``"HIGH_VOLTAGE"``/``"GATE"``/``"DRIVE"`` as plain
    substrings (``kw in name_upper``) -- the same defect class confirmed
    three times elsewhere in this repo (``creepage_check.py``,
    ``clearance_check.py``, ``clearance_engine.py``; see
    ``docs/evidence/2026-07-27-net-classification-gate.md``). Found by
    ``scripts/check_net_classification.py`` auditing every net-name
    classifier for the same shape. ``"AC_"``/``"HV_"`` collapse to bare
    ``"AC"``/``"HV"`` here because the boundary regex already requires a
    trailing ``"_"``/digit/end, making the explicit trailing ``"_"`` in
    the original keyword redundant.
    """
    return _tg.kw_boundary_match_py(upper, list(keywords))


@dataclass
class TraceWidth:
    """Trace width assignment for a net."""

    net_name: str
    width_mm: float
    reason: str  # Why this width was chosen


@dataclass
class TraceWidthAssignment:
    """Collection of trace width assignments."""

    assignments: dict[str, TraceWidth]  # net_name -> TraceWidth

    @property
    def assignment_count(self) -> int:
        """Number of trace width assignments."""
        return len(self.assignments)

    def get_width(self, net_name: str) -> float | None:
        """Get assigned width for a net."""
        assignment = self.assignments.get(net_name)
        return assignment.width_mm if assignment else None


def _netclass_trace_width(design_rules: Any, net_name: str) -> TraceWidth | None:
    """The SSOT width for *net_name*, or ``None`` if it has no real class.

    Returns ``None`` (so the caller falls back, loudly) in exactly three
    cases: no ``design_rules`` was threaded in, the net resolves only to the
    synthesized ``Default`` catch-all, or the resolved class carries a
    non-positive width.  Any *other* failure is re-raised rather than
    swallowed -- a broad ``except`` here would recreate the silent-fallback
    shape this function exists to remove.
    """
    if design_rules is None:
        return None
    get_rules = getattr(design_rules, "get_rules_for_net", None)
    if get_rules is None:
        return None

    rules = get_rules(net_name)
    if rules is None:
        return None
    class_name = getattr(rules, "name", None)
    if class_name is None or class_name == _CATCH_ALL_CLASS_NAME:
        return None

    width_mm = getattr(rules, "trace_width", None)
    if width_mm is None:
        width_mm = getattr(rules, "trace_width_mm", None)
    if width_mm is None or float(width_mm) <= 0.0:
        return None

    return TraceWidth(
        net_name=net_name,
        width_mm=float(width_mm),
        reason=f"netclass {class_name} trace_width",
    )



def assign_trace_widths(
    pathfinding_result: PathfindingResult,
    default_width: float = 0.127,  # 5mil standard
    power_width: float = 0.508,  # 20mil for power
    hv_width: float = 0.635,  # 25mil for HV
    design_rules: Any = None,
    stackup: StackupInfo | None = None,
    temp_rise_c: float = _tdrc.TRACE_TEMP_RISE_C,
) -> TraceWidthAssignment:
    """
    Assign trace widths from the netclass table and layer-aware ampacity.

    Two independent SSOTs are combined, each preserved from the PR that
    introduced it:

    * ``design_rules.get_rules_for_net(net).trace_width`` (netclass table)
      is the declared-width SSOT (PR #1199-era netclass threading,
      docs/evidence/2026-08-13-router-netclass-trace-widths.md).  It is
      used as the FLOOR whenever the net resolves to a real class.
    * ``stackup`` + ``temp_rise_c`` (PR #1195 layer-aware ampacity,
      docs/evidence/2026-08-13-router-nlayer-routing.md SS4) make width a
      function of (current, copper weight, internal-vs-external) per net
      via IPC-2221B -- the PHYSICS minimum.  It can only WIDEN the
      netclass floor, never narrow it.

    The three keyword buckets (``default_width``/``power_width``/
    ``hv_width``) are the fallback for classless nets ONLY, logged at
    WARNING (see the module docstring's bug history).

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        default_width: Fallback default trace width (mm), classless nets only
        power_width: Fallback width for power nets (mm), classless nets only
        hv_width: Fallback width for high-voltage nets (mm), classless only
        design_rules: Board ``DesignRules``; when omitted, the netclass
            table is not consulted and every net falls to the keyword
            buckets unless ``stackup`` provides a physics width.
        stackup: The board's declared stackup (``ParsedPCB.stackup``), read
            live from ``pcb/temper.kicad_pcb``'s own ``(setup (stackup
            ...))`` block. When supplied, width becomes a function of
            (current, copper weight, internal-vs-external) per net -- see
            ``_determine_trace_width_layer_aware`` -- instead of the flat
            ``power_width``/``hv_width`` constants alone, so a stackup edit
            (e.g. a copper-weight change) propagates automatically instead
            of silently going stale. ``None`` (the default) preserves the
            exact pre-existing keyword-only behavior for callers that
            haven't been updated to pass it -- see AGENTS.md and
            docs/evidence/2026-08-13-router-nlayer-routing.md SS4 for why a
            width picked without this input can be silently wrong once a
            net can route on an inner layer.
        temp_rise_c: Allowed temperature rise (deg C) for the IPC-2221B
            derivation, only used when `stackup` is supplied. Defaults to
            `temper_drc_rs.TRACE_TEMP_RISE_C` (20.0), single-sourced from
            `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` SS1 ("Max Temp Rise
            (traces): 20C -- IPC-2221B recommendation").

            FIXED 2026-08-14: this default used to be an independent
            literal `10.0`, justified only as "matches this repo's existing
            convention (temper-drc-rs's `ipc2152_min_width_mm`/`gates.py`'s
            `StackupGate`, both default 10.0)" -- i.e. agreement between
            uncited code defaults, not agreement with this board's own
            formal design spec. Measured consequence
            (docs/evidence/2026-08-14-ntc-no-ampacity-current-fix-and-pour-neck-measurement.md
            SS2.2 found it, docs/evidence/2026-08-14-ntc-no-realization-and-delta-t-reconciliation.md
            fixed it): the as-wired production call
            (`_pipeline_route.py::_run_stage5`) sized every current-cited
            net (`AC_L`/`AC_N`/`power_in.ntc-no`/`DC_BUS+`/`SW_NODE`/
            `GATE_H`/`GATE_L`/...) at the uncited 10C figure, not this
            document's cited 20C one -- e.g. `power_in.ntc-no` at
            6.329mm instead of 4.156mm. Every current-cited net's required
            width becomes SMALLER at 20C than at 10C (higher allowed rise
            needs less copper for the same current) -- this correction is
            not a shortcut to pass any specific board, it is adopting the
            cited standard instead of an unsourced internal default; see
            the second evidence doc above for the full per-net table.

    Returns:
        TraceWidthAssignment with all width assignments

    Example:
        >>> from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        >>> result = PathfindingResult(routed_paths={}, failed_nets=[])
        >>> assignment = assign_trace_widths(result)
        >>> assignment.assignment_count >= 0
        True
    """
    assignments = {}

    # Tree geometry is branch-aware rather than serial RoutePath data, but
    # width is a net-class property.  Include complete and partial trees so
    # experimental output receives the same board-derived assignment as every
    # conventional route.
    routed_net_names = (
        set(pathfinding_result.routed_paths)
        | set(pathfinding_result.partial_paths)
        | set(pathfinding_result.tree_routes)
        | set(pathfinding_result.partial_tree_routes)
    )
    fallback_nets: list[str] = []
    for net_name in routed_net_names:
        path = (
            pathfinding_result.routed_paths.get(net_name)
            or pathfinding_result.partial_paths.get(net_name)
            or pathfinding_result.tree_routes.get(net_name)
            or pathfinding_result.partial_tree_routes.get(net_name)
        )
        # Layer-aware physics first (PR #1195): IPC-2221B minimum from the
        # net's real current, copper weight, and internal-vs-external role.
        # Explicit annotation: without it, mypy infers `width`'s type from
        # this branch's non-Optional `TraceWidth` return alone, then flags
        # the `else` branch below (which legitimately assigns the Optional
        # `_netclass_trace_width` result, handled by the `if width is None`
        # right after it) as an incompatible reassignment.
        width: TraceWidth | None
        if stackup is not None:
            width = _determine_trace_width_layer_aware(
                net_name,
                path,
                default_width,
                power_width,
                hv_width,
                stackup,
                temp_rise_c,
            )
        else:
            # No stackup: the netclass table is the SSOT (main's netclass
            # threading), keyword buckets only for classless nets.
            width = _netclass_trace_width(design_rules, net_name)
            if width is None:
                # No real netclass for this net -- keyword cascade, logged.
                fallback_nets.append(net_name)
                width = _determine_trace_width(
                    net_name,
                    default_width,
                    power_width,
                    hv_width,
                )

        # The netclass table is a floor even when stackup supplied the
        # physics width: a declared 5.0mm HighVoltage width must not be
        # undercut by a physics minimum computed from a stale/smaller
        # current citation.
        if design_rules is not None and stackup is not None:
            netclass_width = _netclass_trace_width(design_rules, net_name)
            if netclass_width is not None and netclass_width.width_mm > width.width_mm:
                width = netclass_width

        assignments[net_name] = width

    if fallback_nets:
        if design_rules is None:
            logger.warning(
                "trace-width: no design_rules threaded into Stage 4.4 -- all "
                "%d routed net(s) fell back to the keyword buckets "
                "(default=%.4gmm power=%.4gmm hv=%.4gmm) instead of the "
                "netclass trace_width table. This is the shape of the defect "
                "in docs/evidence/2026-08-13-router-netclass-trace-widths.md.",
                len(fallback_nets),
                default_width,
                power_width,
                hv_width,
            )
        else:
            logger.warning(
                "trace-width: %d of %d routed net(s) have no netclass "
                "assignment and fell back to the keyword buckets: %s",
                len(fallback_nets),
                len(routed_net_names),
                ", ".join(sorted(fallback_nets)),
            )

    return TraceWidthAssignment(assignments=assignments)




def _determine_trace_width(
    net_name: str,
    default_width: float,
    power_width: float,
    hv_width: float,
) -> TraceWidth:
    """
    Determine appropriate trace width for a net.

    Args:
        net_name: Net name
        default_width: Default width
        power_width: Power net width
        hv_width: High voltage width

    Returns:
        TraceWidth assignment
    """
    width_mm, reason = _tg.determine_trace_width_py(
        net_name, default_width, power_width, hv_width
    )
    return TraceWidth(
        net_name=net_name,
        width_mm=width_mm,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Layer-aware width assignment (PR #1195 copper-weight-blindness fix)
# ---------------------------------------------------------------------------


def _layers_touched(path: RoutePath | RoutePath3D | TreeRouteGeometry | None) -> frozenset[str]:
    """Every physical copper layer name `path`'s geometry actually occupies.

    Handles all three shapes `PathfindingResult` can hand back: a legacy
    single-layer `RoutePath` (`.layer_name`), a real per-segment
    `RoutePath3D` (`.segments`' third element), and a branch-aware
    `TreeRouteGeometry` (delegates to `iter_segments`, which already
    normalizes both branch-path shapes). Returns an empty set if `path` is
    None or carries no geometry -- callers must decide the safe fallback,
    this function does not guess a layer.
    """
    if path is None:
        return frozenset()
    if isinstance(path, TreeRouteGeometry):
        return frozenset(pt[2] for seg in path.iter_segments() for pt in seg)
    if isinstance(path, RoutePath3D):
        return frozenset(seg[2] for seg in path.segments)
    return frozenset({path.layer_name})


def _copper_weight_oz(layer_name: str, stackup: StackupInfo) -> float | None:
    """This layer's declared copper weight, read live from the board's own
    stackup SSOT (`StackupInfo`, parsed from `pcb/*.kicad_pcb`'s own
    `(setup (stackup ...))` block by `temper_design_bundle_python`'s parse
    engine -- see `router_v6/io/_parse_board.py`). `None` if `stackup`
    doesn't declare this layer name -- callers decide the fallback.
    """
    for layer in stackup.layers:
        if layer.name == layer_name:
            return layer.thickness_um / _OZ_THICKNESS_UM
    return None


def _worst_case_copper_context(
    layers: frozenset[str], stackup: StackupInfo
) -> tuple[float, bool] | None:
    """`(copper_weight_oz, internal_layer)` for the LEAST forgiving layer
    among `layers` -- internal beats external at any weight (IPC-2221B's
    k=0.024 vs 0.048), and within the same internal/external role the
    thinner declared weight is worse. A single width is assigned per net
    (not per segment), so sizing to the worst layer the net's own routed
    geometry actually touches is the only choice that cannot be too narrow
    for wherever the router put the copper.

    Returns `None` if no declared-weight information is available for any
    touched layer (or `layers` is empty) -- the caller falls back to the
    stackup's own worst-case (thinnest) declared layer instead of guessing.
    """
    candidates = []
    # `layers` is a frozenset: iterate a stable order (layer name) rather
    # than the set's PYTHONHASHSEED-dependent iteration order, which would
    # otherwise leak into `candidates`' insertion order before the sort below
    # (scripts/check_hash_order_determinism.py).
    for layer_name in sorted(layers):
        oz = _copper_weight_oz(layer_name, stackup)
        if oz is not None:
            internal = layer_name not in _EXTERNAL_COPPER_LAYERS
            candidates.append((oz, internal))
    if not candidates:
        return None
    # Internal (True) sorts after external (False) for the same weight, so
    # sorting by (not internal, oz) ascending and taking the LAST entry
    # picks internal-if-any, thinnest-if-tied -- the worst case.
    candidates.sort(key=lambda c: (not c[1], -c[0]))
    return candidates[-1]


def _stackup_worst_case_declared(stackup: StackupInfo) -> tuple[float, bool] | None:
    """Worst-case `(copper_weight_oz, internal_layer)` across the WHOLE
    declared stackup -- the safe-by-construction fallback for a net whose
    routed geometry isn't known yet (no path) or whose touched layer(s)
    aren't in the stackup's own declaration. Prefers internal layers
    (matches PR #1195: production routing can place a signal-class net on
    any declared signal/mixed layer, so "no layer info yet" must assume the
    worst one, not the best).
    """
    return _worst_case_copper_context(frozenset(layer.name for layer in stackup.layers), stackup)


def _implied_legacy_current_a(width_mm: float, temp_rise_c: float) -> float:
    """The current IPC-2221B implies `width_mm` was sized for, evaluated at
    the SAME (2oz, external) reference `docs/hardware/
    TRACE_WIDTH_CALCULATIONS.md` SS1 and this repo's own
    `check_stackup_copper_weight_gate.py` already establish as this board's
    outer-copper assumption. This is not a new number -- it is the
    already-fixed legacy `power_width`/`hv_width`/`power_width*0.6`
    constant's OWN implied current, recovered by running the same formula
    forward instead of guessing a fresh one. On 2oz external copper this
    round-trips back to `width_mm` (see
    `test_layer_aware_external_matches_legacy_exactly` for the pinned
    property); on lighter/internal copper it correctly derates.
    """
    return _tg.ipc2221b_current_capacity_a_py(
        width_mm, _LEGACY_CONSTANT_COPPER_OZ, temp_rise_c, _LEGACY_CONSTANT_INTERNAL
    )


def _resolve_current_a(
    net_name: str,
    power_width: float,
    hv_width: float,
    temp_rise_c: float,
) -> tuple[float, str] | None:
    """The physics current input for `net_name`, and which source supplied
    it. Returns `None` for a net with no HV/Power/Gate keyword match AND no
    specific current-table entry -- i.e. a genuine default/signal net,
    which stays on the pure fabrication-floor `default_width` unchanged
    (this function is never consulted for it).
    """
    # FAIL-CLOSED lookup. This used to be
    # `specific = get_net_current(net); if specific != DEFAULT_SIGNAL_CURRENT`
    # -- i.e. the 0.1A default doubled as the "not in the table" sentinel, so
    # a power net nobody had entered was indistinguishable from a declared
    # signal net and fell through to the keyword cascade below. Measured on
    # this board before the fix: `DC_BUS_RTN`, `PWR_RTN`, `tank-out`,
    # `tank.c_tank1-p2`, `w1_1`, `w1_2` and `hb-gnd` all reached this point
    # unmatched, matched no keyword either, and returned None -- the plain
    # 0.127mm fabrication floor. `+170V_BUS` fared no better in kind: it
    # matched only the `startswith("+")` power bucket, sizing the 22.5A RMS
    # DC bus from the legacy 0.508mm power-width constant's implied 3.268A.
    # `try_net_design_current_a` now returns None ONLY for a net with no
    # declared entry, which is a distinct and reportable condition.
    specific = _tdrc.try_net_design_current_a(net_name)
    if specific is not None:
        return specific, (
            f"declared design current {specific:.4g}A "
            f"(temper_drc_rs.net_currents, fail-closed exact lookup)"
        )

    upper = net_name.upper()
    if _tg.kw_boundary_match_py(upper, ["AC_", "HV_", "HIGH_VOLTAGE"]):
        implied = _implied_legacy_current_a(hv_width, temp_rise_c)
        return implied, f"current implied by legacy HV width {hv_width:.4g}mm at 2oz external"
    if _tg.kw_boundary_match_py(upper, ["GND", "VCC", "VDD", "VSS", "POWER"]) or upper.startswith(
        "+"
    ):
        implied = _implied_legacy_current_a(power_width, temp_rise_c)
        return (
            implied,
            f"current implied by legacy power width {power_width:.4g}mm at 2oz external",
        )
    if _tg.kw_boundary_match_py(upper, ["GATE", "DRIVE"]):
        implied = _implied_legacy_current_a(power_width * 0.6, temp_rise_c)
        return (
            implied,
            f"current implied by legacy gate-drive width {power_width * 0.6:.4g}mm at 2oz external",
        )
    return None


def _determine_trace_width_layer_aware(
    net_name: str,
    path: RoutePath | RoutePath3D | TreeRouteGeometry | None,
    default_width: float,
    power_width: float,
    hv_width: float,
    stackup: StackupInfo,
    temp_rise_c: float,
) -> TraceWidth:
    """Layer-aware, current-aware replacement for `_determine_trace_width`.

    Width is `max(default_width, IPC-2221B minimum for (current,
    copper_weight_oz, internal_layer))` -- never a single flat per-class
    constant -- for any net with a resolvable current (see
    `_resolve_current_a`); a genuine default/signal net with no
    current-table entry and no HV/Power/Gate keyword match keeps the plain
    fabrication-floor `default_width`, exactly as `_determine_trace_width`
    already did.
    """
    resolved = _resolve_current_a(net_name, power_width, hv_width, temp_rise_c)
    if resolved is None:
        return TraceWidth(net_name=net_name, width_mm=default_width, reason="Standard signal trace")
    current_a, current_source = resolved

    layers = _layers_touched(path)
    context = _worst_case_copper_context(layers, stackup) if layers else None
    if context is None:
        context = _stackup_worst_case_declared(stackup)
    if context is None:
        # Stackup declares nothing usable at all -- cannot derive a
        # physics width; fail toward the pre-existing keyword-only
        # behavior rather than guessing a copper weight.
        return _determine_trace_width(net_name, default_width, power_width, hv_width)
    copper_weight_oz, internal_layer = context

    physics_width = _tg.ipc2221b_min_trace_width_mm_py(
        current_a, copper_weight_oz, temp_rise_c, internal_layer
    )
    layer_word = "internal" if internal_layer else "external"
    if physics_width > default_width:
        width_mm = physics_width
        reason = (
            f"IPC-2221B: {current_a:.4g}A on {copper_weight_oz:.2f}oz {layer_word} copper "
            f"requires {physics_width:.4f}mm (dT={temp_rise_c:.0f}C; {current_source})"
        )
    else:
        width_mm = default_width
        reason = (
            f"Fabrication floor {default_width:.4f}mm exceeds IPC-2221B minimum "
            f"{physics_width:.4f}mm for {current_a:.4g}A on {copper_weight_oz:.2f}oz "
            f"{layer_word} copper ({current_source})"
        )
    return TraceWidth(net_name=net_name, width_mm=width_mm, reason=reason)
