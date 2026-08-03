---
title: "State-Machine Model Check & Invariant Proofs - Plan"
type: feat
date: 2026-08-02
topic: state-machine-model-check
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R28, R29)
---

# State-Machine Model Check & Invariant Proofs - Plan

## Goal Capsule

**Objective:** An exhaustive reachability and transition-property check over the machine-readable transition manifest — proving the absence of reachable unsafe states and invalid transitions — plus load-bearing safety invariants (power stage disabled under over-temp, sensor fault blocks heating, no re-entry to heating from a faulted state without a reset) proved over the same model, each with a machine-checkable proof record that reruns on every manifest change. A guarantee unit tests cannot give.

**Product authority:** temper firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none at planning time. The modeling decision for the runaway interlock's wildcard state set (KTD2) is the one judgment call; it is resolved as a deliberate over-approximation for the current manifest. The invariant proofs' soundness rests on the power-active abstraction (KTD6) being kept in sync with `firmware/main/state_handlers.c`; the U8 audit unit owns that sync.

---

## Product Contract

### Summary

The transition manifest is treated as a finite transition system and explored exhaustively: every (state, event) cell is enumerated, reachability from `STATE_INIT` is computed, and the unsafe-state and transition-property checks are evaluated over the full graph. Load-bearing safety invariants are proved over the same model: local invariants by per-edge induction, path invariants (I-NO-REENTRY) by the reachability computation — one model, one engine, no parallel parser. Both the model check and the invariant proofs run as gates, so manifest edits cannot introduce a reachable unsafe state or violate an invariant without a named failure.

### Problem Frame

The incident class this idea exists for: safety properties that hold under test still ship because the sampled scenarios did not include the violating path, and load-bearing safety behavior that is asserted in prose and reviewed, never proved. Unit tests exercise selected transitions; they cannot prove that no path reaches an unsafe configuration. "Power stage disabled under over-temp" and "sensor fault blocks heating" are claims about reachability that a review of the code cannot establish for every path. The manifest (`firmware/transition_table.yaml`) is small and machine-readable, so the full state-event product space can be explored exhaustively and the unreachability and invariant claims become checked artifacts instead of review beliefs.

### Requirements

- R28. Exhaustive state-machine model check (Formal / Firmware / P2): the 8-state machine is checked for reachable unsafe states (heating while faulted, invalid transitions from every state) by exhaustive exploration over the transition table — unit tests cannot prove unreachability.
  - **Success signal:** an exhaustive exploration over the transition manifest reports zero reachable unsafe states and zero invalid transitions, as a machine-checked gate that reruns on every manifest change.
- R29. Firmware invariant proofs over the manifest (Formal / Firmware / P2): load-bearing invariants (power stage disabled under over-temp, sensor fault blocks heating) are proved as state invariants over the machine-readable transition table — the manifest makes the proof machine-checkable.
  - **Success signal:** each named invariant is verified by a machine-checked induction over the manifest's transition relation, the proof record is committed, and the checker fails on any manifest change that violates an invariant.

### Key Technical Decisions

