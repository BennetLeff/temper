#!/usr/bin/env python3
"""S1 spike measurements: can GEOS polygon boolean algebra be replicated in Rust?

Companion to ``docs/evidence/2026-08-04-geos-polygon-algebra-spike.md``.

Every number in that document is produced by this script.  It writes **no**
files, changes **no** production code, and builds **no** Rust crate: it only
calls shapely/GEOS and numpy.

Run::

    ./.venv/bin/python tools/measurements/geos_polygon_algebra_spike.py

or a single probe::

    ./.venv/bin/python tools/measurements/geos_polygon_algebra_spike.py --probe P3

Probes
------
P1  Canonical form.  Is the *coordinate sequence* GEOS emits a function of the
    region, or of the computation that produced it?
P2  Representation dependence.  Does an input vertex that adds no area change
    the output?
P3  Intersection-vertex arithmetic.  Where does GEOS put a vertex that is not
    an input vertex, and does the textbook closed form agree?
P4  ``buffer()`` vertex placement, positive and negative (erosion) distance.
P5  Translation invariance under an exactly representable shift.
P6  **The narrowing.**  Is the occupancy mask that ``occupancy_grid.py``
    actually consumes computable without ever forming the GEOS union or the
    GEOS difference?
P7  Per-primitive triage of the other GEOS calls in the three modules:
    ``LineString.buffer``, ``MultiPoint.convex_hull``, the ``buffer(0)``
    invalid-polygon repair idiom, and ``Polygon.intersection``.
"""

from __future__ import annotations

import argparse
import math
import random
import struct
import sys

import numpy as np
import shapely
from shapely import contains, intersects, points
from shapely.affinity import translate
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def ulp_distance(a: float, b: float) -> int:
    """Signed-magnitude ULP distance between two finite doubles."""
    ia = struct.unpack("<q", struct.pack("<d", a))[0]
    ib = struct.unpack("<q", struct.pack("<d", b))[0]
    return abs(ia - ib)


def rings(geom) -> list[tuple[tuple[float, float], ...]]:
    """Every coordinate ring of a (Multi)Polygon, in GEOS's own emission order."""
    out: list[tuple[tuple[float, float], ...]] = []
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    for part in parts:
        if part.is_empty:
            continue
        out.append(tuple(part.exterior.coords))
        for hole in part.interiors:
            out.append(tuple(hole.coords))
    return out


def coord_multiset(geom) -> list[list[tuple[float, float]]]:
    """Rings reduced to sorted coordinate sets.

    Two geometries with the same ``coord_multiset`` describe the same vertices
    but may differ in ring start point, ring winding, or part order -- i.e. the
    difference is *structural*, not numeric.
    """
    return sorted(sorted(set(r)) for r in rings(geom))


def rand_polygon(rng: random.Random, n: int) -> Polygon:
    """A star-shaped random polygon: valid by construction, non-axis-aligned."""
    cx, cy = rng.uniform(-20, 20), rng.uniform(-20, 20)
    r = rng.uniform(0.5, 4.0)
    angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
    return Polygon(
        [
            (
                cx + r * math.cos(a) * rng.uniform(0.6, 1.0),
                cy + r * math.sin(a) * rng.uniform(0.6, 1.0),
            )
            for a in angles
        ]
    )


def dyadic(rng: random.Random, lo: float, hi: float, denom: int = 1024) -> float:
    """A value in [lo, hi) of the form k/denom.

    Adding a power of two below 2**43 to such a value is exact, so a
    translation test built from these coordinates measures GEOS and not the
    rounding of the translation itself.
    """
    k = rng.randint(int(lo * denom), int(hi * denom) - 1)
    return k / denom


def rand_dyadic_polygon(rng: random.Random, n: int) -> Polygon:
    """Random polygon whose coordinates all survive a +1024 shift exactly."""
    cx, cy = dyadic(rng, -20, 20), dyadic(rng, -20, 20)
    pts = []
    angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
    for a in angles:
        r = dyadic(rng, 0.5, 4.0)
        pts.append(
            (
                cx + round(r * math.cos(a) * 1024) / 1024,
                cy + round(r * math.sin(a) * 1024) / 1024,
            )
        )
    return Polygon(pts)


