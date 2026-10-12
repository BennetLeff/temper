# Native-21 power stage: bench bring-up and commissioning

This procedure takes the integrated SELV controller (`zapote/controller`) and native-21
(`zapote/power-stage-120v`) from first power to the point where firmware may set
`commissioned=true`. Neither board has been built or powered yet. Every number below is either cited
to its source or marked **provisional**, and the bench measurement replaces it.

The firmware pieces are:
- `n21_signal.{c,h}` and `n21_binding.{c,h}`: the logic, host-tested by `firmware/test/test_n21_binding.c`.
- `tank_freq.{c,h}`: the commissioned tank ceiling, the trips derived from it, the no-pan clamp and the per-pan frequency loop (stage 15, DECISIONS 10), host-tested by `firmware/test/test_tank_freq.c` against a first-harmonic RLC tank.
- `n21_hw_esp32.c`: the ESP32-S3 peripheral code.
- `Kconfig`: the switches and calibration fields.

## Ground rules

- **Default is off.** `CONFIG_TEMPER_POWER_HW_BINDING=n` leaves the power service unbound. With the binding on, the default mode is `INHIBITED`: PWM pads are held low and acquisition runs for telemetry only. Nothing in this document changes a default in the repository. Bench settings live in a local `sdkconfig`, never in `sdkconfig.defaults`.
- **Firmware never asserts PERMIT.** PERMIT (J4.9) comes only from the interlock latch. Firmware can only request a reset edge on IL_RESET_N (GPIO17), through `n21_request_interlock_reset(…, operator_confirmed=true)`.
  - That call is refused while PWM is live, while any interlock source reads faulted, or within 1 s of the previous request.
  - It is never called from a fault, sample or tick path.
- **Faults latch until MCU reset.** Any input fault, or a stale sample, makes `sample()` return false. `power_service` then forces the pads low and trips; it does not rebind. Hardware trips latch PERMIT independently and need the operator reset.
- **Isolation.** Every measurement on the HOT side uses isolated or differential probes. Use the isolation transformer for every AC step, and the power analyser in the inlet path.
- **Never weaken a check to make a step pass.** If a step needs a lower trip to demonstrate it, lower it in the bench `sdkconfig` only, and restore it before the next step.
- **Board revision.** The trip numbers below are for the **stage-15** board (R34 12.6 kΩ, R43/R46 2.21 kΩ). On a stage-14 board (CT band 50.56–60.01 A) the derived 22 A firmware peak trip (50.74 A) is *not* below the CT band's low corner. Do not run this firmware on a stage-14 board at power without lowering `tank_peak_trip_a` below the measured CT trip in the bench config.

## Modes and what flips `commissioned=true`

| Kconfig | Effect |
|---|---|
| `TEMPER_POWER_MODE_INHIBITED` (default) | Pads low; no binding; acquisition telemetry available |
| `TEMPER_POWER_MODE_BENCH` | `n21_bench_start(ms, confirmed)` runs bounded (≤ 60 s) live-PWM sessions without the adapter. Every acquisition fault check and the capture-timing check (same window as `fullbridge_apply`) stop the session. Never ship |
| `TEMPER_POWER_MODE_COMMISSIONED` | `n21_binding_init` builds `bridge_config_t` with `commissioned=true` and the power service binds. **Only** if all three conditions below hold; otherwise it returns `N21_INIT_NOT_CALIBRATED` or `N21_INIT_NO_RUN_GATE` and the pads stay low |

The three conditions for `commissioned=true`:
1. `CONFIG_TEMPER_POWER_CALIBRATED=y`, set in the same reviewed change that enters the commissioning record (end of this document);
2. the hardware has a firmware run gate (open question **H1**). Controller layout L2 adds it (RUN_EN on GPIO14, PERMIT = latch AND RUN_EN through U37, DECISIONS C23), and `n21_hw_esp32.c` now passes `run_gate` on it. On an earlier controller capture without U37 the gate does nothing, so do not select COMMISSIONED there;
3. steps 1–9 below have passed, with their evidence filed.

**When:** only after step 10's sign-off. Burst mode stays disabled (`burst_enabled=false`) after that too. Enabling it is a separate gate (DECISIONS 2026-10-06: LINE_ZC scheduler, F6 capture, B2).

## Step 0: build gate (desk)

1. Run the host suite. Every test must pass, including `n21_binding_tests`.
   ```sh
   cmake -S firmware/test -B build-host
   cmake --build build-host
   ctest --test-dir build-host
   ```
2. Build with ESP-IDF v5.2.x, `CONFIG_TEMPER_POWER_HW_BINDING=y`, mode INHIBITED. `n21_hw_esp32.c` has so far only been syntax-checked against stub headers; this is its first real compile. Fix any API drift without changing the logic in `n21_binding.c`.
3. **H3** is resolved for layout L2: the RTD service uses `controller_pins.h` (SCK 11, SDI 13, SDO 12, CS 10, mode 3) and samples DRDY from TCA9555 P07. Run `python3 firmware/tools/check_controller_pinmap.py` before flashing; it checks the firmware map against the controller ato.

## Step 1: controller alone (no native-21)

Setup: a bench 15 V, current-limited to 1 A, into J4.1/J4.2. J4 goes to a breakout with 10 kΩ loads on the PWM lines.

1. **Rails:**
   - v3v3 is 3.242–3.367 V.
   - RAIL_OK (GPIO35) reads high.
   - SUP_RUN_OK (TCA9555 P14 since R36, DECISIONS C27; read from the expander snapshot) reads high while the WDI (GPIO18) heartbeat runs. It drops within 0.9–1.6 s when the heartbeat stops (halt the control task).
