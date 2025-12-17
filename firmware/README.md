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
│   ├── hal/               # Hardware abstraction layer
│   └── safety/            # Safety monitoring and fault handling
└── test/                  # Host-based unit and integration tests
```

## Building

### Prerequisites

- ESP-IDF v5.0+ (for target builds)
- CMake 3.16+
- GCC (for host-based tests)

### Target Build (ESP32-S3)

```bash
cd firmware
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

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
    mock_sm_set_dc_bus_current(40.0f);  // > 35A threshold
    state_machine_update();
    
    /* Verify fault handling */
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_CURRENT, state_machine_get_fault());
}
```

## Safety Features

The firmware implements multiple layers of safety:

1. **Hardware Watchdog (TPS3823-33)**: External WDT fed every update cycle, 1.6s timeout
2. **Software Watchdog**: State-specific timeouts (1-10s depending on state)
3. **Over-Current Protection**: DC bus current >35A triggers immediate shutdown
4. **Over-Temperature Protection**: Heatsink >100°C triggers fault
5. **Fan Failure Detection**: Tachometer monitoring during operation
6. **RTD Probe Monitoring**: Open circuit (>10kΩ) and short circuit (<10Ω) detection
7. **Thermal Runaway Detection**: Pan temp exceeding target by >10°C
8. **Pan Detection**: Impedance-based detection with confidence threshold

## Configuration

Key parameters in `state_machine.c`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SAFE_IDLE_TEMP` | 50°C | Temperature for COOLDOWN → IDLE |
| `MAX_TEMP` | 250°C | Maximum allowed setpoint |
| `MIN_TEMP` | 50°C | Minimum allowed setpoint |
| `PAN_DETECT_TIMEOUT_MS` | 5000ms | Pan detection timeout |
| `NO_PAN_TIMEOUT_MS` | 3000ms | Pan removal grace period |
| `MAX_PREHEAT_TIME_MS` | 600000ms | 10 minute preheat limit |

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
