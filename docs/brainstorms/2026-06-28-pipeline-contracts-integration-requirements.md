---
date: 2026-06-28
topic: pipeline-contracts-cross-stage-integration
focus: Extend DRC fence to stages 1 and 4 with Via/Trace primitives, add cross-stage double-entry conservation, and prove occupancy-grid-to-channel-skeleton inductive correctness
origin: docs/ideation/2026-06-28-router-v6-mathematical-rigor-ideation.md
status: active
actors: pipeline stages, temper-drc, DRC fence, Stage 2 micro-stages
---

# Requirements: Pipeline Contracts + Cross-Stage Integration

## Problem / Motivation

The Router V6 DRC fence covers stages 2, 3, and 5 but has two documented gaps at stages 1 and 4 (`pipeline.py:421-425`, `pipeline.py:478-481`). The root cause is that the `temper_drc` input model (`Placement`, `ComponentPlacement`) carries only component-level data — `Via` and `Trace` are not first-class primitives the fence can operate on. Stage 1 produces escape vias; Stage 4 produces routed traces and vias. Both are invisible to the fence, creating a blind spot where garbage-in at entry or undetected errors at exit propagate silently.

A second class of bugs is invisible to per-stage validators: objects silently dropped or duplicated across stage boundaries. No mechanism currently tracks object-set cardinality across stages. A stage that drops a via during transformation passes every per-stage check while producing an incorrect board.

A third gap is compositional: Stage 2's 8 micro-stages each have per-sub-step validators (`@register_validator`), but there is no proof that the conjunction of sub-step invariants implies the channel skeleton graph is correct. Individual validators can all pass while the aggregate output — the graph that Stage 3's SAT solver consumes — is silently broken.

## Users & Value

- **Router V6 developers** — catch entry/exit corruption at the stage where it occurs, not after full pipeline completion
- **CI system** — gate on stage-1 and stage-4 fence violations with the same mechanism already proven for stages 2-3-5
- **Stage 2 maintainers** — trust that micro-stage PBT composes into a correct skeleton graph; localization of gaps to specific invariants
- **Pipeline debuggers** — receive precise audit trails when objects are lost/duplicated, naming the responsible stage and affected items

## Scope & Out of Scope

**In scope:**
- Adding `Via` and `Trace` primitives to the `temper_drc` input model (`placement.py`) as first-class geometric entities alongside `ComponentPlacement`
- Wiring stages 1 and 4 into the `DRCFence` via `InvariantSpec` declarations and `_parsed_pcb_to_drc_input` conversion
- A `StageLedger` that counts object types (components, vias, traces, nets, pads) before and after each pipeline stage and reports imbalances
- An inductive correctness ladder proving that if all Stage-2 micro-stage validator properties hold, the extracted `ChannelSkeleton` graph has connected subgraphs per net, sufficient channel widths for trace + clearance, and no orphan nodes

