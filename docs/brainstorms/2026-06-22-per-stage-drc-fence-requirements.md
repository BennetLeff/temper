---
date: 2026-06-22
topic: per-stage-drc-fence
focus: Run DRC checks after every pipeline stage with stage-declared invariants, incremental checking, and violation attribution
origin: docs/ideation/2026-06-22-design-validation-ideation.md
status: active
actors: pipeline stages, temper-drc, CI system
---

# Requirements: Per-Stage DRC Fence

## Problem Frame

The placement-to-routing pipeline (`DeterministicPipeline`, `RouterV6Pipeline`) runs multiple stages sequentially, but DRC checks execute only at the very end (REFINEMENT → OUTPUT). This creates a class of bugs where one stage silently corrupts the output of an earlier stage, and the corruption is only discovered after the entire pipeline completes — or worse, never discovered at all.

Two concrete failures motivate this:

1. **PowerPlaneStage overwrite (temper-116).** `PowerPlaneStage` runs after `LayerAssignmentStage`. For nets not in its hardcoded `TEMPER_PLANE_NETS` set but that `LayerAssignmentStage` assigned to inner layers (e.g., `PowerTrace` class nets at `layer=0, is_plane=False`), `PowerPlaneStage` creates default `LayerAssignment(net_name=..., layer=0, is_plane=False)`. This silently replaced `LayerAssignmentStage`'s net-class-informed assignments. No per-stage check detected the divergence between the two stages' outputs.

2. **Waterfall pipeline unroutable placement.** The closure test pipeline placed components but the placer produced overlapping/unroutable positions. A placement-stage DRC check (component overlap, courtyard clearance) would have caught this before the router consumed the bad input and wasted compute.

The TDD per-concern approach (routing specific nets with targeted invariant checks) achieved 96.7% clearance pass rate, demonstrating that targeted, stage-scoped invariants work. The gap is that these checks are manual and not structurally part of the pipeline.

The performance budget is tight: Router V6 Stage 4 (geometric realization) is the dominant cost (~tens of seconds for full-board routing). Per-stage DRC must not add more than 20% to any stage's wall-clock time.

## Actors

- **A1. Stage developer** — writes a new pipeline stage and declares its output invariants. The stage fails CI/run if its invariants are violated.
- **A2. Pipeline operator** — runs the pipeline end-to-end and expects any violation to report which stage introduced it, what nets/components are affected, and what the specific violation is.
- **A3. CI system** — runs the closure test; expects per-stage DRC fence to catch regressions immediately rather than at the end.

## Key Decisions

- **K1. Fence, not gate.** The per-stage DRC check is a _fence_ — it runs automatically after every stage, reports violations with attribution, and can be configured to halt or warn. It is not a separate pipeline stage that must be manually inserted between others.
- **K2. Stage-declared invariants.** Each `Stage` subclass declares an `invariants` property returning a list of check names and the geometric guarantees the stage promises. The fence runs only the checks that the stage declares as its output contract. If a stage declares it guarantees no component overlap, the fence runs the component-overlap check after that stage.
- **K3. Incremental DRC.** Only re-check board areas modified by the current stage, not the entire board. The fence receives a diff (added/modified/removed geometry) from the stage and scopes checks to affected regions. This is essential for the 20% performance budget.
- **K4. No new checks, only orchestration.** The per-stage DRC fence does not implement new DRC checks. It uses the existing `temper_drc` checks (clearance, annular ring, mask sliver, connectivity, courtyard, component overlap, zone containment) and the KiCad DRC engine. The fence is a runner/attribution layer.
- **K5. Strangler fig dual-run.** When a stage is being refactored (strangler pattern), the fence runs invariants against _both_ the old and new stage outputs in parallel. Divergence in check results—not just the board data—is collected: "Old `PlacementValidationStage` reported 0 overlaps; new `PlacementValidationV2Stage` reported 3 overlaps on U1, U2, U3."

## Requirements

### R1. Stage Invariant Declaration
Status: required

