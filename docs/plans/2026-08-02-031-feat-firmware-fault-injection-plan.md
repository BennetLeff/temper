---
title: "Firmware fault injection - Plan"
type: feat
date: 2026-08-02
topic: firmware-fault-injection
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R41)
---

# Firmware fault injection - Plan

## Goal Capsule

**Objective:** Demonstrate, not review, the state machine's safety behavior: every safety-relevant fault class is injected into the running state machine — from the states where the manifest defines it — and the machine must reach the designed safe state within the designed latency, with power-off and fault-logging asserted as hard checks.

**Product authority:** temper firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none at planning time. The existing SIL suite (see Sources) already delivers the injection substrate; this plan enriches it.

---

## Product Contract

### Summary

Sensor faults and timing violations are injected into the running state machine and each must drive it to the designed safe state from the manifest. The existing SIL machinery is extended to cover every safety fault class from every designed origin state, and the currently-soft power-off and EEPROM-logging assertions become hard checks.

### Problem Frame

The incident class this idea exists for: safety behavior that is demonstrated in review (code reading, "the fault handler calls shutdown") but never shown to fire under injection. A fault path that exists in the source but is unreachable, mis-timed, or mis-wired from a specific state ships as reviewed-safe. The SIL suite already replays perturbed plant-model traces against the real state machine and asserts state, fault, and latency — but it covers a subset of fault classes, injects mostly from one origin trajectory, and treats power-off and fault logging as warnings. This plan closes those gaps so safety behavior is demonstrated under injection for every class.

### Requirements

- R41. Firmware fault injection (Injection / Firmware / P2): sensor faults and timing violations are injected into the running state machine and it must reach the designed safe state — safety behavior is demonstrated, not reviewed.
  - **Success signal:** for every safety fault class with a manifest path, an injected fault (sensor or timing) drives the running state machine to the designed safe state within the designed latency, with power disabled and the fault logged — asserted by tests, not review.

### Key Technical Decisions

- KTD1. **The existing SIL machinery is the injection vehicle.** `firmware/test/test_sil_fault_injection.c` plus `firmware/test/traces/manifest.json` already replay perturbed plant-model traces against the real `firmware/main/state_machine.c`; this plan extends that suite instead of building a parallel one.
- KTD2. **The manifest defines the designed safe state per injection.** Each injection's expected (state, fault) comes from the transition manifest (fault rows target `STATE_FAULT` with the named code; the interlock targets `STATE_RUNAWAY_FAULT`), so "designed safe state" is not re-asserted by hand.
- KTD3. **Power-off and fault-logging assertions become hard.** The soft-assertion fields in the SIL manifest schema (`power_off`, `eeprom_logged`) are promoted to hard assertions using the existing probe API (`mock_sm_get_pwm_disable_count`, `mock_sm_get_pll_enabled`, `mock_sm_get_power_level`, `mock_sm_get_last_logged_fault`).
- KTD4. **Coverage is a matrix over (fault class, origin state).** Each fault class is injected from every state from which the manifest defines a fault path for it; the coverage report names uncovered pairs, and zero uncovered pairs is a gate condition.

### Assumptions

