"""route_pcb entry point and conversion/writing functions for the router_v6 adapter."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import tempfile
import uuid
from collections.abc import Collection
from pathlib import Path
from typing import Any

from temper_placer.router_v6._adapter_types import (
    CongestionRegion,
    DrcViolation,
    ParsedPcbLike,
    RoutingResult,
)
from temper_placer.router_v6._strip_copper import strip_existing_zones

# Re-exported from _zone_pour_stitch.py (LOC cap paydown, temper-N7-cap5):
# _stitch_isolated_pads/_emit_zone_pours/_zone_layers_for_net/
# _zone_params_for_net are in __all__ below; _chamfer_path_points is used
# directly in _write_routes_to_content() and imported directly by
# tests/router_v6/test_adapter.py from this module path, so both re-exports
# are load-bearing, not vestigial.
from temper_placer.router_v6._zone_pour_stitch import (  # noqa: F401
    _chamfer_path_points,
    _emit_zone_pours,
    _stitch_isolated_pads,
    _zone_layers_for_net,
    _zone_params_for_net,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_apply_placements_to_pcb",
    "_build_routing_result",
    "_emit_zone_pours",
    "_stitch_isolated_pads",
    "_to_stage0_netclass_rules",
    "_write_routes_to_content",
    "_zone_layers_for_net",
    "_zone_params_for_net",
    "route_pcb",
]

# Fixed namespace for deriving synthetic KiCad ``tstamp`` UUIDs
# deterministically (see ``_next_tstamp`` below).
_TSTAMP_NAMESPACE = uuid.UUID("f8b1a2b0-6c4e-4a3a-9b7a-1a2b3c4d5e6f")


def _next_tstamp(counter: list[int]) -> str:
    """Return the next deterministic KiCad ``tstamp`` UUID.

    A single ``route_pcb()`` call writes many synthetic ``(segment ...)``/
    ``(via ...)`` elements. The previous implementation drew each
    ``tstamp`` from ``uuid.uuid4()``, which reads ``os.urandom`` -- so
    identical code and identical input produced a byte-different
    ``.kicad_pcb`` on every single run. Measurement showed this was the
    *only* source of that non-determinism: net topology, routed geometry,
    and layer/via assignment were already stable across 8 independent
    runs with default (randomized) ``PYTHONHASHSEED`` -- diffing two
    such runs after normalizing ``tstamp`` fields to a placeholder
    produced a zero-line diff (see
    docs/evidence/2026-07-27-router-determinism.md).

    ``tstamp`` is a KiCad object identifier only; it carries no
    electrical, geometric, or DRC meaning, so replacing the random draw
    with a value derived from a stable emission-order sequence number is
    safe and does not change what gets routed.

    This *does* depend on segment/via emission happening in a fixed
    order within one ``route_pcb()`` call -- an explicit, documented
    dependency rather than an incidental one. That order is already
    deterministic today (net iteration in ``_write_routes_to_content``
    walks a plain ``dict`` in insertion order, not a ``set``/``HashMap``
    in hash order), so a monotonic counter over that order is sufficient;
    it is not itself a tie-break.
    """
    n = counter[0]
    counter[0] = n + 1
    return str(uuid.uuid5(_TSTAMP_NAMESPACE, f"temper-router-v6-tstamp-{n}"))


def _to_stage0_netclass_rules(rules: Any) -> Any:
    """Convert a core NetClassRules (or duck-type-compatible shape) into a
    stage0 NetClassRules dataclass.

    This adapter is the single conversion boundary between the YAML SSOT
    representation (``core.netclass_rules_gen.NetClassRules``) and the A*
    engine's internal representation (``stage0_data.NetClassRules``).

    Explicit attribute checking replaces the previous ``getattr(rules, attr,
    default)`` duck-type approach: unrecognized shapes raise ``TypeError``
    rather than silently returning defaults.
    """
    from temper_placer.router_v6.stage0_data import NetClassRules as Stage0NetClassRules

    # --- Resolve each mapped field with explicit shape checking ---

    def _resolve(name: str, *aliases: str) -> Any:
        """Return the first attribute of *aliases* that exists on *rules*."""
        for alias in aliases:
            if hasattr(rules, alias):
                return getattr(rules, alias)
        raise TypeError(
            f"Cannot convert {type(rules).__name__!r} to stage0 NetClassRules: "
            f"no attribute matching any of {list(aliases)} found"
        )

    name = _resolve("name", "name")
    clearance_mm = _resolve("clearance", "clearance", "clearance_mm")
    trace_width_mm = _resolve("trace_width", "trace_width", "trace_width_mm")
    via_diameter_mm = _resolve("via_diameter", "via_diameter", "via_diameter_mm")
    via_drill_mm = _resolve("via_drill", "via_drill", "via_drill_mm")

    # max_current_rating → current_rating_amps (R1 fix)
    current_rating_amps: float | None = None
    if hasattr(rules, "max_current_rating"):
        current_rating_amps = getattr(rules, "max_current_rating")

    # safety_category survives conversion (needed by R6 HV/AC forced-segment gate)
    safety_category: str | None = None
    if hasattr(rules, "safety_category"):
        val = getattr(rules, "safety_category")
        if val is not None:
            safety_category = str(val)

    # --- R1b: Warn on unrepresented fields that are explicitly set ---
    _UNREPRESENTED_WARN = (
        ("creepage_mm", "Creepage distance", 0.0),
        ("voltage_v", "Voltage rating", 0.0),
        ("routing_strategy", "Routing strategy", None),
        ("via_cost_multiplier", "Via cost multiplier", 1.0),
        ("layer_costs", "Layer cost overrides", None),
        ("via_template", "Via template", None),
        ("target_impedance", "Target impedance", None),
        ("required_layer", "Required KiCad layer", None),
        ("layer", "KiCad layer", None),
        ("dru_priority", "DRU priority", 0),
    )
    for attr_name, human_label, default_val in _UNREPRESENTED_WARN:
        val = getattr(rules, attr_name, None)
        if val is not None and val != default_val:
            logger.warning(
                "_to_stage0_netclass_rules: dropping %s=%s for netclass %r "
                "— no stage0 equivalent field exists",
                human_label,
                val,
                name,
            )

    return Stage0NetClassRules(
        name=name,
        clearance_mm=clearance_mm,
        trace_width_mm=trace_width_mm,
        via_diameter_mm=via_diameter_mm,
        via_drill_mm=via_drill_mm,
        current_rating_amps=current_rating_amps,
        safety_category=safety_category,
    )


def _normalize_target_nets(
    target_nets: Collection[str] | None,
    available_nets: Collection[str],
) -> list[str] | None:
    """Validate and deterministically normalize an optional net scope."""
    if target_nets is None:
        return None
    normalized = sorted({name.strip() for name in target_nets})
    if not normalized or any(not name for name in normalized):
        raise ValueError("target_nets must contain at least one non-empty name")
    unknown = set(normalized) - set(available_nets)
    if unknown:
        raise ValueError(f"target_nets contains unknown nets: {', '.join(sorted(unknown))}")
    return normalized


def route_pcb(
    parsed: ParsedPcbLike | Any,
    placements: dict[str, tuple[float, float]],
    design_rules: Any = None,
    thermal_flat: Any = None,
    thermal_weight: float = 0.0,
    enable_all_pad_tree: bool = False,
    enable_zone_pours: bool = True,
    enable_connectivity_verifier: bool = False,
    enable_manufacturing_drc: bool = False,
    sat_conflict_limit: int | None = 20_000,
    sat_time_limit_ms: int | None = None,
    rotations: dict[str, float] | None = None,
    target_nets: Collection[str] | None = None,
    skip_stage3: bool = False,
) -> RoutingResult:
    """Route a PCB using the Router V6 pipeline.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6.
        placements: Dict mapping component ref -> (x, y) position in mm.
            If empty, routing proceeds with the board's existing positions.
        design_rules: Optional DesignRules with net_classes for netclass
            form injection into the output PCB. net_class_assignments and
            net_classes are both derived from this object and threaded
            into the pipeline automatically -- see the block below.
        rotations: Optional dict mapping component ref -> new absolute
            footprint rotation in degrees (see
            ``CpSatPlacementResult.to_rotations_dict()``). Threaded
            straight through to ``_apply_placements_to_pcb`` -- see its
            docstring for exactly what is and is not rewritten. A ref
            with no entry here keeps its existing angle unchanged,
            matching this parameter's pre-existing absence entirely.
        thermal_flat: U9 optional (N,) float32 thermal cost field from
            the previous round's field.  Threaded to A* kernel.
        thermal_weight: U9 multiplier on per-cell thermal cost
            (from CostFieldInput.weight).  0.0 = field-off.
        enable_all_pad_tree: Enable experimental all-terminal tree
            expansion (default False).
        enable_zone_pours: Emit filled-copper zone geometry for power/
            ground/HV nets (per netclass SSOT).  Default True -- zones
            are enabled by default for multi-layer power/ground routing.
        enable_connectivity_verifier: Run post-write connectivity
            preflight via verify_net_connectivity (default False).
        enable_manufacturing_drc: Run the Stage 5 manufacturing DRC
            checks (acid_trap, annular_ring, teardrop, thermal_relief,
            power_planes, copper_balance, creepage, clearance) and attach
            a ManufacturingReport to the result. Reporting-only; never
            raises. Default False -- verify_clearance is O(n^2) pure
            Python and does not complete on a routed board (27 min,
            9.2 GB, unfinished). See
            docs/evidence/2026-07-26-manufacturing-drc-scalability.md.
        sat_conflict_limit: Bound the Stage 3 CaDiCaL SAT solve to at
            most this many conflicts (see
            RouterV6Pipeline.__init__'s docstring for the full
            rationale and docs/evidence/2026-07-27-sat-bound-tradeoff.md
            for the measured trade-off curve). Default 20_000 -- pass
            None for the old, unbounded behavior.
        sat_time_limit_ms: Secondary wall-clock bound on the same
            solve. None by default (conflict-count alone is the
            recommended bound; it is deterministic, wall-clock is not).
        target_nets: Optional names of nets to route during Stage 4. ``None``
            preserves the full-board default; a non-empty scope is validated
            against the parsed board and normalized before dispatch.
        skip_stage3: Bypass the SAT topology stage for a bounded scoped run.
            Defaults to ``False`` so existing callers are unchanged.

    Returns:
        RoutingResult with completion_rate, routed_pcb_content, and
        optional connectivity dict.

    Raises:
        ValueError: If parsed has no source_path.
    """
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    if not placements:
        logger.warning("Empty placements provided; routing with existing board positions.")

    pcb_path = getattr(parsed, "source_path", None)
    if pcb_path is None:
        raise ValueError("ParsedPCB has no source_path attribute")
    pcb_path = Path(pcb_path)
    available_nets = {
        net.name for net in getattr(parsed, "nets", []) if getattr(net, "name", None)
    }
    normalized_target_nets = _normalize_target_nets(target_nets, available_nets)

    # Resolve per-net layer assignments from the netclass SSOT (W2 R2) so the
    # router constrains each net to its assigned layer instead of letting a
    # signal hop onto a reference/power plane.
    layer_constraints: dict[str, Any] = {}
    if design_rules is not None:
        from temper_placer.router_v6.layer_assignment import (
            layer_assignments_from_netclass,
        )

        net_names = [n.name for n in getattr(parsed, "nets", []) if getattr(n, "name", None)]
        if net_names:
            layer_constraints = layer_assignments_from_netclass(design_rules, net_names)
        else:
            # design_rules was supplied (caller wants netclass-aware routing)
            # but `parsed` has no usable `.nets` -- every net silently stays
            # on its default layer and DesignRules' `layer` field is never
            # consulted. This is the exact shape of a known prior bug: see
            # docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md.
            # Loud on purpose -- this previously failed silently across every
            # production-board measurement call site in this codebase.
            logger.warning(
                "route_pcb: design_rules was provided but `parsed` has no "
                "resolvable .nets (got %r) -- per-net layer-constraint "
                "resolution is silently disabled; every net will stay on "
                "its default layer regardless of netclass SSOT `layer` "
                "assignments. Pass `parsed.nets` (a sequence with .name "
                "attributes) if real multi-layer routing behavior matters "
                "for this call.",
                getattr(parsed, "nets", None),
            )

    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_theta_star=False,
        enable_lazy_theta_star=False,
        enable_smoothing=False,
        max_iter=500_000,
        layer_constraints=layer_constraints,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
        enable_all_pad_tree=enable_all_pad_tree,
        enable_zone_pours=enable_zone_pours,
        enable_connectivity_verifier=enable_connectivity_verifier,
        # Manufacturing DRC (acid_trap, annular_ring, teardrop,
        # thermal_relief, power_planes, copper_balance, creepage,
        # clearance). This never ran during production routing before
        # 2026-07-25 -- it defaulted to False and nothing set it. See
        # docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md.
        #
        # Reporting-only: dfm_fail_on="none" attaches the
        # ManufacturingReport to the result without raising or changing
        # routing behaviour.
        #
        # DEFAULT IS OFF because the stage does not currently complete on
        # a real board. Enabling it on the temper board (149 footprints,
        # ~3,265 emitted segments, 98 zones) ran 27 minutes at 98% CPU and
        # 9.2 GB RSS without finishing. A stack sample showed pure-Python
        # interpreter work -- float/tuple allocation and division, no
        # numpy or Rust -- i.e. an O(n^2) pairwise geometry loop in
        # verify_clearance. It was never discovered because the stage had
        # never executed. See
        # docs/evidence/2026-07-26-manufacturing-drc-scalability.md.
        #
        # Turning it on by default made every route unusable, which is a
        # worse failure than the check being off. It stays off, but is now
        # switchable and documented rather than silently dead. Restore the
        # default to True once verify_clearance scales.
        enable_manufacturing_drc=enable_manufacturing_drc,
        dfm_fail_on="none",
        sat_conflict_limit=sat_conflict_limit,
        sat_time_limit_ms=sat_time_limit_ms,
        target_nets=normalized_target_nets,
        skip_stage3=skip_stage3,
    )

    # Resolve the net->class-name mapping from the caller's design_rules.
    # Without this, pipeline.run()'s net_class_assignments is empty and
    # get_rules_for_net() can never find a class for any net regardless of
    # how many real NetClassRules exist in net_classes below -- the class
    # lookup needs BOTH the name mapping and the rules dict to resolve
    # anything beyond the flat "Default" fallback.
    net_class_assignments: dict[str, str] = {}
    if design_rules is not None:
        net_class_assignments = dict(getattr(design_rules, "net_class_assignments", {}) or {})

    # R6 (2026-07-23-008): Convert core netclass rules to stage0 format
    # so safety_category survives into pcb.design_rules for the HV/AC
    # forced-segment fail-closed gate.  If _to_stage0_netclass_rules() is
    # later wired into a different injection point (e.g. _parse_nets.py),
    # this block becomes redundant — but it is the correct place today.
    _stage0_net_classes: dict[str, Any] = {}
    if design_rules is not None:
        core_net_classes = getattr(design_rules, "net_classes", None)
        if core_net_classes:
            for class_name, core_rules in core_net_classes.items():
                try:
                    _stage0_net_classes[class_name] = _to_stage0_netclass_rules(
                        core_rules
                    )
                except Exception:
                    logger.warning(
                        "route_pcb: failed to convert core netclass %r to "
                        "stage0 format — safety_category will not survive; "
                        "HV/AC forced-segment gate will not activate for nets "
                        "in this class",
                        class_name,
                        exc_info=True,
                    )

    if placements:
        raw_content = pcb_path.read_text(encoding="utf-8")
        modified_content = _apply_placements_to_pcb(
            raw_content, placements, design_rules=design_rules, rotations=rotations
        )

        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(modified_content)

            # NOTE 2026-06-23: the closure test was using
            # enable_theta_star=True, enable_lazy_theta_star=True,
            # and enable_smoothing=True.  All three are wrong for
            # SM1 measurement on temper.kicad_pcb:
            #   * lazy theta star is a Python A* with no iter cap
            #     and the reroute loop blows up the full-run wall
            #     time to 5+ minutes (15/24 in 18s in the smoke vs
            #     13/24 incomplete after 5 min in the full profile).
            #   * plain theta star is also Python (no iter cap)
            #     and finds fewer nets than plain A* (Numba).
            #   * enable_smoothing=True is broken:
            #     SDFGrid.from_polygons is missing, so the
            #     smoothing step is a silent no-op (or worse).
            # The closure test should use the smoke-equivalent
            # path: plain 2D A* via the Numba kernel, no
            # smoothing.
            #
            # NOTE 2026-06-24: ``max_iter=500_000`` is the
            # path-quality sweet spot on temper.kicad_pcb.  The
            # kernel default of 1M explores further but lands
            # SPI_MOSI on a different tie-break path and the
            # reroute loop can't recover it (95.83% vs 100.0% at
            # 500k).  See
            # docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md
            # for the iter-cap sweet-spot table.
            #
            # NOTE 2026-07-27: that table was measured on a 24-net
            # smoke subset. Re-swept on today's full 96-net
            # production board (docs/evidence/2026-07-27-forced-
            # segment-analysis.md): 500k, 1M, 2M, and 4M all produce
            # the identical 59-net failure count (2M and 4M are
            # byte-identical output), with only *which* specific
            # nets fail churning between 500k and 1M before
            # stabilizing. Raising this value is not a completion
            # lever on the current board -- the remaining forced-
            # segment failures are congestion/placement-limited, not
            # search-budget-limited. 500k remains the right choice
            # (no worse than 8x more compute, and faster).
            result = pipeline.run(
                Path(temp_path),
                net_class_assignments=net_class_assignments,
                net_classes=_stage0_net_classes if _stage0_net_classes else None,
            )
            result.enable_zone_pours = enable_zone_pours
            placed_content = Path(temp_path).read_text(encoding="utf-8")
            routed_content, pad_positions = _write_routes_to_content(
                placed_content,
                result,
                design_rules=design_rules,
            )
            return _build_routing_result(
                result,
                routed_content,
                pad_positions=pad_positions,
                enable_connectivity_verifier=enable_connectivity_verifier,
            )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
    else:
        result = pipeline.run(
            pcb_path,
            net_class_assignments=net_class_assignments,
            net_classes=_stage0_net_classes if _stage0_net_classes else None,
        )
        result.enable_zone_pours = enable_zone_pours
        placed_content = pcb_path.read_text(encoding="utf-8")
        routed_content, pad_positions = _write_routes_to_content(
            placed_content,
            result,
            design_rules=design_rules,
        )
        return _build_routing_result(
            result,
            routed_content,
            pad_positions=pad_positions,
            enable_connectivity_verifier=enable_connectivity_verifier,
        )



def _write_routes_to_content(
    pcb_content: str, result: Any, *, design_rules: Any = None
) -> tuple[str, dict[str, list[tuple[float, float]]]]:
    """Inject routing tracks from RouterV6Pipeline result into KiCad PCB content.

    Extracts successfully routed paths from the pipeline result and writes
    them as ``(segment ...)`` entries into the PCB content. For plane nets
    (zero-length dummy paths) and for missing pins on multi-pin signal nets,
    creates direct connections using pad positions from the parsed PCB.
    """
    from types import SimpleNamespace

    # Single deterministic tstamp sequence shared by every segment/via
    # this call emits (routed paths, vias, and -- via _emit_zone_pours --
    # zone pours and isolated-pad stitch segments). See _next_tstamp.
    tstamp_counter: list[int] = [0]

    pad_positions: dict[str, list[tuple[float, float]]] = {}

    routing_results = getattr(result.stage4, "routing_results", None)
    if routing_results is None:
        return pcb_content, pad_positions

    compiled = getattr(routing_results, "compiled_routes", {})
    tree_compiled = getattr(routing_results, "tree_routes", {})
    partial_tree_compiled = getattr(routing_results, "partial_tree_routes", {})
    if not compiled and not tree_compiled and not partial_tree_compiled:
        return pcb_content, pad_positions

    # U7: fold tree routes into the compiled-routes iteration so the
    # writer emits tree-routed net geometry alongside legacy paths.
    _tree_seen: set[str] = set()
    for net_name, ctr in {**tree_compiled, **partial_tree_compiled}.items():
        if net_name in compiled or net_name in _tree_seen:
            continue
        _tree_seen.add(net_name)
        fake_path = SimpleNamespace(
            path_length=1.0,
            coordinates=[],  # tree routes have no serial coordinates
        )
        compiled[net_name] = SimpleNamespace(
            path=fake_path,
            width_mm=getattr(ctr, "width_mm", 0.2),
            vias=getattr(ctr, "vias", []),
            _tree_route=ctr,
        )

    # Build net name -> net number mapping from the PCB content
    net_name_to_number: dict[str, int] = {}
    for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', pcb_content):
        net_name_to_number[m.group(2)] = int(m.group(1))

    # Collect pad world positions from the parsed PCB data
    pcb = getattr(result, "pcb", None)
    if pcb is not None:
        comp_by_ref = {c.ref: c for c in pcb.components}
        for net in pcb.nets:
            positions: list[tuple[float, float]] = []
            for comp_ref, pin_name in getattr(net, "pins", []):
                comp = comp_by_ref.get(comp_ref)
                if comp is None:
                    continue
                comp_pos = getattr(comp, "initial_position", (0.0, 0.0))
                pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
                if pin is None:
                    positions.append((float(comp_pos[0]), float(comp_pos[1])))
                else:
                    px, py = pin.position
                    positions.append(
                        (float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py))
                    )
            if positions:
                pad_positions[net.name] = positions

    segments: list[str] = []
    for net_name, compiled_route in compiled.items():
        path = getattr(compiled_route, "path", None)
        if path is None:
            continue

        # U7: emit tree-route branch geometry directly.  Each branch's
        # segments are written as independent track segments; sibling
        # branches are never bridged by synthetic copper.
        tree_route = getattr(compiled_route, "_tree_route", None)
        if tree_route is not None:
            tree_width = getattr(compiled_route, "width_mm", 0.2)
            net_num = net_name_to_number.get(net_name, 0)
            # iter_segments() lives on TreeRouteGeometry (yields pairs of
            # (x, y, layer) points across all branches), not on a branch's
            # individual RoutePath/RoutePath3D -- neither has iter_segments.
            for (sx, sy, s_layer), (ex, ey, e_layer) in tree_route.geometry.iter_segments():
                if s_layer != e_layer:
                    # A layer change between consecutive points is a via
                    # crossing, not a same-layer copper run -- KiCad segments
                    # are single-layer. Via emission for tree-routed nets
                    # isn't wired yet (pre-existing gap; the vias loop below
                    # is skipped for this branch by the `continue`), so this
                    # point-pair is dropped rather than drawn incorrectly.
                    continue
                seg_id = _next_tstamp(tstamp_counter)
                segments.append(
                    f"  (segment (start {sx:.4f} {sy:.4f}) (end {ex:.4f} {ey:.4f})"
                    f' (width {tree_width:.4f}) (layer "{s_layer}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
            continue

        path_length = getattr(path, "path_length", 0.0)
        width = getattr(compiled_route, "width_mm", 0.2)
        # Defense-in-depth: never emit a zero/negative-width track (KiCad DRC
        # flags these as track_width violations). getattr's default does not
        # catch a present-but-zero width, so guard explicitly.
        if not width or width <= 0.0:
            width = 0.2
        net_num = net_name_to_number.get(net_name, 0)
        pads = pad_positions.get(net_name, [])

        if path_length > 0 and len(pads) >= 2:
            # Real routed net: extract path coordinates with per-step layer
            path_points: list[tuple[float, float, str]] = []
            path_segs = getattr(path, "segments", None)
            if path_segs:
                for s in path_segs:
                    path_points.append((s[0], s[1], s[2]))
            else:
                coords = getattr(path, "coordinates", None)
                if coords:
                    default_layer = getattr(path, "layer_name", "F.Cu")
                    for c in coords:
                        path_points.append((c[0], c[1], default_layer))

            # Chamfer 90-degree orthogonal turns to reduce grid-staircasing.
            # After collapse, remaining turns are still sharp 90-degree
            # corners from the 0.1 mm A* grid.  Two adjacent traces following
            # similar grid paths have edge-to-edge clearance violations at
            # these corners because the staircase stagger pushes segments
            # closer than the minimum clearance.  Chamfering replaces each
            # orthogonal turn with a 45-degree diagonal, reducing both
            # shorting_items and tracks_crossing DRC violations.
            path_points = _chamfer_path_points(path_points, chamfer_offset=0.1)

            # Write path segments, collapsing consecutive same-direction
            # same-layer steps to avoid A* grid-stepping staircasing.
            # Each individual grid step (0.1mm) emitted as its own
            # (segment ...) creates 8k+ micro-segments that KiCad DRC
            # flags as clearance / shorting / masking violations because
            # adjacent segments from different nets interleave with
            # edge-to-edge gaps under the 0.2mm rule. Only merge
            # consecutive steps that share the same layer -- a layer
            # change always splits the merged chain.
            i = 0
            while i < len(path_points) - 1:
                x1, y1, lyr = path_points[i]
                x2, y2, _l2 = path_points[i + 1]
                dx_prev = x2 - x1
                dy_prev = y2 - y1
                j = i + 2
                while j < len(path_points):
                    xm, ym, _ = path_points[j - 1]
                    xn, yn, lyr_n = path_points[j]
                    dx_cur = xn - xm
                    dy_cur = yn - ym
                    if (
                        abs(dx_cur - dx_prev) < 1e-12
                        and abs(dy_cur - dy_prev) < 1e-12
                        and lyr_n == lyr
                    ):
                        x2, y2 = xn, yn
                        j += 1
                    else:
                        break
                seg_id = _next_tstamp(tstamp_counter)
                segments.append(
                    f"  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})"
                    f' (width {width:.4f}) (layer "{lyr}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
                i = j - 1
        # U5: emit real (via ...) s-expressions for each Via in the compiled route.
        for via in getattr(compiled_route, "vias", []):
            vx, vy = via.position
            segments.append(
                f"  (via (at {vx:.4f} {vy:.4f}) (size {via.diameter:.4f})"
                f' (drill {via.drill:.4f}) (layers "{via.from_layer}" "{via.to_layer}")'
                f' (net {net_num}) (tstamp "{_next_tstamp(tstamp_counter)}"))'
            )

    if getattr(result, "enable_zone_pours", False):
        pcb_content, _ = strip_existing_zones(pcb_content)  # R7: replace, don't append
        _emit_zone_pours(
            pad_positions,
            segments,
            net_name_to_number,
            design_rules=design_rules,
            tstamp_counter=tstamp_counter,
        )

    if not segments:
        return pcb_content, pad_positions

    # Inject segments before the closing ")" of the kicad_pcb s-expression
    segment_block = "\n" + "\n".join(segments) + "\n"
    pcb_content = pcb_content.rstrip()
    if pcb_content.endswith(")"):
        pcb_content = pcb_content[:-1] + segment_block + ")\n"

    return pcb_content, pad_positions


def _build_routing_result(
    result: Any,
    routed_content: str | None = None,
    *,
    pad_positions: dict[str, list[tuple[float, float]]] | None = None,
    enable_connectivity_verifier: bool = False,
) -> RoutingResult:
    """Extract failure data from RouterV6Pipeline result into RoutingResult.

    Pulls failed net names, DRC violations from per-net reports, and
    congestion regions from bottleneck geometry analysis so that the
    FeedbackClassifier can act on real routing failures.
    """
    routing_results = result.stage4.routing_results
    unrouted_nets = list(routing_results.failed_nets)

    # R5: Extract forced-segment net names from compiled routes.
    # Each CompiledRoute.path is the original RoutePath/RoutePath3D which
    # carries forced_segment_count.  (The routed_paths dict lives on
    # PathfindingResult, replaced by compile_routing_results() in Stage 4.)
    # Always empty as of docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md:
    # no net class produces forced_segment_count > 0 anymore.
    forced_segment_nets: list[str] = []
    compiled = getattr(routing_results, "compiled_routes", None)
    if compiled:
        forced_segment_nets = [
            net_name
            for net_name, route in compiled.items()
            if getattr(getattr(route, "path", None), "forced_segment_count", 0) > 0
        ]

    drc_violations: list[DrcViolation] = []
    congestion_regions: list[CongestionRegion] = []

    for report in getattr(routing_results, "net_reports", []):
        # Collect DRC violations from per-net reports
        drc_count = getattr(report, "drc_violations", 0)
        if drc_count > 0:
            drc_violations.append(
                DrcViolation(
                    net_name=getattr(report, "net_name", "unknown"),
                    count=drc_count,
                    message=getattr(report, "message", ""),
                )
            )

        # Collect congestion regions from bottleneck geometry
        bottleneck = getattr(report, "bottleneck", None)
        if bottleneck is not None:
            pair_kind = getattr(bottleneck, "pair_kind", None)
            if pair_kind in ("component_edge", "component_keepout"):
                comps = getattr(bottleneck, "component_pair", ("unknown", "unknown"))
                gap = getattr(bottleneck, "current_gap_mm", 0.0)
                positions = getattr(bottleneck, "positions_mm", ((0.0, 0.0), (0.0, 0.0)))
                congestion_regions.append(
                    CongestionRegion(
                        net_name=getattr(report, "net_name", "unknown"),
                        comp_a=comps[0],
                        comp_b=comps[1],
                        current_distance_mm=gap,
                        positions=positions,
                    )
                )

    # Pull DRC data from manufacturing report if available
    mfg = getattr(result, "manufacturing_report", None)
    if mfg is not None:
        for v in getattr(mfg, "violations", []):
            drc_violations.append(
                DrcViolation(
                    type=getattr(v, "type", "unknown"),
                    message=getattr(v, "message", ""),
                    net_name=getattr(v, "net_name", ""),
                    location=getattr(v, "location", (0.0, 0.0)),
                )
            )

    # U4: post-write connectivity preflight
    connectivity = None
    if enable_connectivity_verifier and routed_content and pad_positions:
        from temper_placer.router_v6.kicad_connectivity import (
            connectivity_preflight,
        )

        connectivity = connectivity_preflight(routed_content, pad_positions)

    return RoutingResult(
        completion_rate=result.completion_rate,
        unrouted_nets=unrouted_nets,
        drc_violations=drc_violations,
        congestion_regions=congestion_regions,
        failure_reports=dict(sorted((getattr(routing_results, "failure_reports", {}) or {}).items())),
        routed_pcb_content=routed_content,
        connectivity=connectivity,
        forced_segment_nets=forced_segment_nets,
    )


# A .kicad_pcb pad's `(at x y angle)` angle is its ABSOLUTE (world)
# orientation -- unlike a .kicad_mod's, it is not an offset added to the
# parent footprint's angle at load time (see _write_board.py::_reorient_pads,
# the kiutils-based precedent for this same rule on a parsed board tree).
# Matches pad shapes across pad kinds actually present in this repo's boards
# (thru_hole/np_thru_hole/smd/connect x circle/rect/oval/roundrect/
# trapezoid/custom): `(pad "<num-or-empty>" <type> <shape> (at X Y [ANGLE])`.
_PAD_AT_RE = re.compile(
    r'(\(pad\s+"[^"]*"\s+\S+\s+\S+\s+\(at\s+[\d.-]+\s+[\d.-]+)(?:\s+([\d.-]+))?(\))'
)


def _reorient_pads_in_footprint_block(block: str, delta_deg: float) -> str:
    """Rewrite every pad's absolute angle in *block* by *delta_deg*.

    Raw-string-content counterpart of ``_write_board.py::_reorient_pads``:
    same rule (pad angle is absolute, not footprint-relative), applied to
    ``.kicad_pcb`` s-expression text instead of a parsed ``kiutils`` tree.
    Each pad's *intrinsic* orientation (its angle relative to its parent, as
    defined by the library footprint) is preserved -- only the absolute
    angle shifts by the footprint's own rotation delta. Skipping this step
    was the root cause of 60 intra-component copper shorts on this board
    (PRs #412/#420/#426); see
    docs/evidence/2026-07-29-intra-component-shorts-root-cause.md.
    """

    def _shift(m: re.Match[str]) -> str:
        old_angle = float(m.group(2)) if m.group(2) else 0.0
        new_angle = (old_angle + delta_deg) % 360.0
        # kiutils/KiCad omit the angle token when it is 0; write it back
        # only when the result really is nonzero, matching _reorient_pads.
        angle_token = "" if new_angle == 0.0 else f" {new_angle:.4f}"
        return f"{m.group(1)}{angle_token}{m.group(3)}"

    return _PAD_AT_RE.sub(_shift, block)


def _apply_placements_to_pcb(
    raw_content: str,
    placements: dict[str, tuple[float, float]],
    design_rules: Any = None,
    rotations: dict[str, float] | None = None,
) -> str:
    """Modify footprint (at X Y [ANGLE]) positions in KiCad PCB raw content.

    ``rotations``, if given, maps component ref -> new absolute footprint
    rotation in degrees (the same convention as
    ``CpSatPlacementResult.rotations[ref] * 90.0``, see cli/__init__.py).
    A ref present in ``placements`` but absent from ``rotations`` (or
    passed with ``rotations=None`` entirely) keeps its existing angle
    byte-for-byte unchanged -- the pre-existing, position-only behavior.
    When a ref's target angle differs from its current one, every pad in
    that footprint is re-oriented by the same delta so pad geometry keeps
    matching where the footprint visually points (see
    ``_reorient_pads_in_footprint_block`` above).
    """
    foot_starts = [m.start() for m in re.finditer(r'\(footprint\s+"[^"]+"\s+\(layer', raw_content)]

    if not foot_starts:
        return raw_content

    result_parts = []
    prev_end = 0

    for i, start in enumerate(foot_starts):
        end = foot_starts[i + 1] if i + 1 < len(foot_starts) else len(raw_content)
        block = raw_content[start:end]

        ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if ref_match:
            ref = ref_match.group(1)
            if ref in placements:
                x, y = placements[ref]
                target_angle = rotations.get(ref) if rotations else None

                if target_angle is None:
                    # No solved rotation for this ref: preserve its existing
                    # angle exactly, unchanged from the pre-fix behavior.
                    block = re.sub(
                        r"(\(at\s+)[\d.-]+\s+[\d.-]+(\s*[\d.-]*\s*\))",
                        rf"\g<1>{x:.4f} {y:.4f}\2",
                        block,
                        count=1,
                    )
                else:
                    fp_at_match = re.search(
                        r"\(at\s+[\d.-]+\s+[\d.-]+(?:\s+([\d.-]+))?\s*\)", block
                    )
                    old_angle = 0.0
                    if fp_at_match and fp_at_match.group(1):
                        old_angle = float(fp_at_match.group(1))

                    new_angle = target_angle % 360.0
                    angle_token = "" if new_angle == 0.0 else f" {new_angle:.4f}"
                    block = re.sub(
                        r"(\(at\s+)[\d.-]+\s+[\d.-]+(\s*[\d.-]*\s*\))",
                        rf"\g<1>{x:.4f} {y:.4f}{angle_token})",
                        block,
                        count=1,
                    )

                    delta = target_angle - old_angle
                    if delta % 360.0 != 0.0:
                        block = _reorient_pads_in_footprint_block(block, delta)

        result_parts.append(raw_content[prev_end:start])
        result_parts.append(block)
        prev_end = end

    result_parts.append(raw_content[prev_end:])
    raw_content = "".join(result_parts)

    if design_rules is not None and getattr(design_rules, "net_classes", None):
        nc_forms = []
        for nc_name, nc_rules in sorted(design_rules.net_classes.items()):
            nc_forms.append(
                f'  (net_class "{nc_name}" "Auto-generated from netclass_rules.yaml"'
                f" (clearance {nc_rules.clearance})"
                f" (trace_width {nc_rules.trace_width})"
                f" (via_dia {nc_rules.via_diameter})"
                f" (via_drill {nc_rules.via_drill}))"
            )
        nc_block = "\n" + "\n".join(nc_forms) + "\n"

        setup_match = re.search(r"\(setup\b", raw_content)
        if setup_match:
            depth = 0
            i = setup_match.start()
            while i < len(raw_content):
                if raw_content[i] == "(":
                    depth += 1
                elif raw_content[i] == ")":
                    depth -= 1
                    if depth == 0:
                        raw_content = raw_content[: i + 1] + nc_block + raw_content[i + 1 :]
                        break
                i += 1

    return raw_content
