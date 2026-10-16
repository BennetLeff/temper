# T3 — CR-5 band with a setpoint cap

A model study, not a board change. `cr5_band.py` imports `firmware/leak_checks.py`, `firmware/rim_limit.py` and their benign generators and rebuilds the unchanged C apparatus with `firmware/build_lib.sh`. It changes no firmware, no existing study and nothing in zapote/controller, and computes no resistor values. Every number below is regenerated into `cr5-band.json`; dotted paths are its keys.

**Hazard rule.** A leak run is hazardous when its untripped pan-centre temperature crosses 300 °C at any time (`leak_checks.hazardous()`, owner 2026-10-16). The cloud run used the steady rule (final-100-s mean > 300 °C); each coverage row keeps that count as `steady_rule_hazardous_info`, and `hazardous_settling_at_or_below_bar` counts the hazardous runs that only overshoot.

## Reproduce

```sh
cd output/temper-sensor-r3/leak-barrier
python3 cr5_band.py --check --caps 250,200   # run.sh step 5e (caps 250 and 200)
python3 cr5_band.py --check                  # every cap (manual; see run.sh header)
python3 cr5_band.py                          # regenerate cr5-band.json and this file
```

`--check` compares by content; only the toolchain strings in `TOOLCHAIN_KEYS` are exempt. A full run is 9852 simulations (`apparatus.simulations`). `T3 PASS` means the control, input-identity, band-margin and benign gates pass; it does not mean the bar is met.

## Control (cap 250 °C, today's band)

Reproduced from the committed evidence (`control`, `control.expected`): 277 hazardous runs, 0 reach the band top and 23 the band low edge before the bar, 69 are latched by firmware before the bar; hottest simulated benign glass 246.5 °C, analytic hold envelope 245.1 °C, margin 15.8 K (full precision 15.817639 K).

## Board-owner table

Glass temperatures. Centre is the band midpoint, not a comparator threshold. A proposed band position, not a resistor or a released circuit (`board_owner`, `caps.<cap>.benign.glass_bound_C`).

| Cap °C | Hottest benign bound °C | Low °C | Centre °C | Top °C |
|---|---|---|---|---|
| 200 | 200.000 | 215.9 | 228.8 | 241.7 |
| 210 | 208.971 | 224.8 | 237.7 | 250.6 |
| 220 | 218.309 | 234.2 | 247.1 | 260.0 |
| 230 | 227.820 | 243.7 | 256.6 | 269.5 |
| 240 | 237.245 | 253.1 | 266.0 | 278.9 |
| 250 | 246.482 | 262.3 | 275.2 | 288.1 |

## Coverage before the bar

Counts are hazardous runs stopped before the first pan crossing: the CR-5 top edge (a guaranteed trip), the low edge (possible only, never credited), any firmware latch, and top OR firmware. **CR-5 adds** is the number of runs the band top reaches before the bar that firmware had not already latched before the bar.

**Nominal sensing, both glass-offset endpoints** (`caps.<cap>.nominal.all`):

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|
| 200 | 89 | 26 | 48 | 48 | 48 (53.933%) | 0 | 41 |
| 210 | 90 | 12 | 39 | 40 | 40 (44.444%) | 0 | 50 |
| 220 | 106 | 11 | 38 | 44 | 44 (41.509%) | 0 | 62 |
| 230 | 106 | 6 | 20 | 30 | 30 (28.302%) | 0 | 76 |
| 240 | 123 | 4 | 12 | 30 | 30 (24.39%) | 0 | 93 |
| 250 | 135 | 0 | 10 | 29 | 29 (21.481%) | 0 | 106 |

**Cold stack, high rail, slow glass** (`caps.<cap>.worst_corner.all`, both glass geometries pooled):

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|
| 200 | 90 | 10 | 20 | 14 | 14 (15.556%) | 0 | 76 |
| 210 | 90 | 6 | 11 | 9 | 9 (10.0%) | 0 | 81 |
| 220 | 108 | 6 | 11 | 9 | 9 (8.333%) | 0 | 99 |
| 230 | 108 | 3 | 9 | 6 | 6 (5.556%) | 0 | 102 |
| 240 | 126 | 0 | 8 | 6 | 6 (4.762%) | 0 | 120 |
| 250 | 137 | 0 | 8 | 3 | 3 (2.19%) | 0 | 134 |

