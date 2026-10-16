# T1 — method, numerical evidence and open questions

## Reproduction and scope

Run from the repository root after activating the prepared environment:

```sh
source /workspace/.temper-tools/activate.sh
python3 output/temper-sensor-r3/leak-barrier/leak_barrier.py
python3 output/temper-sensor-r3/leak-barrier/leak_barrier.py --check
```

The script imports existing study code unchanged, reads committed `firmware/leak-checks.json`, and compiles the production `rtd_convert.c` into a temporary shared library. It uses no random draws, records input content hashes, the derivation source hash, input working-tree state and tool versions, and normalizes floating-point output to deterministic precision. `--check` regenerates in memory, compares the JSON bytes, exits nonzero on a difference or failed derivation gate, and ends with `T1 PASS` or `T1 FAIL: ...`. PASS means evidence consistency, **not hardware safety qualification**. [source: `provenance`, `gates`, `production.release_status`]

## What the hazardous threshold means

The source has 624 leak runs and 235 hazardous runs. The highest **sampled** hazardous resistance is 1732.1 Ω, with a maximum final-window mean of 318.9 °C at that resistance. Only 59 hazardous runs latch before the first crossing. [source: `hazard.runs`, `hazard.hazardous_runs`, `hazard.highest_sampled_hazardous_ohm`, `hazard.highest_sampled_hazardous_max_steady_C`, `hazard.latched_before_bar`]

The grid jumps by 587.8 Ω to 2319.9 Ω. That next sample's largest mean is 299.8 °C: headroom 0.2 K, versus source rounding to 0.1 K. Its largest transient is 304.2 °C, with 27 runs crossing the bar, and the largest absolute drift over the last 100 s is 11.11 K. Calling its result a “peak of 299.8 °C” is incorrect; the quoted value is a maximum of tail means. [source: `hazard.unsampled_gap_ohm`, `hazard.next_sample_ohm`, `hazard.next_sample_max_steady_C`, `hazard.next_sample_steady_headroom_K`, `hazard.source_steady_rounding_K`, `hazard.next_sample_max_transient_C`, `hazard.next_sample_runs_transient_over_bar`, `hazard.source_tail_window_s`, `hazard.next_sample_max_abs_tail_drift_K`]

A literal continuous largest hazardous resistance **cannot be derived from these sampled, rounded, finite-duration data**. The JSON deliberately reports it as null. D1 and supervisor power interventions remain active even though latches are passive; the response need not be monotone in leak resistance. Interpolation or a bisection without additional convergence/monotonicity evidence would overclaim. The minimal follow-up needs no existing-script edits: import `leak_checks.run_case`, supply finer resistance values and longer `t_end` arguments with the same seeds, inspect tail convergence, and sweep for disconnected hazardous regions. It must distinguish a converged equilibrium from the recorded finite-horizon statistic. [source: `hazard.continuous_status`, `hazard.criterion`, `provenance.input_sha256`]

The following table combines onsets at each pan/glass/bead corner. The JSON also records each onset separately. “None sampled” for the water pot is not infinite resistance tolerance; it belongs to a boiling-water model. [source: `hazard.per_pan_corner`]

| Pan | Glass offset (K) | Bead | Highest sampled hazardous Ω | Next-sample maximum mean °C | Key |
|---|---:|---|---:|---:|---|
| carbon_steel_28 | 12 | cold | 1732.1 | 299.7 | `hazard.per_pan_corner[0]` |
| carbon_steel_28 | 12 | hot | 1732.1 | 299.4 | `hazard.per_pan_corner[1]` |
| carbon_steel_28 | 46 | cold | 1732.1 | 299.5 | `hazard.per_pan_corner[2]` |
| carbon_steel_28 | 46 | hot | 1732.1 | 299.8 | `hazard.per_pan_corner[3]` |
| cast_iron_26 | 12 | cold | 1732.1 | 296.1 | `hazard.per_pan_corner[4]` |
| cast_iron_26 | 12 | hot | 1732.1 | 299.4 | `hazard.per_pan_corner[5]` |
| cast_iron_26 | 46 | cold | 1732.1 | 299.5 | `hazard.per_pan_corner[6]` |
| cast_iron_26 | 46 | hot | 1732.1 | 299.8 | `hazard.per_pan_corner[7]` |
| disc_pot_water_1l5 | 12 | cold | None sampled | 115.6 | `hazard.per_pan_corner[8]` |
| disc_pot_water_1l5 | 12 | hot | None sampled | 115.6 | `hazard.per_pan_corner[9]` |
| disc_pot_water_1l5 | 46 | cold | None sampled | 115.3 | `hazard.per_pan_corner[10]` |
| disc_pot_water_1l5 | 46 | hot | None sampled | 115.3 | `hazard.per_pan_corner[11]` |
| triply_clad_24 | 12 | cold | 1732.1 | 295.1 | `hazard.per_pan_corner[12]` |
| triply_clad_24 | 12 | hot | 1732.1 | 299.4 | `hazard.per_pan_corner[13]` |
| triply_clad_24 | 46 | cold | 1732.1 | 299.3 | `hazard.per_pan_corner[14]` |
| triply_clad_24 | 46 | hot | 1732.1 | 299.6 | `hazard.per_pan_corner[15]` |

