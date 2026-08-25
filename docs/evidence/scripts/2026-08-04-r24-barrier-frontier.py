#!/usr/bin/env python3
"""Where may R24 go? The displacement frontier for a barrier-admitting placement.

# provenance: commit=f2b09d84673b3a18d8fabe454230f1b240148f3d dirty=false

PR #690 proved that ``R24`` alone is why the committed placement admits no
``MAINS_SELV_ISOLATION_BARRIER`` of any shape, and named the fix -- move it --
without saying where to. This script computes the admissible set directly.

For each candidate origin on a raster, ``R24``'s two pads are REMOVED from the
copper model and RE-ADDED at the candidate, and the position is kept only if
it clears both bars:

  BAR 1 -- barrier admissibility. #690's Part-C HV-copper reachability test
    must report CONNECTED at 0.4mm AND at 0.25mm raster (verdicts must agree,
    as #690 requires). Evaluating with R24's own copper PRESENT is
    load-bearing: R24's pads are what close the 5.727mm channel they sit in,
    so a map computed with R24 removed wrongly marks its current position
    admissible.

  BAR 2 -- clearance. R24 carries HV copper, so its pads must sit >= 8.0mm
    from all non-HV copper -- the REQ-SAFE-01 DC_BUS<->LV_CONTROL figure, and
    also what ``generate_unclassified_hv_keepaway_constraints`` holds
    unclassified copper to (``MAX_IEC_MARGIN_MM``) -- and >= 0.5mm from other
    HV copper (ordinary clearance).

Bar 2 is not optional and is not a refinement: the nearest position that
satisfies bar 1 ALONE is 25.78mm away and measures a REQ-SAFE-01 creepage
violation (R24<->C36, 7.71mm < 8.0mm). Enforcing both bars moves the frontier
from 25.78mm to 37.28mm.

Because R24 is removed and re-placed at every candidate, the admissible SET is
independent of where R24 currently sits; only the displacement column depends
on the reference, which therefore defaults to R24's position at f2b09d846
(31.48, 21.24) so the numbers stay comparable after the board is written.

Usage:
  uv run --no-sync python docs/evidence/scripts/2026-08-04-r24-barrier-frontier.py \\
      [--step 1.0] [--json OUT.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_isolation_keepout import (  # noqa: E402
    MIN_BARRIER_WIDTH_MM,
    _rotate,
    load_board,
    load_manifest,
)

BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

HALF_WIDTH_MM = MIN_BARRIER_WIDTH_MM / 2.0
# R24 is HV. 8.0mm is the REQ-SAFE-01 DC_BUS<->LV_CONTROL minimum AND the
# unclassified-near-HV keepaway margin; 0.5mm is ordinary HV<->HV clearance.
MIN_GAP_NON_HV_MM = 8.0
MIN_GAP_HV_MM = 0.5
PROVENANCE_COMMIT = "f2b09d84673b3a18d8fabe454230f1b240148f3d"
# R24's position at f2b09d846 -- the placement the frontier is measured from.
REFERENCE_XY = (31.48, 21.24)


def _local_shape(shape: str, w: float, h: float, rr_ratio: float):
    from shapely.geometry import LineString, Point, Polygon

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


def load_geometry(board_path: Path, hv_nets: frozenset[str] | set[str]):
    """Exact rotated pad outlines, split into (other-HV, non-HV, R24-local)."""
    from kiutils.board import Board
    from shapely import affinity

    board = Board.from_file(str(board_path))
    copper_names = {ly.name for ly in board.layers if getattr(ly, "type", None) == "signal"}
    hv_geoms, non_hv_geoms, r24_local = [], [], []
    for fp in board.footprints:
        ref = (fp.properties or {}).get("Reference") or "<noref>"
        fx, fy = fp.position.X, fp.position.Y
        fang = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")
        for pad in fp.pads:
            lys = pad.layers or []
            if not any(ln in ("*.Cu", "*Cu") or ln in copper_names for ln in lys):
                continue
            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            dx, dy = _rotate(lx, ly, fang)
            w = getattr(pad.size, "X", 0.0) or 0.0
            h = getattr(pad.size, "Y", 0.0) or 0.0
            rr = getattr(pad, "roundrectRatio", None)
            rr = 0.25 if rr is None else rr
            g = _local_shape(getattr(pad, "shape", None) or "rect", w, h, rr)
            g = affinity.rotate(g, -(pad.position.angle or 0.0), origin=(0, 0))
            if ref == "R24":
                b = g.bounds
                r24_local.append(
                    {
                        "dx": dx,
                        "dy": dy,
                        "hw": (b[2] - b[0]) / 2.0,
                        "hh": (b[3] - b[1]) / 2.0,
                        "number": pad.number,
                    }
                )
                continue
            g = affinity.translate(g, fx + dx, fy + dy)
            net = pad.net.name if pad.net is not None else ""
            (hv_geoms if net in hv_nets else non_hv_geoms).append(g)
    return hv_geoms, non_hv_geoms, r24_local


class Raster:
    """One raster resolution of #690's Part-C reachability map."""

    def __init__(self, cell, board_poly, copper_without_r24, selv_pads, hv_pads_other, r24_local):
        import shapely
        from scipy.ndimage import distance_transform_edt

        self.cell = cell
        self.r24 = r24_local
        minx, miny, maxx, maxy = board_poly.bounds
        self.xs = np.arange(minx + cell / 2, maxx, cell)
        self.ys = np.arange(miny + cell / 2, maxy, cell)
        self.gx, self.gy = np.meshgrid(self.xs, self.ys)
        self.cu0 = shapely.contains_xy(copper_without_r24, self.gx, self.gy)
        self.inb = shapely.contains_xy(board_poly, self.gx, self.gy)
        self._edt = distance_transform_edt
        self.selv_cells = self._cells(selv_pads)
        self.hv_idx = [self._rc(p.x, p.y) for p in hv_pads_other]

    def _rc(self, x, y):
        return (
            int((y - self.ys[0]) / self.cell + 0.5),
            int((x - self.xs[0]) / self.cell + 0.5),
        )

    def _in(self, r, c):
        return 0 <= r < len(self.ys) and 0 <= c < len(self.xs)

    def _cells(self, pads):
        m = np.zeros_like(self.inb)
        for p in pads:
            r, c = self._rc(p.x, p.y)
            if self._in(r, c):
                m[r, c] = True
        return m

    def connected(self, ox, oy) -> bool:
        from scipy.ndimage import label

        m = np.zeros_like(self.inb)
        for pad in self.r24:
            cx, cy = ox + pad["dx"], oy + pad["dy"]
            m |= (np.abs(self.gx - cx) <= pad["hw"]) & (np.abs(self.gy - cy) <= pad["hh"])
        dist = self._edt(~(self.cu0 | m), sampling=self.cell)
        capable = (dist >= HALF_WIDTH_MM) & self.inb
        lab, n = label((~capable) & self.inb)
        selv_blobs = {int(v) for v in np.unique(lab[self.selv_cells & (lab > 0)])}
        absorbable = (
            np.isin(lab, [i for i in range(1, n + 1) if i not in selv_blobs]) & (lab > 0)
        )
        plab, _ = label(capable | absorbable)
        keys = set()
        for r, c in self.hv_idx:
            keys.add(int(plab[r, c]) if self._in(r, c) else 0)
        for pad in self.r24:
            r, c = self._rc(ox + pad["dx"], oy + pad["dy"])
            keys.add(int(plab[r, c]) if self._in(r, c) else 0)
        # key 0 == "no admissible HV-side space at all" -- never a silent drop.
        return len(keys) == 1 and 0 not in keys


