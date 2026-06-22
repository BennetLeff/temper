---
title: "feat: Add Runaway-Boundary Interlock to State Machine"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-design-validation-ideation.md
---

# feat: Add Runaway-Boundary Interlock to State Machine

## Summary

A firmware safety-hardening feature that adds a non-software-overridable runaway-boundary interlock to the induction cooker state machine. On every control loop iteration—before any state-specific logic—the system checks pan/coil temperature against configurable `max_absolute_temp` and `max_temp_rise_rate` thresholds. A breach transitions the system to a dedicated `STATE_RUNAWAY_FAULT` that cuts power via the hardware GPIO path and requires a physical power-cycle to clear. No software condition, shortcut, or state handler can override or bypass this interlock.

Today the state machine (`firmware/main/state_machine.c`) performs thermal runaway detection only in two narrow contexts: (1) a preheat timeout at line 540–543 that trips `FAULT_THERMAL_RUNAWAY → STATE_FAULT`, and (2) a `current_temp > target + 10°C` check at line 666–670 within `state_heating_update()` that trips the same path. Both are state-local (only PREHEAT and HEATING), neither checks rate-of-rise, and both route to `STATE_FAULT` which is reset-clearable. The `trigger_hardware_shutdown()` path at `state_machine.c:889–891` only fires when already in `STATE_FAULT` and heatsink exceeds 125°C—it is a secondary failsafe, not a primary interlock.

This plan adds: a dedicated `STATE_RUNAWAY_FAULT` and `FAULT_RUNAWAY_BOUNDARY` to the X-macro lists in `state_machine.h`; a `check_runaway_boundary()` function invoked at the top of `state_machine_update()` before the per-state dispatch; two new float fields (`max_absolute_temp_c`, `max_temp_rise_rate_c_per_s`) in `config.yaml` under a new `runaway` config group; hardware-GPIO-driven power cut that gates the IGBT driver disable line independently of software PWM; and a latching interlock flag that blocks all state transitions until power-cycle.

---

## Problem Frame

### 1. The existing thermal runaway protection is state-local and reset-clearable

| # | Site | What it checks | Limitation |
|---|------|---------------|------------|
| 1 | `firmware/main/state_machine.c:540–543` | `state_duration > MAX_PREHEAT_TIME_MS` | Only in STATE_PREHEAT; timeout-based, not temperature-rate-based |
| 2 | `firmware/main/state_machine.c:666–670` | `current_temp > target + 10°C` | Only in STATE_HEATING; threshold-based, no rate-of-rise check |
| 3 | `firmware/main/state_machine.c:939–944` | `read_heatsink_temperature() > 100°C` | Checks heatsink (NTC), not pan/coil (RTD); calls `check_safety_interlocks()` only from PREHEAT and HEATING state updates |
| 4 | `firmware/main/state_machine.c:889–891` | `read_heatsink_temperature() > 125°C` → `trigger_hardware_shutdown()` | Only when already in STATE_FAULT; hardcoded 125°C threshold |

All four paths route to `STATE_FAULT`. Per `state_fault_update()` at line 866–895, `STATE_FAULT` can be exited via `BUTTON_RESET` if `fault_cleared()` returns true (line 874). A user can reset and re-enter a heating state after a thermal runaway event without a power-cycle—the fault is not latched.

### 2. No rate-of-rise check exists in the state machine

The NTC guard at `firmware/components/safety/ntc_guard.c:64–73` performs a rate-of-change check on the heatsink thermistor (max `10.0°C/s`, hardcoded at `ntc_guard.h:30`), but this is a per-sensor validation that rejects individual readings—it does not trip a fault state. The state machine itself never compares consecutive pan temperature readings to detect a runaway rate of rise. A pan heating at 8°C/s toward 280°C while the target is 180°C would pass the `target + 10°C` check until 190°C is reached, by which point thermal inertia may already make the pan unrecoverable.

### 3. The hardware shutdown path is secondary, not primary

`trigger_hardware_shutdown()` at `firmware/components/safety/safety.c:435–442` disables PWM outputs via `pwm_disable_all()` and `power_set_level(0)`—both are **software-mediated** paths through the ESP32's PWM peripheral. If the firmware is in a state where PWM peripherals are not responding (lockup, silicon bug), this shutdown may not execute. The external hardware watchdog (TPS3823-33) at `safety.c:457–497` provides independent MCU-lockup protection with a 1.6s timeout, but that is a last-resort reset, not a sub-millisecond power cut.

The hardware interlock design at `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` Section 2 describes a hardware OR gate that combines OCP, OVP, NTC thermal shutdown (85°C comparator), and TPS3823 RESET into a single gate-driver disable signal. There is no firmware-driven input to this OR gate today—the ESP32 cannot directly assert the gate-driver disable line from software.

### 4. Configurable runaway thresholds do not exist

`firmware/config.yaml` currently declares `temperatures` (3 entries), `timeouts` (8 entries), `thresholds` (8 entries), and `misc` (1 entry). None of these cover a pan/coil absolute temperature ceiling or a rate-of-rise limit. The `fan_max_temp_rise_rate_c_per_s` (5.0°C/s, `config.h:100`) is for the fan guard, and `ntc_guard.h:30` hardcodes `NTC_MAX_RATE_C_PER_SEC 10.0f` for the heatsink—neither applies to the pan/coil RTD path.

---

## Scope Boundaries

### In scope

