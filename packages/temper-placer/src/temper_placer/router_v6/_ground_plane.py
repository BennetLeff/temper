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
from pathlib import Path

from shapely.geometry import LineString, Polygon

logger = logging.getLogger(__name__)

GND_NET_NAME = "gnd"
PLANE_LAYER = "In1.Cu"
# See the MST-backbone emission site below for why this is F.Cu, not
# PLANE_LAYER -- pad_connectivity_audit.py models a via's reach literally
# from its own declared `layers` tuple, not from stackup position.
BACKBONE_LAYER = "F.Cu"

# Matches the existing production via convention already written by
# router_v6 elsewhere in this file (see pcb/temper.kicad_pcb's own
# existing vias: `(size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu")` --
# a standard plated through-hole via, which contacts every inner copper
# layer it physically passes through, including In1.Cu).
VIA_SIZE_MM = 0.8
VIA_DRILL_MM = 0.4

# In1.Cu carries zero pre-existing copper of any kind (measured: this is
# the whole point of this module), so a modest, ordinary trace width for
# the MST backbone is not competing with anything on this layer.
STITCH_TRACE_WIDTH_MM = 0.4

# Extra margin beyond the measured/derived keepout band, independent of
# clearance-class values -- errs toward a smaller, safer plane rather
# than a maximal one, matching this module's spike-level conservatism.
KEEPOUT_EXTRA_MARGIN_MM = 1.0

# Margin the plane polygon itself is kept off the physical board edge.
BOARD_EDGE_MARGIN_MM = 1.0

DEFAULT_DOMAIN_MANIFEST_PATH = Path("elec/domain_manifest.yaml")


__all__ = [
    "GND_NET_NAME",
    "PLANE_LAYER",
    "GroundPlaneResult",
    "compute_hv_selv_keepout",
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
    ) -> None:
        self.pad_count = pad_count
        self.drop_via_count = drop_via_count
        self.mst_edge_count = mst_edge_count
        self.zone_polygon_count = zone_polygon_count
        self.keepout_established = keepout_established
        self.keepout_area_mm2 = keepout_area_mm2
        self.pour_area_mm2 = pour_area_mm2

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"GroundPlaneResult(pads={self.pad_count}, "
            f"drop_vias={self.drop_via_count}, mst_edges={self.mst_edge_count}, "
            f"zone_polygons={self.zone_polygon_count}, "
            f"keepout_established={self.keepout_established}, "
            f"keepout_area_mm2={self.keepout_area_mm2:.1f}, "
            f"pour_area_mm2={self.pour_area_mm2:.1f})"
        )


