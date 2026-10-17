# ESP32 platform layer: the 26 functions that did not link

Date: 2026-10-12. Branch `fw/platform`. Before this change the strict `idf.py build` failed at link with 26 undefined
references (`undefined-symbols.txt`, commit 4168c046a): functions that `main/state_machine.c` and `main/state_handlers.c`
declare `extern` but that existed only as host doubles in `firmware/test/state_machine_stubs.c` (unchanged by this work).
Each now has a production implementation for the integrated SELV controller (`zapote/controller`, branch
`controller-layout` @ 5dca3ef62, "DECISIONS" below = `zapote/controller/DECISIONS.md` there).

## Where the code is

| File | Built | Contents |
|---|---|---|
| `main/platform/platform_esp32.c` | ESP-IDF only (`main/CMakeLists.txt`, `#if defined(ESP_PLATFORM)`) | time, `peripherals_*`, sensors, blower request, NVS fault log, POST self-tests |
| `main/platform/ui_esp32.c`, `ui_board_map.h` | ESP-IDF only | UI board on J7 / SPI3: SSD1322 OLED, MCP23S08 buttons / encoder / buzzer, `led_set_pattern` |
| `components/platform/platform_logic.c` | target and host | every decision: PT100 conversion and sentinels, blower floor, fault-log ring, display text and framebuffer, debounce, quadrature, buzzer timing |
| `components/sensors/max31865.c`, `rtd_service.c` | target and host | added: RTD data-word read (`01h/02h`) on each DRDY completion, `rtd_service_latest_word()`, `max31865_rtd_word_to_ohm()`, `MAX31865_RREF_OHM` |
| `main/thermal_io.c` | ESP-IDF only | one added line: the state machine's full-speed request applied to the fan law's command (`thermal_io.c:186`) |

Host tests: `test/test_platform_logic.c` (ctest `platform_logic_tests`, 17 tests), `test/test_max31865.c` (20 Unity
tests: driver contract, RTD conversion / fault-cycle schedule, staleness, mid-conversion fault), `test/test_state_machine.c`
(75, incl. the native-21 over-current sources), SIL (23 scenarios). `ctest`: 29/29.

Update 2026-10-12 (second commit on `fw/platform`): the two design calls below replaced the DC-bus-current interlock and
turned on MAX31865 conversions; the image can now reach PREHEAT on a healthy system.

## Decisions (by the design lead)

**D1. DC bus current is removed from the legacy safety interlocks.** On native-21 over-current is protected by the
hardware shunt comparator (BUS_FAULT, which drops PERMIT on its own) and by the n21 binding's CT peak and RMS trips.
`check_safety_interlocks()` (`main/state_machine.c`) now reads, instead of `read_dc_bus_current()`:

| Fault | Source (extern, `state_machine.c`) | Signal the controller reads | Where |
|---|---|---|---|
| FAULT_IGBT_SHORT (priority) | `power_bus_fault_tripped()` | BUS_FAULT_RB **GPIO21** high (shunt OCP ~61 A, bus OVP ~280 V, tank-CT comparators, HOT5), or PERMIT_RB **GPIO36** low while the binding has the bridge live (telemetry `pads_live && gate_on`) | `controller_pins.h:45` (BUS_FAULT_RB), `controller_pins.h:47` (PERMIT_RB); read as in `n21_hw_esp32.c:530-531`, pads configured `n21_hw_esp32.c:562`; meaning `power-stage-120v/README.md:79`, `:113` |
| FAULT_OVER_CURRENT | `power_tank_overcurrent_tripped()` | the n21 binding's latched fault via `n21_telemetry()` (`n21_binding.c:522`): `N21_FAULT_TANK_PEAK` (CT_MON peak trip / over-range, `n21_binding.c:227-229`), `N21_FAULT_TANK_RMS` (half-cycle RMS trip `:157`, ceiling `:183`, crest guard `:242`); also `N21_FAULT_CT_MON` / `N21_FAULT_RMS_CHANNEL` (current-sense channel lost: current unknown) | `platform_power_tank_trip()` |

- Implementation: `main/platform/platform_esp32.c` (`power_bus_fault_tripped`, `power_tank_overcurrent_tripped`); the
  decisions are `platform_power_bus_trip()` / `platform_power_tank_trip()` (`components/platform/platform_logic.c`,
  host-tested). Unknown status (no n21 binding, i.e. `CONFIG_TEMPER_POWER_HW_BINDING=n` or `n21_hw_start()` failed) =
  tripped. PERMIT is not required before the bridge runs: it is latched low at power-up until the reset request (C6).
