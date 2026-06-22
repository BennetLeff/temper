---
date: 2026-06-22
type: feat
origin: docs/brainstorms/2026-06-22-per-stage-drc-fence-requirements.md
status: active
---

# Plan: Per-Stage DRC Fence

## Problem Frame

The placement-to-routing pipeline (`DeterministicPipeline`, `RouterV6Pipeline`) runs multiple stages sequentially, but DRC checks execute only at the very end. This creates a class of bugs where one stage silently corrupts the output of an earlier stage, and the corruption is only discovered after the entire pipeline completes — or never.

Two concrete failures:
1. **PowerPlaneStage overwrite (temper-116).** `PowerPlaneStage` silently replaced `LayerAssignmentStage`'s net-class-informed assignments with defaults for nets outside its hardcoded `TEMPER_PLANE_NETS` set. No per-stage check detected the divergence.
2. **Waterfall pipeline unroutable placement.** The placer produced overlapping/unroutable positions. A placement-stage DRC check would have caught this before the router consumed the bad input.

The fix is a _fence_ — not a separate pipeline stage but an automatic check that runs after every stage, reports violations with stage attribution, and can be configured to halt or warn.

## Requirements Trace

| Requirement | Source | Description |
|-------------|--------|-------------|
| R1 — Stage Invariant Declaration | Req doc | `Stage` ABC gains `invariants` property; each entry names a check + guarantee text |
| R2 — Per-Stage Fence Runner | Req doc | `DRCFence` class wraps `CheckRunner`, invoked after each stage's `.run()` |
| R3 — Violation Attribution | Req doc | Fence diffs post-vs-pre violations; only _new_ violations attributed to current stage |
| R4 — Dual-Run Mode | Req doc | When stage has `alternative` attribute, fence runs invariants against both outputs, reports divergence |
| R5 — Incremental Check Scoping | Req doc | `modified_regions` from stage bounds check execution; `supports_incremental` on `Check` ABC |
| R6 — Performance Budget | Req doc | ≤20% overhead per stage (skip for stages <50ms); CI gate on-by-default with 2-week soft-launch |
| R7 — Integration with Existing Checks | Req doc | Fence uses `CheckRunner` via existing `check_names` filtering; no new checks implemented |
| R8 — State Snapshot for Diffs | Req doc | Two paths: `BoardState.copy()` for deterministic, `StageOutput.to_snapshot_dict()` for RouterV6 |
| SC1 — PowerPlaneStage catch | Req doc | Closure test with `fail_on_violation=True` catches the temper-116 overwrite |
| SC2 — Placement-stage halt | Req doc | Overlapping components trigger fence violation at placement boundary, before routing |
| SC3 — ≤20% overhead target | Req doc | Per-stage DRC overhead ≤20% for stages ≥50ms; CI gate enforces |
| SC4 — Strangler divergence | Req doc | Dual-run reports pass/fail for both old and new code paths |
| SC5 — Attributed violation reports | Req doc | Reports name offending stage, invariant, check, and affected nets/components |
| SC6 — One-edit invariant addition | Req doc | Adding a check name to `invariants` property is sufficient; fence auto-discovers |

## Implementation Units

### U1. Stage Invariant Declaration

**Goal:** Add `invariants` property to `Stage` ABC and define the `InvariantSpec` type.

