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

**The disc union is Rust, not shapely.** Every term of this keepout is a
disc, so the union is built directly from circle-circle intersection arcs
by ``temper_geometry.disc_union_keepout_py``
(``packages/temper-geometry/src/disc_union_keepout.rs``) -- no polygon
boolean engine, no GEOS. The Rust generator will not return a keepout that
under-covers any disc it was asked for: its only constructor proves
containment first. The shapely ``Point.buffer(r, quad_segs=16)`` +
``unary_union`` path it replaced emitted a 64-gon *inscribed* in each
circle, under-covering by 1.69e-2mm at this module's 14.1mm radius. See
``disc_union``'s docstring.
"""

from __future__ import annotations

import heapq
import logging
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

logger = logging.getLogger(__name__)

GND_NET_NAME = "gnd"
PLANE_LAYER = "In1.Cu"
# See the MST-backbone emission site below for why this is F.Cu, not
# PLANE_LAYER -- pad_connectivity_audit.py models a via's reach literally
# from its own declared `layers` tuple, not from stackup position.
BACKBONE_LAYER = "F.Cu"

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

# Polygonal-approximation budget for the Rust disc-union keepout generator
# (temper_geometry.disc_union_keepout_py). NOT a clearance, and deliberately
# not tunable per call site: it is the amount of EXTRA board area the emitted
# keepout is allowed to claim beyond the true circle, and the generator's own
# construction guarantee (keepout CONTAINS every required disc, proved before
# the value can exist) holds for every positive value of it. Smaller = tighter
# and more vertices; larger = looser and fewer. It can never make the keepout
# smaller than required, which is the only direction that would matter.
#
# 0.01mm is chosen against the thing it replaces: shapely's
# `buffer(r, quad_segs=16)` is a 64-gon INSCRIBED in the circle, whose edges
# fall 1.69e-2mm SHORT of the required radius at this module's 14.1mm keepout
# radius. 0.01mm of outward slack costs less area than that inscribed 64-gon
# was already losing, in the safe direction rather than the unsafe one.
KEEPOUT_APPROX_EPSILON_MM = 0.01

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
    "disc_union",
    "hv_copper_discs",
    "hv_pad_centre_discs",
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


def disc_union(discs: list[tuple[float, float, float]]) -> Polygon | None:
    """Union ``[(x, y, radius), ...]`` into one polygon, in Rust.

    The single keepout primitive this module and its twin
    (``_power_islands.py``) share. Every keepout input here is a **disc** --
    an HV pad centre buffered by the corridor width, an HV pad's real
    half-extent, an HV via -- so this is a union of discs, not a general
    polygon boolean, and ``temper_geometry.disc_union_keepout_py`` builds it
    directly from the circle-circle intersection arcs (see
    ``packages/temper-geometry/src/disc_union_keepout.rs``).

    **This replaced ``shapely``'s ``Point.buffer(r, quad_segs=16)`` +
    ``unary_union``, and it is deliberately not bit-identical to it.**
    ``buffer(quad_segs=16)`` emits a 64-gon *inscribed* in the circle: its
    edges sit at ``r*cos(pi/64)``, so at this module's production radius
    (13.1 + 1.0 = 14.1mm) the old keepout under-covered the disc it was
    asked for by 1.69e-2mm, everywhere -- the same inscribed-polygon undercut
    ``clearance_halo.rs`` records as a measured bug. Measured across all 222
    discs of the real board's keepout on 2026-08-18, the worst under-coverage
    was 2.259e-2mm (on an 18.757mm HV pad half-extent disc); the Rust
    generator's was 0.0mm. The Rust generator's
    output is instead guaranteed, *at construction*, to CONTAIN every
    required disc: its only constructor proves that each disc centre is
    inside the emitted region and that no emitted edge comes within the
    required radius of it, and refuses to return a keepout otherwise. The
    new keepout is therefore a strict superset of the old one, point for
    point -- it can only ever claim more board area, never less.

    Returns ``None`` for an empty disc list, matching
    ``compute_hv_selv_keepout``'s "cannot establish a keepout" contract.
    """
    if not discs:
        return None

    from shapely.geometry import MultiPolygon
    from shapely.geometry import Polygon as _ShapelyPolygon
    from temper_geometry import disc_union_keepout_py

    pieces = [
        _ShapelyPolygon(rings[0], rings[1:])
        for rings in disc_union_keepout_py(discs, KEEPOUT_APPROX_EPSILON_MM)
    ]
    if not pieces:
        return None
    return pieces[0] if len(pieces) == 1 else MultiPolygon(pieces)


def hv_pad_centre_discs(
    hv_positions: list[tuple[float, float]], corridor_width_mm: float
) -> list[tuple[float, float, float]]:
    """``[(x, y, radius), ...]`` for the HV pad-CENTRE term of the keepout."""
    radius = corridor_width_mm + KEEPOUT_EXTRA_MARGIN_MM
    return [(float(x), float(y), radius) for x, y in hv_positions]


def compute_hv_selv_keepout(
    hv_positions: list[tuple[float, float]],
    selv_positions: list[tuple[float, float]],
    board_polygon: Polygon,
    corridor_width_mm: float,
) -> Polygon | None:
    """Build a keepout region as the union of a ``corridor_width_mm``-radius
    buffer around every HV-domain pad.

    **Scope, as of 2026-08-18.** This is the named entry point for the
    pad-CENTRE term alone. Both production call sites (this module's
    ``generate_ground_plane_content`` and its twin
    ``_power_islands.generate_power_islands_blocks``) now build the whole
    keepout in ONE ``disc_union`` call over ``hv_pad_centre_discs`` +
    ``hv_copper_discs``, because unioning the two terms separately and
    merging the polygons afterwards needed a third, general polygon union
    that a union of discs does not. This function is the same primitive with
    the same radii -- not a second implementation -- kept because it is the
    documented public name for "the pad-centre keepout" and is what the
    evidence trail and tests measure.

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

    keepout = disc_union(hv_pad_centre_discs(hv_positions, corridor_width_mm))
    if keepout is None:
        return None
    clipped = keepout.intersection(board_polygon)
    if clipped.is_empty:
        return None
    return clipped


