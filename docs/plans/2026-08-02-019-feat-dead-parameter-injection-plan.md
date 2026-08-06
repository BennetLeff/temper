---
title: Dead-Parameter & Physics-Input Injection - Plan
type: feat
date: 2026-08-02
topic: dead-parameter-injection
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
origin: docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md (R33, R37)
---

# Dead-Parameter & Physics-Input Injection - Plan

## Goal Capsule

**Objective:** Wire then unwire every gate input and every physics parameter, and require the output to change, so the dead-parameter sweep pattern becomes a standing check instead of a one-off fix — applied to both the gate-input surface (R37) and the physics-input surface (R33).

**Product authority:** temper-placer maintainer (single-maintainer project; this plan is pulled from the portfolio menu, not scheduled).

**Open blockers:** none. The perturbation magnitude and the detection threshold per parameter are measured at implementation time.

---

## Product Contract

### Summary

The `design_rules` wiring bug and its eighteen siblings (`docs/plans/2026-07-23-006-fix-dead-parameter-wiring-sweep-plan.md`) had a recognizable shape: a parameter is accepted, stored, and never forwarded to the code that would change behavior. That sweep was a one-off fix. This plan makes the pattern a standing check: for every declared gate input, run the gate twice — with the input live and with it unwired — and require the verdict to change. An input whose removal does not change the verdict is a dead parameter and fails the run.

R33 (physics-parameter injection) is the physics-scoped subset of this same sweep: physics parameters (`k_fr4`, `k_copper`, `h_conv`, `convection_weight`, IPC-2152 ampacity inputs) plumbed into the FDM solver, the thermal scorer, the thermal potential, and the IPC-2152 checks must be proven live the same way — perturb the parameter and require the downstream output to move. Because the two ideas share the same perturb-and-observe harness, register, and gate, this merged plan builds that machinery once and drives both input surfaces from it.

### Problem Frame