**Requirements:** R1, SC6

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/base.py`
- Create: `packages/temper-drc/src/temper_drc/core/fence.py` (InvariantSpec dataclass — co-located with DRCFence since invariants are the fence's input contract)

**Approach:**
- Define `InvariantSpec` dataclass in `fence.py`:
  ```python
  @dataclass(frozen=True)
  class InvariantSpec:
      check_name: str          # e.g. "drc_component_overlap"
      guarantees: str          # human-readable guarantee text
      affected_regions: tuple[tuple[float, float, float, float], ...] | None = None  # (xmin, ymin, xmax, ymax); None = board-wide
  ```
- Add `invariants` property to the `Stage` ABC at `base.py:4`:
  ```python
  @property
  def invariants(self) -> tuple[InvariantSpec, ...]:
      return ()
  ```
- Default returns empty tuple — stages with no invariants (e.g., net ordering) skip the fence entirely (AE5).
- Add `modified_regions` as an optional return from `Stage.run()` or a post-run property. The `Stage.run()` signature remains `BoardState → BoardState`; regions are exposed via a separate `last_modified_regions` property added to the ABC, returning `None` by default (falls back to board-wide checking).

**Patterns to follow:** `Stage` ABC at `base.py:4-15`. Match the existing `@property` + `@abstractmethod` pattern for `name`.

**Test scenarios:**
- Stage with no `invariants` override returns empty tuple (fence no-ops)
- Stage with `invariants` returning `(InvariantSpec(check_name="drc_component_overlap", ...),)` — fence discovers the check name automatically
- Type checker passes: `tuple[InvariantSpec, ...]` is the return annotation

**Verification:** All existing `Stage` subclasses continue to work without changes. Adding a single check name to a stage's `invariants` tuple is sufficient for the fence to run that check (SC6).

---

### U2. DRCFence Core

**Goal:** Implement `DRCFence` class with `FenceResult`, `FenceViolationError`, check filtering, CheckRunner integration, violation attribution, timing, and reporting.

**Requirements:** R2, R3, R5, R6, R7, SC1, SC2, SC3, SC5

**Dependencies:** U1 (InvariantSpec type), existing `CheckRunner`, `Check`, `CheckResult`, `RunResult`, `Issue`, `Location` (`temper_drc.core`)

**Files:**
- Create: `packages/temper-drc/src/temper_drc/core/fence.py`
- Modify: `packages/temper-drc/src/temper_drc/core/__init__.py` (export new types)
- Modify: `packages/temper-drc/src/temper_drc/__init__.py` (re-export for package-level import)

**Approach:**

`fence.py` contains:

1. **`FenceResult` dataclass** — the primary output of a fence check run:
   - `stage_name: str`
   - `passed: bool` — all invariants passed
   - `violations: tuple[FenceViolation, ...]` — attributed violations (see below)
   - `elapsed_ms: float` — total fence wall-clock time
   - `check_results: tuple[CheckResult, ...]` — raw results passed through from CheckRunner
   - `overhead_pct: float | None` — overhead vs stage time (None if stage time unavailable)
   - `mode: str` — `"single"` or `"dual"` (U7)

2. **`FenceViolation` dataclass** — a single attributed violation:
   - `stage_name: str`
   - `invariant_description: str` — from the InvariantSpec
   - `check_name: str`
   - `issue: Issue` — the underlying Issue from CheckResult
   - `is_new: bool` — True if violation was not present before this stage
   - `introduced_count: int` — count of new violations introduced by this stage

3. **`FenceViolationError` exception** — raised when `fail_on_violation=True` and a stage introduces violations. Includes the full FenceResult.

4. **`DRCFence` class:**
   - **`__init__(self, check_runner: CheckRunner, fail_on_violation: bool = False, perf_budget_pct: float = 20.0, perf_budget_floor_ms: float = 50.0, ci_enforce: bool = False)`**
   - **`check(self, stage_name: str, invariants: tuple[InvariantSpec, ...], placement: Placement, constraints: ConstraintSet, modified_regions: list[tuple[float, float, float, float]] | None = None, previous_violations: frozenset[Issue] | None = None, stage_wall_time_ms: float | None = None, alternative_result: FenceResult | None = None) -> FenceResult`**

   The `check` method:
   - Collects check names from `invariants`; if empty, returns early with `FenceResult(passed=True, elapsed_ms=0, ...)`
   - Calls `check_runner.run(placement, constraints, check_names=check_names)` — uses existing filtering (line 89-100 of `runner.py`)
   - For each check, if `supports_incremental` (see U4) and `modified_regions` provided, passes regions; otherwise runs board-wide and logs perf advisory
   - Computes violation attribution: compares `previous_violations` (frozenset of Issue from pre-stage) against current issues. Only _new_ issues are attributed to this stage.
   - Constructs `FenceViolation` list for new issues, with `introduced_count = len(new_issues)`
   - Computes timing: `elapsed_ms` is wall-clock time of the entire check call
   - Computes overhead: if `stage_wall_time_ms` is provided and `>= 50`, `overhead_pct = (elapsed_ms / stage_wall_time_ms) * 100`
   - Perf budget check: if `overhead_pct > 20` and `stage_wall_time_ms >= 50`, logs WARNING; if `ci_enforce=True` and outside soft-launch window, raises `FenceViolationError` for budget violation
   - If `fail_on_violation=True` and any new violations exist, raises `FenceViolationError`

5. **Issue equality for diffing:** Since `Issue` is a dataclass with fields containing lists/dicts, and there's no registry of issue codes guaranteeing uniqueness, the fence uses a **canonical fingerprint**: `_issue_fingerprint(issue: Issue) -> str` returning `f"{issue.code}:{issue.message}:{','.join(sorted(issue.affected_items))}"`. The `previous_violations` is stored as `frozenset[str]` of fingerprints, and the diff operates on these fingerprints. This avoids depending on `Issue.__eq__`, per assumption 3 in the requirements doc.

6. **Reporting format** — `FenceResult.format()` produces the output shown in AE2/AE4:
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

**Patterns to follow:** `CheckRunner.run()` at `runner.py:84-144` for filtering and timing patterns. `RunResult` at `result.py:171-268` for aggregated result patterns.

**Test scenarios:**
- Fence with empty invariants returns instantly (elapsed ≈ 0, passed=True)
- Fence runs only checks named in invariants (verify via mock CheckRunner)
- Violation attribution correctly identifies new violations vs pre-existing via fingerprint diff
- `fail_on_violation=True` raises `FenceViolationError` with complete violation details
- Report format matches AE2/AE4 output
- Perf warning fires when overhead > 20% and stage_time ≥ 50ms
- Perf budget: no warning when stage_time < 50ms even if overhead > 20%

**Verification:** SC1 (PowerPlaneStage catch), SC2 (placement halt), SC5 (attributed reports). All acceptance examples (AE1-AE5) pass.

---

### U3. Incremental Check Scoping Protocol

**Goal:** Add `supports_incremental` property to `Check` ABC and optional `modified_regions` parameter to `Check.run()`. Enable region-scoped checking for meeting the 20% performance budget.

**Requirements:** R5, SC3

**Dependencies:** None (independent protocol addition to `Check` ABC)

**Files:**
- Modify: `packages/temper-drc/src/temper_drc/core/check.py` (add `supports_incremental` property, optional `modified_regions` to `run()`)
- Modify: `packages/temper-drc/src/temper_drc/core/runner.py` (pass `modified_regions` through to checks that support it)
- Modify: `packages/temper-drc/src/temper_drc/checks/drc/component_overlap.py` (first check to support incremental — computes overlap only within regions)

**Approach:**

1. **`Check` ABC additions** at `check.py:15`:
   - Add `supports_incremental: bool` property (not abstract — defaults to `False` at base class):
     ```python
     @property
     def supports_incremental(self) -> bool:
         return False
     ```
   - Modify `run()` signature to accept optional `modified_regions`:
     ```python
     @abstractmethod
     def run(
         self,
         placement: Placement,
         constraints: ConstraintSet,
         modified_regions: list[tuple[float, float, float, float]] | None = None,
     ) -> CheckResult:
     ```
     This is a backward-compatible signature change: all existing `run()` implementations accept `**kwargs` implicitly through Python's parameter passing, and explicit implementations that don't declare the parameter get `None`.

2. **`CheckRunner.run()` modification** at `runner.py:84`: Add `modified_regions` parameter and pass through when the check supports it:
   ```python
   def run(self, ..., modified_regions=None, ...):
       ...
       if modified_regions and check.supports_incremental:
           result = check.run(placement, constraints, modified_regions=modified_regions)
       else:
           result = check.run(placement, constraints)
   ```

3. **`ComponentOverlapCheck` incremental support** at `component_overlap.py:6`: Override `supports_incremental = True`. When `modified_regions` is provided, filter `placement.all_pairs()` to only components whose bounding boxes intersect any modified region. This is the simplest and highest-impact incremental check because component overlap is O(n²) in component count.

4. **`DRCFence` perf advisory** (part of U2): When a check name in invariants does not support incremental but `modified_regions` is provided, log: `"check X does not support incremental; running board-wide (N regions scoped)"`.

**Patterns to follow:** `Check.run()` abstract method at `check.py:84-99`. The `CompositeCheck.run()` at `check.py:179-200` must also forward `modified_regions`.

**Test scenarios:**
- Existing checks that don't override `supports_incremental` get `False` by default (no behavior change)
- `CheckRunner` passes `modified_regions` only to checks with `supports_incremental=True`
- `ComponentOverlapCheck` with regions scopes to components intersecting bounding boxes
- `ComponentOverlapCheck` without regions behaves identically to current board-wide check
- `CompositeCheck` forwards `modified_regions` to child checks

**Verification:** Incremental `component_overlap` produces identical results to board-wide for components within regions. Subset execution time is lower than full-board.

**Deferred:** Which existing checks benefit most from incremental support? Profile first (per outstanding question in requirements doc). `component_overlap` is the first target because it's O(n²), simple to bound, and directly relevant to the waterfall pipeline failure (SC2).

---

### U4. State Snapshot Mechanism

**Goal:** Implement pre/post-stage state snapshots for violation diffing, using two separate paths: `dataclasses.replace()` for `BoardState` (deterministic pipeline) and `to_snapshot_dict()` for RouterV6 stage outputs.

**Requirements:** R8

**Dependencies:** U2 (DRCFence needs snapshot to compute previous_violations), U1 (invariants tell us _what_ to snapshot)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/deterministic/state.py` (add `copy()` method to `BoardState`)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (add `to_snapshot_dict()` to `Stage2Output`, `Stage3Output`, `Stage4Output` dataclasses)
- Modify: `packages/temper-drc/src/temper_drc/core/fence.py` (U2 — fence routes to appropriate diff logic internally based on snapshot type)

