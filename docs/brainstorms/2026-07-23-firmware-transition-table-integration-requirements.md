---
date: 2026-07-23
topic: firmware-transition-table-integration
---

# Firmware Transition Table Integration: Using the Generated Table at Runtime

## Summary

The firmware's `transition_table.h` (492 lines, generated from `transition_table.yaml`) defines a complete 2D lookup table of valid state transitions across 9 states and 23 events -- but this table is only validated in tests (`test_transition_table_generated.c`). The runtime state machine in `state_machine.c` (556 lines) uses manual `switch`-based dispatch and explicit `transition_to()` calls inside each state handler. This creates a specification-implementation disconnect: the generated table says "STATE_PREHEAT + EVENT_TEMP_REACHED -> STATE_HEATING" but the runtime code must independently and manually implement this transition in `state_preheat_update()`. Align the runtime to query the generated table, eliminating the possibility of spec-code drift.

---

## Problem Frame

The firmware state machine has two independent representations of the same state graph:

**Representation 1: Generated transition table** (`transition_table.h`)
- Declares a `static const system_state_t transition_table[STATE_COUNT][EVENT_COUNT]` using C99 designated initializers
- Only explicitly-declared transitions are set; all others are `TRANSITION_INVALID`
- A parallel `transition_fault[STATE_COUNT][EVENT_COUNT]` gives the fault code for each transition
- Validated at compile time via `_Static_assert` on dimensions
- Auto-generated from `transition_table.yaml` -- the single source of truth

**Representation 2: Manual switch dispatch** (`state_machine.c`, `state_handlers.c`)
- `state_machine_update()` calls the current state's update function via `switch (sm_ctx.current_state)`
- Each state handler (e.g., `state_preheat_update()`) manually calls `transition_to(NEXT_STATE)` based on its own internal logic
- The transition logic is spread across 9 state handler functions in `state_handlers.c` (687 lines)
- `check_safety_interlocks()` is currently called from within `state_preheat_update()` and `state_heating_update()` only (state_handlers.c:298, 402), not globally from `state_machine_update()`. This means safety checks only run during PREHEAT and HEATING -- not during IDLE, PAN_DET, NO_PAN, or COOLDOWN. The refactored architecture moves these checks to `state_machine_update()` as a pre-handler gate, which is a behavioral change that broadens safety coverage.

**The consequences of this split:**

1. **Drift risk.** A developer edits `transition_table.yaml` to add a new transition from PREHEAT to FAULT on event `PROBE_SHORT`, re-runs `gen_transition_table.py`, and commits. The generated table is correct. But the runtime code in `state_preheat_update()` doesn't check for `PROBE_SHORT` because safety events are handled globally in `check_safety_interlocks()`. The table says the transition exists; the code may or may not trigger it depending on where the safety check runs in the 100Hz loop.

2. **Redundant test effort.** `test_transition_table_generated.c` (384 lines) validates the table for consistency (no invalid states, no duplicate entries, all states reachable). `test_state_machine.c` (1,657 lines) independently validates the runtime behavior by driving events and checking state transitions. Both test suites encode the same knowledge but cannot catch each other's errors.

3. **No single place to answer "what happens when...".** To determine the system's response to `EVENT_PAN_REMOVED` during `STATE_HEATING`, a developer must: check the generated table (which says `STATE_NO_PAN`), check `state_heating_update()` (which implements a debounce counter and transition), and check `check_safety_interlocks()` (which may preempt with a fault). Three code locations for one behavioral question.

4. **The generated table is dead weight at runtime.** It occupies flash memory (492 lines of designated initializers compiles to a binary lookup table) but is never queried by the running firmware. It exists purely as a test artifact and documentation.

---

## Requirements

### Runtime Integration

