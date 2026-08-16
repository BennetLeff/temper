"""route_pcb entry point and conversion/writing functions for the router_v6 adapter."""

from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import temper_orchestration as _to

from temper_placer.geometry.kicad_transform import rotate_local_to_world
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

# Phase E batch E6 (Rust Orchestration Engine plan 2026-08-09-001): the
# portable adapter orchestration — ``_next_tstamp`` (the deterministic UUIDv5
# tstamp sequence), ``_to_stage0_netclass_rules`` (the netclass SSOT->stage0
# conversion boundary), ``_write_routes_to_content``'s segment/via
# emission core (the collinear-step merge + ``(segment ...)``/``(via ...)``
# rendering with the shared tstamp counter) and ``_summarize_batch_results``
# (the ``batch_results`` -> summary-dict reduction) — moved to
# ``temper-orchestration``'s ``pipeline_route.rs``; this module keeps its
# public API as a thin FFI delegation. What stays Python (the E6 boundary):
# ``route_pcb`` / ``_apply_placements_to_pcb`` /
# ``_reorient_pads_in_footprint_block`` — the pipeline-invocation glue and
# the ``re``-based s-expression text rewriting
# (no regex engine in the crate; the PAD-AT rewrite is a Perl-5-flavoured
# regex state machine), argued in VERIFICATION.md. The chamfer
# (``_chamfer_path_points``), the tree-route folding
# (``TreeRouteGeometry.iter_segments``), the zone-pour emission
# (``_emit_zone_pours``), the net-number regex parsing, the s-expression
# injection and the ``connectivity_preflight`` call-back stay Python
# single-source; the Rust core is driven per compiled route so the shared
# tstamp counter's increment order stays byte-identical. The oracle is pinned
# verbatim as ``tests/router_v6/_adapter_convert_py_oracle.py`` (content-hash
# registered in ``scripts/oracle_hashes.json``); ``_summarize_batch_results``'s
# oracle is pinned inline in
# ``tests/router_v6/test_adapter_convert_rust_differential.py``.
#
# Unit U-H (E6 follow-on): the residual deterministic wire-format
# construction moved to ``pipeline_route.rs`` next to the E6 kernels —
# ``_write_routes_to_content``'s pad-positions block
# (``run_collect_pad_positions``, the board conversion whose per-net length
# feeds the emission core / zone pours / connectivity preflight), the
# per-route payload marshalling (``run_build_route_payload`` — the
# path_length/width reads with the width snap, the segments/coordinates
# duck-typed extraction, the chamfer CALL-BACK and the via extraction, one
# payload per compiled route) and ``_build_routing_result``'s
# failure-extraction assembly (``run_build_routing_result`` — unrouted /
# forced-segment nets, DRC violations, congestion regions, topology-solved
# nets returned as plain data; this shim wraps the ``DrcViolation`` /
# ``CongestionRegion`` dataclasses, which stay Python single-source, and
# keeps the ``connectivity_preflight`` call-back). The pre-migration bodies
# are pinned VERBATIM as inline oracles in
# ``tests/router_v6/test_adapter_convert_marshal_rust_differential.py``
# (content-addressed by per-body SHA-256).
#
# Residual decision record (R3, see docs/wave4-discipline-contract.md §3):
# - ``_reorient_pads_in_footprint_block``: product-runtime → JUSTIFIED-KEEP —
#   a CPython-``re`` s-expression rewrite (B9 divergence class: the crate has
#   no Perl-5 regex engine and Rust's `regex` is RE2-style), whose float
#   ``% 360.0`` / ``float()`` parse / ``:.4f`` render would all still round-trip
#   through CPython -- a net-zero win with real divergence risk. Remedy named
#   for re-openability: a hand-rolled pad-AT parser (or a KiCad s-expr emitter
#   crate) IF the footprint-writing path is ever reworked. (LOC: ~21; consumers:
#   1 — ``_apply_placements_to_pcb``; deps: re; churn: low)
# - ``_apply_placements_to_pcb``: product-runtime → JUSTIFIED-KEEP — regex-based
#   footprint text surgery + the rotation/netclass-form-injection orchestration
#   (``rotate_local_to_world`` already Rust-backed; the ``re`` walks and the
#   duck-typed ``design_rules.net_classes`` read stay Python). (LOC: ~224;
#   consumers: 1 — ``route_pcb``, plus 5 test files; deps: re, math,
#   kicad_transform; churn: high — 2026-08-11 board-origin fix)
# - ``route_pcb`` / ``_write_routes_to_content`` (remaining body):
#   product-runtime → JUSTIFIED-KEEP — pipeline invocation,
#   ``tempfile``/subprocess boundary, duck-typed result walks, and the Python
#   single-source callbacks (``_chamfer_path_points``, ``_emit_zone_pours``,
#   ``strip_existing_zones``, ``connectivity_preflight``) plus the
#   ``re``-based net-number parsing and the s-expression injection.

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

