# Task 01 findings register

Every finding that affects the switching verdict, with its status, evidence
and what closes it. Update the row; don't append a new section. Current
answer: [STATUS.md](STATUS.md). Last updated 2026-10-03 (D-12…D-15).

Status: **OPEN** (affects the verdict, work possible), **WAITING** (needs
outside input), **CLOSED** (resolved, with evidence), **ACCEPTED** (known
limit, judged not to change any conclusion).

## Design risks (what the board may do)

| # | Finding | Status | Evidence | Closes it |
| --- | --- | --- | --- | --- |
| F1 | **Dead-time margin:** off-gate crosses 3.0 V between 307 and 348 ns; 307 ns (D-1's lower tolerance estimate) fails every nominal case at 3.45–4.01 V. D-5: the firmware does **not** establish ≥ 500 ns at the gates (configuration, delay-resource handling and cached readback prevent the claim); keep 307 ns. | OPEN | [grid v2](round17/d2/README.md), [out-D1](round17/delegation/out-D1/README.md), [out-D5](round17/delegation/out-D5/README.md) | owner: establish the deployed four-PWM configuration and correct dead-time handling, then measure gate timing (D-8 procedure); or adopt a gate-drive remedy (F6) that passes at 307 ns |
| F2 | **Hard turn-on (S4) fails at every dead time and temperature** (die VDS up to 543 V, off-gate up to 5.2 V). D-24 swept the body-diode recovery: all 86 completed model cases fail, no passing boundary found, but no physical bound on recovery exists, so simulation cannot settle it (answer c). F7 does not fix S4; F6 does in simulation at 27/100 °C. | WAITING | grid-best; [out-D3](round17/delegation/out-D3/README.md); [out-D13](round17/delegation/out-D13/README.md); [out-D24](round17/delegation/out-D24/README.md) | one synchronised S4 commutation-waveform measurement (D-24's criteria, in the D-8 plan); if it fails, F6 |
| F3 | **Bulk-capacitor current path:** C6 couples to the gate loops like the local caps (M53 3.34, M54 5.47 nH). Direct 5-port A/B/C test: the coupling moves off-gate by −0.11 … +0.29 V and die VDS by −23 … +14 V; one verdict flips (S2 280 V/71 A at 348 ns, 3.07 → 2.92 V). The earlier 14–48 V EMF estimate was far too pessimistic. | ACCEPTED | [bulk A/B/C](round17/d2/README.md), `round17/d2/results/bulk-ab/`, `round17/results/matrices/legA5-h1-e1p0-m10.matrix.txt` | revisit only if a decision case is within ~0.3 V of the limit (S2 280 V/71 A at 348 ns is) |
| F4 | S2 280 V / 71 A, LS first, 348 ns: marginal off-gate (3.07–3.22 V depending on matrix; passes with the 5-port bulk model) | OPEN | grid v2, bulk A/B/C, extrapolation test | F6 remedy passes it (D-6) |
| F5 | **Off-gate criterion at hot junction.** Infineon guarantees VGS(th) ≥ 3.5 V only at 25 °C. D-6's provisional hot screen is **< 1.9 V** (model-derived). D-13 ran the transients hot (the vendor model reads `TEMP`): the nominal model's own threshold − 0.5 V is 2.92 V at 100 °C and 2.49 V at 150 °C, so 1.9 V is conservative **relative to the nominal model** (never passes a case the model-relative judgement fails); it cannot be relaxed on that basis because the population minimum is lower. Keep 1.9 V as the screen. | ACCEPTED | [out-D6](round17/delegation/out-D6/README.md), [out-D13](round17/delegation/out-D13/README.md) | vendor minimum-hot-threshold data would replace the screen |
| F6 | **Remedy A: negative bias (≈1 Ω discharge + 1 nF Cgs + −2 V).** Passes all decision cases incl. S4 at 27 and 100 °C (D-6, D-13). At 150 °C every F6 run aborts at D-6's **generic placeholder Schottky** (`doffl`, Is = 1 µA, N = 1) during turn-off; D-14's `itl4=100000` does not resolve it while reproducing all 56 converged 100 °C runs exactly (`d2/results/f6-hot-itl4/`): a placeholder-model artefact, so F6 at 150 °C is indeterminate until the selected Schottky's vendor model is used. Build (D-12): the cheap bootstrap Zener network does **not** reproduce the simulated stiff −2 V source; the preferred implementation is an isolated +15 V / negative-rail supply, ≈ $115–119 including supply replacement, with layout change (FEM rerun). | OPEN | [out-D6](round17/delegation/out-D6/README.md), [out-D12](round17/delegation/out-D12/README.md), [out-D13](round17/delegation/out-D13/README.md) | only if S4 immunity is required; then the real Schottky model at 150 °C and a layout/FEM rerun |
| F7 | **Remedy B (implemented in native-18, #1640): longer dead time.** R9/R17 39 kΩ → **49.9 kΩ ±0.1 %, 25 ppm/°C (RT0603BRD0749K9L)**, same 0603 footprint: estimated 396.6–488.0 ns (D-12; a ±1 % part would not hold 391 ns). On the best matrix, all nominal S1 and S2 cases pass the 1.9 V hot screen with ZVS across 391–498 ns (`d2/results/grid-best-longdt/`), and still pass hot: at 27/100/150 °C against the model threshold, 1.9 V and 3.0 V (D-13). Cost (D-15): +0.09–0.11 W per switch overlap proxy at 37 A, 36 kHz; ZVS map unchanged (2/5/10 A fail, 20/30/37 A pass, as at 348 ns). Value-only: no copper change, no FEM rerun. Does **not** fix S4. | IMPLEMENTED | [out-D12](round17/delegation/out-D12/README.md), [out-D13](round17/delegation/out-D13/README.md), [out-D15](round17/delegation/out-D15/README.md); DECISIONS.md 2026-10-03 | confirm gate timing at bring-up (D-8) |
| F8 | **Firmware failed-init state can leave PWM pins floating high.** D-25: D-21's force polarity is correct, but on an initialisation failure generator deletion calls `gpio_reset_pin()` (output disabled, weak pull-up on); against the UCC21550's ≥ 50 kΩ input pull-down the pin can sit between thresholds or read high. | OPEN | [out-D25](round17/delegation/out-D25/README.md) | amend D-21 (#1643) to re-assert active-low after cleanup, stub `gpio_reset_pin` faithfully; controller ≤ 10 kΩ PWM pull-downs (DECISIONS.md 2026-10-05) |

## Model and method limits (how far to trust the numbers)

| # | Finding | Status | Evidence | Closes it |
| --- | --- | --- | --- | --- |
| M1 | **Mesh convergence.** Mutual inductances converge (power-to-gate couplings 0.3–0.6 % at the last step); self-inductances do not (+1.2–1.7 % per refinement, no asymptote: edge singularity). A pessimistic +3 refinement steps (+4–6 % self-L) changes **no** native-18 decision verdict (off-gate −0.07 … +0.05 V, VDS −3 … +7 V). | ACCEPTED | [mesh section](round17/d2/README.md), `round17/d2/results/mesh-sensitivity/`, `round17/results/matrices/` | — |
| M2 | **Closure-height extrapolation is curved near zero.** Coarse-mesh parabola through 0.5/1/2 mm vs the straight line through 1/2 mm: self L −1.6 … −7.3 %, power-to-gate mutuals +7 … +16 %. Applied to the best matrix: no verdict changes, off-gate +0.04 … +0.19 V in every decision case (nominal S1 at 348 ns 2.58 V). lin(1,2) is not conservative for off-gate. | OPEN | [extrapolation test](round17/d2/README.md), `round17/scripts/extrap_delta.py`, `round17/d2/results/extrap-test/` | fine-mesh 1/2/3 mm parabola (remote, last port) and coarse 3 mm (Mac): if they agree, adopt the curved matrix as best |
| M3 | Crop margin: L high by up to 5.2 % at 10 mm; converged by 20 mm | ACCEPTED | `results/matrices/`, `scripts/margin_correct.py`; corrected grid: no verdict changes | transfer test at a second mesh/height would make it CLOSED |
| M4 | Capacitor ESL assumed (C38–C41 5–20 nH; C5/C6 unknown). D-7 located the exact TDK model entries but no verified values yet (TDK licence being accepted). | WAITING | [PACKAGE-INDUCTANCE.md](round17/PACKAGE-INDUCTANCE.md), D-7 PR #1634 | D-7 with the TDK models, or bench |
| M5 | Driver modelled as DC output resistances (5 Ω / 0.55 Ω, typical) with ideal command edges. Two attempts at a real driver model failed to validate (D-23: TI B-Q1 proxy does not converge; D-26: datasheet-parametric output stage misses TI's loaded fixtures); D-26's 11 completed real-timing cases kept every S1/S2 verdict. | ACCEPTED | [out-D2](round17/delegation/out-D2/README.md), [out-D23](round17/delegation/out-D23/README.md), [out-D26](round17/delegation/out-D26/README.md); DECISIONS.md 2026-10-05 | physical gate timing at bring-up (D-8, D-20 R29) |
| M6 | Gate resistor package inductance generic (2 nH), not Yageo-specific | ACCEPTED | out-D2 | — |
| M7 | Zero-height result is a reference-geometry extrapolation, not removal of every closure conductor (D-4 P2) | ACCEPTED | [out-D4](round17/delegation/out-D4/README.md) | — |
| M10 | **Board revision native-19** (R5 rework, In1 plane around it, U8 reroute) changed both legs' FEM regions. Leg A re-extracted on native-19 copper: entries within ±1.8 % (power-to-gate mutuals −0.1 … +0.7 %); native-18/19 decision cases show no verdict change (off-gate within ±0.025 V). Leg B pair running. | OPEN | [native-19 section](round17/d2/README.md), `round17/d2/results/native19-carryover/` | leg B native-17 vs native-19 comparison |
| M9 | Solver aborts ("timestep too small"). D-14 qualified `.options itl4=100000` (all 25 cold aborts resolved, 221 comparable results unchanged, decision cases converge 0.1 → 0.05 ns). Now in `d2/leg_matrix.cir` (and `leg_matrix5.cir`): a formerly aborted case (S3 280 V / 5 A / dir 1 / 20 nH) converges, and converged cases reproduce exactly (S1 280 V / dir 1 / 348 ns: 2.421827 V, identical to `grid-best`). F6 at 150 °C still aborts (placeholder Schottky; F6). | CLOSED | [out-D14](round17/delegation/out-D14/README.md), `d2/leg_matrix.cir` | — |
| M8 | Signed mutuals confirmed by independent pair-solve energy (coarse mesh): M12; M13 3.747422 vs 3.747410 nH; M34 −0.295900 vs −0.295904 nH (sign confirmed) | CLOSED | [`round17/results/pair-check-h1-e1p0.txt`](round17/results/pair-check-h1-e1p0.txt), `scripts/pair_check.sh` | — |

## Software defects (closed)

| # | Finding | Status | Evidence |
| --- | --- | --- | --- |
| S1 | Grid reused stale cases after a matrix change (D-4 P1) | CLOSED | f5a1c8083, `d2/test_grid.py` |
| S2 | ZVS failure could count as a pass (D-4 P1) | CLOSED | f5a1c8083 |
| S3 | Off-gate cause labels over-claimed (D-4 P2) | CLOSED | f5a1c8083 |
| S4 | No port identity/orientation check (D-4 P2) | CLOSED | f5a1c8083 |
| S5 | Elmer VTU averaged DG fields (first matrix withdrawn) | CLOSED | round17 README §5 |
| S6 | Gate–source bridges at h+1 instead of 2h | CLOSED | round17 README §8 |
| S7 | Mesher pinch false positives blocked margin ≥ 20 mm | CLOSED | 66f61d9e8 |
| S8 | Grid identity omitted deck includes, runner and simulator build (D-9) | CLOSED | `d2/grid.py`, `d2/test_grid.py` |
| S9 | Campaign resume accepted any converged run, whatever its tolerance or mesh; mesh-gate scripts not in the manifest (D-9) | CLOSED | `scripts/campaign.py` receipts, `scripts/run_elmer.py` |
| S10 | `--set` could override scenario keys and mislabel a case (D-9) | CLOSED | `d2/grid.py`, `d2/test_grid.py` |
| S11 | Port identity not carried through extrapolation and corrections; runs not bound to their mesh (D-9) | CLOSED | `scripts/matrix_gate.py`, `scripts/inductance_matrix.py` receipts |
| S12 | Pair checks reported agreement without requiring a converged, correctly excited solve (D-9) | CLOSED | `scripts/pair_check.sh` |
| S13 | Crop correction accepted a nonsymmetric matrix as positive definite (D-9) | CLOSED | `scripts/matrix_gate.py`, `scripts/test_matrix_gate.py` |

## Outside inputs needed

| Input | For | Who |
| --- | --- | --- |
| Diode recovery at high di/dt (measurement or Infineon) | F2 | owner / vendor |
| TI timing limits at the fitted 39 kΩ DT resistor | F1 | TI |
| Deployed four-PWM controller configuration and harness (D-5: firmware does not establish dead time at the gates; D-10: controller/harness absent) | F1 | owner |
| Gate-drive remedy choice and hot acceptance criterion | F5, F6 | owner |
| C38 ESL measurement | M4 | bench (D-7 may make it unnecessary) |
