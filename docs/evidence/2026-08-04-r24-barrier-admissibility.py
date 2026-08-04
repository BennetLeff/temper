#!/usr/bin/env python3
"""Barrier-admissibility scorer: PR #690's necessary-condition tests, per placement.

# provenance: commit=f2b09d84673b3a18d8fabe454230f1b240148f3d dirty=false

Why this exists
---------------
``docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md`` (PR #690)
established, shape-independently, that the *committed placement* admits no
conforming ``MAINS_SELV_ISOLATION_BARRIER`` of any shape, and that ``R24``
alone is why: its two HV pads are marooned in the current-sense/RTD corner and
the widest copper-free channel back to the other 99 HV copper pads is 5.728mm
against the 8.000mm the barrier needs.

#690 answered that question for ONE board file. Choosing between candidate
re-placements needs the same verdict computed for an ARBITRARY placement, so
this module re-implements #690's two necessary conditions against a
``--board`` argument and emits a machine-readable verdict. The
maths is #690's, unchanged; only the plumbing (board path, JSON out, channel
bisection helper) is new. #690's script is not importable here: it lives on an
unmerged branch, and vendoring the two tests keeps this scorer runnable
against ``origin/main`` alone.

The two tests (both NECESSARY, neither sufficient -- see #690's UNVERIFIED
section, which this inherits verbatim):

TEST 1 (#690 Part B) -- pairwise separability.
  Let ``C`` be the union of all copper and ``F`` the copper-free region. A
  conforming barrier ``B`` satisfies ``B subset F`` (check 5) and is >= 8.0mm
  wide everywhere (check 3's stated contract, formalised as a union of discs
  of radius 4.0mm). Every such disc lies in ``F``, so
  ``B subset O := opening(F, 4mm)`` for every barrier of every shape. Hence
  ``board \\ O subset board \\ B``: two pads in the SAME component of
  ``board \\ O`` are on the SAME side of every conforming barrier, so an
  HV/SELV pair sharing a component falsifies check 6 universally.

TEST 2 (#690 Part C) -- HV-side connectivity.
  Checks 4 and 6 together demand ONE region holding every HV copper pad. The
  HV region may occupy at most ``K = {points >= 4mm from all copper}`` (where
  the barrier centreline can live) plus any blob of the remainder carrying no
  SELV copper. If the HV copper pads fall into two or more components of that
  maximally permissive space, no conforming barrier exists.

Test 2 is the one ``R24`` fails on the committed placement, and therefore the
one a candidate re-placement has to flip.

Obstacle model is ``reroutable`` -- exact rotated pad outlines only, assuming
a full re-route. #690 Sec 4.1 already settled that the board AS ROUTED admits
no barrier of any shape (copper covers 87.4% of the area), placement-
independently; that is not re-litigated here and is not something a placement
change can fix.

Usage:
  uv run --no-sync python docs/evidence/2026-08-04-r24-barrier-admissibility.py \\
      --board pcb/temper.kicad_pcb [--json OUT.json] [--label NAME] [--channel-bisect]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_isolation_keepout import (  # noqa: E402
    MIN_BARRIER_WIDTH_MM,
    BoardData,
    Manifest,
    PadInstance,
    _rotate,
    load_board,
    load_manifest,
)

MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

# 64 segments/quadrant, as #690. Erosion with a vertex-on-circle polygon
# under-cuts slightly, making O marginally LARGER -- the safe direction for a
# necessary condition (errs toward "a barrier might exist").
PROVENANCE_COMMIT = "f2b09d84673b3a18d8fabe454230f1b240148f3d"
QUAD_SEGS = 64
HALF_WIDTH_MM = MIN_BARRIER_WIDTH_MM / 2.0


def exact_pad_polygons(board_path: Path) -> list:
    """Exact copper footprints of every COPPER-BEARING pad as rotated Shapely
    polygons -- rect / roundrect / circle / oval (the only four shapes on this
    board). #690's ``_exact_pad_polygons``, verbatim maths.

    The gate itself models a pad as its circumscribing circle, which is right
    for an intrusion test but over-states elongated pads (it reports T1 at
    5.977mm where the true geometry is 9.100mm). Exact outlines are the honest
    input to a feasibility question about the BOARD rather than about the
    gate's model.
    """
    from kiutils.board import Board
    from shapely import affinity
    from shapely.geometry import LineString, Point, Polygon

    board = Board.from_file(str(board_path))
    copper_names = {ly.name for ly in board.layers if getattr(ly, "type", None) == "signal"}

    def _has_copper(layers: list[str]) -> bool:
        return any(ln in ("*.Cu", "*Cu") or ln in copper_names for ln in (layers or []))

    def _local_shape(shape: str, w: float, h: float, rr_ratio: float):
        if shape == "circle":
            return Point(0, 0).buffer(max(w, h) / 2.0, quad_segs=32)
        if shape == "oval":
            if w >= h:
                r, d = h / 2.0, max(w - h, 0.0) / 2.0
                return LineString([(-d, 0), (d, 0)]).buffer(r, quad_segs=32)
            r, d = w / 2.0, max(h - w, 0.0) / 2.0
            return LineString([(0, -d), (0, d)]).buffer(r, quad_segs=32)
        rect = Polygon([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
        if shape == "roundrect":
            r = max(min(rr_ratio, 0.5), 0.0) * min(w, h)
            if r > 1e-9:
                return rect.buffer(-r, quad_segs=32).buffer(r, quad_segs=32)
        return rect

    geoms: list = []
    for fp in board.footprints:
        fx, fy = fp.position.X, fp.position.Y
        fang = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")
        for pad in fp.pads:
            if not _has_copper(pad.layers or []):
                continue
            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            dx, dy = _rotate(lx, ly, fang)
            w = getattr(pad.size, "X", 0.0) or 0.0
            h = getattr(pad.size, "Y", 0.0) or 0.0
            rr = getattr(pad, "roundrectRatio", None)
            rr = 0.25 if rr is None else rr
            geom = _local_shape(getattr(pad, "shape", None) or "rect", w, h, rr)
            # KiCad stores a pad's shape rotation absolutely (footprint angle
            # already folded in); y-down board frame, so a CCW board rotation
            # is a negative Shapely rotation.
            geom = affinity.rotate(geom, -(pad.position.angle or 0.0), origin=(0, 0))
            geoms.append(affinity.translate(geom, fx + dx, fy + dy))
    return geoms


def _opening(free, r: float):
    """``opening(free, r)`` -- the union of every disc of radius r that fits
    inside ``free``. Any barrier >= 2r wide everywhere and copper-free is a
    subset of this, whatever its shape."""
    eroded = free.buffer(-r, quad_segs=QUAD_SEGS)
    return eroded if eroded.is_empty else eroded.buffer(r, quad_segs=QUAD_SEGS)


def _components(geom) -> list:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]


def classified_pads(board: BoardData, manifest: Manifest, board_poly):
    """Pads the necessary conditions may reason about: manifest-classified,
    carrying copper on at least one layer, inside the outline.

    Copper-bearing is load-bearing -- check 5 forbids copper inside the
    barrier, so a copper pad must land on one side or the other and check 6
    must classify it. A pad with no copper (``K1.13``/``K1.14`` here) may
    legally sit inside the barrier, where ``_side_of`` returns None and drops
    it, so it can never prove impossibility."""
    from shapely.geometry import Point

    hv, selv, dropped = [], [], []
    for p in board.pads:
        if p.net_name in manifest.hv_nets:
            dom = "HV"
        elif p.net_name in manifest.selv_nets:
            dom = "SELV"
        else:
            continue
        if not p.layers:
            dropped.append((dom, p, "no copper layer"))
            continue
        if not board_poly.covers(Point(p.x, p.y)):
            dropped.append((dom, p, "outside Edge.Cuts"))
            continue
        (hv if dom == "HV" else selv).append(p)
    return hv, selv, dropped


def _mixed_components(components: list, hv: list[PadInstance], selv: list[PadInstance]):
    """Components of ``board \\ O`` holding pads of BOTH domains. Each one is a
    proof that no conforming barrier of any shape exists."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    if not components:
        return 0, [{"component_index": -1, "note": "board \\ O is empty"}]
    tree = STRtree(components)

    def _assign(pads: list[PadInstance]) -> dict[int, list[PadInstance]]:
        by_comp: dict[int, list[PadInstance]] = defaultdict(list)
        for p in pads:
            pt = Point(p.x, p.y)
            best, best_d = None, float("inf")
            for i in tree.query(pt):
                d = components[int(i)].distance(pt)
                if d < best_d:
                    best, best_d = int(i), d
            if best is None:
                for i, comp in enumerate(components):
                    d = comp.distance(pt)
                    if d < best_d:
                        best, best_d = i, d
            by_comp[best].append(p)
        return by_comp

    hv_by, selv_by = _assign(hv), _assign(selv)
    conflicts = []
    for ci in sorted(set(hv_by) & set(selv_by)):
        a, b = hv_by[ci], selv_by[ci]
        best = min(
            (
                (h, s, ((h.x - s.x) ** 2 + (h.y - s.y) ** 2) ** 0.5 - h.radius - s.radius)
                for h in a
                for s in b
            ),
            key=lambda t: t[2],
        )
        conflicts.append(
            {
                "component_index": ci,
                "component_area_mm2": round(components[ci].area, 2),
                "hv_pads": len(a),
                "selv_pads": len(b),
                "closest_pair": (
                    f"{best[0].ref}.{best[0].number} <-> {best[1].ref}.{best[1].number}"
                ),
                "closest_circle_model_gap_mm": round(best[2], 4),
            }
        )
    return len(components), conflicts


