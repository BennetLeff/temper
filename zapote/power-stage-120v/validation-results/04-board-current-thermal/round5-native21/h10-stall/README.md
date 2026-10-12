# Blower stall at the 28 A ceiling, h 10: does the derate own it?

Question (DECISIONS item 14, "Still open"): at h 10 W/m²K (blower failed) the FET-row copper is 198 °C at 28 A steady
state, and "the blower stall detection and derate own this". Show whether that is true.

## Pass criterion (written before any result was computed)

Verdict is PASS only if every line holds; otherwise FAIL (INCONCLUSIVE if an input needed for a line is missing).

| id | Quantity | Limit | Source of the limit |
|---|---|---|---|
| L1 | FET junction, worst FET, at every time from the blower stop to the tank switch-off, at the conservative corner of the lumped bound | ≤ 150 °C | IPW65R018CFD7 Tj max (trip-ladder doc `docs/evidence/2026-10-12-thermal-trip-ladder-l3.md`). The 125 °C design target is reported, not gated: the committed basis-A loss already puts the worst FET above it at 28 A before any failure (see Results). |
| L2 | True sink temperature when the C28 mechanism alone (stall derate, then 0 % on a 2 K sink rise) has switched the tank off | ≤ 104.6 °C (hardware sink trip, high corner) | DECISIONS items 14-16, `thermal_mgmt.h` `THERMAL_HW_SINK_TRIP_HIGH_C` |
| L3 | Board copper and pad cells (all layers), at every time in the window, finite-volume transient with adiabatic air side | ≤ 150 °C | NP-155F laminate Tg 150 °C, `native-17/stackup.json` |
| L4 | Derated steady state at h 10, committed `b3/thermal.py`: board peak and FET-row copper | ≤ 150 °C | same |

Also reported, not gated, because the accepted 28 A h 25 baseline already exceeds them: 105 °C (stage-15 B3 gate, replaced
by a relative gate), 130 °C (FR-4 class that gate was 25 K under), 134.1 °C (the accepted 28 A h 25 peak).
Why 150 and not 105/130: the model's own accepted baseline (U26 pad cell, 133.9 °C at h 25) is over both, so they cannot
separate "the failure made it worse" from "the model's hot spots". Tg is the lowest absolute board limit the baseline meets.

Window definition for L3 (fixed before the final run, see "Revision note"): from the blower stop to the tank switch-off, taken as
the longest switch-off time over every lumped-bound run in which the C28 path acts (conservative corner, central estimate and the
36-run sensitivity set). The derate is taken as working (that is the mechanism under test); "cap never applies" is reported as a
sensitivity, not gated.

## Method

1. **Firmware timeline** (`firmware/components/control/thermal_mgmt.[ch]`, `main/thermal_io.c`, `main/state_handlers.c`):
   - Tach: rpm from a 250 ms gate (`BLOWER_TACH_WINDOW_MS`); stall when rpm < 300 for more than 1000 ms while driven; blower tick 100 ms.
     Worst-case detection = 0.25 + 1.0 + 2 × 0.1 = **1.45 s** after the blower stops.
   - **The cap is on tank power, not current**: `BLOWER_STALL_POWER_CAP_PCT = 25` is a percentage of the tank power *request*
     (`apply_thermal_caps()` in `state_handlers.c` takes `min(requested, limit)` on a `uint8_t` percent). Nothing in the committed
     firmware turns it into amperes. This study assumes tank power ∝ I² at fixed reflected resistance, so 25 % of the request at
     the 28 A point is **28 × √0.25 = 14 A**. The 7 A reading (cap as a current fraction) and caps of 5/10/15 % are also run.
   - The cap takes effect `APPLY_S` = 0.5 s after detection (**assumed**; the power-loop response is not in the committed firmware):
     derate in force at 1.95 s.
   - Then 0 % once the sink NTC reading exceeds its value at stall detection by more than 2 K (`BLOWER_STALL_RISE_K`), again 0.5 s to take effect.
     Backstops: firmware sink trip 95 °C on the NTC reading, hardware sink trip 98.3 / 101.4 / 104.6 °C (low / nominal / high corner) on the true sink.
