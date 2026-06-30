---
title: "Pattern: Per-Stage DRC Fence Verification"
date: 2026-06-22
category: architecture-patterns
module: temper_drc
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - A multi-stage pipeline has only endpoint-based DRC checks
  - One stage silently corrupts the output of an earlier stage
  - A strangler-fig refactor introduces an alternative code path that must verify parity
  - Performance-critical pipelines need bounded DRC overhead (<20%)
  - An input model evolves incrementally and some stage outputs cannot yet be validated
tags:
  - drc-fence
  - per-stage-verification
  - pipeline-safety
  - strangler-fig
  - incremental-checking
  - performance-budget
  - dual-run
  - soft-launch
  - sprint-N10
---

# Pattern: Per-Stage DRC Fence Verification

## Context

Temper's placement-to-routing pipeline (`DeterministicPipeline` 26-stage,
`RouterV6Pipeline` 5-stage) ran DRC only at the pipeline endpoint. Two concrete
failures proved this insufficient:

1. **PowerPlaneStage overwrite (temper-116).** `PowerPlaneStage` silently
   replaced `LayerAssignmentStage`'s net-class-informed layer assignments with
   defaults for nets outside its hardcoded `TEMPER_PLANE_NETS` set. No per-stage
   check detected the divergence. The corruption propagated silently through the
   rest of the pipeline and was only discovered when the final DRC flagged
   violations with no attribution to their source.

2. **Waterfall pipeline unroutable placement.** The placer produced
   overlapping/unroutable positions. A placement-stage DRC check would have
   caught this before the router consumed the bad input, saving minutes of
   wasted routing compute.

The fix is a _fence_ — not a separate pipeline stage to insert, but an automatic
check that runs after every stage, attributes violations to their source stage,
and can halt or warn the pipeline.

## Guidance

### 1. Fence-Not-Gate Architecture

A _fence_ runs automatically at pipeline stage boundaries without any manual
insertion point. It is not a stage — it has no `run()` method, does not appear
in the stage ordering, and cannot be omitted. The pipeline runner invokes it
internally after each stage's `run()` returns.

```python
# In DeterministicPipeline.run():
for stage in self.stages:
    pre_state = state.copy()
    t0 = time.time()
    state = stage.run(state)
    stage_time = (time.time() - t0) * 1000

    if self.fence and stage.invariants:
        result = self.fence.check(
            stage_name=stage.name,
            invariants=stage.invariants,
            placement=_extract_placement(state),
            constraints=_extract_constraints(state),
            previous_violations=previous_violations,
            stage_wall_time_ms=stage_time,
        )
        previous_violations = frozenset(_fingerprint(v) for v in result.violations)
```

This is structurally different from a gate: gates fail the build (CI-gate
pattern), while a fence halts the _pipeline_ immediately at the offending stage
with attributed diagnostic output. The fence can also emit WARNING without
halting, enabling soft-launch adoption.

### 2. Stage-Declared Invariants

Each `Stage` subclass declares which DRC checks apply to its output by
overriding the `invariants` property. No central registry is needed — the fence
auto-discovers invariants from the stage instance.

```python
# In determinitic/stages/base.py:
from temper_drc.core.fence import InvariantSpec

class Stage(ABC):
    @property
    def invariants(self) -> tuple[InvariantSpec, ...]:
        return ()  # stages with no invariants skip the fence entirely
```

A stage declares invariants by returning a tuple of `InvariantSpec`:

```python
def _stage_0_5_invariants() -> tuple:
    return (
        InvariantSpec(
            check_name="drc_component_overlap",
            guarantees="No component overlaps after legalization",
        ),
    )
```

Adding a check name to the `invariants` tuple is sufficient — the fence
auto-discovers the check via `CheckRunner.run(check_names=[...])`. No other
wiring is required.

### 3. Dual-Run Mode for Strangler Transitions

When a stage has an `alternative` attribute (set during strangler-fig
refactors), the fence runs invariants against _both_ the primary and alternative
outputs and reports pass/fail divergence. This makes strangler replacement
self-certifying: if the alternative stage introduces violations that the primary
does not (or vice versa), the fence flags the discrepancy immediately.