Each `Stage` subclass exposes an `invariants` property that returns a list of invariant specifications. Each specification names:
- `check_name`: a `temper_drc` check name (e.g., `"clearance"`, `"component_overlap"`, `"courtyard"`)
- `guarantees`: human-readable text describing the geometric guarantee (e.g., `"No component footprints overlap after placement"`)
- `affected_regions` (optional): which spatial regions this invariant applies to; if omitted, board-wide

The base `Stage` class adds `invariants` as an optional property defaulting to an empty list. Stages with no output invariants (e.g., net ordering) skip the fence entirely.

### R2. Per-Stage Fence Runner
Status: required

A `DRCFence` class wraps the `CheckRunner` from `temper_drc` and integrates into the pipeline runner (both `DeterministicPipeline.run()` and `RouterV6Pipeline.run()`). Before returning from each stage's `.run()`, the pipeline invokes:

```python
fence.check(stage_name, invariants, board_snapshot, modified_regions)
```

The fence:
- Filters to checks declared in `invariants`
- Passes only the `modified_regions` geometry to checks that support incremental evaluation
- For checks that do not support incremental evaluation, runs board-wide but logs a perf warning
- Returns a `FenceResult` with: passed/passed-oci, violation list, elapsed_ms, stage name
- If `fail_on_violation=True` (configurable), raises `FenceViolationError` halting the pipeline

### R3. Violation Attribution
Status: required

When a DRC violation is found, the fence report attributes it to the stage that introduced it. The report format:

```
STAGE FENCE VIOLATION
  Stage:        placement_validation
  Invariant:    No component overlaps after placement
  Check:        component_overlap
  Introduced:   2 violations (0 in previous stage output)
  Violations:
    - [DRC_OVL_001] U1 overlaps U2 by 1.2mm at (34.5, 22.1)
    - [DRC_OVL_002] U3 overlaps board edge by 0.8mm at (0.4, 15.0)
```

The fence compares violations found after stage N against violations found after stage N-1 (or against the pre-stage snapshot). Only _new_ violations are attributed to stage N. Violations present before stage N and still present after are reported as "pre-existing."

### R4. Dual-Run Mode for Strangler Transitions
Status: required

When a stage has an `alternative` attribute (set during strangler-fig refactors), the fence runs invariants against _both_ the primary stage output and the alternative stage output. The fence reports:

1. Whether each invariant passed on the primary output
2. Whether each invariant passed on the alternative output
3. Whether the pass/fail statuses are identical (consistency check)
4. If they differ: which check failed on which output, with full violation details

The dual-run result is logged at WARNING level during strangler transitions and at ERROR level if the primary and alternative disagree on pass/fail.

### R5. Incremental Check Scoping
Status: required

Stages provide a `modified_regions` set to the fence: a list of axis-aligned bounding boxes describing areas the stage touched. The fence passes these to each DRC check. Checks that support incremental evaluation use the regions to skip geometry outside the modified area.

A check declares incremental support via a `supports_incremental: bool` property (default `False`). The fence logs: `"check X does not support incremental; running board-wide (N regions scoped)"` — this is a perf advisory, not an error.

Incremental scoping is the primary mechanism for meeting the 20% performance budget.

### R6. Performance Budget Enforcement
Status: required

The fence collects per-stage timing:
- `stage_wall_time_ms`: the stage's own `.run()` elapsed time
- `fence_wall_time_ms`: the fence's check execution time
- `overhead_pct`: `fence_wall_time / stage_wall_time * 100`

Pipeline metrics emit these values. If `overhead_pct > 20%` for any stage whose `stage_wall_time_ms >= 50`, the pipeline logs a WARNING with the stage name and actual overhead. CI enforces this budget via an opt-in gate (on by default; a 2-week WARNING-only soft-launch period precedes hard-block). Stages under 50ms wall time skip the percentage check — the absolute cost is negligible regardless of ratio.

### R7. Integration with Existing Checks
Status: required

The fence uses the `CheckRunner` from `temper_drc` as its check execution engine. It does not duplicate check logic. The fence's responsibilities are:
- Filtering checks to those declared in the stage's invariants
- Scoping geometry to modified regions
- Diffing violation lists for attribution
- Timing and reporting

