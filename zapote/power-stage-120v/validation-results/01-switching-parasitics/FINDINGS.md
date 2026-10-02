# Task 01 findings register

Every finding that affects the switching verdict, with its status, evidence
and what closes it. Update the row; don't append a new section. Current
answer: [STATUS.md](STATUS.md). Last updated 2026-10-03.

Status: **OPEN** (affects the verdict, work possible), **WAITING** (needs
outside input), **CLOSED** (resolved, with evidence), **ACCEPTED** (known
limit, judged not to change any conclusion).

## Design risks (what the board may do)

| # | Finding | Status | Evidence | Closes it |
| --- | --- | --- | --- | --- |
| F1 | **Dead-time margin:** off-gate crosses 3.0 V between 307 and 348 ns; 307 ns (D-1's lower tolerance estimate) fails every nominal case at 3.45–4.01 V. D-5: the firmware does **not** establish ≥ 500 ns at the gates (configuration, delay-resource handling and cached readback prevent the claim); keep 307 ns. | OPEN | [grid v2](round17/d2/README.md), [out-D1](round17/delegation/out-D1/README.md), [out-D5](round17/delegation/out-D5/README.md) | owner: establish the deployed four-PWM configuration and correct dead-time handling, then measure gate timing (D-8 procedure); or adopt a gate-drive remedy (F6) that passes at 307 ns |
| F2 | **Hard turn-on (S4) fails at every dead time:** die VDS up to 543 V, off-gate up to 5.1 V; driven by the model's abrupt body-diode snap-off and Miller rebound. D-6's preferred remedy brings S4 to VDS ≤ 484 V and off-gate ≤ 0.51 V in simulation. | WAITING | grid v2; [out-D3](round17/delegation/out-D3/README.md); [out-D6](round17/delegation/out-D6/README.md) | measured recovery (D-8 procedure, [out-D8](round17/delegation/out-D8/README.md)) or Infineon confirmation; F6 |
| F3 | **Bulk-capacitor current path:** C6 couples to the gate loops like the local caps (M53 3.34, M54 5.47 nH). Direct 5-port A/B/C test: the coupling moves off-gate by −0.11 … +0.29 V and die VDS by −23 … +14 V; one verdict flips (S2 280 V/71 A at 348 ns, 3.07 → 2.92 V). The earlier 14–48 V EMF estimate was far too pessimistic. | ACCEPTED | [bulk A/B/C](round17/d2/README.md), `round17/d2/results/bulk-ab/`, `round17/results/matrices/legA5-h1-e1p0-m10.matrix.txt` | revisit only if a decision case is within ~0.3 V of the limit (S2 280 V/71 A at 348 ns is) |
| F4 | S2 280 V / 71 A, LS first, 348 ns: marginal off-gate (3.07–3.22 V depending on matrix; passes with the 5-port bulk model) | OPEN | grid v2, bulk A/B/C, extrapolation test | F6 remedy passes it (D-6) |
| F5 | **The 3.0 V off-gate criterion is optimistic at hot junction.** Infineon guarantees VGS(th) ≥ 3.5 V only at 25 °C; the vendor model's threshold falls 1.07 V by 150 °C. D-6's provisional hot screen is **< 1.9 V** (model-derived, not a guaranteed bound). Against it, today's nominal S1 at 348 ns (2.0–2.6 V) **fails**. | OPEN | [out-D6](round17/delegation/out-D6/README.md) (criterion section, `threshold.py`) | vendor minimum-hot-threshold data or characterization; until then results are reported against both 3.0 V (25 °C) and 1.9 V (hot screen) |
| F6 | **Gate-drive remedy (proposal).** D-6: ≈1 Ω discharge path + 1 nF Cgs + −2 V turn-off bias passes all 32 decision cases on both matrices against the 1.9 V screen (max off-gate 0.512 V, die VDS 483.8 V, nominal ZVS kept, overlap energy −2.9 … −51.2 %). Alternative: 1 nF + −4 V (19 V span). The board has no negative rail: a bias-supply redesign. Transients at 27 °C; 11/32 timestep-refinement runs aborted, so convergence is not established. | OPEN | [out-D6](round17/delegation/out-D6/README.md), `TABLES.md` | owner selects the remedy; then a board change (not made here) and a converged/hot recheck |

## Model and method limits (how far to trust the numbers)

| # | Finding | Status | Evidence | Closes it |
| --- | --- | --- | --- | --- |
| M1 | Mesh not converged: P1 31.84 / 32.27 / 33.05 nH at 1.0 / 0.7 / 0.35 mm edges | OPEN | [round17 README §10](round17/README.md), `results/sensitivity-mac.json` | a finer mesh or Richardson estimate on the coarse ladder; check grid sensitivity to ±3 % |
| M2 | **Closure-height extrapolation is curved near zero.** Coarse-mesh parabola through 0.5/1/2 mm vs the straight line through 1/2 mm: self L −1.6 … −7.3 %, power-to-gate mutuals +7 … +16 %. Applied to the best matrix: no verdict changes, off-gate +0.04 … +0.19 V in every decision case (nominal S1 at 348 ns 2.58 V). lin(1,2) is not conservative for off-gate. | OPEN | [extrapolation test](round17/d2/README.md), `round17/scripts/extrap_delta.py`, `round17/d2/results/extrap-test/` | fine-mesh 1/2/3 mm parabola (remote, last port) and coarse 3 mm (Mac): if they agree, adopt the curved matrix as best |
| M3 | Crop margin: L high by up to 5.2 % at 10 mm; converged by 20 mm | ACCEPTED | `results/matrices/`, `scripts/margin_correct.py`; corrected grid: no verdict changes | transfer test at a second mesh/height would make it CLOSED |
| M4 | Capacitor ESL assumed (C38–C41 5–20 nH; C5/C6 unknown). D-7 located the exact TDK model entries but no verified values yet (TDK licence being accepted). | WAITING | [PACKAGE-INDUCTANCE.md](round17/PACKAGE-INDUCTANCE.md), D-7 PR #1634 | D-7 with the TDK models, or bench |
| M5 | Driver modelled as DC output resistances (5 Ω / 0.55 Ω, typical); no transient boost | ACCEPTED | [out-D2](round17/delegation/out-D2/README.md) | boosted variant changes S4 only slightly (560 V, 4.85 V); revisit if D-6 depends on it |
| M6 | Gate resistor package inductance generic (2 nH), not Yageo-specific | ACCEPTED | out-D2 | — |
| M7 | Zero-height result is a reference-geometry extrapolation, not removal of every closure conductor (D-4 P2) | ACCEPTED | [out-D4](round17/delegation/out-D4/README.md) | — |
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