Model scope: frying setpoint 250 °C, run duration 1800 s, glass offsets [12.0, 46.0], bead tolerance approximately ±10.2 K at the frying setpoint. Pan classes, gain identification, glass lag, contact model and deterministic seeds are inherited from the hashed source. No pan population or contact/material uncertainty beyond that sweep is certified. [source: `hazard.source_fry_setpoint_C`, `hazard.source_duration_s`, `hazard.glass_offsets_K`, `hazard.bead_tolerance_at_250C_K`, `provenance.input_sha256`]

## Reading errors and conversion

For the ideal comparison the imported function applies the IEC Pt100 resistance curve, the parallel-resistance equation, and the inverse curve. Positive values below mean “reads low.” The C function is called independently on the same effective resistance. The digital illustration also calls the real MAX31865 conversion, with its default self-heating subtraction and loading correction setting. The quoted leak-only error is not the absolute digital error. [source: `reading_errors`, `conversion`]

| True °C | Parallel resistance MΩ | Ideal reading low K | Digital incremental low K | Key |
|---:|---:|---:|---:|---|
| 25 | 1.04 | 0.029843 | 0.033827 | `reading_errors[2]` |
| 25 | 10 | 0.003104 | 0.000000 | `reading_errors[3]` |
| 25 | 100 | 0.000310 | 0.000000 | `reading_errors[4]` |
| 150 | 1.04 | 0.063708 | 0.070267 | `reading_errors[7]` |
| 150 | 10 | 0.006627 | 0.000000 | `reading_errors[8]` |
| 150 | 100 | 0.000663 | 0.000000 | `reading_errors[9]` |
| 250 | 1.04 | 0.100061 | 0.108765 | `reading_errors[12]` |
| 250 | 10 | 0.010408 | 0.000000 | `reading_errors[13]` |
| 250 | 100 | 0.001041 | 0.000000 | `reading_errors[14]` |
| 300 | 1.04 | 0.121362 | 0.110535 | `reading_errors[17]` |
| 300 | 10 | 0.012624 | 0.000000 | `reading_errors[18]` |
| 300 | 100 | 0.001262 | 0.000000 | `reading_errors[19]` |

The hazardous and adjacent sampled resistances are included at every temperature in the JSON as well. At the design IR minimum the nominal digital codes can be identical to the intact code: the MAX31865 readout cannot resolve this insulation resistance directly. The C comparison checks conversion consistency; it does not assert converter, reference-resistor, loading or self-heating accuracy on hardware. [source: `reading_errors`, `conversion.meaning`]

## Audit of every numeric claim in D-LEAK hardware/production items

| Claim | Reproduction / correction | Key |
|---|---|---|
| Design IR and hot test | 10 MΩ at 300 °C is an inherited requirement, not an observed measurement. | `insulation.minimum_ohm`, `insulation.test_C`, `claim_audit.D_LEAK_1` |
| Fused-silica claim | 4 bores, approximately 100 MΩ at 350 °C: **not reproducible; pending supplier confirmation**. | `insulation.candidate_status`, `claim_audit.D_LEAK_1` |
| Highest hazardous leak | Quoted 1.73 kΩ reproduces 1732.1 Ω on the sampled grid only. | `claim_audit.D_LEAK_1.quoted_1_73kohm`, `hazard.continuous_status` |
| Minimum-IR margin | 5773.338722× rounds to 5773. | `insulation.margin_to_sampled_hazard`, `claim_audit.D_LEAK_1.quoted_5773_ratio_reproduced` |
| Hot reading errors | Rounded 0.013 K and 0.001 K reproduce the ideal curve; full precision is in the reading table. | `claim_audit.D_LEAK_1`, `reading_errors` |
| Hot accuracy boundary | ±0.5 K gives 252.256889 kΩ ideally; the old rounded result is 252 kΩ. The source rounds error before bisection; this script uses unrounded error. | `claim_audit.D_LEAK_2`, `accuracy_acceptance[1]` |
| Detection margin | The rounded old boundary gives 145×; the unrounded ideal ratio is 145.636447×. | `claim_audit.D_LEAK_2.quoted_145_ratio_reproduced`, `accuracy_acceptance[1].ideal_margin_to_sampled_hazard` |
| Uncertainty correction | With only the reference allowance: 210.175 kΩ. With the complete positive masking allowance: 83.931 kΩ (48.46× sampled hazard). | `accuracy_acceptance[1]`, `metrology` |
| Post-ingress IR | The same hot IR acceptance is a proposed pass criterion; no actual ingress tests were available. | `claim_audit.D_LEAK_3`, `qualification` |

