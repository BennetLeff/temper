# D1-FEM round 15: defeatured leg-A mesh, first board solves

- Board: unchanged native-17 copper export
  (`../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz`).
- Mesher: `scripts/mesh25d_simple.py` (2.5-D extrusion of a defeatured
  planar arrangement; loop nets only, 0.1 mm open/close, 50 µm simplify,
  10 µm grid, layers snapped to each other at 30 µm). Closures:
  `closures-legA.json` (same 11 as round 13).
- Solver: Elmer, `../round12/scripts/run_elmer_fixture.py` (I1 = BiCGStabl
  degree 4 + ILU1, tol 1e-10, abort if not converged; direct = Big Umfpack
  with tree gauge). Operator: Claude, 2026-09-29. Numbers are in
  `results/leg-a-solves.json`; meshes and logs are local.
- Evidence class: simulation/model-based.
- **Verdict: no board inductance yet. The mesher works (5.5 M tets, no
  degenerate elements). The first solves stalled because the source was
  inconsistent; that defect is found, fixed and now gated. After the fix
  the iterative solve still stalls (≈4e-3 at 3000 iterations), so a second
  cause remains open.**

## What happened

| Run | Mesh | Result |
| --- | --- | --- |
| I1, P1 alone | 5.5 M tets (h_edge 0.35) | residual flat at ~1e-2 from iteration ~200; killed at ~1660 (31 min, 2.2 GB) |
| I1, P1 alone | 1.08 M tets (h_edge 1.2) | same stall (1.2–1.5e-2 at 280–320); killed |
| I1, P1 alone | 606 k tets (3 mm margin/air) | aborted at 1500, residual 1.07e-2 (201 s, 2.2 GB) |
| Direct, P1 alone | same 606 k | 18.256 nH, 24.1 GB peak, 26 min — **not a result** (leaky source, below) |
| I1, P1 alone, ports fixed | 609 k tets | aborted at 3000, residual 3.5e-3 (388 s) |

## Cause 1 (fixed): the P1/P2 sources leaked into the air

A constant sheet current K on the port triangles puts a source moment
s_i = Σ_T K·∇φ_i A_T on each node. Off PEC it must be zero; otherwise the
load vector has a component along the gradient null space of the ungauged
curl-curl operator, and no iterative solve can converge. (A direct solve
with a tree gauge still returns a number, which is why the direct run
"worked".)

`scripts/port_divergence.py` measured it. P1 and P2 leaked 0.133 A of their
1 A into the air, up to 0.0167 A at single nodes at y = 21.72 / 22.28 mm: the
30 µm layer snap had pulled the 0.6 mm strips' corners onto the C38/C39 pad
edges, so the strip sides were no longer parallel to K. The gate ports P3/P4
were clean (1e-16 A). `scripts/check_ports.py`, which only checks that the
strip ends touch PEC, had passed. Checking where the ends are isn't enough.

Fix: port strips are 0.4 mm wide (legs stay 0.6 mm) and not snapped, and the
mesher now computes the same leakage and refuses to write a mesh above
1e-9 A. The fixed mesh leaks 0.0 A on all four ports.

## Cause 2 (open): very stretched elements (likely)

`scripts/tet_quality.py` on the 1.08 M mesh: 12,372 tets have aspect ratio
(longest edge / shortest altitude) > 100, and 430 exceed 1000 (worst 7954).
10,352 of those 12,372 are in the graded air above and below the board.
There, sliver 2-D triangles (e.g. 0.05 × 0.7 mm, from short snapped
boundary segments) are extruded through 2–3 mm slabs; the median bad tet is
6× taller than wide. The fixed 609 k mesh has 4,108 tets above 100. None
of the fixtures had elements like these. Next: extrude only the board and
closure band, and fill the outer air with a free (unstructured) tet mesh,
then re-run I1. Only after that, try stronger solvers. (ILU2 gave the same
residuals as ILU1 on the leaky mesh, which was expected: the problem was the
source, not the preconditioner.)

## Reproduce

```
X=../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz
python3 scripts/mesh25d_simple.py $X legA-small-v2.msh --leg A --closures closures-legA.json \
  --arch-h 1 --h-edge 1.2 --h-far 3 --dz-max 0.8 --margin 3 --air 3 --simplify 0.05 > legA-small-v2.log
python3 scripts/port_divergence.py legA-small-v2.msh legA-small-v2.log
python3 scripts/tet_quality.py legA-small-v2.msh
python3 ../round12/scripts/run_elmer_fixture.py legA-small-v2.msh iter-P1 --pec 2 3 --port 10 \
  --k -2500 0 0 --iterative BiCGStabl --precond ILU1 --maxit 3000
```

The 5.5 M mesh: `--h-edge 0.35 --h-far 4 --dz-max 0.45` with the default
10 mm margin and air.
