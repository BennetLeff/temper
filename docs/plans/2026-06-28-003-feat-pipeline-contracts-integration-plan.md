---
date: 2026-06-28
status: active
depth: deep
source: docs/brainstorms/2026-06-28-pipeline-contracts-integration-requirements.md
---

# feat: Pipeline Contracts & Cross-Stage Integration

## Summary

Extend the DRC fence to stages 1 and 4 by adding `ViaPlacement` and `TracePlacement` as first-class DRC primitives; add a `StageLedger` for cross-stage object-set conservation; and prove via executable PBT that Stage 2's 8 micro-stage validators compose into a correct `ChannelSkeleton` graph.

---

## Problem Frame

The Router V6 DRC fence covers stages 2, 3, and 5 but has documented gaps at stages 1 and 4 (`pipeline.py:421-425`, `pipeline.py:478-481`). The root cause is that the `temper_drc` input model (`Placement`, `ComponentPlacement`) carries only component-level data — `Via` and `Trace` are not first-class primitives the fence can operate on. Stage 1 produces escape vias; Stage 4 produces routed traces and vias. Both are invisible to the fence, creating a blind spot where garbage-in at entry or undetected errors at exit propagate silently.

A second class of bugs is invisible to per-stage validators: objects silently dropped or duplicated across stage boundaries. No mechanism currently tracks object-set cardinality across stages. A stage that drops a via during transformation passes every per-stage check while producing an incorrect board.

A third gap is compositional: Stage 2's 8 micro-stages each have per-sub-step validators (`@register_validator`), but there is no proof that the conjunction of sub-step invariants implies the `ChannelSkeleton` graph is correct. Individual validators can all pass while the aggregate output — the graph that Stage 3's SAT solver consumes — is silently broken.

## Scope Boundaries

**In scope:**
- Adding `ViaPlacement` and `TracePlacement` primitives to `temper_drc/input/placement.py` as first-class geometric entities alongside `ComponentPlacement`
- Wiring stages 1 and 4 into the `DRCFence` via `InvariantSpec` declarations and `_parsed_pcb_to_drc_input` conversion
- New `Check(ABC)` subclasses: `ViaSpacingCheck`, `ViaComponentClearanceCheck`, `TraceWidthCheck`, `TraceSpacingCheck`, `AnnularRingCheck`
- A `StageLedger` that counts object types (components, vias, traces, nets, pads) before and after each pipeline stage and reports imbalances
- An inductive correctness ladder (PBT) proving that if all 8 Stage 2 micro-stage validator properties hold, the extracted `ChannelSkeleton` graph satisfies three aggregate properties: connected subgraphs per net, sufficient channel widths, no orphan nodes