# --------------------------------------------------------------------------
# P1 -- is the emitted coordinate sequence canonical?
# --------------------------------------------------------------------------


def probe_p1(trials: int = 200) -> None:
    """Two GEOS computations of the *same region* -- same vertices, same order?

    ``A - (B1 u B2)`` and ``(A - B1) - B2`` are the same set.  If GEOS emits
    the same coordinate *sequence* for both, its output has a canonical form
    that a port could target with ``==``.
    """
    print("\n=== P1  canonical form: A-(B1uB2)  vs  (A-B1)-B2 ===")
    rng = random.Random(11)
    n = same_seq = same_set_diff_order = diff_coords = 0
    for _ in range(trials):
        a = box(-25, -25, 25, 25)
        b1, b2 = rand_polygon(rng, rng.randint(3, 6)), rand_polygon(rng, rng.randint(3, 6))
        if not (b1.is_valid and b2.is_valid and b1.area > 0 and b2.area > 0):
            continue
        x = a.difference(unary_union([b1, b2]))
        y = a.difference(b1).difference(b2)
        n += 1
        if rings(x) == rings(y):
            same_seq += 1
        elif coord_multiset(x) == coord_multiset(y):
            same_set_diff_order += 1
        else:
            diff_coords += 1
    print(f"  n = {n}")
    print(f"  identical coordinate sequence            : {same_seq}")
    print(f"  identical vertex set, different sequence : {same_set_diff_order}")
    print(f"  different vertex set                     : {diff_coords}")
    print(
        "  -> `==` on the emitted ring is NOT a region-level equality test"
        if same_seq < n
        else "  -> emission order is stable"
    )

    # Which part of the sequence moves?
    a = box(-25, -25, 25, 25)
    rng2 = random.Random(11)
    for _ in range(50):
        b1, b2 = rand_polygon(rng2, 5), rand_polygon(rng2, 5)
        if not (b1.is_valid and b2.is_valid):
            continue
        x = a.difference(unary_union([b1, b2]))
        y = a.difference(b1).difference(b2)
        if rings(x) != rings(y) and coord_multiset(x) == coord_multiset(y):
            print(f"  example ring-start x: {rings(x)[0][0]}")
            print(f"  example ring-start y: {rings(y)[0][0]}")
            print(f"  example ring len x/y: {len(rings(x)[0])}/{len(rings(y)[0])}")
            break


# --------------------------------------------------------------------------
# P2 -- does the input representation leak into the output?
# --------------------------------------------------------------------------


def probe_p2(trials: int = 200) -> None:
    """Insert an exact edge midpoint into the subtrahend and re-difference.

    The midpoint adds no area and lies exactly on an existing edge, so the
    region subtracted is unchanged.  A region-canonical implementation would
    emit the same polygon.
    """
    print("\n=== P2  representation dependence: collinear vertex in the input ===")
    rng = random.Random(11)
    n = same = differs = 0
    vert_delta = []
    worst_coord = 0.0
    for _ in range(trials):
        a = box(-25, -25, 25, 25)
        b = rand_polygon(rng, rng.randint(3, 6))
        if not b.is_valid or b.area <= 0:
            continue
        coords = list(b.exterior.coords)[:-1]
        (x0, y0), (x1, y1) = coords[0], coords[1]
        mid = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        b_mid = Polygon([coords[0], mid] + coords[1:])
        if not b_mid.is_valid or b_mid.area != b.area:
            continue
        n += 1
        r1, r2 = a.difference(b), a.difference(b_mid)
        if rings(r1) == rings(r2):
            same += 1
        else:
            differs += 1
            n1 = sum(len(r) for r in rings(r1))
            n2 = sum(len(r) for r in rings(r2))
            vert_delta.append(n2 - n1)
            worst_coord = max(worst_coord, abs(r1.area - r2.area))
    print(f"  n = {n}  (only cases where inserting the midpoint left .area bit-identical)")
    print(f"  output unchanged : {same}")
    print(f"  output changed   : {differs}")
    if vert_delta:
        print(f"  vertex-count delta: min {min(vert_delta)} max {max(vert_delta)}")
    print(f"  worst |area difference| : {worst_coord!r}")