def hv_reachability(
    board: BoardData,
    manifest: Manifest,
    board_poly,
    copper,
    cell: float,
    half_width_mm: float = HALF_WIDTH_MM,
) -> dict:
    """#690 Part C at one raster resolution and one required half-width.

    Key 0 = "in no admissible HV-side space at all": that pad could only lie
    INSIDE the barrier, which check 5 forbids for copper. It is a stranded
    group in its own right, never a silent drop."""
    import shapely
    from scipy.ndimage import distance_transform_edt, label

    hv = [p for p in board.pads if p.net_name in manifest.hv_nets and p.layers]
    selv = [p for p in board.pads if p.net_name in manifest.selv_nets and p.layers]
    minx, miny, maxx, maxy = board_poly.bounds

    xs = np.arange(minx + cell / 2, maxx, cell)
    ys = np.arange(miny + cell / 2, maxy, cell)
    gx, gy = np.meshgrid(xs, ys)
    cu = shapely.contains_xy(copper, gx, gy)
    inb = shapely.contains_xy(board_poly, gx, gy)
    dist = distance_transform_edt(~cu, sampling=cell)

    def _cells(pads):
        msk = np.zeros_like(inb)
        for p in pads:
            r = int((p.y - ys[0]) / cell + 0.5)
            c = int((p.x - xs[0]) / cell + 0.5)
            if 0 <= r < len(ys) and 0 <= c < len(xs):
                msk[r, c] = True
        return msk

    capable = (dist >= half_width_mm) & inb
    lab, n = label((~capable) & inb)
    selv_blobs = {int(v) for v in np.unique(lab[_cells(selv) & (lab > 0)])}
    absorbable = np.isin(lab, [i for i in range(1, n + 1) if i not in selv_blobs]) & (lab > 0)
    plab, _ = label(capable | absorbable)

    groups: dict[int, list[str]] = defaultdict(list)
    for p in hv:
        r = int((p.y - ys[0]) / cell + 0.5)
        c = int((p.x - xs[0]) / cell + 0.5)
        key = int(plab[r, c]) if (0 <= r < len(ys) and 0 <= c < len(xs)) else 0
        groups[key].append(f"{p.ref}.{p.number}")
    ordered = sorted(groups.values(), key=len)
    homeless = len(groups.get(0, []))
    return {
        "cell_mm": cell,
        "required_width_mm": round(2 * half_width_mm, 4),
        "hv_pads": len(hv),
        "selv_pads": len(selv),
        "hv_reachability_components": len(groups),
        "hv_pads_with_no_admissible_space": homeless,
        "stranded_groups": [sorted(g) for g in ordered[:-1]] if len(ordered) > 1 else [],
        "connected": len(groups) == 1 and 0 not in groups,
    }


