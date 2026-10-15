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
  - No forgetting in the first heat-up; 0.99 per block on later ramps.
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

## Open items for the firmware owner

1. **Integration is not done.** `pan_temp_loop` is not wired into
   `state_handlers.c` or the ESP-IDF build. `main/CMakeLists.txt` does not
   list the new sources.
2. **Hot-pan placement against the runaway checks.** On hot-pan placement the
   reading rises at > 300 K/s. If that reading feeds the existing
   `check_runaway_boundary`, its 15 K/s rise latch (non-clearable RUNAWAY)
   would trip.
3. **h_c drops against the heating handler.** The heating handler's
   "temp > target + 10 → FAULT_THERMAL_RUNAWAY" would trip on the h_c-drop
   cases. Overshoot reaches 13.09 K for 1000 → 300 (`cosim-results.json`
   h_step: B1 0/4, B2 0/4, B3 2/4; reported, not gated).
4. **PCB CR-7 constants are driver-level** (`components/sensors/`, outside my
   write scope):
   - MAX31865 thresholds 12844 / 35544;
   - the loading correction;
   - the 0.061 K self-heating subtraction;
   - the 20 ms read with the 3-read stale rule;
   - rim ADC attenuation.

   The guard's stale check is a second layer at 10 Hz.
5. **Later-ramp identification never updates.** In every design case, a at the
   end of the run equals a at the end of the first ramp (`cosim-results.json`
   a_ratio_end). The later ramps are too short or not saturated.
6. **Hot-pan starts run on the prior.** a is never identified (no updates,
   src_mask 0), so a0 is used. For cast iron that is 2.34 × a_true. B1–B3 still pass.