- A1. **Seed resolves:** the portfolio seed `firmware/test/test_state_machine_only` exists as a build artifact; the injection substrate it anchors (`firmware/test/test_sil_fault_injection.c`, `firmware/test/state_machine_stubs.c`, `firmware/test/traces/manifest.json`) is the machinery this plan extends.
- A2. **The designed safe state for recoverable faults is `STATE_FAULT` with the named code; for the runaway interlock it is `STATE_RUNAWAY_FAULT`.** This follows the manifest's fault rows and the interlock in `firmware/main/state_machine.c`.
- A3. **Latency is asserted in ticks** (the existing SIL schema's `max_latency_ticks`), not microseconds; microsecond timing claims belong to the move-3 bench track.
- A4. **Portfolio R7's success-signal field** is satisfied by the idea text's outcome clause; no separate signal was published for R41.

---

## Implementation Units

### U1. Fault-class and origin-state coverage expansion

**Goal:** Extend the SIL scenario set so every safety fault class with a manifest path is injected from every designed origin state, with a coverage report over (fault class, origin state) pairs.

**Requirements:** R41

**Dependencies:** none

**Files:**
- `firmware/test/traces/manifest.json` (extended)
- `firmware/test/traces/trace_*.csv` (new perturbed traces)
- `firmware/test/test_sil_fault_injection.c` (extended origin-state handling)
- `firmware/test/test_sil_coverage.py` (new coverage check)

**Approach:** Enumerate the safety fault classes from the fault list and the manifest fault rows: over-temp, over-current, IGBT short, fan failure, probe open, probe short, thermal runaway, ADC stuck, cooldown overheat, self-test failed, runaway boundary (absolute and rate), watchdog reset, and pan-detect hardware. For each, add scenarios injecting from every origin state where the manifest defines the fault path (preheat, heating, cooldown, and the interlock's any-state reach). The boilerplate-to-origin helper in the SIL runner is generalized to reach each origin state, not only HEATING. The coverage check parses the manifest and the scenario set and fails on any uncovered (fault class, origin state) pair.

**Patterns to follow:** The scenario schema and replay loop in `firmware/test/test_sil_fault_injection.c`; the boilerplate helper pattern; the trace-invariant preflight that keeps perturbed traces from tripping spurious faults.

**Test scenarios:**
1. Happy path: over-temp injected from HEATING reaches `STATE_FAULT` with `FAULT_OVER_TEMP` within the latency bound.
2. Edge case: cooldown-overheat injected from COOLDOWN reaches `STATE_FAULT` with `FAULT_COOLDOWN_OVERHEAT` (welded-relay class).
3. Edge case: the runaway absolute-temperature injection reaches `STATE_RUNAWAY_FAULT` with `FAULT_RUNAWAY_BOUNDARY`.
4. Error path: the coverage check fails when a scenario is missing for a manifest-defined (fault class, origin state) pair, naming the pair.
5. Coverage: self-test-failed injection from INIT reaches `STATE_FAULT` with `FAULT_SELF_TEST_FAILED`.

**Verification:** The extended SIL target builds and passes; the coverage check reports zero uncovered (fault class, origin state) pairs.

### U2. Safe-state assertion hardening

**Goal:** Promote the SIL soft assertions to hard checks: every fault scenario must assert power-off and fault logging, not warn.

**Requirements:** R41

**Dependencies:** U1

**Files:**
- `firmware/test/test_sil_fault_injection.c` (hard-assertion logic)
- `firmware/test/traces/manifest.json` (assertion flags per scenario)
- `firmware/test/state_machine_stubs.c` (probe API, reused)

**Approach:** For every fault scenario, hard-assert the safe-state side effects using the existing probes: the power stage is disabled (`mock_sm_get_pwm_disable_count` incremented and `mock_sm_get_pll_enabled` false or `mock_sm_get_power_level` zero) and the fault is logged (`mock_sm_get_last_logged_fault` equals the manifest fault). A scenario reaching the right state without the power-off side effect fails the run.

**Patterns to follow:** The probe API in `firmware/test/state_machine_stubs.c`; the soft-assertion schema in `firmware/test/traces/manifest.json`; the fail-with-message style of the SIL runner's existing assertions.

**Test scenarios:**
1. Happy path: every existing fault scenario passes with the hardened power-off and fault-log assertions.
2. Error path: a scenario that reaches `STATE_FAULT` but fails to call the power-disable path fails the run with the missing side effect named.
3. Error path: a scenario whose logged fault differs from the manifest fault fails the run.

**Verification:** The SIL target passes with hard assertions on every scenario; a deliberately weakened stub (no power-disable) makes the run fail, proving the assertions bite.

### U3. Timing-violation injection

**Goal:** Inject timing violations — timeout events, message-drain timing, and latency bounds — and assert the machine reaches the designed state within the manifest-derived latency.

**Requirements:** R41

**Dependencies:** U1

**Files:**
- `firmware/test/traces/manifest.json` (timing scenarios)
- `firmware/test/traces/trace_timeout_*.csv` (new timing traces)
- `firmware/test/test_sil_fault_injection.c` (timing assertion path)

**Approach:** Add timing scenarios that advance time across the manifest's timeout boundaries: pan-detect timeout, preheat timeout, no-pan timeout, and the cooldown window. Each asserts the manifest's target state (e.g., `EVENT_PAN_TIMEOUT` → `STATE_IDLE`, `EVENT_PREHEAT_TIMEOUT` → `STATE_FAULT` with `FAULT_THERMAL_RUNAWAY`). Latency-bound scenarios assert the observed tick latency stays within `max_latency_ticks` for the sensor-fault classes, using the existing latency accounting.

**Patterns to follow:** The time-advance patterns in `firmware/test/gen_transition_table.py` event stubs (timeout forcing) and the SIL runner's latency accounting; the timing-forcing values documented in `firmware/config.yaml` (`PAN_DETECT_TIMEOUT_MS`, `MAX_PREHEAT_TIME_MS`, `NO_PAN_TIMEOUT_MS`).

**Test scenarios:**
1. Happy path: advancing past `MAX_PREHEAT_TIME_MS` from PREHEAT reaches `STATE_FAULT` with `FAULT_THERMAL_RUNAWAY`.
2. Happy path: advancing past `PAN_DETECT_TIMEOUT_MS` from PAN_DET reaches `STATE_IDLE`.
3. Edge case: an injection slower than `max_latency_ticks` fails the latency assertion with the measured latency.
4. Error path: a timing scenario whose trace violates a pre-perturbation invariant is reported before replay (reuse of the invariant preflight).

**Verification:** The timing scenarios pass within their latency bounds; a latency-bound mutation (lowered bound) makes the run fail, proving the assertion bites.

### U4. CI wiring and coverage gate

**Goal:** Run the full injection suite in CI with the coverage matrix as a gate condition.

**Requirements:** R41

**Dependencies:** U1, U2, U3

**Files:**
- `.github/workflows/firmware-tests.yml` (extend the existing SIL step)
- `scripts/check_sil_coverage.py` (new coverage gate, with `scripts/manifest.yaml` entry)
- `firmware/test/test_sil_coverage.py` (moved into or aligned with the gate)

**Approach:** Extend the existing SIL CI step to run the expanded suite and the coverage gate. The gate fails on any uncovered (fault class, origin state) pair, on any scenario whose hard assertions were skipped, or on any latency violation.

**Patterns to follow:** The existing SIL step in `.github/workflows/firmware-tests.yml`; the gate-script convention and `scripts/manifest.yaml` entry requirement.

**Test scenarios:**
1. Happy path: the expanded suite passes and the coverage gate reports zero uncovered pairs.
2. Error path: a new fault class added to the fault list without a scenario fails the gate naming the class.
3. Error path: a scenario with a soft-only assertion (hard check skipped) fails the gate.

**Verification:** The CI step runs the expanded SIL suite and the coverage gate on the firmware path; both scripts carry `scripts/manifest.yaml` entries.

---

## Verification Contract

- Host build and tests: `cmake -B firmware/test/build firmware/test`, `cmake --build firmware/test/build --target test_sil_fault_injection`, then `ctest --test-dir firmware/test/build -R sil_fault_tests --output-on-failure` (the existing SIL CI invocation, extended).
- Coverage gate: `scripts/check_sil_coverage.py` exits 0 only with zero uncovered (fault class, origin state) pairs.
- Hard-assertion proof: a deliberately weakened stub makes the suite fail (documented in U2's scenarios).
- CI: the firmware workflow runs the expanded suite and the gate.

## Definition of Done

- U1's scenario set covers every safety fault class from every designed origin state, with zero uncovered pairs.
- U2's hard assertions make power-off and fault-logging failure conditions, not warnings.
- U3's timing scenarios cover the manifest's timeout boundaries and latency bounds.
- U4's CI gate fails closed on coverage gaps, skipped hard assertions, or latency violations.
- No scratch injection code is left in the diff; the extended manifest and traces are the committed artifacts.

---

## Scope Boundaries

- Injection is host-based (the running state machine under `HOST_BUILD`); real-hardware and emulated-target injection is owned by R17's HIL oracle.
- Microsecond timing claims (OCP trip times) are out of scope; latency is asserted in ticks (A3).
- The defense-in-depth "test-mode firmware never ships" build from the move-3 track is outside this plan; injection here uses the existing host stubs.
- The plan injects faults, not hardware faults (stuck GPIO, damaged drivers); hardware-level fault classes are the move-3 bench track's scope.

### Deferred to Follow-Up Work

- Injection from additional origin states as new manifest paths are added (each is a scenario addition).
- Merging this suite's coverage matrix with the R17 golden corpus once the HIL target lands.
- Fault-scenario mutation (perturbing the perturbation) as a later hardening pass.

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — R41, R17 (adjacent oracle idea), R3 (forward-looking framing).
- `firmware/test/test_sil_fault_injection.c` — the SIL replay runner this plan extends.
- `firmware/test/traces/manifest.json` — the scenario schema and soft-assertion fields promoted to hard.
- `firmware/test/state_machine_stubs.c` — the probe API for power-off and fault-logging assertions.
- `firmware/test/gen_transition_table.py` — timeout-forcing patterns reused by U3's timing scenarios.
- `firmware/config.yaml` — the timeout constants the timing scenarios advance across.
- `.github/workflows/firmware-tests.yml` — the existing SIL CI step extended by U4.
- `docs/plans/2026-07-24-003-feat-firmware-hardware-validation-track-plan.md` — the bench-track boundary (microsecond timing, live-stimulus evidence) this plan does not overlap.

---
