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

**Crop-margin correction** (`legA-h0-lin12-m20corr.matrix.txt`,
`results/grid-h0-lin12-m20corr/`, S1/S2/S4 = 240 cases): no verdict
changes against grid v2; die VDS moves −3.1 … +1.0 V and off-gate peak
−0.055 … +0.037 V. The ~2–5 % crop error in the power loops does not
affect any conclusion above.

## Bulk current mode: 5-port A/B/C test (`results/bulk-ab/`)

Closes the D-4 P1 current-mode question for the decision cases. The leg-A
model was re-extracted with a fifth FEM port at bulk capacitor C6
(`closures-legA5.json`; coarse mesh, h = 1 mm, 10 mm crop; matrix
`../results/matrices/legA5-h1-e1p0-m10.matrix.txt`, SPD, gates at round-off).
C6 couples to the gate loops about as strongly as the local capacitors do
(M53 3.34, M54 5.47 nH vs M13 3.75, M14 5.56 nH); the four existing
self-inductances moved < 0.1 % (largest mutual change 0.0027 nH, M12). Three variants on the same basis (h = 1 mm, 1.0 mm mesh),
S1/S2/S4 at 307 and 348 ns, ESL 10 nH, 32 cases each:

| Variant | Deck | Pass |
| --- | --- | ---: |
| a | 4-port, bulk 5.4 µF through LBULK | 9/32 |
| b | 5-port, C5 via LBULK + C6 via FEM L_P5, P5 couplings zeroed | 10/32 |
| c | 5-port, full coupling | 10/32 |

- Bulk split (a → b): die VDS −22 … +1 V, off-gate −0.29 … +0.05 V.
- **The omitted coupling itself (b → c): VDS −23 … +14 V, off-gate
  −0.11 … +0.29 V.**
- Only one verdict flips: S2 280 V / 71 A, LS first, 348 ns (3.07 V in a →
  2.92 V in c). All S1 verdicts, every S4 failure and the 307 ns failures
  are unchanged.
- The `bulk_mode.py` EMF estimate (14–48 V) was far too pessimistic:
  peak slew × mutual overstates the gate-loop effect, which the gate
  resistance and the brevity of the peaks suppress. It is kept as recorded,
  superseded by this direct test.

Basis: coarse mesh at 1 mm closures, not the h → 0 fine matrix; given
shifts of ≤ 0.3 V, a fine 5-port extraction is not warranted unless a
decision case sits within ~0.3 V of the 3.0 V limit.

## Zero-height extrapolation test with 0.5 mm closures (`results/extrap-test/`)

Coarse mesh (1.0 mm edges, 10 mm crop), full matrices at h = 0.5, 1, 2 mm
(`../results/matrices/legA-h{0p5,1,2}-e1p0-m10.matrix.txt`). The closure
inductance is not linear in h near zero: P1 rises 6.1 nH/mm between 0.5
and 1 mm but 4.8 nH/mm between 1 and 2 mm (P2 6.7 / 5.3, P3 4.6 / 3.6).
Against the straight line through 1 and 2 mm (what the campaign uses), a
parabola through 0.5 / 1 / 2 mm gives, entry by entry:

- self-inductances **−1.6 … −7.3 %** (power loops −6.3 / −7.3 %);
- power-to-gate mutuals **+7 … +16 %**; gate-to-gate M34 −24 % (more negative).

So lin(1, 2) is not conservative for the coupling terms that drive the
off-gate criterion. `../scripts/extrap_delta.py` adds this coarse-mesh
difference to the current best matrix (`legA-h0-quad05-m20corr.matrix.txt`,
SPD, min eig 9.06 nH; transfer assumed, as for the crop correction).
Decision cases (S1/S2/S4 at 307 and 348 ns, ESL 10 nH, 32 cases) on both
matrices with the current code:

- **no verdict changes** (9/32 pass on both);
- off-gate **+0.04 … +0.19 V in every case**; nominal S1 at 348 ns peaks at
  2.58 V (was 2.51 V), margin 0.42 V to the 3.0 V limit;
- die VDS −25.5 … +5.3 V;
- S2 280 V / 71 A, LS first, 348 ns: 3.08 → 3.22 V (fails on both).