- KTD1. **The manifest is the model.** `firmware/transition_table.yaml` is parsed into a finite transition graph (states, events, edges, fault codes); the generated `firmware/main/transition_table.h` grid is a derived artifact cross-checked, not a second model.
- KTD2. **The runaway interlock is modeled as an implicit transition over a named wildcard state set — a deliberate over-approximation.** The boundary interlock in `firmware/main/state_machine.c` (`check_runaway_boundary`) fires from any state and is not an event row; the model adds an implicit edge from every state to `STATE_RUNAWAY_FAULT` on the two interlock conditions (absolute-temperature and rate-of-rise breach, fault `FAULT_RUNAWAY_BOUNDARY`). The intended wildcard set is **all 9 manifest states**, chosen deliberately over mirroring the test generator's expansion: `firmware/test/gen_transition_table.py` expands `"*"` over `ACTIVE_STATES` only (`STATE_PAN_DET`, `STATE_PREHEAT`, `STATE_HEATING`, `STATE_NO_PAN`, `STATE_COOLDOWN` — excluding INIT, IDLE, FAULT, RUNAWAY_FAULT) for test-side reasons. Modeling the interlock from all 9 states matches the C-level "fires from any state" semantics and is conservative: over-approximating the transition relation only adds reachable states (and `STATE_RUNAWAY_FAULT` is the designed safe dead-end), so reachability and invariant claims proved over the model hold over the real system. The cross-check (KTD4, U3) treats the state-set divergence from the test list as a documented exception, not drift.
- KTD3. **Unsafe-state checks are predicate checks over the graph, not path sampling.** Each check is evaluated over every cell and every reachable configuration, so the result is an exhaustive verdict with a per-cell evidence list.
- KTD4. **The two manifests must agree.** The production manifest and the test generator's hardcoded transition list are cross-checked row-for-row (modulo the interlock wildcards, whose state set deliberately differs per KTD2), so the model check also catches manifest drift.
- KTD5. **One model, one engine: invariants are a module over the model builder, not a parallel engine.** The invariants module (U5) consumes the transition graph and reachability computation from the model builder (U1) — no separate parser or induction engine. Local (edge-inductive) invariants are checked per-edge over the model's transition relation; path properties (I-NO-REENTRY) use the reachability computation directly. The checker re-derives its verdict on every run, so the proof record cannot go stale.
- KTD6. **The power-active abstraction is the proof's interface.** `power_active` maps to `STATE_PREHEAT` and `STATE_HEATING` (the states whose entry handlers call `power_enable()` in `firmware/main/state_handlers.c`); `faulted` maps to `STATE_FAULT` and `STATE_RUNAWAY_FAULT`. The mapping is documented and audited (U8) so a state-handler change cannot silently invalidate a check or proof; the audit's claim is scoped to the state-handler entry/exit surface.
- KTD7. **Invariants are declared in a machine-readable form.** Each invariant is a predicate over (state, event, fault, derived flags) written in a small declarative format the invariants module evaluates, so adding an invariant is data, not check code.
- KTD8. **Every invariant carries a named counter-example mutation.** The module's test suite demonstrates each invariant can fail, so the proofs are known to bite (the repo's proven-non-vacuity discipline applied to proofs).

### Assumptions

- A1. **State-count wording:** the portfolio's "8-state" wording predates `STATE_RUNAWAY_FAULT`; the manifest defines 9 states and is authoritative.
- A2. **Power-active and faulted state sets:** `power_active` is `STATE_PREHEAT` and `STATE_HEATING` (entry handlers call `power_enable()` in `firmware/main/state_handlers.c`); `faulted` is `STATE_FAULT` and `STATE_RUNAWAY_FAULT`. This is the documented check/proof interface (KTD6).
- A3. **The manifest is the authority for legality:** a cell with no declared row is `TRANSITION_INVALID` by construction; the check's "invalid transitions" property is the full enumeration of the cell space plus the edge-property checks below.
- A4. **The manifest is the transition relation; the interlock is outside it.** The runaway boundary implementation in `firmware/main/state_machine.c` is outside the manifest and therefore outside the manifest-level claims; it is modeled only as implicit edges (KTD2), and the manifest-level claims are stated accordingly (e.g., over-temp rows target `STATE_FAULT`; the interlock's own path to `STATE_RUNAWAY_FAULT` is not a manifest row).
- A5. **Portfolio R7's success-signal field** is satisfied by each idea text's outcome clause; no separate signal was published for R28 or R29.

---

## Implementation Units

**Unit ID mapping (merge of 028 + 029):** U1–U4 carry the surviving plan's (028) numbering unchanged. U5–U8 are the absorbed invariant-proof units (formerly 029's U1–U4), renumbered after the surviving units: 029-U1 (invariant predicate framework) → U5, 029-U2 (seed invariant set) → U6, 029-U3 (proof record and rerun gate) → U7, 029-U4 (power-active abstraction audit) → U8. The absorbed plan `docs/plans/2026-08-02-029-feat-firmware-invariant-proofs-plan.md` was folded into this document per the merge map in `docs/evidence/2026-08-02-validation-portfolio-review.md`.

