# Clamp bar STEP check (scripts/bench_bar_verify.py; do not edit)

File: `fab/clamp-bar/bench-clamp-bar-r1.step`, re-imported with build123d / OCP. Part frame: x = u from the bar's left end, y = v from its lower edge, z = 0 back face, z = 9.525 face A (pockets open here). Geometric tolerance 0.001 mm.

| check | measured | expected | verdict | note |
|---|---|---|---|---|
| bench_params.py vs drill-table.md | 0 disagreements | 0 | PASS |  |
| STEP length unit | MILLI METRE | MILLI METRE | PASS |  |
| solids in file | 1 | 1 | PASS |  |
| bounding box min (x, y, z) | 0.0000, 0.0000, 0.0000 | 0.0000, 0.0000, 0.0000 | PASS |  |
| bounding box size L x H x t | 130.5000 x 25.4000 x 9.5250 | 130.5000 x 25.4000 x 9.5250 | PASS |  |
| volume mm3 | 29272.284 | 29272.284 | PASS |  |
| faces other than plane / cylinder | 0 | 0 | PASS |  |
| cylindrical faces | 6 | 6 | PASS |  |
| planar faces (6 box + 4 floors) | 10 | 10 | PASS |  |
| pocket Q5: centre u, v | 20.9500, 9.0000 | 20.9500, 9.0000 | PASS |  |
| pocket Q5: diameter | 9.5300 | 9.5300 | PASS | axis along z |
| pocket Q5: depth from face A | 7.0000 | 7.0000 +/- 0.05 | PASS |  |
| pocket Q5: flat floor at z 2.525 | plane, 1 circle r 4.7650, area 71.331 | plane, 1 circle r 4.7650, area 71.331 | PASS |  |
| pocket Q6: centre u, v | 38.9500, 9.0000 | 38.9500, 9.0000 | PASS |  |
| pocket Q6: diameter | 9.5300 | 9.5300 | PASS | axis along z |
| pocket Q6: depth from face A | 7.0000 | 7.0000 +/- 0.05 | PASS |  |
| pocket Q6: flat floor at z 2.525 | plane, 1 circle r 4.7650, area 71.331 | plane, 1 circle r 4.7650, area 71.331 | PASS |  |
| pocket Q3: centre u, v | 61.0500, 9.0000 | 61.0500, 9.0000 | PASS |  |
| pocket Q3: diameter | 9.5300 | 9.5300 | PASS | axis along z |
| pocket Q3: depth from face A | 7.0000 | 7.0000 +/- 0.05 | PASS |  |
| pocket Q3: flat floor at z 2.525 | plane, 1 circle r 4.7650, area 71.331 | plane, 1 circle r 4.7650, area 71.331 | PASS |  |
| pocket Q2: centre u, v | 79.0500, 9.0000 | 79.0500, 9.0000 | PASS |  |
| pocket Q2: diameter | 9.5300 | 9.5300 | PASS | axis along z |
| pocket Q2: depth from face A | 7.0000 | 7.0000 +/- 0.05 | PASS |  |
| pocket Q2: flat floor at z 2.525 | plane, 1 circle r 4.7650, area 71.331 | plane, 1 circle r 4.7650, area 71.331 | PASS |  |
| end hole 1: centre u, v | 4.0000, 12.7000 | 4.0000, 12.7000 | PASS |  |
| end hole 1: diameter | 4.5000 | 4.5000 | PASS | axis along z |
| end hole 1: through (z extent) | 0.0000 .. 9.5250 | 0.0000 .. 9.5250 | PASS |  |
| end hole 2: centre u, v | 126.5000, 12.7000 | 126.5000, 12.7000 | PASS |  |
| end hole 2: diameter | 4.5000 | 4.5000 | PASS | axis along z |
| end hole 2: through (z extent) | 0.0000 .. 9.5250 | 0.0000 .. 9.5250 | PASS |  |
| BR1 driver slot absent (option a) | metal at u 105.20, v 3.90/7.40/10.90: [True, True, True] | all True | PASS |  |

Derived (not checks): pocket floor web 2.525 mm; smallest hole-to-end wall 1.750 mm; smallest hole-to-edge wall 4.235 mm; mass 79.0 g at 2.70 g/cm3.

**32 PASS, 0 FAIL.**
