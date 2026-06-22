---
title: "Safety-Critical Firmware Testing Patterns: SIL Fault Injection & Runaway Boundary Interlock"
date: 2026-06-22
category: best-practices
module: firmware/safety
problem_type: best_practice
component: testing
severity: high
applies_when:
  - Adding or modifying safety-critical state machine transitions
  - Introducing a new fault code to FAULT_LIST
  - Changing thresholds that affect fault detection latency
  - Adding a hardware-invariant interlock (non-software-overridable)
tags:
  - safety
  - testing
  - sil
  - fault-injection
  - runaway
  - interlock
  - firmware
---

# Safety-Critical Firmware Testing Patterns

## Context

The Temper induction cooker firmware runs on ESP32-S3 and controls a power stage capable of delivering hundreds of watts into a pan. The state machine (`firmware/main/state_machine.c`) defines 8 states and 12 fault codes. Safety is layered across hardware comparators (OCP, OVP, thermal), a TPS3823-33 external watchdog, and software fault detection in `check_safety_interlocks()`. Two complementary testing patterns ensure these layers work together: **SIL fault injection** validates that perturbed sensor data triggers correct state transitions at correct latency; **runaway boundary interlock** validates a hardware-latched, non-software-overridable power cut against configurable temperature thresholds.

## Guidance

### Pattern 1: SIL Fault Injection Testing

**What:** Replay perturbed plant-model CSV traces through the real `state_machine.c` compiled for host build, validating that injected faults cause correct state transitions within latency bounds.

**How:** A test harness (`firmware/test/test_sil_fault_injection.c`) reads `firmware/test/traces/manifest.json`, which declares test cases with perturbed sensor traces, expected outcomes, and latency budgets. Each test case drives the state machine through a standardized warm-up sequence (INIT → IDLE → PAN_DET → PREHEAT → HEATING), then replays the perturbed trace tick-by-tick. The harness checks:
- **Hard assertions**: final state matches expected, fault code matches expected, latency ≤ `max_latency_ticks`.
- **Soft assertions**: power level zeroed, fault code logged to mock EEPROM.
- **Coverage report**: a table of all `FAULT_LIST` entries with test/detection/latency status.

**When to extend:** Every new entry in `FAULT_LIST` (in `firmware/main/state_machine.h`) needs a corresponding entry in `manifest.json` and a perturbed CSV trace. The trace generator is in `firmware/test/traces/` (plant-model scripts that produce `.csv` files with injected sensor anomalies at specific tick offsets).

### Pattern 2: Runaway Boundary Interlock

**What:** A continuous interlock running at the top of `state_machine_update()`—before ALL state-specific logic and before the message-pending early-return—that reads pan/coil temperature, computes rate-of-rise from the previous reading, and on breach: asserts a dedicated GPIO to cut the gate driver independently of software PWM, calls `trigger_hardware_shutdown()`, sets a latching flag that blocks all `transition_to()` calls away from `STATE_RUNAWAY_FAULT`, and requires a physical power-cycle to clear.

**How:** 
1. `check_runaway_boundary()` is called at `state_machine.c:218` (after `watchdog_hardware_feed()`, before `message_pending` early-return).
2. It reads `read_pan_temperature()`, compares against `g_config.runaway.max_absolute_temp_c` (default 300°C) and rate-of-rise against `g_config.runaway.max_temp_rise_rate_c_per_s` (default 15°C/s, computed from `last_pan_temp_c` stored on the previous call).
3. On breach: `gpio_set_level(RUNAWAY_CUT_GPIO, 1)`, `trigger_hardware_shutdown()`, `sm_ctx.runaway_latched = true`, `sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY`, `transition_to(STATE_RUNAWAY_FAULT)`.
4. `transition_to()` at line 901 gains a guard: `if (sm_ctx.runaway_latched && new_state != STATE_RUNAWAY_FAULT) return;`.
5. `STATE_RUNAWAY_FAULT` has a no-op update function — no button reads, no temperature monitoring, no watchdog changes. Power is cut at the hardware level by the GPIO latch.

**CI gate:** `simulation/testbenches/check_runaway_boundary.sh` extracts the worst-3 corners from a parametric sweep margin report, re-runs ngspice with tight tolerance (RELTOL=1e-5), and asserts margin ≥ 20°C between IGBT junction temperature and destructive runaway boundary.