Caveat: the 0.5 mm closure strips (0.6 mm wide) are narrower than the 1.0 mm
mesh edges, so part of the curvature may be mesh error; the fine-mesh
parabola through 1 / 2 / 3 mm (remote, last port solving) and the coarse 3 mm
matrix (Mac) are the cross-checks.

**With the coarse 3 mm matrix** (`legA-h3-e1p0-m10`), zero-height estimates
per entry (nH):

| Entry | lin(1,2) | quad(1,2,3) | quad(0.5,1,2) | cubic(0.5,1,2,3) |
| --- | ---: | ---: | ---: | ---: |
| L11 | 27.05 | 26.84 | 25.33 | 25.03 |
| L22 | 25.21 | 24.90 | 23.37 | 23.06 |
| L33 | 24.43 | 24.55 | 23.03 | 22.73 |
| L44 | 34.09 | 34.11 | 33.55 | 33.44 |
| M13 | 3.59 | 3.79 | 4.04 | 4.09 |
| M14 | 5.18 | 5.35 | 5.55 | 5.59 |
| M23 | 3.31 | 3.55 | 3.82 | 3.88 |
| M24 | 5.30 | 5.48 | 5.70 | 5.74 |

- The power-to-gate mutuals are **not monotonic in h**: M13 is
  3.84 / 3.75 / 3.91 / 4.26 nH at 0.5 / 1 / 2 / 3 mm, with a minimum near 1 mm,
  so the raw 0.5 mm value already exceeds lin(1,2).
- quad(1,2,3), the fine campaign's planned method, captures about 45 % of
  the mutual increase and almost none of the self-inductance drop; the
  0.5 mm point decides it (cubic and quad(0.5,1,2) agree to ~0.3 nH).
- Coarse and fine meshes agree on the 1→2→3 mm slopes to ~1 %
  (P1 4.79/4.59 vs 4.80/4.62; P2 5.34/5.03 vs 5.36/5.08; P3 3.59/3.70 vs
  3.61/3.75 nH/mm), which supports transferring the coarse low-height
  correction. Planned best matrix: fine quad(1,2,3) + coarse
  [cubic − quad(1,2,3)] + crop correction (`scripts/extrap_delta.py
  --base quad123 --h3 …`, then `scripts/margin_correct.py`).

## Capacitor ESL from TDK models (D-7, `results/esl-test/`)

D-7 (`../delegation/out-D7/`) derived resonance-equivalent ESL from TDK's
typical models: **C38–C41 1.060 nH**, **C5/C6 19.200 nH** (typical model
values, not mounted-part bounds; lead geometry unresolved). The grid's
5/10/20 nH sweep therefore started above the typical value. Decision cases
(S1/S2/S4 at 307/348 ns, 32 cases) at 1.06 vs 5 nH, both matrices:

| Matrix | Pass 1.06 / 5 nH | ΔVDS | Δ off-gate | S1 348 ns off-gate (1.06 nH) |
| --- | ---: | ---: | ---: | ---: |
| `legA-h0-lin12-m20corr` | 9 / 9 | −13.9 … +2.7 V | −0.065 … +0.064 V | 2.53 V |
| `legA-h0-quad05-m20corr` | 9 / 9 | −15.2 … +2.9 V | −0.096 … +0.067 V | 2.57 V |

No verdict changes, no aborts, ZVS kept. At 1.06 nH S4's die VDS falls
below 520 V (max 514.7 / 501.1 V); S4 still fails off-gate. Use
1.06–20 nH as the local ESL sweep. The 5-port deck still uses one LESL for
C6; with C6 at 19.2 nH (vs 10 nH used) the bulk branch carries less edge
current, so the bulk A/B/C coupling effect above is, if anything, overstated.

## Grid on the best matrix (`legA-h0-best.matrix.txt`, `results/grid-best/`)

Best matrix: fine quad(1,2,3) + coarse low-height correction [cubic(0.5,1,2,3)
− quad(1,2,3)] + crop correction (SPD, min eig 8.90 nH). ESL 1.06 / 5 / 10 /
20 nH (D-7), all five dead times: **680 cases, 10 aborted**. Every case is
reported against both off-gate criteria (`grid.py`: 3.0 V at 25 °C; D-6's
provisional 1.9 V hot screen).

