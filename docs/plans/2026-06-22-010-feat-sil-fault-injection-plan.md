---
title: "SIL Fault Injection Testing for Firmware Test Suite"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-design-validation-ideation.md
---

# Plan: SIL Fault Injection Testing for Firmware Test Suite

## Problem Frame

The induction cooker operates at mains voltage with a 3 kW power stage driving an IGBT-based resonant inverter. A firmware fault (missed sensor reading, stuck relay, runaway current) can cause fire, electrical shock, or toxic smoke. The state machine at `firmware/main/state_machine.c:939` defines `check_safety_interlocks()` which checks over-temperature, over-current, fan failure, and RTD probe health on every update cycle. These interlocks must be **proven to work** — not just code-reviewed.

A partial SIL fault-injection framework already exists at `firmware/test/test_sil_fault_injection.c` (711 lines, committed) and a CMake target `test_sil_fault_injection` at `firmware/test/CMakeLists.txt:376`. The framework reads `traces/manifest.json` and replays CSV trace files against the real `state_machine.c` (compiled for `HOST_BUILD`) using the mock_sm_* API from `state_machine_stubs.c`. However, **the traces/manifest.json and CSV trace files are missing** — the framework has no test cases to run. Additionally, the current fault coverage in `check_safety_interlocks()` only covers 5 fault types (RTD open/short, over-temp, over-current, fan failure) out of the 10 defined in `FAULT_LIST` at `firmware/main/state_machine.h:61`.

This plan completes the SIL fault injection system by: (1) generating trace files for all 10 fault codes, (2) creating the manifest.json that maps traces to expected outcomes, (3) adding missing fault detection paths for IGBT-short and relay-welded, and (4) producing a fault coverage report.

## Requirements Trace

| Requirement | Source |
|-------------|--------|
| R1: Fault injection harness can simulate sensor-open, sensor-short, relay-welded, ADC-stuck, IGBT-short via trace CSV replay | User requirement |
| R2: Each injected fault triggers the correct `FAULT_*` enum from `FAULT_LIST` | User requirement |
| R3: System enters safe state (power cut, STATE_FAULT) within bounded time after fault injection | User requirement |
| R4: All fault tests run in CI (no hardware required — state injection, not electrical injection) | User requirement |
| R5: Fault coverage report generated as test output | User requirement |

## Ground Truth Interfaces (verified against working tree)

| Symbol | Actual Location | Key Fields |
|--------|----------------|------------|
| `FAULT_LIST(X)` — X-macro with 10 fault codes | `firmware/main/state_machine.h:61-72` | `FAULT_NONE`, `FAULT_OVER_TEMP`, `FAULT_OVER_CURRENT`, `FAULT_FAN_FAILURE`, `FAULT_PROBE_OPEN`, `FAULT_PROBE_SHORT`, `FAULT_THERMAL_RUNAWAY`, `FAULT_SELF_TEST_FAILED`, `FAULT_WATCHDOG_RESET`, `FAULT_COOLDOWN_OVERHEAT`, `FAULT_PAN_DETECT_HW` |
| `check_safety_interlocks()` — runs per tick during PREHEAT/HEATING | `firmware/main/state_machine.c:939-973` | Checks: heatsink > 100°C, current > 35A, fan not running, RTD > 10kΩ, RTD < 10Ω |
| `state_fault_entry()` — emergency power cut on fault | `firmware/main/state_machine.c:845-864` | Calls `power_set_level(0)`, `pwm_disable_all()`, `pll_disable()`, `fan_set_speed(FAN_SPEED_MAX)`, `eeprom_log_fault()` |
| `fault_cleared()` — determines if user can reset | `firmware/main/state_machine.c:975-996` | Per-fault clear conditions (temp < 70°C, fan running, RTD in range, self-test passes) |
| `mock_sm_*` API — stubbed sensor/actuator control | `firmware/test/state_machine_stubs.c:140-420` | `mock_sm_set_pan_temperature`, `mock_sm_set_heatsink_temperature`, `mock_sm_set_dc_bus_current`, `mock_sm_set_rtd_resistance`, `mock_sm_set_fan_running`, `mock_sm_set_pan_status`, `mock_sm_press_button`, `mock_sm_advance_time` |
| `test_sil_fault_injection.c` — trace replay runner | `firmware/test/test_sil_fault_injection.c:1-711` | Parses `traces/manifest.json`, loads CSV traces, replays against `state_machine_update()`, asserts `expected_state`, `expected_fault`, `max_latency_ticks` |
| `test_sil_fault_injection` — CMake target | `firmware/test/CMakeLists.txt:376-390` | Links `state_machine.c + stubs + test_sil_fault_injection.c`; registered as `sil_fault_tests` in CTest |
| `safety_sim_inject_fault()` — safety-level injection pattern | `firmware/components/safety/safety.h:175` | Used by `test_safety.c:138` for SAFETY_INTERLOCK_TRIP injection |
| `adc_guard_read_safe()` — ADC stuck-at-value detection | `firmware/components/safety/adc_guard.c` | Detects range-low, range-high, stuck-at, timeout conditions |

