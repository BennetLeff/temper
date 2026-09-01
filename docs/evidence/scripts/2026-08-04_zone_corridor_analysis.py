#!/usr/bin/env python3
"""Corridor-feasibility analysis for the MAINS_SELV_ISOLATION_BARRIER keepout
(docs/evidence/2026-08-04-domain-first-resolve-keepout.md).

The falsification (2026-08-03_mains_selv_barrier_falsification.py) showed the
current board's copper-free space is 12.6% in 99 fragments with no edge-to-
edge corridor. Zones (pours) are PLACEMENT-INDEPENDENT -- a placement re-solve
moves footprints (pads), never the 96 copper zones. So the question that
decides whether ANY placement can open a barrier corridor is:

  Does the ZONE-ONLY free space (board outline minus the union of the 96
  copper-zone outline polygons) contain a connected component that spans
  two opposite board edges with an inscribed 8.0mm disk (inradius >= 4.0)?

If NO: the keepout is impossible regardless of the ring re-solve -- the
residual obstruction is copper-exclusion (checks 4+5), placement-independent.
If YES: pads (which the re-solve can move) are the blocker, and freeing the
ring refs (or more) can open the corridor.

# provenance: commit=ab11daaba37f1fca17d057fd087110a663e01deb dirty=false
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))

import check_isolation_keepout as _ck  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

BOARD = REPO / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO / "elec" / "domain_manifest.yaml"


def main() -> None:
    board = _ck.load_board(BOARD)
    outline = Polygon(board.board_outline)
    minx, miny, maxx, maxy = outline.bounds

    zone_geoms = [
        g for cz in board.copper_zones if (g := _ck._polygon_or_none(cz.polygons)) is not None
    ]
    zone_union = unary_union(zone_geoms)
    zone_free = outline.difference(zone_union)
    comps = list(zone_free.geoms) if zone_free.geom_type == "MultiPolygon" else [zone_free]
    comps = [c for c in comps if not c.is_empty and c.area > 1e-6]
    board_area = outline.area

    print(f"board outline: {board.board_outline}  area={board_area:.0f} mm^2")
    print(f"zones: {len(zone_geoms)}  zone-union coverage: {zone_union.area / board_area * 100:.1f}%")
    print(f"zone-free fraction: {zone_free.area / board_area * 100:.1f}% "
          f"({zone_free.area:.0f} mm^2) in {len(comps)} component(s)")

    eps = 0.01
    edge_polys = {
        "left": Polygon([(minx, miny), (minx + eps, miny), (minx + eps, maxy), (minx, maxy)]),
        "right": Polygon([(maxx - eps, miny), (maxx, miny), (maxx, maxy), (maxx - eps, maxy)]),
        "bottom": Polygon([(minx, miny), (maxx, miny), (maxx, miny + eps), (minx, miny + eps)]),
        "top": Polygon([(minx, maxy - eps), (maxx, maxy - eps), (maxx, maxy), (minx, maxy)]),
    }
    # A corridor host must touch two OPPOSITE edges (left/right or top/bottom).
    opposite = {("left", "right"), ("right", "left"), ("top", "bottom"), ("bottom", "top")}
    hosts = []
    for i, c in enumerate(comps):
        s = {k for k, e in edge_polys.items() if c.intersects(e)}
        if len(s) >= 2 and any((a, b) in opposite for a in s for b in s):
            hosts.append((i, c, s))

    print(f"\ncomponents touching 2 OPPOSITE edges (corridor hosts): {len(hosts)}")
    for i, c, s in hosts:
        eroded = c.buffer(-4.0)
        inradius_ok = not eroded.is_empty
        print(f"  comp {i}: edges={sorted(s)} area={c.area:.0f} mm^2 "
              f"inradius>=4.0 (8mm disk): {inradius_ok} "
              f"eroded_area={0 if eroded.is_empty else eroded.area:.0f} mm^2")
        print(f"    bbox=({c.bounds[0]:.1f},{c.bounds[1]:.1f})-({c.bounds[2]:.1f},{c.bounds[3]:.1f})")

    # Also: the largest inscribed disk of any zone-free component (upper bound
    # on what a placement solve could ever open).
    best = None
    for i, c in enumerate(comps):
        if c.area < 1:
            continue
        for t in (4.0, 3.0, 2.0, 1.0):
            e = c.buffer(-t)
            if not e.is_empty:
                if best is None or t > best[0]:
                    best = (t, i, c)
                break
    if best:
        t, i, c = best
        print(f"\nlargest zone-free component inradius >= {t:.0f}mm: comp {i} "
              f"area={c.area:.0f} mm^2 bbox={c.bounds}")
        er = c.buffer(-t)
        print(f"  eroded core area={er.area:.0f} mm^2; "
              f"core bbox=({er.bounds[0]:.1f},{er.bounds[1]:.1f})-({er.bounds[2]:.1f},{er.bounds[3]:.1f})")

    print("\nVERDICT: zone-free corridor" + (" EXISTS" if hosts else " DOES NOT EXIST") +
          " -- a keepout is" + ("" if hosts else " NOT") +
          " possible for ANY placement (zones are placement-independent).")


if __name__ == "__main__":
    main()
