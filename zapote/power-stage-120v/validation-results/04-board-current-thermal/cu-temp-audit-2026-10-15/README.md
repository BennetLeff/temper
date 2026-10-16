# Copper-temperature basis audit, 2026-10-15

Tree: `ps-integrate`, `codex/power-stage-integration` at abd891e5c (read only). PS = `zapote/power-stage-120v`.
Trigger: OPEN-ITEMS S17. The task-04 A4 fields are solved at 20 °C copper, and B3 scales them by I² only. This folder
audits every other consumer of copper resistance or copper loss, and drafts a gate that keeps the class out.
It does not design the B3 fix (another agent has it).

Everything here is derived from committed files. `results/estimates.py` recomputes every estimate below from those files
(`python3 -I results/estimates.py`); nothing was re-solved. Estimates are labelled ESTIMATE.

## Files

| File | What |
|---|---|
| `README.md` | this note |
| `results/audit.json` | the ranked consumers: file:line, assumed temperature, actual temperature, direction, flip, estimate |
| `results/estimates.py`, `results/estimates.json` | the arithmetic |
| `proposed/native-21/layout/gates/cu_temp_basis.py` | the gate |
| `proposed/native-21/layout/gates/cu_temp_registry.json` | the registry (14 entries covering 37 files) |
| `proposed/native-21/layout/gates/test_cu_temp_basis.py` | 41 controls |
| `cu_temp_basis.patch` | `git diff` format against the PS tree: three new files, plus the `chain.sh` and `scorecard.py` wiring. `git apply --check` passes against the repo; not applied |
| `results/test_output.txt`, `results/gate_run.txt`, `results/gate_run.json` | the last test and gate runs on the real tree |

## What temperature the copper actually reaches

- Release case (c18_h10, bay 61 °C), heat-weighted, from `heat-attribution-2026-10-15/results.json` (`copper_tcr_first_order`):
  sw_a 90–96, sw_b 96–98, res_a and coil_feed 83–86, bus_p 99–102, hv_ret 104–106, leg 109–112 °C.
  ρ factor 1 + 0.00393 (T − 20) = ×1.25 to ×1.36.
- 28 A case (c28_h10, bay 55 °C): not solved with TCR anywhere. ESTIMATE of the heat-weighted tank copper: 108 to 160 °C.
  - Low end: 55 + (29.4/18.9)² × (82.9 − 61) = 55 + 2.42 × 21.9 = 108 °C.
  - High end: the B3 c28 copper peak, 160.2 / 160.1 °C (`b3-ratings/margins.json`), which no mean can exceed.
  - ρ factor ×1.35 to ×1.55.
- The c22 and c28 ratchet cases already fail the B3 ratings gate without TCR (laminate −30.2 K, worst part −32.3 K at c28). TCR makes those worse; it cannot flip them.

## Ranked consumers (verdict risk, highest first)

"Direction" is the temperature side that is conservative for that consumer's verdict. NON-CON marks a basis on the wrong side.