2. **(a) Steady state**: the committed `b3/thermal.py` and `b3/run_study.py` `cases()` at tank current 1.05 × the derated ceiling (the
   stage-15 convention that the sustained current is the 1.05 × ceiling firmware RMS trip), 1.0 mm pitch, h 10. The tank-current rows of the
   c28 heat file (R5, R39, the five bank capacitors, C5, C6) are scaled by (I/29.4)²; every other part row and the line current (11.1 A)
   stay at the c28 values, which is conservative at reduced power. Controls: the same call at 28 A reproduces the committed h 25 and h 10 peaks.
3. **(b) Lumped sink and junction bound** (`b_sink_junction`):
   - Sink S8 (`validation-results/08-manufacturing-package/native-21/owner-items/m11/SINK-DRAWING-NOTES.md`: 6063, 8 mm base, 15 × 1.5 mm fins,
     40 mm deep, 67.5 × 117 mm envelope). Heat capacity: **base only 153.5 J/K** (conservative bound: the fins are ignored, which maximises the
     heating rate) and whole sink 409.4 J/K (central). ρ 2700 kg/m³, c 900 J/kg·K are handbook values, not in the repo.
   - Sink loss and junction rise from the committed round-6 table `05-resonant-tank-envelope/round6-full-power/outputs/board-side-fets.csv`
     (basis A, 120 V, worst FET Q2): the sink load at 28 A is 132.8 W at 40 kHz and Tj − T_sink = Tj − (50 + 0.3061 × P_sink) with
     R_SA 0.29 + 0.0161 pedestal from `scripts/board_side.py`. The sink starts at the csv's own steady state (90.65 °C at 28 A, 40 kHz).
   - Direction chosen to be conservative: airflow zero from t = 0 (the real blower coasts down); **no heat loss from the sink** (G = 0); minimum
     heat capacity; FET stack and tile capacity ignored (Tj follows the sink with its steady offset); NTC lag τ = 7 s (the committed GT-2 figure,
     applied to the sink NTC, whose own lag is not committed), which delays the 2 K rise detection; the power during the derated phase is the
     **value at the lowest committed current (22 A)**, which is an upper bound because loss increases with current. The central runs add a
     still-air sink conductance (forced-air R_SA scaled by h10/h25, **assumed**), the quadratic fit of the csv at the derated current, and the whole-sink capacity.
   - What it bounds: the true sink temperature and the worst FET junction from the blower stop to the tank switch-off. It does not bound the
     blocked-inlet case with a turning blower (the tach does not see that) or any case after the tank is off.
4. **(b) Board transient** (`b_board_transient`): the committed `thermal.py` conductance matrix (copied, matrix checked against `thermal.py`'s
   steady solution to 7e-8 K) with node heat capacities added from the committed stack-up thicknesses (copper ρc 3.45 MJ/m³K, FR-4 2.04 MJ/m³K, handbook values),
   implicit Euler. Start: the 28 A h 25 steady field. **The air side is adiabatic during the window** (h = 0, a bound), heat = 28 A until
   1.95 s, the derated field until the switch-off, then the tank-stopped field with h 10 for 900 s. No component, solder or mask heat capacity is counted.

## Results

(All numbers from `results.json`; the script asserts the controls.)

**Controls.** 28 A, h 25: 133.92 °C (committed `b3/outputs/ceiling_sweep.json` 133.92; README stage 15b quoted 134.1 for the earlier board, a 0.18 K
difference), at U26 (109.5, 77.5). 28 A, h 10: 198.11 °C (item 14: 198) at (50.5, 4.5) In1.Cu in the FET row.

**(a) Steady state at h 10** (tank RMS used = 1.05 × the ceiling in the first column):

| Tank ceiling after the stall response | Board peak | Where | FET-row copper (x 0-80, y 0-12.5) | vs L4 (150 °C) |
|---|---|---|---|---|
| 28 A (no response) | 198.1 | R5 / FET row, In1.Cu | 198.1 | over |
| 21 A | 164.0 | U42 pad cell | 136.7 | over |
| **14 A (cap 25 % of power, assumed I ∝ √P)** | **152.6** | U42 pad cell (14.5, 56.5) F.Cu | **92.8** | **over by 2.6 K** |
| 10.8 A (15 %) | 149.4 | U26 pad cell | 80.0 | under |
| 8.9 A (10 %) | 149.1 | PS2 pad cell | 73.9 | under |
| 7 A (25 % read as a current fraction) | 148.9 | PS2 pad cell | 70.0 | under |
| 0 A (tank stopped, the C28 end state) | 148.7 | PS2 pad cell (209.5, 17.5) | 65.1 | under by 1.3 K |

