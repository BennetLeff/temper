---
title: "Hardware-in-the-loop oracle - Plan"
type: feat
date: 2026-08-02
topic: hil-oracle
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R17)
---

# Hardware-in-the-loop oracle - Plan

## Goal Capsule

**Objective:** Move the state machine's validation off the host-only stub build and onto an emulated ESP-IDF target, driven by a golden transition-trace corpus that covers every (state, event) pair in the transition manifest.

**Product authority:** temper firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none at planning time. Execution depends on an emulated ESP-IDF target being runnable in this repo's CI (Assumption A2) and on the golden-trace corpus derivation in U1.

---

## Product Contract

### Summary

The state machine runs against golden transition traces on a non-host target, so the "every state/event pair is exercised" claim holds outside host-based tests. The golden corpus is derived from the transition manifest, not hand-written, and a coverage gate fails closed when any pair is missing.

### Problem Frame

Host-based tests compile `firmware/main/state_machine.c` with `firmware/test/state_machine_stubs.c` under `HOST_BUILD`, so the real ESP-IDF execution path (FreeRTOS scheduling, HAL drivers, timer semantics) is never exercised. The incident class this idea exists for: firmware behavior that only diverges on the real target (timing, driver interaction, interrupt preemption) ships because every gate ran on the host. The oracle closes the gap by replaying manifest-derived golden traces on an emulated ESP-IDF target, with the manifest as the expected-state oracle.

### Requirements

- R17. Hardware-in-the-loop oracle (Oracle / Firmware / P2): the state machine runs on real or emulated hardware against golden transition traces — every state/event pair is exercised outside host-based tests.
  - **Success signal:** for every (state, event) row in the transition manifest, a golden trace exists and replays on a non-host target to the manifest's expected (state, fault); the coverage gate fails when any row is missing or unexercised.

### Key Technical Decisions

- KTD1. **Golden corpus is generated from the manifest.** Each manifest row becomes a scenario whose plant-model CSV reaches the `from` state and then perturbs sensors to fire the `event`; the event-forcing knowledge already encoded in `firmware/test/gen_transition_table.py` (event stubs and per-state preconditions) is reused rather than re-derived.
- KTD2. **The first non-host target is an emulated ESP-IDF build (QEMU), not real hardware.** No functional board exists (see Sources), so emulation is the only non-host target available today; the replay harness is written against a target abstraction so a real board can substitute later.
- KTD3. **The manifest is the expected-state oracle.** The replay harness compares observed (state, fault) against the manifest row, never against hand-asserted expectations, so the oracle cannot drift from the spec.
- KTD4. **Trace invariants are preflighted before replay.** The pre-perturbation invariant checker pattern from `firmware/test/test_sil_fault_injection.c` (`check_trace_invariants`) is reused so a trace that would trip a spurious fault is reported, not silently replayed.

### Assumptions

