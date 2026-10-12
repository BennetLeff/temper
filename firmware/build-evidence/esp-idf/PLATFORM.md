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

Host tests: `test/test_platform_logic.c` (new ctest `platform_logic_tests`, 15 tests) and 3 new Unity tests in
`test/test_max31865.c` (RTD word capture, ageing, failed data read, RREF vs threshold words). `ctest`: 29/29.

## Sentinels: what the callers already treat as a fault

| Quantity | Sentinel | Why this value (caller, file:line) |
|---|---|---|
| resistance, current | `+INFINITY` | `state_machine.c:413/417/432` compare with `>`, so `+inf` trips FAULT_IGBT_SHORT / FAULT_PROBE_OPEN; `safety.c:267/304/359` test `!isfinite()`. **NaN would pass every ordered comparison in `state_machine.c`** (asserted in `test_pan_and_rtd_sentinels`), so NaN is never returned for these. |
| temperature | `NaN` | `check_runaway_boundary()` `state_machine.c:473`: `!isfinite(temp)` = immediate breach; the state handlers pass `isfinite(pan)` as "valid" to the pan cap. Same convention as `read_coil_temperature()` / `read_heatsink_temperature()` in `thermal_io.c`. |
| self-test | `false` | `run_self_test()` -> FAULT_SELF_TEST_FAILED, retried by `fault_cleared()` on RESET. |

## Per function

### Safety-relevant reads

**`read_rtd_resistance()`** - implemented.
- Path: PT100 `rtd_pan` (RTDSensing) -> MAX31865 on SPI2 (SCK 11, SDI 13, SDO 12, CS 10, mode 3; DECISIONS C20) ->
  DRDY on TCA9555 P07 (C23) -> `rtd_service_control_tick()` (control task) reads the RTD word `01h/02h` on each DRDY
  completion, before servicing the fault cycle (`rtd_service.c`). R = (word >> 1) x RREF / 32768 with RREF = 430 ohm
  (`modules.ato:1823`, `r_ref.value = 430ohm +/- 0.05%`, 4-wire network). The same RREF derives
  `MAX31865_{LOW,HIGH}_THRESHOLD_WORD` (`config.yaml`, `board_derivations.yaml`); both host suites assert those words decode
  to 10 / 300 ohm within 1 LSB, so the conversion and the hardware thresholds cannot use different references.
- Failure: `+INFINITY` when the service is not ready (bootstrap failed, DRDY timeout, fault reported), no word read yet, the
  last data read failed, the word is older than `RTD_DRDY_TIMEOUT_CONTROL_TICKS` (100 ms, the existing DRDY bound), or the
  word's MAX31865 fault bit (D0) is set. Callers: FAULT_PROBE_OPEN (`state_machine.c:432`), sensor fault (`safety.c:304`).

**`read_pan_temperature()`** - implemented.
- Path: the same RTD word, then IEC 60751 Callendar-Van Dusen (A = 3.9083e-3, B = -5.775e-7, R0 = 100 ohm). Exact for
  T >= 0 C; below 0 C the C term is ignored (< 0.03 K to -50 C, `test_pt100_below_zero_error`).
- Failure: `NaN` whenever `read_rtd_resistance()` would be non-finite, and for a resistance outside the standard's
  -200..850 C range (e.g. a shorted or never-converted register, 0 ohm). Caller: runaway boundary breach (`state_machine.c:473`).

**`read_dc_bus_current()`** - **unsupported-safe: no such measurement exists on this hardware; returns `+INFINITY`.**
- What exists: native-21 has a 1 mOhm DC-return shunt, but it feeds only a TLV3201 comparator (~61 A) whose output is ORed
  into BUS_FAULT (`zapote/power-stage-120v/README.md:79`, `:113`); BUS_FAULT reaches GPIO21 and the interlock latch, which
  drops PERMIT in hardware (controller DECISIONS C5). The MCU's ADC channels are VBUS (bus voltage, C10), CT_MON and the
  AD8436 RMS (tank current through CT T1, C11/C19), which the n21 binding already trips on (tank peak / RMS trips). None is
  the DC bus current, and none is converted into one here: that would fabricate the measurement the 40 A / 50 A
  interlocks (`config.yaml` `OVER_CURRENT_THRESHOLD`, `IGBT_SHORT_CURRENT_THRESHOLD`, legacy IGBT board) expect.
- Failure behaviour: always `+INFINITY` (one `ESP_LOGE` at first call). **Consequence:** `check_safety_interlocks()` runs
  in PREHEAT and HEATING (`state_handlers.c:373`, `:477`) and latches FAULT_IGBT_SHORT on the first pass, so this image
  cannot heat. That is the intended fail-safe; re-pointing that interlock at a signal that exists (BUS_FAULT read-back,
  n21 telemetry) is a control-logic change for the owner (open item P1 below).

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
| read_dc_bus_current | unsupported-safe: no measurement exists, `+INFINITY` |
| peripherals_enter_low_power, peripherals_exit_low_power, led_set_pattern | unsupported-safe: documented no-ops |

## Open items found doing this (not changed: control logic / owner decisions)

- **P1 (blocks heating).** `check_safety_interlocks()` needs a DC bus current that this hardware does not measure. With the
  sentinel the image latches FAULT_IGBT_SHORT on entering PREHEAT. The owner has to re-point the 40 / 50 A interlock (e.g. to
  the BUS_FAULT read-back and the n21 binding's tank-current trips) or retire it for native-21.
- **P2 (RTD conversions).** `rtd_service` arms only automatic fault-detection cycles (`CONFIG = 0x84`, VBIAS + fault
  cycle, conversion mode off, no 1-shot). The MAX31865 updates the RTD data register only on a conversion, so unless bench
  bring-up shows DRDY / data in this mode, there is no pan temperature: `read_pan_temperature()` returns NaN and the
  runaway boundary latches on the first control tick (fail-safe, but the cooker cannot leave the fault). The service now
  reads the RTD data registers on each completion, which per the datasheet also returns DRDY high; before this change
  nothing read them, so DRDY could stay low after the first cycle and only ever give one completion (the existing
  `test_rtd_service_drdy_held_low_is_one_completion` documents that outcome). Adding conversions (1-shot after each fault
  cycle, or auto mode) changes the RTD sequence in `SAFETY_TEST_CHECKLIST.md` and is left to its owner.
- **P3 (UI board).** The MCP23S08 bit map, buzzer polarity, encoder detent ratio and OLED RES# source are provisional until
  the UI board is captured (DECISIONS open item 3); update `ui_board_map.h` from its schematic. The SSD1322 init sequence and
  nibble order follow the Newhaven example and need a bench check.
- **P4.** `test_fan_operation` can only see an active diagnosis; on a cold boot the stall detector may not have run yet.
