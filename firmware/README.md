# Temper Induction Cooktop Firmware

ESP32-S3 based firmware for the Temper induction cooktop, implementing a state machine-driven control system with comprehensive safety features.

## Architecture

### State Machine

The firmware is organized around a central state machine (`main/state_machine.c`) with the following states:

| State | Description |
|-------|-------------|
| `INIT` | Power-on self-test (POST) |
| `IDLE` | Standby mode, awaiting user input |
| `PAN_DET` | Pan detection phase (5s timeout) |
| `PREHEAT` | Aggressive heating to approach target |
| `HEATING` | Precision PID temperature control |
| `NO_PAN` | Pan removed pause (3s window to replace) |
| `COOLDOWN` | Active cooling after stop |
| `FAULT` | Safety lockout (requires reset) |

### Components

```
firmware/
├── main/
│   ├── state_machine.c    # Core state machine logic
│   ├── state_machine.h    # Public API and type definitions
│   └── main.c             # Application entry point
├── components/
│   ├── control/           # PID controller, PLL tracking
│   ├── temper_hal/        # Hardware abstraction layer (not `hal`: that name
│   │                      #   would replace ESP-IDF's own hal component)
│   └── safety/            # Safety monitoring and fault handling
└── test/                  # Host-based unit and integration tests
```

## Hardware pin map (zapote/controller)

`components/temper_hal/include/temper_pins.h` is the one place firmware names
a pin, and every value there comes from the controller netlist:
`firmware/tools/check_board_pin_map.py` derives the board's map from
`zapote/controller/frozen/default.net` and `controller_parts.ato` (branch
`controller-c1-crs` at 467917c38) into `tools/zapote_controller_pins.json`,
and CI fails when a define disagrees, when a wired GPIO or TCA9555 pin has no
define, when a source hard-codes `GPIO_NUM_n`, or when anything but the owners
below touches WDI or RUN_EN. Rerun `--derive` (and review the pin diff) when
the board moves; `--verify-board-ref controller-c1-crs` checks a newer head.

| GPIO | Net | Use |
|---|---|---|
| 4 / 5 / 15 / 16 | PWM_HA / LA / HB / LB | native-21 full-bridge gate commands, held low as outputs at boot |
| 14 | RUN_EN | gate enable (PERMIT = latch OK AND RUN_EN, C23); `power_gate.c` only |
| 18 | IL_WDI | TPS3823 heartbeat (C42); WDI supervisor task only |
| 17 | IL_RESET_N | interlock latch reset request |
| 21 / 35 / 36 | BUS_FAULT_RB / RAIL_OK_RB / PERMIT_RB | interlock read-backs |
| 38 / 39 | CT_ZC_MCU / LINE_ZC_MCU | tank-current and line zero cross (PLL and pan-detect capture on 38) |
| 1 / 2 / 6 / 7 / 8 / 9 | CT_MON / VBUS / HS / COIL / M12 / RIM ADC | ADC1_CH0 / 1 / 5 / 6 / 7 / 8 |
| 10 / 11 / 12 / 13 / 42 | RTD_CS_N / SCK / SDO (MISO) / SDI (MOSI) / EXT_ADC_CS_N | SPI2: MAX31865 and MCP3202 |
| 37 / 0 | I2C_SDA / I2C_SCL_BOOT | TCA9555 at 0x20 (GPIO0 is also the boot strap) |
| 46 / 3 | FAN_PWM / FAN_TACH | blower speed (strap) and tach |
| 40 / 41 / 44 / 45 / 47 / 48 | UI bus | OLED + MCP23S08 (J7) |
| 43 / 19 / 20 | UART0_TX / USB D- / D+ | console, TC2050 land |

TCA9555: P00/P01 capacitive-mode read-backs, **P07 RTD_DRDY**, P10-P13 fault
read-backs, P14 SUP_RUN_OK_RB (TPS3823 RESET_N), P15 FAN_OFF, P16 BLW_PG.
`rtd_service` polls P07 over I2C each control tick (`components/sensors/tca9555.c`,
D-DRDY), so on the target `PIN_RTD_DRDY` stays `HAL_PIN_INVALID` (the legacy
map put DRDY on GPIO9, the rim NTC).

The legacy `pcb/temper.kicad_pcb` contracts this section used to list (IO47
DISCHARGE_CTRL, IO9 DRDY, IO7 WDT_KICK) do not apply to zapote: GPIO47 is the
OLED chip select, GPIO9 the rim NTC and GPIO7 the coil ADC.

## Building

### Prerequisites