### U1. Model builder and reachability core

**Goal:** A parser that turns `firmware/transition_table.yaml` into a transition graph, plus an exhaustive reachability computation from `STATE_INIT`, emitting a machine-readable reachability report.

**Requirements:** R28

**Dependencies:** none

**Files:**
- `firmware/tools/transition_model.py` (new model builder)
- `firmware/tools/test_transition_model.py` (new host pytest)
- `firmware/transition_table.yaml` (read-only input)

**Approach:** Parse states, events, and transition rows into a graph; add the implicit runaway-interlock edges per KTD2 (over all 9 manifest states). Compute the reachable set from `STATE_INIT` by fixed-point closure over the finite graph. Emit a report listing the reachable set, the unreachable set (with justification or classification), and per-state outgoing edges. Because the graph is finite (9 states x 23 events), closure is exhaustive by construction.

**Patterns to follow:** The manifest validation logic in `firmware/tools/gen_transition_table.py` (row validation, duplicate detection); the host-pytest pattern of `firmware/test/test_codegen_tools.py`.

**Test scenarios:**
1. Happy path: on the current manifest, the reachable set from `STATE_INIT` is computed and every state except the interlock-only entry is reachable; `STATE_RUNAWAY_FAULT` is reachable only via an interlock edge.
2. Edge case: a state with zero incoming edges other than the interlock is classified as interlock-only with evidence.
3. Error path: a manifest row referencing an unknown state or event fails parsing with the row named.
4. Coverage: the report enumerates every one of the 9 x 23 cells as either a declared transition or `TRANSITION_INVALID`.

**Verification:** Host pytest passes; the reachability report for the current manifest is committed and matches the check's output.

### U2. Unsafe-state and transition-property checks

**Goal:** Predicate checks over the full graph proving: no faulted-to-power-active edge, every sensor-fault event lands in a fault state with a fault code, fault codes and fault targets are consistent, and no invalid targets exist in any row.

**Requirements:** R28

