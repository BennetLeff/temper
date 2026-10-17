# The as-built gate network on the s51 loop matrices (2026-10-17; OPEN-ITEMS S3, S14)

Adopted network (DECISIONS 54/55): 68 ohm 2512 turn-on, 1 ohm PMEG turn-off path, Cgs 4.7 nF (`split68_1_cgs4p7`). `gn.py full` grid, 640 cases, on:
- **n21**: the committed round-17 decision matrices `round17/d2/leg{A,B}21-h0-s9b2-n21.matrix.txt` (control);
- **s51**: the matrices recomposed from the s51 FEM re-extraction (`round17/results/matrices-s51/README.md`, `round17/d2/leg{A,B}21-h0-s9b2-s51.matrix.txt`).
Runs: `gn_run_s51.py` (tt125, the committed `gn.py` with the matrices swapped) and `gn_run_s6_s51.py` (tt260, the s6 `gn_s6.py` harness); `C8LIB` was pointed at the CFD7 library, which
is hashed into the identity only (the adopted configuration does not use the C8 model). `gn_compare.py` writes `compare-tt125.json` and `compare-tt260.json`. Raw rows: `full-tt{125,260}-{n21,s51}.json`.

| | tt125 n21 (control) | tt125 s51 | tt260 (max Qrr) n21 (control) | tt260 s51 |
|---|---:|---:|---:|---:|
| cases passing every screen | 640/640 | 640/640 | 640/640 | 640/640 |
| row pass/fail flips vs control | | none | | none |
| S1 worst die VDS (V) | 353.6 | 353.1 | 353.6 | 353.1 |
| S2 worst die VDS, fault (V) | 435.0 | **435.7** | 435.0 | **435.7** |
| S4 worst die VDS (V) | 347.2 | 346.8 | 383.9 | 381.5 |
| S5 worst die VDS (V) | 360.3 | 360.1 | 360.4 | 360.1 |
| S4 max diode slew (V/ns) | 49.70 | 49.29 | **68.16** | **67.43** |
| S4 max diF/dt (A/us) | 243.7 | 243.9 | 243.7 | 243.9 |
| max off-gate S4 (V) | 0.497 | 0.504 | 1.567 | 1.581 |

**Controls:** the n21 runs reproduce the committed typical-Qrr 347.2 V / 49.70 V/ns and the S6 maximum-Qrr 68.16 V/ns exactly.
**Result:** on the as-built network the s51 matrices change nothing that matters. Worst die VDS over all cases is **435.7 V** (the S2 fault case, limit 585 V); the worst S4 slew at maximum Qrr falls from 68.16
to **67.43 V/ns** (0.963 of the 70 V/ns rating, was 0.974).
**Limits:** the s51 decision matrices are composed by round 17's recipe from the coarse FEM matrices, not extracted with the fine mesh; the grid models the adopted network only.
