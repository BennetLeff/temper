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