- **R1.** The state machine determines the next state by querying `transition_table[current_state][event]` rather than by manually calling `transition_to()` inside state handlers.
- **R1a.** When `transition_table[current_state][event]` returns `TRANSITION_INVALID`, the state machine MUST enter STATE_FAULT with fault code FAULT_INVALID_TRANSITION, call `assert_hardware_fault_cut()`, and log the (state, event) pair to EEPROM for post-mortem analysis.
- **R2.** State handlers become pure "update loops" that detect events and return them, rather than detecting events and calling `transition_to()`. Example: `state_heating_update()` returns `EVENT_PAN_REMOVED` (or `EVENT_NONE`). The state machine core queries `transition_table[STATE_HEATING][EVENT_PAN_REMOVED]` to get `STATE_NO_PAN` and executes the transition.
- **R2a.** Each state handler's update function SHALL check event conditions in descending priority order and return the first matching event. The priority order for each state SHALL be documented in a comment at the top of the handler function.
- **R3.** Safety events (over-temp, IGBT short, over-current, fan failure, RTD open/short, ADC stuck) remain preemptive -- `check_safety_interlocks()` returns a safety event before the state handler runs, and the transition table maps that event to `STATE_FAULT` or `STATE_RUNAWAY_FAULT`. The preemption semantics don't change, only the lookup mechanism.
- **R3a.** External fault injection paths (`state_machine_report_rtd_device_fault`) assert the hardware fault cut in the caller's context, then enqueue a safety event for the next `state_machine_update()` cycle to dispatch through the transition table. This keeps the hardware cut atomic while routing the state change through the table.
- **R3b.** All safety preemption checks (`check_runaway_boundary` and `check_safety_interlocks`) execute before the `message_pending` early-return. No UI or message state may delay safety fault detection.
- **R3c.** `check_safety_interlocks()` runs only when the current state is in the power-active set: `STATE_PREHEAT`, `STATE_HEATING`. For all other states, safety interlock checks are skipped. The pre-handler call still gates on power-active states, preserving existing behavior while centralizing the check location.
- **R3d.** Upon detecting any safety event, `assert_hardware_fault_cut()` MUST be called before any state transition processing. The refactored `check_safety_interlocks()` must trigger hardware shutdown within the same function call that detects the fault, not after returning to the dispatch loop. The event return and table lookup are for software state tracking only; hardware protection is immediate and atomic.
- **R3e.** `check_runaway_boundary()` retains its direct preemptive path: it asserts `assert_hardware_fault_cut()` and calls `transition_to(STATE_RUNAWAY_FAULT)` directly, bypassing the transition table. Runaway is a hardware-latched condition that must never be gated on table validity. This is an explicit carve-out from R1.
- **R3f.** For safety events where the fault code depends on sensor reading magnitude (e.g., `FAULT_OVER_CURRENT` at 35A vs `FAULT_IGBT_SHORT` at 50A), split into distinct events: `EVENT_OVER_CURRENT` and `EVENT_IGBT_SHORT`. The YAML manifest declares both with appropriate fault codes. `check_safety_interlocks()` returns the correct event based on the current threshold comparison.

### State Entry/Exit Handlers

- **R4.** `transition_to()` is refactored to: (a) look up the next state from `transition_table[current_state][event]`, (b) call the exit handler via `state_exit[previous_state]()`, (c) call the entry handler via `state_entry[next_state]()`, (d) update `current_state`. No switch statement remains. Exit handlers are new functionality previously not implemented in the existing `transition_to()`.
- **R4a.** When `transition_table[current][event] == current` (self-loop), `transition_to()` skips exit/entry handler calls. Only timing fields are updated.

### Test Consolidation

- **R5.** `test_transition_table_generated.c` validates the generated table for structural correctness (no invalid states, all states reachable, per-state coverage). This test doesn't change -- the generated table is still the single source of truth.
- **R6.** `test_state_machine.c` switches from testing "does heating state transition to no-pan on pan removal?" to testing "does heating state's update function detect pan removal and return the correct event?" and "does the transition table map EVENT_PAN_REMOVED + STATE_HEATING to STATE_NO_PAN?" This separates "event detection" testing from "transition mapping" testing.
- **R7.** Add a property-based test (or exhaustive enumeration) that verifies: for every cell in the transition table, the corresponding state handler's update function CAN produce the event that triggers that transition. This catches the case where the table says `STATE_X + EVENT_Y -> STATE_Z` but `state_X_update()` never returns `EVENT_Y`.