A gate that accepts an input it never uses reports a verdict that looks enforced but is not. The dead-parameter class is invisible to review because the wiring looks correct by inspection — the 2026-07-23 "fix" was itself a runtime no-op. The same class exists on the physics layer: a check reads a physics parameter, and nobody verifies the value actually changes the outcome. The repo has already suffered this failure once (`docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — metrics that recorded `0.0` while the gate passed because the tolerance absorbed them). The physics layer has many parameters consumed across the FDM solver, the thermal scorer, the thermal potential, and the IPC-2152 checks, and each plumbed value needs a live-plumbing proof.

The only reliable detector is behavioral: perturb the input and require the output to move. When that probe is a standing check, the next dead parameter fails at CI time instead of surfacing as a mysterious regression. One correction sharpens the target: the original dead-parameter plan aimed at `validation/validation_gates.py` and its `RunMetrics` container, but the portfolio review established that surface is deprecated and callerless (`check_gate`/`check_all_gates` have no callers outside `validation_gates.py`). The probe therefore targets the live surface — the `cp_sat/gate.py` acceptance gate and the CI gate scripts actually invoked — and treats the deprecated surface's phantom declarations as a tracked finding to remediate, not as the sweep's substrate.

### Requirements

- R37. Every gate input is wired then unwired and output must change — the dead-parameter sweep pattern becomes a standing check, not a one-off fix.
  - **Success signal:** a standing check enumerates each gate's declared inputs, runs each gate with and without each input, and fails when a gate's verdict does not change; the check covers the gates that declare their inputs on the live surface today (`cp_sat/gate.py` acceptance gate + invoked CI gate scripts).
- R33. **Physics-parameter injection** (Injection / Physics / P2): perturbed physics parameters (conductivity, convection, ampacity inputs) must be detected by downstream checks — parameter plumbing is proven live, not assumed.
  - **Success signal:** every registered physics parameter, when perturbed deterministically, moves its downstream check's output beyond the measured noise floor; a parameter whose perturbation produces no signal fails CI.
  - **Covers portfolio flows:** F1 (pull-to-plan), via the success signal as acceptance criteria.

### Key Technical Decisions

- KTD1. **Start from declarative input surfaces on the live gate surface.** The gates' declared inputs (`cp_sat/gate.py` acceptance gate + invoked CI gate scripts) and the physics config dataclass fields (`ThermalFDMConfig` `k_fr4`/`k_copper`, `heat_removal` constants, IPC-2152 inputs) are the two mechanically enumerable input surfaces, and the physics parameter-to-consumer map is part of the register. Rationale: starting declaratively avoids the grep-scope blind spot that corrupted the 2026-07-23 sweep (`src/`-only grep missed real callers in `scripts/` and `benchmarks/`); starting from the live surface avoids sweeping a deprecated callerless stub.
- KTD2. **Perturbation is fail-forcing for gate consumers, signal-over-noise for threshold-less consumers.** For a gate, each declared input is perturbed to a value that should flip the verdict (beyond its threshold); a verdict that does not flip on a fail-forcing value proves the input dead. For threshold-less consumers (scorers and field-producing checks), the noise floor is measured first and a perturbation counts only when the output delta exceeds the measured variance. Rationale: fail-forcing is stronger than random mutation and makes a dead input unambiguous where a verdict exists; signal-over-noise is the only honest bar where there is no verdict to flip.
- KTD3. **Perturbation is deterministic and bounded per parameter, applied at the parameter's source, through the production path only.** Each parameter carries a documented delta (such as ±10%, or a sign/unit change where meaningful); the sweep reuses the existing validation entry points rather than a parallel evaluation harness. Rationale: nondeterministic perturbation cannot distinguish signal from run-to-run noise, and the sweep must measure the production path, not a copy of it.
- KTD4. **One registry, one harness, one gate.** A single check drives every registered input, extending the existing gate-inventory conventions rather than adding parallel per-gate or per-domain scripts. Rationale: matches the repo's "prefer extending existing gates over new parallel scripts" convention, and the merge mandate that R33 and R37 must not build the same machinery twice.

### Assumptions

- A1. No seed is named in the origin for R37 or R33. The pattern source is `docs/plans/2026-07-23-006-fix-dead-parameter-wiring-sweep-plan.md` (verified to exist); the live gate surface is `packages/temper-placer/src/temper_placer/placer/cp_sat/gate.py` plus the CI gate scripts invoked in `.github/workflows/`.
- A2. The deprecated `validation_gates.py` / `RunMetrics` surface is callerless (per the 019 review ground-truth correction) and is not a probe target; it is in scope only as a tracked pre-existing finding — the four phantom `required_metrics` declarations — remediated by U5. Live gates read their inputs from containers that actually carry them, and gates are deterministic given their inputs.
- A3. The standing check starts with the live gates and the physics parameter set named in the origin idea (conductivity `k_fr4`/`k_copper`, convection `h_conv`/`convection_weight`/`H_CONV_BACKGROUND`, ampacity IPC-2152 inputs); the U1 inventory is the authority for the full set. Inputs that are not declaratively enumerable are registered as a documented follow-up, not silently excluded.
- A4. "Unwired" means the input is perturbed to a fail-forcing value (KTD2), because physically removing a metric from its container would crash the consumer rather than prove it dead.
- A5. Parameters consumed only by exploratory/scratch tooling are out of scope until they reach a production path; the sweep's CI cadence is an implementation-time choice.

---

## Implementation Units

### U1. Live-input registry

**Goal:** Enumerate every live gate and its declared inputs, plus every physics parameter and its consumers, in one machine-readable registry — starting with a pre-flight survey of the current gate set so the registry targets the live surface, not the deprecated one.

**Requirements:** R33, R37

**Dependencies:** none

**Files:**
- `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py` (new)
- `power_pcb_dataset/physics_parameter_map.yaml` (new register)
- `packages/temper-placer/tests/validation/test_gate_input_registry.py` (new)
- `packages/temper-placer/tests/` inventory-loading tests

**Approach:**
1. Pre-flight survey of the current gate set (019 review fix): classify every gate as live (invoked by CI gate scripts or by the `cp_sat/gate.py` acceptance gate) or deprecated/callerless. Only live gates are registered; the deprecated `validation_gates.py` / `RunMetrics` surface is recorded as a tracked finding, never silently dropped.
2. Build the registry: read each live gate's declared inputs and produce a (gate, input) table. The registry validates that every declared input is a field the consumer's container actually carries, so a gate declaring a non-existent metric is itself a registry failure.
3. Enumerate the physics parameters by scanning the config dataclasses and module constants (`ThermalFDMConfig` `k_fr4`/`k_copper`, `heat_removal` constants, IPC-2152 inputs); trace each to its consumers through the production path (FDM solver, thermal scorer, thermal potential, validation gates, ampacity checks); record the parameter-to-consumer map as a second declarative input surface.
4. The registry is the single source of truth the probe drives; adding a gate, input, or parameter is a registry change, never a hidden code edit.
5. Record the four phantom `required_metrics` declarations (`gate_loop_area_mm2`, `bootstrap_loop_area_mm2`, `commutation_loop_area_mm2`, `igbt_edge_distance_mm` on the deprecated `RunMetrics` stub) as a tracked pre-existing finding, cross-referenced to U5.

**Patterns to follow:** the registry-and-validate pattern of `power_pcb_dataset/drc_ceiling.json` provenance checks; the AST-scan discovery shape of `scripts/bmc_adoption_gate.py`; the tracked-finding/warn-gate convention from the portfolio review.

**Test scenarios:**
1. Happy path — the registry enumerates every live gate with its declared inputs and every physics parameter with its consumers.
2. Fail path — a gate declaring a metric absent from its container fails registry validation, naming the gate and metric.
3. Edge case — a gate with an empty input list is listed as declaring zero inputs, and the probe treats it as a known non-covered case.
4. Edge case — a deprecated, callerless gate is absent from the registry only as a recorded tracked finding, never silently.
5. Physics map — `k_fr4` maps to the FDM solver's conductivity-field builder; `h_conv` maps to the thermal scorer's convective-boundary variant; an ampacity input maps to the IPC-2152 gate.
6. Dead parameter — a parameter whose consumer list is empty fails validation (dead parameter flagged).
7. Round-trip — the registry's gate names match the acceptance gate's known-gate lookup.

**Verification:** The registry validation passes on the current live gate set, the invented-metric scenario fails it, and the physics map covers the inventoried parameters, each with a resolvable source and non-empty consumers.

### U2. Wire/unwire probe

**Goal:** For each declared input — gate input or physics parameter — run the consumer live and perturbed, and require the outcome to change: a verdict flip for gate consumers, a measured signal over the noise floor for threshold-less consumers.

**Requirements:** R33, R37

**Dependencies:** U1

**Files:**
- `packages/temper-placer/src/temper_placer/validation/dead_parameter_probe.py` (new)
- `packages/temper-placer/tests/validation/test_dead_parameter_probe.py` (new)
- `packages/temper-placer/tests/` noise-floor and sensitivity tests

**Approach:**
1. For each (gate, input) pair: construct two input sets — the baseline values and the same values with that one input fail-forced past the gate's threshold — run the gate on both, and compare verdicts. The probe fails when the verdict does not change, reporting the gate, the input, and both verdicts. The fail-forcing value per metric is derived from the gate's own threshold logic, so the probe does not guess what value should flip it.
2. For each physics parameter: perturb it deterministically at its source (the documented delta from KTD3), run the production consumer, and record baseline output, perturbed output, and delta — through the production path only, no copied evaluation code.
3. For threshold-less consumers (scorers and field-producing checks): measure the run-to-run noise floor on identical input first, and count the perturbation as detected only when the delta exceeds the measured floor. Gate consumers skip the noise-floor step — a fail-forcing value must flip the verdict outright.
4. Emit a per-input record: baseline outcome, perturbed outcome, delta, perturbation applied, and a disposition (live / dead / inconclusive / `UNMEASURED`).

**Patterns to follow:** the gate verdict semantics (PASS/FAIL) of the live gates; the fail-capable rule (R4) in `docs/physics-verification-methodology.md` §4 — each probe names the dead-input bug class it catches; the measured-not-assumed discipline of the DRC-ceiling and R9/R10 bound conventions.

**Test scenarios:**
1. Happy path — a gate whose verdict flips when its metric is fail-forced passes the probe.
2. Fail path — a gate whose verdict is unchanged under a fail-forced declared metric fails, naming the dead input.
3. Edge case — a gate already FAIL at baseline (no flip possible) is reported inconclusive with the baseline verdict recorded, not as dead.
4. Edge case — a metric whose fail-forcing value is not derivable from the gate's threshold logic is reported `UNMEASURED`, not silently skipped.
5. Physics — perturbing `k_fr4` by −10% changes the FDM solver's temperature field output; perturbing `h_conv` changes the thermal scorer's score; perturbing an ampacity input changes the IPC-2152 gate's pass/fail or width output.
6. Physics — applying a perturbation at the source (not at a copy) is verified by a call-path test; an unregistered parameter is rejected by the harness.
7. Noise floor — on identical input, a consumer's output variance is below the recorded floor (floor is stable); for each registered parameter, the perturbation delta exceeds the floor (signal over noise); a delta below the floor fails the sensitivity assertion with both numbers reported.
8. Determinism — the noise-floor measurement and the probe run twice on the same inputs yield identical results (seed fixed).

**Verification:** The probe passes on gates whose declared metrics are live, the injected-dead-input scenario fails it with the input named, and every registered parameter has a measured delta over a measured floor — no signal-over-noise claim is unmeasured.

### U3. Standing check in CI

**Goal:** Run the probe across the registered live inputs and physics parameters on every CI pass as one standing check — the dead-parameter sweep and the physics-plumbing gate are the same check.

**Requirements:** R33, R37

**Dependencies:** U2

**Files:**
- `scripts/check_dead_parameter_inputs.py` (new)
- `scripts/manifest.yaml` (entry for the new script)
- `.github/workflows/python-tests.yml` (extend the existing `checks` job)

**Approach:**
1. Package the probe as a CI check script that imports the registry and probe from `temper_placer` and exits non-zero on any dead input, any unregistered parameter, or any parameter without a delta-over-floor record (or verdict flip for gate consumers).
2. Landing discipline (019 review fix): land the check behind a first-run remediation PR or warn-only initially — the first run will surface dead inputs and unproven parameters that need triage before the check can be hard-failing.
3. The script gets a `scripts/manifest.yaml` entry per the repo's script manifest convention, and the check is wired into the existing `checks` job rather than a new workflow.

**Patterns to follow:** the script-manifest convention in AGENTS.md (every `scripts/*.py` needs a manifest entry); the `bmc_adoption_gate.py` scan-and-report shape; the extension-over-new-parallel-scripts convention.

**Test scenarios:**
1. Integration — a clean run passes the standing check with every registered input live and every parameter proven.
2. Fail path — a gate whose declared metric is silently unused (per U2 scenario 2) makes the check fail, naming the gate and input.
3. Fail path — a new physics parameter without a map entry fails the gate; a registered parameter whose delta-over-floor record is stale (older than a threshold) fails the gate.
4. Stability — re-measuring on unchanged code reproduces the recorded delta within the noise floor; the gate exits 0 with the full map covered.
5. Manifest — the new script has a manifest entry with purpose, owner, and category populated.

**Verification:** The CI `checks` job passes on clean runs and fails on the injected-dead-input scenario and on a synthetic unproven parameter.

### U4. Extend to non-declarative gate inputs

**Goal:** Register the remaining gate surface whose inputs are not yet declaratively enumerable, so the standing check's coverage is explicit.

**Requirements:** R37

**Dependencies:** U3

**Files:**
- `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py`
- `packages/temper-placer/tests/validation/test_gate_input_registry.py`

**Approach:** Survey the CI gate scripts and the `cp_sat/gate.py` acceptance gate for inputs that are not declared as `required_metrics`/config fields, and register each one either as a declarative input (when the input can be named) or as a documented non-covered case with a reason. The registry's non-covered list is visible, so "not covered" is a recorded decision, never an oversight.

**Patterns to follow:** the corrected-grep-scope discipline from `docs/plans/2026-07-23-006-fix-dead-parameter-wiring-sweep-plan.md` (search `scripts/`, `benchmarks/`, and shell automation, not only `src/`); the documented-NOTE convention from `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md`.

**Test scenarios:**
1. Happy path — every surveyed gate is registered either as declarative or as a documented non-covered case.
2. Fail path — a gate found in the survey but absent from the registry fails a completeness test.
3. Edge case — a non-covered case's reason is required; a registration without a reason fails validation.

**Verification:** The completeness test passes, and the survey's findings are all reflected in the registry.

### U5. Phantom `required_metrics` remediation

**Goal:** Track and remediate the four phantom `required_metrics` declarations on the deprecated `RunMetrics` stub — a live instance of the dead-parameter class that the retarget to the live surface would otherwise orphan.

**Requirements:** R37

**Dependencies:** U1

**Files:**
- `packages/temper-placer/src/temper_placer/core/loss_types.py`
- `packages/temper-placer/src/temper_placer/validation/validation_gates.py`
- `packages/temper-placer/src/temper_placer/validation/gate_input_registry.py`

**Approach:** The deprecated gate family in `validation_gates.py` declares `gate_loop_area_mm2`, `bootstrap_loop_area_mm2`, `commutation_loop_area_mm2`, and `igbt_edge_distance_mm` as `required_metrics` on a `RunMetrics` container that does not carry them (019 review ground-truth correction; the gates have no callers outside `validation_gates.py`). Each metric is reconciled one of two ways: (a) it is a real input the live surface consumes — it moves onto the live container the gate actually reads and must then pass U2's probe; or (b) it is a phantom declaration and is removed. Either way the declaration and the container end up consistent, the closure is attributed (which container, which commit), and the finding leaves the registry's tracked-findings list only when remediated — never silently dropped with the deprecated surface.

**Patterns to follow:** the tracked-finding/warn-gate convention from the portfolio review (020's KTD4 pattern, generalized); the documented-NOTE convention.

**Test scenarios:**
1. Happy path — each of the four metrics resolves to a real field on a live container and passes the U2 probe, or the declaration is removed.
2. Fail path — a phantom declaration that is neither moved nor removed keeps the tracked finding open and the standing check flags it.
3. Edge case — the registry's findings list records the finding with attribution until closure.

**Verification:** The four phantom declarations are either proven live (U2) or removed, and the registry records the closure with attribution.

---

## Verification Contract

The standing check runs inside the existing `checks` job of `.github/workflows/python-tests.yml`; no new workflow file is introduced. The new `scripts/check_dead_parameter_inputs.py` gets a `scripts/manifest.yaml` entry (refreshed with `uv run python scripts/trace_invocations.py`) and passes the manifest gate. New public functions in `temper_placer/` must clear the coverage gate (`.coverage-allowlist`); the unit suites run under the standard pytest configuration in `packages/temper-placer/`. The import boundary gate (`uv run python scripts/import_linter_gate.py`) must stay green.

---

## Definition of Done

- The pre-flight survey classifies every gate as live or deprecated, and the registry enumerates every live gate's declared inputs and every physics parameter's consumers (U1).
- The registry validates every declared input against its container and every parameter against its consumers (U1).
- The probe proves each declared gate input live by a verdict flip under fail-forcing, and each physics parameter live by a delta over the measured noise floor (U2).
- The standing check runs in CI (warn-only or behind a first-run remediation PR initially) and fails on a dead input or unproven parameter (U3).
- The new check script has a `scripts/manifest.yaml` entry (U3).
- Non-declarative gate inputs are registered or documented as non-covered with reasons (U4).
- The four phantom `required_metrics` declarations are remediated — moved to a live container and proven, or removed — with attribution (U5).
- All new public functions have executed-line coverage; the validation test suite passes under the standard pytest run.

---

## Scope Boundaries

**In scope:** the live gates' declared inputs and the physics parameter set; the wire/unwire probe; the standing CI check; the pre-flight survey and the registration of non-declarative inputs; the phantom-`required_metrics` remediation.

**Out of scope:** rewiring any gate found dead — the check detects and reports; fixing is a separate change. Mutation of constraint encodings (that is R32); mutation of placement quality metrics (that is R36); changing physics parameter values in production; retuning the physics models.

**Unit mapping (merge of 007 into 019):** surviving 019 units keep their U-IDs U1–U4, retargeted to the live surface and extended with the absorbed 007 physics units (parameter inventory → U1, perturbation harness → U2, noise-floor → U2, plumbing gate → U3) for one registry, one harness, one gate; U5 is new from the 019 review fix.

### Deferred to Follow-Up Work

- Fixes for any dead inputs or unproven parameters the standing check discovers on its first run (each fix is its own change with its own attribution).
- Automated fail-forcing-value derivation for metrics whose threshold logic is not mechanical (currently reported `UNMEASURED`).
- A fully declarative input contract for CI gate scripts beyond the validation gates.
- Time-series tracking of parameter deltas across board revisions.
- Perturbation of firmware-side physics constants once the placer sweep is proven (aligns with the R18 firmware-assumption oracle).

---

## Sources / Research

- `docs/plans/2026-08-02-001-feat-validation-portfolio-plan.md` — the portfolio origin (R33, R37).
- `docs/plans/2026-07-23-006-fix-dead-parameter-wiring-sweep-plan.md` — the pattern source and the grep-scope lesson.
- `docs/evidence/2026-08-02-validation-portfolio-review.md` — the merge verdict (007 → 019), the 019 ground-truth correction (deprecated `RunMetrics` stub, phantom `required_metrics`), and fix-before-execution item 4 (pre-flight survey, live surface, warn-only landing).
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gate.py` — the live acceptance gate (inner audit + truth DRC) that is the primary probe target.
- `packages/temper-placer/src/temper_placer/validation/validation_gates.py` — the deprecated `required_metrics` surface and the four phantom declarations (U5).
- `packages/temper-placer/src/temper_placer/core/loss_types.py` — the deprecated `RunMetrics` stub.
- `packages/temper-placer/src/temper_placer/physics/thermal_fdm.py` — `k_fr4`, `k_copper`, conductivity-field builder.
- `packages/temper-placer/src/temper_placer/physics/thermal_potential.py` — `convection_weight`, airflow parameters.
- `packages/temper-placer/src/temper_placer/physics/heat_removal.py` — `H_CONV_BACKGROUND` convection constant.
- `packages/temper-placer/src/temper_placer/core/ipc2152.py` — IPC-2152 ampacity inputs.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` — the IPC-2152 ampacity gate.
- `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — the dead-parameter incident class this idea exists for.
- `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md` — the documented-NOTE convention for non-covered cases.
- `docs/physics-verification-methodology.md` — the fail-capable rule (R4) and the measured-not-assumed discipline.