**Out of scope:**
- SAT solver or topology stage correctness proofs (covered by separate ideation ideas #4, #10)
- Runtime monitors for A\* (covered by ideation idea #7)
- Structural induction on `RoutingResults` for DFM validators (covered by ideation idea #10)
- Real-time pipeline monitoring or telemetry dashboards

## Functional Requirements

### FR1: Via and Trace as First-Class DRC Primitives

**Status:** required

The `temper_drc.input.placement` module shall define two new dataclasses:

- `ViaPlacement` with fields: `ref: str` (unique ID), `x: float`, `y: float`, `diameter: float`, `drill: float`, `layer: str`, `net_name: str`, `via_type: str` (e.g., `"escape"`, `"routed"`, `"thermal"`)
- `TracePlacement` with fields: `ref: str` (unique ID), `path: list[tuple[float, float]]` (ordered vertices in mm), `width: float`, `layer: str`, `net_name: str`

Each shall expose a `bounds` property returning `(x_min, y_min, x_max, y_max)` for incremental fence scoping.

The `Placement` container shall add:
- `vias: dict[str, ViaPlacement]`
- `traces: dict[str, TracePlacement]`
- `from_dict` / `to_dict` support for the new fields


**FR2: Stage 1 Fence (Escape Via Generation)**

**Status:** required

The pipeline shall run `DRCFence.check()` after Stage 1 escape via generation with at least the following invariants:
- `drc_via_spacing` — no two escape vias violate drill-to-drill or annular-ring spacing on the same layer
- `drc_component_clearance` — no escape via position falls within a component courtyard

The conversion function `_parsed_pcb_to_drc_input` (`pipeline.py:207-209`) shall be extended to populate `Placement.vias` from the `list[EscapeVia]` produced by `generate_escape_vias()`. The conversion function receives the owning `Component`/`DensePackage` alongside the via list and resolves the layer from the component's `side` property. Alternatively, `generate_escape_vias` shall be extended to produce the `layer` field on `EscapeVia` output.

The `_run_fence` method signature shall be extended with optional parameters `escape_vias=None` and `routing_results=None` to pass stage-specific data to the fence conversion.

The existing `# NOTE: No Stage 1 fence` documentation block shall be removed.

**FR3: Stage 4 Fence (Geometric Realization)**

**Status:** required

The pipeline shall run `DRCFence.check()` after Stage 4 geometric realization with at least the following invariants:
- `drc_trace_width` — all routed trace segments meet minimum trace width per net class
- `drc_trace_spacing` — no two traces on the same layer violate the intra-net or inter-net clearance requirement
- `drc_via_spacing` — no two routed vias violate drill-to-drill or annular-ring spacing
- `drc_annular_ring` — all vias meet minimum annular ring
- `drc_component_overlap` — no via or trace intersects a component courtyard

The conversion from `RoutingResults.compiled_routes` to `Placement.traces` and `Placement.vias` shall be implemented as part of `_parsed_pcb_to_drc_input`.

The existing `# NOTE: No Stage 4 fence` documentation block shall be removed.

**FR4: Stage Ledger — Double-Entry Conservation Across Boundaries**

**Status:** required

A `StageLedger` class shall be created that:
1. Accepts a `register_objects(stage_name, objects)` call enumerating all objects of interest (components, vias, traces, nets, pads) entering a stage and `commit_objects(stage_name, objects)` for the output.
2. Computes the delta per object type and records any loss (`count_in > count_out`) or duplication (`count_out > count_in`).
3. Defines a mapping table for legitimate transformations: e.g., Stage 3 may create `ViaVar` objects from net connections; the ledger records these as `transform(source_type=Net, target_type=ViaVar)` rather than reporting an imbalance.
4. Produces an audit trail on imbalance: `{stage_name} dropped 3 EscapeVia objects: [ref list]`.
5. Can be run at a summary level (count-based) and optionally at an identity level (object-ref matching) for debugging.

The `StageLedger` shall be integrated into `RouterV6Pipeline.run()` with ledger records at all 5 stage boundaries: pre-Stage-1, post-Stage-1, post-Stage-2, post-Stage-3, post-Stage-4, post-Stage-5.

The pipeline shall raise `StageLedgerImbalanceError` when `is_balanced=False`, with severity matching `fail_on_violation` from `DRCFence`.

**FR5: Ledger Conservation Reporting**

**Status:** required

The `StageLedger` shall report a `LedgerReport` containing an `is_balanced: bool` flag and a structured log of per-stage object-type deltas. The pipeline shall log the report at `INFO` level on every run and expose it on the `RouterV6Result` return value. The full `LedgerReport` dataclass (with `per_stage_deltas`, `total_dropped`, `total_duplicated`, `transformations`) is deferred to Phase 2.

**FR6: Inductive Correctness Ladder (PBT)**

**Status:** required

An executable PBT test suite shall establish that if all 8 Stage 2 micro-stage validator properties hold, then the resulting `ChannelSkeleton` graph (per outer layer) satisfies three aggregate properties:

1. **Connected subgraphs per net.** Every net's pin set is contained in a single connected component of the channel skeleton accessible from those pins.
2. **Sufficient channel widths.** Every channel segment's computed width (`ChannelWidthsStage` output) is >= `trace_width + clearance` for the widest net routed through that segment per net-class rules.
3. **No orphan nodes.** Every skeleton graph node lies on at least one path between a net's pin positions; there are no dead-end branches unreachable from all nets.

Each aggregate property shall be implemented as a `@register_validator("ChannelSkeletonAggregate")` PBT test using `@given` strategies from the shared DFM strategy file. The test shall:
- Construct test boards exercising each property independently
- Verify that when all 8 micro-stage validators pass, the aggregate property holds
- Flag counterexamples where micro-stage validators pass but the aggregate property fails, naming which sub-step invariant requires strengthening

**FR7: Aggregation Gap Diagnostic**

**Status:** required

When an aggregate property fails while all micro-stage validators pass (a "gap failure"), the diagnostic shall report:
- Which aggregate property failed (connectivity / channel width / orphan nodes)
- Which net or layer triggered the failure
- The specific values of each micro-stage output that contributed (e.g., `channel_width=0.12mm` vs required `0.15mm` for net class `Power`)
- A suggestion for which micro-stage validator needs strengthening (e.g., "ChannelWidths validator does not check against per-net-class minimum width")

This diagnostic enables the invariant-strengthening feedback loop without requiring full proof embedding in the codebase.

## Non-Functional Requirements

- **NFR1: Fence overhead budget.** Stage 1 and Stage 4 fence checks must not exceed 20% of the stage's wall-clock time on the temper.kicad_pcb reference board (matching existing `DRCFence.perf_budget_pct=20.0`).
- **NFR2: Ledger overhead.** The `StageLedger` counting must add <50ms total across all 5 boundaries (count-based mode) and report a per-stage overhead delta.
- **NFR3: Backward compatibility.** The `Placement` dataclass extensions (vias/traces fields) must default to empty dicts, maintaining compatibility with all existing `Placement.from_dict()` callers.
- **NFR4: Test strategy reuse.** Aggregate property PBT strategies must reuse or extend the existing shared strategies module (`dfm_property_strategies.py`). No private strategy copies.
- **NFR5: Drift prevention.** All new dataclasses shall be `@dataclass`; all new Hypothesis tests shall pair `@settings` with `@given` per the established pattern.

## Success Criteria

- **SC1:** Stages 1 and 4 each have >= 2 `InvariantSpec` declarations producing fence results identical in format to existing stages 2-3-5.
- **SC2:** The `ViaPlacement` and `TracePlacement` DRC primitives can be constructed from `EscapeVia` (Stage 1) and `CompiledRoute` (Stage 4) respectively without data loss.
- **SC3:** A deliberately corrupted pipeline stage (drop every 3rd via) produces a `LedgerReport` with `is_balanced=False` and an audit trail naming the responsible stage, object type, and count.
- **SC4:** A deliberately corrupted occupancy grid (negative cell values) that passes all 8 micro-stage validators triggers an aggregate property failure with a diagnostic pointing to the `OccupancyGrid` cell-non-negativity validator as insufficient.
- **SC5:** Stage 1 fence overhead on temper.kicad_pcb is <= 20% of Stage 1 wall-clock time.
- **SC6:** Stage 4 fence overhead on temper.kicad_pcb is <= 20% of Stage 4 wall-clock time.
- **SC7:** Stage ledger counting overhead across all 5 boundaries is < 50ms total.
- **SC8:** All existing tests continue to pass with the extended `Placement` model (backward compatibility).

## Dependencies & Assumptions

- **D1:** The `DRCFence` and `InvariantSpec` protocol in `temper_drc/core/fence.py` is stable and will not require breaking changes.
- **D2:** The `CheckRunner` in `temper_drc/core/runner.py` supports checks written against `ViaPlacement`/`TracePlacement`. New check subclasses `drc_via_spacing` and `drc_trace_spacing` (subclassing `Check(ABC)`) are in-scope for the fence wiring.
- **D3:** The 8 micro-stage validators (ObstacleMap, RoutingSpace, ChannelSkeleton, ChannelWidths, OccupancyGrid, LayerCapacity, RoutingDemand, BottleneckAnalysis) already register with `@register_validator` and their invariants are individually defined with well-known pass/fail semantics.
- **D4:** The `RouterV6Pipeline.run()` method's stage orchestration (`pipeline.py:336-493`) is the sole integration point for fence checks and ledger recording.
- **D5:** The `EscapeVia` dataclass in `escape_via_generator.py` and `CompiledRoute` in `routing_results.py` are the canonical representations of via and trace data for stages 1 and 4 respectively.
- **D6:** The shared DFM Hypothesis strategy file at `tests/router_v6/dfm_property_strategies.py` provides `realistic_paths`, `realistic_vias`, and `realistic_routing_results` strategies suitable for aggregate property testing.

## Open Questions

- **Q1 (RESOLVED):** `ViaPlacement` and `TracePlacement` shall be separate DRC primitives, NOT unified with `temper_placer/core/board.py` types. Rationale: DRC concerns are check-facing; `board.py` types are internal pipeline state. Coupling them creates circular imports between `temper_drc` and `temper_placer`.
- **Q2:** What existing `temper_drc` checks can consume `ViaPlacement`/`TracePlacement` without modification? Clearance checks may need a `geometric_entity` abstraction rather than being hard-wired to `ComponentPlacement` bounds.
- **Q3:** Should the `StageLedger` track object identity (by UUID) or only type-level counts? Identity tracking enables precise audit trails ("via `V123` lost") but requires propagating stable IDs through all stages, which may be invasive.
- **Q5:** Should Stage 1 and Stage 4 fence violations halt the pipeline (matching Stage 2-3-5 `fail_on_violation=True`) or warn-and-continue during a soft-launch period? The existing `# NOTE` comments suggest the fence was intentionally deferred, implying existing runs may produce violations that need fixing before gating.

## Alternatives Considered

- **A1: Fence-only without Via/Trace primitives (rejected).** Running the fence with only `ComponentPlacement` data would be a no-op for trace/via checks. The fence wiring is trivial; the real work is the DRC input model extension. Deferring the primitive work defers the gap.

- **A2: Cross-stage invariant assertions without a ledger (rejected during ideation).** Ad-hoc `assert len(vias_out) == len(vias_in)` at each boundary is fragile (transforms break it, different stages use different types) and provides no audit trail. The ledger's explicit transform mapping is the essential addition beyond raw counting.

- **A3: Pure mathematical proof of composition (rejected during ideation).** Formal refinement proofs (`docs/brainstorms/2026-06-28-router-v6-mathematical-rigor-ideation.md` line 172) are heavyweight and unmaintainable as first-pass rigor. Executable PBT that verifies the composition claim at test time is the pragmatic alternative: it localizes gaps to specific validators and survives refactoring.

- **A4: Merge Via/Trace primitives into existing `temper_placer/core/board.py` types (rejected).** The `board.py` domain model (`Component`, `Trace`, `Via`, `Pad`) already defines geometric primitives. However, the DRC input model lives in `temper-drc` (a separate package) and imposes a different contract (dictionary serialization, bounding box API, check-runner compatibility). Merging would create circular imports between `temper_drc` and `temper_placer`.

- **A5: Extending Stage 5 DFM checks instead of per-stage fences (rejected).** Stage 5 DFM checks operate on final output and cannot attribute violations to a specific upstream stage. Per-stage fences at Stages 1 and 4 provide precise stage attribution, enabling earlier detection and targeted fixes.
