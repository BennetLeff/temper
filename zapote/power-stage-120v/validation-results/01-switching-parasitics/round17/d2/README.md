# Round 17 D2: switching transient on the FEM board matrix (provisional)

`leg_matrix.cir` is round 3's complementary-leg deck (same Infineon L1
models, driver output-resistance approximation, snubbers, shunt, ramped
current-source load, solver options) with the board copper replaced by the
FEM 4-port matrix: one coupled inductor per FEM port (C38 branch, C39
branch, high-side gate path, low-side gate path) and `K` from the FEM
mutuals. The common-source effect comes from the power-to-gate mutuals, not
a separate `LCS`. Not from the FEM: the bulk path `LBULK` (round-3
heuristic), capacitor ESL `LESL` (TDK bound ≤ ~20 nH; swept), shunt `LSHUNT`
(Vishay 0.5–5 nH). The Infineon model already has the TO-247 leads.

**Wiring check** (`run_d2.py --wiring-check`): with every board inductance
0.01 nH and no coupling, this deck and round 3's describe the same circuit;
all six die measures agree to < 1 % (VDS LS/HS, VGS max/min both devices).

## Provisional case: leg A, 1 mm matrix (arches included), 170 V, 37 A, LS turn-off, 348 ns

| LESL | LS die VDS peak | HS die VDS peak | LS gate after HS on-command (max) | aborted |
| --- | ---: | ---: | ---: | --- |
| 5 nH | 191.2 V | 170.9 V | 2.20 V | no |
| 10 nH | 195.0 V | 171.0 V | — | no |
| 20 nH | 202.7 V | 171.0 V | 2.07 V | no |

Against the task criteria (01-switching-parasitics.md): VDS ≤ 520 V and
off-device VGS < 3.0 V (3.5 V min threshold − 0.5 V) both hold in this one
case. Round 3's single case with heuristic inductances failed both (724 V,
7.37 V); the main difference is its assumed 11.5 nH common-source
inductance, where the FEM gives power-to-gate coupling k = 0.12–0.16.

**Provisional only:** one case, the 1 mm matrix (closure arches included,
10 mm crop margin which round 17's sensitivity runs show overstates L by
several percent), no S2 fault (61/71 A at 280 V), S3, S4, DIR=1 or
dead-time corners yet. The full grid runs on the h -> 0 matrix.

## Full grid on the 1 mm matrix (provisional; `grid.py`, `results/grid-h1/`)

306 cases (task Step 3: S1 37 A, S2 61/71 A at 280 V, S3 2/5/10 A, S4 −20 A
hard turn-on; buses 170/198/280 V; both directions; dead time 250/348/450
ns; capacitor ESL 5/10/20 nH). 162 pass, 144 fail, 6 aborted in ngspice
(S3, 280 V, 2/5 A, HS turned off first, ESL 20 nH).

| Case | dt 250 ns | dt 348 ns | dt 450 ns | Cause |
| --- | --- | --- | --- | --- |
| S1 nominal | 18/18 fail | 0/18 | 0/18 | gate still above 3 V at the partner's on command |
| S2 fault 61/71 A | 12/12 fail | 2/12 (71 A, LS-first: 3.05–3.15 V) | 0/12 | same |
| S3 light load | 54/54 fail | 2/54 | 2/54 | same at 250 ns; 6 aborted runs |
| **S4 hard turn-on** | **18/18 fail** | **18/18 fail** | **18/18 fail** | **gate rebound 3.2–5.0 V; VDS 484–544 V (> 520 V in 33)** |

- ZVS holds in every S1 case at 348 ns.
- At 250 ns dead time the turned-off gate has not yet fallen below 3 V when
  the partner is commanded on (shoot-through risk): a gate-drive timing
  result, little dependent on board inductance; the driver is an
  output-resistance approximation.
