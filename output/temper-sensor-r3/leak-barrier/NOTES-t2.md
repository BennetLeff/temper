# T2 — maximum user setpoint and Pt100 leak coverage

This is a sensitivity study for a human product decision. No firmware constants, existing studies, or existing evidence are changed.

## Combined coverage

The plot and mid-cook columns cover any first firmware latch in `leak_checks.LATCHES`, including the leak chain, rim limit and rim over-range. The leak begins during heating, so cold soak contributes no catches to those runs. The last column reports the cold check alone for temperature-independent leakage already present at an eligible cold start, with a measured rail at the stated ambient. These are distinct onset scenarios, with no assumed probability of a cold-present leak. They cannot be combined into a physically validated cold-start trajectory by adding or joining counts: leakage from cold can change D1 and the subsequent trajectory. That would require a separate coupled cold-start simulation.

Source: `combined_table[]`; each count and percentage is regenerated into `setpoint-cap.json`. Nominal/worst denominators are separate ensembles. `caps.<cap>.{nominal,worst}.highest_hazardous_R_ohm` gives the highest hazardous resistance (weakest hazardous conductance); lowest resistance is also recorded, since the older study calls that the largest leak.

| Cap C | Nominal before / hazardous (%) | Worst before / hazardous (%) | Highest hazardous R, nominal / worst (ohm) | False, benign / stress | Cold check alone at 25 C, measured rail, nominal / worst (%) |
|---:|---:|---:|---:|---:|---:|
| 200 | 90/168 (53.57) | 10/80 (12.50) | 965.5 / 965.5 | 0 / 0 | 100.00 / 77.50 |
| 210 | 76/168 (45.24) | 6/84 (7.14) | 965.5 / 965.5 | 0 / 0 | 100.00 / 82.14 |
| 220 | 79/184 (42.93) | 6/95 (6.32) | 1293.2 / 1293.2 | 0 / 0 | 100.00 / 70.53 |
| 230 | 66/199 (33.17) | 5/100 (5.00) | 1293.2 / 1293.2 | 0 / 0 | 100.00 / 69.00 |
| 240 | 69/224 (30.80) | 4/113 (3.54) | 1732.1 / 1732.1 | 0 / 0 | 87.95 / 57.52 |
| 250 | 59/235 (25.11) | 0/116 (0.00) | 1732.1 / 1732.1 | 0 / 0 | 85.11 / 56.90 |

![Coverage vs cap](setpoint-cap.png)

### Separate adverse glass geometries

The plotted worst curve is the combined `rim_limit.stress_leak` ensemble, matching the published control. Its lower-glass leak envelope is distinct from its flat/cool-eye geometry. Source: `caps.<cap>.worst_by_glass.<geometry>.{hazardous,before,before_percent,never}`. These counts retain their own hazardous populations.

| Cap C | Leak envelope before / hazardous (%) | Leak envelope never | Flat/cool eye before / hazardous (%) | Flat/cool eye never |
|---:|---:|---:|---:|---:|
| 200 | 0/43 (0.00) | 0 | 10/37 (27.03) | 0 |
| 210 | 0/45 (0.00) | 0 | 6/39 (15.38) | 0 |
| 220 | 0/54 (0.00) | 9 | 6/41 (14.63) | 0 |
| 230 | 0/54 (0.00) | 9 | 5/46 (10.87) | 0 |
| 240 | 0/61 (0.00) | 18 | 4/52 (7.69) | 0 |
| 250 | 0/62 (0.00) | 18 | 0/54 (0.00) | 0 |

## First mechanism and timing

Source: `caps.<cap>.<ensemble>.by_first_mechanism`; pairs are before / after the first crossing. `none.never` is the never-latched count within the run horizon. A same-tick latch and crossing counts as after, matching the original strict-before rule. The JSON retains all other mechanisms separately, including the sensor guard and supervisor.