- **R1**: Add `check_runaway_boundary()` invoked at the top of `state_machine_update()` (before the message-pending early-return and before the per-state dispatch switch), reading pan temperature and comparing against two configurable thresholds on every control loop iteration.
- **R2**: The interlock disables the power stage via a dedicated GPIO output pin (`RUNAWAY_CUT_GPIO`) that feeds the hardware OR gate described in `SAFETY_INTERLOCK_DESIGN.md` Section 2. This cuts power independently of software PWM—the GPIO drives the gate-driver disable signal directly through the OR gate. The pin is configured as push-pull output, latched HIGH on runaway breach, and **never cleared except by power-cycle** (the GPIO is initialized LOW during `watchdog_hardware_init()` at boot, and only the runaway interlock can raise it).
- **R3**: Add `STATE_RUNAWAY_FAULT` to `STATE_LIST` and `FAULT_RUNAWAY_BOUNDARY` to `FAULT_LIST` in `state_machine.h`. `STATE_RUNAWAY_FAULT` has a no-op update function (power stays off, no button processing) and **no exit transition** except power-cycle. A `runaway_latched` flag in `sm_ctx` blocks the `transition_to()` function from entering any non-fault state once set.
- **R4**: Add a `runaway` config group to `firmware/config.yaml` with `max_absolute_temp_c` (float, default 300.0°C) and `max_temp_rise_rate_c_per_s` (float, default 15.0°C/s), each with `c_type: float`, `env_var`, and `doc`. Regenerate `firmware/config.h` via `python3 firmware/tools/gen_config.py` to emit the struct, initializer, legacy `#define`s, and env-var documentation.
- Wire `check_runaway_boundary()` call sites to use `g_config.runaway.max_absolute_temp_c` and `g_config.runaway.max_temp_rise_rate_c_per_s` (not hardcoded constants).
- Add a host test in `firmware/test/test_state_machine.c` covering: breach by absolute temp, breach by rate-of-rise, non-breach normal operation, and power-cycle-required latching behavior.
- Extend the SIL fault injection test in `firmware/test/test_sil_fault_injection.c` to cover the new `FAULT_RUNAWAY_BOUNDARY` code.
- Update the transition table in `firmware/test/gen_transition_table.py` to include two new *state-free* transitions (any-state → `STATE_RUNAWAY_FAULT` on boundary breach) and regenerate `firmware/test/test_transition_table_generated.c`.

### Deferred

- **Board-level OR gate wiring verification.** The plan assumes GPIO assignment of `RUNAWAY_CUT_GPIO` (proposed: `GPIO_NUM_5`, the next available GPIO after `WDI_GPIO_NUM 4` and `WDT_RESET_GPIO_NUM 6` in `safety.c:53–54`) and that the PCB has a trace from this GPIO to the OR gate input. Actual PCB routing and BOM confirmation is a hardware task.
- **NTC sensor rate-of-rise unification.** `fan_guard.h:23` defines `FAN_MAX_TEMP_RISE_RATE_C_PER_S 0.5f` (fan guard) and `ntc_guard.h:30` defines `NTC_MAX_RATE_C_PER_SEC 10.0f` (NTC guard). These remain independent constants. Unifying all rate limits under a single config group is a separate ticket (tracked as `FAN_MAX_TEMP_RISE_RATE_C_PER_S` unification in plan `008`).
- **Runaway-specific LED pattern.** The plan uses `LED_FAULT` for `STATE_RUNAWAY_FAULT` (same as `STATE_FAULT`). A distinct LED pattern (e.g., continuous red with no blink) is a UX refinement.
- **Persistent runaway counter in NVS.** Recording how many runaway events have occurred across power-cycles for service diagnostics is out of scope.

### Out of scope

- Changes to the hardware OR gate circuit or PCB layout.
- Replacing `trigger_hardware_shutdown()` with the new GPIO path—the existing secondary failsafe at `state_machine.c:889–891` remains as a defense-in-depth layer.
- Modifying the NTC guard's rate-of-change hardcoded constant (`ntc_guard.h:30`).
- Adding `FAULT_RUNAWAY_BOUNDARY` clearing logic—by definition, this fault cannot be cleared by software.

---

## Key Technical Decisions

**1. Interlock runs before ALL state-specific logic, including message-pending early-return.** The current `state_machine_update()` at `state_machine.c:207–263` has a message-pending early-return at line 221–229 that skips state update logic while a message is displayed. The runaway check must fire *before* this early-return—if temperature is breaching a boundary, a "COMPLETE" or "NO PAN" message must not delay the power cut. The check is therefore placed immediately after `watchdog_hardware_feed()` at line 218 and before the `message_pending` check at line 221. This satisfies R1's "regardless of current state" requirement.

**2. Dedicated GPIO for hardware-level power cut, not software PWM disable.** `trigger_hardware_shutdown()` at `safety.c:435–442` disables power by calling `pwm_disable_all()` and `power_set_level(0)`—software functions that write PWM peripheral registers. If the ESP32 is in a state where the PWM peripheral is unresponsive, this path fails. The runaway interlock instead asserts a dedicated GPIO (`RUNAWAY_CUT_GPIO`, proposed GPIO5) that connects to the hardware OR gate (per `SAFETY_INTERLOCK_DESIGN.md` Section 2 block diagram). This GPIO is:

- Configured as push-pull output, initialized LOW in `watchdog_hardware_init()` (expanded from `safety.c:457–487`).
- Set HIGH by `check_runaway_boundary()` on breach detection.
- **Never cleared by software.** The GPIO stays HIGH through any reset, fault recovery, or state transition. Only a physical power-cycle (MCU reset clears all GPIOs to input/high-impedance) releases the latch. This is the hardware manifestation of R2 ("non-software-overridable").