```python
# Dual-run invocation:
alt_stage = getattr(stage, 'alternative', None)
if alt_stage:
    alt_state = alt_stage.run(pre_state.copy())
    alt_result = fence.check(
        stage_name=stage.name,
        invariants=stage.invariants,
        placement=_extract_placement(alt_state),
        constraints=_extract_constraints(alt_state),
        previous_violations=previous_violations,
    )
    result = fence.check(
        stage_name=stage.name,
        invariants=stage.invariants,
        placement=_extract_placement(state),
        constraints=_extract_constraints(state),
        alternative_result=alt_result,
        ...
    )
```

The dual-run report format:

```
STAGE FENCE DUAL-RUN
  Stage: placement_validation
  Primary:     PASS (0 violations)
  Alternative: FAIL (2 violations)
  Divergence: pass/fail disagreement
    Alt violation: [DRC_OVL_001] U1 overlaps U2 by 1.2mm at (34.5, 22.1)
```

Performance budget warnings are suppressed during dual-run since the 2× overhead
is transient (a single PR cycle).

### 4. Incremental Check Scoping

To meet the ≤20% per-stage performance budget, the fence supports
_region-scoped_ checking: only board areas modified by the current stage are
re-checked. The `Check` ABC gains an optional `supports_incremental` property
(default `False`) and `modified_regions` parameter on `run()`.

```python
class Check(ABC):
    @property
    def supports_incremental(self) -> bool:
        return False

    def run(self, placement, constraints, modified_regions=None) -> CheckResult:
        ...
```

The `CheckRunner` passes `modified_regions` through only to checks that declare
`supports_incremental=True`. Checks without incremental support run board-wide
with a perf advisory log message. `ComponentOverlapCheck` was the first check
to gain incremental support (it's O(n²) in component count and directly relevant
to placement-stage fence checks).

### 5. 50ms Absolute-Time Floor

Fast stages with sub-50ms runtimes skip the percentage-based budget check. A
stage taking 30ms with a 3ms DRC fence is 10% overhead — well under 20% — but
even at 33% overhead it's only 10ms of absolute wall time. The floor prevents
spurious budget warnings on trivial stages.

The enforcement logic in `DRCFence.check()`:

```python
if stage_wall_time_ms is not None and stage_wall_time_ms >= self.perf_budget_floor_ms:
    overhead_pct = (elapsed_ms / stage_wall_time_ms) * 100
    if overhead_pct > self.perf_budget_pct:
        logger.warning(...)
        if self.ci_enforce and datetime.now() >= BUDGET_ENFORCEMENT_START:
            raise FenceBudgetError(result)
```

Both `perf_budget_pct` (default 20.0) and `perf_budget_floor_ms` (default 50.0)
are constructor parameters.

### 6. Two Snapshot Paths (No Common Protocol)

Rather than force a single snapshot protocol across pipelines with different
data models, the fence supports two snapshot paths:

- **`BoardState.copy()`** for the `DeterministicPipeline`. `BoardState` is a
  frozen dataclass with all-immutable fields (`frozenset`, `Optional`,
  primitives). `dataclasses.replace(self)` produces a shallow copy that is
  effectively deep — free beyond the dataclass struct itself.

- **`StageOutput.to_snapshot_dict()`** for RouterV6 stages. Each output
  dataclass (`Stage2Output`, `Stage3Output`, `Stage4Output`) returns a flat
  `dict[str, Any]` of the fields relevant to DRC checking (e.g.,
  `via_placement`, `routed_paths`). Timing internals and other DRC-irrelevant
  fields are excluded.

The fence routes internally based on `isinstance(snapshot, BoardState)` vs
`isinstance(snapshot, dict)`. Snapshots are held in-memory during the pipeline
run only — after the fence returns, both pre and post snapshots are eligible for
GC. No disk persistence.

### 7. No-Op Fence When Input Model Can't Represent Output

RouterV6 Stage 1 (escape vias) and Stage 4 (geometric realization) have no fence
checks because the `temper_drc` `Placement` model only carries component-level
data — it cannot represent via positions or trace geometry. The `drc_clearance`
and `drc_component_overlap` checks operate on component pairs only.

