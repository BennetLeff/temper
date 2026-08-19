"""In1.Cu ground-plane generation for the ``gnd`` net (spike/keepout-before-pour).

**Why this module exists.** ``pcb/temper.kicad_pcb`` declares ``In1.Cu``/
``In2.Cu`` as power-plane layers (commit ``c4956df66``), but that commit's
own message documents the declaration is inert: ``io/_parse_board.py``'s
``_extract_stackup`` never reads the raw per-layer role token at all --
layer role comes from zone content or structural position, never from the
board file's own ``(layers (1 "In1.Cu" power) ...)`` annotation. Separately,
``router_v6/_zone_pour_stitch.py::_zone_layers_for_net`` -- the *only* place
in the production ``route_pcb()`` path that emits ``(zone ...)`` geometry --
hardcodes its return value to ``["F.Cu", "B.Cu"]`` for every zone-eligible
net; there is no code path anywhere in ``router_v6`` capable of emitting a
zone on an inner layer. The correct architecture (GND -> In1.Cu plane,
power islands -> In2.Cu) is fully described in
``deterministic/stages/power_plane.py``, but that module belongs to the
``deterministic`` pipeline, which no production entry point invokes --
``scripts/route_board.py`` (the ``make route`` target) calls
``router_v6.adapter.route_pcb`` exclusively. router_v6 never inherited
inner-layer plane generation from the pipeline that has it.

This module is the first real inner-layer plane generator for router_v6:
a single, net-specific pour for ``gnd`` (net 50 on the production board,
86 pads -- the board's largest net, and the one with the least excuse
for having zero copper). It deliberately does **not** generalize
``_zone_layers_for_net`` to return inner layers for every zone-eligible
net class -- that is real-plane-geometry work (per-domain pours on
In2.Cu, thermal considerations, U4 of
``docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md``)
well beyond a spike's budget. This is deliberately narrow: one net, one
layer, reusing the isolation corridor as a hard keepout so the fix cannot
recreate the isolation-barrier problem it is adjacent to.

**Keepout-before-pour.** The keepout this module pours around is *not*
re-derived from scratch: it reuses ``isolation_barrier.py``'s own SSOT
constant (``DEFAULT_CORRIDOR_WIDTH_MM``, itself derived from
``MIN_BARRIER_WIDTH_MM``) and its own net-domain source of truth
(``load_domain_manifest_nets`` against ``elec/domain_manifest.yaml``).
What it does *not* reuse is ``add_isolation_barrier_to_model``'s live
CP-SAT solver run, and it does *not* attempt a single global barrier
band -- a first version tried exactly that (the axis-aligned-gap
construction the "Keepout-before-pour" section used to describe here)
and measured, directly against this board, that no such gap exists: the
HV and SELV pad clusters' bounding boxes overlap. This corroborates
``docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md``'s own
citation of the unmerged ``safety/mains-selv-isolation-barrier`` branch,
whose commit message reports no single axis-aligned line cleanly
separates this board's HV/SELV pads (28-32% misclassified at best).
``compute_hv_selv_keepout`` instead unions a
``DEFAULT_CORRIDOR_WIDTH_MM``-radius disc around *every individual*
HV-domain pad -- see that function's docstring for the full before/after
and why the per-pad construction is the more robust one for this board's
real, locally-interleaved geometry.
"""

from __future__ import annotations

import heapq
import logging
import math
from collections.abc import Callable
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

logger = logging.getLogger(__name__)

GND_NET_NAME = "gnd"
PLANE_LAYER = "In1.Cu"
# CHANGED 2026-08-19 (F.Cu -> PLANE_LAYER). See the MST-backbone emission
# site below for the full before/after; in short, the F.Cu choice rested
# on a `pad_connectivity_audit.py` limitation that was fixed five days
# after this module landed, and keeping the backbone on the board's most
# congested layer was what reduced it to a 53-component forest.
BACKBONE_LAYER = PLANE_LAYER
# The pad-to-offset-via stub is NOT on BACKBONE_LAYER: it exists to join a
# gnd pad to the drop via that had to move off the pad centre, and the pad
# is on F.Cu. A stub on an inner layer would touch neither. The via itself
# (a through-via) carries the join down to BACKBONE_LAYER.
STUB_LAYER = "F.Cu"

# RAISED size 0.8 -> 1.0mm 2026-08-13
# (docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md sec.6.1,
# docs/hardware/FAB_CAPABILITY.md): this constant is one of the two literal
# generators of the 44 vias measured on the real board -- the old 0.8mm
# pad / 0.4mm drill pair gave a 0.2mm annular ring, below JLCPCB's 2oz PTH
# annular-ring floor (0.254mm); every one of this module's stitching vias
# failed it. Drill is unchanged (0.4mm) -- this is a pure pad-geometry fix,
# not a current-capacity change. New pad = drill + 2 x 0.3mm ring target,
# the same board-wide 0.3mm-ring convention applied to every
# TEMPER_NET_CLASSES via_diameter (core/design_rules.py) and to
# _power_islands.py's identical constant below.
VIA_SIZE_MM = 1.0
VIA_DRILL_MM = 0.4

# In1.Cu carries zero pre-existing copper of any kind (measured: this is
# the whole point of this module), so a modest, ordinary trace width for
# the MST backbone is not competing with anything on this layer.
#
# RAISED 0.4 -> 1.0mm 2026-08-16 (full-route agent, fix/route-to-100-
# percent): the 0.4mm width violated the DRC's own netclass rule for
# gnd copper. pcb/temper.kicad_pro assigns gnd to the declared "GND"
# class (track_width 1.0mm), and the emitted DRU carries a "Ground trace
# width" rule at min 1.0mm -- measured on the 2026-08-16 capstone route:
# all 216 backbone/stub segments at 0.4mm were real track_width DRC
# violations (216 of the 747 uncapped total). 1.0mm matches both the
# GND-class SSOT width (design_rules TEMPER_NET_CLASSES["GND"]
# trace_width=1.0) and the Power-class width design_rules maps the net
# name "gnd" to; it is also a better fit for the backbone's actual role
# (real return-current copper, not just audit-visible topology). The
# corridor mask's erosion (compute_corridor_mask uses this same constant)
# tightens correspondingly; the keepout-only fallback and the drop-via
# stubs share the same width.
STITCH_TRACE_WIDTH_MM = 1.0

# Extra margin beyond the measured/derived keepout band, independent of
# clearance-class values -- errs toward a smaller, safer plane rather
# than a maximal one, matching this module's spike-level conservatism.
KEEPOUT_EXTRA_MARGIN_MM = 1.0

# Margin the plane polygon itself is kept off the physical board edge.
BOARD_EDGE_MARGIN_MM = 1.0

# --- DRC-cost fix constants (docs/evidence measured against this board,
# 2026-08-11: the +32 creepage/+77 hole_clearance/+32 tracks_crossing/+122
# clearance deltas from the first version of this module) --------------------

# Generic (non-HV) copper clearance this module keeps its own new copper
# (drop vias, MST backbone segments) away from every OTHER net's existing
# F.Cu/B.Cu copper. Not a creepage figure -- ordinary electrical clearance.
# Sized from this board's own netclasses (pcb/temper.kicad_pro
# net_settings.classes): Default 0.2mm, Power 0.5mm, GateDriveHV/SELV
# 0.25mm are the classes gnd's new copper can actually land next to (every
# HV-netclass pairing -- HighVoltage 2.0mm, HighVoltageIsolated/ACMains
# 6.0mm -- is already dominated by the much larger HV creepage keepout
# below, so this constant only has to cover the SELV-domain worst case).
# 0.5mm is that worst case with no extra headroom added, deliberately not
# padded further: padding it hurts MST routability (see
# mst_edges/_blocked's one-bend detour, which becomes less likely to find a
# clear waypoint as more of F.Cu is excluded) for diminishing DRC benefit
# once tracks_crossing (a strict topological violation) is fixed outright.
OTHER_NET_CLEARANCE_MM = 0.05

# Minimum edge-to-edge gap this module keeps between a new drop via's own
# drill and any EXISTING drilled hole (another net's via or through-hole
# pad) already on the board. Matches scripts/generate_kicad_dru.py's "PTH
# hole to hole" rule (0.5mm) -- the larger of its two hole rules
# (hole_clearance 0.25mm, hole_to_hole 0.5mm) -- used uniformly since a new
# via can be adjacent to either kind of existing hole.
MIN_HOLE_EDGE_GAP_MM = 0.5

# Ring-search radii/step-count for finding a clear via drop point near a
# gnd pad that DRU hole rules forbid dropping straight onto (see
# _find_via_drop_point). Small and local by design -- same
# deliberately-not-optimal-pathfinding spirit as mst_edges' one-bend
# detour: adequate to dodge an isolated nearby hole, not a router.
VIA_OFFSET_RING_RADII_MM = (0.6, 1.0, 1.5, 2.2)
VIA_OFFSET_RING_STEPS = 12

DEFAULT_DOMAIN_MANIFEST_PATH = Path("elec/domain_manifest.yaml")


__all__ = [
    "GND_NET_NAME",
    "PLANE_LAYER",
    "GroundPlaneResult",
    "compute_hv_selv_keepout",
    "generate_ground_plane_blocks",
    "generate_ground_plane_content",
    "mst_edges",
]


def _dedupe_positions(
    positions: list[tuple[float, float]], nd: int = 3
) -> list[tuple[float, float]]:
    seen: dict[tuple[float, float], tuple[float, float]] = {}
    for p in positions:
        seen[(round(p[0], nd), round(p[1], nd))] = p
    return list(seen.values())