- ESP-IDF v5.3.6 (target builds; CI uses the `espressif/idf:v5.3.6` image)
- CMake 3.16+
- GCC (for host-based tests)

### Target Build (ESP32-S3)

```bash
. ~/esp/esp-idf-v5.3.6/export.sh          # activates the IDF Python env
cd firmware
python -m pip install -r tools/requirements.txt   # once per IDF env: jinja2 + pyyaml
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

- The configure step regenerates `config.h` and `main/transition_table.h`
  from their YAML with the IDF env's `python3`. The IDF env does not ship
  jinja2, so the `pip install` line is required; without it the configure
  stops with an error rather than building from a possibly stale header.
- `main/CMakeLists.txt` builds the C1 pan-temperature loop
  (`TEMPER_PAN_CONTROL_C1=1`).
- `partitions.csv` is a single 1984 KB factory slot in the 4 MB flash that
  `sdkconfig.defaults` selects. The first linked image (2026-10-15) was
  `induction_cooker.bin` at 0x4F500 bytes (317 KB, 84 % of the slot free).
- CI builds the target as the last step of the Firmware Tests job
  (`.github/workflows/firmware-tests.yml`).

**The target image is not yet bench-ready.** `main/board_peripherals.c`
holds `TODO(hardware)` implementations for every peripheral without a driver
(display, buttons, buzzer, LEDs, fan, bus current, power stage, the
self-tests, the fault log). The rim NTC and the heatsink NTC have real
drivers (`components/sensors/rim_ntc.c`, `hs_ntc.c` on GPIO6 / ADC1_CH5;
the heatsink reads +INFINITY on a driver fault). `main/board_power.c` holds
the four gate commands low, owns RUN_EN through `power_gate.c`, and starts the
MCPWM capture on PWM_HA and CT_ZC for the PLL and pan detection; the native-21
gate generator is `TODO(hardware)`, so the PLL has no timer and pan detection
reports no pan. The rest fail safe: temperatures and currents read
+INFINITY, the fan reads stopped, buttons read released, the self-tests fail,
and the power outputs refuse any non-zero command. A unit flashed with this
image stops in FAULT (`FAULT_SELF_TEST_FAILED`) with the coil off.

### Host Build (Tests Only)

```bash
cd firmware/test
mkdir -p build && cd build
cmake ..
make
```

## Testing

The firmware includes comprehensive test coverage with:
- **37 unit tests** for state machine transitions
- **30 integration tests** for complete operational sequences

### Running Tests

```bash
cd firmware/test

# Build all test targets
mkdir -p build && cd build
cmake ..
make

# Run state machine unit tests
./test_state_machine_only

# Run integration tests
./test_integration_only

