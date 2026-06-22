---
title: "feat: Firmware SSOT — Config Codegen + X-Macro State Enum"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-21-firmware-ssot-codegen-requirements.md
---

# feat: Firmware SSOT — Config Codegen + X-Macro State Enum

## Summary

A firmware-only initiative that collapses the Temper induction cooker's three-way configuration duplication into a single YAML manifest rendered through a Jinja2 template into `firmware/config.h`, and replaces the hand-maintained state/fault enums and their twin string-table `switch`es with X-macro lists in `firmware/main/state_machine.h`. Today the nine tunables `SAFE_IDLE_TEMP`, `MAX_TEMP`, `MIN_TEMP`, `PAN_DETECT_TIMEOUT_MS`, `NO_PAN_TIMEOUT_MS`, `PAN_DEBOUNCE_COUNT`, `PAN_CONFIDENCE_REQUIRED`, `MAX_PREHEAT_TIME_MS`, `MESSAGE_DISPLAY_TIME_MS` live as bare `#define`s at `firmware/main/state_machine.c:39-47`, again as the `TEMP_LIMITS_DEFAULT` / `TIMEOUTS_DEFAULT` / `THRESHOLDS_DEFAULT` aggregate initializers in `firmware/config.h:52-112`, and again as the values copied by `config_init()` at `firmware/config.c:27-36`. The 8-state `system_state_t` enum (`firmware/main/state_machine.h:26-35`) is mirrored a third time by the literal-string `switch` in `state_machine_get_state_string` (`state_machine.c:309-321`) and a fourth time by the `fault_code_t` enum (`state_machine.h:40-52`) and its own `state_machine_get_fault_string` switch (`state_machine.c:292-307`).

This plan makes the SSOT claim true by construction in three phases: (1) X-macro the state and fault enums so the enum, the `STATE_COUNT` / `FAULT_COUNT` sentinels, and the string tables expand from one list each; (2) add a firmware-local YAML manifest and a Jinja2 codegen script that emits `firmware/config.h` containing both the legacy `#define` surface *and* the `g_config` struct/initializer defaults, wired into both the ESP-IDF build and the host test build; (3) delete the bare `#define`s from `state_machine.c`, commit the generated header as a versioned derived artifact, and add host tests that assert header-matches-manifest and string-tables-cover-enums.

---

## Problem Frame

The duplication is not theoretical and has already produced documented drift.

**Tunable duplication (three sites, one drift):**

| # | Site | Example | Notes |
|---|------|---------|-------|
| 1 | `firmware/main/state_machine.c:39-47` | `#define SAFE_IDLE_TEMP 50.0f` | Bare `#define`s consumed directly at `:239, :279, :444-445, :452-453, :483, :505, :570, :706, :722-723, :729-730, :761, :852` |
| 2 | `firmware/config.h:52-112` | `.safe_idle_temp = 50.0f` inside `TEMP_LIMITS_DEFAULT` | Same numeric values, never references site 1 |
| 3 | `firmware/config.c:27-36` | `g_config.temperatures = (temperature_limits_t)TEMP_LIMITS_DEFAULT;` | Copies site 2 into `g_config`; the values are not re-stated, but the aggregate is the bridge |
| 4 | `firmware/README.md:154-159` | `MIN_TEMP \| 50°C` | **Drifted** — `state_machine.c:41` says `30°C`; README says `50°C` |

A developer who changes one site has no signal that the others disagree. The header comment at `config.h:16-18` admits the duplication is intentional ("existing code using direct #defines continues to work"), which makes the labor *preserved* on every edit rather than eliminated.

**State-enum duplication (four sites):**

| # | Site | Notes |
|---|------|-------|
| 1 | `firmware/main/state_machine.h:26-35` | `system_state_t` enum, 8 states |
| 2 | `firmware/main/state_machine.c:309-321` | `state_machine_get_state_string` switch, 8 string literals |
| 3 | `firmware/main/state_machine.c:5-14` | File header comment listing the 8 states |
| 4 | `firmware/main/state_machine.h:40-52` + `state_machine.c:292-307` | `fault_code_t` enum + `state_machine_get_fault_string` switch, 11 faults |

Adding a state today requires four coordinated edits; forgetting one produces either a silent `"UNKNOWN"` return (`state_machine.c:319, :305`) or an unhandled `switch` case (the two state-dispatch switches at `state_machine.c:266-275` and `:953-962` have no `default:` and rely on no `-Wswitch` being enabled today — `firmware/test/CMakeLists.txt:18` uses `-Wall -Wextra -Wpedantic` but not `-Wswitch`, and the ESP-IDF build at `firmware/CMakeLists.txt` sets no warning flags).

**Additional context discovered during planning:**

- `firmware/config.h` is currently `#include`d by exactly one translation unit: `firmware/config.c:11`. No other file includes it. `g_config`, `config_init`, `config_validate`, `config_print`, and the access macros at `config.h:184-203` are defined but have no consumer in `firmware/main/` or `firmware/components/` today. The migration in R8 is therefore low-risk: making `state_machine.c` include `config.h` adds a single new include and zero name collisions (the bare `#define`s are removed in the same commit, so the names come from exactly one place).
- `config.h:154` declares `void config_load_from_env(void);` but `config.c:49` defines `void config_set_from_env(void)` — a pre-existing header/implementation mismatch. The env-var plumbing (`config.c:49-149`) is out of scope per the origin doc, but the codegen in U5 emits the header and therefore must emit a declaration matching the existing implementation name `config_set_from_env`, not the currently-declared `config_load_from_env`. This is a one-line fix in the generated header and resolves the latent mismatch as a side effect.
- `firmware/components/safety/include/fan_guard.h:23` defines `FAN_MAX_TEMP_RISE_RATE_C_PER_S 0.5f`, which **collides by name** with the `g_config.thresholds.fan_max_temp_rise_rate_c_per_s` field (default `5.0f` at `config.h:111`). `fan_guard.c:72-73` uses the `0.5f` macro directly. This is an existing independent duplication, not introduced by N8. The manifest in U4 will declare only the nine tunables listed in the origin doc; `FAN_MAX_TEMP_RISE_RATE_C_PER_S` stays in `fan_guard.h` and is explicitly out of scope (see Scope Boundaries).
- No `.github/workflows/` job builds firmware or runs `ctest` today. `.github/workflows/python-tests.yml` runs only Python tests. R7's CI regenerate-and-diff step therefore requires a **new** firmware CI job, not an extension of an existing one.
- `firmware/tools/` does not exist today; U5 creates it. No firmware-local `requirements.txt` exists; U5 creates one declaring `jinja2` + `pyyaml`.

---

## Scope Boundaries

### In scope

- R1–R10 from the origin requirements document: the X-macro state and fault enums (R1–R3), the YAML manifest + Jinja2 codegen emitting `firmware/config.h` (R4–R6), committing the generated header with a CI regenerate-and-diff gate (R7), deleting the bare `#define`s from `state_machine.c` and migrating call sites to `#include "config.h"` (R8), and the two host tests for header-matches-manifest and string-table-coverage (R9–R10).
- Resolving the `config_load_from_env` / `config_set_from_env` declaration mismatch as a side effect of generating the header (U5).
- Adding the `default:` fault-handler arms to the two state-dispatch switches in `state_machine.c` (`:266-275` and `:953-962`) per R3.

### Deferred

