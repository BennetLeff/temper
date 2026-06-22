---
title: "feat: Formalize Firmware State Machine Transition Table"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-design-validation-ideation.md
---

# feat: Formalize Firmware State Machine Transition Table

## Summary

A firmware data-structure initiative that replaces the hand-maintained, scattered `transition_to(NEW_STATE)` calls embedded in `state_machine.c`'s handler functions with a single generated transition table — a Cartesian-product matrix `transition_table[STATE_COUNT][EVENT_COUNT]` of `system_state_t` entries — that maps every legal `(state, event)` pair to its next state. The table is generated from a `firmware/transition_table.yaml` manifest through a Jinja2-based generator (`firmware/tools/gen_transition_table.py`), emitted as a committed derived artifact at `firmware/main/transition_table.h`, and wired into both the firmware build and the host test build. An `EVENT_LIST` X-macro is added to `firmware/main/state_machine.h:30` (sibling to the existing `STATE_LIST` at line 30) to define the event enum, sentinel, and string-name table. The existing hand-maintained Python `TRANSITIONS` list in `firmware/test/gen_transition_table.py:20-67` is replaced by a test that references the official C table from `transition_table.h`, eliminating a hand-maintained second copy. CI regenerates the table from the manifest and `git diff --exit-code`s, build-fails on any missing or illegal `(state, event)` cell (Python validator catches gaps at codegen time, `_Static_assert` catches dimension mismatch at compile time), and runs the full `test_state_machine_only` suite to confirm runtime behavior matches the declared table.

Today the 27 legal transitions across the 8-state × ~20-event matrix exist in three diverging copies: (1) the `transition_to()` call sites embedded in `state_machine.c` handler bodies at lines `:337, :340, :407, :486, :495, :501, :542, :554, :567, :573, :669, :677, :686, :706, :750, :759, :763, :770, :779, :823, :830, :879` and the `check_safety_interlocks()` calls at `:943, :949, :957, :966, :971`; (2) the `transition_to()` entry dispatch switch at `:923-936` dispatching to `state_*_entry()` functions; (3) the Python `TRANSITIONS` list at `firmware/test/gen_transition_table.py:20-67` (30 rows). Adding a state today edits one `X(...)` line in `STATE_LIST` but leaves the transition matrix unchanged — no signal that the new state's interaction with every event must be defined, no guard that an event handler in the new state has a defined next state. The table makes this a **structured failure**: a missing cell is caught by the Python generator at codegen time (before compilation), and a wrong next state is caught by the CI test at test time.

---

## Problem Frame

### The three-copy transition definition

| # | Site | Format | Risk |
|---|------|--------|------|
| 1 | `firmware/main/state_machine.c` handler functions (22 sites across `state_*_update()` and `check_safety_interlocks()`) | `transition_to(STATE_*)` call statements | Primary runtime behavior — hand-maintained, no cross-reference to the declared table |
| 2 | `firmware/main/state_machine.c:923-936` (`transition_to()` entry dispatch) | `switch(new_state)` → `state_*_entry()` | Mechanical — mirrors `STATE_LIST` via `switch`/`case`; no transition semantics |
| 3 | `firmware/test/gen_transition_table.py:20-67` (`TRANSITIONS` list) | Python `(from, event, to, fault, needs_fault_setup)` tuples | Test-only spec — hand-maintained, 30 rows, no guarantee of completeness |

A developer who adds `X(STATE_WARMUP, "WARMUP")` to `STATE_LIST` has **no mechanical prompt** to define the WARMUP→* and *→WARMUP transitions. The existing `default:` arms added in N8 (U2) at `state_machine.c:258-261` and `:932-935` route to `STATE_FAULT` — better than silent fall-through but still a runtime fault with no compile-time or codegen-time signal.

### Specific drift already documented

The Python `TRANSITIONS` list (`gen_transition_table.py:20-67`) contains 30 rows. The C handler functions contain the same transitions but expressed as conditional logic — there is no automated cross-check between the two. The test in `test_transition_table_generated.c` verifies the Python list against runtime behavior via mocking, but the Python list itself is a hand-maintained **copy** of the intended specification, not derived from the implementation.

### Why a table (not more switch/case dispatch)

The existing `switch(sm_ctx.current_state)` dispatch at `state_machine.c:249-262` is a **control-flow dispatch** — it routes to the correct `state_*_update()` function. It does not declare, check, or enforce *what transitions are legal* from that state. A transition table is a **declarative specification** of the state graph — it answers "given I am in state S and event E occurs, what is the next state?" as a single data structure, not as scattered code paths. The switch/case remains for control flow (calling the right handler); the table is the separate spec that the handlers are verified against.

---

## Scope Boundaries

### In scope

- R1: Add `EVENT_LIST` X-macro to `firmware/main/state_machine.h` (sibling to `STATE_LIST` at line 30), defining the event enum, `EVENT_COUNT` sentinel, and `event_name_table[]`.
- R2: Create `firmware/transition_table.yaml` manifest — the SSOT declaring every `(state, event) → (next_state, fault_code)` mapping.
- R3: Create `firmware/tools/gen_transition_table.py` — Jinja2 codegen that loads the YAML manifest and produces `firmware/main/transition_table.h` (the `transition_table[][]` array, typedef, `_Static_assert` completeness check).
- R4: The generated `transition_table.h` uses designated initializers `[STATE_X][EVENT_Y] = NEXT_STATE` so every cell is explicit; unset cells zero-initialize to an invalid sentinel caught by the Python validator at codegen time.
- R5: Replace the hand-maintained Python `TRANSITIONS` list in `firmware/test/gen_transition_table.py:20-67` with a generation step that reads the same `transition_table.yaml` manifest and produces test entries that map `(from, event)` rows to mock-setup code and expected assertions — **one manifest, two consumers**.
- R6: CI step: regenerate `transition_table.h` from the manifest, `git diff --exit-code` the committed copy, build `test_state_machine_only`, and run it — ensuring the committed table matches the manifest and runtime behavior matches the table.
- R7: Add a compile-time `_Static_assert(sizeof(transition_table) == STATE_COUNT * EVENT_COUNT * sizeof(system_state_t), ...)` to guarantee the 2D array dimensions are coherent.
- R8: Document the regenerate-and-commit workflow in `AGENTS.md` (extend the existing "Transition Table Regeneration" section at lines ~54-61).

### Deferred