| Case | 250 ns | 307 ns | 348 ns | 391 ns | 450 ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 nominal, 3.0 V / hot | 0 / 0 of 24 | 0 / 0 | **24 / 0** | 24 / 24 | 24 / 24 |
| S2 overcurrent | 0 / 0 of 16 | 0 / 0 | 12 / 0 | 16 / 16 | 16 / 16 |
| S3 light load | 0 / 0 of 72 | 47 / 0 | 69 / 0 | 70 / 46 | 70 / 52 |
| S4 hard turn-on | 0 / 0 of 24 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

- Against 3.0 V: 372 / 680 pass, the same pattern as grid v2. Nominal S1 at
  348 ns: off-gate 2.08–2.59 V, ZVS in all 24, die VDS ≤ 385 V.
- **Against the 1.9 V hot screen: 178 / 680; nominal operation passes only
  at ≥ 391 ns.** At the nominal 348 ns every S1 and S2 case fails it.
- S4: die VDS 441–536 V, off-gate 3.44–5.21 V; fails everywhere.
- **Aborts (10):** S3 280 V, direction 1: 5 A at ESL 20 nH and 10 A at
  1.06 nH, at every dead time ("timestep too small", node `bus`, at 2 µs and
  2 ps respectively). Indeterminate, not passes. The same operating points
  at neighbouring ESL (19 / 21 nH; 1.0 / 1.1 nH) converge with smooth
  results (348 ns: VDS 384 / 383 V and 296 / 296 V, off-gate 1.98 / 1.98 V and
  2.09 / 2.09 V), so the aborts are isolated solver failures, not a masked
  stress.

## Longer dead time as the hot-screen remedy (FINDINGS F7, `results/grid-best-longdt/`)

Best matrix, ESL 1.06 / 5 / 10 / 20 nH, dead times 391 / 443 / 498 ns:
a 443 ns nominal with D-1's tolerance stack scaled (307–391 ns around
348) gives ≈ 391 ns minimum and ≈ 498 ns maximum. ZVS is required at the
443 ns nominal (`grid.py --nominal-dt 443`). 408 cases, 6 aborted (the same
two S3 280 V points as in `grid-best`, at every dead time).

| Case (3.0 V / 1.9 V hot / ZVS) | 391 ns | 443 ns | 498 ns |
| --- | ---: | ---: | ---: |
| S1 nominal (of 24) | 24 / 24 / 24 | 24 / 24 / 24 | 24 / 24 / 24 |
| S2 overcurrent (of 16) | 16 / 16 / 16 | 16 / 16 / 16 | 16 / 16 / 16 |
| S3 light load (of 72) | 70 / 46 / 0 | 70 / 48 / 0 | 70 / 66 / 23 |
| S4 hard turn-on (of 24) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

- Across the whole 391–498 ns band, nominal S1 and S2 pass the hot screen
  with ZVS: S1 off-gate ≤ 1.06 V, S2 ≤ 1.72 V (0.18 V margin), die VDS ≤ 385 V.
- Light load (S3) does not soft-switch at 391–443 ns (it does not at 348 ns
  either); its hot-screen pass rate rises with dead time.
- S4 hard turn-on fails at every dead time; F7 does not address it.
- Not yet evaluated: switching and diode-conduction loss vs dead time (D-15),
  hot-junction transients (D-13), build details (D-12).

## Mesh convergence and its effect (FINDINGS M1, `results/mesh-sensitivity/`)

Leg A at h = 1 mm on four meshes (1.0 / 0.7 / 0.5 / 0.35 mm edges;
`../results/matrices/legA-h1-e{1p0-m10,0p7-fine,0p5-fine}.matrix.txt`,
`legA-h1-e0p35.matrix.txt`):

- **mutual inductances converge**: steps shrink; the power-to-gate couplings
  that drive the off-gate criterion move 0.3–0.6 % at the last step
  (M13 3.747 / 3.768 / 3.780 / 3.792 nH);