| Cap C | Ensemble | Leak before / after | Rim limit before / after | Rim over-range before / after | Other before / after | Never |
|---:|---|---:|---:|---:|---:|---:|
| 200 | nominal | 0 / 0 | 90 / 78 | 0 / 0 | 0 / 0 | 0 |
| 200 | worst | 0 / 0 | 10 / 70 | 0 / 0 | 0 / 0 | 0 |
| 210 | nominal | 0 / 0 | 76 / 92 | 0 / 0 | 0 / 0 | 0 |
| 210 | worst | 0 / 0 | 6 / 78 | 0 / 0 | 0 / 0 | 0 |
| 220 | nominal | 1 / 0 | 78 / 105 | 0 / 0 | 0 / 0 | 0 |
| 220 | worst | 0 / 0 | 6 / 80 | 0 / 0 | 0 / 0 | 9 |
| 230 | nominal | 1 / 0 | 65 / 133 | 0 / 0 | 0 / 0 | 0 |
| 230 | worst | 0 / 0 | 5 / 86 | 0 / 0 | 0 / 0 | 9 |
| 240 | nominal | 1 / 0 | 68 / 146 | 0 / 0 | 0 / 0 | 9 |
| 240 | worst | 0 / 0 | 4 / 91 | 0 / 0 | 0 / 0 | 18 |
| 250 | nominal | 1 / 0 | 58 / 176 | 0 / 0 | 0 / 0 | 0 |
| 250 | worst | 0 / 0 | 0 / 98 | 0 / 0 | 0 / 0 | 18 |

## Late-latch exposure

Sources: `caps.<cap>.<ensemble>.late_thermal` (ranges), and `caps.<cap>.rows.<ensemble>[].late_thermal` (every late hazardous run). Passive-until-latch reports the original trajectory up to its first latch. Passive-full-horizon reports continued heating with every latch passive, exactly as `leak_checks.run_case` operates. Both peak temperature and time above the bar are reported for each window; full-horizon metrics are not a post-shutdown prediction. Coverage counts detection timing and does not establish that an early-latched pan remains below the bar after power removal. The existing API has no actuation argument. Minimal extension needed, not made under this task's rules: add an optional `actuate_latches=False` argument to `leak_checks.run_case`; when enabled, remember the first latch and force plant input power to zero from the next control period onward, keeping the default passive path unchanged. That would permit shutdown peak/exposure measurement with the existing truth plant; its first latch should be checked against the passive run. No functions or truth-model classes are replaced by this script.

Exposure counts sampled periods at 0.1 s resolution; peak temperatures are rounded to a tenth of a degree. A final sample still above the bar means the duration is censored by the 1800.0 s horizon.

| Cap C | Ensemble | Late runs | Passive through latch: peak C range | Through latch: seconds above range | Passive full run: peak C range | Passive full run: seconds above range | Still above at horizon |
|---:|---|---:|---:|---:|---:|---:|---:|
| 200 | nominal | 78 | [301.1, 381.6] | [0.5, 38.1] | [309.6, 783.8] | [872.5, 1496.8] | 77 |
| 200 | worst | 70 | [300.1, 486.1] | [0.7, 200.4] | [309.3, 782.6] | [934.8, 1496.4] | 70 |
| 210 | nominal | 92 | [300.2, 392.6] | [0.4, 60.7] | [324.1, 819.5] | [1270.5, 1496.8] | 92 |
| 210 | worst | 78 | [301.4, 501.1] | [3.0, 234.5] | [324.9, 816.4] | [978.2, 1496.4] | 78 |
| 220 | nominal | 105 | [300.2, 403.3] | [0.5, 68.9] | [305.0, 819.5] | [774.2, 1496.8] | 104 |
| 220 | worst | 80 | [300.1, 515.6] | [0.4, 437.5] | [305.0, 816.5] | [714.3, 1496.4] | 80 |
| 230 | nominal | 133 | [300.6, 413.2] | [0.5, 84.2] | [318.4, 819.5] | [1055.2, 1496.8] | 133 |
| 230 | worst | 86 | [302.0, 529.7] | [6.7, 488.2] | [319.1, 816.5] | [978.6, 1496.4] | 86 |
| 240 | nominal | 146 | [300.2, 422.5] | [0.5, 107.7] | [306.4, 819.5] | [751.1, 1496.8] | 141 |
| 240 | worst | 91 | [302.2, 543.1] | [9.2, 532.1] | [306.5, 816.5] | [971.7, 1496.4] | 91 |
| 250 | nominal | 176 | [300.0, 431.1] | [0.1, 329.1] | [319.1, 819.5] | [1094.2, 1496.8] | 176 |
| 250 | worst | 98 | [300.2, 556.2] | [1.6, 608.3] | [317.9, 816.5] | [978.6, 1496.4] | 98 |