**Approach:**

1. **`BoardState.copy()`** at `state.py:15`: Since `BoardState` is a frozen dataclass with all-Optional/frozenset fields, `dataclasses.replace(self)` produces a shallow copy that is effectively deep (all fields immutable). Add:
   ```python
   def copy(self) -> "BoardState":
       """Return a shallow copy (safe because BoardState is fully immutable)."""
       from dataclasses import replace
       return replace(self)
   ```
   This is free — no memory allocation beyond the dataclass struct itself.

2. **`StageOutput.to_snapshot_dict()`** for RouterV6: Each output dataclass (`Stage2Output`, `Stage3Output`, `Stage4Output`) gets a `to_snapshot_dict()` method that returns a flat `dict[str, Any]` of the fields relevant to DRC checking. For example, `Stage4Output.to_snapshot_dict()` extracts:
   ```python
   def to_snapshot_dict(self) -> dict[str, Any]:
       return {
           "via_placement": self.via_placement,
           "width_assignment": self.width_assignment,
           "routed_paths": self.pathfinding_result.routed_paths,
       }
   ```
   Fields irrelevant to DRC (e.g., timing internals) are excluded.
   The fence stores these dicts and passes them to checks that know how to interpret them (the DRC checks already operate on their own data structures extracted from these outputs).

