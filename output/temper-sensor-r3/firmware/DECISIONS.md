# sensor-r3 C1 firmware: decisions

Scope: HANDOFF.md section C. Every number below is written by a script in this
folder; `run.sh` reruns all of them. The file each number comes from is in
brackets.

## D-PATH. This folder is `firmware/`, not `firmware-sim/`

The caller asked for harness, results and decisions in
`output/temper-sensor-r3/firmware/`. HANDOFF section C names `firmware-sim/`.
Nothing else differs. The co-sim, exporter, runner and results are all here.

## D-K. Cartridge constants: the HANDOFF values, in one calibratable struct

`pte_params_t` holds C_cap 40.4 mJ/K, C_el 8.175 mJ/K, G_bond 0.0612 W/K,
G_leak 0.8 mW/K, area 45.4 mm² and h_nom 1300 W/m²K, as the HANDOFF lists them.
The truth plant uses the r3 cartridge (C_cap 39.7 mJ/K). The 2 % mismatch
stays in deliberately, so the bars are passed with a model error.

The CAD agent's as-built budget gives C_cap 39.18 mJ/K by the budget method and
45.39 mJ/K by the effusivity estimate. It gives a cold leak of 0.319 to
0.388 mW/K (`../cad/budget-asbuilt.json`). C_el, G_bond and the area agree.
The firmware's 40.4 sits inside the C_cap band, and the 0.8 mW/K leak is the
budget ceiling. Both are bench-T3 calibration items. I changed no constants.

## D-KF. Float filter with double-precision precompute

F and the input gains for 5 Euler substeps are composed once in double, at
init. The 10 Hz step is single-precision float. The filter tracks the Python
double reference, worst max |C − Py| 0.00009 K on the five golden vectors, bar
0.05 K (`test_pan_temp_estimator_only` output). In the loop the shadow-KF
difference is ≤ 3.9e-5 K rms and ≤ 1.5e-4 K max (`cosim-results.json`
shadow_parity).

## D-ID. Plant gain: the effective heat-up gain, measured or estimated power

- **Method.** Scalar RLS on 1 s blocks over a 20-block window:
  ΔT̂ = a·ΔE.
  - Prior a0 = 1.8e-3 K/J (the lightest modelled pan, so the least power per
    K/s); clamps 5e-5 to 5e-3.
  - No forgetting in the first heat-up. Later setpoint steps use a
    hold-to-hold energy balance instead (D-ID2).
  - Updates start after a 10 K rise. The estimate is used only after a 20 K
    rise and 30 kJ of regressed energy.
- **Gate.** Identification runs only while all of these hold:
  - the identification phase is open;
  - T̂ < SP − 2 K;
  - the setpoint is ramping or the power is saturated;
  - D1 is NORMAL and no sensor fault is latched.
  Any D1 event closes the phase. A later setpoint step of ≥ 5 K re-arms it only
  if the loop had settled at the previous setpoint. Without that condition a
  food drop re-opened the phase and corrupted a.
- **No loss term (k_loss = 0).** With the loss regressor
  ΔT = a(ΔE − k_loss·ΔS), a comes out high:
  - k_loss 1 W/K gives a/a_true 1.024 to 1.218;
  - k_loss 2 W/K gives 1.048 to 1.339, which is outside ±30 %;
  - k_loss 0 gives 0.88 to 1.115 (`sensitivity.json`, `cosim-results.json`).

  The effective heat-up gain is what the rate loop needs, because P = rate/a
  is commanded under the same losses.
- **Tolerance.** With a fixed at a_true × {0.5, 0.7, 1.4, 2.0}, B2/B3 pass at
  0.7 and 1.4 (`sensitivity.json`). At 0.5, B2 fails in 4/16 cases (overshoot
  7.61 K). At 2.0, B3 fails in 5/16 cases, and the slowest case takes 396 s to
  reach SP − 2 K. The ±30 % bar is therefore the right one.
- **Power provenance** (`pg_power_source_t`), per coil-driver-r1
  RECOMMENDATIONS items 2 and 6:
  - every sample is tagged MEASURED (bus/coil sense) or ESTIMATED (from the
    command);
  - a regression window never mixes sources: a source change flushes the
    window;
  - `src_mask` reports which sources built the estimate.

  In co-sim mode id_estimated the coil really delivers
  P_cmd·(1.10 − 0.20·P/P_max), and that error is absorbed into a. Pan
  detection was not implemented, as instructed.

## D-PID. Rate PID as frozen in r2, with a bumpless start

KP 0.1/s, KI 0.002/s², KD 1.0, integration within 10 K, a 1 K/s setpoint ramp,
P = rate/a clamped to 0–1800 W. The ramp starts from the first T̂, not from
ambient. That makes the start bumpless when a hot pan is placed.

