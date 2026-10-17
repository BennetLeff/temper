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
    runs, and T_c ≤ SP + 6.43 K (11.88 K before the contact-shift window,
    D-CSW).

## D-B5. The B5 stretch (≤ 15 s confirm) is not adopted

The candidate was a 3/6/3 s first probe at 60 %, with a 1.5 s lag.
- It confirmed in ≤ 15.4 s (16.2 s before D-CSW).
- It latched falsely in 40 of 160 probe-on-intact-contact runs
  (`b5-montecarlo.json`).

The default stays at 5/8/5 s, 50 %. The ≤ 21 s confirm bar is met on screen.py's
seeds: 20.9 s worst. Across 20 seeds the water pot takes up to 3.4 s to suspect
and up to 21.4 s to confirm (4.2 s and 22.2 s before D-CSW). This is reported, not gated: its probe response is
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
| Fault-detection cycle at power-up, coil off; completion by polling CONFIG D3:D2 | **Manual** cycle (D-FCYC): `rtd_service` C1 bootstrap + `c1_fault_cycle_tick`, `max31865_manual_fault_step1/2`, `max31865_fault_cycle_busy`; also on every probe-fault reset request (D-RESET). The automatic cycle is never written in C1 |
| Thresholds 84.27 / 233.21 Ω (R(−40) / R(360 °C)) | D-THRESH |
| Self-heating 0.061 K subtracted | `rtd_convert_code_to_c` |
| Loading correction R − (7.86e-4·R − 0.0331) | `rtd_convert`, behind `RTD_FRONT_END_CR1`, default **1** since zapote C37 fitted CR-1 exactly (D-FCYC) |
| Stale: no DRDY for 3 × 20 ms | `RTD_C1_STALE_CONTROL_TICKS` 6 (60 ms); DRDY from TCA9555 P07, polled (D-DRDY) |
| V_node / v3v3 with the rail from MCP3202 CH1 | `components/sensors/rail_adc.c` (D-RAIL) |
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

**With the manual fault cycle and the expander DRDY (D-FCYC, D-DRDY).** The
first conversion after any (re)start of conversions takes the single-
conversion time (data sheet Note 5: 52–55 ms with the 60 Hz notch), so it
gets `RTD_C1_FIRST_DRDY_CONTROL_TICKS` = 8 (80 ms) instead of 6; every later
one keeps 6. On zapote/controller DRDY is a level on TCA9555 P07, polled once
per tick: a failed I2C read counts as a tick without DRDY, so a dead expander
or bus trips the same 60 ms stale rule as a silent converter. The frozen rule
is unchanged.

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

## D-SIL. The SIL suite runs in both configurations, from one manifest

`firmware/test/test_sil_fault_injection.c` builds twice:
- `test_sil_fault_injection` (ctest `sil_fault_tests`): the legacy loop, as
  before;
- `test_sil_fault_injection_c1` (ctest `sil_fault_tests_c1`): built with
  `TEMPER_PAN_CONTROL_C1` like the ESP-IDF target, with the C1 loop,
  `pan_supervisor`, `pan_control.c` and the real MAX31865 service
  (`rtd_service.c`, `max31865.c`) linked.

Both read `firmware/test/traces/manifest.json`. A scenario's `modes` says which
targets run it (default both). CI's firmware job builds both targets and runs
`ctest -R sil_fault_tests`, then `scripts/check_sil_coverage.py`.

**The C1 target models the converter and the power stage.** It steps the
firmware's own cadence: each 100 ms trace row is 10 control ticks of 10 ms in
`main.c` order (`rtd_service_control_tick`, then `state_machine_update`), and
it observes the state after every tick. Behind the SPI and GPIO mocks:
- **MAX31865.** The power-up fault cycle completes on the first tick. Then,
  while CONFIG has VBIAS and auto-convert set, the model converts at 50 Hz:
  code = R / 430 Ω · 2^15, compared with the threshold words the firmware
  programmed. A crossing latches register 07h and sets the fault bit. Each
  conversion pulls DRDY.
- **R.** The Pt100 at the trace's pan temperature plus 0.061 K self-heating.
- **Bus current.** An obeying stage, P_cmd / 120 V. The supervisor allows
  down to 100 V.

The hand-written traces hold `dc_current` 5.0 A and `rtd_resistance` 100.0 Ω
as fixed placeholders, whatever the pan does: 100 Ω is a 0 °C Pt100, while
the pan reads 92 °C. C1 cross-checks both, so replaying them verbatim would
inject faults: 5 A against a near-zero command is stage-2a evidence. The rule
is therefore:
- a column equal to its row-0 value is the placeholder, and C1 replaces it
  with the consistent value;
- any other value is an injected fault, and C1 replays it verbatim.

A new `rtd_drdy` column (C1 only) injects a silent converter. The C1 runner
never calls the legacy test hooks `state_machine_reset_temp_baseline()` and
`state_machine_reset_stuck_tracking()`. Instead it primes the trace's start
temperature from power-up, so R1 sees every reading.

**Legacy-only assertions and their C1 replacements.**

| Legacy assertion | Why it is legacy-only | C1 replacement |
|---|---|---|
| Thermal Runaway (HEATING): reading at target + 15 K latches `FAULT_THERMAL_RUNAWAY` | The target + 10 K latch is compiled out (D-RUN). The trace also holds 115.0 noise-free for 6.5 s, which C1 rightly reports as a frozen code (`FAULT_ADC_STUCK` at row 134). | 1. Stage 1: target + 15 K for 31 s with an obeying stage. The state stays HEATING, the power is 0 and nothing latches. 2. Stage 2a: the stage is stuck on at 15 A and the pan rises 1.5 K/s. 3. Stage 2b: the same with the current sense at 0 A. |
| Relay Welded and Cooldown Overheat (COOLDOWN) | Both traces reach COOLDOWN one 100 ms update before the heatsink step, with the heatsink at 35 °C. At 10 ms, COOLDOWN ends on its first update (< 50 °C → IDLE), so the fault is never injected from COOLDOWN. This is a property of the trace, not of the loop. | Hot-heatsink variants (55 °C) that reach COOLDOWN at either cadence. They run in both modes. |
| DEMONSTRATED GAP: fan off during PAN_DET | The fan is off for 3 legacy updates (300 ms). At 10 ms the PAN_DET dwell is 30 ms, so the PREHEAT interlock (correctly) latches the fan fault. | A 1 s PAN_DET dwell (no pan) with the fan off. Same finding; runs in both modes. |
| Trace invariant: 15 K/s per 100 ms, legacy RTD window | The C1 rules differ. | R1 over 1 s block means, the C1 window, no injected placeholder or DRDY fault, no 50-row hold (frozen). Logged, as before. |
| RTD Probe Open: final state FAULT / `FAULT_PROBE_OPEN` | C1 reads the temperature from the same conversion. A saturated code converts to 988.7 °C, so the absolute check latches RUNAWAY_FAULT in the same 10 ms tick (runaway-checks.json sensor_open: C_abs 0.0 s). | `c1_escalates_to_runaway`: `FAULT_PROBE_OPEN` must be logged first (07h), then RUNAWAY_FAULT / `FAULT_RUNAWAY_BOUNDARY`, with exactly two EEPROM entries. |

**C1 latency bounds above the legacy ones.** Each needs a stated reason in
the manifest (`c1_later_than_legacy_reason`); the gate enforces it.
- **Double fault:** 350 rows = 35.0 s. This is the D-RUN allowance. The SIL
  latches at 207 rows (20.7 s), against 120 rows for legacy.
- **Sensor-path rise at 20 K/s:** 70 rows. That is R1's 5 blocks plus up to 2
  blocks of alignment. The SIL latches at 62 rows (6.2 s) with the reading at
  216.0 / 204.0 °C, against 1 row for legacy.

Where C1 is faster:
- the stuck-on stage latches at 4 rows (0.4 s) by stage 2a, against 120
  (HEATING) and 200 (PREHEAT) rows for legacy;
- the frozen code is timed from the freeze onset at exactly 50 rows = 250
  conversions, in IDLE, PREHEAT and HEATING.

**Checks now applied in both modes**, all of which legacy passes:
- no fault before the perturbation;
- the machine is in `origin_state` when the perturbation starts;
- `eeprom_logged` is the first fault logged since reset (it was the last);
- the first latched fault keeps its code and is logged once (D-LATCH);
- a reset with the fault condition still present is refused.

The old runner had 24 hard-coded test slots and silently skipped any manifest
entry past the 24th. It now runs every entry by name.

**Coverage** (`firmware/test/test_sil_coverage.py --gate`):

| Mode | Scenarios | Designed (fault class, origin) pairs covered |
|---|---|---|
| legacy | 31 | 20/20 |
| C1 | 46 | 27/27 |

(36 and 23/23 when D-SIL landed; D-OPEN, D-ISENSE, D-LEAK and D-RIMLIM added
the rest.)

C1's pairs are a superset of legacy's. It adds IDLE for `FAULT_PROBE_OPEN`,
`FAULT_PROBE_SHORT` and `FAULT_ADC_STUCK`: the converter service reports from
every state, while legacy's RTD checks run only in PREHEAT/HEATING. It also
adds FAULT_CURRENT_SENSE (PREHEAT, HEATING) and FAULT_PROBE_LEAKAGE (HEATING,
and PREHEAT for the rim limit).

A second matrix, C1 mechanism × origin, covers 22/22 cells (16/16 at D-SIL):
- R1 and the absolute 300 °C check;
- R2 stages 1, 2a and 2b;
- register 07h, DRDY stale and frozen code;
- the current-sense checks (a) and (b) (D-ISENSE);
- the Pt100 leak check (D-LEAK);
- the setpoint-relative rim limit, from HEATING and PREHEAT (D-RIMLIM).

The C1 runner checks each attribution where the firmware exposes it:
- the supervisor latch, through the new read-only
  `pan_control_supervisor_latch()`, and likewise the current-sense latch
  (`pan_control_current_sense_latch()`), the leak latch
  (`pan_control_leak_latched()`) and the rim limit
  (`pan_control_rim_limit_latched()`);
- the reading at the trip;
- register 07h;
- whether the service has stopped.

The gate also enforces:
- every legacy-only scenario names its C1 replacement, which runs in C1;
- every C1-only scenario says why;
- every generated trace matches `gen_sil_traces.py`.

`manifest.json` supports `"xfail": {"c1": "reason"}` for a known defect: it is
reported as XFAIL, and an unexpected pass fails the run. No scenario uses it.

## D-LATCH. A sensor report no longer overwrites an already-latched fault

**Found by the C1 SIL.** The C1 converter service runs in every state,
including FAULT and RUNAWAY_FAULT. `state_machine_report_rtd_device_fault()`
and `state_machine_report_rtd_frozen()` called
`enter_hardware_latched_fault()` unconditionally. Against the unfixed
firmware, 19 of the 36 C1 scenarios failed:
- **07h re-entry.** A MAX31865 holds register 07h until it is cleared, so a
  latched threshold fault re-entered FAULT and logged to EEPROM on every
  conversion. Probe short (HEATING, PREHEAT, IDLE) and 80 Ω each gave 251
  EEPROM entries, not 1: one per conversion, 50 a second, until the
  frozen-code check stopped the service 5 s later.
- **Fault code overwritten.** A later report replaced the latched fault code.
  Over-temperature, over-current, fan and IGBT faults (8 scenarios) ended as
  `FAULT_ADC_STUCK` with a second EEPROM entry. RUNAWAY_FAULT kept its state
  but its code became `FAULT_ADC_STUCK` (absolute-temperature scenarios) or
  `FAULT_PROBE_OPEN` (probe open, 3 scenarios). The code is what the user sees
  and what `fault_cleared()` tests.

To reproduce these numbers, revert the D-LATCH and D-RESET hunks in
`main/state_machine.c` and run `sil_fault_tests_c1`.

**Fix** (`main/state_machine.c`). While FAULT or RUNAWAY_FAULT is latched,
the two sinks only re-assert the hardware cut. The first fault keeps its code
and is logged once. Escalation from FAULT to RUNAWAY_FAULT by
`check_runaway_boundary()` is unchanged.

**Why the fix loses no protection.** A terminal sensor report that the latch
absorbs (stale, frozen) stops the converter service, and D-RESET then refuses
the reset. A non-terminal one (07h) is reported again by the service as soon
as the machine leaves FAULT.

This applies to both builds; the legacy sinks only fire from the legacy
MAX31865 path.

## D-RESET. `fault_cleared()` uses the C1 window and refuses while the converter is stopped

**Found by the C1 SIL after D-LATCH.** Three C1 scenarios still accepted a
reset with the fault present, going FAULT → INIT → IDLE:
- **80 Ω.** `fault_cleared()` tested the legacy 10–300 Ω window. 80 Ω is
  inside it but below the C1 84.27 Ω short threshold, so the reset was
  accepted.
- **No DRDY (IDLE and HEATING).** The service had stopped, but the last
  conversion's resistance was in the window.

**Fix.**
- The probe-fault clear condition uses `SM_RTD_*`, the window the interlock
  uses. That is the C1 window in C1 builds; the legacy build is unchanged.
- In C1 builds, `fault_cleared()` returns false for every fault while
  `pan_control_sensor_ready()` (which is `rtd_service_is_ready()`) is false.
  A stopped service needs a power cycle to bootstrap it again.
- `test_c1_runtime.c` gains an `rtd_service_is_ready()` stub, because that
  target does not link the service.

**A manual fault cycle before every probe-fault reset (D-FCYC).** For
FAULT_PROBE_OPEN / SHORT, `fault_cleared()` → `rtd_service_fault_status_clean()`
asks the service for a verification: CONFIG 0x82 (07h clear, conversions
stop, VBIAS stays on), 0x88 (step 1), 5.5 ms, 0x8C (step 2), 07h, then the
restart 11.5 ms after step 2. The reset is accepted only when that cycle read
07h = 0 **and** a later conversion came back unflagged, and that verdict is
used once. A flagged cycle is reported (the latch absorbs it) and refuses the
reset: an input shorted to ground still converts inside the window (the
short adds the lead and switch, about 12 Ω), so the window alone would have
accepted it. The verification takes about 0.1 s, longer than a short press,
so in C1 a probe-fault press stays **armed for 1 s** after it is let go
(`state_handlers.c`, `RESET_PROBE_ARM_MS`); the check keeps running with the
coil off, FAULT PERSISTS shows only while the button is held, and other
faults still need the button held. The SIL's refused-reset check now watches
2 s past the press. The power-up cycle's fault is terminal (the service
stops), so a power cycle is still needed for it.

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
  - **The rail.** With the rail unknown the driver assumes 3.300 V, which
    costs up to 4.37 K at the contract limits. The MCP3202 CH1 reading
    (D-RAIL) is now the board binding's `read_v3v3_mv`; measured, the rail
    term is at most **2.87 K** over 100–250 °C (`rim-ntc.json`
    `rail_error_with_MCP3202_worst_K`, the reading's full-range 1.33 % error
    on a −40..85 °C board). The 19.1 K stack below keeps the unknown-rail
    4.37 K, because the rail can be unknown (D-RAIL: that is not a fault).
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
  - Worst estimate error 1.96 K nominal and 13.13 K food (9.92 K before D-CSW). cosim.py's own food
    runs reach 8.47 K.
- **Element-parallel leakage** from 250 s, 16 runs (cold corner):
  - **1 kΩ:** the cross-check fires in 5 of 8, 233–292 s after the leak
    (with the contact-shift window in the loop, D-CSW). D1's probe then
    (correctly) finds the sensor in contact, so heating continues. T_c
    reaches SP + 121.9 K, about 352 °C. On carbon steel and cast iron at
    Δ 12 K the glass passes 300 °C and the rim channel's over-range fault
    latches first, at 447–463 s. (Until D-LEAK the glass model clamped the
    NTC at its 300 °C table top, which hid that fault.) The water pot at
    Δ 46 K never fires.
  - **3 kΩ:** no cross-check. T_c settles at SP + 35.8 K.
  - **CR-5 hardware trip:** the glass reaches the band's low edge (262.3 °C)
    in 6 of 16 runs and its top (288.1 °C) in 5.

  So the cross-check as specified (D-XCHK: suspect → probe) does not stop
  leakage. See D-LEAK and open item 10.

## D-OPEN. A sensor-failure conversion is a recoverable probe fault, not RUNAWAY

**Before.** An open Pt100 converts to full scale (code 32767, 988.7 °C). In
the same 10 ms tick the absolute 300 °C check in `check_runaway_boundary()`
latched RUNAWAY_FAULT, which is not software-clearable, although register
07h had already flagged the conversion (open item 6).

**Rule.** `rtd_convert_classify_failure(code, fault_status)`
(`components/sensors/rtd_convert.c`) classes a conversion as:
- **OPEN:** code ≥ `RTD_C1_FAIL_HIGH_CODE` = 29757, the code of R(850 °C) =
  390.48 Ω, or any 07h input bit D5..D2 (REFIN/RTDIN and over/undervoltage);
- **SHORT:** code ≤ `RTD_C1_FAIL_LOW_CODE` = 1411, the code of R(−200 °C) =
  18.52 Ω;
- **a temperature**, otherwise. The 07h threshold bits D7/D6 alone are not a
  failure: a flagged 300–850 °C reading is a real over-temperature.

In C1 builds `check_runaway_boundary()` sends a failed conversion to
`state_machine_report_rtd_device_fault()` (FAULT_PROBE_OPEN /
FAULT_PROBE_SHORT, recoverable) and returns: no RUNAWAY latch and no R1
sample. Every other reading above 300 °C still latches RUNAWAY.

**Why 850 °C** (`sensor_fail_codes.py` → `sensor-fail-codes.json`, gated
against `rtd_convert.h`):
- it is the IEC 60751 range top; the Callendar–Van Dusen equation the
  firmware inverts is not defined above it;
- the element is rated −200..600 °C (IST P0K1.202);
- the hottest the truth plant drives the element uncontrolled is 775.1 °C
  (triply clad at 1.8 kW and η 0.92; cast iron 495.2, carbon steel 516.4);
- the fastest heating of any modelled fault is 3.84 K/s
  (`runaway-checks.json` margins). A pan takes 143 s from 300 °C to 850 °C at
  that rate, and each of its 7161 conversions on the way latches RUNAWAY.

So a first reading at or above 850 °C is a sensor, not a pan.

**Reset.** The MAX31865 latches 07h until CONFIG D1 clears it, so before this
a healed sensor was re-reported for ever. `fault_cleared()` for
PROBE_OPEN/SHORT in C1 now needs, in order:
1. the resistance inside the C1 window;
2. a conversion that is not a failure;
3. `rtd_service_fault_status_clean()`: if the latest conversion carried a
   flag, the service writes CONFIG 0xC2 at the start of its next converting
   tick, and returns true only after a later conversion reads clean
   (`max31865_clear_fault_status()`).

**Evidence.**
- `runaway-checks.json`: the open and short sensor runs now trip
  `rtd_fail_code` (0.00 s) and `rtd_fault` (0.02 s), no longer `C_abs`.
  Acting peaks are unchanged (197.9 °C).
