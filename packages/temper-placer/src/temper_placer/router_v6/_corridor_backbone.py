"""Corridor-aware A* routing for the In1.Cu/In2.Cu plane backbones.

**Why this module exists.** `_ground_plane.py` (#1022/#1033) and
`_power_islands.py` (#1047) both build their copper backbone the same way:
a minimum spanning tree (`mst_edges`) over pad/via-drop positions, then a
STRAIGHT LINE per MST edge, with only the HV/SELV keepout checked
(`_blocked`) and a bounded one-bend detour if a straight edge crosses it.
Neither generator's backbone ever avoids another net's *existing* F.Cu
copper -- both modules' own docstrings measure and document why: doing so
with the straight-line-plus-local-detour heuristic collapsed `gnd`
connectivity from 46/86 to 7/86, because F.Cu is dense enough (1193+
other-net tracks) that a straight edge with one bend essentially never
clears it, and the MST is a tree -- losing one "hub" edge disconnects
everything downstream of it.

A minimum spanning tree over pad positions carries no notion of occupancy;
adding local detours to a straight-line tree is a weak approximation of
routing. This module replaces the straight-line-plus-detour step with a
REAL pathfinding search -- reusing, not reimplementing, the two pieces of
existing infrastructure built for exactly this:

- `corridor_erosion.rs` (#1017) -- configuration-space erosion that
  matches `mark_path_rect`'s exact Chebyshev structuring element and
  exempts a net's own copper from the obstacle set.
- `astar_core._astar_search`'s `corridor_mask` parameter (also #1017) --
  the wiring that lets a real, `net_id >= 0` search consult an eroded
  corridor mask.

**The obstacle grid this module builds is deliberately narrow: existing
OTHER-net F.Cu copper (already buffered by ``OTHER_NET_CLEARANCE_MM`` --
the exact polygon ``_collect_other_net_copper`` already computes for via
placement, reused here rather than re-derived) plus the HV/SELV keepout
plus, for power islands, this run's own earlier-rail copper.** Passing
``clearance=0.0`` to `corridor_mask_for_net` and the net's own
``trace_width`` means erosion only has to add the trace's OWN half-width
(Chebyshev) on top of an obstacle boundary that already carries the
required standoff -- the same C-space composition
`docs/evidence/2026-08-11-corridor-aware-astar-spike.md` §6.2 describes,
applied here to a real production call site instead of a spike.

**Measured before wiring anything in** (this module's own construction,
`pcb/temper.kicad_pcb`, `gnd`, 2026-08-11): eroding F.Cu free space by
just the HV keepout + 0.05mm-buffered other-net copper fragments the
board into 73 disconnected components, and `gnd`'s 86 pads land in at
least 10 of them (the largest holds 25). This is a genuine physical
disconnection, not a search-strategy artifact -- no window size and no
smarter local search reconnects two different components, because by
construction no corridor-clean path between them exists on this layer at
this net's required clearance. This is why this module is a **hybrid**,
not a pure replacement: A* is attempted first (bounded, growing local
windows, cheapest case first); an edge whose two endpoints are not
co-reachable under full corridor avoidance falls back to the existing
keepout-only straight-line/one-bend-detour helper each generator already
has (`_blocked`/one-bend loop, unchanged) -- so connectivity can only
improve edge-by-edge over the prior behaviour, never regress below it,
while every edge A* *can* solve gets a genuinely collision-free path
instead of an unconditionally straight one.
"""

from __future__ import annotations

import fnmatch
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import temper_geometry as _tg
from shapely import contains, points
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from temper_placer.router_v6.astar_core import _astar_search
from temper_placer.router_v6.corridor_erosion import corridor_mask_for_net
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

# Cell size for the backbone-routing grid. Coarser than production's 0.1mm
# default (chosen, like the corridor-aware-astar-spike, to keep the
# pure-Python A* inner loop tractable at whole-board scope) -- a physical
# corridor at these trace widths (0.3-0.4mm) either fits a given gap or it
# doesn't, largely independent of grid discretization aside from
# quantization noise at the mm/5 scale.
CELL_SIZE_MM = 0.2

