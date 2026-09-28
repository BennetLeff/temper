# A1 — ZVS thresholds, switch-node edges, and turn-off energy

- Board: `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Date/tool: 2026-09-27, ngspice 45.2, Miniforge Python/NumPy; Infineon `IPW65R018CFD7_L1` library SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`.
- Evidence class: **simulation/model-based, reference inductances, sampled sensitivity**. This is not a native-15 board-bound switching or thermal verdict.
- Verdict: **A1 inductance-independence gate FAIL** for light-load edges; **board-specific threshold/edge use BLOCKED** pending A2/B1. The 37 A reference cases meet the nominal 348 ns ZVS diagnostic.

## Summary

The [runner](run_a1.py) completed the requested 540-case grid: three bus voltages (120/170/198 V), two directions, three dead times (250/348/450 ns), ten currents (1/2/3/4/6/8/10/15/20/37 A), and reference board/ESL inductances at ×0.5/×1/×3. It then bisected each qualifying threshold to a bracket half-width at most 0.25 A. Every case has a checked full transient, a compressed ngspice log, a compressed commutation waveform, and a per-case JSON record under [outputs/runs](outputs/runs/). The [source hashes](source_hashes.json) cover the board, vendor model/archive, deck, solver options, scripts, and governing plan.

At 348 ns, the nominal-reference-L threshold is 21.99 A at 120 V, 21.46 A at 170 V, and 20.93 A at 198 V in both directions. At 450 ns it is 11.09 A at 120 V in both directions and 170 V DIR0; it is 10.78 A at 198 V in both directions and 170 V DIR1. The 170 V DIR1 value uses a 0.1 ns refinement after a numerical classification flip at the diagnostic boundary. These are **midpoints of model pass/fail brackets**, not physical lower/upper bounds. At 250 ns, none of the 18 bus/direction/L-scale tuples qualified at any sampled current through 100 A; there is no inferred threshold beyond the sampled range. See [zvs_threshold.json](zvs_threshold.json) for each direction, scale, dead time, bracket, and status.

The largest threshold shift among the bracketed ×0.5/×3 comparisons is 6.04%, below A1's 10% check. Edges fail A1's 20% sensitivity check: the maximum sampled 10–90% edge-time change is **68.92%** at 120 V, DIR1, 20 A, ×0.5, tied between 348 ns (both compared cases non-ZVS) and 450 ns (both ZVS). The 10–90%-band 1 ns peak dv/dt changes by **50.69%** at worst (120 V, DIR1, 450 ns, 4 A, ×3, non-ZVS); the full-event 1 ns peak changes by **47.42%** at worst (120 V, DIR0, 450 ns, 4 A, ×3, non-ZVS). The 37 A ZVS cases have smaller sampled changes, but the 20 A ZVS case itself exceeds the gate, so an all-current board-independent input is unsupported. [edge_rates.csv](edge_rates.csv) and [edge_sensitivity.csv](edge_sensitivity.csv) retain every grid case and comparison. The three-point scale sweep does not prove behavior at every inductance between ×0.5 and ×3.

## Method and assumptions

The [deck](complementary_leg.cir) copies round 2's complementary half-bridge and adds a zero-volt high-side drain-current probe and explicit saved vectors. It uses two Infineon L1 MOSFETs, 1 nF snubbers per device, a 1 mΩ shunt, a continuous 15 V push-pull driver approximation (ROH 5 Ω, ROL 0.55 Ω, 5 ns command ramps), and a constant-current load ramped on before the event. It uses the model's default 27 °C operating point. The gate driver transistor behavior, propagation spread, distributed copper, full resonant tank waveform, and temperature dependence are absent. The same assumptions are documented in [round 2](../../round2/README.md) and the [simulation runbook](../../../../validation-plan/SIMULATION-RUNBOOK.md).

The reference deck inductances are LD_HS/LS_HS/LD_LS/LS_LS = 4 nH each, LCAP = 3 nH, LBULK = 30 nH, LCS = 1 nH, and LG = 20 nH. These represent **board copper, gate loop and capacitor ESL placeholders**. The sensitivity sweep scales exactly those eight values together. Infineon's L1 subcircuit already contains package Ld = 1.88 nH, Ls = 2.82 nH, Lg = 8.32 nH, and internal Rg = 2.7 Ω; none is added externally or scaled. A2/B1 must replace the placeholders before a native-15 stress or EMI conclusion.

DIR0 turns the low side off and then the high side on; DIR1 reverses the sequence and load-current sign. The reported switch node is `v(sw)`, the deck node after high-side source board inductance and before low-side drain board inductance. Incoming **die** VDS is `v(xqh.dd)-v(xqh.s)` for DIR0 or `v(xql.dd)-v(xql.s)` for DIR1. A run is called ZVS only when the absolute incoming die VDS stays at or below 5% of VBUS at every saved point and interpolated boundary during the 20 ns before the incoming **7.5 V command crossing**. That 5%/20 ns rule is a diagnostic from round 2, not a measured MOSFET conduction criterion.