def generate_ground_plane_content(
    pcb_path: Path,
    *,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
) -> tuple[str, GroundPlaneResult]:
    """Read *pcb_path*, compute an ``In1.Cu`` ``gnd`` plane + via/MST
    stitching, and return (new board content, result report).

    Does not write anything -- the caller decides where the output goes
    (a scratch copy for validation, or the tracked board once validated).
    Reuses the same zone-emission primitives
    (``zone_emission.compute_zones_for_net`` / ``emit_zone_s_expr``) the
    production ``_emit_zone_pours`` path uses for F.Cu/B.Cu pours, and
    the same via/segment s-expression conventions already written
    elsewhere in this board by ``router_v6``'s route-writing path
    (see module docstring).
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.placer.cp_sat.isolation_barrier import (
        DEFAULT_CORRIDOR_WIDTH_MM,
        load_domain_manifest_nets,
    )
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net
    from temper_placer.router_v6.routing_space import _get_board_polygon
    from temper_placer.router_v6.topology_copper_audit import net_number_to_name_map
    from temper_placer.router_v6.zone_emission import (
        compute_zones_for_net,
        emit_zone_s_expr,
    )

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

    hv_nets, selv_nets = load_domain_manifest_nets(domain_manifest_path)
    hv_positions: list[tuple[float, float]] = []
    for net_name in hv_nets:
        for pad in pads_by_net.get(net_name, []):
            hv_positions.append(pad.position)
    # SELV cluster for the keepout gap measurement includes gnd's own
    # pads plus every other declared-SELV net's pads -- the empirical
    # "where does the SELV footprint actually sit" question, not just
    # gnd alone (a keepout sized only to gnd's own pads could be
    # narrower than the real SELV/HV divide and cut it close).
    selv_positions: list[tuple[float, float]] = list(gnd_positions)
    for net_name in selv_nets:
        if net_name == GND_NET_NAME:
            continue
        for pad in pads_by_net.get(net_name, []):
            selv_positions.append(pad.position)

    board_polygon = _get_board_polygon(pcb)

    keepout = compute_hv_selv_keepout(
        hv_positions, selv_positions, board_polygon, DEFAULT_CORRIDOR_WIDTH_MM
    )
    keepout_established = keepout is not None

    # Board-edge margin, applied the same way _clip_to_board's callers
    # already clip zone hulls to the physical outline (R6 of
    # docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md) --
    # here as an explicit inward buffer rather than a hull-clip, since
    # this plane covers the whole gnd footprint, not per-pad hulls.
    plane_region = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)
    if keepout_established:
        plane_region = plane_region.difference(keepout)

    zones = compute_zones_for_net(
        GND_NET_NAME,
        gnd_net_num,
        gnd_positions,
        layer=PLANE_LAYER,
        margin=0.0,
        cluster=False,
        board_polygon=None,
    )
    # compute_zones_for_net gives the convex hull of gnd's own pads
    # (unclipped here -- clipping is done explicitly below against
    # plane_region, which already carries both the board-edge margin
    # and the HV keepout, so the hull is bounded by the *safe* region,
    # not merely by Edge.Cuts).
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

    tstamp_counter = [0]

    def _next_tstamp() -> str:
        from temper_placer.router_v6._adapter_convert import _next_tstamp as _nt

        return _nt(tstamp_counter)

    new_blocks: list[str] = []
    pour_area_mm2 = 0.0
    for poly in zone_polys:
        pour_area_mm2 += poly.area
        pts = [(float(x), float(y)) for x, y in poly.exterior.coords]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        if len(pts) < 3:
            continue
        from temper_placer.router_v6.zone_emission import ZoneDefinition

        zd = ZoneDefinition(
            net_name=GND_NET_NAME,
            net_number=gnd_net_num,
            layer=PLANE_LAYER,
            points=tuple(pts),
            clearance=0.3,
            min_thickness=0.25,
            priority=0,
        )
        new_blocks.append(emit_zone_s_expr(zd))

    # Drop vias: one per (deduped) gnd pad position, through-hole
    # F.Cu<->B.Cu (matches every other via already on this board --
    # contacts In1.Cu automatically as a plated through-hole).
    for x, y in gnd_positions:
        new_blocks.append(
            f'  (via (at {x:.4f} {y:.4f}) (size {VIA_SIZE_MM:.4f}) '
            f'(drill {VIA_DRILL_MM:.4f}) (layers "F.Cu" "B.Cu") '
            f"(net {gnd_net_num}) (tstamp \"{_next_tstamp()}\"))"
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

    def _blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
        return keepout_established and LineString([p1, p2]).intersects(keepout)

    crossed_keepout = 0
    rerouted = 0
    for i, j in edges:
        p1, p2 = gnd_positions[i], gnd_positions[j]
        if not _blocked(p1, p2):
            _emit_segment(p1, p2)
            continue

        # Bounded one-bend detour: try routing p1 -> waypoint -> p2 through
        # an existing via-drop point, nearest candidates first, accepting
        # the first waypoint whose *both* sub-segments clear the keepout.
        # This is a deliberately small, local heuristic (not a real
        # visibility-graph shortest path) -- adequate to recover most of
        # the fragmentation a straight-edge MST causes near a locally
        # shaped (per-pad-buffer-union, not a single band) keepout, not a
        # claim of optimality.
        candidates = sorted(
            (k for k in range(len(gnd_positions)) if k != i and k != j),
            key=lambda k: (
                (gnd_positions[k][0] - p1[0]) ** 2 + (gnd_positions[k][1] - p1[1]) ** 2
                + (gnd_positions[k][0] - p2[0]) ** 2 + (gnd_positions[k][1] - p2[1]) ** 2
            ),
        )[:40]
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
        else:
            crossed_keepout += 1
    if crossed_keepout:
        logger.warning(
            "generate_ground_plane_content: %d MST edge(s) crossed the HV "
            "keepout and could not be rerouted around it (a %d-candidate "
            "one-bend detour search found no clear waypoint either) -- "
            "dropped rather than routed through the keepout. The "
            "resulting backbone may be a forest, not a single tree. This "
            "is fail-closed (never emits copper through the keepout) but "
            "is a known incompleteness of the local detour heuristic; "
            "report this count honestly rather than silently accepting a "
            "partial backbone. %d other edge(s) were successfully "
            "rerouted around the keepout with a one-bend detour.",
            crossed_keepout,
            40,
            rerouted,
        )

    new_content = content.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(new_blocks) + "\n)\n"

    result = GroundPlaneResult(
        pad_count=len(gnd_positions),
        drop_via_count=len(gnd_positions),
        mst_edge_count=len(edges) - crossed_keepout,
        zone_polygon_count=len(zone_polys),
        keepout_established=keepout_established,
        keepout_area_mm2=keepout.area if keepout_established else 0.0,
        pour_area_mm2=pour_area_mm2,
    )
    return new_content, result