## D-D1. Contact check: screen.py's D1 plus three firmware rules

D1 has the trigger, the probe, the regression on [1, t, t², E_lag], the 25 %
coefficient rule, the free-decay fit, retry every 20 s and the 30 s hold-off,
all exactly as in screen.py. The constants are in `cc_params_t`.

- **Implementation.**
  - Integer ticks.
  - A fixed 184-sample ring, with no heap.
  - Regressions in double: the normal equations are ill-conditioned in float.

  In screen mode the C code reproduces screen.py's suspect and lost samples
  exactly on every exported vector (`test_contact_check_only`).
- **Firmware additions**, each with its own parameter so screen mode can be
  restored:
  - **D-D1a.** A probe from NORMAL concludes LOST only if the fitted free decay
    changes by ≥ 1 K.
  - **D-D1b.** A retry restores contact only if the reading departs from the
    free decay (rms > 0.5 K).
  - **D-D1c.** The probe response must be ≥ 3 standard errors.
- **Why.** Over 20 seeds per case, measured power (`b5-montecarlo.json`):
  - screen mode detected the 1.5 L water pot's loss in 15/20 runs, with 12
    false restores and T_c up to SP + 15.22 K;
  - the firmware rules detected all 80 losses, with 0 false restores and
    0 false latches in 60 food, 80 nominal and 160 probe-on-intact-contact
    runs, and T_c ≤ SP + 11.88 K.

## D-B5. The B5 stretch (≤ 15 s confirm) is not adopted

The candidate was a 3/6/3 s first probe at 60 %, with a 1.5 s lag.
- It confirmed in ≤ 16.2 s.
- It latched falsely in 40 of 160 probe-on-intact-contact runs
  (`b5-montecarlo.json`).

The default stays at 5/8/5 s, 50 %. The ≤ 21 s confirm bar is met on screen.py's
seeds: 20.6 s worst. Across 20 seeds the water pot takes up to 4.2 s to suspect
and up to 22.2 s to confirm. This is reported, not gated: its probe response is
only 0.12 K/kJ, an SNR limit.

## D-RATE. Rate fault = spike or sustained slew, not one fast step

The HANDOFF rule "|dT/dt| > 30 K/s is a sensor fault" would fault on every
hot-pan placement. The co-sim's reading rises at 308.6 to 462.7 K/s when a
preheated pan lands on the 40 mJ/K disc (`cosim-results.json` hot_pan
max_reading_rise_K_per_s).

A fault is therefore either of these:
- a reversal, meaning two consecutive steps > 3 K with opposite signs;
- a monotone slew > 30 K/s lasting > 3 s.

The three hot-pan cases pass B1–B3 with no fault.

## D-XCHK. Cross-check: 25 K margin, and the reading must not be rising

The PCB agent requires 25 K, not the HANDOFF's 15 K (`../pcb/DECISIONS.md`
D5, CR-7): the rim NTC is ±10.2 K at 250 °C. I adopted 25 K.

The low reading must also have risen < 2 K from its lowest value during the
30 s count. A pan quenched by cold food rises; a stuck or leaking sensor does
not. A suspect result requests a D1 probe; it is not a fault.

In the co-sim the cross-check never fires, at either 15 or 25 K, because D1
catches every loss first: the results are identical at both margins. There
is a second reason: cosim.py's rim stays below the real channel's saturation.
`xcheck_cosim.py` gives the plant a rim and exercises the cross-check
(D-RIM).

## D-SM. State machine mapping

- **Faults.** Register 07h, SPI, stale, range and rate faults reuse the
  existing RTD sink, `state_machine_report_rtd_device_fault`. They map to
  EVENT_PROBE_SHORT for RTD_LOW and below-range readings, and to
  EVENT_PROBE_OPEN for everything else, the same priority as the MAX31865
  driver.
- **Contact lost.** A new EVENT_CONTACT_LOST is a self-loop in PREHEAT and in
  HEATING. It shows "PAN MUST TOUCH SENSOR" and beeps. Power authority stays
  in `pan_temp_loop` (D1 holds P = 0 and retries), so the state machine does
  not leave the cooking state on a recoverable loss.
- **Regenerated files.** The transition table, generated test and proof
  record were regenerated. Edge counts were updated: 32 → 34 transitions and
  42 → 44 mutation targets.

## D-MODE. One compile-time switch, TEMPER_PAN_CONTROL_C1

The C1 runtime is selected by `TEMPER_PAN_CONTROL_C1`:
- `main/CMakeLists.txt` defines it for the ESP-IDF target;
- the C1 host targets define it (`test_c1_runtime_only`,
  `test_c1_rtd_service_only`);
- the legacy host suites build without it and still test the legacy control
  and runaway behaviour unchanged.

