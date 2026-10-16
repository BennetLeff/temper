"""Bend-finder for authored local connections (route21.py).

route21 decides every net's layer, corridor box and order; this finds the bends of one
connection inside that box on that layer: an 8-connected A* on a 0.2 mm grid whose cells
are legal for the trace under rules21 clearances (via geom21). The result is an explicit
polyline that route21 records like any hand-drawn track. It never changes layers, adds
vias or leaves the box; if it fails, the caller chooses another corridor or layer.
"""
from __future__ import annotations

import heapq
import itertools
import math

_TIE = itertools.count()

from shapely.geometry import LineString, Point
from shapely.prepared import prep

from layers21 import CU, OUTER

STEP = 0.2
# Polygonal buffers are inscribed in the true offset curve: with 8 segments per quarter circle a
# corner falls short by r(1 - cos(pi/32)), 0.04 mm at the 8 mm barrier -- more than the 0.03 mm
# margin. Scaling the radius by 1/cos(pi/32) makes every buffer a circumscribed (safe) one.
_RES = 8
_CIRC = 1 / math.cos(math.pi / (4 * _RES))


# Grown obstacles repeat across calls (the same base copper around every connection): cached per (geometry, distance).
# The geometry is kept in the value so its id cannot be reused by a new object while the entry lives.
_GROWN = {}


def _grow(g, d):
    hit = _GROWN.get((id(g), d))
    if hit is not None and hit[0] is g:
        return hit[1]
    grown = g.buffer(d * _CIRC, resolution=_RES)
    _GROWN[(id(g), d)] = (g, grown)
    return grown


# Search grids sit on one board-wide lattice (x = i * STEP, y = j * STEP), the box snapped inward to it, so every
# grown obstacle is rasterised once per lattice tile and reused by every later search (2026-10-15: rebuilding the
# union of all grown obstacles for every search was most of incr21's time, and it grew with the box area).
TILE = 32
_TILES = {}      # (id(shape), STEP) -> (shape, {(ti, tj): bool array | True | False})
_STABLE = {}     # derived outline shapes, kept so their ids (and tiles) stay valid
_TILE_XY = {}    # (ti, tj, step) -> shared lattice coordinates, independent of the obstacle


def _window(bx):
    """Lattice cells inside box bx: (i0, j0, nx, ny, x0, y0) with x0 = i0 * STEP."""
    i0, j0 = math.ceil(bx[0] / STEP - 1e-9), math.ceil(bx[1] / STEP - 1e-9)
    i1, j1 = max(math.floor(bx[2] / STEP + 1e-9), i0), max(math.floor(bx[3] / STEP + 1e-9), j0)
    return i0, j0, i1 - i0 + 1, j1 - j0 + 1, i0 * STEP, j0 * STEP


def _stable(key, make):
    hit = _STABLE.get(key)
    if hit is None:
        hit = _STABLE[key] = make()
    return hit


def _shape_tile(shape, ti, tj, step=None):
    """Lattice tile (ti, tj) of one shape: True / False when wholly inside / outside, else a bool array."""
    import numpy as np
    import shapely
    step = STEP if step is None else step
    ent = _TILES.get((id(shape), step))
    if ent is None or ent[0] is not shape:
        shapely.prepare(shape)
        ent = _TILES[(id(shape), step)] = (shape, {})
    t = ent[1].get((ti, tj))
    if t is None:
        xy = _TILE_XY.get((ti, tj, step))
        if xy is None:
            xy = _TILE_XY[(ti, tj, step)] = np.meshgrid(
                np.arange(ti * TILE, ti * TILE + TILE) * step,
                np.arange(tj * TILE, tj * TILE + TILE) * step, sparse=True)
        t = shapely.contains_xy(shape, *xy)
        t = False if not t.any() else True if t.all() else t
        ent[1][(ti, tj)] = t
    return t