The existing `trigger_hardware_shutdown()` is also called for defense-in-depth—the GPIO cuts the gate driver hardware path; the software PWM disable cuts the firmware path. Both fire on runaway.

**3. `STATE_RUNAWAY_FAULT` is a dead-end state with no exit transitions.** The state update function (`state_runaway_fault_update()`) does nothing: no button reads, no temperature monitoring, no watchdog changes. Power is already cut by the GPIO latch. The entry function calls `trigger_hardware_shutdown()` and asserts the GPIO. The `transition_to()` function at line 901 gains a guard:

```c
if (sm_ctx.runaway_latched && new_state != STATE_RUNAWAY_FAULT) {
    return;  // Block all transitions away from runaway
}
```

Once `runaway_latched` is set true, the only way to leave `STATE_RUNAWAY_FAULT` is a full power-cycle that resets `sm_ctx` to its default initializer (which has `runaway_latched = false`). This satisfies R3.

The existing `FAULT_THERMAL_RUNAWAY` fault code (line 68 in `state_machine.h`) remains for the less-severe cases (preheat timeout, `target + 10°C` in HEATING) that are validly reset-clearable. `FAULT_RUNAWAY_BOUNDARY` is the new, latched code for the absolute/rate boundary breach. The distinction is documented in the fault list comment.

**4. The `FAULT_RUNAWAY_BOUNDARY` is placed after `FAULT_OVER_CURRENT` in `FAULT_LIST`** to group safety-critical latched faults near the top while preserving existing enum value stability (tests reference existing fault codes by integer value in transition tables). Insertion at position 4 (index 3) shifts `FAULT_FAN_FAILURE` and all subsequent codes by one. The transition table generator and all fault-code-aware tests are regenerated in the same commit to keep integer values consistent.

**5. Rate-of-rise is computed from consecutive `read_pan_temperature()` calls stored in `sm_ctx`.** Two new fields are added to `sm_ctx`:
- `float last_pan_temp_c` — stored at the end of each `check_runaway_boundary()` call.
- `uint32_t last_pan_temp_time_ms` — stored alongside it.

The rate check requires at least one prior reading (`last_pan_temp_time_ms > 0`). On the very first loop iteration after init, the rate check is skipped and the absolute-temperature check proceeds alone. NaN/infinite temperature values trigger the interlock immediately (sensor failure is a safety event).