- **Replacing the `switch(sm_ctx.current_state)` control-flow dispatch with a table-driven dispatch.** The handlers remain `state_*_update()` / `state_*_entry()` called via switch at `state_machine.c:249-262` and `:923-936`. The table is the **spec, not the runtime dispatch** — using it as the dispatch mechanism is a follow-on optimization (reduces code size, enables the compiler to optimize the jump table, but introduces a function-pointer table that must be validated against `STATE_LIST`). Tracked as a follow-up ticket.
- **Refactoring the event-condition evaluation to a single event-evaluation function.** Today each `state_*_update()` handler evaluates events via inline conditionals (`button_is_pressed(BUTTON_START)`, `detect_pan_presence() == PAN_ABSENT`, etc.). Abstracting these into a `evaluate_event(system_state_t state, event_t event) → bool` function is a larger refactor — the transition table stays the spec layer, the handler functions stay the logic layer.
- **Runtime validation that every `transition_to()` call is a legal transition per the table.** A `static_assert`-time debug-mode check wrapping `transition_to()` that asserts `transition_table[sm_ctx.current_state][event] == new_state` — valuable but requires plumbing the event argument through every `transition_to()` call, which is a significant API change. Deferred.
- **Generating the state-handler dispatch table (entry/update function pointers).** The `state_*_entry` / `state_*_update` forward declarations at `state_machine.c:78-93` and the two dispatch switches at `:249-262`, `:923-936` stay hand-written. The X-macro covers only the enum, count sentinel, and string tables.

### Out of scope

- Renaming the existing `transition_to()` function or changing its signature. It stays as-is.
- Generating `firmware/main/state_machine.c` itself. The generator emits only the header with the table data structure.
- Extending the YAML manifest to non-PCB-related hardware states (the 8 induction-cooker states are the complete current set).
- PCIe/KiCad transition-table analogues — this is firmware-only.

---

## Key Technical Decisions

### EVENT_LIST X-macro (R1)

An `EVENT_LIST` is added immediately after `STATE_LIST` at `firmware/main/state_machine.h:39`. Each entry is `X(EVENT_NAME, "STRING")`. The pattern mirrors the existing `STATE_LIST`:

```c
#define EVENT_LIST(X) \
    X(EVENT_SELFTEST_PASS,      "SELFTEST_PASS") \
    X(EVENT_SELFTEST_FAIL,      "SELFTEST_FAIL") \
    X(EVENT_START_BUTTON,       "START_BUTTON") \
    X(EVENT_PAN_DETECTED,       "PAN_DETECTED") \
    X(EVENT_PAN_TIMEOUT,        "PAN_TIMEOUT") \
    X(EVENT_NEAR_TARGET,        "NEAR_TARGET") \
    X(EVENT_PREHEAT_TIMEOUT,    "PREHEAT_TIMEOUT") \
    X(EVENT_OVER_TEMP,          "OVER_TEMP") \
    X(EVENT_OVER_CURRENT,       "OVER_CURRENT") \
    X(EVENT_FAN_FAILURE,        "FAN_FAILURE") \
    X(EVENT_PROBE_OPEN,         "PROBE_OPEN") \
    X(EVENT_PROBE_SHORT,        "PROBE_SHORT") \
    X(EVENT_THERMAL_RUNAWAY,    "THERMAL_RUNAWAY") \
    X(EVENT_PAN_REMOVED,        "PAN_REMOVED") \
    X(EVENT_STOP_BUTTON,        "STOP_BUTTON") \
    X(EVENT_TIMER_EXPIRED,      "TIMER_EXPIRED") \
    X(EVENT_PAN_REPLACED_SAME,  "PAN_REPLACED_SAME") \
    X(EVENT_PAN_REPLACED_DIFFERENT, "PAN_REPLACED_DIFFERENT") \
    X(EVENT_NO_PAN_TIMEOUT,     "NO_PAN_TIMEOUT") \
    X(EVENT_COOLED_DOWN,        "COOLED_DOWN") \
    X(EVENT_COOLDOWN_OVERHEAT,  "COOLDOWN_OVERHEAT") \
    X(EVENT_FAULT_RESET_CLEARED,"FAULT_RESET_CLEARED") \
    X(EVENT_FAULT_RESET_PERSISTS,"FAULT_RESET_PERSISTS")
```

This expands via the same pattern as `STATE_LIST` and `FAULT_LIST`: `typedef enum { EVENT_LIST(EXPAND_EVENT_ENUM) EVENT_COUNT } event_t;` plus `static const event_name_entry_t event_name_table[]`. The event names map 1:1 to the strings in the existing `EVENT_STUBS` dict at `gen_transition_table.py:74-116`.

**Why 23 events?** The existing `EVENT_STUBS` dict contains 23 event keys. Each corresponds to a conditional branch in a `state_*_update()` handler or a `check_safety_interlocks()` path that leads to `transition_to()`. The list is enumerated from the 30-row Python `TRANSITIONS` list (which has duplicate event names across different from-states — deduplicated events = 23 unique event strings).

### YAML manifest structure (R2)

`firmware/transition_table.yaml` declares every transition as a flat list of rows. Each row: `from`, `event`, `to`, `fault` (optional, defaults to `FAULT_NONE`), `notes` (optional documentation string). The manifest is validated at codegen time: every `from` must be in `STATE_LIST`, every `event` in `EVENT_LIST`, every `to` in `STATE_LIST`, and every `fault` (if set) in `FAULT_LIST`.