**Out of scope:**
- SAT solver or topology stage correctness proofs (covered by separate plans)
- Runtime monitors for A\* (covered by ideation idea #7)
- Structural induction on `RoutingResults` for DFM validators (covered by ideation idea #10)
- Real-time pipeline monitoring or telemetry dashboards

---

## Key Technical Decisions

1. **Separate `ViaPlacement` / `TracePlacement` DRC primitives, NOT unified with `board.py` types.** The `board.py` domain model (`Component`, `Trace`, `Via`, `Pad`) already defines geometric primitives, but the DRC input model lives in `temper-drc` (a separate package) and imposes a different contract (dictionary serialization, bounding box API, check-runner compatibility). Merging would create circular imports between `temper_drc` and `temper_placer`. (Resolved Q1 from requirements.)

2. **EscapeVia layer resolved from `Component.initial_side`.** The `EscapeVia` dataclass (`escape_via_generator.py:19-38`) has no `layer` field. The layer is derived from the owning component's `initial_side` property (`0` -> `"F.Cu"`, `1` -> `"B.Cu"`) using the existing `side_to_layer_name()` function in `board.py:211-220`. Each `EscapeVia` is associated with a specific `Component`/`DensePackage`; the conversion function `_parsed_pcb_to_drc_input` receives this association via the `escape_vias` parameter alongside the component mapping already available from `ParsedPCB.components`.

3. **`_run_fence` extended with optional `escape_vias` and `routing_results` params.** The current signature (`stage_name, invariants, pcb`) is extended with `escape_vias=None` and `routing_results=None`. When either is provided, `_parsed_pcb_to_drc_input` populates the corresponding `Placement.vias` / `Placement.traces` fields. Default `None` preserves backward compatibility with Stage 0.5 fence calls.

4. **New `Check(ABC)` subclasses in `temper_drc/checks/drc/`.** Five new checks are needed, each subclassing `Check(ABC)` per the existing pattern (`clearance.py`, `component_overlap.py`): `ViaSpacingCheck` (`drc_via_spacing`), `ViaComponentClearanceCheck` (`drc_component_clearance`), `TraceWidthCheck` (`drc_trace_width`), `TraceSpacingCheck` (`drc_trace_spacing`), `AnnularRingCheck` (`drc_annular_ring`). Existing clearance checks operate on `ComponentPlacement.bounds` and are hard-wired to component-level data only; they cannot be reused for via/trace geometry without a `geometric_entity` abstraction (deferred per Q2).

5. **`StageLedgerImbalanceError` (RuntimeError subclass) raised when `is_balanced=False`.** Mirrors the existing `FenceViolationError` pattern at `fence.py:129-134`. The error carries the `LedgerReport` as a field for upstream handlers. Severity matching follows `fail_on_violation` from `DRCFence` — when the fence is configured with `fail_on_violation=True`, the ledger imbalance also raises.

6. **Executable PBT for inductive correctness ladder.** Red-blue check structure: red (counterexample-seeking) PBT tests verify the claim "all 8 micro-stage validators pass ⇒ aggregate property holds." Blue (property) tests verify the aggregate properties hold on known-good skeletons. Counterexamples flag which micro-stage validator requires strengthening.

7. **`StageLedger` identity tracking deferred to Phase 2.** The current implementation uses count-based tracking only. Object-ref identity tracking (Q3) is deferred — it requires propagating stable UUIDs through all stages, a cross-cutting concern that warrants its own plan.

8. **Stage 1 and 4 fence violations halt the pipeline** (matching Stage 2-3-5 `fail_on_violation=True`). The soft-launch question (Q5) is resolved: follow the existing fence contract. If existing runs produce violations that need fixing, those are bugs to fix, not reasons to defer the fence.

---

## Implementation Units

---

### U1. Define `ViaPlacement` and `TracePlacement` DRC Primitives

**Goal**: Add via and trace primitives to the `temper_drc` input model so the DRC fence can operate on Stage 1 and Stage 4 geometry.

**Requirements**: FR1

**Dependencies**: None

**Files**:
- **Modify**: `packages/temper-drc/src/temper_drc/input/placement.py`
  - Add `ViaPlacement` dataclass: `ref: str`, `x: float`, `y: float`, `diameter: float`, `drill: float`, `layer: str`, `net_name: str`, `via_type: str`
  - Add `TracePlacement` dataclass: `ref: str`, `path: list[tuple[float, float]]`, `width: float`, `layer: str`, `net_name: str`
  - Each exposes a `bounds` property returning `(x_min, y_min, x_max, y_max)`
  - Extend `Placement` with `vias: dict[str, ViaPlacement]` and `traces: dict[str, TracePlacement]` (default `field(default_factory=dict)`)
  - Extend `from_dict()` / `to_dict()` for both new fields
- **Modify**: `packages/temper-drc/src/temper_drc/input/__init__.py` — export new types

**Approach**:
- `ViaPlacement.bounds` returns a tight bounding box: `(x - diameter/2, y - diameter/2, x + diameter/2, y + diameter/2)`
- `TracePlacement.bounds` returns the axis-aligned bounding box of all path vertices, expanded by `width/2` on each side
- `Placement.from_dict()` and `Placement.to_dict()` follow the existing pattern for `components` list serialization (`placement.py:194-240`). The new `vias` and `traces` fields use list-of-dict serialization (matching the `components` pattern), not nested dict keys.
- `Placement.all_via_pairs()` and `Placement.all_trace_pairs()` methods (or a general `all_entity_pairs()` abstraction) for check consumption
- Backward compatibility: `from_dict()` without `"vias"` or `"traces"` keys produces empty dicts (NFR3)

**Test scenarios**:
- `ViaPlacement.bounds` returns correct box for a 0.6mm via at (10, 20)
- `TracePlacement.bounds` for a 3-point path returns correct axis-aligned bounding box with width expansion
- `Placement` with empty vias/traces dicts serializes to/from JSON without data loss
- `Placement.from_dict()` on a dict without `"vias"` key produces `vias={}` (backward compat)
- `Placement.to_dict()` includes vias/traces arrays when populated

**Verification**: `pytest packages/temper-drc/tests/` passes. Round-trip JSON test with all fields populated.

---

### U2. Implement New DRC Checks for Via and Trace Geometry

**Goal**: Create `Check(ABC)` subclasses that consume `ViaPlacement` and `TracePlacement` primitives to detect spacing, clearance, width, and annular ring violations.

**Requirements**: FR2, FR3

**Dependencies**: U1

**Files**:
- **Create**: `packages/temper-drc/src/temper_drc/checks/drc/via_spacing.py` — `ViaSpacingCheck` (`drc_via_spacing`)
- **Create**: `packages/temper-drc/src/temper_drc/checks/drc/via_component_clearance.py` — `ViaComponentClearanceCheck` (`drc_component_clearance`)
- **Create**: `packages/temper-drc/src/temper_drc/checks/drc/trace_width.py` — `TraceWidthCheck` (`drc_trace_width`)
- **Create**: `packages/temper-drc/src/temper_drc/checks/drc/trace_spacing.py` — `TraceSpacingCheck` (`drc_trace_spacing`)
- **Create**: `packages/temper-drc/src/temper_drc/checks/drc/annular_ring.py` — `AnnularRingCheck` (`drc_annular_ring`)
- **Modify**: `packages/temper-drc/src/temper_drc/checks/drc/__init__.py` — export new checks
- **Create**: `packages/temper-drc/tests/checks/test_via_spacing.py`
- **Create**: `packages/temper-drc/tests/checks/test_via_component_clearance.py`
- **Create**: `packages/temper-drc/tests/checks/test_trace_width.py`
- **Create**: `packages/temper-drc/tests/checks/test_trace_spacing.py`
- **Create**: `packages/temper-drc/tests/checks/test_annular_ring.py`

**Approach**:

- **`ViaSpacingCheck`** — For each same-layer pair of `ViaPlacement` entries, compute center-to-center distance and verify `distance >= max(drill_a, drill_b) / 2 + max(drill_a, drill_b) / 2 + required_clearance`. For annular ring spacing, verify `distance >= (diameter_a / 2) + (diameter_b / 2) + 0.15` (default annular-to-annular clearance). Uses `Placement.vias` and `Placement.components` to cross-check via-vs-component.

- **`ViaComponentClearanceCheck`** — For each via, check against all same-layer component `bounds`. Via padded bounds (diameter-center radius + clearance) must not intersect component bounding boxes. Uses both `Placement.vias` and `Placement.components`.

- **`TraceWidthCheck`** — For each `TracePlacement`, verify `width >= min_trace_width` from `ConstraintSet` for the net's class. Net class resolved via the `Placement.net_classes` mapping with fallback to `"Signal"`.

- **`TraceSpacingCheck`** — For each same-layer pair of traces, compute minimum segment-to-segment distance and verify it meets the required clearance from `ConstraintSet.get_clearance()`. Intra-net traces on the same net are checked with a reduced clearance threshold (or skipped, per net-class config).

- **`AnnularRingCheck`** — For each `ViaPlacement`, verify `(diameter - drill) / 2 >= 0.15` (or the configured minimum annular ring from `ConstraintSet`). Report violation with the calculated annular ring width.

**Patterns to follow**: `ClearanceCheck` at `checks/drc/clearance.py` for the `Check(ABC)` subclass pattern. `ComponentOverlapCheck` at `checks/drc/component_overlap.py` for the incremental region filtering pattern. Issue severity: via spacing violations -> ERROR, component clearance -> CRITICAL, trace width -> ERROR, trace spacing -> ERROR, annular ring -> WARNING.

**Test scenarios**:
- Two vias at (0,0) and (0.2,0.2) with 0.6mm diameter and 0.15mm clearance produce a violation
- Two vias at (0,0) and (2.0,2.0) with adequate spacing produce no violation
- Via positioned inside a component's bounding box produces a violation
- Trace with width 0.05mm when minimum is 0.15mm produces a violation
- Two parallel traces 0.1mm apart when clearance requires 0.2mm produce a violation
- Via with 1.0mm diameter and 0.9mm drill produces an annular ring violation (0.05mm < 0.15mm)
- Empty `Placement.vias` / `Placement.traces` produce `passed=True` with no issues
- Same-layer filtering works correctly (vias on different layers ignored)

**Verification**: `pytest packages/temper-drc/tests/checks/ -v` passes. All new checks return correct `CheckResult` with proper severity, affected items, and location data.

---

### U3. Extend `EscapeVia` with Layer Field

**Goal**: Add a `layer: str` field to `EscapeVia` so the DRC fence can attribute vias to the correct layer without cross-referencing the owning component at fence time.

**Requirements**: FR2

**Dependencies**: None (can run in parallel with U1, U2)

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/escape_via_generator.py`
  - Add `layer: str` field to `EscapeVia` dataclass (default `"F.Cu"` for backward compat)
  - Accept an optional `layer_name: str | None = None` parameter in `generate_escape_vias()`
  - When `layer_name` is provided, set it on every generated `EscapeVia`; when `None`, default to `"F.Cu"`

**Approach**:
- The `layer_name` is resolved at the call site (`pipeline.py:406-417`) from the `DensePackage.component.initial_side` using `side_to_layer_name(side)`. The call site in the pipeline loop already has access to the `DensePackage` and its `component`.
- The `layer` field is optional with default `"F.Cu"` to maintain backward compatibility for existing callers that don't supply a layer (principally tests).
- Modify the pipeline's Stage 1 loop (`pipeline.py:406-417`):
  ```python
  side = getattr(dense_pkg.component, "initial_side", 0) or 0
  layer_name = side_to_layer_name(side)
  vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="dog-bone", layer_name=layer_name)
  ```
- Update the `generate_escape_vias` docstring to document the new parameter.

**Patterns to follow**: `side_to_layer_name()` at `board.py:211-220` (already imported in `pipeline.py:28`). Dataclass extension pattern: add field with default value for backward compat.

**Test scenarios**:
- `EscapeVia(layer="B.Cu", ...)` constructs correctly
- `generate_escape_vias(dense_pkg, rules, layer_name="B.Cu")` produces vias with `layer="B.Cu"`
- `generate_escape_vias(dense_pkg, rules)` with no `layer_name` produces vias with `layer="F.Cu"` (default)
- Pipeline run on `minimal_board.kicad_pcb` populates `EscapeVia.layer` correctly

**Verification**: `pytest packages/temper-placer/tests/ -k "escape" -v` passes. Manual inspection of pipeline output confirms layer field on all vias.

---

### U4. Extend `_parsed_pcb_to_drc_input` for Via/Trace Population

**Goal**: Extend the DRC input conversion function to populate `Placement.vias` from `EscapeVia` lists and `Placement.traces`/`Placement.vias` from `RoutingResults`.

**Requirements**: FR2, FR3

**Dependencies**: U1, U3

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (`_parsed_pcb_to_drc_input`, lines 195-261)
  - Add optional `escape_vias: list[EscapeVia] | None = None` parameter
  - Add optional `routing_results: RoutingResults | None = None` parameter
  - When `escape_vias` is provided, populate `Placement.vias` from the list:
    - `ref` = `"escape_{net_name}_{pin_number}"`
    - `layer` = `via.layer` (from U3)
    - `via_type` = `via.via_type`
    - `diameter` / `drill` / position from `EscapeVia` fields
  - When `routing_results` is provided:
    - For each `CompiledRoute`, populate `Placement.traces` from `route.path`:
      - `ref` = `"trace_{net_name}"`
      - `path` = `route.path.coordinates`
      - `width` = `route.width_mm`
      - `layer` = `route.path.layer_name`
    - For each `CompiledRoute.vias`, populate `Placement.vias` (routed vias):
      - `ref` = `"routed_{net_name}_{idx}"`
      - `layer` = `via.from_layer` (for single-layer attribution; multi-layer vias get one entry per connected layer)
      - `via_type` = `"routed"`

**Approach**:
- The conversion follows the existing component population pattern (lines 215-234)
- Escape via `ref` format: `"escape_{net_name}_{pin_number}"` ensures uniqueness within the DRC placement
- Routed via `ref` format: `"routed_{net_name}_{idx}"` uses the via's index in the `CompiledRoute.vias` list
- Trace `ref` format: `"trace_{net_name}"` — for nets with multiple segments, each segment gets an index suffix: `"trace_{net_name}_0"`, `"trace_{net_name}_1"`, etc.
- The `ViaPlacement` and `TracePlacement` dict keys use the generated `ref` values as dict keys
- When both `escape_vias` and `routing_results` are provided (Stage 4 fence), vias from both sources are merged — escape via refs start with `"escape_"` and routed via refs start with `"routed_"` to prevent key collisions
- The function imports `ViaPlacement` and `TracePlacement` from `temper_drc.input.placement`

**Test scenarios**:
- `_parsed_pcb_to_drc_input(pcb, escape_vias=[via_a, via_b])` produces `Placement.vias` with 2 entries
- `_parsed_pcb_to_drc_input(pcb, routing_results=rr)` produces `Placement.traces` and `Placement.vias` from routes
- `_parsed_pcb_to_drc_input(pcb)` with neither param produces `Placement.vias={}, traces={}` (backward compat)
- Escape and routed via refs do not collide when both sources are present

**Verification**: `pytest packages/temper-placer/tests/ -k "fence" -v` passes. Unit test verifying via/trace counts in the output Placement.

---

### U5. Wire Stage 1 Fence into Pipeline

**Goal**: Run `DRCFence.check()` after Stage 1 escape via generation with via spacing and component clearance invariants.

**Requirements**: FR2

**Dependencies**: U1, U2, U3, U4

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
  - Add `_stage_1_invariants()` function returning `tuple[InvariantSpec, ...]`:
    - `InvariantSpec("drc_via_spacing", "Escape vias do not violate drill or annular-ring spacing")`
    - `InvariantSpec("drc_component_clearance", "Escape vias do not fall within component courtyards")`
  - Modify `_run_fence` signature (line 858) to accept `escape_vias=None`, `routing_results=None`, passing them through to `_parsed_pcb_to_drc_input`
  - Insert Stage 1 fence call after the escape via loop (after line 419, before the `# NOTE: No Stage 1 fence` block):
    ```python
    if self.fence:
        self._run_fence(
            stage_name="router_v6.stage1_escape_vias",
            invariants=_stage_1_invariants(),
            pcb=pcb,
            escape_vias=escape_vias,
        )
    ```
  - Remove the `# NOTE: No Stage 1 fence` block (lines 421-425)

**Approach**:
- The `_run_fence` modification passes `escape_vias` through to `_parsed_pcb_to_drc_input`, which populates `Placement.vias`
- The `_stage_1_invariants` tuple follows the existing `_stage_0_5_invariants` pattern (line 884-886)
- The fence check runs on the full escape via set after all dense packages are processed
- When `self.fence is None` (no fence configured), the check is skipped — backward compatible

**Test scenarios**:
- Pipeline with fence enabled runs Stage 1 fence and completes without error on `minimal_board.kicad_pcb`
- Pipeline without fence (fence=None) completes without error (backward compat)
- Deliberately corrupted escape vias (two vias at the same position) trigger `FenceViolationError` when `fail_on_violation=True`
- Stage 1 fence overhead on `temper.kicad_pcb` is <= 20% of Stage 1 wall-clock time (NFR1 / SC5)

**Verification**: `pytest packages/temper-placer/tests/ -k "fence" -v` passes. Manual pipeline run on `temper.kicad_pcb` with verbose output confirms Stage 1 fence execution and result.

---

### U6. Wire Stage 4 Fence into Pipeline

**Goal**: Run `DRCFence.check()` after Stage 4 geometric realization with trace width, trace spacing, via spacing, annular ring, and component overlap invariants.

**Requirements**: FR3

**Dependencies**: U1, U2, U4

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
  - Add `_stage_4_invariants()` function returning `tuple[InvariantSpec, ...]`:
    - `InvariantSpec("drc_trace_width", "All routed traces meet minimum width per net class")`
    - `InvariantSpec("drc_trace_spacing", "No trace-to-trace clearance violations on same layer")`
    - `InvariantSpec("drc_via_spacing", "No routed via spacing violations")`
    - `InvariantSpec("drc_annular_ring", "All vias meet minimum annular ring")`
    - `InvariantSpec("drc_component_overlap", "No via or trace intersects component courtyards")`
  - Insert Stage 4 fence call after `_run_stage4` (after line 456, before `# NOTE: No Stage 4 fence`):
    ```python
    if self.fence:
        self._run_fence(
            stage_name="router_v6.stage4_geometric",
            invariants=_stage_4_invariants(),
            pcb=pcb,
            escape_vias=escape_vias,
            routing_results=stage4.routing_results,
        )
    ```
  - Remove the `# NOTE: No Stage 4 fence` block (lines 478-481)

**Approach**:
- Both `escape_vias` and `routing_results` are passed to `_run_fence` so the conversion produces a complete `Placement` with all vias (escape + routed) and all traces
- The `drc_component_overlap` check now operates on both component-vs-component and component-vs-via/component-vs-trace intersections
- Stage 4 fence runs after geometric realization but before the (optional) manufacturing DRC stage

**Test scenarios**:
- Pipeline with fence enabled runs Stage 4 fence and completes without error on `minimal_board.kicad_pcb`
- Deliberately corrupted routing results (zero-width traces) trigger `FenceViolationError` when `fail_on_violation=True`
- Stage 4 fence overhead on `temper.kicad_pcb` is <= 20% of Stage 4 wall-clock time (NFR2 / SC6)

**Verification**: `pytest packages/temper-placer/tests/ -k "fence" -v` passes. Manual pipeline run on `temper.kicad_pcb` confirms Stage 4 fence execution and result.

---

### U7. Implement `StageLedger` — Cross-Stage Double-Entry Conservation

**Goal**: Create a `StageLedger` class that counts object types at each stage boundary and detects when objects are silently dropped or duplicated across stages.

**Requirements**: FR4, FR5

**Dependencies**: None (can run in parallel with U1-U6)

**Files**:
- **Create**: `packages/temper-placer/src/temper_placer/router_v6/stage_ledger.py` — `StageLedger`, `StageLedgerEntry`, `LedgerReport`, `TransformMapping`, `StageLedgerImbalanceError`
- **Create**: `packages/temper-placer/tests/router_v6/test_stage_ledger.py` — unit tests

**Approach**:
- `StageLedgerEntry` dataclass:
  - `stage_name: str`
  - `phase: str` — `"pre"` or `"post"`
  - `counts: dict[str, int]` — `{"components": N, "vias": N, "traces": N, "nets": N, "pads": N}`
- `TransformMapping` dataclass:
  - `source_type: str` — object type consumed (e.g., `"nets"`)
  - `target_type: str` — object type produced (e.g., `"via_vars"`)
  - `stage_name: str` — stage responsible for the transformation
  - `source_count: int` — count consumed
  - `target_count: int` — count produced
- `LedgerReport` dataclass:
  - `is_balanced: bool`
  - `per_stage_deltas: list[DeltaEntry]` — per-stage breakdown (deferred to Phase 2 for full detail; Phase 1 provides `is_balanced` and a text summary)
  - `total_dropped: int`
  - `total_duplicated: int`
  - `transformations: list[TransformMapping]`
- `StageLedger` class:
  - `register(stage_name, phase, **counts)` — record counts entering/exiting a stage
  - `add_transform(source_type, target_type, stage_name)` — declare a legitimate transformation
  - `commit() -> LedgerReport` — compute deltas, check balance
  - Computes delta per object type: `delta = post[type] - pre[type]`
  - Applies transform mappings: a `TransformMapping("nets", "via_vars")` for Stage 3 means `delta.nets` can be negative (net count consumed) without triggering imbalance, as long as the net count decrease is matched by a net-to-via_var transform declaration
  - On imbalance: raises `StageLedgerImbalanceError` (when `raise_on_imbalance=True`) containing the `LedgerReport`
  - `format_delta_report()` returns a human-readable string
- `StageLedgerImbalanceError(RuntimeError)`:
  - Carries `ledger_report: LedgerReport`
  - `__str__` reports the responsible stage, object type, and count delta

**Integration points in `RouterV6Pipeline.run()`**:
- Ledger records at all 5 stage boundaries:
  - **Pre-Stage-1**: `register("stage1_escape_vias", "pre", components=N, nets=M, pads=P)`
  - **Post-Stage-1**: `register("stage1_escape_vias", "post", vias=len(escape_vias))`
  - **Post-Stage-2**: `register("stage2_channel", "post", skeletons=k)`
  - **Post-Stage-3**: `register("stage3_topology", "post", ...)`
  - **Post-Stage-4**: `register("stage4_geometric", "post", traces=N, vias=M)`
  - **Post-Stage-5**: `register("stage5_manufacturing", "post", ...)`
- `add_transform("nets", "via_vars", "stage3_topology")` — Stage 3 may create `ViaVar` objects from net connections
- `commit()` called at pipeline exit
- `LedgerReport` exposed on `RouterV6Result.ledger_report` and logged at `INFO` level

**Patterns to follow**: `DRCFence` at `fence.py:147-297` for the "check object with optional enforcement" pattern. `StageDRCFailure` at `stage_validators.py:22-31` for the lightweight result dataclass pattern.

**Test scenarios**:
- Equal counts in/out for all object types: `is_balanced=True`
- 5 vias in, 2 vias out without transform mapping: `is_balanced=False`, `total_dropped=3`
- 3 nets in, 0 nets out with `TransformMapping("nets", "via_vars")` declared: `is_balanced=True` (net loss explained by transform)
- `StageLedgerImbalanceError` raised when `raise_on_imbalance=True` and imbalance detected
- Empty ledger (no registrations): `is_balanced=True`
- Multiple stages with cumulative deltas: report aggregates correctly

**Verification**: `pytest packages/temper-placer/tests/router_v6/test_stage_ledger.py -v` passes.

---

### U8. Integrate `StageLedger` into Pipeline

**Goal**: Wire `StageLedger` into `RouterV6Pipeline.run()` at all 5 stage boundaries and expose the `LedgerReport` on the pipeline result.

**Requirements**: FR4, FR5

**Dependencies**: U7

**Files**:
- **Modify**: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
  - Import `StageLedger`, `StageLedgerImbalanceError`
  - Add `ledger: StageLedger | None = None` to `RouterV6Pipeline.__init__(line 267)`
  - Create `StageLedger` in `run()` (or accept from constructor):
    - Pre-Stage-1: register component, net, pad counts from `pcb`
    - Post-Stage-1: register via counts from `escape_vias`
    - Post-Stage-2: register skeleton/node counts from `stage2`
    - Post-Stage-3: register `ViaVar` / `NetChannelVar` counts
    - Post-Stage-4: register trace and via counts from `stage4.routing_results`
    - Post-Stage-5: register any manufacturing artifacts
  - Add transform mappings: Stage 3 `nets -> via_vars`
  - `commit()` at pipeline end; raise `StageLedgerImbalanceError` if unbalanced and `fence.fail_on_violation` is True
- **Modify**: `RouterV6Result` — add `ledger_report: LedgerReport | None = None` field
- **Create**: `packages/temper-placer/tests/router_v6/test_pipeline_ledger_integration.py`

**Approach**:
- Count extraction uses `len()` on collections:
  - Pre-Stage-1: `len(pcb.components)`, `len(pcb.nets)`, sum of pads across components
  - Post-Stage-1: `len(escape_vias)`
  - Post-Stage-2: `len(stage2.skeletons)`, sum of node/edge counts
  - Post-Stage-3: counts from `stage3.topology_graph`
  - Post-Stage-4: `len(stage4.routing_results.compiled_routes)`, vias from `stage4.via_placement`
- The `RouterV6Pipeline.__init__` adds `ledger_enabled: bool = True` param to control ledger activation
- When `ledger_enabled=False`, no ledger is created and no overhead is incurred (opt-out for performance-critical runs)

**Test scenarios**:
- Pipeline run on `minimal_board.kicad_pcb` produces `ledger_report.is_balanced=True`
- Deliberately corrupted pipeline (injected via count mismatch) produces `is_balanced=False` (SC3)
- Ledger report is logged at INFO level during pipeline execution
- `RouterV6Result.ledger_report` is populated when ledger is enabled

**Verification**: `pytest packages/temper-placer/tests/router_v6/test_pipeline_ledger_integration.py -v` passes. Pipeline JSON snapshot test confirms `ledger_report` in output.

---

### U9. Inductive Correctness Ladder — Aggregate PBT Tests

**Goal**: Prove via executable PBT that all 8 Stage 2 micro-stage validators passing implies the `ChannelSkeleton` graph is correct (connected subgraphs per net, sufficient channel widths, no orphan nodes).

**Requirements**: FR6, FR7

**Dependencies**: U1-U8 (conceptually independent; can run in parallel with U1-U8)

**Files**:
- **Create**: `packages/temper-placer/tests/router_v6/test_stage2_inductive_ladder.py` — PBT test suite
- **Modify**: `packages/temper-placer/tests/router_v6/dfm_property_strategies.py` — add `channel_skeleton_boards` strategy (if needed; extensions to existing strategies)

**Approach**:
- **Red tests (counterexample-seeking)**:
  - `@given(channel_skeleton_boards())` generates test boards exercising each aggregate property
  - For each board, run all 8 micro-stage validators
  - Assert: if all validators pass, then the aggregate property holds
  - On counterexample: report which aggregate property failed, which net/layer triggered it, the specific micro-stage output values, and a diagnostic suggesting which micro-stage validator needs strengthening
- **Blue tests (property verification)**:
  - Verify each aggregate property independently on known-good skeleton graphs
  - Property 1 (connected subgraphs): `@given(channel_skeleton_boards(min_nets=2))` — every net's pin positions are path-connected in the skeleton graph
  - Property 2 (channel widths): `@given(channel_skeleton_boards(with_widths=True))` — every channel edge width >= trace_width + clearance for the widest net
  - Property 3 (no orphans): `@given(channel_skeleton_boards())` — every node lies on at least one path between pin positions; no dead-end branches

- **Aggregate property implementations**:
  - `_check_connected_subgraphs(skeleton: ChannelSkeleton, pcb: ParsedPCB) -> list[StageDRCFailure]`
    - For each net, collect its pin positions from `pcb.nets` / `pcb.components`
    - Check that all pin positions for a net are in the same connected component of the skeleton graph
    - A pin is "connected to the skeleton" if there exists a skeleton node within `tolerance` distance
  - `_check_sufficient_widths(skeleton: ChannelSkeleton, channel_widths: ChannelWidths, pcb: ParsedPCB) -> list[StageDRCFailure]`
    - For each channel edge, get the computed width from `ChannelWidths`
    - For the widest net routed through that channel (from net-class rules), verify `channel_width >= trace_width + clearance`
  - `_check_no_orphans(skeleton: ChannelSkeleton, pcb: ParsedPCB) -> list[StageDRCFailure]`
    - Identify "leaf" nodes (degree 1 in the graph) that are not within proximity of any pin position
    - A leaf that is not pinned to a pad is an orphan — a dead-end branch with no net terminus

- **Diagnostic format** (FR7):
  - When an aggregate property fails while all micro-validators pass:
    ```
    GAP FAILURE: Property=connectivity, Net=NET1, Layer=F.Cu, Detail="Pin at (12,34) not reachable from pin at (56,78)"
    Micro-stage outputs: channel_width=0.12mm, required=0.15mm for net class Power
    Diagnostic: ChannelWidths validator at channel_widths.py:265 does not check against per-net-class minimum width
    ```

**Patterns to follow**: `dfm_property_strategies.py` for Hypothesis strategy patterns. `stage_validators.py:21-65` for `StageDRCFailure` and `@register_validator` pattern. All tests use `@settings` with `@given` per NFR5. Strategies reuse or extend `dfm_property_strategies.py` (NFR4).

**Test scenarios**:
- Known-good board: all 8 validators pass, all 3 aggregate properties hold
- Board with connected skeleton: connectivity property passes
- Board with sufficient widths: channel width property passes
- Board with no orphans: orphan property passes
- Board with negative occupancy grid cells that passes individual validators but fails aggregate (SC4)
- Counterexample naming: diagnostic identifies which validator needs strengthening
- Empty board (no nets): all aggregate properties vacuously hold

**Verification**: `pytest packages/temper-placer/tests/router_v6/test_stage2_inductive_ladder.py -v` passes. PBT shrink output produces minimal counterexamples.

---

## Deferred Work

| Item | Rationale |
|------|-----------|
| `StageLedger` identity-level object-ref matching (Q3) | Requires propagating stable UUIDs through all pipeline stages — a cross-cutting concern warranting its own plan |
| Full `LedgerReport.per_stage_deltas` breakdown in structured format | Phase 1 delivers `is_balanced` + text summary; structured per-stage breakdown deferred to Phase 2 per FR5 |
| `geometric_entity` abstraction for DRC checks | Existing clearance checks are hard-wired to `ComponentPlacement.bounds`. A shared `geometric_entity` abstraction would reduce code duplication for via/component/trace checks but is deferred per Q2 |
| Per-net-class congestion heatmaps (from ideation idea #4) | Separate ideation scope; not required for fence/ledger/ladder integration |
| Real-time pipeline monitoring dashboards | Out of scope per requirements |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| New DRC checks produce false positives on valid boards | Medium | Medium | Run checks on `temper.kicad_pcb` and the existing test board fixtures; tune clearance thresholds using existing design rules |
| Stage 4 fence overhead exceeds 20% budget on large boards | Low | Medium | The `DRCFence.perf_budget_pct` mechanism already emits warnings (and enforces after 2026-07-06). Reduce check scope via `affected_regions` on `InvariantSpec` if needed |
| `StageLedger` counting is brittle to object representation changes across stages | Medium | Low | Counts are computed from `len()` on well-known collections. Only a type-renaming or removal across stages would break — unlikely given the frozen stage output dataclasses |
| Aggregate PBT tests are too slow for CI | Medium | Medium | Use `@settings(max_examples=50)` for CI runs; full `max_examples=200` for nightly. Hypothesis shrinking produces minimal counterexamples quickly |
| Stage 1/4 fence violations are pre-existing in current pipeline output | Medium | Medium | Run fence against `temper.kicad_pcb` first; fix any violations before gating. The `fail_on_violation` flag gates enforcement — keep it `False` during development, `True` in CI |

## Dependencies

- `temper_drc/input/placement.py` — `Placement`, `ComponentPlacement` (U1 modifies)
- `temper_drc/core/check.py` — `Check(ABC)` (U2 subclasses)
- `temper_drc/core/fence.py` — `DRCFence`, `InvariantSpec` (U5, U6 consume)
- `temper_drc/core/runner.py` — `CheckRunner` (U2 checks run through it)
- `temper_placer/core/board.py` — `side_to_layer_name()` (U3 uses)
- `temper_placer/router_v6/escape_via_generator.py` — `EscapeVia`, `generate_escape_vias()` (U3 modifies)
- `temper_placer/router_v6/routing_results.py` — `CompiledRoute`, `RoutingResults` (U4 consumes)
- `temper_placer/router_v6/astar_core.py` — `RoutePath` (U4 consumes `.coordinates`, `.layer_name`)
- `temper_placer/router_v6/via_placement.py` — `Via` (U4 consumes routed vias)
- `temper_placer/router_v6/stage2_orchestrator.py` — `Stage2Orchestrator`, micro-stage chain (U9 context)
- `temper_placer/router_v6/channel_skeleton.py` — `ChannelSkeleton`, skeleton graph (U9 target)
- `temper_placer/router_v6/stage_validators.py` — `StageDRCFailure`, `register_validator`, `run_validators` (U9 context)
- `temper_placer/tests/router_v6/dfm_property_strategies.py` — shared PBT strategies (U9 extends)

## Verification Checklist

- [ ] `ViaPlacement` and `TracePlacement` round-trip through `Placement.to_dict()` / `Placement.from_dict()` without data loss
- [ ] `Placement.from_dict()` on dict without `"vias"`/`"traces"` keys produces empty dicts (SC8)
- [ ] All 5 new DRC checks return `passed=True` on empty input
- [ ] `ViaSpacingCheck` detects two vias at positions violating drill-to-drill clearance
- [ ] `ViaComponentClearanceCheck` detects via inside component courtyard
- [ ] `TraceWidthCheck` detects trace width below minimum
- [ ] `TraceSpacingCheck` detects parallel traces too close together
- [ ] `AnnularRingCheck` detects via with annular ring below minimum
- [ ] `EscapeVia.layer` populated correctly from component side
- [ ] `_parsed_pcb_to_drc_input` populates `Placement.vias` from escape vias and `Placement.traces`/`Placement.vias` from routing results
- [ ] Stage 1 fence runs with >= 2 `InvariantSpec` declarations (SC1)
- [ ] Stage 4 fence runs with >= 2 `InvariantSpec` declarations (SC1)
- [ ] `# NOTE: No Stage 1 fence` and `# NOTE: No Stage 4 fence` blocks removed
- [ ] Pipeline with `fence=None` completes without error (backward compat)
- [ ] Stage 1 fence overhead on `temper.kicad_pcb` <= 20% (SC5)
- [ ] Stage 4 fence overhead on `temper.kicad_pcb` <= 20% (SC6)
- [ ] `StageLedger` reports `is_balanced=True` for error-free pipeline run
- [ ] Corrupted pipeline (dropped vias) produces `is_balanced=False` with audit trail naming stage and count (SC3)
- [ ] `StageLedgerImbalanceError` raised when imbalance detected and enforcement enabled
- [ ] Stage ledger counting overhead < 50ms total across all 5 boundaries (SC7)
- [ ] Inductive ladder PBT: all 8 micro-validators pass ⇒ aggregate properties hold on test board
- [ ] Counterexample diagnostic names the aggregate property, net, layer, micro-stage values, and suggested strengthening (SC4)
- [ ] All existing tests continue to pass (SC8)
- [ ] `uv run python scripts/import_linter_gate.py` passes