3. **Fence snapshot routing** (in `fence.py`): The fence's `check()` method accepts `previous_snapshot: BoardState | dict | None` and `current_snapshot: BoardState | dict | None`. Internally, it checks `isinstance(snapshot, BoardState)` vs `isinstance(snapshot, dict)` and extracts the `Placement` and `ConstraintSet` for the CheckRunner. The snapshot difference is used _only_ for computing `modified_regions` when the stage doesn't provide them explicitly.

4. **Transient storage:** Snapshots are held in-memory during the pipeline run. The pipeline runner creates a pre-stage snapshot, runs the stage, then passes both pre and post snapshots to the fence. After the fence returns, both snapshots are eligible for GC. Nothing is persisted to disk.

**Patterns to follow:** `BoardState` frozen dataclass pattern at `state.py:15-81`. RouterV6 output dataclasses at `pipeline.py:47-79`.

**Test scenarios:**
- `BoardState.copy()` produces an equal but distinct object (id differs, fields equal)
- `Stage4Output.to_snapshot_dict()` includes `via_placement`, `width_assignment`, `routed_paths`
- Fence correctly identifies snapshot type and routes to appropriate diff path
- Pre/post snapshots produce correct `modified_regions` from field differences

**Verification:** Pipeline runs with fence produce correct pre-stage snapshots. Memory overhead of snapshot storage is negligible (<1MB for any Temper board).