## Cold soak: before heating, only if the leak is present when cold

The existing check runs at eligible PREHEAT entry, before any heating; it is not an unconditional power-up latch. The original idle/history, heatsink, flatness and rim-saturation conditions still apply. A leak forming later during a cook cannot be caught by this layer for that cook. `window` denotes the existing RTD low-resistance fault rather than D-SOAK.

Source: `caps.<cap>.cold.<ensemble>.coverage.<rail>.<family>.<ambient>`. The script reweights committed `cold-soak.json` `hazardous.per_leak_value` by the newly hazardous runs at each cap, rather than carrying over the original denominator. Fractions in the table count hazardous runs; each JSON cell also records `distinct_leak_values` and `caught_R_ohm` for the fraction of distinct hazardous resistance values. Nominal uses the nominal cold corner; worst uses the cold check's miss corner as well as the dynamic cold-stack ensemble. Rail unknown is `rail_fallback`. The original cold-start validation results are retained as reference evidence in `model.cold_benign`. These thermal histories were not rerun at each cap's prior-cook temperature. Their zero counts validate the original gated sets; they are not new per-cap warm-restart tests.

The next table gives temperature-independent leakage fractions at the displayed ambient and the minimum/maximum percentages across the source ambient grid. All Arrhenius families, ambients and counts are also in the JSON; no distribution over ambients or leak families is assumed.

| Cap C | Ensemble | Rail | At 25 C: caught / hazardous (%) | Range across ambients (%) | Arrhenius range across all Ea and ambients (%) |
|---:|---|---|---:|---:|---:|
| 200 | nominal | rail_fallback | 168/168 (100.00) | 100.00–100.00 | 0.00–100.00 |
| 200 | nominal | rail_measured | 168/168 (100.00) | 100.00–100.00 | 0.00–100.00 |
| 200 | worst | rail_fallback | 44/80 (55.00) | 20.00–77.50 | 0.00–77.50 |
| 200 | worst | rail_measured | 62/80 (77.50) | 20.00–100.00 | 0.00–77.50 |
| 210 | nominal | rail_fallback | 168/168 (100.00) | 100.00–100.00 | 0.00–100.00 |
| 210 | nominal | rail_measured | 168/168 (100.00) | 100.00–100.00 | 0.00–100.00 |
| 210 | worst | rail_fallback | 52/84 (61.90) | 20.24–82.14 | 0.00–82.14 |
| 210 | worst | rail_measured | 69/84 (82.14) | 20.24–100.00 | 0.00–82.14 |
| 220 | nominal | rail_fallback | 184/184 (100.00) | 92.93–100.00 | 0.00–100.00 |
| 220 | nominal | rail_measured | 184/184 (100.00) | 100.00–100.00 | 0.00–100.00 |
| 220 | worst | rail_fallback | 50/95 (52.63) | 17.89–70.53 | 0.00–70.53 |
| 220 | worst | rail_measured | 67/95 (70.53) | 17.89–87.37 | 0.00–70.53 |
| 230 | nominal | rail_fallback | 199/199 (100.00) | 85.43–100.00 | 0.00–100.00 |
| 230 | nominal | rail_measured | 199/199 (100.00) | 100.00–100.00 | 0.00–100.00 |
| 230 | worst | rail_fallback | 52/100 (52.00) | 17.00–69.00 | 0.00–69.00 |
| 230 | worst | rail_measured | 69/100 (69.00) | 17.00–85.00 | 0.00–69.00 |
| 240 | nominal | rail_fallback | 197/224 (87.95) | 74.11–87.95 | 0.00–87.95 |
| 240 | nominal | rail_measured | 197/224 (87.95) | 87.95–100.00 | 0.00–87.95 |
| 240 | worst | rail_fallback | 49/113 (43.36) | 14.16–57.52 | 0.00–57.52 |
| 240 | worst | rail_measured | 65/113 (57.52) | 14.16–73.45 | 0.00–57.52 |
| 250 | nominal | rail_fallback | 200/235 (85.11) | 71.91–85.11 | 0.00–85.11 |
| 250 | nominal | rail_measured | 200/235 (85.11) | 85.11–100.00 | 0.00–85.11 |
| 250 | worst | rail_fallback | 50/116 (43.10) | 14.66–56.90 | 0.00–56.90 |
| 250 | worst | rail_measured | 66/116 (56.90) | 14.66–72.41 | 0.00–56.90 |