By glass geometry (`caps.<cap>.worst_corner.by_glass.<geometry>`):

| Cap °C | Geometry | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|---|
| 200 | flat_cool_eye | 45 | 10 | 20 | 14 | 14 (31.111%) | 0 | 31 |
| 200 | leak_envelope | 45 | 0 | 0 | 0 | 0 (0.0%) | 0 | 45 |
| 210 | flat_cool_eye | 45 | 6 | 11 | 9 | 9 (20.0%) | 0 | 36 |
| 210 | leak_envelope | 45 | 0 | 0 | 0 | 0 (0.0%) | 0 | 45 |
| 220 | flat_cool_eye | 54 | 6 | 11 | 9 | 9 (16.667%) | 0 | 45 |
| 220 | leak_envelope | 54 | 0 | 0 | 0 | 0 (0.0%) | 0 | 54 |
| 230 | flat_cool_eye | 54 | 3 | 9 | 6 | 6 (11.111%) | 0 | 48 |
| 230 | leak_envelope | 54 | 0 | 0 | 0 | 0 (0.0%) | 0 | 54 |
| 240 | flat_cool_eye | 63 | 0 | 8 | 6 | 6 (9.524%) | 0 | 57 |
| 240 | leak_envelope | 63 | 0 | 0 | 0 | 0 (0.0%) | 0 | 63 |
| 250 | flat_cool_eye | 71 | 0 | 8 | 3 | 3 (4.225%) | 0 | 68 |
| 250 | leak_envelope | 66 | 0 | 0 | 0 | 0 (0.0%) | 0 | 66 |

**Headline: what a retuned CR-5 band adds over firmware.** Zero at every cap in every cohort: each hazardous run whose glass reaches the band top before the bar is one firmware had already latched before the bar. Lowering the band with a cap buys no timing coverage in this model; CR-5 keeps its role as the independent hardware trip if the MCU fails.

Per cap, nominal / worst corner / offset worst corner: 200 °C 0/0/0, 210 °C 0/0/0, 220 °C 0/0/0, 230 °C 0/0/0, 240 °C 0/0/0, 250 °C 0/0/0 (`caps.<cap>.<cohort>.all.cr5_adds_over_firmware`).

Hazardous runs that only overshoot (settle at or below 300 °C), nominal / worst corner: 200 °C 9/10, 210 °C 5/6, 220 °C 18/13, 230 °C 5/8, 240 °C 10/13, 250 °C 19/21 (`hazardous_settling_at_or_below_bar`).

## Glass-offset sensitivity

Same band as the board table; the offset is a bench item (`sensitivity.<offset>[]`).

**Offset 12 K, nominal sensing:**

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|
| 200 | 44 | 20 | 31 | 31 | 31 (70.455%) | 0 | 13 |
| 210 | 45 | 12 | 30 | 31 | 31 (68.889%) | 0 | 14 |
| 220 | 54 | 11 | 29 | 35 | 35 (64.815%) | 0 | 19 |
| 230 | 54 | 6 | 17 | 27 | 27 (50.0%) | 0 | 27 |
| 240 | 62 | 4 | 12 | 30 | 30 (48.387%) | 0 | 32 |
| 250 | 69 | 0 | 10 | 29 | 29 (42.029%) | 0 | 40 |

**Offset 12 K, cold stack and slow glass:**

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|
| 200 | 45 | 9 | 21 | 16 | 16 (35.556%) | 0 | 29 |
| 210 | 45 | 6 | 13 | 9 | 9 (20.0%) | 0 | 36 |
| 220 | 54 | 6 | 11 | 9 | 9 (16.667%) | 0 | 45 |
| 230 | 54 | 2 | 8 | 6 | 6 (11.111%) | 0 | 48 |
| 240 | 63 | 0 | 8 | 6 | 6 (9.524%) | 0 | 57 |
| 250 | 71 | 0 | 7 | 3 | 3 (4.225%) | 0 | 68 |