2. **Pads low at every boot phase.** Scope all four PWM lines through reset, boot ROM, app start and `n21_hw_start`. Expected: low throughout, with no pulse over 0.8 V (D-25, controller misc checks). Repeat with the MCU held in reset and with it unpowered (10 kΩ pull-downs).
3. **Interlock with J4.10 open:**
   - BUS_FAULT_RB reads high (10 kΩ pull-up) and PERMIT_RB stays low.
   - `n21_request_interlock_reset(true)` is refused (bus_fault), and the IL_RESET_N scope shows no edge.
   - Tie J4.10 low on the breakout and request again: one falling edge, and PERMIT_RB goes high.
   - Lift the tie: PERMIT drops with no firmware action.
4. **Analog front ends.** These set the VBUS and CT_MON trims (enter them in the record):
   - **VBUS:** drive J4.11–J4.12 differentially with a calibrated source at `k·V`, where k = 15.8k/(4×470k+15.8k) = 8.334 × 10⁻³ (D-11). Use 0 V, 1.417 V (170 V equivalent) and 1.650 V (198 V).
     - Expected readings: 247.8 / 956.2 / 1072.9 mV (`controller_calcs.d11_receiver`).
     - `TEMPER_POWER_VBUS_OFFSET_UV` is the 0 V reading minus 247.77 mV.
     - `TEMPER_POWER_VBUS_GAIN_PPM` is the ratio that maps 170 V exactly.
     - D-11 allows ±6 %.
   - **VBUS thresholds:** 95 mV equivalent must give "invalid", and 1215 mV the latched `N21_FAULT_VBUS_OVERRANGE` (231 V).
   - **CT_MON:** with J4.14 driven at 1.650 V DC, record the reading as `TEMPER_POWER_CT_MON_ZERO_MV`. With J4.14 open, the reading is < 50 mV ("unplugged").
   - **Tank RMS:** drive J4.14 with 1.650 V DC plus a 40 kHz sine of 0.330 V rms (22 A equivalent at 15 mV/A).
     - Expected: telemetry `tank_rms_a` = 22.0 A and `v3v3` within 3.242–3.367 V.
     - Set `TEMPER_POWER_RMS_GAIN_PPM` from the error.
     - Repeat at 31 and 55 kHz; the error must be ≤ 1 % (AD8436 65 kHz figure, C19).
     - Step the sine on and off and measure settling to 0.1 %. It must be ≤ 3.4 ms (assumed in C19, bench item 5).
   - **SPI sharing:** run the MAX31865 conversion loop at the same time and confirm both devices read correctly for 10 min with no `N21_FAULT_RMS_CHANNEL` (mode 3, bus lock).
5. **ADC pattern (C12 flag):** check the logged sample rates: VBUS ≥ 20 kS/s with a gap ≤ 150 µs, and CT_MON 20 kS/s with the repeated-channel pattern on this IDF version.

## Step 2: native-21 logic powered, HV bus dead, gates disconnected

Setup:
- Native-21 SELV and HOT logic and gate supplies powered: V15_LS and the F6 bias come from isolated bench supplies; the DC bus is at 0 V and shorted through 10 kΩ.
- **FET gates disconnected:** gate resistors not fitted, or the driver outputs lifted, and each driver output loaded with 10 nF to its source return.
- The controller is powered from J4.1 as in step 1, with the real J4 harness.
- Mode BENCH, `TEMPER_POWER_F_MAX_HZ=50000` (a test value, as in round 5; bench sessions run at F_MAX, the loop runs only in COMMISSIONED).

1. **Interlock:**
   - With all sources healthy, BUS_FAULT_RB reads low.
   - Request a reset (operator-confirmed); PERMIT goes high.
   - Remove V15_LS: HOT5 → BUS_FAULT goes high and PERMIT drops (FAULT-INTERFACE.md). Record the latency from the V15_LS collapse to DIS high.
2. **PWM verification, PERMIT low** (drivers disabled by DIS):
   - Run `n21_bench_start(2000, true)`.
   - At the J4 pads, measure:
     - period 20.00 µs (1600 ticks at 80 MHz);
     - HA/LA and HB/LB complementary;
     - leg B 180° from leg A;
     - MCU non-overlap ≥ 200 ns (16 ticks) on all four transitions (DECISIONS 2026-10-03 O07). Record the measured value: the capture check accepts 16–18 ticks.
   - The driver outputs must stay low throughout (DIS).
   - The session must end at 2 s with the pads low and no fault.
3. **PWM verification, PERMIT high** (drivers enabled, gates still disconnected):
   - Repeat item 2 and measure at the driver outputs (into the 10 nF loads).
   - **Driver dead time:** 396.6–488 ns on every transition (R9/R17 49.9 kΩ, DECISIONS 2026-10-03). Record the value per transition.
   - No overlap at any transition, including the first period after the force release and the last before the force.
4. **Stop paths:**
   - During a session, pull J4.10 high: the session stops (`permit && bus_fault`), the pads go low and PERMIT drops.
   - Repeat with the acquisition task suspended (stale sample → stop) and with the CT_ZC line held (no fault expected at 0 A).
   - Inject a capture mismatch: swap the HB/LB harness wires. Expect an `N21_FAULT_PWM` stop on the first poll.
5. **Reset and brown-out:**
   - Reset the MCU mid-session: pads low within the reset assertion, drivers low (D-25).
   - Brown out v3v3 slowly: RAIL_OK trips before the TPS3823 and the UCC21550 VCCI UVLO (FMEA order). Record the order.

## Step 3: over-current and over-voltage trip calibration

Gates stay disconnected and the bus stays dead unless stated otherwise.