- Not used: the expander bits. LATCHED_FAULT (P10) is the interlock latch itself (set at power-up, not an over-current
  indication); SUP_RUN_OK (P14) is the TPS3823 watchdog, not in the trip path (`controller_pins.h:108`). Both are already
  inputs to the n21 binding's `interlock_healthy()` gate.
- `read_dc_bus_current()` is **no longer called by the state machine** (its `extern`s are removed from `state_machine.c`
  and `state_handlers.c`). The platform function stays, returning `+INFINITY`, documented as unused; the only remaining
  callers are safety.c `check_hardware_interlocks()` / `run_safety_check()`, reachable on target only from safety.c's
  example `task_control_loop()`, which no task runs. In the strict image it is removed by `--gc-sections`
  (`platform-symbols-nm.txt`: `UNREFERENCED`, defined in `platform_esp32.c.obj`).
- Fault list and transition table unchanged (FAULT_IGBT_SHORT / FAULT_OVER_CURRENT and their events already exist; the
  committed generators reproduce the headers byte for byte). Tests that injected a DC bus current now inject the new
  sources: `test_state_machine.c`, `test_integration.c`, the transition-table test (generator
  `test/gen_transition_table.py` updated, `test_transition_table_generated.c` regenerated), and the SIL traces: column
  `dc_current` became `power_trip` (0 healthy, 1 = n21 tank trip, 2 = BUS_FAULT / PERMIT drop; mechanically converted,
  > 40 A -> 1, > 50 A -> 2) with the manifest sensor renamed to `power_trip`. New tests: a healthy system enters and stays
  in PREHEAT (even with an absurd legacy DC current injected), BUS_FAULT -> FAULT_IGBT_SHORT and tank trip ->
  FAULT_OVER_CURRENT in both PREHEAT and HEATING, both at once -> FAULT_IGBT_SHORT, and the truth tables of the two
  decisions (`test_power_bus_trip`, `test_power_tank_trip`). Python checks (SIL coverage, codegen, tools: 175; mutation
  sweep: 13) pass.

**D2. MAX31865 in normal conversion mode, with the fault cycle at startup and periodically.**
- Wiring **4-wire** (CONFIG D4 = 0): RTDSensing uses the datasheet 4-wire topology with FORCE+/RTDIN+ and FORCE-/RTDIN-
  on separate conductors (`zapote/controller/elec/src/modules.ato:2122-2128`, branch controller-layout; DECISIONS C27
  cartridge table). Filter **60 Hz** (D0 = 0): the product is 120-127 V~ 60 Hz
  (`zapote/power-stage-120v/DECISIONS.md:299`). Converting CONFIG = `0xC0` (bias, auto conversion); fault cycle CONFIG =
  `0x84` (`100X010Xb`, conversions off) - `max31865.h`.
- Sequence (`components/sensors/rtd_service.c`, control task, 10 ms tick): bootstrap writes the thresholds and starts
  the **startup fault-detection cycle**; each tick CONFIG is read until D3:D2 return to 00 (the datasheet's completion
  indication), then the latched status is reported and conversions start. While converting, DRDY (expander P07, the
  existing poll path: the per-tick snapshot) low = a conversion: the data word is read (which releases DRDY) and DRDY
  is re-polled (`ctrl_board_poll_expander()`, control task) to confirm the release before the next low is accepted; a
  DRDY stuck low gives one conversion and then the fail-silent timeout. Every **1 s** (`RTD_FAULT_CYCLE_PERIOD_TICKS` =
  100), right after a conversion has been read, conversions pause and a fault cycle runs; they resume when it finishes.
- Why 1 s: open and short of the element are caught on every conversion (16.7 ms at 60 Hz) by the threshold faults,
  which set the data word's fault bit; the periodic cycle adds the lead / force-path diagnoses. Each pause costs about
  one tick plus the first conversion after the restart (~52 ms, single-conversion time), i.e. < 7 % of conversions at
  1 s, and the word never ages past the 100 ms bound across a pause (`test_rtd_service_periodic_fault_cycle_schedule`:
  age <= 3 ticks throughout). A shorter period would only trade more conversion gaps for faster lead-fault detection.
- Faults: a fault-cycle status, a conversion word with the fault bit (status read and reported at once; a clean status
  despite the bit = open, fail closed), a fault cycle that does not finish within 100 ms, no conversion for 100 ms, or
  an SPI failure all report to the state machine (FAULT_PROBE_SHORT for the low threshold, else FAULT_PROBE_OPEN) and end
  the service (terminal: RUN_EN is killed until MCU reset anyway). `read_rtd_resistance()` / `read_pan_temperature()`
  return `+INFINITY` / NaN exactly as before for a faulted, stale (> 10 ticks), failed or missing word.
