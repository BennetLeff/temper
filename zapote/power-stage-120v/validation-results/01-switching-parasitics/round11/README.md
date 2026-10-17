# D1-FEM round 11: sizing the leg-A board mesh

- Board: native-17. Copper: the FlashLayer-aware all-net export committed in
  round 4 (`../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz`).
- Operator: Claude, 2026-09-28. gmsh 4.15.2 (Python API); no field solve.
- Evidence class: exact structural (element counts), estimate (memory).
- Results: `results/leg-a-sizing.json`. Meshes and logs are local.
- **Verdict: a direct solve of one board leg needs roughly 140–550 GB, beyond
  this Mac (32 GB) and the 64 GB desktop. The board needs an iterative
  solver. Barrel geometry also still has local defects.**

## Sizing (leg A, 10 mm copper margin, 10 mm air, no barrels)

| Size at copper edges / on copper faces | Tetrahedra | Estimated direct-solve peak |
| --- | ---: | ---: |
| 0.15 / 0.4 mm | 9,535,144 | ~550 GB |
| 0.20 / 0.5 mm | 5,167,468 | ~250 GB |
| 0.25 / 0.6 mm | 3,193,717 | ~140 GB |

The memory estimate extrapolates round 10's Elmer direct runs
(9.9 GB at 402,587 tetrahedra, peak ∝ N^1.27) a long way, and a board
matrix fills differently from a plate fixture, so treat it as order of
magnitude. The conclusion doesn't depend on the exact figure: even the
coarsest mesh is about twice 64 GB.

**Why it can't go coarser.** Copper of different nets sits 0.2 mm apart.
A surface element larger than about that cuts corners on round features
(antipads, pad rings) by more than the gap, and neighbouring surfaces'
facets cross; the 0.5 mm uniform mesh failed exactly this way. So sizing
has to be fine at copper *edges* (feature-driven: 0.15–0.25 mm) while
flat copper faces can be coarser; the planes' 0.44–0.5 mm dielectric gaps
set the face size for accuracy.

## Geometry: what failed and what works

KiCad's fused STEP copper (the D1-FEM §3 route) failed to mesh four ways
(overlapping facets at a via bore; facet intersections with filled vias,
with point merging, and with HXT). Its zone fills and pad rings leave
near-coincident faces.

`scripts/build_crop_geometry.py` builds the copper instead from the layer
polygons: union per net and layer, crop, snap to 1 µm, simplify at 10 µm,
extrude to the stackup z-ranges, fragment with the air box, and mesh only
the air with feature-driven sizing. **Without barrels it meshes cleanly**
(9.5 M tetrahedra in 33 s). With barrels it still fails at single spots,
each fixed in turn:
1. exact OCC cylinders against polygonal via rings → 16-sided prisms;
2. barrels overlapping same-net layer copper → barrel pieces only in the
   dielectric gaps, and within a layer only where the net has no copper;
3. fuse-then-cut leaving duplicate faces → fragment the air with every
   piece;
4. a barrel clipped at the crop edge coinciding with the clipped plane
   (C6.1) → drop barrels that straddle the crop;
5. still open: "two segments intersect" at (124.34, board y 22.34) mm, top of
   In1, inside C40.2's barrel footprint.

The surface-only mode (`--surface-only`) finds duplicate triangles and
names the surfaces, which located item 4.

## Next (round 12)

1. **Qualify an iterative Elmer solver on the exact fixtures** (the
   boundary and interior sections, the two-port section, the thick plates),
   each against the round-10 direct results within 1 % and with its own
   residual converged. Candidates: BiCGStab(l) or GCR with ILU; the AMS
   preconditioner with the gauge options Elmer documents (round 6's AMS run
   stagnated, and its verifier stays in force). Record memory and time.
   This is cheap and decides the board path.
2. Fix barrel item 5 and mesh with barrels; confirm the count is close to
   the no-barrel figure.
3. Only then add ports and arches, and solve.

## Reproduce

```sh
export PYTHONPATH=/opt/homebrew/lib
X=../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz
/Users/bennet/Miniforge3/bin/python3 scripts/build_crop_geometry.py $X legA.msh \
    --leg A --h-edge 0.25 --h-near 0.6 --algo3d 10 --no-barrels
```