1. **Tank-CT comparators** (U10–U13; stage 15: R43/R46 2.21 kΩ, band **64.55–76.09 A** both polarities, exact-corner model, stage-15 PLAN §3):
   - Pass a test winding of N turns through T1 and drive it from an amplifier at 40 kHz, measuring current with a calibrated probe.
   - Raise slowly until BUS_FAULT goes high, then repeat for each polarity (use a half-wave drive per polarity).
   - Record the trip current, both polarities, and the latency to DIS high.
   - **Pass:** both polarities ≥ 64.17 A (round-6 floor at 28 A) and inside the band.
   - Firmware: the raw CT_MON supplementary trip (`tank_peak_trip_a` = min(2.17 × ceiling + 3, 62) A: 50.74 A at 22 A, 62 A at 28 A; config cap < 64.5 A) must latch `N21_FAULT_TANK_PEAK` before or at the hardware trip. Check it at the commissioned ceiling's value. It is asynchronous sampling, so record its hit rate; it is not a qualified protection.
2. **Shunt OCP** (R5 1 mΩ; stage 15: R34 12.6 kΩ / R35 11.7 kΩ, band **66.30–118.74 A** after the Kelvin shift, nominal 92.6 A, stage-15 PLAN §1):
   - With the bus dead, inject a current pulse through R5 from a pulse source, for example a capacitor discharge through a resistor, with the current probe on the loop.
   - Find the trip level with 10 µs pulses of rising amplitude.
   - Record the trip current and the delay to BUS_FAULT and to DIS.
3. **Bus OVP** (U7, 280 V) and **firmware over-range** (231 V, D-11):
   - Use a current-limited (≤ 50 mA) 300 V isolated DC supply on the bus, gates disconnected.
   - Raise slowly. The firmware `N21_FAULT_VBUS_OVERRANGE` latch must occur at 231 V ± 6 %, and BUS_FAULT at 280 V. Record both.
   - Discharge the bus, and confirm the firmware latch survives until MCU reset.

## Step 4: first switching on an isolated, current-limited DC supply

Setup:
- Gates connected, a nominal pan on the coil.
- Isolated DC supply on the bus, starting at ≤ 50 V, current-limited to 0.5 A (DECISIONS 2026-10-05 native-20 rule 1).
- BENCH mode, continuous only (no bursts).

1. **First edge capture** (S5 / F6, D-24): isolated probes on the partner VGS of each leg, the bus current, and both switch nodes. Run `n21_bench_start(200, true)`. The partner gate must stay below 3.0 V (rule 3) and the off-gate below 1.9 V; record both. Do the S4 commutation measurement from D-24 in the same session.
2. **ZVS check at light load:**
   - At 50 V, then in steps to 170 V, check on each edge that the switch node completes its swing before the incoming gate crosses its threshold (ZVS).
   - If an edge hard-switches, stop: frequency below resonance, or dead time too short.
   - Record bus current and tank current per step.