# --------------------------------------------------------------------------
# P3 -- the arithmetic of a non-input vertex
# --------------------------------------------------------------------------


def _closed_form(p1, p2, p3, p4):
    """Textbook determinant form of a segment/segment intersection point."""
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p1, p2, p3, p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if den == 0:
        return None
    a = x1 * y2 - y1 * x2
    b = x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / den, (a * (y3 - y4) - (y1 - y2) * b) / den)


def probe_p3(trials: int = 4000) -> None:
    """Every vertex of a boolean result that is not an input vertex is one of
    these.  Does GEOS agree with the closed form?"""
    print("\n=== P3  intersection-vertex arithmetic: GEOS vs the closed form ===")
    rng = random.Random(23)
    n = mismatch = 0
    worst_abs = 0.0
    worst_ulp = 0
    for _ in range(trials):
        pts = [(rng.uniform(-50, 50), rng.uniform(-50, 50)) for _ in range(4)]
        g = LineString(pts[:2]).intersection(LineString(pts[2:]))
        if g.is_empty or g.geom_type != "Point":
            continue
        ref = _closed_form(*pts)
        if ref is None:
            continue
        n += 1
        if (g.x, g.y) != ref:
            mismatch += 1
            worst_abs = max(worst_abs, abs(g.x - ref[0]), abs(g.y - ref[1]))
            worst_ulp = max(worst_ulp, ulp_distance(g.x, ref[0]), ulp_distance(g.y, ref[1]))
    pct = 100.0 * mismatch / max(n, 1)
    print(f"  n = {n}")
    print(f"  bit-mismatch vs closed form : {mismatch} ({pct:.1f}%)")
    print(f"  worst |delta|               : {worst_abs!r} mm")
    print(f"  worst ULP distance          : {worst_ulp}")


# --------------------------------------------------------------------------
# P4 -- buffer()
# --------------------------------------------------------------------------


def probe_p4() -> None:
    """``buffer`` is an approximation; where does GEOS choose to put the
    vertices, and is the choice reconstructible?"""
    print("\n=== P4  buffer() vertex placement ===")

    # (a) circular buffer of a point -- the escape-via / pre-existing-via case
    for quad_segs in (4, 8):
        cx, cy, r = 3.7, -2.1, 0.6
        ring = list(Point(cx, cy).buffer(r, quad_segs=quad_segs).exterior.coords)[:-1]
        mism = 0
        worst = 0.0
        for i, (x, y) in enumerate(ring):
            ang = -i * math.pi / (2 * quad_segs)
            px, py = cx + r * math.cos(ang), cy + r * math.sin(ang)
            if (x, y) != (px, py):
                mism += 1
                worst = max(worst, abs(x - px), abs(y - py))
        print(
            f"  Point.buffer(r, quad_segs={quad_segs}): {len(ring)} verts, "
            f"clockwise from +x; bit-mismatch vs cx+r*cos(-k*pi/{2 * quad_segs}) "
            f"= {mism}/{len(ring)} (worst {worst!r})"
        )

    # (b) the disk approximation is INSCRIBED -> erosion under-removes
    for quad_segs in (4, 8):
        half = math.pi / (4 * quad_segs)
        print(
            f"    quad_segs={quad_segs}: {4 * quad_segs}-gon, vertices exactly on the "
            f"circle, inradius/r = {math.cos(half)!r} "
            f"(offset short by {(1 - math.cos(half)) * 100:.3f}% of the distance)"
        )

    # (c) negative buffer of a real routing-space shape -- the production path
    board, obstacles = synthetic_board(random.Random(5))
    merged = unary_union(obstacles)
    avail = board.difference(merged)
    inflation = 0.125  # default_trace_width_mm 0.25 / 2, see the evidence doc
    eroded = avail.buffer(-inflation, quad_segs=4)
    print(
        f"  available_area.buffer(-{inflation}, quad_segs=4): "
        f"{avail.geom_type}({len(rings(avail))} rings, "
        f"{sum(len(r) for r in rings(avail))} verts) -> "
        f"{eroded.geom_type}({len(rings(eroded))} rings, "
        f"{sum(len(r) for r in rings(eroded))} verts)"
    )
    print(f"    area {avail.area!r} -> {eroded.area!r}")

    # Is the eroded result reachable without the difference?  Morphologically
    # (A \ B) erode D == (A erode D) \ (B dilate D) for the same D.
    alt = board.buffer(-inflation, quad_segs=4).difference(merged.buffer(inflation, quad_segs=4))
    print(
        f"    morphological identity (A-B)(-)D == (A(-)D) - (B(+)D): "
        f"same vertex set = {coord_multiset(eroded) == coord_multiset(alt)}, "
        f"|area delta| = {abs(eroded.area - alt.area)!r}"
    )