def _paint(mask, shape, i0, j0, nx, ny, add=False):
    """mask[j - j0, i - i0] |= lattice point (i, j) lies inside shape (strictly: contains_xy), tile by tile."""
    import numpy as np
    import shapely
    bx0, by0, bx1, by1 = shape.bounds
    a0, a1 = max(math.ceil(bx0 / STEP - 1e-9), i0), min(math.floor(bx1 / STEP + 1e-9), i0 + nx - 1)
    b0, b1 = max(math.ceil(by0 / STEP - 1e-9), j0), min(math.floor(by1 / STEP + 1e-9), j0 + ny - 1)
    if a0 > a1 or b0 > b1:
        return
    for ti in range(a0 // TILE, a1 // TILE + 1):
        for tj in range(b0 // TILE, b1 // TILE + 1):
            t = _shape_tile(shape, ti, tj)
            if t is False:
                continue
            c0, c1 = max(ti * TILE, a0), min(ti * TILE + TILE - 1, a1)
            r0, r1 = max(tj * TILE, b0), min(tj * TILE + TILE - 1, b1)
            win = mask[r0 - j0:r1 - j0 + 1, c0 - i0:c1 - i0 + 1]
            if t is True:
                if add:
                    win += 1
                else:
                    win[...] = True
            else:
                part = t[r0 - tj * TILE:r1 - tj * TILE + 1, c0 - ti * TILE:c1 - ti * TILE + 1]
                if add:
                    win += part
                else:
                    win |= part


def _goal_distance(goal_cells, nx, ny):
    """h for A*: Euclidean distance in cells from every grid cell to its nearest goal cell (one distance transform
    instead of a min over all goals on every push), as a (ny, nx) array."""
    import numpy as np
    from scipy.ndimage import distance_transform_edt
    far = np.ones((ny, nx), dtype=bool)
    for i, j in goal_cells:
        far[j, i] = False
    _, (gj, gi) = distance_transform_edt(far, return_indices=True)
    jj, ii = np.indices((ny, nx))
    return np.hypot(ii - gi, jj - gj)


# Shared obstacle rasters (2026-10-15). rules21.clearance(net, other) depends on the routed net only through its
# class (domain, tank node, HOT group), so the obstacle grid of every net of one class is the same count raster:
# per lattice tile, how many grown obstacles cover each point (each obstacle grown by the class's clearance to its
# net). A net's grid is that count minus its own copper's share, > 0. The plan-view barrier is one boolean raster per
# barrier side. Tiles are computed when a search first needs them and dropped when copper is added near them.
_CLS = {}        # geo key -> {"seen": {layer: (id(list), len, id(last))}, "own": {layer: {net: [i]}}, "rasters": {...}}


def _cls(net):
    import rules21
    return (rules21.domain(net), net in rules21.TANK, rules21.GROUP.get(net), net in rules21.RES_A_NETS)


def _clr(c, other, layer):
    """rules21.clearance_on(a, other, layer) for a net a of class c, a != other (checked against rules21 by
    _check_cls). The layer matters for RES_A against SELV / PE: 12.6 mm on the outer layers (stage 18)."""
    import rules21
    if other == "<npth>":
        return 0.3
    if not other:
        return rules21.FLOOR
    da, ta, ga, ra = c
    db = rules21.domain(other)
    if layer in OUTER and ((ra and db in ("SELV", "PE")) or (other in rules21.RES_A_NETS and da in ("SELV", "PE"))):
        return max(rules21.BARRIER if {da, db} in ({"SELV", "HOT"}, {"PE", "HOT"}) else rules21.FLOOR,
                   rules21.RES_A_CREEPAGE)
    if {da, db} in ({"SELV", "HOT"}, {"PE", "HOT"}):
        return rules21.BARRIER
    if da == db == "HOT":
        tb = other in rules21.TANK
        if ta != tb or (ta and tb):
            return rules21._m.wr.TANK_CREEPAGE_MM
        if ga != rules21.GROUP[other]:
            return rules21._m.wr.FUNCTIONAL_CREEPAGE_MM
    return rules21.FLOOR


def _check_cls(nets):
    import rules21
    nets = sorted(n for n in nets if n and n != "<npth>")
    for a in nets:
        c = _cls(a)
        for b in nets:
            for lay in CU:
                if a != b and _clr(c, b, lay) != rules21.clearance_on(a, b, lay):
                    raise AssertionError(f"maze21 class clearance {a} / {b} on {lay}: {_clr(c, b, lay)} != "
                                         f"{rules21.clearance_on(a, b, lay)}")


def _state(geo):
    st = _CLS.get(id(geo))
    if st is None or st["geo"] is not geo:
        st = _CLS[id(geo)] = {"geo": geo, "seen": {}, "own": {}, "rasters": {}, "grow": {}}
        _check_cls({n for its in geo.items.values() for _, n in its})
    return st


def forget(geo):
    """After items were removed from or restored into geo (incr21's rip-up): every layer's rasters are rebuilt on
    the next query. (_sync alone could miss it: a list cut and refilled to its old length keeps its fingerprint
    when a new item reuses a freed item's id.)"""
    st = _CLS.get(id(geo))
    if st is not None:
        st["seen"].clear()


def _sync(st, layer):
    """Bring the caches of one layer up to date with geo.items[layer]: an appended item is added into every computed
    tile its grown shape reaches (the count a rebuild would give), anything else (a patch deleting or replacing items)
    drops the layer's rasters."""
    items = st["geo"].items[layer]
    seen = st["seen"].get(layer)
    fp = (id(items), len(items), id(items[-1]) if items else 0)
    if seen == fp:
        return
    rasters = [k for k in st["rasters"] if k[1] == layer]
    own = st["own"].setdefault(layer, {})
    if seen is None or seen[0] != fp[0] or seen[1] > fp[1] or (seen[1] and id(items[seen[1] - 1]) != seen[2]):
        for k in rasters:
            del st["rasters"][k]
        own.clear()
        start = 0
    else:
        start = seen[1]
        import numpy as np
        for k in rasters:
            tiles, step, grow_of = st["rasters"][k], k[-1], st["grow"][k]   # each raster on its own lattice
            for g, other in items[start:]:
                sh = grow_of(g, other)
                if sh is None:
                    continue
                bx0, by0, bx1, by1 = sh.bounds
                for ti in range(math.floor(bx0 / step) // TILE, math.floor(bx1 / step) // TILE + 1):
                    for tj in range(math.floor(by0 / step) // TILE, math.floor(by1 / step) // TILE + 1):
                        old = tiles.get((ti, tj))
                        if old is None:
                            continue                       # not computed yet: it will include the item
                        t = _shape_tile(sh, ti, tj, step)
                        if t is False:
                            continue
                        if k[0] == "bar":
                            tiles[(ti, tj)] = np.ones((TILE, TILE), dtype=bool) if t is True else (
                                t.copy() if isinstance(old, int) else old | t)
                        else:
                            base = np.zeros((TILE, TILE), dtype=np.int16) if isinstance(old, int) else old
                            tiles[(ti, tj)] = base + t
    for i in range(start, len(items)):
        own.setdefault(items[i][1], []).append(i)
    st["seen"][layer] = fp


def _reach(c, layer, width):
    """How far a grown obstacle of class c's grid on `layer` can reach past its copper: the class's largest clearance
    there plus the trace and margins. RES_A against SELV / PE on F.Cu / B.Cu is 12.6 mm; a fixed 9 mm query missed
    RES_A copper 9-12.6 mm from a SELV path, which the final check then rejected (2026-10-15)."""
    import rules21
    big = max(rules21.BARRIER, rules21._m.wr.TANK_CREEPAGE_MM)
    if layer in OUTER and (c[3] or c[0] in ("SELV", "PE")):
        big = max(big, rules21.RES_A_CREEPAGE)
    return big + width / 2 + 0.1


def _tile_shapes(geo, layer, ti, tj, grow_of, r=9):
    """Grown obstacles (grow_of(geom, net) -> grown or None) whose bounds reach lattice tile (ti, tj); r bounds how
    far a grown shape reaches past its copper."""
    from shapely.geometry import box as _box
    x0, y0 = ti * TILE * STEP, tj * TILE * STEP
    x1, y1 = x0 + (TILE - 1) * STEP, y0 + (TILE - 1) * STEP
    tree, items = geo._tree(layer)
    out = []
    for i in tree.query(_box(x0 - r, y0 - r, x1 + r, y1 + r)):
        g, other = items[i]
        sh = grow_of(g, other)
        if sh is None:
            continue
        b = sh.bounds
        if b[2] >= x0 and b[0] <= x1 and b[3] >= y0 and b[1] <= y1:
            out.append(sh)
    return out


def _raster_window(st, key, i0, j0, nx, ny, compute, dtype):
    """Assemble a window of raster `key` from its tiles (computed on first use by compute(ti, tj))."""
    import numpy as np
    tiles = st["rasters"].setdefault(key, {})
    out = np.zeros((ny, nx), dtype=dtype)
    for ti in range(i0 // TILE, (i0 + nx - 1) // TILE + 1):
        for tj in range(j0 // TILE, (j0 + ny - 1) // TILE + 1):
            t = tiles.get((ti, tj))
            if t is None:
                t = tiles[(ti, tj)] = compute(ti, tj)
            if isinstance(t, int):      # 0: nothing in this tile
                continue
            c0, c1 = max(ti * TILE, i0), min(ti * TILE + TILE - 1, i0 + nx - 1)
            r0, r1 = max(tj * TILE, j0), min(tj * TILE + TILE - 1, j0 + ny - 1)
            out[r0 - j0:r1 - j0 + 1, c0 - i0:c1 - i0 + 1] = t[r0 - tj * TILE:r1 - tj * TILE + 1, c0 - ti * TILE:c1 - ti * TILE + 1]
    return out


def _cover(shapes, ti, tj, count):
    """Per lattice point of tile (ti, tj): how many shapes contain it (count) or whether any does, from the shapes'
    own cached tiles (shared by every class whose growth gives the same shape); 0 when none."""
    import numpy as np
    acc = np.zeros((TILE, TILE), dtype=np.int16 if count else bool)
    for sh in shapes:
        t = _shape_tile(sh, ti, tj)
        if t is False:
            continue
        if count:
            acc += t
        elif t is True:
            return np.ones((TILE, TILE), dtype=bool)
        else:
            acc |= t
    return acc if acc.any() else 0


def _copper_grid(geo, net, layer, i0, j0, nx, ny, width, via):
    """Cells within clearance of other nets' copper on `layer` for a trace (or via, via=True) of `width`:
    the class count raster minus the net's own copper."""
    import numpy as np
    st = _state(geo)
    _sync(st, layer)
    c = _cls(net)
    perm = geo.via_permeable

    def grow_of(g, other):
        if via and id(g) in perm:
            return None
        return _grow(g, _clr(c, other, layer) + width / 2 + 0.03)
    key = ("via" if via else "trk", layer, c, width, STEP)
    reach = _reach(c, layer, width)
    st["grow"][key] = grow_of
    count = _raster_window(st, key, i0, j0, nx, ny,
                           lambda ti, tj: _cover(_tile_shapes(geo, layer, ti, tj, grow_of, reach), ti, tj, True), np.int16)
    own = st["own"][layer].get(net, ())
    if own:
        items = geo.items[layer]
        mine = np.zeros((ny, nx), dtype=np.int16)
        for i in own:
            sh = grow_of(*items[i])
            if sh is not None:
                _paint(mine, sh, i0, j0, nx, ny, add=True)
        count = count - mine
    return count > 0


def _barrier_grid(geo, net, i0, j0, nx, ny, width):
    """Cells within the plan-view barrier of the other side's copper (SELV / PE against HOT), or None."""
    import numpy as np
    import rules21
    side = rules21.domain(net)
    if side not in ("SELV", "PE", "HOT"):
        return None
    side = "hot" if side == "HOT" else "low"
    st = _state(geo)
    _sync(st, "PLAN")

    def grow_of(g, other):
        if other in ("<npth>", net) or not rules21.barrier(net, other):
            return None
        return _grow(g, rules21.BARRIER + width / 2 + 0.03)
    key = ("bar", "PLAN", side, width, STEP)
    st["grow"][key] = grow_of
    return _raster_window(st, key, i0, j0, nx, ny,
                          lambda ti, tj: _cover(_tile_shapes(geo, "PLAN", ti, tj, grow_of), ti, tj, False), bool)


def _blocked(geo, net, layer, bx, width):
    import numpy as np
    i0, j0, nx, ny, _, _ = _window(bx)
    mask = _copper_grid(geo, net, layer, i0, j0, nx, ny, width, via=False)
    _paint(mask, _stable(("band", id(geo.outline), width), lambda: geo.outline.exterior.buffer(width / 2 - 0.005)),
           i0, j0, nx, ny)
    bar = _barrier_grid(geo, net, i0, j0, nx, ny, width)
    if bar is not None:
        mask |= bar
    return bytearray(mask.astype(np.uint8).tobytes()), nx, ny


def connect(geo, net, layer, bx, width, starts, goals):
    """Shortest legal path from any start point to any goal point (lists of (x, y))."""
    x0, y0 = _window(bx)[4:]
    grid, nx, ny = _blocked(geo, net, layer, bx, width)

    def cell(p):
        return (min(max(int(round((p[0] - x0) / STEP)), 0), nx - 1),
                min(max(int(round((p[1] - y0) / STEP)), 0), ny - 1))
    goal_cells = {cell(g): g for g in goals}
    for c in goal_cells:
        grid[c[1] * nx + c[0]] = 0
    start_cells = {cell(s): s for s in starts}
    openq, came, cost = [], {}, {}
    hd = _goal_distance(goal_cells, nx, ny).tolist()

    def h(c):
        return hd[c[1]][c[0]]
    for c in start_cells:
        grid[c[1] * nx + c[0]] = 0
        cost[c] = 0.0
        heapq.heappush(openq, (h(c), next(_TIE), c, None))
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    end = None
    while openq:
        _, _, c, d = heapq.heappop(openq)
        if c in goal_cells:
            end = c
            break
        for dx, dy, w in moves:
            n = (c[0] + dx, c[1] + dy)
            if not (0 <= n[0] < nx and 0 <= n[1] < ny) or grid[n[1] * nx + n[0]]:
                continue
            turn = 0.0 if d is None or d == (dx, dy) else 0.6
            nc = cost[c] + w + turn
            if nc < cost.get(n, 1e18):
                cost[n] = nc
                came[n] = (c, (dx, dy))
                heapq.heappush(openq, (nc + h(n), next(_TIE), n, (dx, dy)))
    if end is None:
        return None
    cells = [end]
    while cells[-1] in came:
        cells.append(came[cells[-1]][0])
    cells.reverse()
    pts = [(x0 + c[0] * STEP, y0 + c[1] * STEP) for c in cells]
    pts[0] = start_cells[cells[0]]
    pts[-1] = goal_cells[cells[-1]]
    simple = [pts[0]]
    for a, b in zip(pts[1:], pts[2:]):
        p = simple[-1]
        if abs((a[0] - p[0]) * (b[1] - p[1]) - (a[1] - p[1]) * (b[0] - p[0])) > 1e-6:
            simple.append(a)
    simple.append(pts[-1])
    return [[round(x, 3), round(y, 3)] for x, y in simple]


# Other nets' pours, [(layer, net, polygon)] (incr21 sets it from the board's zone outlines; route21 leaves it empty):
# a track may cross one (the fill knocks out round it) but can cut it in two, as a re-route across the stage-40 n_ls
# "GOOD change" pour did (2026-10-15), so each step into a cell inside one costs POUR_COST more.
POURS = []
POUR_COST = 2.0


def _pour_mask(net, layer, i0, j0, nx, ny):
    """Cells inside another net's pour on `layer`."""
    import numpy as np
    from shapely.geometry import box as _box
    from shapely.strtree import STRtree

    def build():
        polys = [poly for lay, _, poly in POURS if lay == layer]
        return STRtree(polys), [n for lay, n, _ in POURS if lay == layer], polys
    tree, nets, polys = _stable(("pours", id(POURS), len(POURS), layer), build)
    mask = np.zeros((ny, nx), dtype=bool)
    win = _box(i0 * STEP, j0 * STEP, (i0 + nx - 1) * STEP, (j0 + ny - 1) * STEP)
    for k in sorted(tree.query(win)):
        if nets[k] != net:
            _paint(mask, polys[k], i0, j0, nx, ny)
    return mask


def _via_ok(geo, net, bx, size):
    """Grid of cells where a through via of `size` is legal on every copper layer."""
    import numpy as np
    import shapely
    from shapely.geometry import box as _box
    import rules21
    i0, j0, nx, ny, _, _ = _window(bx)
    grid = np.zeros((ny, nx), dtype=bool)
    for lay in CU:
        grid |= _copper_grid(geo, net, lay, i0, j0, nx, ny, size, via=True)
    bar = _barrier_grid(geo, net, i0, j0, nx, ny, size)
    if bar is not None:
        grid |= bar
    inside = np.zeros((ny, nx), dtype=bool)
    _paint(inside, _stable(("inner", id(geo.outline), size), lambda: geo.outline.buffer(-size / 2 - 0.03)), i0, j0, nx, ny)
    return (grid | ~inside).ravel()


_DX = (1, -1, 0, 0, 1, 1, -1, -1)
_DY = (0, 0, 1, -1, 1, -1, 1, -1)
_W = (1.0, 1.0, 1.0, 1.0, 1.414, 1.414, 1.414, 1.414)


def _astar_core(blocked, vok, hd, start_nodes, goal_mask, nx, ny, nl, via_cost, pour_cost, cost, came):
    """8-connected A* over nl layers of an nx x ny grid with through-via moves; node = layer * nx * ny + j * nx + i.
    blocked: 0 free, 1 blocked, 2 inside another net's pour (pour_cost more per step into it). 0.6 per bend, via_cost
    per layer change. Pushes in the order the tuple-keyed version did (same tie counter), so it
    returns the same path. Returns the goal node reached or -1; came[] holds each node's predecessor (-1: none)."""
    P = nx * ny
    heap = [(0.0, 0, 0, 0)]
    heap.pop()
    tie = 0
    for s in start_nodes:
        cost[s] = 0.0
        heapq.heappush(heap, (hd[s % P], tie, s, -1))
        tie += 1
    end = -1
    while len(heap) > 0:
        _, _, c, d = heapq.heappop(heap)
        if goal_mask[c]:
            end = c
            break
        li = c // P
        r = c - li * P
        j = r // nx
        i = r - j * nx
        cc = cost[c]
        for k in range(8):
            ni = i + _DX[k]
            nj = j + _DY[k]
            if ni < 0 or ni >= nx or nj < 0 or nj >= ny:
                continue
            n = li * P + nj * nx + ni
            b = blocked[n]
            if b == 1:
                continue
            nc = cc + _W[k] + (0.0 if d == -1 or d == k else 0.6) + (pour_cost if b == 2 else 0.0)
            if nc < cost[n]:
                cost[n] = nc
                came[n] = c
                heapq.heappush(heap, (nc + hd[n - li * P], tie, n, k))
                tie += 1
        if vok[r]:
            for lj in range(nl):  # through vias: any layer change
                n = lj * P + r
                if lj == li or blocked[n] == 1:
                    continue
                nc = cc + via_cost + (pour_cost if blocked[n] == 2 else 0.0)
                if nc < cost[n]:
                    cost[n] = nc
                    came[n] = c
                    heapq.heappush(heap, (nc + hd[r], tie, n, -1))
                    tie += 1
    return end


_CORE = None


def _astar(blocked, vok, hd, start_nodes, goal_mask, nx, ny, nl, via_cost, pour_cost=0.0):
    """Run the core JIT-compiled (numba, cached beside this file) or, without numba or with MAZE21_NO_JIT, as plain
    Python on lists: the same code either way."""
    global _CORE
    import os
    import numpy as np
    N = nl * nx * ny
    if _CORE is None:
        _CORE = _astar_core
        if not os.environ.get("MAZE21_NO_JIT"):
            try:
                import numba
                _CORE = numba.njit(cache=True)(_astar_core)
            except ImportError:
                pass
    if _CORE is _astar_core:
        came = [-1] * N
        end = _astar_core(blocked.tolist(), vok.tolist(), hd.tolist(), start_nodes.tolist(), goal_mask.tolist(),
                          nx, ny, nl, via_cost, pour_cost, [1e18] * N, came)
        return end, came
    came = np.full(N, -1, dtype=np.int64)
    end = _CORE(blocked, vok, hd, start_nodes, goal_mask, nx, ny, nl, via_cost, pour_cost, np.full(N, 1e18), came)
    return int(end), came


def connect2(geo, net, bx, width, starts, goals, layers=OUTER, via=0.75, via_cost=8.0):
    """Multi-layer variant: starts/goals are (x, y, layer_index or None for any layer).
    Returns (segments [(layer, pts)], vias [(x, y)]) or None."""
    import numpy as np
    x0, y0 = _window(bx)[4:]
    grids = []
    for lay in layers:
        g, nx, ny = _blocked(geo, net, lay, bx, width)
        if POURS:
            i0, j0 = _window(bx)[:2]
            a = np.frombuffer(g, dtype=np.uint8)
            a[(a == 0) & _pour_mask(net, lay, i0, j0, nx, ny).ravel()] = 2
        grids.append(g)
    vok = ~_via_ok(geo, net, bx, via)

    def cell(p):
        return (min(max(int(round((p[0] - x0) / STEP)), 0), nx - 1),
                min(max(int(round((p[1] - y0) / STEP)), 0), ny - 1))
    goal = {}
    for gx, gy, gl in goals:
        c = cell((gx, gy))
        for li in (range(len(layers)) if gl is None else [gl]):
            goal[(c[0], c[1], li)] = (gx, gy)
            grids[li][c[1] * nx + c[0]] = 0
    nl, P = len(layers), nx * ny
    hd = _goal_distance({(c[0], c[1]) for c in goal}, nx, ny).ravel()
    goal_mask = np.zeros(nl * P, dtype=np.uint8)
    for (i, j, li) in goal:
        goal_mask[li * P + j * nx + i] = 1
    startpt, start_nodes = {}, []
    for sx, sy, sl in starts:
        c = cell((sx, sy))
        for li in (range(nl) if sl is None else [sl]):
            grids[li][c[1] * nx + c[0]] = 0
            startpt[(c[0], c[1], li)] = (sx, sy)
            start_nodes.append(li * P + c[1] * nx + c[0])
    blocked = np.frombuffer(b"".join(bytes(g) for g in grids), dtype=np.uint8)
    end, came = _astar(blocked, np.ascontiguousarray(vok, dtype=np.uint8), hd, np.array(start_nodes, dtype=np.int64),
                       goal_mask, nx, ny, nl, float(via_cost), float(POUR_COST))
    if end < 0:
        return None
    cells = [end]
    while came[cells[-1]] >= 0:
        cells.append(int(came[cells[-1]]))
    cells = [(c % P % nx, c % P // nx, c // P) for c in cells]
    cells.reverse()
    segs, vias, cur = [], [], []
    for k, c in enumerate(cells):
        p = (x0 + c[0] * STEP, y0 + c[1] * STEP)
        if k == 0:
            p = startpt.get(c, p)
        if k == len(cells) - 1:
            p = goal[c]
        if cur and cur[-1][2] != c[2]:
            segs.append(cur)
            vias.append((p[0], p[1], layers[cur[-1][2]], layers[c[2]]))
            cur = []
        cur.append((p[0], p[1], c[2]))
    segs.append(cur)
    out = []
    for s in segs:
        pts = [(q[0], q[1]) for q in s]
        simple = [pts[0]]
        for a, b in zip(pts[1:], pts[2:]):
            p = simple[-1]
            if abs((a[0] - p[0]) * (b[1] - p[1]) - (a[1] - p[1]) * (b[0] - p[0])) > 1e-6:
                simple.append(a)
        if len(pts) > 1:
            simple.append(pts[-1])
        if len(simple) > 1:
            out.append((layers[s[0][2]], [[round(x, 3), round(y, 3)] for x, y in simple]))
    return out, [(round(x, 3), round(y, 3), la, lb) for x, y, la, lb in vias]