---

### U5. Dual-Run Mode for Strangler Transitions

**Goal:** When a stage has an `alternative` attribute (set during strangler-fig refactors), the fence runs invariants against both outputs and reports divergence.

**Requirements:** R4, SC4

**Dependencies:** U2 (DRCFence core)

**Files:**
- Modify: `packages/temper-drc/src/temper_drc/core/fence.py` (add `DualRunResult`, dual-run logic to `DRCFence.check()`)
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` (add optional `alternative` attribute)

**Approach:**

1. **`Stage.alternative` attribute** at `base.py:4`: Add to the `Stage` ABC:
   ```python
   alternative: "Stage | None" = None
   ```
   Set during strangler transitions: `PlacementValidationStage.alternative = NewPlacementValidationStage()`.

2. **Dual-run logic in `DRCFence.check()`**: When the stage has an `alternative`:
   - Run invariants against primary stage output → `primary_result: FenceResult`
   - Run invariants against alternative stage output → `alt_result: FenceResult`
   - Compute `consistency: bool = (primary_result.passed == alt_result.passed)`
   - If inconsistent: log at WARNING level during strangler transitions, ERROR level on pass/fail disagreement
   - Return `FenceResult` with `mode="dual"` and `alternative_result=alt_result`
   - Report format (AE4):
     ```
     STAGE FENCE DUAL-RUN
       Stage: placement_validation
       Primary:     PASS (0 violations)
       Alternative: FAIL (2 violations)
       Divergence: drc_component_overlap — PRIMARY=PASS, ALTERNATIVE=FAIL
         Alt violation: U1 overlaps U2 by 1.2mm at (34.5, 22.1)
     ```

3. **Overhead consideration:** Dual-run doubles fence overhead for the strangler stage. Per assumption 5 in requirements doc, strangler transitions are transient (single PR/commit cycle), so 2× overhead is acceptable. The performance budget warning is suppressed for dual-run stages.

**Patterns to follow:** FenceResult and FenceViolation structs in U2.

**Test scenarios:**
- Stage without `alternative`: single-run mode, no dual-run overhead
- Stage with `alternative`: both outputs checked, divergence reported
- Primary passes, alternative fails: consistency=False, ERROR log
- Both pass: consistency=True, no log
- Performance budget warning suppressed during dual-run

**Verification:** SC4 (strangler divergence reported). AE4 output matches spec.

---

### U6. Performance Budget Monitoring & CI Enforcement

**Goal:** Collect per-stage timing, enforce ≤20% overhead budget with 50ms floor, and integrate CI gate with 2-week soft-launch period.

**Requirements:** R6, SC3

**Dependencies:** U2 (DRCFence with timing collection)

**Files:**
- Modify: `packages/temper-drc/src/temper_drc/core/fence.py` (budget check in `DRCFence.check()`)
- Create: `packages/temper-drc/tests/test_fence_perf_budget.py` (budget enforcement tests)
- Modify: CI configuration (`.github/workflows/` or project CI config — add budget gate)

**Approach:**

1. **Budget check in `DRCFence.check()`**: Already designed in U2:
   - `stage_wall_time_ms` passed by pipeline caller
   - If `stage_wall_time_ms >= perf_budget_floor_ms` (default 50ms): compute `overhead_pct = (fence_elapsed_ms / stage_wall_time_ms) * 100`
   - If `overhead_pct > perf_budget_pct` (default 20%): log `WARNING` with stage name and actual overhead
   - If `ci_enforce=True` and outside soft-launch window: raise `FenceBudgetError(FenceResult)` halting the pipeline

2. **Soft-launch state machine:**
   - Implement a `_budget_enforcement_start` module-level timestamp: `datetime(2026, 7, 6)` (2 weeks after plan date of 2026-06-22)
   - Before the date: WARNING-only mode regardless of `ci_enforce` flag
   - After the date: `ci_enforce=True` → hard block on budget violation
   - The CI config sets `ci_enforce=True` in the closure test configuration

3. **Metrics emission:** `FenceResult` includes `overhead_pct` and `stage_wall_time_ms` as public fields. Pipeline metrics (existing logging/metrics infra) emit these per-stage. This enables dashboards and trend tracking.

4. **CI gate configuration:**
   - Add `DRCFence(ci_enforce=True)` to the closure test pipeline
   - The closure test is the integration gate — runs both pipelines on `pcb/temper_placed.kicad_pcb`
   - On CIfailure, report: which stage exceeded budget, by how much, and which checks contributed

**Patterns to follow:** Existing CI workflow patterns. `MetricsSummary` at `metrics.py:61` for timing aggregation patterns.

**Test scenarios:**
- Stage < 50ms with 100% overhead → no warning (floor)
- Stage ≥ 50ms with 15% overhead → no warning (within budget)
- Stage ≥ 50ms with 25% overhead → WARNING log
- `ci_enforce=True` before cutoff date → WARNING only (soft-launch)
- `ci_enforce=True` after cutoff date → `FenceBudgetError` raised
- Budget violation message names stage and actual overhead percentage

**Verification:** SC3 (CI gate enforces budget). Closure test CI pass/fail based on budget compliance.

---

### U7. DeterministicPipeline Integration

**Goal:** Integrate DRCFence into `DeterministicPipeline.run()` — pre-stage snapshot, fence invocation after each stage, violation handling.

**Requirements:** R2, R8, SC1, SC2

**Dependencies:** U1, U2, U4, U6

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/deterministic/pipeline.py`