The proposed uncertainty allowances are assumed **bounds**, not measured expanded uncertainties. If a calibration certificate only supplies a coverage interval, the residual probability outside it must be treated explicitly; it is not an absolute guarantee. An in-circuit accuracy pass cannot demonstrate the inaccessible across-element IR requirement. The supplier/process qualification gap remains even when the hot screen passes. [source: `metrology.status`, `production.release_status`]

## Conditional lifetime ageing budget

Temperature-dependent conduction is not ageing. An Arrhenius resistance-versus-temperature curve contains no elapsed time. Neither a production IR reading nor activation energy alone establishes life. We introduce a clearly conditional damage law: resistance evaluated at the hot reference temperature decays exponentially with accumulated equivalent hot exposure. The activation energy here belongs to that degradation rate, not automatically to electrical conduction. [source: `ageing.law`, `ageing.temperature_units`, `ageing.supplier_rate_or_life_anchor`]

The table spans Ea 0.3–1.2 eV. These are sensitivity cases for thermally activated ionic/contamination transport in glass or ceramic and seal/polymer degradation. They are **not measured material constants** for fused silica, alumina, any enamel or the chosen seal. No defensible assignment of a specific Ea to this assembly is available. A supplier must provide the mechanism, fitted slope and rate anchor under relevant humidity, electrical bias and stress. [source: `ageing.Ea_scope_eV`, `ageing.material_interpretation`, `ageing.supplier_rate_or_life_anchor`]

Starting at 10 MΩ, the requested sampled-hazard × 10 floor is 17.321 kΩ, allowing a logarithmic degradation budget of 6.358421. The strict stay-above condition is `k300 < maximum_k300_per_hour`, equivalently `tau300 > minimum_tau300_hours`. Equality only reaches the floor. **Every Ea remains undetermined from the production pass alone.** The example column assumes an unmeasured rate of 0.001 per hour solely to show both pass and fail cases. [source: `ageing.initial_R300_ohm`, `ageing.target_R300_ohm`, `ageing.log_degradation_budget`, `ageing.example_k300_per_hour`, `ageing.rows`]