| # | Consumer (registry id) | file:line | Assumes | Actual (c18 / c28) | Direction | Flip risk |
|---|---|---|---|---|---|---|
| 1 | Task-04 A4 fields into B3 and `b3_ratings` (CU-01, 02, 04): `b3_release_margin_K`, `b3_laminate_margin_K`, `b3_rated_part_margin_K` | `round5-native21/run_board.py:34, 312`; `b3/thermal.py:277-308, 406`; `sheet_solver.py:102-105`; `scorecard.py:185-196` | 20 °C, by default | 83–112 °C / 108–160 °C (est.) | hot conservative; **NON-CON** | **Flips the release verdict.** See below |
| 2 | R5 derating G6, `r5_derating.py`, `r5_vias17.py` (CU-05) | `stage17-r5/g6_r5_derating.py:165-171`; `r5-derating/r5_derating.py:96, 139`; `stage17-r5/r5_vias17.py:42, 102` | 20 °C (inherits B3; the via barrel uses ρ with no TCR) | R5 row 118 °C / pad 135 °C (h25), 162.5 °C (h10, bay 55) | hot conservative; **NON-CON** | **Possible** at c28/h25. See below |
| 3 | Fuse-copper fusing ratio `fuse_copper_fusing_ratio` (CU-06) | `shoot-through-f1/f1_containment.py:49-57, 287-308`; `scorecard.py:218-226` | 105 °C explicit (Onderdonk); cord R at 20 °C | bus_p 99–102, hv_ret 104–106, leg 109–112 °C | both corners | None as coded; the ratio is 0.993 and sign-sensitive to Ta within ±5 K |
| 4 | IPC-2221 20 K width screen (CU-12) | `stage15-28A/sw_widths.py:40, 45-51`; `native-21/layout/patches21.py:197` | about 45 °C, implicit | 81 °C if the screen were met (bay 61 + 20 K) | hot conservative; **NON-CON** | Design margin only; B3 is the gate |
| 5 | Tank neck fin estimate (CU-11) | `stage15-28A/neck_fin.py:23`; `stage15b/ref/neck_fin.py:23` | 95 °C (comment says 100) | 83–112 / 108–160 °C | hot conservative; **NON-CON** at c28 | None; an estimate, not a gate |
| 6 | Kelvin plane and budget, `kelvin_band_low_A` (CU-08, 09) | `kelvin/kelvin_plane.py:53, 113`; `kelvin_budget.py:44-73`; `scorecard.py:180-184` | 125 °C explicit | Kelvin pour at local board temperature, R5 row 118 / 135–162 °C | hot conservative low edge, zero shift at the high edge | No |
| 7 | OCP band, R5 alloy TCR with the B3 pad rise (CU-05b, not registered: no copper constant) | `round3/thresholds.py:131, 182`; `stage17-r5/screen.py:153` | 25 °C + rise (+50 K committed; 84.87 K from B3) | pad 135 °C | magnitude of the rise matters | No |
| 8 | F2 coordination (CU-07) | `f2-coordination/f2_coord.py:39, 72, 83, 166, 197` | 20 °C, explicit ("cold = max current") plus Cu=0 | wiring, not board | cold conservative | No; not a scorecard metric |
| 9 | `via_currents.json` splits (CU-04) | `summarize.py:148` | 20 °C | — | ratios cancel under uniform heating | No |
| 10 | Coil pickup `ocp_pickup_stack_pan60_A` | `coil-pickup/s21b/run_ocp.py:108` | none (flux only); nominal Rs | — | cold (nominal) Rs conservative | No |
| 11 | Kelvin track bound (CU-10) | `kelvin/kelvin_track_bound.py:31` | 120 °C (comment says 125) | — | hot conservative | No (label error 1.4 % in ρ) |
| 12 | Kit solver library and self-tests (CU-13, 14) | `sheet_solver.py:56-57, 102-105`; `audit_kit_solver.py:26-62` | 20 °C | — | not a claim | No |

`firmware/tools/board_derivations.yaml` has no copper resistance, loss or temperature entries (searched for copper, tcr, temp, mohm, shunt, ocp), so it is not a consumer. The scorecard's EMI, leakage, CMTI, bank-ratio and ledger inputs use no copper resistance.

### 1. B3 and the A4 fields: NON-conservative, flips the release verdict

Committed first-order step (`heat-attribution-2026-10-15/results.json`, one Picard step, no feedback), subtracted from
the 20 °C margins in `b3-ratings/margins.json` (c18_h10 at bay 61 °C). `results/estimates.json` E1 has the arithmetic.

| Row | Margin at 20 °C | Added by TCR | Margin after |
|---|---|---|---|
| C40 body | +1.2 K | +6.13 K | −4.93 K |
| R10 terminal | +3.1 K | +6.51 K | −3.41 K |
| Laminate 1 mm block | +5.0 K | +7.22 K | −2.22 K |
| C41 body | +3.8 K | +4.95 K | −1.15 K |
| R20 terminal | +4.6 K | +5.40 K | −0.80 K |

The bay-61 ceiling goes 18.44 → 16.42 A. R18 (+5.3 K), U26 (+5.9 K), R12 (+6.6 K) and the FET-row copper (+7.9 K) were
not quantified by that run and may follow. Scorecard metrics hit: `b3_release_margin_K` (+1.2 → about −4.9),
`b3_laminate_margin_K`, `b3_rated_part_margin_K`. Via-current splits (`via_currents.json`) do not move: they are ratios.
This item is the one the B3 lane is fixing.