```yaml
# Temper firmware — transition table specification.
# Single source of truth for every legal (state, event) -> next_state mapping.
# Generated by firmware/tools/gen_transition_table.py into:
#   firmware/main/transition_table.h
#
# After editing, regenerate:
#   python3 firmware/tools/gen_transition_table.py
#   git add firmware/main/transition_table.h && git commit -m "chore: regenerate transition table"

# Each row: from_state, event, to_state, [fault_code]
# Omitted fault_code defaults to FAULT_NONE.
# Every (state, event) pair MUST have a row. Missing cells fail codegen.
transitions:
  # INIT
  - { from: STATE_INIT, event: EVENT_SELFTEST_PASS,       to: STATE_IDLE }
  - { from: STATE_INIT, event: EVENT_SELFTEST_FAIL,       to: STATE_FAULT, fault: FAULT_SELF_TEST_FAILED }

  # IDLE
  - { from: STATE_IDLE, event: EVENT_START_BUTTON,        to: STATE_PAN_DET }

  # PAN_DET
  - { from: STATE_PAN_DET, event: EVENT_PAN_DETECTED,     to: STATE_PREHEAT }
  - { from: STATE_PAN_DET, event: EVENT_PAN_TIMEOUT,      to: STATE_IDLE }

  # PREHEAT
  - { from: STATE_PREHEAT, event: EVENT_NEAR_TARGET,      to: STATE_HEATING }
  - { from: STATE_PREHEAT, event: EVENT_PREHEAT_TIMEOUT,  to: STATE_FAULT, fault: FAULT_THERMAL_RUNAWAY }
  - { from: STATE_PREHEAT, event: EVENT_OVER_TEMP,        to: STATE_FAULT, fault: FAULT_OVER_TEMP }
  - { from: STATE_PREHEAT, event: EVENT_OVER_CURRENT,     to: STATE_FAULT, fault: FAULT_OVER_CURRENT }
  - { from: STATE_PREHEAT, event: EVENT_FAN_FAILURE,      to: STATE_FAULT, fault: FAULT_FAN_FAILURE }
  - { from: STATE_PREHEAT, event: EVENT_PROBE_OPEN,       to: STATE_FAULT, fault: FAULT_PROBE_OPEN }
  - { from: STATE_PREHEAT, event: EVENT_PROBE_SHORT,      to: STATE_FAULT, fault: FAULT_PROBE_SHORT }
  - { from: STATE_PREHEAT, event: EVENT_PAN_REMOVED,      to: STATE_NO_PAN }
  - { from: STATE_PREHEAT, event: EVENT_STOP_BUTTON,      to: STATE_COOLDOWN }

  # HEATING
  - { from: STATE_HEATING, event: EVENT_NEAR_TARGET,      to: STATE_HEATING, notes: "self-loop (PID control continues)" }
  - { from: STATE_HEATING, event: EVENT_OVER_TEMP,        to: STATE_FAULT, fault: FAULT_OVER_TEMP }
  - { from: STATE_HEATING, event: EVENT_OVER_CURRENT,     to: STATE_FAULT, fault: FAULT_OVER_CURRENT }
  - { from: STATE_HEATING, event: EVENT_FAN_FAILURE,      to: STATE_FAULT, fault: FAULT_FAN_FAILURE }
  - { from: STATE_HEATING, event: EVENT_PROBE_OPEN,       to: STATE_FAULT, fault: FAULT_PROBE_OPEN }
  - { from: STATE_HEATING, event: EVENT_PROBE_SHORT,      to: STATE_FAULT, fault: FAULT_PROBE_SHORT }
  - { from: STATE_HEATING, event: EVENT_THERMAL_RUNAWAY,  to: STATE_FAULT, fault: FAULT_THERMAL_RUNAWAY }
  - { from: STATE_HEATING, event: EVENT_PAN_REMOVED,      to: STATE_NO_PAN }
  - { from: STATE_HEATING, event: EVENT_STOP_BUTTON,      to: STATE_COOLDOWN }
  - { from: STATE_HEATING, event: EVENT_TIMER_EXPIRED,    to: STATE_COOLDOWN }

  # NO_PAN
  - { from: STATE_NO_PAN, event: EVENT_PAN_REPLACED_SAME,        to: STATE_PREHEAT }
  - { from: STATE_NO_PAN, event: EVENT_PAN_REPLACED_DIFFERENT,   to: STATE_COOLDOWN }
  - { from: STATE_NO_PAN, event: EVENT_NO_PAN_TIMEOUT,           to: STATE_COOLDOWN }

  # COOLDOWN
  - { from: STATE_COOLDOWN, event: EVENT_COOLED_DOWN,            to: STATE_IDLE }
  - { from: STATE_COOLDOWN, event: EVENT_COOLDOWN_OVERHEAT,      to: STATE_FAULT, fault: FAULT_COOLDOWN_OVERHEAT }

  # FAULT
  - { from: STATE_FAULT, event: EVENT_FAULT_RESET_CLEARED,       to: STATE_INIT }
  - { from: STATE_FAULT, event: EVENT_FAULT_RESET_PERSISTS,      to: STATE_FAULT }
```

The manifest is validated at codegen time via `firmware/tools/check_transition_table_completeness.py` — a separate validator script (or method in `gen_transition_table.py`) that asserts for every `s in STATE_LIST` and every `e in EVENT_LIST`, there exists exactly one row with `from == s` and `event == e`. Missing cells are reported as `ERROR: (STATE_INIT, EVENT_START_BUTTON) has no transition row` and exit 1. This satisfies R3 (build-time detection of illegal/unreachable transitions) — a new state added to `STATE_LIST` without updating the manifest causes the build to fail **before compilation**.

### 2D array with designated initializers (R3, R4)

The generated `firmware/main/transition_table.h` produces:

```c
/** Sentinel: marks a (state, event) pair that has no declared transition. */
#define TRANSITION_INVALID ((system_state_t)(-1))

/** Complete transition table: transition_table[from_state][event] → next_state.
 *  Indexed by system_state_t (0..STATE_COUNT-1) and event_t (0..EVENT_COUNT-1).
 *  Every cell is explicitly initialized. Unreachable cells are TRANSITION_INVALID. */
static const system_state_t transition_table[STATE_COUNT][EVENT_COUNT] = {
    [STATE_INIT] = {
        [EVENT_SELFTEST_PASS]       = STATE_IDLE,
        [EVENT_SELFTEST_FAIL]       = STATE_FAULT,
        /* ... all remaining events → TRANSITION_INVALID (implicit zero-init) */
    },
    [STATE_IDLE] = {
        [EVENT_START_BUTTON]        = STATE_PAN_DET,
        /* ... all remaining events → TRANSITION_INVALID */
    },
    /* ... remaining states */
};

/** Fault code for a transition (or FAULT_NONE if not a fault transition).
 *  Indexed identically to transition_table. */
static const fault_code_t transition_fault[STATE_COUNT][EVENT_COUNT] = {
    [STATE_INIT] = {
        [EVENT_SELFTEST_FAIL]       = FAULT_SELF_TEST_FAILED,
        /* ... all remaining events → FAULT_NONE (implicit zero-init) */
    },
    /* ... */
};

/** Compile-time guard: dimensions match the X-macro sentinels. */
_Static_assert(
    sizeof(transition_table) == STATE_COUNT * EVENT_COUNT * sizeof(system_state_t),
    "transition_table dimensions must match STATE_COUNT * EVENT_COUNT");

_Static_assert(
    sizeof(transition_fault) == STATE_COUNT * EVENT_COUNT * sizeof(fault_code_t),
    "transition_fault dimensions must match STATE_COUNT * EVENT_COUNT");
```

This design gives **compile-time** guarantees: if `STATE_COUNT` or `EVENT_COUNT` changes (due to a new entry in the X-macro list) but the generated header is stale, the `_Static_assert` fires because the array literal's implicit size no longer matches `STATE_COUNT * EVENT_COUNT`. The **codegen-time** guarantee is stronger: `gen_transition_table.py` parses `STATE_LIST` and `EVENT_LIST` from `state_machine.h`, iterates every combination, and asserts a manifest row exists for each.

**Why not a flat `transition_row_t` array?** A flat array of structs (the current `test_transition_table_generated.c:40-72` style) requires a linear search to find the `(from, event)` pair — O(n) lookup. The 2D array indexed by enum value is O(1) and directly represents the Cartesian product. A flat array also cannot `_Static_assert` dimensional completeness because its length is count-of-legitimate-transitions, not `STATE_COUNT * EVENT_COUNT`. The 2D array's `sizeof` check is exact.

**Initialization semantics:** Designated initializers `[STATE_INIT] = { [EVENT_START_BUTTON] = ... }` explicitly set each cell. Cells not listed are zero-initialized (C99 §6.7.8.21). `TRANSITION_INVALID` is `(system_state_t)(-1)` which is `0xFFFFFFFF` — NOT zero. So an unset cell is `0` = `STATE_INIT`, which is a **valid but incorrect** value. This means the C compiler cannot distinguish "missing" from a real `STATE_INIT` transition — the compile-time guard is the **dimensional** `_Static_assert` (catches stale header when enum sizes change), not a per-cell sentinel check. The per-cell completeness is enforced by the Python codegen validator, which runs as a CMake `add_custom_command` dependency on the manifest — the build fails if a cell is missing in the manifest.

