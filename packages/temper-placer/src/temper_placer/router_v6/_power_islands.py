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

from temper_placer.core.design_rules import TEMPER_NET_CLASSES
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

# NOTE: the comment this replaced claimed this matched design_rules.py's
# Power netclass via convention "0.8/0.4mm exactly" -- that was already
# stale before this fix: Power's via_diameter/via_drill was corrected to
# 1.0/0.5mm on 2026-08-12 (docs/evidence/2026-08-12-netclass-param-
# reconciliation.md) and this literal constant was never updated alongside
# it, so it had already drifted from the class it claimed to mirror. This
# constant is, and always was, an independent hardcoded generator (one of
# the two literal generators of the board's 44 vias, along with
# _ground_plane.py's identical constant) -- not a derived mirror of any
# netclass table.
#
# RAISED size 0.8 -> 1.0mm 2026-08-13
# (docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md sec.6.1,
# docs/hardware/FAB_CAPABILITY.md): the old 0.8mm pad / 0.4mm drill pair
# gave a 0.2mm annular ring, below JLCPCB's 2oz PTH annular-ring floor
# (0.254mm). Drill is unchanged (0.4mm) -- pure pad-geometry fix. New pad =
# drill + 2 x 0.3mm ring target, the board-wide 0.3mm-ring convention (see
# _ground_plane.py's identical constant and every TEMPER_NET_CLASSES
# via_diameter in core/design_rules.py).
VIA_SIZE_MM = 1.0
VIA_DRILL_MM = 0.4

# RAISED 0.3 -> Power netclass trace_width (1.0mm) 2026-08-17 (pour-stitch
# track_width root-cause fix,
# docs/evidence/2026-08-17-pour-stitch-defect-rootcause-and-m6c-reeval.md):
# every net in POWER_ISLAND_NETS ("+3V3", "vcc", "+15V", "V_BUS_SENSE") is
# classified "Power" in pcb/temper.kicad_pro, and the emitted DRU carries a
# "Power trace width" rule at min 1.0mm (design_rules.py
# TEMPER_NET_CLASSES["Power"].trace_width). This module's own comment
# above (VIA_SIZE_MM) claimed this constant was "identical" to
# _ground_plane.py's STITCH_TRACE_WIDTH_MM -- that was already false by
# the time it was written: _ground_plane.py's was raised 0.4 -> 1.0mm on
# 2026-08-16 for the exact same defect class on GND (216/747 track_width
# violations, that module's own STITCH_TRACE_WIDTH_MM comment), and this
# constant was never brought along. At 0.3mm every stitch/via-drop segment
# this generator emits for a Power-class net is, by construction, a real
# track_width DRC violation -- measured ~100 pre-existing on +3V3 alone at
# the committed board, worsening under router congestion as the MST
# generator falls back to more narrow-stub segments (see evidence doc
# above for the full before/after). Derived from TEMPER_NET_CLASSES rather
# than a second hardcoded literal, since a hardcoded copy silently
# drifting from its own netclass SSOT is exactly the failure being fixed.
# The corridor mask's erosion (compute_corridor_mask uses this same
# constant) and the inter-net blocked-check radius both widen
# correspondingly -- this is the same single-knob relationship
# _ground_plane.py's identical fix already established.
STITCH_TRACE_WIDTH_MM = TEMPER_NET_CLASSES["Power"].trace_width

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
    "generate_power_islands_blocks",
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