Cold and dynamic catches are not added as independent percentages. The dynamic sweep does not simulate temperature-varying resistance for the Arrhenius families. Those families illustrate how leakage that disappears when cold can evade D-SOAK. The source study also reports benign latches outside its gated assumptions, including frozen-pan plateaus, a room below the budgeted band, and an unusually slow heatsink relaxation. Those source results are retained in `model.cold_reported_outside_assumptions` and `model.cold_reported_latched`; they are reference results at the original cook condition, not new cap-specific trajectories. A cap does not establish that those cases are safe or eliminate their bench prerequisites.

## Model scope and control

The nominal ensemble retains glass offsets [12.0, 46.0] K, both bead corners (the cited bead budget is ±10.2 K at the reference temperature), and a 60.0 s glass lag. The stress ensemble is exactly `rim_limit.stress_leak`: both its leak-envelope and flat/cool-eye geometries, cold bead/rail stack at 3367.0 mV, glass lag 106.0 s, eye 45.0 C, and weights 0.7075 / 0.9554. It is an adverse sampled model ensemble, not a proof over every possible pan or tolerance combination. `caps.<cap>.worst_by_glass` separates its geometries.

The cap changes the requested frying-pan final target and clips all requested profiles. Initial targets, pan physics, seeds, leak values, onset ramps, C thresholds, gains, D1 response and supervisor behavior are preserved. Stress-benign hold/down/hot-pan profiles come from the existing factory with its top target capped. The stress factory's fixed initially hot glass is retained, including the original high-temperature envelope even for a lower cap. Original benign hot-glass cases are retained too. The fixed initially hot glass tests the original high-temperature boundary case. It does not establish a bound on every possible benign transient.

Hazardous means the original script's rounded mean pan-center temperature over the final tail window exceeds the bar. D1 LOST still removes power and may alter which runs are hazardous. `max_abs_tail_drift_K` is reported per ensemble: this finite-horizon criterion is not an independently converged equilibrium solve. Both ends of the hazardous resistance range are sampled sweep values, not continuous critical-resistance bounds. Percentages describe this grid of runs, not probabilities or field failure rates.

`control_250.checks` compares the committed C-loop headline counts and the rim study's offline chosen/existing headline counts exactly. The offline rim evaluation has its original decimated sampling and differs from the authoritative C result; it is retained only to reproduce that control, while cap results use the C latches. A control mismatch raises an error before any lower cap runs. `gate` also checks unchanged source inputs, unchanged rim constants, benign latches, and pre-leak latches. A modeled coverage shortfall is reported, not turned into a passing safety claim.

## Firmware integration and re-verification

Exact source lines/excerpts are in `firmware_cap_inventory`. A real product cap belongs in the config manifest's `MAX_TEMP`/`max_temp` entry and generated header, with both independent UI clamps reconciled. The target setter rejects targets beyond `MAX_TEMP`; heating handlers also clamp to it. Runtime config/environment metadata is present in the generated header; a change must preserve agreement between the runtime config, compile-time limit, UI, persistence and all entry points. No limit is changed here.