- **Generating `g_config` runtime-override plumbing from the manifest.** `config_set_from_env` (`config.c:49-149`) keeps its hand-written env-var switch. Only the `*_DEFAULT` initializer macros and the legacy `#define`s are generated. (origin Out of Scope)
- **Merging the manifest into `packages/temper-placer/temper_placer/core/design_rules.py`.** The placer's design rules concern trace widths, clearances, and via templates — physical routing constraints. Firmware behavior limits do not belong in the PCB design-rules model. The manifest is firmware-local. (origin Out of Scope)
- **Generating the state-handler dispatch table.** The `state_<x>_entry` / `state_<x>_update` forward declarations (`state_machine.c:95-110`) and the two dispatch switches (`:266-275`, `:953-962`) stay hand-written; the X-macro covers only the enum, the count sentinel, and the string tables. (origin Out of Scope)
- **NVS-backed config persistence.** `nvs_flash` is a `REQUIRES` of the main component (`firmware/main/CMakeLists.txt:12`), but implementing NVS persistence of `g_config` is a separate feature. (origin Out of Scope)
- **`FAN_MAX_TEMP_RISE_RATE_C_PER_S` unification.** `firmware/components/safety/include/fan_guard.h:23` defines a separate `0.5f` constant that collides by name with `g_config.thresholds.fan_max_temp_rise_rate_c_per_s` (`config.h:111`, `5.0f`). This is a pre-existing independent duplication outside the nine tunables the origin doc enumerates. Tracked as a follow-up ticket; not in N8.
- **Atopile / KiCad cross-layer SSOT.** Owned by the source-of-truth-validation initiative. N8 is firmware-only.

### Out of scope

- Renaming the legacy `#define` symbols to a single naming convention. The generator preserves the existing uppercase names verbatim so `state_machine.c` call sites compile unchanged (resolves origin Open Question [Affects R5][Format] — default assumption holds: keep legacy names).
- Generating `firmware/README.md`'s tunable table. The table at `firmware/README.md:154-159` is deleted in U8 in favor of a one-line pointer to the manifest. Regenerating it as an appendix is a second template for marginal benefit (resolves origin Open Question [Affects README][Documentation] — delete outright).
- Adding `-Wswitch` to the ESP-IDF build's compile flags. R3's `default:` arms make unhandled cases explicit fault paths, which is stronger than the `-Wswitch` warning and works in the ESP-IDF build that sets no warning flags today.

---

## Key Technical Decisions

**Phase 1 first, Phase 2 second, Phase 3 last — three independent commits, each green on `main`.** The X-macro refactor (U1–U2) touches only `state_machine.h` and `state_machine.c`, compiles under the existing host test build with no new dependencies, and is verifiable via `test_state_machine_only` (`firmware/test/CMakeLists.txt:117-127`). The codegen (U3–U6) adds a Python toolchain and a generated header but does not yet remove the bare `#define`s — the generated `#define`s and the hand-written ones emit byte-identical values, so U6 can land with the generated header `#include`d after the hand-written block is removed in U7. The migration (U7–U9) deletes the hand-written `#define`s and adds the regression tests. Each phase is independently revertible.

**X-macro pattern: a single `STATE(symbol, string)` list in `state_machine.h` expands to the enum, the `STATE_COUNT` sentinel, and a `static const struct { system_state_t value; const char *name; } state_name_table[]` array.** `state_machine_get_state_string` becomes a table walk over `state_name_table` bounded by `STATE_COUNT`, returning `"UNKNOWN"` only if the input is `>= STATE_COUNT` (defensive, not the historical drift path). The fault list uses an independent `FAULT(symbol, string)` macro expanding to `fault_code_t`, `FAULT_COUNT`, and `fault_name_table[]`; `state_machine_get_fault_string` becomes the equivalent walk. The two lists are not merged. The file header comment at `state_machine.c:5-14` is deleted in favor of a pointer to `state_machine.h`'s X-macro list. (satisfies R1, R2; resolves origin Assumption A4 for the enum case)

**R3 implementation: add `default:` arms to the two state-dispatch switches, not to the string-table walks.** The string-table walks (`state_machine_get_state_string`, `state_machine_get_fault_string`) keep a `default: return "UNKNOWN"` arm because they are *lookup* functions and an out-of-range input is a legitimate runtime query. The two dispatch switches at `state_machine.c:266-275` (update dispatch) and `:953-962` (entry dispatch) gain `default: fault_code = FAULT_SELF_TEST_FAILED; transition_to(STATE_FAULT);` arms — an unhandled state is a firmware bug, not a lookup, and must fault loudly. The `fault_cleared` switch at `:1004-1021` already has a `default: return false;` and is left unchanged. (satisfies R3)

