# OPEN-ITEMS S3: F6 re-run on the s51 FEM matrices (2026-10-17)

**Question.** F6's 252/252-per-leg pass rested on round-17 loop matrices from board 76ec8cca (native-21 stage 5), not on the board of record.

**FEM (remote box, `chain_s3.sh` v2, 10 ranks, gmsh HXT outer boxes after the zero-volume-tet failure of the first run).** Round 17's native-21 coarse reference
(h 1 mm, 1.0 mm edges, 10 mm crop, Hypre GMRES(100) + singular AMS, tol 1e-8) re-extracted on the s51 copper (board 0b0ebcf7, copper key 3a4c616e7870; the
copper is unchanged at s52 and s53 for the power loops) and, as the control, on the n21 board (76ec8cca). All four meshes pass the mesh-quality gate
(q_min > 0): `legA21-h1-e1p0-{s51,n21}`, `legB21-h1-e1p0-{s51,n21}.matrix.txt` here.

**Decision matrices.** `d2/compose_s51.py` applies round 17's recipe (coarse + [native-19 best - coarse] + 2 nH on both gate-port diagonals) to the s51 coarse
matrices. Control: the recipe on the committed n21 coarse reproduces the committed s9b2 matrix (max abs difference 0.0 nH, `compose-summary-s51.json`). The primary (P) and the
control-differenced (D) variants agree to 0.01 nH, so the solver, rank count and mesher offsets cancel.

| (nH) | leg A cap ports | leg A pair | leg A gate ports | leg B cap ports | leg B pair | leg B gate ports |
|---|---|---:|---|---|---:|---|
| committed s9b2-n21 | 34.94, 37.45 | 32.00 | 55.02, 72.32 | 22.94, 21.06 | 18.07 | 55.09, 47.55 |
| s51 | 31.28, 33.47 | 28.32 | 60.05, 76.25 | 23.35, 21.60 | 18.56 | 58.04, 49.00 |
| change | -3.7, -4.0 | -3.7 | +5.0, +3.9 | +0.4, +0.5 | +0.5 | +2.9, +1.4 |

**F6 re-run** (`d2/f6_legs.py --diode pmeg --vneg -1.6 --temps 27,100,150`, the committed deck F6.cir sha 55a2058f..., decision and startup cases, matrices
`legA21 / legB21-h0-s9b2-s51`): **504/504 complete, 504/504 pass, 504/504 pass the 1.9 V hot screen** (252 per leg). Results: `d2/results/f6-vneg-m1p6-leg{A,B}21-s9b2-s51[-startup]/`.

| Case | committed worst die VDS | s51 worst die VDS | limit | committed max off-gate | s51 max off-gate | hot screen |
|---|---:|---:|---:|---:|---:|---:|
| leg A S1 | 351.0 | 352.9 | 520 | -0.897 | -0.752 | 1.9 |
| leg A S2 | 445.3 | 461.6 | 585 | -0.426 | -0.178 | 1.9 |
| leg A S4 | 467.6 | 462.7 | 520 | 0.694 | 0.751 | 1.9 |
| leg A S5 (startup) | 439.6 | 433.9 | 520 | 0.424 | 0.278 | 1.9 |
| leg B S1 | 359.0 | 358.6 | 520 | -0.674 | -0.554 | 1.9 |
| leg B S2 | 417.0 | 427.2 | 585 | 0.070 | 0.291 | 1.9 |
| **leg B S4** | **490.2** | **504.5** | **520** | **1.145** | **1.287** | **1.9** |
| leg B S5 (startup) | 405.3 | 407.3 | 520 | 0.182 | 0.319 | 1.9 |
The worst row is leg B, 27 C, S4, 170 V, IL -20 A, dead time 443 ns, ESL 10 nH: 504.47 V. **The leg B S4 margin to the 520 V screen halves, 29.8 V to 15.5 V**; off-gate margin to the hot
screen goes from 0.755 V to 0.613 V.

**What this does not cover.** (1) The decision matrices are composed by round 17's recipe, not extracted fresh with the fine mesh. (2) F6's deck is the older gate network; the stage-42 network
(68 ohm + 4.7 nF, DECISIONS 54/55, full grid 640/640, typical-Qrr S4 347.2 V) and the S6 max-Qrr study (SW_A 68.16 V/ns chord) also rest on the n21 matrices and were **not re-run** (the grid is
about 6 h on a loaded Mac and needs the vendor models restored beside `gate-network-2026-10-15/scripts`). (3) The leg B loop is +0.5 nH and the gate loops +1.4 to +5 nH higher than the
committed ones; the dv/dt screen at maximum Qrr (0.97 of the diode rating, S14) is the tight one and may move.
