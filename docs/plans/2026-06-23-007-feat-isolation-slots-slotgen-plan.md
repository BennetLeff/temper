---
date: 2026-06-23
type: feat
origin: docs/brainstorms/2026-06-23-isolation-slots-requirements.md
status: active
---
# Plan: Consume Existing Isolation Slots in Slot Generation

## Problem Frame

The deterministic PCB routing pipeline completes only 33% of nets (8/24) before hitting a wall: 10 nets are blocked by 6mm HV creepage clearances around TO-247 power components Q1, Q2, D1, D2. The config `configs/temper_deterministic_config.yaml:482-499` already declares `isolation_slots` — 1.5mm milled cutouts that force the creepage path to detour, achieving 12-15mm effective creepage. The data path is broken: `packages/temper-placer/src/temper_placer/deterministic/__init__.py` never extracts `isolation_slots` from `Constraints`, and `packages/temper-placer/src/temper_placer/deterministic/stages/zone_aware_slot_generation.py:231-288` filters slots against copper pour polygons only — it has no concept of milled isolation cutouts as slot-blockers and no mechanism to communicate the effective clearance reduction to the DRC oracle. The fix reuses the existing config (no new keys, no new data structures) and closes the seam between slot generation and the DRC oracle.

## Implementation Units

### U1. Thread `isolation_slots` from Constraints to slot-generation stage

Goal: Make the existing YAML-declared `isolation_slots` available to `ZoneAwareSlotGenerationStage` without mutating or dropping fields.

Requirements: R1, R4 (regression guard)

Files:
- packages/temper-placer/src/temper_placer/deterministic/__init__.py
- packages/temper-placer/src/temper_placer/io/config_loader.py (read-only reference, no edits)

Approach: Add a new local `yaml_isolation_slots = []` in the deterministic module's config-extraction block alongside `yaml_copper_zones`, `yaml_slot_generation`, `yaml_net_class_rules`, `yaml_hv_exclusion_zones`. Populate it via `getattr(config, "isolation_slots", [])` so the call degrades to an empty list if the field is absent (older configs, tests). Pass it as a new keyword argument `yaml_isolation_slots=yaml_isolation_slots` to the `ZoneAwareSlotGenerationStage` constructor in the same line that already passes `yaml_copper_zones`. The value is the same `list[IsolationSlot]` populated by `io/config_loader.py:1304-1319` — `name`, `component_ref`, `start_offset`, `end_offset`, `width_mm`, `lv_pin`, `hv_pin` all preserved by reference.

Test scenarios:
- `extract_passes_iso_slots_to_stage`: input — `Constraints` with Q1 and Q2 isolation slots from `configs/temper_deterministic_config.yaml`; action — run `DeterministicPipeline.build()`; expected — stage receives a list with identical `len()`, `component_ref`, `width_mm`, `lv_pin`, `hv_pin` for every entry (object identity preserved).
- `extract_tolerates_missing_field`: input — `Constraints` constructed without setting `isolation_slots`; action — build pipeline; expected — stage receives `[]`, no `AttributeError`.
- `regression_round_trip_via_kicad_writer`: re-run `tests/io/test_isolation_slots.py`; expected — all existing assertions pass unchanged, confirming the slot data is not mutated when threaded through the builder (R4 guard).

Verification: `uv run pytest packages/temper-placer/tests/io/test_isolation_slots.py` green; new unit tests for extraction pass.

### U2. Treat isolation slots as slot-blockers and emit reclaim

Goal: Reject candidate slots that intersect any isolation-slot cutout, and emit the per-component clearance reclaim that downstream consumers (U3) will use.

Requirements: R2, R6 (logging portion)

Files:
- packages/temper-placer/src/temper_placer/deterministic/stages/zone_aware_slot_generation.py
- packages/temper-placer/src/temper_placer/io/isolation_slot_geometry.py (new helper, ≤10 lines: convert component-local `start_offset`/`end_offset` + current component position + `width_mm` into an axis-aligned board-coords rectangle)

