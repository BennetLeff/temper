# PROCEDURE: jet bench day

The rig is built and checked per RIG.md §6. Times are wall-clock estimates. One logger serves this bench and the
sensor-r3 survey:
- flash `jet_logger_fw.ino` for this day and the sensor firmware for the survey;
- move the MAX31865 between the hood Pt100 and the sensor probe.

The two benches can share an order and a bench week, but not the logger at the same time.

## A. Bring-up (30 min, once)

1. Flash `logger_fw/jet_logger_fw.ino` (Arduino core 2.x or 3.x for ESP32, "USB CDC On Boot: Enabled"). **It was not
   compiled in the session that wrote it.** Fix any compile error first.
2. `python3 jet_logger.py --port <port> --run bringup --condition zero --no-guard --minutes 2`. The start line should
   read `ina=1, sdp=1`, and every thermocouple, the Pt100, V, I and dp should print with no `SR=0x..` faults.
3. Guard loop check: plate heater at 2 W, blower on, guard on (default), 15 min. `Tg-Tp` should settle within ±0.1 K.
   `logger-selftest.json` shows the loop settling in 329 s on a model plant. If it rings, halve `kp_W_per_K` in
   `bench.json`.

## B. Calibrations (30 min, once)

1. **INA226 against the DMM.**
   - At about 0.4 A, put the DMM in series to read current and compare it with `i_A`. Read the DMM across the
     resistor terminals and compare with `v_bus_V − i_A × r_lead`.
   - Set `ina226.i_gain` and `v_gain` in `bench.json` so they agree. Enter the measured `r_lead_ohm` (RIG §5).
2. **SDP810 zero.** With the blower off and the tubes connected, average `dp_Pa` over 2 min and enter it as
   `dp_zero_Pa`.
3. **Plate heat capacity.** Enter `plate.C_J_K` from the weighing (RIG §3.4).

## C. Zero: the night before the bench day

1. Heaters off, blower off. Cover the rig and hood with a cardboard box to stop drafts.
2. `python3 jet_logger.py --port <port> --run zero --condition zero --no-guard --minutes 600`
3. `python3 fit.py zero runs/zero.csv` writes `tc_offsets_K` into `bench.json`, referenced to the Pt100.

It accepts the run only if it lasted ≥ 90 min and the Pt100 drifted ≤ 0.1 K/h over the last hour. That limit keeps
the slowest mass's lag below about 0.03 K (the plate's still-air τ is 975 s, `plate-design.json`). If it refuses,
repeat on a quieter night.

**Why not a zero with the blower on:** the blower heats its own air by up to about 1 K, so the rig is not isothermal
then (DECISIONS J10).

## D. Bench day: jet runs (about 7 h attended)

**Before the first run:** blower on, guard on. Tape bleed holes on the hood lid and trim the blower volts until `dp`
sits on the target below, within ±2 % (±0.2 Pa at the floor). Re-trim at every set-point change.

**Manifold pressure targets** (`setpoints.json` → `rig_dp_Pa_by_room_C`, Re-matched to the product). Use the column
nearest your room temperature, or interpolate.

| Drive (volts, product) | Product jet Δp (Pa) | Rig Δp at 21 °C | 24 °C | 27 °C |
|---|---|---|---|---|
| 0.458 floor (5.5 V) | 15.10 | 10.83 | 11.10 | 11.37 |
| 0.5 (6.0 V) | 17.63 | 12.64 | 12.96 | 13.27 |
| **0.55 (6.6 V)** | 20.96 | 15.03 | **15.40** | 15.78 |
| 0.6 (7.2 V) | 24.38 | 17.48 | 17.92 | 18.36 |
| 0.7 (8.4 V) | 32.23 | 23.11 | 23.69 | 24.27 |
| 0.8 (9.6 V) | 40.93 | 29.35 | 30.08 | 30.82 |
| 1.0 full (12 V) | 61.59 | 44.16 | 45.26 | 46.37 |

