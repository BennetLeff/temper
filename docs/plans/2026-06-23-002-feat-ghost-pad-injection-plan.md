---
type: feat
origin: docs/brainstorms/2026-06-23-ghost-pad-injection-requirements.md
status: active
date: 2026-06-23
---

# Plan: Ghost-Pad Injection for HV Creepage

## Problem Frame

The deterministic placer completes 8/24 HV nets (33%) because `_reserve_slots` in `phased_component_assignment.py:527-540` treats every footprint as a uniform disc via `_get_footprint_radius` (`phased_component_assignment.py:520-525`) and has no knowledge of which pins are HV. IEC 62368-1 6mm creepage around Q1, Q2, D1, D2 is only enforced downstream by `drc_oracle.py:75-105` as a post-hoc report, so the placer produces placements the router cannot legally route. This plan injects HV pin positions as 6mm-radius "ghost pads" into `used_slots` before the assignment loop, reusing `NetClassRules.safety_category` and `DesignRules.creepage_mm` as the SSOTs and lifting closure completion from 33% to ≥90% (SM1) without regressing DRC clearance (SM2). Downstream ideas (channel-aware scoring, HV/LV guard strip) compose on top of this prerequisite.

## Implementation Units

### U1. Ghost-Pad Injection Core

**Goal.** Inject 6mm-radius obstacles at every HV pin position into `used_slots` before the existing placement loop runs, with no schema change and no downstream visibility.

**Requirements.** FR1, FR2, FR2b, FR3, FR4, FR6, FR7, NFR1, NFR2, NFR6.