# Grid margin beyond the board outline -- cells outside the board polygon
# are always blocked (-1), so this only needs to be large enough that the
# raster boundary doesn't clip legitimate near-edge board area.
GRID_MARGIN_MM = 1.0

# Extra erosion margin correcting `build_obstacle_grid`'s centre-sampling
# quantization error (a cell is classified free/blocked by its centre
# point, so up to `CELL_SIZE_MM/sqrt(2)` of a cell's real footprint can
# be mis-rasterized free right at an obstacle boundary) -- see
# `compute_corridor_mask`'s docstring for the direct, measured evidence
# this closes a real (if small) under-coverage, not a theoretical one.
# Set equal to CELL_SIZE_MM: larger than the worst-case diagonal error
# (`CELL_SIZE_MM/sqrt(2) ≈ 0.141mm` at this module's cell size), so it
# fully covers the quantization gap with a small amount to spare.
RASTER_SAFETY_MARGIN_MM = CELL_SIZE_MM

# Bounded, growing local search windows (mm of padding around the
# straight-line bounding box of an edge's two endpoints), cheapest first.
# `None` means "the whole precomputed grid" -- the last resort before
# declaring an edge corridor-unroutable and falling back. Most MST edges
# are short/local (nearest-neighbour construction), so the common case
# resolves at the smallest window; a handful of longer edges need to grow.
WINDOW_PADDINGS_MM: tuple[float | None, ...] = (15.0, 40.0, 100.0, None)

# Fallback obstacle clearance for a net whose class cannot be resolved at
# all (should not happen for a real board -- `Default` is always present
# in `net_settings.classes` -- but a defensive floor is cheap insurance).
# NOT a reuse of `_ground_plane.OTHER_NET_CLEARANCE_MM` (0.05mm) -- see
# `resolve_netclass_clearances`'s docstring for why a single flat
# constant (that one, or an earlier version of this module that used a
# flat 0.5mm here) is the wrong shape for this problem at all, not just
# the wrong number: KiCad's real DRC clearance requirement is PER NET
# PAIR (`max` of the two nets' own netclass clearance), and this board
# has classes spanning 0.1mm (FinePitch) to 0.5mm (Power) outside the
# HV keepout's own scope -- a single flat constant is either too loose
# (under-covers Power-class pairs, the exact bug `OTHER_NET_CLEARANCE_MM`
# had) or too tight (over-constrains every Default-vs-Default pair,
# needlessly costing A* routability for zero DRC benefit). Measured
# directly (2026-08-12): a flat 0.5mm reduced `gnd`'s corridor-aware A*
# success from 33/85 (at the too-loose 0.05mm) to 19/85, and STILL left
# the `clearance` DRC delta completely unchanged (499 in both cases, and
# in the unpatched baseline) -- proof a single number cannot be both
# correct and un-costly here, which is why this module resolves the
# real per-pair value instead of guessing at one constant.
_FALLBACK_CLEARANCE_MM = 0.2