Re-verify D1 excitation/acceptance, contact-loss and retry behavior, food/batch and hot-pan behavior, estimator/contact-shift and online gain identification, PID gain scheduling and the latent-plateau guard across the reduced target range. The rim rule is setpoint-relative: its glass envelope, hot-tolerance interpolation, decaying reference and not-falling window still require coverage/false-latch checks, with bench glass transients and sensor tolerances. Do not simply lower the absolute runaway, RTD-window or independent hardware comparator limits along with the UI cap. Revisit overshoot/recovery bars, thermal and cooking performance, stored targets, UI feedback, SIL/runtime tests, cold-soak restart histories, production calibration and hot insulation/ingress qualification. This sweep does not replace physical fault injection or qualification.

## Reproduce

The separate unchanged firmware suite passed before this study. Its regeneration produced platform-dependent report differences, which were preserved outside the checkout before the committed files were restored. Existing gates and evidence were not rebaselined. The new control compares exact published headline counts from both instruments. Dependency versions below are recorded in `apparatus`; the project manifests and lockfile were not changed.

```bash
cd /workspace/temper
source /workspace/.temper-tools/activate.sh
uv pip install --python /workspace/temper/.venv/bin/python numpy==2.5.4 scipy==1.18.1 matplotlib==3.11.2
# Verify retained evidence without overwriting the reviewed notes:
python3 output/temper-sensor-r3/leak-barrier/setpoint_cap.py --check
# To regenerate the JSON, PNG and base report (then retain/review these observations):
# python3 output/temper-sensor-r3/leak-barrier/setpoint_cap.py
cd output/temper-sensor-r3/firmware && ./run.sh
```

The script rebuilds the unchanged C cosimulation library on each invocation. `--check` fully reruns the sweep and compares the regenerated JSON byte-for-byte with the committed file; it does not rewrite it. No timestamps or changing current-HEAD/full-worktree-status fields enter gated evidence. Relevant source-input drift against the fixed base is checked explicitly. `apparatus` records the source base, source-input hashes/dirty status, script and library hashes, interpreter/packages, machine and compiler. `--jobs` affects throughput only. `T2 PASS` means evidence/control/benign gates pass, not that the every-hazard-before-bar requirement is met.

## Review observations and validation

A cap changes both the hazardous population and the detector signal. Hazardous counts generally fall, but the identities are not strictly nested: D1 power interruptions and the finite-tail criterion can make a case qualify at one cap and not at another. The physical case identities and seeds are fixed. Compare `caps.<cap>.rows.<ensemble>[].{case_id,T_c_steady,d1_lost}` against `model.bar_C`. The before-bar percentage alone does not describe the tradeoff: `caps.240.nominal.never` records hazardous runs that never latch within the horizon even though `caps.250.nominal.never` is zero. The mechanism table retains all after/never counts.

`caps.<cap>.benign.<set>.d1_lost` records nonlatched contact-loss interruptions separately from false latched faults. Some stress-benign cases have these interruptions. Zero false-latch counts do not mean that every benign trajectory is uninterrupted.

The word steady follows the original rounded final-tail criterion. `caps.<cap>.<ensemble>.max_abs_tail_drift_K` and the per-row drift show that some runs are still changing materially at the horizon. No independent equilibrium-convergence claim is made.

Validation: the complete unchanged firmware `run.sh` passed, the full cap generation passed its exact published controls and other gates, and selected hazardous rows from each cap matched fresh C-library spot replays. The script and library hashes matched the generated apparatus record. A full additional `--check` regeneration was not run within this delivery's time budget; the command above rebuilds and reruns the complete study before comparing JSON bytes.

Run T2 from the committed source inputs. The separate `run.sh` regenerates existing reports; review and preserve its platform-dependent outputs, then restore only reports produced by that run before regenerating T2. The T2 script does not restore other files. The committed notes include this review after the generated tables; `--check` preserves them.