- Tests (`test_max31865.c`): config words 4-wire / 60 Hz; startup fault cycle then conversions; startup fault reported;
  fault cycle never finishing; conversion read releases DRDY (a stale snapshot is not a conversion); periodic schedule
  over 300 ticks (cycles at t = 100 and 202, conversions off during the cycle, DRDY lows not consumed); word ages out
  when conversions stop; fault in the middle of a conversion (short reported once, service ends); fault bit with clean
  status; DRDY stuck low; failed data read.

## Sentinels: what the callers already treat as a fault

| Quantity | Sentinel | Why this value (caller, file:line) |
|---|---|---|
| resistance (and the unused DC current) | `+INFINITY` | `state_machine.c:439` compares with `>`, so `+inf` trips FAULT_PROBE_OPEN; `safety.c` tests `!isfinite()`. **NaN would pass every ordered comparison in `state_machine.c`** (asserted in `test_pan_and_rtd_sentinels`), so NaN is never returned for these. |
| temperature | `NaN` | `check_runaway_boundary()` `state_machine.c:480`: `!isfinite(temp)` = immediate breach; the state handlers pass `isfinite(pan)` as "valid" to the pan cap. Same convention as `read_coil_temperature()` / `read_heatsink_temperature()` in `thermal_io.c`. |
| self-test | `false` | `run_self_test()` -> FAULT_SELF_TEST_FAILED, retried by `fault_cleared()` on RESET. |

## Per function

### Safety-relevant reads

**`read_rtd_resistance()`** - implemented.
- Path: PT100 `rtd_pan` (RTDSensing) -> MAX31865 on SPI2 (SCK 11, SDI 13, SDO 12, CS 10, mode 3; DECISIONS C20),
  continuous conversions 4-wire / 60 Hz with a fault cycle at startup and every 1 s (D2 above); DRDY on TCA9555 P07
  (C23). R = (word >> 1) x RREF / 32768 with RREF = 430 ohm (`modules.ato:1823`, `r_ref.value = 430ohm +/- 0.05%`). The
  same RREF derives `MAX31865_{LOW,HIGH}_THRESHOLD_WORD` (`config.yaml`, `board_derivations.yaml`); both host suites assert
  those words decode to 10 / 300 ohm within 1 LSB.
- Failure: `+INFINITY` when the service is not ready (bootstrap failed, a fault reported, a timeout), no word read yet,
  the last data read failed, the word is older than `RTD_DRDY_TIMEOUT_CONTROL_TICKS` (100 ms), or the word's fault bit
  (D0) is set. Callers: FAULT_PROBE_OPEN (`state_machine.c`, `> RTD_GROSS_OPEN_DIAGNOSTIC_OHM`), sensor fault (`safety.c`).

**`read_pan_temperature()`** - implemented.
- Path: the same RTD word, then IEC 60751 Callendar-Van Dusen (A = 3.9083e-3, B = -5.775e-7, R0 = 100 ohm). Exact for
  T >= 0 C; below 0 C the C term is ignored (< 0.03 K to -50 C, `test_pt100_below_zero_error`).
- Failure: `NaN` whenever `read_rtd_resistance()` would be non-finite, and for a resistance outside the standard's
  -200..850 C range. Caller: runaway boundary breach (`check_runaway_boundary()`).

**`read_dc_bus_current()`** - **unsupported-safe and unused** (D1): no DC-bus current measurement exists (native-21's
1 mOhm shunt feeds only a comparator into BUS_FAULT, `power-stage-120v/README.md:79`, `:113`, DECISIONS C5; the ADC
channels are bus voltage and tank current). Returns `+INFINITY`; the state machine no longer calls it.

### Time, storage, peripherals

**`get_time_ms()`** - implemented. `esp_timer_get_time() / 1000` (64-bit us since boot, truncated to 32 bits; wraps after
49.7 days, the state machine uses unsigned differences only). Cannot fail.

**`eeprom_log_fault(code, timestamp)`** - implemented on NVS. There is no EEPROM on this controller; the store is the `nvs`
partition (`partitions.csv:3`, initialised by `init_nvs()` in `main.c` before any task). Namespace `temper`, key
`faultlog`: one blob, a 16-entry ring (`platform_fault_log_t`: seq, ms since boot, fault code, boot index; boot index
incremented once per boot by `peripherals_init()`). A corrupt blob (bad magic, size or sequence) is replaced by a fresh log.
Failure: a store error is logged (`ESP_LOGE`) and otherwise ignored; it is called after the power cut on FAULT /
RUNAWAY_FAULT entry (`state_handlers.c:680`, `:737`) and the fault handling never depends on it.