**Offset 46 K, nominal sensing:**

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|
| 200 | 45 | 6 | 17 | 17 | 17 (37.778%) | 0 | 28 |
| 210 | 45 | 0 | 9 | 9 | 9 (20.0%) | 0 | 36 |
| 220 | 52 | 0 | 9 | 9 | 9 (17.308%) | 0 | 43 |
| 230 | 52 | 0 | 3 | 3 | 3 (5.769%) | 0 | 49 |
| 240 | 61 | 0 | 0 | 0 | 0 (0.0%) | 0 | 61 |
| 250 | 66 | 0 | 0 | 0 | 0 (0.0%) | 0 | 66 |

**Offset 46 K, cold stack and slow glass:**

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds | Missed |
|---|---|---|---|---|---|---|---|
| 200 | 45 | 0 | 7 | 6 | 6 (13.333%) | 0 | 39 |
| 210 | 45 | 0 | 3 | 0 | 0 (0.0%) | 0 | 45 |
| 220 | 54 | 0 | 3 | 0 | 0 (0.0%) | 0 | 54 |
| 230 | 54 | 0 | 0 | 0 | 0 (0.0%) | 0 | 54 |
| 240 | 63 | 0 | 0 | 0 | 0 (0.0%) | 0 | 63 |
| 250 | 67 | 0 | 0 | 0 | 0 (0.0%) | 0 | 67 |

Conclusions that flip between the 12 K and 46 K endpoints (`sensitivity.flips`): `all_hazardous_stopped` nominal none, offset worst corner none; `cr5_top_before_300` nominal [210, 220, 230, 240], offset worst corner [200, 210, 220, 230]; `cr5_adds_over_firmware` nominal none, offset worst corner none.

## Benign runs: no false latch, but D1 power cuts

Benign sets: the leak sweep's 548 and the rim study's stress set, commands capped (`caps.<cap>.benign.by_set`). Firmware latches: 200 °C 0, 210 °C 0, 220 °C 0, 230 °C 0, 240 °C 0, 250 °C 0 (`caps.<cap>.benign.firmware_latches`, gated at zero). D1 LOST runs: 200 °C 0, 210 °C 0, 220 °C 0, 230 °C 1, 240 °C 0, 250 °C 2 (`caps.<cap>.benign.d1_lost`). D1 LOST is the contact check classifying the pan as lifted: it cuts power without a fault until a retry probe passes. No existing gate measured it on the stress set; it is held at the recorded count (`gate.benign_d1_lost_as_recorded`) and is DECISIONS.md D-BARRIER open item 18.

| Cap °C | Set | Kind | Pan | Seed | Corner | τ_g s | LOST at s | Mean power 10 s before W | Power off s | Restored | LOST events |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 230 | stress_benign | sp_down | carbon_steel_28 | 40017 | hot_stack | 106.0 | 1177.9 | 450.0 | 25.0 | True | 1 |
| 250 | stress_benign | sp_down | carbon_steel_28 | 40014 | hot_stack | 106.0 | 1195.5 | 450.0 | 25.0 | True | 1 |
| 250 | stress_benign | sp_down | cast_iron_26 | 40020 | hot_stack | 106.0 | 1261.6 | 450.0 | 25.0 | True | 1 |

Power off is measured by replaying the case with the controller output logged: the time from the first LOST tick until p_cmd is next above zero (`caps.<cap>.benign.d1_lost_runs[]`).

## Interpretation

The hardware band is expressed in true glass temperature; its spread already includes comparator/NTC tolerances and self-heating. The software rim tolerance table is a reading error and is carried only through the firmware comparison, so it is not counted twice. The benign bound is the larger of the analytic hold envelope and the hottest simulated benign glass at that cap; each lower band keeps today's actual low-edge margin and today's width.

"Stopped before the bar" means the band top is reached, or a firmware latch is recorded, strictly before the first pan crossing, with an ideal immediate cut: comparator and power-cut delay, stored heat and post-cut rise are not modelled. Cold soak gets no credit here because these leaks start mid-cook. Cohorts have different case counts and sensor parameters (`assumptions.cohorts`); compare trends within a cohort.

## Provenance and bench work

Written by a Codex cloud agent on Linux (2aea71687, steady rule); its unchanged script was rerun on the Mac for the cross-platform comparison recorded in the port's commit message, then ported to the peak rule and regenerated here. Glass offset and lag, mounting and warp, bead and rail errors, comparator spread at a shifted band and the full sensing-to-power-off path remain bench items. The insulation, production-test and qualification requirements (`SPEC.md`, D-BARRIER) carry the bar.