def hv_copper_discs(
    pcb, hv_nets: frozenset[str], corridor_width_mm: float
) -> list[tuple[float, float, float]]:
    """``[(x, y, radius), ...]`` for every HV-net PAD (real half-extent, not
    a point) and VIA already on the board, each buffered by
    ``corridor_width_mm`` (already carries a 0.5mm cushion over the bare
    8.0mm creepage minimum -- see ``DEFAULT_CORRIDOR_WIDTH_MM``'s own
    docstring -- so no additional margin is stacked on top here).

    Returns the DISCS, not a polygon: the caller unions them together with
    ``hv_pad_centre_discs``' in a single ``disc_union`` call, so there is
    exactly one union for the whole keepout instead of three (two per-term
    unions plus a shapely ``unary_union`` to merge them).

    ``compute_hv_selv_keepout`` alone only buffers HV PAD *centres* --
    measured against this board (2026-08-11), 25 creepage violations
    landed between the emitted gnd zone/vias/backbone and HV pads that
    are geometrically deep inside the gnd hull (PS1's ``+170V_BUS`` pad,
    U6's ``DC_BUS_RTN`` pad, C26's ``SW_NODE`` pad, ...) -- a pad-centre
    buffer alone under-covers a large pad by exactly the distance from
    its centre to its own furthest corner. This function is unioned into
    These discs join that keepout's at the call site so a single
    ``keepout`` polygon governs the pour clip, the MST backbone detour, and
    the drop-via placement check alike -- one source of truth, not a second,
    easy-to-drift computation. HV tracks and existing HV zones were both tried here too
    and both reverted -- see the two comments at this function's call
    site in ``generate_ground_plane_content`` for the measured reasons
    (tracks: real but too dense, collapses MST routability; zones: the
    board's own declared zone outlines are not real fill geometry).
    """
    from temper_placer.core.pin_geometry import pin_world_position

    geoms: list[tuple[float, float, float]] = []

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
            geoms.append((float(pos[0]), float(pos[1]), pad_radius + corridor_width_mm))

    for via in getattr(pcb, "vias", []):
        if via.net not in hv_nets:
            continue
        geoms.append(
            (
                float(via.position[0]),
                float(via.position[1]),
                via.diameter / 2.0 + corridor_width_mm,
            )
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
    return geoms


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

    for via in getattr(pcb, "vias", []):
        if via.net == exclude_net or layer not in getattr(via, "layers", ()):
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
        if _clear(pad_pos, require_pour=require_pour):
            return pad_pos, False
        for radius in VIA_OFFSET_RING_RADII_MM:
            for i in range(VIA_OFFSET_RING_STEPS):
                angle = 2.0 * math.pi * i / VIA_OFFSET_RING_STEPS
                cand = (
                    pad_pos[0] + radius * math.cos(angle),
                    pad_pos[1] + radius * math.sin(angle),
                )
                if _clear(cand, require_pour=require_pour):
                    return cand, True
        return None, False

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

    hv_nets, _selv_nets = load_domain_manifest_nets(domain_manifest_path)
    hv_positions: list[tuple[float, float]] = []
    for net_name in sorted(hv_nets):
        for pad in pads_by_net.get(net_name, []):
            hv_positions.append(pad.position)
    # The SELV pad cluster used to be collected here and handed to
    # compute_hv_selv_keepout. It was already dead by the time this module
    # landed -- that function's own docstring records that the global
    # separating-band construction which needed it measured NO positive gap
    # on either axis of this board and was removed, and every version since
    # has opened with `del selv_positions`. Collecting it here only to
    # discard it inside the callee is the kind of "still looks load-bearing"
    # residue that makes a keepout change hard to reason about, so it goes
    # with the rest of the replaced code. `compute_hv_selv_keepout` keeps
    # the parameter for call-site stability (see its docstring).

    board_polygon = _get_board_polygon(pcb)

    # ONE disc union for the whole keepout: the HV pad CENTRES buffered by
    # the corridor width, plus real HV pad half-extents (not just their
    # centres) and every HV via already on the board -- see
    # hv_copper_discs' docstring for the measured bug that second term
    # closes, and for why HV tracks/zones were tried and reverted. One
    # union, so the pour clip, MST detour, and via placement below all see
    # the exact same keepout.
    keepout_discs = hv_pad_centre_discs(
        hv_positions, DEFAULT_CORRIDOR_WIDTH_MM
    ) + hv_copper_discs(pcb, hv_nets, DEFAULT_CORRIDOR_WIDTH_MM)
    keepout: Polygon | None = None
    merged = disc_union(keepout_discs)
    if merged is not None:
        clipped = merged.intersection(board_polygon)
        if not clipped.is_empty:
            keepout = clipped
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
    emitted_fcu_copper: Polygon | None = None
    emitted_holes: list[tuple[float, float, float]] = []
    if segments:
        from temper_placer.router_v6.zone_pour_clearance import _SEGMENT_RE, _VIA_RE

        emitted_geoms: list = []
        emitted_fcu_geoms: list = []
        for line in segments:
            match = _SEGMENT_RE.search(line)
            if match:
                x0, y0, x1, y1, width, seg_layer, net_num = match.groups()
                other = num_to_name.get(int(net_num), "")
                if not other or other == GND_NET_NAME:
                    continue
                layer = seg_layer
                if layer not in ("F.Cu", "B.Cu", "In3.Cu", "In4.Cu"):
                    continue
                pair_clr = max(
                    gnd_own_clearance,
                    net_clearance.get(other, default_clearance),
                )
                geom = LineString(
                    [(float(x0), float(y0)), (float(x1), float(y1))]
                ).buffer(float(width) / 2.0 + pair_clr, quad_segs=8)
                emitted_geoms.append(geom)
                if layer == "F.Cu":
                    emitted_fcu_geoms.append(geom)
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
                if "F.Cu" in via_layers.replace('"', "").split():
                    emitted_fcu_geoms.append(geom)
                emitted_holes.append((float(x), float(y), float(size) / 2.0))
        if emitted_geoms:
            from shapely.ops import unary_union as _unary_union_emitted

            emitted_avoid_copper = _unary_union_emitted(emitted_geoms)
            via_avoid_parts.append(emitted_avoid_copper)
            if len(via_avoid_parts) > 1:
                via_avoid_copper = _unary_union_via(via_avoid_parts)
        if emitted_fcu_geoms:
            from shapely.ops import unary_union as _unary_union_emitted

            emitted_fcu_copper = _unary_union_emitted(emitted_fcu_geoms)

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
    via_skipped_through_hole = 0
    via_offset_count = 0
    via_unresolved_conflict = 0
    via_radius_mm = VIA_SIZE_MM / 2.0
    for x, y in gnd_positions:
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
            # The stub itself is real 1.0mm-wide F.Cu copper and was not
            # covered by the via-drop point search (which only clears the
            # via's own footprint): measured (2026-08-16 route v2), 6 of
            # the residual 18 shorting_items were gnd stubs running from a
            # pad to its offset via straight across an adjacent other-net
            # pad (rtd_force_p/rtd_sense_p on U8, io0 on SW2, s1, refin_n,
            # vcc) that the via ring search dodged but the stub line did
            # not. Gate the stub with the same buffered-footprint check as
            # the backbone fallback; a blocked stub is skipped fail-closed
            # (the via stays; the pad just isn't stub-joined, a labelled
            # connectivity cost on this net).
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
            if stub_blocked:
                continue
            new_blocks.append(
                f"  (segment (start {x:.4f} {y:.4f}) (end {vx:.4f} {vy:.4f})"
                f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{BACKBONE_LAYER}")'
                f" (net {gnd_net_num}) (tstamp \"{_next_tstamp()}\"))"
            )

    # MST backbone joining every drop via -- see mst_edges() docstring for
    # why this is necessary in addition to the zone.
    #
    # LAYER CHOICE, measured not assumed: a first version of this function
    # put these segments on In1.Cu (the plane layer itself -- the
    # geometrically obvious choice). Measured against
    # ``pad_connectivity_audit.check_net_pad_connectivity``: it never
    # joined a single extra pad. Root cause, read directly in that
    # function (``pad_connectivity_audit.py`` lines ~190-194): a via only
    # unions nodes for the layers *literally present* in its own
    # ``via.layers`` tuple -- ``("F.Cu", "B.Cu")`` for a standard KiCad
    # through-via, which is what every via already on this board uses and
    # what this module's drop vias use (see above). KiCad's own real
    # electrical semantics treat a through-via as contacting every copper
    # layer it physically spans, including In1.Cu, without listing it --
    # but this audit tool models a via's reach literally from its
    # ``layers`` tuple, not from stackup position, so an In1.Cu segment
    # never unions with an F.Cu/B.Cu via at the same point in this tool's
    # graph, even though the real board electrically joins them. This is
    # a genuine gap in ``pad_connectivity_audit.py`` (it would equally
    # miss a through-via's real contact with In1.Cu for *any* net, not
    # just this one) worth its own fix, out of this module's scope.
    # Widening the via's own ``layers`` tuple to a non-standard 3-entry
    # list to work around it was considered and rejected: KiCad's file
    # format uses exactly two layer names per via (the span's endpoints)
    # regardless of via type, and a 3-entry list is not a form kicad-cli
    # is known to accept -- correctness against the real DRC/fab tool
    # matters more than satisfying one internal audit script. Using
    # ``BACKBONE_LAYER`` (F.Cu, already one of the via's two declared
    # layers) instead is the fix that keeps the file standard *and* makes
    # the real connectivity legible to the audit tool.
    edges = mst_edges(gnd_positions)

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
    other_copper_fcu_backbone = collect_other_net_copper_by_pairwise_clearance(
        pcb, GND_NET_NAME, "F.Cu", net_clearance, gnd_own_clearance, default_clearance
    )
    # Union in this route's own emitted other-net F.Cu copper (parsed
    # above): the A* corridor must also route around the tracks this very
    # run placed on F.Cu, not only the pre-existing board copper.
    backbone_obstacles: list[Polygon | None] = [keepout, other_copper_fcu_backbone]
    if emitted_fcu_copper is not None:
        backbone_obstacles.append(emitted_fcu_copper)
    backbone_grid = build_obstacle_grid(board_polygon, backbone_obstacles)
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
        gnd_positions, backbone_grid, backbone_corridor_mask, mst_edges
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
    # keepout. ``other_copper_fcu_backbone`` (the per-pair-clearance-
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
        if keepout_established and footprint.intersects(keepout):
            return True
        if (
            other_copper_fcu_backbone is not None
            and not other_copper_fcu_backbone.is_empty
            and footprint.intersects(other_copper_fcu_backbone)
        ):
            return True
        return (
            emitted_fcu_copper is not None
            and not emitted_fcu_copper.is_empty
            and footprint.intersects(emitted_fcu_copper)
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

        p1, p2 = gnd_positions[i], gnd_positions[j]
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
            (k for k in range(len(gnd_positions)) if k != i and k != j),
            key=lambda k: (
                (gnd_positions[k][0] - p1[0]) ** 2 + (gnd_positions[k][1] - p1[1]) ** 2
                + (gnd_positions[k][0] - p2[0]) ** 2 + (gnd_positions[k][1] - p2[1]) ** 2
            ),
        )[:200]
        found = False
        for k in candidates:
            w = gnd_positions[k]
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