**Config:** Two new fields in `firmware/config.yaml` under a `runaway:` group, with `legacy_define: false` (accessed via `g_config.runaway.*`), each with `env_var` for runtime tuning and `doc` for generated documentation. Regenerate `firmware/config.h` with `python3 firmware/tools/gen_config.py`.

## Why This Matters

| Without SIL fault injection | With SIL fault injection |
|---|---|
| Ad-hoc printf debugging of fault paths | Every fault code has a regression test with known-good perturbed trace and latency bound |
| No guarantee transition latency meets response-time requirements | Hard assertion that FAULT is reached within `max_latency_ticks` (e.g., 2 ticks = 200ms) |
| Coverage unknown | `FAULT_LIST` macro drives a coverage table showing tested/detected/latency per fault code |
| Sensor anomaly → fault chain ends untested | Trace perturbation covers ADC stuck-at, relay welding (cooldown overheat), fan failure with realistic temporal profiles |

| Without runaway interlock | With runaway interlock |
|---|---|
| Thermal runaway detected only in PREHEAT (timeout) and HEATING (target+10°C) | Detected on every control loop iteration, regardless of state |
| No rate-of-rise check | Rate-of-rise computed from consecutive readings, catches rapid thermal escalation before absolute threshold is hit |
| Fault clearable via BUTTON_RESET | Hardware GPIO latch + software latching flag: only power-cycle clears it |
| Software PWM disable is the only firmware-level power cut path (can fail if PWM peripheral is locked up) | Dedicated GPIO drives the hardware OR gate directly, cutting the gate-driver disable line within nanoseconds |
| Config thresholds hardcoded | Thresholds in `config.yaml`, runtime-configurable via env vars, CI-verified with ngspice margin sweeps |

## When to Apply

- **SIL fault injection**: Every time you add a fault code to `FAULT_LIST` in `state_machine.h`. Create a perturbed trace CSV and a manifest entry. If the fault is triggered from a specific state (not STATE_HEATING), extend the warm-up boilerplate in `sm_boilerplate_to_heating()`.
- **Runaway boundary interlock**: Every time you modify `check_safety_interlocks()`, add or change a temperature threshold, or touch `trigger_hardware_shutdown()`. The interlock must remain the *first* check in `state_machine_update()` — nothing may move above it. If a new sensor is added to the safety chain, consider whether it should also feed the boundary check.
- **Both patterns**: Before merging any PR that touches `firmware/main/state_machine.c`, `firmware/main/safety.*`, `firmware/config.yaml`, or `firmware/main/state_machine.h`.

## Examples

### Example 1: Adding a SIL test for FAULT_OVER_TEMP

From `firmware/test/traces/manifest.json` line 3:

```json
{
  "name": "SIL: Over-Temperature Fault",
  "description": "Heatsink exceeds 100C during heating triggers FAULT_OVER_TEMP",
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

The corresponding perturbed trace (`trace_fault_over_temp.csv`) is generated with `heatsink_temperature` column spiking to 105°C at tick 85. The harness replays this trace through `state_machine_update()`, checks that `STATE_FAULT` is reached within 2 ticks (200ms) of the perturbation end, and that the logged fault is `FAULT_OVER_TEMP`.

### Example 2: Runaway interlock check placement in `state_machine_update()`

From the planned implementation at `firmware/main/state_machine.c:218`:

```c
void state_machine_update(void) {
    uint32_t now = get_time_ms();
    sm_ctx.state_duration = now - sm_ctx.state_entry_time;

    /* Hardware watchdog heartbeat */
    watchdog_hardware_feed();

    /* --- RUNAWAY BOUNDARY INTERLOCK (fires before ALL state logic) --- */
    check_runaway_boundary();
    if (sm_ctx.runaway_latched) {
        return;  /* No further processing; power is cut at hardware level */
    }

    /* Handle non-blocking message display */
    if (sm_ctx.message_pending) {
        /* ... */
    }
    /* ... per-state dispatch ... */
}
```

The interlock fires *before* the `message_pending` early-return. If temperature breaches a boundary while a "COMPLETE" or "NO PAN" message is displayed, the UI message is preempted — safety-critical events must never be delayed by UI state.

### Example 3: Config group for runaway thresholds

From `firmware/config.yaml` (runaway group, planned):

```yaml
runaway:
  - c_symbol: RUNAWAY_MAX_ABSOLUTE_TEMP_C
    field: max_absolute_temp_c
    value: 300.0
    c_type: float
    units: "°C"
    env_var: RUNAWAY_MAX_ABSOLUTE_TEMP_C
    doc: "Pan/coil absolute temperature ceiling for runaway boundary interlock"
    legacy_define: false

  - c_symbol: RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S
    field: max_temp_rise_rate_c_per_s
    value: 15.0
    c_type: float
    units: "°C/s"
    env_var: RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S
    doc: "Pan/coil maximum temperature rise rate before runaway interlock triggers"
    legacy_define: false