# R1b: Netclass fields with no stage0 equivalent, warned on when explicitly
# set (marshalled into ``run_to_stage0_netclass_rules`` by the E6 shim --
# the table stays the Python SSOT).
_UNREPRESENTED_WARN = (
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

    Phase E E6: the UUIDv5 computation moved to
    ``temper_orchestration.pipeline_route::run_next_tstamp`` (RFC 1321 MD5
    hand-rolled, byte-pinned against CPython ``uuid.uuid5`` by the
    differential); the shared counter list is mutated in place exactly like
    the oracle so the segment/via/zone-pour emission order keeps a single
    sequence.
    """
    return _to.run_next_tstamp(counter)


def _to_stage0_netclass_rules(rules: Any) -> Any:
    """Convert a core NetClassRules (or duck-type-compatible shape) into a
    stage0 NetClassRules dataclass.

    This adapter is the single conversion boundary between the YAML SSOT
    representation (``core.netclass_rules_gen.NetClassRules``) and the A*
    engine's internal representation (``stage0_data.NetClassRules``).

    Explicit attribute checking replaces the previous ``getattr(rules, attr,
    default)`` duck-type approach: unrecognized shapes raise ``TypeError``
    rather than silently returning defaults.

    Phase E E6: the conversion orchestration moved to
    ``temper_orchestration.pipeline_route::run_to_stage0_netclass_rules``
    (the explicit alias checking, the TypeError message rendered through
    CPython ``str.format``, the unrepresented-field warnings through THIS
    module's logger); the ``_UNREPRESENTED_WARN`` table stays the Python SSOT
    and is marshalled once per call. This shim wraps the returned values in
    the ``stage0_data.NetClassRules`` dataclass (which stays Python
    single-source).
    """
    from temper_placer.router_v6.stage0_data import NetClassRules as Stage0NetClassRules

    result = _to.run_to_stage0_netclass_rules(rules, _UNREPRESENTED_WARN)
    (
        name,
        clearance_mm,
        trace_width_mm,
        via_diameter_mm,
        via_drill_mm,
        current_rating_amps,
        safety_category,
        creepage_mm,
    ) = result
    return Stage0NetClassRules(
        name=name,
        clearance_mm=clearance_mm,
        trace_width_mm=trace_width_mm,
        via_diameter_mm=via_diameter_mm,
        via_drill_mm=via_drill_mm,
        current_rating_amps=current_rating_amps,
        safety_category=safety_category,
        creepage_mm=creepage_mm,
    )


def route_pcb(
    parsed: ParsedPcbLike | Any,
    placements: dict[str, tuple[float, float]],
    design_rules: Any = None,
    thermal_flat: Any = None,
    thermal_weight: float = 0.0,
    enable_all_pad_tree: bool = True,
    enable_zone_pours: bool = True,
    enable_connectivity_verifier: bool = False,
    enable_geographic_pruning: bool = False,
    enable_manufacturing_drc: bool = False,
    sat_conflict_limit: int | None = 20_000,
    sat_time_limit_ms: int | None = None,
    rotations: dict[str, float] | None = None,
    components: list | None = None,
    enable_net_batching: bool = False,
    net_batch_size: int = 10,
    max_sat_nets: int | None = None,
    enable_nlayer_astar_spike: bool = False,
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
        components: Optional list of ``Component`` objects (the netlist
            ``solve_placement`` was called with). Threaded straight through
            to ``_apply_placements_to_pcb`` so it can invert each
            footprint's pad-centroid offset (``_center_offset_x/y``) back
            to a KiCad anchor -- see its docstring. Required alongside
            ``rotations`` for any footprint whose pads are not centred on
            its raw anchor (e.g. an asymmetric TO-247); omitting it keeps
            prior behavior unchanged.
        thermal_flat: U9 optional (N,) float32 thermal cost field from
            the previous round's field.  Threaded to A* kernel.
        thermal_weight: U9 multiplier on per-cell thermal cost
            (from CostFieldInput.weight).  0.0 = field-off.
        enable_all_pad_tree: Expand the Stage 4 A* waypoint chain to visit
            every terminal of multi-pad (N>2) nets, not just the SAT-derived
            channel waypoints -- without it, pad centres missing from the
            chain are never appended and A* never routes to them (measured
            2026-08-15: +15V_LS's C23.1+U7.2 were visited, U6.11 was not).
            Default True (callers that want the old SAT-waypoints-only
            behaviour can pass False).
        enable_zone_pours: Emit filled-copper zone geometry for power/
            ground/HV nets (per netclass SSOT).  Default True -- zones
            are enabled by default for multi-layer power/ground routing.
        enable_connectivity_verifier: Run post-write connectivity
            preflight via verify_net_connectivity (default False).
        enable_geographic_pruning: Enable geographic pruning of the
            Stage 3 SAT model (U3 of plan
            2026-08-07-001-feat-router-encoding-pruning-plan.md).
            Default False -- behavior unchanged. When True,
            NetChannelVar and ViaVar variables are created only for
            edges/nodes within max(K * pin_span, M_min) of each net's
            pins, reducing CNF variable/clause count. See
            RouterV6Pipeline.__init__'s docstring for the full
            rationale. This worktree's branch point predates that U3
            merge landing on ``main``; ported forward here (parameter +
            wiring below) because this task needs to compare route_pcb()
            on the production board with and without it once the
            plane-condemnation fix makes the model non-empty.
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
        enable_net_batching: `#871` net-batching prototype. Solve Stage
            3's SAT model in batches of ``net_batch_size`` nets, with
            each batch's channel capacity reduced by what earlier
            batches already consumed, instead of one monolithic model
            covering every net. Default False (behavior unchanged). See
            ``router_v6/net_batching.py`` for the full design and
            ``RouterV6Pipeline.__init__``'s docstring for interaction
            with ``enable_bundling``/``max_sat_nets``.
        net_batch_size: Nets per Stage 3 SAT batch when
            ``enable_net_batching=True``. Default 10.
        max_sat_nets: Selective-SAT cap: encode only the top-N nets
            (ascending pin count) into the Stage 3 model; every other net
            falls through to Stage 4's unguided A* fallback. Default None
            -- encode every net. Caps the |nets| x |edges| Sinz CNF term
            (the 2026-08-15 Stage 3 memory-blowup fix, wired through
            ``RouterV6Pipeline(max_sat_nets=...)`` ->
            ``ModelBuilder(net_filter=...)``). Ignored when
            ``enable_net_batching`` is set (batching takes priority in
            ``_run_stage3``).
        enable_nlayer_astar_spike: Opt into the N-layer, via-aware A*
            pathfinding spike prototype (``_astar_nlayer.py``) instead of
            the production 2-layer-capped path. Default False -- see
            ``RouterV6Pipeline.__init__``'s docstring for the full
            rationale.

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
        # Ported forward from a later point on `main` than this worktree's
        # branch point (see the docstring above) -- ConstraintModel.build()
        # only honors this when it is actually threaded through to
        # RouterV6Pipeline; ModelBuilder itself already defaults it False,
        # so leaving this unwired would make enable_geographic_pruning=True
        # a silent no-op at this call site specifically.
        enable_geographic_pruning=enable_geographic_pruning,
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
        enable_net_batching=enable_net_batching,
        net_batch_size=net_batch_size,
        max_sat_nets=max_sat_nets,
        enable_nlayer_astar_spike=enable_nlayer_astar_spike,
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
            raw_content,
            placements,
            design_rules=design_rules,
            rotations=rotations,
            components=components,
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
            #     and finds fewer nets than plain A* (Rust).
            #   * enable_smoothing=True is broken:
            #     SDFGrid.from_polygons is missing, so the
            #     smoothing step is a silent no-op (or worse).
            # The closure test should use the smoke-equivalent
            # path: plain 2D A* via the Rust kernel, no
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
        # U-H: the board->pad_positions conversion moved to
        # temper_orchestration.pipeline_route::run_collect_pad_positions (the
        # comp_by_ref dict comprehension, the getattr(net, "pins", []) walk,
        # the conditional comp.get_pin call and the float position sums --
        # duck-typed through CPython exactly like the oracle). The dict wrap
        # preserves first-seen net order; a net with no resolvable pin
        # positions stays absent.
        pad_positions = dict(_to.run_collect_pad_positions(pcb))

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
                if s_layer != e_layer or (sx == ex and sy == ey):
                    # A layer change between consecutive points is a via
                    # crossing, not a same-layer copper run -- KiCad segments
                    # are single-layer. Via emission for tree-routed nets
                    # isn't wired yet (pre-existing gap; the vias loop below
                    # is skipped for this branch by the `continue`), so this
                    # point-pair is dropped rather than drawn incorrectly.
                    # Coincident points are dropped for the same reason as in
                    # the path branch below: a start == end track is copper
                    # joining a node to itself, carrying no connectivity but
                    # leaving DRC's tracks_crossing test without a direction.
                    continue
                seg_id = _next_tstamp(tstamp_counter)
                segments.append(
                    f"  (segment (start {sx:.4f} {sy:.4f}) (end {ex:.4f} {ey:.4f})"
                    f' (width {tree_width:.4f}) (layer "{s_layer}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
            continue

        # Phase E E6: the chamfer (`_chamfer_path_points`) stays Python
        # single-source; the collinear-step merge and the (segment ...)/
        # (via ...) rendering move to
        # temper_orchestration.run_write_route_segments (one payload per
        # compiled route so the shared tstamp counter's increment order
        # relative to the tree branch above stays byte-identical).
        #
        # U-H: the per-route payload marshalling itself (the path_length /
        # width reads with the `not width or width <= 0.0` snap, the
        # segments/coordinates duck-typed extraction, the chamfer CALL-BACK
        # and the via extraction) moved to
        # temper_orchestration.pipeline_route::run_build_route_payload --
        # the deterministic route->wire-format conversion that feeds the
        # emission core; the Rust core applies the
        # `path_length > 0 and len(pads) >= 2` guard itself, exactly like
        # the oracle.
        net_num = net_name_to_number.get(net_name, 0)
        pads = pad_positions.get(net_name, [])

        segments.extend(
            _to.run_write_route_segments(
                [_to.run_build_route_payload(path, compiled_route, net_name, net_num, len(pads))],
                tstamp_counter,
            )
        )

    if getattr(result, "enable_zone_pours", False):
        pcb_content, _ = strip_existing_zones(pcb_content)  # R7: replace, don't append
        _emit_zone_pours(
            pad_positions,
            segments,
            net_name_to_number,
            design_rules=design_rules,
            tstamp_counter=tstamp_counter,
            pcb=pcb,
        )

        # M4: gnd's dedicated In1.Cu ground plane. gnd -- the board's
        # largest net (88 pads) -- is mapped to the "Power" netclass
        # (kicad_pro does not declare a "GND" class; see design_rules.py's
        # gnd entry), and Power declares no routing_strategy, so
        # _zone_layers_for_net("gnd") == [] and the F.Cu/B.Cu pour pass
        # above never gives it copper (measured before this: zero copper
        # on gnd). router_v6/_ground_plane.py emits its pour + HV/SELV
        # keepout + drop vias + MST backbone on In1.Cu; it was a
        # standalone spike (scripts/generate_ground_plane.py) with no
        # production caller until being wired in here. The blocks are
        # appended AFTER the R7 strip + pour pass above so the In1.Cu
        # zones survive, and tstamp_counter is threaded so the plane's
        # tstamps continue this run's deterministic sequence.
        gnd_source = getattr(pcb, "source_path", None) if pcb is not None else None
        # Only boards that actually declare a gnd net get the plane --
        # synthetic fixtures without one are skipped (the generator itself
        # raises ValueError for a gnd-less board; that is the right
        # discipline for the standalone script, wrong for production
        # routing of arbitrary input boards).
        if gnd_source is not None and "gnd" in net_name_to_number:
            from temper_placer.router_v6._ground_plane import (
                generate_ground_plane_blocks,
            )

            gnd_blocks, _gnd_report = generate_ground_plane_blocks(
                Path(gnd_source),
                tstamp_counter=tstamp_counter,
            )
            segments.extend(gnd_blocks)

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

    U-H: the failure-extraction assembly moved to
    ``temper_orchestration.pipeline_route::run_build_routing_result`` (the
    duck-typed walk over ``stage4.routing_results`` / ``net_reports`` /
    ``manufacturing_report`` / ``stage3.topology_graph`` -- unrouted nets,
    forced-segment nets, DRC violations, congestion regions, topology-solved
    nets -- returned as plain data). This shim wraps the returned tuples in
    the ``DrcViolation`` / ``CongestionRegion`` dataclasses (which stay
    Python single-source, the D4 ``StageDRCFailure`` precedent) and keeps the
    ``connectivity_preflight`` call-back Python.
    """
    (
        completion_rate,
        unrouted_nets,
        forced_segment_nets,
        drc_violations,
        congestion_regions,
        topology_solved_nets,
    ) = _to.run_build_routing_result(result)

    drc_violations = [
        DrcViolation(net_name=n, message=m, location=loc, count=c, type=t)
        for (n, m, loc, c, t) in drc_violations
    ]
    congestion_regions = [
        CongestionRegion(
            net_name=n,
            comp_a=a,
            comp_b=b,
            current_distance_mm=d,
            positions=(pa, pb),
        )
        for (n, a, b, d, pa, pb) in congestion_regions
    ]

    # U4: post-write connectivity preflight
    connectivity = None
    if enable_connectivity_verifier and routed_content and pad_positions:
        from temper_placer.router_v6.kicad_connectivity import (
            connectivity_preflight,
        )

        connectivity = connectivity_preflight(routed_content, pad_positions)

    # NetRouteResult (2026-08-16): Rust-verified per-net verdicts over the
    # EMITTED content, ALWAYS on -- "connected" is only reachable through
    # NetRouteResult::verify_continuity, whose Connected variant cannot be
    # fabricated (private VerifiedRoute fields). This is the router-side
    # fake-completion fix: the A* "path found" claim is no longer the
    # completion claim. The legacy connectivity_preflight above stays
    # flag-gated (differential-pinned); this is the authoritative verdict.
    net_route_results: dict[str, Any] | None = None
    if routed_content:
        try:
            from temper_placer.router_v6.kicad_connectivity import (
                net_route_result_preflight,
            )

            net_route_results = net_route_result_preflight(routed_content)
        except Exception:
            # Fail open with a LOUD non-result (None), never a fabricated
            # "connected": a caller that sees None knows the verdicts are
            # missing; a caller that saw {} would read it as "all failed".
            logger.warning(
                "route_pcb: NetRouteResult preflight failed to run — no "
                "per-net verified verdicts will be reported for this route",
                exc_info=True,
            )
            net_route_results = None

    return RoutingResult(
        completion_rate=completion_rate,
        unrouted_nets=unrouted_nets,
        drc_violations=drc_violations,
        congestion_regions=congestion_regions,
        routed_pcb_content=routed_content,
        connectivity=connectivity,
        forced_segment_nets=forced_segment_nets,
        topology_solved_nets=topology_solved_nets,
        net_batch_summary=_summarize_batch_results(getattr(result, "batch_results", None)),
        net_route_results=net_route_results,
    )


def _summarize_batch_results(batch_results: list[Any] | None) -> dict[str, Any]:
    """Reduce ``RouterV6Result.batch_results`` (net_batching.NetBatchResult,
    one per batch or singleton retry attempt) to a small, always-printable
    summary -- see ``RoutingResult.net_batch_summary``'s docstring for why
    this needs to exist at all: the per-batch records already carry
    ``batch_crashed``/``crash_reason`` (net_batching.py's own "Crash vs.
    UNSAT, made distinguishable by construction" mechanism), but nothing
    read them by default before this function existed.

    Returns ``{}`` (falsy, easy for a caller to skip) when net-batching
    was not used (``batch_results`` empty/None) -- distinct from a
    populated dict with zero crashes, so a caller can tell "net-batching
    off" from "net-batching on, nothing degraded."

    Phase E E6 follow-on: the reduction moved to
    ``temper_orchestration.pipeline_route::run_summarize_batch_results`` (the
    shim passes the ``batch_results`` list itself; the Rust core walks the
    duck-typed attributes through CPython ``getattr`` and the
    ``"timed out" in ...`` substring test through ``str.__contains__`` so the
    summary stays bit-identical). The pre-migration body is pinned verbatim
    as the inline ``_oracle_summarize_batch_results`` in
    ``tests/router_v6/test_adapter_convert_rust_differential.py``
    (content-addressed by its body SHA-256).
    """
    return _to.run_summarize_batch_results(batch_results)


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
    components: list | None = None,
    board_origin: tuple[float, float] = (0.0, 0.0),
) -> str:
    """Modify footprint (at X Y [ANGLE]) positions in KiCad PCB raw content.

    ``board_origin``: (x, y) mm offset ADDED to every entry in *placements*
    before it is written. ``placements`` is normally produced by solving
    against ``parse_kicad_pcb(..., normalize=True)`` output (the default),
    which subtracts the board's own Edge.Cuts origin (``board.origin`` --
    (20, 20) mm on the real ``pcb/temper.kicad_pcb``, not (0, 0)) from every
    parsed coordinate. ``raw_content``'s own ``(at X Y)`` fields are always
    in ABSOLUTE file coordinates. Omitting this (the previous, sole
    behavior -- default keeps every existing caller byte-for-byte
    unchanged) silently writes every placed footprint ~board_origin mm off
    from the real outline -- caught by ``scripts/check_board_containment.py``,
    which the self-consistency round-trip oracle
    (``validation.placement_roundtrip.check_placement_roundtrip``) does not
    cover (it re-derives its own "expected" geometry from the same,
    already-wrong positions dict rather than independently from Edge.Cuts).
    See docs/evidence/2026-08-11-board-origin-write-path-fix.md.

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

    ``components``, if given, is the ``Component`` list the placements were
    *solved* against (the same object ``solve_placement`` was called with).
    ``placements[ref]`` is CP-SAT's box-CENTRE coordinate -- for a footprint
    whose pad centroid does not coincide with its raw KiCad anchor
    (``Component.attributes["_center_offset_x/y"]`` != 0, e.g. an
    asymmetric TO-247), the anchor this function writes into ``(at X Y)``
    must be the centre minus that offset, rotated (KiCad's actual,
    clockwise convention -- see the inline comment below) by whichever
    rotation the centre was actually computed at (``rotations.get(ref)``
    when a solved rotation was supplied, else the footprint's own existing
    angle) -- otherwise every pad in the footprint is written up to
    ``2 * center_offset`` mm away from where CP-SAT verified it to be
    sound, silently reopening the exact clearance/overlap gap the
    box-containment proof in ``domain_clearance.py`` depends on. Same
    correction as ``io/_write_board.py::write_placements_to_pcb`` (the
    write path ``pcb/temper.kicad_pcb`` ships through) and
    ``io/_parse_modules.py``'s read-side ``rotated_cx``/``rotated_cy`` --
    both were carrying the wrong rotation sign until this change; see
    docs/evidence/2026-07-30-generic-separation-writer-frame-fix.md.
    Omitting ``components`` (the default) keeps prior behavior byte-for-byte
    identical -- callers that never pass it (nothing else in this codebase
    besides the golden-board regression gate did, until this was wired in)
    are unaffected.
    """
    # The footprint header's own s-expression fields between the quoted
    # footprint name and `(layer ...)` are not fixed: newer KiCad exports
    # (kicad-cli 10.0.5, e.g. the real, committed ``pcb/temper.kicad_pcb``,
    # regenerated 2026-08-08) insert `(version NNNNNNNN) (generator "...")`
    # there, while the older ``power_pcb_dataset/corpus/temper/temper.kicad_pcb``
    # golden-test fixture (last touched 2026-07-08) has neither. A regex
    # requiring `(layer` immediately after the name (no tolerance for those
    # optional fields) matches 0 footprints on the real board -- silently, via
    # this function's own empty-``foot_starts`` early return below -- so a
    # caller writing solved placements onto the real board got back its input
    # completely byte-unchanged, with no exception and no visible signal
    # anything had gone wrong. Found 2026-08-11 while wiring
    # docs/evidence/2026-08-11-pumpkin-golden-test-spike.md's real-board
    # golden test: the round-trip oracle
    # (``validation.placement_roundtrip.check_placement_roundtrip``) caught it
    # immediately (1033 mismatches across all 169 components -- this function
    # had touched none of them), which is exactly the class of silent-no-op
    # bug that oracle exists to catch (see this file's own U3 rotation-drop
    # precedent, docs/evidence/2026-07-30-placement-writer-rotation.md). The
    # `(?:\s*\([^()]*\))*` clause below tolerates any number of such flat
    # (non-nested-paren) fields in either order, and is a no-op change for the
    # 33-component fixture (still 33/33 matches, confirmed directly). This
    # bug is orthogonal to which solver produced the placements being
    # written -- OR-Tools output would hit it identically; nothing before
    # this fix had ever exercised this function against the real board's
    # newer export format, since neither `test_golden_board_drc_regression`
    # (fixture only) nor `test_production_board_drc_regression`/
    # `test_production_board_routing_drc_regression` (real board, but DRC the
    # committed board or `route_pcb()`'s output -- neither calls this
    # function) had a reason to.
    foot_starts = [
        m.start()
        for m in re.finditer(r'\(footprint\s+"[^"]+"(?:\s*\([^()]*\))*\s*\(layer', raw_content)
    ]

    if not foot_starts:
        return raw_content

    center_offsets: dict[str, tuple[float, float]] = {}
    if components:
        for comp in components:
            attrs = getattr(comp, "attributes", None)
            if not attrs:
                continue
            cx = float(attrs.get("_center_offset_x", "0"))
            cy = float(attrs.get("_center_offset_y", "0"))
            if cx != 0.0 or cy != 0.0:
                center_offsets[getattr(comp, "ref", "")] = (cx, cy)

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
                x += board_origin[0]
                y += board_origin[1]
                target_angle = rotations.get(ref) if rotations else None

                fp_at_match = re.search(
                    r"\(at\s+[\d.-]+\s+[\d.-]+(?:\s+([\d.-]+))?\s*\)", block
                )
                old_angle = 0.0
                if fp_at_match and fp_at_match.group(1):
                    old_angle = float(fp_at_match.group(1))

                if ref in center_offsets:
                    # The centre was computed at whichever rotation CP-SAT
                    # actually chose (target_angle); if this call wasn't
                    # given a solved rotation for this ref, the centre must
                    # have been computed at its pre-existing angle instead
                    # (no rotation change), so fall back to old_angle.
                    #
                    # Rotation sign: a KiCad footprint's `(at X Y ANGLE)`
                    # rotates each pad's stored LOCAL (unrotated) offset by
                    # ANGLE *clockwise* to get its absolute board position --
                    # i.e. `abs = anchor + R(-ANGLE)` in the standard
                    # (CCW-positive) trig convention, not `R(+ANGLE)`.
                    # Verified directly against ``pcbnew`` (KiCad's own
                    # placement engine, not kiutils or a re-derivation): a
                    # 2-pad footprint at a non-axis-aligned angle (37 deg)
                    # with an off-axis local pad offset (10, 4) places that
                    # pad at (10.393615, -2.823608) -- the R(-ANGLE)
                    # prediction to 6 decimal places; the R(+ANGLE)
                    # (standard-CCW) prediction, (5.579095, 9.212693), is a
                    # different point entirely. Using the standard-CCW sign
                    # here (as this function's first cut did, and as
                    # ``io/_write_board.py::write_placements_to_pcb`` and
                    # ``io/_parse_modules.py``'s ``rotated_cx``/``rotated_cy``
                    # did before this same change corrected them too)
                    # silently re-offsets every pad of a rotated,
                    # off-centroid footprint by up to ``2 * |center_offset|``
                    # -- exactly what turned Q1/Q2's real, sound clearance
                    # into a measured copper short here. See
                    # docs/evidence/2026-07-30-generic-separation-writer-frame-fix.md.
                    cx, cy = center_offsets[ref]
                    rot_rad = math.radians(target_angle if target_angle is not None else old_angle)
                    rotated_cx, rotated_cy = rotate_local_to_world(cx, cy, rot_rad)
                    x -= rotated_cx
                    y -= rotated_cy

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
