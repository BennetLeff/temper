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
from shapely.ops import unary_union

STEP = 0.2


def _blocked(geo, net, layer, bx, width):
    x0, y0, x1, y1 = bx
    nx, ny = int(round((x1 - x0) / STEP)) + 1, int(round((y1 - y0) / STEP)) + 1
    tree, items = geo._tree(layer)
    import rules21
    shapes = []
    from shapely.geometry import box as _box
    for i in tree.query(_box(x0 - 9, y0 - 9, x1 + 9, y1 + 9)):
        g, other = items[i]
        if other == net:
            continue
        need = 0.3 if other == "<npth>" else rules21.clearance(net, other)
        shapes.append(g.buffer(need + width / 2 + 0.03, resolution=8))
    shapes.append(geo.outline.exterior.buffer(width / 2 - 0.005))
    import numpy as np
    import shapely
    xs, ys = np.meshgrid(x0 + np.arange(nx) * STEP, y0 + np.arange(ny) * STEP)
    if shapes:
        bad = unary_union(shapes)
        shapely.prepare(bad)
        mask = shapely.contains_xy(bad, xs.ravel(), ys.ravel())
    else:
        mask = np.zeros(nx * ny, dtype=bool)
    return bytearray(mask.astype(np.uint8).tobytes()), nx, ny


def connect(geo, net, layer, bx, width, starts, goals):
    """Shortest legal path from any start point to any goal point (lists of (x, y))."""
    x0, y0 = bx[0], bx[1]
    grid, nx, ny = _blocked(geo, net, layer, bx, width)

    def cell(p):
        return (min(max(int(round((p[0] - x0) / STEP)), 0), nx - 1),
                min(max(int(round((p[1] - y0) / STEP)), 0), ny - 1))
    goal_cells = {cell(g): g for g in goals}
    for c in goal_cells:
        grid[c[1] * nx + c[0]] = 0
    start_cells = {cell(s): s for s in starts}
    openq, came, cost = [], {}, {}
    gx = [c[0] for c in goal_cells]
    gy = [c[1] for c in goal_cells]

    def h(c):
        return min(math.hypot(c[0] - a, c[1] - b) for a, b in zip(gx, gy))
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
    nx, ny = int(round((x1 - x0) / STEP)) + 1, int(round((y1 - y0) / STEP)) + 1
    xs, ys = np.meshgrid(x0 + np.arange(nx) * STEP, y0 + np.arange(ny) * STEP)
    mask = np.zeros(nx * ny, dtype=bool)
    for lay in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        tree, items = geo._tree(lay)
        shapes = []
        for i in tree.query(_box(x0 - 9, y0 - 9, x1 + 9, y1 + 9)):
            g, other = items[i]
            if other == net:
                continue
            need = 0.3 if other == "<npth>" else rules21.clearance(net, other)
            shapes.append(g.buffer(need + size / 2 + 0.03, resolution=8))
        if shapes:
            bad = unary_union(shapes)
            shapely.prepare(bad)
            mask |= shapely.contains_xy(bad, xs.ravel(), ys.ravel())
    inner = geo.outline.buffer(-size / 2 - 0.03)
    shapely.prepare(inner)
    mask |= ~shapely.contains_xy(inner, xs.ravel(), ys.ravel())
    return mask


def connect2(geo, net, bx, width, starts, goals, layers=("F.Cu", "B.Cu"), via=0.75, via_cost=8.0):
    """Multi-layer variant: starts/goals are (x, y, layer_index or None for any layer).
    Returns (segments [(layer, pts)], vias [(x, y)]) or None."""
    import numpy as np
    x0, y0 = bx[0], bx[1]
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
    gl_ = [(c[0], c[1]) for c in goal]

    def h(c):
        return min(math.hypot(c[0] - a, c[1] - b) for a, b in gl_)
    openq, came, cost = [], {}, {}
    startpt = {}
    for sx, sy, sl in starts:
        c = cell((sx, sy))
        for li in (range(len(layers)) if sl is None else [sl]):
            s = (c[0], c[1], li)
            grids[li][c[1] * nx + c[0]] = 0
            cost[s] = 0.0
            startpt[s] = (sx, sy)
            heapq.heappush(openq, (h(s), next(_TIE), s, None))
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    end = None
    while openq:
        _, _, c, d = heapq.heappop(openq)
        if c in goal:
            end = c
            break
        i, j, li = c
        for dx, dy, w in moves:
            n = (i + dx, j + dy, li)
            if not (0 <= n[0] < nx and 0 <= n[1] < ny) or grids[li][n[1] * nx + n[0]]:
                continue
            nc = cost[c] + w + (0.0 if d is None or d == (dx, dy) else 0.6)
            if nc < cost.get(n, 1e18):
                cost[n] = nc
                came[n] = c
                heapq.heappush(openq, (nc + h(n), next(_TIE), n, (dx, dy)))
        if vok[j * nx + i]:
            for lj in range(len(layers)):  # through vias: any layer change
                if lj == li or grids[lj][j * nx + i]:
                    continue
                n = (i, j, lj)
                nc = cost[c] + via_cost
                if nc < cost.get(n, 1e18):
                    cost[n] = nc
                    came[n] = c
                    heapq.heappush(openq, (nc + h(n), next(_TIE), n, None))
    if end is None:
        return None
    cells = [end]
    while cells[-1] in came:
        cells.append(came[cells[-1]])
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