```python
# router_v6/pipeline.py:320-324
# NOTE: No Stage 1 fence. The temper_drc Placement model only
# carries component-level data (no via positions or trace geometry).
# The drc_clearance and drc_component_overlap checks operate on
# component pairs only; a fence check at this stage would be a no-op.
# Revisit when the DRC input model supports via/trace primitives.
```

The explicit comments serve as deferred-invariant markers: they document _why_
the fence is missing and what needs to change before it can be added. This
prevents future readers from assuming the stage was simply forgotten.

Stage 0.5 (legalization) is the only RouterV6 stage with active invariants
(`drc_component_overlap`), because legalization produces component-level output
that the `Placement` model can represent.

### 8. 2-Week WARNING-Only Soft-Launch Before CI Hard-Blocks

The performance budget enforcement uses a date-gated soft-launch:

```python
_BUDGET_ENFORCEMENT_START = datetime(2026, 7, 6)  # 2 weeks after plan date
```

Before the enforcement date, `ci_enforce=True` only logs WARNING on budget
violations — never halts CI. After the date, `ci_enforce=True` raises
`FenceBudgetError`, hard-blocking the pipeline. The violation enforcement
(`fail_on_violation=True`) is a separate flag and was active from day one on the
closure test.

## Why This Matters

Without per-stage DRC verification, the pipeline is a black box: failures
discovered at the endpoint require tracing backward through 8+ phases to
identify the source. The PowerPlaneStage overwrite (temper-116) went undetected
because no intermediate stage could signal "the output I received is not what
the previous stage produced."

The fence converts the pipeline from a black box into a sequence of verified
transitions. Each stage boundary declares what invariants hold — and the fence
attests that they hold. When a violation appears, the fence names the offending
stage, the violated invariant, and the affected nets/components. The developer
does not trace backward; they fix the stage that introduced the violation.

The dual-run mode closes the strangler-fig verification gap. Without it, a
strangler transition replaces a stage implementation and hopes the new version
produces equivalent DRC results. With dual-run, the fence runs invariants
against both outputs and reports divergence on the spot — making each
extraction self-certifying.

The incremental scoping and 50ms floor together make the fence practical in
performance-sensitive pipelines. Without them, a 26-stage pipeline with
board-wide DRC at every boundary would be prohibitively expensive. The fence
meets its ≤20% overhead target by checking only what changed and skipping
trivial stages.

## When to Apply

Apply this pattern when:

- A multi-stage pipeline has only endpoint-based validation and bugs are
  discovered after the pipeline completes, requiring backward trace through
  multiple phases.
- Stage outputs have deterministic, checkable invariants (component overlap,
  clearance, connectivity) that can be expressed in terms of existing
  check infrastructure.
- A strangler-fig refactor is underway and replacement stages need
  self-certifying parity verification.
- The pipeline has a bounded number of stages with typical runtimes well above
  the per-check cost (so incremental scoping keeps overhead within budget).
- The check infrastructure already supports named-check filtering — the fence
  wraps it, not replaces it.

Do NOT apply when:

- The pipeline stages have no checkable invariants (purely computational stages
  producing intermediate data structures with no geometric output). These stages
  are explicitly documented as no-op fence sites with comments explaining the
  deferral.
- The check input model cannot represent the stage's output (e.g., routing
  traces when the model only supports components). Deferred with a comment until
  the model evolves.
- The pipeline is a single stage with no intermediate boundaries.
- Every stage runtime is well below the performance floor — the fence overhead
  would dominate and the benefit is minimal (single-stage pipelines don't have
  cross-stage corruption failure modes).

### Decision Flow

```
Multi-stage pipeline with endpoint-only DRC checks
    │
    ├─ Does each stage have checkable geometric invariants? ── No ──→ Document
    │                                                               deferral with
    │                                                               comment explaining
    │                                                               what input model
    │                                                               change is needed
    │
    ├─ Is the check infrastructure reusable (named-check filtering)? ── No ──→ Not
    │                                                                       yet ready
    │
    ├─ Is there a strangler transition in progress? ── Yes ──→ Enable dual-run mode
    │
    ├─ Will board-wide checks exceed the ≤20% perf budget? ── Yes ──→ Implement
    │                                                  incremental scoping first
    │
    └─ Deploy with WARNING-only soft-launch → hard-block after 2-week bake-in
```