For reference, 14 A at h 25 is 132.5 °C.
The derate does what item 14 asks of it for the FET row: 198 °C becomes 92.8 °C (65.1 °C once stopped). The remaining board peak at h 10 is **not
the tank**: with the tank at 0 A it is 148.7 °C and the 14 A hold adds 3.8 K to it. Those cells are the bias and supply parts that run whatever
the tank does (RECOM module U42, Mean Well PS2, the U26 LDO, heat file rows held at the c28 values), which is the nominal-h 10 hot-spot picture
already in this README (stage 14-16, 163 / 133 °C nominal at h 10 / h 25 at 21.5 A).

**(b) Sink and junction, lumped bound** (40 kHz basis A):

| Run | Tank switched off at | True sink peak | Worst-FET Tj peak |
|---|---|---|---|
| Start, 28 A, h 25 (before the failure) | | 90.65 | 129.0 (already over the 125 °C target on basis A) |
| Conservative corner (base-only C, G = 0, τ 7 s, P at 22 A bound), C28 rise stop | 7.8 s | 96.5 | **130.7** (at the derate instant 1.95 s; 126.8 after) |
| Central (whole sink, still-air G, fit), C28 rise stop | 23.2 s | 93.0 | 129.4 |
| Hardware backstop only, high corner, no C28 and no firmware trip | 19.2 s | 104.66 | 134.9 |
| 36-run sensitivity (40/45/50 kHz × C × τ 0/7/15 × P bound/fit), all protections | 0.5-19.6 s | max 98.5 | max 140.6 (50 kHz starts at 95.9 °C and trips the 95 °C firmware limit at once) |

The true sink stays below the 98.3 °C low corner of the hardware trip in the conservative C28-only run, so the 2 K rule, not the hardware
trip, ends the window; and Tj stays below 150 °C in every run.

**(b) Board transient** (adiabatic window, derate in force; start = 28 A h 25 field, whose peak is the U26 pad cell at 133.9 °C):

| Window | Board peak (derate in force) | Board peak if the cap never applies | FET-row copper peak (derate in force) |
|---|---|---|---|
| 7.8 s (conservative-corner switch-off) | 140.2 | 141.0 | 134.8 |
| **23.2 s (longest C28-path switch-off)** | **147.5** | 154.2 (not gated) | 134.8 |
| 19.2 s (hardware-backstop-only window) | 145.7 | 150.8 | 134.8 |

After the window, with the tank stopped and h 10, the board peak goes through 152.4 °C at about 100 s (heat stored in the adiabatic window; outside L3) and settles to
148.7 °C at 900 s. The window's rise is dominated by the tank-independent pad cells (U26 climbs from 133.9 °C because the adiabatic bound removes its convection), not by the FET row.

### Verdict against the pre-written criterion: **FAIL**

| id | Result | Limit | |
|---|---|---|---|
| L1 | 140.6 °C worst case over all lumped runs (130.7 at the conservative corner) | 150 | pass |
| L2 | 96.5 °C | 104.6 | pass |
| L3 | 147.5 °C (23.2 s window, derate in force) | 150 | pass, 2.5 K margin; 154.2 if the cap does not take effect |
| L4 | board peak 152.6 °C at the 14 A derated hold (FET row 92.8 °C) | 150 | **fail by 2.6 K** |

Also exceeded in every row above (reported, not gated): 105, 130 and 134.1 °C, because the accepted 28 A h 25 baseline already is.

**Reading.** Item 14's statement is true for what it names: the stall response removes the 198 °C FET-row copper (to 92.8 °C at the 25 % hold,
65 °C stopped), keeps Tj at or below 130.7 °C at the conservative corner (140.6 °C at the worst sensitivity corner) and the true sink at or below 96.5 °C. It is not true that the
board is then below the limit at h 10: a persistent 25 % hold leaves the U42 pad cell at 152.6 °C, 2.6 K over the pre-written 150 °C, and even a fully stopped tank leaves
the board at 148.7 °C with 1.3 K of margin. That residual is the idle h 10 board (bias modules and supplies), not the 28 A stall; this study cannot remove it.
The 25 % hold is also not a state the unit can stay in: in still air the sink rises by more than 2 K within about 8-23 s (the bound and central runs), after which the C28 rule stops the tank.