def channel_bisect(board, manifest, board_poly, copper, cell: float = 0.20) -> dict:
    """Widest corridor width at which the HV copper pads stay CONNECTED.

    #690 reports 5.728mm for the committed placement: below that width the HV
    side is one component, above it ``R24`` strands. That number is the
    "widest available channel", and ``8.0 - it`` is the shortfall. Bisects on
    half-width to 0.001mm."""
    lo, hi = 0.05, HALF_WIDTH_MM  # lo assumed connected, hi assumed split
    lo_res = hv_reachability(board, manifest, board_poly, copper, cell, lo)
    if not lo_res["connected"]:
        return {"widest_connected_width_mm": None, "note": "split even at 0.10mm width"}
    hi_res = hv_reachability(board, manifest, board_poly, copper, cell, hi)
    if hi_res["connected"]:
        return {
            "widest_connected_width_mm": round(2 * hi, 4),
            "note": "connected at the full 8.0mm bar; no shortfall",
        }
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if hv_reachability(board, manifest, board_poly, copper, cell, mid)["connected"]:
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.0005:
            break
    return {
        "widest_connected_width_mm": round(2 * lo, 4),
        "shortfall_mm": round(MIN_BARRIER_WIDTH_MM - 2 * lo, 4),
        "cell_mm": cell,
    }


