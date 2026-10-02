# Task 01 status: layout parasitics and switching transient

**Read this first.** It is the current answer for task 01 and is updated as
results land. The round folders are the lab notebook behind it
([ROUNDS.md](ROUNDS.md)); open findings and risks are in
[FINDINGS.md](FINDINGS.md). Last updated 2026-10-02.

Board: `native-17/section.kicad_pcb`. Leg A (Q2 high / Q3 low, driver U1)
is extracted and simulated; leg B is queued. Evidence class: simulation and
model-based throughout. **No physical qualification is claimed.**

## Bottom line

| Question | Current answer | Confidence |
| --- | --- | --- |
| Board loop inductances (leg A) | Extracted by FEM as a 4-port matrix (C38 loop, C39 loop, two gate loops), extrapolated to zero closure height, crop-corrected | provisional: 3 mm points still solving |
| Nominal operation (S1, 170–280 V, 37 A, 348 ns dead time) | **passes**: die VDS within limit, off-gate 2.03–2.54 V (< 3.0 V), soft-switches (ZVS) in all 18 cases | model result |
| Dead-time margin | off-gate limit crossed **between 307 and 348 ns**; 307 ns fails every nominal case (3.45–4.01 V) | **open risk**: real worst-case dead time unknown (D-5) |
| Hard turn-on (S4, −20 A) | **fails at every dead time**: die VDS up to 543 V (> 520 V), off-gate up to 5.1 V | **open risk**: hinges on the body-diode recovery model (D-3, D-8) |
| Overcurrent (S2, 280 V / 61–71 A) | passes at ≥ 391 ns; 2 marginal fails at 348 ns (3.12–3.14 V) | model result |
| Light load (S3, 2–10 A) | passes at ≥ 348 ns; 12 fails at 307 ns | model result |

Verdict definitions, criteria and all cases: [round17/d2/README.md](round17/d2/README.md).
Criteria: die VDS ≤ 520 V (S2 ≤ 585 V), off-device VGS < 3.0 V
(3.5 V min threshold − 0.5 V; D-6 checks it at hot junction), |VGS| ≤ 30 V,
ZVS for nominal S1 at 348 ns.

## Current best inputs

| Item | File | Notes |
| --- | --- | --- |
| Board matrix, h → 0, crop-corrected | [`round17/d2/legA-h0-lin12-m20corr.matrix.txt`](round17/d2/legA-h0-lin12-m20corr.matrix.txt) | straight line through 1 and 2 mm closures + per-entry 20 mm crop correction; SPD |
| Same, uncorrected | [`round17/d2/legA-h0-lin12.matrix.txt`](round17/d2/legA-h0-lin12.matrix.txt) | grid v2 ran on this; the correction changes no verdict |
| SPICE deck | [`round17/d2/leg_matrix.cir`](round17/d2/leg_matrix.cir) | Infineon IPW65R018CFD7 L1 model (package L included); 5-port bulk variant [`leg_matrix5.cir`](round17/d2/leg_matrix5.cir) |
| Package / part inductances | [`round17/PACKAGE-INDUCTANCE.md`](round17/PACKAGE-INDUCTANCE.md) | capacitor ESL swept 5/10/20 nH (assumed; D-7) |
| Grid results | [`round17/d2/results/grid-h0-lin12-v2/`](round17/d2/results/grid-h0-lin12-v2/) (510 cases), [`grid-h0-lin12-m20corr/`](round17/d2/results/grid-h0-lin12-m20corr/) (240) | fixed grid code (D-4 findings) |

Leg A matrix, h → 0 lin12, crop-corrected (nH; P1 C38, P2 C39, P3 gate high, P4 gate low):

```
P1  26.59  16.09   3.54   5.08
P2  16.09  25.97   3.30   5.29
P3   3.54   3.30  25.94  -0.21
P4   5.08   5.29  -0.21  36.30
```

## How far to trust it

Checked and passing: the solver (exact on qualification fixtures), the
reciprocity mutuals (independent pair-solve energies: M12 on a coarse
mesh 18.106446 vs 18.106450 nH; M13 3.747410 vs 3.747422 nH; M34
−0.295904 vs −0.295900 nH, sign confirmed), port identity and orientation, the circuit wiring (agrees with
round 3's deck to < 1 % at near-zero board L), the air box (+0.7 %) and
defeaturing (−0.7 %). Crop margin: converged by 20 mm, corrected per entry,
no verdict changes.

Known limits, each tracked in [FINDINGS.md](FINDINGS.md):
- **Mesh:** P1 is not yet mesh-converged (31.84 / 32.27 / 33.05 nH at
  1.0 / 0.7 / 0.35 mm edges).
- **Extrapolation to zero closure height:** early 3 mm diagonals move P1/P2
  by −0.6 % / −1.1 % from the straight line.
- **Bulk-capacitor current path:** not yet in the FEM; this is the largest
  unrepresented effect.
- **Diode recovery model** (S4).
- **Dead time at the gates** (D-5).
- **Capacitor ESL** (D-7).

## Running and pending

| Work | Where | State |
| --- | --- | --- |
| 3 mm closure matrix (fine mesh) → parabolic extrapolation | remote box | P1, P2 done; P3, P4 running |
| Leg B matrix | remote box | queued after leg A |
| 5-port bulk model (port at C6) | Mac | queued |
| Extrapolation test with 0.5 / 2 / 3 mm closures on the coarse mesh | Mac | queued |
| D-5 gate dead time, D-6 off-gate remedies, D-7 capacitor ESL, D-8 double-pulse plan, D-9 review, D-10 J4 interface | delegated ([briefs](round17/delegation/README.md)) | not started |
| Diode-recovery data, TI timing limits at 39 kΩ, controller dead time, C38 ESL | outside input | open |

## Superseded results (do not use)

- The round-1 verdict in [README.md](README.md) (BLOCKED, native-13), and
  rounds 2–5's reference/heuristic inductances: replaced by the round-17
  FEM matrix.
- Round 15's mesh (spurious PEC columns) and round 16's first values.
- Round 17's **first matrix** (DG-averaged fields; withdrawn, README §5).
- Round 17's grid v1 (`results/grid-h1/`, `results/grid-h0-lin12/`):
  stale-cache and ZVS-verdict defects (D-4); use grid v2.