## Recommendation (proposal only; no board or firmware edits made)

1. Keep the stall detection and the 0 % stop; they own the FET row and the junction.
2. Lower `BLOWER_STALL_POWER_CAP_PCT` from 25 to **15 % or less** (or go straight to 0 %): at 15 % the h 10 board peak is 149.4 °C (under L4), at 25 % it is 152.6 °C. The hold buys only the 8-23 s before the 2 K rule stops the tank anyway.
3. The 148.7 °C idle h 10 board is a separate item (blower failed with the fan law off, covered elsewhere): the U42 / PS2 / U26 pad cells need the bench IR at h 10, or a firmware step that
   removes standing bias loss once the tank is stopped on a blower failure (to be modelled; not evaluated here).
4. State in the firmware requirement that the cap is a percentage of the tank power request and give its ampere equivalent; today nothing in the committed firmware converts it.
5. Reconcile the trip-ladder doc (Tj ≈ T_sink + 27.8 K at 28 A) with the round-6 csv this study uses (38.35 K for the worst FET, 40 kHz basis A): at the 95 °C firmware trip that is 133 °C, not 123 °C, still under 150 °C.

## Inputs (commit `3b515aade`, branch `an/h10-stall`)

- `b3/thermal.py`, `b3/run_study.py`, `b3/inputs/native21-board-heat-sources-c28.json`, `native-21/verification/native21s16-all-copper.json.gz`, A4 cases `../outputs/*.json` and `*-heat.npz`.
- `firmware/components/control/thermal_mgmt.[ch]`, `firmware/main/thermal_io.c`, `firmware/main/state_handlers.c`, `firmware/components/power/COMMISSIONING.md` step 8b.
- `docs/evidence/2026-10-12-thermal-trip-ladder-l3.md`, `zapote/power-stage-120v/DECISIONS.md` items 14-16, `native-17/stackup.json`.
- `validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-fets.csv`, `scripts/board_side.py`; `08-manufacturing-package/native-21/owner-items/m11/SINK-DRAWING-NOTES.md`.

## Rerun

```
cd zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/h10-stall && python3 h10_stall.py
```

About 4 minutes. It needs numpy, scipy, shapely and matplotlib, and the gitignored A4 heat arrays `../outputs/*-heat.npz` (written by `../run_cases.py`; here copied from a worktree
at the same commit whose committed A4 json files are byte-identical). It rewrites `results.json` and asserts the controls.

## Limitations

- Pad-cell temperatures are 1.0 mm model cells with point-deposited part heat, not package or junction temperatures; the stage-15b section of `../README.md` shows the h 25 FET-row figure moving from 136.6 to 126.9 / 128.6 °C between the 1.0 and 0.5 / 0.25 mm meshes.
  The 2.6 K L4 exceedance is inside that uncertainty in either direction.
- Cap-to-current mapping (I ∝ √P), the 0.5 s apply time, the sink NTC lag, the still-air sink conductance and the handbook heat capacities are assumptions, listed in `results.json` under `assumptions`.
- Airflow loss is instantaneous and total in the bounds; a real coast-down helps. Not covered: a blocked inlet with a turning blower, a blower that fails while the fan law has it off, a failure at another frequency or load.
- Tj uses the round-6 basis A (conservative switching proxy). On the ZVS basis B the same FET sits near 82 °C at 28 A.
- Tank-independent part heat is held at the c28 values when the tank is stopped (conservative), and the line current is held at 11.1 A.
- No hardware was measured. This is simulation and a lumped model.

## Revision note

The first full run gated L3 on the longest window of any scenario, including one where the C28 path was disabled and only the 104.6 °C hardware trip acts. L3 then read 151.0 °C
in the never-derating variant. The window was redefined (above) before the final run to the longest window in which the C28 path acts, with the derate working; the
hardware-backstop-only window and the never-applies variant are reported in `results.json` and above instead of being gated. The gated L3 number moved from a failure artefact of that
scenario choice to 147.5 °C; L4 (the verdict) did not change.