| Ea eV | Age °C | Hours | Rate / hot-reference rate | Required minimum tau at hot reference (h) | Example final hot IR (MΩ) | Example above floor? | Key |
|---:|---:|---:|---:|---:|---:|---|---|
| 0.3 | 250 | 1000 | 0.55960 | 88.01 | 5.714363 | Yes, conditional | `ageing.rows[0]` |
| 0.3 | 250 | 3000 | 0.55960 | 264.03 | 1.865965 | Yes, conditional | `ageing.rows[1]` |
| 0.3 | 250 | 10000 | 0.55960 | 880.10 | 0.037126 | Yes, conditional | `ageing.rows[2]` |
| 0.3 | 275 | 1000 | 0.75803 | 119.22 | 4.685864 | Yes, conditional | `ageing.rows[3]` |
| 0.3 | 275 | 3000 | 0.75803 | 357.65 | 1.028890 | Yes, conditional | `ageing.rows[4]` |
| 0.3 | 275 | 10000 | 0.75803 | 1192.17 | 0.005104 | No | `ageing.rows[5]` |
| 0.3 | 300 | 1000 | 1.00000 | 157.27 | 3.678794 | Yes, conditional | `ageing.rows[6]` |
| 0.3 | 300 | 3000 | 1.00000 | 471.82 | 0.497871 | Yes, conditional | `ageing.rows[7]` |
| 0.3 | 300 | 10000 | 1.00000 | 1572.72 | 0.000454 | No | `ageing.rows[8]` |
| 0.6 | 250 | 1000 | 0.31315 | 49.25 | 7.311368 | Yes, conditional | `ageing.rows[9]` |
| 0.6 | 250 | 3000 | 0.31315 | 147.75 | 3.908372 | Yes, conditional | `ageing.rows[10]` |
| 0.6 | 250 | 10000 | 0.31315 | 492.50 | 0.436502 | Yes, conditional | `ageing.rows[11]` |
| 0.6 | 275 | 1000 | 0.57462 | 90.37 | 5.629206 | Yes, conditional | `ageing.rows[12]` |
| 0.6 | 275 | 3000 | 0.57462 | 271.11 | 1.783781 | Yes, conditional | `ageing.rows[13]` |
| 0.6 | 275 | 10000 | 0.57462 | 903.71 | 0.031950 | Yes, conditional | `ageing.rows[14]` |
| 0.6 | 300 | 1000 | 1.00000 | 157.27 | 3.678794 | Yes, conditional | `ageing.rows[15]` |
| 0.6 | 300 | 3000 | 1.00000 | 471.82 | 0.497871 | Yes, conditional | `ageing.rows[16]` |
| 0.6 | 300 | 10000 | 1.00000 | 1572.72 | 0.000454 | No | `ageing.rows[17]` |
| 0.9 | 250 | 1000 | 0.17524 | 27.56 | 8.392538 | Yes, conditional | `ageing.rows[18]` |
| 0.9 | 250 | 3000 | 0.17524 | 82.68 | 5.911258 | Yes, conditional | `ageing.rows[19]` |
| 0.9 | 250 | 10000 | 0.17524 | 275.61 | 1.733537 | Yes, conditional | `ageing.rows[20]` |
| 0.9 | 275 | 1000 | 0.43558 | 68.50 | 6.468898 | Yes, conditional | `ageing.rows[21]` |
| 0.9 | 275 | 3000 | 0.43558 | 205.51 | 2.707016 | Yes, conditional | `ageing.rows[22]` |
| 0.9 | 275 | 10000 | 0.43558 | 685.04 | 0.128323 | Yes, conditional | `ageing.rows[23]` |
| 0.9 | 300 | 1000 | 1.00000 | 157.27 | 3.678794 | Yes, conditional | `ageing.rows[24]` |
| 0.9 | 300 | 3000 | 1.00000 | 471.82 | 0.497871 | Yes, conditional | `ageing.rows[25]` |
| 0.9 | 300 | 10000 | 1.00000 | 1572.72 | 0.000454 | No | `ageing.rows[26]` |
| 1.2 | 250 | 1000 | 0.09807 | 15.42 | 9.065892 | Yes, conditional | `ageing.rows[27]` |
| 1.2 | 250 | 3000 | 0.09807 | 46.27 | 7.451292 | Yes, conditional | `ageing.rows[28]` |
| 1.2 | 250 | 10000 | 0.09807 | 154.23 | 3.750639 | Yes, conditional | `ageing.rows[29]` |
| 1.2 | 275 | 1000 | 0.33018 | 51.93 | 7.187913 | Yes, conditional | `ageing.rows[30]` |
| 1.2 | 275 | 3000 | 0.33018 | 155.79 | 3.713713 | Yes, conditional | `ageing.rows[31]` |
| 1.2 | 275 | 10000 | 0.33018 | 519.29 | 0.368153 | Yes, conditional | `ageing.rows[32]` |
| 1.2 | 300 | 1000 | 1.00000 | 157.27 | 3.678794 | Yes, conditional | `ageing.rows[33]` |
| 1.2 | 300 | 3000 | 1.00000 | 471.82 | 0.497871 | Yes, conditional | `ageing.rows[34]` |
| 1.2 | 300 | 10000 | 1.00000 | 1572.72 | 0.000454 | No | `ageing.rows[35]` |

For a mixed-temperature mission, sum the equivalent exposure at each temperature before applying the logarithmic budget; do not average temperatures. At the reference temperature Ea drops out. No benefit from higher instantaneous insulation resistance at cooler temperatures is credited: all residual resistance is evaluated at the hot reference temperature. Abrupt cracking, water ingress, electrochemical migration and a change of degradation mechanism are outside this smooth exponential law. A part initially exactly at the design minimum has no headroom to meet the stronger post-qualification minimum under any positive degradation rate; qualification therefore needs demonstrated initial headroom as well as a rate bound. The physical continuous hazardous threshold remains unresolved, so even this lifetime floor is a sampled-model sensitivity target, not a lifetime safety certification. [source: `ageing.law`, `ageing.temperature_units`, `ageing.rows`, `hazard.continuous_status`]