def main() -> int:
    from shapely.geometry import Polygon
    from shapely.geometry import Polygon as P
    from shapely.ops import unary_union
    from shapely.strtree import STRtree

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", type=Path, default=BOARD)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--json", type=Path, default=Path(__file__).with_suffix(".json"))
    args = ap.parse_args()

    manifest = load_manifest(MANIFEST)
    board = load_board(args.board)
    board_poly = Polygon(board.board_outline)
    hv_geoms, non_hv_geoms, r24_local = load_geometry(args.board, manifest.hv_nets)
    selv = [p for p in board.pads if p.net_name in manifest.selv_nets and p.layers]
    hv_other = [
        p for p in board.pads if p.net_name in manifest.hv_nets and p.layers and p.ref != "R24"
    ]
    print(
        f"board {args.board}: other-HV pads {len(hv_geoms)}, non-HV pads {len(non_hv_geoms)}, "
        f"R24 pads {len(r24_local)}"
    )

    copper_wo = unary_union(hv_geoms + non_hv_geoms)
    tree_n, tree_h = STRtree(non_hv_geoms), STRtree(hv_geoms)

    def gaps(ox, oy):
        polys = []
        for pad in r24_local:
            cx, cy = ox + pad["dx"], oy + pad["dy"]
            polys.append(
                P(
                    [
                        (cx - pad["hw"], cy - pad["hh"]),
                        (cx + pad["hw"], cy - pad["hh"]),
                        (cx + pad["hw"], cy + pad["hh"]),
                        (cx - pad["hw"], cy + pad["hh"]),
                    ]
                )
            )
        dn = min(min(non_hv_geoms[int(i)].distance(g) for i in tree_n.query_nearest(g)) for g in polys)
        dh = min(min(hv_geoms[int(i)].distance(g) for i in tree_h.query_nearest(g)) for g in polys)
        return dn, dh

    r4 = Raster(0.4, board_poly, copper_wo, selv, hv_other, r24_local)
    r25 = Raster(0.25, board_poly, copper_wo, selv, hv_other, r24_local)

    ref = REFERENCE_XY
    print(f"reference (R24 at f2b09d846): {ref}; connected there? "
          f"{r4.connected(*ref)} / {r25.connected(*ref)}  (expect False/False)")

    minx, miny, maxx, maxy = board_poly.bounds
    t0 = time.time()
    stage1 = []
    for y in np.arange(miny + 1.5, maxy - 1.5, args.step):
        for x in np.arange(minx + 1.5, maxx - 1.5, args.step):
            dn, dh = gaps(float(x), float(y))
            if dn < MIN_GAP_NON_HV_MM or dh < MIN_GAP_HV_MM:
                continue
            stage1.append((float(x), float(y), dn, dh))
    print(f"bar 2 (clearance) alone: {len(stage1)} positions [{time.time()-t0:.0f}s]")

    t0 = time.time()
    rows = []
    for x, y, dn, dh in stage1:
        if not r4.connected(x, y) or not r25.connected(x, y):
            continue
        rows.append(
            {
                "x": round(x, 3),
                "y": round(y, 3),
                "manhattan_mm": round(abs(x - ref[0]) + abs(y - ref[1]), 3),
                "euclid_mm": round(float(np.hypot(x - ref[0], y - ref[1])), 3),
                "gap_non_hv_mm": round(dn, 3),
                "gap_hv_mm": round(dh, 3),
            }
        )
    print(f"bar 1 + bar 2: {len(rows)} positions survive [{time.time()-t0:.0f}s]")

    rows.sort(key=lambda r: r["manhattan_mm"])
    print("\nNEAREST admissible positions:")
    for r in rows[:10]:
        print(f"    {r}")
    out = {
        "provenance": {"commit": PROVENANCE_COMMIT, "dirty": False},
        "board": str(args.board),
        "step_mm": args.step,
        "reference_xy": list(ref),
        "bars": {
            "barrier_width_mm": MIN_BARRIER_WIDTH_MM,
            "rasters_mm": [0.4, 0.25],
            "min_gap_non_hv_mm": MIN_GAP_NON_HV_MM,
            "min_gap_hv_mm": MIN_GAP_HV_MM,
        },
        "positions_clearing_clearance_only": len(stage1),
        "positions_admissible": len(rows),
        "frontier_manhattan_mm": rows[0]["manhattan_mm"] if rows else None,
        "nearest": rows[:25],
        "roomiest": sorted(rows, key=lambda r: -r["gap_non_hv_mm"])[:10],
    }
    args.json.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {args.json.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