New checks added to `temper_drc` via the `@register_check` decorator (R3 from the source-of-truth-validation initiative) are automatically available to the fence. No separate registration is needed.

### R8. State Snapshot for Diffs
Status: required

The pipeline runner maintains a pre-stage snapshot of the board state (or relevant subset: component positions, track segments, via placements). After the stage runs, the fence compares the post-stage DRC result against the pre-stage DRC result (or computes the diff regionally). The snapshot mechanism must support both `BoardState` (deterministic pipeline) and `ParsedPCB` + stage output dataclasses (Router V6 pipeline).

Snapshot storage is transient (in-memory during pipeline run). Snapshots are not persisted to disk.

## Success Criteria

- **SC1.** Running the closure test pipeline with `DRCFence(fail_on_violation=True)` catches the PowerPlaneStage→LayerAssignmentStage overwrite: violations appear in the `power_plane` stage fence report, attributing the clearance/assignment issues to that stage.
- **SC2.** A placement stage that produces overlapping components triggers a fence violation at the placement stage boundary, before routing begins. The router never receives bad input.
- **SC3.** Per-stage DRC overhead target is ≤ 20% of each stage's wall-clock time for stages with incremental check support. Stages with wall-clock time under 50ms skip the percentage check entirely (fast-enough floor). R6 enforces this via CI opt-in gate (on-by-default) with WARNING logging for stages exceeding the budget. The CI gate starts as WARNING-only for 2 weeks after deployment, then hard-blocks on violation.
- **SC4.** During a strangler-fig transition of a stage, the dual-run fence reports pass/fail for both old and new code paths, with divergence details.
- **SC5.** Violation reports name the offending stage, the specific invariant violated, the check that flagged it, and the affected nets/components — not just a count.
- **SC6.** Adding a stage invariant requires exactly one edit: adding the check name to the stage's `invariants` property. The fence discovers and runs it automatically.

## Acceptance Examples

- **AE1.** Given `LayerAssignmentStage` declares invariant `component_overlap` (checking that its output does not introduce component overlaps), and `PowerPlaneStage` runs after it and changes `layer_assignments` for nets not in its hardcoded set, when the fence runs after `PowerPlaneStage`, the component-overlap check may pass but the _net assignment consistency_ check (if declared as an invariant of LayerAssignmentStage or as a cross-stage check) flags that assignments have changed. The fence attributes the divergence to `PowerPlaneStage`.

- **AE2.** Given a placement stage produces overlapping component positions, and that stage declares `component_overlap` as an invariant, when the fence runs after placement, it reports: `"Stage placement_validation introduced 3 component_overlap violations on U1, U3, U7"`. The pipeline halts if `fail_on_violation=True`.

- **AE3.** Given `RouterV6Pipeline` runs Stage 4 (geometric realization) which modifies tracks on F.Cu within bounding box `(10,20)-(50,60)`, and the `clearance` check supports incremental evaluation, when the fence runs after Stage 4, only clearance checks against geometry in that bounding box are evaluated. Total fence time is < 20% of Stage 4 time.

- **AE4.** Given `PlacementValidationStage` is being refactored with a new implementation, and the stage has `alternative=NewPlacementValidationStage()`, when the pipeline runs, the fence reports:
  ```
  STAGE FENCE DUAL-RUN
    Stage: placement_validation
    Primary:   PASS (0 violations)
    Alternative: FAIL (2 violations)
    Divergence: component_overlap — PRIMARY=PASS, ALTERNATIVE=FAIL
      Alt violation: U1 overlaps U2 by 1.2mm at (34.5, 22.1)
  ```

- **AE5.** Given the fence runs after `NetOrderingStage`, which declares zero invariants, the fence is a no-op. Zero checks are run. Zero overhead is incurred.

## Scope Boundaries

### Deferred for later