Delta-time for rate computation uses the same `get_time_ms()` source as the state duration counter. If the delta is less than 10ms (faster than the control loop's expected ~10ms period), the rate check is skipped to avoid amplifying sensor noise.

**6. Config manifest: new `runaway` group with two fields.** Following the existing pattern from `firmware/config.yaml`, the new group is:

```yaml
runaway:
  - c_symbol: RUNAWAY_MAX_ABSOLUTE_TEMP_C
    field: max_absolute_temp_c
    value: 300.0
    c_type: float
    units: "°C"
    env_var: RUNAWAY_MAX_ABSOLUTE_TEMP_C
    doc: "Maximum absolute pan temperature before runaway interlock triggers"

  - c_symbol: RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S
    field: max_temp_rise_rate_c_per_s
    value: 15.0
    c_type: float
    units: "°C/s"
    env_var: RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S
    doc: "Maximum pan temperature rise rate before runaway interlock triggers"
```

Defaults are conservative: 300°C absolute (above MAX_TEMP of 250°C, but below common cookware thermal limits) and 15°C/s rise rate (above the NTC guard's 10°C/s for the heatsink, accounting for pan thermal mass being lower than heatsink mass). These are tuning starting points, not safety-validated values—the plan provides the mechanism; validating the thresholds against IEC 60335-2-9 is a separate compliance activity.

The generated `firmware/config.h` gains:
- A `runaway_t` struct with `float max_absolute_temp_c` and `float max_temp_rise_rate_c_per_s`.
- A `RUNAWAY_DEFAULT` initializer macro.
- A `runaway_t runaway` field in `config_t` (at `config.h:121–125`).
- Two legacy `#define`s (`RUNAWAY_MAX_ABSOLUTE_TEMP_C`, `RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S`).
- Env-var loading in `config_set_from_env()` (manually added to `config.c`), validation in `config_validate()` (range: 0–500°C, 0–100°C/s), and `config_print()` output.

**7. The transition table gains two "free" transitions (any source state → STATE_RUNAWAY_FAULT).** The existing transition table at `firmware/test/gen_transition_table.py:34–60` defines per-source-state transitions. The runaway interlock is state-independent, so two new entries are added with a special `*` source-state notation:

```python
("*", "RUNAWAY_ABSOLUTE_TEMP", "STATE_RUNAWAY_FAULT", "FAULT_RUNAWAY_BOUNDARY", False),
("*", "RUNAWAY_RISE_RATE", "STATE_RUNAWAY_FAULT", "FAULT_RUNAWAY_BOUNDARY", False),
```

The `gen_transition_table.py` generator and the C test runner `test_transition_table_generated.c` are extended to understand `*` as "apply this transition to every power-active state" (excludes STATE_INIT, STATE_RUNAWAY_FAULT itself). This is a minor extension to the generator, not a rewrite.

---

## Implementation Units

### U1. Add `STATE_RUNAWAY_FAULT` and `FAULT_RUNAWAY_BOUNDARY` to X-macro lists

**Goal:** The `STATE_LIST` and `FAULT_LIST` X-macros in `state_machine.h` gain new entries. The dispatch switches and entry-function forward declarations in `state_machine.c` gain corresponding cases. The string tables expand automatically.

**Requirements:** R3

**Dependencies:** None

**Files:**
- `firmware/main/state_machine.h` (add `X(STATE_RUNAWAY_FAULT, "RUNAWAY_FAULT")` after `X(STATE_FAULT, "FAULT")` at line 38; add `X(FAULT_RUNAWAY_BOUNDARY, "RUNAWAY BOUNDARY")` at FAULT_LIST position 3, after `X(FAULT_OVER_CURRENT, "OVER CURRENT")` at line 64)
- `firmware/main/state_machine.c`:
  - Add `static void state_runaway_fault_entry(void);` and `static void state_runaway_fault_update(void);` to the forward declaration block (after line 93).
  - Add `case STATE_RUNAWAY_FAULT: state_runaway_fault_update(); break;` to the update dispatch switch (after line 257).
  - Add `case STATE_RUNAWAY_FAULT: state_runaway_fault_entry(); break;` to the `transition_to()` dispatch switch (after line 929).
  - Implement `state_runaway_fault_entry()` and `state_runaway_fault_update()` as stub functions (entry: call `trigger_hardware_shutdown()`, set `LED_FAULT`, display `"RUNAWAY"`, log to EEPROM, set WDT to 5000ms; update: no-op).
  - Add `sm_ctx.runaway_latched = false;` to the initializer at line 69 (default false).
  - Add `bool runaway_latched;` to the `sm_ctx` struct (after `thermal_mass_estimation_done` at line 66).
  - Add `sm_ctx.runaway_latched = false;` to `state_machine_init()` reset block (after line 194).

**Approach:**
The new state and fault follow the exact X-macro pattern established in plan `008` U1. Adding `X(STATE_RUNAWAY_FAULT, "RUNAWAY_FAULT")` to `STATE_LIST` automatically creates the enum value (which becomes `STATE_COUNT` sentinel predecessor), expands the `state_name_table[]` array, and increments `STATE_COUNT` from 9 to 10 (STATE_COUNT already equals 9 because there are 8 states + sentinel; adding one makes it 10). Adding `FAULT_RUNAWAY_BOUNDARY` at position 3 in `FAULT_LIST` shifts all subsequent fault enum values by +1—this is intentional and all dependent test code regenerates in U6.

`FAULT_RUNAWAY_BOUNDARY` is placed between `FAULT_OVER_CURRENT` and `FAULT_FAN_FAILURE` to group it with the safety-critical faults near the list head. The `fault_cleared()` function at line 975 adds `case FAULT_RUNAWAY_BOUNDARY: return false;` (never clearable).

**Verification:** `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build` compiles. `ctest --test-dir firmware/test/build -R state_machine` passes (existing tests reference `STATE_COUNT` via the generated enum, `FAULT_COUNT` matches the expanded list, string tables include the new entries).

---

### U2. Implement `check_runaway_boundary()` with GPIO hardware cut

**Goal:** A `check_runaway_boundary()` function that reads pan/coil temperature, computes rate-of-rise from the previous reading, compares against `g_config.runaway.*` thresholds, and on breach: asserts `RUNAWAY_CUT_GPIO` HIGH, calls `trigger_hardware_shutdown()`, sets `runaway_latched = true`, sets `sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY`, and transitions to `STATE_RUNAWAY_FAULT`. The function is called at the top of `state_machine_update()` before any other logic.

**Requirements:** R1, R2

**Dependencies:** U1 (STATE_RUNAWAY_FAULT and FAULT_RUNAWAY_BOUNDARY must exist)

**Files:**
- `firmware/main/state_machine.c`:
  - Add `#include "driver/gpio.h"` (ESP_PLATFORM guard) near line 18.
  - Add `#define RUNAWAY_CUT_GPIO GPIO_NUM_5` (ESP_PLATFORM guard, near the existing WDI_GPIO_NUM at `safety.c:53` pattern—but in `state_machine.c` since the interlock lives here).
  - Add forward declaration `static void check_runaway_boundary(void);` (after the helper declarations at line 96).
  - Add two new fields to `sm_ctx`: `float last_pan_temp_c;` (initialized `0.0f`) and `uint32_t last_pan_temp_time_ms;` (initialized `0`), after the `runaway_latched` field.
  - Insert the `check_runaway_boundary()` call at line 218 of `state_machine_update()`, after `watchdog_hardware_feed()` and before the `message_pending` check.
  - Implement the function body.
  - Add `#ifndef ESP_PLATFORM` guard around `RUNAWAY_CUT_GPIO` definition for host test builds.

**Approach:**

```c
static void check_runaway_boundary(void) {
    /* If already latched, nothing to check */
    if (sm_ctx.runaway_latched) return;

    float temp = read_pan_temperature();
    uint32_t now = get_time_ms();

    /* NaN/infinite temperature → immediate breach */
    if (!isfinite(temp)) {
        goto trigger_runaway;
    }

    /* Absolute temperature check */
    if (temp > g_config.runaway.max_absolute_temp_c) {
        sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY;
        goto trigger_runaway;
    }

    /* Rate-of-rise check (requires at least one prior reading) */
    if (sm_ctx.last_pan_temp_time_ms > 0) {
        uint32_t dt_ms = now - sm_ctx.last_pan_temp_time_ms;
        if (dt_ms >= 10) {  /* Minimum 10ms to avoid noise amplification */
            float dt_s = dt_ms / 1000.0f;
            float rate = (temp - sm_ctx.last_pan_temp_c) / dt_s;
            if (rate > g_config.runaway.max_temp_rise_rate_c_per_s) {
                sm_ctx.fault_code = FAULT_RUNAWAY_BOUNDARY;
                goto trigger_runaway;
            }
        }
    }

    /* Store for next iteration */
    sm_ctx.last_pan_temp_c = temp;
    sm_ctx.last_pan_temp_time_ms = now;
    return;

trigger_runaway:
    /* Hardware-level cut: assert GPIO to OR gate */
#ifdef ESP_PLATFORM
    gpio_set_level(RUNAWAY_CUT_GPIO, 1);
#endif
    /* Software-level cut: disable PWM and power */
    trigger_hardware_shutdown();

    sm_ctx.runaway_latched = true;
    transition_to(STATE_RUNAWAY_FAULT);
}
```

The `goto` pattern mirrors the existing `check_safety_interlocks()` at `state_machine.c:939–973` which uses early-return-after-transition and is the established style.

The GPIO assertion (`gpio_set_level(RUNAWAY_CUT_GPIO, 1)`) drives the hardware OR gate input HIGH. Per `SAFETY_INTERLOCK_DESIGN.md` Section 2, the OR gate output connects to the UCC21550 gate driver DISABLE pin. A HIGH at any OR gate input disables the gate driver. The GPIO stays HIGH through any MCU state (including resets), only a power-cycle clears it.

**Note on GPIO initialization:** The `RUNAWAY_CUT_GPIO` must be configured as output LOW during startup. The natural place is `watchdog_hardware_init()` at `safety.c:457–487`, which already configures `WDI_GPIO_NUM` and `WDT_RESET_GPIO_NUM`. An additional GPIO config block for `RUNAWAY_CUT_GPIO` is added there, or alternatively in a new `runaway_gpio_init()` called from `state_machine_init()`. The plan adds it to `watchdog_hardware_init()` for co-location with the other safety GPIOs.

**Verification:** Host test build compiles with the `#ifdef ESP_PLATFORM` guards stubbing out `gpio_set_level`. `ctest` passes existing tests (the runaway check fires before the state update, but since `last_pan_temp_time_ms == 0` on the first loop iteration after init, the rate check is skipped and test temperatures remain within defaults).

---

### U3. Add `runaway_latched` guard to `transition_to()`

**Goal:** Once `runaway_latched` is set, `transition_to()` blocks all transitions except into `STATE_RUNAWAY_FAULT` itself. This prevents any code path (including the `show_message_then_transition` mechanism) from leaving the runaway state.

**Requirements:** R3

**Dependencies:** U1 (STATE_RUNAWAY_FAULT exists), U2 (runaway_latched is set)

**Files:**
- `firmware/main/state_machine.c` (add the guard at the top of `transition_to()` at line 901)

**Approach:**

At line 901, immediately after the function signature and before the `if (sm_ctx.current_state == STATE_HEATING)` block, add:

```c
    /* Runaway interlock: block all transitions once latched */
    if (sm_ctx.runaway_latched && new_state != STATE_RUNAWAY_FAULT) {
        return;
    }
```

This is the only code change in this unit. The guard is placed before any existing logic so it catches transitions from all sources: direct `transition_to()` calls, `show_message_then_transition()` (which calls `transition_to()` at line 224 after the message delay), and `state_machine_force_state()` (which calls `transition_to()` at line 309).

**Verification:** A test in U5 sends a temperature above `max_absolute_temp_c`, verifies `STATE_RUNAWAY_FAULT` is entered, then calls `state_machine_force_state(STATE_IDLE)` and verifies the state remains `STATE_RUNAWAY_FAULT`.

---

### U4. Extend `firmware/config.yaml` with `runaway` group and regenerate `config.h`

**Goal:** Two new configurable thresholds under a `runaway` group in the manifest, with full codegen support matching the existing pattern.

**Requirements:** R4

**Dependencies:** None (manifest edit is independent; regeneration depends on U1/U2 needing the symbols)

**Files:**
- `firmware/config.yaml` (add the `runaway` group after the `misc` group at line 163)
- `firmware/tools/gen_config.py` (extend to handle the new `runaway` group—if the script is data-driven from the YAML structure, this may require no Python changes; if it has hardcoded group names, add `runaway`)
- `firmware/tools/config.h.j2` (add template blocks for the `runaway` group struct, `RUNAWAY_DEFAULT` initializer, `config_t` aggregate field, legacy `#define`s, env-var docs)
- `firmware/config.h` (regenerated)
- `firmware/config.c` (add runaway defaults loading to `config_init()` at line 27, `config_load_defaults()` at line 38, env-var loading to `config_set_from_env()` at line 49, validation to `config_validate()` at line 151, and output to `config_print()` at line 229)
- `firmware/tools/check_config_matches_manifest.py` (verify the new group is checked, or confirm it's data-driven)

**Approach:**

Add to `firmware/config.yaml` after the `misc` group:

```yaml
runaway:
  - c_symbol: RUNAWAY_MAX_ABSOLUTE_TEMP_C
    field: max_absolute_temp_c
    value: 300.0
    c_type: float
    units: "°C"
    env_var: RUNAWAY_MAX_ABSOLUTE_TEMP_C
    doc: "Maximum absolute pan temperature before runaway interlock triggers"

  - c_symbol: RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S
    field: max_temp_rise_rate_c_per_s
    value: 15.0
    c_type: float
    units: "°C/s"
    env_var: RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S
    doc: "Maximum pan temperature rise rate before runaway interlock triggers"
```

If `gen_config.py` and `config.h.j2` are data-driven (iterating over top-level YAML keys as groups), no script changes are needed—the `runaway` group is automatically discovered, templated, and emitted. If they hardcode `temperatures`, `timeouts`, `thresholds`, `misc`, extend them to include `runaway`.

Manually add to `config.c`:
- In `config_init()` (after line 35): `g_config.runaway = (runaway_t)RUNAWAY_DEFAULT;`
- In `config_load_defaults()` (after line 46): same line.
- In `config_set_from_env()` (after line 148): env-var loading for `RUNAWAY_MAX_ABSOLUTE_TEMP_C` and `RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S`.
- In `config_validate()` (after line 221): validate range `0.0f < max_absolute_temp_c <= 500.0f` and `0.0f <= max_temp_rise_rate_c_per_s <= 100.0f`.
- In `config_print()` (after line 265): print the two new values.

**Verification:** `python3 firmware/tools/gen_config.py` produces updated `config.h` with the new struct/initializer/defines. `python3 firmware/tools/check_config_matches_manifest.py` exits 0. `cmake --build firmware/test/build` compiles `state_machine.c` with `#include "config.h"` resolving the new symbols.

---

### U5. Write host tests for the runaway interlock

**Goal:** C tests in `firmware/test/test_state_machine.c` verifying the four scenarios: absolute temp breach, rate-of-rise breach, non-breach normal operation, and latch-after-breach behavior. SIL fault injection test extended.

**Requirements:** R1, R2, R3, R4 (validation)

**Dependencies:** U1–U4

**Files:**
- `firmware/test/test_state_machine.c` (add 4 test functions)
- `firmware/test/test_main_state_machine.c` (register the new tests with `RUN_TEST`)
- `firmware/test/test_sil_fault_injection.c` (add `FAULT_RUNAWAY_BOUNDARY` to the fault code string-to-enum mapping at line ~88)
- `firmware/test/state_machine_stubs.c` (add call counter for `trigger_hardware_shutdown` when triggered from runaway—already exists at line 406)

**Test 1: `test_sm_runaway_absolute_temp`**
- Initialize state machine, start profile to enter PAN_DET.
- Set pan temperature to `301.0°C` (above default 300.0°C threshold).
- Call `state_machine_update()`.
- Assert `state_machine_get_state() == STATE_RUNAWAY_FAULT`.
- Assert `state_machine_get_fault() == FAULT_RUNAWAY_BOUNDARY`.

**Test 2: `test_sm_runaway_rate_of_rise`**
- Initialize, start profile, enter PAN_DET.
- Set pan temperature to `30.0°C`, call update (establishes baseline).
- Set pan temperature to `200.0°C`, ensuring mock time delta is `100ms` (rate = 1700°C/s, far above 15°C/s).
- Call `state_machine_update()`.
- Assert `STATE_RUNAWAY_FAULT` and `FAULT_RUNAWAY_BOUNDARY`.

**Test 3: `test_sm_runaway_no_breach_normal_operation`**
- Initialize, start profile, enter HEATING.
- Set pan temperature to `100.0°C`, call update, assert still HEATING.
- Set pan temperature to `101.0°C`, call update (rate = 1°C/10ms = 100°C/s? Need to adjust mock time).
- With mock time advancing at 100ms per call, `1°C / 0.1s = 10°C/s` < 15°C/s threshold.
- Assert still HEATING (no false positive).

**Test 4: `test_sm_runaway_latch_blocks_transition`**
- Trigger runaway (set temp > 300°C, call update).
- Assert `STATE_RUNAWAY_FAULT`.
- Call `state_machine_force_state(STATE_IDLE)`.
- Assert still `STATE_RUNAWAY_FAULT` (latch guard working).

**SIL fault injection extension:**
- Add `if (!strcmp(str, "FAULT_RUNAWAY_BOUNDARY")) return FAULT_RUNAWAY_BOUNDARY;` to the parse function at `test_sil_fault_injection.c:88`.

**Verification:** `ctest --test-dir firmware/test/build -R "runaway" --output-on-failure` passes all 4 tests. `ctest --test-dir firmware/test/build -R "sil" --output-on-failure` passes (the new fault code is parseable).

---

### U6. Regenerate transition table with runaway transitions

**Goal:** `gen_transition_table.py` and `test_transition_table_generated.c` include the two wildcard transitions for runaway boundary breach, and the regenerated C file passes all transition tests.

**Requirements:** R1, R3 (validation via generated tests)

**Dependencies:** U1 (STATE_RUNAWAY_FAULT and FAULT_RUNAWAY_BOUNDARY enum values)

**Files:**
- `firmware/test/gen_transition_table.py` (add the two wildcard transitions; extend the transition application logic to handle `*` source state by injecting the transition into every active state)
- `firmware/test/test_transition_table_generated.c` (regenerated)

**Approach:**

In `gen_transition_table.py`, add to the transition list after the existing STATE_HEATING transitions:

```python
# Wildcard transitions (apply to all active states)
("*", "RUNAWAY_ABSOLUTE_TEMP", "STATE_RUNAWAY_FAULT", "FAULT_RUNAWAY_BOUNDARY", False),
("*", "RUNAWAY_RISE_RATE", "STATE_RUNAWAY_FAULT", "FAULT_RUNAWAY_BOUNDARY", False),
```

Add to the event-to-setup mapping:

```python
"RUNAWAY_ABSOLUTE_TEMP": "mock_sm_set_pan_temperature(310.0f);",
"RUNAWAY_RISE_RATE": "mock_sm_set_pan_temperature(200.0f);",
```

The generator's `generate_transitions()` function is extended: when iterating over transitions, if `source_state == "*"`, apply the transition entry to every state in `ACTIVE_STATES` (currently defined as `[STATE_PAN_DET, STATE_PREHEAT, STATE_HEATING, STATE_NO_PAN, STATE_COOLDOWN]`—excluding `STATE_INIT`, `STATE_IDLE`, `STATE_FAULT`, and `STATE_RUNAWAY_FAULT`).

Run `python3 firmware/test/gen_transition_table.py --generate` to produce the updated C file.

**Verification:** `cmake --build firmware/test/build && ctest --test-dir firmware/test/build -R transition` passes all generated transition tests including the two new wildcard transitions.

---

### U7. Add GPIO initialization for `RUNAWAY_CUT_GPIO`

**Goal:** The `RUNAWAY_CUT_GPIO` is configured as push-pull output LOW at system startup, co-located with the other hardware safety GPIOs in `watchdog_hardware_init()`.

**Requirements:** R2

**Dependencies:** U2 (GPIO is defined and used)

**Files:**
- `firmware/components/safety/safety.c` (add GPIO config for `RUNAWAY_CUT_GPIO` in `watchdog_hardware_init()` at lines 457–487)

**Approach:**

In `watchdog_hardware_init()` at `safety.c:457`, after the `WDI_GPIO_NUM` configuration block (lines 459–468) and before the `WDT_RESET_GPIO_NUM` configuration block (lines 470–478), add:

```c
/* Configure RUNAWAY_CUT_GPIO output (active HIGH cuts power via OR gate) */
gpio_config_t runaway_cut_conf = {
    .pin_bit_mask = (1ULL << RUNAWAY_CUT_GPIO),
    .mode = GPIO_MODE_OUTPUT,
    .pull_up_en = GPIO_PULLUP_DISABLE,
    .pull_down_en = GPIO_PULLDOWN_ENABLE,  /* Default LOW = power ON */
    .intr_type = GPIO_INTR_DISABLE,
};
ESP_ERROR_CHECK(gpio_config(&runaway_cut_conf));
gpio_set_level(RUNAWAY_CUT_GPIO, 0);
```

Add `#define RUNAWAY_CUT_GPIO GPIO_NUM_5` alongside the other GPIO definitions at `safety.c:53–54`.

Add `extern` declaration or `#include` guard so `state_machine.c` can reference `RUNAWAY_CUT_GPIO` (or define it once in a shared header). The simplest approach: move the `#define` to `safety.h` (public header) so both `safety.c` and `state_machine.c` can use it.

**Verification:** Build compiles. On hardware, GPIO5 is LOW at boot and stays LOW during normal operation. On a runaway breach, GPIO5 goes HIGH and stays HIGH.

---

### U8. Update `AGENTS.md` with regenerate instructions

**Goal:** The `AGENTS.md` "Firmware Config Codegen" section (added in plan `008` U6) already documents the `gen_config.py` + commit workflow. An additional line documents the transition table regeneration.

**Requirements:** Developer workflow

**Dependencies:** U6

**Files:**
- `AGENTS.md` (add a subsection under the existing firmware config section)

**Approach:**

After the existing firmware config codegen block, add:

```
### Transition Table Regeneration

`firmware/test/test_transition_table_generated.c` is generated from the
transition table in `firmware/test/gen_transition_table.py`. After editing
the table:

    python3 firmware/test/gen_transition_table.py --generate
    git add firmware/test/test_transition_table_generated.c
    git commit -m "test: regenerate transition table tests"

CI regenerates and `git diff --exit-code`s against the committed copy.
```

---

## System-Wide Impact

- **`firmware/main/state_machine.h`:** Two new X-macro entries in `STATE_LIST` and `FAULT_LIST`. `STATE_COUNT` increments from 9 to 10. `FAULT_COUNT` increments from 12 to 13. All consumers of these sentinels (string-table walks, test loops) adjust automatically.
- **`firmware/main/state_machine.c`:** Gains ~80 lines: `check_runaway_boundary()` function, two stub entry/update functions for `STATE_RUNAWAY_FAULT`, a `runaway_latched` guard in `transition_to()`, two new fields in `sm_ctx`, the interlock call site at the top of `state_machine_update()`. The message-pending early-return block (lines 221–229) is now *after* the interlock, not before—this is a behavioral change: runaway detection fires even during message display.
- **`firmware/config.yaml`:** New `runaway` group with 2 entries (20→22 total entries).
- **`firmware/config.h`:** New `runaway_t` struct, `RUNAWAY_DEFAULT` initializer, `config_t.runaway` field, two legacy `#define`s. Regenerated by `gen_config.py`.
- **`firmware/config.c`:** `config_init()`, `config_load_defaults()`, `config_set_from_env()`, `config_validate()`, and `config_print()` gain runaway entries. ~15 lines added.
- **`firmware/components/safety/safety.h`:** Gains `#define RUNAWAY_CUT_GPIO GPIO_NUM_5` and possibly extern declarations (1 line).
- **`firmware/components/safety/safety.c`:** `watchdog_hardware_init()` gains GPIO configuration for `RUNAWAY_CUT_GPIO` (~10 lines in ESP_PLATFORM block).
- **`firmware/test/test_state_machine.c`:** 4 new test functions (~80 lines).
- **`firmware/test/test_main_state_machine.c`:** 4 new `RUN_TEST` registrations.
- **`firmware/test/test_sil_fault_injection.c`:** 1 new fault code string-to-enum entry.
- **`firmware/test/gen_transition_table.py`:** 2 new wildcard transitions, extended `*` source-state handling (~15 lines).
- **`firmware/test/test_transition_table_generated.c`:** Regenerated (2 new transition entries expanded across ~5 active states = ~10 new test cases).
- **`firmware/tools/gen_config.py` / `config.h.j2`:** May need no changes if data-driven; if hardcoded group list, add `runaway` (~2 lines).
- **`AGENTS.md`:** New "Transition Table Regeneration" subsection (~10 lines).
- **Hardware:** GPIO5 must be routed to an input of the OR gate on the PCB. This is a hardware dependency tracked separately.

---

## Risk Analysis

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| `RUNAWAY_CUT_GPIO` (GPIO5) conflicts with an existing peripheral assignment | High | Low | GPIO5 is not assigned in `safety.c:53–54` (GPIO4 and GPIO6 are used). ESP32-S3 GPIO5 is a general-purpose IO. Verify against the KiCad schematic `pcb/` directory before finalizing the GPIO number. If GPIO5 is in use, pick the next available GPIO from the schematic. |
| The `check_runaway_boundary()` call before `message_pending` early-return causes a disruptive UI experience (message interrupted by fault) | Low | Low | This is intentional. Safety-critical events must preempt UI messages. The fault display (`"RUNAWAY"`) replaces any pending message, which is the correct behavior for a safety interlock. |
| Rate-of-rise false positives due to sensor noise on `read_pan_temperature()` | Medium | Medium | The 10ms minimum delta-time gate (U2) prevents noise amplification at very short intervals. The 15°C/s default is intentionally high—above the expected heating rate of an induction cooker under normal load (~2–5°C/s). A persistent noisy sensor that oscillates by 15°C at 100ms intervals would trigger, but this is a sensor fault that *should* trigger a safety response. |
| `STATE_COUNT` / `FAULT_COUNT` increments break test code that uses hardcoded sentinel values | Low | Low | No test hardcodes `STATE_COUNT` or `FAULT_COUNT` as literal integers. All tests use the enum sentinels. The transition table generator uses symbol names, not integers, and regenerates in U6. |
| Fault code enum value shift (FAULT_RUNAWAY_BOUNDARY inserted at index 3) breaks logged EEPROM data | Low | Low | `eeprom_log_fault()` at `state_machine.c:860` stores the fault code integer. The `FAULT_LIST` is the authoritative ordering. If previously logged fault codes are interpreted by a newer firmware, `FAULT_FAN_FAILURE` (was 3, now 4) would misidentify as `FAULT_RUNAWAY_BOUNDARY`. Mitigation: the fault code insertion point is documented in U1; a firmware version number bump accompanies this change; EEPROM migration is a separate concern tracked outside this plan. |
| `config.h.j2` template does not handle a new top-level group automatically | Medium | Medium | If the Jinja2 template hardcodes group names (`{% for entry in temperatures %}` etc.), adding `runaway` to `config.yaml` will not produce output until the template is updated. The plan explicitly makes this an U4 step. If the template is data-driven (iterates `manifest.items()`), no changes are needed—verify at implementation time. |
| The `*` wildcard transition syntax breaks the existing transition table runner | Low | Low | The `gen_transition_table.py` generator and the C test runner are modified in lockstep (U6). The `*` expansion happens at Python generation time, statically producing per-state transitions in the generated C file. The C runner sees no special syntax—only expanded state-specific entries. |

---

## Test Strategy

### Unit Tests (host, `ctest`)

| Test | File | What it verifies | Requirements |
|------|------|-----------------|-------------|
| `test_sm_runaway_absolute_temp` | `test_state_machine.c` | Pan temp > 300°C → STATE_RUNAWAY_FAULT, FAULT_RUNAWAY_BOUNDARY | R1, R3 |
| `test_sm_runaway_rate_of_rise` | `test_state_machine.c` | Rate > 15°C/s → STATE_RUNAWAY_FAULT | R1, R3 |
| `test_sm_runaway_no_breach_normal_operation` | `test_state_machine.c` | Normal temps/rates → state unchanged | R1 |
| `test_sm_runaway_latch_blocks_transition` | `test_state_machine.c` | After breach, force_state() is blocked | R2, R3 |
| Transition table wildcard entries | `test_transition_table_generated.c` | Every active state transitions to STATE_RUNAWAY_FAULT on both breach events | R1 |
| SIL fault injection parse | `test_sil_fault_injection.c` | `"FAULT_RUNAWAY_BOUNDARY"` string parses to correct enum | R3 |
| Config manifest check | `check_config_matches_manifest.py` | `config.h` `#define`s and struct fields match `config.yaml` | R4 |

### Integration & Verification

- `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build && ctest --test-dir firmware/test/build --output-on-failure` — all tests pass.
- `python3 firmware/tools/gen_config.py && git diff --exit-code firmware/config.h` — header matches manifest.
- `python3 firmware/tools/check_config_matches_manifest.py` — exits 0.
- Manual review: `rg "RUNAWAY" firmware/` confirms the new symbols appear in all expected locations and no hand-written duplicates exist.
- On hardware (ESP32-S3 + PCB): GPIO5 is LOW at boot, stays LOW during normal heating, goes HIGH and stays HIGH after injecting a temp > 300°C via the debug interface. Gate driver disable line asserts within one control loop period (~10ms). Power-cycle restores normal operation.