- **self-inductances do not**: +1.2–1.7 % per ~0.7× refinement with no
  shrinking (L11 31.836 / 32.272 / 32.636 / 33.047 nH), consistent with an
  unresolved edge singularity in thin copper; no asymptote can be extrapolated.

Effect, bounded pessimistically: `legA-h0-best-meshpess.matrix.txt` = best +
3 × (L[0.35] − L[0.5]) per entry (+1.2 … +2.1 nH on self-inductances, ≤ 0.5 nH
on mutuals; SPD). Native-18 decision cases (S1/S2/S4 at 391 / 443 / 498 ns,
443 ns nominal, ESL 1.06 and 10 nH, 96 cases) against `grid-best-longdt`:
**no verdict changes** (3.0 V and 1.9 V criteria, ZVS 12/12 at 443 ns);
off-gate −0.073 … +0.047 V, die VDS −2.9 … +6.9 V; S1/S2 off-gate ≤ 1.74 V.
One case aborted (S2 280 V / 71 A, direction 0, 443 ns, 10 nH, node `bus`);
rerun with D-14's `.options itl4=100000` it converges at 1.569 V (passes,
ZVS), and the same option reproduces the best-matrix result for that case to
every printed digit (1.588991 V, 335.2273 V) — further evidence that the
option does not change physics.

## Native-19 carry-over, leg A (`results/native19-carryover/`)

Native-19 (other session, integrated in #1647) reworked R5 (WSK2512 T2.21 mm
footprint, larger current pads, Kelvin pad R5.2 on `ocp_kelvin_p`) and the
In1 return plane around it, and rerouted U8: both legs' FEM regions changed
(`leg_region_diff.py`). Leg A re-extracted on native-19 copper at the coarse
reference (h = 1 mm, 1.0 mm edges, 10 mm crop; closures identical except the
R5 bridge on the new pad centres, `closures-legA-n19.json`; export by
`04-…/reextract-b3/extract_geometry.py`, which reproduces the committed
native-17 export exactly): `../results/matrices/legA-h1-e1p0-m10-n19.matrix.txt`.
Change vs native-17 at the same reference: power loops −1.08 / −1.19 %,
M12 −1.80 %, power-to-gate mutuals −0.10 … +0.68 %, gate loops ≤ 0.16 %.

`legA-h0-best-n19.matrix.txt` = best + that per-entry change (SPD, min eig
8.89 nH). Native-18/19 decision cases (S1/S2/S4 at 391 / 443 / 498 ns, 443 ns
nominal, ESL 1.06 and 10 nH, 96 cases) against `grid-best-longdt`: **no verdict
changes, no aborts**; off-gate −0.016 … +0.025 V, die VDS −3.3 … +1.2 V; S1/S2
off-gate ≤ 1.742 V (1.9 V hot screen), ZVS 12/12 at 443 ns. Round 17's leg-A
conclusions carry to native-19. Leg B: native-17 vs native-19 pair running.

## Leg B, first decision cases (provisional, `results/legB-prov-n19/`)

Leg B's own corrections are still running on the remote box (`b19corr`, then
the fine extraction `campB19`), so this run uses **`legB-h0-prov-n19.matrix.txt`**
(`compose_legB_prov.py`). It is leg B's native-19 coarse reference (h = 1 mm,
1.0 mm edges, 10 mm crop) plus leg A's per-entry correction to its best matrix
(best − coarse, native-19). Both legs' closure files orient every port the same
way semantically (bus_p → hv_ret, driver output → its return), so the entries
correspond one to one. The transfer is an assumption that leg B's real
corrections will test. SPD, min eigenvalue 7.87 nH.

Leg B differs from leg A at the reference mainly in the power loop: C41's self
inductance is +6 nH and M12 is +4.7 nH. The low-gate coupling to the power ports
is smaller (3.3–3.7 vs 5.5–5.8 nH) and the high-gate coupling slightly larger
(+0.2–0.5 nH).

Same 96 cases as the leg A carry-over (S1/S2/S4 at 391 / 443 / 498 ns, 443 ns
nominal, ESL 1.06 / 10 nH); comparison in `results/legB-prov-n19/compare-vs-legA.json`
(`compare_legs.py`):

