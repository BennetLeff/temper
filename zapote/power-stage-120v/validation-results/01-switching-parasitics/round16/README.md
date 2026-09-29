# D1-FEM round 16: an iterative solver that converges on the board, and a spurious-via bug

- Board: unchanged native-17 copper export. Leg A, P1 (C38) alone, 1 mm
  arches, deliberately crude mesh (1.2 mm edges, 3 mm margin and air).
- Mesher: `scripts/mesh25d_hybrid.py` (round-15 mesher plus: only the board
  and closure band is extruded, outer air is free tetrahedra; mesh size
  follows short boundary segments; faces thinner than 20 µm are merged into
  a neighbour; no face may be dropped).
- Solvers: Elmer rev a19504a built on the 24-core Linux box (conda env
  `temper-fem`, MPI + MUMPS + Hypre 2.32) and the round-6 Mac build.
  `scripts/run_elmer.py` (round-12 runner plus Hypre AMS, MPI, Linux time).
  Operator: Claude, 2026-09-29. Numbers are in `results/`.
- Evidence class: simulation/model-based.
- **Verdict: Hypre GMRES(100) + AMS converges on a board mesh and matches
  the direct solve there to all printed digits (18.15053 nH both). But
  every board mesh before the thin-face merge contained two spurious PEC
  columns shorting all four copper layers, so 18.15 nH (round 15) and
  18.54 nH are wrong. The first board solve without them gives
  29.771 nH (P1 alone, crude mesh, one arch height) — a solver-validated
  number on a crude model, not the board's loop inductance.**

## 1. The solver: Hypre GMRES + AMS, qualified

Every local iterative option stalled on the board mesh (BiCGStabl/ILU1,
GCR, IDR(s), and BiCGStabl with the tree gauge: 3.5e-3 to 1e-2 after 3000
iterations, IDR(s) diverged). The fixtures never needed more.

On the Linux box, Hypre's AMS (the auxiliary-space multigrid built for
curl-curl edge elements), singular mode (no conductivity anywhere):

| Case | BiCGStab + AMS | GMRES(100) + AMS | Exact |
| --- | ---: | ---: | ---: |
| Plate section, boundary port | 3.141592 (60 its) | 3.141592 (85) | 3.141593 |
| Plate section, interior port | 3.141592 (56) | 3.141592 (83) | 3.141593 |
| Two-port L11 / L22 | 3.141592 / 1.884956 | 3.141592 / 1.884956 | 3.141593 / 1.884956 |
| Two-port both (M = 1.884956) | 8.79646 | 8.79646 | 8.796459 |
| Thick plates 0.35 mm | 2.808988 (81) | 2.808988 (117) | 2.808988 (direct, round 10) |
| Thick plates + 2 floating PEC blocks (coarse) | — | 2.762936 | 2.762936 (direct) |
| **Board, round-15 mesh (609 k tets), P1** | 7.5e-9 at 2000 its, then broke down | **18.15053** (6164 its, 25 min, 8 ranks) | **18.15053 (direct)** |

Two gate fixes were needed. Elmer ignores `Abort Not Converged` on the Hypre
path, and the residual lines in its log belong to the field-calculation CG,
not the AV solve. The first AMS board run (non-singular) "finished" with a
solution norm of 1e105. `run_elmer.py` now gates Hypre runs on Hypre's own
summary ("Required iterations N ... to norm R": N below the cap, R ≤ tol) and
rejects non-finite or absurd energies. PCG + AMS is not qualified (5000
iterations at 6.5e-10 on the plate section).

## 2. The bug: dropped 2-D faces became PEC columns (spurious vias)

The mesher skipped 2-D faces below 1e-4 mm² (slivers where layer outlines
nearly meet). A skipped face is a hole in the 2-D mesh; extruded, its walls
are PEC. Leg A had two, at board (135.65, 7.40) and (136.40, 18.47). Each
column touched copper on B.Cu, In2, In1 and F.Cu (`scripts/pec_columns.py`,
`port_loops.py`): a via shorting all four layers. In round 15 they also ran
to the outer box.

| Mesh (same geometry: air 26,105.8 mm³, PEC area within 0.002 %) | PEC columns | P1, GMRES+AMS |
| --- | ---: | ---: |
| Round 15, extruded air | 2 | 18.15053 nH (direct: 18.15053) |
| Round 16, free-tet outer air | 2 | 18.543654 nH |
| Round 16, + size follows segments | 2 | (see results) |
| Round 16, + thin-face merge | **0** | **29.77092 nH** (9356 its, 25 min) |

The mesher now merges thin faces instead of dropping them and refuses to
build if any face would be dropped. Negative control: with `--thin 0` it
stops and names the two faces.

## 3. Mesh quality (for the record)

Extruding only the band, letting size follow short segments, and merging
thin faces cut tets with aspect ratio > 100 from 4,108 to 497 and > 1000 from
170 to 2 (`scripts/tet_quality.py`). This helped less than expected: the
local solvers still stalled, and GMRES+AMS converges on the round-15 mesh
too. The merge matters for correctness (§2), not speed.

## 4. Other checks added

- `port_loops.py --closures`: which PEC body each port and closure end sits
  on. Every closure end in the full leg-A model lands on one body. A probe
  without the R5 shunt bridge opens P1's loop, as it should (negative
  control).
- `probe_remote.sh`: mesh-and-solve bisection on the remote box.

## Next

1. Commit this; re-solve the gated mesh.
2. Finer meshes (h_edge 0.35 → 5 M tets fits the remote box by memory:
   0.7 GB at 850 k on 8 ranks) and the full 10 mm margin/air.
3. All four ports (the 4 × 4 matrix), the three arch heights and the h → 0
   extrapolation.

## Reproduce

Mesh (Mac or the remote env):

```
X=../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz
python3 scripts/mesh25d_hybrid.py $X legA.msh --leg A --closures closures-legA.json \
  --arch-h 1 --h-edge 1.2 --h-far 3 --dz-max 0.8 --margin 3 --air 3 --simplify 0.05
python3 scripts/pec_columns.py legA.msh      # must be 0
python3 scripts/port_divergence.py legA.msh legA.log
python3 scripts/port_loops.py legA.msh legA.log --closures closures-legA.json
```

Solve (remote): `python3 scripts/run_elmer.py --elmer $ELMER legA.msh out
--pec 2 3 --port 10 --k -2500 0 0 --hypre-ams --hypre-method 8 --ams-singular
--tol 1e-10 --maxit 20000 --np 8`. Fixtures: `scripts/gmres_remote.sh`.