## Scope Boundaries

### In Scope
- Generate CSV trace files and `traces/manifest.json` covering all 10 `FAULT_LIST` entries
- Add fault detection for **IGBT-short** (manifests as DC bus over-current spike > 50 A in < 10 ms) — requires new `check_igbt_short()` in `check_safety_interlocks()` or a dedicated fast-path check
- Add fault detection for **relay-welded** (manifests as heatsink temperature continuing to rise during COOLDOWN state — already partially detected via `FAULT_COOLDOWN_OVERHEAT` at `state_machine.c:828`)
- Add fault detection for **ADC-stuck** (same reading over multiple update cycles) — requires new sensor-stuck detection
- Produce a fault coverage report summarizing which faults are detected, cleared, and tested
- CI integration: CTest `sil_fault_tests` target runs during `cmake --build build --target run_tests`

### Deferred to Follow-Up Work
- Hardware-in-the-loop (HIL) tests with actual sensor break-out boards
- Independent SIL assessor certification paperwork
- Coverage of combined faults (simultaneous sensor failure + fan failure)
- Trace generation automation (currently hand-written CSV; a plant model simulator would be a separate project)
- JAX-based plant model integration for generating degenerate traces

## Key Technical Decisions

### K1: Trace replay architecture (keep existing design)

**Decision:** Continue with the existing trace-replay pattern in `test_sil_fault_injection.c` rather than building a new harness.

**Rationale:** The framework already compiles, links, and registers with CTest. It replays time-series CSV traces against the real `state_machine.c` binary. This is a proven SIL technique (ANSYS medini, Zephyr twister) where deterministic inputs are replayed against the production binary. The trace format is simple:
```
tick,hs_temp,pan_temp,dc_current,rtd_resistance,pan_impedance,fan_running
```

**Files consumed:** `test_sil_fault_injection.c` (reader), `state_machine_stubs.c` (mock backend), `traces/*.csv` (input data), `traces/manifest.json` (test spec).

### K2: Manifest-driven test generation

**Decision:** Each fault scenario is a JSON entry in `traces/manifest.json` specifying the trace file, perturbation timing, expected outcome, and latency bound. The existing parser at `test_sil_fault_injection.c:213` reads this format.

**Rationale:** Separates test data from test logic. Adding a new fault scenario requires only a CSV trace + manifest entry — no C code changes. This matches the existing architecture.

### K3: New fault detection for IGBT-short and ADC-stuck

**Decision:** Add two new checks to `check_safety_interlocks()` and two new entries in `FAULT_LIST`:
- `FAULT_IGBT_SHORT` — triggered when `dc_bus_current > 50.0f` (hard short, distinct from steady-state over-current at 35A)
- `FAULT_ADC_STUCK` — triggered when 3+ consecutive ADC readings return identical values (stuck-at detection)