**Dependencies:** U1, U8 (P1's power-active mapping is the audited interface from U8)

**Files:**
- `firmware/tools/transition_model_checks.py` (new checks)
- `firmware/tools/test_transition_model_checks.py` (new host pytest)

**Approach:** Implement each property as a predicate over cells and edges, per KTD3. Property set: (P1) no edge from `STATE_FAULT` or `STATE_RUNAWAY_FAULT` to a power-active state (`STATE_PREHEAT`, `STATE_HEATING`, per KTD6); (P2) every sensor-fault event from any state targets a fault state with a non-`FAULT_NONE` code — the sensor-fault event set is **derived from the manifest**, not hardcoded, as every event with at least one fault-targeting row (a row targeting a fault state with a non-`FAULT_NONE` code); on the current manifest that set is `EVENT_SELFTEST_FAIL`, `EVENT_PREHEAT_TIMEOUT`, `EVENT_OVER_TEMP`, `EVENT_OVER_CURRENT`, `EVENT_FAN_FAILURE`, `EVENT_PROBE_OPEN`, `EVENT_PROBE_SHORT`, `EVENT_THERMAL_RUNAWAY`, and `EVENT_COOLDOWN_OVERHEAT`, and it excludes `EVENT_FAULT_RESET_PERSISTS` (whose self-loop row carries no fault code); (P3) a row targeting a fault state carries a fault code, and a row carrying a fault code targets a fault state; (P4) no row targets `TRANSITION_INVALID` or an unknown state. Each check emits per-cell evidence so a violation names the exact row. The derived sensor-fault event set is shared with U6's I-SENSOR-FAULT-BLOCKS-HEATING via a common helper so the two consumers cannot drift.

**Patterns to follow:** The invariant-checking shape of the trace preflight in `firmware/test/test_sil_fault_injection.c`; the fail-with-row discipline of the manifest validators in `firmware/tools/gen_transition_table.py`.

**Test scenarios:**
1. Happy path: all four properties pass on the current manifest.
2. Error path: a synthetic edge `(STATE_HEATING, EVENT_OVER_TEMP) → STATE_HEATING` added to the model fails P2 with the row named.
3. Error path: a synthetic row `(STATE_FAULT, EVENT_OVER_TEMP) → STATE_PREHEAT` fails P1.
4. Error path: a row with a fault target but `FAULT_NONE` fails P3.

**Verification:** Host pytest passes; a mutation harness (synthetic bad edges injected into the model in memory) demonstrates each property can fail, proving the checks bite.

### U3. Manifest cross-check

**Goal:** Prove the production manifest and the test generator's transition list agree, so the model check doubles as a drift gate between the two manifests.

**Requirements:** R28

**Dependencies:** U1

**Files:**
- `firmware/tools/transition_manifest_crosscheck.py` (new)
- `firmware/tools/test_transition_manifest_crosscheck.py` (new host pytest)
- `firmware/test/gen_transition_table.py` (read-only input, parsed via its transition list)

**Approach:** Load the production manifest rows and the test generator's transition rows, and compare them row-for-row on `(from, event, to, fault)`. The comparison treats the interlock wildcard rows (present only in the test list) as the documented KTD2 exception, not as drift — including the deliberate state-set divergence (the model's over-approximation over all 9 states vs the test list's `ACTIVE_STATES` expansion). Regenerate `firmware/main/transition_table.h` in memory and compare its grid to the parsed manifest, catching codegen drift.

**Patterns to follow:** The drift-check shape of the codegen steps in `.github/workflows/firmware-tests.yml`; the module-import reuse pattern of the repo's Python tooling.

**Test scenarios:**
1. Happy path: current manifests agree modulo the interlock wildcards, and the generated grid matches the manifest.
2. Error path: deleting a production manifest row fails the cross-check naming the missing `(from, event)` pair.
3. Error path: a test-list row whose `to` differs from the production row fails the cross-check with both values.

**Verification:** Host pytest passes; the cross-check is green on the current tree and red under each documented mutation.

### U4. CI gate and report

**Goal:** Run the model check in CI on the firmware path and fail closed on any reachable unsafe state, invalid transition, or manifest drift.

**Requirements:** R28

**Dependencies:** U1, U2, U3

**Files:**
- `scripts/check_state_machine_model.py` (new gate entry point, with `scripts/manifest.yaml` entry)
- `.github/workflows/firmware-tests.yml` (add the gate step)
- `firmware/main/transition_table.h` (read-only input, regenerated by the existing codegen step)

**Approach:** The gate runs the reachability report, the property checks, and the cross-check in one invocation and exits nonzero with the offending rows on any failure. The gate is added to the firmware CI path so manifest edits are checked on every firmware change; the same workflow also hosts U7's invariant gate. The reachability report is committed as an artifact so the exhaustive-exploration claim is auditable.

**Patterns to follow:** The gate-script convention and `scripts/manifest.yaml` entry requirement; the two-tier acceptance-gate discipline documented in `docs/solutions/architecture-patterns/`.

**Test scenarios:**
1. Happy path: the gate passes on the current manifest and emits a committed reachability report.
2. Error path: a manifest change introducing a reachable unsafe state fails the gate with the offending row and property.
3. Error path: a manifest change that drifts from the test list fails the gate before any test runs.

**Verification:** The gate runs in CI on the firmware path; its unit tests cover each failure mode; the reachability report artifact is current with the manifest.

### U5. Invariants module (over the model builder)

**Goal:** A declarative invariant format and a checker module that evaluates a predicate on the model from U1 and verifies the inductive step over every model edge (and, for path properties, the reachability computation), emitting a per-edge evidence list. The module is a consumer of the U1 model builder — no parallel parser or engine (KTD5).

**Requirements:** R29

**Dependencies:** U1

**Files:**
- `firmware/tools/invariants.py` (new invariants module over `transition_model.py`)
- `firmware/tools/invariants.yaml` (new declared invariants)
- `firmware/tools/test_invariants.py` (new host pytest)
- `firmware/transition_table.yaml` (read-only input, consumed via the U1 model builder)

**Approach:** Define a predicate language over (state, event, fault, derived flags) sufficient for the seed invariants: state membership, event identity, fault-code identity. The module loads the model object from U1 (no separate manifest parsing), checks the base case at `STATE_INIT`, then for every edge verifies `pre-state satisfies invariant` implies `post-state satisfies invariant`, collecting per-edge evidence. Path properties (I-NO-REENTRY) are evaluated against U1's reachability computation instead of per-edge induction. A violation report names the invariant, the edge (or path), and the failing side.

**Patterns to follow:** The predicate-over-cells shape of the U2 property checks; the manifest parsing in `firmware/tools/gen_transition_table.py`; the module-import reuse pattern of the repo's Python tooling; the induction-record convention in `packages/temper-geometry/VERIFICATION.md`.

**Test scenarios:**
1. Happy path: a trivial invariant ("state is one of the 9 states") verifies over the full model with per-edge evidence.
2. Error path: an invariant that is false at `STATE_INIT` fails at the base case.
3. Error path: an invariant whose inductive step fails on a synthetic bad edge fails with the edge named.
4. Edge case: an invariant over a derived flag (e.g., `power_active`) evaluates correctly on states that do and do not carry the flag.

**Verification:** Host pytest passes; the module reproduces a correct verdict on the current model and a failing verdict under each documented synthetic edge.

### U6. Seed invariant set

**Goal:** Encode and prove the load-bearing invariants: over-temp disables the power stage, sensor faults block heating, and faulted states cannot re-enter heating without the reset path.

**Requirements:** R29

**Dependencies:** U5, U8 (the power-active abstraction audit is a dependency of the over-temp predicates, whose targets are defined against the audited mapping)

**Files:**
- `firmware/tools/invariants.yaml` (populated)
- `firmware/tools/test_invariants.py` (extended)

**Approach:** Encode the seed invariants. I-OVERTEMP-DISABLES: every row whose event is `EVENT_OVER_TEMP` or `EVENT_COOLDOWN_OVERHEAT` targets `STATE_FAULT` with a non-`FAULT_NONE` code, from every state that declares the event (the interlock's own path to `STATE_RUNAWAY_FAULT` is outside the manifest per A4 and is not part of this claim). I-SENSOR-FAULT-BLOCKS-HEATING: every sensor-fault event row originating in a power-active state targets a fault state, never a power-active or benign state — the sensor-fault event set is derived from the manifest (shared derivation with U2's P2). I-FAULT-EXITS: from `STATE_FAULT` the only declared exits are `EVENT_FAULT_RESET_CLEARED` → `STATE_INIT` and `EVENT_FAULT_RESET_PERSISTS` → `STATE_FAULT`; from `STATE_RUNAWAY_FAULT` the only declared row is the `EVENT_FAULT_RESET_PERSISTS` self-loop (no escape to any other state). I-NO-REENTRY: no path exists from a faulted state to a power-active state except through `STATE_INIT` — verified via U1's reachability computation (KTD5), not per-edge induction.

**Patterns to follow:** The property-check list from U2 (P1-P4) as the foundation; the fault-code discipline of `firmware/transition_table.yaml`.

**Test scenarios:**
1. Happy path: all four invariants verify on the current manifest.
2. Error path: a synthetic edge `(STATE_HEATING, EVENT_OVER_TEMP) → STATE_HEATING` fails I-OVERTEMP-DISABLES.
3. Error path: a synthetic edge `(STATE_FAULT, EVENT_FAULT_RESET_CLEARED) → STATE_HEATING` fails I-NO-REENTRY and I-FAULT-EXITS.
4. Error path: a synthetic row adding a fault code to a benign transition fails the code discipline that I-FAULT-EXITS relies on.

**Verification:** Host pytest passes; each invariant has a documented counter-example mutation that fails it (KTD8), recorded in the test file.

### U7. Proof record and rerun gate

**Goal:** Commit a machine-readable proof record per invariant and rerun the checker in CI on every manifest change, failing on drift.

**Requirements:** R29

**Dependencies:** U1, U5, U6

**Files:**
- `firmware/tools/proof_record.json` (generated, committed)
- `firmware/tools/gen_proof_record.py` (new)
- `scripts/check_firmware_invariants.py` (new gate entry point, with `scripts/manifest.yaml` entry)
- `.github/workflows/firmware-tests.yml` (add the gate step alongside U4's gate)

**Approach:** The generator writes the proof record: per invariant, the predicate, the base-case evidence, the per-edge (or reachability) verification list, and the verdict. The CI gate reruns the invariants module from source over the shared model (KTD1, KTD5) and fails on any violated invariant; a record that no longer matches the current manifest also fails, so the record cannot drift from the source of truth.

**Patterns to follow:** The drift-check shape of the codegen steps in `.github/workflows/firmware-tests.yml`; the `scripts/manifest.yaml` entry requirement; the induction-record convention in `packages/temper-geometry/VERIFICATION.md`.

**Test scenarios:**
1. Happy path: the gate passes on the current manifest and regenerates an identical proof record.
2. Error path: a manifest edit that violates an invariant fails the gate with the invariant and edge named.
3. Error path: a stale proof record (edited by hand) fails the gate as drift.

**Verification:** The gate runs in CI on the firmware path (same workflow as U4's gate); the committed proof record is byte-stable under regeneration.

### U8. Power-active abstraction audit

**Goal:** Document the power-active mapping as the proof's interface and audit that state-handler entry/exit power calls match the mapping.

**Requirements:** R29

**Dependencies:** U1 (the model's state list defines the mapped-state surface the audit enumerates)

**Files:**
- `firmware/tools/POWER_ACTIVE_MAPPING.md` (new interface contract)
- `firmware/tools/test_power_active_mapping.py` (new audit test)
- `firmware/main/state_handlers.c` (read-only input)

**Approach:** Write the mapping contract: `power_active` states call `power_enable()` in their entry handler and disable power in their exit path; fault states call `pwm_disable_all()` and `pll_disable()`. The audit test scans the state-handler entry/exit calls and fails when a `power_enable()` call appears outside a mapped state, or when a power-disable call is missing from a fault-state entry handler, so the abstraction cannot drift silently. The claim is scoped to the state-handler surface: the audit inspects entry/exit handlers in `firmware/main/state_handlers.c` and cannot see power-enable paths in other components (main loop, timers), so the documented interface states that scope.

**Patterns to follow:** The source-audit shape of repo gates that scan source for symbol use (e.g., the fault-list consistency check); the documentation-first convention of `docs/solutions/`.

**Test scenarios:**
1. Happy path: the current `firmware/main/state_handlers.c` passes the audit (power calls match the mapping).
2. Error path: a synthetic handler adding `power_enable()` to a non-mapped state fails the audit naming the state.
3. Error path: removing the power-disable call from a fault-state entry handler fails the audit.

**Verification:** Host pytest passes; the mapping document is committed and cited by the invariant module's assumptions.

---

## Verification Contract

- Host pytest for `firmware/tools/test_transition_model.py`, `firmware/tools/test_transition_model_checks.py`, `firmware/tools/test_transition_manifest_crosscheck.py`, `firmware/tools/test_invariants.py`, and `firmware/tools/test_power_active_mapping.py`.
- Gate: `scripts/check_state_machine_model.py` exits 0 on the current tree and nonzero under each documented synthetic violation; `scripts/check_firmware_invariants.py` exits 0 on the current tree and nonzero under each documented invariant violation.
- CI: both gates run in `.github/workflows/firmware-tests.yml` on the firmware path.
- Host build and tests: `cmake -B firmware/test/build firmware/test`, `cmake --build firmware/test/build`, then `ctest --test-dir firmware/test/build` (per AGENTS.md), confirming the codegen and generated tests stay green alongside the model check and the proofs.

## Definition of Done

- U1's reachability core enumerates the full cell space and emits a committed report.
- U2's property checks pass on the current manifest and are demonstrated to bite on synthetic violations.
- U3's cross-check is green on the current tree.
- U4's CI gate fails closed on any unsafe reachable state, invalid transition, or manifest drift.
- U5's invariants module evaluates declared invariants over the shared model builder with per-edge (or reachability) evidence.
- U6's four seed invariants are proven on the current manifest, each with a documented counter-example mutation.
- U7's proof record is committed, byte-stable under regeneration, and CI-rerun on every manifest change.
- U8's power-active mapping is documented and audited (scoped to the state-handler surface).
- The reachability report artifact is current; no dead-end experimental code is left in the diff.

---

## Scope Boundaries

- The model check validates the manifest-as-model; proving the C implementation follows the manifest is the job of the generated transition-table tests and remains covered by the existing suite.
- The interlock semantics of the runaway boundary are modeled as implicit edges; the interlock's timing behavior is out of scope.
- The check does not modify the state machine or the manifest; it is read-only validation.
- The invariant proofs are manifest-level state invariants; timed behavior (latency, watchdog windows) is out of scope.
- Interlock-only behavior (the runaway boundary implementation) is not part of the manifest and not covered by the proofs; it enters the model only as implicit edges (KTD2).
- The power-active audit's claim is scoped to the state-handler entry/exit surface; power-enable paths in other components are outside its reach.
- Proving the C implementation matches the manifest is the generated-test suite's job, unchanged by this plan.

### Deferred to Follow-Up Work

- A mutation suite proving the checks bite on every property (a lighter form of R40's discipline, scoped to the model check).
- Bounded model checking over timed behavior (latency, watchdog timing) — out of scope for a state-level model.
- Invariants over the state-handler side effects (e.g., EEPROM logging on every fault transition) — a richer predicate set for a later pass.
- A proof of the emulated-target behavior (R17) as an extension of these manifest proofs.

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — R28, R29, R8 (seed anchoring), R3 (forward-looking framing).
- `docs/evidence/2026-08-02-validation-portfolio-review.md` — the review outcome that drove this merge (028 KEEP, 029 MERGE → 028, ground-truth corrections, fix-before-execution item 18).
- `firmware/transition_table.yaml` — the manifest that is the model.
- `firmware/main/state_machine.h` — `STATE_LIST` (9 states) and `EVENT_LIST` (23 events).
- `firmware/main/transition_table.h` and `firmware/tools/gen_transition_table.py` — the generated grid and its validation logic.
- `firmware/main/state_machine.c` — `check_runaway_boundary()` interlock semantics modeled as implicit edges.
- `firmware/test/gen_transition_table.py` — the test-side transition list cross-checked by U3 (`ACTIVE_STATES` wildcard expansion).
- `firmware/main/state_handlers.c` — power-active state mapping (`power_enable()` in preheat/heating entry handlers; `pwm_disable_all()`/`pll_disable()` in fault entry handlers).
- `.github/workflows/firmware-tests.yml` — the CI path the gates extend.
- `packages/temper-geometry/VERIFICATION.md` — the repo's induction-proof record convention reused for the proof artifact.
- `docs/physics-verification-methodology.md` — the soundness/proof-interface discipline the abstraction audit follows.

---