Approach: Mirror the existing copper-zone filter. Compute each isolation slot's board-coords AABB once per stage run, expanded by `slot.width_mm / 2` on each side (the cutout width is the blocker footprint, per K2). In the per-candidate-slot filter, add a containment test equivalent to `_is_slot_in_copper_zone` but using the isolation rectangles. Reject the candidate if its AABB intersects any isolation rectangle. Compute the reclaim for each slot using the K4 formula: `reclaim = clamp(slot.width_mm / 2 + perpendicular_clearance_budget - 5.45, 0, original_requirement - 0.5)`, with `perpendicular_clearance_budget = 5.5` and `original_requirement = 6.0` (Q1/Q2 default — read from `net_class_rules` if available, else hard-coded default). Bundle the reclaims into a `dict[tuple[str, str, str], float]` keyed by `(component_ref, lv_pin, hv_pin)` and stash on the stage output (a new attribute on the existing output dataclass — no new top-level structure). Extend the existing `logger.info` block (lines 224-227) to report `copper_zone_filtered=N, isolation_slot_filtered=M` on separate lines, and add `f"Isolation slots reclaim {total_reclaim_mm:.2f}mm of routing channel"` (R6).

Test scenarios:
- `slot_overlapping_cutout_is_rejected`: input — Q1 isolation slot at `(2.725, -5.0) → (2.725, 5.0)` with `width_mm=1.5`; action — generate a candidate slot whose AABB straddles `(2.725, 0.0)`; expected — candidate is dropped, no overlap appears in the emitted slot set.
- `slot_outside_cutout_is_kept`: input — same Q1 isolation slot; action — candidate slot at `(0.0, 0.0) → (-5.0, 0.0)` (perpendicular channel, outside cutout footprint); expected — candidate survives, appears in emitted set.
- `reclaim_matches_k4_formula_with_defaults`: input — Q1 slot with `width_mm=1.5`, `Constraints` with no `net_class_rules` override; action — read `reclaim_by_pin_pair` from stage output for key `(Q1, gate, drain)`; expected — `reclaim = 0.8mm`, `effective_requirement = 5.2mm` (the K4 worked example with hard-coded `perpendicular_clearance_budget=5.5`, `original_requirement=6.0`).
- `reclaim_reads_from_net_class_rules`: input — Q1 slot with `width_mm=1.5`, `net_class_rules` sets Q1/Q2 HV `clearance_mm=5.5`; action — read reclaim for key `(Q1, gate, drain)`; expected — `reclaim = clamp(1.5/2 + 5.5 - 5.45, 0, 5.5 - 0.5) = 0.8mm`, `effective_requirement = 4.7mm` (confirms net_class_rules drives the formula).
- `reclaim_clamps_to_zero_when_cutout_is_wider_than_5mm`: input — Q1 slot with `width_mm=12.0`; action — read reclaim for key `(Q1, gate, drain)`; expected — `reclaim = clamp(6 + 5.5 - 5.45, 0, 5.5) = 5.5` (saturates the upper clamp).
- `log_lines_report_separate_filter_counts`: action — run stage with both copper zones and isolation slots present; expected — log contains both `copper_zone_filtered` and `isolation_slot_filtered` integers plus the reclaim summary line.

Verification: New unit tests pass; stage log lines appear in captured log output; emitted slot count strictly less than or equal to the pre-change count for the closure test board.

### U3. DRC oracle accepts spatially-scoped clearance credit

Goal: Permit clearance checks between a slot's `lv_pin` and `hv_pin` to use a reduced requirement, but only when the line between the two pad centers lies inside the slot's reclaimed band.

Requirements: R3

Files:
- packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py