```

These are accessed via `g_config.runaway.max_absolute_temp_c` and `g_config.runaway.max_temp_rise_rate_c_per_s` in `check_runaway_boundary()`. The `legacy_define: false` means no bare `#define` is emitted — only the struct field, which is the preferred pattern for new config values (existing call sites use legacy `#define`s for backward compatibility).

### Example 4: ADC stuck-at fault — a temporal perturbation test

From `firmware/test/traces/manifest.json` line 177:

```json
{
  "name": "SIL: ADC Stuck Fault",
  "description": "Pan temperature ADC returns identical value across 3+ reads triggers FAULT_ADC_STUCK",
  "trace_file": "trace_fault_adc_stuck.csv",
  "initial_conditions": { "self_test_pass": true },
  "perturbation": {
    "at_tick": 60,
    "sensors": [
      { "name": "pan_temperature", "over_ticks": 50 }
    ]
  },
  "expected": {
    "final_state": "FAULT",
    "fault_code": "FAULT_ADC_STUCK",
    "max_latency_ticks": 52,
    "soft_assertions": [
      { "power_off": true },
      { "eeprom_logged": "FAULT_ADC_STUCK" }
    ]
  }
}
```

This tests the ADC stuck-at detection at `state_machine.c:1007-1034`, which requires 50 consecutive identical readings before tripping. The trace holds `pan_temperature` constant for 50 ticks starting at tick 60. The `max_latency_ticks: 52` accounts for the 50-tick detection window plus 2 ticks of allowed dispatch latency. This is a *temporal* fault — it cannot be detected by a threshold check alone; the stuck-count accumulator must be exercised over time.

### Example 5: CI regression gate for runaway margins

From `simulation/testbenches/check_runaway_boundary.sh` line 1:

```bash
#!/bin/bash
# check_runaway_boundary.sh
# CI regression gate for runaway boundary interlock margin.
#   1. Reads worst-3 corners from runaway_interlock_margin.md
#   2. Re-runs those 3 combinations with tight tolerance (RELTOL=1e-5)
#   3. Asserts margin >= 20 C for all
#   4. Exit 0 on pass, 1 on fail

MIN_MARGIN=20
# ... extracts VBUS, K, C_TOL, TAMB, FAN from markdown table ...
# ... reruns ngspice per corner, computes margin = Tj_end - Tj_trip ...
if awk "BEGIN {exit !($margin >= $MIN_MARGIN)}"; then
    echo "  RESULT: PASS (margin >= $MIN_MARGIN C)"
fi
```

This gate runs in `.github/workflows/simulation-tests.yml` and prevents merging any PR that reduces the runaway thermal margin below 20°C in the worst-3 parametric corners. The full parametric sweep (`sweep_runaway_boundary.sh`) explores 972 combinations of VBUS, thermal conductivity, capacitor tolerance, ambient temperature, and fan RPM.

## Related

- `firmware/test/test_sil_fault_injection.c` — SIL test harness (807 lines, hand-rolled JSON parser, coverage report)
- `firmware/test/traces/manifest.json` — 10 test cases covering all currently defined fault codes
- `firmware/main/state_machine.c:958-1035` — `check_safety_interlocks()` (over-temp, IGBT short, over-current, fan failure, probe open/short, ADC stuck-at)
- `firmware/main/state_machine.c:218` — planned `check_runaway_boundary()` call site
- `firmware/config.yaml:14-169` — single-source-of-truth config manifest
- `firmware/config.h` — generated config header (do not edit directly)
- `docs/plans/2026-06-22-010-feat-runaway-boundary-interlock-plan.md` — full implementation plan for runaway interlock
- `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` — hardware OR gate, OCP/OVP/thermal comparators, TPS3823-33 watchdog, fault latch logic
- `simulation/testbenches/check_runaway_boundary.sh` — CI regression gate for runaway boundary margin
- `docs/SAFETY_TEST_CHECKLIST.md` — pre-power-on hardware safety checklist
- `docs/guides/GPBM_WORKFLOW.md` — Gather-Plan-Build-Measure development workflow