### 2. R5 derating G6: NON-conservative, can flip at c28/h25

`stage17-r5/g6.json`: R5 pad max 134.87 °C against the 148.39 °C bound, so 13.52 K of headroom. The pad rise is 84.87 K
and was built from 20 °C copper heat plus R5's own 0.864 W (the alloy part, which does not scale with copper TCR).
- G6 flips if (copper share of the rise) × (ρ factor − 1) × 84.87 K ≥ 13.52 K.
- That needs a copper share of 0.46 at ρ ×1.35, or 0.29 at ρ ×1.55.
- The share is unknown without a re-solve. The R5 rows of margins.json (57.3, 75.9, 107.5 K of rise at c18, c22, c28) fit about 20 K fixed plus 0.1 K per A², so most of the rise scales with I². R5's own heat is a part of that. I cannot split it further without a solve.
- The same row at c28/h10/bay 55 already fails by 14.1 K (162.5 against 148.4 °C), so the verdict that can flip is the h25 one.
- Via barrel I²R in `r5_vias17.py` (no TCR): 0.0293 W → 0.0425 W at 135 °C, mid-wall rise 0.28 → 0.41 K. Negligible.

### 3. Fuse-copper ratio: conservative as coded, but the sign is within the TCR noise

`s44_necks.json` `min_ratio_all` = 0.993, binding row bus_p BR1+ → Q2/Q5 drain (1697.7 of 1710 A²s), at explicit Ta = 105 °C.
Onderdonk factor log10(1 + (1083 − Ta)/(234 + Ta)):

| Ta | 95 | 100 | 102 | 105 | 112 |
|---|---|---|---|---|---|
| ratio (0.993 × f(Ta)/f(105)) | 1.015 | 1.004 | 0.9995 | 0.993 | 0.978 |

The ratio crosses 1.0 at Ta = 101.7 °C. The bus_p copper runs 99–102 °C heat-weighted, so a true basis puts the ratio
at about 1.00. Hot Ta is the conservative side, so 105 °C cannot hide a failure that the real temperature would show.
It does mean the "0.993" and the "1.021 conductor-only" figures are within a few tenths of a percent of 1.0, and anyone
re-basing Ta to the B3 temperature should expect the number to move up by 0.5–1 %. The cord and branch resistance in the
let-through cases uses 20 °C copper (RHO_CU 1.724e-8): cold is conservative there, correctly.

### 4–5. IPC-2221 screen and neck fin: NON-conservative estimates, not gates

- IPC-2221 external 20 K at 70 µm: 9.82 mm at 28 A. The fit assumes copper near 25 °C ambient + 20 K = about 45 °C.
  At bay 61 °C + 20 K = 81 °C: ρ(81)/ρ(45) = 1.2397/1.0983 = 1.129; width ∝ I^(1/0.725) and I_eq = I √1.129, so width ×1.087, about 10.7 mm. ESTIMATE.
  The stage-15 "no part move" call (PLAN.md:179) used this screen and neck_fin; B3 is named as the gate in both.
- neck_fin: ρ = 1.72e-8 × (1 + 0.00393 × 75) is 95 °C, not the 100 °C the comment says. Worst span excess at 28 A is 30.4 K;
  with ρ at 130 to 160 °C it scales to about 33.6 to 36.4 K (ρ ratio only, ESTIMATE).

### 6–7. Kelvin and OCP band: conservative, no flip

- Kelvin plane solved at explicit 125 °C (`kelvin_plane.py:53`). A positive threshold error lowers the trip, so hot is
  the conservative side for the low edge (44 A min, 64.17 A floor). The high edge takes zero shift, which is the cold bound.
  Budget s44: band low 67.77 A, margin 3.60 A.
- The Kelvin pour sits beside R5, which reaches 134.9 °C (c28/h25) to 162.5 °C (c28/h10). e_th scales by f(T)/f(125):
  ×1.028 and ×1.104. Trip shift −2.123 → −2.18 and −2.34 A. Band low 67.71 and 67.55 A. Margin stays above 3.3 A.
