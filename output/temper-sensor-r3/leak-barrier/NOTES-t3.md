# T3 — CR-5 band with a setpoint cap

This is a model study on the requested leak-study base, not a board change.
`cr5_band.py` imports `firmware/leak_checks.py`, `firmware/rim_limit.py`, and
their benign generators. It rebuilds the unchanged C apparatus with
`firmware/build_lib.sh`. It does not change firmware, an existing study, or
the controller. No resistor values are calculated.

## Reproduce

From `/workspace/temper`:

```sh
source /workspace/.temper-tools/activate.sh
python output/temper-sensor-r3/leak-barrier/cr5_band.py --check
```

To regenerate the new evidence intentionally, omit `--check`. Both commands
perform all simulations; `--check` never writes the evidence and compares
the complete regenerated JSON byte for byte. Jobs affect scheduling only.
Every result below comes from `cr5-band.json`; dotted paths identify keys.
The file's `apparatus` records the base, compiler and Python package versions,
script hash, and full hashes of the unchanged model/C inputs. No timestamps
or current-HEAD values enter the gate.

**Current result: `T3 FAIL`.** The strict benign gate remains failed:
`gate.benign_no_firmware_latch_or_d1_lost` is false because
`caps.230.benign.d1_lost` is **1** and `caps.250.benign.d1_lost` is **2**.
These count benign runs with a D1 LOST classification, not repeated events.
All caps have **0** benign firmware latches (`caps.<cap>.benign.firmware_latches`)
and **0** hardware nuisance trips (`caps.<cap>.band.benign_hardware_trips`).
D1 LOST is a non-latching probe classification that removes power; it is
reported separately from firmware latches. The gate is retained unchanged.
This new check covers both imported benign sets and does not alter any
existing firmware or study gate.
The full `--check` rerun reproduced the committed JSON exactly, then returned
nonzero for this benign gate. All other `gate` entries are true. Its final
line was `T3 FAIL: gates failed: ...`; no JSON mismatch was reported. No gate
was loosened.

## Results and source keys

The control reproduces **0/235** guaranteed top-edge trips and **13/235** possible low-edge trips, with **59/235** firmware latches before the bar. The simulated benign maximum is **246.5 °C**, the analytic hold envelope **245.1 °C**, and the reported margin **15.8 K** (`control`). The full-precision reference margin used for band shifts is 15.817639 K (`control.margin_to_benign_bound_K`).

**Board-owner table.** Glass temperatures; centre means band midpoint. This is a proposed band position, not a resistor or a released circuit.

| Cap °C | Hottest benign bound °C | Low °C | Centre °C | Top °C |
|---|---|---|---|---|
| 200 | 200.000 | 215.9 | 228.8 | 241.7 |
| 210 | 208.971 | 224.8 | 237.7 | 250.6 |
| 220 | 218.309 | 234.2 | 247.1 | 260.0 |
| 230 | 227.820 | 243.7 | 256.6 | 269.5 |
| 240 | 237.245 | 253.1 | 266.0 | 278.9 |
| 250 | 246.482 | 262.3 | 275.2 | 288.1 |

Sources: `board_owner`, `caps.<cap>.benign.glass_bound_C`; the hold-only envelope and its hot reading stack are `benign.envelope_glass_C`, `benign.rim_hot_tolerance_K`, and `benign.rim_reading_limit_C`. Width, reference margin and actual margin are under each cap’s `band`.

**Nominal sensing, both fixed glass-offset endpoints.** Sources: `caps.<cap>.nominal.all`; counts below are before the pan bar and use the hazardous denominator in that row.

| Cap °C | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds |
|---|---|---|---|---|---|---|
| 200 | 80 | 20 | 41 | 41 | 41 (51.250%) | 0 |
| 210 | 85 | 11 | 36 | 37 | 37 (43.529%) | 0 |
| 220 | 88 | 8 | 28 | 34 | 34 (38.636%) | 0 |
| 230 | 101 | 5 | 18 | 28 | 28 (27.723%) | 0 |
| 240 | 113 | 4 | 12 | 27 | 27 (23.894%) | 0 |
| 250 | 116 | 0 | 8 | 26 | 26 (22.414%) | 0 |