- **S4 mechanism** (170 V, −20 A, 348 ns, ESL 10 nH waveform): the LS body
  diode's reverse-recovery current reaches +89 A, then snaps (LS die VDS
  24 → 400 V in ~4 ns, ~95 V/ns, 15 A/ns); the loop rings at ~41 MHz (24 ns),
  overshooting to 541 V; the dV/dt couples through Cgd and lifts the LS gate
  to 4.4 V (> 3.5 V min threshold). Hard turn-on occurs only when ZVS is
  lost, so S4 bounds an operating region, not nominal operation. Diode
  recovery is from Infineon's 27 °C L1 model and the 1 mm matrix includes
  the closure arches, so both magnitude and margin are provisional. Fixes
  (named per the task, not implemented): negative gate-off bias or an
  active Miller clamp; slower high-side turn-on to soften the recovery.

## Grid on the straight-line h -> 0 matrix (`legA-h0-lin12.matrix.txt`, `results/grid-h0-lin12/`)

Board-only matrix extrapolated from 1 and 2 mm (provisional until 3 mm):
L = 28.24 / 26.48 / 25.97 / 36.37 nH (P1..P4), k12 0.62, power-to-gate
k 0.13–0.17; C38 ∥ C39 board loop ≈ 22.1 nH. Positive definite.

166 pass, 140 fail, 0 aborted. Same pattern as the 1 mm matrix: every
case fails at 250 ns dead time (gate still on at the partner's command);
at 348/450 ns only S2 71 A LS-first (2 cases, marginal) and **all of S4**
fail. S3's 348/450 ns failures and the six aborted runs disappear. S4:
die VDS 461–543 V (> 520 V in 23 of 54, all < 650 V), off-gate rebound
3.25–5.14 V. Highest VDS outside S4: 449.8 V. Removing the arches barely
changes the result: the S4 outcome is set by the diode recovery and the
gate drive more than by the loop inductance (see the delegation briefs
D-1 to D-3).

## Grid v2 on the same matrix, fixed `grid.py` (`results/grid-h0-lin12-v2/`)

Rerun after the D-4 fixes (identity-checked reuse, ZVS in the task verdict,
timing-only cause labels), with D-1's tolerance corners 307 and 391 ns added:
510 cases, 0 aborted, **292 task pass / 218 fail**. Every failure includes the
off-gate criterion (< 3.0 V); 39 also exceed 520 V die VDS (all S4). The
stress and task counts are equal: every nominal S1 case at 348 ns soft-switches
(ZVS), so the ZVS condition removed no passes here.

| Case | 250 ns | 307 ns | 348 ns | 391 ns | 450 ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 nominal 37 A | 0/18 | 0/18 | 18/18 | 18/18 | 18/18 |
| S2 OCP 61/71 A, 280 V | 0/12 | 0/12 | 10/12 | 12/12 | 12/12 |
| S3 light load 2–10 A | 0/54 | 42/54 | 54/54 | 54/54 | 54/54 |
| S4 hard turn-on, −20 A | 0/18 | 0/18 | 0/18 | 0/18 | 0/18 |

- **307 ns, D-1's lower tolerance estimate, fails nominal S1 everywhere:**
  off-gate 3.45–4.01 V (limit 3.0 V; 250 ns: 5.2–5.3 V), all at the partner's
  on command, i.e. the off device's gate has not yet discharged. At 348 ns
  S1 off-gate is 2.03–2.54 V. The dead-time margin is therefore between
  307 and 348 ns, and D-1's interval (307–391 ns) is an estimate, not a
  guaranteed bound, so **dead time is a live risk**, not a stress corner to
  discard.
- S2 at 348 ns: the two failures are 280 V/71 A, LS first, ESL 5/10 nH,
  3.12–3.14 V (marginal).
- S3 at 307 ns: 12 failures at 2 A, 3.01–3.43 V, labelled `later_peak`
  (the peak comes after the partner's command; a timing observation, not a
  diagnosed cause).
- S4 fails at every dead time: die VDS up to 543.4 V, off-gate 3.25–5.14 V,
  unchanged from v1. D-3 (diode recovery) is the open question there.

All of this is on the provisional lin12 matrix and the 4-port deck, which
omits the bulk-path coupling (README §11 at round-17 level); results move
with the 3 mm extrapolation, the crop correction and the 5-port check.