## Examples

### Invariant Declaration (Stage ABC)

```python
# determinitic/stages/base.py
from abc import ABC, abstractmethod
from temper_drc.core.fence import InvariantSpec

class Stage(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    def invariants(self) -> tuple[InvariantSpec, ...]:
        """Override to declare which DRC checks apply to this stage's output."""
        return ()

    @property
    def last_modified_regions(self) -> list[tuple[float, float, float, float]] | None:
        """Override to provide bounding boxes of modified board areas."""
        return None

    @abstractmethod
    def run(self, state: BoardState) -> BoardState:
        pass
```

### Fence Check Invocation (DeterministicPipeline)

```python
# determinitic/pipeline.py
for stage in self.stages:
    pre_state = state.copy()
    t0 = time.time()
    state = stage.run(state)
    stage_time = (time.time() - t0) * 1000

    if self.fence and stage.invariants:
        result = self.fence.check(
            stage_name=stage.name,
            invariants=stage.invariants,
            placement=_board_state_to_drc_input(state).placement,
            constraints=_board_state_to_drc_input(state).constraints,
            modified_regions=getattr(stage, 'last_modified_regions', None),
            previous_violations=previous_violations,
            stage_wall_time_ms=stage_time,
        )
        previous_violations = frozenset(
            _issue_fingerprint(v.issue) for v in result.violations
        )
```

### Fence Violation Output

```
STAGE FENCE VIOLATION
  Stage:        placement_validation
  Invariant:    No component overlaps after placement
  Check:        drc_component_overlap
  Introduced:   2 violations
  Violations:
    - [DRC_OVL_001] U1 overlaps U2 by 1.2mm at (34.5, 22.1)
    - [DRC_OVL_002] U3 overlaps board edge by 0.8mm at (0.4, 15.0)
```

### Deferred Fence Site (RouterV6 Stages 1 and 4)

```python
# router_v6/pipeline.py:320-324
# NOTE: No Stage 1 fence. The temper_drc Placement model only
# carries component-level data (no via positions or trace geometry).
# The drc_clearance and drc_component_overlap checks operate on
# component pairs only; a fence check at this stage would be a no-op.
# Revisit when the DRC input model supports via/trace primitives.
```

## Related

- `packages/temper-drc/src/temper_drc/core/fence.py` — `DRCFence`, `InvariantSpec`, `FenceResult`, `FenceViolation`, `FenceViolationError`, `FenceBudgetError`
- `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` — `Stage` ABC with `invariants` and `last_modified_regions` properties
- `packages/temper-placer/src/temper_placer/deterministic/pipeline.py` — `DeterministicPipeline` fence integration
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — `RouterV6Pipeline` fence integration, Stage 1/4 deferral comments (lines 320-324, 341-344)
- `packages/temper-drc/src/temper_drc/core/check.py` — `Check` ABC with `supports_incremental` property and `modified_regions` parameter
- `packages/temper-drc/src/temper_drc/core/runner.py` — `CheckRunner.run()` with `check_names` filtering and incremental check routing
- `packages/temper-drc/tests/test_fence.py` — unit tests for violation attribution, fingerprint diff, soft-launch behavior
- `packages/temper-drc/tests/test_fence_perf_budget.py` — performance budget enforcement tests
- `docs/solutions/architecture-patterns/4layer-invariant-chain-boundary-enforcement-2026-06-30.md` — concrete instantiation of the fence pattern for layer-count invariants with preflight checks and output validation across 12 write call sites
- `packages/temper-placer/tests/test_stage_invariants.py` — stage invariant declaration tests
- `docs/plans/2026-06-22-013-feat-per-stage-drc-fence-plan.md` — full implementation plan (U1–U8)
- `docs/ideation/2026-06-22-pipeline-strangler-decomposition-ideation.md` — strangler-fig context (#6: per-stage DRC fence)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — sibling pattern (baseline + monotonic shrink for CI gates)