**Lowest combined coverage among the cold-stack / slow-glass geometries.** Each row selects the lower coverage fraction from the two imported geometries, retaining that geometry’s own hazardous denominator. Sources: `caps.<cap>.worst_corner.by_glass.<selected geometry>`.

| Cap °C | Selected geometry | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds |
|---|---|---|---|---|---|---|---|
| 200 | leak_envelope | 43 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 210 | leak_envelope | 45 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 220 | leak_envelope | 54 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 230 | leak_envelope | 54 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 240 | leak_envelope | 61 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 250 | flat_cool_eye | 54 | 0 | 4 | 0 | 0 (0.000%) | 0 |

The complete geometry breakdown follows; these model-case fractions do not establish a worst-case probability. Sources: `caps.<cap>.worst_corner.by_glass.<geometry>`. The pooled cohort is retained separately in `worst_corner.all`.

| Cap °C | Glass geometry | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds |
|---|---|---|---|---|---|---|---|
| 200 | flat_cool_eye | 37 | 7 | 15 | 10 | 10 (27.027%) | 0 |
| 200 | leak_envelope | 43 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 210 | flat_cool_eye | 39 | 3 | 7 | 6 | 6 (15.385%) | 0 |
| 210 | leak_envelope | 45 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 220 | flat_cool_eye | 41 | 3 | 7 | 6 | 6 (14.634%) | 0 |
| 220 | leak_envelope | 54 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 230 | flat_cool_eye | 46 | 2 | 7 | 5 | 5 (10.870%) | 0 |
| 230 | leak_envelope | 54 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 240 | flat_cool_eye | 52 | 0 | 6 | 4 | 4 (7.692%) | 0 |
| 240 | leak_envelope | 61 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 250 | flat_cool_eye | 54 | 0 | 4 | 0 | 0 (0.000%) | 0 |
| 250 | leak_envelope | 62 | 0 | 0 | 0 | 0 (0.000%) | 0 |

**Offset sensitivity — Nominal sensing.** The benign bound and band are unchanged from the board table. Sources: `sensitivity.<offset>[].nominal` (also `caps.<cap>.nominal.by_offset_K.<offset>`).

| Cap °C | Offset K | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds |
|---|---|---|---|---|---|---|---|
| 200 | 12 | 38 | 15 | 26 | 26 | 26 (68.421%) | 0 |
| 210 | 12 | 43 | 11 | 28 | 29 | 29 (67.442%) | 0 |
| 220 | 12 | 46 | 8 | 21 | 27 | 27 (58.696%) | 0 |
| 230 | 12 | 52 | 5 | 15 | 25 | 25 (48.077%) | 0 |
| 240 | 12 | 56 | 4 | 12 | 27 | 27 (48.214%) | 0 |
| 250 | 12 | 58 | 0 | 8 | 26 | 26 (44.828%) | 0 |
| 200 | 46 | 42 | 5 | 15 | 15 | 15 (35.714%) | 0 |
| 210 | 46 | 42 | 0 | 8 | 8 | 8 (19.048%) | 0 |
| 220 | 46 | 42 | 0 | 7 | 7 | 7 (16.667%) | 0 |
| 230 | 46 | 49 | 0 | 3 | 3 | 3 (6.122%) | 0 |
| 240 | 46 | 57 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 250 | 46 | 58 | 0 | 0 | 0 | 0 (0.000%) | 0 |

**Offset sensitivity — Cold stack and slow glass.** The benign bound and band are unchanged from the board table. Sources: `sensitivity.<offset>[].offset_worst_corner` (also `caps.<cap>.offset_worst_corner.by_offset_K.<offset>`).