### Code Generation Improvements

- **R8.** `gen_transition_table.py` generates the entry/exit handler function pointer arrays alongside the transition table. The YAML manifest already declares states and events; adding handler function names is a natural extension.
- **R9 [OPTIONAL].** `transition_describe(system_state_t from, system_event_t event)` returns a human-readable description by internally querying the table. For TRANSITION_INVALID cells, returns '<INVALID>'. Implementation is deferred if time does not permit. The core refactoring (R1-R7) takes priority.

### Non-Regression

- **R10.** All existing firmware tests pass with identical behavioral expectations. The runtime behavior of the state machine is unchanged -- only the internal dispatch mechanism changes.
- **R11.** Flash memory usage does not increase by more than 5%. The transition table already occupies flash; the function pointer arrays add a small fixed cost (STATE_COUNT * sizeof(function_ptr) ~ 72 bytes).

---

## Acceptance Examples

- **AE1. Covers R1, R2.** Given the state machine is in STATE_HEATING and `state_heating_update()` returns `EVENT_PAN_REMOVED`, the state machine queries `transition_table[STATE_HEATING][EVENT_PAN_REMOVED]`, gets `STATE_NO_PAN`, calls `state_heating_exit()`, calls `state_no_pan_enter()`, and sets `current_state = STATE_NO_PAN`. No state handler calls `transition_to()` directly.
- **AE2. Covers R6.** Given `test_state_machine.c` runs, it tests event detection (does `state_heating_update` detect pan removal?) separately from transition mapping (does the table say HEATING + PAN_REMOVED -> NO_PAN?). A bug in the table doesn't cause event-detection tests to fail, and a bug in event detection doesn't cause transition-mapping tests to fail.
- **AE3. Covers R7.** Given a PR adds a transition `STATE_NO_PAN + EVENT_NEAR_TARGET -> STATE_PREHEAT` to the YAML (incorrectly, since NO_PAN should never check temperature), but `state_no_pan_update()` never returns `EVENT_NEAR_TARGET`, the property-based test fails: "Table declares transition NO_PAN + NEAR_TARGET -> PREHEAT but state_no_pan_update never returns EVENT_NEAR_TARGET."

---

## Success Criteria

- `state_machine.c` has zero `transition_to()` calls inside state handler update functions -- all transitions go through the table
- `transition_to()` is reduced to: lookup table, call exit handler, call entry handler, update state -- no switch statement
- `test_state_machine.c` separates event-detection tests from transition-mapping tests
- The property-based test (R7) catches at least one spec-code drift bug during development
- Firmware flash usage delta <= 5%
- All 18 firmware test executables pass

---

## Scope Boundaries

- **In scope:** Changing the internal dispatch mechanism in `state_machine.c` and `state_handlers.c` to query the generated transition table at runtime. Updating tests to reflect the new separation of concerns. Extending code generation to produce handler function pointer arrays.
- **Out of scope:** Changing the state graph itself (adding/removing states or events). The YAML manifest defines the behavior; this refactor only changes how that behavior is executed.
- **Out of scope:** Changing the safety interlock mechanism (`check_safety_interlocks`, `check_runaway_boundary`). Safety checks remain preemptive regardless of dispatch mechanism.
- **In scope:** Restructuring where `check_safety_interlocks()` is called (from within PREHEAT/HEATING state handlers to a centralized pre-handler gate in `state_machine_update()`). Safety check logic and threshold values are unchanged. This is a call-site architecture change, not a safety mechanism change.
- **Out of scope:** Web UI changes beyond the debug description function (R10).
- **Out of scope:** Porting the state machine to a different architecture (e.g., event-driven RTOS primitives instead of the 100Hz polling loop). The polling loop stays.

---

## Test Migration Strategy

**Phase 1:** Add new transition-mapping-only tests (query the table directly, verify all declared transitions).

**Phase 2:** Refactor existing tests one state at a time, splitting detection from mapping assertions.

**Phase 3:** Remove old end-to-end transition tests once coverage parity is reached.

