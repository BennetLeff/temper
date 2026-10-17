# 05 Round 4 item A — derated tank operating grid

- **Board:** `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- **Date / tools / operator:** 2026-09-27 local; source revision `829ee9debc08ce239bc2dffe0938c4fec2429545`; ngspice 45.2, Miniforge Python 3.12.12; Codex GPT-6-Sol. Exact input hashes are in [input-provenance.json](outputs/input-provenance.json).
- **Evidence class:** simulation/model-based. The ideal frequency-control deck and the static trip-band calculation are not a hardware operating-limit qualification.
- **Verdict:** **BLOCKED for release of a controller command limit.** The requested 270 model solves and their numerical checks are complete; the physical sensing/control error and transient allowance below the provisional 42 A actual-current ceiling remain unknown. The lowest static R5 trip threshold is below both analyzed ceilings.

## Summary

Each ceiling has **135/135 frequency-only solutions at or below 60 kHz**. At 42 A, **72** round-3 frequencies remain and **63** are derated; at 40.45 A, **66** remain and **69** are derated. No evaluated case needs burst or phase shift merely to reach its current ceiling. One otherwise retained 42 A point was also derated because its refined numerical margin was too small to trust.

The 1,710 W request falls to as little as **342.6 W** of total pan-plus-coil resistive power at 42 A, or **317.8 W** at 40.45 A (offset/small pan, low L/R corner, 140 V line). These are model outputs, not measured cooking power. Across accepted states, **73/135 cases at each ceiling** exceed the lowest **38.438 A static R5 trip**; 63 of those are derated at 42 A and 69 at 40.45 A. All accepted tank peaks are below the lowest 50.558 A static CT trip.

All **270** accepted peaks were checked at 25 ns, and **133 near-ceiling or stress-extremum** cases at 12.5 ns. No refined result exceeds its ceiling. The smallest 12.5 ns margins are **0.04783 A** below 42 A and **0.04210 A** below 40.45 A. The maximum 25-to-12.5 ns change is **0.0197%** for current peak and **0.0058%** for capacitor-voltage peak. The full checks and the **44** preserved numerical corrections are in [numerical-checks.json](outputs/numerical-checks.json), [quarterstep-checks.json](outputs/quarterstep-checks.json) and [numerical-corrections.json](outputs/numerical-corrections.json).

## Method and assumptions

- **Model assumption:** the copied [tank.cir](scripts/tank.cir) drives an ideal square-wave full bridge from the rectified 60 Hz line into the series loaded-coil/pan/capacitor model. It includes the round-3 frequency-dependent pan resistance, but omits dead time, MOSFET drops, phase shift and burst behavior. The `triply_clad_GUESS` pan class is explicitly estimated. The grid uses the same five pan classes, three paired L/R corners, 108/120/140 V line and 1710/855/300 W requests as round 3.
- **Power definition:** the deck's `p_avg` is `I_rms² × (R_pan(f) + R_coil)`, the **total tank resistive dissipation** used by the round-3 request search. [power-breakdown.csv](outputs/power-breakdown.csv) separately derives pan heating and coil copper heating from the same waveform. Pan heating is a model component, not a cooking-efficiency measurement.
- **Current ceilings:** 42 A is provisional on **actual peak** tank current. The 40.45 A alternative is 20% below the lowest 50.56 A static CT trip, a stand-in for command margin. Neither is a firmware setpoint. No unmeasured control/sensing error or transient allowance was invented.
- **Search:** a round-3 point was first retained when it met the ceiling. Otherwise, frequency was raised only on the inductive side and never past 60 kHz. Bisection held a current-safe upper-frequency bracket and accepted a peak within 0.2 A below the ceiling. A 25 ns check found seven few-milliamp crossings; these and 37 further cases within 0.05 A of the ceiling were re-solved with a nominal 0.10–0.17 A guard. Previous raw runs remain under `outputs/runs/superseded-numerical/`. The one newly derated round-3 point had a marginal refined peak despite passing the original 50 ns screen.
- **R5 and events:** in this ideal diagonal-drive mode, the signed R5 waveform is `sign(v(drv)) × i_tank`, so time-weighted R5 RMS equals tank RMS. Finite-dead-time waveform changes and phase-shift zero states are outside this model. [switching-events.csv](outputs/switching-events.csv) has **190,336** ideal full-bridge drive crossings, keyed by `(ceiling_a, run_id, event_index)`; [event-schema.json](outputs/event-schema.json) defines the signed current, bus, capacitor and ±500 ns fields. The post-crossing samples follow immediate ideal-drive reversal and cannot establish physical current persistence through a floating dead time. A qualified ZVS threshold is still absent.
- **Part shares:** C21/C22/C23 nominal current shares use 0.22/0.22/0.10 µF of the 0.54 µF bank. Static CT and R5 trip ranges come from the pinned round-3 A3 threshold source. Those static thresholds do not include detection and gate-off latency.

## Results

The full [derated_cases.csv](outputs/derated_cases.csv) contains every case's ceiling, status, frequency, tank current RMS and peak, capacitor voltage RMS and peak, capacitor current shares and total resistive power. [delivered-power.csv](outputs/delivered-power.csv) gives min/mean/max across three L/R corners for every pan, line voltage, request and ceiling. For the 1,710 W request, the table below gives the **mean of the three corners** in watts: total pan-plus-coil dissipation, followed by pan heating in parentheses.

| Pan class | Line V RMS | 42 A: total (pan) W | 40.45 A: total (pan) W |
| --- | ---: | ---: | ---: |
| Cast iron | 108 | 1432 (1309) | 1338 (1224) |
| Cast iron | 120 | 1430 (1310) | 1341 (1228) |
| Cast iron | 140 | 1418 (1301) | 1327 (1218) |
| Carbon / 430 steel | 108 | 1181 (1061) | 1092 (981) |
| Carbon / 430 steel | 120 | 1170 (1052) | 1084 (975) |
| Carbon / 430 steel | 140 | 1148 (1035) | 1056 (953) |
| Tri-ply clad **guess** | 108 | 832 (718) | 769 (664) |
| Tri-ply clad **guess** | 120 | 821 (710) | 757 (656) |
| Tri-ply clad **guess** | 140 | 801 (696) | 738 (642) |
| Low-R Silargan-like | 108 | 851 (737) | 788 (683) |
| Low-R Silargan-like | 120 | 840 (730) | 773 (672) |
| Low-R Silargan-like | 140 | 816 (712) | 753 (657) |
| Offset / small pan | 108 | 556 (448) | 513 (415) |
| Offset / small pan | 120 | 548 (443) | 505 (409) |
| Offset / small pan | 140 | 536 (436) | 495 (404) |

| Evaluated maximum | 42 A | 40.45 A | Evidence |
| --- | ---: | ---: | --- |
| Tank line RMS / 12.5 ns peak | 21.667 / 41.952 A | 21.002 / 40.408 A | `derated_cases.csv`, `quarterstep-checks.json` |
| Tank-capacitor voltage peak / RMS (50 ns) | 408.280 / 201.523 V | 392.319 / 193.797 V | `derated_cases.csv` |
| C21 or C22 nominal line RMS share | 8.827 A each | 8.556 A each | `derated_cases.csv` |
| R5 line / ≥90%-line-crest RMS | 21.667 / 29.648 A | 21.001 / 28.728 A | [shunt-grid.csv](outputs/shunt-grid.csv) |
| Frequency range | 31.598–57.647 kHz | 31.903–57.647 kHz | `derated_cases.csv` |

The 12.5 ns capacitor-voltage peak extrema are 408.332 V and 392.371 V, respectively; the table retains the nominal-step values recorded in `derated_cases.csv`.

The capacitor current and hot voltage ratings for these exact CDE parts remain unresolved as in round 3. The 100 kHz, 70 °C catalogue current rating cannot be applied as a pass/fail limit to this 31.6–57.6 kHz grid. The maximum capacitor bank voltage is much lower than the unconstrained round-3 822.297 V result, but this does not close hot capacitor acceptance.

[trip-band-screen.csv](outputs/trip-band-screen.csv) and [trip-band-summary.json](outputs/trip-band-summary.json) classify each accepted peak against the CT **50.558–60.014 A** and R5 **38.438–85.551 A** static trip bands. All 135 cases per ceiling are below the CT band; 73 per ceiling lie inside the R5 band, never above its upper edge. At 42 A the R5-band count is 10 retained + 63 derated; at 40.45 A it is 4 retained + 69 derated. This supports keeping the resistor-only backup-shunt retune on hold until dynamic fault timing and hardware current waveforms are known.

## Numerical checks and sensitivity

The kit [smoke-test.txt](outputs/smoke-test.txt) ends `SMOKE PASS`; the round-3 [raw-verification.txt](outputs/raw-verification.txt) reports `3327/3327 files verified`. Every saved case has a SHA-256 input fingerprint binding its baseline row, ceiling, frequency, deck, options, vendor model and ngspice version. Cache reuse checks the saved resolved deck, parameter file, result and accepted waveform archive. Two independent final `.meas` replays matched exactly. [replay_frozen.py](scripts/replay_frozen.py) also reproduced one corrected and one retained case, including every event and its R5 integrals; the exact source frequencies in `derated_cases.csv` permit full replay.

The full 50-to-25 ns pass changed reported current peaks by at most **0.0895%** and capacitor peaks by at most **0.0229%**. The 12.5 ns pass covered all cases within 0.18 A of their ceiling at 25 ns, plus peak current, capacitor voltage/RMS and tank RMS extrema; its maximum current-peak change was **0.0197%**. The smallest 12.5 ns margin is 0.04210 A. These checks establish the stated numerical results of this model, not the unknown controller/transient allowance. The 42 → 40.45 A choice lowers mean total 1,710 W-request power at 140 V from 536 to 495 W for offset/small pans, and from 1418 to 1327 W for cast iron; pan heating is lower still.

## Open items and physical confirmation

A controller command must be below the actual-current ceiling by measured CT/sense error, control overshoot and a transient allowance. The low R5 static trip at 38.438 A may interrupt nominally accepted cases; dynamic detection and gate-off timing cannot be inferred from this grid. The qualified board ZVS threshold and exact hot CDE current/voltage limits also remain open. Physical confirmation requires tank current and capacitor voltage waveforms for representative pans, line voltages and commanded powers at bring-up, including R5 current, trip behavior and actual coil/pan parameter measurement. No hardware or firmware change is proposed here.

**Master-plan §5 status line:** 05 Round 4 A — **model grid complete / hardware command limit blocked**: 270 current-ceiling solves, per-case R5 and switching-event evidence, trip screen and numerical refinements completed; sensing/control allowance, dynamic shunt behavior, exact hot capacitor rating and physical pan waveforms remain open.

## Reproduce

All paths below start from `zapote/power-stage-120v/`. Restore the round-3 raw evidence first if needed. The copied kit deck, round-3 case CSV, vendor model and threshold source hashes are in `outputs/input-provenance.json`; final C2 file hashes are in [frozen-hashes.json](outputs/frozen-hashes.json). The per-case raw runs are gitignored under `outputs/runs/`, including gzip-compressed ngspice waveforms; no vendor-model copies are retained there.

```sh
python3 validation-results/round3-coordination/raw-evidence/verify.py validation-results
(cd validation-plan/sim-kit && PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 smoke_test.py)
cd validation-results/05-resonant-tank-envelope/round4/a-derated
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/find_freq.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/check_numerics.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/refine_ceiling.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/find_freq.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/check_numerics.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/check_quarterstep.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/power_tables.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 scripts/trip_screen.py
```

The recorded correction history has an initial seven-case ceiling-crossing pass and a later 37-case numerical-margin pass. A fresh single correction pass can choose slightly different safe frequencies within the allowed band. For byte-exact independent verification of every reported value at the saved frequencies, run `scripts/replay_frozen.py` with no filter; `--case` and `--ceiling` select one case. The final [derated_cases.csv](outputs/derated_cases.csv) records the exact frequencies. Two targeted event/R5 replays are logged in `outputs/replay-corrected.txt` and `outputs/replay-retained.txt`. The full run's raw ngspice logs, parameters, source deck and waveform archives remain under `outputs/runs/`.

Post-review replay guards pin the original refinement decks, options, runner, model and ngspice version before cache reuse. New raw-wave gzip files are verified and atomically installed before the case completion marker; cached gzip streams are checked through EOF/CRC. Pre-guard source snapshots remain under ignored `outputs/runs/source-before-review/`; the original numerical results and producer provenance are unchanged.
