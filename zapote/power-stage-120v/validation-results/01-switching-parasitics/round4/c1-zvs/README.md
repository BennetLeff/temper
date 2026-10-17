# C1 — dead-time ZVS reference map

- **Board:** `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`. The board hash identifies context; the C1 sweep uses A1's **reference** inductances, not extracted native-15 inductance.
- **Date and tools:** 2026-09-28; checkout `829ee9debc08ce239bc2dffe0938c4fec2429545`; ngspice 45.2; `/Users/bennet/Miniforge3/bin/python3`; Infineon IPW65R018CFD7 L1 model SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`.
- **Evidence class:** simulation/model-based, nominal 27 °C, reference inductance plus sampled ×0.5/×3 sensitivity. The [source manifest](source_hashes.json) pins every input and script.
- **Verdict:** **PASS WITH CONDITIONS for the C1 reference-deck deliverable; BLOCKED for a board-specific ZVS or dead-time choice.** D1's coupled matrix for both legs, derated A event trajectories, hot diode properties, and physical switching tests remain necessary.
- **Preflight:** round-3 raw evidence [3327/3327 verified](raw-evidence-check.txt); sim-kit [SMOKE PASS](smoke-test.txt).

## Summary

The [runner](run_c1.py) completed six driver timing corners × seven buses (10, 30, 60, 90, 120, 170, 198 V) × two current directions at reference inductance: **84 threshold searches**. It added **56** searches at typical timing with reference L ×0.5 and ×3. Every sampled pass/fail transition was refined to a bracket half-width ≤0.25 A; no sampled nonmonotonic sequence appeared. The [strict threshold file](zvs_thresholds_c1.json) has 120 bounded rows. All 20 strict 10 V rows have no pass through the sampled 100 A limit, because a forward diode drop near 1 V exceeds the strict 5% band of 0.5 V. This is a **diagnostic classification artifact**, not evidence of hard switching. The [supplemental signed-VDS map](physical_thresholds_10v.json) separately refines all 20 positive-residual commutation brackets to ≤±0.25 A.

The reference model's longer timing lowers the nominal-L strict threshold at 120 V from 21.5–22.0 A at 39 kΩ typical to 10.5–11.0 A at 51 kΩ typical in both directions. That comparison excludes extra diode dwell, recovery, hard turn-on, temperature, board inductance, and controller-imposed dead time. It is **not** the C2 loss verdict or a recommendation to change R9/R17.

## Method and assumptions

TI UCC21550 Rev. C, printed page 10, §5.8 characterizes **50 kΩ** RDT at 399/443/487 ns (min/typ/max) and gives `DT(ns) ≈ 8.6 × RDT(kΩ) + 13`. TI does **not** specify a 39 kΩ or 51 kΩ min/max row. C1 computes the formula nominal at 39/51 kΩ, then **ASSUMES** the 50 kΩ min/typ/max ratios apply there:

| RDT | Min ns | Typ ns | Max ns | Evidence |
| --- | ---: | ---: | ---: | --- |
| 39 kΩ installed | 313.796 | 348.400 | 383.004 | formula nominal; min/max relative extrapolation **ASSUMED** |
| 51 kΩ candidate | 406.746 | 451.600 | 496.454 | formula nominal; min/max relative extrapolation **ASSUMED** |

The [official PDF, revision, page, and hash](sources/README.md) are retained. RDT resistor tolerance is **additional** and not included in these six IC-spread points; neither is any controller PWM dead time. The datasheet's driver-output dead time is not the MOSFET effective off interval. The deck preserves A1's measured command crossings and evaluates the incoming **die** voltage, outgoing turn-off, incoming diode branch, and channel-onset surrogate from each waveform. It keeps the A1 20 ns criterion: incoming |die VDS| ≤5% of VBUS throughout the interval before the 7.5 V incoming command crossing. Direction 0 is LS-off/HS-on with +IL; direction 1 is HS-off/LS-on with −IL. `current_a` is a positive magnitude.

The [A1 deck](../../round3/a1-zvs/complementary_leg.cir) represents a single current-source commutation, continuous approximate push-pull driver, 1 nF snubbers, and the Infineon L1 devices. Reference board/gate/ESL inductances are LD_HS/LS_HS/LD_LS/LS_LS = 4 nH each, LCAP = 3 nH, LBULK = 30 nH, LCS = 1 nH, LG = 20 nH. Only these eight external quantities are scaled; the vendor package parasitics stay internal. This is neither a coupled two-leg model nor a resonant tank waveform. The A1 runner, deck, model, and solver options match their pinned hashes; no solver tolerance was loosened.

## Results

At reference L, representative **strict** fail/pass brackets (A) are:

| RDT corner | 30 V DIR0 / DIR1 | 120 V DIR0 / DIR1 | 198 V DIR0 / DIR1 |
| --- | --- | --- | --- |
| 39 kΩ min | 33.0–33.5 / 32.5–33.0 | 32.5–33.0 / 32.0–32.5 | 31.5–32.0 / 31.5–32.0 |
| 39 kΩ typ | 22.5–23.0 / 22.5–23.0 | 21.5–22.0 / 21.5–22.0 | 20.5–21.0 / 20.5–21.0 |
| 39 kΩ max | 17.5–18.0 / 17.0–17.5 | 16.0–16.5 / 16.0–16.5 | 16.0–16.5 / 16.0–16.5 |
| 51 kΩ min | 14.5–15.0 / 14.5–15.0 | 13.5–14.0 / 13.5–14.0 | 13.0–13.5 / 13.0–13.5 |
| 51 kΩ typ | 11.5–12.0 / 11.5–12.0 | 10.5–11.0 / 10.5–11.0 | 10.5–11.0 / 10.5–11.0 |
| 51 kΩ max | 9.5–10.0 / 9.5–10.0 | 9.0–9.5 / 9.0–9.5 | 8.5–9.0 / 8.5–9.0 |

At **10 V**, the supplemental criterion is `max(signed incoming die VDS over the precommand 20 ns) ≤ +0.5 V`. It accepts a negative, forward-diode-clamped die VDS as discharged; continuous forward diode current is reported independently. Its reference-L brackets are:

| RDT corner | DIR0 A | DIR1 A |
| --- | ---: | ---: |
| 39 kΩ min | 20.0–20.5 | 18.5–19.0 |
| 39 kΩ typ | 10.5–11.0 | 10.5–11.0 |
| 39 kΩ max | 8.5–9.0 | 8.5–9.0 |
| 51 kΩ min | 7.5–8.0 | 7.5–8.0 |
| 51 kΩ typ | 6.5–7.0 | 6.5–7.0 |
| 51 kΩ max | 5.0–5.5 | 5.5–6.0 |

For example, at 10 V, DIR0, 39 kΩ typical, 40 A, the precommand die VDS is **−0.951 to −0.914 V** and the model's incoming forward diode current stays at least **44.6 A**. The strict absolute-5% diagnostic says false while positive-residual discharge and continuous diode clamp both say true. C2 must not charge the full 10 V Eoss as a hard event solely from that strict flag. The model diode branch is `-i(V_sense2)` for forward current; the external drain probe also carries Coss/snubber displacement and is not interchangeable with diode current. All per-case values, transition completion, command times, gate/current onset, finite-window diode charge/dwell, outgoing dissipative energy, and source case links are in [waveform_metrics.csv](outputs/waveform_metrics.csv) and the [C2 schema handback](C2-HANDBACK.md). The latter also states the preceding half-cycle history that this deck cannot supply for physical Qrr qualification.

The waveform catalog contains **2,118 saved transients** including coarse-grid, threshold-bisection, physical-refinement, and half-step cases. Eleven sampled light-load, L×3 cases at 170/198 V reach ≥650 V die peak (maximum **723.75 V**); their `avalanche_or_overstress` flag invalidates the channel-onset/dwell-to-channel surrogate for normal C2 interpolation. Infineon Table 4, printed page 5, gives 3.5 V minimum VGS(th) at only 2.91 mA. C1 requires die VGS≥3.5 V as well as sustained model current for its **onset surrogate**; it remains a model analysis threshold, not a physical conduction guarantee.

## Sensitivity and numerical checks

The [sensitivity table](sensitivity.csv) shows a largest strict threshold-midpoint shift of **13.19%** from nominal L at 60 V, DIR0, 39 kΩ typical, L×3 (22.75 → 19.75 A). The largest supplemental 10 V signed-threshold shift is **27.91%** at 39 kΩ typical, DIR1, L×3 (10.75 → 13.75 A). These are sampled sensitivity results, not guaranteed bounds between scale points. They reinforce that the reference map cannot replace D1's native-15 coupled matrix.

The [82 half-step checks](timestep_checks.json) cover 10/198 V timing and L extremes plus A1's sensitive 170 V/DIR1/51 kΩ typical boundary. No strict classification flipped. Two 10 V, 100 A, L×0.5 cases initially changed one die peak by 2.29% at 0.2→0.1 ns; further halving to 0.05 ns changed it by **0.538%**, meeting the runbook's <2% peak criterion without changing solver tolerances. [Resolution](resolution-run.txt), [further refinement](refinement-run.txt), and [audit](audit-run.txt) outputs retain the evidence. The audit reports **AUDIT PASS**, all 15 source hashes match, and no half-step peak failure remains. The strict 10 V no-pass and signed 10 V pass are reported as two distinct diagnostics, not reconciled by changing the criterion.

## Open items and physical confirmation

The **D1 both-leg coupled inductance matrix** has not been applied; the board-dependent rerun is pending. C2 also needs A's derated signed current trajectory at each switching event to detect reversal during dead time, plus voltage/current-dependent hot diode Vf and recovery conditions. No result is extrapolated below **10 V**; events there are outside C1's map. A1's ideal current source cannot determine tank-current reversal or the preceding diode stored-charge state. A staged scope test of both legs' OUT, die-proximate VGS, VDS, switch node, and current at low bus and rising load, cold/hot, is the physical confirmation. This reference report changes no board, source, firmware, or part value.

**Master-plan §5 status line:** C1 reference map complete and handed to C2; native-15 dead-time/loss verdict **BLOCKED pending D1 both-leg matrix and C2 derated-event comparison**. Cheapest next step: D1 supplies its extracted matrix in a documented machine-readable form, then rerun this pinned deck for both legs and hand the resulting waveform catalog to C2.

## Reproduce

From this checkout's repository root, with the pinned vendor library/archive restored under the ignored `validation-plan/sim-kit/models/vendor/` directory, run:

```sh
cd zapote/power-stage-120v
/Users/bennet/Miniforge3/bin/python3 validation-results/round3-coordination/raw-evidence/verify.py validation-results
cd validation-plan/sim-kit
/Users/bennet/Miniforge3/bin/python3 smoke_test.py
cd ../../../../
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/run_c1.py --phase sweep --jobs 4
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/run_c1.py --phase export
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/check_resolution.py --jobs 4
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/refine_resolution.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/refine_physical.py --jobs 4
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/run_c1.py --phase export
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs/audit_c1.py
```

The `cd ../../../../` returns to the repository root. The licensed vendor library is pinned in [source_hashes.json](source_hashes.json) and is not shipped here. Raw per-case `case.json`, `commutation.csv.gz`, and `ngspice.log.gz` are under ignored `outputs/runs/`; they remain local in this worktree and regenerate from the scripts. Summary JSON/CSV and scripts are the handback artifacts.

Post-review cache checks bind saved search rows to the recorded C1 script, current timing/specification and unique expected IDs. Original pre-guard source and source manifest are preserved under ignored `outputs/runs/source-before-review/`. Numerical results are unchanged. The frozen `c2-waveform-sha256.csv` pins the 1,226 nominal-L raw waves consumed by C2; each entry agrees with the coordinator raw-evidence manifest.