Approach: Extend `DRCOracle` to accept a `clearance_credits: dict[tuple[str, str, str], tuple[float, ...]]` (mapping `(component_ref, pin_a, pin_b) → (effective_clearance_mm, half_width_mm, half_length_mm)`) injected at construction (or via a setter called by the pipeline after U2 runs). Pin resolution — accept a `pin_owner: Callable[[str], str] | dict[str, str]` mapping each `pin_id` to its `component_ref` (populated from the placed Components at pipeline-build time). In the clearance check, for each credited `(component_ref_c, pin_a_c, pin_b_c)`, require the resolved owners of `net_a`'s pin and `net_b`'s pin to BOTH be `component_ref_c`; if either lookup is missing or yields a different `component_ref`, fall back to the uncredited `ClearanceMatrix` value. Do not attempt cross-component credit on this iteration. When a check's `net_a` and `net_b` pins resolve to a credited `(component_ref, pin_a, pin_b)` and the credited `component_ref` matches both pin owners (or one of them and the other is on the same component), test the line segment between pad centers against the credit rectangle: an AABB centered on the slot's midpoint, oriented along the slot's axis, with half-extents `(half_length_mm, half_width_mm + max(slot.width_mm / 2, 0.5))` (per R3 spatial scope). If the segment intersects the AABB, apply the reduced clearance for that check; otherwise fall back to the original `ClearanceMatrix` value. Do not modify `INTERNAL_LAYER_CREEPAGE_FACTOR` (K5) — credit stacks multiplicatively with internal-layer credit.

