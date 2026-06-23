---
date: 2026-06-23
topic: ghost-pad-injection
focus: Inject HV creepage as physical obstacles in placement to unblock the 10 stuck nets and lift routing completion from 33% to ~100%
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (#2)
status: active
actors: PCB placer developer, CI system, closure test pipeline
---

# Requirements: Ghost-Pad Injection for HV Creepage

## Problem

The deterministic placer completes 8/24 HV nets (33%). The remaining 10 are blocked by IEC 60335-1 6mm creepage around Q1, Q2, D1, D2: placement places HV components close enough that no legal route between LV and HV domains exists, and the post-placement DRC oracle reports clearance violations that the router cannot satisfy. Today, `_reserve_slots` (`packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py:527-540`) treats every component footprint as a uniform disc sized by `_get_footprint_radius` (`phased_component_assignment.py:520-525`) and has no knowledge of which pins are HV. HV safety is enforced downstream by `drc_oracle.py:75-105` and the `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` rule, but only as a post-hoc report. The placer never sees the constraint, so it never respects it.

## Goals

- **G1.** Prevent the placer from assigning slots that place any HV pin within 6mm of any LV pin, for any component combination on the canonical temper board.
- **G2.** Decouple HV safety from the routing stage: routes never enter creepage-violating space because the placer never creates a placement that would require it.
- **G3.** Lift closure-test routing completion from 33% (8/24) to ≥90% (≥22/24) without regressing DRC clearance pass rate.
- **G4.** Reuse the existing `NetClassRules.safety_category` SSOT and `isolation_slots` config (`configs/temper_deterministic_config.yaml:482-499`) as inputs rather than re-encoding the 6mm rule in code.
- **G5.** Land in ≤50 lines of new code, ≤2 files touched, with full property-based and parity coverage before downstream ideas (channel-aware scoring, HV/LV guard strip) build on top.

## Non-Goals

- Changing the 6mm creepage constant — that is an electrical compliance value owned by `DesignRules.creepage_mm`.
- Rewriting the routing-stage DRC oracle or `INTERNAL_LAYER_CREEPAGE_FACTOR` policy.
- Implementing channel-aware placement scoring (ideation #3) or HV/LV guard strips (ideation #1). This is the prerequisite; later ideas compose with it.
- Reformatting the `isolation_slots` config schema. We consume it as-is.
- Adding runtime-pluggable clearance radii per net class. Out of scope until a second clearance tier is requested.

## User Stories

- **US1. Placer developer.** "I add an HV component to the board, run the placer, and observe that the solver never proposes a slot within 6mm of any HV pin position. I do not have to teach the placer about creepage — the ghost-pad mechanism handles it."
- **US2. CI maintainer.** "A new test fails loudly if `_reserve_slots` stops honoring the 6mm radius, so I cannot accidentally regress the HV invariant in a future refactor."
- **US3. Closure test owner.** "After deploying this change, the closure test reports ≥22/24 routed HV nets and zero new DRC creepage violations. I can attribute the lift to this initiative and not to coincidental downstream changes."
- **US4. Reviewer.** "I can read one short diff (~50 lines) and understand: HV pins are sourced from `NetClassRules.safety_category`, expanded by `DesignRules.creepage_mm` (6mm), and pre-injected into `used_slots` before the assignment loop. No new abstractions."

## Functional Requirements

- **FR1. HV pin source.** The placer reads HV pin positions from `NetClassRules.safety_category` (the existing SSOT) on the parsed `DesignRules` carried in `BoardState`. Pins whose net class is `HV` (or `safety_category == "HV"`) are eligible for ghost-pad injection. LV and signal pins are ignored.
- **FR2. Ghost-pad radius.** Each HV pin contributes a ghost pad centered on the pin's (x, y) in board coordinates, with radius equal to `DesignRules.creepage_mm` (6mm for IEC 60335-1).
- **FR2b. 2D-only ghost pads.** Ghost pads are 2D and applied uniformly. Inner-layer creepage reduction is a routing-stage concern and is not modeled by the placer; the placer will over-reserve on inner layers by design, which is acceptable per G2 (placement is the safety net, not routing).
- **FR3. Injection point.** Ghost pads are computed at the start of the placement pass and added to `used_slots` before the existing placement loop runs. The set is not exposed on `BoardState`; downstream stages remain unaware of the injection.
- **FR4. Reuse existing machinery.** Injection calls `_reserve_slots` (`phased_component_assignment.py:527-540`) with the ghost-pad center and radius. No duplicate geometry pass is introduced; the existing radius-based reservation is the single point of truth.
- **FR5. Isolation slot integration (optional, gated by FR5-toggle).** When `isolation_slots` (`configs/temper_deterministic_config.yaml:482-499`) is non-empty, the effective creepage radius is reduced by the slot's contribution along the slot's axis, per IEC 62368-1 Annex G. The reduction equals the slot length projected onto the pin-to-pin vector. Off-axis creepage is unchanged. If `isolation_slots` is empty (default), the radius is unchanged and behavior is identical to FR2. The toggle is the boolean `placer.use_isolation_slots` (default: `false`) in `configs/temper_deterministic_config.yaml`, parsed alongside `isolation_slots`. When `false`, FR5 is a no-op and behavior is bit-identical to FR2 (verified by NFR4 parity test).
- **FR6. Determinism preserved.** Ghost-pad generation is a pure function of `(DesignRules, BoardState.netlist, BoardState.components)`. It introduces no randomness, no I/O, and no global state. The placer's JAX-side seed contract is unaffected.
- **FR7. Logging.** When a placement attempt is rejected because a slot lies inside a ghost pad, the rejection is logged at DEBUG with `(component_ref, pin, slot_xy, ghost_pad_center, distance_mm)`. Production runs log at INFO summary: `ghost_pads_injected={N} slots_blocked={M}`.

## Non-Functional Requirements

- **NFR1. Performance.** Ghost-pad injection adds ≤5% wall time to `phased_component_assignment` for the canonical temper board. Measured against the pre-change baseline on a fixed seed.
- **NFR2. Code size.** ≤50 lines of new code, ≤2 source files touched, ≤1 config file modified. (FR5's isolation-slot path is excluded from this budget — it is a one-line config read.)
- **NFR3. Test coverage.** New code reaches ≥90% line coverage. Property-based tests (≥100 examples) cover: every HV pin produces a ghost pad; LV pins produce none; inner-layer radius reduction is exact; injection is idempotent under repeated calls; `used_slots` membership is symmetric in (component, ghost-pad center).
- **NFR4. Parity.** A parity test asserts that for the canonical board with no HV components, the post-change `placement_result` is bit-identical (coordinates and slot assignments) to the pre-change result. The change is invisible to LV-only boards.
- **NFR5. Per-stage DRC fence.** A stage-DRC validator runs after `_inject_ghost_pads` and asserts: (a) for every HV pin, every candidate slot whose center lies within `creepage_mm` of that pin is present in `used_slots`; (b) for every candidate slot whose center lies within `creepage_mm` of any HV pin, that slot is in `used_slots`; (c) no slot in `used_slots` is closer than `creepage_mm` to an LV pin position unless the slot's origin is also an LV pin. Failure raises a typed `StageDRCFailure` per `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`.
- **NFR6. Backward compatibility.** `BoardState` schema is unchanged. `NetClassRules.safety_category` parsing is unchanged. `isolation_slots` config schema is unchanged. Downstream stages (`zone_assignment`, routing) are unchanged.

## Out of Scope

- Consuming `isolation_slots` inside `zone_aware_slot_generation.py:231-288` (`_is_slot_in_copper_zone`) — that is ideation #7, a separate initiative. FR5 here is a one-off call inside the placer, not a slot-generation hook.
- Replacing `_get_footprint_radius` (`phased_component_assignment.py:520-525`) with a per-pin variant for non-HV components. The function continues to be called for LV pins with its current behavior.
- Topology surgery (HV/LV guard strip, ideation #1) and channel-aware scoring (ideation #3). These compose with this initiative but are not delivered here.
- Multi-tier creepage (e.g., 8mm for reinforced insulation, 4mm for functional). A single `creepage_mm` value is the only input.
- Visualizing ghost pads in KiCad output. The placer's internal model only; `kicad_writer` is untouched.

## Success Metrics

- **SM1.** Closure test `router_completion_pct ≥ 90%` on the canonical temper board (was 33%, target ≥90%, stretch 100%).
- **SM2.** DRC clearance pass rate remains ≥96.7% (the pre-change baseline from past learnings). No regression.
- **SM3.** Per-stage DRC fence validator passes on the canonical board, the LV-only parity board, and a synthetic 100-HV-pin stress board.
- **SM4.** Property-based test suite (≥100 examples per strategy) passes with no `hypothesis` health-check failures.
- **SM5.** Code metrics: ≤50 lines added, ≤2 source files touched, ≥90% coverage on new code, parity test diff = 0 on LV-only boards.
- **SM6.** Wall time regression: `phased_component_assignment` completes within 105% of the pre-change baseline on the canonical board at fixed seed.

## Dependencies

- `packages/temper-placer/src/temper_placer/core/design_rules.py` — `NetClassRules.safety_category`, `DesignRules.creepage_mm` (SSOT for HV classification and clearance value).
- `packages/temper-placer/src/temper_placer/deterministic/state.py` — `BoardState` carrying `design_rules`, `netlist`, `components` (read-only inputs).
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py:520-540` — `_get_footprint_radius` and `_reserve_slots` (consumed, not modified).
- `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py:75-105` — clearance matrix and `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` (read for parity with routing's understanding of creepage).
- `configs/temper_deterministic_config.yaml:482-499` — `isolation_slots` config (consumed by FR5 only).
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — DRC fence pattern the new validator must conform to.
- Closure test harness — for SM1 and SM2 measurement.

## Assumptions

1. **`NetClassRules.safety_category` already populates correctly for the canonical board.** Verified by reading `setup.py:53-69` which populates the field from the parsed YAML. Spot-check: Q1, Q2, D1, D2 are tagged `HV`.
2. **`DesignRules.creepage_mm == 6.0`** is the only value in production. No per-net-class override exists. The single-value assumption collapses the radius-computation problem.
3. **`_reserve_slots` is the sole slot-blocking primitive** in `phased_component_assignment`. Confirmed by reading `phased_component_assignment.py:527-540`. Any future second primitive would need to consume the same ghost-pad set.
4. **HV pin positions are stable across retries** (i.e., component placement does not move HV pins relative to the component origin before the ghost-pad pass runs). This holds for through-hole and SMD pads modeled as fixed offsets from component ref.
5. **The placer's slot grid is finer than 6mm.** If slot spacing ≥ 6mm, ghost-pad reservation cannot distinguish "violating" from "compliant" and the mechanism degenerates. Verify slot_spacing ≤ 3mm on the canonical board before relying on FR1's guarantees.
6. **The closure test's 33% baseline is reproducible at fixed seed.** Required for SM1 and SM6 to be measurable. If the baseline drifts, the success threshold needs a paired re-measurement.

## Open Questions

### Resolve Before Planning

- **[Affects FR1][Technical]** Is `NetClassRules.safety_category` populated on every net class in the canonical config, or only on HV ones? If the field is missing for LV classes (defaulting to `None`), the placer must treat `None` as LV — confirm by reading `setup.py:60-65` and a sample net class block.
- **[Affects FR2][Technical]** Should inner-layer reduction use `creepage_mm * INTERNAL_LAYER_CREEPAGE_FACTOR` (1.8mm) or skip ghost-pad injection entirely on inner layers? The DRC oracle applies a reduction; the placer could either match or over-reserve. Recommendation: match the oracle to keep placer/router agreement.
- **[Affects FR5][Technical]** The `isolation_slots` entries in the config are tied to specific component refs (`Q1`, `Q2`). If a future config adds a slot for a non-HV component, does the placer still apply creepage reduction? Recommendation: ignore the slot unless the referenced component has at least one HV pin.
- **[Affects NFR5][Technical]** Where does the per-stage DRC validator live — as a method on `PhasedComponentAssignment`, or as a standalone function registered via `@register_validator("PhasedComponentAssignment")`? The latter matches the recommendation in `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`.

### Deferred to Planning

- **[Affects SM1][Needs measurement]** Re-run the closure test on `main` at a fixed seed to confirm the 33% baseline before shipping the change. Required so SM1's threshold is anchored to a real number.
- **[Affects NFR1][Needs measurement]** Profile the pre-change `phased_component_assignment` wall time on the canonical board at a fixed seed. Target is ≤5% overhead; the baseline measurement is needed to compute the budget.
- **[Affects FR3][Design]** Should ghost-pad injection run inside the per-component loop (re-injecting per call) or once at stage start (pre-computing the full set)? Per-component is simpler but O(N×M); pre-compute is O(M) once. The 5% NFR1 ceiling should pick.