- **No verdict changes and no aborts.** S1 36/36 and S2 24/24 pass the 3.0 V and
  1.9 V hot screens, with ZVS 12/12 at 443 ns.
- **Leg B has more off-gate margin than leg A:** S1 ≤ 1.03 V and S2 ≤ 1.29 V
  (leg A 1.74 V). S1/S2 die VDS ≤ 384 V.
- **S4 (already failing on off-gate) is worse on die VDS:** up to **537 V**
  (170 V, direction 1, 443 ns, 10 nH), +3 … +86 V vs leg A, and above the 520 V
  screen in 18/36 cases. Leg A stays ≤ 511 V. Any S4 remedy (FINDINGS F2, D-24
  answer (c)) must therefore be judged on leg B's power loop as well as leg A's.

Status: provisional until leg B's corrected matrix exists. Then rerun with
`grid.py --matrix <legB best> --out results/legB-best-n19 --only S1,S2,S4
--dt 391,443,498 --esl 1.06,10 --nominal-dt 443` and compare with this run
to test the transfer. Native-20 is copper-identical, so these results apply to it too.

## F6 on both legs (`f6_legs.py`, `results/f6-legs/`)

D-13's F6 deck (1 Ω discharge, 1 nF Cgs, −2 V off bias) unchanged except D-14's
`itl4=100000`. Run on `legA-h0-best-n19` and `legB-h0-prov-n19` at Tj 27/100 °C,
both directions, ESL 1.06/10 nH: S4 (−20 A) at 170/198/280 V × 391/443/498 ns,
S1 (37 A) at 198/280 V and S2 (71 A) at 280 V, both at 443 ns. 192 runs.

**All 192 complete and pass** the 3.0 V, model-threshold (D-13) and 1.9 V hot
off-gate screens, VDS (520/585 V) and ±30 V gate screens, and S1 ZVS:

| leg | Tj | S4 max off-gate | S4 max die VDS | S1/S2 max die VDS |
| --- | ---: | ---: | ---: | ---: |
| A | 27 °C | 1.233 V | 489.1 V | 383.9 V |
| A | 100 °C | 1.039 V | 481.9 V | 383.1 V |
| B | 27 °C | 0.997 V | 484.0 V | 370.3 V |
| B | 100 °C | 0.814 V | 478.6 V | 366.1 V |

Without F6, leg B's S4 reached 537 V (section above). F6 is therefore a remedy
for S4 on both legs in the model. It is still not a qualified fix: 150 °C stays
indeterminate (placeholder Schottky, FINDINGS F6), recovery has no physical bound
(D-24 answer c), and the stiff −2 V source must be built as modelled (D-12).

### F6 with the selected Schottky's vendor model (`results/f6-legs-pmeg/`)

`f6_legs.py --diode pmeg --temps 27,100,150` replaces D-6's generic `D6D`
(Is = 1 µA, N = 1, Cjo = 20 pF) with Nexperia's PMEG6030EP subcircuit (D-12's
selected part; fetched by `sim-kit/models/fetch_models.sh`, not committed;
Cjo 634 pF, EG 0.69). **288/288 complete and pass at 27/100/150 °C on both
legs.** S4 max off-gate is 1.27 V (A 27 °C) and max die VDS is 489.6 V (B 27 °C);
S1/S2 off-gate ≤ −0.27 V with ZVS. 150 °C converges with no aborts, so D-13's
150 °C indeterminacy was the placeholder diode. 27/100 °C agree with the
placeholder run within 0.23 V off-gate and 12.5 V die VDS (192 matched cases; the real diode's 634 pF junction changes the discharge path), with no verdict change.

## S5: the burst-start edge (`f6_legs.py --cases startup`, `startup_probe.py`)

With the bridge idle, the bus film capacitors keep the line peak through the
zero crossing. A burst's (or any power-up's) first turn-on therefore
hard-switches the full bus into **zero tank current**: no diode recovery,
unlike S4, but the same dv/dt on the partner's gate. S5 = IL 0 A at
170/198/280 V × 391/443/498 ns, both directions, ESL 1.06/10 nH, Tj
27/100/150 °C, both legs (108 cases per variant).