# --------------------------------------------------------------------------
# P5 -- translation invariance
# --------------------------------------------------------------------------


def probe_p5(trials: int = 200, shift: float = 1024.0) -> None:
    """All coordinates are dyadic, so ``x`` and ``x + 1024`` are both exact and
    the shift itself introduces no rounding."""
    print(f"\n=== P5  translation invariance of difference (shift = {shift}) ===")
    rng = random.Random(11)
    n = same = differs = 0
    worst = 0.0
    for _ in range(trials):
        a = box(-25.0, -25.0, 25.0, 25.0)
        b = rand_dyadic_polygon(rng, rng.randint(3, 6))
        if not b.is_valid or b.area <= 0:
            continue
        r1 = a.difference(b)
        r2 = translate(
            translate(a, shift, shift).difference(translate(b, shift, shift)), -shift, -shift
        )
        n += 1
        c1, c2 = coord_multiset(r1), coord_multiset(r2)
        if c1 == c2:
            same += 1
        else:
            differs += 1
            flat1 = sorted(p for r in c1 for p in r)
            flat2 = sorted(p for r in c2 for p in r)
            if len(flat1) == len(flat2):
                worst = max(
                    worst,
                    max(
                        max(abs(u[0] - v[0]), abs(u[1] - v[1]))
                        for u, v in zip(flat1, flat2, strict=True)
                    ),
                )
    print(f"  n = {n}  (dyadic coordinates: the +/-{shift} shift is exact)")
    print(f"  translation-invariant : {same}")
    print(f"  not invariant         : {differs}")
    print(f"  worst coordinate drift: {worst!r} mm")


# --------------------------------------------------------------------------
# P6 -- the narrowing
# --------------------------------------------------------------------------


def synthetic_board(rng: random.Random, nx: int = 8, ny: int = 6):
    """A board and an obstacle list built from the same primitives
    ``obstacle_map.py`` uses: rotated rectangular pads, ``Point.buffer(r,
    quad_segs=8)`` vias, ``LineString.buffer(w/2, cap_style=1)`` tracks."""
    width, height = 40.0, 30.0
    board = box(0.0, 0.0, width, height)
    obstacles: list[Polygon] = []
    for i in range(nx):
        for j in range(ny):
            cx, cy = 2.0 + i * 4.6, 2.0 + j * 4.6
            ang = rng.choice([0.0, math.pi / 2, 0.37, 1.1])
            w, h = 1.2, 0.7
            ca, sa = math.cos(ang), math.sin(ang)
            corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
            obstacles.append(
                Polygon([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in corners])
            )
    for _ in range(30):
        obstacles.append(
            Point(rng.uniform(1, width - 1), rng.uniform(1, height - 1)).buffer(0.3, quad_segs=8)
        )
    for _ in range(20):
        a = (rng.uniform(1, width - 1), rng.uniform(1, height - 1))
        b = (a[0] + rng.uniform(-6, 6), a[1] + rng.uniform(-6, 6))
        obstacles.append(LineString([a, b]).buffer(0.1, cap_style=1))
    return board, obstacles


def _grid_points(geom, cell: float, margin: float):
    """Exactly ``occupancy_grid.build_occupancy_grid``'s cell-centre lattice."""
    x_min, y_min, x_max, y_max = geom.bounds
    x_min -= margin
    y_min -= margin
    x_max += margin
    y_max += margin
    wc = max(1, int(np.ceil((x_max - x_min) / cell)))
    hc = max(1, int(np.ceil((y_max - y_min) / cell)))
    xx, yy = np.meshgrid(np.arange(wc), np.arange(hc))
    fx = (x_min + (xx + 0.5) * cell).ravel()
    fy = (y_min + (yy + 0.5) * cell).ravel()
    return points(fx, fy), hc, wc