The legacy suites encode legacy behaviour in dozens of assertions:
- bang-bang preheat and PID power levels (the intensity-clamping tests assert
  20/50/100/30 %);
- step temperature jumps that the C1 guard would flag;
- `test_fault_thermal_runaway` (`test_integration.c`) and
  `test_sm_fault_on_thermal_runaway` (`test_state_machine.c`), which assert
  the target + 10 K latch;
- the SIL trace invariant of 15 K/s per 100 ms.

The transition model, its invariants and the `EVENT_RUNAWAY_RISE_RATE` /
`EVENT_THERMAL_RUNAWAY` edges stay abstract and unchanged. What changes is
how the firmware decides that the event happened.

With the switch on:
- `main/pan_control.{c,h}` owns the loop (`ptl_t`) and the supervisor
  (`psup_t`). It runs `ptl_step` every 100 ms from the 10 ms state-machine
  update and holds the command in between. Its inputs are:
  - `rtd_service_latest_sample()`;
  - the rim NTC driver, one period per control period (D-RIM; it also
    defines `read_rim_ntc_temperature()`);
  - the last command, as `PG_POWER_ESTIMATED`.

  Its output is `power_set_level()` in percent of 1.8 kW. The intensity level
  becomes the loop's own power limit (`ptl_set_power_limit`), so the PID
  anti-windup and the plant-gain saturation gate see it.
- PREHEAT entry starts the loop. PREHEAT hands over to HEATING at
  T̂ ≥ target − 10 K, the legacy threshold, and the loop runs on through
  HEATING. Any other way into HEATING starts the loop, and leaving the power
  states stops it (`transition_to`).
- Events:
  - guard verdicts go to `state_machine_report_rtd_device_fault`;
  - D1 contact lost goes to `state_machine_report_pan_contact_lost`;
  - supervisor stage 2a/2b latches `FAULT_THERMAL_RUNAWAY`;
  - frozen codes latch `FAULT_ADC_STUCK` through the new
    `state_machine_report_rtd_frozen`.
- Every `read_pan_temperature()` / `read_rtd_resistance()` in
  `state_machine.c` and `state_handlers.c` reads the latest conversion. The
  RTD resistance interlock uses the C1 window, 84.27 / 233.2144 Ω.

## D-THRESH. C1 threshold words: 12844 / 35544, as CR-7 lists

These are `config.yaml` constants with `board_derivation: true` and
derivations in `firmware/tools/board_derivations.yaml`:
- `RTD_C1_SHORT_FAULT_OHM` 84.27;
- `RTD_C1_OPEN_FAULT_OHM` 233.2144, which is R(360 °C);
- `MAX31865_C1_LOW_THRESHOLD_WORD` 12844;
- `MAX31865_C1_HIGH_THRESHOLD_WORD` 35544.