- SIL C1 (`sil_fault_tests_c1`):
  - the three probe-open scenarios (HEATING, PREHEAT, IDLE) now hold
    FAULT_PROBE_OPEN to the end, where they used to escalate to RUNAWAY;
  - *C1 Flagged Over-Temperature Still Latches Runaway*: a 380 °C step
    (07h D7 set) still latches RUNAWAY on the absolute check, in 1 row;
  - *C1 RTD Near Full Scale, Not Open*: 410 Ω (917.5 °C, no input bit) is
    held as FAULT_PROBE_OPEN;
  - *C1 RTD Probe Open Then Reconnected*: the reset is accepted once the
    element is back. Without the 07h clear the same scenario fails (negative
    control, run by hand).
- Unit tests: 4 classifier tests (`test_c1_units_only`), 2 clear tests
  (`test_c1_rtd_service_only`).

## D-ISENSE. The bus-current sense is checked on its own

**Why.** Stage 2a (D-RUN) finds a power stage that does not obey its command
from the bus current. If the sense reads 0 A, 2a is blind, and only stage 2b
is left against a stuck-on stage (≤ 35.0 s, D-RUN). A stage and a sense need
not fail together: a sense that dies first stays latent until the stage
sticks. `components/control/current_sense_check.{c,h}` checks the sense on
its own. `main/pan_control.c` runs it and latches FAULT_CURRENT_SENSE through
`state_machine_report_latched_fault()` (hardware cut, not
software-clearable).

**Rules.**
- **(a) run**, every control period: the command in force has been ≥ 300 W
  for > 0.3 s, and the bus current reads ≤ 0.5 A (or not finite) for 0.5 s.
  - 0.5 A, 0.3 s and 0.5 s are stage 2a's no-current bound, settle time and
    hold.
  - 300 W is well above the stage's ~160 W burst floor, so the stage runs
    continuously whenever (a) looks. Below the floor it bursts and reads 0 A
    between bursts.
  - At 300 W an obeying stage draws at least 0.9 × 300 W / 120 V = 2.25 A,
    4.5× the bound.
- **(b) start-up pulse**, at PREHEAT entry (PAN_DET has found a pan): 360 W
  (20 % of 1.8 kW, clamped to the intensity limit) replaces the loop's
  command for 1.0 s. After 0.3 s the mean current must exceed 0.5 A. The
  pulse restarts if something holds the command at 0 (stage 1, a fault).
  (a) does not look while the pulse runs.
- **(c) input vs bus current**, for the AMC1301 input-current sense
  (nameplate-r1 D3). On the unfiltered full-bridge bus the two read the same
  statistic, so above 1.0 A a difference greater than max(1.0 A, 25 %) for
  0.5 s latches. It is compiled only with `TEMPER_INPUT_CURRENT_SENSE`
  (default 0, the sense is not on the board), and tested by
  `test_c1_runtime_isense_only`.

Stage 2b is unchanged and remains the last resort for a stage and a sense
that fail at the same moment.

**Evidence** (`runaway_checks.py` → `runaway-checks.json` `current_sense`;
the C library is driven passively on every run):
- **Latent sense failure, then the stage sticks at 250 s.** Two pans × 600 /
  1200 / 1800 W × 3 noise levels:
  - dead from power-up: the pulse latches 1.0 s after PREHEAT entry, 18/18;
  - dies at 100 s: (a) latches at 100.4 s, 18/18.

  Acting, the stage never gets to stick: peak T_c is 32.6–34.2 °C and
  107.8–117.2 °C. The same double fault with the sense dying at the moment
  the stage sticks peaks at 197.4–259.9 °C.
- **Simultaneous double fault** (the existing `current_broken` runs, the
  sense now dying at 250 s with the stage). Cast iron: (a) latches 0.4 s
  after, because the loop is commanding ≥ 300 W when both fail. Triply clad
  holds below 300 W, so (a) does not look and stage 2b latches in 22.6–26.7 s. The 2b result is unchanged, because the passive trajectories are
  identical: 20/5/2 detects 15/15 hazardous double faults in ≤ 35.0 s with
  T_c ≤ 243.5 °C (`stage_2b_sweep` worst_T_c_at_detect; 245.7 °C at the trip
  in D-RUN's `at_trip` reading), and has 0 false trips.
- **Sense dies with no other fault**, 4 pans × at 30 / 100 / 200 s × 3 noise
  levels: (a) latches 0.4 s later in 36/36. The loop was commanding ≥ 300 W
  each time.
- **False trips: 0.** That covers the 75 benign runs, and the same 75 with the
  stage in burst mode below its floor (160 W, 20 s period, on for P/160 of
  it, 1.33 A while on and 0 A between). It also covers the fault runs before
  their fault, and the four contact-loss runs.
- **SIL C1:**
  - *C1 Current Sense Fails While Heating* (HEATING, PREHEAT): 4 rows.
  - *C1 Current-Sense Start-Up Pulse Fails* (PREHEAT): 11 rows.
  - *C1 Stuck-On Stage with Current Sense Lost While Heating*: (a), 4 rows.
  - *…, No Command*: pan at 112 °C, so stage 1 holds the command at 0; 2b
    latches in 199 rows (bound 350).
  - The legacy double-fault trace is legacy-only, and names both.
- **Unit tests:** 9 (`test_c1_units_only`). Runtime: 3 tests, plus 3 more
  under `TEMPER_INPUT_CURRENT_SENSE`.

**Changed JSON.**
- `runaway-checks.json` gains the `current_sense` block, the burst and
  sense_latent rows, and `rtd_fail_code` (D-OPEN).
- Legacy false trips are still counted on the 75 non-burst runs. The 2b
  sweep now also sees the 75 burst runs. Every variant that false-tripped
  before trips about twice as often (6 → 12 or 13, 3 → 6): holds of 5 s, of
  10 s with a 10–20 s window, and of 20 s with a 20 s window. Every variant
  that had no false trip still has none, 20/5/2 and its half-hold 10/5/2
  included.
- `max_identical_codes` at 0.3 LSB rises from 88 to 93 (burst runs), still
  under 250.

**Limits.**
- (a) looks only while the command is ≥ 300 W. A sense that dies during a
  hold below 300 W waits for the next such command; meanwhile, 2b still
  stands.
- The pulse runs once per heating session.
- None of this helps when the sense and the stage fail in the same instant
  while the loop is not commanding: that case is still 2b's (open item 4).

## D-LEAK. Element-parallel Pt100 leakage: a latch, and why firmware cannot meet the 300 °C bar

**The bar's hazard definition (owner, 2026-10-16).** A leak run is
hazardous when its untripped pan temperature exceeds 300 °C *at any time*,
transient overshoot included (`leak_checks.hazardous()`: the unrounded first
crossing, `t_T_c_over_300_s`). It was the steady T_c (mean of the last
100 s) above 300 °C. The peak rule adds 42 runs that overshoot and settle
below 300 °C: 300 Ω 1, 721 Ω 7, 966 Ω 3, 1.29 kΩ 1, 1.73 kΩ 1 and 29 of the
36 runs at 2.32 kΩ (peak up to 304.2 °C, steady ≤ 299.8 °C; two peak at
300.0x °C, which the 0.1 K-rounded `T_c_max` hides). With the rim limit in
the loop (`leak-checks.json`):

| | Steady rule (to 2026-10-15) | Peak rule (from 2026-10-16) |
|---|---|---|
| Hazardous runs | 235, 300 Ω–1.73 kΩ | **277**, 300 Ω–2.32 kΩ |
| Latched before T_c passes 300 °C | 59 | **69** |
| Latched after | 176 | 204 |
| Never latched | 0 | **4** (2.32 kΩ, Δ 46 K, cold bead, ramp onsets; peak 300.3–302.2 °C) |
| Largest hazardous leak; 10 MΩ margin | 1.73 kΩ; 5773× | **2.32 kΩ; 4311×** |
| Next sample (not hazardous) | 2.32 kΩ | 3.11 kΩ (peak 290.8, steady 286.2 °C) |

The gate's recorded status moved with it (EXPECTED_BEFORE_300_MIN 59 → 69,
EXPECTED_NEVER_MAX 0 → 4; cold_soak.py EXPECTED_INDEP_NOMINAL likewise): a
stricter definition re-recorded, the same ratchet. D-RIMLIM, D-SOAK, open
items 10–11 and `../leak-barrier/` carry the peak-rule numbers.

*Superseded in part by D-RIMLIM:* the setpoint-relative rim limit latches 69
of the 277 hazardous runs before 300 °C (peak rule). The bar is still not
met. The numbers below are this rule's alone, as first recorded under the
steady rule, and are not regenerated.

**The hazard.** A leak in parallel with the element reads low and is an
ordinary in-range resistance to the MAX31865 (`../pcb/DECISIONS.md` D6). The
loop holds the reading at the setpoint and the pan runs hot.

**The bar (owner).** Every leak whose untripped pan temperature would
exceed 300 °C (at any time, from 2026-10-16; steady before) must latch
before the pan first exceeds 300 °C.