- Colder than 125 (85 °C): e_th ×0.889, i.e. a smaller downward shift, so the 125 °C figure is conservative by 11 %.
- The R5 alloy TCR (75 ppm/K) with the B3 pad rise: dLow/dRise = 69.71 A × 75e-6 = 0.0052 A/K. 0 to 20 K more rise costs 0 to 0.10 A against a 3.31 A margin (67.48 against 64.17 A).
- Direction caution for the Kelvin class: for a minimum-trip claim hot copper is conservative; for a maximum-trip or
  nuisance-trip claim cold copper is. The budget already bounds both ends (low edge shifted, high edge unshifted).

### 8–12. Remaining

- Coil pickup (`run_ocp.py`): the induced volts come from loop flux; copper resistance does not enter. A = V/Rs, so a hot
  R5 (×1.0083 at 135 °C, 75 ppm) shrinks the pickup in amps (4.173 → 4.139 A). The nominal Rs used is the conservative side.
- F2: cold is conservative for let-through; not a scorecard input.
- Out of the chain but 20 °C or unregistered (listed in `audit.json`, field `off_chain_20C_or_unregistered`):
  `g02-g03-power-path` (RHO20, DC path R), the c35/c36/r2/13-coupling A4 readers, `budget16.py` harness wire (loop 2 × 0.6 × 0.01724/0.519 = 39.9 mΩ for 0.6 m AWG20; ×1.157 at 60 °C), mains wiring in `burst_meter_sweep.py`.
  Coil R_ac (`board_side.py`, `coil_spec_28a_check.py`) and L1 (`f12_l1_mot.py`) already use hot copper explicitly.

## The gate: `cu_temp_basis.py`

What it does. Static, stdlib `ast`, about 0.9 s, no board data, no KiCad. For each `.py` in the registry's `scan.include`
globs (the scorecard input chain: sim-kit 04-current, task-04 round 5, the 02-protection-timing folders that feed
`kelvin_band_low_A`, `fuse_copper_fusing_ratio` and `ocp_pickup_stack_pan60_A`):

| Finder | Fires on | Explicit (needs no entry) when |
|---|---|---|
| `net` | `Net(...)` or `<mod>.Net(...)` in a file that loads `sheet_solver` | every call passes `temp_c` and it is not a literal ≤ 25 |
| `rho` | copper resistivity constants (1.68e-8, 1.72e-8, 1.724e-8, 1.7241e-8, 0.01724) or names RHO, RHO_CU, RHO20, RHO_CU20 | every statement using one also carries 0.00393 or an ALPHA_CU name |
| `a4field` | the string `heat.npz` or `_joule_w`, or an import of a module that reads the A4 fields (`thermal`, `thermal_body`, `body_runs`, `a4_fields`, `a4_cases`, `thermal_snap`, `thermal_lead`) | never |
| `ipc` | constants 0.048 and 0.725 in one file (IPC-2221) | never |
| `derived` (registry only) | a file that consumes a registered producer's output, anchored by its `pin` regex | — |

Registry entry fields: `id`, `consumer`, `file` or `files`, `kinds`, `basis_temp_c`, `basis_how`, `direction`,
`justification`, and optionally `pin`, `markers`, `waiver`, `hot_floor_c`, `cold_ceil_c`.

Rules; any of these fails the gate (exit 1):

1. An unregistered finding that is not explicit.
2. A registered file that is gone, outside the scan, or whose registered kinds no longer appear (stale entry).
3. "hot is conservative" with a basis below `hot_floor_c` (default 100 °C) or "cold is conservative" with a basis above
   `cold_ceil_c` (default 25 °C), unless the entry has an unexpired waiver `{id, reason, expires}`. This is the rule that
   would have caught S17: a 20 °C basis on a hot-is-conservative consumer.
4. "both corners" without at least two `markers` regexes that are all found in the file.
5. A `pin` regex that no longer matches (ties the declared basis to the code, e.g. `TA_HOT = 105`, `TEMP = 125`).
6. An expired waiver, or any open waiver under `--fail-waived`.

Fourth direction value: I added "not a claim (self-test)" for the kit library and its closed-form audit, because forcing a
hot/cold label on a solver self-test would be false. Drop it if you want exactly three.

Waivers in the filled registry: `S17` (26 files, the A4/B3 family and the R5 consumers; expires 2026-11-30),
`S17-neck` and `S17-ipc` (2 files each). The real tree passes with them. When the B3 hot-copper iteration lands, flip
the B3 entries to a numeric hot basis or to "both corners", delete the waivers, and run `--fail-waived`.