**Files.**
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py`
- `packages/temper-placer/src/temper_placer/deterministic/state.py` (read-only access to `design_rules`, `netlist`, `components`; no schema change)

**Approach.**
- Add a private method `_collect_hv_pin_positions(state)` that iterates `state.components`, looks up each pin's net class via `state.design_rules.net_classes`, and returns `[(pin.x, pin.y, component_ref, pin_name), ...]` for pins whose `safety_category == "HV"`. Treat `None`/missing as LV (per open question A.1 resolution).
- Add a private method `_inject_ghost_pads(state, used_slots, all_slots)` that calls existing `_reserve_slots(phased_component_assignment.py:527-540)` once per HV pin with radius `state.design_rules.creepage_mm` (FR4 — single point of truth for the base; U2 may apply isolation-slot reductions on top). No geometry pass is duplicated.
- Invoke `_inject_ghost_pads` once at the top of the existing assignment loop (pre-compute path, O(M) once per stage — per open question A.3).
- Add a DEBUG log on rejection (FR7) and an INFO summary line `ghost_pads_injected={N} slots_blocked={M}` at stage end.
- Inner-layer reduction is NOT modeled (FR2b — over-reserve on inner layers by design).

**Test scenarios.**
- `test_hv_pin_yields_ghost_pad`: input canonical board, expected `used_slots` contains every slot within 6mm of an HV pin.
- `test_lv_pin_yields_no_ghost_pad`: input board with all `safety_category="LV"`, expected `used_slots` identical to pre-change baseline (parity anchor).
- `test_none_safety_category_treated_as_lv`: input pin with `safety_category=None`, expected no ghost pad.
- `test_injection_idempotent`: input state, call twice, expected `used_slots` membership equal.
- `test_no_randomness_seed_unchanged`: input fixed seed, expected identical `placement_result` across two runs.
- `test_hv_pin_at_slot_grid_boundary_still_blocked`: synthetic board with an HV pin positioned within 1 slot-spacing of the board edge, expected the edge-adjacent slot is reserved in `used_slots` (covers the A5 slot-grid-boundary failure mode).
- `test_empty_net_classes_yields_no_ghosts`: input state with `state.design_rules.net_classes = {}`, expected `used_slots` is empty and no exception is raised.

**Verification.** `pytest packages/temper-placer/tests/test_phased_component_assignment.py -k ghost_pad`; closure test re-run shows `router_completion_pct` trending toward SM1's 90% target; wall time within 5% of pre-change baseline (SM6).

### U2. Isolation-Slot Creepage Reduction (FR5, gated)

**Goal.** When `placer.use_isolation_slots: true` in the config, reduce the effective ghost-pad radius by the projection of each `isolation_slots` entry onto the pin-to-pin vector, per IEC 62368-1 Annex G. When `false` (default), behave bit-identically to U1.

**Requirements.** FR5, NFR4. (FR5 — creepage reductions conform to IEC 62368-1 Annex G, the same standard governing the 6mm base radius in the problem frame.)

**Files.**
- `configs/temper_deterministic_config.yaml` (add `placer.use_isolation_slots: false` key alongside `isolation_slots` at line 482)
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (extend `_inject_ghost_pads` with the gated reduction path)

**Approach.**
- Read `placer.use_isolation_slots` and `isolation_slots` at stage init; cache on the stage instance.
- When `use_isolation_slots=False`, skip this unit's logic entirely (NFR4 parity).
- When `True`, for each `(pin, isolation_slot)` pair, compute the slot length projected onto the pin-to-other-HV-pin vector; subtract that projection from the effective radius (clamped at 0). Apply only when the referenced component has at least one HV pin (open question A.5).
- The reduction runs strictly after U1's base-radius reserve and is clamped so the effective radius never exceeds `state.design_rules.creepage_mm` (the FR4 base) — it can only reduce, never expand.
- One-line config read; reduction path excluded from NFR2's 50-line budget.

**Test scenarios.**
- `test_isolation_slots_disabled_is_bit_identical`: input `use_isolation_slots=False`, expected `placement_result` bit-identical to U1's result.
- `test_isolation_slots_enabled_reduces_radius`: input `use_isolation_slots=True` with Q1 slot, expected effective Q1 radius = 6mm − projected slot length, off-axis distance unchanged.
- `test_isolation_slot_on_lv_component_ignored`: input slot referencing a non-HV component, expected no reduction applied.

**Verification.** Parity test passes with toggle off; targeted reduction test passes with toggle on; config validates with `python -c "import yaml; yaml.safe_load(open('configs/temper_deterministic_config.yaml'))"`.

### U3. Per-Stage DRC Fence Validator

**Goal.** Add a typed validator that runs after `_inject_ghost_pads` and asserts HV slot-blocking is total and symmetric, conforming to `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`.

**Requirements.** NFR5.

**Files.**
- `packages/temper-placer/src/temper_placer/router_v6/stage_validators.py` (reuse `StageDRCFailure`, `register_validator`, `run_validators`)
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (call `run_validators("PhasedComponentAssignment", state)` after the assignment loop, before return)

**Approach.**
- Register `validate_phased_component_assignment_hv` via `@register_validator("PhasedComponentAssignment")` in a new small module or appended to `phased_component_assignment.py`.
- Validator walks `state.design_rules.net_classes` for HV pins, then for each candidate slot in `all_slots` checks: (a) for every HV pin p, every slot within `creepage_mm` of p is in `used_slots` [coverage]; (b) for every slot s in `used_slots` whose origin is not an LV pin position, no HV pin is within `creepage_mm` of s [non-over-claim]. Violations yield `StageDRCFailure(field=..., value=slot_xy, reason=..., stage="PhasedComponentAssignment")`.

**Test scenarios.**
- `test_validator_passes_on_canonical_board`: input canonical board, expected zero `StageDRCFailure`.
- `test_validator_fails_when_hv_slot_unblocked`: input manually remove one HV-pin ghost pad, expected one `StageDRCFailure` referencing the unblocked slot.
- `test_validator_fails_when_lv_slot_too_close`: input inject a near-LV slot outside LV-pin origin, expected one `StageDRCFailure`.
- `test_validator_passes_on_lv_only_board`: input LV-only board, expected zero failures (parity with U1).
- `test_validator_passes_on_100_hv_pin_stress_board`: input synthetic board, expected zero failures (SM3).
- `test_validator_handles_zero_creepage_mm`: input board with `creepage_mm=0.0`, expected validator passes with zero failures (degenerate radius case).
- `test_validator_handles_large_creepage_mm`: input board with `creepage_mm` larger than the board diagonal, expected validator passes with zero failures (saturation case).

**Verification.** `pytest packages/temper-placer/tests/test_stage_validators.py -k phased_component_assignment`; failure path raises typed `StageDRCFailure`, not generic `AssertionError`.

### U4. Property-Based & Parity Coverage

**Goal.** Achieve NFR3's ≥100-example property coverage and NFR4's bit-identical parity on LV-only boards; satisfy SM4 and SM5.

**Requirements.** NFR3, NFR4, SM4, SM5.

**Files.**
- `packages/temper-placer/tests/property/test_ghost_pad_injection.py` (new)
- `packages/temper-placer/tests/parity/test_lv_only_parity.py` (new)
- `packages/temper-placer/tests/property/conftest.py` (hypothesis strategies for `DesignRules`, `BoardState`, net-class tables) — reuse if it exists

**Approach.**
- Hypothesis strategies: arbitrary `DesignRules` with mixed HV/LV/None `safety_category`; arbitrary `BoardState` with N pins (0 ≤ N ≤ 200).
- Properties: (1) every HV pin → ≥1 ghost pad; (2) no LV pin → ghost pad; (3) injection is idempotent; (4) `used_slots` membership is symmetric in (component, ghost-pad center).
- Parity test: snapshot the pre-change `placement_result` for a frozen LV-only board fixture; assert post-change result is byte-equal.
- Configure `hypothesis.HealthCheck` to fail the suite on data-dependence or filter-too-much warnings.

**Test scenarios.**
- `test_property_every_hv_pin_produces_ghost_pad`: 100+ examples.
- `test_property_no_lv_pin_produces_ghost_pad`: 100+ examples.
- `test_property_injection_idempotent`: 100+ examples.
- `test_parity_lv_only_bit_identical`: single frozen fixture, exact equality.
- `test_coverage_new_code_ge_90`: pytest-cov gate on changed lines.

**Verification.** `pytest --hypothesis-seed=0 -p no:cacheprovider` passes; coverage report on `phased_component_assignment.py` ghost-pad methods ≥90%; parity fixture diff = 0.

### U5a. Pre-Change Baseline (runs on `main` before any code change)

**Goal.** Record the pre-change closure numbers on `main`, commit them as a fixture, and freeze the baseline so the candidate branch can be compared against an immutable reference.

**Requirements.** SM1, SM2, SM3, SM4, SM5, SM6; resolves open question A.4 (baseline re-measurement).

**Files.**
- `packages/temper-placer/tests/closure/fixtures/baseline_closure.json` (new — committed baseline numbers)
- `docs/closure-reports/2026-06-23-ghost-pad-injection.md` (new — human-readable baseline record)
- `packages/temper-placer/tests/closure/test_router_completion.py` (read for SM1/SM2 measurement, no edits)

**Approach.**
- Run closure test on `main` at a fixed seed; record `router_completion_pct`, DRC clearance pass rate, and wall time as the pre-change baseline.
- Write the numbers to `tests/closure/fixtures/baseline_closure.json` and commit the fixture to `main` with a timestamp strictly before U1's merge commit.
- Mirror the numbers into `docs/closure-reports/2026-06-23-ghost-pad-injection.md` for human review.

**Test scenarios.**
- `test_closure_pre_change_baseline_recorded`: asserts `tests/closure/fixtures/baseline_closure.json` exists, contains the required fields, and the file's committed timestamp predates U1's merge commit on the candidate branch.

**Verification.** `pytest` on `main` (no code change applied) passes; fixture file present in the repo and timestamped before U1 merge; baseline block present in the closure report.

### U5b. Post-Change Promotion Gate (runs on candidate branch)

**Goal.** Compare candidate-branch closure numbers against the committed U5a fixture and block promotion unless SM1/SM2/SM6 all clear.

**Requirements.** SM1, SM2, SM3, SM4, SM5, SM6.

**Files.**
- `packages/temper-placer/tests/closure/test_router_completion.py` (add post-change comparison tests)
- `docs/closure-reports/2026-06-23-ghost-pad-injection.md` (append post-change block)

**Approach.**
- Run closure test on the candidate branch at the same fixed seed used by U5a.
- Read the committed `tests/closure/fixtures/baseline_closure.json` and assert candidate numbers clear SM1 (≥90%), SM2 (≥96.7%), SM6 (≤105% wall time vs. baseline).
- If any gate fails, file a follow-up issue and do not merge.
- Capture `ghost_pads_injected={N} slots_blocked={M}` log line and per-stage validator output for the closure report.

**Test scenarios.**
- `test_closure_post_change_meets_sm1`: compares candidate `router_completion_pct` against baseline; expected ≥90% and ≥baseline.
- `test_closure_post_change_meets_sm2`: compares candidate DRC clearance pass rate against baseline; expected ≥96.7% and ≥baseline.
- `test_closure_post_change_meets_sm6`: compares candidate wall time against baseline; expected ≤105% of baseline.

**Verification.** All three scenarios pass on the candidate branch; closure report diffs reviewed; `git status` clean; U5a fixture unchanged on the candidate branch (verified by git diff against `main`).

## Risks & Dependencies

- **Assumption risk (A5 — slot grid fineness).** If `state.slot_spacing ≥ 6mm` on the canonical board, the ghost-pad mechanism degenerates. Verify on the canonical board before U1 ships; if violated, file a discovered-from issue and pause. U1's `test_hv_pin_at_slot_grid_boundary_still_blocked` directly exercises the slot-grid-boundary case and must pass before U1 merges.
- **Baseline reproducibility (Assumption 6).** The 33% number must be reproducible at fixed seed. U5's pre-change run confirms or triggers a paired re-measurement.
- **Determinism coupling.** U1 must not introduce JAX-side randomness; FR6 verified by U4's seed-stability property.
- **Config schema coupling.** U2's `placer.use_isolation_slots` is additive (new key, default `false`) and must not break existing config loaders. `temper_deterministic_config.yaml:482-499` block is the only touch point.
- **DRC fence ordering.** U3's validator must run after `_inject_ghost_pads` and after the assignment loop, before the stage return. If the orchestrator calls `run_validators` at a different hook point, the validator sees post-loop state — confirm against `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md`.
- **Inner-layer over-reservation (FR2b).** The placer will over-reserve on inner layers by design; this is acceptable per G2 but may reduce slot availability for inner-layer routing in extreme cases. Wall-time gate (SM6) catches it.
- **Upstream SSOT stability.** `NetClassRules.safety_category` and `DesignRules.creepage_mm` are owned by other plans; changes there invalidate FR1/FR2 and require re-running U4's parity test.

## Scope Boundaries

**Deferred to Follow-Up Work.**
- Channel-aware placement scoring (ideation #3) — composes on top of U1's clean `used_slots`.
- HV/LV pre-placement guard strip (ideation #1) — structural complement to ghost pads.
- Pre-route HV clearance obstacle expansion in the obstacle map (ideation #5) — routing-stage counterpart.
- Min-cut bottleneck detection (ideation #6) — diagnostic infrastructure.

**Out of Scope.**
- Changing `DesignRules.creepage_mm` from 6.0 — electrical compliance value, owned elsewhere.
- Rewriting `drc_oracle.py` or `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` — routing-stage policy.
- Reformatting the `isolation_slots` config schema — consumed as-is in U2.
- Per-net-class creepage tiers (8mm reinforced, 4mm functional) — single-value assumption holds (Assumption 2).
- `_get_footprint_radius` becoming per-pin for non-HV components — stays as-is for LV pins.
- Consuming `isolation_slots` inside `zone_aware_slot_generation.py:231-288` (`_is_slot_in_copper_zone`) — ideation #7, separate initiative.
- Visualizing ghost pads in KiCad output — placer-internal only; `kicad_writer` untouched.
- Runtime-pluggable clearance radii per net class — out of scope until a second tier is requested.