def generate_power_islands_blocks(
    pcb_path: Path,
    *,
    nets: tuple[str, ...] = POWER_ISLAND_NETS,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
    tstamp_counter: list[int] | None = None,
    segments: list[str] | None = None,
) -> tuple[list[str], dict[str, PowerIslandResult]]:
    """Compute per-rail ``In2.Cu`` power-island pours + via/MST stitching
    for every net in *nets* and return the NEW s-expression blocks plus
    the per-rail result reports.

    Does not write anything. This is the production wiring seam (the
    ``_ground_plane.generate_ground_plane_blocks`` counterpart): the
    caller appends the blocks to its own emitted copper after the pour
    pass. Rails are processed in the order given in *nets* (default:
    pad-count-descending); each rail's emitted zone footprint, drop vias,
    and backbone segments are folded into the obstacle set every later
    rail avoids, so the result never has two rails' new copper
    overlapping on ``In2.Cu`` (or a later rail's F.Cu/B.Cu vias landing
    on an earlier rail's). ``tstamp_counter`` is threaded from the caller
    (same convention as ``generate_ground_plane_blocks``) so the blocks'
    tstamps continue the caller's deterministic sequence; when ``None`` a
    fresh counter is used (the standalone script and the spike tests call
    it without one).

    UPDATED 2026-08-16: the pour outline for every rail is now computed
    by the Rust zone generator (``temper_geometry.pour_outline_py`` /
    ``emit_zone_outline_s_expr_py``, the #1257 machinery) carved at
    ``max(clearance, creepage)`` per foreign obstacle -- see the zone
    footprint section below for the measured rationale and the
    ``docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py`` data.
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
        compute_zones_for_net,
    )

    content = pcb_path.read_text()
    pcb = parse_kicad_pcb_v6(pcb_path)

    # The default manifest path is CWD-relative, and production callers
    # (route_pcb via _write_routes_to_content) run from arbitrary CWDs
    # (pytest from packages/temper-placer, route_board.py from the repo
    # root). Resolve a missing relative default against the repo root
    # (this module lives at packages/temper-placer/src/temper_placer/
    # router_v6/, so the repo root is five parents up) before handing it
    # to the loader -- the same fallback _ground_plane.py already has.
    if not domain_manifest_path.is_file() and not domain_manifest_path.is_absolute():
        alt = Path(__file__).resolve().parents[5] / domain_manifest_path
        if alt.is_file():
            domain_manifest_path = alt

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

    if tstamp_counter is None:
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

        # --- Zone footprint: one hull per rail, carved by the Rust zone
        # generator (2026-08-16). ---
        # Previously: compute_zones_for_net(cluster=True) convex hulls
        # emitted via single-ring emit_zone_s_expr -- no carve, no holes,
        # clearance scalar only -- the same emission that fragmented the
        # historical +3V3 pours into pad-sized remnants (the measured
        # reason R1/R7 made Power trace-only). The Rust generator
        # (temper_geometry.pour_outline_py / emit_zone_outline_s_expr_py,
        # #1257) carves each foreign obstacle's halo at that pair's
        # max(clearance, creepage) -- 12.6mm HV-vs-Power creepage, not the
        # 2.0mm clearance table -- and emits one (polygon ...) element per
        # ring (exterior + holes). Measured 2026-08-16
        # (docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py): a
        # per-cluster carve covers 28/50 +3V3 pads in 12 zones, while a
        # SINGLE hull over all 50 pads (cluster=False, the gnd-plane
        # precedent) covers 34/50 pads in just 2 islands -- the same
        # fragmentation lesson gnd taught (see _ground_plane.py's region
        # comment): splitting the region before carving multiplies
        # islands without adding coverage. The remaining ~16 pads sit
        # inside the 12.6mm HV creepage halos and cannot be pour-covered
        # on ANY layer; they are trace-routing debt, reported honestly.
        # The pour is still PadsOnly -- padless islands are pure
        # isolated_copper liability -- and `_zone_layers_for_net` is
        # still NOT consulted (R1/R7's
        # `test_power_class_is_not_zone_eligible` stays intact: Power
        # remains outer-layer trace-only by policy; this is the
        # sanctioned `_ground_plane.py`-precedent inner-layer generator,
        # per this module's own docstring).
        import temper_geometry as _tg

        from temper_placer.router_v6.zone_pour_clearance import (
            collect_zone_obstacle_records,
        )
        from temper_placer.router_v6.zone_pour_clearance import (
            default_table as _zone_clearance_default_table,
        )
        from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

        obstacle_records = [
            tuple(r)
            for r in collect_zone_obstacle_records(
                net_name,
                PLANE_LAYER,
                pcb=pcb,
                segments=[],
                net_number_to_name=num_to_name,
                clearance_table=_zone_clearance_default_table(),
                creepage_table=default_creepage_table(),
            )
        ]
        own_rust = [(float(x), float(y)) for x, y in positions]

        zones = compute_zones_for_net(
            net_name, net_num, positions, layer=PLANE_LAYER, margin=0.5, cluster=False,
            board_polygon=None,
        )
        plane_region = plane_region_base
        if other_rail_zone_region is not None:
            plane_region = plane_region.difference(
                other_rail_zone_region.buffer(INTER_RAIL_CLEARANCE_MM)
            )

        zone_polys: list[Polygon] = []
        pour_area_mm2 = 0.0
        this_rail_zone_geoms: list[Polygon] = []
        for zd in zones:
            hull_poly = Polygon(zd.points)
            clipped = hull_poly.intersection(plane_region)
            if clipped.is_empty:
                continue
            geoms = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
            for g in geoms:
                if not hasattr(g, "exterior") or g.is_empty or len(g.exterior.coords) < 4:
                    continue
                rpts = [(float(x), float(y)) for x, y in g.exterior.coords]
                if len(rpts) > 1 and rpts[0] == rpts[-1]:
                    rpts.pop()
                if len(rpts) < 3:
                    continue
                # The clip's piece may carry INTERIOR rings (an earlier
                # rail's buffered zone region, or a keepout island, sitting
                # inside this hull).  pour_outline_py takes a single region
                # ring, so passing only the exterior would silently pour
                # back over the other rail (measured 2026-08-16: vcc's
                # outline overlapped +3V3's by 75mm^2 exactly this way --
                # the region hole was dropped at the ring extraction).  The
                # region polygon (exterior + these interior rings) is
                # subtracted from the Rust carve result below so every
                # interior hole survives into the emitted outline.
                region_interiors = [
                    [(float(x), float(y)) for x, y in ring.coords]
                    for ring in g.interiors
                ]
                region_interiors = [r for r in region_interiors if len(r) >= 3]
                region_poly = Polygon(rpts, region_interiors)
                pour_zones = _tg.pour_outline_py(
                    rpts, own_rust, obstacle_records, 0.25 * 0.25, True
                )
                final_rings: list[tuple[list, list]] = []
                for zone_rings in pour_zones:
                    zp = Polygon(
                        zone_rings[0],
                        [list(h) for h in zone_rings[1:] if len(h) >= 3],
                    )
                    remaining = zp.intersection(region_poly)
                    if remaining.is_empty:
                        continue
                    pieces = (
                        list(remaining.geoms) if hasattr(remaining, "geoms") else [remaining]
                    )
                    for piece in pieces:
                        if piece.is_empty or not hasattr(piece, "exterior"):
                            continue
                        ext = [(float(x), float(y)) for x, y in piece.exterior.coords]
                        if ext and ext[0] == ext[-1]:
                            ext.pop()
                        pholes = [
                            [(float(x), float(y)) for x, y in h.coords]
                            for h in piece.interiors
                        ]
                        pholes = [h for h in pholes if len(h) >= 3]
                        if len(ext) >= 3:
                            final_rings.append((ext, pholes))
                for exterior, holes in final_rings:
                    new_blocks.append(
                        _tg.emit_zone_outline_s_expr_py(
                            net_num,
                            net_name,
                            PLANE_LAYER,
                            exterior,
                            holes,
                            0.25,
                            0,
                            0.25,
                        )
                    )
                    hole_polys = [list(h) for h in holes if len(h) >= 3]
                    carved = Polygon(exterior, hole_polys)
                    zone_polys.append(carved)
                    this_rail_zone_geoms.append(carved)
                    pour_area_mm2 += abs(carved.area)

        if this_rail_zone_geoms:
            merged_this_rail = unary_union(this_rail_zone_geoms)
            other_rail_zone_region = (
                merged_this_rail
                if other_rail_zone_region is None
                else unary_union([other_rail_zone_region, merged_this_rail])
            )
        # Union of THIS rail's carved pour outlines -- the fill's real
        # copper footprint on In2.Cu. Vias placed inside it touch the rail
        # after fill (see _find_via_drop_point's pour_region parameter); a
        # via outside it sits on the F.Cu backbone only (measured 2026-08-16:
        # keepout-only placement landed vias up to 12.6mm from HV copper,
        # outside the creepage-carved fill, touching no rail at all).
        pour_region: Polygon | None = None
        if this_rail_zone_geoms:
            merged_pour = unary_union(this_rail_zone_geoms)
            if not merged_pour.is_empty:
                pour_region = merged_pour

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
        # The route's own F.Cu/B.Cu copper (in-memory segment strings,
        # invisible to the stripped board file this generator re-parses)
        # must also be avoided -- see
        # _corridor_backbone.routed_segments_obstacle's docstring for the
        # measured 2026-08-16 failure mode (backbones blind to the routed
        # copper + the earlier gnd plane crossed them 81 times on one
        # route). The gnd plane's blocks are part of *segments* by the
        # time this generator runs (the caller extends the list first), so
        # gnd's vias/backbone are included here too.
        from temper_placer.router_v6._corridor_backbone import (
            routed_segments_obstacle,
        )

        routed_fcu_avoid = routed_segments_obstacle(
            segments, net_name, "F.Cu", num_to_name,
            _net_clearance, _net_clearance.get(net_name, _default_clearance), _default_clearance,
        )
        routed_bcu_avoid = routed_segments_obstacle(
            segments, net_name, "B.Cu", num_to_name,
            _net_clearance, _net_clearance.get(net_name, _default_clearance), _default_clearance,
        )
        via_avoid_parts = [
            g
            for g in (
                other_copper_fcu,
                other_copper_bcu,
                routed_fcu_avoid,
                routed_bcu_avoid,
                *run_new_fcu_copper,
                *run_new_bcu_copper,
            )
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
                pour_region=pour_region,
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
                # RAISED 2026-08-17 (stitch-congestion root-cause fix, see
                # the MST-backbone `_blocked` comment below for the full
                # mechanism): this stub is real STITCH_TRACE_WIDTH_MM-wide
                # F.Cu copper from the pad straight to the offset via, and
                # was never checked against anything -- the via-drop search
                # only clears the via's OWN footprint, not the straight
                # line joining it back to the pad. `_ground_plane.py`'s
                # identical stub already gates on exactly this
                # (2026-08-16, "fix/route-to-100-percent"); this one,
                # cloned earlier, never did. Gate with the same
                # buffered-footprint check, reusing `via_avoid_copper`
                # (already comprehensive: pre-existing other-net copper,
                # this run's routed segments, and every earlier power rail's
                # own new copper). A blocked stub is skipped fail-closed --
                # the via stays; the pad just isn't stub-joined, a labelled
                # connectivity cost on this net, not a short.
                stub_footprint = LineString([(x, y), (vx, vy)]).buffer(
                    STITCH_TRACE_WIDTH_MM / 2.0
                )
                stub_blocked = (
                    keepout_established and stub_footprint.intersects(keepout)
                ) or (
                    via_avoid_copper is not None
                    and not via_avoid_copper.is_empty
                    and stub_footprint.intersects(via_avoid_copper)
                )
                if not stub_blocked:
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
        # The route's own F.Cu copper (and the earlier gnd plane, which is
        # part of *segments* by now) is an obstacle for the backbone search
        # too -- see routed_segments_obstacle's docstring.
        routed_fcu_backbone = routed_segments_obstacle(
            segments, net_name, "F.Cu", num_to_name,
            _net_clearance, this_net_own_clearance, _default_clearance,
        )
        prior_rail_backbone_obstacles = [
            g.buffer(INTER_RAIL_CLEARANCE_MM) for g in run_new_fcu_copper
        ]
        backbone_grid = build_obstacle_grid(
            board_polygon,
            [keepout, other_copper_fcu_backbone, routed_fcu_backbone, *prior_rail_backbone_obstacles],
        )
        backbone_corridor_mask = compute_corridor_mask(backbone_grid, STITCH_TRACE_WIDTH_MM)

        # DIAGNOSTIC (2026-08-18, vcc/V_BUS_SENSE zero-backbone root-cause
        # task): attribute how many of this rail's OWN pad positions land
        # in the corridor mask's largest component vs. their own singleton/
        # small component -- distinguishes "genuinely fragmented corridor"
        # from "a search-strategy near-miss" per _corridor_backbone.py's
        # own documented mechanism. Cheap (reuses the mask already
        # computed for the real A* pass, no extra grid build), logged at
        # INFO so it is visible without extra logging config. Left in
        # permanently -- this is exactly the per-rail visibility
        # PowerIslandResult's other counters already provide, extended to
        # the one dimension (corridor fragmentation) that was previously
        # invisible.
        from temper_placer.router_v6._corridor_backbone import (
            _NEAREST_LABEL_SEARCH_RADIUS_CELLS,
            _connected_components_8,
        )

        _labels = _connected_components_8(backbone_corridor_mask)

        def _nearest_label(cx: int, cy: int) -> int:
            # Exact copy of corridor_aware_spanning_edges's own growing-
            # radius search (same radius constant) -- a raw exact-cell
            # lookup alone underrepresents real reachability, since that
            # function tolerates a via/pad landing just outside the mask
            # (see its own docstring, "52 of 86 positions" measured gap).
            if _labels[cy, cx] != 0:
                return int(_labels[cy, cx])
            h, w = _labels.shape
            for r in range(1, _NEAREST_LABEL_SEARCH_RADIUS_CELLS + 1):
                x0, x1 = max(0, cx - r), min(w, cx + r + 1)
                y0, y1 = max(0, cy - r), min(h, cy + r + 1)
                window = _labels[y0:y1, x0:x1]
                nonzero = window[window != 0]
                if nonzero.size:
                    return int(nonzero[0])
            return 0

        _own_component_ids: list[int] = []
        _own_component_sizes: list[int] = []
        for _x, _y in positions:
            _cx, _cy = backbone_grid.world_to_grid(_x, _y)
            if 0 <= _cx < backbone_grid.width_cells and 0 <= _cy < backbone_grid.height_cells:
                _lbl = _nearest_label(_cx, _cy)
            else:
                _lbl = 0
            _own_component_ids.append(_lbl)
            _own_component_sizes.append(int((_labels == _lbl).sum()) if _lbl != 0 else 0)
        _unreachable_positions = sum(1 for lbl in _own_component_ids if lbl == 0)
        _distinct_components = len({lbl for lbl in _own_component_ids if lbl != 0})
        logger.warning(
            "generate_power_islands_content(%s): corridor-mask reachability "
            "(WITH the %d-cell/%0.1fmm growing nearest-label search, matching "
            "corridor_aware_spanning_edges's own tolerance) for this rail's "
            "%d own positions -- component id per position: %s, sizes (cells): "
            "%s -- %d position(s) totally unreachable (no labelled cell within "
            "the growing search at all) and the reachable positions split "
            "across %d DISTINCT components (only same-component pairs are ever "
            "attempted by the MST-within-component A* pass) at %.2fmm width, "
            "given keepout + other-net copper + %d earlier-rail obstacle "
            "polygon(s) this run.",
            net_name,
            _NEAREST_LABEL_SEARCH_RADIUS_CELLS,
            _NEAREST_LABEL_SEARCH_RADIUS_CELLS * backbone_grid.cell_size,
            len(positions),
            _own_component_ids,
            _own_component_sizes,
            _unreachable_positions,
            _distinct_components,
            STITCH_TRACE_WIDTH_MM,
            len(prior_rail_backbone_obstacles),
        )

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

        # RAISED 2026-08-17 (stitch-congestion root-cause fix,
        # docs/evidence/2026-08-17-stitch-congestion-rootcause-and-fix.md):
        # this fallback used to test a ZERO-WIDTH line against obstacle
        # polygons that only carry the FOREIGN copper's own half-width +
        # OTHER_NET_CLEARANCE_MM -- correct for a point probe, wrong for a
        # STITCH_TRACE_WIDTH_MM-wide segment (under-buffers by exactly this
        # segment's own half-width, i.e. by 0.5mm at today's 1.0mm width,
        # vs. 0.15mm at the old 0.3mm width the check was never wrong
        # enough to catch). It ALSO never checked `other_copper_fcu_backbone`
        # (every OTHER net's pre-existing board copper, real per-net-class-
        # pair clearance) or `routed_fcu_backbone` (this run's own Stage
        # 3/4-routed copper + the gnd plane, same clearance convention) --
        # both already computed above for the primary corridor-aware A*
        # pass but never wired into this legacy fallback, so a straight-
        # line/one-bend-detour edge could be drawn directly through a
        # signal net's freshly-routed track with zero awareness it was
        # there. This is `_ground_plane.py`'s own `_blocked` fix
        # (2026-08-16, "fix/route-to-100-percent") applied here for the
        # first time -- that module's fallback got exactly this
        # combination (buffered test footprint + foreign-copper checks)
        # and this one, cloned from an earlier version, never did.
        # Measured (see evidence doc): 108/130 of the +77 shorting_items
        # regression from the 0.3->1.0mm stitch-width fix (PR #1329) is on
        # +3V3 alone -- the rail with by far the most MST edges, hence the
        # most fallback usage, hence the most exposure to exactly this gap.
        # DIAGNOSTIC (2026-08-18): attribute WHICH obstacle category is
        # responsible when _blocked() rejects a candidate line -- reported
        # per-rail below (mirrors the corridor-mask component-size
        # diagnostic above). Does not change _blocked()'s decision in any
        # way (same checks, same order, same fail-closed semantics) --
        # purely observational, first-match-wins classification for
        # visibility into why an edge failed, not a new gate.
        _block_reason_counts: dict[str, int] = {
            "keepout": 0,
            "other_net_preexisting_copper": 0,
            "this_run_routed_signal_or_gnd_copper": 0,
            "earlier_rail_this_run": 0,
        }

        def _blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
            footprint = LineString([p1, p2]).buffer(STITCH_TRACE_WIDTH_MM / 2.0)
            if keepout_established and footprint.intersects(keepout):
                _block_reason_counts["keepout"] += 1
                return True
            if (
                other_copper_fcu_backbone is not None
                and not other_copper_fcu_backbone.is_empty
                and footprint.intersects(other_copper_fcu_backbone)
            ):
                _block_reason_counts["other_net_preexisting_copper"] += 1
                return True
            if (
                routed_fcu_backbone is not None
                and not routed_fcu_backbone.is_empty
                and footprint.intersects(routed_fcu_backbone)
            ):
                _block_reason_counts["this_run_routed_signal_or_gnd_copper"] += 1
                return True
            for g in run_new_fcu_copper:
                if footprint.intersects(g):
                    _block_reason_counts["earlier_rail_this_run"] += 1
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
                "forest, not a single tree. Fallback _blocked() reject "
                "attribution (first-match-wins, counts intersection TESTS "
                "not unique edges -- one edge/candidate can trip multiple "
                "reasons across its p1/p2 sub-tests): %s.",
                net_name,
                crossed_keepout,
                rerouted,
                _block_reason_counts,
            )

        # SUMMARY (2026-08-18, vcc/V_BUS_SENSE zero-backbone root-cause
        # task): always logged (not gated on crossed_keepout>0) -- the
        # per-rail attempted-vs-landed ratio is exactly the number this
        # generator was already computing (PowerIslandResult's own
        # fields) but never surfacing anywhere production reads; the
        # caller (`_adapter_convert.route_pcb`) discards the per-net
        # results dict entirely (`_island_reports`, underscore-prefixed).
        # `_ground_plane.py` has the identical gap for gnd -- see that
        # module's own new summary line, added alongside this one.
        logger.warning(
            "generate_power_islands_content(%s): backbone summary -- "
            "%d pad(s), %d MST edge(s) attempted, %d landed via corridor-"
            "aware A* (real, collision-free multi-hop paths), %d landed "
            "via the keepout-only straight-line/one-bend-detour fallback, "
            "%d DROPPED entirely (0 backbone connectivity between those "
            "two endpoints on this run).",
            net_name,
            len(positions),
            len(edges),
            astar_routed_count,
            rerouted,
            crossed_keepout,
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

    return new_blocks, results


def generate_power_islands_content(
    pcb_path: Path,
    *,
    nets: tuple[str, ...] = POWER_ISLAND_NETS,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
    segments: list[str] | None = None,
) -> tuple[str, dict[str, PowerIslandResult]]:
    """Standalone/CLI entry point: read *pcb_path*, compute the ``In2.Cu``
    power-island blocks (via ``generate_power_islands_blocks``), splice
    them into the file's own content, and return ``(new board content,
    {net_name: PowerIslandResult})``.

    This is the surface the standalone spike and the spike tests use.
    Production goes through ``generate_power_islands_blocks`` instead
    (from ``_write_routes_to_content``), because the routed board's
    content string is assembled in memory -- splicing back into the
    file's own text would drop the routing segments.
    """
    content = pcb_path.read_text()
    blocks, results = generate_power_islands_blocks(
        pcb_path, nets=nets, domain_manifest_path=domain_manifest_path, segments=segments
    )
    new_content = content.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(blocks) + "\n)\n"

    return new_content, results