### Codegen script: `firmware/tools/gen_transition_table.py` (R3, R4)

Mirrors the existing `gen_config.py` pattern (`firmware/tools/gen_config.py:20-58`):
1. Resolve paths relative to `__file__`: manifest at `../transition_table.yaml`, header at `../state_machine.h`, output at `../main/transition_table.h`, template at `transition_table.h.j2`.
2. `yaml.safe_load` the manifest.
3. Parse `STATE_LIST` and `EVENT_LIST` from `state_machine.h` via regex (same pattern as `gen_transition_table.py:130-150` `parse_state_machine_header()`).
4. Validate completeness: for every `(state, event)` pair, assert exactly one row exists in the manifest with matching `from` and `event`. On failure, print `MISSING: (STATE_INIT, EVENT_START_BUTTON) has no transition` for each missing cell and exit 1.
5. Validate `to` and `fault` values against the parsed enums from the header.
6. Render the Jinja2 template with the validated transition data, `STATE_COUNT`, and `EVENT_COUNT`.
7. Idempotent write: write to `.tmp` file, compare with existing `transition_table.h`, replace only if different. Print "transition_table.h regenerated" on change, "transition_table.h up to date" on no change. Exit 0 either way.

**Template:** `firmware/tools/transition_table.h.j2` — a Jinja2 template that:
- Emits the generated-file header comment (DO NOT EDIT, generated from `firmware/transition_table.yaml`, pointing at `firmware/tools/gen_transition_table.py`).
- Emits the `#ifndef TRANSITION_TABLE_H` guard.
- Includes `"state_machine.h"` for enum types.
- Emits `#define TRANSITION_INVALID ((system_state_t)(-1))`.
- Emits the `transition_table[STATE_COUNT][EVENT_COUNT]` array literal with designated initializers for each `(from, event)` → `to` mapping.
- Emits the `transition_fault[STATE_COUNT][EVENT_COUNT]` array literal with designated initializers for fault-code-bearing transitions (default `FAULT_NONE` for others).
- Emits the two `_Static_assert` dimensional guards.
- Emits `#endif`.

**Requirements pin:** `firmware/tools/requirements.txt` (created in U4 of the N8 plan) already pins `jinja2>=3.1` and `pyyaml>=6.0`. No new Python dependencies.

### Build wiring: CMake custom command pattern (R3, R6)

The codegen is wired into the host test build at `firmware/test/CMakeLists.txt` following the existing `gen_config` custom-command pattern at lines 101-109:

```cmake
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_SOURCE_DIR}/../main/transition_table.h
    MAIN_DEPENDENCY ${CMAKE_CURRENT_SOURCE_DIR}/../transition_table.yaml
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.h
    COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/../tools/gen_transition_table.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/..
    COMMENT "Regenerating firmware/main/transition_table.h from transition_table.yaml"
    VERBATIM
)
add_custom_target(gen_transition_table DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/transition_table.h)
add_dependencies(test_state_machine_only gen_transition_table)
```

The `DEPENDS` on `state_machine.h` ensures the transition table regenerates when new states or events are added to the X-macro lists — even without a manifest edit. This is critical for R3: adding `X(STATE_WARMUP, "WARMUP")` to `STATE_LIST` triggers a regeneration, which triggers the completeness check, which fails because WARMUP has no transition rows in the manifest → the developer is prompted to add them.

The ESP-IDF build (`firmware/CMakeLists.txt`) gets the same custom command (using `idf_component_register` or project-level `add_custom_target` as established in N8 U5). The `transition_table.h` include path is already covered by the firmware-root `INCLUDE_DIRS` added in N8 U5.

### Test regeneration: one manifest, two consumers (R5)

The existing `gen_transition_table.py` (`firmware/test/gen_transition_table.py:1-565`) is refactored:

1. The hand-maintained `TRANSITIONS` list at lines 20-67 is **deleted**.
2. The script now loads `transition_table.yaml` (the same manifest consumed by the codegen) to build the transition list.
3. The `EVENT_STUBS` dict at lines 74-116 **remains hand-maintained** — it maps event names to mock C setup code, which is inherently implementation-specific and not declarable in the manifest.
4. The generated `test_transition_table_generated.c` uses the same YAML-derived transition list to produce its `transition_table[]` test rows, but the test **also** `#include`s the official `transition_table.h` and adds new assertions:

```c
/* Verify the official table matches the test table row-by-row */
for (size_t i = 0; i < transition_count; i++) {
    system_state_t from = transition_table_test[i].from;
    event_t event = event_from_string(transition_table_test[i].event);
    system_state_t official_next = transition_table[from][event];
    TEST_ASSERT_NOT_EQUAL_INT_MESSAGE(TRANSITION_INVALID, official_next,
        "Official transition table has a gap — missing manifest entry");
    TEST_ASSERT_EQUAL_INT_MESSAGE(official_next, transition_table_test[i].expected_to,
        "Test expected destination differs from official transition table");
}
```

This makes the test a **consistency check** between the official table and the test-runner's expected behavior, rather than the test-runner being the sole spec.

### CI: regenerate-and-diff gate (R6)

A step is added to `.github/workflows/firmware-tests.yml` (created in N8 U9, `firmware/test/CMakeLists.txt` line 101-109 already has the codegen custom command wired into the host test build):

The CI workflow's "Regenerate config.h and check drift" step is extended to also regenerate the transition table, or a new step is added:

```yaml
- name: Regenerate transition table and check drift
  run: |
    python3 firmware/tools/gen_transition_table.py
    git diff --exit-code firmware/main/transition_table.h
```

The existing "Build and run host tests" step already builds `test_state_machine_only` (which depends on the generated `transition_table.h` via the CMake custom-command dependency). If the regenerated table passes `git diff --exit-code`, the build and test proceed; if the table is stale (manifest edited without regenerating), CI fails before the build.

### `AGENTS.md` documentation (R8)

The existing "Transition Table Regeneration" section at `AGENTS.md` (lines ~54-61) currently reads:

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

This is **updated** to reference the new manifest + generator workflow. The old `gen_transition_table.py --generate` command is replaced, and the section documents both the manifest and the test-regeneration command. The existing `gen_transition_table.py --check` mode (runs validation only) is preserved but now validates against the YAML manifest rather than the Python-inline `TRANSITIONS` list.

---

## Implementation Units

### Phase 1 — Event definitions and manifest

### U1. Add `EVENT_LIST` X-macro to `state_machine.h`

**Goal:** A single X-macro list defining all 23 events, expanding to `event_t` enum, `EVENT_COUNT` sentinel, and `event_name_table[]`.

**Requirements:** R1

**Dependencies:** None