**Rule.** `components/control/pan_leak_check.{c,h}`, run by
`main/pan_control.c`, latches FAULT_PROBE_LEAKAGE (new code, label "PROBE
LEAKAGE"). It goes through `state_machine_report_latched_fault()`: hardware
cut, not software-clearable.
- A *leak cycle* is a cross-check suspect (D-XCHK) followed by D1's
  PROBE_PASSED: the reading sits 25 K below the rim and D1 finds the contact
  intact.
- Two consecutive cycles latch when, at the second suspect:
  - it is within 120 s of the first;
  - the rim reads no more than 5 K lower;
  - the Pt100 reads no more than 2 K higher.
- A D1 LOST or RESTORED, or a suspect without a VALID rim reading, restarts
  the count.

Why these values:
- **One cycle is what food does.** 22 of the 548 benign runs below raise
  exactly one suspect, all food, each ending in PROBE_PASSED. A one-cycle
  rule would latch on all 22. No benign run raises a second suspect.
- **120 s.** A leak repeats the cycle about every 48 s (the 30 s
  cross-check hold plus the 18 s probe; D1's 30 s hold-off runs under the
  next hold). 120 s is 2.5 cycles.
- **The qualifiers.** A leak keeps the reading flat or falling and the rim
  flat or rising, while a benign disturbance resolves: the reading recovers
  or the rim cools. 2 K is the cross-check's own rise limit (D-XCHK). Since
  no benign co-sim run reaches a second suspect, the qualifiers are
  exercised only by the unit tests.

**Evidence** (`leak_checks.py` → `leak-checks.json`, gated in `run.sh`
step 3c). The setup:
- the xcheck_cosim plant and loop, every latch passive;
- 13 leaks from 300 Ω to 10 kΩ × 4 pans × glass Δ {12, 46} K × bead corner
  {hot, cold} × onset {step, conductance ramp over 120 s, over 600 s}: 624
  runs;
- frying pans at a 250 °C final setpoint, 1800 s.

Results:
- **Hazardous** (untripped steady T_c > 300 °C): 235 runs, all at 300 Ω –
  1.73 kΩ. Steady T_c reaches up to 819.5 °C (300 Ω, the plant's
  uncontrolled ceiling). 2.32 kΩ peaks at a steady 299.8 °C.
- **The bar is not met.** 7 of 235 latch before T_c first exceeds 300 °C: 6
  by the leak check and 1 by the rim over-range fault, all with a ramp
  onset. By onset that is step 0/84, 120 s ramp 3/80 and 600 s ramp 4/71.
- **219 latch after T_c passes 300 °C:** the first latch comes 30.8–367.3 s
  later, at T_c up to 474.2 °C. The rim over-range fault is the first latch
  in 188 hazardous runs and the leak check in 38 (the leak check latches at
  T_c 283.8–373.1 °C).
- **9 never latch:** 1.73 kΩ at Δ 46 K, cold bead corner, all three frying
  pans, every onset, at a steady 318.7–318.9 °C. This is the largest
  uncaught leak: **1.73 kΩ, steady 318.9 °C.**
- **No rule on these signals can meet the bar.** Any such rule needs a
  cross-check suspect, and 208 of the 235 hazardous runs have none before
  T_c passes 300 °C (step 83/84, 120 s 59/80, 600 s 66/71). The reasons:
  - The cross-check needs the reading 25 K below a rim that reads the glass.
    The glass sits 12–46 K below the pan, and the bead is ±10.2 K at 250 °C
    (D-XCHK). So with the reading held at a 250 °C setpoint, the first
    suspect can need a pan up to 250 + 25 + 46 + 10.2 ≈ 331 °C, and only
    50 K separate the highest setpoint from 300 °C.
  - The suspect also needs a reading that does not rise for 30 s.
- **The CR-5 hardware rim trip is no guaranteed backstop either.** Its band
  is 262.3–288.1 °C on the glass. The glass reaches the band's top before
  T_c passes 300 °C in 0 of 235 hazardous runs, and its low edge in 13.
- **Moderate leaks are firmware-invisible.**
  - ≥ 4.16 kΩ (steady T_c ≤ 276.8 °C): no suspect and no latch in any run.
  - 3.11 kΩ (the owner's ~3 kΩ: steady up to 286.2 °C): latched in 9 of
    48.
  - 2.32 kΩ (up to 299.8 °C): latched in 13 of 48.
  - The water pot never exceeds 115.6 °C (it boils). The leak check
    latches 31 of its 156 leak runs, which are real leaks but not hazards.
- **D1 sometimes takes a leak for a lifted pan.** A leaky reading falling
  under power can look like a lift, and D1 then zeroes the power until a
  retry probe passes (47 of 624 leak runs; `d1_lost` per leak in the JSON).
  That is why the same leak is not hazardous in every run. It does not
  latch.
- **Benign: 0 leak latches in 548 runs** (gated). The runs are xcheck's 28,
  and b5-style sets through the glass and rim model (5 seeds × Δ × corner):
  nominal 80, food 60, probe on intact contact 160, food batches every
  120 s 60, a cold pan on 200 °C glass 80, and the setpoint lowered by 60 K
  80. There were also 0 D1 LOST and 0 other latches (gated).
- **D1 probes the cross-check did not ask for do not count.** The
  contact-shift window (D-CSW) and D1's own trigger also start probes. Only
  a probe that starts at or after the suspect counts (D1's CC_EVT_SUSPECT
  while the suspect is pending). A suspect raised while another probe or
  LOST is in progress is not armed (unit test
  `test_leak_a_probe_not_started_by_the_suspect_does_not_count`).
- **SIL C1:** *C1 Pt100 Element-Parallel Leakage (HEATING)*: the pan and rim
  at 140 °C, the reading at 100 °C. It latches in 972 rows (bound 1250). The
  SIL trace limit was raised from 1000 to 2000 rows for it.
- **Unit tests:** 5 (`test_c1_units_only`).

**What the hardware and production must carry** (the firmware cannot):
1. **Hot-zone insulation ≥ 10 MΩ at 300 °C** between leads and across the
   element (`../pcb/REQUIREMENTS.md` R3.3). CAD's fused-silica 4-bore
   capillary gives about 100 MΩ at 350 °C, pending supplier confirmation
   (`../pcb/DECISIONS.md`, orchestrator rulings). 10 MΩ is 4311× the
   highest hazardous leak (2.32 kΩ, peak rule; 5773× the steady rule's
   1.73 kΩ), and reads 0.013 K low at 300 °C (100 MΩ: 0.001 K).
2. **A production hot insulation test on every cartridge:** ≥ 10 MΩ at
   300 °C, as R3.3. Leakage *across* the element cannot be measured with the
   element in circuit. A hot accuracy check covers it: at 300 °C with a
   ±0.5 K acceptance, it catches any parallel path below 252 kΩ, 109× the
   hazard, with zero measurement uncertainty; `../leak-barrier/` (T1) gives
   84 kΩ under its full masking budget.
3. **Seal-ingress qualification.** Moisture or fat entering the cartridge is
   the credible way a hot-zone leak forms. Qualify the seal with steam/damp
   heat, thermal cycling and wash exposure. Afterwards the cartridge must
   still pass the 10 MΩ at 300 °C test.

## D-RIMLIM. A setpoint-relative rim limit, and what energy, a cold soak and the coil can add

**Why.** D-LEAK's rule needs a cross-check suspect: the reading 25 K below a
rim that itself reads glass 12–46 K below the pan. With the reading held at
250 °C that is a pan up to ~331 °C. A leak holds the *reading* at the
setpoint; the glass under the rim NTC follows the *pan*. So the rim has a
ceiling set by the temperature the loop believes the pan is at, and a rim
above it is a pan hotter than the loop believes. Four candidates were
evaluated (A–D below). A is implemented; B and D do not separate a leak on
today's signals; C does, for one leak type, but needs a reference driver
that does not exist yet.

### A. The rule (`components/control/pan_rim_limit.{c,h}`)

`main/pan_control.c` runs it every control period and latches
FAULT_PROBE_LEAKAGE (the D-LEAK code and sink: hardware cut, not
software-clearable). `pan_control_rim_limit_latched()` tells it from the
D-LEAK chain.
- **Reference.** T_ref is a decaying maximum of max(setpoint, t_hat): it
  rises at once and decays toward the present value with τ_dec = 300 s. A
  lowered setpoint, a food quench or a pan lift does not pull the limit
  down under a glass that is still hot (the glass's own t63 is 18–106 s,
  study 08). It restarts with each heating session.
- **Glass envelope.** The glass under the bead is a weighted mean of the
  pan and the coil-eye air, Tg = w·T_pan + (1 − w)·T_eye. This fits both
  sources to 0.01 in w (`rim_limit.py` `envelope`, `rim-limit.json`):
  - `../cad/thermal-axisym.json` (G8, 260 °C pan, glass underside at the
    NTC radius r14.5): flat pan w = 0.955, 0.5 mm warp w = 0.830, for both
    eye states (air 130.0 and 139.7 °C);
  - study 08 (`output/temper-r33-studies/08-undrilled-glass-sensor`,
    `undrilled-thermal.json` `steady_offsets_B`; not in this tree, the six
    rows used are copied verbatim into `rim_limit.py`): w = 0.646–0.830, eye
    air 45 (low hold) to 139.7 °C (fry hold).

  The hottest benign glass for a pan at T is
  Tg_max(T) = max(0.9554·T + 0.0446·139.7, 0.6457·T + 0.3543·139.7): below
  the eye air the glass can be hotter than the pan. Tg_max is 114.1 / 149.5
  / 197.3 / 245.1 °C at 100 / 150 / 200 / 250 °C.
- **Tolerance.** The rim channel's hot stack at the comparison temperature,
  tabulated by `rim_limit.py` (`PRL_TOL_K`, gated against the header):
  the bead's hot corner scaled to pcb D5's 10.2 K at 250 °C, the rail read
  as 3300 mV when it is 3242 mV (no MCP3202 CH1 driver), and 4.53 K
  still-air self-heating. That is 11.0 / 11.2 / 13.2 / 16.0 / 19.3 K at
  100 / 150 / 200 / 250 / 300 °C. D-RIM's constant 19.1 K adds the rail's
  worst (4.37 K, near the saturation end) to the bead's worst (at 250 °C);
  at 250 °C the rail costs 1.25 K. The constant is kept as `tol_table =
  false`.
- **Limit** = Tg_max(T_ref) + tol(Tg_max(T_ref)) + margin (0 K):
  125.1 / 160.7 / 210.4 / 240.6 / 260.8 °C for T_ref 100 / 150 / 200 / 230
  / 250 °C.
- **Latch.** The rim VALID, above the limit and not falling (now ≥ the
  reading 30 s ago − 1 K) for 5 s. A rim that is not VALID restarts the
  count and the 30 s window. "Not falling" is what keeps a cooling glass
  from tripping, whatever its level: a cold pan on hot glass, a setpoint
  lowered after a long hold. A leak heats the glass.

### A. Evidence

**The sets** (`rim_limit.py` → `rim-limit.json`, run.sh step 3e; all through
the C loop, every latch passive):
- the 624-run leak sweep and the 548 benign runs of D-LEAK;
- **stress_benign, 132 runs:** the hot side of every model input:
  - glass at the benign envelope: w 0.955 and 0.646, eye at 139.7 °C;
  - the rim's hot stack: bead hot, v3v3 3242 mV, +4.53 K self-heating;
  - τ_g 18 / 60 / 106 s;
  - kinds: an 1800 s hold at 250 °C, the setpoint lowered 250 → 150 °C at
    900 s, a cold pan on glass at 245.1 °C, a preheated 250 °C pan on cold
    glass, food, and food batches; 4 pans;
- **stress_leak, 234 runs:** the leak sweep's frying pans at the cold side:
  - glass at the leak envelope (w 0.708, eye 45 °C), and flat (w 0.955)
    with a 45 °C eye;
  - the cold stack (bead cold, 3367 mV), τ_g 106 s.

**Trade-off curve** (offline on 0.5 s traces of the same runs; τ_dec 300 s,
"not falling" on; the counts are hazardous runs latched before T_c first
exceeds 300 °C, of 277 under the peak rule, `rim-limit.json` `curve`):

| Margin (K) | Tolerance table | Constant 19.1 K | Never latched (table) | False latches, 548 benign | False, 132 stress |
|---|---|---|---|---|---|
| −10 | 115 | 89 | 4 | 0 | 56 |
| −5 | 91 | 69 | 4 | 0 | 55 |
| −2.5 | 78 | 55 | 4 | 0 | 42 |
| −1 | 76 | 55 | 4 | 0 | 28 |
| **0 (chosen)** | **70** | 51 | **4** | **0** | **0** |
| +1 | 67 | 48 | 4 | 0 | 0 |
| +2.5 | 64 | 43 | 22 | 0 | 0 |
| +5 | 52 | 37 | 22 | 0 | 0 |
| +10 | 39 | 26 | 22 | 0 | 0 |

(Steady rule, first recorded: 60 of 235 at the chosen variant, 0 never.)
- **The constant stack** never latches 22 runs at margin 0. The four the
  chosen variant never latches are 2.32 kΩ at Δ 46 K with a cold bead,
  peaking 300.3–302.2 °C: no margin within the benign envelope reaches them.
- **"Not falling" is necessary.** Without it, margin 0 false-latches 30 of
  the 548 benign runs (the cold pan on 200 °C glass) and 24 of the stress
  runs.
- **τ_dec.** 60 s false-latches 3 stress runs at margin 0 (the lowered
  setpoint with τ_g 106 s); 120 and 300 s none.
- **Closest approach.** At the chosen variant the stress set comes within
  0.54 K of the limit, sustained and not falling. The benign 548 come no
  closer than 16.9 K below it. The envelope is the worst case by
  construction, so the stress set sits on the limit; −1 K already trips 28.

**C in the loop** (`leak_checks.py` → `leak-checks.json`, step 3d, gated):

| | Before (D-LEAK, steady rule) | After (D-RIMLIM, steady rule) | After (D-RIMLIM, peak rule) |
|---|---|---|---|
| Hazardous runs latched before T_c passes 300 °C | 7 / 235 | 59 / 235 | **69 / 277** |
| — step / 120 s ramp / 600 s ramp | 0/84, 3/80, 4/71 | 27/84, 18/80, 14/71 | 31/93, 18/92, 20/92 |
| Latched after 300 °C | 219 (T_c ≤ 474.2 °C, 30.8–367.3 s after) | 176 (T_c ≤ 431.1 °C, 0.0–329.0 s after) | 204 (T_c ≤ 431.1 °C, 0.0–329.0 s after) |
| Never latched | 9 | 0 | **4** |
| Largest never-latched leak | 1.73 kΩ, steady 318.9 °C | none | 2.32 kΩ, peak 302.2 °C, steady 299.5 °C |
| First latch, hazardous runs | rim over-range 188, leak chain 38 | rim limit 234, leak chain 1 | rim limit 272, leak chain 1 |
| False latches, 548 benign | 0 | 0 | 0 |

- **The gate.** `leak_checks.py` holds coverage at ≥ 69 and never-latched at
  ≤ 4 (EXPECTED_BEFORE_300_MIN, EXPECTED_NEVER_MAX; 59 / 0 under the steady
  rule). The bar status stays `not_met`.
- **By glass offset.** Δ 12 K: 66 of 141 before 300 °C. Δ 46 K: 3 of 136.
- **By leak** (latched before 300 °C / hazardous): 300 Ω 7/36, 402 Ω 5/36,
  538 Ω 6/36, 721 Ω 7/36, 966 Ω 13/36, 1.29 kΩ 11/32, 1.73 kΩ 12/36,
  2.32 kΩ 8/29.
- **The largest leak that is not always caught before 300 °C** is the
  largest in the sweep, 300 Ω: a step to a steady 819.5 °C. It passes
  300 °C before the glass, with its 18–106 s lag, can follow.
- **At the leak envelope** (stress_leak: warped pan, cool eye, cold stack,
  τ_g 106 s), 3 of 137 latch before 300 °C (0/116 under the steady rule).
  25 of 137 never latch on the existing rules, and 21 still do not with the
  rim limit (22 and 18 of 116 under the steady rule).

**Why the bar is still out of reach.** At a 250 °C setpoint the benign glass
can reach 245.1 °C, and the rim can read 16 K above that. A leak that takes
the pan to 300 °C under a warped pan and a cool eye leaves the glass at
225.4 °C (0.708·300 + 0.292·45), and the rim can read 9–11 K below it.
- The two ranges overlap by about 46 K.
- The glass also lags the pan by 18–106 s, which a fast leak outruns.
- No rim threshold separates them at 250 °C. The rule is strongest at the
  lower setpoints a leak passes through first.
- Benign runs no closer than −0.54 K to the limit show that margin cannot be
  traded for coverage without false latches.

**Firmware tests.**
- `test_c1_units_only`: 6 new tests (41 in all). They cover the limit
  values, the latch after the sustain, a steady rim 0.3 K under the limit
  for an hour, a falling glass above the limit (a cold pan on 260 °C glass,
  a setpoint lowered under a hot glass), the fall-window and sustain
  requirements, and parameter rejection.
- **SIL C1**, 2 new scenarios with mechanism `rim-limit`:
  - *C1 Rim Above the Setpoint Envelope (HEATING)*: pan and rim 140 °C over
    a 100 °C reading. 166 rows (bound 300).
  - *(PREHEAT)*: pan 150 °C over an 85 °C reading, the machine still in
    PREHEAT. 267 rows (bound 400).
  - The coverage gate is now 27/27 C1 pairs (adds FAULT_PROBE_LEAKAGE from
    PREHEAT) and 22/22 mechanism cells.
  - **The D-LEAK chain scenario changed.** Its 140 °C rim over a 100 °C
    reading is now the rim limit's case, which latches first. The chain's
    trace now holds the rim at 105 °C over a reading sagging to 75 °C
    (-0.43 K/s, under D1's trigger). That is 30 K for the cross-check and
    under the 125.1 °C limit. 901 rows (bound 1250). The mechanism check
    now also fails if the rim limit latched instead.

### A. CR-5: the hardware rim trip (a PCB change request, written up only)

`rim-limit.json` `cr5`: the benign glass maximum over all the sets above is
246.5 °C. The band's low edge, 262.3 °C, is 15.8 K above it.

| Lowered by | Band (°C) | Hazardous trip at band top before 300 °C | Benign margin to band low |
|---|---|---|---|
| 0 | 262.3–288.1 | 0 / 277 | 15.8 K |
| 4 K | 258.3–284.1 | 0 | 11.8 K |
| 8 K | 254.3–280.1 | 9 | 7.8 K |
| 12 K | 250.3–276.1 | 11 | 3.8 K |
| 16 K | 246.3–272.1 | 16 | −0.2 K |

(Peak rule; under the steady rule 0 / 0 / 6 / 7 / 11 of 235.)

**Recommendation: lower the trip by about 8 K.** Change the divider's 86.6 k
to 76.8 k (E96). The nominal moves from 275.6 to 267.8 °C, and the band to
about 254.5–280.3 °C.
- **Gain.** Small: 9 of 277 hazardous runs (peak rule; 6 of 235 steady)
  trip before 300 °C instead of none. The trip stays independent of firmware, and leaves
  7.8 K over the benign envelope.
- **Condition.** pcb D6's bench condition must tighten with it. Bench T3's
  rim log under a 250 °C hold must stay ≤ 244.5 °C (the new band low − 10 K)
  instead of ≤ 252 °C.
- **Don't go further.** Lowering by 12 K leaves 3.8 K and buys two more runs;
  16 K overlaps the benign envelope.

### B. Energy plausibility: does not separate (`leak_alternatives.py` → `leak-alternatives.json`)

- **Compression.** A hazardous leak (peak rule) compresses dReading/dT_true
  at a 250 °C reading to 0.08 (300 Ω) – 0.83 (2.32 kΩ); 0.77 at 1.73 kΩ,
  0.70 at 1.29 kΩ.
- **The plant gain a = η/C** spans 6.8× over the three modelled frying pans
  with η 0.82–0.92 and a food load alone. The firmware prior bounds span
  100×. A leak looks like a heavier pan: the modelled food load alone moves
  a frying pan's a to 0.21–0.38× of the bare pan, as far as the
  compression of every leak down to about 540 Ω (0.37).
- **Hold power.** Holding the same pan at 300 instead of 250 °C costs
  1.21–1.41× the power. The honest 250 °C hold already spans 1.67× over
  three modelled pans (247–413 W at η 1), and real pan sizes spread it
  further. The firmware has only commanded power, with η unknown.
- **The rim's rise per joule against the Pt100's.** The rim follows the pan
  with w 0.65–0.96, a wider spread than the compression of the leaks that
  matter (0.83 at 2.32 kΩ).
- **Verdict.** Nothing observable separates a leak from a heavier or less
  efficient pan without a per-pan reference. A within-session drop of the
  identified a when a leak forms mid-cook is real, but adding food does the
  same.

### C. Cold-soak plausibility: implemented as D-SOAK; with CR-8 the reference reads room temperature

This section first evaluated C on paper, before a heatsink NTC driver existed
(a 12.2 K budget on "GPIO3 / ADC1_CH2"; the board has the NTC on GPIO6 /
ADC1_CH5). Both now exist: D-HSNTC (the driver) and D-SOAK (the check, its
threshold, 19.4 K since the CR-8 divider (zapote C45), the benign sets and
the coverage, through the C).
`leak_alternatives.py` keeps the closed-form view at 35 °C against the
`hs-ntc.json` threshold:
- **A temperature-independent leak** reads low by 12.8 K at 2.32 kΩ, the
  largest hazardous leak under the peak rule, at 25 °C (11.0 K at 5 °C,
  14.2 K at 40 °C), and by 16.8 K at 1.73 kΩ; more at every lower resistance.
- **An Arrhenius leak** R(T) = R_300·exp(Ea/k·(1/T − 1/573 K)), equal to
  the hazardous 2.32 kΩ at 300 °C: at 35 °C it reads 13.7 K low even
  temperature-independent, under both the 19.4 K threshold and the
  rail-measured 16.9 K, so the closed form misses it at any Ea. The largest
  leak caught at 35 °C is 1.60 kΩ (1.86 kΩ rail-measured).
  Pre-C45 these were Ea 0.020 / 0.043 eV and 2.47 / 3.67 kΩ against the
  12.9 / 8.8 K thresholds, which held only in a warm room. Conduction that
  only conducts hot is invisible to C.
- **What changed from the paper version:** the heatsink channel saturated
  below 28.6–35.7 °C before C45, so C ran only in a warm room. With the CR-8
  divider it runs from 5 °C up, at a higher threshold set by the cold end
  (D-SOAK table).

### D. Coil-impedance pan temperature: feasibility only, no signal today

- **Today's measurements.** `firmware/components/power/` (`tank_freq.c`,
  `n21_binding.c`) is not in this tree; it lives on the power-stage
  branches. In this tree nothing on the target measures tank frequency,
  current or R_eq. Bus current is a stub (+INF). `pll_control.c` never
  registers its capture callbacks, and resonance is a constant 37580 Hz.
  `pan_detect` is never initialised. The control loop uses commanded power.
- **Sensitivity** (`../../temper-mining-r3/impedance-sensitivity.json`,
  FINDINGS §3; an upper bound, because μ(T) opposes ρ(T)):
  - carbon steel: dR_eq/R 0.09–0.24 %/K, so 4–11 K resolution at 1 %
    repeatability;
  - cast iron and 430-clad: 0.03–0.09 %/K, so 11–30 K.

  R_eq is weighted over the heated annulus, which can sit up to 29 K from
  the C1 contact point (sensor-r2). The literature's R/L estimation is good
  to 7.1 % / 2.9 % (Energies 15:1294), far worse than the 1 % this needs.
- **Detectable leaks.** The pan reaches 300 °C at 50 K over a 250 °C
  reading: 4.5–12 % of R_eq on carbon steel, 1.7–4.7 % on cast iron and
  430. At 1 % repeatability with a 2× detection margin (2 %), that is
  caught before 300 °C on carbon steel, and only on the most sensitive
  cast iron or 430. At steady state every hazardous leak holds the pan
  ≥ 68 K over the reading under the steady rule (1.73 kΩ: 318.4 °C at a
  250 °C reading), ≥ 2.3 % even at cast iron's low end. Under the peak rule
  the 2.32 kΩ leak settles at 285.1–299.8 °C (`leak-checks.json`), 35–50 K
  over the reading: 1.1–1.5 % on cast iron's low end, under the 2 % margin.
  So D could close the never-latched gap on carbon steel, but not on cast
  iron and clad, nor the before-300 °C gap there.
- **Recommendation.** Once the power stage reports P and I per period
  (needed by D-ISENSE anyway), log R_eq = P/I² against the Pt100 reading on
  the bench. Adopt it only if a per-pan baseline, learned in the first
  minute, repeats to ≤ 1 % across a hold. Mind E.G.O. US10085303B2 and
  Whirlpool US8530805B2 (mining-r3 RECOMMENDATIONS). Not built here.

### Bench measurements this needs (`../bench/`)

1. **The glass envelope and lag** under the rim NTC: a thermocouple bonded to
   the glass underside beside the bead, and the rim channel, logged against
   the pan. Cover a flat and a 0.5 mm-warped pan, holds at 100 / 200 /
   250 °C at low and full coil current, and a 100 → 250 °C step.
   - This measures w, T_eye and t63, which replace the 0.955 / 0.646 /
     139.7 °C envelope and the 60 s τ_g assumption.
   - The logger and rig exist (`bench/logger.py`, `RIG.md`; bench T3 already
     logs the rim under a 250 °C hold). It needs a second thermocouple
     channel on the glass.
2. **The bead's dissipation constant on the glass** (D-RIM, open item 2).
   The 4.53 K still-air self-heating is in the tolerance table; bearing on
   the glass it is smaller, and the measured value would lower the limit.
3. **The heatsink NTC against ambient after a soak** (for C): D-SOAK bench
   item 1, with the rest of the cold-soak list there.

## D-CSW. Contact-shift window: re-estimate the contact after an abrupt change

Open item 9: a mid-cook h_c drop made the fixed-contact KF read low by the
change in its static offset, and the loop over-heated the pan by up to
13.09 K. Coil power cannot identify absolute h_c (sensor-r2), but it can
identify a **step**: the cartridge re-settles in 0.2–3.5 s while the pan
cannot change its rate unless the power changes.

`contact_shift.{c,h}` (Python reference `../robustness/shift_kf.py`):
- **Trigger** (D1 NORMAL, no sensor fault, ≥ 30 s after start, > 20 s after
  the last window): the reading's slope over the last 1.5 s minus its slope
  over the 3 s before is below −0.6 K/s (DOWN), or above +0.6 K/s while the
  model contact is below 0.95 h_nom (UP); and no 1 s block of applied power in
  the last 8 s is more than 10 % P_max below (DOWN) / above (UP) the mean of
  the 8 s before. A power change explains a change of rate; a contact change
  does not.
- **Window:** the KF state from 2.5 s ago is replayed as a 5-state EKF
  [T_pan, v, T_cap, T_el, ln G] in double. The pan is pinned (T from the
  snapshot, sd 0.1 K; v from the reading slope over the 5 s before, sd
  0.03 K/s). ln G (sd 1.0) is clamped to [ln G_floor (150 W/m²K), ln G_old]
  for DOWN, [ln G_old, ln G_nom] for UP. While open, its T̂ is the loop's T̂.
  The base KF runs on underneath.
- **Close:** ESCALATE when ln G reaches the floor (a fall faster than any
  partial contact: loss or real cooling). The loop requests a D1 probe and
  keeps the old contact. ACCEPT after ≥ 4 s (8 s when the loop was steady at
  its setpoint), with ln G settled (< 0.04 over 2 s), a change ≥ 25 % and
  sd ≤ 0.2 (or an UP estimate at nominal). The estimator takes the window's
  state and the contact exp(ln G − 1 sd): the lower side, because a contact
  assumed too good reads low and over-heats. REVERT at 12 s or when the gate
  drops.
- **Loop wiring** (`pan_temp_loop.c`): the gate is D1 NORMAL and no fault;
  "steady" is sp_eff ≥ SP and |T̂ − SP| < 3 K for 10 s. ESCALATE requests a
  D1 probe. D1 RESTORED (a new seating after a loss) resets the contact to
  nominal. Any window event ends the a-identification phase.
- **Cost:** ~5 kB of state, double math only inside a window (≤ 12 s).

Evidence (`../robustness/DECISIONS.md` R-A): four candidates in the Python
screen (power cap, an immediate D1 probe, a power-frozen window, the window).
Only the window fixes the static error. In the C co-sim, 64 steps per gain
mode, before → after:
- B2: 36/36/39 → 64/64/64;
- worst overshoot: 12.83/13.14/13.14 → 4.95/5.00/4.72 K;
- B1 (3 K): 11/11/10 → 49/49/45;
- D1 probes: 31/32/30 → 1/2/1.
The cases nearest the 5 K bar are water-pot steps the window cannot see; they
are unchanged.

Effects on the gated co-sim (`cosim-results.json`, all bars still pass):
- **Loss:** T_c − SP 11.65–12.04 → 6.72–6.94 K, because T̂ no longer chases
  the falling reading. The suspect time moves from 2.5–2.6 to 2.7–2.9 s:
  0.1 s margin to the 3 s bar in id_measured.
- **Original h_step cases:** 1000 → 300 overshoot 9.88–13.09 → 1.93–4.21 K.
  The 300 → 3000 cases still overshoot 5.65–7.08 K, unchanged: that is the
  first ramp at h_c 300 from the start, before the step.
- **Stress:** B1 8/12 → 6–7/12, reported. A window opened without a contact
  change on carbon steel at 3000 W/m²K and, in id_measured, accepted
  585 W/m²K: the hold ran 3.66 K cool. A false DOWN acceptance errs cool.

The co-sim shadow is now `shift_kf.ShiftKF`, fed C's gate and steady flag.
Parity: worst 1.3e-4 K rms here, 2.2e-4 K rms in `hc-cosim.json`, against a
bar of 0.05 K. Unit tests in `test_pan_temp_loop_only`:
- an abrupt drop is accepted within 30 % of the truth;
- a power cut vetoes the trigger;
- contact loss escalates;
- the gate reverts the window, and reset returns the contact to nominal.

## D-LPG. Latent-plateau guard with an energy budget, in the rate PID

Water trapped in the bore boils under the pan centre and pins the reading
near 100 °C. The PID then holds full power while the annulus runs away. In
the Python screen, 5 of 54 water cases exceeded SP + 15 K (up to +27 K).
Before this change the runaway supervisor latched only after that
(`../robustness/hc-cosim.json` before).

`pan_rate_pid.c`:
- **Condition:** T̂ in 95–118 °C, the least-squares slope of the previous
  100 T̂ within ±0.15 K/s, and SP − T̂ > 5 K.
- **Action:** limit the PID to 0.2 K/s / a, once the budget is spent.
- **Budget:** a·E ≥ SP − T̂. E is the PID output energy since T̂ entered the
  band from below. That is the energy to take the whole pan to the setpoint,
  enough to boil the pocket off by heating the pan around it.
- **Entering from above:** the reading fell into the band, so the pan was
  hotter than T̂. There is no budget.

Without the budget, the plain cap held a clad pan at ~100 °C for 480 s with
the pocket intact (hold −105 K). With it, the worst under-temperature is
−6.64 K.

Results, water cases, C co-sim:
- 54/54 stay ≤ SP + 15 K in every gain mode, worst SP + 6.05 K;
- before this change: 49–51/54, worst SP + 29.14 K;
- 0 D1 latches and 0 supervisor latches.

The pan mean still reaches SP + 22 K; the B5 line is on T_c. A deglaze above
105 °C gets the budget, then the cap, until the liquid boils off. Both are
open items in `../robustness/DECISIONS.md` R-C. The design, nominal, food,
stress and probe-on-intact runs are unchanged by the guard.

## D-HSNTC. Heatsink NTC driver, from the zapote/controller circuit

**The circuit** (zapote/controller, read only, at `controller-c1-crs`
467917c38, DECISIONS C45; `hs_ntc.py --verify-board-ref controller-c1-crs`
re-reads every part below from the .ato sources, the PCB and C45 and passes):
- `elec/src/thermal_block.ato` ThermalSenseUnit: `hs_fixed` 10 kΩ 1 %
  (RC0603FR-0710KL) from v3v3 to HS_SENSE, the NTC (external lug
  NTCALUG01A104GA) from HS_SENSE to ground, `hs_filter` 100 nF. A TLV3201
  hot comparator (HS_HOT, 98.3–104.6 °C) and a TLV9031 open comparator
  (HS_OPEN: HS_SENSE above v3v3 · 100 k / 101.21 k, i.e. colder than
  −16.1 °C) OR into HS_FAULT, a hardware latch input.
- `elec/src/controller.ato`: 10 kΩ / 100 nF into the TLV9062 follower U6B,
  then **the CR-8 divider (C45)**: `r_hs_adc` 1.00 kΩ 0.1 % 25 ppm/K
  (RT0603BRD071KL) from the follower to HS_ADC, `r_hs_adc_bot` 5.90 kΩ
  0.1 % 25 ppm/K (ERA-3AEB5901V) from HS_ADC to ground, `c_hs_adc` 100 nF
  at HS_ADC; **`mcu.IO6 ~ hs_adc`, so GPIO6 = ADC1_CH5.** The PCB has R89 /
  R90 / C67 and U4 pad 6 on HS_ADC and nothing else. GPIO3 is the blower
  tach (`mcu.IO3 ~ fan_tach`); the legacy `temper_pins.h` name
  `ADC_CHANNEL_NTC` = GPIO3 / ADC1_CH2 is wrong for this board (open item 13).
- **Gain** 5.90 / 6.90 = **0.855072**, band 0.854824–0.855320 from the
  0.1 % tolerances and **0.854421–0.855722** with 25 ppm/K over the board's
  −40…85 °C. `hs_ntc.py` recomputes all three from the parts and gates them
  against C45's printed values; the budget uses the wider band.
- zapote DECISIONS C13: "values above ATTEN3's 2.9 V occur only cold or
  open"; C32: the firmware heatsink trip is 95 °C.

**Pre-C45** (kept as a reported row, `hs-ntc.json` `pre_c45`): 100 Ω /
100 nF and no divider, gain 1. The node was above ATTEN3's 2900 mV below
28.64 / 32.17 / 35.72 °C (v3v3 3.242 / 3.300 / 3.367 V), so the channel was
SATURATED at most room temperatures and the cold-soak check ran only in a
warm room (threshold 12.9 K then). That board will not be built. Its
cold-soak results stay in `cold-soak.json` at 75e512eab and are no longer
rerun.

**The R-T table.** The NTCALUG01A data sheet (Vishay doc 29092, rev
14-Jan-2026, sha256 a14f8704…189b) has no table: its ordering line gives
NTCALUG01A104GA as 100 kΩ ± 2 %, B25/85 4190 K ± 1.5 %. 4190 K ± 1.5 % is
Vishay material D, curve 11 (NTCLE100E3 data sheet, doc 29049, rev
07-May-2025, sha256 f9d61537…c9cb, p. 4), and the table is that document's
p. 12 NTCLE100E3104 column, −40 to 150 °C in 5 K steps, with its "dR/R due
to B tolerance" column. The power-stage branch's `thermal_mgmt.c` (44cf184a7)
uses the same curve for this part. `hs_ntc.py` holds the table and checks it:
- material D's own A1–D1 polynomial: within 0.027 K over the table (the
  4-digit rounding);
- B25/85 from the table: 4190 K;
- `--verify-pdf ntcle100.pdf`, `--verify-lug-pdf ntcalug01a.pdf`,
  `--verify-esp-pdf esp32-s3_datasheet_en.pdf` re-extract the column, the
  ordering line and Table 5-6 with pdftotext. All three pass (run
  2026-10-15 on the files with the sha256 above; `run.sh` runs `hs_ntc.py`
  without the PDFs or the board ref).

It writes `firmware/components/sensors/hs_ntc_table.h` (deterministic) and
`hs-ntc.json`.

**The driver** (`components/sensors/hs_ntc.{c,h}`, the structure of
`rim_ntc.c`):
- hardware only through `hs_ntc_hal_t` (`read_pin_mv(atten)`,
  `read_v3v3_mv`), so host tests use a mock; `hs_ntc_board.c` binds it to
  `hal_adc` on ADC1_CH5 with the per-channel calibration the rim uses;
- each 100 ms period (`hs_ntc_poll`): 8 samples, trimmed mean, the CR-7
  attenuation rule on the pin voltage with 30 mV hysteresis and the clip
  re-read; node = pin / `adc_gain`; R from the v3v3 ratio; T from the table
  (1/T linear in ln R; leave-one-out over 10 K 0.029 K); a 1 s filter;
- **`adc_gain` is `HS_NTC_ADC_GAIN` = 0.855072** in `hs_ntc.h`, the
  driver's default. That header is the single source: the zapote board is
  the only target, the rest of the driver's board numbers (10 k pull-up,
  2900 mV top) already live in its defaults, and `hs_ntc.py` gates the
  define against the parts. It is not a `config.yaml` entry: a
  `board_derivation: true` constant there must be checked by
  `scripts/check_firmware_board_contract.py`, whose only board is the legacy
  `pcb/temper.kicad_pcb` (no HS_ADC divider). See the board contract below.