def resolve_netclass_clearances(kicad_pro_path: Path | str) -> tuple[dict[str, float], float]:
    """Read *kicad_pro_path*'s ``net_settings`` and return
    ``(net_name -> own_clearance_mm, default_clearance_mm)``.

    This is the SAME source KiCad's own DRC engine resolves a net's
    clearance from -- ``classes`` (netclass name -> clearance),
    ``netclass_assignments`` (explicit net -> class, KiCad's own
    resolved/cached mapping), and ``netclass_patterns`` (ordered
    glob-pattern fallback for nets with no explicit assignment) -- read
    directly rather than through
    ``temper_placer.core.design_rules.DesignRules.get_rules_for_net``,
    which was checked directly against this board (2026-08-12) and
    returns ``"Default"``/0.2mm for every real net name tried (including
    ones the `.kicad_pro` itself explicitly assigns to ``Power``) --
    that module's own `TEMPER_NET_ASSIGNMENTS` table is Python-side and
    admittedly incomplete for this board (`gnd` has no entry at all, per
    `docs/evidence/2026-08-11-keepout-before-pour-spike.md` §3), so it is
    not a reliable proxy for what kicad-cli itself will enforce. Reading
    the `.kicad_pro` file directly sidesteps that gap entirely.

    Tolerant of a missing *kicad_pro_path* (e.g. a test fixture that
    copies only the `.kicad_pcb` to a scratch dir, deliberately, to
    prove the generator never writes to the tracked project file) --
    falls back to an empty assignment table and
    ``_FALLBACK_CLEARANCE_MM`` for everything rather than raising, since
    a missing project file is a degraded-precision case, not a hard
    error for this module's own generation to depend on.
    """
    path = Path(kicad_pro_path)
    if not path.is_file():
        return {}, _FALLBACK_CLEARANCE_MM
    data = json.loads(path.read_text())
    net_settings = data.get("net_settings", {})
    classes = {c["name"]: float(c["clearance"]) for c in net_settings.get("classes", [])}
    default_clearance = classes.get("Default", _FALLBACK_CLEARANCE_MM)

    assignments: dict[str, str | None] = net_settings.get("netclass_assignments", {})
    patterns: list[dict[str, str]] = net_settings.get("netclass_patterns", [])

    def _resolve_class(net_name: str) -> str:
        assigned = assignments.get(net_name)
        if assigned:
            return assigned
        for p in patterns:
            if fnmatch.fnmatch(net_name, p.get("pattern", "")):
                return p.get("netclass", "Default")
        return "Default"

    net_clearance: dict[str, float] = {}
    for net_name in assignments:
        cls = _resolve_class(net_name)
        net_clearance[net_name] = classes.get(cls, default_clearance)

    return net_clearance, default_clearance


def collect_other_net_copper_by_pairwise_clearance(
    pcb,
    exclude_net: str,
    layer: str,
    net_clearance: dict[str, float],
    own_net_clearance_mm: float,
    default_clearance_mm: float,
) -> Polygon | None:
    """Like `_ground_plane._collect_other_net_copper`, but buffers each
    OTHER net's own geometry by the REAL pairwise clearance
    (``max(own_net_clearance_mm, that_net's_resolved_clearance)``)
    instead of one flat value applied to everything -- see
    `resolve_netclass_clearances`'s docstring for why a flat constant is
    the wrong shape here. Mirrors that function's exact
    pin/track/via-iteration structure (same primitives,
    `pin_world_layer`/`pin_world_position`) so the two stay easy to
    compare; not calling it directly because it takes one clearance
    value for its whole call, not a per-net mapping.
    """
    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    geoms: list = []

    def _pairwise(net_name: str) -> float:
        return max(own_net_clearance_mm, net_clearance.get(net_name, default_clearance_mm))

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
            # Half-diagonal, not max(width, height)/2 -- the furthest
            # point on a rectangular pad from its own centre is a
            # corner, not an edge midpoint (same fix already applied to
            # HV pads in `_collect_hv_copper_geometry`; the ORIGINAL,
            # shared `_collect_other_net_copper` this module's own
            # docstring compares itself to still uses the less-safe
            # max(w,h)/2 convention -- left unchanged there, since that
            # function is also used by via placement and is out of this
            # task's scope, but this module's own copy is corrected).
            # Measured directly (2026-08-12): using max(w,h)/2 here let
            # A*-routed edges pass geometrically "clean" against this
            # module's own obstacle polygon while still landing real DRC
            # `clearance` violations against rectangular pads' actual
            # corners, at gaps (0.12-0.19mm) matching this exact
            # under-coverage's magnitude -- not a coincidence.
            pad_radius = math.hypot(pin.width / 2.0, pin.height / 2.0)
            geoms.append(Point(pos).buffer(pad_radius + _pairwise(pin.net), quad_segs=8))

    for track in getattr(pcb, "tracks", []):
        if track.net == exclude_net or track.layer != layer:
            continue
        geoms.append(
            LineString([track.start, track.end]).buffer(
                track.width / 2.0 + _pairwise(track.net), quad_segs=8
            )
        )

    # Span-aware, not endpoint-literal: a through-via declaring
    # ``("F.Cu", "B.Cu")`` is copper on every layer in between, so it must
    # be an obstacle for a backbone routed on an INNER layer too. See
    # ``zone_pour_clearance._via_is_on_layer``'s docstring for the measured
    # blind spot this closes (no via was ever an obstacle on In1.Cu/In2.Cu).
    from temper_placer.router_v6.zone_pour_clearance import _via_is_on_layer

    for via in getattr(pcb, "vias", []):
        if via.net == exclude_net or not _via_is_on_layer(getattr(via, "layers", ()), layer):
            continue
        geoms.append(
            Point(via.position).buffer(via.diameter / 2.0 + _pairwise(via.net), quad_segs=8)
        )

    if not geoms:
        return None
    return unary_union(geoms)