**Files:**
- `firmware/main/state_machine.h` (add `EVENT_LIST` after `FAULT_LIST` at line 87, add `event_t` typedef, `EVENT_COUNT`, and `event_name_table[]`)

**Approach:**

Insert after line 87 (`#undef EXPAND_FAULT_NAME`):

```c
#define EVENT_LIST(X) \
    X(EVENT_SELFTEST_PASS,       "SELFTEST_PASS") \
    X(EVENT_SELFTEST_FAIL,       "SELFTEST_FAIL") \
    X(EVENT_START_BUTTON,        "START_BUTTON") \
    X(EVENT_PAN_DETECTED,        "PAN_DETECTED") \
    X(EVENT_PAN_TIMEOUT,         "PAN_TIMEOUT") \
    X(EVENT_NEAR_TARGET,         "NEAR_TARGET") \
    X(EVENT_PREHEAT_TIMEOUT,     "PREHEAT_TIMEOUT") \
    X(EVENT_OVER_TEMP,           "OVER_TEMP") \
    X(EVENT_OVER_CURRENT,        "OVER_CURRENT") \
    X(EVENT_FAN_FAILURE,         "FAN_FAILURE") \
    X(EVENT_PROBE_OPEN,          "PROBE_OPEN") \
    X(EVENT_PROBE_SHORT,         "PROBE_SHORT") \
    X(EVENT_THERMAL_RUNAWAY,     "THERMAL_RUNAWAY") \
    X(EVENT_PAN_REMOVED,         "PAN_REMOVED") \
    X(EVENT_STOP_BUTTON,         "STOP_BUTTON") \
    X(EVENT_TIMER_EXPIRED,       "TIMER_EXPIRED") \
    X(EVENT_PAN_REPLACED_SAME,   "PAN_REPLACED_SAME") \
    X(EVENT_PAN_REPLACED_DIFFERENT, "PAN_REPLACED_DIFFERENT") \
    X(EVENT_NO_PAN_TIMEOUT,      "NO_PAN_TIMEOUT") \
    X(EVENT_COOLED_DOWN,         "COOLED_DOWN") \
    X(EVENT_COOLDOWN_OVERHEAT,   "COOLDOWN_OVERHEAT") \
    X(EVENT_FAULT_RESET_CLEARED, "FAULT_RESET_CLEARED") \
    X(EVENT_FAULT_RESET_PERSISTS,"FAULT_RESET_PERSISTS")

#define EXPAND_EVENT_ENUM(sym, str)  sym,
typedef enum {
    EVENT_LIST(EXPAND_EVENT_ENUM)
    EVENT_COUNT
} event_t;
#undef EXPAND_EVENT_ENUM

#define EXPAND_EVENT_NAME(sym, str)  { sym, str },
typedef struct { event_t value; const char *name; } event_name_entry_t;
static const event_name_entry_t event_name_table[] = {
    EVENT_LIST(EXPAND_EVENT_NAME)
};
#undef EXPAND_EVENT_NAME
```

Also add a public API function `const char* state_machine_get_event_string(event_t event)` (mirroring `state_machine_get_state_string` at `state_machine.h:176`).

**Patterns to follow:** Existing `STATE_LIST` / `FAULT_LIST` X-macro pattern at `state_machine.h:30-86`.

**Test scenarios:**
- `test_state_machine_only` builds — no existing code uses `event_t`, so zero compilation breakage.
- `EVENT_COUNT == 23`.
- `state_machine_get_event_string((event_t)0)` returns `"SELFTEST_PASS"`.
- Adding `X(EVENT_NEW, "NEW")` increments `EVENT_COUNT` to 24 and adds a string-table entry.

**Verification:** `cmake --build firmware/test/build && ./firmware/test/build/test_state_machine_only` passes.

---

### U2. Create `firmware/transition_table.yaml` manifest

**Goal:** A single YAML file declaring every legal `(state, event) → (next_state, fault_code)` transition — the SSOT.

**Requirements:** R2, R4

**Dependencies:** U1 (`EVENT_LIST` must exist so the manifest can reference `EVENT_*` symbols)

**Files:**
- `firmware/transition_table.yaml` (new)

**Approach:**

The manifest contains exactly the 30 transitions currently in `gen_transition_table.py:20-67`, translated from the Python `("STATE_INIT", "SELFTEST_PASS", ...)` tuple format to the YAML `{from:, event:, to:, fault:}` format shown in Key Technical Decisions above.

Validation during authoring:
1. For each of the 8 states in `STATE_LIST`, list which events can fire in that state (by inspecting `state_*_update()` handler bodies at `state_machine.c`).
2. Cross-reference against the existing `TRANSITIONS` list — 30 rows map 1:1 to 30 YAML entries.
3. The `fault` field is `null` (or omitted) for all non-fault transitions; fault transitions carry the `FAULT_*` constant.
4. Self-loops (e.g., `STATE_HEATING + EVENT_NEAR_TARGET → STATE_HEATING`) are explicitly listed — they are legal transitions that keep the state machine in its current state.

**Patterns to follow:** `firmware/config.yaml` YAML style (`firmware/config.yaml:1-169`) — YAML with inline comments allowed. Flat list of entries grouped by `from` state.

**Test scenarios:**
- `python3 -c "import yaml; yaml.safe_load(open('firmware/transition_table.yaml'))"` succeeds.
- The manifest contains exactly 30 rows (matching the existing `TRANSITIONS` list count).
- Every declared `from` state is one of the 8 `STATE_*` symbols in `STATE_LIST`.
- Every declared `to` state is one of the 8 `STATE_*` symbols.
- Every declared `event` is one of the 23 `EVENT_*` symbols in `EVENT_LIST`.
- Every declared `fault` (when non-null) is one of the 11 `FAULT_*` symbols.
- No duplicate `(from, event)` pairs exist.

**Verification:** A Python validation script (developed as part of U3) confirms the manifest covers every `(state, event)` pair and references only valid enum members.

---

### Phase 2 — Codegen + table

### U3. Create `firmware/tools/gen_transition_table.py` and template

**Goal:** A standalone Python script that loads `firmware/transition_table.yaml`, parses `state_machine.h` for enum members, validates completeness, and renders `firmware/main/transition_table.h` via Jinja2.

**Requirements:** R3, R4

**Dependencies:** U1 (`EVENT_LIST`), U2 (manifest)

**Files:**
- `firmware/tools/gen_transition_table.py` (new)
- `firmware/tools/transition_table.h.j2` (new)
- `firmware/tools/check_transition_table_completeness.py` (new — the validator, may be a function in `gen_transition_table.py` or standalone)

**Approach:**

`gen_transition_table.py` structure mirrors `firmware/tools/gen_config.py:20-58`:

1. Parse `STATE_LIST` and `EVENT_LIST` from `firmware/main/state_machine.h` via regex (reusing the `parse_state_machine_header()` pattern at `firmware/test/gen_transition_table.py:130-150`, extended to parse `EVENT_LIST`).
2. `yaml.safe_load` the manifest.
3. Validate every transition row: `from` and `to` in `states` set, `event` in `events` set, `fault` in `faults` set or `None`.
4. **Completeness check (R3):** For every `s in states` and every `e in events`, assert there is exactly one row in `transitions` with `from == s and event == e`. Print `ERROR: (STATE_INIT, EVENT_START_BUTTON) has no transition row` for each missing pair. Exit 1 on any missing.
5. Render `transition_table.h.j2` with Jinja2, passing:
   - `state_names`: list of `(STATE_X, "NAME")` tuples
   - `event_names`: list of `(EVENT_X, "NAME")` tuples
   - `state_count`: `len(states)`
   - `event_count`: `len(events)`
   - `transition_map`: dict `{(from, event): (to, fault)}` for rendering the designated initializers
6. Idempotent write: write to `firmware/main/transition_table.h.tmp`, compare with existing `firmware/main/transition_table.h`, replace only if different.

**Template (`transition_table.h.j2`):**

```
/** @file transition_table.h — GENERATED FILE. DO NOT EDIT. */
#ifndef TRANSITION_TABLE_H
#define TRANSITION_TABLE_H
#include "state_machine.h"
#define TRANSITION_INVALID ((system_state_t)(-1))

static const system_state_t transition_table[STATE_COUNT][EVENT_COUNT] = {
{%- for s in state_names %}
    [{{ s.enum }}] = {
{%- for e in event_names %}
        [{{ e.enum }}] = {{ transition_map[(s.enum, e.enum)].to | default("TRANSITION_INVALID") }},
{%- endfor %}
    },
{%- endfor %}
};

static const fault_code_t transition_fault[STATE_COUNT][EVENT_COUNT] = {
{%- for s in state_names %}
    [{{ s.enum }}] = {
{%- for e in event_names %}
        [{{ e.enum }}] = {{ transition_map[(s.enum, e.enum)].fault | default("FAULT_NONE") }},
{%- endfor %}
    },
{%- endfor %}
};

_Static_assert(sizeof(transition_table) == STATE_COUNT * EVENT_COUNT * sizeof(system_state_t),
    "transition_table dimensions must equal STATE_COUNT * EVENT_COUNT");
_Static_assert(sizeof(transition_fault) == STATE_COUNT * EVENT_COUNT * sizeof(fault_code_t),
    "transition_fault dimensions must equal STATE_COUNT * EVENT_COUNT");

#endif
```

**Patterns to follow:** `firmware/tools/gen_config.py:20-58` (idempotent write pattern). `firmware/tools/config.h.j2:1-199` (Jinja2 template style with guards). `firmware/test/gen_transition_table.py:130-150` (header parsing regex).

**Test scenarios:**
- Running on the seeded manifest produces a `transition_table.h` with 8×23 = 184 cells, of which 30 are explicit transitions and 154 are `TRANSITION_INVALID`.
- Adding `X(STATE_WARMUP, "WARMUP")` to `STATE_LIST` and re-running causes the completeness check to fail with `ERROR: (STATE_WARMUP, EVENT_*) has no transition row` — 23 errors, exit 1. Build fails before compilation.
- Running twice produces byte-identical `transition_table.h` (idempotence).
- Editing the manifest to change `STATE_PREHEAT + EVENT_PAN_REMOVED → STATE_NO_PAN` to `→ STATE_COOLDOWN` and regenerating changes the designated initializer for that cell — `git diff` shows the one-line change.
- Removing one transition row from the manifest causes the completeness check to fail for that `(state, event)` pair.

**Verification:** `python3 firmware/tools/gen_transition_table.py && python3 firmware/tools/gen_transition_table.py` — second invocation prints "transition_table.h up to date". The generated `transition_table.h` compiles with `#include` in a test C file.

---

### U4. Wire codegen into builds and commit `transition_table.h`

**Goal:** Both the host test build (`firmware/test/CMakeLists.txt`) and the ESP-IDF build (`firmware/CMakeLists.txt`) regenerate `transition_table.h` before compiling, and the generated file is committed as a versioned derived artifact.

**Requirements:** R3, R6

**Dependencies:** U3 (generator must exist)

**Files:**
- `firmware/test/CMakeLists.txt` (add custom command for `transition_table.h`, add dependency to `test_state_machine_only`)
- `firmware/CMakeLists.txt` (add custom command at project level for ESP-IDF build)
- `firmware/main/transition_table.h` (new — committed generated file, created by running the generator once)

**Approach:**

In `firmware/test/CMakeLists.txt`, after the existing `gen_config` target at line 109:

```cmake
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_SOURCE_DIR}/../main/transition_table.h
    MAIN_DEPENDENCY ${CMAKE_CURRENT_SOURCE_DIR}/../transition_table.yaml
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/state_machine.h
    COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/../tools/gen_transition_table.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/..
    COMMENT "Regenerating firmware/main/transition_table.h from transition_table.yaml"
    VERBATIM
)
add_custom_target(gen_transition_table DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../main/transition_table.h)
add_dependencies(test_state_machine_only gen_transition_table)
```

Run `python3 firmware/tools/gen_transition_table.py` once to create the initial `firmware/main/transition_table.h`, then commit it.

**Patterns to follow:** Existing `gen_config` custom command at `firmware/test/CMakeLists.txt:101-109`. The `DEPENDS` on `state_machine.h` is critical — it triggers regeneration on enum changes without manifest edits (R3 requirement).

**Test scenarios:**
- Touching `firmware/transition_table.yaml` and building `test_state_machine_only` regenerates `transition_table.h` and recompiles.
- Adding `X(STATE_WARMUP, "WARMUP")` to `STATE_LIST` and building causes the completeness check to fail — build error before compilation.
- Deleting `firmware/main/transition_table.h` and rebuilding recreates it.
- `git ls-files firmware/main/transition_table.h` lists the file as tracked.

**Verification:** `rm firmware/main/transition_table.h && cmake --build firmware/test/build` recreates it. `git diff --exit-code firmware/main/transition_table.h` after regeneration exits 0.

---

### Phase 3 — Test integration and CI

### U5. Wire `transition_table.h` into `test_transition_table_generated.c`

**Goal:** The generated test references the official transition table and adds cross-check assertions, replacing the hand-maintained Python `TRANSITIONS` list as the authoritative spec.

**Requirements:** R2, R5

**Dependencies:** U3 (table must exist), U4 (table committed)

**Files:**
- `firmware/test/gen_transition_table.py` (refactor — load YAML manifest instead of Python-inline `TRANSITIONS` list)
- `firmware/test/test_transition_table_generated.c` (regenerated)
- `firmware/main/transition_table.h` (included by the generated test file)

**Approach:**

In `gen_transition_table.py`:

1. **Delete** the `TRANSITIONS` list at lines 20-67.
2. **Add**: `def load_transitions_from_yaml():` that reads `firmware/transition_table.yaml` and returns the same `(from_state, event_name_str, expected_to, expected_fault_or_None, needs_fault_setup)` tuple list format that the downstream code generation functions expect. `needs_fault_setup` is True when `from == STATE_FAULT` (inferred from the YAML's `from` field — FAULT rows need a two-step test pattern per `test_transition_table_generated.c:256-269`).
3. The `EVENT_STUBS` dict at lines 74-116 **remains** — it maps event name strings to mock C code, which is implementation-specific.
4. The downstream functions `_c_table_rows()`, `_c_test_function()`, `_c_event_stubs()`, etc. are unchanged — they receive the same tuple list format.
5. The `generate_c_output()` function adds a new include: `#include "../main/transition_table.h"` and adds the cross-check assertion described in Key Technical Decisions above.

The `test_transition_table_generated.c` is regenerated by running `python3 firmware/test/gen_transition_table.py --generate` (existing command, now consuming the YAML manifest).

**Patterns to follow:** Existing function boundaries in `gen_transition_table.py` — the `TRANSITIONS` list is the only deleted element; the rest is additive.

**Test scenarios:**
- Running `python3 firmware/test/gen_transition_table.py --generate` produces `test_transition_table_generated.c` that includes `transition_table.h` and references the official table.
- `test_state_machine_only` builds and passes — all 30 rows match the official table.
- Changing a `to` field in `transition_table.yaml` without updating the expected value in the test causes the cross-check assertion to fail, naming the row and the two disagreeing values (official table vs. test runner expectation).
- Removing a transition row from the manifest causes `gen_transition_table.py`'s `load_transitions_from_yaml()` to return only legal rows — the generated test file has fewer rows, and the cross-check asserts the official table has valid (non-INVALID) entries for those rows.

**Verification:** `cmake --build firmware/test/build && ./firmware/test/build/test_state_machine_only` passes. `python3 firmware/test/gen_transition_table.py --check` validates the manifest against `state_machine.h` and exits 0.

---

### U6. Update CI workflow, `AGENTS.md`, and commit the generated files

**Goal:** CI regenerates `transition_table.h` and `git diff --exit-code`s; `AGENTS.md` documents the new regenerate-and-commit workflow.

**Requirements:** R6, R8

**Dependencies:** U4 (generated file committed), U5 (test references the official table)

**Files:**
- `.github/workflows/firmware-tests.yml` (add a "Regenerate transition table" step or extend the existing regenerate step)
- `AGENTS.md` (update the "Transition Table Regeneration" section)

**Approach:**

In `.github/workflows/firmware-tests.yml`, after the existing "Regenerate config.h and check drift" step (U9 of N8 plan), add:

```yaml
- name: Regenerate transition table and check drift
  run: |
    python3 firmware/tools/gen_transition_table.py
    git diff --exit-code firmware/main/transition_table.h
```

In `AGENTS.md`, replace the existing "Transition Table Regeneration" section with:

```
### Transition Table Regeneration

`firmware/main/transition_table.h` is generated from `firmware/transition_table.yaml`
by `firmware/tools/gen_transition_table.py`. After editing the manifest:

    python3 firmware/tools/gen_transition_table.py
    git add firmware/main/transition_table.h && git commit -m "chore: regenerate transition table"

CI regenerates and `git diff --exit-code`s against the committed copy.

`firmware/test/test_transition_table_generated.c` is also regenerated from the
same manifest via `firmware/test/gen_transition_table.py`. After manifest edits:

    python3 firmware/test/gen_transition_table.py --generate
    git add firmware/test/test_transition_table_generated.c
    git commit -m "test: regenerate transition table tests"
```

**Patterns to follow:** Existing "Firmware Config Codegen" section in `AGENTS.md` (added in N8 U6). Existing CI job structure in `.github/workflows/firmware-tests.yml`.

**Test scenarios:**
- Editing `transition_table.yaml` to change a transition target, committing only the manifest (not regenerating), and pushing causes CI to fail at the `git diff --exit-code` step.
- Editing `transition_table.yaml`, regenerating both files, and committing all three causes CI to pass.
- Adding `X(STATE_WARMUP, "WARMUP")` to `STATE_LIST` and pushing without updating the manifest causes the CI build to fail at the codegen step (completeness check in `gen_transition_table.py`).

**Verification:** The new CI step runs on `push` and `pull_request` with `paths: ['firmware/**']`. A test PR that edits the manifest without regenerating fails CI.

---

## System-Wide Impact

- **`firmware/main/state_machine.h`:** Gains `EVENT_LIST` X-macro (~23 lines), `event_t` enum, `EVENT_COUNT` sentinel, `event_name_table[]`, and `state_machine_get_event_string()` declaration. No existing declarations modified. The X-macro expansion patterns are identical to `STATE_LIST` and `FAULT_LIST`.
- **`firmware/main/state_machine.c`:** Gains `state_machine_get_event_string()` implementation (~8 lines, table walk over `event_name_table`). No existing handler logic changed — the transition table is a parallel spec, not a runtime replacement.
- **`firmware/main/transition_table.h`:** New file — generated, committed. Contains the `transition_table[STATE_COUNT][EVENT_COUNT]` and `transition_fault[STATE_COUNT][EVENT_COUNT]` arrays plus `_Static_assert` guards. No existing file modified.
- **`firmware/transition_table.yaml`:** New file — the SSOT manifest for every legal transition.
- **`firmware/tools/gen_transition_table.py`:** New file — the codegen script.
- **`firmware/tools/transition_table.h.j2`:** New file — the Jinja2 template.
- **`firmware/tools/requirements.txt`:** Unchanged — `jinja2` and `pyyaml` already pinned.
- **`firmware/test/gen_transition_table.py`:** Refactored — the `TRANSITIONS` list deleted; the script loads the YAML manifest instead.
- **`firmware/test/test_transition_table_generated.c`:** Regenerated — includes `transition_table.h`, adds cross-check assertions.
- **`firmware/test/CMakeLists.txt`:** Gains `add_custom_command` + `add_custom_target(gen_transition_table)` + `add_dependencies(test_state_machine_only gen_transition_table)`. The `gen_config` dependency already exists (lines 101-109, 146); the new one mirrors it.
- **`firmware/CMakeLists.txt`:** Gains the same custom command at the project level for ESP-IDF builds.
- **`.github/workflows/firmware-tests.yml`:** Gains one new step ("Regenerate transition table and check drift").
- **`AGENTS.md`:** Updated "Transition Table Regeneration" section.
- **Developer workflow:** A developer who adds a state to `STATE_LIST` and builds gets a codegen-time failure naming the 23 missing `(NEW_STATE, EVENT_*)` transitions — before compilation. A developer who adds an event to `EVENT_LIST` gets a similar failure naming the 8 missing `(STATE_*, NEW_EVENT)` transitions. A developer who edits the manifest to change a transition target must regenerate both `transition_table.h` (for the build) and `test_transition_table_generated.c` (for the tests) — CI catches a forgotten regeneration on either.

---

## Risk Analysis

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| 23 events × 8 states = 184 cells; the 154 `TRANSITION_INVALID` cells are implicitly zero-initialized, which is `STATE_INIT` (value 0) — a valid state, not the sentinel. The `TRANSITION_INVALID` sentinel `(system_state_t)(-1)` cannot be used because designated initializers can't set 154 unreachable array values. | Medium | High | **Compile-time:** The `_Static_assert` on `sizeof` catches stale dimensions but cannot catch per-cell `STATE_INIT` vs. real `STATE_INIT` transitions. **Codegen-time:** The Python completeness check catches missing manifest entries before compilation. **Test-time:** The test iterates legal transitions only (30 rows); it does not probe illegal cells. Only cells that are both missing from the manifest AND not caught by codegen could pass silently — this requires editing `gen_transition_table.py` to remove the completeness check. The `_Static_assert` dimensional guard catches the case where `STATE_COUNT` changes but the array literal doesn't. **Mitigation summary:** Three-layer defense — codegen validator (fastest fail), `_Static_assert` (catches enum mismatch), test (catches logic drift). |
| The `DEPENDS state_machine.h` on the custom command in CMake causes unnecessary regeneration when editing comments/whitespace in `state_machine.h`. | Low | Medium | The idempotent write in `gen_transition_table.py` (U4) ensures the output file content doesn't change when the manifest is unchanged — the CMake rule fires, the generator runs, the `.tmp` matches existing, no recompilation. Acceptable cost for correctness. |
| The 23-event list misses an event that triggers a transition implicitly (e.g., `NEAR_TARGET` in HEATING is a self-loop kept for PID, but other states might have implicitly-same-state transitions not in the manifest). | Medium | Low | Every explicit `transition_to()` call in `state_machine.c` corresponds to an event in the current 23-event list (verified by grep for `transition_to(` and cross-referencing with the existing `EVENT_STUBS` dict). Self-loops (transitions that don't call `transition_to()` because the state stays the same) are documented but not mechanically validated — the handler's `return` or `continue` without a `transition_to()` call is the implicit self-loop. If a future handler calls `transition_to(NEW_STATE)` for an event not in `EVENT_LIST`, the codegen doesn't catch it (no event enum value to cross-reference against) — the test catches it because the test runner fails to find the expected transition. |
| Memory cost of the 2D array on ESP32-S3: `STATE_COUNT * EVENT_COUNT * sizeof(system_state_t)` = 8 × 23 × 4 = 736 bytes for `transition_table` + 736 bytes for `transition_fault` = **1,472 bytes** of `.rodata`. | Low | Low | ESP32-S3 has 512 KiB of flash. 1.5 KiB is negligible. The table is `static const` and lives in `.rodata` (flash, not RAM). No runtime lookup of this table is implemented in N10 — the table is compile-time spec + test verification. Memory cost is zero at runtime (compiler may or may not strip unused `static const` data). If the table is later used for runtime dispatch, the flash cost is already accepted. |
| The `_Static_assert` fires on stale header but only when the enum dimensions change — not when a single cell value is wrong. | Low | Medium | The test (`test_state_machine_only`) catches wrong cell values at test time. The codegen validator catches missing cells at build time. The `_Static_assert` is one layer of three. |
| `gen_transition_table.py` in `firmware/test/` and `gen_transition_table.py` in `firmware/tools/` have similar names (same base name) — confusion risk. | Low | Low | `firmware/test/gen_transition_table.py` is the *test generator* (consumes the same manifest, produces `test_transition_table_generated.c`). `firmware/tools/gen_transition_table.py` is the *table generator* (consumes the manifest, produces `transition_table.h`). Documented in `AGENTS.md` with distinct commands. The test generator will eventually be renamed `gen_transition_table_test.py` in a follow-up cleanup — deferred. |

---

## Test Strategy

- **U1 (EVENT_LIST):** `test_state_machine_only` builds with no compile errors (no existing code references `event_t`). Manual verification that `EVENT_COUNT == 23` and `event_name_table[]` has 23 entries.
- **U2 (manifest):** `python3 -c "import yaml; yaml.safe_load(open('firmware/transition_table.yaml'))"` succeeds. Manual cross-reference against the existing `TRANSITIONS` list (30 rows → 30 YAML entries). The completeness validator (U3) confirms 0 missing `(state, event)` pairs.
- **U3 (codegen):** `python3 firmware/tools/gen_transition_table.py` exits 0 on the seeded manifest. Adding `X(STATE_WARMUP, ...)` to `STATE_LIST` without updating the manifest causes exit 1 with 23 `ERROR: (STATE_WARMUP, EVENT_*) has no transition row` messages. Adding `X(EVENT_NEW, ...)` to `EVENT_LIST` without updating the manifest causes exit 1 with 8 `ERROR: (STATE_*, EVENT_NEW) has no transition row` messages.
- **U4 (build wiring):** `rm firmware/main/transition_table.h && cmake --build firmware/test/build` recreates it and builds successfully. `cmake --build firmware/test/build` a second time is a no-op (codegen exits "up to date").
- **U5 (test integration):** `cmake --build firmware/test/build && ./firmware/test/build/test_state_machine_only` passes all 30 transition tests. The cross-check assertion passes (official table matches test expectations). Changing a `to` field in the manifest without regenerating the test causes a test failure naming the mismatch.
- **U6 (CI):** Pushing a commit that edits `transition_table.yaml` without regenerating `transition_table.h` causes the CI "Regenerate transition table and check drift" step to fail with a diff. Pushing a commit that regenerates both passes. Adding a state to `STATE_LIST` without updating the manifest causes the CI build to fail at the codegen step.
- **Regression:** No existing tests modified except `test_transition_table_generated.c` (regenerated from the same YAML source — behaviorally identical, plus the new cross-check assertion). `test_state_machine.c` and all other test files are untouched. The `test_transition_table()` function at `test_transition_table_generated.c:231` continues to exercise all 30 transitions via the same mock/force-state/apply-event/assert pattern.

---

## References

- `firmware/main/state_machine.h` — existing `STATE_LIST` X-macro (line 30), `FAULT_LIST` X-macro (line 61)
- `firmware/main/state_machine.c` — state handlers with inline `transition_to()` calls (lines 316–1009)
- `firmware/config.yaml` — existing YAML manifest pattern (lines 1–169)
- `firmware/tools/gen_config.py` — existing codegen script pattern (lines 1–58)
- `firmware/tools/config.h.j2` — existing Jinja2 template pattern (lines 1–199)
- `firmware/test/gen_transition_table.py` — existing test generator (to be refactored, lines 1–565)
- `firmware/test/test_transition_table_generated.c` — existing generated test (lines 1–361)
- `firmware/test/CMakeLists.txt` — host test build with `gen_config` custom command pattern (lines 101–109, 132–146)
- `AGENTS.md` — existing "Transition Table Regeneration" documentation (to be updated)
- `.github/workflows/firmware-tests.yml` — CI workflow (to be extended, created in N8 U9)
- `docs/plans/2026-06-22-008-feat-firmware-ssot-codegen-plan.md` — N8 plan (X-macro enums, config codegen)