- A1. **Seed discrepancy:** the portfolio seed `firmware/test/build/test_state_machine_only` is a build artifact, not source. The plan anchors on what the binary exercises: `firmware/test/test_state_machine.c`, `firmware/test/test_transition_table_generated.c`, and `firmware/test/state_machine_stubs.c`.
- A2. **Emulated target runnable:** an ESP-IDF build for an emulated ESP32-S3 target (QEMU) is assumed runnable in CI. If the ESP32-S3 machine is unavailable, the harness targets the closest available ESP-IDF emulated target and the discrepancy is reported, not hidden.
- A3. **The transition manifest is the coverage authority:** the 9 states and 23 events in `firmware/transition_table.yaml` define "every state/event pair" (the portfolio's "8-state" wording predates `STATE_RUNAWAY_FAULT`).
- A4. **Portfolio R7's success-signal field** is satisfied by the idea text's outcome clause; no separate signal was published for R17.

---

## Implementation Units

### U1. Golden-trace corpus generator

**Goal:** A generator that emits one golden scenario (manifest entry + plant-model CSV) per (state, event) manifest row, with a coverage assertion that the scenario set equals the manifest row set.

**Requirements:** R17

**Dependencies:** none

**Files:**
- `firmware/test/golden_traces/generate_golden_traces.py` (new)
- `firmware/test/golden_traces/manifest.json` and `firmware/test/golden_traces/traces/*.csv` (generated output)
- `firmware/test/test_golden_trace_generator.py` (new, host pytest)

**Approach:** Reuse the row-to-event-forcing knowledge in `firmware/test/gen_transition_table.py`: the per-state preconditions and event stubs already define how to reach each `from` state and fire each `event`. Each scenario encodes that knowledge as a sensor trajectory CSV (columns: tick, heatsink temp, pan temp, dc current, rtd, pan impedance, fan running — the format already parsed by `firmware/test/test_sil_fault_injection.c`) plus a manifest entry with the manifest row's expected state and fault. The generator fails loudly on any row with no event-forcing recipe instead of emitting a vacuous trace.

**Patterns to follow:** `firmware/test/test_codegen_tools.py` (host pytest for codegen), the trace CSV format and `traces/manifest.json` schema from `firmware/test/test_sil_fault_injection.c`, the `(state, event) → expected` row shape from `firmware/test/gen_transition_table.py`.

**Test scenarios:**
1. Happy path: for row `(STATE_PREHEAT, EVENT_OVER_TEMP)` the generator emits a scenario whose trace holds preheat conditions (pan present, nominal sensors) then perturbs heatsink temperature to 105.0 °C; the manifest entry expects `STATE_FAULT` with `FAULT_OVER_TEMP`.
2. Edge case: row `(STATE_HEATING, EVENT_NEAR_TARGET)` (self-loop) yields a scenario whose expected outcome is `STATE_HEATING` — the trace must not falsely exit HEATING.
3. Edge case: row `(STATE_RUNAWAY_FAULT, EVENT_FAULT_RESET_PERSISTS)` (dead-end) yields a scenario asserting `STATE_RUNAWAY_FAULT` persists.
4. Error path: a manifest row whose event has no forcing recipe fails generation with the row named, rather than emitting an empty trace.
5. Coverage: the generator fails when any manifest row lacks a scenario or any scenario duplicates a row.

**Verification:** Host pytest on `firmware/test/test_golden_trace_generator.py` passes; regenerating the corpus produces exactly one scenario per manifest row; the generated corpus round-trips through the existing CSV loader.

### U2. Target-independent replay harness

**Goal:** Extract the trace-replay loop from the SIL test into a replay core that host and emulated targets both drive, and prove host parity: every golden scenario replays on the host state machine to the manifest's expected (state, fault).

**Requirements:** R17

**Dependencies:** U1

**Files:**
- `firmware/test/replay_core.c` and `firmware/test/replay_core.h` (new, refactored out of `firmware/test/test_sil_fault_injection.c`)
- `firmware/test/state_machine_stubs.c` (host plant model, reused)
- `firmware/test/test_replay_parity.c` (new, Unity host test)
- `firmware/test/CMakeLists.txt` (add the parity target)

**Approach:** Split scenario loading (manifest + CSV parsing) and the tick loop (set sensors, advance time, call update, observe state) from the target binding. The host binding uses the existing `mock_sm_*` API; the emulated binding (U3) supplies the same probes. The parity test replays the full golden corpus on the host and asserts every scenario matches its manifest row.

**Patterns to follow:** The replay loop and trace-invariant preflight in `firmware/test/test_sil_fault_injection.c`; the `mock_sm_*` probe API in `firmware/test/state_machine_stubs.c`; the Unity target pattern in `firmware/test/CMakeLists.txt`.

**Test scenarios:**
1. Happy path: host replay of every golden scenario yields the manifest's expected (state, fault).
2. Error path: a scenario whose trace violates a pre-perturbation invariant (heatsink over 100.0 °C, pan over 300.0 °C, current over 35.0 A, fan off, RTD out of the staged guard window) is reported with the violation before replay.
3. Integration: host latency per scenario is recorded as the host baseline, so the emulated target's latency delta is reportable rather than silently absorbed.

**Verification:** The new Unity parity target builds and passes inside the host test build; `ctest --test-dir firmware/test/build` includes the parity test.

### U3. Emulated-target runner

**Goal:** Run the golden corpus on an emulated ESP-IDF target — the first execution of the state machine outside host-based tests — and compare observed outcomes to the manifest oracle.

**Requirements:** R17

**Dependencies:** U1, U2

**Files:**
- `firmware/components/test/plant_model.c` and `firmware/components/test/plant_model.h` (new, trace-driven plant model compiled only into the emulated test build)
- `scripts/run_emulated_golden_traces.py` (new runner)
- `firmware/test/build/emulated-report.json` (generated report)

**Approach:** Build the ESP-IDF binary for the emulated target (per `firmware/README.md`'s `idf.py` flow) with the trace-driven plant model bound to the same probes the host replay core uses. The runner boots the emulator once, feeds each golden scenario's CSV, collects observed (state, fault, latency), and compares against the manifest oracle. The runner exits nonzero unless every scenario ran and matched. Timing drift versus the host baseline is reported as a delta.

**Patterns to follow:** The CSV replay loop from `firmware/test/test_sil_fault_injection.c`; the ESP-IDF build layout in `firmware/CMakeLists.txt` and `firmware/README.md`; the run-and-report shape of existing CI runner scripts under `scripts/`.

**Test scenarios:**
1. Smoke: a single scenario (`STATE_INIT` + `EVENT_SELFTEST_PASS` → `STATE_IDLE`) replays on the emulated target and reaches `STATE_IDLE`.
2. Happy path: each fault scenario reaches its manifest state and fault code on the emulated target.
3. Edge case: emulated latency differing from the host baseline is emitted as a measured delta in the report, not treated as pass or fail.
4. Coverage: the runner's report asserts every manifest row was exercised on the emulated target; a scenario run only on host is reported as a coverage gap.

**Verification:** `scripts/run_emulated_golden_traces.py` exits 0 only with 100% row coverage and all manifest-oracle matches; `firmware/test/build/emulated-report.json` records per-row verdicts.

### U4. CI coverage gate

**Goal:** Wire the emulated run and a coverage check into CI so the "every state/event pair outside host tests" claim is enforced on every firmware change.

**Requirements:** R17

**Dependencies:** U2, U3

**Files:**
- `.github/workflows/firmware-tests.yml` (extend, or add `.github/workflows/firmware-hil.yml`)
- `scripts/check_golden_trace_coverage.py` (new coverage gate)

**Approach:** The coverage gate parses the emulated report and the transition manifest, and fails when any manifest row lacks a golden scenario or any scenario did not run on the emulated target. The emulated job is added to the firmware CI path; its failure is reported as a normal check failure (branch protection remains advisory until the repo enables it, per the Sources handoff).

**Patterns to follow:** The drift-check shape of the codegen steps in `.github/workflows/firmware-tests.yml`; the check-script convention and `scripts/manifest.yaml` entry requirement.

**Test scenarios:**
1. Happy path: a report with 100% row coverage passes the gate.
2. Error path: a manifest row added without a golden scenario fails the gate naming the row.
3. Error path: a scenario present in the corpus but marked host-only fails the gate.

**Verification:** The coverage gate runs in CI on the firmware path and fails closed on any coverage gap; the gate script has a `scripts/manifest.yaml` entry per the repo's script convention.

---

## Verification Contract

- Host build and tests: `cmake -B firmware/test/build firmware/test`, `cmake --build firmware/test/build`, then `ctest --test-dir firmware/test/build` (per AGENTS.md's host test flow).
- Generator and gate: host pytest for `firmware/test/test_golden_trace_generator.py` and the coverage gate's unit tests.
- Emulated oracle: `scripts/run_emulated_golden_traces.py` exits 0 only with 100% manifest-row coverage and all manifest-oracle matches.
- CI: the firmware workflow runs the host parity target, the emulated runner, and the coverage gate.

## Definition of Done

- U1's generator emits exactly one golden scenario per manifest row and fails on uncovered rows.
- U2's host parity target passes for the full corpus.
- U3's emulated runner executes the full corpus on the emulated target with 100% row coverage and matching manifest oracle.
- U4's coverage gate runs in CI and fails closed on gaps.
- The generated corpus and runner report are committed artifacts; no scratch replay code is left in the diff.
- Abandoned-attempt code from emulator bring-up is removed before landing.

---

## Scope Boundaries

- The emulated target is the shipped non-host target; real hardware is deferred (no functional board exists — see Sources).
- Fault injection beyond trace perturbations is outside this plan (owned by R41).
- Test-mode firmware with fault-injection hooks is outside this plan (owned by the move-3 plan in Sources).
- Timing-precision claims (e.g., OCP trip times) are outside this plan; the emulated oracle reports state and latency, not microseconds.

### Deferred to Follow-Up Work

- Real-hardware target binding for the replay harness once a functional board exists.
- Full-operator golden-trace mutation (perturbing traces themselves) — a later hardening pass.
- A QEMU CI job if the emulated run exceeds the firmware workflow's runtime budget — the coverage gate stays, the runner moves to a scheduled workflow.

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — R17, Key Flows F1, R7/R8 seed and success-signal conventions.
- `firmware/test/test_sil_fault_injection.c` — trace replay loop, CSV format, invariant preflight.
- `firmware/test/gen_transition_table.py` — event stubs and per-state preconditions reused by the corpus generator.
- `firmware/test/traces/manifest.json` — existing SIL scenario schema.
- `firmware/test/state_machine_stubs.c` — the `mock_sm_*` probe API.
- `firmware/test/CMakeLists.txt` and `firmware/README.md` — host test targets and the ESP-IDF `esp32s3` build flow.
- `.github/workflows/firmware-tests.yml` — the CI path the emulated job extends.
- `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` — board/fab state justifying emulation over real hardware, and advisory-gate status.
- `docs/plans/2026-07-24-003-feat-firmware-hardware-validation-track-plan.md` — move-3 scope boundary (test-mode firmware, bench evidence) this plan does not overlap.

---