The MAX31865 sets the RTD High bit when the code is ≥ the high threshold, and
the Low bit when it is ≤ the low threshold (`datasheets/max31865.pdf`, "Fault
Threshold Registers"). The board contract therefore rounds the low code up and
the high code down. A resistance at or beyond the boundary then trips whether
the converter truncates or rounds.

**Open item 7, resolved** (`cr7_thresholds.py` → `cr7-thresholds.json`, gated
in `run.sh`). The CR-7 inputs are temperatures: R(−40 °C) = 84.27065 Ω and
R(360 °C) = 233.21440 Ω (IEC 60751, RREF 430 Ω).
- High: code 17772.022 rounds down to 17772, word **35544**. That is what
  CR-7 lists.
- Low: code 6421.816 rounds up to 6422, word 12844. Both sides agree.

The firmware was wrong by one code. It derived its word from the 2-decimal
233.21 Ω printed in CR-7, which is 0.0044 Ω below R(360 °C), and got 35542.
- 35542 trips at 359.96 °C, early and on the safe side.
- 35544 trips at 359.9992 °C, still at or below 360 °C.
- The earlier note here, that 35544 is "233.22 Ω, just outside the window",
  was wrong: 35544 is 233.21411 Ω, below R(360 °C).

`config.yaml` now carries 233.2144 Ω and 35544. `config.h` is regenerated, and
`scripts/check_firmware_board_contract.py` passes 5/5. The CR-7 document
is right, so the PCB owner needs no change. The legacy words 1526/45722 are
unchanged.

## D-CR7. Where each CR-7 item landed

| CR-7 item | Where |
|---|---|
| CONFIG 0xC0 (VBIAS, auto conversion, 60 Hz) | `max31865_start_conversions`, after the power-up cycle |
| One automatic fault cycle at power-up, coil off; completion by polling CONFIG D3:D2 | `rtd_service` C1 bootstrap / `max31865_fault_cycle_busy`. **Manual** cycle (needs CR-1 filter): open |
| Thresholds 84.27 / 233.21 Ω (R(−40) / R(360 °C)) | D-THRESH |
| Self-heating 0.061 K subtracted | `rtd_convert_code_to_c` |
| Loading correction R − (7.86e-4·R − 0.0331) | `rtd_convert`, behind `RTD_FRONT_END_CR1` (default 0: the captured controller has no CR-1) |
| Stale: no DRDY for 3 × 20 ms | `RTD_C1_STALE_CONTROL_TICKS` 6 (60 ms) |
| Rim ADC attenuation and rim faults | `components/sensors/rim_ntc.c` (D-RIM) |
| 25 K cross-check | the guard (D-XCHK) |

## D-STALE. Stale means no DRDY; a frozen code means 250 identical codes

CR-7's "code does not change in 3 reads" would fault a healthy sensor. At
15 bits (about 0.034 K/LSB) and sub-LSB noise, identical consecutive codes are
normal. In the runaway runs the longest run of identical codes on a healthy
sensor is (`runaway-checks.json` margins.max_identical_codes_by_noise):
- 88 conversions at 0.3 LSB noise;
- 12 at 1 LSB;
- 6 at the 0.2 K design noise.

So in C1 builds:
- **stale** is no DRDY for 6 control ticks (60 ms);
- **frozen** is `RTD_C1_FROZEN_CONVERSIONS` = 250 identical codes, 5 s at
  50 Hz, which latches `FAULT_ADC_STUCK`. That is 2.8× the longest healthy
  run.

The legacy equal-reading check (49 equal 10 ms reads, about 0.5 s) is
compiled out in C1 builds. It trips 24 of 25 benign runs at 0.3 LSB
(`runaway-checks.json` legacy_false_trips.L_stuck; all 24 at 0.3 LSB). A
frozen reading is caught 4.7–5.0 s after it freezes, against the legacy
0.2–0.5 s (`runaway-checks.json` faults, kind fault_frozen). In those 5 s the
loop keeps heating, so the pan can rise by up to 5 s × the heating rate. The
pan peak stays ≤ 198.6 °C across the 24 frozen runs, which include freezes
during the first heat-up.

## D-RUN. Runaway checks: R1 replaces the 10 ms rate latch, R2 replaces target + 10 K

`components/control/pan_supervisor.{c,h}` replaces the two legacy checks.
`runaway_checks.py` produces the evidence and `run.sh` gates it. Each run
closes the C loop and the C supervisor around the truth plant. The model
feeds a 50 Hz quantised MAX31865 stream to 10 ms state-machine ticks, at
three noise levels (0.3 LSB, 1 LSB, 0.2 K). The scenarios are:
- 25 benign runs per noise level: design, hot pan at sp and sp + 40 K, h_c
  steps, food, setpoint lowered by 30 K;
- 4 contact-loss runs;
- 23 fault runs.

**The legacy checks false-trip** on benign runs, out of 75 (25 per noise
level; `legacy_false_trips`):
- **15 K/s per 10 ms:** 58 runs (8 at 0.3 LSB, 25 at 1 LSB, 25 at 0.2 K).
  These include all hot-pan placements, design runs and h_c steps. One LSB
  in 10 ms is 3.4 K/s.
- **Target + 10 K:** 21 runs: every lowered setpoint (12) and hot-pan
  placement (9).

**R1 (sustained rise).** It latches the RUNAWAY boundary when the 1 s block
means rise > 15 K/s for 5 consecutive blocks.
- No benign run sustains more than 1.5 K/s over 5 blocks. The largest
  single-block rise is a 79.4 K/s placement transient.
- No fault runs faster than 3.84 K/s (`margins`). 1.8 kW cannot heat even the
  lightest pan at 15 K/s.

So R1, like the legacy rate latch, guards the sensor path, not the pan. A
real runaway meets the absolute 300 °C check, which still runs every 10 ms
and is unchanged.

**R2 runs at 10 Hz in PREHEAT/HEATING.**
- **Stage 1** is not latching: max(T̂, reading) > target + 10 K forces the
  command to 0. In the co-sim it was active in 5 runs, for at most 1.4 s
  (`cosim-results.json` summary.supervisor).
- **Stage 2a** latches `FAULT_THERMAL_RUNAWAY` on bus current that the
  command cannot explain, for 0.5 s:
  - > 0.5 A with the command at 0 for 0.3 s, or
  - > P_cmd/100 V + 2.5 A, taking the largest command of the last 0.3 s.

  That is a power stage not obeying, which is the failure the legacy latch
  was a proxy for. For a stage stuck on at 600–1800 W it trips within
  0.4–3.1 s on every hazardous run, while the pan is still ≤ 198.3 °C. The
  legacy latch takes 7.8–35.1 s on the same runs.
- **Stage 2b** latches when the pan is over target with the command at 0 for
  20 s and still rising ≥ 2 K over 5 s. It is current-independent, for the
  double fault: a stuck-on stage with the current sense reading 0. The sweep
  (`stage_2b_sweep`) covered holds 5–60 s, windows 5–20 s and rises 1–4 K.
  - Holds of 5 s, and of 10 s with a 10–20 s window, false-trip on the hot
    pan placed at sp + 40 K.
  - 20/5/2 and its half-hold neighbour 10/5/2 have no false trip.
  - 20/5/2 catches all 15 hazardous double-fault runs in ≤ 35.0 s, with
    T_c ≤ 245.7 °C at the trip. The pan centre peaks at 259.9 °C after the
    cut.
  - The placeholder hold of 60 s took up to 75.1 s and reached 360.4 °C.

**Trade-off (double fault only).** With the current sense also failed, C1
latches later than the legacy target + 10 K check: up to 35.0 s against 7.8 s
at best for legacy, which also latches falsely. The pan stays under 300 °C at
the C1 trip (≤ 245.7 °C). The absolute 300 °C check, the hardware comparator
(299–322 °C), the rim-NTC trip (262–288 °C, CR-5) and the TCO are unchanged.

**Checks that pass** (`runaway-checks.json` checks):
- there are no C1 false trips on any benign run or before any fault;
- every hazardous fault is caught by a C1 rule before T_c exceeds 301 °C;
- C1 is never later than the legacy budget, except for the double fault and
  the frozen code (D-STALE), and those two are allowed explicitly with
  reasons in `allowed_later_than_legacy`;
- RTD open and short are caught at 0.00 s and no-DRDY at 0.05 s (legacy
  0.45–0.47 s);
- contact loss is confirmed in ≤ 20.8 s.

A 600 W stuck stage on cast iron settles at 223.5 °C, below 230 + 10 K, so
it is not hazardous. 2a still catches it with current sensing.

The C1 runtime tests (`test_c1_runtime_only`) repeat the key cases through
the real state machine:
- a hot pan placed in IDLE does not latch;
- target + 13 K holds the power off without latching;
- a lowered target does not latch;
- 10 A with the power off latches `FAULT_THERMAL_RUNAWAY`;
- 3 K/s with the power off latches after 20 s;
- 305 °C still latches the RUNAWAY boundary.

## D-ID2. Plant gain on later setpoint steps: one hold-to-hold energy balance

Before, a never changed after the first heat-up. A later step (10–30 K) is
too short for the 20-block window.

A short sliding window on later ramps is corrupted by the pan-centre lag. The
sensor sits at the pan centre, and during a ramp the pan mean runs well ahead
of it: in the design runs the mean overshoots the setpoint by up to 18.5 K
while the reading overshoots ≤ 3.2 K (`cosim-results.json` design
worst_T_mean_overshoot_K and worst_overshoot_K). A window also absorbs the
hold loss, several hundred W at 200 °C, into a, which pushes it low: the
over-powering side.

A later step therefore makes one update, from an energy balance between two
holds:

  a = (T_end − T_0) / (E_in − ∫L dt)

- T_0, P_0 are the mean reading and input power over the 10 s before the
  step. They must be a hold: block means within 1 K. The hold power is the
  measured loss at T_0.
- T_end, P_end are the same over the first 10 s hold after the step.
- L(T) is linear through (T_0, P_0) and (T_end, P_end).
- The gate must stay closed-clean from the step to the end hold: no D1 event,
  no fault, contact normal. The update also needs a rise of ≥ 5 K, and it
  times out after 300 s.

Protection:
- The phase estimate must lie within [θ/1.5, 1.5θ], or it is rejected. That
  rejects a boil plateau (the end-hold power is the boil power), a lifted pan
  and a stuck reading.
- One phase may raise a by up to 1.5× and lower it by up to 1/1.25.
- The covariance floor is (0.2θ)².

Results (`cosim-results.json`):
- **Carbon steel and cast iron** now update: a/a_true moves from 0.88–1.115
  to 1.049–1.251.
- **Triply clad** is rejected: its end hold is not yet steady, so the
  estimate falls outside 1.5θ.
- **Water pot:** the boil plateau is rejected.
- **Food runs:** a stays at its first-ramp value.

Every update moved a up, the sluggish and safe side. The design bars are
unchanged in every gain mode: B1 15/16, B2 16/16, B3 16/16, worst overshoot
3.15 K. The new bar `a_after_later_ramp_0p7_to_1p6` passes. `sensitivity.json`
shows B2/B3 pass at 1.4× a.

Unit tests in `test_pan_temp_loop_only` cover:
- recovering a from hold to hold;
- rejecting a boil plateau;
- requiring a clean phase that starts from a hold;
- limiting a decrease per phase.

## D-RIM. Rim NTC driver; a rim fault latches through the RTD sink

**Driver.** The driver is `components/sensors/rim_ntc.{c,h}`.
- It reads hardware only through `rim_ntc_hal_t`, so the host tests drive it
  through a mock.
- `rim_ntc_board.c` binds it to `hal_adc` on ADC1_CH8 (GPIO9). The HAL's
  ESP32 port keeps the one ADC1 one-shot unit and the curve-fitting
  calibration. An attenuation change re-initialises the channel and rebuilds
  its calibration.
- `main/pan_control.c` runs one driver period per 10 Hz control period.

Each period:
- **Read.** Eight one-shot samples. The mean drops the lowest and highest.
- **Attenuation (CR-7).** ATTEN0 below 0.80 V, ATTEN2 below 1.55 V, otherwise
  ATTEN3.
  - Switching down needs 30 mV of hysteresis.
  - A sample within 10 mV of the calibrated full scale (850 / 1600 / 2900 mV)
    is read again, one range up, in the same period.
- **Ratio.** The node is divided by v3v3, and R = 1 k·x/(1 − x).
- **Temperature.** From the datasheet table, with 1/T linear in ln R between
  points.
- **Filter.** First order, τ 1 s. The bead's own still-air time constant is
  7 s, so the filter adds no lag the cross-check or the KF sink would see.

**Table.** The 104GT-2 column of the Semitec GT-2 datasheet R-T table, −50 to
300 °C in 10 K steps plus 25 and 85 °C: 38 points.
- **Source:** `https://www.semitec.co.jp/uploads/GT-2シリーズ.pdf`, retrieved
  2026-10-15, sha256 c0a2841d….
- **Transcription:** in `rim_ntc.py`, which generates `rim_ntc_table.h`.
- **Checks:**
  - `--verify-pdf` re-extracts the column from the PDF and matches all 38
    values;
  - all 23 points that `pcb/checks.py` uses agree;
  - B25/85 computed from the table is 4267 K.

**Accuracy.** Numbers from `rim-ntc.json` and `test_c1_rim_ntc_only`:
- **Interpolation.** Leave-one-out over a 20 K step, 100–280 °C: worst
  0.030 K. pcb/checks.py's log-linear-in-T rule gives 0.257 K. The table
  step is 10 K, so the real error is smaller.
- **Datasheet points through `rim_ntc_r_to_c`.** At 25, 100, 150, 200 and
  250 °C the error is 0.00000 K.
- **The whole chain.** From the node voltage, rounded to whole mV as the IDF
  calibration returns it, to the filtered output:

  | °C | v3v3 3.300 V | v3v3 3.242 V | Attenuation |
  |---|---|---|---|
  | 100 | −0.026 K | +0.037 K | ATTEN3 |
  | 150 | −0.015 K | +0.014 K | ATTEN3 |
  | 200 | +0.015 K | −0.035 K | ATTEN2 |
  | 250 | +0.014 K | −0.073 K | ATTEN0 |

- **Resolution.** The worst is 0.143 K/mV, at 250 °C. That meets "≤ 0.3 K,
  100–250 °C" with whole-mV output; the PCB agent's 0.057 K assumed raw LSBs.
- **Not in these numbers:** the sensor's own tolerance (R25 ±3 %, B ±2 %,
  the PCB agent's 10.2 K at 250 °C), the rail and self-heating:
  - **The rail.** The MCP3202 CH1 rail reading (CR-7) has no firmware driver.
    The board binding reports "no rail", and the driver assumes 3.300 V. That
    costs up to 4.37 K at the contract limits.
  - **Self-heating is not subtracted.** In still air it is at most 4.53 K over
    100–250 °C (0.6 mW/K, datasheet). Bearing on the glass the dissipation is
    higher, so the true offset is smaller, and correcting with the still-air
    figure would make the rim read low. Reading high is the safe direction
    for the cross-check: it can only add probes.
  - **Stacked against the 25 K margin:** 10.2 + 4.37 + 4.53 = 19.1 K, still
    under 25 K. Some of the PCB's 10.2 K is its own 0.2 % rail term, so this
    stack double-counts slightly and is conservative.

**States.**
- **SATURATED.** The node is at or above 2900 mV at ATTEN3, which is
  87.05–96.51 °C over the v3v3 range (91.76 °C at 3.300 V). This is the
  normal cold state, not a fault. The reading is an upper bound only.
- **Loop input** (`pan_control.c` `loop_rim_input`):
  - VALID: the filtered rim.
  - SATURATED: min(bound, Pt100 reading). The glass under a heated pan is not
    hotter than the pan, so this is the closer of the two known limits. It
    never exceeds the reading, so the cross-check cannot fire without rim
    information (`test_saturated_rim_never_cross_checks`; with the bound alone
    it fires).
  - No data or fault: the Pt100 reading.

  The value is always finite, because a NaN sink would corrupt the KF.
- **Faults:**

  | Fault | Condition | Persistence | Reported as |
  |---|---|---|---|
  | SHORT | node < 0.25 V (297.5–300.4 °C) | 3 periods | short |
  | OVER_RANGE | T > 290 °C, above the CR-5 band top of 288.1 °C | 3 periods | short |
  | OPEN | saturated while T̂ ≥ 150 °C | 600 s (CR-7) | open |
  | ADC | no reading | 10 periods | open |

  While a fault is only a candidate, the last reading is held.

**Fault policy: latch, through `state_machine_report_rtd_device_fault`.**
SHORT and OVER_RANGE map to FAULT_PROBE_SHORT; OPEN and ADC map to
FAULT_PROBE_OPEN. This is the same sink and priority that `pan_sensor_guard`
uses. The power is cut in the same period. The detail is in
`rim_ntc_reading_t.diag` (`pan_control_rim_reading`). Why latch, not degrade
to suspect:
1. **Convention.** Every C1 sensor-path electrical fault latches: register
   07h, SPI, stale, range, rate and frozen. Only plausibility verdicts (D1
   suspect, the cross-check) are non-latching. A shorted, open or unreadable
   rim is an electrical fault, not a plausibility verdict.
2. **No other check covers leakage.** The rim is the only electrical check on
   element-parallel leakage (REQUIREMENTS R3.1 exception), and an open bead
   also disables the CR-5 hardware rim trip (it reads cold). Degrading would
   keep heating with that layer silently gone.
3. **The hardware already latches a short.** The node at 0.25 V is below the
   CR-5 comparator threshold (v3v3·10/96.6 = 0.342 V), so the hardware latches
   RUNAWAY_FAULT anyway. Firmware agrees with it.
4. **No new state-machine event.** The transition table, proof record and
   mutation counts are unchanged.

Each heating session re-detects: `pan_control_begin` re-initialises the
driver, as `ptl_init` clears the guard. The cost is that a rim fault stops
cooking with a "probe" fault code. UI wording for a rim fault is open.

**Evidence:**
- `test_c1_rim_ntc_only`, 13 tests. Conversion, chain accuracy, the CR-7
  attenuation and hysteresis, the clip re-read, saturation, the rail fallback,
  short, glitch rejection, over-range, open, ADC failure, the filter τ, the
  trimmed mean, and the board binding over the `hal_adc` mock.
- `test_c1_runtime_only`, 6 new tests through the real state machine and
  `pan_control`:
  - the cross-check fires on a low, flat Pt100 at 30 s;
  - it ignores a quench that is rising at 0.25 K/s (with the rise rule
    disabled, this test fails);
  - a saturated rim never cross-checks;
  - a rim short gives FAULT_PROBE_SHORT and zero power within 3 periods;
  - an open rim gives FAULT_PROBE_OPEN at 600 s hot;
  - an ADC failure gives FAULT_PROBE_OPEN.

**Co-sim** (`xcheck_cosim.py` → `xcheck-cosim.json`, gated in `run.sh` step
3b).

*Why cosim.py cannot do it.* Its "rim" is the r2 leak sink, which stays at
≤ 78 °C. The real channel saturates below 87 °C, so the cross-check can
never fire there. cosim.py is unchanged.

*The model here.* The plant gains a glass node under the NTC: a lag toward
T_c − Δ with τ_g 60 s.
- Δ is 12 or 46 K, study 08's glass-underside spread.
- τ_g is an assumption: there is no transient glass data.
- The cartridge leaks to the glass.
- The NTC runs at its tolerance corners, through the C driver.

Results:
- **Benign:** 28 runs (4 pans × nominal/food × Δ × corner).
  - 0 D1 lost latches, 0 guard faults, 0 rim faults, 0 supervisor latches
    (gated).
  - 2 cross-check suspects, both cast iron food at Δ 12 K, 50 s after the
    food. These are probes on intact contact, which D-B5 shows never latch.
  - Worst estimate error 1.96 K nominal and 9.92 K food. cosim.py's own food
    runs reach 8.47 K.
- **Element-parallel leakage** from 250 s, 16 runs (cold corner):
  - **1 kΩ:** the cross-check fires in 7 of 8, 208–292 s after the leak. D1's
    probe then (correctly) finds the sensor in contact, so heating continues.
    T_c reaches SP + 121.9 K, about 352 °C.
  - **3 kΩ:** no cross-check. T_c settles at SP + 35.4 K.
  - **CR-5 hardware trip:** the glass reaches the band's low edge (262.3 °C)
    in 6 of 16 runs and its top (288.1 °C) in 4.

  So the cross-check as specified (D-XCHK: suspect → probe) does not stop
  leakage. See open item 10.

## Open items for the firmware owner

1. **The ESP-IDF target has never linked**, before or after this work
   (IDF v5.3.6, esp32s3). The blockers are all pre-existing:
   - `partitions.csv` is missing (`sdkconfig.defaults` selects a custom
     table);
   - the project's `components/hal` shadows IDF's `hal`, so `driver/gpio.h`
     and mbedtls cannot find `hal/*_types.h`;
   - `components/webui` needs `esp_vfs_fat` and `json`;
   - the IDF Python env lacks jinja2;
   - many peripheral externs exist only in test stubs (`read_pan_temperature`,
     `peripherals_init`, …). `read_rim_ntc_temperature` is now defined, in
     `pan_control.c` (D-RIM).

   All C1 objects compile with the real IDF flags (`xtensa-esp32s3-elf-gcc`,
   `TEMPER_PAN_CONTROL_C1=1`):
   - the 7 `control` sources;
   - `pan_control.c`, `rtd_service.c`, `rtd_convert.c`, `max31865.c` and
     `state_handlers.c`;
   - `state_machine.c` and `main.c`, which compile once IDF's hal includes
     are put ahead of the shadow.
2. **Rim NTC driver and rim faults: closed by D-RIM.** What remains:
   - **MCP3202 CH1 rail driver.** Without it the rim assumes 3.300 V, which
     costs up to 4.37 K.
   - **Bench:** the bead's dissipation constant on the glass (self-heating is
     not subtracted), and a transient glass log to replace the 60 s τ_g
     assumption in `xcheck_cosim.py`.
   - **Pin header.** The legacy `hal/include/temper_pins.h` still names GPIO9
     `PIN_RTD_DRDY`. On zapote DRDY is on TCA9555 P07, and GPIO9 is the rim.
   - **UI wording** for a rim fault, which today shows as a probe fault.

   The three changed sources (`rim_ntc.c`, `rim_ntc_board.c`,
   `pan_control.c`) compile with `xtensa-esp32s3-elf-gcc` (`-Wall -Wextra
   -Werror`, C1 on). The IDF link is still item 1.