- **Implementation of incremental geometry in all checks.** Some `temper_drc` checks may not support incremental scoping initially. They run board-wide with a perf warning. Incremental support is added check-by-check as needed to meet the performance budget.
- **Cross-stage invariant checks.** Invariants that compare the output of stage N against the output of stage N-1 (e.g., "no stage may reduce the routed-net count") are deferred. R3's diff-based attribution handles the detection of regressions; explicit cross-stage contracts are a future enhancement.
- **Automatic invariant inference.** Stage invariants are manually declared. Automatic inference from stage code (e.g., static analysis of what fields a stage modifies) is deferred.

### Outside this product's identity

- **New DRC check implementations.** The fence does not implement any new DRC checks. It consumes existing `temper_drc` checks and KiCad DRC.
- **Changes to the DRC check `run()` signature.** Existing checks continue to receive `Placement` and `ConstraintSet`. The incremental region parameter is an optional addition; checks that don't accept it are not broken.
- **Pipeline runner replacement.** The fence wraps the existing `DeterministicPipeline.run()` and `RouterV6Pipeline.run()` loops; it does not replace them.

## Dependencies

- `packages/temper-drc/src/temper_drc/core/runner.py` — `CheckRunner` with filtering and metrics (already supports category/name filtering, timing)
- `packages/temper-drc/src/temper_drc/core/check.py` — `Check` ABC with `name`, `category`, `run()`, `is_applicable()` (already implemented)
- `packages/temper-drc/src/temper_drc/core/result.py` — `CheckResult`, `RunResult`, `Issue`, `Location`, `Severity` (already implemented)
- `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` — `Stage` ABC with `name` and `run()` (needs `invariants` property added)
- `packages/temper-placer/src/temper_placer/deterministic/pipeline.py` — `DeterministicPipeline` with stage loop (needs fence integration)
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — `RouterV6Pipeline` with stage methods (needs fence integration)
- `packages/temper-drc/src/temper_drc/core/severity.py` — `Severity` enum with weights (used in violation reporting)

## Assumptions

1. **`CheckRunner` can be instantiated with subsets of checks.** The existing `CheckRunner.run()` already supports `categories` and `check_names` filtering. This is sufficient for the fence's per-invariant filtering.
2. **Stages can report modified regions.** The `Stage.run()` method or a post-run hook can emit a list of bounding boxes. For stages that cannot, the fence falls back to board-wide checking.
3. **`CheckResult` and `Issue` types support equality comparison.** The fence diff logic compares violation lists to isolate newly introduced violations. If `Issue` does not have `__eq__`, a comparator function is needed.
4. **The `Issue.location` field is populated by existing checks.** Violation attribution requires spatial coordinates to produce actionable messages (e.g., `"at (34.5, 22.1)"`). Checks that do not set `location` still work; the report omits spatial details.
5. **Strangler transitions are short-lived.** The dual-run mode adds 2× fence overhead during transitions. This is acceptable because strangler transitions are transient (single PR/commit cycle).

## Outstanding Questions

### Resolved (pre-planning complete)

- **[R2][Design][Resolved]** `DRCFence` lives in `packages/temper-drc/src/temper_drc/core/fence.py` as a new module. It depends only on `temper_drc` types (`CheckRunner`, `CheckResult`, `Issue`) and is consumed by pipeline runners via import.
- **[R8][Technical][Resolved]** Snapshot format is two separate paths, not a common protocol: DeterministicPipeline uses `BoardState.copy()` via `dataclasses.replace()` (native frozen-dataclass copy is free); RouterV6Pipeline uses per-stage `StageOutput.to_snapshot_dict()` method that returns a flat dict of the output fields relevant to DRC checking. The fence receives either `BoardState` or `dict` and routes to the appropriate diff logic internally.

### Deferred to Planning

- **[Affects R5][Performance]** Which existing `temper_drc` checks are the most expensive and would benefit most from incremental support? Profile first before adding `supports_incremental` to any check.
- **[Affects R3][UX]** Should the fence report include a suggested fix (similar to the scripted-routing diagnostic output), or is stage attribution sufficient? The seed idea mentions "Stage N introduced 2 clearance violations on nets Q1-GATE, Q2-DRAIN" — this is implemented. Fix hints are a UX enhancement.