### Test result

`CU_TEMP_ROOT=<PS> python3 -I test_cu_temp_basis.py` → 41 controls, all passed (`results/test_output.txt`). In the repo the
test needs no environment variable. It covers: unregistered `Net()` fails; `temp_c=20.0` is not explicit; `temp_c=100.0`
passes; a bare 1.68e-8 fails; a TCR term makes it explicit; air and aluminium densities do not trip it; A4 readers and
IPC formula fail; hot-conservative at 20 °C fails, with a waiver passes, expired fails, `--fail-waived` fails; cold-conservative at 105 °C fails;
"both corners" with a missing marker fails; pin drift, stale entries, missing files, double entries fail; `files` groups
and `derived` entries work. Real tree: real registry passes (101 files scanned, 37 registered, 30 waived); fails after
2027-01-01 (waivers expired); fails under `--fail-waived`; fails with the `run_board.py` entry removed; fails when
the f1_containment "both corners" marker or the kelvin_plane pin is wrong.

### Wiring (cheap, seconds)

`cu_temp_basis.patch` carries it. Two small edits:
- `chain.sh`: one line before the `H=$(shasum ...)` line (after the build or scoped-reuse branch, so it runs in every mode, scoped or full):
  `python3 -I $G/cu_temp_basis.py --report "$B/cu-temp-basis.json" | tail -4 || { ...; exit 1; }`.
  `chain.sh` sets `pipefail`, so a gate failure stops the chain.
- `scorecard.py`: a hard gate `cu_temp_basis` read from `BUILDDIR/cu-temp-basis.json` (`not errors`). Older builds lack the file and skip it, as the other optional gates do.
It is independent of the board, so it could equally run in `regate.sh` or in a pre-commit hook; it does not need a cache key.

### Limits

- Syntactic. It sees a literal `temp_c=`, a resistivity constant or a TCR term. It cannot see a temperature passed through a function argument, read from JSON, or composed on a shell command line. A script that gets copper resistance from a library it imports under another name is missed (e.g. `run_study.py` and `b3_ratings_gate.py` reach the A4 fields through modules not on the `a4_modules` list, but they sit under `thermal.py` and `run_basis.py`, which are registered).
- A literal `temp_c=20` is treated as non-explicit; `temp_c=T` with any variable is treated as explicit without checking the value. The `pin` regex is the mitigation, and it is optional.
- The registry's `basis_temp_c` and `direction` are human claims. The gate checks them against each other (basis against floor or ceiling), against the code (`pin`, `markers`), and for staleness, not against physics. A wrong "cold is conservative" with a 20 °C basis passes.
- "Both corners" is checked by marker strings, not by running both evaluations.
- Scan roots are the scorecard chain. New folders feeding the scorecard must be added to `scan.include`. A wide scan (all of `validation-results`) finds 22 further unregistered files (the list is in `audit.json`); those are candidate studies and wiring checks outside the chain.
- A4 readers are flagged on the strings `heat.npz` and `_joule_w`; a renamed field file would escape.
- The rho finder is name-and-constant based; the heat-capacity and aluminium `RHO_*` names are excluded by pattern.

## Source files read (all read-only)

`validation-results/04-board-current-thermal/round5-native21/{run_board.py, summarize.py, b3/thermal.py, b3-ratings/margins.json,
heat-attribution-2026-10-15/{README.md, results.json}, stage17-r5/{g6.json, g6_r5_derating.py, r5_vias17.py, screen.py},
r5-derating/r5_derating.py, stage15b/ref/{neck_fin.py, sw_widths.py}}`; `validation-results/02-protection-timing/{kelvin/*,
shoot-through-f1/{f1_containment.py, s21_necks.py, s44_necks.json}, coil-pickup/s21b/{run_ocp.py, result-s44.json},
f2-coordination/f2_coord.py, stage15-28A/{neck_fin.py, sw_widths.py, out/neck_fin.json}, round3/thresholds.py}`;
`validation-plan/sim-kit/04-current/sheet_solver.py`; `native-21/layout/gates/{scorecard.py, chain.sh, model_key.py}`;
`OPEN-ITEMS.md` S17; `firmware/tools/board_derivations.yaml`.