**Plate power.** Aim for a plate rise of 20–30 K over the jet air. P ≈ h × 1.485e-3 × 25 W: about 3.7 W at h 100 and
8.9 W at h 240 (`plate-design.json` → heater rows, all inside the INA226's 0.82 A).
- Start the first run at 4.5 W. The logger prints a live `h~`; rescale P for later runs if the rise leaves 15–35 K.
- Never let the plate exceed 60 °C.

**Steady state.** Each run ends with fit.py's test: over the last 5 min, `|d(dT)/dt| ≤ 0.02 K/min` and the guard
null within 0.1 K. At h 100 the plate τ is 98 s (`plate-design.json`), so 25 min is ample. Change only dp between runs where you can.

Command per run:

```
python3 jet_logger.py --port <port> --run <id> --condition <cond> --minutes <min> [--guard-offset K] [--H-mm H] [--flow-slpm F]
```

| # | Run id | Condition | Set-point | Min | Notes |
|---|---|---|---|---|---|
| 1 | `d055_r1` | d055 | 0.55 | 25 | First steady point |
| 2 | `gap_p3` | gap | 0.55 | 30 | `--guard-offset 3` (guard 3 K hotter) |
| 3 | `gap_p6` | gap | 0.55 | 30 | `--guard-offset 6`; then `python3 fit.py gap runs/d055_r1.csv runs/gap_p3.csv runs/gap_p6.csv` writes G_gap |
| 4 | `floor_r1` | floor | 0.458 | 25 | |
| 5–8 | `sweep_0p5`, `sweep_0p6`, `sweep_0p7`, `sweep_0p8` | sweep | 0.5–0.8 | 25 each | Nu(dp) shape between the named drives |
| 9 | `full_r1` | full | 1.0 | 20 | |
| | | | | | **Re-seat:** lift the duct off, refit it, re-gauge H = 6.0. The repeats then include mounting scatter. |
| 10 | `floor_r2` | floor | 0.458 | 25 | |
| 11 | `d055_r2` | d055 | 0.55 | 25 | |
| 12 | `full_r2` | full | 1.0 | 20 | |
| 13 | `d055_r3` | d055 | 0.55 | 25 | Third repeat at the decision drive |
| 14 | `height_5p5` | height | 0.55 | 25 | Shim to H 5.5 (Ø5.5 shank go, Ø5.6 no-go); `--H-mm 5.5` |
| 15 | `height_6p5` | height | 0.55 | 25 | H 6.5; `--H-mm 6.5`. Gives d ln h / dH, so R45's ±0.5 mm production tolerance can be judged. Reset to 6.0 afterwards. |
| 16 | `transient_d055` | transient | 0.55 | 30 | At about 15 min, steady, press BOOT and raise the supply volts × 1.22 (P × 1.5) |
| 17 | `flowcal_*` (optional) | flowcal | 0.458 / 0.55 / 1.0 | 5 each | Flow meter in line between the hood box and leg A, heaters off, `--flow-slpm <reading>`. Then remove the meter. |

**Optional bumps run.** Glue 1 mm aluminium dummies on the plate at the 2512 / SOD-128 positions in
`../cad/channel-parts.json` and rerun `d055`. The 2512 parts are about 0.6 mm tall and the SOD-128 about 1.0 mm
(datasheet package heights, not computed here). This bounds the smooth-plate assumption (DECISIONS J9).

## E. Evening: still air (3 h, unattended with the cut-outs in place)

1. Blower off, bleed holes open, guard on, plate at 0.2 W.
2. `--run still_r1 --condition still --minutes 180`
3. The plate τ in still air is 975 s (`plate-design.json`), and with the guard loop the approach is slower still
   (the self-test's 45 min run had to be extrapolated; its 180 min run settled). Do not cut it short.

## F. Report

`python3 fit.py report runs/` prints every run, the still-air h, the product h at each drive with 95 % bounds, the
PASS / MARGINAL / FAIL table for the four board-h-sweep cases, the ceiling the lower bound supports, and flags. It
writes `results.json`.

`python3 fit.py transient runs/transient_d055.csv` gives the power-meter-independent cross-check. The self-test puts
it within 4 % of the steady h, low by about the prior on C (`selftest.json`).

Send `results.json` and the printed verdict to the power-stage session.

## Safety

- **Low voltage only:** ≤ 30 V DC and 12 V, no mains on the rig.
- **Plate heater:** supply current limit 0.8 A. Each heater has a KSD9700 70 °C cut-out in series, because XPS
  softens at about 75 °C. Keep the plate ≤ 60 °C.
- **Guard:** the PWM drops to 0 if the host is silent for 5 s (firmware).
- **Blower:** keep fingers and loose wires clear of the inlet.
- **Unattended still-air run:** leave it only with both cut-outs fitted and the supply current-limited.