**Approach:**

1. **Add `DRCFence` to `DeterministicPipeline.__init__`:**
   ```python
   def __init__(self, stages: List[Stage] = None, fence: DRCFence | None = None):
       self.stages = stages or []
       self.fence = fence
   ```
   When `fence=None`, per-stage checking is disabled (backward-compatible).

2. **Modify `run()` loop** at `pipeline.py:14-18`:
   ```python
   def run(self, initial_state: BoardState = None) -> BoardState:
       state = initial_state or BoardState()
       previous_violations: frozenset[str] | None = None  # fingerprints
       for stage in self.stages:
           t0 = time.time()
           pre_state = state.copy()
           state = stage.run(state)
           stage_time = (time.time() - t0) * 1000

           if self.fence and stage.invariants:
               invariants = stage.invariants
               modified_regions = getattr(stage, 'last_modified_regions', None)
               previous_snapshot = pre_state
               current_snapshot = state

               # Build Placement + Constraints from BoardState
               placement, constraints = _board_state_to_drc_input(state)

               # For strangler dual-run
               alt_stage = getattr(stage, 'alternative', None)
               if alt_stage:
                   alt_state = alt_stage.run(pre_state.copy())
                   # ... run fence in dual mode ...

               result = self.fence.check(
                   stage_name=stage.name,
                   invariants=invariants,
                   placement=placement,
                   constraints=constraints,
                   modified_regions=modified_regions,
                   previous_violations=previous_violations,
                   stage_wall_time_ms=stage_time,
               )
               previous_violations = frozenset(
                   _issue_fingerprint(v.issue) for v in result.violations
               )
       return state
   ```

3. **`_board_state_to_drc_input()` helper**: Converts `BoardState` to the `Placement` and `ConstraintSet` types that `temper_drc` checks consume. This bridges the deterministic pipeline's `BoardState` representation to the DRC check input format. Initial implementation handles the fields relevant to existing checks (component positions, net assignments); expanded as checks require more data.