def probe_p6(seeds=(5, 17, 101, 2027), cell: float = 0.1, margin: float = 2.0) -> None:
    """Does ``occupancy_grid`` need the GEOS *polygon*, or only the mask?

    ``mask_A`` is what production computes.  ``mask_B`` never forms the
    difference.  ``mask_C`` never forms the union either -- it is the boolean
    algebra done on the raster, over per-obstacle point-in-polygon predicates.
    """
    print("\n=== P6  the narrowing: mask instead of polygon ===")
    print("  A = contains(board.difference(unary_union(obs)), p)     [production]")
    print("  B = contains(board, p) & ~intersects(unary_union(obs), p)")
    print("  C = contains(board, p) & ~OR_o intersects(o, p)          [no union, no difference]")
    total_cells = tot_ab = tot_ac = 0
    for seed in seeds:
        rng = random.Random(seed)
        board, obstacles = synthetic_board(rng)
        merged = unary_union(obstacles)
        avail = board.difference(merged)
        if isinstance(avail, Polygon):
            avail = MultiPolygon([avail])
        pts, hc, wc = _grid_points(avail, cell, margin)
        mask_a = contains(avail, pts)
        mask_b = contains(board, pts) & ~intersects(merged, pts)
        acc = np.zeros(len(pts), dtype=bool)
        for o in obstacles:
            acc |= intersects(o, pts)
        mask_c = contains(board, pts) & ~acc
        d_ab = int((mask_a != mask_b).sum())
        d_ac = int((mask_a != mask_c).sum())
        total_cells += hc * wc
        tot_ab += d_ab
        tot_ac += d_ac
        print(
            f"  seed {seed:>5}: {hc}x{wc} = {hc * wc:>7} cells, "
            f"{int(mask_a.sum()):>7} free | A!=B {d_ab} | A!=C {d_ac}"
        )
    print(f"  TOTAL {total_cells} cells: A!=B {tot_ab}, A!=C {tot_ac}")

    # Adversarial: put cell centres exactly on obstacle vertices and edges.
    print("  adversarial lattice (cell centres forced onto obstacle vertices):")
    rng = random.Random(5)
    board, obstacles = synthetic_board(rng)
    merged = unary_union(obstacles)
    avail = board.difference(merged)
    probe = []
    for o in obstacles:
        ring = list(o.exterior.coords)[:-1]
        probe.extend(ring)
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
            probe.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    for r in rings(avail):
        probe.extend(r)
    px = np.array([p[0] for p in probe])
    py = np.array([p[1] for p in probe])
    pts = points(px, py)
    mask_a = contains(avail, pts)
    acc = np.zeros(len(pts), dtype=bool)
    for o in obstacles:
        acc |= intersects(o, pts)
    mask_c = contains(board, pts) & ~acc
    bad = np.nonzero(mask_a != mask_c)[0]
    print(f"    {len(probe)} boundary-exact probe points: A!=C {len(bad)}")
    if len(bad):
        worst = max(avail.boundary.distance(Point(px[i], py[i])) for i in bad)
        print(f"    every disagreement lies within {worst:.3e} mm of the boundary")

    # How close does the real lattice ever get to that band?
    pts, hc, wc = _grid_points(avail, cell, margin)
    d = shapely.distance(avail.boundary, pts)
    print(
        f"    real {hc}x{wc} lattice: {int((d == 0.0).sum())} cell centres exactly on a "
        f"boundary, {int(((d > 0) & (d < 1e-14)).sum())} within (0, 1e-14) mm, "
        f"min nonzero {d[d > 0].min():.3e} mm -- and 0 disagreements above"
    )

    # And the eroded (C-space) path that production actually takes.
    print("  eroded C-space path, inflation = 0.125 mm (default_trace_width_mm 0.25 / 2):")
    inflation = 0.125
    eroded = avail.buffer(-inflation, quad_segs=4)
    pts, hc, wc = _grid_points(avail, cell, margin)
    mask_a = contains(eroded, pts)
    acc = np.zeros(len(pts), dtype=bool)
    for o in obstacles:
        acc |= intersects(o.buffer(inflation, quad_segs=4), pts)
    mask_c = contains(board.buffer(-inflation, quad_segs=4), pts) & ~acc
    print(
        f"    {hc * wc} cells: A free {int(mask_a.sum())}, C free {int(mask_c.sum())}, "
        f"A!=C {int((mask_a != mask_c).sum())}"
    )


