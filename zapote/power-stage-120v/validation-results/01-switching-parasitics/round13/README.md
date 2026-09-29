# D1-FEM round 13: leg-A model built; the 3-D mesh still fails

- Board: native-17 (round-4 FlashLayer export). Operator: Claude, 2026-09-28.
- **Status: BLOCKED at meshing.** The leg-A model (copper, 28 barrels, the
  11 closures of D1-FEM §2 with the round-6 arches, 4 driven port sheets)
  builds, and its surface mesh is clean (no duplicate triangles across 7,323
  surfaces), but every 3-D mesh attempt failed at a local spot. No solve ran.
- Scripts: `scripts/build_leg_model.py`, `closures-legA.json`.
  Attempts: `results/leg-a-mesh-attempts.json`.

## What was built

- **Closures** (`closures-legA.json`, native-17 pads): P1 across C38, P2
  across C39, P3 across U1.15→U1.14, P4 across U1.10→U1.9 as driven flat
  sheets (constant direction, 0.6 mm wide, K = 1/0.6 mm per ampere); bridges
  over Q2 and Q3 drain–source, R5 pads 1–4, R10, R12, and Q2/Q3 gate–source
  one level (1 mm) higher so they clear the drain–source arches. Each closure
  is two PEC legs on its pads plus the span at h above the top copper.
- **Barrels:** 16-sided footprints joined to their net's copper on every
  layer in 2-D, and gap prisms between layers.

## 3-D mesh attempts (all at h = 1 mm)

| Construction | Failure |
| --- | --- |
| Gap prisms imprinted on the layer faces | segments intersect at a 16-gon vertex on In1 (C40.2) |
| Barrels merged after simplification, boolean tolerance 0.1 µm (HXT; also Delaunay) | same spot; Delaunay: boundary recovery failed |
| Layers split into barrel 16-gons plus the rest | 58 air volumes (micro-gaps) and duplicate facets |
| Gap prisms 5 µm into the layers, fused per net | segments intersect on the underside of In2 at the edge of the 3.8 mm BUS_P clearance hole around C39.2; the same at 0.15/0.4 mm |

The last construction is clean in every way I could check (75 copper
volumes, 2 air volumes, the plane outline valid and simple, no duplicate
surface triangles), but the mesher still finds crossing segments.

## Assessment and recommendation

Rounds 11 and 13 fixed about a dozen local defects, and each fix exposed
the next. Building exact 3-D solids from PCB copper with OpenCASCADE
booleans, then meshing them, doesn't converge to a working model on this
board. That isn't a physics or solver problem: round 12's solver is
qualified, and the barrel-free geometry meshes.

The robust method for a layered board is a **2.5-D layered mesh**, which
needs no 3-D booleans:
1. Overlay every layer's copper outline, barrel footprint and closure
   footprint into one planar arrangement, and mesh it once in 2-D
   (conforming to every outline).
2. Extrude that 2-D mesh through the stack's z-levels (and above and below
   the board for the air), so every layer uses the same nodes.
3. Mark each extruded cell as copper or air by which outline it falls in on
   that layer; the copper cells are removed, and their faces become the PEC
   boundary. Barrels are the footprint cells through the dielectric.
4. Closures above the board: extrude the leg footprints up to h, and the
   port sheet is a set of cell faces at height h.

This is how PCB field tools mesh boards. It gives a conforming mesh by
construction. It's a focused tool to build (a few hundred lines, using
gmsh's 2-D mesher and its extrusion, or building the prisms directly), and
it's the recommended round 14.

## Reproduce an attempt

```sh
export PYTHONPATH=/opt/homebrew/lib
X=../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz
/Users/bennet/Miniforge3/bin/python3 scripts/build_leg_model.py $X legA.msh --leg A \
    --h-near 0.6 --h-edge 0.25 --closures closures-legA.json --arch-h 1 --algo3d 10
```
