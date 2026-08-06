---
title: "Transition-table mutation suite - Plan"
type: feat
date: 2026-08-02
topic: transition-table-mutation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R40)
---

# Transition-table mutation suite - Plan

## Goal Capsule

**Objective:** Prove that the generated transition-table tests bite: every transition row in the test manifest is mutated (wrong target, wrong guard) and the regenerated tests must fail against the real state machine. Live mutations (tests still pass) are triaged to test defects and driven to zero.

**Product authority:** temper firmware maintainer (single-maintainer project; the portfolio is pulled from, not scheduled).

**Open blockers:** none at planning time. The sweep's runtime (KTD4) is a sizing decision resolved as an assumption for CI.

---

## Product Contract

### Summary

The codegen manifest makes mutation cheap: a driver mutates one row, regenerates the test C into a scratch build, runs it, and classifies the mutation as killed, live, or equivalent. The mutation score and the live-mutant triage report become a gate, so every transition in the manifest is proven to be exercised by tests that can fail.

### Problem Frame

The incident class this idea exists for: a generated test that passes for the wrong reason — an event stub that never fires, a precondition that masks the transition, a drain-message fallback that lands on the expected state by coincidence. Unit tests look green while the row they claim to cover is not actually exercised. Mutation testing converts "the tests pass" into "the tests would fail if the spec changed", and the manifest makes each row's mutation mechanical and exhaustive.

### Requirements

- R40. Transition-table mutation suite (Injection / Firmware / P1): each transition in the manifest is mutated (wrong target, wrong guard) and the generated tests must fail — the codegen manifest makes mutation cheap and exhaustive.
  - **Success signal:** for every transition row, at least one mutation (wrong target or wrong guard) produces a regenerated test that fails against the real implementation; the suite reports zero live mutants, with any live mutant triaged to a stub, precondition, or drain-mask defect and fixed.

### Key Technical Decisions

- KTD1. **The mutation driver imports the generator and writes scratch output only.** The committed generator (`firmware/test/gen_transition_table.py`) and the committed generated file stay byte-stable; each mutation is applied in memory, written to a scratch build directory, built, and run there.
- KTD2. **A canonical mutation set per row.** Each row receives a wrong-target mutation (target replaced by a canonical alternate state) and guard mutations (fault code dropped, fault code swapped to a different code, fault code added to a benign row); same-value mutations are classified equivalent and excluded, keeping the sweep tractable.
- KTD3. **Live mutants are test defects, not spec approvals.** A mutation surviving means the generated test cannot distinguish the mutated spec from the real one; the fix is to the test's stub or precondition (or the mutation is proven equivalent), never to accept the live mutant.
- KTD4. **The sweep reuses one scratch build tree across mutants.** Regeneration changes only the generated C file, so incremental rebuilds keep the full sweep inside a CI-runnable budget; the operator set stays canonical (KTD2) rather than exhaustive target enumeration.

### Assumptions

