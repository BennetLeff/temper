#!/usr/bin/env python3
"""Measure per-block spatial dispersion on the committed board, for the
2026-08-07 placement-clustering-feasibility study.

Reuses `block_edge_estimate.py`'s component->block classification (net-name
prefix matching + a hand-built override crosswalk + hub-net-excluded
adjacency propagation) so this script's block membership is IDENTICAL to
the one that already produced the "8/11 blocks cover >=84% of the board"
bounding-box finding in
`docs/plans/2026-08-07-003-feat-routing-block-decomposition-plan.md`. This
script adds two dispersion metrics that bounding box alone does not
capture, so a future re-placement attempt has more than one number to beat:

  1. **Radius of gyration** (mm) -- root-mean-square distance of each
     block's components from their own centroid. Unlike bounding box, this
     is not dominated by a single outlier component; it reflects how
     "spread out" the typical component is. A tightly clustered block of
     N components occupying a small patch has small Rg; a block whose
     components are smeared across the board has Rg approaching the
     board's own Rg.
  2. **Convex hull area** (mm^2), as a fraction of the board's own convex
     hull area. Bounding box can be inflated by a single far corner
     component in a way that doesn't reflect the block's overall footprint
     as well as its hull does; hull area also directly lower-bounds the
     keepout/exclusion-zone area a real re-placement would need to reserve
     per block.

Reads pcb/temper.kicad_pcb (read-only) and elec/src/main.ato /
elec/src/modules.ato (read-only, via tools/block_partition.py). Writes
nothing to any of those files -- per task rules, pcb/temper.kicad_pcb is
never modified. Pure stdlib (no numpy/scipy dependency), since this repo's
default python3 in this shell is 3.9 and the package itself requires
>=3.11.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_edge_estimate as bee  # noqa: E402
import block_partition as bp  # noqa: E402

BOARD_W, BOARD_H = 152.0, 234.0
BOARD_ORIGIN = (20.0, 20.0)  # Edge.Cuts rectangle origin, per block_edge_estimate.py


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def radius_of_gyration(points: list[tuple[float, float]]) -> float:
    if not points:
        return 0.0
    cx, cy = centroid(points)
    ss = sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in points)
    return (ss / len(points)) ** 0.5


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain. O(n log n). Returns hull vertices CCW,
    deduplicated, without the closing repeat of the first point."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def polygon_area(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    a = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--margin-mm", type=float, default=15.0)
    args = ap.parse_args()

    pcb_text = bee.PCB_FILE.read_text()
    ref_pos, ref_nets = bee.parse_footprints(pcb_text)

    net_to_refs: dict[str, set[str]] = {}
    for ref, nets in ref_nets.items():
        for net in nets:
            net_to_refs.setdefault(net, set()).add(ref)

    ref_block: dict[str, set[str]] = {}
    for ref, nets in ref_nets.items():
        blocks: set[str] = set()
        for net in nets:
            blocks |= bee.classify_net_block(net)
        if blocks:
            ref_block[ref] = blocks

    bee.propagate_unknown(ref_nets, net_to_refs, ref_block)

    all_points = [ref_pos[r] for r in ref_pos]
    board_rg = radius_of_gyration(all_points)
    board_hull = convex_hull(all_points)
    board_hull_area = polygon_area(board_hull)
    board_bbox_area = BOARD_W * BOARD_H
    board_diag = (BOARD_W**2 + BOARD_H**2) ** 0.5

    report = {}
    for block in bp.TOP_INSTANCES:
        pts = [ref_pos[r] for r, bl in ref_block.items() if block in bl and r in ref_pos]
        n = len(pts)
        if n == 0:
            report[block] = {"n_components": 0}
            continue
        rg = radius_of_gyration(pts)
        hull = convex_hull(pts)
        hull_area = polygon_area(hull) if n >= 3 else 0.0
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys)) if n >= 2 else 0.0
        report[block] = {
            "n_components": n,
            "radius_of_gyration_mm": round(rg, 1),
            "radius_of_gyration_frac_of_board": round(rg / board_rg, 3) if board_rg else None,
            "convex_hull_area_mm2": round(hull_area, 1),
            "convex_hull_area_frac_of_board_hull": round(hull_area / board_hull_area, 4)
            if board_hull_area
            else None,
            "bbox_area_mm2_no_margin": round(bbox_area, 1),
            "bbox_area_frac_of_board_no_margin": round(bbox_area / board_bbox_area, 4),
        }

    if args.json:
        print(
            json.dumps(
                {
                    "board_radius_of_gyration_mm": round(board_rg, 1),
                    "board_convex_hull_area_mm2": round(board_hull_area, 1),
                    "board_bbox_area_mm2": board_bbox_area,
                    "board_diagonal_mm": round(board_diag, 1),
                    "blocks": report,
                },
                indent=2,
            )
        )
        return 0

    print(
        f"Whole-board Rg = {board_rg:.1f} mm | hull area = {board_hull_area:.0f} mm^2 "
        f"({board_hull_area / board_bbox_area * 100:.1f}% of bbox) | diagonal = {board_diag:.1f} mm"
    )
    print()
    hdr = f"{'block':<12}{'comps':>7}{'Rg(mm)':>9}{'Rg%board':>10}{'hull mm2':>11}{'hull%board':>12}{'bbox%board':>12}"
    print(hdr)
    for block in bp.TOP_INSTANCES:
        r = report[block]
        if r["n_components"] == 0:
            print(f"{block:<12}{0:>7}{'--':>9}{'--':>10}{'--':>11}{'--':>12}{'--':>12}")
            continue
        rgfrac = r["radius_of_gyration_frac_of_board"]
        hullfrac = r["convex_hull_area_frac_of_board_hull"]
        bboxfrac = r["bbox_area_frac_of_board_no_margin"]
        print(
            f"{block:<12}{r['n_components']:>7}{r['radius_of_gyration_mm']:>9.1f}"
            f"{(rgfrac or 0) * 100:>9.1f}%{r['convex_hull_area_mm2']:>11.0f}"
            f"{(hullfrac or 0) * 100:>11.1f}%{bboxfrac * 100:>11.1f}%"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