4. **Backward compatibility:** When `fence=None`, the pipeline behaves identically to current code. All existing call sites (`DeterministicPipeline(stages=[...]).run(state)`) continue to work.

**Patterns to follow:** Existing `run()` loop at `pipeline.py:14-18`. The `BoardState` frozen dataclass at `state.py:15`.

**Test scenarios:**
- Pipeline with `fence=None`: no fence runs, identical behavior to current
- Pipeline with fence and stage with invariants: fence runs after stage, violations collected
- Stage introduces overlaps: fence reports violation, pipeline halts if `fail_on_violation=True`
- PowerPlaneStage overwrite (temper-116): fence catches divergence between LayerAssignmentStage output and PowerPlaneStage output

**Verification:** SC1 (PowerPlaneStage catch via closure test), SC2 (placement halt).

---

### U8. RouterV6Pipeline Integration

**Goal:** Integrate DRCFence into `RouterV6Pipeline.run()` — snapshot capture per-stage, fence invocation after each stage method, violation handling.

**Requirements:** R2, R8, SC3

**Dependencies:** U1, U2, U4, U6, U7 (shares `_board_state_to_drc_input` or equivalent logic)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`

**Approach:**

1. **Add `DRCFence` to `RouterV6Pipeline.__init__`:**
   ```python
   def __init__(self, ..., fence: DRCFence | None = None):
       ...
       self.fence = fence
   ```

2. **Modify `run()`** at `pipeline.py:143-239`: Wrap each stage call with fence invocation:
   - **Stage 0** (load PCB): No invariants, no fence. PCB parsing is a data-load step.
   - **Stage 0.5** (legalization): Guards: `component_overlap` invariant. `modified_regions` = bounding boxes of legalized components.
   - **Stage 1** (escape vias): Guards: `clearance` invariant (via-to-pad clearance). `modified_regions` = escape via positions.
   - **Stage 2** (channel analysis): No invariants initially — this is a computational stage producing data structures, not geometric output. Fence no-ops.
   - **Stage 3** (topological routing): No invariants initially — SAT output is logical, not geometric.
   - **Stage 4** (geometric realization): Guards: `clearance`, `component_overlap` (tracks must not overlap pads). `modified_regions` = bounding box of routed tracks.

3. **Snapshot extraction:** For each stage, capture pre-stage state via `StageOutput.to_snapshot_dict()`. Pass to fence along with post-stage snapshot.

4. **`_parsed_pcb_to_drc_input()` helper:** Converts `ParsedPCB` to `Placement` + `ConstraintSet` for DRC checks. Similar to U7's `_board_state_to_drc_input()` but operating on the RouterV6 data model. Unlike `BoardState`, `ParsedPCB` is mutable — the helper extracts component positions and design rules at the time of fence invocation.

5. **Performance-critical path:** Stage 4 (geometric realization) is the dominant cost (~tens of seconds). The fence's `modified_regions` bounding box from routed tracks is essential for keeping overhead ≤20% here. This is AE3.

**Patterns to follow:** RouterV6 stage methods at `pipeline.py:241-625`. Stage output dataclasses at `pipeline.py:47-79`.

**Test scenarios:**
- RouterV6Pipeline with `fence=None`: backward compatible
- Stage 0.5 legalization fence: detects component overlap before routing (SC2 analog for RouterV6)
- Stage 4 fence with `modified_regions`: incremental clearance check respects bounding box
- Stage 4 fence overhead < 20% of stage runtime (SC3)
- Closure test: `RouterV6Pipeline(fence=DRCFence(fail_on_violation=True)).run(pcb_path)`

**Verification:** SC3 (≤20% overhead on Stage 4 with incremental scoping). Closure test integration passes.

---

## Scope Boundaries

### Deferred to Follow-Up Work

- **Incremental support for all checks.** `component_overlap` is implemented in U3. Other checks (`clearance`, `courtyard`, `annular_ring`, `zone_containment`) get incremental support check-by-check as profiling reveals need. Checks without incremental support run board-wide with a perf warning.
- **Cross-stage invariant checks.** Invariants comparing stage N output against stage N-1 output (e.g., "no stage may reduce the routed-net count") are deferred. R3's diff-based attribution handles regression detection; explicit cross-stage contracts are future.
- **Automatic invariant inference.** Stage invariants remain manually declared. Static analysis of what fields a stage modifies is deferred.
- **New DRC check implementations.** The fence consumes existing `temper_drc` checks only.
- **Persistent snapshot storage.** Snapshots are in-memory only. Disk persistence for post-mortem analysis is deferred.
- **`@register_check` decorator.** Referenced in requirements doc (R7 mentions it from source-of-truth-validation initiative). Not a dependency for this plan — `CheckRunner` already supports `check_names` filtering. The decorator is a separate initiative.

### Outside This Product's Identity

- **Pipeline runner replacement.** The fence wraps existing pipelines; it does not replace them.
- **Changes to `Check.run()` signature.** The `modified_regions` parameter is optional and backward-compatible.
- **KiCad DRC engine changes.** The fence uses `temper_drc` checks, not direct KiCad DRC integration.

## Test Strategy

### Unit Tests

| Test File | Covers | Key Assertions |
|-----------|--------|----------------|
| `packages/temper-drc/tests/test_fence.py` | U2, U3, U4 | Fence with empty invariants no-ops; check filtering by name; violation attribution (new vs pre-existing); fingerprint diff; report format matches AE2/AE4; incremental scoping filter; snapshot routing |
| `packages/temper-drc/tests/test_fence_perf_budget.py` | U6 | Budget warning at >20% overhead; no warning <50ms floor; soft-launch vs hard-block behavior |
| `packages/temper-placer/tests/test_stage_invariants.py` | U1 | Stage ABC default invariants empty; override returns tuple; type checker pass |
| `packages/temper-placer/tests/test_board_state_snapshot.py` | U4 | BoardState.copy() identity/equality; StageOutput.to_snapshot_dict() content |

### Integration Tests

| Test | Covers | Key Assertions |
|------|--------|----------------|
| `tests/regression/test_closure_drc_fence.py` | U7, U8 | Closure test with `DRCFence(fail_on_violation=True)` detects temper-116 (SC1); overlapping placement halted at placement stage (SC2); per-stage overhead ≤20% for stages ≥50ms (SC3) |
| `tests/regression/test_strangler_fence.py` | U5 | Dual-run mode with alternative stage; divergence reporting matches AE4 |

### Existing Test Regression

- All existing `tests/` must continue to pass without modification — the fence is opt-in via `fence=None` default on both pipelines
- `tests/regression/test_closure.py` must pass (backward-compatible pipeline behavior)

### CI Gates

- **Budget gate**: `DRCFence(ci_enforce=True)` in closure test. WARNING-only for 2 weeks post-deployment, then hard-block on >20% overhead.
- **Violation gate**: `DRCFence(fail_on_violation=True)` in closure test. Any stage introducing DRC violations fails CI.
- Both gates are opt-in via pipeline configuration; default is `fail_on_violation=False, ci_enforce=False`.

## Implementation Order

Units are ordered by dependency chain:

```
U1 (invariants) ──┬── U2 (DRCFence core) ──┬── U5 (dual-run) ──┐
                  │                        │                     ├── U7 (DeterministicPipeline)
U3 (incremental)──┘                        ├── U6 (perf budget)─┤
                                           │                     └── U8 (RouterV6Pipeline)
U4 (snapshots) ────────────────────────────┘
```

- **Phase A (Foundation):** U1 + U3 + U4 — no fence yet, just the protocols and data structures. Can be implemented in parallel.
- **Phase B (Core):** U2 — DRCFence class with all orchestration logic (check filtering, attribution, timing, reporting). Depends on U1.
- **Phase C (Features):** U5 (dual-run) + U6 (perf budget) — both extend U2 independently.
- **Phase D (Integration):** U7 (DeterministicPipeline) + U8 (RouterV6Pipeline) — wire fence into both pipelines. Depends on U2+U6.

Each phase is independently testable and reviewable.