| Cap °C | Offset K | Hazardous | CR-5 top | CR-5 low | Firmware | Top OR firmware | CR-5 adds |
|---|---|---|---|---|---|---|---|
| 200 | 12 | 41 | 8 | 18 | 13 | 13 (31.707%) | 0 |
| 210 | 12 | 41 | 6 | 13 | 9 | 9 (21.951%) | 0 |
| 220 | 12 | 45 | 4 | 8 | 7 | 7 (15.556%) | 0 |
| 230 | 12 | 48 | 2 | 7 | 6 | 6 (12.500%) | 0 |
| 240 | 12 | 54 | 0 | 5 | 3 | 3 (5.556%) | 0 |
| 250 | 12 | 54 | 0 | 2 | 0 | 0 (0.000%) | 0 |
| 200 | 46 | 41 | 0 | 6 | 6 | 6 (14.634%) | 0 |
| 210 | 46 | 40 | 0 | 3 | 0 | 0 (0.000%) | 0 |
| 220 | 46 | 42 | 0 | 1 | 0 | 0 (0.000%) | 0 |
| 230 | 46 | 51 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 240 | 46 | 59 | 0 | 0 | 0 | 0 (0.000%) | 0 |
| 250 | 46 | 56 | 0 | 0 | 0 | 0 (0.000%) | 0 |

**Conclusions that flip between the offset endpoints.** Each list gives cap values; “none” means the conclusion does not flip. Source: `sensitivity.flips` (whether the named count is nonzero, or complete coverage is true).

- `all_hazardous_stopped`: nominal: none; offset_worst_corner: none.
- `cr5_top_before_300`: nominal: 210, 220, 230, 240; offset_worst_corner: 200, 210, 220, 230.
- `cr5_adds_over_firmware`: nominal: none; offset_worst_corner: none.

Complete-coverage results in the two main cohorts (`caps.<cap>.<cohort>.all.all_hazardous_stopped`):

- nominal: no tested cap.
- worst_corner: no tested cap.

No tested cap meets the complete-coverage bar. In every tested cohort, the
guaranteed CR-5 top-edge trips before the bar are already covered by a firmware
latch before the bar (`cr5_adds_over_firmware` is zero throughout). CR-5 retains
its independent hardware role, but its proposed retuning adds no timing
coverage to this model's functioning firmware.

The glass-offset conclusion that changes is whether standalone hardware
coverage exists: under nominal sensing, the positive top-edge coverage at the
hotter endpoint disappears at the cooler endpoint for the caps listed in
`sensitivity.flips.cr5_top_before_300.nominal`; the cold-stack/slow-glass
counterpart is the adjacent `offset_worst_corner` list. Neither complete
coverage nor an incremental guarantee over firmware changes at the endpoints
(`sensitivity.flips.all_hazardous_stopped`,
`sensitivity.flips.cr5_adds_over_firmware`).

A missed nominal case at the lowest cap is triply_clad_24, 300.0 Ω, step onset: the pan first exceeds the bar at 303.2 s, with glass at 190.0 °C against the band top of 241.7 °C. Source: `caps.200.nominal.all.missed_example` and `caps.200.band.top_C`.

The denominator is the inherited steady-hazard definition. Transient crossings outside it are recorded separately as `not_steady_hazard_but_crossed_300` in every coverage row. These are passive trajectories, and a previous passive latch may have been recorded; the diagnostic is not an additional count of missed trips.

| Cap °C | Nominal transient-only crossings | Worst-corner transient-only crossings |
|---|---|---|
| 200 | 9 | 10 |
| 210 | 5 | 6 |
| 220 | 18 | 13 |
| 230 | 5 | 8 |
| 240 | 10 | 13 |
| 250 | 19 | 21 |

Every missed cohort retains `missed_example`, including leak resistance, onset, first pan-bar crossing time, glass at that crossing, and eventual latch. The original first-hold setpoints and step time are in `assumptions.original_pan_setpoints_C` and `assumptions.setpoint_step_s`: early leaks can outrun the glass before the final setpoint step, which these caps do not retime.

The new script executes **9852 simulations** per generation/check (`apparatus.simulations`). `T3 PASS` means the control, identity, band-margin and benign-nuisance gates pass; it does not mean complete coverage of the pan-temperature bar.

## Interpretation

The hardware band is expressed in **true glass temperature**. Its spread
already includes its comparator/NTC component tolerances and hardware
self-heating. The software rim tolerance table is a **reading error**: it is
carried through the imported stress benign runs and the unchanged firmware
comparison. Adding that table to true glass as well would count sensor error
twice. The JSON records both the glass bound and software reading limit.