3. **Resonance map** (BENCH sessions at fixed `TEMPER_POWER_F_MAX_HZ`, one rebuild per point, 35–60 kHz) at 50 V, for the empty coil and each pan class:
   - Find resonance by stepping the bench frequency; record f_res, and the CT_ZC lag and tank current at 60, 55, 50, 45, 40 and 35 kHz.
   - ZVS at every point at or above max(35 kHz, 1.05 f_res), and lag ≥ 45° there (the loop's `zvs_lag_deg`). **Provisional:** `min_lag_deg` = 5° hard latch.
   - These lags feed the f_res-fit check (step 9a) and the pan-detect criteria (step 9a).
4. **Phase calibration:**
   - `TEMPER_POWER_VSW_DELAY_NS`: time from the PWM_LA command fall at the pad to the 50 % point of the switch-node A rise. **Provisional:** 100 ns.
   - `TEMPER_POWER_CT_ZC_DELAY_NS` and `TEMPER_POWER_CT_ZC_INVERTED`: time from the true tank-current zero (calibrated current probe, rising) to the CT_ZC edge. If CT_ZC rises on the falling current, set INVERTED.
   - Check: telemetry `phi_rad` against the scope-measured voltage-to-current phase, to within 3° at 3 frequencies.

## Step 5: variac on mains

Setup: isolation transformer → variac → power analyser → native-21 inlet. Start at about 30 V AC with the pan on.

1. **LINE_ZC:** the telemetry shows `zc_locked` within 4 pulses. With an isolated differential probe on the line, measure the true zero against the LINE_ZC pulse centre. `TEMPER_POWER_LINE_ZC_OFFSET_US` is centre minus zero (bench item from DECISIONS 2026-10-06). The predicted-zero error must then be ≤ 250 µs (D-11) at 108, 120 and 132 V.
2. **VBUS against the line:** with the bridge idle the bus holds the line peak. Telemetry `bus_v` against a DMM must agree within ±6 %. `last_half.line_rms_v` against the analyser's line RMS must read low (conservative) by less than 3 %. Leave `rectifier_drop_v = 0` unless the record justifies more.
3. Raise to 108 V and run 10 s bench sessions. Each half cycle must close (`halves_bad` not increasing with the bridge running).

## Step 6: tank current ramp with a pan

1. Raise the variac 108 → 120 → 132 V with nominal, low-R and high-R pans. Per point, record:
   - tank RMS (current probe through the coil lead) against telemetry `tank_rms_a`: within 2 % after the step 1 trim;
   - cos φ;
   - bus voltage;
   - tank and heatsink temperatures.
2. **Tank envelope at the commissioned ceiling** (22 A ships; DECISIONS 10): the per-pan loop (step 9a) *regulates* the half-cycle tank RMS to the ceiling; the binding *trips* (`N21_FAULT_TANK_RMS`) at `tank_rms_trip_a` = 1.05 × ceiling **on the half-cycle RMS** (23.1 A at 22 A), and on any single AD8436 sample above the crest guard 1.5 × ceiling (33 A at 22 A). The per-sample reading is the 120 Hz envelope crest, about 1.41 × the half-cycle RMS (round 6), so it is not the trip quantity.
   - Demonstrate the half-cycle trip with `tank_rms_trip_a` temporarily lowered in the bench config to 10 A, then restore it.
   - Record per pan and line case the frequency the loop settles at, the telemetry reason (`freq_reason`) and the half-cycle RMS.
3. **AD8436 envelope smoothing** (C19 open item): compare the per-half-cycle mean of telemetry against the current probe's 120 Hz envelope. The resulting error feeds step 7.

## Step 7: inlet-current estimator error (sets e_est and the hold)

This step qualifies the firmware estimate that replaces a line-current sensor (DECISIONS 2026-10-08, "input current ≤ 15 A RMS", option (a)).

1. **Instruments:** a true-RMS power analyser (≥ 0.2 % basic accuracy, bandwidth ≥ 100 kHz) at the inlet. A separate measurement of the auxiliary current I_aux with the bridge idle at each line voltage.
2. **Grid:** line 108 / 120 / 132 V × pans (low-R, nominal, high-R; cold and at temperature) × at least 3 power points up to the highest power that stays ≤ 15 A at the inlet.
3. **Per point, over ≥ 10 s:**
   - I_line (analyser true RMS);
   - I_aux;
   - telemetry `last_half.est.i_ps_a` (the unmargined estimate), averaged over the same window;
   - `p_inv_w` and the analyser's input power, which also checks `eta_min = 0.93`.
4. **Error:** e = (I_line − I_aux) / i_ps_a − 1 at each point. Only under-estimation is unsafe. Take e_est = max(0, max e) + the analyser's uncertainty, rounded up to 0.5 %.
   - If any point shows efficiency below 0.93, lower `eta_min` instead of folding it into e_est.
   - If e_est > 0.5 the estimator is unusable (`input_limits_config_ok` rejects it), and the board needs a hardware line-current sense (DECISIONS option (b)).
5. **Set** `TEMPER_POWER_EST_ERROR_PPM = e_est × 10⁶`. The hold is then (13.5 − I_aux) / (1 + e_est) and the trip, where the bound reaches 15 A, (15 − I_aux) / (1 + e_est). Since stage 16, I_aux is scheduled with the blower (step 8c): 1.35 A with the blower off (11.05 / 12.41 A at the provisional 10 %), 2.03 A at typical blower (10.43 A hold), 2.57 A at full blower or whenever the drive is unknown (9.94 / 11.30 A). Recompute them and record them.
   - I_aux in this step is the measured auxiliary current at the blower state of each point; run the grid with the blower off and again at full blower.
6. **Re-run** the grid's highest-current points with the new value. Confirm that `inlet_bound_a` ≥ the analyser's I_line at every point.

## Step 8: thermal and endurance (bench mode)

At 120 V and the highest power inside the envelope, run 10 min sessions with heatsink, coil and R5 temperatures logged. R5's local ambient must be ≤ 100 °C (D-18 item 4). Over 50 sessions:
- no `halves_bad` growth while running;
- no nuisance `N21_FAULT_*` latches;
- no RAIL_OK trips from combined Wi-Fi/OLED load steps (controller bench item).

## Step 8b: controller L3 thermal and blower (firmware side of C28 / C32)

Firmware: `components/control/thermal_mgmt.{c,h}` (host-tested by `test/test_thermal_mgmt.c`), glue in `main/thermal_io.c` and `components/hal/esp32/controller_board_esp32.c`. Decisions recorded here (coordinator, 2026-10-12):
- **Blower duty cap 85 % (firmware side of C28).** Duty 0 = full speed (11.96–12.40 V). 100 % duty gives 5.03–5.78 V, below the Delta blower's 5.5 V floor at a corner, so the firmware never commands more than `BLOWER_PWM_DUTY_MAX` = 0.85 (≥ 6.07 V at every VFB / resistor / v3v3 corner).
- **Reset / brown-out speed accepted as fail-safe.** GPIO46 floats on its 100 kΩ strap pull-down: 11.0–11.4 V, near full speed.
- **Rim / coil plausibility (ADC top ~3.1 V: a cold NTC and an open one read alike).** Latched until MCU reset, shown on the display, all PROVISIONAL:
  - rim below its range (< ~70 °C, or open) while the pan RTD reads > 150 °C for > 30 s → rim-sensor fault; the 250 °C cap runs on the pan RTD alone;
  - coil below 25 °C after > 5 min (cumulative) at > 50 % power → coil-sensor fault; the tank ceiling is clamped to 22 A (`n21_set_thermal_tank_limit()`) and the blower runs full speed. A true open coil NTC is still latched by the thermal-sense OPEN_REF comparator.

Bench (record below):
1. FG pulses per revolution (`BLOWER_TACH_PULSES_PER_REV`, `config.yaml`): FG frequency against an optical rpm at fixed V_BLOWER.
2. V_BLOWER at duty 0, at 85 % and with the MCU held in reset; blower start at 85 % from standstill at the PS1 low corner.
3. Stall: lock the rotor, then unplug J10 and then open FG alone, each while driven: `power_cap_pct` falls to 10 % after > 1 s, then 0 if the sink or coil keeps rising (`BLOWER_STALL_RPM`, `BLOWER_STALL_POWER_CAP_PCT`, `BLOWER_STALL_RISE_K`).
4. ADC top: the calibrated reading of HS / COIL / RIM with the NTC open and with a 100 kΩ resistor in its place; confirm the ~3.1 V `THERMAL_ADC_MEAS_MAX_MV`.
5. Plausibility: unplug J12 with the pan above 150 °C (rim fault after 30 s); unplug the coil NTC (hardware OPEN_REF latch) and, separately, replace it with a 100 kΩ resistor (coil fault after 5 min at > 50 %). Tune the four constants from logged cold starts.

## Step 8c: blower supply PS3 inlet current against blower drive (replaces the model constants)

Stage 16 (power-stage DECISIONS 16) feeds the blower from PS3 (Mean Well IRM-60-15ST) on the mains tap F2 / J11. The inlet estimate counts it through an allowance scheduled with the commanded blower drive (`components/power/blower_aux.{c,h}`, host-tested by `test/test_blower_aux.c`):
- I_aux = PS1 + PS2 (1.3 A static, `aux_min_a`) + PS3(drive).
- PS3(drive) = P_blower / η_buck / (η_PS3 × PF × 108 V), with P_blower = 32.4 W × (V / 12 V)³ (Delta's maximum at 12 V, fan law), V the C28 drive map's upper envelope, η_buck 0.90, η_PS3 0.89 and PF 0.326 (IRM-60-SPEC p.2).
- Below full speed the allowance adds 15 % plus 0.05 A (PS3 idle).
- Full speed, unknown drive, failed blower write, stall, boot and an unconfirmed off all use the worst case, 2.57 A.
- Speed-ups take the allowance first (4 A/s, then 300 ms in force before the blower moves; the binding ramps it 0.05 A per half). A fault goes to full speed at once.

All of it is PROVISIONAL. This step replaces the model with measurements.

Setup:
- Bridge idle (no power request), so the inlet carries PS1 / PS2 / PS3 only; the inlet fed from the variac through the power analyser (true RMS, ≥ 0.2 %, bandwidth ≥ 100 kHz).
- A bench-config hook forces the blower drive (fan law bypassed); log `V_BLOWER` (J10), the 15 V rail at J13, the tach rpm and the duty.

Procedure:
1. **Baseline:** blower off with FAN_OFF confirmed (tach 0): I_PS1+PS2+PS3 at 108 / 120 / 132 V. This sets `base_a` + `idle_a`.
2. **Sweep:** drive 0 (duty 0.85), 0.25, 0.5, 0.75, 0.8 and 1.0 (duty 0), each settled ≥ 30 s, at 108 / 120 / 132 V. Record the true-RMS inlet current, real power, PF, V_BLOWER and rpm. Do it on two blowers if available (Delta's maximum vs typical spread).
3. **Model check:** at each point, the scheduled allowance (`blower_aux_level_a()`, printed by `test_blower_aux`) must be ≥ the measured auxiliary current. Report the worst ratio.
4. **Replace the constants** in `blower_aux_native21()` from the data, keeping each one conservative:
   - `vout_max_v` / `vout_slope_min_v`: the measured V_BLOWER envelope against duty;
   - `fan_law_exp` and `p_rated_max_w`: a fit of P_blower against V_BLOWER, through the highest unit; if the exponent fits below 3, use the fitted value (a lower exponent gives a larger allowance at partial drive);
   - `ps3_eta × ps3_pf`: the measured I_in × 108 V / P_out at the low line, taking the lowest product over load;
   - `idle_a` from step 1, and `margin` reduced only to cover the unit-to-unit spread seen.
   Re-run `test_blower_aux`; update its pinned numbers and the hold table in DECISIONS.
5. **Step-up on the bench (COMMISSIONED, after 9a):** at the inlet hold on the 120 V nominal pan, force the fan law from off to 0.8 drive, then a fault (full speed at once). With the analyser at 10 ms resolution, the inlet stays ≤ 13.5 A on the normal step and < 15 A on the fault step, with no `freq_reason` other than UP_INLET / HOLD_LIMIT and no adapter trip.
6. **Blower start (G-B1):** at a full-voltage enable, record PS3's output and input peak, and confirm no IRM-60 hiccup.
7. **BLW_PG (expander P16, controller C33):**
   - With PS3 on, P16 reads 1 and the diagnosis is clear.
   - Unplug J13 (PS3 output) with the bridge idle. P16 reads 0 after the 3-poll debounce, the start button stays in IDLE showing "NO BLOWER PWR", and no power is applied.
   - Unplug J13 with the blower forced on. After the > 1 s stall it is labelled "PS3 absent" and the C28 derate applies.
   - Unplug only J10 (blower) with PS3 on. The stall is labelled "blower failed".
   - Hold P16 low with a 1 k pull-down while the blower turns. After 3 s the BLW_PG sense fault latches and the firmware falls back to stall-only behaviour. Remove the pull-down and reset.

## Step 9a: per-pan frequency loop and no-pan clamp (COMMISSIONED, needs H1)

The loop (`tank_freq.h`) starts at F_MAX (60 kHz), steps down 250 Hz per closed half line cycle while every limit holds with 2 % to spare, holds in the band, and retreats (1 kHz, or 250 Hz for a marginal excess) when one is exceeded, blocking that frequency for 1 s. Limits: lag ≥ 45° and f ≥ 1.05 f_res (ZVS), f ≥ F_MIN, half-cycle RMS ≤ effective ceiling, inlet bound ≤ `inlet_target_a`, peak estimate ≤ peak trip − 3 A. A missing CT_ZC lag or a stale half steps up. Each live period change goes through `pwm_update` (MCPWM shadow registers, loaded at timer zero) and is ≤ 1 kHz per control tick.

1. **Live retiming (HIL, first):** 120 V variac, nominal pan, isolated probes on both switch nodes and all four gate commands. Force a 1 kHz step (bench config `step_up_hz`) down and up at 45 kHz and at 36 kHz, 20 times each, with persistence on. Pass: no truncated or merged period, MCU non-overlap ≥ 200 ns on every edge, ZVS kept on every edge of the transition period. Confirm `pwm_program` still starts the timer at the written period (`update_period_on_empty`).
2. **Descent:** at 120 V per pan class, log `freq_hz`, `floor_hz`, `f_res_hz`, `q`, `freq_reason` and the half RMS from gate-on to settle. Pass: monotone descent from 60 kHz, settle within 2 s, no trip, ZVS on the scope at the settled point, and `f_res_hz` within 3 % of step 4.3's measured resonance where a fit exists.
3. **Each limit, demonstrated:** with bench-lowered limits one at a time (ceiling via `TANK_CEILING_DA`=150, inlet via `inlet_target_a`, peak via `tank_peak_trip_a`), the loop settles on that limit (`freq_reason` HOLD_LIMIT / UP_x) without tripping. Remove CT_ZC (lift the lead at low power): `N21_FAULT_CT_ZC_STALE` latches above 2 A.
4. **Pan-detect tuning (no-pan clamp):** for the empty coil and every pan class (cold and hot), record at the settled point the telemetry `q` and p_inv / I² (`last_half.est.p_inv_w / tank_rms_a²`). Set `TEMPER_POWER_PAN_Q_MAX_X10` and `TEMPER_POWER_PAN_R_MIN_MOHM` between the empty-coil and the lowest-R pan values with ≥ 30 % margin each side. **Provisional:** Q ≤ 10, R ≥ 0.8 Ω (empty coil ~0.12–0.25 Ω, Q 50–100; a pan needing 28 A: ~1.4 Ω, Q 4–8).
5. **Power tracking:** per pan class at 120 V, `power_set_level` 15 / 35 / 60 / 100 %, and steps 20 → 60 → 15 % while running. Pass: analyser input power within ±6 % of the request (plus the e_est error) where the limits allow it, `freq_reason` HOLD_POWER, no frequency change over 60 s once settled; at 100 % the limit reason shows instead. Record the 60 kHz minimum power per pan (H12).
6. **No-pan clamp:** empty coil, ceiling set to 28 A in the bench config, 120 V and 132 V. Pass: `pan_present` stays false, `ceiling_eff_a` = 22 and the half RMS ≤ 22 A throughout; then lift a pan off mid-run at the 28 A ceiling: `pan_present` drops on the first half and the tank is back ≤ 22 A within 100 ms (otherwise the overrun latch `N21_FAULT_TANK_RMS` must fire). Measure the ferrite bar temperature in the no-pan case (enclosure item).

## Raising the commissioned tank ceiling (22 → 24 → 26 → 28 A)

The hardware is sized for 28 A (stage 15, DECISIONS 10). The firmware ships at **22 A** (`TEMPER_POWER_TANK_CEILING_DA=220`). The ceiling is one parameter; the RMS trip (1.05 ×), crest guard (1.5 ×) and peak trip (min(2.17 × + 3, 62) A) derive from it and cannot be set above their derived values (`config_ok`).

| Ceiling | Peak trip | Half-cycle RMS trip | Crest guard |
|---|---|---|---|
| 22 A | 50.74 A | 23.1 A | 33 A |
| 24 A | 55.08 A | 25.2 A | 36 A |
| 26 A | 59.42 A | 27.3 A | 39 A |
| 28 A | 62.0 A (cap) | 29.4 A | 42 A |

At 28 A the 62 A cap binds: with the peak estimate at 2.17 × RMS, the loop's peak limit (59 A) holds the line RMS to **27.2 A** until the bench calibrates the peak ratio (gate 5 below).

**Precondition for any raise above 22 A (once):**
- Stage-15 board confirmed: R34 = 12.6 kΩ (RT0603BRD0712K6L), R43/R46 = 2.21 kΩ (RT0603BRD072K21L).
- **B3 28 A pass** (task 04, the `c28` case with the `sw_a_low` path and the corrected bank rows): copper and pad cells ≤ 105 °C at 50 °C ambient, h 10 and h 25.
- Steps 0–9a above passed at 22 A, with the record filed.

**Per step N = 24, then 26, then 28 A — never skip a step.** Set N only in the bench config, run every gate at N A on the worst-case pan for the gate (and the 132 V line where it matters), and file the evidence:
1. **Bank hot-spot:** 10 min at N A, IR / thermocouple on the hottest TDK B32654A part. Rise ≤ 20 K at the enclosure ambient, or within TDK's p.57 curve at the measured local ambient (round 6: 0.89× at 22 A, 1.05× at 26 A, 1.12× at 28 A of the 85 °C curve).
2. **Coil:** R_ac ≤ 0.23 Ω at 40 kHz / 100 °C on the fitted coil (DECISIONS 10/12; 0.25 Ω is the acceptance limit but holds only 27.2 A), and winding temperature at N A, full blower, within the enclosure's coil limit; the coil-NTC derating loop stays enabled.
3. **Switching loss** at 45–50 kHz at N A (basis A vs B): FET Tj ≤ 125 °C with the fitted sink (basis A needs R_SA ≤ 0.233 °C/W at 28 A).
4. **Measured trip points:** the step 3 CT trip (both polarities) and shunt OCP measurements on this board; the derived firmware peak trip at N must be below the measured CT low trip, and the measured CT and shunt low trips must clear the round-6 envelope peak at N + 3 A pickup + 2 A (64.17 A at 28 A, stage-15 PLAN §1 basis A).
5. **Coil pickup at U6 INP−INN at 45–55 kHz** at N A (PICKUP.md; closes basis C of stage-15 PLAN §1), and the measured tank peak / half-cycle RMS ratio over the pan set (CT_MON raw max against the current probe). If the measured ratio is below 2.17 the `TANK_PEAK_PER_RMS` constant may be lowered in a reviewed change.
6. **B3 28 A pass** (above) still current for this board revision.
7. **Loop at N:** 50 × 10 min sessions across the pan set: half RMS settles ≤ N, no `N21_FAULT_*` latch, `freq_reason` and peak estimate logged.

Then one reviewed change sets `TEMPER_POWER_TANK_CEILING_DA` = 10 × N in the product sdkconfig for that unit or lot, and the record gains a row for N. **Any gate failing:** stay at the previous step (no partial raises); a gate failing at the current step after a hardware change lowers the ceiling back to the last step that passes.

## Step 9: run gate and adapter integration (H1: RUN_EN, layout L2)

Requires the hardware run gate (H1), fitted on controller layout L2 (RUN_EN, GPIO14, U37). `run_gate` in `n21_hw_esp32.c` drives it through `ctrl_board_set_run_en()`, which reads the pad back and refuses "on" after a firmware safety cut (`ctrl_board_run_en_kill()`, latched until MCU reset).

1. Check that the gate can only remove permission: pads live with the gate low gives driver outputs low with PERMIT high.
2. Mode COMMISSIONED with `CALIBRATED=y` on the bench, with the variac at 120 V. Expected:
   - the binding arms only after PERMIT high, all sources healthy, and LINE_ZC locked;
   - the pads run with the gate low;
   - `power_set_level` > 0 raises the gate;
   - `power_set_level(0)` lowers it without a trip.
3. Repeat every fault injection of `test_any_fault_inhibits` physically (J4.10, RAIL_OK, PERMIT, v3v3, VBUS over-range by supply, SPI unplug of U15, CT_ZC lead, LINE_ZC lead, stalled acquisition). Each must end with gate low, pads low, and the latch observed.

## Step 10: sign-off

The owner reviews:
- the commissioning record below;
- the step 2–9 evidence (scope captures and analyser logs, committed under the unit's validation folder);
- open questions H1–H2 closed.

Then one reviewed change sets `CONFIG_TEMPER_POWER_CALIBRATED=y`, enters the measured Kconfig values, and selects `TEMPER_POWER_MODE_COMMISSIONED` **in the product sdkconfig for that unit or lot**. `sdkconfig.defaults` stays INHIBITED.

## Commissioning record

| Field | Kconfig | Provisional | Measured | Step |
|---|---|---|---|---|
| VBUS zero offset | `VBUS_OFFSET_UV` | 0 | | 1 |
| VBUS gain | `VBUS_GAIN_PPM` | 0 (1.0) | | 1, 5 |
| CT_MON idle zero | `CT_MON_ZERO_MV` | 0 (1650) | | 1 |
| Tank RMS gain | `RMS_GAIN_PPM` | 0 (1.0) | | 1, 6 |
| MCU non-overlap (ticks, each transition) | — (200 ns fixed) | 16 | | 2 |
| Driver dead time (ns, each transition) | — | 396.6–488 | | 2 |
| CT comparator trip ± (A) | — | 64.55–76.09 (stage 15) | | 3 |
| Shunt OCP trip (A) | — | 66.30–118.74 (stage 15) | | 3 |
| Firmware over-range / OVP (V) | — | 231 / 280 | | 3 |
| Loop window (Hz) | `F_MAX_HZ`, `F_MIN_HZ` | 60000, 35000 | | 4, 9a |
| Live retiming HIL | — | not done | | 9a.1 |
| Pan detect: Q max, R min | `PAN_Q_MAX_X10`, `PAN_R_MIN_MOHM` | 100 (10), 800 (0.8 Ω) | | 9a.4 |
| Commissioned tank ceiling (A) | `TANK_CEILING_DA` | 220 (22 A) | | ceiling procedure |
| Measured tank peak / RMS ratio | (`TANK_PEAK_PER_RMS`) | 2.17 | | ceiling gate 5 |
| Switch-node delay (ns) | `VSW_DELAY_NS` | 100 | | 4 |
| CT_ZC delay (ns), polarity | `CT_ZC_DELAY_NS`, `CT_ZC_INVERTED` | 0, n | | 4 |
| LINE_ZC centre offset (µs) | `LINE_ZC_OFFSET_US` | 0 | | 5 |
| Estimator error e_est | `EST_ERROR_PPM` | 100000 | | 7 |
| Resulting hold / trip (A), blower off | — | 11.05 / 12.41 | | 7 |
| Resulting hold / trip (A), full blower or unknown | — | 9.94 / 11.30 | | 7, 8c |
| PS1 + PS2 static allowance (A) | (`blower_aux_native21` `base_a`) | 1.3 | | 8c.1 |
| PS3 idle (A), margin below full speed | (`idle_a`, `margin`) | 0.05, 15 % | | 8c.1, 8c.4 |
| Drive map envelope (V at duty 0, V per duty) | (`vout_max_v`, `vout_slope_min_v`) | 12.40, 6.57 | | 8c.4 |
| Blower power: max at 12 V (W), fan-law exponent | (`p_rated_max_w`, `fan_law_exp`) | 32.4, 3 | | 8c.4 |
| PS3 η × PF at 108 V | (`ps3_eta`, `ps3_pf`) | 0.89 × 0.326 | | 8c.4 |
| Worst-case auxiliary allowance (A) | (`input_limits` `aux_max_a`) | 2.57 | | 8c.3 |
| η_min check | (`input_limits_native21`) | 0.93 | | 7 |
| Blower FG pulses / rev | (`BLOWER_TACH_PULSES_PER_REV`, config.yaml) | 2 | | 8b.1 |
| Blower stall threshold (rpm) | (`BLOWER_STALL_RPM`) | 300 | | 8b.3 |
| ADC measurable top (mV) | (`THERMAL_ADC_MEAS_MAX_MV`) | 3100 | | 8b.4 |
| Rim plausibility: pan RTD, time | (`RIM_PLAUS_PAN_HOT_C`, `RIM_PLAUS_TIME_MS`) | 150 °C, 30 s | | 8b.5 |
| Coil plausibility: cold, power, time | (`COIL_PLAUS_*`) | 25 °C, 50 %, 5 min | | 8b.5 |

## Open hardware questions

- **H1. No firmware run gate (blocked COMMISSIONED; hardware closed by controller layout L2, DECISIONS C23: PERMIT = latch Q AND RUN_EN, RUN_EN on GPIO14 with a 4.7 kΩ pull-down; firmware `run_gate` implemented, bench step 9 still open).**
  - **The conflict:** `fullbridge_apply` qualifies the four PWM captures on every tick, idle included, and gates the drivers through a separate request. That is round 5's REQUEST → supervisor → SUP_RUN_OK path.
  - **This controller:** PERMIT comes only from the interlock latch, and the latch is granted by operator reset. So with PERMIT high, live pads mean a running bridge, and the pads cannot be qualified while idle.
  - **Proposed ECO:** native-21's PERMIT = latch Q AND RUN_EN. Firmware can only *remove* permission with it, never grant it. RUN_EN is pulled down, with a read-back through the LVC244.
  - **GPIO:** none is free. The candidates are TCA9555 P06/P07 (slow, adequate for an enable that is not a trip path), or freeing a GPIO.
  - **Rejected:** turning MAX31865 BIAS off to trip the runaway comparator as a stop. That makes a firmware reset request the "run" action, i.e. firmware asserting PERMIT.
- **H2. No power actuator at a fixed frequency.**
  - The adapter computes a conductance from the inlet hold (11.1 A; 9.94–11.05 A with the stage-16 blower allowance) and min(pan, tank ceiling), but `fullbridge_apply` uses it only as on/off. Phase shift is removed (DECISIONS 2026-10-05) and frequency is fixed (`power_service_frequency` accepts only the configured value).
  - **Stage 15 (partly closed):** the per-pan frequency loop (`tank_freq.h`) now regulates the tank ceiling, the inlet hold and the peak limit by frequency, from 60 kHz down. The trips stay as the backstop (adapter 15 A inlet bound; binding 1.05 × ceiling on the half-cycle RMS).
  - **Power level:** the adapter's `requested_w` (`power_set_level`) is the loop's power target: input power = min(request, the limit-bound maximum), in a ±6 % dead band (wider than the ~5.7 % power change of one 250 Hz step, so it cannot chatter). Every limit wins over the request; level 0 stops the bridge.
  - **Still open (H12):** below the power the pan draws at 60 kHz the loop caps at 60 kHz and over-delivers.
- **H3. The RTD service used the legacy pin map (resolved for layout L2).** It now uses `controller_pins.h`: SCK 11, SDI 13, SDO 12, CS 10, mode 3 (C20). DRDY moved from GPIO14 to TCA9555 P07 (C23); the control task samples it once per 10 ms tick and the service takes a high-to-low transition as completion. A DRDY low pulse shorter than one tick is missed and ends in the 100 ms fail-silent timeout (bench: confirm the MAX31865 DRDY stays low until the data registers are read).
- **H4. CT_ZC.** Its polarity and the T1 + TLV3201 delay across 31–55 kHz are unspecified, and so is the CT's phase error.
- **H5. Capture independence and channel count.**
  - The PWM feedback is a loop-back capture of the MCU's own pads. Round 5 used an external capture over JFAST, so this is not independent of the MCU. Confirm it is acceptable to the safety review.
  - It uses all six MCPWM capture channels (both groups), with HA captured in each group as the phase reference.
- **H6. C12 / C19 bench items:** repeated ADC1 channels in one continuous pattern; the AD8436 settling with CAVG = 100 nF and its envelope smoothing (steps 1 and 6).
- **H7. CT_MON raw path.** It is sampled asynchronously at 20 kS/s, so its peak trip (derived from the ceiling, 50.74 A at 22 A) is supplementary. The qualified over-current protection is the hardware CT comparators and the shunt OCP.
- **H8. Precharge and contactors.** `energy_supervisor` (precharge, K1/K2/KB) runs on an AUX-powered owner. Native-21 and this controller have no such owner. Confirm the inrush path, so this binding's assumption that the bus is simply present holds.
- **H9. LINE_ZC on J4.16.** The pin took a return contact; recheck it against the D-10/D-20 return allocation (DECISIONS 2026-10-06).
- **H10. Live MCPWM retiming.** `hw_pwm_update` relies on `update_period_on_empty` and `update_cmp_on_tez` shadow loading; never compiled against ESP-IDF or scoped (step 9a.1). Per-leg non-overlap does not depend on the load timing (one comparator per leg), but a period and its compares landing on different timer zeros gives one period of up to half-step duty error.
- **H11. Peak and f_res estimates.** The peak estimate is max(2.17 × half RMS, 1.485 × crest AD8436 sample, max |CT_MON| sample) and the f_res fit assumes a series RLC with constant L and R across a 2 kHz span; both are pre-measurement (ceiling gate 5, step 9a.2).
- **H12. Low-power operation.** The loop's lowest continuous power is what the pan draws at 60 kHz. The FHA model (120 V, 55 µH / 0.5 µF) gives about 73 W into a 1.4 Ω pan, 104 W at 2.0 Ω and 175 W at 3.5 Ω (×1.21 at 132 V). Requests below that are capped at 60 kHz and over-delivered (`TF_POWER_AT_FMAX`). Pulse-skipping or LINE_ZC burst (`burst_scheduler`, disabled) is out of scope here; the temperature PID above it sees the over-delivery.
- **H13. Blower off through an MCU-only hang (controller L3, accepted 2026-10-12).** Expander P15 FAN_OFF is a TCA9555 output latch, which an MCU reset or hang does not clear, so a hang while the fan law had the blower off leaves it off. Accepted: the TPS3823 watchdog drops PERMIT, so the tank is off too; a hang means blower off and tank off, which is safe (only residual heat). Open hardware options if that is ever not enough: a TCA9539 (the TCA9555 with a RESET pin) with RESET tied to the MCU's EN, so every MCU reset returns FAN_OFF to an input (blower on); or a hardware tach-loss trip (retriggerable monostable on FG into a spare interlock input, DECISIONS C28).
