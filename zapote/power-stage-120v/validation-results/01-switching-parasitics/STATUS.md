# Task 01 status: layout parasitics and switching transient

**Read this first.** It is the current answer for task 01 and is updated as
results land. The round folders are the lab notebook behind it
([ROUNDS.md](ROUNDS.md)); open findings and risks are in
[FINDINGS.md](FINDINGS.md). Last updated 2026-10-03.

Board: `native-17/section.kicad_pcb`. Leg A (Q2 high / Q3 low, driver U1)
is extracted and simulated; leg B is queued. Evidence class: simulation and
model-based throughout. **No physical qualification is claimed.**

## Bottom line

| Question | Current answer | Confidence |
| --- | --- | --- |
| Board loop inductances (leg A) | Extracted by FEM as a 4-port matrix (C38 loop, C39 loop, two gate loops); **best matrix** = fine parabola through 1/2/3 mm + coarse low-height correction + crop correction | model result; mesh not fully converged (M1); 0.5 mm curvature transferred from the coarse mesh (M2) |
| Nominal operation (S1, 170–280 V, 37 A, 348 ns dead time) | **passes the 25 °C criterion** (best matrix, ESL 1.06–20 nH: off-gate 2.08–2.59 V < 3.0 V, die VDS ≤ 385 V, ZVS in all 24) but **fails D-6's provisional hot screen** (< 1.9 V) at 348 ns; passes it at ≥ 391 ns | **open**: the 3.0 V criterion is optimistic at hot junction (FINDINGS F5) |
| Dead-time margin | off-gate limit crossed **between 307 and 348 ns**; 307 ns fails every nominal case (3.45–4.01 V) | **open risk**: D-5 found the firmware does not establish ≥ 500 ns at the gates; keep 307 ns (F1) |
| Hard turn-on (S4, −20 A) | **fails at every dead time**: die VDS up to 543 V (> 520 V), off-gate up to 5.1 V | **open risk**: hinges on the body-diode recovery model (D-3, D-8) |
| Overcurrent (S2, 280 V / 61–71 A) | passes at ≥ 391 ns; 2 marginal fails at 348 ns (3.12–3.14 V) | model result |
| Light load (S3, 2–10 A) | passes at ≥ 348 ns; 12 fails at 307 ns | model result |
| Gate-drive remedy | D-6: ≈1 Ω discharge + 1 nF Cgs + −2 V off-bias passes **all** 32 decision cases (incl. S4 and 307 ns) against the 1.9 V screen: off-gate ≤ 0.51 V, die VDS ≤ 484 V, ZVS kept | **proposal**: needs a negative bias rail (board change, owner decision); 27 °C; refinement not fully converged (F6) |

Verdict definitions, criteria and all cases: [round17/d2/README.md](round17/d2/README.md).
Criteria: die VDS ≤ 520 V (S2 ≤ 585 V), |VGS| ≤ 30 V, ZVS for nominal S1 at
348 ns, and off-device VGS reported against **both** < 3.0 V (3.5 V minimum
threshold at 25 °C − 0.5 V) and D-6's provisional hot screen **< 1.9 V**
(model-derived; no guaranteed hot minimum exists) until vendor data settles it.

## Current best inputs

