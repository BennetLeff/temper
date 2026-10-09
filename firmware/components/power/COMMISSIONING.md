# Native-21 power stage: bench bring-up and commissioning

This procedure takes the integrated SELV controller (`zapote/controller`) and native-21
(`zapote/power-stage-120v`) from first power to the point where firmware may set
`commissioned=true`. Neither board has been built or powered yet. Every number below is either cited
to its source or marked **provisional**, and the bench measurement replaces it.

The firmware pieces are:
- `n21_signal.{c,h}` and `n21_binding.{c,h}`: the logic, host-tested by `firmware/test/test_n21_binding.c`.
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

## Modes and what flips `commissioned=true`

| Kconfig | Effect |
|---|---|
| `TEMPER_POWER_MODE_INHIBITED` (default) | Pads low; no binding; acquisition telemetry available |
| `TEMPER_POWER_MODE_BENCH` | `n21_bench_start(ms, confirmed)` runs bounded (≤ 60 s) live-PWM sessions without the adapter. Every acquisition fault check and the capture-timing check (same window as `fullbridge_apply`) stop the session. Never ship |
| `TEMPER_POWER_MODE_COMMISSIONED` | `n21_binding_init` builds `bridge_config_t` with `commissioned=true` and the power service binds. **Only** if all three conditions below hold; otherwise it returns `N21_INIT_NOT_CALIBRATED` or `N21_INIT_NO_RUN_GATE` and the pads stay low |

The three conditions for `commissioned=true`:
1. `CONFIG_TEMPER_POWER_CALIBRATED=y`, set in the same reviewed change that enters the commissioning record (end of this document);
2. the hardware has a firmware run gate (open question **H1**). `n21_hw_esp32.c` passes `run_gate = NULL` today, so COMMISSIONED is refused on the controller as captured;
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
3. Resolve **H3** (RTD service pins and SPI mode) before flashing. Otherwise the MAX31865 bus comes up on the legacy pins, and GPIO8 is M12_ADC on this board.

## Step 1: controller alone (no native-21)

Setup: a bench 15 V, current-limited to 1 A, into J4.1/J4.2. J4 goes to a breakout with 10 kΩ loads on the PWM lines.

1. **Rails:**
   - v3v3 is 3.242–3.367 V.
   - RAIL_OK (GPIO35) reads high.
   - SUP_RUN_OK (GPIO37) reads high while the WDI heartbeat runs. It drops within 0.9–1.6 s when the heartbeat stops (halt the control task).
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
- Mode BENCH, `TEMPER_POWER_FREQUENCY_HZ=50000` (a test value, as in round 5).

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

1. **Tank-CT comparators** (U10–U13, ≈ 55 A, DC corner band 50.9–59.5 A):
   - Pass a test winding of N turns through T1 and drive it from an amplifier at 40 kHz, measuring current with a calibrated probe.
   - Raise slowly until BUS_FAULT goes high, then repeat for each polarity (use a half-wave drive per polarity).
   - Record the trip current, both polarities, and the latency to DIS high.
   - Firmware: the raw CT_MON supplementary trip (`tank_peak_trip_a` = 45 A, below the band) must latch `N21_FAULT_TANK_PEAK` before or at the hardware trip. It is asynchronous sampling, so record its hit rate; it is not a qualified protection.
2. **Shunt OCP** (R5 1 mΩ, R34 10.6 kΩ; band 49.73–97.98 A, DECISIONS 2026-10-05 D-31):
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
3. **Frequency selection** (`TEMPER_POWER_FREQUENCY_HZ`):
   - Find resonance with this coil and pan by stepping the bench frequency (one rebuild per point, 35–60 kHz allowed by `bridge_plan_cycle`) at 50 V.
   - Choose the fixed frequency on the inductive side with ZVS at every step, and a CT_ZC lag ≥ `min_lag_deg` + 5° at the lowest-inductance pan (D-20 O06).
   - **Provisional:** `min_lag_deg` = 5°. Task 05's envelope gives the final margin.
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
2. **22 A envelope** (DECISIONS 2026-10-08): the adapter at a fixed frequency cannot reduce power (open question **H2**), so the binding enforces the envelope by **tripping** at `tank_rms_trip_a` = 23.1 A.
   - Demonstrate the trip with the bench threshold temporarily set to 10 A, then restore 23.1 A.
   - Record which pan and line cases exceed 22 A at the chosen frequency. These are the cases where the product would trip today.
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
5. **Set** `TEMPER_POWER_EST_ERROR_PPM = e_est × 10⁶`. The hold is then (13.5 − 1.3) / (1 + e_est): 11.1 A at the provisional 10 %, 11.6 A at 5 %. The trip, where the bound reaches 15 A, is (15 − 1.3)/(1 + e_est). Recompute both and record them.
6. **Re-run** the grid's highest-current points with the new value. Confirm that `inlet_bound_a` ≥ the analyser's I_line at every point.