# --------------------------------------------------------------------------
# P7 -- the remaining primitives, one at a time
# --------------------------------------------------------------------------


def probe_p7() -> None:
    """Per-primitive triage of the other GEOS calls in the three modules."""
    print("\n=== P7  the remaining primitives ===")

    # (a) obstacle_map.py:137 -- LineString.buffer(w/2, cap_style=1)
    a, b, w = (1.25, -3.5), (7.75, 2.25), 0.2
    r = w / 2.0
    ring = list(LineString([a, b]).buffer(r, cap_style=1).exterior.coords)[:-1]
    theta = math.atan2(b[1] - a[1], b[0] - a[0])
    cands = set()
    for centre in (a, b):
        for k in range(-64, 65):
            for ang in (theta + k * math.pi / 16, k * math.pi / 16):
                cands.add((centre[0] + r * math.cos(ang), centre[1] + r * math.sin(ang)))
    hit = sum(1 for p in ring if p in cands)
    print(
        f"  LineString.buffer(r={r}, cap_style=1): {len(ring)} vertices, {len(set(ring))} distinct"
    )
    print(f"    bit-equal to an exact end-cap circle point : {hit}/{len(ring)}")
    print(f"    a minimal closed form needs                : {2 * (16 + 1)} vertices")

    # (b) placement_audit.py:66 -- MultiPoint.convex_hull
    pts = [(0.0, 0.0), (2.0, 0.5), (1.0, 3.0), (0.5, 1.0), (-1.0, 2.0), (1.0, 1.0)]
    hull = list(MultiPoint(pts).convex_hull.exterior.coords)[:-1]
    print(
        f"  MultiPoint.convex_hull: {len(hull)} verts, all of them input points: "
        f"{all(p in pts for p in hull)}"
    )

    # (c) obstacle_map.py:108 -- the `poly.buffer(0)` invalid-zone repair idiom
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
    fixed = bowtie.buffer(0)
    print(
        f"  Polygon(bow-tie).is_valid = {bowtie.is_valid}; .buffer(0) -> "
        f"{fixed.geom_type}, area {fixed.area} (the two lobes total 2.0)"
    )
    print(f"    wkt: {fixed.wkt}")

    # (d) placement_audit.py:86-94 -- polygon/polygon intersection
    p1 = Polygon([(0.0, 0.0), (3.0, 0.3), (2.7, 2.9), (0.1, 2.5)])
    p2 = Polygon([(1.4, 1.1), (4.2, 1.6), (3.9, 4.0), (1.1, 3.4)])
    inter = p1.intersection(p2)
    iv = list(inter.exterior.coords)[:-1]
    inputs = set(p1.exterior.coords) | set(p2.exterior.coords)
    from_input = sum(1 for p in iv if p in inputs)
    print(
        f"  Polygon.intersection: {len(iv)} verts, {from_input} are input vertices, "
        f"{len(iv) - from_input} are P3-class computed"
    )
    print(f"    centroid: {(inter.centroid.x, inter.centroid.y)}")


# --------------------------------------------------------------------------

PROBES = {
    "P1": probe_p1,
    "P2": probe_p2,
    "P3": probe_p3,
    "P4": probe_p4,
    "P5": probe_p5,
    "P6": probe_p6,
    "P7": probe_p7,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", choices=sorted(PROBES), action="append")
    args = parser.parse_args()
    print(f"shapely {shapely.__version__}  GEOS {shapely.geos_version}  numpy {np.__version__}")
    print(f"python {sys.version.split()[0]}  platform {sys.platform}")
    for name in args.probe or sorted(PROBES):
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