- A1. **Seed resolves:** `firmware/test/gen_transition_table.py` exists and its hardcoded `TRANSITIONS` list is the manifest this plan mutates (the portfolio seed is the generator itself).
- A2. **Two manifests, two roles:** this suite mutates the test-side manifest (the generator's `TRANSITIONS` list) whose rows drive `firmware/test/test_transition_table_generated.c`; drift between it and the production manifest (`firmware/transition_table.yaml`) is owned by the R28 model check, not this plan.
- A3. **Wildcard rows mutate as expanded instances:** the interlock rows (`RUNAWAY_ABSOLUTE_TEMP`, `RUNAWAY_RISE_RATE` expanded over the active states) are mutated per expanded instance, matching how the generator emits them.
- A4. **CI runtime assumption:** with one canonical mutation set per row and incremental scratch rebuilds, the full sweep fits the firmware workflow's budget; if it does not, the gate keeps the coverage assertion and the sweep moves to a scheduled workflow (deferred follow-up).
- A5. **Portfolio R7's success-signal field** is satisfied by the idea text's outcome clause; no separate signal was published for R40.

---

## Implementation Units

### U1. Mutation driver scaffold

**Goal:** A driver that applies one mutation to the generator's transition list, regenerates the test C into a scratch build, builds and runs the test binary, and classifies the outcome as killed, live, or equivalent.

**Requirements:** R40

**Dependencies:** none

**Files:**
- `firmware/test/mutate_transition_table.py` (new driver)
- `firmware/test/build/mutations/` (scratch build directory, generated, not committed)
- `firmware/test/gen_transition_table.py` (read-only input, imported)

**Approach:** Import the generator module and its `TRANSITIONS` list; apply a single mutation; call the generator's C-emission path into the scratch directory; build a scratch test binary from the same source set as the `test_state_machine_only` target (`firmware/test/CMakeLists.txt`); run it; classify by exit code and assertion output. A mutation is killed when the run fails an assertion, live when it passes, and equivalent when the mutated row is identical to the original (detected and excluded).

**Patterns to follow:** The module-import reuse pattern of the repo's Python tooling; the `test_state_machine_only` source list in `firmware/test/CMakeLists.txt`; the generated-test shape in `firmware/test/gen_transition_table.py`.

**Test scenarios:**
1. Happy path: a known-kill mutation (row `(STATE_PREHEAT, NEAR_TARGET)` target changed to `STATE_FAULT`) is classified killed — the regenerated test fails because the real machine reaches `STATE_HEATING`.
2. Edge case: a no-op mutation (target changed to the original target) is classified equivalent and excluded from the score.
3. Error path: a mutation that breaks generation or build is classified error, not live, with the reason captured.
4. Error path: the driver leaves the committed `firmware/test/test_transition_table_generated.c` byte-identical after a run.

**Verification:** The driver's unit tests pass; a dry run on one row classifies all three outcome classes; the committed generated file stays byte-identical after the run.

### U2. Operator set and exhaustive sweep

**Goal:** Apply the canonical mutation set (KTD2) to every row, emit a per-row kill report with a mutation score, and assert full row coverage.

**Requirements:** R40

**Dependencies:** U1

**Files:**
- `firmware/test/mutate_transition_table.py` (extended with the operator set and sweep loop)
- `firmware/test/build/mutations/report.json` (generated kill report)
- `firmware/test/test_mutation_sweep.py` (new host pytest)

**Approach:** For each row, generate the canonical mutations (one wrong target, guard drop, guard swap, guard add where applicable), run each through U1, and record killed/live/equivalent with the observed assertion output. The sweep asserts every row received its mutations; the report names the mutation score and lists every live mutant with the row, the mutant, and the outcome.

**Patterns to follow:** The per-row enumeration style of the generator's `TRANSITIONS` list; the report-and-fail shape of repo gates like `scripts/check_drc_ceiling_approval.py`.

**Test scenarios:**
1. Happy path: the report covers every row of the manifest with its canonical mutation set.
2. Edge case: wildcard-expanded instances are each mutated as emitted rows, and equivalent instances are excluded rather than counted live.
3. Error path: a row whose mutations are all classified live is listed first in the report with the outcome evidence.
4. Coverage: the sweep fails if any row was skipped (row-count assertion).

**Verification:** Host pytest passes; the sweep's report on the current tree lists each row's mutations and the current live-mutant count.

### U3. Live-mutant triage

**Goal:** For each live mutant, identify the reason class (stub never fires, precondition masks the row, drain-message fallback masks the target, timing) and fix the generated test's stub or precondition so the mutant is killed.

**Requirements:** R40

**Dependencies:** U2

**Files:**
- `firmware/test/gen_transition_table.py` (event stubs and preconditions, modified where a live mutant exposes a defect)
- `firmware/test/test_transition_table_generated.c` (regenerated)
- `firmware/test/mutate_transition_table.py` (extended with a triage reason classifier)

**Approach:** The driver classifies each live mutant's reason from the run context: the event stub's mock calls, the state reached, and the drain fallback path. Each fix is a change to the stub or precondition recipe in the generator so the regenerated test genuinely fires the row; after the fix, the mutant must classify killed. The triage report records the reason class and the fix per mutant.

**Patterns to follow:** The event-stub and precondition recipes in `firmware/test/gen_transition_table.py`; the special-case patterns (confidence loop, message drain) already present in the generated test's runner logic.

**Test scenarios:**
1. Happy path: a live mutant whose event stub never fires becomes killed after its stub is corrected.
2. Happy path: a live mutant masked by a precondition becomes killed after the precondition is corrected.
3. Edge case: a mutant proven truly equivalent (no behavioral difference exists) is documented as equivalent with justification, not silently dropped.
4. Regression: fixing one row's stub does not kill another row's previously-killed mutants (full sweep rerun stays green).

**Verification:** The triage report shows zero live mutants on the current tree, with every formerly-live mutant attributed to a reason class and a fix; the full sweep rerun confirms no collateral kills.

### U4. CI gate and runtime guard

**Goal:** Run the mutation sweep in CI with a zero-live-mutant gate and a row-coverage assertion.

**Requirements:** R40

**Dependencies:** U2, U3

**Files:**
- `scripts/check_transition_table_mutations.py` (new gate entry point, with `scripts/manifest.yaml` entry)
- `.github/workflows/firmware-tests.yml` (add the sweep step)
- `firmware/test/build/mutations/report.json` (gate input)

**Approach:** The gate parses the sweep report, fails on any live mutant, fails on any skipped row, and prints the mutation score. It is added to the firmware CI path. Per A4, if the full sweep exceeds the workflow budget, the gate keeps the coverage assertion and the sweep itself moves to a scheduled workflow (deferred follow-up).

**Patterns to follow:** The gate-script convention and `scripts/manifest.yaml` entry requirement; the drift-check shape of the codegen steps in `.github/workflows/firmware-tests.yml`.

**Test scenarios:**
1. Happy path: a report with zero live mutants and full row coverage passes the gate.
2. Error path: a report with one live mutant fails the gate naming the row and mutant.
3. Error path: a report missing a row fails the gate on the coverage assertion.

**Verification:** The gate runs in CI on the firmware path; its unit tests cover each failure mode.

---

## Verification Contract

- Host pytest for `firmware/test/test_mutation_sweep.py` and the gate's tests.
- Host build and tests: `cmake -B firmware/test/build firmware/test`, `cmake --build firmware/test/build`, then `ctest --test-dir firmware/test/build` (per AGENTS.md), confirming the committed generated tests stay green.
- Sweep: the driver's report on the current tree shows zero live mutants and full row coverage.
- CI: the gate runs in `.github/workflows/firmware-tests.yml`.

## Definition of Done

- U1's driver classifies killed / live / equivalent and leaves the committed generated file byte-stable.
- U2's sweep covers every row with the canonical mutation set and emits a report.
- U3's triage drives live mutants to zero with an attributed reason class per mutant.
- U4's CI gate fails on live mutants or skipped rows.
- No scratch mutation artifacts are left in the diff; the committed generator and generated file are the only tracked outputs.

---

## Scope Boundaries

- The suite mutates the test-side manifest (the generator's `TRANSITIONS` list); mutating the production manifest (`firmware/transition_table.yaml`) and its codegen drift is owned by R28.
- The canonical operator set covers wrong-target and wrong-guard mutations; timing-window and event-order mutations are out of scope.
- The suite does not modify the state machine implementation; it only reveals test defects.

### Deferred to Follow-Up Work

- Full target-enumeration mutations (every alternate target per row) as a scheduled batch if CI budget demands.
- Mutation of the event-stub recipes themselves (perturbing how an event is forced).
- Folding the triage reason classes into a standing test-quality report.

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — R40, R28 (manifest-drift ownership), R3 (forward-looking framing).
- `firmware/test/gen_transition_table.py` — the manifest and generator this suite mutates.
- `firmware/test/test_transition_table_generated.c` — the generated test under mutation.
- `firmware/test/CMakeLists.txt` — the `test_state_machine_only` source set the scratch build mirrors.
- `firmware/test/test_sil_fault_injection.c` — the trace-invariant and latency patterns relevant to stub-firing defects.
- `.github/workflows/firmware-tests.yml` — the CI path the gate extends.

---