def routed_segments_obstacle(
    segments: list[str] | None,
    exclude_net: str,
    layer: str,
    net_number_to_name: dict[int, str],
    net_clearance: dict[str, float],
    own_net_clearance_mm: float,
    default_clearance_mm: float,
) -> Polygon | None:
    """Buffered obstacle polygon from THIS route's emitted segment/via
    strings on *layer* -- the routed copper that the stripped board file
    cannot show.

    The plane/backbone generators re-parse the STRIPPED source board (the
    route's own copper is assembled in memory and never written to a file
    the generators could read), so ``collect_other_net_copper_by_pairwise_clearance``
    -- which walks ``pcb.tracks``/``pcb.vias`` -- sees ZERO routed tracks:
    measured 2026-08-16, the +3V3/vcc/+15V F.Cu backbones crossed the
    routed tracks and each other 81 times on one route (the definitive
    route's gnd-only backbone crossed ~10). This parses the in-memory
    ``(segment ...)``/``(via ...)`` strings the caller already holds and
    buffers each foreign net's copper by the same per-net pairwise
    clearance, so the corridor the backbone searches actually respects the
    copper that will be on the layer. Mirrors
    ``collect_other_net_copper_by_pairwise_clearance``'s conventions.
    """
    from temper_placer.router_v6.zone_pour_clearance import (
        _SEGMENT_RE,
        _VIA_RE,
        _via_is_on_layer,
    )

    geoms: list = []

    def _pairwise(net_name: str) -> float:
        return max(own_net_clearance_mm, net_clearance.get(net_name, default_clearance_mm))

    for line in segments or []:
        m = _SEGMENT_RE.search(line)
        if m:
            x0, y0, x1, y1, width, seg_layer, net_num = m.groups()
            if seg_layer != layer:
                continue
            name = net_number_to_name.get(int(net_num), "")
            if not name or name == exclude_net:
                continue
            geoms.append(
                LineString([(float(x0), float(y0)), (float(x1), float(y1))]).buffer(
                    float(width) / 2.0 + _pairwise(name), quad_segs=8
                )
            )
            continue
        m = _VIA_RE.search(line)
        if m:
            x, y, size, layers_str, net_num = m.groups()
            # Span-aware (2026-08-19): a substring test against the
            # declared endpoint pair misses every layer a through-via
            # actually pierces. See `zone_pour_clearance._via_is_on_layer`.
            if not _via_is_on_layer(tuple(layers_str.replace('"', "").split()), layer):
                continue
            name = net_number_to_name.get(int(net_num), "")
            if not name or name == exclude_net:
                continue
            geoms.append(
                Point(float(x), float(y)).buffer(
                    float(size) / 2.0 + _pairwise(name), quad_segs=8
                )
            )
    if not geoms:
        return None
    return unary_union(geoms)


# Arbitrary positive sentinel passed as `net_id` to `_astar_search` /
# `corridor_mask_for_net`. This grid never marks any cell with a positive
# value (only 0=free / -1=blocked -- see `build_obstacle_grid`), so the
# own-net-exemption branch these functions carry never fires; the
# sentinel only has to be positive to select the `net_id >= 0` occupancy
# branch in `_astar_search` (the one `corridor_mask` is wired into -- see
# that function's own docstring on why `net_id < 0` takes a different,
# `corridor_mask`-blind path).
_ROUTE_NET_ID = 1

