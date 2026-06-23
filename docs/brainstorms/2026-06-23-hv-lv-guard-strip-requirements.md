---
date: 2026-06-23
topic: hv-lv-guard-strip
focus: Pre-placement stage that partitions components by NetClassRules.safety_category and reserves a 6mm guard strip between HV (board edge) and LV (board interior) domains
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (Idea #1)
status: active
actors: deterministic placer, design rules, DRC, pipeline runner
---

# Requirements: HV/LV Pre-Placement Guard Strip

## Problem

The temper PCB autorouter pipeline achieves only 33% routing completion (8/24 nets). The 10 stuck nets are blocked by 6mm HV (high-voltage, IEC 60335-1) creepage clearances around power components Q1, Q2, D1, D2. The current placement pipeline (`zone_geometry` -> `zone_assignment` -> `phased_component_assignment`) is unaware of `NetClassRules.safety_category` when partitioning or placing components, so HV and LV components can be placed within 6mm of each other. No valid routing then exists that respects the IEC 60335-1 creepage between HV pins and any LV trace. The 6mm value is the SSOT in `packages/temper-placer/src/temper_placer/core/design_rules.py` (HighVoltage.creepage_mm, ACMains.creepage_mm) and re-declared in `configs/temper_deterministic_config.yaml` (`net_class_rules.HighVoltage.creepage_mm`).

## Goals

- Lift routing completion on the temper design from 33% (8/24) to >=90% (>=22/24), specifically unblocking the 10 HV creepage-blocked nets.
- Guarantee by construction that no LV component footprint is placed within 6mm of any HV component footprint.
- Derive the guard-strip width from the active `NetClassRules` (SSOT: `creepage_mm` of HV-classified net classes), not from a duplicated constant.
- Compute the guard strip from the board outline so it adapts to the actual board geometry (100mm x 150mm for temper, but supports arbitrary outlines).
- Reuse `NetClassRules.safety_category` (Literal["HV", "LV", "AC", "iso"]) as the single source of truth for the partition.
- Keep the change additive and minimal (~100 lines, per ideation complexity estimate), with no edits to the router, DRC, or `design_rules.py`.

## Non-Goals

- Replacing or restructuring the existing 4-zone layout (HV / Power / Signal / MCU). The guard strip augments it; Power/Signal/MCU zones fall inside the LV bucket.
- Modifying any DRC check, the router, or routing strategies.
- Changing `NetClassRules.safety_category` semantics, values, or population.
- Multi-domain partitions (e.g., separate "AC vs HV" cuts or iso regions). Single HV vs LV cut only.
- Pin-level creepage enforcement. Per-pin 6mm clearances remain a post-placement DRC concern.
- Voltage-aware dynamic guard-strip width. Width derives from `creepage_mm` only, not `voltage_v`.
- Auto-tuning guard-strip width per board region or per component.
- L-shaped, U-shaped, or non-rectangular guard geometries. Single convex offset of the board outline.

## User Stories

- **US1.** As a placement operator, I want the pre-placement stage to read each component's nets' `safety_category` so I do not reclassify manually.
- **US2.** As a placement operator, I want HV components constrained to the board-edge region so they cluster away from LV components.
- **US3.** As a placement operator, I want LV components constrained to the board-interior region so the corridor between HV and LV is guaranteed empty.
- **US4.** As a routing operator, I want the guard strip registered as a known-empty routing corridor so the router can route LV signals through it without re-checking HV proximity.
- **US5.** As a CI maintainer, I want the stage to fail loudly (with bucket name, largest component ref, and region area) if the guard strip leaves no valid area for either bucket.
- **US6.** As a developer, I want the new stage to slot into the existing stage DAG so I do not rewire the pipeline runner.

## Functional Requirements

**FR1. New Stage Module.** A new stage lives at `packages/temper-placer/src/temper_placer/deterministic/stages/hv_lv_partition.py`, implements the `Stage` ABC, and is inserted in the pipeline DAG between `zone_assignment` and `phased_component_assignment`.

**FR2. HV/LV Bucket Partition.** The stage reads each net's `NetClassRules.safety_category` (via `DesignRules.get_rules_for_net()`) and partitions components:
- HV bucket: any component connected to >=1 net whose `safety_category` in {"HV", "AC"}.
- LV bucket: all remaining components (`safety_category` in {"LV", "iso"} or `None`).
- Components with no net connections (mounting holes, fiducials) default to LV.
- Dual-domain components (those connected to nets in both {"HV","AC"} and {"LV","iso"}) are flagged as iso-isolators and excluded from the guard-strip constraint, or assigned to LV bucket with a recorded warning. The exact policy is implementation choice but must be specified before FR2 is testable.

**FR3. Guard Strip Computation.** The stage computes a guard strip as an inward offset of the board outline:
- Width = max(`creepage_mm`) over all HV-classified `NetClassRules` in the active `DesignRules` (default 6.0mm; sourced from `HighVoltage`/`ACMains` in `core/design_rules.py`).
- HV region = board outline minus the guard strip (board-edge domain).
- LV region = interior of the guard strip (board-interior domain).
- Guard strip itself is reserved as a component-free routing corridor (FR5).
- If config `hv_lv_guard_strip.width_mm` is set and > 0, it overrides the derived max(creepage_mm). If set to a value below max(creepage_mm), the stage logs a WARNING and uses max(creepage_mm). If set to 0, the stage is a no-op pass-through (equivalent to enabled=false).

**FR4. Domain Map Output.** The stage emits `component_domain_map: frozenset[(ref, domain)]` on `BoardState`, where `domain in {"HV_edge", "LV_interior"}`. Downstream `phased_component_assignment` consumes this map to filter `zone_slots` so each component is only placed in its domain's region.

**FR5. Routing Corridor Registration.** The guard strip polygon is added to a new `BoardState.routing_corridors` field so the router treats it as a component-free zone but freely available for traces. `BoardState.routing_corridors: tuple[Polygon, ...]` (ordered, immutable). The router contract is: any trace segment within a corridor polygon is permitted; component placement is forbidden inside any corridor (enforced by `phased_component_assignment` via FR4). If the current router does not consume this field, document that corridors are advisory until router-side support lands, and adjust NFR6 (golden fixtures) to compare placement output only.

**FR6. Empty Bucket Handling.** If one bucket is empty, the stage logs INFO and skips the guard strip for the non-empty bucket (no partitioning). If both buckets are empty, the stage is a no-op pass-through.

**FR7. Insufficient Area Handling.** If the HV region area < bounding-box area of the largest unplaced HV component, OR the LV region area < bounding-box area of the largest unplaced LV component, the stage raises `PartitionError(bucket, largest_ref, region_area_mm2, required_area_mm2)` and halts the pipeline.

**FR8. Pipeline Integration.** The new stage appears in the deterministic pipeline DAG after `zone_assignment` and before `phased_component_assignment`. No orchestrator or runner edits; only a stage list entry and the new `BoardState` fields.

**FR9. Config Block.** `configs/temper_deterministic_config.yaml` gains an `hv_lv_guard_strip` block:
- `enabled` (bool, default `true`)
- `width_mm` (float, default derived from `creepage_mm`)
- `fallback_to_unconstrained` (bool, default true): when true, an FR7 insufficient-area condition logs a WARNING with bucket/largest_ref/area context and proceeds without the guard strip (legacy placement); when false, FR7's PartitionError is raised. Does not apply to FR6 empty-bucket case (always a no-op pass-through).

When `enabled: false`, the stage is a no-op pass-through (NFR6 compatibility).

## Non-Functional Requirements

**NFR1. Determinism.** Same inputs (board, netlist, design rules) produce the same partition, guard strip, and domain map.

**NFR2. Performance.** Stage adds <5% to total pipeline wall-clock time. Partition is O(N+M) for N components, M nets. Guard-strip offset is O(1) for a rectangle, O(E) for a polygon of E edges.

**NFR3. Testability.** Stage is unit-testable in isolation with a fabricated `BoardState`, `netlist`, and `DesignRules`. No dependency on the full pipeline.

**NFR4. Logging.** Bucket sizes, guard-strip dimensions, and partition warnings log at INFO. `PartitionError` logs at ERROR with full diagnostic context.

**NFR5. Code Size.** Implementation fits in ~100 lines of Python (per ideation estimate), excluding tests and config.

**NFR6. Backwards Compatibility.** Legacy netlists without `safety_category` default all components to LV. The pipeline runs as today with the guard strip in place but only the LV region active. `enabled: false` produces byte-identical output to the pre-change version (verifiable via existing golden fixtures in `docs/brainstorms/2026-06-22-golden-fixture-ladder-requirements.md`).

## Out of Scope

- Layer-aware partitioning (HV on F.Cu only). Existing `required_layer` constraints handle this elsewhere.
- Non-convex guard geometries (L-shape, U-shape, hole-aware). Single convex offset of the outline only.
- Dynamic guard-strip width derived from `voltage_v` per net. Width is the max `creepage_mm` across HV classes.
- A second guard strip between "AC" and "HV" sub-domains. Both fall in the same HV bucket.
- Re-routing the existing 4-zone layout. The new partition is a strict refinement.
- Migration of `zone_assignments` config in `configs/temper_deterministic_config.yaml`. Existing entries remain valid; new stage layers above them.

## Success Metrics

- **SM1.** Routing completion on the temper design rises from 33% (8/24) to >=90% (>=22/24).
- **SM2.** Placement output has zero DRC creepage violations between HV component footprints and LV component footprints (component-to-component only). HV-pin-to-LV-trace creepage remains a routing/DRC concern tracked separately.
- **SM3.** All 10 currently-stuck HV nets (those blocked by 6mm clearance around Q1, Q2, D1, D2) are routed.
- **SM4.** Pipeline wall-clock time increases by <5% with the new stage enabled.
- **SM5.** Stage has >=95% line and branch coverage in unit tests.
- **SM6.** With `enabled: false`, the pipeline produces byte-identical output to the pre-change version (golden-fixture regression gate).

## Dependencies

- `NetClassRules.safety_category` in `packages/temper-placer/src/temper_placer/core/design_rules.py:133` (SSOT for partition).
- `NetClassRules.creepage_mm` in `packages/temper-placer/src/temper_placer/core/design_rules.py:121` (SSOT for guard width).
- `DesignRules.get_rules_for_net()` in `packages/temper-placer/src/temper_placer/core/design_rules.py:190` (per-net class lookup).
- `BoardState` extended with `component_domain_map` and `routing_corridors` fields.
- `Stage` ABC at `packages/temper-placer/src/temper_placer/deterministic/stages/base.py`.
- `zone_geometry.py` and `zone_assignment.py` run before the new stage; their outputs are unchanged.
- `phased_component_assignment.py` consumes `component_domain_map` to filter slots per FR4.
- `configs/temper_deterministic_config.yaml` gains the `hv_lv_guard_strip` block per FR9.
- Existing DRC creepage checks (unchanged) validate the placement output post-hoc.

## Assumptions

1. The board outline is available on `BoardState` as a closed polygon (currently 100mm x 150mm rectangle for temper).
2. `safety_category` is populated for all relevant net classes in `TEMPER_NET_CLASSES`: `ACMains`->"AC", `HighVoltage`->"HV", `HighCurrent`->"HV", all others->"LV".
3. The 6mm creepage value is correct for the temper design. Both `HighVoltage.creepage_mm` and `ACMains.creepage_mm` are 6.0 in `core/design_rules.py:337-444`.
4. The existing 4-zone layout coexists with the new HV/LV partition: Power/Signal/MCU zones fall inside the LV bucket; the HV zone falls inside the HV bucket. No conflict.
5. The guard strip is a component-free region only; copper clearance remains the router's and DRC's responsibility.
6. The pipeline runner supports inserting new stages without code changes, per the per-stage-DRC-fence pattern (`docs/brainstorms/2026-06-22-per-stage-drc-fence-requirements.md`).
7. `phased_component_assignment` can consume both `component_zone_map` and `component_domain_map` simultaneously; the domain map is a strict refinement of the zone map.