Test scenarios:
- `credit_applied_within_band`: input — credit for `(Q1, gate, drain)` with `effective=5.2, half_length=10, half_width=1.25`; action — check clearance between pads at `(2.725, -4.0)` and `(2.725, 4.0)` (inside the slot's reclaimed band); expected — pass at 5.2mm, fail at 5.1mm.
- `credit_not_applied_outside_band`: input — same credit; action — check clearance between pads at `(0.0, 0.0)` and `(10.0, 0.0)` (perpendicular axis, far from slot); expected — original 6.0mm requirement applies; 5.5mm is rejected.
- `credit_does_not_apply_to_other_components`: input — credit for `(Q1, gate, drain)`; action — check clearance between two D1 pads; expected — 6.0mm original requirement applies, credit ignored.
- `credit_stacks_with_internal_layer`: input — credit for `(Q1, gate, drain)` on internal layer; action — check 1.6mm clearance on internal layer; expected — pass (5.2 × 0.30 = 1.56 < 1.6), confirming multiplicative stacking.
- `credit_skipped_when_pin_owner_differs`: input — credit for `(Q1, gate, drain)`; `pin_owner` maps `net_a`'s pin to `Q1` and `net_b`'s pin to `Q2`; action — check clearance between those two pads; expected — original 6.0mm requirement applies (cross-component credit is rejected, falls back to `ClearanceMatrix`).

Verification: New oracle unit tests pass; existing oracle tests still pass (no behavior change for uncredited pin pairs).

### U4. End-to-end test suite and completion-rate gate

Goal: Prove the seam works end-to-end and unlocks the 10 previously-stuck nets.

Requirements: R5

Files:
- packages/temper-placer/tests/deterministic/test_isolation_slots_in_slot_generation.py (new)
- docs/test-boards/closure-seeds.txt (read-only reference)

Approach: Create a new test module under `packages/temper-placer/tests/deterministic/`. The fixture loads the real `configs/temper_deterministic_config.yaml`, builds `DeterministicPipeline` end-to-end, runs slot generation, asserts the U1 thread (stage received the slot list), asserts U2 outputs (no slot overlaps a cutout, reclaim dict has Q1/Q2 entries with the K4 value), asserts U3 by constructing a `DRCOracle` with the reclaim dict and running clearance checks (mirrors the U3 unit tests in a more integration-shaped harness). The end-to-end test runs the full placement-to-routing closure on the three seeds in `docs/test-boards/closure-seeds.txt` and asserts the 10 previously-stuck Q1/Q2 nets (enumerated in a new fixture inside this test module) complete at every seed. Mark as `@pytest.mark.slow` and gate behind an env var or existing slow-test marker if one exists in `packages/temper-placer/tests/conftest.py`.

Test scenarios:
- `full_pipeline_extracts_iso_slots` (R1 integration): input — full `Constraints` load; action — run pipeline; expected — `stage.isolation_slots == constraints.isolation_slots` (U1 surface).
- `stage_filters_overlapping_candidates` (R2 integration): action — run stage on closure board; expected — `count(s for s in emitted if aabb_intersects(s, iso_rect)) == 0`.
- `oracle_accepts_credited_clearance` (R3 integration): action — build oracle with stage's reclaim dict; expected — clearance check at 5.2mm inside slot band passes, at 5.1mm fails.
- `closure_completion_reaches_23_of_24` (success criterion): action — run full pipeline on 3 seeds; expected — routed net count ≥ 17/24 at each seed (8 baseline + 9 Q1/Q2-attributable stuck nets from the brainstorm net-attribution mapping); the D1↔D2 net is explicitly excluded per scope boundary. The remaining 7 nets (those not attributable to Q1/Q2 isolation slots) are deferred to follow-up work; file a follow-up issue for them. Zero new DRC violations (per the brainstorm's success criteria).

Verification: New test file passes locally; `uv run pytest packages/temper-placer/tests/deterministic/test_isolation_slots_in_slot_generation.py -m slow` green; `uv run pytest packages/temper-placer/tests/io/test_isolation_slots.py` still green (U1 regression guard).

## Risks & Dependencies

- **R1 (slot data shape drift).** If `IsolationSlot` adds a new field in a future config-loader change, the K4 formula's inputs (`width_mm`, offsets) remain stable but downstream consumers may break. Mitigated by the U1 object-identity preservation guarantee and the U4 round-trip test.
- **R2 (intersection-test precision).** AABB-vs-AABB intersection is robust for the rectilinear cutouts declared in config, but if a future slot uses non-rectangular geometry, the test will silently let overlaps through. Document this assumption in `isolation_slot_geometry.py` and add a fixture-level assert that all current slots are axis-aligned.
- **R3 (K4 constants are config-derived).** The worked example uses `perpendicular_clearance_budget = 5.5mm` and `original_requirement = 6.0mm` hard-coded. These should be sourced from `net_class_rules` (already on `Constraints`) when present. U2 reads them from there; document the fallback.
- **D1.** Stacks after #2 (ghost-pad injection) and #4 (seed filtering) so the placer already understands HV exclusion when the credit is applied. Per-stage DRC fence (U3) catches any R3 violation where the credit leaks outside its spatial scope.
- **Code budget.** ≤40 lines net excluding tests (ideation estimate). U1 ≈ 4 lines, U2 ≈ 20 lines (geometry helper + filter + reclaim + logs), U3 ≈ 12 lines (credit lookup + band test). Within budget.

## Scope Boundaries

**Deferred to follow-up work:**
- Adding D1/D2 or transformer-secondary isolation slots to `configs/temper_deterministic_config.yaml`. The D1↔D2 net is the only one of the 10 stuck nets not covered by Q1/Q2 slots; defer until the seam is proven on Q1/Q2.
- Geometric optimization of slot position per component. The config-declared `(2.725, -5.0) → (2.725, 5.0)` is treated as ground truth.
- Routing the reclaimed-channel score into placement-stage scoring (the per-stage DRC fence can be extended to emit a per-credit contribution to `_place_optimize` loss terms — out of scope for this plan).
- Non-rectangular isolation slot geometry (curved or L-shaped cutouts). The AABB intersection test assumes axis-aligned rectangles.

**Out of scope:**
- Modifying `packages/temper-placer/src/temper_placer/io/kicad_writer.py:1132-1189`. The output path is already correct; touching it risks the round-trip regression guard.
- Changing `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` or `INTERNAL_LAYERS` in `drc_oracle.py:60-71`. The slot credit stacks with the internal-layer factor (K5), not replaces it.
- Removing or weakening the 6mm HV clearance in the config's `net_class_rules`. The reduction is per-pin-pair, applied only to the `(lv_pin, hv_pin)` named on each slot, and only inside the slot's reclaimed band — not a global relaxation.