Estimated effort: ~3-5 days for full test migration.

---

## Key Decisions

- **State handlers return events, not target states.** Returning events rather than target states was chosen because a handler's job is environmental sensing, not graph topology. The table owns the topology. This separation means a handler can be reused in a different state graph without modification.
- **Safety events remain preemptive.** The 100Hz loop calls `check_safety_interlocks()` first; if a safety event fires, the state handler is skipped entirely and the transition table maps the safety event directly. This preserves the existing safety priority without requiring every state handler to duplicate safety checks.
- **Function pointer arrays over switch statements.** A `switch` in `transition_to()` grows linearly with state count and is a merge-conflict magnet. Function pointer arrays are constant-size, compiler-verifiable (missing entries are compile errors, not runtime bugs), and generated from the YAML.
- **Handler function names follow convention.** Handler function names are derived from the `state_<name>_enter/update/exit` naming convention. `gen_transition_table.py` emits `extern` declarations for each and `_Static_assert` compile-time checks that function pointers are non-null. If a naming convention violation is detected at compile time, the convention must be fixed -- no runtime fallback.

---

## Dependencies / Assumptions

- **Methodology.** All implementation follows TDD (Red-Green-Refactor per AGENTS.md) with an elevated safety bar: every transition table integration change is validated by property-based tests (Hypothesis, via the host build's C test harness) proving that the table-driven dispatch is equivalent to the original switch-based dispatch. Base cases: for each of the 9 states and each declared transition, verify the new dispatch produces the same next-state and fault-code as the old dispatch. Proof by induction: if all base cases hold for single transitions, and the event-detection logic is unchanged (only the dispatch mechanism changed), then any sequence of transitions produces identical behavior. The exhaustive 9x23=207 cell enumeration serves as the BMC (bounded model check) verification required by the CP-SAT Physics Constraint Discipline (R24) pattern. No runtime change ships without the 207-cell enumeration passing.
- **Assumption:** All state transitions are expressible as "current state + event -> next state" with optional fault code. If any transition has complex conditional logic (e.g., "go to STATE_X only if temperature < 50C, otherwise STATE_Y"), the table model needs extension. Current analysis suggests all transitions are unconditional -- conditional logic lives in event detection within state handlers.
- **Assumption:** The generated transition table and fault table are already correct (validated by `test_transition_table_generated.c`). This refactor does not change the table content, only how it's used.
- **Dependency:** `gen_transition_table.py` must be extended to generate the function pointer arrays. This is a ~30 line addition to an existing 219-line codegen script.
- **Dependency:** The C standard (C11) supports designated initializers and function pointers in `static const` arrays -- both used extensively already.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R2][User decision]** Should state handlers return `system_event_t` (the event enum) or a new `state_handler_result_t` that can represent "no event" and "internal state change" separately? Using `EVENT_NONE` for "no event" overloads the event enum with a non-event sentinel. A separate result type is cleaner but introduces a new type.
- **[Affects R8][Technical]** Does `gen_transition_table.py` already have access to state handler function names? The YAML manifest has `states:` entries; handler functions follow the naming convention `state_<name>_enter` and `state_<name>_update`. The codegen can either derive names from the convention or accept explicit function name fields in the YAML.

### Deferred to Planning

- **[Affects R7][Technical]** How is the property-based test (R7) implemented in C with the Unity framework? C doesn't have property-based testing libraries. Options: (a) exhaustive enumeration of all `STATE_COUNT * EVENT_COUNT` cells at test time (fast -- 9 * 23 = 207 cells), (b) a Python test that drives the C firmware via the host build and checks coverage, (c) manual test cases for each state's event detection.
- **[Affects R1][Technical]** Does the transition table lookup happen in `state_machine_update()` (centralized) or in a new `dispatch_event()` function? Centralized keeps the change minimal; a separate function is more testable.

---

## Notes

- **AGENTS.md state count discrepancy.** AGENTS.md currently says "8-state machine" but the firmware has 9 states (INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT, RUNAWAY_FAULT). This is a documentation-only issue in AGENTS.md, not blocking.