3. **Manual fault-detection cycle** (needs the CR-1 filter): still open. It is
   not trivially doable:
   - the captured controller has no CR-1, so `RTD_FRONT_END_CR1` defaults
     to 0;
   - the manual sequence (FORCE− open, ≥ 5 ms waits, CONFIG D3:D2 steps) is
     only meaningful against the filter's settling, which the SPI mock does
     not model.

   C1 runs the automatic cycle at power-up with the coil off.
4. **The double-fault trade-off (D-RUN)** is for the safety owner to accept or
   tighten. Options:
   - a bus-current validity signal, which would turn 2b into 2a;
   - a bus-voltage sense, to replace the 100 V placeholder in P_cmd/V.
5. **Bench items:**
   - real MAX31865 conversion noise. Below about 0.25 LSB the 250-code frozen
     check needs lengthening;
   - the bus-current sense scaling for stage 2a;
   - whether the end hold is steady on clad pans (D-ID2 rejections).
6. **The SIL suite is not run in C1 mode.** It encodes the legacy loop.
7. **CR-7 high threshold word: closed (D-THRESH).** Recomputed from R(360 °C)
   by `cr7_thresholds.py`, CR-7's 35544 is right. The firmware's 35542 came
   from the rounded 233.21 Ω and is fixed to 35544. The PCB side needs no
   change.
8. **Hot-pan starts run on the prior.** a is never identified (no updates,
   src_mask 0), so a0 is used. For cast iron that is 2.34 × a_true. B1–B3
   still pass.
9. **h_c steps are reported, not gated:** B1 0/4, B2 0/4, overshoot up to
   13.09 K for 1000 → 300 (`cosim-results.json` h_step). C1 no longer latches
   on them (D-RUN).
10. **Element-parallel leakage is not stopped by firmware (safety owner).**
    In `xcheck-cosim.json`:
    - 1 kΩ drives the pan to SP + 121.9 K;
    - 3 kΩ holds it at SP + 35.4 K;
    - the cross-check fires on 7 of the 8 1 kΩ runs only, and its D1 probe
      correctly confirms contact.

    Only the CR-5 hardware trip remains: the glass reaches the band's low edge
    in 6 of 16 runs and its top in 4.

    The obvious rule is to latch when a cross-check suspect is followed by a
    probe that confirms contact. That is the leakage signature, but 2 of 28
    benign runs (cast iron food, Δ 12 K) raise a suspect, so it needs a
    further qualifier before adoption, for example:
    - two consecutive suspect-and-confirm cycles;
    - the rim's own rise.

    D-XCHK is unchanged here.
