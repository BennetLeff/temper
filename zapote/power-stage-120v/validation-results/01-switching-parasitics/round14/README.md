# D1-FEM round 14: 2.5-D layered mesher (work in progress, blocked)

- Board: native-17. Operator: Claude, 2026-09-28. No solve ran.
- Script: `scripts/mesh25d.py` (closures: `closures-legA.json`).

## What works

The layered method itself works: with a hand-built planar arrangement
(noded outlines, polygonized, one gmsh plane surface per face), leg A
without barrels meshed in **24 s**: 113k 2-D triangles, 38 z-levels, 12.0 M
tetrahedra, all four port sheets present (P1 544, P2 442, P3 52, P4 30
faces), PEC and far-field faces found, 3.2 GB peak. Extrusion,
classification and the sorted-vertex tetrahedral split are fast and
conform by construction.

## What blocks it: the 2-D arrangement of real board outlines

| 2-D arrangement | Result |
| --- | --- |
| One face, all outlines embedded | gmsh point location effectively quadratic; >10 min, stopped |
| Polygonized faces, 1 µm grid | 87 zero-volume tetrahedra from zero-area faces (min 7×10⁻¹⁵ mm²) |
| Common 5 µm grid | 801 zero-volume tetrahedra; faces of ~10⁻¹⁷ mm² (collinear overlaps) |
| Re-noded after snapping | 203 faces < 10⁻⁴ mm², 19 self-touching faces; gmsh "NULL points" |
| OCC 2-D fuzzy fragment (tolerance 5 µm) | fragment succeeds; 2-D meshing then segfaults (Frontal-Delaunay and Delaunay) or fails (MeshAdapt: "unable to find ...") |

The size is also too large as run (12 M tetrahedra ≈ 29 GB by the round-12
memory trend); coarsening z and the far field was the next step.

## Assessment

The obstacle in rounds 11, 13 and 14 is the same one, seen three ways: the
board's real copper outlines (zone fills with many holes, pads, thermal
spokes, 0.2 mm clearances, near-coincident edges across layers) are hard to
turn into a clean, conforming geometry with open-source kernels. The
physics, the solver (round 12) and the port definitions are ready.