- **VALID** with the pin inside ATTEN3's calibrated range and T in the
  table: **from −40 °C up at every corner.** The pin's highest value, at
  −40 °C with the NTC +2 % and its B column, the pull-up low, the rail at
  3.367 V, +2 mV of offset and the gain high, is 2.876 V (C45: 2.877 V with
  β +1.5 % and 1.6 mV); with the NTC open (node at the rail) it is at most
  2883 mV.
- **SATURATED** is left for readings the intact divider gives only at its
  extremes: the pin at or above 2900 mV (the ADC's own +50 mV error, at a
  sink colder than −13.7 °C at the worst corner) or a reading colder than
  the table (an open sensor, which HS_OPEN latches in hardware). `t_c` is an
  upper bound from the pin less `HS_NTC_SAT_MARGIN_MV` (55 mV: ADC 50, gain
  band 2.2, offset 1.7) at the rail contract maximum when the rail is not
  measured. (Before this change a SATURATED reading with a gain below 1
  computed R = ∞ and returned NAN, which the interlock read as +INF.)
- **FAULT**, latched until `hs_ntc_init()`: SHORT (node < 0.25 V for 3
  periods), OVER_RANGE (hotter than 150 °C for 3 periods), ADC (10 failed
  periods) and, new, **DIVIDER** (below).
- **The rail.** MCP3202 CH1 (the LM4040A25 reference) is the board's rail
  measurement; `read_v3v3_mv` is its reading (`rail_adc.c`, D-RAIL) when
  MEASURED, and 3.300 V (`rail_nominal`) when the rail is unknown. With the
  divider the rail error is largest at the cold end, where the node is near
  the rail: assumed 3.300 V it is 7.9 K at 5 °C and 4.0 K at 25 °C (rail
  low); measured, the reading's own error (1.33 % full range) costs at most
  8.6 / 3.4 / 0.71 K at 5 / 25 / 95 °C either way (`hs-ntc.json`
  `channel.rows[].rail_measured_K`; 14.7 / 5.3 / 1.06 K assumed, rail high).
  The cold soak uses the soak-band figure (D-RAIL, D-SOAK).

**Accuracy** (`hs-ntc.json` `channel.rows`; first-order terms in K, the ADC
at its Table 5-6 error for the attenuation the pin calls for; "corner" is
every heatsink error at its limit at once, rail unmeasured, read back
through the driver's arithmetic; "—" = the corner reads below the table):

| T | node / pin | atten | pin mV/K | ADC | tolerance | gain band | SAR | rail (3.242 / 3.367 V) | corner high / low |
|---|---|---|---|---|---|---|---|---|---|
| −40 °C | 3291 / 2814 mV | 3 | 0.52 | 97.0 K | 1.17 K | 4.16 K | 6.19 K | +33.5 / — | +47.3 / — |
| 0 °C | 3206 / 2741 mV | 3 | 4.11 | 12.2 K | 0.75 K | 0.51 K | 0.78 K | +9.5 / −21.4 K | +18.1 / — |
| 5 °C | 3179 / 2718 mV | 3 | 5.09 | 9.8 K | 0.69 K | 0.41 K | 0.63 K | +7.9 / −14.7 K | +15.7 / — |
| 15 °C | 3106 / 2656 mV | 3 | 7.54 | 6.6 K | 0.57 K | 0.27 K | 0.42 K | +5.6 / −8.3 K | +11.8 / −24.7 K |
| 25 °C | 3000 / 2565 mV | 3 | 10.66 | 4.7 K | 0.44 K | 0.18 K | 0.30 K | +4.0 / −5.3 K | +9.0 / −13.8 K |
| 35 °C | 2855 / 2441 mV | 3 | 14.27 | 3.5 K | 0.62 K | 0.13 K | 0.22 K | +2.9 / −3.6 K | +7.3 / −9.6 K |
| 50 °C | 2555 / 2185 mV | 3 | 19.73 | 2.5 K | 0.91 K | 0.08 K | 0.16 K | +1.9 / −2.3 K | +5.8 / −6.8 K |
| 80 °C | 1748 / 1495 mV | 2 | 24.21 | 0.41 K | 1.53 K | 0.05 K | 0.13 K | +1.1 / −1.3 K | +3.7 / −5.5 K |
| 95 °C | 1340 / 1146 mV | 2 | 21.83 | 0.46 K | 1.87 K | 0.04 K | 0.15 K | +0.9 / −1.1 K | +4.0 / −4.0 K |
| 125 °C | 718 / 614 mV | 0 | 13.46 | 0.37 K | 2.60 K | 0.04 K | 0.24 K | +0.8 / −0.9 K | +4.8 / −4.7 K |

The hot end, where the interlocks
act, is better than before: 80 °C now reads at ATTEN2 (ADC 0.41 K, was
1.77 K at ATTEN3), 95 °C is unchanged at ATTEN2. The cold end is VALID but
coarse: the 10 k pull-up was sized for the hardware trip, so below ~15 °C
the node is within 10 % of the rail, the pin moves 5–8 mV/K, and ±50 mV of
ADC error and an unmeasured rail are many kelvin. That is what sizes the
cold-soak threshold (D-SOAK). Whole-mV readings add ≤ 0.08 K from 0 °C
up (half a millivolt at 5 mV/K; 0.12 K at −40 °C).

**Sampling against the ESP32-S3 SAR** (`hs-ntc.json` `sar_sampling`). The
source is the divider's Thevenin, 855 Ω, with the 100 nF as the reservoir:
τ = 85.5 µs. **Assumed: a 20 pF sample capacitor** (Espressif does not
publish it; C45 assumes the same) **and a 2.9 V swing** from whatever it
held before (another channel or the DAC's last state). Each sample kicks
the node by at most 0.58 mV. The driver takes its 8 one-shot samples back
to back; with no recovery assumed between them (a bound whatever the
one-shot interval), sample k is off by at most k + 1 kicks, and the 6 the
trimmed mean keeps average at most 5.5 kicks whatever the signs:
**3.19 mV at the pin, 0.15 K at 95 °C, 0.63 K at 5 °C.** Between periods
the reservoir recovers fully (100 ms = 1170 τ). For comparison, C45's
continuous-DMA case (HS every 112.5 µs): 0.44 mV DC + 0.16 mV residual.
The 3.19 mV is in the accuracy rows, the budget and `cold_soak.py`'s
corners. The old 100 Ω had less source error but read nothing below
~32 °C.

**Divider faults** (C45 single faults; `hs-ntc.json` `divider_faults`):
- **Bottom open or top shorted (gain 1): flagged, as a latched driver
  fault.** The intact divider cannot put more than 2883 mV on the pin, for
  any NTC state including open (g_hi × (3.367 V + V_OS)). The highest it can
  read is 2937 mV, with +50 mV of Table 5-6 error, the 3.19 mV SAR bound and
  3σ of noise. So `HS_NTC_DIVIDER_FAULT_MV` = 2950: a pin at or above
  2950 mV at ATTEN3 for 3 periods latches **DIVIDER**, and the interlock
  reads +INF (FAULT_OVER_TEMP: power off until the board is repaired).
  - A false flag needs the ADC more than 17 mV beyond its data-sheet error,
    at the very corner where the node is at the rail (an open NTC, which
    HS_OPEN already latches, or a sink below −40 °C) and the rail at its
    contract maximum. A rail above contract alone does not do it unless the
    node is also at the rail. Rail ripple does not matter (the node is
    ratiometric) and the reading is a trimmed mean held for 3 periods.
  - Detected at a cold start: with gain 1 the pin passes 2950 mV whenever the
    sink is below 19.8 / 24.5 / 29.0 °C (rail 3.242 / 3.300 / 3.367 V, ADC
    −50 mV), 24.8 / 28.8 / 32.7 °C with the ADC exact. Above that it is
    not seen. It does not need to be: the firmware then reads cold (86.45 °C
    at a true 95 °C; its 95 °C trip fires at a true 102.97 °C; C45, on its own
    NTC model: 86.1 / 103.3 °C), and the HS_HOT comparator, on HS_SENSE
    upstream of the follower and the divider, still trips at 98.3–104.6 °C.
  - Why latch rather than report: with gain 1 the C32 ladder's order
    (firmware 95 °C < hardware 98.3 °C) no longer holds, and the cold-soak
    reference reads ~10 K cold. A unit that shows it should not cook.
  - Open: the ESP32-S3's calibrated read above 2900 mV is outside Table 5-6.
    If a chip's raw code clips below 2950 mV, the flag never fires (a missed
    detection, not a false one). Bench item 6 (D-SOAK).
- **Top open or bottom shorted:** the pin reads 0 V, the node 0 V < 0.25 V:
  SHORT after 3 periods, +INF, FAULT_OVER_TEMP. Fail-safe, a nuisance
  trip (test `test_divider_top_open_reads_short_and_infinite`).

**`read_heatsink_temperature()`** (`main/board_peripherals.c`) is real:
VALID gives the filtered reading, SATURATED the upper bound (below every
limit and release), and a latched fault or no reading +INF, as the stub
always returned. Its callers: `check_safety_interlocks()` (> 95 °C,
FAULT_OVER_TEMP), `fault_cleared()` (< 70 °C releases it), the IDLE
background read, COOLDOWN (< 50 °C ends it; > start + 5 K latches), FAULT
(> 125 °C asserts the hardware shutdown), and `safety.c`
`check_hardware_interlocks()` / `run_safety_check()` (non-finite or > 95,
linked, no caller in this image). `OVER_TEMP_THRESHOLD` is 95 °C per C32
(open item 12, closed). `read_heatsink_ntc()` gives the cold-soak check the
driver state as well.

**The firmware-board contract.** `scripts/check_firmware_board_contract.py`
was not extended: it re-derives constants from `pcb/temper.kicad_pcb` (the
legacy board, keyed by `Sheetpath`), which has no HS_ADC divider. The
zapote/controller board is not in this branch's tree (it lives on
`controller-c1-crs`) and keys its footprints by `SourceInstance`, so a
registry entry here would fail closed (MISSING_COMPONENT). The same check
runs from `hs_ntc.py --verify-board-ref <ref>`: the .ato values, MPNs and
connections, the PCB's footprints on HS_ADC (MPN, pads, nets, nothing else
on the net) and C45's gain band. When zapote/controller lands on main, the
divider gain belongs in the oracle's registry with a per-entry board.

Tests (`test_c1_hs_ntc_only`, 14): the table against the data-sheet points;
chain accuracy at the trip points through the divider; room and cold
temperatures VALID (25, 15, 5, 0, −35 °C); SATURATED readings give an upper
bound (above the calibrated range, an open sensor, with and without the
rail); the divider's bottom open latches DIVIDER at a cold start and holds a
VALID history while a candidate; the intact divider at its extreme
(2933 mV) is not a divider fault; the divider's top open reads SHORT and
+INF; short, over-range and ADC failure latch (+INF); the 1 s filter; one
period per 100 ms; the defaults are the CR-8 board; the board binding reads
ADC1_CH5 only.

## D-SOAK. The cold-soak Pt100 leakage check

A leak in parallel with the Pt100 reads low (D-LEAK). If it conducts at room
temperature it reads low there too, where an idle unit sits at one
temperature, and the heatsink NTC is the only on-board reference (D-HSNTC).
The check is `components/control/pan_cold_soak.{c,h}`, run by
`main/pan_control.c`; `cold_soak.py` → `cold-soak.json` runs it, the heatsink
driver and the Pt100 conversion in C.