**Rationale:** The user requirement explicitly names these faults. The current interlock check only catches steady-state over-current at 35A (`state_machine.c:947`), which may not trigger fast enough for an IGBT short-circuit (<10ms event). A dedicated high-threshold fast-check with a shorter debounce window catches the IGBT-short case. ADC-stuck is a silent failure that existing threshold checks may miss (if stuck value is within range).

**Files modified:** `firmware/main/state_machine.h` (FAULT_LIST +2 entries), `firmware/main/state_machine.c` (check_safety_interlocks + ADC stuck detection), `firmware/test/test_state_machine.c` (add fault string coverage for new entries), `firmware/test/test_transition_table_generated.c` (regenerate if needed).

### K4: Fault coverage report format

**Decision:** Output a machine-parseable coverage summary at the end of the SIL test run, listing each fault code, whether it was tested, whether detection passed, and the measured latency.

**Rationale:** R5 requires a coverage report. The Unity test framework prints pass/fail for each test. We extend `test_sil_fault_injection.c:main()` to print a summary table after `UnityEnd()` returns. This is CI-friendly (plain text, grep-able) and human-readable.

### K5: No hardware dependency

**Decision:** All SIL tests use `HOST_BUILD` (no ESP-IDF, no FreeRTOS) and `state_machine_stubs.c` for mock sensor inputs. The tests run as a native binary on the CI runner (macOS/Linux).

**Rationale:** R4 requires CI execution. The existing `test_state_machine_only` target at `CMakeLists.txt:132` demonstrates this pattern works — it compiles `state_machine.c` with stubs and runs without hardware.

## Implementation Units

### U1. Trace file generation (`traces/*.csv`)

**Goal:** Create one CSV trace file per fault scenario. Each trace replays the plant model (sensor values) over time with a perturbation injected at a specific tick.

**Requirements:** R1, R2

**Files:**
- Create: `firmware/test/traces/` directory
- Create: `firmware/test/traces/trace_fault_over_temp.csv`
- Create: `firmware/test/traces/trace_fault_over_current.csv`
- Create: `firmware/test/traces/trace_fault_fan_failure.csv`
- Create: `firmware/test/traces/trace_fault_probe_open.csv`
- Create: `firmware/test/traces/trace_fault_probe_short.csv`
- Create: `firmware/test/traces/trace_fault_thermal_runaway.csv`
- Create: `firmware/test/traces/trace_fault_igbt_short.csv`
- Create: `firmware/test/traces/trace_fault_relay_welded.csv`
- Create: `firmware/test/traces/trace_fault_adc_stuck.csv`
- Create: `firmware/test/traces/trace_fault_cooldown_overheat.csv`

**Approach:**
Each CSV has 7 columns: `tick,hs_temp,pan_temp,dc_current,rtd_resistance,pan_impedance,fan_running`. The trace starts with nominal values (25°C ambient, 0 A current, 100 Ω RTD, 5 Ω pan impedance, fan running). At the perturbation tick, sensor values shift to fault-state values. The trace continues for enough ticks to observe the state machine's reaction + latency window.

Nominal pre-perturbation values:
```
tick,hs_temp,pan_temp,dc_current,rtd_resistance,pan_impedance,fan_running
0,35,25,5,100,5,1
...
80,35,92,5,100,5,1   <- boilerplate reaches HEATING here (~tick 80)
```

Fault injection parameters per scenario:

| Fault | Perturb at tick | Sensor changed | Fault values | Expected latency |
|-------|----------------|----------------|--------------|-----------------|
| FAULT_OVER_TEMP | 85 | `hs_temp` | 105.0 | ≤2 ticks |
| FAULT_OVER_CURRENT | 85 | `dc_current` | 40.0 | ≤2 ticks |
| FAULT_FAN_FAILURE | 85 | `fan_running` | 0 (false) | ≤2 ticks |
| FAULT_PROBE_OPEN | 85 | `rtd_resistance` | 15000.0 | ≤2 ticks |
| FAULT_PROBE_SHORT | 85 | `rtd_resistance` | 5.0 | ≤2 ticks |
| FAULT_THERMAL_RUNAWAY | 85 | `pan_temp` | 115.0 | ≤2 ticks |
| FAULT_IGBT_SHORT | 85 | `dc_current` | 60.0 | ≤2 ticks |
| FAULT_RELAY_WELDED | — | `hs_temp` during COOLDOWN | 80→85→90 rising | ≤3 ticks after drift |
| FAULT_ADC_STUCK | 80 | `pan_temp` | 92.0 repeated (no change) | ≤5 ticks |
| FAULT_COOLDOWN_OVERHEAT | — | `hs_temp` during COOLDOWN | 55→65 (rising 10°C) | ≤3 ticks |