def analyse(board_path: Path, label: str, do_bisect: bool) -> dict:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    manifest = load_manifest(MANIFEST)
    board = load_board(board_path)
    board_poly = Polygon(board.board_outline)
    pads = exact_pad_polygons(board_path)
    copper = unary_union(pads)

    hv, selv, dropped = classified_pads(board, manifest, board_poly)
    out: dict = {
        "provenance": {"commit": PROVENANCE_COMMIT, "dirty": False},
        "label": label,
        "board": str(board_path),
        "min_barrier_width_mm": MIN_BARRIER_WIDTH_MM,
        "obstacle_model": "reroutable (exact rotated pad outlines only)",
        "board_area_mm2": round(board_poly.area, 2),
        "pad_copper_area_mm2": round(copper.intersection(board_poly).area, 2),
        "hv_pads_used": len(hv),
        "selv_pads_used": len(selv),
        "pads_excluded_from_proof": [f"{p.ref}.{p.number} ({d}): {w}" for d, p, w in dropped],
    }
    print(f"=== {label} :: {board_path}")
    print(f"    outline area {board_poly.area:.1f} mm^2, pad copper {out['pad_copper_area_mm2']} mm^2")
    print(f"    classified copper pads: HV={len(hv)} SELV={len(selv)}")

    # ---- TEST 1: pairwise separability (#690 Part B) -------------------
    ambient = board_poly.buffer(50.0, quad_segs=8)  # barrier may leave/re-enter
    free = ambient.difference(copper)
    o = _opening(free, HALF_WIDTH_MM)
    rest = board_poly.difference(o) if not o.is_empty else board_poly
    n_regions, conflicts = _mixed_components(_components(rest), hv, selv)
    out["test1_pairwise"] = {
        "corridor_space_in_board_mm2": (
            round(o.intersection(board_poly).area, 2) if not o.is_empty else 0.0
        ),
        "regions_outside_opening": n_regions,
        "mixed_domain_regions": len(conflicts),
        "passes": len(conflicts) == 0 and n_regions >= 2,
        "conflicts": conflicts[:5],
    }
    print(
        f"    TEST 1 (pairwise): regions={n_regions} mixed={len(conflicts)} -> "
        f"{'PASS' if out['test1_pairwise']['passes'] else 'FAIL'}"
    )
    for c in conflicts[:3]:
        print(f"        mixed region #{c.get('component_index')}: {c}")

    # ---- TEST 2: HV-side connectivity (#690 Part C) --------------------
    per_res = [
        hv_reachability(board, manifest, board_poly, copper, cell) for cell in (0.4, 0.25)
    ]
    for r in per_res:
        if r["hv_pads_with_no_admissible_space"]:
            tag = f"IMPOSSIBLE ({r['hv_pads_with_no_admissible_space']} HV pad(s) homeless)"
        elif r["connected"]:
            tag = "CONNECTED"
        else:
            tag = f"SPLIT into {r['hv_reachability_components']}"
        print(f"    TEST 2 cell={r['cell_mm']}mm: HV copper reachability -> {tag}")
        for g in r["stranded_groups"]:
            print(f"        STRANDED: {len(g)} HV pad(s) {g}")
    agree = {r["connected"] for r in per_res}
    verdict = "possible" if agree == {True} else ("impossible" if agree == {False} else "resolution-dependent")
    out["test2_hv_connectivity"] = {"per_resolution": per_res, "verdict": verdict}

    if do_bisect:
        out["channel_bisect"] = channel_bisect(board, manifest, board_poly, copper)
        print(f"    channel bisect: {out['channel_bisect']}")

    admissible = out["test1_pairwise"]["passes"] and verdict == "possible"
    out["barrier_necessary_conditions_met"] = admissible
    print(
        f"    => necessary conditions for a conforming barrier: "
        f"{'MET (not ruled out)' if admissible else 'NOT MET (no barrier of any shape)'}\n"
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", type=Path, default=REPO_ROOT / "pcb" / "temper.kicad_pcb")
    ap.add_argument("--label", default="board")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--channel-bisect", action="store_true")
    args = ap.parse_args()

    result = analyse(args.board, args.label, args.channel_bisect)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