# Growing-radius (in cells) search `corridor_aware_spanning_edges` uses to
# find the nearest labelled (reachable) cell when a position's own exact
# cell isn't part of any component -- see that function's own docstring.
# 15 cells = 3mm at this module's 0.2mm cell size, comfortably larger
# than the few-cell gaps actually measured (via drop points sit close to
# but not deep inside the tighter obstacle boundary), small enough that
# the search stays cheap (worst case a 31x31 window, once per position).
_NEAREST_LABEL_SEARCH_RADIUS_CELLS = 15


@dataclass
class BackboneRoutingResult:
    """Per-net/per-rail report of how many MST edges got a real,
    corridor-clean A* path vs. fell back to the prior
    keepout-only-straight-line/one-bend-detour behaviour."""

    astar_routed: int = 0
    fallback_used: int = 0
    dropped: int = 0


def build_obstacle_grid(
    board_polygon: Polygon,
    obstacle_polygons: list[Polygon | None],
    cell_size: float = CELL_SIZE_MM,
    margin_mm: float = GRID_MARGIN_MM,
) -> OccupancyGrid:
    """Rasterize *board_polygon* (free) minus every polygon in
    *obstacle_polygons* (blocked) into a fresh ``OccupancyGrid``.

    Mirrors ``occupancy_grid.build_occupancy_grid``'s own vectorized
    ``shapely.contains`` construction (board-availability rasterization),
    generalized to also rasterize an arbitrary obstacle-polygon union in
    the same pass -- the obstacle polygons here are already-buffered
    (clearance baked in, e.g. by ``_collect_other_net_copper``), so no
    additional buffering happens in this function; only the net's OWN
    trace-width erosion (`corridor_mask_for_net`, called by callers of
    this grid, not by this function) is layered on top.
    """
    x_min, y_min, x_max, y_max = board_polygon.bounds
    x_min -= margin_mm
    y_min -= margin_mm
    x_max += margin_mm
    y_max += margin_mm

    width_cells = max(1, int(np.ceil((x_max - x_min) / cell_size)))
    height_cells = max(1, int(np.ceil((y_max - y_min) / cell_size)))

    x_idx = np.arange(width_cells)
    y_idx = np.arange(height_cells)
    xx_idx, yy_idx = np.meshgrid(x_idx, y_idx)
    xx_world = x_min + (xx_idx + 0.5) * cell_size
    yy_world = y_min + (yy_idx + 0.5) * cell_size
    flat_x = xx_world.ravel()
    flat_y = yy_world.ravel()
    pts = points(flat_x, flat_y)

    inside_board = contains(board_polygon, pts).reshape(height_cells, width_cells)
    grid_arr = np.where(inside_board, 0, -1).astype(np.int8)

    real_obstacles = [g for g in obstacle_polygons if g is not None and not g.is_empty]
    if real_obstacles:
        merged = unary_union(real_obstacles)
        if not merged.is_empty:
            blocked = contains(merged, pts).reshape(height_cells, width_cells)
            grid_arr[blocked] = -1

    return OccupancyGrid(
        layer_name="F.Cu",
        grid=grid_arr,
        origin=(x_min, y_min),
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
    )


def _window(
    grid: OccupancyGrid,
    corridor_mask: np.ndarray,
    p1: tuple[float, float],
    p2: tuple[float, float],
    pad_mm: float | None,
) -> tuple[OccupancyGrid, np.ndarray]:
    """Slice *grid*/*corridor_mask* down to a local window around the
    straight-line bounding box of *p1*/*p2*, padded by *pad_mm* on every
    side (``None`` returns the full grid unmodified). Numpy array
    slicing is a view, not a copy -- ``_astar_search`` only reads these
    arrays, never mutates them, so no copy is needed."""
    if pad_mm is None:
        return grid, corridor_mask

    xmin = min(p1[0], p2[0]) - pad_mm
    xmax = max(p1[0], p2[0]) + pad_mm
    ymin = min(p1[1], p2[1]) - pad_mm
    ymax = max(p1[1], p2[1]) + pad_mm

    ox, oy = grid.origin
    cs = grid.cell_size
    cx0 = max(0, int((xmin - ox) / cs))
    cy0 = max(0, int((ymin - oy) / cs))
    cx1 = min(grid.width_cells, int(np.ceil((xmax - ox) / cs)) + 1)
    cy1 = min(grid.height_cells, int(np.ceil((ymax - oy) / cs)) + 1)

    sub = OccupancyGrid(
        layer_name=grid.layer_name,
        grid=grid.grid[cy0:cy1, cx0:cx1],
        origin=(ox + cx0 * cs, oy + cy0 * cs),
        cell_size=cs,
        width_cells=cx1 - cx0,
        height_cells=cy1 - cy0,
    )
    return sub, corridor_mask[cy0:cy1, cx0:cx1]