A hot-accuracy pass alone does not establish the initial hot IR used by this lifetime table. With the proposed full masking budget, the screen establishes only a conservative resistance lower bound of approximately 83.931 kΩ. Starting there reduces the logarithmic budget to 1.578071, or 1578.07 equivalent hot-reference hours at the illustrative damage rate. Therefore the hidden-path initial-IR claim must be established by qualified construction/process evidence before using the larger lifetime budget. [source: `ageing.initial_condition_status`, `ageing.accuracy_screen_only_resistance_floor_ohm`, `ageing.accuracy_screen_only_log_budget`, `ageing.accuracy_screen_only_example_equivalent_hours`]

## Supplier and laboratory questions before release

- Confirm the fused-silica capillary claim, test voltage, dwell, specimen dimensions, actual wire/termination geometry, atmosphere, contamination limits and measurement uncertainty. Supply hot resistance distributions and ageing data, not a room-temperature bulk resistivity alone. Compare alumina on the same geometry and service profile. [source: `insulation.candidate_status`, `production.ir_voltage_status`]
- Provide a validated ageing-rate anchor and Ea uncertainty for the assembled insulation/seal mechanism; identify material transitions and changes in wet or oily environments. Demonstrate that separate witness structures represent the hidden element-pad and bore-exit leakage paths. [source: `ageing.supplier_rate_or_life_anchor`, `ageing.material_interpretation`, `production.release_status`]
- Confirm the IR stress is nondestructive, define the seal’s allowed temperature/strain, and approve wash/oil chemistry, humidity/cycling severities and recovery sequence. Standard texts were not available for review; a named method is not a completed test specification. [source: `production.ir_voltage_status`, `qualification.standard_text_read`, `qualification.standard_severities`]
- Validate bridge/reference calibration, thermal gradients, self-heating and bias dependence. Establish yield with the fixed final accuracy threshold, independently bound intrinsic element drift after ageing, and demonstrate that calibration before assembly cannot conceal a later leak. [source: `metrology.status`, `production.hot_measured_acceptance_K`, `production.release_status`]
- Extend the finite leak grid near the adjacent sample, resolve tail drift, and bound pan/contact/glass variation before using any continuous cutoff for a safety claim. Verify the actual fitted rim hardware and cold-soak prerequisites on the final product. [source: `hazard.continuous_status`, `hazard.next_sample_max_abs_tail_drift_K`, `residual_layers.coverage`]

## Environment and baseline reproducibility

The restored checkout initially contained a different branch; the requested base was fetched and the dedicated T1 branch created. The scratch nightly editor and official KiPy IPC were checked before analysis. No board edits were made. NumPy and SciPy were missing from the activated environment and installed with user authorization; no manifests or lockfiles were changed.

The baseline run regenerated numerical differences in pre-existing evidence on this Linux apparatus. The user authorized preserving those differences separately, restoring original evidence byte-for-byte, and proceeding only if all existing gates passed. The final validation record below identifies the preserved logs/differences. This is an explicit cross-environment reproducibility gap; a passing firmware suite does not mean the existing evidence reproduced byte-for-byte. The T1 gate reads the restored, hashed committed evidence and never rewrites it. Its source-cleanliness gate rejects uncommitted changes to the study inputs, including evidence regenerated by the full suite; the new deliverables themselves are outside that input-state check. [source: `provenance.input_sha256`, `gates.source_sweep_passed`]

Validation records for this workspace are preserved outside the checkout at `/workspace/t1-validation/`: `baseline.log` and `baseline.diff` retain the initial run and its differences; `final.log`, `final.diff`, and `comparison.txt` retain the final run and comparison. The baseline ended `ALL C1 FIRMWARE CHECKS PASS`. Run the T1 gate from a clean checkout: the full firmware suite rewrites its own evidence, so cross-platform drift must be preserved and reviewed before restoring the originals. The new gate is invoked separately; the existing `run.sh` remains unchanged.

Final validation: both complete firmware runs ended `ALL C1 FIRMWARE CHECKS PASS`, retaining the expected report-only `screen_d1` and `stretch_3_6_3` failures. The generated evidence differences were byte-identical between these runs and were preserved before restoring every original record. The new derivation and its `--check` passed after restoration; an altered JSON was rejected without writes, and dirty study inputs were rejected during the rerun. Ruff and the repository import-boundary gate passed. No existing source, evidence, gate or board file is changed in this commit.
