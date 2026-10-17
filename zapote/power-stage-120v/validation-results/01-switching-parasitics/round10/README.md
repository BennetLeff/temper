# D1-FEM round 10: Elmer carries the fixtures

- Board: unchanged native-17 (not solved in this round).
- Solver: Elmer 64-bit direct (`Big Umfpack`), first-order edge elements,
  `/tmp/ps-r6-fem-elmer-install` (round-6 build). Operator: Claude,
  2026-09-28. Every number is in `results/elmer-fixtures.json`; meshes and
  logs are local (regenerate with `../round9/scripts/` and
  `scripts/run_elmer_fixture.py`).
- Evidence class: simulation/model-based.
- **Verdict: Elmer passes every fixture the board model needs (flat ports on
  the boundary and inside the air; self and mutual inductance, all exact) and
  respects the plate bound. The limit is memory: a converged direct solve of
  a board leg probably doesn't fit 32 GB, and may not fit 64 GB.**

## Results

| Fixture | Elmer | Exact / bound |
| --- | ---: | ---: |
| Plate section, port on the boundary | 3.141592 nH | 3.141593 nH |
| Plate section, port 2 mm inside (Palace diverged here) | 3.141592 nH | 3.141593 nH |
| Two ports in one gap (x = 0 boundary, x = 20 mm interior): L₁₁ / L₂₂ / **M** | 3.141592 / 1.884956 / **1.884956 nH** | 3.141593 / 1.884956 / 1.884956 nH |
| Board-style plates (70 µm, cut from the air, interior port, 40 mm margin), 0.5 mm | 2.785094 nH (154k tets, 2.9 GB, 62 s) | ≤ 3.141593 |
| Same, 0.35 mm | 2.808988 nH (403k tets, 9.9 GB peak, 417 s) | ≤ 3.141593 |
| Same, Richardson (energy error ∝ h²; estimate) | ≈ 2.832 nH | Wheeler 2-D: 2.873 |

Each fixture ran at 0.76–0.83 GB except the thick plates. The two-port
mutual comes from three solves (each port alone, then both):
M = (L_both − L₁₁ − L₂₂)/2.

**Rejected fixture:** Palace's `rings` geometry, linearized for Elmer, gave
L₁₁ 22.7 pH, L₂₂ 407 pH, M 1.23 pH against approximate analytic 41.8, 707,
1.97 pH. The rings are 1 µm zero-thickness strips meshed coarsely at their
edges, where first-order elements are far under-resolved; the "analytic"
values are themselves approximations. It isn't used for either solver. The
two-port plate section replaces it as the exact mutual fixture.

## Memory, and what it means for the board

Peak memory rose from 2.9 to 9.9 GB for 154k → 403k tetrahedra, about
N^1.27. A board leg crop needs the same 0.25–0.35 mm resolution near its
copper over a much larger region; a rough estimate is 2–5 million
tetrahedra, which by this trend needs 80–250 GB for a direct solve. At
0.5 mm (about 1.7 % below the converged value on the plates), a crop of
around a million tetrahedra would need about 30 GB. These are estimates;
the real count comes from meshing the board crop.

## Next (round 11)

1. **Mesh the leg-A board crop only** (no solve), per D1-FEM §3 with the
   round-6 arch rules, at 0.5 and 0.35 mm near the copper. Record the
   tetrahedron count. It's cheap, and it settles the machine question.
2. If 0.5 mm fits 32 GB: solve on this Mac, both legs, with the arch-height
   extrapolation. If it needs up to ~60 GB: the 64 GB desktop. Beyond that: a
   lower-memory direct solver (MUMPS, out-of-core) or an iterative Elmer
   solver qualified against these direct results within 1 %.
3. The two-port section, the boundary/interior section and the thick plates
   become the regression set for every solver or mesh change.

## Reproduce

```sh
PY=/Users/bennet/Miniforge3/bin/python3; export PYTHONPATH=/opt/homebrew/lib
$PY ../round9/scripts/make_plate_section.py sect.msh --h 0.25
$PY ../round9/scripts/make_plate_section.py secti.msh --h 0.25 --behind 2
$PY ../round9/scripts/make_plate_section.py sect2.msh --h 0.25 --second-port 20
$PY ../round9/scripts/make_thick_plates.py thick.msh --h-near 0.35
$PY scripts/run_elmer_fixture.py sect.msh run-sect --pec 2 --port 4 --k 0 0 100
$PY scripts/run_elmer_fixture.py sect2.msh run-12 --pec 2 --port 4 --k 0 0 100 --port2 5 --k2 0 0 100
$PY scripts/run_elmer_fixture.py thick.msh run-thick --pec 2 --port 4 --k 0 0 100
```
