"""In2.Cu power-island generation for the ``+3V3``/``vcc``/``+15V``/
``V_BUS_SENSE`` rails (feat/in2cu-power-islands).

**Why this module exists.** ``docs/evidence/2026-08-11-keepout-before-pour-spike.md``
(#1022/#1033) traced why ``pcb/temper.kicad_pcb`` declares ``In1.Cu``/
``In2.Cu`` as power-plane layers (commit ``c4956df66``) but both are
completely empty: (1) the Rust board parser
(``packages/temper-design-bundle/src/parse_engine.rs``) reads a layer's
*name* and discards its declared *role* token, so nothing downstream can
key off "this is a power-plane layer"; and (2)
``router_v6/_zone_pour_stitch.py::_zone_layers_for_net`` -- the only place
in the production ``route_pcb()`` path that emits ``(zone ...)``
geometry -- hardcoded its return value to ``["F.Cu", "B.Cu"]`` for every
zone-eligible net, so no code path in ``router_v6`` could ever emit a
zone on an inner layer at all. #1022/#1033 fixed cause (2) narrowly for
``In1.Cu``/``gnd`` by bypassing ``_zone_layers_for_net`` entirely (a
dedicated generator, ``_ground_plane.py``, calling the same zone-emission
primitives directly). This module is the ``In2.Cu`` counterpart, and
**does the same thing for the same reason, not the reason originally
proposed** -- see the course-correction below before reading further.

**Course correction on how this module reaches ``_zone_layers_for_net``.**
This task's own brief suggested driving inner-layer eligibility from
``NetClassRules.routing_strategy`` -- "the ``GND``/``Power`` classes carry
``routing_strategy: plane_preferred`` ... that is probably the right
signal" -- mirroring the paired fix ``design_rules.py``'s ``GND`` entry
and ``_zone_layers_for_net``'s ``nc_name == "GND"`` branch already got
(R3/R4, docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md).
**Measured, not assumed: this premise is false for ``Power`` on this
board today.** ``TEMPER_NET_CLASSES["Power"].routing_strategy`` is
``None`` (the dataclass default), not ``"plane_preferred"`` -- and
setting it to match GND's fix was prototyped here and reverted, because
doing so does not close an accidental drift the way GND's fix did; it
**reverts an already-landed, evidence-corroborated, actively-tested
decision that Power stays trace-only.** That decision is R1/R7 of the
SAME plan document GND's own fix comes from:

- R1: "No net in ``Power`` or ``GateDrive`` gets a default pour: ``+3V3``,
  ``vcc``, ``+15V``, ``+15V_LS``, ``V_BUS_SENSE`` ... route as traces
  only," corroborated three independent ways --
  ``docs/hardware/TRACE_WIDTH_CALCULATIONS.md`` SS3.4/3.6-3.8 gives each of
  these nets a trace-width spec with local decoupling, never a pour spec;
  ``packages/temper-placer/configs/temper_constraints.yaml`` (a
  human-authored, independent net-class table) declares
  ``Power: routing_strategy: "wide_trace"``, not a plane tier at all; and
  ``docs/evidence/2026-07-28-pour-strategy-audit.md`` Task 1 independently
  reached DELETE (not pour) for all nine Power/GateDrive nets after
  checking real current budgets.
- R7: an explicit regression test,
  ``tests/router_v6/test_adapter.py::TestZoneLayersForNet.test_power_class_is_not_zone_eligible``,
  asserts ``_zone_layers_for_net("+3V3") == []`` (and the same for
  ``vcc``/``+15V``/``V_BUS_SENSE``) by name, specifically so a regression
  re-granting Power a pour would fail loudly instead of passing silently.
  Roughly a dozen other fixtures across the same test file were
  deliberately rewritten 2026-07-28 and again 2026-07-30 to stop using
  ``vcc``/``+3V3`` as "zone-eligible" test data, for the same reason.

Flipping ``Power.routing_strategy`` would not add an In2.Cu option
alongside the existing trace-only behavior -- it would silently revert
R1/R7 for every production ``route_pcb()`` call, re-granting these four
rails an *outer-layer* (F.Cu/B.Cu) pour too, which is exactly the
regression R7's test exists to catch. ``deterministic/stages/power_plane.py``'s
own docstring (this task's other cited source for "Power belongs on
In2.Cu") is not independent corroboration of the opposite conclusion --
it is a design note in a pipeline no production entry point invokes
(see ``_ground_plane.py``'s own module docstring, S:2e), naming nets
(``+5V``, ``VCC_BOOT``) that do not exist on the compiled board at all,
which is itself a sign of drift rather than a currently-validated
intent to weigh against R1's three live, cross-checked sources.

Given that, ``_zone_layers_for_net`` is **left completely unchanged** by
this task (see that function's own updated docstring for the pointer
back here). This module instead follows the precedent ``_ground_plane.py``
already set for ``In1.Cu``/``gnd``: a standalone generator that calls
the zone-emission primitives (``zone_emission.compute_zones_for_net``/
``emit_zone_s_expr``) directly, never going through ``_zone_layers_for_net``
at all -- so ``In2.Cu`` becomes expressible without touching R1/R7's
tested guarantee for a single production net. Cause (1) (``parse_engine.rs``'s
discarded layer-role token) is **also** not touched -- see "What this
does not do" below for why.

**Power islands are plural, not one plane.** Unlike ``gnd`` (a single
convex hull over all 86 pads), ``In2.Cu`` per this project's own
documented stackup intent carries *per-rail regions* -- ``+3V3``,
``+15V``, ``vcc``, ``V_BUS_SENSE`` each get their own copper, and those
regions must not touch each other (they are different nets sharing one
physical layer) on top of not touching the HV keepout ``_ground_plane.py``
already had to solve for. This module processes rails in priority order
(largest pad count first: ``+3V3`` (51), ``vcc`` (13), ``+15V`` (10),
``V_BUS_SENSE`` (4) -- measured directly against the production board,
2026-08-11) and accumulates each rail's own new copper (zone footprint,
drop vias, backbone segments) into the obstacle set every later rail's
geometry is kept clear of -- the single genuinely new geometry problem
this task has that the ground-plane spike did not: inter-rail clearance
on a shared layer, not just net-vs-HV-keepout.

**What this module reuses from ``_ground_plane.py`` (read-only import,
never modified -- out of this task's boundary).** The hard-won,
already-measured-safe primitives: ``compute_hv_selv_keepout`` (per-pad HV
buffer union, not a global band -- a global band was tried and measured
to fail on this board's real geometry), ``_collect_hv_copper_geometry``
(HV pad/via half-extent buffering, not just centres -- the fix for the
25-creepage-violation gap a centre-only buffer left), ``_collect_other_net_copper``,
``_existing_drilled_holes``, ``_find_via_drop_point``, ``mst_edges``,
``_emit_keepout_zone_s_expr``, ``_dedupe_positions``. None of that logic
is re-derived here; only the *multi-net accumulation* around it is new.

**What this module does NOT do (out of budget, reported honestly rather
than silently skipped):**

- **``parse_engine.rs`` is not touched.** The task names two independent
  root causes; this module addresses the second (the emitter path) the
  same way ``_ground_plane.py`` already did for ``In1.Cu`` -- a standalone
  generator bypassing ``_zone_layers_for_net`` entirely, not by making
  either function read the layer-role token. Fixing (1) requires
  rebuilding a shared pyo3/maturin extension (``temper-design-bundle``)
  that this sandbox's own tooling notes document as fragile under
  concurrent worktree builds (stale ``.so`` after a reported-successful
  ``maturin develop``, a shared venv multiple agents' worktrees point
  at). Given this module's bypass route is sufficient to make an
  inner-layer zone expressible and measurable end-to-end without it,
  rebuilding a shared native extension for a second, redundant path to
  the same capability was judged not worth the shared-environment risk
  this run.
- **UPDATED 2026-08-12**: the line above ("No MST backbone routing
  avoids OTHER rails'/nets' existing F.Cu copper") described the
  straight-line-MST-plus-one-bend-detour heuristic, which is genuinely
  incapable of this (measured: collapses connectivity). It is no longer
  the whole story -- ``_corridor_backbone.py``'s corridor-aware A* pass
  is now tried first for every MST edge (both the HV keepout and every
  other net's/rail's existing F.Cu copper), falling back to the
  keepout-only detour only for edges A* cannot solve (a measured,
  genuine fraction -- see that module's docstring). Residual
  ``tracks_crossing``/``clearance`` against pre-existing other-net
  copper is therefore reduced, not eliminated; still an honest,
  partial result, reported per-rail via
  ``PowerIslandResult.mst_edges_astar_routed_count`` /
  ``mst_edges_fallback_count``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from temper_placer.router_v6._ground_plane import (
    _collect_hv_copper_geometry,
    _collect_other_net_copper,
    _dedupe_positions,
    _emit_keepout_zone_s_expr,
    _existing_drilled_holes,
    _find_via_drop_point,
    compute_hv_selv_keepout,
    mst_edges,
)

logger = logging.getLogger(__name__)

PLANE_LAYER = "In2.Cu"
# Same reasoning as _ground_plane.py's BACKBONE_LAYER choice: a via only
# unions pad_connectivity_audit's graph nodes for the layers *literally
# present* in its own ``via.layers`` tuple (a real, documented gap in that
# tool -- see _ground_plane.py's MST-layer-choice comment), so the
# backbone must land on a layer the via's own ``(layers "F.Cu" "B.Cu")``
# tuple already names, not on PLANE_LAYER itself.
BACKBONE_LAYER = "F.Cu"

# Matches this board's Power netclass via convention (design_rules.py:
# TEMPER_NET_CLASSES["Power"].via_diameter/via_drill == 0.8/0.4mm exactly)
# -- the same values _ground_plane.py already uses for gnd's Via3x3-class
# drops, so this is not a new convention, just the same one applied to a
# different net class that happens to specify identical numbers.
VIA_SIZE_MM = 0.8
VIA_DRILL_MM = 0.4
STITCH_TRACE_WIDTH_MM = 0.3

BOARD_EDGE_MARGIN_MM = 1.0
OTHER_NET_CLEARANCE_MM = 0.05
# NOTE: this module deliberately does NOT redeclare
# KEEPOUT_EXTRA_MARGIN_MM/MIN_HOLE_EDGE_GAP_MM/VIA_OFFSET_RING_RADII_MM/
# VIA_OFFSET_RING_STEPS. _find_via_drop_point and compute_hv_selv_keepout
# are imported functions, not reimplemented here -- their free variables
# resolve against _ground_plane.py's own module globals regardless of
# what this module happens to name a same-named constant, so a local
# copy of those values would be inert and misleading (it would look
# like it configures the imported functions' behavior; it would not).

# Minimum edge-to-edge gap kept between one rail's own new zone footprint
# and every OTHER rail's already-emitted zone footprint this same run --
# the inter-rail-on-one-shared-layer problem _ground_plane.py never had
# (In1.Cu carries exactly one net). Not a safety-rated (creepage) figure
# -- these are all SELV/LV rails per elec/domain_manifest.yaml, so this
# is ordinary electrical clearance, sized to this board's own Power
# netclass clearance (design_rules.py: 0.25mm) with a small margin so a
# KiCad zone-fill pass (which itself adds clearance beyond a bare
# polygon-vs-polygon touch) has room to work with.
INTER_RAIL_CLEARANCE_MM = 0.4

DEFAULT_DOMAIN_MANIFEST_PATH = Path("elec/domain_manifest.yaml")

# Priority order: largest pad count first (measured against the
# production board, 2026-08-11: +3V3=51, vcc=13, +15V=10,
# V_BUS_SENSE=4 unique pad positions) -- see module docstring for why
# order matters (each later rail is clipped around every earlier rail's
# new copper).
POWER_ISLAND_NETS: tuple[str, ...] = ("+3V3", "vcc", "+15V", "V_BUS_SENSE")


__all__ = [
    "PLANE_LAYER",
    "POWER_ISLAND_NETS",
    "PowerIslandResult",
    "generate_power_islands_content",
]


class PowerIslandResult:
    """Per-rail report, mirroring ``_ground_plane.GroundPlaneResult`` so a
    caller can write the same kind of honest before/after evidence."""

    def __init__(
        self,
        *,
        net_name: str,
        pad_count: int,
        drop_via_count: int,
        mst_edge_count: int,
        zone_polygon_count: int,
        pour_area_mm2: float,
        via_skipped_through_hole_count: int = 0,
        via_offset_count: int = 0,
        via_unresolved_conflict_count: int = 0,
        mst_edges_dropped_count: int = 0,
        mst_edges_astar_routed_count: int = 0,
        mst_edges_fallback_count: int = 0,
    ) -> None:
        self.net_name = net_name
        self.pad_count = pad_count
        self.drop_via_count = drop_via_count
        self.mst_edge_count = mst_edge_count
        self.zone_polygon_count = zone_polygon_count
        self.pour_area_mm2 = pour_area_mm2
        self.via_skipped_through_hole_count = via_skipped_through_hole_count
        self.via_offset_count = via_offset_count
        self.via_unresolved_conflict_count = via_unresolved_conflict_count
        self.mst_edges_dropped_count = mst_edges_dropped_count
        self.mst_edges_astar_routed_count = mst_edges_astar_routed_count
        self.mst_edges_fallback_count = mst_edges_fallback_count

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"PowerIslandResult(net={self.net_name!r}, pads={self.pad_count}, "
            f"drop_vias={self.drop_via_count}, mst_edges={self.mst_edge_count}, "
            f"zone_polygons={self.zone_polygon_count}, "
            f"pour_area_mm2={self.pour_area_mm2:.1f}, "
            f"via_skipped_through_hole={self.via_skipped_through_hole_count}, "
            f"via_offset={self.via_offset_count}, "
            f"via_unresolved_conflict={self.via_unresolved_conflict_count}, "
            f"mst_edges_dropped={self.mst_edges_dropped_count}, "
            f"mst_edges_astar_routed={self.mst_edges_astar_routed_count}, "
            f"mst_edges_fallback={self.mst_edges_fallback_count})"
        )


def generate_power_islands_content(
    pcb_path: Path,
    *,
    nets: tuple[str, ...] = POWER_ISLAND_NETS,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
) -> tuple[str, dict[str, PowerIslandResult]]:
    """Read *pcb_path*, compute per-rail ``In2.Cu`` power-island pours +
    via/MST stitching for every net in *nets*, and return
    ``(new_board_content, {net_name: PowerIslandResult})``.

    Does not write anything. Rails are processed in the order given in
    *nets* (default: pad-count-descending); each rail's emitted zone
    footprint, drop vias, and backbone segments are folded into the
    obstacle set every later rail avoids, so the result never has two
    rails' new copper overlapping on ``In2.Cu`` (or a later rail's F.Cu/
    B.Cu vias landing on an earlier rail's).
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.placer.cp_sat.isolation_barrier import (
        DEFAULT_CORRIDOR_WIDTH_MM,
        load_domain_manifest_nets,
    )
    from temper_placer.router_v6.pad_connectivity_audit import ALL_LAYERS, _pads_by_net
    from temper_placer.router_v6.routing_space import _get_board_polygon
    from temper_placer.router_v6.topology_copper_audit import net_number_to_name_map
    from temper_placer.router_v6.zone_emission import (
        ZoneDefinition,
        compute_zones_for_net,
        emit_zone_s_expr,
    )

    content = pcb_path.read_text()
    pcb = parse_kicad_pcb_v6(pcb_path)

    num_to_name = net_number_to_name_map(content)
    name_to_num = {v: k for k, v in num_to_name.items()}

    # Real, per-net-class-pair clearance table for the corridor-aware A*
    # obstacle grid, read once (not per rail) -- see
    # _corridor_backbone.resolve_netclass_clearances's docstring for why
    # this replaces a flat constant.
    from temper_placer.router_v6._corridor_backbone import resolve_netclass_clearances

    _net_clearance, _default_clearance = resolve_netclass_clearances(
        pcb_path.with_suffix(".kicad_pro")
    )

    pads_by_net = _pads_by_net(pcb)
    board_polygon = _get_board_polygon(pcb)
    hv_nets, _selv_nets = load_domain_manifest_nets(domain_manifest_path)

    hv_positions: list[tuple[float, float]] = []
    for net_name in sorted(hv_nets):
        for pad in pads_by_net.get(net_name, []):
            hv_positions.append(pad.position)

    keepout_pads = compute_hv_selv_keepout(
        hv_positions, [], board_polygon, DEFAULT_CORRIDOR_WIDTH_MM
    )
    hv_extra = _collect_hv_copper_geometry(pcb, hv_nets, DEFAULT_CORRIDOR_WIDTH_MM)
    keepout_parts = [g for g in (keepout_pads, hv_extra) if g is not None]
    keepout: Polygon | None = None
    if keepout_parts:
        merged = unary_union(keepout_parts).intersection(board_polygon)
        if not merged.is_empty:
            keepout = merged
    keepout_established = keepout is not None

    plane_region_base = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)
    if keepout_established:
        plane_region_base = plane_region_base.difference(keepout)

    tstamp_counter = [0]

    def _next_tstamp() -> str:
        from temper_placer.router_v6._adapter_convert import _next_tstamp as _nt

        return _nt(tstamp_counter)

    new_blocks: list[str] = []

    # One fill-time keepout rule-area zone on PLANE_LAYER, shared by every
    # rail (the region is net-independent -- see _emit_keepout_zone_s_expr's
    # own docstring for why this is a hard, independent defense on top of
    # the pour-outline clip, not merely a duplicate of it).
    if keepout_established:
        keepout_pieces = list(keepout.geoms) if hasattr(keepout, "geoms") else [keepout]
        for piece in keepout_pieces:
            if piece.is_empty or not hasattr(piece, "exterior"):
                continue
            pts = [(float(x), float(y)) for x, y in piece.exterior.coords]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            if len(pts) < 3:
                continue
            new_blocks.append(_emit_keepout_zone_s_expr(pts, PLANE_LAYER, _next_tstamp()))

    # Cross-rail accumulators -- everything a LATER rail must stay clear
    # of that an EARLIER rail in this same run just added.
    other_rail_zone_region: Polygon | None = None  # In2.Cu, this run only
    run_new_holes: list[tuple[float, float, float]] = []  # any layer, this run
    run_new_fcu_copper: list[Polygon] = []  # vias + backbone, F.Cu, this run
    run_new_bcu_copper: list[Polygon] = []  # vias, B.Cu, this run

    results: dict[str, PowerIslandResult] = {}

    for net_name in nets:
        net_num = name_to_num.get(net_name)
        if net_num is None:
            logger.warning(
                "generate_power_islands_content: %r not found in this board's "
                "(net ...) declarations -- skipping.",
                net_name,
            )
            continue
        pads = pads_by_net.get(net_name, [])
        if not pads:
            logger.warning(
                "generate_power_islands_content: net %r has zero pads on this "
                "board -- skipping.",
                net_name,
            )
            continue
        positions = _dedupe_positions([p.position for p in pads])

        through_hole_positions: dict[tuple[float, float], bool] = {}
        for p in pads:
            key = (round(p.position[0], 3), round(p.position[1], 3))
            through_hole_positions[key] = through_hole_positions.get(key, False) or (
                p.layer == ALL_LAYERS
            )

        # --- Zone footprint: per-component clusters (cluster=True -- these
        # are "islands", plural, not one board-spanning hull like gnd's). ---
        zones = compute_zones_for_net(
            net_name, net_num, positions, layer=PLANE_LAYER, margin=0.5, cluster=True,
            board_polygon=None,
        )
        plane_region = plane_region_base
        if other_rail_zone_region is not None:
            plane_region = plane_region.difference(
                other_rail_zone_region.buffer(INTER_RAIL_CLEARANCE_MM)
            )

        zone_polys: list[Polygon] = []
        for zd in zones:
            hull_poly = Polygon(zd.points)
            clipped = hull_poly.intersection(plane_region)
            if clipped.is_empty:
                continue
            geoms = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
            for g in geoms:
                if hasattr(g, "exterior") and not g.is_empty and len(g.exterior.coords) >= 4:
                    zone_polys.append(g)

        pour_area_mm2 = 0.0
        this_rail_zone_geoms: list[Polygon] = []
        for poly in zone_polys:
            pour_area_mm2 += poly.area
            this_rail_zone_geoms.append(poly)
            pts = [(float(x), float(y)) for x, y in poly.exterior.coords]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            if len(pts) < 3:
                continue
            zd = ZoneDefinition(
                net_name=net_name,
                net_number=net_num,
                layer=PLANE_LAYER,
                points=tuple(pts),
                clearance=0.25,
                min_thickness=0.25,
                priority=0,
            )
            new_blocks.append(emit_zone_s_expr(zd))

        if this_rail_zone_geoms:
            merged_this_rail = unary_union(this_rail_zone_geoms)
            other_rail_zone_region = (
                merged_this_rail
                if other_rail_zone_region is None
                else unary_union([other_rail_zone_region, merged_this_rail])
            )

        # --- Drop vias + MST backbone. Vias: keepout + this run's own
        # prior new copper + OTHER nets' pre-existing F.Cu/B.Cu copper
        # are all hard obstacles for the per-point via-placement search
        # below. Backbone: as of 2026-08-12, a corridor-aware A* pass
        # (below, near `edges = mst_edges(positions)`) now ALSO attempts
        # to avoid OTHER nets' pre-existing F.Cu copper for the backbone
        # path itself, not just via placement -- see
        # _corridor_backbone.py's module docstring for why this had to
        # be a hybrid (A* first, keepout-only detour as fallback) rather
        # than a full per-path search replacing `_blocked` outright. ---
        other_copper_fcu = _collect_other_net_copper(
            pcb, net_name, "F.Cu", OTHER_NET_CLEARANCE_MM
        )
        other_copper_bcu = _collect_other_net_copper(
            pcb, net_name, "B.Cu", OTHER_NET_CLEARANCE_MM
        )
        via_avoid_parts = [
            g
            for g in (other_copper_fcu, other_copper_bcu, *run_new_fcu_copper, *run_new_bcu_copper)
            if g is not None
        ]
        via_avoid_copper: Polygon | None = (
            unary_union(via_avoid_parts) if via_avoid_parts else None
        )

        existing_holes = _existing_drilled_holes(pcb, net_name) + list(run_new_holes)

        via_skipped_through_hole = 0
        via_offset_count = 0
        via_unresolved_conflict = 0
        via_radius_mm = VIA_SIZE_MM / 2.0
        this_rail_vias: list[Polygon] = []

        for x, y in positions:
            key = (round(x, 3), round(y, 3))
            if through_hole_positions.get(key, False):
                via_skipped_through_hole += 1
                continue

            drop_point, needs_stub = _find_via_drop_point(
                (x, y),
                existing_holes=existing_holes,
                via_radius_mm=via_radius_mm,
                keepout=keepout if keepout_established else None,
                other_copper=via_avoid_copper,
                board_polygon=board_polygon,
            )
            if drop_point is None:
                via_unresolved_conflict += 1
                logger.warning(
                    "generate_power_islands_content(%s): no clear via drop "
                    "point found near pad at (%.4f, %.4f) -- skipping this "
                    "via rather than emitting a known-colliding one.",
                    net_name,
                    x,
                    y,
                )
                continue

            vx, vy = drop_point
            new_blocks.append(
                f'  (via (at {vx:.4f} {vy:.4f}) (size {VIA_SIZE_MM:.4f}) '
                f'(drill {VIA_DRILL_MM:.4f}) (layers "F.Cu" "B.Cu") '
                f"(net {net_num}) (tstamp \"{_next_tstamp()}\"))"
            )
            existing_holes.append((vx, vy, via_radius_mm))
            run_new_holes.append((vx, vy, via_radius_mm))
            this_rail_vias.append(Point(vx, vy).buffer(via_radius_mm + OTHER_NET_CLEARANCE_MM, quad_segs=8))
            if needs_stub:
                via_offset_count += 1
                new_blocks.append(
                    f"  (segment (start {x:.4f} {y:.4f}) (end {vx:.4f} {vy:.4f})"
                    f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{BACKBONE_LAYER}")'
                    f" (net {net_num}) (tstamp \"{_next_tstamp()}\"))"
                )

        edges = mst_edges(positions)

        # --- Corridor-aware A* pass (see _corridor_backbone.py's module
        # docstring): try a real, collision-avoiding path for every MST
        # edge first, over a grid that blocks the HV keepout, every
        # OTHER net's existing F.Cu copper (other_copper_fcu, already
        # computed above for via placement), AND every earlier rail's
        # new copper this same run (run_new_fcu_copper) -- the one
        # power-islands-specific obstacle _ground_plane.py never has
        # (In1.Cu carries exactly one net; In2.Cu carries four, each
        # needing to stay off the others' F.Cu backbone too). The
        # keepout-only `_blocked`/one-bend-detour loop below is the
        # fallback for edges this cannot solve (a measured, genuine
        # physical disconnection for a real fraction of edges -- see
        # that module's docstring), so connectivity per rail can only
        # improve edge-by-edge, never regress below the prior behaviour.
        from temper_placer.core.topology import UnionFind
        from temper_placer.router_v6._corridor_backbone import (
            build_obstacle_grid,
            collect_other_net_copper_by_pairwise_clearance,
            compute_corridor_mask,
            corridor_aware_spanning_edges,
        )

        # Real, per-net-pair clearance polygon for the A* obstacle grid --
        # NOT other_copper_fcu (built above at OTHER_NET_CLEARANCE_MM
        # =0.05mm for via placement); see
        # _corridor_backbone.resolve_netclass_clearances's docstring.
        # run_new_fcu_copper (earlier rails' new copper this run) is
        # additionally buffered by INTER_RAIL_CLEARANCE_MM here -- those
        # polygons already carry ~0.05mm from their own construction
        # (_emit_segment/this_rail_vias), so this brings their effective
        # standoff up near the same ballpark as the real Power-class
        # pairwise clearance without re-deriving them from raw geometry.
        this_net_own_clearance = _net_clearance.get(net_name, _default_clearance)
        other_copper_fcu_backbone = collect_other_net_copper_by_pairwise_clearance(
            pcb, net_name, "F.Cu", _net_clearance, this_net_own_clearance, _default_clearance
        )
        prior_rail_backbone_obstacles = [
            g.buffer(INTER_RAIL_CLEARANCE_MM) for g in run_new_fcu_copper
        ]
        backbone_grid = build_obstacle_grid(
            board_polygon,
            [keepout, other_copper_fcu_backbone, *prior_rail_backbone_obstacles],
        )
        backbone_corridor_mask = compute_corridor_mask(backbone_grid, STITCH_TRACE_WIDTH_MM)

        # Component-aware (see _corridor_backbone.py / _ground_plane.py's
        # own docstrings for the measured reason a blind per-Euclidean-
        # MST-edge attempt undersells this): a Euclidean MST WITHIN each
        # of the corridor mask's own connected components, not the
        # global MST's own (possibly corridor-infeasible) edge list.
        astar_routed_edges = corridor_aware_spanning_edges(
            positions, backbone_grid, backbone_corridor_mask, mst_edges
        )
        connectivity_uf = UnionFind()
        for i, j in astar_routed_edges:
            connectivity_uf.union(i, j)

        def _emit_segment(p1: tuple[float, float], p2: tuple[float, float], _net_num=net_num) -> Polygon:
            new_blocks.append(
                f"  (segment (start {p1[0]:.4f} {p1[1]:.4f}) (end {p2[0]:.4f} {p2[1]:.4f})"
                f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{BACKBONE_LAYER}")'
                f" (net {_net_num}) (tstamp \"{_next_tstamp()}\"))"
            )
            return LineString([p1, p2]).buffer(
                STITCH_TRACE_WIDTH_MM / 2.0 + OTHER_NET_CLEARANCE_MM, quad_segs=8
            )

        run_this_rail_backbone: list[Polygon] = []

        def _blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
            line = LineString([p1, p2])
            if keepout_established and line.intersects(keepout):
                return True
            for g in run_new_fcu_copper:
                if line.intersects(g):
                    return True
            return False

        # Emit every component-local A*-routed edge unconditionally --
        # additional real connectivity beyond (not necessarily a subset
        # of) the global Euclidean MST's own edge list.
        astar_routed_count = 0
        for (_i, _j), astar_path in astar_routed_edges.items():
            for a, b in zip(astar_path, astar_path[1:]):
                run_this_rail_backbone.append(_emit_segment(a, b))
            astar_routed_count += 1

        crossed_keepout = 0
        rerouted = 0
        for i, j in edges:
            if connectivity_uf.find(i) == connectivity_uf.find(j):
                # Already joined by a component-local A*-clean edge (or a
                # chain of them) -- drawing this global-MST edge too
                # would only add collision risk for zero connectivity
                # benefit.
                continue

            p1, p2 = positions[i], positions[j]
            if not _blocked(p1, p2):
                run_this_rail_backbone.append(_emit_segment(p1, p2))
                connectivity_uf.union(i, j)
                continue

            candidates = sorted(
                (k for k in range(len(positions)) if k != i and k != j),
                key=lambda k: (
                    (positions[k][0] - p1[0]) ** 2
                    + (positions[k][1] - p1[1]) ** 2
                    + (positions[k][0] - p2[0]) ** 2
                    + (positions[k][1] - p2[1]) ** 2
                ),
            )[:200]
            found = False
            for k in candidates:
                w = positions[k]
                if not _blocked(p1, w) and not _blocked(w, p2):
                    run_this_rail_backbone.append(_emit_segment(p1, w))
                    run_this_rail_backbone.append(_emit_segment(w, p2))
                    found = True
                    break
            if found:
                rerouted += 1
                connectivity_uf.union(i, j)
            else:
                crossed_keepout += 1

        if crossed_keepout:
            logger.warning(
                "generate_power_islands_content(%s): %d MST edge(s) crossed "
                "the HV keepout or another rail's new F.Cu copper and could "
                "not be rerouted (%d rerouted via one-bend detour). Dropped "
                "rather than routed through it -- the backbone may be a "
                "forest, not a single tree.",
                net_name,
                crossed_keepout,
                rerouted,
            )

        run_new_fcu_copper.extend(this_rail_vias)
        run_new_fcu_copper.extend(run_this_rail_backbone)
        run_new_bcu_copper.extend(this_rail_vias)

        results[net_name] = PowerIslandResult(
            net_name=net_name,
            pad_count=len(positions),
            drop_via_count=len(positions) - via_skipped_through_hole - via_unresolved_conflict,
            mst_edge_count=len(edges) - crossed_keepout,
            zone_polygon_count=len(zone_polys),
            pour_area_mm2=pour_area_mm2,
            via_skipped_through_hole_count=via_skipped_through_hole,
            via_offset_count=via_offset_count,
            via_unresolved_conflict_count=via_unresolved_conflict,
            mst_edges_dropped_count=crossed_keepout,
            mst_edges_astar_routed_count=astar_routed_count,
            mst_edges_fallback_count=len(edges) - astar_routed_count,
        )

    new_content = content.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(new_blocks) + "\n)\n"

    return new_content, results