Traces are ~200 ticks each (20 seconds at 100 ms/tick). The runner at `test_sil_fault_injection.c:559` iterates ticks 0..row_count, calling `mock_sm_advance_time(DT_MS)`, setting sensor values from CSV columns, and calling `state_machine_update()`.

**Verification:** Run `./build/test_sil_fault_injection` with traces present; each test case passes with `[PASS] state=N fault=N latency=N ticks`.

---

### U2. Manifest.json creation

**Goal:** Create `traces/manifest.json` describing each fault injection test case.

**Requirements:** R1, R2, R3

**Files:**
- Create: `firmware/test/traces/manifest.json`

**Approach:**
The manifest schema is defined implicitly in `test_sil_fault_injection.c:193-208` (`manifest_entry_t`). Each entry specifies:
```json
{
  "name": "SIL: Over-Temperature Fault",
  "description": "Heatsink exceeds 100°C during heating triggers FAULT_OVER_TEMP",
  "trace_file": "trace_fault_over_temp.csv",
  "initial_conditions": { "self_test_pass": true },
  "perturbation": {
    "at_tick": 85,
    "sensors": [
      { "name": "heatsink_temperature", "over_ticks": 1 }
    ]
  },
  "expected": {
    "final_state": "FAULT",
    "fault_code": "FAULT_OVER_TEMP",
    "max_latency_ticks": 2,
    "soft_assertions": [
      { "power_off": true },
      { "eeprom_logged": "FAULT_OVER_TEMP" }
    ]
  }
}
```

The existing parser at `test_sil_fault_injection.c:213-426` handles all these fields. Key fields:
- `trace_file`: path relative to `traces/` directory
- `perturbation.at_tick`: when the fault is injected in the trace
- `perturbation.sensors[].over_ticks`: how many ticks the fault condition persists
- `expected.final_state`: `"FAULT"` for all fault scenarios
- `expected.fault_code`: the `FAULT_*` enum string
- `expected.max_latency_ticks`: maximum allowed delay between perturbation end and state transition
- `expected.soft_assertions`: optional checks (power cut, EEPROM log, relay state)

