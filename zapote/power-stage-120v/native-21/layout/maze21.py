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


def _paint(mask, shape, i0, j0, nx, ny):
    """mask[j - j0, i - i0] |= lattice point (i, j) lies inside shape (strictly: contains_xy), tile by tile."""
    import numpy as np
    import shapely
    bx0, by0, bx1, by1 = shape.bounds
    a0, a1 = max(math.ceil(bx0 / STEP - 1e-9), i0), min(math.floor(bx1 / STEP + 1e-9), i0 + nx - 1)
    b0, b1 = max(math.ceil(by0 / STEP - 1e-9), j0), min(math.floor(by1 / STEP + 1e-9), j0 + ny - 1)
    if a0 > a1 or b0 > b1:
        return
    ent = _TILES.get((id(shape), STEP))
    if ent is None or ent[0] is not shape:
        shapely.prepare(shape)
        ent = _TILES[(id(shape), STEP)] = (shape, {})
    tiles = ent[1]
    for ti in range(a0 // TILE, a1 // TILE + 1):
        for tj in range(b0 // TILE, b1 // TILE + 1):
            t = tiles.get((ti, tj))
            if t is None:
                xs, ys = np.meshgrid(np.arange(ti * TILE, ti * TILE + TILE) * STEP,
                                     np.arange(tj * TILE, tj * TILE + TILE) * STEP)
                t = shapely.contains_xy(shape, xs, ys)
                t = False if not t.any() else True if t.all() else t
                tiles[(ti, tj)] = t
            if t is False:
                continue
            c0, c1 = max(ti * TILE, a0), min(ti * TILE + TILE - 1, a1)
            r0, r1 = max(tj * TILE, b0), min(tj * TILE + TILE - 1, b1)
            win = mask[r0 - j0:r1 - j0 + 1, c0 - i0:c1 - i0 + 1]
            if t is True:
                win[...] = True
            else:
                win |= t[r0 - tj * TILE:r1 - tj * TILE + 1, c0 - ti * TILE:c1 - ti * TILE + 1]


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


def _blocked(geo, net, layer, bx, width):
    x0, y0, x1, y1 = bx
    i0, j0, nx, ny, _, _ = _window(bx)
    tree, items = geo._tree(layer)
    import rules21
    shapes = []
    from shapely.geometry import box as _box
    for i in tree.query(_box(x0 - 9, y0 - 9, x1 + 9, y1 + 9)):
        g, other = items[i]
        if other == net:
            continue
        need = 0.3 if other == "<npth>" else rules21.clearance(net, other)
        shapes.append(_grow(g, need + width / 2 + 0.03))
    shapes.append(_stable(("band", id(geo.outline), width), lambda: geo.outline.exterior.buffer(width / 2 - 0.005)))
    ptree, pitems = geo._tree("PLAN")
    for i in ptree.query(_box(x0 - 9, y0 - 9, x1 + 9, y1 + 9)):
        g, other = pitems[i]
        if other != net and other != "<npth>" and rules21.barrier(net, other):
            shapes.append(_grow(g, rules21.BARRIER + width / 2 + 0.03))
    import numpy as np
    mask = np.zeros((ny, nx), dtype=bool)
    for sh in shapes:
        _paint(mask, sh, i0, j0, nx, ny)
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


def _via_ok(geo, net, bx, size):
    """Grid of cells where a through via of `size` is legal on every copper layer."""
    import numpy as np
    import shapely
    from shapely.geometry import box as _box
    import rules21
    x0, y0, x1, y1 = bx
    i0, j0, nx, ny, _, _ = _window(bx)
    grid = np.zeros((ny, nx), dtype=bool)
    for lay in CU:
        tree, items = geo._tree(lay)
        for i in tree.query(_box(x0 - 9, y0 - 9, x1 + 9, y1 + 9)):
            g, other = items[i]
            if other == net or id(g) in geo.via_permeable:
                continue
            need = 0.3 if other == "<npth>" else rules21.clearance(net, other)
            _paint(grid, _grow(g, need + size / 2 + 0.03), i0, j0, nx, ny)
    ptree, pitems = geo._tree("PLAN")
    for i in ptree.query(_box(x0 - 9, y0 - 9, x1 + 9, y1 + 9)):
        g, other = pitems[i]
        if other != net and other != "<npth>" and rules21.barrier(net, other):
            _paint(grid, _grow(g, rules21.BARRIER + size / 2 + 0.03), i0, j0, nx, ny)
    inside = np.zeros((ny, nx), dtype=bool)
    _paint(inside, _stable(("inner", id(geo.outline), size), lambda: geo.outline.buffer(-size / 2 - 0.03)), i0, j0, nx, ny)
    return (grid | ~inside).ravel()


_DX = (1, -1, 0, 0, 1, 1, -1, -1)
_DY = (0, 0, 1, -1, 1, -1, 1, -1)
_W = (1.0, 1.0, 1.0, 1.0, 1.414, 1.414, 1.414, 1.414)


def _astar_core(blocked, vok, hd, start_nodes, goal_mask, nx, ny, nl, via_cost, cost, came):
    """8-connected A* over nl layers of an nx x ny grid with through-via moves; node = layer * nx * ny + j * nx + i.
    0.6 per bend, via_cost per layer change. Pushes in the order the tuple-keyed version did (same tie counter), so it
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
            if blocked[n]:
                continue
            nc = cc + _W[k] + (0.0 if d == -1 or d == k else 0.6)
            if nc < cost[n]:
                cost[n] = nc
                came[n] = c
                heapq.heappush(heap, (nc + hd[n - li * P], tie, n, k))
                tie += 1
        if vok[r]:
            for lj in range(nl):  # through vias: any layer change
                n = lj * P + r
                if lj == li or blocked[n]:
                    continue
                nc = cc + via_cost
                if nc < cost[n]:
                    cost[n] = nc
                    came[n] = c
                    heapq.heappush(heap, (nc + hd[r], tie, n, -1))
                    tie += 1
    return end


_CORE = None


def _astar(blocked, vok, hd, start_nodes, goal_mask, nx, ny, nl, via_cost):
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
                          nx, ny, nl, via_cost, [1e18] * N, came)
        return end, came
    came = np.full(N, -1, dtype=np.int64)
    end = _CORE(blocked, vok, hd, start_nodes, goal_mask, nx, ny, nl, via_cost, np.full(N, 1e18), came)
    return int(end), came


def connect2(geo, net, bx, width, starts, goals, layers=OUTER, via=0.75, via_cost=8.0):
    """Multi-layer variant: starts/goals are (x, y, layer_index or None for any layer).
    Returns (segments [(layer, pts)], vias [(x, y)]) or None."""
    import numpy as np
    x0, y0 = _window(bx)[4:]
    grids = []
    for lay in layers:
        g, nx, ny = _blocked(geo, net, lay, bx, width)
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
                       goal_mask, nx, ny, nl, float(via_cost))
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