The edge time is `v(sw)` 10→90% for DIR0 and 90→10% for DIR1, using interpolated crossing times. The band-limited peak dv/dt is the maximum absolute **1 ns secant** whose midpoint lies between 10% and 90% VBUS; the full-event peak uses all 1 ns secants from T1 to 200 ns after the incoming command, including ringing. Secants are evaluated every 0.5 ns. These definitions, the ZVS flag, and whether the edge finishes before the incoming command are explicit in [edge_rates.csv](edge_rates.csv). A 1 ns secant is a defined bandwidth-limited estimate, not an instantaneous derivative.

## Turn-off energy for A6

[turnoff_energy.csv](turnoff_energy.csv) gives current-resolved values at every simulated bus/direction/dead-time/L scale. The turn-off integration interval is outgoing 50% command to incoming 50% command. `turnoff_die_vds_external_drain_id_proxy_j` integrates **die VDS × external drain-probe current** (`i(Vids)` or `i(Vidh)`); the current is not a channel-only current, and this integral is **not all heat**. The compressed waveforms retain each device's die drain/source voltage, external drain-probe current, and internal channel, epitaxial and diode currents.

`turnoff_model_dissipative_sum_j` reconstructs the L1 library's `G_G_Ptot_channel` and `G_G_Ptot_Epi` terms: `LIMIT(V(d,s)·I(V_Ichannel),0,100 kW)`, `LIMIT(V(dd,d1)·I(V_Iepi),0,100 kW)`, and `LIMIT(V(dd,s)·I(V_sense2),0,100 kW)`. It therefore separates the model's semiconductor dissipation from reversible Coss displacement and stored-energy transfer in the external-port proxy. It is still only a model-based estimate at 27 °C; package ohmic loss and a solved thermal rise are outside this integral. Every case records whether any model power term reached the vendor's 100 kW clip. None of the 811 verified transients did. At 198 V, 37 A, 348 ns and nominal L, the model dissipative sums are 26.89 µJ (DIR0) and 19.55 µJ (DIR1), while the external-drain-probe integrals are 78.10 and 41.37 µJ.

## Numerical and scope checks

The [smoke output](smoke-test.txt) ends in `SMOKE PASS`; the [sheet-solver self-test](sheet-solver-selftest.txt) ends in `SELFTEST PASS`. The runner rejects nonzero ngspice status, an abort signature, missing saved vectors, incomplete or non-increasing transient time, overlapping or reversed commands, and a command gap inconsistent with the requested dead time. The same 198 V/DIR1/4 A/×0.5 topology aborted at 0.2 ns maximum step at T1 (`Timestep too small; node bus`) for all three dead times, then completed at 0.1 ns with no tolerance change. Failed and successful compressed logs remain in the respective case directories; each successful record is marked `nominal_0p2ns_abort_log`.

[timestep_checks.json](timestep_checks.json) compares 0.2 and 0.1 ns runs at both nominal-L threshold bracket endpoints, plus 37 A at 120/198 V in both directions and all three L scales. All 36 checks completed; the largest die-VDS peak change is **0.611%**, meeting the runbook's <2% half-step requirement. One ZVS classification flips at the strict boundary: 170 V/DIR1/450 ns/nominal L/10.9375 A gives 8.50505 V at 0.2 ns and 8.49979 V at 0.1 ns against an 8.500 V limit. [The refinement](timestep_refined_thresholds.json) finds a 0.1 ns fail/pass bracket of [10.625, 10.9375] A, midpoint 10.78125 ±0.15625 A; that bracket is in the authoritative threshold JSON. This is numerical sensitivity of the diagnostic at its boundary, not a voltage-peak instability. [audit.json](audit.json) confirms all 540 grid keys, 811 complete raw runs, source hashes, compressed artifacts, threshold widths, model heat-clipping checks and timestep results.

## Open items and physical confirmation

The inductance sensitivity failure means B4's ZVS map and B5's EMI inputs wait for B1's board-bound switching grid. B4 also has event bus voltages below A1's lowest 120 V point; no threshold is interpolated or extrapolated into that region. A2/B1 must provide the actual board/gate-loop inductances and capacitor ESL. These simulations do not replace staged oscilloscope confirmation of VDS, VGS, switch-node edges and dead time at low bus voltage.

## Reproduce

From this worktree's repository root, copy the exact licensed vendor directory into the ignored kit `models/vendor/` directory and verify both pinned hashes in [source_hashes.json](source_hashes.json). The vendor files must not be committed. Then run:

```sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/04-current/sheet_solver.py --selftest
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/run_a1.py --phase grid --jobs 3
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/run_a1.py --phase thresholds --jobs 3
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/run_a1.py --phase resolution
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/refine_thresholds.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/run_a1.py --phase export
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/audit_a1.py
```

The [grid](grid-run.txt), [threshold](threshold-run.txt), [resolution](resolution-run.txt), [export](export-run.txt) and [audit](audit-run.txt) logs record execution. Per-case `case.json` contains the exact parameters, waveform/log paths, solver step, command times, edge metrics and energy terms. Every compressed waveform stores every simulator point in the commutation window; the licensed vendor library is fetched/copied separately and never saved in this result tree.