**`peripherals_init()`** - implemented. Called from `state_init_entry()`. The board itself (pins, RUN_EN, I2C expander,
UI SPI3 bus, blower LEDC/PCNT, RTD bootstrap, n21 binding) is already brought up by `init_peripherals()` in `main.c`; this
adds: fault-log load and boot record, the UI board (`platform_ui_init()`), the DECISIONS C6 wait (>= 10 ms after MAX31865
BIAS on before the RTD comparator read-back is trusted), and a bounded wait (<= 100 ms) for the first calibrated ADC1
frame. Idempotent. Failure: each failing part is logged and then fails its own POST test.

**`peripherals_enter_low_power()` / `peripherals_exit_low_power()`** - **unsupported-safe (documented no-ops).**
`sdkconfig.defaults:81` `CONFIG_PM_ENABLE=n` ("need deterministic timing"); in IDLE the control task must keep the TPS3823
heartbeat (IL_WDI) and the expander / RTD polls running, and the blower belongs to the fan law. Nothing is switched off.

### Blower

**`fan_set_speed(speed)`**, **`fan_set_auto_mode(enabled)`** - implemented through the C28 blower path, never around it.
- The fan law (`blower_ctrl_decide()`, `thermal_mgmt.c`) owns the J10 blower (FAN_PWM GPIO46, tach GPIO3, FAN_OFF expander
  P15; DECISIONS C28). A request can only add a **full-speed floor**: `FAN_SPEED_MAX` sets it; `FAN_SPEED_OFF/MIN/MEDIUM`
  and `fan_set_auto_mode(true)` clear it (the fan law alone decides); `fan_set_auto_mode(false)` keeps the last request.
- `thermal_io.c:186` applies the floor to the fan law's command (`on = true`, `duty = 0` = full speed, C28) before the PS3
  inlet schedule (`blower_aux_step`, C33), so a speed-up still waits for its inlet allowance, and before the LEDC / FAN_OFF
  write and the stall detector. It never lowers the fan law's speed and never switches the blower off
  (`test_blower_floor_never_lowers_speed`). No new speed values were invented for MIN / MEDIUM.
- Failure: none of its own; every LEDC / FAN_OFF failure keeps the existing C28 full-speed defaults.

### UI board (J7, SPI3, DECISIONS C26)

Controller side fixed by C26: SCK 40, MOSI 41, MISO 44 (pulled up), CS_OLED# 47, CS_EXP# 48, D/C 45. The UI board is not
designed yet (DECISIONS open item 3), so **the MCP23S08 bit map in `main/platform/ui_board_map.h` is PROVISIONAL**: it
follows the C26 allocation order "3 buttons, encoder A/B/switch, buzzer, local CS/reset" (GP0 START, GP1 STOP, GP2 RESET,
GP3/GP4 encoder A/B, GP5 encoder switch, GP6 buzzer output, GP7 left an input with pull-up) and the C16 convention
(switch to GND, pull-up, active low). That table is the only place the map is encoded. All SPI traffic runs in one UI I/O
task (1 ms poll as C26 asks, core 0, low priority); the control task only touches shared fields under a spinlock. Bus at
8 MHz, mode 0 (both parts' maximum is 10 MHz; margin for the 120 mm jumper). Frames go out in 512-byte chunks, one per poll.

**`display_show_message`**, **`display_update_temperature`**, **`display_update_countdown`**, **`display_show_fault`** -
implemented. SSD1322 (NHD-3.12-25664UCW2, 256 x 64, 4-bit grey; C3) on CS_OLED#, D/C 45 (command byte D/C low, parameters
D/C high). Two-line screen: line 1 the state message (or "FAULT"), line 2 the temperature ("123 C", "--- C" for NaN), the
countdown ("m:ss") or the fault name (`state_machine_get_fault_string()`). Rendered by `platform_oled_render()` (5 x 7 font,
host-tested) into an 8 KB framebuffer. RES# is not driven (C26: RC power-on reset on the UI board, or the spare expander bit,
which stays an input with its pull-up). Failure: none visible to the state machine; a failed chunk re-sends the frame.

