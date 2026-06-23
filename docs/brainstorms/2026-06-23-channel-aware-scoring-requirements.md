---
date: 2026-06-23
topic: channel-aware-scoring
focus: Wire Router V6 Stage 2 channel analysis output (obstacle maps, occupancy grids, bottleneck scores from placement.channels.json) into phased_component_assignment's _place_optimize scoring so each placement iteration optimizes for routing success
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (#3)
status: active
actors: placer developer, closure test, Router V6 channel analysis, DRC fence
---

# Requirements: Channel-Aware Placement Scoring

## Problem Frame

The placer (`phased_component_assignment`) and the router (`RouterV6Pipeline`) share a board but share no feedback. Placement scores slots using only `slot_scorer` (soft constraints) plus HPWL wirelength with a 0.1 weight (`phased_component_assignment.py:447-455`). The router's Stage 2 channel analysis produces rich routing-foresight data — obstacle maps, occupancy grids, bottleneck scores — but the placer never sees it.

The 33% completion wall (`docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md`) is one consequence: 10 of 24 nets fail routing because placement picked slots that scored well on wirelength but sit in congestion cells the router later cannot navigate. The Stage 2 outputs already exist (`placement.channels.json` sidecar pattern from `docs/solutions/design-patterns/dsn-universal-seam-eda-pipelines-2026-06-22.md`) and the 8 micro-stages (`docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md`) make them addressable individually. The gap is plumbing from `placement.channels.json` into the placer's `score_slot` closure.

Today the sidecar is written and never consumed. Tomorrow it must drive placement choices.

## Actors

- **A1. Placer developer** — extends `_select_best_slot` with a routability term; tunes the weight so wirelength ranking is preserved on un-congested boards
- **A2. Closure test** — runs parse → place → route → DRC; expects `router_completion_pct` to rise from 33% to ≥90% on the 4 canonical boards
- **A3. Router V6 channel analysis** — the 8 micro-stages that already produce `obstacle_maps`, `routing_spaces`, `channel_skeletons`, `channel_widths`, `occupancy_grids`, `layer_capacities`, `routing_demand`, `bottleneck_analysis` and serialize to `placement.channels.json`
- **A4. DRC fence** — runs after placement; should now catch "component placed inside a CRITICAL bottleneck cell" as a stage-declared invariant violation

## Key Decisions

- **K1. Sidecar as the contract.** The placer reads `placement.channels.json` via a typed loader. The sidecar is the seam — channel analysis publishes, placement subscribes. No direct coupling between `phased_component_assignment.py` and `router_v6/*` modules.
- **K2. Sampled penalty, not full occupancy grid.** Placer iterates hundreds of candidate slots; a per-slot lookup into the occupancy grid (O(1) cell read) is the cheap operation. The placer does not re-run channel analysis — it consumes the snapshot.
- **K3. Additive scoring term, weighted low.** `score_slot` becomes `constraint_penalty + wirelength * 0.1 + routability_penalty * w_r`. The default `w_r` is small enough that wirelength ranking dominates on un-congested boards (no regression on existing fixtures) but large enough to flip slot choice inside a CRITICAL bottleneck cell.
- **K4. Snapshot, not live link.** The placer reads the sidecar produced by the *previous* channel-analysis run, not the current placement. This decouples dataflow: the placer does not trigger channel analysis, and channel analysis does not need to know what the placer placed. A re-run loop is a separate concern (deferred).
- **K5. Graceful degradation.** If the sidecar is missing, empty, or schema-incompatible, `score_slot` falls back to current behavior (constraint + wirelength only) with a logged warning. The placer must not break for callers that do not run channel analysis first.

## Requirements

### R1. Channel Sidecar Loader

Status: required

Add `ChannelMap.load_from_sidecar(path: Path) -> ChannelMap` in `packages/temper-placer/src/temper_placer/deterministic/channels.py` (new module) that:

- Reads `placement.channels.json` matching the schema from `dsn-universal-seam-eda-pipelines-2026-06-22.md` (occupancy grid cells, layer capacity map, bottleneck list with severity CRITICAL/HIGH/MEDIUM/LOW)
- Returns a frozen dataclass `ChannelMap(grid: tuple[tuple[int, ...], ...], cell_size_um: int, bottlenecks: tuple[Bottleneck, ...])` where `Bottleneck` is a typed record `(x: int, y: int, layer: int, severity: str, score: float)`
- Raises `ChannelSidecarError` (typed, not generic) on schema mismatch, missing required fields, or unknown severity values
- Validates the sidecar's `temper_schema_hash` header against the placer's supported set (same pattern as the DSN reader); unknown hash → `ChannelSidecarError`

### R2. Routability Penalty Function

Status: required

Add `routability_penalty(slot: Tuple[float, float], channel_map: ChannelMap) -> float` in `channels.py`:

- Converts `slot` (mm) to grid coordinates using `channel_map.cell_size_um`
- Looks up the cell; reads occupancy (0.0 = free, 1.0 = fully blocked) and bottleneck severity
- Returns a score in `[0.0, 1.0]` where 0.0 means the slot is in free, un-bottlenecked space and 1.0 means the slot is in a CRITICAL bottleneck cell on a fully free layer. A fully blocked layer (occupancy=1.0) is unreachable from the placer's perspective and yields 0.0 — the penalty reflects "where the router still has room to work," not raw occupancy.
- Mapping: `severity ∈ {LOW: 0.05, MEDIUM: 0.15, HIGH: 0.4, CRITICAL: 1.0}`, multiplied by `(1.0 - occupancy)`
- A slot outside the grid bounds returns `0.0` (do not penalize slots that simply do not overlap the channel map) — this is the path by which boards without a sidecar degrade gracefully when `ChannelMap.empty()` is passed

### R3. Wire into `_select_best_slot`

Status: required

Modify `phased_component_assignment.py:447-455`:

- Constructor accepts optional `channel_map: ChannelMap | None = None` and `w_r: float = 0.05` parameters (default `None` preserves current behavior for callers that do not produce a sidecar). `w_r=0.0` is equivalent to no-sidecar behavior.
- `score_slot` adds the new term: `constraint_penalty + wirelength * 0.1 + routability_penalty(slot, self.channel_map) * w_r`
- Default `w_r = 0.05` — chosen so a MEDIUM bottleneck (penalty 0.15) adds 0.0075 to the score, comparable to a 0.075mm wirelength penalty; HIGH (0.4) adds 0.02, comparable to 0.2mm; CRITICAL (1.0) adds 0.05, comparable to 0.5mm
- The existing `_simple_greedy_placement` fallback and `_place_optimize` primary path both use the same `score_slot` — both get routability awareness for free
- A `WARNING` is logged at construction if `channel_map is None` so callers can see the sidecar was not supplied.

### R4. Closure Test Plumbing

Status: required

- **R4a.** `packages/temper-placer/src/temper_placer/deterministic/__init__.py:67-127` (pipeline orchestration) detects when a `placement.channels.json` is present in the run output directory and constructs `ChannelMap` from it before instantiating `PhasedComponentAssignmentStage`
- **R4b.** Channel analysis is invoked before placement in the closure test path: closure test currently runs parse → place → route → DRC. The new order is parse → **channel analysis** → place (with sidecar) → route → DRC. Channel analysis here is a *re-parse* of the empty board for routing foresight; placement is not yet done so the channel map is "pre-placement" routing capacity
- **R4c.** The sidecar is read once per pipeline run; the same `ChannelMap` instance is shared across all component placement iterations (cache the object, do not re-read the file)
- **R4d.** If channel analysis is unavailable (e.g., Router V6 not importable in the closure test environment), the closure test logs a `WARNING` and falls back to current placement (R5 graceful degradation). It does not hard-fail the closure test on this dependency

### R5. Graceful Degradation

Status: required

- Missing file: `ChannelMap.empty()` is constructed; `routability_penalty` always returns 0.0; `score_slot` reduces to current behavior
- Malformed file: `ChannelSidecarError` is caught at the pipeline boundary; logged with the path and a clear message; `ChannelMap.empty()` is used
- Unknown schema hash: same as malformed
- Channel analysis failed mid-pipeline: sidecar absent; falls back as in the missing-file case
- All degradation paths produce the same placement quality as today (no regression on boards where channel analysis was never run); the warning surfaces the under-instrumented case

### R6. DRC Fence Integration

Status: required

- `PhasedComponentAssignmentStage` declares a new invariant in its `invariants` property (per `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`): `"no_component_in_critical_bottleneck"` — no placed component center may fall inside a CRITICAL-severity bottleneck cell from `channel_map`. Check samples at component center AND at each footprint corner (or axis-aligned bounding-box extremes) of the placed component; a violation in any sampled point is a violation. If multi-cell sampling is deferred, R6 must state that explicitly: the invariant guards center-only placement, not footprint extent, and this limitation is documented in the invariant name (e.g., `no_component_center_in_critical_bottleneck`).
- The fence runs this check after the placement stage completes; violation report names the component ref, bottleneck coordinates, and severity
- Violations are warnings during a 2-week soft-launch, then become fence failures (consistent with the per-stage DRC fence soft-launch policy)
- When `channel_map is None` (graceful degradation path), this invariant is *not declared* — no false positives when the sidecar is absent

### R7. Parity Test: Sidecar On vs Off

Status: required

- **R7a.** `test_channel_scoring_parity.py` runs the closure test on each of the 4 canonical boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra) twice: once with `channel_map=None` (current behavior) and once with the sidecar loaded
- **R7b.** Assertions: (1) every board that currently routes 100% of nets continues to route 100% with the sidecar loaded; (2) every board that currently fails nets (the 33% case) shows a non-decreasing completion rate; (3) wirelength changes by < 2% on boards that already route 100% (proves K3's weight choice)
- **R7c.** The parity test gates landing — a board that currently passes routing but regresses with the sidecar loaded fails CI with `"regression: board X completion dropped from 100% to Y% with sidecar"`
- **R7d.** A monotonicity assertion: across 5 random seeds (0, 1, 2, 3, 4) on each canonical board, the sidecar-on path's mean `router_completion_pct` is ≥ the sidecar-off path's mean
- **R7e.** Read-counter test: instrument the sidecar loader with a monotonic counter; assert it is incremented exactly once per `PhasedComponentAssignmentStage` invocation across the 4 canonical boards, regardless of component count.

### R8. Property-Based Tests for the Penalty Function

Status: required

`test_channel_penalty_pbt.py` with `hypothesis`:

- **R8a.** For any `ChannelMap` and any slot inside the grid, `0.0 ≤ routability_penalty(slot, cm) ≤ 1.0`
- **R8b.** A slot in a fully-free cell on a non-bottlenecked layer returns 0.0
- **R8c.** A slot at a CRITICAL bottleneck cell with occupancy 0.0 returns 1.0
- **R8d.** Penalty is monotonic with severity: `LOW ≤ MEDIUM ≤ HIGH ≤ CRITICAL` for the same occupancy
- **R8e.** Penalty is monotonic with occupancy: for a fixed severity, higher occupancy → higher penalty
- **R8f.** A slot outside the grid bounds returns 0.0 (out-of-bounds is not penalized — boards can extend past the analyzed region)

### R9. Performance Budget

Status: required

- `routability_penalty` must execute in ≤ 5 microseconds per call on the 4 canonical boards (grid lookups, no allocations in the hot path)
- The full closure test must complete in ≤ 110% of its current wall-clock time (≤ 10% overhead from sidecar loading + per-slot penalty). Measured via the existing closure-test timing metrics.
- If the budget is exceeded, the implementation may cache the `ChannelMap`'s grid as a flat numpy array or pre-compute per-cell penalty scores — but the public API (`routability_penalty(slot, channel_map) -> float`) is unchanged

## Scope Boundaries

### Deferred for later

- **Re-running channel analysis after placement.** The current sidecar is pre-placement routing foresight. A feedback loop that re-runs channel analysis with placed components and re-places the worst-offending components is a separate initiative (requires a `placement.channels.json` writer in the placer too, plus a re-entry contract for the placement stage)
- **Differentiated weights per net class.** HV nets (per `NetClassRules.safety_category`) get a higher `w_r` because their routing failure is a safety issue, not just a completion-rate issue. The current implementation uses a single global `w_r`; per-class weights are future work
- **Channel-aware seed filtering.** This initiative adds scoring; it does not change the seed-generation path in `_place_optimize`. Combining channel analysis with seed filtering (ideation #4) is a separate initiative that can layer on top
- **Sidecar freshness checks.** The placer trusts whatever `placement.channels.json` exists. A mtime check (refuse sidecars older than the source PCB) is deferred

### Outside this product's identity

- **Changing the channel analysis algorithm.** This initiative consumes what the 8 micro-stages produce. It does not modify `obstacle_map.py`, `occupancy_grid.py`, `bottleneck_analysis.py`, etc.
- **Replacing HPWL with channel-aware wirelength.** The wirelength term remains HPWL-based. A congestion-weighted wirelength metric is a future enhancement
- **Modifying the DRC check implementations.** R6 adds a new invariant declaration to the placement stage; it does not change `temper_drc` checks
- **Re-architecting the pipeline.** The pipeline orchestration in `__init__.py:67-127` gets a single new step (load sidecar); the overall stage order is unchanged. A feedback loop that re-runs channel analysis is deferred

## Success Criteria

- **SC1.** Closure test `router_completion_pct` on the 4 canonical boards is ≥ 90% (up from 33%) with the sidecar loaded (R7 parity test)
- **SC2.** Boards that currently route 100% of nets continue to route 100% with the sidecar loaded; wirelength changes by < 2% (R7b)
- **SC3.** PBT suite (R8) runs ≥ 100 examples per property and catches a deliberately introduced violation (e.g., penalty > 1.0)
- **SC4.** DRC fence (R6) catches a component deliberately placed at a CRITICAL bottleneck cell with a named violation report
- **SC5.** `routability_penalty` executes in ≤ 5 microseconds per call; closure test completes in ≤ 110% of current wall-clock (R9)
- **SC6.** Graceful degradation (R5): removing the sidecar file restores current placement behavior; no test that currently passes starts failing
- **SC7.** The sidecar is read once per pipeline run, not once per component (R4c — verified by a counter test)

## Dependencies

- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py:447-455` — `score_slot` closure (modified by R3)
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` — `PhasedComponentAssignmentStage` constructor (gains `channel_map` param)
- `packages/temper-placer/src/temper_placer/deterministic/__init__.py:67-127` — pipeline orchestration (loads sidecar per R4a)
- `packages/temper-placer/src/temper_placer/router_v6/stage0_data.py` — `DesignRules`, `NetClassRules` (referenced for future per-class weight work, not modified now)
- `packages/temper-placer/src/temper_placer/router_v6/{obstacle_map, occupancy_grid, bottleneck_analysis, ...}.py` — the 8 micro-stages (consumed via sidecar, not modified)
- `placement.channels.json` — sidecar file produced by the 8 micro-stages, schema documented in `docs/solutions/design-patterns/dsn-universal-seam-eda-pipelines-2026-06-22.md`
- `docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md` — micro-stage pattern this initiative builds on
- `docs/solutions/design-patterns/per-stage-drc-fence-verification-2026-06-22.md` — DRC fence pattern referenced by R6
- `docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md` — ideation source (Idea #3)

## Assumptions

1. **The sidecar is produced before placement in the closure test pipeline.** The closure test currently runs parse → place → route → DRC. R4b adds channel analysis between parse and place. The channel analysis is a *re-parse* of the empty board — it does not depend on placement output. Verified by reading `RouterV6Pipeline._run_stage2` inputs (`pipeline.py:241-326`): obstacle map and occupancy grid depend on `pcb` and `escape_vias`, not on placement
2. **The 4 canonical boards have `placement.channels.json` generated without errors.** Sanity check during planning: run channel analysis on each of the 4 boards standalone and confirm a valid sidecar is produced
3. **Grid lookups in `routability_penalty` are O(1).** The grid is stored as a 2D tuple-of-tuples or flat array; coordinate conversion is integer arithmetic. No tree lookups, no graph traversals
4. **The 0.05 default weight (`w_r`) does not require per-board tuning.** Verified by the R7 parity test: 100%-routing boards must remain at 100% with the sidecar loaded. If the test fails, the default weight is tuned globally, not per-board
5. **Per-stage DRC fence is deployed.** R6 depends on the fence infrastructure from `per-stage-drc-fence-verification-2026-06-22.md`. If the fence is not yet in production, R6 is a no-op (the invariant declaration is added but not enforced)
6. **The closure test can import Router V6 channel analysis.** If Router V6 is not importable in the closure test environment, R4d's fallback applies and this initiative contributes zero placement improvement on that run

## Open Questions

### Resolve Before Planning

- **[Affects R1][Technical]** What is the exact field set in `placement.channels.json`? Read the sidecar writer in `temper_placer/router_v6/serialization/` (or wherever the sidecar is emitted) to confirm the field names match R1's spec. If the writer uses different field names, R1 must adapt or the writer must be updated to match
- **[Affects R2][Technical]** What grid resolution does the sidecar use? The cell size in mm determines the penalty granularity. If cells are 0.5mm and a component footprint is 2mm, a single slot lookup samples at the slot's center only — a 1mm misplacement could be in a different cell. Confirm whether multi-cell sampling (4 corners + center) is needed for footprint-size components
- **[Affects R3][Tuning]** Is `w_r = 0.05` the right default? The R7 parity test is the gate; if it fails, the weight needs tuning. The CRITICAL case (penalty 1.0 × 0.05 = 0.05) is the dominant flip case — verify empirically that this flips slot choice in CRITICAL cells while leaving wirelength ranking intact in un-congested regions

### Deferred to Planning

- **[Affects R4b][Pipeline]** Where exactly does channel analysis slot into the closure test sequence? Confirm by reading `packages/temper-placer/src/temper_placer/regression/closure_test.py` and the deterministic pipeline `__init__.py`. The channel analysis step may be a call to `RouterV6Pipeline._run_stage2` (or its orchestrator) with the parse output, before placement
- **[Affects R6][Process]** When does the DRC fence soft-launch end? The per-stage DRC fence initiative defines a 2-week WARNING-only period before hard-blocking. This initiative inherits that timeline — confirm the dates and align the soft-launch
- **[Affects R9][Performance]** What is the current closure test wall-clock time? The 10% overhead budget (R9) is relative; if the current time is 30 seconds, the new budget is 33 seconds. Confirm the baseline before planning the perf test
- **[Affects R7d][Statistical]** Is "≥ mean across 5 seeds" a strong enough monotonicity assertion? For boards with high variance, a Welch's t-test or a rank-based test (Wilcoxon) may be more appropriate. Decide during planning based on observed variance on the 4 canonical boards