| Item | File | Notes |
| --- | --- | --- |
| **Board matrix (best)** | [`round17/d2/legA-h0-best.matrix.txt`](round17/d2/legA-h0-best.matrix.txt) | fine quad(1,2,3) + coarse [cubic − quad(1,2,3)] + crop correction; SPD, min eig 8.90 nH |
| Earlier straight-line matrix | [`round17/d2/legA-h0-lin12-m20corr.matrix.txt`](round17/d2/legA-h0-lin12-m20corr.matrix.txt) | lin(1,2) + crop correction; understates power-to-gate coupling (M2) |
| Same, uncorrected | [`round17/d2/legA-h0-lin12.matrix.txt`](round17/d2/legA-h0-lin12.matrix.txt) | grid v2 ran on this; the correction changes no verdict |
| SPICE deck | [`round17/d2/leg_matrix.cir`](round17/d2/leg_matrix.cir) | Infineon IPW65R018CFD7 L1 model (package L included); 5-port bulk variant [`leg_matrix5.cir`](round17/d2/leg_matrix5.cir) |
| Package / part inductances | [`round17/PACKAGE-INDUCTANCE.md`](round17/PACKAGE-INDUCTANCE.md) | capacitor ESL swept 5/10/20 nH (assumed; D-7) |
| **Grid results (best)** | [`round17/d2/results/grid-best/`](round17/d2/results/grid-best/) (680 cases, ESL 1.06–20 nH, 3.0 V and 1.9 V verdicts; 10 isolated solver aborts) | earlier: `grid-h0-lin12-v2/` (510), `grid-h0-lin12-m20corr/` (240) |

Leg A best matrix (nH; P1 C38, P2 C39, P3 gate high, P4 gate low):

```
P1  24.60  15.32   4.04   5.49
P2  15.32  23.85   3.87   5.74
P3   4.04   3.87  24.26  -0.26
P4   5.49   5.74  -0.26  35.68
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
- **Extrapolation to zero closure height:** curved near zero. A 0.5 mm test
  raises power-to-gate coupling 7–16 % and off-gate by 0.04–0.19 V; no
  verdict changes (FINDINGS M2).
- **Bulk-capacitor current path:** tested with a 5-port model; it shifts
  off-gate by ≤ 0.3 V and flips one marginal S2 case (FINDINGS F3).
- **Diode recovery model** (S4).
- **Dead time at the gates** (D-5).
- **Capacitor ESL** (D-7).

## Running and pending

| Work | Where | State |
| --- | --- | --- |
| Mesh convergence point (fine, 0.5 mm edges, h = 1 mm) | remote box | running |
| Leg B matrix | remote box | **paused** until the enclosure layout settles (restart note in the remote's `r17/chain_legB.out`) |

| D-5, D-6, D-8, D-9, D-10 | delegated ([reports](round17/delegation/README.md)) | **done, merged** (#1629–#1633); D-9's six tooling findings fixed (FINDINGS S8–S13) |
| D-7 capacitor ESL | delegated | waiting on TDK model access |
| D-11 bus-sense range (AMC1311B linear to ~240 V, < 280 V OVP; from D-10) | delegated | brief written |
| Diode-recovery data, TI timing limits at 39 kΩ, deployed four-PWM controller and harness, gate-drive remedy and hot criterion (owner), C38 ESL | outside input / owner | open |

## Board revisions: does a change need a rerun?

The extraction covers native-17. Copper more than 20 mm outside a leg's box
changed L by < 0.1 % (crop convergence), so moves elsewhere (connectors,
supplies, mounting, outline) do not need the FEM rerun. To check a new
revision:

```sh
python3 round17/scripts/leg_region_diff.py ../../native-17/section.kicad_pcb ../../native-NN/section.kicad_pcb
```

It compares footprints, pads, tracks, vias and zone fills inside each leg's
FEM region, and the stackup; it prints per leg `UNCHANGED` (no rerun) or
`CHANGED` (rerun that leg), exit code 2 if any rerun is needed. A change to
a power MOSFET's footprint or 3-D model offset is flagged separately: the
vendor model assumes standard TO-247 leads, so a taller mounting or longer
leads adds source/drain inductance that the board FEM does not see. Test:
`round17/scripts/test_leg_region_diff.py`.

## Superseded results (do not use)

- The round-1 verdict in [README.md](README.md) (BLOCKED, native-13), and
  rounds 2–5's reference/heuristic inductances: replaced by the round-17
  FEM matrix.
- Round 15's mesh (spurious PEC columns) and round 16's first values.
- Round 17's **first matrix** (DG-averaged fields; withdrawn, README §5).
- Round 17's grid v1 (`results/grid-h1/`, `results/grid-h0-lin12/`):
  stale-cache and ZVS-verdict defects (D-4); use grid v2.