The analytic hold envelope and simulated transient benign maximum are
different quantities. The committed **246.5 °C** simulated maximum and
reported **15.8 K** margin are the control to preserve;
the analytic envelope is **245.1 °C** (`control`).

The benign bound is the larger of the imported analytic glass envelope and
the largest true-glass sample across both imported benign sets, retained at
the recorded trace precision. The band preserves at least the control's actual
low-edge margin; each lower-cap low edge rounds upwards to the next band-table
increment, so it is the lowest representable band with that margin. Its
complete width is preserved, and its centre is the arithmetic
midpoint of the tolerance band. The nominal comparator threshold need not
be that midpoint.

All pan setpoints, including the first hold, obey the cap; the water pot
retains its lower commands. The rim-limit stress generator's hardcoded hot
glass is replaced with the envelope at that cap. The fixed initial glass
states from the leak-check benign set are retained. Maxima include the exact
initial temperature as well as after-tick trace samples. Installing a lower
band while glass is still hot from a higher-cap cook is outside these starts.

The control includes the complete original sweep. The main table's nominal
sensing runs at each cap use the same seeds as its hot-bead slots with nominal
bead parameters. The worst-corner cohort is `rim_limit.stress_leak`: cold bead,
high rail, slow glass, with both its lower-envelope and flat/cool-eye
geometries. Each is also broken out under `worst_corner.by_glass`; the
aggregate is a fraction of these model cases, not a probability distribution
of manufactured appliances. Denominators are re-evaluated at each cap
because the closed loop and D1 can change which untripped runs are hazardous.
Even in nominal sensing rows, hardware credit requires the top of the full
manufacturing-tolerance band.
The full original control and the new parameter cohorts have different case
counts and sensor parameters (`control.sweep`, `assumptions.cohorts`). Compare
cap trends within a cohort rather than comparing their raw counts directly.

The sensitivity table separates the two fixed-offset endpoints and also
runs the cold/high-rail/slow-glass corner at each endpoint. It keeps the
same benign-envelope band: an unmeasured offset is not permission to lower
the band using a cooler benign-glass assumption. An endpoint-specific band
would require bench evidence that excludes the hotter benign envelope.

"Stopped before the bar" means the CR-5 **top** edge is reached, or an
existing firmware latch is recorded, strictly before the first pan crossing.
The low edge denotes a possible trip and is never credited as guaranteed.
The imported latches remain passive so all mechanisms see the same
trajectory. Native D1 and the non-latching supervisor power actions remain
active as in the imported apparatus. Credit assumes immediate interruption
at that event: comparator
and power-cut delay, stored heat, and post-cut temperature rise are not
modelled. This is a timing screen, not proof that a physical pan stays below
the bar. The cold-soak latch gets no credit because these leaks develop
during cooking, after its opportunity to evaluate.

## Assumptions and validation

The glass-offset endpoints, bead tolerance, unknown-rail corners,
self-heating and glass lag are recorded in `assumptions`. The glass weights
come from `rim_limit.envelope()` and its retained axisymmetric evidence and
study-08 rows. They are model inputs pending bench validation. The hardware
band's width is held constant under shifting; a real comparator design must
establish that tolerance spread over the chosen temperature range. Nothing
here establishes a new component choice.

The unchanged baseline was run after installing the NumPy and SciPy versions
already pinned in `uv.lock`. Its host/SIL and study gates passed. The run
rewrites existing evidence, including platform-sensitive floating-point
fields; the generated versions and diff were retained under
`/tmp/temper-t3-baseline-generated`, then only this run's generated tracked
outputs were restored to their exact original bytes. No existing evidence
was re-baselined. The T3 gate checks its input hashes again after regeneration.

Ruff passed for the new script, and the repository's required import-boundary
gate passed. Smoke checks covered strict before-bar timing, possible-only
low-edge trips, OR de-duplication, and rejection of changed evidence without
writing it. The recorded input hashes and script hash match the committed
files.

Bench work remains: glass temperature and lag under the proposed cap,
mounting/warp and eye-air range, bead/rail errors, component tolerance spread
at a shifted band, and complete sensing-to-power-extinction and post-cut
thermal behaviour. The insulation, hot production test and seal-ingress
requirements from D-LEAK remain necessary.