**`button_is_pressed`**, **`button_set_enabled`** - implemented (provisional map). START / STOP / RESET: debounced level
(10 identical 1 ms polls). TEMP_UP / TEMP_DOWN: one encoder detent (one full quadrature cycle) = one press, consumed by the
read. `button_set_enabled` gates any button (the state machine uses START only, as the host double does). Failure: with
no UI board, or one that stops answering the configuration read-back (checked once a second), every button reads
released. Nothing here can start heating on its own.

**`buzzer_beep`**, **`buzzer_beep_continuous`**, **`buzzer_stop`** - implemented: the self-oscillating buzzer on an
expander output (C26 owner decision; on/off only), timed in the UI task. A beep never shortens a continuous alarm. The
output latch is written 0 before the pin becomes an output. Failure: no UI board, no sound (logged).

**`led_set_pattern`** - **unsupported-safe (documented no-op).** No indicator LED exists: C26 deleted J5/J6/J8 and the
UI-board expander bits are allocated to buttons, encoder, buzzer and a local CS/reset. The pattern is stored for
diagnostics; the OLED carries the state text.

### POST self-tests (`run_self_test()`, STATE_INIT)

| Function | Pass condition on this hardware | Source |
|---|---|---|
| `test_adc_calibration` | a calibrated ADC1 frame <= 20 ms old (n21 continuous pattern; means exist only for samples `adc_cali_raw_to_voltage()` converted) with every thermal channel finite in 0..3300 mV. Without `CONFIG_TEMPER_POWER_HW_BINDING` there is no ADC owner: fails. | C12, `n21_hw_esp32.c:380-404` |
| `test_fan_operation` | `is_fan_running()` and blower diagnosis `BLOWER_DIAG_OK` (no stall / PS3 absent / blower failed). The tach counter belongs to the monitor task and is not read here; the stall detector supervises continuously. | C28, C33 |
| `test_hardware_comparators` | fresh TCA9555 snapshot with HS_FAULT (P12), COIL_FAULT (P13) and RTD_HW_FAULT (P11) all clear. The MCU cannot drive protective nets (C4), so this is a read-back, not an injection test. The interlock latch (P10) is latched at power-up and is not checked. | C4, C6, C23 |
| `test_rtd_sensor` | MAX31865 service ready; if a conversion has completed, its resistance is strictly inside (RTD_SHORT_FAULT_OHM, RTD_OPEN_FAULT_OHM). | C6, C20 |
| `test_display_communication` | the MCP23S08 answered its configuration read-back. The SSD1322 serial interface is write-only, so the shared UI connector and bus are proven through the expander. | C3, C26 |
| `test_eeprom_read` | the NVS fault log opened and read (an empty or format-reset log passes; an NVS error fails). | `partitions.csv` |

## Summary

| Function | Status |
|---|---|
| get_time_ms, read_rtd_resistance, read_pan_temperature, eeprom_log_fault, peripherals_init, fan_set_speed, fan_set_auto_mode | implemented |
| display_show_message, display_update_temperature, display_update_countdown, display_show_fault | implemented (SSD1322) |
| button_is_pressed, button_set_enabled, buzzer_beep, buzzer_beep_continuous, buzzer_stop | implemented, UI-board bit map provisional |
| test_adc_calibration, test_fan_operation, test_hardware_comparators, test_rtd_sensor, test_display_communication, test_eeprom_read | implemented (read-back / presence tests, see table) |
| read_dc_bus_current | unsupported-safe and unused (D1): no measurement exists, `+INFINITY`, no caller in the state machine |
| peripherals_enter_low_power, peripherals_exit_low_power, led_set_pattern | unsupported-safe: documented no-ops |

## Open items found doing this (not changed: control logic / owner decisions)

- **P1, P2: resolved** by the design lead's decisions D1 and D2 above.
- **P2a (bench).** Confirm on hardware: the automatic fault cycle's completion (CONFIG D3:D2 -> 00) within a tick, the
  first-conversion time after each restart (assumed ~52 ms, inside the 100 ms bound), and that the datasheet's automatic
  fault-cycle timing suits this front end's input RC (1 nF C0G with the 1 MOhm open-lead bias, `modules.ato:1842-1856`);
  if it does not, the datasheet's manual cycle is the fallback.
- **P3 (UI board).** The MCP23S08 bit map, buzzer polarity, encoder detent ratio and OLED RES# source are provisional until
  the UI board is captured (DECISIONS open item 3); update `ui_board_map.h` from its schematic. The SSD1322 init sequence and
  nibble order follow the Newhaven example and need a bench check.
- **P4.** `test_fan_operation` can only see an active diagnosis; on a cold boot the stall detector may not have run yet.