**Manifest location: `firmware/config.yaml`.** Firmware-local, sibling to `firmware/config.h` (the file it generates) and `firmware/config.c` (the consumer). YAML over TOML/JSON per origin Assumption A5 — YAML supports inline comments and `pyyaml` is already a transitive dependency via `packages/temper-placer/temper_placer/core/design_rules.py:9` (`import yaml`). The manifest declares exactly the nine tunables at `state_machine.c:39-47` plus the additional `g_config` fields that have no legacy `#define` today (`wdt_normal`, `wdt_idle`, `wdt_init`, `fan_check_interval`, `adc_check_interval`, `adc_min_valid_raw`, `adc_max_valid_raw`, `adc_stuck_buffer_size`, `adc_stuck_variance_threshold`, `adc_watchdog_timeout_ms`, `fan_max_temp_rise_rate_c_per_s`) so the generated `*_DEFAULT` macros are complete and `config.c:27-36` needs no edits. Each entry declares: `c_symbol`, `value`, `c_type`, `units`, `env_var`, `doc`. The `env_var` field is emitted into the header comment block (documentation only — `config_set_from_env`'s plumbing stays hand-written per the deferred scope). (satisfies R4)

**Codegen script: `firmware/tools/gen_config.py`, idempotent, Jinja2-templated, runnable standalone.** A single Python script loads `firmware/config.yaml`, renders a Jinja2 template (`firmware/tools/config.h.j2`), and writes `firmware/config.h`. Idempotence is enforced by writing to a temporary file and only replacing the target if the content differs (R6). The script is runnable as `python3 firmware/tools/gen_config.py` with no arguments (defaults relative to its own `__file__`). A firmware-local `firmware/tools/requirements.txt` pins `jinja2>=3.1` and `pyyaml>=6.0`. (satisfies R5, R6; resolves origin Assumption A1)

**Build wiring: host test build gets a CMake custom command; ESP-IDF build gets a pre-build custom target at the project level.** Per origin Open Question [Affects R6][Build]: ESP-IDF's `idf_component_register` wrapper in `firmware/main/CMakeLists.txt:4` does not expose `add_custom_command` cleanly inside the component, and the generated `config.h` must be visible to *both* `firmware/main/` (which compiles `state_machine.c` and `config.c`) and `firmware/test/` (host build). The codegen custom command is therefore attached at `firmware/CMakeLists.txt` (project level, before `project(induction_cooker)`) using `add_custom_command(OUTPUT ${CMAKE_SOURCE_DIR}/config.h MAIN_DEPENDENCY ${CMAKE_SOURCE_DIR}/config.yaml COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/gen_config.py BYPRODUCTS ${CMAKE_SOURCE_DIR}/config.h)`, and `firmware/main/CMakeLists.txt` adds `config.h` to its target's dependency via `set_source_files_properties` / a custom target dependency. The host test build at `firmware/test/CMakeLists.txt` adds the same `add_custom_command` before the `test_state_machine_only` target (lines 117-127) and adds `../config.h` to its `INCLUDE_DIRS` (currently absent from lines 86-94). Both builds invoke the same `gen_config.py`, so the host test build picks up the generated header automatically. (satisfies R6; resolves origin Open Question [Affects R6][Build])

**`config.h` is committed, not gitignored.** It is a versioned derived artifact. `.gitignore` currently ignores `firmware/build/` and `firmware/test/build/` (lines 66-67) but not `firmware/config.h` — no `.gitignore` edit is required. A new CI job (U9) regenerates and `git diff --exit-code`s. (satisfies R7; resolves origin Open Question [Affects R7][CI])

**CI: new firmware job in `.github/workflows/`, mirroring `python-tests.yml` structure.** There is no existing firmware CI job. U9 adds `.github/workflows/firmware-tests.yml` with two steps: (1) `pip install -r firmware/tools/requirements.txt && python3 firmware/tools/gen_config.py && git diff --exit-code firmware/config.h`; (2) `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build && ctest --test-dir firmware/test/build --output-on-failure`. The `paths:` trigger includes `firmware/**`. (resolves origin Open Question [Affects R7][CI])

**R9 test is a Python script in CI, not a C test.** Per origin Open Question [Affects R9][Testing]: a Python script parses both `firmware/config.yaml` and the generated `firmware/config.h` in one pass, extracts the `#define` values and the `*_DEFAULT` initializer fields, and asserts they match the manifest for every entry. This avoids building a C harness that parses YAML. The script lives at `firmware/tools/check_config_matches_manifest.py` and is invoked from the new CI job. The R10 test (string-table coverage) *is* a C test inside `test_state_machine.c` because it must call `state_machine_get_state_string` and `state_machine_get_fault_string` at runtime — this is the natural surface for it. (resolves origin Open Question [Affects R9][Testing])

**Header preservation: the generated `config.h` keeps the legacy `#define` names verbatim, the `temperature_limits_t` / `timeouts_t` / `thresholds_t` structs, the `*_DEFAULT` initializer macros, the `config_t` aggregate, the `g_config` extern, the `config_init` / `config_set_from_env` / `config_validate` / `config_print` declarations, and the access macros at `config.h:184-203`.** The header file comment is regenerated to state the file is generated from `firmware/config.yaml` and to point at `firmware/tools/gen_config.py`, replacing the current "ADDITIVE, non-breaking … continue to work" note at `config.h:16-18` with a statement that is now true by construction. The version-info block at `config.h:32-38` is preserved verbatim (not generated — `CONFIG_BUILD_DATE` / `CONFIG_BUILD_TIME` use `__DATE__` / `__TIME__` and must remain in the header). (satisfies R5)

**Migration is atomic: U7 deletes the nine `#define`s at `state_machine.c:39-47` and adds `#include "config.h"` in the same commit.** The generated header emits the same nine names with the same values, so the 14 call sites (`state_machine.c:239, :279, :444-445, :452-453, :483, :505, :570, :706, :722-723, :729-730, :761, :852, :1027`) compile unchanged. `MESSAGE_DISPLAY_TIME_MS` (line 47) migrates with the others. No call-site rewrite is required. (satisfies R8; resolves origin Assumption A4 for the `#define` case)

**Open Question [Affects R8][Migration] resolution:** `firmware/test/test_state_machine.c:230` and `:354` reference `PAN_CONFIDENCE_REQUIRED` and `PAN_DEBOUNCE_COUNT` in **comments only** — no test asserts a numeric value for any of the nine tunables. The grep across `firmware/test/` confirms zero numeric assertions on the migrated symbols. The migration is safe; no test edits are required for U7.

---

## Implementation Units

### Phase 1 — X-macro state and fault enums (no codegen, no new deps)

### U1. Rewrite `system_state_t` and `fault_code_t` as X-macro expansions

**Goal:** Replace the hand-maintained `system_state_t` enum (`state_machine.h:26-35`) and `fault_code_t` enum (`state_machine.h:40-52`) with X-macro lists that expand to the enum, a count sentinel, and a string-name table each.

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- `firmware/main/state_machine.h` (rewrite the two enum blocks; add `state_name_table` / `fault_name_table` declarations and `STATE_COUNT` / `FAULT_COUNT`)
- `firmware/main/state_machine.c` (rewrite `state_machine_get_state_string` at `:309-321` and `state_machine_get_fault_string` at `:292-307` as table walks; delete the file header comment at `:5-14`)

**Approach:**

In `state_machine.h`, replace lines 26-35 with:

```c
#define STATE_LIST(X) \
    X(STATE_INIT,     "INIT") \
    X(STATE_IDLE,     "IDLE") \
    X(STATE_PAN_DET,  "PAN_DET") \
    X(STATE_PREHEAT,  "PREHEAT") \
    X(STATE_HEATING,  "HEATING") \
    X(STATE_NO_PAN,   "NO_PAN") \
    X(STATE_COOLDOWN, "COOLDOWN") \
    X(STATE_FAULT,    "FAULT")

#define EXPAND_STATE_ENUM(sym, str)  sym,
typedef enum {
    STATE_LIST(EXPAND_STATE_ENUM)
    STATE_COUNT
} system_state_t;
#undef EXPAND_STATE_ENUM

#define EXPAND_STATE_NAME(sym, str)  { sym, str },
typedef struct { system_state_t value; const char *name; } state_name_entry_t;
static const state_name_entry_t state_name_table[] = {
    STATE_LIST(EXPAND_STATE_NAME)
};
#undef EXPAND_STATE_NAME
```

Apply the same pattern to `fault_code_t` (lines 40-52):

```c
#define FAULT_LIST(X) \
    X(FAULT_NONE,             "NO FAULT") \
    X(FAULT_OVER_TEMP,        "OVER TEMP") \
    X(FAULT_OVER_CURRENT,     "OVER CURRENT") \
    X(FAULT_FAN_FAILURE,      "FAN FAILED") \
    X(FAULT_PROBE_OPEN,       "PROBE OPEN") \
    X(FAULT_PROBE_SHORT,      "PROBE SHORT") \
    X(FAULT_THERMAL_RUNAWAY,  "THERMAL RUNAWAY") \
    X(FAULT_SELF_TEST_FAILED, "SELF TEST FAIL") \
    X(FAULT_WATCHDOG_RESET,   "WATCHDOG RESET") \
    X(FAULT_COOLDOWN_OVERHEAT,"COOLDOWN FAULT") \
    X(FAULT_PAN_DETECT_HW,    "PAN DETECT HW")

#define EXPAND_FAULT_ENUM(sym, str)  sym,
typedef enum {
    FAULT_LIST(EXPAND_FAULT_ENUM)
    FAULT_COUNT
} fault_code_t;
#undef EXPAND_FAULT_ENUM

#define EXPAND_FAULT_NAME(sym, str)  { sym, str },
typedef struct { fault_code_t value; const char *name; } fault_name_entry_t;
static const fault_name_entry_t fault_name_table[] = {
    FAULT_LIST(EXPAND_FAULT_NAME)
};
#undef EXPAND_FAULT_NAME
```

The `FAULT_NONE = 0` initializer is preserved by keeping `FAULT_NONE` first in the list and the enum starting at 0 by default. The string values are verbatim from the existing `state_machine_get_fault_string` switch at `state_machine.c:294`.

In `state_machine.c`, replace `state_machine_get_state_string` (`:309-321`) with:

```c
const char* state_machine_get_state_string(system_state_t state) {
    for (size_t i = 0; i < STATE_COUNT; i++) {
        if (state_name_table[i].value == state) return state_name_table[i].name;
    }
    return "UNKNOWN";
}
```

Replace `state_machine_get_fault_string` (`:292-307`) with the equivalent walk over `fault_name_table` bounded by `FAULT_COUNT`, returning `"UNKNOWN FAULT"` on miss. Delete the file header state-list comment at `:5-14` and replace with a one-line pointer: `/* States are defined by STATE_LIST in state_machine.h. */`.

**Patterns to follow:** Standard X-macro idiom; no existing X-macro use in the firmware tree to mirror, so the pattern is self-contained. The `state_name_table` is `static const` so it lives in `.rodata` on ESP32-S3.

**Test scenarios:**
- `test_state_machine_only` (`firmware/test/CMakeLists.txt:117-127`) builds and passes with no test changes — the public API (`state_machine_get_state_string`, `state_machine_get_fault_string`, `system_state_t`, `fault_code_t`) is unchanged.
- Adding `X(BoilHold, "BOIL_HOLD")` to `STATE_LIST` causes `STATE_BOIL_HOLD` to exist, `STATE_COUNT` to increment to 9, and `state_machine_get_state_string(STATE_BOIL_HOLD)` to return `"BOIL_HOLD"` with zero other edits (AE1).
- Removing one `X(...)` from `STATE_LIST` causes `state_name_table` to shrink and `STATE_COUNT` to decrement; any switch in `state_machine.c` that lacks a `default:` (after U2 adds them) is caught at review.

**Verification:** `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build && ctest --test-dir firmware/test/build -R state_machine --output-on-failure` passes.

---

### U2. Add `default:` fault arms to the two state-dispatch switches

**Goal:** The two `switch (sm_ctx.current_state)` / `switch (new_state)` dispatches at `state_machine.c:266-275` and `:953-962` gain `default:` arms that route to `STATE_FAULT` with `FAULT_SELF_TEST_FAILED`, so an unhandled state (the historical drift failure mode after adding a state to `STATE_LIST`) faults loudly instead of falling through silently.

**Requirements:** R3

**Dependencies:** U1 (the `default:` arm references `STATE_FAULT` and `FAULT_SELF_TEST_FAILED`, both defined by the X-macro lists)

**Files:**
- `firmware/main/state_machine.c` (add `default:` arms at `:275` and `:962`)

**Approach:**

At `state_machine.c:266-275`, after `case STATE_FAULT: state_fault_update(); break;`, add:

```c
default:
    sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
    transition_to(STATE_FAULT);
    break;
```

At `:953-962`, after `case STATE_FAULT: state_fault_entry(); break;`, add the same `default:` arm. The `fault_cleared` switch at `:1004-1021` already has `default: return false;` and is unchanged.

**Patterns to follow:** The existing `check_safety_interlocks` (`state_machine.c:965-999`) sets `sm_ctx.fault_code` then calls `transition_to(STATE_FAULT)` — the `default:` arm mirrors this established pattern.

**Test scenarios:**
- `test_state_machine_only` builds and passes — no test exercises the `default:` arm (no out-of-range state is injectable today), so coverage is structural.
- A future state added to `STATE_LIST` without a corresponding `case` in either dispatch switch routes through `default:` to `STATE_FAULT` at runtime, rather than silently doing nothing (AE2).

**Verification:** `ctest --test-dir firmware/test/build -R state_machine` passes. Manual review confirms both `default:` arms present.

---

### Phase 2 — Config manifest + codegen

### U3. Create `firmware/config.yaml` manifest

**Goal:** A single YAML file declaring every tunable currently in `state_machine.c:39-47` and `config.h:52-112`, plus the additional `g_config` fields with no legacy `#define`, so the generated `*_DEFAULT` macros are complete.

**Requirements:** R4

**Dependencies:** None (can be authored in parallel with U4/U5; only consumed by U5)

**Files:**
- `firmware/config.yaml` (new)

**Approach:**

The manifest is a flat list of entries grouped by struct. Each entry:

```yaml
temperatures:
  - c_symbol: SAFE_IDLE_TEMP
    field: safe_idle_temp
    value: 50.0
    c_type: float
    units: "°C"
    env_var: TEMP_SAFE_IDLE_C
    doc: "Safe temperature to return to IDLE"
  - c_symbol: MIN_TEMP
    field: min_temp
    value: 30.0
    ...
  - c_symbol: MAX_TEMP
    field: max_temp
    value: 250.0
    ...

timeouts:
  - c_symbol: PAN_DETECT_TIMEOUT_MS
    field: pan_detect
    value: 5000
    c_type: uint32_t
    units: ms
    env_var: PAN_DETECT_TIMEOUT_MS
    doc: "Pan detection timeout"
  - c_symbol: NO_PAN_TIMEOUT_MS
    field: no_pan_grace
    value: 3000
    ...
  - c_symbol: MAX_PREHEAT_TIME_MS
    field: max_preheat
    value: 600000
    ...
  # Entries below have no legacy #define today — generated header adds them
  # only inside TIMEOUTS_DEFAULT, no #define emitted:
  - field: wdt_normal
    value: 1000
    c_type: uint32_t
    units: ms
    env_var: WDT_NORMAL_MS
    doc: "Watchdog timeout in normal operation"
    legacy_define: false
  - field: wdt_idle
    value: 10000
    ...
  - field: wdt_init
    value: 5000
    ...
  - field: fan_check_interval
    value: 1000
    ...
  - field: adc_check_interval
    value: 500
    ...

thresholds:
  - c_symbol: PAN_DEBOUNCE_COUNT
    field: pan_debounce_count
    value: 10
    c_type: uint16_t
    env_var: PAN_DEBOUNCE_COUNT
    doc: "Pan detection debounce samples"
  - c_symbol: PAN_CONFIDENCE_REQUIRED
    field: pan_confidence_required
    value: 3
    c_type: uint8_t
    ...
  - field: adc_min_valid_raw
    value: 100
    c_type: uint16_t
    legacy_define: false
    ...
  - field: adc_max_valid_raw
    value: 3950
    ...
  - field: adc_stuck_buffer_size
    value: 8
    c_type: uint8_t
    ...
  - field: adc_stuck_variance_threshold
    value: 5
    c_type: uint32_t
    ...
  - field: adc_watchdog_timeout_ms
    value: 500
    c_type: uint32_t
    ...
  - field: fan_max_temp_rise_rate_c_per_s
    value: 5.0
    c_type: float
    ...

# MESSAGE_DISPLAY_TIME_MS has no g_config field — legacy #define only.
misc:
  - c_symbol: MESSAGE_DISPLAY_TIME_MS
    value: 2000
    c_type: uint32_t
    units: ms
    doc: "Non-blocking message display time"
    legacy_define_only: true
```

The `legacy_define: false` flag suppresses `#define` emission for fields that have no existing `#define` in `state_machine.c:39-47` (avoids introducing new bare macros that would need future migration). The `legacy_define_only: true` flag emits a `#define` with no struct field (for `MESSAGE_DISPLAY_TIME_MS`, which has no `g_config` home today). Values are sourced verbatim from `config.h:52-112` and `state_machine.c:39-47`; the `MIN_TEMP` value is `30.0` per the code, not `50` per the README drift.

**Patterns to follow:** YAML style mirrors `packages/temper-placer/temper_placer/core/design_rules.py:9` (`yaml.safe_load` consumer). Inline comments permitted.

**Test scenarios:**
- `python3 -c "import yaml; yaml.safe_load(open('firmware/config.yaml'))"` succeeds.
- The manifest contains exactly 9 entries with `c_symbol` (the legacy `#define` names) and the additional `g_config`-only fields, totaling the 3 + 8 + 8 = 19 fields present in `config.h:45-112` plus `MESSAGE_DISPLAY_TIME_MS` (= 20 total).

**Verification:** `python3 -c "import yaml; d=yaml.safe_load(open('firmware/config.yaml')); print(len(d['temperatures']), len(d['timeouts']), len(d['thresholds']), len(d['misc']))"` prints `3 8 8 1`.

---

### U4. Create `firmware/tools/gen_config.py` and Jinja2 template

**Goal:** A standalone Python script that loads `firmware/config.yaml`, renders `firmware/tools/config.h.j2`, and writes `firmware/config.h` idempotently.

**Requirements:** R5, R6

**Dependencies:** U3 (manifest must exist)

**Files:**
- `firmware/tools/gen_config.py` (new — the codegen script)
- `firmware/tools/config.h.j2` (new — the Jinja2 template)
- `firmware/tools/requirements.txt` (new — pins `jinja2>=3.1`, `pyyaml>=6.0`)

**Approach:**

`gen_config.py`:
1. Resolve paths relative to its own `__file__`: `manifest = Path(__file__).parent.parent / "config.yaml"`, `template = Path(__file__).parent / "config.h.j2"`, `output = Path(__file__).parent.parent / "config.h"`.
2. `yaml.safe_load` the manifest.
3. `jinja2.Environment(loader=FileSystemLoader(template.parent)).get_template(template.name).render(**manifest)`.
4. Write to a `.tmp` file, compare with existing `config.h`; replace only if different (idempotence per R6).
5. Print `config.h regenerated` on change, `config.h up to date` on no change. Exit 0 either way.

`config.h.j2` emits, in order:
- The generated-file header comment pointing at `firmware/config.yaml` and `firmware/tools/gen_config.py`, replacing the current `config.h:1-19` "ADDITIVE, non-breaking" note.
- The `#ifndef CONFIG_H` guard, `#include <stdint.h>`, `#include <stdbool.h>`.
- The version-info block (`config.h:32-38`) verbatim — `CONFIG_BUILD_DATE` / `CONFIG_BUILD_TIME` use `__DATE__` / `__TIME__` and must remain literal.
- For each group (`temperatures`, `timeouts`, `thresholds`): the `typedef struct { ... } <group>_t;` block, then the `#define <GROUP>_DEFAULT { ... }` initializer macro with `.field = value` lines. The struct field order and types match `config.h:45-112` exactly.
- The `config_t` aggregate struct (`config.h:119-123`), `extern config_t g_config;` (`:126`).
- The function declarations: `config_init`, `config_set_from_env` (correcting the `config_load_from_env` mismatch at `config.h:154`), `config_validate`, `config_print`. The env-var documentation comment block (`config.h:142-153`) is regenerated from the manifest's `env_var` fields.
- The access macros (`config.h:184-203`) verbatim.
- `#endif /* CONFIG_H */`.
- Legacy `#define` block: for each entry with `legacy_define: true` (default) and a `c_symbol`, emit `#define <c_symbol> <value>` with the value formatted per `c_type` (float values get the `f` suffix, e.g. `50.0f`; integer values are bare). These are emitted *after* the struct/initializer block so they are visible to `state_machine.c` when it `#include`s the header in U7.

**Patterns to follow:** Jinja2 templating is new to the firmware tree but standard. The template uses `{% for entry in temperatures %}` loops and `{{ entry.c_symbol }}` / `{{ entry.value }}{{ "f" if entry.c_type == "float" else "" }}` formatting.

**Test scenarios:**
- `python3 firmware/tools/gen_config.py` produces a `config.h` byte-identical to the current committed `config.h` for the struct/initializer/`#define` content (the header comment and the `config_load_from_env` → `config_set_from_env` rename are the only intentional diffs).
- Running the script twice produces byte-identical output (idempotence, R6).
- Editing `firmware/config.yaml` to set `safe_idle_temp: 55.0` and re-running causes both `#define SAFE_IDLE_TEMP 55.0f` and `.safe_idle_temp = 55.0f` inside `TEMP_LIMITS_DEFAULT` to update in one pass (AE3).

**Verification:** `python3 firmware/tools/gen_config.py && python3 firmware/tools/gen_config.py` — second invocation prints "up to date". `diff` between the generated `#define` block and `state_machine.c:39-47` shows identical values.

---

### U5. Wire codegen into ESP-IDF build and host test build

**Goal:** Both `idf.py build` and the host `cmake` test build regenerate `firmware/config.h` before compiling any source that includes it.

**Requirements:** R6

**Dependencies:** U4 (script must exist)

**Files:**
- `firmware/CMakeLists.txt` (add `add_custom_command` for `config.h` before `project(induction_cooker)`)
- `firmware/main/CMakeLists.txt` (add `config.h` to the component's dependency so the custom command fires)
- `firmware/test/CMakeLists.txt` (add `add_custom_command`, add `../config.h` directory to `INCLUDE_DIRS` at line 86-94, ensure `test_state_machine_only` depends on the generated header)

**Approach:**

In `firmware/CMakeLists.txt`, before `project(induction_cooker)` (line 10), add:

```cmake
add_custom_command(
    OUTPUT ${CMAKE_SOURCE_DIR}/config.h
    MAIN_DEPENDENCY ${CMAKE_SOURCE_DIR}/config.yaml
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tools/gen_config.py
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Regenerating firmware/config.h from config.yaml"
    VERBATIM
)
add_custom_target(gen_config DEPENDS ${CMAKE_SOURCE_DIR}/config.h)
```

ESP-IDF's `project.cmake` (included at line 7) wraps standard CMake; `add_custom_command` at the project level is the supported pattern. In `firmware/main/CMakeLists.txt`, after `idf_component_register(...)`, add `add_dependencies(${COMPONENT_LIB} gen_config)` so the component library depends on the generated header. The `INCLUDE_DIRS "."` at line 9 already covers `firmware/main/`; `config.h` lives at `firmware/config.h` (one level up), so add `..` to `INCLUDE_DIRS` or `#include "config.h"` from `state_machine.c` resolves via the parent-dir include path — confirm at implementation time whether ESP-IDF component includes search parent directories; if not, add `..` to `INCLUDE_DIRS`.

In `firmware/test/CMakeLists.txt`, add the same `add_custom_command` block (parameterized to `${CMAKE_CURRENT_SOURCE_DIR}/..`), add `${CMAKE_CURRENT_SOURCE_DIR}/..` to `INCLUDE_DIRS` (currently lines 86-94 list only `..`/components — add the firmware root), and `add_dependencies(test_state_machine_only gen_config)` so the host test build regenerates before compiling `state_machine.c`.

**Patterns to follow:** Standard CMake `add_custom_command` + `add_custom_target` + `add_dependencies` idiom. The host test build already uses `add_compile_options` / `add_definitions` at the project level (`firmware/test/CMakeLists.txt:18, 28-43`), so project-level custom commands fit the existing structure.

**Test scenarios:**
- Touching `firmware/config.yaml` and running `cmake --build firmware/test/build` regenerates `config.h` and recompiles `test_state_machine_only`.
- `idf.py build` (on an ESP-IDF-equipped host) regenerates `config.h` before compiling `state_machine.c` and `config.c`. (Not verifiable in CI without ESP-IDF; documented as the ESP-IDF build contract.)
- Deleting `firmware/config.h` and running the host test build recreates it.

**Verification:** `rm firmware/config.h && cmake --build firmware/test/build` recreates `config.h` and the build succeeds.

---

### Phase 3 — Migration and enforcement

### U6. Commit the generated `firmware/config.h` and document the regenerate command

**Goal:** Land the generated header as a versioned derived artifact and document the regenerate-and-commit workflow in `AGENTS.md`.

**Requirements:** R7

**Dependencies:** U4, U5 (the generator and build wiring must be in place)

**Files:**
- `firmware/config.h` (regenerated by `gen_config.py`; committed)
- `AGENTS.md` (add a one-liner under the existing "Configuration" section near the bd commands)

**Approach:**

Run `python3 firmware/tools/gen_config.py` and commit the resulting `firmware/config.h`. The committed file's header comment states it is generated and points at `firmware/config.yaml` + `firmware/tools/gen_config.py`. No `.gitignore` edit is needed — `firmware/config.h` is not currently ignored (only `firmware/build/` and `firmware/test/build/` are, per `.gitignore:66-67`).

In `AGENTS.md`, under the existing "Configuration" section (which currently documents `BEADS_AGENT_ID` etc. environment variables), add a firmware subsection:

```
## Firmware Config Codegen

`firmware/config.h` is generated from `firmware/config.yaml` by
`firmware/tools/gen_config.py`. After editing the manifest:

    python3 firmware/tools/gen_config.py
    git add firmware/config.h && git commit -m "chore: regenerate config.h"

CI regenerates and `git diff --exit-code`s against the committed copy.
```

**Test scenarios:**
- `git status` shows `firmware/config.h` tracked, not ignored.
- The committed `config.h` contains the generated-file header comment and the `config_set_from_env` declaration (not `config_load_from_env`).

**Verification:** `git ls-files firmware/config.h` lists the file. `git diff --exit-code firmware/config.h` after `python3 firmware/tools/gen_config.py` exits 0.

---

### U7. Delete bare `#define`s from `state_machine.c` and include `config.h`

**Goal:** Remove the nine `#define`s at `state_machine.c:39-47` and add `#include "config.h"` so the call sites pick up the same names from the generated header.

**Requirements:** R8

**Dependencies:** U6 (generated header must be committed and provide the nine `#define`s)

**Files:**
- `firmware/main/state_machine.c` (delete lines 39-47; add `#include "config.h"` near the existing `#include "state_machine.h"` at line 16)

**Approach:**

Delete lines 38-47 (the `/* Configuration */` comment block and the nine `#define`s). Add `#include "config.h"` after `#include "state_machine.h"` at line 16. The 14 call sites (`:239, :279, :444-445, :452-453, :483, :505, :570, :706, :722-723, :729-730, :761, :852, :1027`) continue to compile because `config.h` emits the same nine names with the same values. `MESSAGE_DISPLAY_TIME_MS` (the comment at `:1027` references it; the call site at `:239` uses it) is covered by the `legacy_define_only: true` emission in U4.

No test file edits are required — `firmware/test/test_state_machine.c:230` and `:354` reference the names in comments only (confirmed by grep), and no test asserts a numeric value for any of the nine tunables.

**Patterns to follow:** The existing `#include "../components/control/thermal_mass.h"` at `state_machine.c:35` shows parent-directory includes are already used in this file; `#include "config.h"` resolves via the firmware-root include path added in U5.

**Test scenarios:**
- `test_state_machine_only` builds and passes with no test changes (AE3, AE4).
- `state_machine.c` no longer contains any `#define SAFE_IDLE_TEMP` / `MAX_TEMP` / etc. — grep confirms zero matches.
- The 14 call sites compile unchanged (the names resolve via `config.h`).

**Verification:** `rg "#define (SAFE_IDLE_TEMP|MAX_TEMP|MIN_TEMP|PAN_DETECT_TIMEOUT_MS|NO_PAN_TIMEOUT_MS|PAN_DEBOUNCE_COUNT|PAN_CONFIDENCE_REQUIRED|MAX_PREHEAT_TIME_MS|MESSAGE_DISPLAY_TIME_MS)" firmware/main/state_machine.c` returns no matches. `ctest --test-dir firmware/test/build -R state_machine` passes.

---

### U8. Delete the drifted README tunable table

**Goal:** Remove the fourth copy of the tunable values — the `firmware/README.md:154-159` table that has already drifted (`MIN_TEMP = 50°C` per README vs `30°C` in code) — and replace with a one-line pointer to the manifest.

**Requirements:** Success Criteria (README cannot disagree with `config.h`)

**Dependencies:** U3 (manifest exists to point at)

**Files:**
- `firmware/README.md` (delete the table at lines 150-160; replace with a pointer)

**Approach:**

Replace the `Key parameters in state_machine.c:` paragraph and the table at `firmware/README.md:150-160` with:

```
Tunable parameters are declared in `firmware/config.yaml` and rendered into
`firmware/config.h` by `firmware/tools/gen_config.py`. See the manifest for
current values.
```

This resolves the `MIN_TEMP` drift by removing the duplicated statement; the manifest is the only place to state the value. (resolves origin Open Question [Affects README][Documentation] — delete outright)

**Test scenarios:**
- `rg "MIN_TEMP|MAX_TEMP|SAFE_IDLE_TEMP" firmware/README.md` returns no matches (the table is gone).
- The README still references `state_machine.c` for the state list (lines 12-19 are unchanged — those describe states, not tunables).

**Verification:** `rg "MIN_TEMP" firmware/README.md` returns no matches.

---

### U9. Add CI workflow and the two regression tests

**Goal:** A new `.github/workflows/firmware-tests.yml` job that (1) regenerates `config.h` and `git diff --exit-code`s, (2) runs the manifest-matches-header Python check, and (3) builds and runs the host test build including a new C test asserting string-table coverage.

**Requirements:** R7, R9, R10

**Dependencies:** U6, U7, U8 (the generated header, migration, and README cleanup must be in place)

**Files:**
- `.github/workflows/firmware-tests.yml` (new — the firmware CI job)
- `firmware/tools/check_config_matches_manifest.py` (new — the R9 Python check)
- `firmware/test/test_state_machine.c` (add the R10 string-table-coverage test cases)

**Approach:**

`.github/workflows/firmware-tests.yml` mirrors the structure of `.github/workflows/python-tests.yml`:

```yaml
name: Firmware Tests
on:
  push:
    paths: ['firmware/**', '.github/workflows/firmware-tests.yml']
  pull_request:
    paths: ['firmware/**', '.github/workflows/firmware-tests.yml']
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r firmware/tools/requirements.txt
      - name: Regenerate config.h and check drift
        run: |
          python3 firmware/tools/gen_config.py
          git diff --exit-code firmware/config.h
      - name: Check header matches manifest
        run: python3 firmware/tools/check_config_matches_manifest.py
      - name: Build and run host tests
        run: |
          cmake -B firmware/test/build firmware/test
          cmake --build firmware/test/build
          ctest --test-dir firmware/test/build --output-on-failure
```

`firmware/tools/check_config_matches_manifest.py` (R9):
1. `yaml.safe_load` `firmware/config.yaml`.
2. Parse `firmware/config.h` with regex: extract every `#define <c_symbol> <value>` and every `.field = <value>` inside `*_DEFAULT` blocks.
3. For every manifest entry with a `c_symbol`, assert the `#define` value matches `manifest value` (with `f` suffix normalization for floats).
4. For every manifest entry with a `field`, assert the corresponding `.field = value` inside the matching `*_DEFAULT` block matches.
5. On mismatch, print `<c_symbol>: header=<header_value>, manifest=<manifest_value>` and exit 1 (AE5).

The R10 C test is added to `firmware/test/test_state_machine.c`:

```c
static void test_state_string_table_covers_all_states(void) {
    for (int s = 0; s < STATE_COUNT; s++) {
        const char *name = state_machine_get_state_string((system_state_t)s);
        TEST_ASSERT_NOT_EQUAL_STRING("UNKNOWN", name);
        TEST_ASSERT_GREATER_THAN(0, strlen(name));
    }
}

static void test_fault_string_table_covers_all_faults(void) {
    for (int f = 0; f < FAULT_COUNT; f++) {
        const char *name = state_machine_get_fault_string((fault_code_t)f);
        TEST_ASSERT_NOT_EQUAL_STRING("UNKNOWN FAULT", name);
        TEST_ASSERT_GREATER_THAN(0, strlen(name));
    }
}
```

These are registered with `RUN_TEST` in `test_main_state_machine.c` (the test runner for the `test_state_machine_only` target per `firmware/test/CMakeLists.txt:124`). A state added to `STATE_LIST` with an empty string field fails the `strlen` assertion (AE6).

**Patterns to follow:** `.github/workflows/python-tests.yml` job structure. `test_state_machine.c` existing test function style (e.g. the `test_state_machine_*` functions already present). `ctest` registration via `add_test` in `firmware/test/CMakeLists.txt:294`.

**Test scenarios:**
- On a clean `main` after U1-U8, the CI job is green: `config.h` matches the committed copy, the manifest check passes, all host tests pass.
- Editing `firmware/config.yaml` to set `pan_detect_timeout_ms: 4000` without regenerating `config.h` causes the `git diff --exit-code` step to fail (AE4) *and* the `check_config_matches_manifest.py` step to fail with `PAN_DETECT_TIMEOUT_MS: header=5000, manifest=4000` (AE5).
- Adding `X(BoilHold, "")` to `STATE_LIST` causes `test_state_string_table_covers_all_states` to fail at `STATE_BOIL_HOLD` with `strlen(name) == 0` (AE6).
- Hand-editing `firmware/config.h` to change `MAX_TEMP` to `260.0f` without touching the manifest causes the `git diff --exit-code` step to fail with the diff attached (AE4).

**Verification:** The new CI job runs on push and passes. Locally: `python3 firmware/tools/check_config_matches_manifest.py` exits 0; `ctest --test-dir firmware/test/build -R state_machine --output-on-failure` passes including the two new tests.

---

## System-Wide Impact

- **`firmware/main/state_machine.h`:** The `system_state_t` and `fault_code_t` enums are rewritten as X-macro expansions; `state_name_table` and `fault_name_table` are new `static const` arrays. Consumers of `system_state_t` / `fault_code_t` (the test files, `state_machine.c` itself) see no API change. The `STATE_COUNT` / `FAULT_COUNT` sentinels are new public symbols.
- **`firmware/main/state_machine.c`:** Loses the nine `#define`s (lines 39-47), the file header comment (lines 5-14), and the two string-table switches (lines 292-321). Gains `#include "config.h"` and two `default:` fault arms. Net reduction ~40 lines.
- **`firmware/config.h`:** Becomes a generated, committed derived artifact. The struct/initializer/`g_config` surface is preserved; the legacy `#define` surface is preserved (now generated from the manifest); the header comment is replaced; the `config_load_from_env` declaration is corrected to `config_set_from_env`. No consumer besides `config.c` and (after U7) `state_machine.c`.
- **`firmware/config.c`:** Unchanged. `config_init`, `config_set_from_env`, `config_validate`, `config_print` continue to work against the generated `*_DEFAULT` macros. The header/impl name mismatch is resolved by the generated header emitting `config_set_from_env` (matching the implementation at `config.c:49`).
- **`firmware/config.yaml`:** New file, the SSOT for tunable values.
- **`firmware/tools/`:** New directory with `gen_config.py`, `config.h.j2`, `check_config_matches_manifest.py`, `requirements.txt`.
- **`firmware/CMakeLists.txt`, `firmware/main/CMakeLists.txt`, `firmware/test/CMakeLists.txt`:** Add the codegen custom command and dependencies; `firmware/test/CMakeLists.txt` adds the firmware root to `INCLUDE_DIRS`.
- **`firmware/README.md`:** The tunable table at lines 150-160 is deleted; replaced with a manifest pointer.
- **`firmware/test/test_state_machine.c`, `firmware/test/test_main_state_machine.c`:** Add the two R10 string-table-coverage tests.
- **`AGENTS.md`:** Gains a "Firmware Config Codegen" subsection documenting the regenerate-and-commit command.
- **`.github/workflows/firmware-tests.yml`:** New CI job. No existing CI job is modified (`python-tests.yml` is untouched).
- **`packages/temper-placer/temper_placer/core/design_rules.py`:** Untouched. The manifest is firmware-local; the placer's design-rules SSOT is a separate concern.
- **Developer workflow:** A developer who tunes a timeout edits `firmware/config.yaml`, runs `python3 firmware/tools/gen_config.py`, commits `firmware/config.yaml` + `firmware/config.h`. CI catches a forgotten regeneration. A developer who adds a state edits one `STATE(...)` line in `state_machine.h`; the enum, count, string table, and `default:` fault coverage all update.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| ESP-IDF's `project.cmake` wrapper does not propagate `add_custom_command`/`add_custom_target` defined before `project()` to component libraries | High | Medium | Per origin Assumption A2, the standard CMake pattern is supported but unverified for this exact case. Fallback: invoke `gen_config.py` as a pre-build shell step in `firmware/CMakeLists.txt` via `execute_process(...)` at configure time (runs once per CMake configure, not per build). This is weaker (no rebuild on manifest change without reconfigure) but always works. The host test build is unaffected (plain CMake). Document the fallback in U5. |
| `config.h` include path does not resolve from `state_machine.c` under ESP-IDF (component include dirs do not search parent directories) | Medium | Medium | U5 adds `..` to `firmware/main/CMakeLists.txt` `INCLUDE_DIRS` if needed. Confirm at implementation time by running `idf.py build`. The host test build already adds `${CMAKE_CURRENT_SOURCE_DIR}/..` paths. |
| Generated `#define` values differ in float formatting from the hand-written ones (e.g. `50.0f` vs `50.f` vs `5e1f`) causing binary differences | Low | Low | The Jinja2 template formats floats as `{{ value }}f` (e.g. `50.0f`), matching the existing `state_machine.c:39` style. Integer values are bare. The idempotence check in U4 catches formatting drift. |
| The `FAN_MAX_TEMP_RISE_RATE_C_PER_S` name collision (`fan_guard.h:23` defines `0.5f`; `config.h:111` has `g_config.thresholds.fan_max_temp_rise_rate_c_per_s = 5.0f`) becomes a compile conflict when `state_machine.c` includes `config.h` | Low | Low | `config.h` does not emit a `#define FAN_MAX_TEMP_RISE_RATE_C_PER_S` (the field is `g_config`-only, `legacy_define: false` in the manifest). `fan_guard.h:23`'s `#define` is unaffected. `state_machine.c` does not use the name today. No conflict. |
| Jinja2 is not installed on a contributor's host and they skip `pip install -r firmware/tools/requirements.txt` | Low | Medium | The committed `config.h` means a contributor who never regenerates still builds. CI catches a stale header. The `firmware/tools/requirements.txt` is installed in CI by the new workflow. |
| The R10 test's `STATE_COUNT` / `FAULT_COUNT` loop assumes the enum values are contiguous from 0 | Low | Low | The X-macro expansion produces contiguous values by construction (no explicit `= N` initializers in `STATE_LIST`). `FAULT_NONE = 0` is preserved by keeping `None` first with no explicit initializer. |
| `config_set_from_env` rename (from the declared `config_load_from_env`) breaks a caller | Low | Low | Grep confirms no caller of either name exists in `firmware/` outside `config.c`/`config.h` themselves. The rename aligns the declaration with the existing implementation; it fixes a latent bug, it does not introduce one. |
| The new firmware CI job runs on every `firmware/**` push and adds latency | Low | Medium | The host test build is fast (Unity + stubs, <30s). The codegen + drift check is <5s. Acceptable. |
| A manifest field is added without `legacy_define: false` and the generator emits a new bare `#define` that collides with an existing symbol | Low | Low | The `check_config_matches_manifest.py` script and the host build both catch a redefinition error at compile time (loud, not silent). The manifest's default is `legacy_define: true` only for the nine existing names; new fields should default to `false`. Document in `config.yaml` header comment. |

---

## Test Strategy

- **U1 (X-macro enums):** The existing `test_state_machine_only` target (`firmware/test/CMakeLists.txt:117-127`) is the regression surface — it must build and pass with no test changes, proving the public API (`system_state_t`, `fault_code_t`, `state_machine_get_state_string`, `state_machine_get_fault_string`) is preserved. Manual verification: add `X(BoilHold, "BOIL_HOLD")` to `STATE_LIST`, rebuild, confirm `STATE_BOIL_HOLD` exists and the string lookup returns `"BOIL_HOLD"` (AE1).
- **U2 (default fault arms):** Structural review — the two `default:` arms are present and route to `STATE_FAULT` with `FAULT_SELF_TEST_FAILED`. No runtime test exercises the arm (no out-of-range state is injectable); coverage is by inspection.
- **U3 (manifest):** `python3 -c "import yaml; yaml.safe_load(open('firmware/config.yaml'))"` succeeds; field counts match `config.h:45-112`.
- **U4 (codegen script):** Idempotence — running `gen_config.py` twice produces byte-identical output. Value consistency — the generated `#define` block matches `state_machine.c:39-47` value-for-value (before U7 deletes the latter). AE3 (manifest edit propagates to both `#define` and `*_DEFAULT` in one pass).
- **U5 (build wiring):** `rm firmware/config.h && cmake --build firmware/test/build` recreates the header and the build succeeds. Touching `config.yaml` triggers regeneration on the next build.
- **U6 (committed header):** `git diff --exit-code firmware/config.h` after `gen_config.py` exits 0.
- **U7 (migration):** `rg "#define SAFE_IDLE_TEMP" firmware/main/state_machine.c` returns no matches. `test_state_machine_only` builds and passes with no test changes.
- **U8 (README):** `rg "MIN_TEMP" firmware/README.md` returns no matches.
- **U9 (CI + R9/R10 tests):** The new CI job is green on `main`. The R9 Python script (`check_config_matches_manifest.py`) catches a manifest/header drift (AE5). The R10 C tests (`test_state_string_table_covers_all_states`, `test_fault_string_table_covers_all_faults`) catch a missing string-table entry (AE6). The `git diff --exit-code` step catches a hand-edited header (AE4).
- **Regression:** The existing `test_runner`, `test_state_machine_only`, `test_pid_only`, `test_safety_only`, and other host targets (`firmware/test/CMakeLists.txt:100-354`) continue to pass. No existing test is modified except `test_state_machine.c` (U9 adds two test functions) and `test_main_state_machine.c` (U9 adds two `RUN_TEST` lines).

---

## Deferred to Implementation

- **ESP-IDF `add_custom_command` placement:** Confirm whether `add_custom_command` before `project(induction_cooker)` in `firmware/CMakeLists.txt` propagates to `firmware/main/CMakeLists.txt`'s component library, or whether ESP-IDF requires the custom command at the component level via a different mechanism. If the project-level approach fails, fall back to `execute_process(...)` at configure time (runs once per configure, weaker but always works). Verify on an ESP-IDF-equipped host; the host test build is the CI-verifiable surface regardless. (origin Open Question [Affects R6][Build])
- **`config.h` include path under ESP-IDF:** Confirm whether `#include "config.h"` from `firmware/main/state_machine.c` resolves via the component's `INCLUDE_DIRS` or needs `..` added to `firmware/main/CMakeLists.txt:8-9`. The host test build already searches parent directories via `${CMAKE_CURRENT_SOURCE_DIR}/..` in `INCLUDE_DIRS`. (resolves origin Assumption A2)
- **`config_set_from_env` vs `config_load_from_env`:** The generated header emits `config_set_from_env` (matching `config.c:49`). Confirm no external consumer depends on the `config_load_from_env` name declared at `config.h:154` — grep shows none in `firmware/`, but a downstream consumer outside the repo is theoretically possible (unlikely for firmware). (origin context, not an Open Question)
- **`STATE_COUNT` / `FAULT_COUNT` sentinel visibility:** Decide whether `STATE_COUNT` and `FAULT_COUNT` are part of the public API (usable by tests and external code) or an internal detail. The R10 test uses them, so they are at minimum test-visible. Recommend public (they are useful for any state-iterating consumer and are emitted in the header). Document in `state_machine.h`.
- **Float formatting in the Jinja2 template:** Confirm `{{ value }}f` produces `50.0f` (not `50f` or `5e1f`) for the existing values. If Python's `str(50.0)` yields `"50.0"`, the template emits `50.0f` correctly. Edge case: `str(5.0)` yields `"5.0"`, not `"5"` — verify the `f` suffix is appended without a space.
- **`config.yaml` schema validation:** The manifest is small enough that a missing field (e.g. `c_type` omitted) surfaces as a Jinja2 template error at generation time. A formal schema (pydantic or jsonschema) is not required for N8 but could be added as a follow-up if the manifest grows.
- **CODEOWNERS for `firmware/config.yaml` and `firmware/config.h`:** Require firmware-reviewer approval on manifest changes. Not required for N8 functionally; recommend as a follow-up.