# Run all tests via CTest
ctest --output-on-failure
```

### Test Categories

#### Unit Tests (`test_state_machine.c`)
- State initialization and defaults
- Individual state transitions
- Self-test pass/fail scenarios
- Fault detection (OCP, OVP, thermal, probe)
- Fault recovery conditions
- API boundary testing

#### Integration Tests (`test_integration.c`)
- **Startup Sequence**: INIT → IDLE → PAN_DET → PREHEAT → HEATING
- **Normal Operation**: Temperature regulation, timer countdown, manual stop
- **Fault Injection**: Over-current, over-temp, fan failure, probe faults
- **Power Cycle**: Recovery from idle, heating, fault states
- **Stress Tests**: Rapid state changes, long duration, sensor noise

### Test Infrastructure

Tests use the [Unity](http://www.throwtheswitch.org/unity) test framework with mock HAL implementations:

- `state_machine_stubs.c` - Mock implementations for all HAL functions
- `mock_sm_*()` functions - Control mock behavior (temperatures, currents, buttons)
- Time simulation via `mock_sm_advance_time()`

Example test setup:
```c
void test_fault_over_current(void) {
    setup_test();  // Resets mocks and state machine
    
    /* Reach HEATING state */
    state_machine_update();  /* INIT -> IDLE */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    // ... setup to reach HEATING ...
    
    /* Inject fault condition */
    mock_sm_set_dc_bus_current(45.0f);  // > 40A threshold
    state_machine_update();
    
    /* Verify fault handling */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_CURRENT, state_machine_get_fault());
}
```

## Safety Features

The firmware implements multiple layers of safety:

1. **Hardware Watchdog (TPS3823-33, zapote C42)**: WDI (GPIO18) is toggled
   only by the WDI supervisor task (`main.c`, `components/safety/wdi_supervisor.c`),
   one edge per 100 ms (C42: <= 400 ms against the TPS3823's 0.9 s minimum),
   and only while the control loop's sequence counter advances (>= 5 of the
   expected 10 iterations per period) and the newest MAX31865 conversion is
   <= 300 ms old. Any failure stops the heartbeat for good; the TPS3823 trips
   the interlock latch within 0.9-2.5 s and PERMIT drops. Never from an ISR,
   timer, LEDC, RMT or the state machine.
2. **Software Watchdog**: the control task is subscribed to the ESP-IDF task
   watchdog; the state handlers' `watchdog_feed()` resets it with
   state-specific timeouts (1-10 s). A stall panics and reboots into safe mode.
3. **RUN_EN interlock (zapote C23 / C39)**: RUN_EN (GPIO14) is raised only
   through `components/safety/power_gate.c`, which refuses unless every gate
   PWM channel is idle (stopped with its outputs held low), so the
   capacitive-mode detector re-arms with no edge in flight. Every fault path
   (`pwm_disable_all()`) forces the gate PWM low and drops RUN_EN, which takes
   PERMIT low; the MCU cannot drive the interlock's trip itself (C4).
4. **Burst start at or above resonance (zapote C39)**: every start of
   switching in this tree (`pll_enable()`, `pll_reset()`, the pan-detection
   pulse) takes its first frequency from `pll_burst_start_frequency()`:
   max(47 kHz, 1.02 x last known resonance), refused (no pulse) when that is
   above the PLL range.
5. **Over-Current Protection**: DC bus current >40A triggers immediate shutdown
6. **Over-Temperature Protection**: Heatsink >95°C triggers fault (`OVER_TEMP_THRESHOLD`; the hardware comparator backs it at 98.3–104.6°C, zapote C32)
7. **Fan Failure Detection**: Tachometer monitoring during operation
8. **RTD Probe Monitoring**: Open circuit (>10kΩ) and short circuit (<10Ω) detection
9. **Thermal Runaway Detection**: Pan temp exceeding target by >10°C
10. **Pan Detection**: CT_ZC ring-down after a pulse, with a confidence
    threshold. On zapote the pulse needs the native-21 gate drive, which is
    not in this tree, so `detect_pan_presence()` reports no pan (no power)
    until the power stage installs its pulse ops.

## C1 sensor bus (zapote/controller)

The C1 build (`TEMPER_PAN_CONTROL_C1=1`) reads the pan through one SPI bus,
one I2C expander pin and three ADC1 channels. The design record is
`output/temper-sensor-r3/firmware/DECISIONS.md`; `output/temper-sensor-r3/firmware/run.sh`
reruns every derivation and gate.

- **MAX31865 (Pt100, CR-1)**, `components/sensors/rtd_service.c`: thresholds
  35544 / 12844, continuous conversion, and the *manual*
  fault-detection cycle at power-up and before every probe-fault reset
  (D-FCYC). The automatic cycle's fixed 100 µs wait is shorter than the CR-1
  input filter (τ_max 1.01 ms) and flags a healthy element; the manual
  cycle waits 5.5 ms per step and restarts conversion 11.5 ms later
  (`fault_cycle.py`, `fault-cycle.json`).
- **DRDY** is TCA9555 P07, not a GPIO: `rtd_service` polls Input Port 0 over
  I2C each control tick (`components/sensors/tca9555.c`, D-DRDY). A failed
  I2C read counts as "no DRDY", so a dead expander becomes a stale RTD in
  5-6 ticks (D-STALE); an expander absent at boot fails the bootstrap closed.
- **MCP3202 (v3v3 rail)**, `components/sensors/rail_adc.c`: CH1 reads v3v3/2
  against the LM4040A25 on CH0, on the RTD's bus and tick (one bus owner, no
  lock). The rim and heatsink NTC drivers divide by the measured rail inside
  3195-3415 mV and by 3.300 V otherwise; the cold-soak check uses 16.9 K
  with a measured rail and 19.4 K without (D-RAIL, `rail_adc.py`).
- **Coil-off token (NVS)**, `components/control/pan_soak_store.c` with
  `main/soak_store_nvs.c` (namespace `temper_soak`, key `off_s`): one write
  when a coil-off period reaches 15 min, an erase before the coil is
  energised, and at boot a credit of 15 min (a lower bound: the unpowered
  time counts as zero) so the cold-soak check can run after a power cycle
  (D-SOAKNV).

## Configuration

Tunable parameters are declared in `firmware/config.yaml` and rendered into
`firmware/config.h` by `firmware/tools/gen_config.py`. See the manifest for
current values.

## API Reference

### Core Functions

```c
void state_machine_init(void);           // Initialize/reset state machine
void state_machine_update(void);         // Call from main loop (10-100Hz)
system_state_t state_machine_get_state(void);  // Get current state
fault_code_t state_machine_get_fault(void);    // Get active fault code
```

### User Control

```c
void state_machine_set_target_temp(float temp_celsius);  // Set target (50-250°C)
void state_machine_set_timer(bool enabled, uint32_t time_ms);  // Cooking timer
```

### Debug/Test

```c
const char* state_machine_get_state_string(system_state_t state);
const char* state_machine_get_fault_string(fault_code_t code);
void state_machine_force_state(system_state_t new_state);  // Testing only
```

## Contributing

1. All state machine changes require corresponding test updates
2. Run full test suite before committing: `ctest --output-on-failure`
3. Follow existing code style (K&R braces, 4-space indent)
4. Update this README for any API changes

## 2026-10-16 — F2 firmware hygiene

Base: `cloud/sensor-c1-leak` at `ebf8a777b50ecb81040fc0c56fa8bde706720638`.
Checked with Python 3.12.14, CMake 3.31.10 and Debian GCC 14.2.0.

- Keep the current cooking-profile tests. `profiles.c` still implements
  their API; `state_machine.c` starts profiles and `state_handlers.c`
  advances stages and applies their settings. The build failure was the
  local Unity `TEST_ASSERT_EQUAL` macro passing pointers to its integer
  assertion (`UnityAssertEqualInt`), not a removed API. Compare the pointers
  directly with `TEST_ASSERT_TRUE`, and register `profiles_tests` with CTest.
- Link `test_power_gate_only` with `m`, as the other mock-HAL targets do.
  On this Linux host the shared converter mocks require `exp` and `floor`;
  this target previously failed to link and CTest could not run it.
- Keep `hal_timer_ops_t.configure_capture` and the host mock's injected
  capture support. A firmware-wide search finds only `pwm_guard_init` calling
  the op. Its only caller is `test_pwm_guard.c`, where `hal_timer` is NULL;
  `pwm_guard.c` is not in the ESP-IDF source list. The target instead creates
  MCPWM channels in `main/board_power.c` and attaches the PLL and pan detector
  directly (D-BRINGUP). Remove the unused ESP32 capture-context type/array
  and document the existing unsupported result, with no hardware allocation
  or callback registration. Remove the misleading GPIO fallback/TODO text.
- Remove `state_handlers.c`'s unused `TAG` and explicitly discard the
  completion return from `thermal_mass_update`, retaining the call and its
  state updates. A true return also covers sensor failure; it is not a
  classification-valid signal. The handler already checks the persistent
  `thermal_mass_is_classified` state when pan confidence is sufficient.
  This preserves the existing control behavior. Host build warnings from
  this file fell from 9 to 0; ESP-IDF-only declarations were not compiled
  here. The estimator audit suite reported `36 Tests 0 Failures 0 Ignored`.

Before/after verification (no thresholds, gates or existing expected counts
changed):

| Check | Before | After |
|---|---|---|
| Profile target | `error: passing argument 1 of ‘UnityAssertEqualInt’ makes integer from pointer without a cast [-Wint-conversion]` | `5 Tests 0 Failures 0 Ignored` |
| Profile CTest selection (`--no-tests=error`) | `No tests were found!!!` (exit 8) | `100% tests passed, 0 tests failed out of 1` (exit 0) |
| Power-gate target | unresolved `exp` and `floor` | `10 Tests 0 Failures 0 Ignored` |
| Complete host build / CTest | `gmake: Target 'default_target' not remade because of errors.` (exit 2); `96% tests passed, 1 tests failed out of 26` (`power_gate_tests` not run) | `[100%] Built target test_c1_rtd_service_only` (exit 0); `100% tests passed, 0 tests failed out of 27` |
| SIL coverage | `SUMMARY legacy: 31 scenarios, 20/20 designed pairs covered`; `SUMMARY c1: 52 scenarios, 28/28 designed pairs covered`; `SUMMARY c1 mechanisms: 27/27 cells covered`; `PASS` | Same (exit 0) |
| Trace freshness | `SIL traces up to date (27 generated traces)` | Same (exit 0) |
| Invariants | `OK: all 5 invariants verified and proof_record.json is fresh` | Same (exit 0) |
| State-machine model | `OK: state machine model check passed (reachability, P1-P4, manifest cross-check)` | Same (exit 0) |
| Fault list | `fault list consistency check passed`; `manifest codes: 14`; `generated codes: 16`; `supplemental codes: 3` | Same (exit 0) |
| Board pin map | `PASSED: temper_pins.h agrees with zapote/controller controller-c1-crs at 467917c38 (36 GPIOs, 10 expander pins)` | Same (exit 0) |
| Full C1 `run.sh` | `T1 FAIL: derivation gates failed: source_inputs_clean` (exit 1) | Same (exit 1); 23 selected result lines identical |

The model gate retains its one existing manifest-divergence backlog entry.
ESP-IDF compilation was not run: `idf.py is not on PATH`, `IDF_PATH is unset`,
and `No ~/esp/esp-idf-*/export.sh found`. Target warning verification remains
for the Mac build. `scripts/check_firmware_board_contract.py` was skipped as
requested because it needs the unpushed board branch.

The prepared environment needed SciPy for `run.sh` (the first invocation
stopped with `ModuleNotFoundError: No module named 'scipy'`). Installing
SciPy 1.18.1 and the T2 metadata dependency matplotlib 3.11.2 required no
repository dependency or lockfile changes.

Additional repository check: `Import boundary gate PASSED — 0 new violations`
after installing the missing import-linter tool. `make regen-check` reports
the pre-existing unrelated error: `[gen_repo_state] ERROR: tracked top-level
directories have no description in DIRECTORY_PURPOSE: output. Add one so
the map stays complete.` The post-edit output was identical
(`REGEN_CHECK_OUTPUT_IDENTICAL=True`).
No unrelated derived artifacts were re-baselined.

Both C1 runs retained the expected report-only `== screen_d1: FAIL` and
`== stretch_3_6_3: FAIL`, with `== firmware: PASS`. The unmodified full C1
run reached `ALL RUNAWAY CHECKS PASS` and
`SENSOR FAIL CODES PASS`, then stopped at T1 because its earlier Linux
regeneration changed the tracked `leak-checks.json` input. After restoring
all six generated JSON files, the unchanged T1 command reported `T1 PASS`.
The subsequent T2 and sensitivity stages were run directly to measure the
parts that `run.sh` did not reach. Baseline sensitivity exited 0. The clean
T2 run reported `250 C controls match committed C and offline headlines`
and `cap 200: nominal 99/179; worst 14/90`, then `T2 FAIL: regenerated
evidence differs`. Its candidate had all eight internal gates true and an
empty dirty-input list. After applying T2's own comparison normalization,
the summary had 0 differing leaves, while the detailed rows had 173,
including `r_leak` 720.8434242404265 versus 720.8434242404264 and one
rim-limit time 527.8 versus 527.9 s. No evidence was re-baselined.

T2 also pins source bytes against `03c28e76bd893a716c1b080bd34ccbfffd42993e`,
including `firmware/main/state_handlers.c`. The post-edit T2 run exited 1:
`T2 FAIL: regenerated evidence differs`. Its candidate reports
`"source_inputs_unchanged": false`, with the dirty-input list containing
only `firmware/main/state_handlers.c`; the other seven internal gates remain
true. This is a worse gate result caused by the requested hygiene edit
against T2's fixed source pin. No gate, pin or committed hash was changed.

The saved Linux candidates report `T2_ROWS_BEFORE_AFTER_IDENTICAL=True` and
`T2_ROWS_BEFORE_AFTER_DIFFERING_LEAVES=0`. Comparing the simulation summaries
separately from apparatus, cap-inventory line numbers and gate status gives
`T2_SIMULATION_SUMMARIES_BEFORE_AFTER_IDENTICAL=True`. That diagnostic
comparison does not waive the actual gate. The post-edit candidate still
has 173 detailed-row differences against the committed evidence, as the
baseline did. Owner follow-up is needed to reconcile the fixed source pin
with approved source edits and reproduce the exact evidence on the Mac.

Generated JSON restored after the first full C1 run: `firmware/cosim-results.json`,
`firmware/fault-cycle.json`, `firmware/leak-checks.json`,
`firmware/runaway-checks.json`, `firmware/xcheck-cosim.json`, and
`robustness/hc-cosim.json` (all under `output/temper-sensor-r3/`). The recorded
post-restore result was `TRACKED_TREE_CLEAN`. The same six files were
restored after the post-edit run; each was byte-identical
to its saved Linux baseline output (`JSON_REPEAT IDENTICAL` for every file).
The checkout again reported `TRACKED_TREE_CLEAN`, and the clean-input T1
rerun reported `T1 PASS` (exit 0). Sensitivity exited 0 before and after,
with `SENSITIVITY_BEFORE_AFTER_IDENTICAL=True`. The full harness never
reached `ALL C1 FIRMWARE CHECKS PASS`; this is a recorded validation blocker,
not a passing full run.