One entry per fault scenario (10 entries total for U1's traces + existing fault types).

**Verification:** `parse_manifest()` in the test runner successfully loads all entries. `g_entry_count == 10`.

---

### U3. IGBT-short fault detection

**Goal:** Add `FAULT_IGBT_SHORT` detection to the state machine with a dedicated high-current fast-response check.

**Requirements:** R1 (IGBT-short scenario), R2

**Files:**
- Modify: `firmware/main/state_machine.h` — add `FAULT_IGBT_SHORT` to `FAULT_LIST` (line 65)
- Modify: `firmware/main/state_machine.c` — add IGBT short check in `check_safety_interlocks()` (before line 939), add clear condition in `fault_cleared()` (line 978), add fault string to `fault_name_table` (auto-generated by X-macro)
- Modify: `firmware/test/test_state_machine.c` — add `test_sm_fault_on_igbt_short()` test case (after line 536)
- Regenerate: `firmware/test/test_transition_table_generated.c` via `python3 firmware/test/gen_transition_table.py --generate` if transition table is affected

**Approach:**
Add before the existing over-current check at `state_machine.c:947`:
```c
/* IGBT short-circuit detection (hard short > 50A) */
/* Catches the hard-fault case before the steady-state 35A limit */
if (read_dc_bus_current() > 50.0f) {
    sm_ctx.fault_code = FAULT_IGBT_SHORT;
    transition_to(STATE_FAULT);
    return;
}
```

The existing FAULT_OVER_CURRENT check at 35A (`state_machine.c:947`) handles steady-state over-current from load mismatch. The new 50A check catches hard shorts (IGBT collector-emitter short, shoot-through) with a higher threshold. The FAULT_IGBT_SHORT clear condition is identical to OVER_CURRENT (power cycle).

**X-macro update in `state_machine.h` line 65** — insert after FAULT_OVER_CURRENT:
```c
X(FAULT_IGBT_SHORT,        "IGBT SHORT") \
```

**Test case at `test_state_machine.c` (after line 536):**
```c
void test_sm_fault_on_igbt_short(void) {
    /* Boilerplate to reach HEATING (identical to over-current test) */
    setup_test();
    state_machine_update();
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(100);
    state_machine_update();
    mock_sm_release_button(BUTTON_START);
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < 5; i++) {
        mock_sm_advance_time(100);
        state_machine_update();
    }
    mock_sm_set_pan_temperature(92.0f);
    mock_sm_advance_time(100);
    state_machine_update();  /* PREHEAT -> HEATING */

    mock_sm_set_dc_bus_current(55.0f);  /* Exceeds 50A IGBT short threshold */
    mock_sm_advance_time(100);
    state_machine_update();

    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_IGBT_SHORT, state_machine_get_fault());
}
```

Register the test in `run_state_machine_tests()` (after test_sm_fault_on_over_current, line 1148).

**Verification:** `./build/test_state_machine_only` passes all existing + new test. IGBT-short trace in U1 triggers FAULT_IGBT_SHORT.

---

### U4. ADC-stuck fault detection

**Goal:** Add `FAULT_ADC_STUCK` detection. An ADC that returns the same value across consecutive reads is a silent failure — thresholds may not catch it.

**Requirements:** R1 (ADC-stuck scenario), R2

**Files:**
- Modify: `firmware/main/state_machine.h` — add `FAULT_ADC_STUCK` to `FAULT_LIST`
- Modify: `firmware/main/state_machine.c` — add stuck-ADC tracking to `sm_ctx`, add detection in `check_safety_interlocks()`, add clear condition in `fault_cleared()`
- Modify: `firmware/test/test_state_machine.c` — add test case
- Regenerate: `firmware/test/test_transition_table_generated.c` if needed

**Approach:**
Add to `sm_ctx` struct at `state_machine.c:33`:
```c
/* ADC stuck-at detection */
float last_pan_temp;
uint8_t pan_temp_stuck_count;
float last_heatsink_temp;
uint8_t heatsink_temp_stuck_count;
```

Add to `state_machine_init()` (after line 175), reset these counters to 0.

Add to `check_safety_interlocks()` (at end, before closing brace at line 973):
```c
/* ADC stuck-at detection: same value across 3+ consecutive reads */
float pan_temp = read_pan_temperature();
if (pan_temp == sm_ctx.last_pan_temp) {
    sm_ctx.pan_temp_stuck_count++;
    if (sm_ctx.pan_temp_stuck_count >= 3) {
        sm_ctx.fault_code = FAULT_ADC_STUCK;
        transition_to(STATE_FAULT);
        return;
    }
} else {
    sm_ctx.last_pan_temp = pan_temp;
    sm_ctx.pan_temp_stuck_count = 0;
}
float hs_temp = read_heatsink_temperature();
if (hs_temp == sm_ctx.last_heatsink_temp) {
    sm_ctx.heatsink_temp_stuck_count++;
    if (sm_ctx.heatsink_temp_stuck_count >= 3) {
        sm_ctx.fault_code = FAULT_ADC_STUCK;
        transition_to(STATE_FAULT);
        return;
    }
} else {
    sm_ctx.last_heatsink_temp = hs_temp;
    sm_ctx.heatsink_temp_stuck_count = 0;
}
```

**Important:** The detection uses equality comparison on floats. This is intentional — an ADC reads integer counts that get converted to a float representation. A stuck ADC returns bit-identical values because the underlying ADC register hasn't changed. In production, this check would use the raw ADC counts, not the temperature floats. For the trace-based test, we simulate it by repeating the same float value in the CSV.

**Clear condition:** Power cycle. Add to `fault_cleared()` switch:
```c
case FAULT_ADC_STUCK:
    return false;  /* requires power cycle */
```

**Test case** in `test_state_machine.c`: boilerplate to HEATING, then inject same pan temperature across 3+ updates, assert FAULT_ADC_STUCK.

**Verification:** `./build/test_state_machine_only` passes. ADC-stuck trace triggers FAULT_ADC_STUCK.

---

### U5. Fault coverage report

**Goal:** After all SIL tests run, print a machine-parseable coverage summary showing which fault codes were tested and the measured latency.

**Requirements:** R5

**Files:**
- Modify: `firmware/test/test_sil_fault_injection.c` — add coverage reporting after `UnityEnd()` (after line 710)

**Approach:**
After `UnityEnd()` returns, iterate the manifest entries and print a summary table:

```
=== SIL Fault Coverage Report ===
FAULT CODE              TESTED  DETECTED  LATENCY (ms)
-------------------------------------------------------
FAULT_OVER_TEMP          YES      YES       200
FAULT_OVER_CURRENT       YES      YES       200
FAULT_FAN_FAILURE        YES      YES       200
FAULT_PROBE_OPEN         YES      YES       200
FAULT_PROBE_SHORT        YES      YES       200
FAULT_THERMAL_RUNAWAY    YES      YES       200
FAULT_IGBT_SHORT         YES      YES       200
FAULT_RELAY_WELDED       YES      YES       300
FAULT_ADC_STUCK          YES      YES       500
FAULT_COOLDOWN_OVERHEAT  YES      YES       300
FAULT_SELF_TEST_FAILED   YES      YES         -
FAULT_WATCHDOG_RESET      NO       -          -
FAULT_PAN_DETECT_HW       NO       -          -
-------------------------------------------------------
Coverage: 11/13 faults tested (84.6%)
```

Track test results during execution via a static array of `fault_test_result_t` structs that record `fault_code`, `tested` (bool), `detected` (bool), `latency_ms` (int). Populate during `run_sil_test()`.

CI can grep for `Coverage:` and fail if below a threshold.

**Verification:** Run `./build/test_sil_fault_injection`, observe coverage report at end of output.

---

### U6. CI integration

**Goal:** SIL fault tests run automatically in CI.

**Requirements:** R4

**Files:**
- Modify: `.github/workflows/firmware-tests.yml` (or equivalent CI config) — add step for `sil_fault_tests`
- (No changes to `CMakeLists.txt` — target already exists at line 376)

**Approach:**
The CMake target `test_sil_fault_injection` and CTest registration `sil_fault_tests` already exist at `firmware/test/CMakeLists.txt:376-390`. Add a CI step:
```yaml
- name: SIL Fault Injection Tests
  run: |
    cd firmware/test/build
    ctest -R sil_fault_tests --output-on-failure
```

Ensure the working directory is `firmware/test/build` so the test binary finds `traces/manifest.json` via the relative path `traces/manifest.json` (hardcoded at `test_sil_fault_injection.c:61`).

**Verification:** Push a branch; CI runs `sil_fault_tests` and passes.

---

## System-Wide Impact

| Component | Impact |
|-----------|--------|
| `firmware/main/state_machine.h` | +2 entries in `FAULT_LIST` X-macro (FAULT_IGBT_SHORT, FAULT_ADC_STUCK) |
| `firmware/main/state_machine.c` | +ADC stuck tracking fields in `sm_ctx`, +IGBT short check in `check_safety_interlocks()`, +ADC stuck check, +clear conditions |
| `firmware/test/test_state_machine.c` | +2 test cases (igbt_short, adc_stuck), +2 in fault string coverage test (auto-pass via loop) |
| `firmware/test/test_transition_table_generated.c` | Regenerated if transition table changed |
| `firmware/test/traces/` | New directory with 10 CSV trace files + 1 manifest.json |
| `firmware/test/test_sil_fault_injection.c` | +coverage report logic (~60 lines) in `main()` |
| CI workflow | +1 test step for `sil_fault_tests` |
| `firmware/test/CMakeLists.txt` | No changes needed (target already exists) |
| `firmware/config.yaml` | No changes needed (thresholds are code constants, not config) |

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ADC stuck detection via float equality unreliable | Medium | Medium | Use epsilon comparison (1e-6f) instead of `==`; document that in production this would use raw ADC counts. If float instability causes false positives, increase `stuck_count` threshold to 5. |
| Manifest.json parse fails silently | Low | High | Existing parser at `test_sil_fault_injection.c:213` prints WARNING if file missing and returns 0 entries. Tests run but produce 0 results — not a false pass. Add `TEST_ASSERT_GREATER_THAN(0, g_entry_count)` to fail hard if manifest is missing/corrupt. |
| Trace files drift from state machine behavior | Medium | Medium | Trace values are deterministic (hardcoded sensor values at specific ticks). If `state_machine.c` state transition timing changes, the trace may need updating. Document trace conventions in `firmware/test/traces/README.md`. |
| FAULT_IGBT_SHORT threshold conflicts with FAULT_OVER_CURRENT | Low | Low | IGBT short check runs first at 50A threshold; steady-state check at 35A acts as a backup. The checks are ordered: IGBT short (50A) → over-current (35A). An IGBT short will always be caught by the 50A check before the 35A check fires. |
| Relay-welded not detectable without actual relay status feedback | Medium | Medium | The firmware has no relay position sensor. Detection is indirect: if heatsink temperature rises during COOLDOWN when relay should be open, we infer welded contacts. This is probabilistic — a hot heatsink from prior cooking may cool slowly, masking the rise. The `FAULT_COOLDOWN_OVERHEAT` at `state_machine.c:828` already monitors for temperature rise during cooldown. We re-use this mechanism. Document limitation in coverage report. |
| Stuck ADC counter reset on state transitions | Medium | Low | The `last_*_temp` and `*_stuck_count` fields must be reset in `state_init_entry()` (already handled by `state_machine_init()` memset). They persist across state transitions inside the same cooking cycle, which is correct — a stuck ADC during heating is a fault regardless of state changes. |

## Test Strategy

### Unit Tests (existing harness, `test_state_machine_only`)
- Verify `FAULT_IGBT_SHORT` triggers on current > 50A in HEATING state
- Verify `FAULT_IGBT_SHORT` does NOT trigger on current = 35A (should be FAULT_OVER_CURRENT)
- Verify `FAULT_ADC_STUCK` triggers after 3 identical pan temperature readings
- Verify `FAULT_ADC_STUCK` does NOT trigger with normal varying readings
- Verify both new fault codes appear in `fault_name_table` (string coverage test auto-passes via loop)
- Verify existing fault tests (over-temp, over-current, fan, probe open/short, thermal runaway) continue to pass

### SIL Trace Tests (new harness, `test_sil_fault_injection`)
- All 10 trace entries in manifest.json produce correct `expected_state` and `expected_fault`
- Latency for each fault is within `max_latency_ticks`
- Soft assertions: power is cut (power_level == 0), fault logged to EEPROM
- Coverage report prints at end with 84%+ coverage

### Integration Tests
- `test_state_machine_only` binary exits 0 (all unit tests pass)
- `test_sil_fault_injection` binary exits 0 (all trace tests pass)
- `ctest -R sil_fault_tests --output-on-failure` passes in CI
- Full build: `cmake -B build && cmake --build build && ctest` passes all targets

### Manual Verification
```bash
cd firmware/test
cmake -B build && cmake --build build
./build/test_state_machine_only          # Passes 50+ tests
./build/test_sil_fault_injection         # Passes 10 SIL tests, prints coverage
ctest --output-on-failure                # All test suites pass
```