**When: PREHEAT entry, not power-up.** At power-up nothing says how long the
coil has been off beyond a stored lower bound (D-SOAKNV: a token in NVS,
written only after 15 min off), and a reset during a cook is exactly when
the glass is hot. So without a token uptime counts as coil-on time, and the
history is kept from power-up. PREHEAT entry is the
last moment before the coil heats, it is reached on every cook, and the user
has just placed the pan, which the flatness and rim conditions see.
`pan_control_begin()` freezes the history; the first control period (100 ms,
before the start-up pulse or any power) evaluates it with the rim driver's
first reading.

**History** (`pcs_note`, from `state_machine_update()` in every state, at
most once a second while idle): the time the coil was last active (power-up,
the loop running or power commanded), and per-minute min/max of the Pt100
(conversions that are not a sensor failure) and of the heatsink while VALID.

**Rule** (`pcs_evaluate`; any failed condition skips and records why):
1. **soaked:** the coil off ≥ N = 30 min;
2. **history:** the last W = 15 min complete;
3. **reference:** the heatsink VALID now and through the window, ≤ 45 °C;
4. **flat:** heatsink max − min ≤ 1.0 K and Pt100 ≤ 0.25 K over W;
5. **rim:** the rim NTC SATURATED (glass below ~87 °C);

then **LEAK** when the heatsink exceeds the Pt100 by more than 19.4 K
through the window (the heatsink's minimum against the Pt100's maximum) and
now; **PASS** otherwise. LEAK commands power 0 and reports
FAULT_PROBE_LEAKAGE through `state_machine_report_latched_fault()` (the D-LEAK
path: FAULT, logged once, power off). The latch is clearable:
`fault_cleared()` accepts a reset once the Pt100 is within 19.4 K of a VALID
heatsink (`pan_control_cold_soak_clearable()`), because a frozen pot reads
the same as a leak (below). A leak keeps it latched.

**The thermal argument for N, W and the flatness limits.** No time constant
is measured (bench items 3–4). Estimates: the 4 mm CERAN glass, 8160 J/m²K
(`bench/plate_check.py`), at h 10 W/m²K (`cad/thermal_axisym.py` h_eye),
816 s with one face cooling, 408 s with two; the ~1 kg aluminium heatsink
(~900 J/K) at 0.5 K/W natural convection (BOM HS1, fan off) 450 s; the
cartridge off-pan 50–73 s, slaved to the glass. The flatness tests carry the
bound: a single exponential with τ ≤ τ_max = 1800 s (2.2× the largest
estimate) that moved ≤ f over the last W lies within f/(e^(W/τ) − 1) of its
final value: 1.54 K for the heatsink, 0.39 K for the Pt100. N keeps the check
out of the first two estimated time constants after a cook, where the fast
components would pass a flatness window; it is not itself the bound.

**The threshold, 19.4 K** (`hs-ntc.json` `cold_soak_budget`, gated against
`pan_cold_soak.h`; was 12.9 K before C45): the false-latch stack at its
worst over the band where the check runs. With the CR-8 divider the
heatsink is VALID from −40 °C, so the band is no longer cut off by
saturation; it is the heatsink at **5–45 °C**: rooms down to 5 °C, 5 K under
the rated 10 °C of `docs/ENVIRONMENTAL_SPEC.md`, up to 40 °C plus the standby
offset. The worst is at its cold edge, 5 °C:
- heatsink reads high **15.68 K**, as a corner: NTC R25 −2 % and its B
  column, pull-up +1 % + 100 ppm/K, divider gain 0.854421, ADC −50 mV, SAR
  −3.19 mV, 3σ noise, buffer −2 mV and the rail 3.242 V read as 3.300 V, all
  applied to the circuit at once and read back through the driver. The
  first-order terms (ADC 9.82, rail 7.95, SAR 0.63, gain 0.41, R25 0.39,
  buffer 0.34, B 0.30, pull-up 0.24, noise 0.16 K) sum to 20.22 K. **The linear
  sum overstates the cold end** because the NTC's sensitivity rises with
  temperature; a reading pushed hot by one term is read on a steeper part of
  the curve by the next. Every term moves the reading the same way, so the
  all-limits corner is the worst case of the combination; that is what the
  budget now uses (at 25 °C the corner is 8.99 K against 10.08 K linear);
- Pt100 reads low 0.72 K: class F0.15 0.16, Rref 0.1 % + 25 ppm/K 0.40,
  converter 3 LSB 0.10, the 0.061 K correction;
- soak residuals 1.54 + 0.39 K, and a 1.0 K standby offset of the heatsink
  over the room (an assumption, bench item 2).

Total 19.33 K → 19.4 K. The stack falls to 12.7 K at 25 °C and 10.4 K at
40 °C (one threshold serves the band, so the warm rooms carry the cold
edge's allowance). With the rail measured it is **16.9 K**
(`PCS_THRESHOLD_MEASURED_K`, `cold_soak_budget_rail_measured`; D-RAIL): the
rail term is then the reading's own 0.93 % soak-band error, not 3.242 V read
as 3.300 V. The CR-8 study's 14.5 K assumed a ±0.2 % rail reading, which
the LM4040A25 alone cannot give (0.1 % at 25 °C plus 100 ppm/K, the current
shift, drift and hysteresis, plus the MCP3202's offset, gain and INL). The
firmware picks per evaluation: 16.9 K only when the heatsink reading used a
measured rail at every history note through the window and now
(`pcs_note_rail` / `pcs_evaluate_rail`), 19.4 K otherwise. The C path (`cold-soak.json`: the same corner through `hs_ntc.c`
and `rtd_convert.c` with modelled noise, steady at 5–44 °C in 0.5 K steps)
needs 16.62 + 1.93 = 18.6 K; the gate holds it at or under the firmware's
19.4 K. The 0.8 K between them is the budget's conservatism (3σ noise and
self-heating as allowances; the C path averages noise into the window's
min/max). The miss stack at the band's cold edge cannot be stated: at the
miss corner the heatsink reads below the table at 5–7.5 °C (SATURATED, the
check skips); it is 46 K at 10 °C, 19.2 K at 25 °C and 13.9 K at 40 °C,
including the Pt100's off-pan self-heating (2.7 K, 2 V bias, G_cold
0.553 mW/K).

**Benign cold starts** (`cold-soak.json`, gated: 0 latches as built, at every
corner, evaluated every 10 s along each trajectory):

| Set | Trajectories | Evaluations that ran | Latches | Largest gap |
|---|---|---|---|---|
| ambient 5–40 °C from power-up | 18 | 13500 | 0 | 16.65 K |
| warm restart after a 250 °C cook (τ_g 408/816/1800 × τ_h 450/900/1800 s) | 162 | 86332 | 0 | 17.71 K |
| hot pan (100/200 °C) placed on a soaked unit | 72 | 5459 | 0 | 16.65 K |
| cold pan (4 / −18 °C, τ 900/1800 s) placed | 144 | 61403 | 0 | 16.97 K |
| transport (−20 / 5 / 50 / 60 °C into a 5–40 °C room, powered on arrival) | 432 | 352180 | 0 | 17.88 K |

The transport set now starts from the storage minimum (−20 °C) and ends in
every room 5–40 °C, since the check runs in cold rooms too (it was 216
trajectories into 25–40 °C rooms). **Rail measured** (`cold-soak.json`
variant `rail_measured`, gated the same way, the firmware choosing 16.9 K
itself): the same 828 trajectories, 532775 evaluations, 0 latches, largest
gap 15.34 K (transport and warm restart), so a **margin of 1.57 K** (C path
14.15 + 1.93 = 16.1 K).

**The false-latch margin: 19.4 − 17.88 = 1.52 K** (the largest gap over every
gated benign trajectory and corner, against the firmware threshold; 0.72 K
against the C path's own 18.6 K). The earlier CR-8 estimate had 0.8 K
(17.8 against 18.6 K, assumed gain 0.85 ± 0.2 %). What sets it, looked into
rather than trimmed: the largest benign gaps are all at the false corner in
the 5 °C room, where the steady C-path gap is 16.62 K; the warm-restart and
transport trajectories add up to 1.25 K of the 1.93 K residual allowance (a
heatsink still above the room within its flatness test). So the benign
model reaches the budget's own corner by construction, and the margin is
the part of the residual allowance a single-exponential cool-down cannot use
plus the budget's 0.8 K over the C path. Neither the budget nor the benign
model is wrong. The thin margin earlier came from evaluating the budget
term by term with an assumed gain; the margin is real only because the
corner is evaluated physically and the SAR and noise allowances are in it.
Outside the assumptions it is thin (below).

The warm restart at the idle times asked for (as built, all corners, 162
trajectories each): 0/10/20 min skip (not soaked); 30, 45 and 60 min skip
(heatsink warm, drifting or, at the miss corner, saturated); the first
passes appear at 90 min (29) and 120 min (78); never a latch. The existing
sets' cold starts (every `leak-checks.json` benign kind starts from a unit
at 25 °C) pass at every corner now (they skipped, heatsink saturated, before
C45); the `hot_glass` kind is the warm restart at idle 0.

**Outside the assumptions (reported, not gated):**
- **a frozen pot**, whose melting contents hold the glass near 2 °C for
  hours: latches in 22 of 36 trajectories (was 12: the check now runs in
  cold rooms). A flat, cold Pt100 is what a leak looks like; nothing on the
  board tells them apart. The latch clears once the pot is lifted and the
  probe returns to the room;
- **a room below 5 °C**: steady at 0 °C, no latch; at −5 °C the false corner
  latches (gap 21.6 K, 1 of 6 trajectories). That is 15 K under the rated
  10 °C, at worst-case parts; the latch is clearable once the room warms.
  A heatsink-reading floor would not help: at the false corner a −5 °C sink
  reads +16 °C, so any floor that excludes it also excludes ordinary
  15–20 °C kitchens;
- **a large pot of cold water** (τ 20000 s): 0 of 36, largest gap 17.6 K;
- **τ_h = 3600 s** (twice τ_max) after a cook or transport: 0 of 126,
  largest gap 19.36 K against 19.4 K: the margin there is 0.04 K, so bench
  item 3 must measure τ_h. Rail measured: **1 of 126 latches** (warm
  restart into a 5 °C room, false corner, gap 16.95 K against 16.9 K at
  3 h). Outside the gated τ ≤ 1800 s, but it makes bench item 3 a
  precondition for trusting the measured-rail threshold. The frozen pot
  (22/36) and the −5 °C room (1/6) latch in both variants.

**Hazardous leaks caught before heating** (`cold-soak.json`): the 277 runs
of `leak-checks.json` whose untripped T_c exceeds 300 °C at any time (the
peak rule, D-LEAK 2026-10-16; 8 leak values, 300 Ω–2.32 kΩ; 235 runs and
7 values under the steady rule), with the same leak present at a cold start (a leak
there before the cook, or the next cook after one developed), soaked at each
ambient. Caught = cold-soak LEAK, or the leaky element below the C1 window's
84.27 Ω (FAULT_PROBE_SHORT in any state, the baseline). As built (CR-8,
threshold 19.4 K), of 277, peak rule (steady-rule counts, of 235, were
71 / 169 / 200 on the first three rows):

| As built | 5 °C | 15 °C | 25 °C | 30 °C | 35 °C | 40 °C |
|---|---|---|---|---|---|---|
| 84.27 Ω window alone | 72 | 72 | 36 | 36 | 36 | 36 |
| temperature-independent, nominal | **180** | **212** | **212** | **212** | **212** | **212** |
| temperature-independent, miss corner | 72 | 36 | 108 | 144 | 144 | 144 |
| Arrhenius Ea 0.01 eV, nominal | 180 | 180 | 180 | 180 | 212 | 212 |
| Arrhenius Ea 0.02 eV, nominal | 144 | 144 | 180 | 180 | 180 | 180 |
| Arrhenius Ea 0.05 eV, nominal | 72 | 72 | 108 | 108 | 108 | 108 |
| Arrhenius Ea 0.1 eV, nominal | 0 | 0 | 0 | 0 | 0 | 36 |
| Arrhenius Ea 0.2 eV, nominal | 0 | 0 | 0 | 0 | 0 | 0 |
| Arrhenius Ea 0.01 / 0.02 / 0.05 eV, miss | 36 / 0 / 0 | 36 / 0 / 0 | 108 / 72 / 0 | 108 / 108 / 36 | 108 / 108 / 36 | 144 / 108 / 36 |

So the check now adds coverage in an ordinary room: with nominal parts it
catches every temperature-independent hazardous leak up to 1.29 kΩ from
15 °C up (212/277; the 1.73 kΩ leak, 16.6 K low at 25 °C, and the 2.32 kΩ
leak, 12.8 K low, are under the threshold), and up to 0.97 kΩ at 5 °C (180;
the 1.29 kΩ leak gives 18.6 K there). Before C45 it added nothing below ~32 °C. At the miss corner the
heatsink reads 13.8 K low at 25 °C and below the table under ~7 °C, so the
check skips or misses there; 107–136 from 25 °C up. With the rail measured
(threshold 16.9 K, gated `hazardous_indep_nominal_as_recorded_rail_measured`)
the temperature-independent nominal count is 212 / 212 / 212 / 248 / 248 / 248
of 277 at 5 / 15 / 25 / 30 / 35 / 40 °C (the 1.73 kΩ leak is caught from
30 °C up; the 2.32 kΩ leak at no ambient) and the miss corner 72 / 36 / 144 /
144 / 180 / 180; Ea 0.1 eV gains 36 at 35–40 °C (steady rule, of 235:
200 / 200 / 200 / 235 / 235 / 235). The CR-8 study's "235 at every ambient"
rested on the ±0.2 % rail and does not hold. Leaks that conduct mostly hot are still missed
(Ea ≥ 0.1 eV). The 300 °C bar stays not met (open item 10).

**SIL** (D-SIL; `trace_c1_cold_soak_preheat.csv`, manifest fields
`c1_idle_soak_s` and `c1_pt100_leak_ohm`, mechanisms `cold-soak`,
`cold-soak-pass`, `cold-soak-skip`), now in a **25 °C room** (was 35 °C,
where the pre-C45 channel was VALID): a 1 kΩ temperature-independent leak
after a 40 min idle latches FAULT_PROBE_LEAKAGE in the first PREHEAT period
(1 row, bound 2; the reading −2.86 °C, gap 27.86 K) and a reset is refused;
the intact probe passes (gap 0) and PREHEAT holds; after a 10 min idle the
check skips with the leak present. D-SOAKNV adds a fourth: the same leak
after a power cycle with a coil-off token in NVS (`c1_soak_token_s` 900)
latches after 1000 s of uptime (coil off ≥ 1900 s).

**Host tests:** `test_c1_units_only` (`pan_cold_soak.c`: not before
30 min, threshold edges at 19.3 / 19.5 K, coil activity restarts, a full
window and clock steps, a non-VALID / warm / drifting reference, Pt100 drift
and a warm rim, agreement and parameters); `test_c1_runtime_only` and
`_isense_only` (through `pan_control` and the state machine: a 25 K leak
latches before any power and holds, agreement passes, a cold pan placed in
the window skips, < 30 min skips and heats, a SATURATED heatsink or warm rim
skips).

**Limits.**
- A power cycle no longer restarts the soak from zero if the unit had been
  off ≥ 15 min before it (D-SOAKNV): the NVS token credits 15 min, so the
  check can run once the 15 min RAM history is complete. Unplug within
  15 min of a cook (or of power-up), and power-up still counts as activity.
- Not soaked is not a pass: the check skips and records the reason
  (`pan_control_cold_soak_result()`); nothing is logged to EEPROM.
- One threshold for the band: the cold edge's 19.4 K applies in a 35 °C
  room too, where the stack is 11.0 K. A threshold read from the heatsink
  temperature would not recover it simply: at the false corner a reading of
  20 °C can be a 5 °C sink, so the threshold for a reading has to cover every
  sink that can produce it. Measuring the rail (D-RAIL) is the larger
  gain (19.4 → 16.9 K, not the 14.5 K the ±0.2 % assumption gave).

**Bench measurements this needs** (`../bench/`). With CR-8 the heatsink
channel is VALID at room temperature, so none of these needs a warm room or
a heated box any more:
1. **The heatsink NTC against ambient after a soak** (the first): log the
   channel (raw mV and `t_c`) against a reference thermometer at the lug and
   one in the room, every 10 min for an hour after a 250 °C cook and through
   an overnight idle, **at normal room temperature (18–25 °C), and once in a
   cool room (10–15 °C)**, where the stack is largest. This measures the
   channel's offset and the standby offset (assumed 1.0 K).
2. **The standby offset** of the heatsink over the room with the unit idle,
   fan off.
3. **τ_h and τ_g**: the heatsink and the glass cooling after a cook and
   warming after transport (the flatness bound assumes τ ≤ 1800 s; at
   τ_h 3600 s the margin is 0.04 K).