def simplify_collinear(path_world: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop interior points that lie exactly on the line between their
    neighbours, so an 8-connected grid path (up to hundreds of per-cell
    points) becomes a handful of KiCad segments without changing the
    route geometry at all (no smoothing/Douglas-Peucker -- a collinear
    merge cannot reintroduce a collision the search already avoided)."""
    if len(path_world) <= 2:
        return path_world
    out = [path_world[0]]
    for i in range(1, len(path_world) - 1):
        dx1 = path_world[i][0] - out[-1][0]
        dy1 = path_world[i][1] - out[-1][1]
        dx2 = path_world[i + 1][0] - path_world[i][0]
        dy2 = path_world[i + 1][1] - path_world[i][1]
        if abs(dx1 * dy2 - dy1 * dx2) > 1e-9:
            out.append(path_world[i])
    out.append(path_world[-1])
    return out


def compute_corridor_mask(grid: OccupancyGrid, trace_width: float) -> np.ndarray:
    """Erode *grid*'s free space by *trace_width*/2 (Chebyshev, matching
    ``mark_path_rect``) plus ``RASTER_SAFETY_MARGIN_MM`` -- the obstacle
    polygons ``build_obstacle_grid`` rasterized already carry the
    required clearance to other copper (see this module's docstring's
    C-space composition note: buffered-obstacle boundary + own-trace
    half-width erosion == the same total standoff `mark_path_rect`/
    `mark_path_blocked` would require if it stamped this trace for
    real) -- the extra margin corrects a SEPARATE, smaller error:
    `build_obstacle_grid` classifies a cell as free/blocked by testing
    its CENTRE against the (already-buffered) obstacle polygon, so a
    cell whose centre falls just outside the polygon but whose real
    half-cell footprint (up to ``cell_size/sqrt(2)`` from centre) still
    overlaps it is wrongly rasterized free. Measured directly (2026-08-12,
    `gnd`, 0.2mm cells): without this margin, up to 2 of 20 A*-routed
    edges' REAL trace footprints (continuous, not grid-quantized)
    intersected the very obstacle polygon they were routed to avoid --
    small (their gap was within a fraction of a cell), but a genuine,
    reproducible under-coverage, not noise. Adding this margin closed it
    to 0/20."""
    return corridor_mask_for_net(grid, _ROUTE_NET_ID, trace_width, RASTER_SAFETY_MARGIN_MM)


def route_edge_astar(
    grid: OccupancyGrid,
    corridor_mask: np.ndarray,
    p1: tuple[float, float],
    p2: tuple[float, float],
    window_paddings: tuple[float | None, ...] = WINDOW_PADDINGS_MM,
) -> list[tuple[float, float]] | None:
    """Try to find a corridor-clean path from *p1* to *p2* on *grid*,
    growing the search window each attempt. Returns a simplified list of
    world-space waypoints, or ``None`` if no window (including the full
    grid) yields a path -- callers must fall back to the prior
    keepout-only behaviour in that case, not drop the edge outright,
    since a corridor-mask failure can be a genuine physical disconnection
    (see this module's docstring), which the fallback is specifically
    there to still connect through.
    """
    for pad_mm in window_paddings:
        sub_grid, sub_mask = _window(grid, corridor_mask, p1, p2, pad_mm)
        start = sub_grid.world_to_grid(*p1)
        goal = sub_grid.world_to_grid(*p2)
        if not (0 <= start[0] < sub_grid.width_cells and 0 <= start[1] < sub_grid.height_cells):
            continue
        if not (0 <= goal[0] < sub_grid.width_cells and 0 <= goal[1] < sub_grid.height_cells):
            continue
        path_cells = _astar_search(
            start, goal, sub_grid, net_id=_ROUTE_NET_ID, corridor_mask=sub_mask
        )
        if path_cells:
            world_path = [sub_grid.grid_to_world(cx, cy) for cx, cy in path_cells]
            # `grid_to_world` returns CELL CENTRES, not the exact
            # world-space point that mapped into that cell -- so the
            # path's first/last points are off by up to half a cell
            # from p1/p2 (0.1mm at this module's 0.2mm cell size).
            # `pad_connectivity_audit` (and KiCad's own copper-joining
            # semantics) match on EXACT coincident coordinates, so
            # leaving this un-snapped would silently disconnect every
            # A*-routed edge's endpoint from the pad/via it must land
            # on -- measured directly: this exact bug collapsed `gnd`
            # pads_connected from the 46/86 floor to 14/86 before this
            # snap was added. The interior of the path is unaffected
            # (only endpoints are exact-position-sensitive).
            world_path[0] = p1
            world_path[-1] = p2
            return simplify_collinear(world_path)
    return None


def _connected_components_8(mask: np.ndarray) -> np.ndarray:
    """8-connected component labeling, delegating to
    ``temper_geometry.connected_components_8_transform`` (Rust two-pass
    union-find raster scan) -- the same migration
    ``routability_check._connected_components_8`` already made for
    ``check_routability_cc`` (see
    ``docs/evidence/2026-08-07-rust-connected-components-spike.md``:
    measured exact partition AND numeric-label agreement against
    ``scipy.ndimage.label(mask, structure=np.ones((3, 3)))`` across ~8.9M
    curated + random cells, 0 mismatches).

    Only the label ARRAY is returned (not ``num_features``) -- this
    module's only consumers, ``corridor_aware_spanning_edges`` and
    ``_nearest_label``, use labels purely as partition/equality markers
    (grouping positions that share a label, or picking the first nonzero
    label in a geometric scan window); neither depends on specific label
    *values* or on scipy's left-to-right/top-to-bottom numbering
    convention, so the (measured, not just asserted) partition-equivalence
    with scipy is the only property this call site relies on.

    ``mask`` must already be the desired boolean/uint8-castable array;
    this function does not renormalize dtype. Returns an ``int32`` array,
    same shape as ``mask``, ``0`` for background and ``1..=num_features``
    for foreground components.
    """
    h, w = mask.shape
    mask_u8 = np.ascontiguousarray(mask, dtype=np.uint8)
    out_bytes, _num_features = _tg.connected_components_8_transform(mask_u8.tobytes(), h, w)
    return np.frombuffer(out_bytes, dtype="<i4").reshape(h, w)


def corridor_aware_spanning_edges(
    positions: list[tuple[float, float]],
    grid: OccupancyGrid,
    corridor_mask: np.ndarray,
    mst_edges_fn,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """Route as much of *positions* as possible using ONLY genuinely
    corridor-clean paths, choosing WHICH edges to attempt based on real
    reachability rather than blind Euclidean-MST topology.

    **Why this exists, not just `route_edge_astar` per Euclidean-MST
    edge.** Measured directly (`gnd`, 2026-08-12): running `route_edge_astar`
    over the Euclidean MST's own edge list solves only 15-33 of 85 edges,
    and -- critically -- increasing that count severalfold (15 to 33, by
    loosening clearance) produced NO measurable change in the resulting
    board's DRC `clearance`/`solder_mask_bridge` totals. Root cause,
    confirmed with a control run that removes the backbone entirely: the
    backbone accounts for effectively all of `solder_mask_bridge` and
    most of `tracks_crossing`/`clearance`, but that violation mass
    concentrates on a SMALL SUBSET of Euclidean-MST edges that cross the
    densest F.Cu congestion -- the exact edges genuinely disconnected
    under full corridor avoidance (see this module's own docstring on
    the 73-component fragmentation). The Euclidean MST forces exactly
    those edges into its topology regardless of whether they are
    corridor-feasible; solving MORE of the "easy" edges elsewhere in the
    same fixed topology does not touch the hard, high-violation ones at
    all.

    **What this does instead:** labels `corridor_mask`'s own connected
    components (`_connected_components_8`, Rust, 8-connectivity), assigns each
    position to whichever component it lands in, and computes a Euclidean
    MST *within each component's own subset* -- i.e. it only ever asks
    A* to solve edges between positions that the mask's own connectivity
    already guarantees SOME corridor-clean path exists for (a component
    boundary is a hard topological fact, not a search-strategy artifact
    -- see this module's docstring). Every one of these intra-component
    edges should be A*-solvable in principle; `route_edge_astar`'s
    bounded windows still apply per edge (falling through to the full
    grid before giving up), so a small number can still fail if the true
    path needs a very long detour outside the tried windows -- reported
    honestly via omission (not present in the returned dict) rather than
    assumed to have succeeded.

    A position whose OWN grid cell is not part of any component (label
    0) is not skipped outright -- a small growing-radius search looks
    for the nearest labelled cell nearby and uses that component
    instead. This matters in practice, not just in theory: via/pad drop
    points are placed by `_find_via_drop_point` against
    `OTHER_NET_CLEARANCE_MM` (0.05mm), a looser standoff than the real
    per-pair clearance this module's own obstacle grid enforces (0.2-
    0.5mm here) -- so a legally-placed via can sit closer to foreign
    copper than THIS grid's corridor mask allows, landing its own exact
    cell just outside the mask even though the mask is free one or two
    cells away. Measured directly (`gnd`, 2026-08-12): treating "own
    cell unlabelled" as "unreachable" cost 52 of 86 positions their
    component membership outright, most of which had a labelled
    neighbour within 2-3 cells -- `route_edge_astar` itself does not
    have this problem (it only checks a NEIGHBOUR cell's corridor_mask
    when stepping, never the start cell's own), so this fix brings the
    grouping step's notion of reachability in line with what the search
    itself already tolerates, rather than being more conservative than
    the search for no reason. Positions with no labelled cell within
    ``_NEAREST_LABEL_SEARCH_RADIUS_CELLS`` are genuinely skipped -- they
    can only be reached via the caller's keepout-only fallback.

    Returns ``{(i, j): path_world}`` for every intra-component MST edge
    that solved -- callers still need their own (unchanged) keepout-only
    fallback to stitch different components together and to cover any
    edges this function's own bounded search could not close.
    """
    labels = _connected_components_8(corridor_mask)

    def _nearest_label(cx: int, cy: int) -> int:
        if labels[cy, cx] != 0:
            return int(labels[cy, cx])
        h, w = labels.shape
        for r in range(1, _NEAREST_LABEL_SEARCH_RADIUS_CELLS + 1):
            x0, x1 = max(0, cx - r), min(w, cx + r + 1)
            y0, y1 = max(0, cy - r), min(h, cy + r + 1)
            window = labels[y0:y1, x0:x1]
            nonzero = window[window != 0]
            if nonzero.size:
                return int(nonzero[0])
        return 0

    groups: dict[int, list[int]] = {}
    for idx, (x, y) in enumerate(positions):
        cx, cy = grid.world_to_grid(x, y)
        if not (0 <= cx < grid.width_cells and 0 <= cy < grid.height_cells):
            continue
        comp_id = _nearest_label(cx, cy)
        if comp_id == 0:
            continue  # no labelled cell within the search radius at all
        groups.setdefault(comp_id, []).append(idx)

    routed: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        sub_positions = [positions[i] for i in idxs]
        for a, b in mst_edges_fn(sub_positions):
            i, j = idxs[a], idxs[b]
            path = route_edge_astar(grid, corridor_mask, positions[i], positions[j])
            if path is not None:
                routed[(i, j)] = path
    return routed
