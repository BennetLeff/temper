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
catches every loss first: the results are identical at both margins. It is
covered by unit tests only.

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
  - `read_rim_ntc_temperature()` (a new peripherals extern);
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
  RTD resistance interlock uses the C1 window, 84.27 / 233.21 Ω.

## D-THRESH. C1 threshold words: 12844 / 35542 (CR-7 lists 35544)

These are new `config.yaml` constants with `board_derivation: true` and
derivations in `firmware/tools/board_derivations.yaml`:
- `RTD_C1_SHORT_FAULT_OHM` 84.27;
- `RTD_C1_OPEN_FAULT_OHM` 233.21;
- `MAX31865_C1_LOW_THRESHOLD_WORD` 12844;
- `MAX31865_C1_HIGH_THRESHOLD_WORD` 35542.

The board contract rounds the low code up and the high code down, so the
window stays inside the requested resistances:
- 84.27 Ω gives code 6421.7, which rounds up to 6422 (word 12844);
- 233.21 Ω gives code 17771.95, which rounds down to 17771 (word 35542).

CR-7's 35544 is 233.22 Ω, just outside the window. The oracle caught it, and
`scripts/check_firmware_board_contract.py` passes 5/5. The legacy words
1526/45722 are unchanged.

## D-CR7. Where each CR-7 item landed

| CR-7 item | Where |
|---|---|
| CONFIG 0xC0 (VBIAS, auto conversion, 60 Hz) | `max31865_start_conversions`, after the power-up cycle |
| One automatic fault cycle at power-up, coil off; completion by polling CONFIG D3:D2 | `rtd_service` C1 bootstrap / `max31865_fault_cycle_busy`. **Manual** cycle (needs CR-1 filter): open |
| Thresholds 84.27 / 233.21 Ω | D-THRESH |
| Self-heating 0.061 K subtracted | `rtd_convert_code_to_c` |
| Loading correction R − (7.86e-4·R − 0.0331) | `rtd_convert`, behind `RTD_FRONT_END_CR1` (default 0: the captured controller has no CR-1) |
| Stale: no DRDY for 3 × 20 ms | `RTD_C1_STALE_CONTROL_TICKS` 6 (60 ms) |
| Rim ADC attenuation and rim faults | no rim driver exists (open) |
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
     `peripherals_init`, …). This work adds `read_rim_ntc_temperature`.

   All C1 objects compile with the real IDF flags (`xtensa-esp32s3-elf-gcc`,
   `TEMPER_PAN_CONTROL_C1=1`):
   - the 7 `control` sources;
   - `pan_control.c`, `rtd_service.c`, `rtd_convert.c`, `max31865.c` and
     `state_handlers.c`;
   - `state_machine.c` and `main.c`, which compile once IDF's hal includes
     are put ahead of the shadow.
2. **Rim NTC driver and rim faults** (CR-7 rim ADC attenuation): not
   implemented. The loop's cross-check needs `read_rim_ntc_temperature()`.
3. **Manual fault-detection cycle** (needs the CR-1 filter): not implemented.
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
7. **CR-7 high threshold word:** CR-7 lists 35544 and the firmware has 35542
   (D-THRESH). The PCB agent should confirm.
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