| Deck | complete | pass (3.0 V + model + VDS) | max off-gate | max die VDS |
| --- | ---: | ---: | ---: | ---: |
| baseline (unipolar, native-20 as built) | 216/216 | **0** | 4.13 V (A, 27 °C) | 463.7 V |
| F6, PMEG6030EP | 216/216 | **216** | 0.02 V | 420.8 V |

`startup_probe.py` measures the off device's peak drain current and its
energy in the 0.75 µs after the edge (worst cases, both legs, 27/150 °C,
170/280 V; `results/startup-probe.json`). Peak current is about 67–73 A in
**both** decks, i.e. dominated by its output-capacitance charging, not
channel conduction. Its energy is **114–143 µJ** without F6 and
**83–105 µJ** with F6. The difference, about 30–40 µJ per edge, is partial
channel conduction with the gate near the model's typical threshold (4.05 V at 27 °C).
Thermally that's negligible at one edge per 20 s burst. The risk is device spread:
the datasheet guarantees VGS(th) ≥ 3.5 V only at 25 °C, and lower hot. A
low-threshold part at about 4 V on its gate would shoot through. Hence FINDINGS F11
and the bring-up precaution in DECISIONS.md.

### Leg B interim check with its own closure data (`results/legB-interim-n19/`)

Leg B's coarse 0.5 mm and 2 mm closure matrices (remote `b19corr`; fetched
as `../results/matrices/legB-h{0p5,2}-e1p0-m10-n19`) allow a quad(0.5,1,2)
closure correction per leg. Leg B's differs from leg A's by up to
**+0.85 nH**. The ones that matter are the power-to-low-gate mutuals M14/M24,
at **+0.67/+0.41 nH** (+20/+11 % of those entries): the transfer
under-states leg B's low-gate coupling. `legB-h0-interim-n19` = provisional +
that difference (min eig 7.63 nH; no 3 mm point and no leg-B crop correction
yet). The 96 decision cases: **no verdict changes, no aborts**. Off-gate
moves −0.14 … +0.21 V (S2 max 1.32 V, inside 1.9 V) and die VDS −12.9 … +5.5 V.
`compose_legB_corr.py` (self-tested against leg A) builds the full
correction once the 3 mm and 20 mm-crop matrices land.

## Leg B on its own corrections (`legB-h0-corr-n19`, `compose_legB_corr.py`)

Leg B's coarse closure set (0.5/1/2/3 mm) and 20 mm-crop matrix are complete
(remote `b19corr`; `../results/matrices/legB-*-n19`). `legB-h0-corr-n19` =
provisional + [C_h(B) + C_m(B)] − [C_h(A) + C_m(A)]: leg B's own closure
(cubic 0.5–3 mm) and crop corrections replace leg A's. Only leg A's
fine-vs-coarse mesh change is still borrowed (the fine leg B extraction,
`campB19`, is running). Min eigenvalue 7.88 nH. Versus the provisional:
**M14 +25 %, M24 +13 %, M13/M23 +5 %**, L22 −6.6 %, M12 −4.7 %, and leg B's
crop correction is larger on the power loop (−2.5…−2.9 nH vs −0.5…−1.7).

| Run | Result |
| --- | --- |
| Unipolar decision cases (`results/legB-corr-n19/`, 96) | 60/96 as provisional; **no verdict flips**, no aborts; ZVS 12/12 at 443 ns; S2 off-gate ≤ 1.28 V (Δ ≤ +0.22 V); S4 die VDS ≤ 523 V (Δ −29 … −3 V) |
| F6 + PMEG6030EP, 27/100/150 °C (`results/f6-legB-corr/`, 144) | **144/144 pass**; S4 off-gate ≤ 1.18 V, die VDS ≤ 493 V |
| S5 burst start, unipolar (`results/startup-baseline-legB-corr/`, 108) | **0/108**; off-gate up to 3.94 V |
| S5 burst start, F6 (`results/startup-f6-legB-corr/`, 108) | **108/108**; off-gate ≤ −0.21 V |

The leg B conclusions from the provisional matrix hold on its own corrections.