4. **The Pt100's off-pan self-heating** (assumed 2.7 K) and its conversion
   noise at idle (the 0.25 K flatness limit; D-OPEN's frozen-code item).
5. **The ADC1_CH5 offset at 2.5–2.75 V** (the pin at 5–25 °C) on a few
   boards: the ±50 mV data-sheet bound is 9.8 K of the 19.4 K threshold at
   5 °C.
6. **The ADC1_CH5 reading at 2.9–3.3 V** (the divider's bottom open: lift
   R90): whether the calibrated read reaches 2950 mV, so DIVIDER can latch.

## D-PINS. The pin map comes from the controller netlist, and CI checks it

**Source.** zapote/controller, read only, branch `controller-c1-crs` at
467917c38 (C45). `firmware/tools/check_board_pin_map.py --derive` reads, with
`git show`:
- `frozen/default.net`, the atopile netlist. The MCU and the expander are
  found by component class (`Esp32S3Wroom1UN8` = U4, `Tca9555` = U8), not by
  refdes;
- `elec/src/controller_parts.ato`, for the module pin of every `IOn` /
  `RXD0` / `TXD0` signal (U0RXD = GPIO44, U0TXD = GPIO43) and every TCA9555
  port pin;
- `frozen/build-receipt.json`: the sha256 of each `.ato` source at the ref
  must match the receipt, so the netlist is the build of those sources.

It writes `firmware/tools/zapote_controller_pins.json`: 36 connected GPIOs,
10 used expander pins (P02–P05, P06 and P17 single-node), and the commit and
sha256 of each file read. The branch has since moved to 431ac27df (C46, a
DECISIONS and calcs change); `--verify-board-ref controller-c1-crs` re-derives
there and matches.

**Check** (default mode, a step of the Firmware Tests CI job, with
`firmware/tools/test_check_board_pin_map.py`: 20 tests, each rule broken once
in a mutated header or source):
1. every define in `temper_pins.h` carries one tag, `@net`, `@adc1`, `@exp`,
   `@not-gpio` or `@host-mock`, and agrees with the snapshot;
2. every connected GPIO and every used expander pin has a define;
3. no file under `firmware/main` or `firmware/components` hard-codes
   `GPIO_NUM_n` (comments excluded);
4. `hs_ntc_board.c` ADC1_CH5 and `rim_ntc_board.c` ADC1_CH8 match HS_ADC
   (GPIO6) and RIM_ADC (GPIO9);
5. single writers: `PIN_IL_WDI` only in `safety.c`,
   `watchdog_hardware_write_wdi()` only from `main.c`'s WDI supervisor task,
   `PIN_RUN_EN` only in `power_gate.c` (D-BRINGUP).

**Pins that changed** (legacy `temper_pins.h` and `safety.h` → zapote):

| Signal | Was | Now | Note |
|---|---|---|---|
| Heatsink NTC | GPIO3, ADC1_CH2 | GPIO6, ADC1_CH5 | GPIO3 is FAN_TACH (open item 13) |
| MAX31865 DRDY | GPIO9 | none: TCA9555 P07 | GPIO9 is RIM_ADC (D-RIM pin-header note) |
| RTD SPI clock | GPIO8 | GPIO11 | GPIO8 is M12_ADC |
| RTD SPI MOSI | GPIO11 | GPIO13 | GPIO11 is RTD_SCK |
| TPS3823 WDI | GPIO7 (`PIN_WDT_KICK`, `WDI_GPIO_NUM`) | GPIO18 | GPIO7 is COIL_ADC |
| TPS3823 RESET_N read | GPIO6 (`WDT_RESET_GPIO_NUM`) | none: TCA9555 P14 | GPIO6 is HS_ADC |
| Runaway-cut output | GPIO15 (`RUNAWAY_CUT_GPIO`) | none | GPIO15 is PWM_HB; the MCU cannot drive the trip (C4) |
| I2C SDA / SCL | GPIO38 / 39 | GPIO37 / 0 | 38 / 39 are CT_ZC / LINE_ZC |
| Gate commands | 4 / 5 (half bridge) | 4 / 5 / 15 / 16 | native-21 full bridge |
| Removed | RTD2 CS 16, FAULT_OUT 20, RELAY_BYPASS 19, RESET_INPUT 14, LED 17 / 18, BUTTON 0, UART RX 44 | | those GPIOs are PWM_LB, USB D+ / D−, RUN_EN, IL_RESET_N, IL_WDI, I2C SCL, UI MISO |

Unchanged: GPIO1 / 2 (CT_MON / VBUS ADC), RTD CS GPIO10, MISO GPIO12, UART
TX GPIO43. Added: RUN_EN 14, IL_RESET_N 17, PERMIT_RB 36, BUS_FAULT_RB 21,
RAIL_OK_RB 35, CT_ZC 38, LINE_ZC 39, COIL / M12 / RIM ADC 7 / 8 / 9,
MCP3202 CS 42, FAN_PWM 46, FAN_TACH 3, the UI bus 40 / 41 / 44 / 45 / 47 /
48, USB 19 / 20 and the ten expander pins.

**What the legacy map did on this board.** The target image configured
GPIO6 (the heatsink ADC) as an input with its internal pull-up, configured
GPIO15 (the leg-B high-side command) as an output and drove it high on every
latched fault and runaway, toggled GPIO7 (the coil ADC) as WDI from the state
machine, armed a falling-edge DRDY interrupt on GPIO9 (the rim NTC node), and
clocked the MAX31865 on GPIO8. None of these is left.

**DRDY on the target.** `PIN_RTD_DRDY` is `HAL_PIN_INVALID` on the target
(`@not-gpio`; the check fails if the board ever puts RTD_DRDY on a GPIO); the
host suites keep mock line 63 (`@host-mock`, above the last pad). When this
was written `rtd_service` waited on a GPIO edge and the bootstrap failed
closed on the target; since the sensor-bus merge it polls P07 through the
TCA9555 instead (D-DRDY).

## D-BRINGUP. WDI supervisor, RUN_EN interlock, burst start, PLL and pan-detect wiring

From zapote/controller (467917c38) C39, C42 and open items 8 and 18.

**WDI (C42).** `components/safety/wdi_supervisor.c` is pure logic; `main.c`
runs it in its own task every 100 ms and is the only caller of
`watchdog_hardware_write_wdi()` (GPIO18). The control task publishes, once
per iteration, a loop sequence number and the sequence number of the newest
MAX31865 conversion (`rtd_service_latest_sample()`). A step toggles WDI only
when:
- the loop advanced by ≥ 5 since the last step (10 expected at 10 ms);
- the newest conversion, aged on the supervisor's own clock from the step it
  first appeared, is ≤ 300 ms old (5 × D-STALE's 60 ms);
- the step itself came ≤ 400 ms after the previous one.

The heartbeat is one edge per 100 ms (C42: ≤ 400 ms against the TPS3823's
0.9 s minimum). Before the first healthy step (power-up, the fault cycle) it
never toggles. Once running, the first failed check stops it for good: a
stall shorter than the TPS3823 timeout is not forgiven. The TPS3823 then
trips the latch in 0.9–2.5 s. Worst case from the last conversion to no
heartbeat is 400 ms. `state_machine_update()` no longer toggles WDI; the
two host tests that asserted it did (`test_state_machine.c`,
`test_integration.c`) now assert it does not. Host tests (`wdi_supervisor_tests`,
13): a healthy loop toggles every period; a stalled loop stops it for good,
even after the loop recovers; a live caller with a dead loop never toggles,
from power-up or after a healthy start; a slow loop (4 of 10), a stale or
invalid RTD and a late supervisor stop it; sequence wrap; a heartbeat over
400 ms is rejected.

**Task watchdog.** The control task subscribes itself (`esp_task_wdt_add`),
so the handlers' `watchdog_feed()` calls reset it instead of logging "task
not found" (open item 1).

**RUN_EN (C23, C39, item 18).** `components/safety/power_gate.c` is the
only writer of GPIO14. `power_gate_enable()` raises it only when every gate
PWM channel is idle: no driver or channel, or `get_state()` reports stopped
with `outputs_off` (set by init and `emergency_stop()`, not by a bare
`stop()`, which leaves the outputs where they were; new field in
`hal_pwm_state_t`, kept by the mock and the ESP32 HAL). Otherwise it refuses
and drives RUN_EN low. Lowering is never refused. In `board_peripherals.c`:
`power_enable()` (PREHEAT entry) raises it; `pwm_set_duty_cycle(0)`
(IDLE / COOLDOWN entry) lowers it; `pwm_disable_all()` (FAULT and RUNAWAY
entry, `trigger_hardware_shutdown()`, so every latched fault) forces the
gate PWM low and then lowers it. The fault cut no longer writes GPIO15.
Host tests (`power_gate_tests`, 10): refused while the PWM runs, after a bare
stop and with an unreadable PWM state; allowed with no channel, with an
initialised idle channel and after an emergency stop; lowering always works.

**Burst start (C39, item 18).** This tree has no native-21 switching path;
the power stage's full bridge (`tank_freq.c`, `burst_scheduler.c`) is on
`codex/power-stage-integration`. It does have three legacy start paths, and
all three now take the first frequency from `pll_burst_start_frequency()`:
f_start = max(47 kHz, 1.02 × f_res, PLL_MIN_FREQ_HZ), refused when that
exceeds PLL_MAX_FREQ_HZ. The 1.02 is the low end of C39's burst-start model
(f/f₀ 1.02–1.8, Q 1–15, no wrong-sign sample in 40 edges); f_res is the last
known resonance (`pll_set_resonant_frequency()`, the declared 37.58 kHz until
something measures it). The paths: `pll_enable()` (PREHEAT entry; refused
leaves the PLL disabled), `pll_reset()`, and the pan-detection pulse
(refused means no pulse). The PLL's running floor is unchanged. Host tests:
`pll_tests` +4 (start never below 1.02 f_res for f_res 30–49 kHz in 250 Hz
steps, refusal at 49.5 kHz, restart after the resonance moves up),
`pan_detection_tests` +9 (the pulse programs the frequency after the idle
check and before the pulse; refused with busy gates or no inductive start).
`test_pll_reset_frequency` now expects the burst-start frequency.

**Requirement for the power-stage owner** (the real start path):
1. the first gate edge after RUN_EN rises is at f ≥ 1.02 × the last
   measured resonance of this pan, or at f_max when none is known (tank_freq
   already approaches from 60 kHz down; this asks the same of every burst
   restart, after a pause or a pan change);
2. raise RUN_EN only with all four commands low, through `power_gate.c` or
   an equivalent check, and report gate state through `hal_pwm` or extend
   `POWER_GATE_PWM_CHANNELS`;
3. create the leg-A high-side generator after `board_power_init()`, with
   `io_loop_back = 1`, and call `pll_set_timer(timer, resolution_hz)`, or
   the PLL's PWM-edge capture goes blind (or replace the legacy PLL with
   tank_freq);
4. install `pan_detect_pulse_ops_t` or replace `detect_pan_presence()` with
   the tank_freq pan evidence; until then there is no pan and no power.

**PLL.** `pll_capture_attach()` registers `pwm_edge_cb` (PWM_HA rising) and
`zcd_edge_cb` (CT_ZC rising, taken only after a PWM edge) and enables both
channels. The lag is computed in float µs from the capture timer's own
resolution (was integer µs from a hard-coded ÷80). `pll_set_timer()` now
takes the timer's resolution: the old period was 160 MHz / f while hal_pwm
runs its timer at 80 MHz, which would have programmed half the frequency
(47 → 23.5 kHz, far below resonance).

**Pan detect.** `pan_detect.c` now builds on the host, and the duplicate
`test/pan_detect_logic.c` is gone. `pan_detect_init()` counts edges on a
CT_ZC capture channel. The pulse goes through `pan_detect_pulse_ops_t`
(gates idle, set the frequency, pulse) in `pan_detect_run_ops()`. Without
pulse ops or a listener, `detect_pan_presence()` returns PAN_ABSENT.

**Board bring-up** (`main/board_power.c`, called from `init_peripherals()`):
1. drive the four gate commands low as GPIO outputs;
2. `power_gate_init()`;
3. `pll_init()`;
4. one MCPWM capture timer (group 0, APB) with three channels: PWM_HA
   (io_loop_back, so the pad stays an output, low), CT_ZC for the PLL, and
   CT_ZC for pan detection. Then `pll_capture_attach()`,
   `pan_detect_init()`, and the timer is started.

Any error leaves the PLL unlocked and no pan. **Stubs that remain**
(`TODO(hardware)`, fail safe):
- the native-21 gate generator: no PLL timer, no pulse ops, so no pan and
  no power;
- the TCA9555 driver: DRDY, SUP_RUN_OK_RB and the latch read-backs;
- the power, fan, UI and self-test stubs in `board_peripherals.c`.
## D-FCYC. The MAX31865 fault-detection cycle is manual, timed from the CR-1 network

**Why.** zapote/controller C37 fitted CR-1 exactly (as-built checks 11/11): a
two-stage differential RC (1.00 k / 100 nF / 1.00 k / 100 nF C0G) between J3
and RTDIN±, 220 nF X7R on every J3 pin, the 499 k open-lead pull-ups. The
data sheet (19-6478 Rev 3, "Fault Detection Cycle (D3:D2)"): "If the external
RTD interface circuitry includes an input filter with a time constant
greater than 100 µs, the fault detection cycle timing should be controlled
in the manual mode operation." C37 says the same and asks for a 5 ms wait.

**The timing** (`fault_cycle.py` → `fault-cycle.json`, gated). It takes
`pcb/checks.py`'s MNA model of that circuit unchanged, assembles C·dx/dt +
G·x = b with FORCE− closed and open at 1536 tolerance corners (C0G ±5 %, X7R
±10 %, R ±0.1/1 %, the unspecified FORCE− switch 0.5/10/20 Ω, leads
0.9/1.1×, the element at −40/25/250/360 °C) and integrates the manual
sequence (backward Euler, 1 µs):
- **τ_max = 1009.9 µs** (FORCE− open, 360 °C, every capacitor high). C37's
  5 ms is 4.95 τ_max: just under the data sheet's 5 τ. The firmware does not
  use it.
- Worst required waits: a healthy input settles to the 85 % comparators with
  FORCE− open in 1.193 ms; an open element is flagged 0.584 ms after VBIAS;
  15-bit settling before a restart 5.533 ms.
- **Firmware waits** (`rtd_service.h`, gated): STEP = max(5 ms, 5 τ_max,
  2 × worst) = **5.5 ms** between VBIAS-on, step 1 and step 2; RESTART =
  max(STEP, 5 τ_max + 1 ms, 10.5 τ_max (Note 4), 2 × worst 15-bit) =
  **11.5 ms** from step 2, plus 1 ms for the chip's own step-2 check, before
  CONFIG 0xC0. Each wait is measured with the HAL microsecond clock and
  checked each 10 ms control tick, so the real spacing is ≥ 10 ms per step.
- **The automatic cycle flags a healthy input** (07h 0x18: D4, D3) at all 48
  transient corners: its 100 µs internal delays are a tenth of τ_max.
- **At the firmware waits**: healthy 0x00; element open 0x28; FORCE+ open
  0x28; FORCE− open 0x20; RTDIN− shorted to ground 0x18; FORCE+ shorted to
  ground 0x18. An open RTDIN− lead is not a cycle condition on this board
  (the 499 k and CR-3 divider pull it to 0.894 VBIAS): the conversion ratio
  goes negative, code 0, below the low threshold: FAULT_PROBE_SHORT within a
  conversion.

**Sequence** (`rtd_service.c` C1, `max31865.c`): bootstrap programs the C1
window and writes 0x82 (VBIAS on, conversions off, 07h clear); the control
ticks then write 0x88 (step 1: D5 with FORCE− closed), 0x8C (step 2: D4/D3
with FORCE− open), poll D3:D2 = 00, read 07h, read the RTD registers once
(D-DRDY), and start conversions (0xC0). The coil is off: the machine is in
INIT until the service converts. A set bit at power-up is reported (D6/D4/D3
as SHORT, the rest as OPEN) and is terminal (D-RESET). A phase still
unfinished 10 ticks past its wait fails open. The same cycle runs on every
probe-fault reset request (D-RESET). `RTD_FRONT_END_CR1` now defaults to 1:
the CR-7 loading correction is on for this board.

**Model and tests.** The SPI mock carries an analog model of the input
(`mock_max31865.c`, its constants generated into `mock_max31865_afe.h` by
`fault_cycle.py`: τ_max and the DC node fractions per wiring condition): the
comparators decide at the moment of each step write, a step sooner than
5 τ_max after the last analog change and a restart sooner than the 15-bit
settling are counted, and the automatic cycle (D3:D2 = 01, or 11 without a
prior 10) is run with its 100 µs delays and counted.
- `test_c1_rtd_service.c`: the manual cycle's order and waits; a cycle run
  0.5 ms apart, and the automatic cycle, flag a healthy element (the model
  behind the rule); the power-up cycle catches an open element, an open
  FORCE− lead and inputs shorted to ground; a stuck cycle fails open.
- SIL (C1, every scenario): the run fails if the model counted an automatic
  cycle, a fast step or an early restart. New scenarios: FORCE− open from
  power-up → FAULT_PROBE_OPEN in INIT (mechanism `rtd-fault-cycle`, 07h
  0x20); the probe reconnected with RTDIN− shorted to ground → the reset's
  cycle flags 0x18 and refuses it (mechanism `rtd-fault-cycle-reset`); the
  reconnect scenario's accepted reset now requires a new cycle. Coverage
  adds INIT as a C1 origin for FAULT_PROBE_OPEN: 28/28 pairs, 27/27
  mechanism cells.
- Mutation check: with the step-1 command set to the automatic code, 50 of
  51 C1 SIL scenarios fail.

## D-DRDY. DRDY is polled through the TCA9555, once per control tick

On zapote/controller the MAX31865 DRDY is TCA9555 P07 (`EXP_RTD_DRDY`), not a
GPIO, and the expander's INT is not wired to the MCU; GPIO9 is the rim NTC.
The bring-up pin map (`sensor-c1-bringup`) sets `PIN_RTD_DRDY` to
`HAL_PIN_INVALID` on the target.

**Choice: poll the expander's Input Port 0 over I2C every 10 ms control tick,
before the MAX31865 work** (`rtd_drdy_source_t`, `components/sensors/
tca9555.c`; `RTD_DRDY_AUTO` picks it whenever `PIN_RTD_DRDY` is invalid; a
valid pin keeps the falling-edge interrupt, which the host mocks use).
- DRDY is a level: it "goes low when a new conversion result is available
  ... When a read operation of an RTD resistance data register occurs, DRDY
  returns high" (19-6478 Rev 3). Conversions are 16.7–17.6 ms apart (0xC0),
  so a 10 ms poll cannot miss one, and the read that follows returns the
  level high, so it cannot see one twice.
- A level has no edge: a conversion left unread when the converter stops (the
  reset verification's 0x82) would hold DRDY low through the cycle and pass
  for the first new conversion, clearing the reset on old data. The service
  therefore reads the RTD registers once before every (re)start. Without that
  read the host test fails (mutation checked).
- A failed I2C read is "no DRDY this tick". Six in a row is the stale open
  fault, exactly as for a silent converter; an expander that does not answer
  at bootstrap fails the service closed. D-STALE and the frozen rule are
  unchanged.
- **Rejected: reading on schedule** (every 20 ms off the 50 Hz period). A
  converter that stopped converting would return its last code until the
  frozen rule (250 codes, 5 s) instead of the 60 ms stale rule, and an
  unsynchronised read can straddle a register update.

The driver is minimal (TI SCPS200E Table 3: command byte 0x00 = Input Port 0,
a write of the command byte then a repeated-start read; the power-up
configuration is all inputs, polarity 0). The ESP-IDF v5.3.6 I2C master
driver is thread-safe only for bus creation (i2c.rst "Thread Safety"), so
the binding serialises its transfers with a mutex and shares an existing
bus (`i2c_master_get_bus_handle`) if another owner created it; 400 kHz, 5 ms
timeout. One poll is about 40 bit times, 0.1 ms at 400 kHz.

**Tests.** `test_c1_rtd_service.c` (the TCA9555 model `test/mock_tca9555.c`,
DRDY as the MAX31865 model's level): each conversion read once; the low
level left over the reset cycle is not a new conversion; an I2C failure is
stale-open in 5–6 ticks with the failures counted; no expander at bootstrap
fails closed; AUTO follows the pin map. The C1 SIL now runs every scenario on
the expander path. The host and target builds take the pin symbols from
`temper_pins.h` (the pre-merge `SENSOR_BUS_PIN_SHIM` was removed at the
merge with D-PINS); a pin map without `EXP_RTD_DRDY` and
`TEMPER_EXPANDER_I2C_ADDR` compiles the expander path out and fails closed
on an invalid DRDY pin.

## D-RAIL. The v3v3 rail reading: MCP3202 CH1 against the LM4040A25

**Driver** (`components/sensors/rail_adc.{c,h}`). U15 MCP3202-CI/SN, VDD =
VREF = v3v3, CH1 = the LM4040A25IDBZR fed from v3v3 through 1 k 1 %, CS
`PIN_SPI_CS_EXT_ADC` (GPIO42, 10 k pull-up), on the MAX31865's bus. Command
0x01 / 0xE0 / 0x00 (DS21034F Figure 6-1: start, single-ended, CH1, MSB
first); the null bit must read 0; v3v3 = 2500 mV × 4096 / (code + 0.5), the
mean of 8 conversions, one reading per 100 ms.
- **SPI.** MCP3202: modes 0,0 and 1,1, f_CLK ≤ 0.9 MHz at 2.7 V (1.8 MHz at
  5 V), the sample read within 1.2 ms (DS21034F 6.1, 6.2): its own device
  handle, **mode 0, 500 kHz**. MAX31865: mode 1 or 3, ≤ 5 MHz: mode 1,
  500 kHz. Both CPOL 0, so SCLK idles at one level for both. ESP-IDF
  v5.3.6 configures mode and clock per device (`spi_device_interface_config_t`)
  and time-multiplexes devices on one bus ("SPI Bus Lock", spi_features.rst);
  the driver is thread-safe when each device is used by one task
  (spi_master.rst "Driver Features").
- **Arbitration.** One task owns the bus: `rtd_service_control_tick()` does
  its MAX31865 work, then calls `rail_adc_board_service()`, which samples
  when 100 ms have passed. So the two never contend and there is no lock to
  starve. A reading is 8 × 24 clocks (≈ 0.4 ms) per 100 ms. DRDY is a
  latched level (D-DRDY), so a rail reading can delay a MAX31865 read by at
  most that tick, never lose it; the host test runs 5 s of both (250
  conversions, 50 readings) with no stale or frozen trip.
- **Unknown, not a fault.** NO_READING, SPI (a transfer error or a high null
  bit: an absent converter's floating DOUT), RANGE (outside the window),
  STALE (no good reading for 1 s), NO_DEVICE (no CS in the pin map, attach
  failed): the NTC drivers then divide by 3.300 V and set `rail_nominal`.
  That is the board's validated state, whose error every budget already
  carries (rim 4.37 K, the cold-soak 19.4 K), so a lost rail reading costs
  accuracy, never availability.
- **Window 3195–3415 mV** (`rail_adc.h`, gated): the TPS62933 contract
  3.242–3.367 V widened by the reading's full-range error and rounded out to
  5 mV, so a healthy board never reads "unknown". An open reference reads
  2500 mV, a shorted one 20480 mV: both outside. A reference that drifted
  inside the window is not detectable; its error is bounded by the window.
  The NTC drivers' own acceptance (`v3v3_min_mv`) is lowered to 3195 to match.

**Error budget** (`rail_adc.py` → `rail-adc.json`, gated; LM4040 TI SLOS456Q
§6.8, MCP3202 DS21034F, both verified against the PDFs with
`--verify-*-pdf`). As a fraction of v3v3, every term at its limit:
- LM4040A25I: ±2.5 mV at 25 °C, + 100 ppm/K × |T − 25| (capped at the
  full-range ±19 mV); + 1 mV for the cathode current (the tolerance is at
  100 µA; the board runs 0.69–0.87 mA, inside IZ,min < IZ < 1 mA over the
  contract); + 120 ppm long-term and 0.08 % thermal hysteresis (typical
  values, carried as allowances);
- MCP3202-C: offset 3 + gain 5 × code/4096 + INL 2 LSB at code ≈ 3103
  (0.28 %), + ½ LSB of decode. These limits are specified at VDD 5.5 V; at
  3.3 V they are assumed in LSB (bench item). With them doubled the
  soak-band error is 1.22 % and the measured-rail threshold would be 17.7 K;
- v3v3 ripple during a conversion (the converter's reference is v3v3): ±5 mV
  assumed (10 mV p-p, forced-CCM TPS62933; bench item).

Total **0.68 % at 25 °C, 0.93 % over a 5–50 °C board** (the cold-soak band,
heatsink 5–45 °C plus 5 K of board self-heating, an assumption), **1.33 %
over −40..85 °C** (used for the window and the rim). The CR-8 study assumed
±0.2 %, which the LM4040A25 cannot give.

**What it buys.**
- **Cold soak:** 19.4 K → **16.9 K** when measured through the window
  (D-SOAK; both thresholds gated in `hs_ntc.py` and `cold_soak.py`, 0 false
  latches in both, margins 1.52 / 1.57 K).
- **Rim:** the rail term 4.37 K → 2.87 K over 100–250 °C (D-RIM); the rim
  limit keeps the unknown-rail stack.
- **Heatsink:** at the 95 °C trip ±1.06 K → ±0.71 K; at 25 °C 5.3 → 3.4 K
  (D-HSNTC).

**Tests** (`test_c1_rtd_service.c`): the decode and its round trip; the
device's own mode 0, 500 kHz and CS; the reading feeding the rim and heatsink
seams and tracking 3.242–3.367 V; every unknown state falls back without a
fault; 5 s of shared bus without starvation. `test_c1_units.c`: the
threshold switches only with the rail measured through the window.

## D-SOAKNV. The coil-off time survives a power cycle as an NVS lower bound

**Time across mains loss.** The ESP32-S3's RTC timer "can also persist time
keeping across any resets (with the exception of power-on resets which reset
the RTC timer)" (ESP-IDF v5.3.6 `system_time.rst`), and zapote/controller has
no battery, backup supply or external RTC. After a mains loss neither the
RTC nor the high-resolution timer knows how long the unit was unpowered, and
wall time (SNTP) is not assumed. So only a **lower bound** can persist: "the
coil had been off at least X when this was written". The unpowered interval
counts as zero, which can only make the unit look less soaked.

**Design** (`components/control/pan_soak_store.{c,h}`, NVS binding
`main/soak_store_nvs.c`, namespace `temper_soak`, key `off_s`):
- **Write once** per coil-off period, when its coil-off time first reaches
  N − W = 900 s: token = 900. With it a power-up credits 15 min
  (`pcs_credit_off`), so the check can run as soon as the 15 min RAM history
  is complete (16 min of uptime) instead of after 30 min. The window cannot
  be persisted: the temperatures during the outage are unknown and flatness
  must be observed. A longer token would buy nothing: the history is the
  binding constraint after 900 s.
- **Revoke** (erase, commit, read back) in `pan_control_begin()` before the
  coil is energised, and on any coil activity the history sees, whenever a
  token is present. So a token always means "the coil has been off since it
  was written".
- **Boot**: a present token in 1..3600 s credits its value; absent,
  unreadable or implausible = unknown = not soaked (power-up counts as
  activity, as before); an implausible one is erased.
- **Write rate**: at most one write and one erase per cook; nothing periodic.
  On re-initialisation (a fault reset through INIT) the token is read again.
- **Power loss during NVS writes**: "one should be able to power off the
  device at any point and time ... This should not result in loss of data,
  except for the new key-value pair if it was being written" (nvs_flash.rst):
  a torn write is an absent token (unknown). A torn erase leaves the token,
  but the erase comes before energising, so the coil was still off.
- **A failed revoke does not block heating.** The store is disabled for the
  session and the failure counted. A stale token can only make the check
  run on a unit still cooling from a later cook after a power cycle: the
  heatsink warm over the Pt100 reads as a leak, a false and clearable
  FAULT_PROBE_LEAKAGE. A skip and a pass have the same effect (no latch), so
  no leak is missed that the RAM-only check would have caught.

**Tests.** `test_c1_units.c`: one write per off period, none periodic,
boot credit, revoke and verify, no flash traffic on coil activity without a
token, implausible / unreadable / failed write / failed or unverified erase.
`test_c1_runtime.c` (through `pan_control` and the state machine, an NVS
mock that survives `state_machine_init()` as flash survives a power cycle):
16 min idle writes the token; after a power cycle the leak latches at 16 min
of uptime before any power and PREHEAT revokes the token; the same unit
without a token skips; a failing erase does not stop heating. SIL: the
power-cycle scenario in D-SOAK.

## Open items for the firmware owner

1. **The ESP-IDF target links** (resolved 2026-10-15, branch
   `sensor-c1-idf-link`; IDF v5.3.6, esp32s3, `TEMPER_PAN_CONTROL_C1=1`).
   `induction_cooker.bin` is 0x4F500 bytes (317 KB), 84 % of the 1984 KB
   factory slot free. CI builds it as the last step of the Firmware Tests
   job. The former blockers and their fixes:
   - `partitions.csv` was missing: added, a single factory slot sized for the
     4 MB flash in `sdkconfig.defaults` (no OTA: Wi-Fi/BT are off and no OTA
     code exists; the upper 2 MB is left free for a later ota_0/ota_1 pair).
   - The project's `components/hal` replaced IDF's `hal`: renamed to
     `components/temper_hal`. Its ESP32 sources had never compiled; they now
     do (format and include fixes only).
   - `components/webui` asked for `esp_vfs_fat` and `json`, but uses
     neither: it now requires only `esp_http_server`. (`json` is still an
     IDF 5.3 core component; there is no `esp_vfs_fat` component, that
     header lives in `fatfs`.)
   - jinja2 was missing from the IDF Python env: installed locally with
     `pip install -r firmware/tools/requirements.txt`, which the README and
     both IDF CI steps now do. The configure now fails instead of falling
     back to the committed `config.h`.
   - Undefined externs (55 at first link). Real implementations already in
     the repo are now linked: `safety.c` (watchdogs, boot reason, hardware
     shutdown), `config.c` (`g_config`, now statically initialised), and
     `thermal_mass`, `pid_control`, `profiles`, `pll_control`, `pan_detect`,
     `zvs_monitor`. `main/board_peripherals.c` adds `get_time_ms` and
     `read_rtd_resistance` (real), and `TODO(hardware)` fail-safe versions of
     every peripheral without a driver. The interim
     `rim_ntc_stub.c` stand-in was deleted when the rim driver merged (D-RIM).

   Defects fixed while linking (never compiled for the target before):
   - `safety_wdt_init()` called `esp_task_wdt_init()` on the task watchdog
     the IDF startup had already initialised, so `ESP_ERROR_CHECK` would
     abort every boot. It now reconfigures it.
   - `g_config` stayed zero until `config_init()`, which nothing calls on the
     target, so `runaway.max_absolute_temp_c` was 0 degC. It is now
     statically initialised to the `config.yaml` defaults.
   - `webui` `/api/status` returned a fixed 25.0 degC. It now returns 503.

   **The image is not bench-ready.** The self-tests fail by design, so it
   stops in FAULT with the coil off. Defects seen while linking, since
   addressed by D-BRINGUP (2026-10-16, branch `sensor-c1-bringup`):
   - ~~`pll_control.c` stores the capture channel but never registers
     `pwm_edge_cb`/`zcd_edge_cb`~~: `pll_capture_attach()` registers both on
     PWM_HA and CT_ZC captures that `main/board_power.c` creates. The PLL
     still cannot lock until the power stage provides the native-21 gate
     timer (`pll_set_timer()`), which this tree does not have;
   - ~~`pan_detect_init()` and the MCPWM bring-up are never called~~: the
     CT_ZC capture and `pan_detect_init()` run at boot. `detect_pan_presence()`
     still reports no pan, now by design: the pulse needs the native-21 gate
     drive (`pan_detect_pulse_ops_t`, TODO(hardware));
   - ~~the control task is not subscribed to the task watchdog~~: it
     subscribes itself (`esp_task_wdt_add`).
2. **Rim NTC driver and rim faults: closed by D-RIM.** What remains:
   - **MCP3202 CH1 rail driver: closed by D-RAIL** (the rail term is 2.87 K
     measured, 4.37 K when the rail is unknown).
   - **Bench:** the bead's dissipation constant on the glass (self-heating is
     not subtracted), and a transient glass log to replace the 60 s τ_g
     assumption in `xcheck_cosim.py`.
   - ~~**Pin header.** The legacy `hal/include/temper_pins.h` still names GPIO9
     `PIN_RTD_DRDY`.~~ Closed by D-PINS: GPIO9 is `PIN_ADC_RIM_NTC`, DRDY is
     `EXP_RTD_DRDY` (TCA9555 P07) and no GPIO; `rtd_service` reading DRDY
     there is D-DRDY (open item 16, closed).
   - **UI wording** for a rim fault, which today shows as a probe fault.

   The three changed sources (`rim_ntc.c`, `rim_ntc_board.c`,
   `pan_control.c`) compile with `xtensa-esp32s3-elf-gcc` (`-Wall -Wextra
   -Werror`, C1 on). The IDF link is still item 1.
3. **Manual fault-detection cycle: closed by D-FCYC.** zapote C37 fitted
   CR-1; τ_max 1009.9 µs from the board's MNA model; 5.5 ms steps and an
   11.5 ms restart, at power-up (coil off) and before every probe-fault reset
   (D-RESET); the SPI mock models the input settling and the SIL fails on an
   automatic cycle, a fast step or an early restart. Still open:
   - **bench:** the FORCE− switch resistance (0.5–20 Ω assumed) and τ on a
     real board (scope REFIN−/RTDIN− through a manual cycle);
   - C37's 5 ms is 4.95 τ_max; the firmware uses 5.5 ms, so nothing is asked
     of the board, but C37's text should say ≥ 5.1 ms.
4. **The double-fault trade-off (D-RUN)** is for the safety owner to accept or
   tighten. **Narrowed by D-ISENSE:** a sense that fails before the stage
   sticks is now caught on its own, by the start-up pulse or by (a) at the
   first ≥ 300 W command, and the stage never gets to stick unwatched. What
   is left for 2b (≤ 35.0 s) is a stage and a sense that fail in the same
   instant while the loop commands under 300 W. Options:
   - a bus-current validity signal, which would turn 2b into 2a;
   - a bus-voltage sense, to replace the 100 V placeholder in P_cmd/V;
   - the AMC1301 input-current sense, for which D-ISENSE (c) is written and
     tested but compiled out (`TEMPER_INPUT_CURRENT_SENSE`).
5. **Bench items:**
   - real MAX31865 conversion noise. Below about 0.25 LSB the 250-code frozen
     check needs lengthening;
   - the bus-current sense scaling for stage 2a;
   - whether the end hold is steady on clad pans (D-ID2 rejections).
6. **Closed (D-SIL): the SIL suite now runs in C1 mode as well.** It used to
   encode only the legacy loop. `sil_fault_tests_c1` runs 52 scenarios
   against the C1 configuration (36 when this item closed); legacy runs 31.
   Each of the four legacy-only scenarios names its C1 replacement. Coverage
   is gated in both modes: 20/20 pairs legacy, 28/28 pairs C1, and 27/27 C1
   mechanism cells (23/23 and 16/16 then). The C1
   run found two defects, both fixed (D-LATCH, D-RESET). Still open:
   - **An open Pt100 escalates to RUNAWAY_FAULT: closed by D-OPEN.** A
     conversion at or beyond R(850 °C) or R(−200 °C), or with a 07h input
     bit, is now the recoverable FAULT_PROBE_OPEN / SHORT. A flagged
     plausible over-temperature still latches RUNAWAY. The reset also clears
     07h.
   - **If `ptl_init()` rejects its parameters,** `pan_control_step()` returns
     `PAN_CONTROL_SENSOR_FAULT` with no report. The PREHEAT/HEATING handlers
     then return before `check_safety_interlocks()` on every update. That
     cannot happen with the default parameters, and the SIL does not reach
     it; it is found by reading the code.
7. **CR-7 high threshold word: closed (D-THRESH).** Recomputed from R(360 °C)
   by `cr7_thresholds.py`, CR-7's 35544 is right. The firmware's 35542 came
   from the rounded 233.21 Ω and is fixed to 35544. The PCB side needs no
   change.
8. **Hot-pan starts run on the prior.** a is never identified (no updates,
   src_mask 0), so a0 is used. For cast iron that is 2.34 × a_true. B1–B3
   still pass.
9. **h_c steps: closed by D-CSW / D-LPG.** Was: B1 0/4, B2 0/4, overshoot up to
   13.09 K for 1000 → 300. Now gated on 64 steps in three gain modes
   (`../robustness/hc-cosim.json`, bars R-HS1–5): B2 64/64, worst 5.00 K;
   the original case is 4.21 K. What remains open is in
   `../robustness/DECISIONS.md` R-C: gradual contact loss (warp, a stuck post
   with pan bow) is not observable by the window or D1, and needs the rim
   cross-check or the mechanical margin.
10. **Element-parallel leakage: two firmware latches now exist (D-LEAK,
    D-RIMLIM), and the 300 °C bar is still not met.** With the
    setpoint-relative rim limit in the loop (`leak-checks.json`):
    - hazardous counts transient overshoot from 2026-10-16 (D-LEAK): 277
      runs, 300 Ω–2.32 kΩ (235 and 1.73 kΩ under the steady rule);
    - 69 of 277 latch before the pan passes 300 °C (7 of 235 before
      D-RIMLIM, 59 of 235 steady rule): 31/93 step, 18/92 120 s ramp,
      20/92 600 s ramp;
    - 204 latch after it, at T_c ≤ 431.1 °C (was ≤ 474.2 °C);
    - **4 never latch**: 2.32 kΩ, Δ 46 K, cold bead, ramp onsets, peaking
      300.3–302.2 °C and settling at 299.3–299.5 °C (none under the steady
      rule, which did not count them; 9 before D-RIMLIM);
    - 0 false latches on the 548 benign runs and on 132 worst-case stress
      runs;
    - ≥ 3.11 kΩ is not a hazard (peak T_c ≤ 290.8 °C) and ≥ 4.16 kΩ is
      invisible (steady T_c ≤ 276.8 °C).

    It cannot be met from the rim. At a 250 °C setpoint the benign and
    leaking glass ranges overlap by about 46 K, and the glass lags the pan
    by 18–106 s (D-RIMLIM). What remains:
    - **C, the cold-soak check, is implemented (D-HSNTC, D-SOAK) and does
      not meet the bar either.** With the CR-8 divider (zapote C45) the
      heatsink channel is VALID from −40 °C, so the check runs in an ordinary
      room: with nominal parts it catches 212/277 temperature-independent
      hazardous leaks before heating at 15–40 °C and 180 at 5 °C
      (threshold 19.4 K; the 1.73 and 2.32 kΩ leaks are under it); at the
      worst corner 108–144 from 25 °C up and only the 84.27 Ω window below.
      It misses leaks that conduct mostly hot (Arrhenius Ea ≥ 0.1 eV: 0–36). 0 false
      latches on 828 gated benign cold-start trajectories (margin 1.52 K);
      a frozen pot latches (clearable).
    - **D, coil impedance, waits for measured P and I.**
    - **The bench must measure the glass envelope and lag** (D-RIMLIM bench
      items 1–3).
    - **CR-5 should come down about 8 K** (86.6 k → 76.8 k), with bench T3's
      criterion tightened to ≤ 244.5 °C.

    The protection that meets the bar is the insulation: ≥ 10 MΩ at 300 °C,
    the production hot test and seal-ingress qualification (D-LEAK
    requirements 1–3), for the PCB, CAD and production owners. The original
    note follows.
    In `xcheck-cosim.json`:
    - 1 kΩ drives the pan to SP + 121.9 K;
    - 3 kΩ holds it at SP + 35.8 K;
    - the cross-check fires on 5 of the 8 1 kΩ runs only (7 before D-LEAK
      extrapolated the NTC above 300 °C and D-CSW joined the loop), and its
      D1 probe correctly confirms contact.

    Only the CR-5 hardware trip remains: the glass reaches the band's low edge
    in 6 of 16 runs and its top in 4.

    The obvious rule is to latch when a cross-check suspect is followed by a
    probe that confirms contact. That is the leakage signature, but 2 of 28
    benign runs (cast iron food, Δ 12 K) raise a suspect, so it needs a
    further qualifier before adoption, for example:
    - two consecutive suspect-and-confirm cycles;
    - the rim's own rise.

    D-XCHK is unchanged here.
11. **MCP3202 CH1 rail driver: closed by D-RAIL.** `rail_adc.c` on the RTD
    bus, sampled from the RTD service's own tick (one bus owner). The real
    error budget (LM4040A25 + MCP3202, 0.93 % over the soak band) gives a
    measured-rail cold-soak threshold of **16.9 K**, not the 14.5 K the
    ±0.2 % assumption gave, and 212–248 of 277 temperature-independent
    hazardous leaks at nominal parts (peak rule; 200–235 of 235 under the
    steady rule; not all everywhere). The firmware
    switches at run time; the rail unknown is the 3.300 V fallback, not a
    fault. Still open (bench): the MCP3202's offset and gain at 3.3 V (its
    limits are specified at 5.5 V), v3v3 ripple at U15 (±5 mV assumed), the
    LM4040's drift and hysteresis (typical values used as allowances), the
    board's self-heating at idle (5 K assumed), and τ_h (a τ_h of 3600 s
    latches the measured-rail threshold once in 126 reported trajectories).
12. **`OVER_TEMP_THRESHOLD` 80 °C → 95 °C: closed (owner decision 2026-10-15).**
    `config.yaml` now sets 95 °C, the firmware trip in the zapote/controller
    ladder (DECISIONS C32): 88.6 °C fan-law operating point < 95 °C firmware
    trip < 101.4 °C hardware comparator (64-corner 98.3–104.6 °C) < 125 °C
    FAULT-state shutdown. Tj ≈ 123 °C at the trip (C32). The 70 °C release
    and the 125 °C shutdown are unchanged. Not changed: the Rust
    `packages/temper-thermal` `FIRMWARE_TRIP_TS_C` (80.0, asserted in its own
    test), which models the legacy elec board's THM-01 85 °C ladder for the
    placer; it belongs to that package's owner.
13. **Closed by D-PINS.** ~~`temper_pins.h` names GPIO3 / ADC1_CH2
    `ADC_CHANNEL_NTC`.~~ The whole pin map now follows the zapote/controller
    netlist (heatsink NTC GPIO6 / ADC1_CH5, GPIO3 FAN_TACH), derived by
    `firmware/tools/check_board_pin_map.py` and checked in CI.
14. **Coil-off time across a power cycle: closed by D-SOAKNV.** No clock
    survives mains loss on this board (the ESP32-S3 RTC timer resets on a
    power-on reset), so NVS keeps a lower bound: a token written once when a
    coil-off period reaches 15 min and revoked before the coil is energised.
    After a power cycle the check can run at 16 min of uptime instead of
    30. What it cannot do: credit the unpowered time itself (a unit unplugged
    overnight right after a cook still waits 30 min).
15. **zapote/controller open item 22 (C45, `adc_gain` and the divider
    plausibility): closed from the firmware side.** Read at
    `controller-c1-crs` 467917c38 (`hs_ntc.py --verify-board-ref` checks the
    .ato, the PCB and C45). `HS_NTC_ADC_GAIN` = 0.855072 (5.90 k / 6.90 k,
    not the 0.849 of the CR-8 example values) is the driver's default in
    `hs_ntc.h`, gated by `hs_ntc.py`; the gain band 0.854421–0.855722 is in
    the error budget. The plausibility check is implemented as the latched
    DIVIDER fault (pin ≥ 2950 mV at ATTEN3 for 3 periods, above the intact
    divider's 2937 mV worst reading; D-HSNTC). Cold-soak threshold 19.4 K
    (D-SOAK). Nothing is asked of the board. The channel binding itself
    (`hs_ntc_board.c` ADC1_CH5 = HS_ADC = GPIO6) is now also checked against
    the netlist by `check_board_pin_map.py` (D-PINS).
16. **RTD DRDY on the TCA9555: closed by D-DRDY.** `rtd_service` polls
    Input Port 0 bit 7 (`EXP_RTD_DRDY`) over I²C each control tick through
    `components/sensors/tca9555.c` (SDA `PIN_I2C_SDA`, SCL `PIN_I2C_SCL`,
    `TEMPER_EXPANDER_I2C_ADDR`); a failed read counts as no DRDY (D-STALE),
    and an expander absent at boot still fails the bootstrap closed. The
    other expander read-backs (P14, P10, P00/P01) can use the same driver.

17. **Native-21 gate drive** (D-BRINGUP). This tree has no full-bridge
    generator, so the PLL has no timer, pan detection has no pulse and the
    coil never runs. D-BRINGUP lists what the power stage's driver must do:
    burst start ≥ 1.02 × last resonance, RUN_EN only with the gates idle,
    PWM_HA loop-back for the PLL capture, and pan evidence.

## F1. 2026-10-17: diagnose D1 nuisance cuts; retain the detector

**Decision: no D1 behavior change.** The measured nuisance counts are retained
as upper-bound gates: **2 at 250 °C and 1 at 230 °C**, on 132 stress-benign cases
per cap. A tested curvature veto removed the three known nuisance losses but
missed a genuine contact loss late in a probe. No threshold, expected count,
retry rule, SIL coverage requirement, B5 safety bar, or leakage ratchet is
relaxed. `contact_check.c/.h`, `pan_temp_loop.c`, and `pan_control.c` are unchanged.

`d1_nuisance.py` uses the unchanged `rim_limit.stress_benign()` factory and
`leak_checks.run_case`, with exactly `setpoint_cap.capped_cases` cap semantics:
set `LC.SP_FRY` **before** constructing cases, then cap the setpoint profile.
The factory is authoritative: its named benign corner is `hot_stack` (hot bead,
3242 mV rail, 4.53 K self-heating), not the `cold_stack` used for stress leaks.
The 230 °C down-step is 230→130 °C, not a clipped 250→150 °C case. Existing
hot-glass initial conditions are preserved.

The script records every LOST event, complete probe/retry windows with the
float32 C inputs, actual C outputs and parameters, independent regression
checks, trigger sources, true pan/glass temperatures, restoration and zero-power
intervals. A read-only host-shim getter avoids duplicating the C struct layout.
`--check` compares every value and source hash exactly; only the six explicitly
named toolchain strings are excluded. The acquisition base is
`ebf8a777b50ecb81040fc0c56fa8bde706720638`; changed/new source bytes are listed
independently of the current branch HEAD. The new `d1-nuisance.json` is the
requested diagnostic evidence; pre-existing regenerated JSON is not replaced.

### Reproduction and rule that fires

All three failures are `sp_down`, `tau_g=106 s`, `t_eye=139.7 °C`, `delta=0`,
`hot_stack`. The target drops at 900 s. These are intact-contact simulations.

| Cap | Case | Pan / seed | h (W/m²K) | Glass weight | LOST (s) | d / d_expected (K/kJ) | Decay RMS / change (K) |
|---|---|---|---:|---:|---:|---|---|
| 250 | stress_benign/73 | carbon_steel_28 / 40014 | 3633.271253 | 0.9554 | 1195.5 | −0.220356 / 2.036979 | 0.485260 / 2.197325 |
| 250 | stress_benign/109 | cast_iron_26 / 40020 | 3396.469932 | 0.9554 | 1261.6 | −0.139180 / 1.026852 | 0.278492 / 1.005648 |
| 230 | stress_benign/91 | carbon_steel_28 / 40017 | 3633.271253 | 0.6457 | 1177.9 | −0.247776 / 1.905633 | 0.474339 / 1.600528 |

The rim cross-check requests the decisive probes at 1177.5, 1243.6 and 1159.9 s.
They are ordinary first probes, not retry or contact-shift escalation decisions.
Each lasts 18 s, including an 8 s, 900 W pulse. The `[1,t,t²,E_lag]` response
fit gives a **negative** energy coefficient, below `0.25*d_expected`; the
free-decay fit nevertheless passes RMS ≤0.5 K and change ≥1 K, so D1 declares
LOST. The delayed intact-pan response is absorbed into the polynomial terms.
The free-decay fit's residual tolerance accepts the incompatible curvature.
For carbon steel at 250 °C, the independent response coefficient is −6.017
standard errors, so this is not a marginal three-sigma classification.

During that probe, true pan temperature rises from 147.033 to 150.167 °C;
the effective rim falls from 180.703 to 177.144 °C. The corresponding rise and
curvature coefficients are 37.878 and 23.644 standard errors above zero.
The other two cases show the same shape (20.115/12.588 and 29.407/25.006 sigma).
These shape statistics are diagnostic evidence, **not an active firmware rule**.

| Case | LOST duration (s) | Cumulative zero power after LOST (s) | Zero power while PID wanted heat (s) |
|---|---:|---:|---:|
| 250 / 73 | ≥304.5, censored at 1500 s | 240.5 | 2.7 |
| 250 / 109 | ≥238.4, censored at 1500 s | 190.4 | 97.7 |
| 230 / 91 | 190.0, restored at 1367.9 s | 156.1 | 0.0 |

The zero-power interval containing the initial LOST event is **30 s in each case**. Retry
pulses interrupt subsequent off time: LOST duration is not continuous power-off
duration. The diagnostic reports these separately and marks horizon censoring.

### Rejected fix and a safety regression test

An isolated candidate rejected the first-probe decay hypothesis when both rise
and upward curvature exceeded the existing three-sigma bar and every effective
rim sample was non-increasing. It left retry behavior unchanged. Under the
single-node passive model, `y''=(rim'-y')/tau`, so a rising detached sensor with
a cooling rim cannot accelerate. The three original failing trajectories then
had `D1 LOST 0/3`; a broader candidate sweep was stopped after the counterexample
below, so no 264-case candidate pass is claimed.

That argument assumes the whole probe describes detached relaxation. A real
loss **during** the probe leaves an intact prefix. In stress_benign/73, changing
contact conductance from 3633.271253 to 2 W/m²K at **1193.5 s**, matching the
existing `cosim.run_case` lift convention, gives:

- Original controller: LOST at **1195.5 s**, latency **2.0 s**; all eight retry
  probes stay LOST through 1500 s.
- Candidate: PROBE_PASSED at 1195.5 s and **no LOST through 1500 s** (306.5 s
  after the lift). There are no later probes, including after its 30 s holdoff.
  The passive rim-limit report reaches **232.7 °C at 1480.7 s against a 150 °C
  target**; the supervisor reports R2b at 1499.6 s.

At the changed decision, d=−0.125010, d_expected=2.036979, decay RMS=0.446454 K,
change=2.079746 K. Rise/curvature still measure 37.05/22.11 sigma because the
window contains 16 s intact and only 2 s detached. Tuning the significance bar
is not a justified remedy. This is a model counterexample, not a bench result.

`test_late_lift_during_probe_remains_lost` replays those exact C input samples
and requires LOST, its event, and a zero-power override. With unchanged D1:
`12 Tests 0 Failures 0 Ignored`; with the rejected candidate:
`test_late_lift_during_probe_remains_lost:FAIL: Expected 2 Was 0` and
`12 Tests 1 Failures 0 Ignored`. No candidate detector code is landed.

The five Python diagnostic tests cover exact evidence comparison (including a
one-ULP numerical change), both cap factories/down-steps, zero intervals that
continue after RESTORED, censoring, and a supplied library inconsistent with
current sources. The full diagnostic is gated in `run.sh` after B5.

### Validation and remaining work

Untouched baseline: host CTest `100% tests passed, 0 tests failed out of 26`;
the all-target build retains the known unregistered `test_profiles.c` failure.
On Linux, the build directory alone needs `CMAKE_C_STANDARD_LIBRARIES=-lm`
for the existing power-gate test; no CMake source was changed. Coverage remains
`31 scenarios, 20/20 designed pairs covered` (legacy), `52 scenarios, 28/28
designed pairs covered` (C1), and `27/27` mechanism cells. Trace freshness,
invariants, state-machine model, fault-list consistency and pin map pass.
The new diagnostic tests report `5 passed`. All 264 full LC result rows match
the independently acquired baseline exactly. All 22 existing D1 vector lines,
28 legacy SIL latency lines and 49 C1 SIL latency lines match before/after
exactly. The four golden real-loss confirm delays remain 20.6, 20.2, 20.3 and
19.7 s (triply clad, water pot, carbon steel and cast iron respectively).
The new late-lift unit reports `12 Tests 0 Failures 0 Ignored`.
`Import boundary gate PASSED — 0 new violations`; Ruff reports
`All checks passed!`. These results are measured, not inferred from the
unchanged source.

The untouched full runner passes co-simulation, cross-check, h_c robustness,
leakage, rim-limit, cold-soak, B5 (`== firmware: PASS`), runaway and sensor-code
checks. The two other B5 variants retain their expected report-only FAILs.
Leakage reports `hazardous: 277 latched before 300: 69 after: 204 never: 4`;
its 69-minimum / 4-maximum ratchets remain unchanged.

The requested short baseline commands were rerun after the change. Exact
before/after output is recorded below; “same” means the displayed output matched
literally, not merely that both commands returned success.

| Command | Before | After |
|---|---|---|
| `cmake -S . -B build` in `firmware/test` | `-- Build files have been written to: /workspace/temper/firmware/test/build` | Same |
| `cmake --build build -j -- -k` | `gmake: Target 'default_target' not remade because of errors.` | Same known profiles failure |
| `ctest` in `firmware/test/build` | `100% tests passed, 0 tests failed out of 26` | Same |
| `test_sil_coverage.py --gate` | `SUMMARY legacy: 31 scenarios, 20/20 designed pairs covered`; `SUMMARY c1: 52 scenarios, 28/28 designed pairs covered`; `SUMMARY c1 mechanisms: 27/27 cells covered`; `PASS` | Same |
| `gen_sil_traces.py --check` | `SIL traces up to date (27 generated traces)` | Same |
| `check_firmware_invariants.py` | `OK: all 5 invariants verified and proof_record.json is fresh` | Same |
| `check_state_machine_model.py` | `OK: state machine model check passed (reachability, P1-P4, manifest cross-check)` | Same |
| `check_fault_list_consistency.py` | `fault list consistency check passed`; manifest 14, generated 16, supplemental 3 | Same |
| `check_board_pin_map.py` | `PASSED: temper_pins.h agrees with zapote/controller controller-c1-crs at 467917c38 (36 GPIOs, 10 expander pins)` | Same |

The first unadjusted Linux baseline additionally failed to link power_gate_tests
(`undefined reference to 'exp'` and `'floor'`), with `96% tests passed, 1 tests
failed out of 26`. The build-cache-only `-lm` adjustment described above was
applied before measuring the comparable 26/26 baseline and after results.

The post-change runner also passes B5 and the new exact diagnostic check:

```text
== firmware: PASS
D1 cap=250: 132 stress_benign; LOST cases=2 events=2 max=2 PASS
D1 cap=230: 132 stress_benign; LOST cases=1 events=1 max=1 PASS
D1 nuisance evidence: MATCH (exact values and source hashes; toolchain strings excluded)
D1 NUISANCE PASS
```

Comparing the two independently generated Linux evidence sets reports
`LEAK PARITY: all 624 leak and 548 benign rows, summaries and gates exactly equal PASS`
and `B5 PARITY: all variant summaries and gates exactly equal PASS`. These are
whole-object comparisons, including all report-only B5 variants. The measured
firmware real-lift rows are:

| Pan | Detected, before→after | Worst suspect (s), before→after | Worst confirm (s), before→after | False restores, before→after |
|---|---|---|---|---|
| carbon_steel_28 | 20/20→20/20 | 2.6→2.6 | 20.6→20.6 | 0→0 |
| cast_iron_26 | 20/20→20/20 | 2.6→2.6 | 20.6→20.6 | 0→0 |
| disc_pot_water_1l5 | 20/20→20/20 | 3.4→3.4 | 21.4→21.4 | 0→0 |
| triply_clad_24 | 20/20→20/20 | 2.7→2.7 | 20.7→20.7 | 0→0 |

D1 LOST per leak resistance (48 cases per resistance) is unchanged:

| Resistance (Ω) | Before | After |
|---:|---:|---:|
| 300.0 | 2 | 2 |
| 401.8 | 4 | 4 |
| 538.2 | 6 | 6 |
| 720.8 | 16 | 16 |
| 965.5 | 11 | 11 |
| 1293.2 | 8 | 8 |
| 1732.1 | 0 | 0 |
| 2319.9 | 0 | 0 |
| 3107.2 | 0 | 0 |
| 4161.8 | 0 | 0 |
| 5574.3 | 0 | 0 |
| 7466.1 | 0 | 0 |
| 10000.0 | 0 | 0 |

The runner then stops at `T1 FAIL: derivation gates failed: source_inputs_clean`:
its freshly generated Linux `leak-checks.json` differs from the committed Mac
file. Restoring the six changed tracked JSON files yields `T1 PASS` on the
untouched sources. Those files are cosim-results.json, fault-cycle.json,
leak-checks.json, runaway-checks.json, xcheck-cosim.json, and
../robustness/hc-cosim.json; their generated copies were preserved for comparison.
No existing generated JSON is committed. In leak-checks.json the observed
cross-platform drift is five stored event-time fields: 527.8→527.9 s (rim-limit
and first latch), and rim-fault times 1554.8→1554.4, 1325.0→1325.1 and
1292.1→1291.9 s. The 69/204/4 coverage counts and all D1 leak classifications
are unchanged from the retained evidence.

The completed post-change full runner also reports `ALL RUNAWAY CHECKS PASS`
and `SENSOR FAIL CODES PASS`, then ends with the same
`T1 FAIL: derivation gates failed: source_inputs_clean`. Thus the requested
before/after `./run.sh` final lines are identical failures; neither run reaches
T2, sensitivity, or `ALL C1 FIRMWARE CHECKS PASS`. All six regenerated JSON
objects match the independent Linux baseline exactly, including runaway data.
Their after-run copies were saved and the tracked originals restored.

After restoration and committing the F1 sources/documentation, a direct
`leak_barrier.py --check` still exits 1:
`T1 FAIL: regenerated JSON differs from /workspace/temper/output/temper-sensor-r3/leak-barrier/leak-barrier.json`.
The clean-tree gate is then satisfied, but the retained evidence's source hashes
are stale for the new decision record and shim. The existing T1 JSON is left
unchanged as required; resolving its provenance belongs to the authorized Mac
evidence refresh, not a relaxed comparison here.

T1 also fingerprints this decision record and the host shim; T2 fingerprints
all firmware study Python files and the shim and demands unchanged inputs
against its fixed base. A metadata-only T2 preflight after instrumentation
reports `source_inputs_unchanged: False` and
`input_sha256 matches retained evidence: False`. Its full numerical sweep was
not reached by the baseline runner. These provenance/evidence gates are not
waived or rebased, and no `ALL C1 FIRMWARE CHECKS PASS` claim is made.

`idf.py` is absent, so no ESP-IDF build is claimed. The firmware-board-contract
check is deliberately skipped because its required board branch is unpushed.
The environment check used live KiCad 10.99 nightly IPC; no boards were edited.

A future fix needs a probe design or model that separates the delayed intact
response from a late loss within the same window, including cooling-glass lift
onset sweeps and bench measurements. The current study establishes the nuisance
mechanism and a counterexample to one proposed fix; it does not prove no safe
fix exists.