def _ring_area(ring: list[tuple[float, float]]) -> float:
    """Shoelace absolute area of a closed ring (used for the Rust zone
    generator's outline rings, whose exterior/holes are open vertex lists)."""
    n = len(ring)
    s = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def mst_edges(positions: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Prim's-algorithm minimum spanning tree over *positions* (plain
    Euclidean, O(n^2) -- fine for the <=100-node counts this module
    handles; no external graph library needed).

    Returns index pairs into *positions*. A real filled zone already
    electrically joins every via that touches it, but
    ``pad_connectivity_audit.py`` (this project's declared PRIMARY
    completion metric, see
    ``docs/evidence/2026-08-11-true-pad-connectivity-baseline.md`` S:3)
    builds its connectivity graph *only* from explicit ``(segment ...)``/
    ``(via ...)`` geometry -- it does not parse zone polygons at all, by
    documented design. An MST backbone of real copper (segments on the
    plane layer, joining via drops at each pad) makes the connectivity
    genuinely visible to that tool, not merely visually/electrically
    true underneath an unparsed zone -- and it is real, valid copper on
    an otherwise-empty layer, not a metric-gaming artifact.
    """
    n = len(positions)
    if n < 2:
        return []
    in_tree = [False] * n
    best_cost = [float("inf")] * n
    best_from = [-1] * n
    best_cost[0] = 0.0
    edges: list[tuple[int, int]] = []
    heap: list[tuple[float, int]] = [(0.0, 0)]
    while heap:
        cost, u = heapq.heappop(heap)
        if in_tree[u]:
            continue
        in_tree[u] = True
        if best_from[u] != -1:
            edges.append((best_from[u], u))
        ux, uy = positions[u]
        for v in range(n):
            if in_tree[v]:
                continue
            vx, vy = positions[v]
            d = ((ux - vx) ** 2 + (uy - vy) ** 2) ** 0.5
            if d < best_cost[v]:
                best_cost[v] = d
                best_from[v] = u
                heapq.heappush(heap, (d, v))
    return edges


def compute_hv_selv_keepout(
    hv_positions: list[tuple[float, float]],
    selv_positions: list[tuple[float, float]],
    board_polygon: Polygon,
    corridor_width_mm: float,
) -> Polygon | None:
    """Build a keepout region as the union of a ``corridor_width_mm``-radius
    buffer around every HV-domain pad.

    **This function's first implementation tried a single global band**
    (whichever axis separates the HV and SELV pad clusters' *bounding
    boxes* with a positive gap, banding that gap). Measured directly on
    the real board: it finds **no positive gap on either axis** -- the
    HV and SELV pad bounding boxes overlap. This is not a bug in the
    gap search; it corroborates
    ``docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md`` S:1's
    citation of the unmerged ``safety/mains-selv-isolation-barrier``
    branch, whose own commit message reports that *no single
    axis-aligned line* separates this board's HV/SELV pads cleanly (28-
    32% misclassified at best) -- HV/SELV pad centroids are only ~5.9mm
    apart in places. A single global band is the wrong shape for this
    board's real geometry, not merely a harder search to tune.

    **Per-pad buffering instead:** the keepout is the union of a disc of
    radius ``corridor_width_mm`` (``isolation_barrier.py``'s own
    ``DEFAULT_CORRIDOR_WIDTH_MM`` SSOT, unless the caller overrides it)
    around every individual HV-domain pad. This has no "clean separating
    line" precondition -- it degrades gracefully to whatever the real,
    locally-interleaved HV/SELV geometry is, at the cost of being more
    locally conservative near any HV pad that sits close to the SELV
    cluster (exactly where a global band would have been *least* safe
    to draw thin). ``selv_positions``/``board_polygon`` are accepted for
    call-site stability with the (removed) global-band approach and to
    let a future revision reintroduce a band term; the current
    implementation does not use them beyond clipping the result to the
    board outline.

    Returns ``None`` only if there are zero HV pads to buffer -- a
    caller must treat that as "cannot establish a keepout," never as
    "no keepout needed."
    """
    del selv_positions  # not used by the per-pad-buffer construction
    if not hv_positions:
        return None

    from shapely.geometry import Point
    from shapely.ops import unary_union

    radius = corridor_width_mm + KEEPOUT_EXTRA_MARGIN_MM
    discs = [Point(x, y).buffer(radius, quad_segs=16) for x, y in hv_positions]
    keepout = unary_union(discs)
    clipped = keepout.intersection(board_polygon)
    if clipped.is_empty:
        return None
    return clipped


def _collect_hv_copper_geometry(
    pcb, hv_nets: frozenset[str], corridor_width_mm: float
) -> Polygon | None:
    """Union of every HV-net PAD (real half-extent, not a point) and VIA
    already on the board, each buffered by ``corridor_width_mm`` (already
    carries a 0.5mm cushion over the bare 8.0mm creepage minimum -- see
    ``DEFAULT_CORRIDOR_WIDTH_MM``'s own docstring -- so no additional
    margin is stacked on top here).

    ``compute_hv_selv_keepout`` alone only buffers HV PAD *centres* --
    measured against this board (2026-08-11), 25 creepage violations
    landed between the emitted gnd zone/vias/backbone and HV pads that
    are geometrically deep inside the gnd hull (PS1's ``+170V_BUS`` pad,
    U6's ``DC_BUS_RTN`` pad, C26's ``SW_NODE`` pad, ...) -- a pad-centre
    buffer alone under-covers a large pad by exactly the distance from
    its centre to its own furthest corner. This function is unioned into
    that keepout at the call site so a single ``keepout`` polygon governs
    the pour clip, the MST backbone detour, and the drop-via placement
    check alike -- one source of truth, not a second, easy-to-drift
    computation. HV tracks and existing HV zones were both tried here too
    and both reverted -- see the two comments at this function's call
    site in ``generate_ground_plane_content`` for the measured reasons
    (tracks: real but too dense, collapses MST routability; zones: the
    board's own declared zone outlines are not real fill geometry).
    """
    from shapely.ops import unary_union

    from temper_placer.core.pin_geometry import pin_world_position

    geoms: list = []

    for comp in getattr(pcb, "components", []):
        for pin in getattr(comp, "pins", []):
            if pin.net not in hv_nets:
                continue
            pos = pin_world_position(pin, comp)
            # Half-diagonal, not max(width, height)/2 -- the furthest
            # point on a rectangular pad from its own centre is a
            # corner, not an edge midpoint, and this buffer must fully
            # contain the pad's real extent before the creepage radius
            # is added on top of it.
            pad_radius = math.hypot(pin.width / 2.0, pin.height / 2.0)
            geoms.append(Point(pos).buffer(pad_radius + corridor_width_mm, quad_segs=16))

    for via in getattr(pcb, "vias", []):
        if via.net not in hv_nets:
            continue
        geoms.append(
            Point(via.position).buffer(via.diameter / 2.0 + corridor_width_mm, quad_segs=16)
        )

    # Existing HV *tracks* deliberately NOT included here either, for a
    # related but distinct reason from zones (below): measured directly,
    # this board's 412 HV-net tracks are real, correctly-transformed
    # copper (their buffered union's bounds track the board outline
    # exactly, unlike the zone outline data) -- but unioning a
    # creepage-radius buffer around all 412 of them covers 61% of the
    # board on its own, and combined with the pad/via buffers above,
    # pushes total keepout coverage to 80%. At that occupancy this
    # module's straight-line MST + small local one-bend detour (never a
    # general router) cannot find a path for all but a handful of the 85
    # backbone edges, which measured as a direct, severe REGRESSION in
    # gnd pad connectivity -- the project's own declared primary
    # completion metric -- not a DRC-only tradeoff. Between "creepage
    # fully closed against every HV track, connectivity collapses" and
    # "creepage closed against every HV PAD and VIA (already ~60% of the
    # measured violations), connectivity holds," this module chooses the
    # latter and reports the residual honestly rather than silently
    # trading away the metric this whole module exists to move. A future
    # revision that wants both needs real pathfinding (see this module's
    # own evidence trail on reusing router_v6.occupancy_grid +
    # corridor_erosion.rs) in place of the MST + local-detour heuristic,
    # not a wider keepout on top of the same heuristic.

    # Existing HV *zones* deliberately NOT included here. Measured directly
    # against this board (2026-08-11): DC_BUS_RTN's own declared zone
    # outline is a 5-vertex polygon reaching x=180.08/y=252.9 while the
    # board itself is x:20-172/y:20-254 -- drawn intentionally larger than
    # the board (a normal KiCad authoring pattern; the fill engine clips
    # to Edge.Cuts and to every other constraint at fill time). Buffering
    # that DECLARED, oversized outline by the creepage radius rather than
    # its much smaller REAL FILLED shape (which this module has no
    # reliable way to obtain without literally invoking KiCad's own fill
    # engine) measured 80%+ of the board excluded from every HV zone's
    # buffer combined, and creates that severe an SELV-vs-HV real
    # geometry only if this board's actual fill is that dense too -- ergo
    # unverifiable and untrustworthy as this module's keepout input.
    # Pads/tracks/vias above are real, already-placed copper with exact
    # positions, not a declared-and-later-clipped outline, which is why
    # they are trusted and zones are not. This is a known, honest
    # incompleteness (see generate_ground_plane_content's evidence
    # trail): a residual creepage violation directly against an existing
    # HV zone's real fill, near but not at an HV pad/track/via, is
    # possible and not covered by this function.
    if not geoms:
        return None
    return unary_union(geoms)


def _collect_other_net_copper(
    pcb, exclude_net: str, layer: str, clearance_mm: float
) -> Polygon | None:
    """Union of every pad/track/via belonging to a net OTHER than
    *exclude_net* that has copper on *layer*, each buffered by its own
    physical half-extent plus *clearance_mm*.

    Used to keep the MST backbone (F.Cu) and drop vias (F.Cu + B.Cu) off
    every other net's existing copper -- measured against this board
    (2026-08-11): the first version of this module placed both with zero
    awareness of anything already on F.Cu/B.Cu, landing 32 tracks_crossing
    and the bulk of a +122 clearance / +45 solder_mask_bridge delta
    against other nets' pads and tracks it never checked.
    """
    from shapely.ops import unary_union

    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    geoms: list = []
    for comp in getattr(pcb, "components", []):
        for pin in getattr(comp, "pins", []):
            if not pin.net or pin.net == exclude_net:
                continue
            raw_layer = pin_world_layer(pin)
            on_layer = raw_layer in ("all", "*.Cu", layer) or (
                isinstance(raw_layer, str) and "Through" in raw_layer
            )
            if not on_layer:
                continue
            pos = pin_world_position(pin, comp)
            pad_radius = max(pin.width, pin.height) / 2.0
            geoms.append(Point(pos).buffer(pad_radius + clearance_mm, quad_segs=8))

    for track in getattr(pcb, "tracks", []):
        if track.net == exclude_net or track.layer != layer:
            continue
        geoms.append(
            LineString([track.start, track.end]).buffer(
                track.width / 2.0 + clearance_mm, quad_segs=8
            )
        )

    # A via barrel is a cylinder: it is copper on every layer between its
    # declared endpoints, not only on the two it names. ``layer in
    # via.layers`` -- what this used to test -- is False for EVERY via on
    # this board when *layer* is an inner layer, because every via here is
    # a standard through-via declaring only ``("F.Cu", "B.Cu")``. That was
    # invisible while this function was only ever called for F.Cu/B.Cu;
    # it stops being invisible the moment a caller asks about In1.Cu (the
    # gnd plane's own layer, where 101 foreign-net vias sit inside the
    # pour outline). ``_via_is_on_layer`` is the span-aware SSOT for this
    # exact question -- see its docstring.
    from temper_placer.router_v6.zone_pour_clearance import _via_is_on_layer

    for via in getattr(pcb, "vias", []):
        if via.net == exclude_net or not _via_is_on_layer(getattr(via, "layers", ()), layer):
            continue
        geoms.append(Point(via.position).buffer(via.diameter / 2.0 + clearance_mm, quad_segs=8))

    if not geoms:
        return None
    return unary_union(geoms)


def _existing_drilled_holes(pcb, exclude_net: str) -> list[tuple[float, float, float]]:
    """``[(x, y, hole_radius_mm), ...]`` for every drilled hole already on
    the board (existing vias' drills, every through-hole pad's drill)
    belonging to a net other than *exclude_net*.

    Used so a new drop via never lands its own hole on top of, or too
    close to, a hole that is already there -- measured against this board
    (2026-08-11): the first version of this module dropped a via at every
    gnd pad position with zero check against what was already drilled,
    producing 12 holes_co_located (vias stacked exactly on gnd's own
    through-hole pads -- see ``generate_ground_plane_content``'s
    through-hole skip, a separate fix from this one) and most of a +77
    hole_clearance delta against OTHER nets' holes.
    """
    from temper_placer.core.pin_geometry import pin_world_position

    holes: list[tuple[float, float, float]] = []
    for via in getattr(pcb, "vias", []):
        if via.net == exclude_net:
            continue
        holes.append((via.position[0], via.position[1], via.drill / 2.0))

    for comp in getattr(pcb, "components", []):
        for pin in getattr(comp, "pins", []):
            if pin.net == exclude_net or not pin.net:
                continue
            if not getattr(pin, "is_pth", False):
                continue
            drill = getattr(pin, "drill", None)
            diameter = getattr(drill, "diameter", None) if drill is not None else None
            if not diameter:
                continue
            pos = pin_world_position(pin, comp)
            holes.append((pos[0], pos[1], diameter / 2.0))

    return holes


def _find_via_drop_point(
    pad_pos: tuple[float, float],
    *,
    existing_holes: list[tuple[float, float, float]],
    via_radius_mm: float,
    keepout: Polygon | None,
    other_copper: Polygon | None,
    board_polygon: Polygon,
    pour_region: Polygon | None = None,
    stub_clear: Callable[[tuple[float, float], tuple[float, float]], bool] | None = None,
) -> tuple[tuple[float, float] | None, bool]:
    """Find a point to drop a via that clears every existing hole (by
    ``MIN_HOLE_EDGE_GAP_MM``, edge to edge), the HV keepout, other nets'
    copper, and the board outline -- trying *pad_pos* itself first, then a
    small local ring search around it.

    ``pour_region`` (optional): the union of this run's OWN zone-fill
    outlines (exterior minus holes). When given, pour-INSIDE points are
    preferred (pass 1: pad_pos then ring, requiring the via footprint to
    sit inside the filled region, so the via's barrel actually touches the
    plane copper after fill -- measured 2026-08-16: vias placed against
    the ~9.5mm keepout alone land up to 12.6mm from HV copper, i.e.
    OUTSIDE the creepage-carved fill, and touch no plane at all). If no
    pour-inside point exists, pass 2 falls back to the keepout-clear-only
    behaviour (a via outside the pour can still be joined by the F.Cu MST
    backbone, so connectivity never regresses -- the plane just does not
    add to it).

    ``stub_clear`` (optional, 2026-08-19): ``(pad_pos, candidate) -> bool``,
    True when the caller can actually draw the pad-to-via stub for that
    candidate. **This is the ordering fix.** Without it this search picked
    a via position on its own criteria (hole / HV keepout / foreign copper
    / pour containment, all of the VIA'S OWN footprint), the caller
    emitted the via, and only THEN tested the stub -- so a candidate whose
    stub was blocked still won the search and still got a via. Measured on
    the 2026-08-19 In1.Cu backbone route (a71765efe): of gnd's 45 offset
    drop vias only 11 kept their stub, and 56 of 88 gnd pads ended with no
    conductor of any kind at the pad.

    Passing this predicate makes the ring search PREFER a candidate whose
    stub can be drawn, falling back to the first otherwise-legal
    candidate only when no such candidate exists. It relaxes no test: the
    caller's stub check is unchanged and still fail-closed, it has simply
    also run inside the search, before the via position is committed.

    Two measured facts fix this as a preference rather than a hard gate,
    and both contradict the obvious design -- record them here so the
    obvious design is not re-attempted:

    **1. Declining the via is NOT free, because the via is not useless.**
    "A via whose stub was dropped has copper on neither side" is false on
    this board. Measured on the a71765efe route: of gnd's 61 drop vias,
    56 carry an In1.Cu backbone segment and only 4 touch no copper at
    all. A stub-less via still joins the plane to itself; it just does
    not join its own pad. A variant of this function that returned
    ``None`` in that case declined 31 of 61 gnd vias and moved
    ``unconnected_items`` 304 -> 318 (gnd's own share 48 -> 62) while
    rescuing zero pads -- the In1.Cu backbone fell from 294 segments to
    196 and gnd's copper fragmented. Hence the fallback.

    **2. No search can rescue a blocked stub, and this is provable, not
    just unmeasured.** The stub is buffered by
    ``STITCH_TRACE_WIDTH_MM / 2`` (0.5mm) and the via by
    ``VIA_SIZE_MM / 2`` (0.5mm), and the stub's own line starts AT the
    pad centre -- so the stub footprint always CONTAINS the via footprint
    the pad centre would have had. A drawable stub therefore implies a
    copper-clear pad centre, for every candidate, at every radius, on
    every bearing. Contrapositive: once the pad centre is blocked by
    copper (rather than by a drilled hole or by falling outside the
    pour), every stub out of that pad is blocked too, and no amount of
    extra ring radii, finer angular steps, bent stubs or A* changes it.
    Measured against that proof on the production route: for all 31 gnd
    pads whose stub was dropped, a 360-bearing x 0.3-3.0mm sweep found
    zero drawable stubs -- ``maxreach = 0.00mm`` in every direction on
    every one of them. At a hypothetical 0.25mm stub width, 15 of the
    same 31 open up. The binding constraint is the stub's WIDTH, not the
    search.

    So this predicate's real value is correctness of ordering, not a
    number: a candidate that can be joined to its pad is now always
    preferred to one that cannot, which is what the caller wanted all
    along. On this board that preference changes nothing -- the routed
    output is byte-identical to a71765efe's -- because the set it prefers
    from is empty exactly where it matters.

    **Where the pads actually are, for whoever picks this up next.** Of
    the 31 gnd pads with a dropped stub, re-running the same sweep against
    F.Cu copper ALONE (rather than the production obstacle set, which is
    every layer's foreign copper unioned together) opens 8 of them at the
    full 1.0mm width. The stub is F.Cu-only copper; the other 23 are
    blocked by F.Cu itself, so for those F.Cu really is full. Two levers
    exist and neither is a search: make the stub's obstacle set match the
    layer the stub is on (worth 8), or narrow the stub (worth 15 at
    0.25mm). Both were deliberately left alone here -- the first is a
    fail-closed test and this change is not permitted to weaken one, the
    second is an ampacity decision.

    Returns ``(point, needs_stub)``: ``needs_stub`` is True when the
    returned point is not *pad_pos* itself, telling the caller to emit a
    short same-net stub segment so the via stays electrically joined to
    the pad (and so ``pad_connectivity_audit``'s exact-position node
    matching still unions them). Returns ``(None, False)`` if no clear
    point was found within the search -- the caller must skip the via
    rather than emit a colliding one (fail-closed, same discipline as the
    MST backbone's keepout detour).
    """

    def _clear(pt: tuple[float, float], *, require_pour: bool) -> bool:
        p = Point(pt)
        footprint = p.buffer(via_radius_mm, quad_segs=12)
        if not board_polygon.contains(footprint):
            return False
        if keepout is not None and footprint.intersects(keepout):
            return False
        if other_copper is not None and footprint.intersects(other_copper):
            return False
        if require_pour and pour_region is not None and not pour_region.contains(footprint):
            return False
        x, y = pt
        for hx, hy, hr in existing_holes:
            min_gap = via_radius_mm + hr + MIN_HOLE_EDGE_GAP_MM
            if ((x - hx) ** 2 + (y - hy) ** 2) ** 0.5 < min_gap:
                return False
        return True

    def _search(*, require_pour: bool) -> tuple[tuple[float, float] | None, bool]:
        # pad_pos itself needs no stub (the via lands ON the pad), so
        # stub_clear does not gate it -- only the offset candidates.
        if _clear(pad_pos, require_pour=require_pour):
            return pad_pos, False
        # Radius-major: the shortest usable offset wins, so the stub that
        # has to be drawn is the shortest one available. Every candidate
        # at radius r on bearing theta has a stub that is exactly the
        # radial segment of length r on that bearing, so a bearing blocked
        # near the pad is blocked at every radius -- which is why the
        # ANGULAR resolution, not the radius list, is the lever that finds
        # a drawable stub (see VIA_OFFSET_RING_STEPS).
        fallback: tuple[float, float] | None = None
        for radius in VIA_OFFSET_RING_RADII_MM:
            for i in range(VIA_OFFSET_RING_STEPS):
                angle = 2.0 * math.pi * i / VIA_OFFSET_RING_STEPS
                cand = (
                    pad_pos[0] + radius * math.cos(angle),
                    pad_pos[1] + radius * math.sin(angle),
                )
                if not _clear(cand, require_pour=require_pour):
                    continue
                if stub_clear is None or stub_clear(pad_pos, cand):
                    return cand, True
                # Legal for the via's own footprint, but the pad cannot be
                # joined to it. Keep looking for one that CAN be joined --
                # but remember this, because a via here is not worthless
                # (see the fallback note below).
                if fallback is None:
                    fallback = cand
        return (fallback, True) if fallback is not None else (None, False)

    if pour_region is not None:
        found = _search(require_pour=True)
        if found[0] is not None:
            return found
    return _search(require_pour=False)


def _emit_keepout_zone_s_expr(points: list[tuple[float, float]], layer: str, uuid: str) -> str:
    """A KiCad rule-area zone that forbids copper POUR FILL (only) inside
    *points* on *layer* -- independent, fill-time defense of the HV
    keepout, on top of (not instead of) clipping the pour outline itself.

    Necessary because ``generate_ground_plane_content``'s pour-clip step
    (``hull.intersection(plane_region)``) can legitimately produce a
    polygon with interior holes -- an HV pad buried deep inside the gnd
    hull, not near its edge, carves an island out of the middle of the
    clipped region rather than a bite out of its boundary -- and this
    module's zone emission (``zone_emission.ZoneDefinition``/
    ``emit_zone_s_expr``) has no representation for a hole, only a single
    exterior contour. Measured directly against this board (2026-08-11):
    dropping the hole in the emitted pour's own outline put solid gnd
    copper right back over PS1's ``+170V_BUS`` pad at a 2.0mm gap against
    an 8.0mm creepage requirement, despite ``keepout_established=True``
    and a mathematically correct 9.5mm-radius keepout disc around that
    exact pad. This keepout zone is independent of that outline
    computation entirely -- it tells KiCad's own fill engine directly "no
    copper pour here," so it holds even if a future change to the pour
    outline logic reintroduces the same class of bug. Only ``copperpour``
    is forbidden (tracks/vias/pads/footprints stay ``allowed``) so it
    never flags anything already validly on the board; net 0 / empty
    net_name is the standard KiCad convention for a rule-area zone that
    is not itself a copper pour for any one net.
    """
    pts = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in points)
    return (
        f'  (zone (net 0) (net_name "") (layer "{layer}") (uuid "{uuid}") '
        f"(hatch edge 0.5) (priority 1000) "
        f"(connect_pads (clearance 0)) (min_thickness 0.254) "
        f"(keepout (tracks allowed) (vias allowed) (pads allowed) "
        f"(copperpour not_allowed) (footprints allowed)) "
        f"(fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) "
        f"(polygon (pts {pts})))"
    )


class GroundPlaneResult:
    """Small, explicit report of what ``generate_ground_plane_content``
    produced -- used by the caller to write an honest before/after
    evidence report rather than trusting silent success."""

    def __init__(
        self,
        *,
        pad_count: int,
        drop_via_count: int,
        mst_edge_count: int,
        zone_polygon_count: int,
        keepout_established: bool,
        keepout_area_mm2: float,
        pour_area_mm2: float,
        keepout_zone_count: int = 0,
        via_skipped_through_hole_count: int = 0,
        via_offset_count: int = 0,
        via_unresolved_conflict_count: int = 0,
        via_offset_stub_dropped_count: int = 0,
        mst_edges_astar_routed_count: int = 0,
        mst_edges_fallback_count: int = 0,
    ) -> None:
        self.pad_count = pad_count
        self.drop_via_count = drop_via_count
        self.mst_edge_count = mst_edge_count
        self.zone_polygon_count = zone_polygon_count
        self.keepout_established = keepout_established
        self.keepout_area_mm2 = keepout_area_mm2
        self.pour_area_mm2 = pour_area_mm2
        # Explicit fill-time keepout rule-area zones emitted on PLANE_LAYER
        # (see _emit_keepout_zone_s_expr) -- the creepage fix's own defense
        # layer, reported so a caller can see it actually fired.
        self.keepout_zone_count = keepout_zone_count
        # Vias NOT emitted because the gnd pad at that position is a
        # through-hole pad -- its own drilled hole already spans every
        # copper layer it lists (see generate_ground_plane_content), so a
        # separate via there is both redundant and the exact cause of the
        # holes_co_located violations measured 2026-08-11.
        self.via_skipped_through_hole_count = via_skipped_through_hole_count
        # Vias whose drop point had to move off the pad centre (with a
        # same-net stub segment back to it) to clear an existing hole or
        # other net's copper -- see _find_via_drop_point.
        self.via_offset_count = via_offset_count
        # Vias skipped entirely because no clear drop point (pad centre or
        # any ring-search offset) was found -- fail-closed, same as the
        # MST backbone's keepout detour; reported honestly rather than
        # emitting a known-colliding via.
        self.via_unresolved_conflict_count = via_unresolved_conflict_count
        # Offset drop vias that WERE emitted but whose pad-to-via stub
        # could not be drawn: the via joins the In1.Cu plane, the pad
        # does not join the via. Counted separately from
        # via_unresolved_conflict_count because they redirect to
        # different work -- that one means the DRILL has nowhere to go
        # (holes / HV keepout / outside the pour), this one means F.Cu
        # copper reaches the pad CENTRE, which by _find_via_drop_point's
        # stub-width proof makes the pad unreachable by ANY stub at
        # STITCH_TRACE_WIDTH_MM, from any via position, on any bearing.
        # Summing them into one 'skipped' would hide exactly the
        # distinction that says which lever to pull.
        self.via_offset_stub_dropped_count = via_offset_stub_dropped_count
        # MST edges that got a real, corridor-clean A* path (avoiding
        # both the HV keepout AND other nets' existing F.Cu copper) vs.
        # edges where no window (up to the whole board) found one, so
        # this edge fell back to the prior keepout-only straight-line/
        # one-bend-detour behaviour -- see _corridor_backbone.py's
        # module docstring for why this is a hybrid, not a full
        # replacement, and _blocked's `crossed_keepout`/`rerouted`
        # counts below for the fallback's own internal breakdown.
        self.mst_edges_astar_routed_count = mst_edges_astar_routed_count
        self.mst_edges_fallback_count = mst_edges_fallback_count

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"GroundPlaneResult(pads={self.pad_count}, "
            f"drop_vias={self.drop_via_count}, mst_edges={self.mst_edge_count}, "
            f"zone_polygons={self.zone_polygon_count}, "
            f"keepout_established={self.keepout_established}, "
            f"keepout_area_mm2={self.keepout_area_mm2:.1f}, "
            f"pour_area_mm2={self.pour_area_mm2:.1f}, "
            f"keepout_zones={self.keepout_zone_count}, "
            f"via_skipped_through_hole={self.via_skipped_through_hole_count}, "
            f"via_offset={self.via_offset_count}, "
            f"via_unresolved_conflict={self.via_unresolved_conflict_count}, "
            f"via_offset_stub_dropped={self.via_offset_stub_dropped_count}, "
            f"mst_edges_astar_routed={self.mst_edges_astar_routed_count}, "
            f"mst_edges_fallback={self.mst_edges_fallback_count})"
        )


def generate_ground_plane_blocks(
    pcb_path: Path,
    *,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
    tstamp_counter: list[int] | None = None,
    segments: list[str] | None = None,
) -> tuple[list[str], GroundPlaneResult]:
    """Compute an ``In1.Cu`` ``gnd`` plane + via/MST stitching and return
    the NEW s-expression blocks (zone / keepout-zone / via / segment
    strings) plus a result report.

    This is the production wiring seam: ``router_v6/_adapter_convert.py``'s
    ``_write_routes_to_content`` appends these blocks to its own emitted
    copper after the F.Cu/B.Cu pour pass, so the gnd plane rides every
    ``route_pcb()`` run (previously this generator was a standalone spike
    -- ``scripts/generate_ground_plane.py`` -- with no production caller).
    ``tstamp_counter`` is threaded from the caller (same convention as
    ``_emit_zone_pours``) so the plane's tstamps continue the caller's
    deterministic sequence instead of restarting at 0 and colliding with
    the routed content's; when ``None`` a fresh counter is used (the
    standalone script and the spike tests call it without one).

    ``segments``: the s-expression track/via strings THIS ROUTE already
    emitted (Stage 4's A* routes + the pour pass), threaded from
    ``_write_routes_to_content``. The plane generator re-reads the
    ORIGINAL board file (``pcb_path``), which cannot see that copper;
    without this parameter the drop vias and MST backbone would treat the
    route's own other-net tracks (F.Cu, and on the signal layers the
    through-vias physically span -- In3.Cu/In4.Cu) as empty space.
    Measured (2026-08-16 post-fix route): 61 of the residual
    shorting_items were gnd drop vias landing on / inside this route's
    In3.Cu/In4.Cu other-net tracks, and the backbone could still cross
    this route's F.Cu tracks. When provided, every other-net segment/via
    in *segments* is buffered by its real pairwise clearance and unioned
    into BOTH the via-placement obstacle set (all four layers the via's
    footprint spans) and the backbone obstacle grid/_blocked check
    (F.Cu). ``None`` (standalone/tests) preserves the pre-change
    original-board-only view.

    Does not write anything -- the caller decides where the output goes
    (a scratch copy for validation, or the tracked board once validated).
    The pour outline is computed by the Rust zone generator
    (``temper_geometry.pour_outline_py`` /
    ``emit_zone_outline_s_expr_py``, the #1257 machinery) carved at
    ``max(clearance, creepage)`` per foreign obstacle -- same as the
    production ``_emit_zone_pours`` path -- and the via/segment
    s-expression conventions are the same ones written elsewhere in this
    board by ``router_v6``'s route-writing path (see module docstring).
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.placer.cp_sat.isolation_barrier import (
        DEFAULT_CORRIDOR_WIDTH_MM,
        load_domain_manifest_nets,
    )
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net
    from temper_placer.router_v6.routing_space import _get_board_polygon
    from temper_placer.router_v6.topology_copper_audit import net_number_to_name_map

    # The default manifest path is CWD-relative, and production callers
    # (route_pcb via _write_routes_to_content) run from arbitrary CWDs
    # (pytest from packages/temper-placer, route_board.py from the repo
    # root). Resolve a missing relative default against the repo root
    # (this module lives at packages/temper-placer/src/temper_placer/
    # router_v6/, so the repo root is five parents up) before handing it
    # to the loader, which raises the honest FileNotFoundError if neither
    # location exists.
    if not domain_manifest_path.is_file() and not domain_manifest_path.is_absolute():
        alt = Path(__file__).resolve().parents[5] / domain_manifest_path
        if alt.is_file():
            domain_manifest_path = alt

    if tstamp_counter is None:
        tstamp_counter = [0]

    content = pcb_path.read_text()
    pcb = parse_kicad_pcb_v6(pcb_path)

    num_to_name = net_number_to_name_map(content)
    name_to_num = {v: k for k, v in num_to_name.items()}
    gnd_net_num = name_to_num.get(GND_NET_NAME)
    if gnd_net_num is None:
        raise ValueError(
            f"{GND_NET_NAME!r} not found in this board's (net ...) declarations"
        )

    pads_by_net = _pads_by_net(pcb)
    gnd_pads = pads_by_net.get(GND_NET_NAME, [])
    if not gnd_pads:
        raise ValueError(f"net {GND_NET_NAME!r} has zero pads on this board")
    gnd_positions = _dedupe_positions([p.position for p in gnd_pads])

    # Through-hole flag per (rounded) gnd position -- ANY pad at that
    # position being through-hole is enough, since its own drilled,
    # plated hole already spans every copper layer it lists (see the via
    # emission loop below for why this means "skip the via here").
    from temper_placer.router_v6.pad_connectivity_audit import ALL_LAYERS

    through_hole_positions: dict[tuple[float, float], bool] = {}
    for p in gnd_pads:
        key = (round(p.position[0], 3), round(p.position[1], 3))
        through_hole_positions[key] = through_hole_positions.get(key, False) or (
            p.layer == ALL_LAYERS
        )

    hv_nets, selv_nets = load_domain_manifest_nets(domain_manifest_path)
    hv_positions: list[tuple[float, float]] = []
    for net_name in sorted(hv_nets):
        for pad in pads_by_net.get(net_name, []):
            hv_positions.append(pad.position)
    # SELV cluster for the keepout gap measurement includes gnd's own
    # pads plus every other declared-SELV net's pads -- the empirical
    # "where does the SELV footprint actually sit" question, not just
    # gnd alone (a keepout sized only to gnd's own pads could be
    # narrower than the real SELV/HV divide and cut it close).
    selv_positions: list[tuple[float, float]] = list(gnd_positions)
    for net_name in sorted(selv_nets):
        if net_name == GND_NET_NAME:
            continue
        for pad in pads_by_net.get(net_name, []):
            selv_positions.append(pad.position)

    board_polygon = _get_board_polygon(pcb)

    keepout_pads = compute_hv_selv_keepout(
        hv_positions, selv_positions, board_polygon, DEFAULT_CORRIDOR_WIDTH_MM
    )
    # Extend the pad-centre-only keepout with real HV pad half-extents
    # (not just their centres) plus every HV via already on the board
    # (see _collect_hv_copper_geometry's docstring for the measured bug
    # this closes, and for why HV tracks/zones were tried and reverted).
    # One union, so the pour clip, MST detour, and via placement below
    # all see the exact same keepout.
    hv_extra = _collect_hv_copper_geometry(pcb, hv_nets, DEFAULT_CORRIDOR_WIDTH_MM)
    keepout_parts = [g for g in (keepout_pads, hv_extra) if g is not None]
    keepout: Polygon | None = None
    if keepout_parts:
        from shapely.ops import unary_union

        merged = unary_union(keepout_parts).intersection(board_polygon)
        if not merged.is_empty:
            keepout = merged
    keepout_established = keepout is not None

    # Board-edge margin, applied the same way _clip_to_board's callers
    # already clip zone hulls to the physical outline (R6 of
    # docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md) --
    # here as an explicit inward buffer rather than a hull-clip, since
    # this plane covers the whole gnd footprint, not per-pad hulls.
    plane_region = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)
    if keepout_established:
        plane_region = plane_region.difference(keepout)

    # Generic (non-HV) clearance from every OTHER net's existing copper --
    # separate from (much smaller than) the HV creepage keepout above, and
    # only used to steer the MST backbone (F.Cu) and drop vias (F.Cu +
    # B.Cu) around it, never to clip the pour itself (In1.Cu carries no
    # pre-existing copper of any kind, so there is nothing on that layer
    # for the pour to clash with).
    other_copper_fcu = _collect_other_net_copper(
        pcb, GND_NET_NAME, "F.Cu", OTHER_NET_CLEARANCE_MM
    )
    other_copper_bcu = _collect_other_net_copper(
        pcb, GND_NET_NAME, "B.Cu", OTHER_NET_CLEARANCE_MM
    )
    via_avoid_parts = [g for g in (other_copper_fcu, other_copper_bcu) if g is not None]
    via_avoid_copper: Polygon | None = None
    if via_avoid_parts:
        from shapely.ops import unary_union as _unary_union_via

        via_avoid_copper = _unary_union_via(via_avoid_parts)

    # THIS ROUTE'S OWN OTHER-NET COPPER (2026-08-16, fix/route-to-100-
    # percent): the generator re-reads the ORIGINAL board, which cannot
    # see the segments Stage 4 and the pour pass just emitted. Without
    # them, a gnd drop via (a through-via whose barrel physically spans
    # In3.Cu/In4.Cu) can land on top of this route's other-net tracks on
    # those layers, and the MST backbone can cross this route's other-net
    # F.Cu tracks -- measured 61 via-involved shorting_items on the
    # 2026-08-16 post-fix route. Parse *segments* (same regexes the zone
    # carve uses) and buffer each other-net item by its real pairwise
    # clearance (resolve_netclass_clearances' net_clearance, the same
    # kicad_pro-derived per-net map the A* corridor uses).
    from temper_placer.router_v6._corridor_backbone import resolve_netclass_clearances

    kicad_pro_path = pcb_path.with_suffix(".kicad_pro")
    net_clearance, default_clearance = resolve_netclass_clearances(kicad_pro_path)
    gnd_own_clearance = net_clearance.get(GND_NET_NAME, default_clearance)

    emitted_avoid_copper: Polygon | None = None
    # This run's own other-net copper that reaches BACKBONE_LAYER -- the
    # obstacle set for the MST backbone's A* corridor. With the backbone on
    # In1.Cu this is via barrels only (no route emits a track there), which
    # is precisely why the via test below is span-aware rather than a
    # literal ``"F.Cu" in via_layers`` membership check.
    emitted_backbone_layer_copper: Polygon | None = None
    emitted_holes: list[tuple[float, float, float]] = []
    if segments:
        from temper_placer.router_v6.zone_pour_clearance import (
            _SEGMENT_RE,
            _VIA_RE,
            _copper_stack_index,
            _via_is_on_layer,
        )

        emitted_geoms: list = []
        emitted_backbone_layer_geoms: list = []
        for line in segments:
            match = _SEGMENT_RE.search(line)
            if match:
                x0, y0, x1, y1, width, seg_layer, net_num = match.groups()
                other = num_to_name.get(int(net_num), "")
                if not other or other == GND_NET_NAME:
                    continue
                layer = seg_layer
                # Any COPPER layer counts. This list used to name only the
                # four router-signal layers, which silently excluded
                # In1.Cu/In2.Cu -- harmless while nothing emitted copper
                # there, and wrong the moment something does (this module's
                # own backbone now does). ``emitted_geoms`` feeds the
                # drop-via avoid set, and a through-via's barrel meets
                # copper on every layer it passes, plane layers included.
                if _copper_stack_index(layer) is None:
                    continue
                pair_clr = max(
                    gnd_own_clearance,
                    net_clearance.get(other, default_clearance),
                )
                geom = LineString(
                    [(float(x0), float(y0)), (float(x1), float(y1))]
                ).buffer(float(width) / 2.0 + pair_clr, quad_segs=8)
                emitted_geoms.append(geom)
                if layer == BACKBONE_LAYER:
                    emitted_backbone_layer_geoms.append(geom)
                continue
            match = _VIA_RE.search(line)
            if match:
                x, y, size, via_layers, net_num = match.groups()
                other = num_to_name.get(int(net_num), "")
                if not other or other == GND_NET_NAME:
                    continue
                pair_clr = max(
                    gnd_own_clearance,
                    net_clearance.get(other, default_clearance),
                )
                geom = Point(float(x), float(y)).buffer(
                    float(size) / 2.0 + pair_clr, quad_segs=8
                )
                emitted_geoms.append(geom)
                if _via_is_on_layer(tuple(via_layers.replace('"', "").split()), BACKBONE_LAYER):
                    emitted_backbone_layer_geoms.append(geom)
                emitted_holes.append((float(x), float(y), float(size) / 2.0))
        if emitted_geoms:
            from shapely.ops import unary_union as _unary_union_emitted

            emitted_avoid_copper = _unary_union_emitted(emitted_geoms)
            via_avoid_parts.append(emitted_avoid_copper)
            if len(via_avoid_parts) > 1:
                via_avoid_copper = _unary_union_via(via_avoid_parts)
        if emitted_backbone_layer_geoms:
            from shapely.ops import unary_union as _unary_union_emitted

            emitted_backbone_layer_copper = _unary_union_emitted(emitted_backbone_layer_geoms)

    existing_holes = _existing_drilled_holes(pcb, GND_NET_NAME)
    # Emitted vias' drills are real holes the drop-via search must respect
    # (hole-to-hole is unconditional in the DRU, same-net exempted for
    # gnd's own -- these are OTHER nets' drills).
    for hx, hy, hr in emitted_holes:
        existing_holes.append((hx, hy, hr))
    # NOTE (measured 2026-08-11): a variant of this function also built a
    # small buffered-hole region and blocked the MST backbone from
    # crossing it, hoping the hole set being small/sparse (dozens, not
    # thousands, unlike other_copper_fcu) would make it cheap. Measured:
    # it still cost 25 pads of connectivity (46 -> 21/86), because the
    # MST is a tree -- losing one "hub" edge disconnects everything
    # downstream of it, not just that edge's own two endpoints. Existing
    # holes are only checked against the (per-point, not per-path) via
    # placement search below, where losing one candidate point is cheap.

    # --- Rust zone-generator pour (2026-08-16): full-board region carved
    # at max(clearance, creepage) per obstacle, holes preserved. ---
    # Previously the pour was the convex hull of gnd's own pads clipped to
    # plane_region (Python `compute_zones_for_net` + single-ring
    # `emit_zone_s_expr`): a single-ring outline that (a) could not express
    # interior holes (an HV pad deep inside the hull stayed inside the
    # outline), (b) was carved only at the keepout's ~9.5mm standoff rather
    # than the 12.6mm pair creepage the DRC judges, and (c) fragmented the
    # FILL into separate unconnected plane pieces -- measured 2026-08-16 via
    # pcbnew's connectivity data on the definitive route: only 38/88 gnd
    # pads landed in the largest component after `--refill-zones`, because
    # the plane itself was several disconnected fill pieces, not one net.
    # The Rust generator (temper_geometry.pour_outline_py /
    # emit_zone_outline_s_expr_py, the #1257 production wiring) carves
    # every foreign obstacle's halo at that pair's max(clearance, creepage)
    # and emits one (polygon ...) element per ring (exterior + holes) --
    # the same machinery _emit_zone_pours uses, applied to the plane.
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
            GND_NET_NAME,
            PLANE_LAYER,
            pcb=pcb,
            segments=[],
            net_number_to_name=num_to_name,
            clearance_table=_zone_clearance_default_table(),
            creepage_table=default_creepage_table(),
        )
    ]
    own_rust = [(float(x), float(y)) for x, y in gnd_positions]

    # The pour REGION is the convex hull of gnd's own pads (UNCLIPPED) --
    # NOT the keepout-clipped safe region. Measured 2026-08-16: the Rust
    # generator's per-obstacle creepage halos (12.6mm HV-vs-LV) are
    # STRICTER than the 9.5mm keepout (corridor + margin) they replace,
    # so pre-clipping the hull to plane_region is redundant AND harmful:
    # the clip's boolean can split the hull into many pieces (measured 11)
    # that then pour separately and never touch, while the raw hull carves
    # into 2 islands covering 69/88 gnd pad positions (design doc §7A
    # shape: "pour pieces 6, gnd pads inside pour 67/88"). The keepout
    # rule-zones below remain as an independent fill-time defense.
    from shapely.geometry import MultiPoint as _MultiPoint

    hull_poly = _MultiPoint(own_rust).convex_hull
    region_parts = [hull_poly]
    pour_zone_rings: list[tuple[list, list]] = []  # (exterior, holes)
    pour_area_mm2 = 0.0
    for part in region_parts:
        if part.is_empty or not hasattr(part, "exterior"):
            continue
        rpts = [(float(x), float(y)) for x, y in part.exterior.coords]
        if len(rpts) > 1 and rpts[0] == rpts[-1]:
            rpts.pop()
        if len(rpts) < 3:
            continue
        pour_zones = _tg.pour_outline_py(rpts, own_rust, obstacle_records, 0.25 * 0.25, False)
        for zone_rings in pour_zones:
            exterior = zone_rings[0]
            holes = zone_rings[1:]
            if len(exterior) < 3:
                continue
            pour_zone_rings.append((exterior, holes))
            pour_area_mm2 += _ring_area(exterior) - sum(_ring_area(h) for h in holes)

    # tstamp_counter: threaded from the caller (production) or a fresh
    # [0] (standalone/tests) -- see generate_ground_plane_blocks' docstring.
    def _next_tstamp() -> str:
        from temper_placer.router_v6._adapter_convert import _next_tstamp as _nt

        return _nt(tstamp_counter)

    # Union of the carved pour outlines (exterior minus holes) -- the
    # fill's real copper footprint. Vias placed inside it touch the plane
    # after fill (see _find_via_drop_point's pour_region parameter); a via
    # outside it sits on the F.Cu backbone only.
    pour_region: Polygon | None = None
    if pour_zone_rings:
        from shapely.ops import unary_union as _unary_union_pour

        pour_geoms: list = []
        for exterior, holes in pour_zone_rings:
            hp = [list(h) for h in holes if len(h) >= 3]
            pour_geoms.append(Polygon(exterior, hp))
        merged = _unary_union_pour(pour_geoms)
        if not merged.is_empty:
            pour_region = merged

    new_blocks: list[str] = []
    for exterior, holes in pour_zone_rings:
        new_blocks.append(
            _tg.emit_zone_outline_s_expr_py(
                gnd_net_num,
                GND_NET_NAME,
                PLANE_LAYER,
                exterior,
                holes,
                0.3,
                0,
                0.25,
            )
        )

    # Explicit fill-time keepout zone(s) over the FULL HV keepout region on
    # PLANE_LAYER -- independent defense against a pour-outline hole
    # dropping bug (documented in _emit_keepout_zone_s_expr's docstring)
    # and against any residual carve imprecision: the Rust generator's
    # outline now carries interior holes, but the rule-area zone tells
    # KiCad's own fill engine "no copper pour here" unconditionally, so
    # the HV keepout holds even if a future outline change regresses.
    keepout_zone_count = 0
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
            keepout_zone_count += 1
            # A piece with its own interior holes (an SELV pocket fully
            # inside an HV-dense area) is vanishingly unlikely on this
            # board's geometry and, if it occurred, would only make the
            # keepout MORE conservative by being ignored here (the outer
            # boundary alone still forbids fill over the whole piece,
            # including the hole) -- never less safe, unlike the pour's
            # own hole-drop bug this function exists to fix.

    # Drop vias: one per (deduped) gnd pad position that is NOT itself a
    # through-hole pad. A through-hole gnd pad's own drilled, plated hole
    # (KiCad `(layers *.Cu ...)`) already spans every copper layer it
    # lists, including F.Cu (where the MST backbone below lands) and
    # In1.Cu (the plane) -- a separate via there is redundant AND, because
    # it lands its own drill exactly on top of the pad's existing drill,
    # is precisely the holes_co_located violation measured 2026-08-11 (12
    # instances, all gnd-vs-gnd). This costs nothing structurally:
    # pad_connectivity_audit already treats a through-hole pad's node as
    # present on every layer in the board's layer universe (see this
    # module's own MST-layer-choice comment below), so an MST segment
    # touching that pad's exact position on F.Cu unions with it with or
    # without a via.
    #
    # For every other (SMD) gnd pad, the via must not land on top of, or
    # too close to, an existing drilled hole or another net's copper
    # (measured 2026-08-11: zero such check produced most of a +77
    # hole_clearance delta). _find_via_drop_point tries the pad's own
    # position first, then a small local offset search; if the offset
    # differs from the pad position a same-net stub segment joins them so
    # connectivity is unaffected.
    #
    # ORDERING FIX (2026-08-19). "Connectivity is unaffected" was an
    # assumption, and on this board it was false. The stub is real
    # STITCH_TRACE_WIDTH_MM-wide F.Cu copper and the drop-point search
    # only ever cleared the VIA'S OWN footprint, so the stub was tested
    # after the fact and dropped when blocked. On congested F.Cu only 11
    # of ~45 offset stubs survived -- and a via whose stub was dropped has
    # copper on NEITHER side of the join, so it is simultaneously a
    # via_dangling finding and an unconnected_items finding: the same
    # physical non-connection, counted twice. Measured on a71765efe: 53 of
    # 88 gnd pads had no conductor at the pad at all, and 63 dangling vias
    # remained.
    #
    # The predicate below is now passed INTO the ring search, so a
    # candidate whose stub cannot be drawn is passed over in favour of one
    # whose stub can. Nothing about the test itself changed -- it is the
    # same buffered-footprint intersects test against the same keepout and
    # the same foreign-copper union, and it is still fail-closed. Only its
    # position in the ordering changed.
    #
    # MEASURED OUTCOME, so nobody re-litigates this: on this board the
    # reordering changes nothing, and that is the finding. All 31 of the
    # dropped stubs are unrescuable BY CONSTRUCTION, not by bad luck --
    # the stub's half-width equals the via's radius, so a drawable stub
    # implies a copper-clear pad centre, and every one of these 31 pads
    # has foreign copper reaching its centre. A 360-bearing x 0.3-3.0mm
    # sweep confirms it: maxreach = 0.00mm on all 31. See
    # _find_via_drop_point's ``stub_clear`` docs for the argument and the
    # numbers. The lever that WOULD move these pads is the stub's 1.0mm
    # width (15 of the 31 open up at 0.25mm), which is an ampacity
    # decision and is deliberately not made here.
    via_skipped_through_hole = 0
    via_offset_count = 0
    via_unresolved_conflict = 0
    via_offset_stub_dropped = 0
    via_radius_mm = VIA_SIZE_MM / 2.0

    # `prep`ared copies: the stub predicate runs up to
    # len(VIA_OFFSET_RING_RADII_MM) * VIA_OFFSET_RING_STEPS times per pad
    # instead of once, against unions with hundreds of parts. Preparing
    # them builds the STRtree index once and makes each `intersects` a
    # bounded query. Same geometry, same answers -- purely how the same
    # predicate is evaluated.
    from shapely.prepared import prep as _prep

    _prep_keepout = _prep(keepout) if keepout_established and keepout is not None else None
    _prep_via_avoid = (
        _prep(via_avoid_copper)
        if via_avoid_copper is not None and not via_avoid_copper.is_empty
        else None
    )

    def _stub_blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
        """Is the pad-to-via stub undrawable between these two points?

        The stub is real STITCH_TRACE_WIDTH_MM-wide copper, so the line is
        buffered by its own half-width before the intersects test -- the
        same discipline (and the same reason) as the MST backbone's own
        ``_blocked``. Fail-closed: anything this returns True for is never
        emitted.
        """
        footprint = LineString([p1, p2]).buffer(STITCH_TRACE_WIDTH_MM / 2.0)
        if _prep_keepout is not None and _prep_keepout.intersects(footprint):
            return True
        return _prep_via_avoid is not None and _prep_via_avoid.intersects(footprint)

    def _stub_drawable(pad_pt: tuple[float, float], via_pt: tuple[float, float]) -> bool:
        return not _stub_blocked(pad_pt, via_pt)

    # The nodes the MST backbone will actually span, in the order they are
    # established here. NOT ``gnd_positions``: the backbone runs on
    # BACKBONE_LAYER (In1.Cu), and an In1.Cu point only reaches this net's
    # copper where a PLATED BARREL passes through it. A gnd pad is F.Cu
    # copper, not In1.Cu copper -- so a backbone endpoint parked on a bare
    # pad position is floating metal on the plane layer, joined to nothing.
    # Measured directly, this was the entire reason the first In1.Cu
    # backbone attempt barely moved connectivity (5 -> 7 of 88 pads
    # despite 204 In1.Cu segments): 45 of 66 drop vias are OFFSET from
    # their pad, and every backbone edge terminating at those 45 pad
    # positions ended on bare In1.Cu. Only three kinds of point are real
    # nodes on this layer, and this list holds exactly those:
    #   * a through-hole gnd pad -- its own plated hole spans every copper
    #     layer it lists, so the pad position IS an In1.Cu node;
    #   * the drop point of a via this loop emits (a through-via);
    # and nothing else. A pad whose via was skipped fail-closed
    # (via_unresolved_conflict) contributes NO node -- there is no
    # conductor joining it to this layer, so spanning to it would emit
    # copper that cannot carry its current.
    #
    # On F.Cu (where this backbone used to run) the distinction did not
    # exist, because a pad position on F.Cu is the pad's own copper. That
    # is the one respect in which the old layer choice was load-bearing,
    # and it is a property of the node set, not of the layer.
    backbone_positions: list[tuple[float, float]] = []
    for x, y in gnd_positions:
        key = (round(x, 3), round(y, 3))
        if through_hole_positions.get(key, False):
            via_skipped_through_hole += 1
            backbone_positions.append((x, y))
            continue

        drop_point, needs_stub = _find_via_drop_point(
            (x, y),
            existing_holes=existing_holes,
            via_radius_mm=via_radius_mm,
            keepout=keepout if keepout_established else None,
            other_copper=via_avoid_copper,
            board_polygon=board_polygon,
            pour_region=pour_region,
            stub_clear=_stub_drawable,
        )
        if drop_point is None:
            via_unresolved_conflict += 1
            logger.warning(
                "generate_ground_plane_content: no clear via drop point "
                "found near gnd pad at (%.4f, %.4f) (pad centre and every "
                "ring-search offset conflict with an existing hole/HV "
                "keepout/other net's copper) -- skipping this via rather "
                "than emitting a known-colliding one.",
                x,
                y,
            )
            continue

        vx, vy = drop_point
        backbone_positions.append((vx, vy))
        new_blocks.append(
            f'  (via (at {vx:.4f} {vy:.4f}) (size {VIA_SIZE_MM:.4f}) '
            f'(drill {VIA_DRILL_MM:.4f}) (layers "F.Cu" "B.Cu") '
            f"(net {gnd_net_num}) (tstamp \"{_next_tstamp()}\"))"
        )
        # Register this via as an existing hole for every LATER via in
        # this same loop -- measured 2026-08-11: without this, two of
        # gnd's own offset-searched vias could independently converge on
        # points close enough to each other to violate hole_to_hole
        # (KiCad's "PTH hole to hole" DRU rule is unconditional, not
        # exempted for same-net holes).
        existing_holes.append((vx, vy, via_radius_mm))
        if needs_stub:
            via_offset_count += 1
            # The stub is real 1.0mm-wide F.Cu copper and this gate is
            # unchanged and still fail-closed: measured (2026-08-16 route
            # v2), 6 of the residual 18 shorting_items were gnd stubs
            # running from a pad to its offset via straight across an
            # adjacent other-net pad (rtd_force_p/rtd_sense_p on U8, io0
            # on SW2, s1, refin_n, vcc) that the via ring search dodged
            # but the stub line did not.
            #
            # What changed is that the SAME predicate now also ran inside
            # the drop-point search, as ``stub_clear``. So reaching here
            # with a blocked stub no longer means "nobody looked" -- it
            # means the search found no joinable candidate at all for this
            # pad and fell back to a legal-but-unjoinable one. See
            # _find_via_drop_point's ``stub_clear`` notes for the proof
            # that no search can do better once F.Cu copper reaches the
            # pad centre, and for why falling back beats declining. The
            # via still joins the In1.Cu plane; the unjoined pad is the
            # labelled, counted cost.
            if _stub_blocked((x, y), (vx, vy)):
                via_offset_stub_dropped += 1
                continue
            new_blocks.append(
                f"  (segment (start {x:.4f} {y:.4f}) (end {vx:.4f} {vy:.4f})"
                f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{STUB_LAYER}")'
                f" (net {gnd_net_num}) (tstamp \"{_next_tstamp()}\"))"
            )

    # One line that says what the drop-via pass actually achieved, since
    # the production caller (_adapter_convert) discards GroundPlaneResult.
    # Every gnd pad is accounted for by exactly one of these outcomes.
    logger.warning(
        "generate_ground_plane_content: %d gnd pad position(s) -> %d drop "
        "via(s), of which %d are offset from their pad; %d of those offsets "
        "got a stub back to the pad and %d could not (F.Cu copper reaches "
        "the pad centre, so no stub can leave it at %.2fmm width -- those "
        "vias join the plane but not their pad). %d through-hole pad(s) "
        "needed no via; %d pad(s) had no clear drill point at all.",
        len(gnd_positions),
        len(backbone_positions) - via_skipped_through_hole,
        via_offset_count,
        via_offset_count - via_offset_stub_dropped,
        via_offset_stub_dropped,
        STITCH_TRACE_WIDTH_MM,
        via_skipped_through_hole,
        via_unresolved_conflict,
    )

    # MST backbone joining every drop via -- see mst_edges() docstring for
    # why this is necessary in addition to the zone.
    #
    # LAYER CHOICE, measured not assumed -- and REVISED 2026-08-19 back to
    # PLANE_LAYER (In1.Cu). The history matters, because the reason this
    # was ever F.Cu no longer exists:
    #
    # The original note here (written with this module, ce4c132d6,
    # 2026-08-11) recorded that In1.Cu backbone segments "never joined a
    # single extra pad", root-caused to ``pad_connectivity_audit.py``
    # unioning a via's graph nodes only for the layers *literally present*
    # in its ``via.layers`` tuple -- ``("F.Cu", "B.Cu")`` for the standard
    # through-vias this module drops -- so an In1.Cu segment could never
    # meet an F.Cu/B.Cu via in that tool's graph. That was true when it
    # was written. It stopped being true five days later: ``dabbeaf73``
    # (2026-08-16) taught ``_parse_segments_and_vias`` KiCad's real via
    # typing -- an untyped ``(via ...)`` is a THROUGH via and is now
    # parsed as ``layers=()``, the ``CopperVia`` convention for "spans
    # every layer the checker knows about" -- so a through-via now unions
    # across the whole layer universe, In1.Cu included, exactly as the
    # physical board does. Nobody revisited this constant, and the
    # workaround outlived its cause.
    #
    # Keeping the backbone on F.Cu was not free. F.Cu carries 652 routed
    # segments and this module's own HV keepout covers 27499 mm^2 of the
    # board, so the corridor left for a 1.0mm gnd backbone is almost
    # nothing: measured on the committed board, 83 of 87 MST edges were
    # dropped fail-closed ("crossed the HV keepout or another net's
    # existing copper"), 1 got a corridor-clean A* path, and gnd's 61 drop
    # vias landed in 53 disconnected components -- 5 of 88 pads connected.
    # In1.Cu, by contrast, carries zero copper of any kind (that is this
    # module's whole premise), so the same A* runs against the HV keepout
    # and the foreign VIA BARRELS alone.
    #
    # Those barrels are the prerequisite, not a follow-up: 101 foreign-net
    # vias sit inside this pour's own outline, and until 2026-08-19
    # ``_via_is_on_layer`` short-circuited to False for In1.Cu/In2.Cu
    # (it indexed the ROUTER's signal-layer list, which excludes the two
    # declared-power layers), so no via was ever an obstacle here. Putting
    # copper on this layer without fixing that would have routed 1.0mm gnd
    # traces straight through other nets' via barrels. That predicate now
    # measures the span on the board's copper stack, and both
    # ``_collect_other_net_copper`` and
    # ``collect_other_net_copper_by_pairwise_clearance`` route their via
    # test through it, so ``other_copper_plane_backbone`` below really does
    # contain all 101.
    #
    # The pad-to-via stubs stay on ``STUB_LAYER`` (F.Cu) -- a gnd pad is
    # F.Cu copper, and the through-via is what carries the join down.
    edges = mst_edges(backbone_positions)

    def _emit_segment(p1: tuple[float, float], p2: tuple[float, float]) -> None:
        new_blocks.append(
            f"  (segment (start {p1[0]:.4f} {p1[1]:.4f}) (end {p2[0]:.4f} {p2[1]:.4f})"
            f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{BACKBONE_LAYER}")'
            f" (net {gnd_net_num}) (tstamp \"{_next_tstamp()}\"))"
        )

    # --- Corridor-aware A* pass: try a REAL, collision-avoiding path for
    # every MST edge first, over a grid that blocks the HV keepout AND
    # every other net's existing F.Cu copper (other_copper_fcu, already
    # computed above for via placement -- reused, not re-derived). This
    # is what actually fixes the tracks_crossing/clearance/
    # solder_mask_bridge deltas the straight-line MST causes; the
    # keepout-only detour below (unchanged) is the fallback for the
    # (measured, real -- see _corridor_backbone.py's docstring)
    # fraction of edges that are genuinely disconnected under full
    # corridor avoidance, so connectivity never regresses below the
    # prior, already-measured 46/86 floor.
    from temper_placer.core.topology import UnionFind
    from temper_placer.router_v6._corridor_backbone import (
        build_obstacle_grid,
        collect_other_net_copper_by_pairwise_clearance,
        compute_corridor_mask,
        corridor_aware_spanning_edges,
    )

    # A separate, per-net-pair-correct clearance polygon for the A*
    # obstacle grid -- NOT other_copper_fcu (built above at
    # OTHER_NET_CLEARANCE_MM=0.05mm for via placement). See
    # resolve_netclass_clearances's docstring for why a single flat
    # constant (0.05mm, or an earlier version of this fix that tried a
    # flat 0.5mm) is the wrong shape for this problem, not just the
    # wrong number: this board's real, kicad-cli-enforced clearance is
    # per NET-CLASS PAIR (0.2mm Default-vs-Default, 0.5mm against Power,
    # etc.), read directly from pcb/temper.kicad_pro -- the same file
    # kicad-cli itself resolves netclasses from. (net_clearance /
    # default_clearance / gnd_own_clearance are resolved ABOVE, in the
    # emitted-copper block, so both consumers share one resolution.)
    #
    # Built for BACKBONE_LAYER, not F.Cu (2026-08-19): the backbone now
    # lands on In1.Cu, so the copper it has to avoid is the copper on
    # In1.Cu -- which is exactly the foreign via barrels passing through
    # it, since no track on this board is on In1.Cu. That set is non-empty
    # only because `_via_is_on_layer` now measures a via's span on the
    # board's copper stack; see the MST-layer-choice note below.
    other_copper_plane_backbone = collect_other_net_copper_by_pairwise_clearance(
        pcb, GND_NET_NAME, BACKBONE_LAYER, net_clearance, gnd_own_clearance, default_clearance
    )
    # Union in this route's own emitted other-net copper that reaches
    # BACKBONE_LAYER (parsed above): the A* corridor must also route around
    # the vias this very run placed, not only the pre-existing board copper.
    backbone_obstacles: list[Polygon | None] = [keepout, other_copper_plane_backbone]
    if emitted_backbone_layer_copper is not None:
        backbone_obstacles.append(emitted_backbone_layer_copper)
    # The grid's free space is the board inset by BOARD_EDGE_MARGIN_MM, not
    # the raw outline. `plane_region` (the pour) has always used the inset;
    # the backbone grid did not, and while the backbone lived on F.Cu that
    # never showed, because F.Cu's own routed copper kept it away from the
    # edge anyway. On In1.Cu -- an empty layer -- A* will happily hug the
    # board outline: measured on the first In1.Cu route, 4 new
    # `copper_edge_clearance` violations, all "Track [gnd] on In1.Cu".
    # Reusing this module's own edge constant (1.0mm) rather than the DRU's
    # 0.5mm manufacturing floor keeps one knob for "how far this plane's
    # copper stays off the edge" and is the more conservative of the two.
    backbone_region = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)
    if backbone_region.is_empty:
        backbone_region = board_polygon
    backbone_grid = build_obstacle_grid(backbone_region, backbone_obstacles)
    backbone_corridor_mask = compute_corridor_mask(backbone_grid, STITCH_TRACE_WIDTH_MM)

    # Component-aware, not Euclidean-MST-topology-locked: attempting A*
    # only on the global Euclidean MST's own edge list measured (2026-08-12)
    # to solve just 15-33/85 edges with NO measurable DRC improvement --
    # root cause, confirmed with a no-backbone control run, is that the
    # violation mass concentrates on the specific MST edges crossing the
    # densest F.Cu congestion, which the Euclidean MST forces into its
    # topology regardless of corridor feasibility, while "easier" edges
    # elsewhere (which the MST also includes) were never the problem.
    # `corridor_aware_spanning_edges` instead builds a Euclidean MST
    # WITHIN each of the corridor mask's own connected components --
    # every such edge is between two points already known (by the mask's
    # own topology, not a search heuristic) to have SOME corridor-clean
    # path -- so it captures far more real, safe connectivity before the
    # keepout-only fallback below has to bridge genuinely disconnected
    # pieces. See _corridor_backbone.py's own docstring for the full
    # measurement.
    astar_routed_edges = corridor_aware_spanning_edges(
        backbone_positions, backbone_grid, backbone_corridor_mask, mst_edges
    )
    # Union-Find seeded with the component-local A* edges: the fallback
    # loop below must skip any GLOBAL MST edge whose endpoints are
    # ALREADY connected this way -- drawing it anyway would be pure
    # downside (adds collision risk for zero connectivity benefit).
    connectivity_uf = UnionFind()
    for i, j in astar_routed_edges:
        connectivity_uf.union(i, j)

    # UPDATED 2026-08-12 (was: "also routing the MST backbone around
    # every other net's existing F.Cu copper ... was tried here and
    # reverted"): that was true of the straight-line-MST-plus-one-bend-
    # detour heuristic specifically -- a real, component-aware
    # corridor-aware A* pass (astar_routed_edges, computed above) now
    # attempts exactly this, and succeeds for every pair of positions the
    # corridor mask's own connectivity actually supports (see
    # _corridor_backbone.py's docstring for the measured before/after and
    # why a naive per-Euclidean-MST-edge attempt undersells this). The
    # loop below is now the FALLBACK: it only has to bridge (a) edges
    # between DIFFERENT corridor-mask components (a genuine physical
    # disconnection under full clearance, not a search weakness) and (b)
    # the rare intra-component edge the bounded A* search itself could
    # not close.
    # UPDATED 2026-08-16 (fix/route-to-100-percent): the fallback now
    # ALSO avoids other nets' existing F.Cu copper, not just the HV
    # keepout. ``other_copper_plane_backbone`` (the per-pair-clearance-
    # buffered foreign-copper union computed above for the A* obstacle
    # grid -- reused, not re-derived) is now a second blocked-region
    # input, so a straight fallback edge that would cross another net's
    # copper is detoured or dropped instead of emitted as a
    # tracks_crossing/shorting line. Measured on the 2026-08-16 capstone
    # route: the 55.2mm straight fallback edge on F.Cu was the single
    # largest gnd shorting source (shorting hb-gnd's pad on T2). The
    # one-bend detour below shares the same check, so it can no longer
    # re-introduce a crossing through a waypoint either. Cost: strictly
    # fewer fallback edges emitted (fail-closed), reported honestly via
    # GroundPlaneResult.mst_edges_fallback_count/crossed_keepout --
    # connectivity for the affected pads is then carried by the In1.Cu
    # plane itself, which pad_connectivity_audit does not parse (its
    # documented zone-blindness gap), so a real, labelled connectivity
    # cost on this net is expected and preferred to emitting shorts.
    # NOTE (measured 2026-08-11): also routing the MST backbone around
    # every OTHER net's existing drilled holes (other_net_hole_avoid,
    # built above for exactly this) was tried here too and reverted --
    # despite the hole set itself being small/sparse, blocking even a
    # handful of specific MST edges cost 25 pads of connectivity (46 ->
    # 21/86) because the MST is a tree: losing one "hub" edge can
    # disconnect everything downstream of it, not just that edge's own
    # two endpoints. other_net_hole_avoid is still used for via placement
    # below, where losing one candidate point is cheap (fail closed for
    # that ONE via, not the whole backbone).
    def _blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
        # The REAL copper footprint, not the zero-width line: the emitted
        # segment is STITCH_TRACE_WIDTH_MM wide, so the line must be
        # buffered by its own half-width before the keepout/foreign-copper
        # intersects test -- measured (2026-08-16 post-fix route): an
        # unbuffered line that cleared C39's +3V3 pad's pairwise buffer by
        # 0.34mm was emitted as a 1.0mm-wide track whose edge cut 0.16mm
        # into that same buffer, a real shorting_items violation the
        # zero-width check could not see.
        footprint = LineString([p1, p2]).buffer(STITCH_TRACE_WIDTH_MM / 2.0)
        # Same board-edge inset the A* grid uses -- the straight-line
        # fallback bypasses that grid entirely, so without this a fallback
        # edge can still run off the inset region and land a
        # copper_edge_clearance violation.
        if not backbone_region.covers(footprint):
            return True
        if keepout_established and footprint.intersects(keepout):
            return True
        if (
            other_copper_plane_backbone is not None
            and not other_copper_plane_backbone.is_empty
            and footprint.intersects(other_copper_plane_backbone)
        ):
            return True
        return (
            emitted_backbone_layer_copper is not None
            and not emitted_backbone_layer_copper.is_empty
            and footprint.intersects(emitted_backbone_layer_copper)
        )

    # Emit every component-local A*-routed edge unconditionally -- these
    # are additional real connectivity beyond (and not necessarily a
    # subset of) the global Euclidean MST's own edge list.
    astar_routed_count = 0
    for (_i, _j), astar_path in astar_routed_edges.items():
        for a, b in zip(astar_path, astar_path[1:]):
            _emit_segment(a, b)
        astar_routed_count += 1

    crossed_keepout = 0
    rerouted = 0
    for i, j in edges:
        if connectivity_uf.find(i) == connectivity_uf.find(j):
            # Already joined by a component-local A*-clean edge (or a
            # chain of them) -- drawing this global-MST edge too would
            # only add collision risk for zero connectivity benefit.
            continue

        p1, p2 = backbone_positions[i], backbone_positions[j]
        if not _blocked(p1, p2):
            _emit_segment(p1, p2)
            connectivity_uf.union(i, j)
            continue

        # Bounded one-bend detour: try routing p1 -> waypoint -> p2 through
        # an existing via-drop point, nearest candidates first, accepting
        # the first waypoint whose *both* sub-segments clear the keepout.
        # This is a deliberately small, local heuristic (not a real
        # visibility-graph shortest path) -- adequate to recover most of
        # the fragmentation a straight-edge MST causes near a locally
        # shaped (per-pad-buffer-union, not a single band) keepout, not a
        # claim of optimality.
        # Candidate cap widened from 40 to 200 (2026-08-11): this board
        # has <= 86 gnd positions, so 200 is "effectively all of them,"
        # not a meaningfully different complexity bound (O(n) candidates
        # x O(1) blocked-check, still trivial at this n) -- measured to
        # recover a handful of otherwise-dropped MST edges (more of the
        # wider pad+via HV keepout's shape is reachable this way) without
        # touching any of the actual safety-relevant geometry.
        candidates = sorted(
            (k for k in range(len(backbone_positions)) if k != i and k != j),
            key=lambda k: (
                (backbone_positions[k][0] - p1[0]) ** 2 + (backbone_positions[k][1] - p1[1]) ** 2
                + (backbone_positions[k][0] - p2[0]) ** 2 + (backbone_positions[k][1] - p2[1]) ** 2
            ),
        )[:200]
        found = False
        for k in candidates:
            w = backbone_positions[k]
            if not _blocked(p1, w) and not _blocked(w, p2):
                _emit_segment(p1, w)
                _emit_segment(w, p2)
                found = True
                break
        if found:
            rerouted += 1
            connectivity_uf.union(i, j)
        else:
            crossed_keepout += 1
    if crossed_keepout:
        logger.warning(
            "generate_ground_plane_content: %d MST edge(s) crossed the HV "
            "keepout or another net's existing copper and could not be "
            "rerouted around it (a %d-candidate one-bend detour search "
            "found no clear waypoint either) -- dropped rather than "
            "routed through it. The resulting backbone may be a forest, "
            "not a single tree. This is fail-closed (never emits copper "
            "through the keepout or on top of other copper) but is a "
            "known incompleteness of the local detour heuristic; report "
            "this count honestly rather than silently accepting a "
            "partial backbone. %d other edge(s) were successfully "
            "rerouted around the obstruction with a one-bend detour.",
            crossed_keepout,
            200,
            rerouted,
        )

    result = GroundPlaneResult(
        pad_count=len(gnd_positions),
        drop_via_count=len(gnd_positions)
        - via_skipped_through_hole
        - via_unresolved_conflict,
        mst_edge_count=len(edges) - crossed_keepout,
        zone_polygon_count=len(pour_zone_rings),
        keepout_established=keepout_established,
        keepout_area_mm2=keepout.area if keepout_established else 0.0,
        pour_area_mm2=pour_area_mm2,
        keepout_zone_count=keepout_zone_count,
        via_skipped_through_hole_count=via_skipped_through_hole,
        via_offset_count=via_offset_count,
        via_unresolved_conflict_count=via_unresolved_conflict,
        via_offset_stub_dropped_count=via_offset_stub_dropped,
        mst_edges_astar_routed_count=astar_routed_count,
        mst_edges_fallback_count=len(edges) - astar_routed_count,
    )
    return new_blocks, result


def generate_ground_plane_content(
    pcb_path: Path,
    *,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
    segments: list[str] | None = None,
) -> tuple[str, GroundPlaneResult]:
    """Standalone/CLI entry point: read *pcb_path*, compute the In1.Cu
    ``gnd`` plane blocks (via ``generate_ground_plane_blocks``), splice
    them into the file's own content, and return ``(new board content,
    result report)``.

    This is the surface ``scripts/generate_ground_plane.py`` and the
    spike tests use. Production goes through
    ``generate_ground_plane_blocks`` instead (from
    ``_write_routes_to_content``), because the routed board's content
    string is assembled in memory -- splicing back into the file's own
    text would drop the routing segments.
    """
    content = pcb_path.read_text()
    blocks, result = generate_ground_plane_blocks(
        pcb_path, domain_manifest_path=domain_manifest_path, segments=segments
    )
    new_content = content.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(blocks) + "\n)\n"
    return new_content, result