## Step 8: thermal and endurance (bench mode)

At 120 V and the highest power inside the envelope, run 10 min sessions with heatsink, coil and R5 temperatures logged. R5's local ambient must be ≤ 100 °C (D-18 item 4). Over 50 sessions:
- no `halves_bad` growth while running;
- no nuisance `N21_FAULT_*` latches;
- no RAIL_OK trips from combined Wi-Fi/OLED load steps (controller bench item).

## Step 9: run gate and adapter integration (blocked by H1)

Requires the hardware run gate (H1). After the ECO, implement `run_gate` in `n21_hw_esp32.c`.

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
| CT comparator trip ± (A) | — | 50.9–59.5 | | 3 |
| Shunt OCP trip (A) | — | 49.73–97.98 | | 3 |
| Firmware over-range / OVP (V) | — | 231 / 280 | | 3 |
| Bridge frequency (Hz) | `FREQUENCY_HZ` | unset | | 4 |
| Switch-node delay (ns) | `VSW_DELAY_NS` | 100 | | 4 |
| CT_ZC delay (ns), polarity | `CT_ZC_DELAY_NS`, `CT_ZC_INVERTED` | 0, n | | 4 |
| LINE_ZC centre offset (µs) | `LINE_ZC_OFFSET_US` | 0 | | 5 |
| Estimator error e_est | `EST_ERROR_PPM` | 100000 | | 7 |
| Resulting hold / trip (A) | — | 11.1 / 12.45 | | 7 |
| η_min check | (`input_limits_native21`) | 0.93 | | 7 |

## Open hardware questions

- **H1. No firmware run gate (blocks COMMISSIONED).**
  - **The conflict:** `fullbridge_apply` qualifies the four PWM captures on every tick, idle included, and gates the drivers through a separate request. That is round 5's REQUEST → supervisor → SUP_RUN_OK path.
  - **This controller:** PERMIT comes only from the interlock latch, and the latch is granted by operator reset. So with PERMIT high, live pads mean a running bridge, and the pads cannot be qualified while idle.
  - **Proposed ECO:** native-21's PERMIT = latch Q AND RUN_EN. Firmware can only *remove* permission with it, never grant it. RUN_EN is pulled down, with a read-back through the LVC244.
  - **GPIO:** none is free. The candidates are TCA9555 P06/P07 (slow, adequate for an enable that is not a trip path), or freeing a GPIO.
  - **Rejected:** turning MAX31865 BIAS off to trip the runaway comparator as a stop. That makes a firmware reset request the "run" action, i.e. firmware asserting PERMIT.
- **H2. No power actuator at a fixed frequency.**
  - The adapter computes a conductance from the inlet hold (11.1 A) and min(pan, tank ceiling), but `fullbridge_apply` uses it only as on/off. Phase shift is removed (DECISIONS 2026-10-05) and frequency is fixed (`power_service_frequency` accepts only the configured value).
  - **Result:** neither the 11.1 A hold nor the 22 A ceiling is *regulated*. What is enforced: the adapter's 15 A inlet-bound trip (12.45 A power-stage current at the provisional e_est) and the binding's 23.1 A tank trip.
  - **Needed:** a frequency (or burst) actuator decision, owned by firmware and the power stage.
- **H3. The RTD service uses the legacy pin map.** `temper_pins.h`: SCLK 8, MOSI 11, MISO 12, DRDY 9, mode 1. This controller uses SCK 11, SDI 13, SDO 12, DRDY 14, and GPIO8 is M12_ADC. The MAX31865 bring-up must move to `n21_pins.h` and mode 3 (C20) before the MCP3202 can share the bus.
- **H4. CT_ZC.** Its polarity and the T1 + TLV3201 delay across 31–55 kHz are unspecified, and so is the CT's phase error.
- **H5. Capture independence and channel count.**
  - The PWM feedback is a loop-back capture of the MCU's own pads. Round 5 used an external capture over JFAST, so this is not independent of the MCU. Confirm it is acceptable to the safety review.
  - It uses all six MCPWM capture channels (both groups), with HA captured in each group as the phase reference.
- **H6. C12 / C19 bench items:** repeated ADC1 channels in one continuous pattern; the AD8436 settling with CAVG = 100 nF and its envelope smoothing (steps 1 and 6).
- **H7. CT_MON raw path.** It is sampled asynchronously at 20 kS/s, so its 45 A peak trip is supplementary. The qualified over-current protection is the hardware CT comparators and the shunt OCP.
- **H8. Precharge and contactors.** `energy_supervisor` (precharge, K1/K2/KB) runs on an AUX-powered owner. Native-21 and this controller have no such owner. Confirm the inrush path, so this binding's assumption that the bus is simply present holds.
- **H9. LINE_ZC on J4.16.** The pin took a return contact; recheck it against the D-10/D-20 return allocation (DECISIONS 2026-10-06).
