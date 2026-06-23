---
date: 2026-06-23
topic: seed-filtering-by-channel-bottleneck-map
focus: Pre-filter placement seed candidates by sampling the bottleneck map at component positions to compound routing-completion gains over retries
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (#4)
status: active
actors: Placement optimizer developer, CI system, closure test pipeline, retry loop
---

# Requirements: Seed Filtering by Channel Bottleneck Map

## Problem Frame

The deterministic placer's seed-and-restart loop (`phased_component_assignment.py:88-180`) tries multiple initial seed positions, optimizes from each, and keeps the lowest-HPWL result. Today seed candidates are picked without any knowledge of where routing will be hard. Of 24 nets in the temper board, only 8 route successfully (33% completion wall) because 10 nets are blocked by HV creepage pockets that the placer has no way to see when choosing its starting points.

Stage 2 of the pipeline already produces a per-cell bottleneck score from the micro-stage decomposition (`bottleneck_analysis.py`), and the DAG engine's `routability-retry` feedback contract (`declarative-stage-dag-replaces-orchestrator-2026-06-22.md`) rewinds to the placement stage when `routing_completion < 0.5`. The retry loop is the right place to filter, but the loop currently re-seeds in the dark.

A pre-filter that samples the bottleneck map at each candidate seed's component positions and discards seeds whose components land in high-congestion cells costs O(1) per seed check, requires no new infrastructure, and compounds with each retry: the more often the feedback contract retriggers, the more bad seeds get filtered. Expected code: ~30 lines.

## Actors

- **A1. Placement optimizer developer** — implements and tunes the seed filter, runs closure tests to confirm routing-completion improvement without HPWL regression
- **A2. CI system** — runs new unit tests for the filter function and property-based tests for the seed-sampling invariant; runs the existing closure test to confirm no behavioral regression
- **A3. DAG feedback loop** — invokes the placer's `seed-and-restart` entry point on each retrigger; benefits automatically from filtered seeds without code changes
- **A4. Closure test pipeline** — measures end-to-end `routing_completion_pct`, `drc_errors`, and HPWL on the temper board and any canonical fixtures; success criteria reference these metrics

## Key Decisions

- **K1. Filter is a pure function on a seed candidate and the bottleneck map.** Signature: `filter_seed(seed: SeedCandidate, bottleneck_map: BottleneckMap, threshold: float) -> bool`. No I/O, no mutation, no global state. Trivially testable.
- **K2. O(1) per seed check via component-position sampling.** Each seed is a dict of `ref -> (x, y)`. Sampling looks up the bottleneck score at each `(x, y)` and rejects if any HV-creepage or capacity-starved component lands in a cell above threshold. Cost is bounded by the number of seed components, not by the map size.
- **K3. Threshold is configurable, not hardcoded.** A `seed_filter_threshold` config key (default: 0.7 of the cell capacity score) lets A1 tune strictness per board. Profiler can also expose a dynamic-strictness hook in a follow-up, but it is out of scope for this requirements document.
- **K4. Filter integrates at the seed-generation boundary, not the optimization loop.** Pre-filter runs after seeds are generated and before the HPWL optimization step. This keeps the optimization kernel unchanged and the filter swappable.
- **K5. No change to the DAG feedback contract.** The filter lives inside the placer; the DAG engine's `routability-retry` contract continues to operate on `routing_completion` as before. The compounding effect is automatic: more retriggers = more filtered seeds considered.

## Requirements

### R1. Seed Filter Function

Status: required

A pure function `filter_seed` takes a seed candidate and the bottleneck map and returns `True` if the seed is acceptable (all components land in acceptable cells), `False` otherwise.

- Input: `seed: dict[str, tuple[float, float]]` (ref → mm position), `bottleneck_map: BottleneckMap` (per-cell congestion score grid), `threshold: float`
- Output: `bool` (accept/reject)
- Sampling: for each `(ref, (x, y))` in the seed, look up the bottleneck map cell containing `(x, y)`; reject the seed if any component lands in a cell with score `>= threshold`
- Bottleneck map lookup must be O(1) (cell-indexed, not linear scan)
- All HV-class components (per `NetClassRules.safety_category`) must pass a stricter `hv_threshold` (default 0.5) because their exclusion zones compound

### R2. Integration into Seed Generation

Status: required

Modify `_phased_placement` (`phased_component_assignment.py:<verified-line-range>, see Dependencies for the same function) so the seed candidate pool is filtered through R1 before optimization begins.

- The function generates a candidate pool (current behavior: random seeds within board bounds)
- After generation, apply `filter_seed` to each candidate with the loaded `bottleneck_map` and `seed_filter_threshold`
- Discarded candidates are not optimized against — saves HPWL optimization cycles
- Surviving candidates proceed to `_place_optimize` / `_place_proximity` / `_place_template` unchanged
- If filtering discards all candidates (over-aggressive threshold), fall back to unfiltered seeds with a logged warning, not a hard error

### R3. Bottleneck Map Loading

Status: required

The placer loads the bottleneck map from the same source Stage 2 micro-stage #5 (`bottleneck_analysis.py`) writes to.

- Read path: `placement.channels.json` sidecar (existing) or `BoardState.bottleneck_analysis` field, whichever the placer's state container already exposes
- If neither is present (e.g., a board without Stage 2 channel analysis), disable filtering silently — the placer must work on boards without bottleneck data
- Type the loaded value as a frozen dataclass `BottleneckMap` with cell-indexed access; do not pass raw dicts through the placer

### R4. Configuration Knobs

Status: required

Two new config keys on the placement config:

- `placement.seed_filter_enabled: bool = True` — master switch, allows A1 to A/B test filtered vs. unfiltered on the same board
- `placement.seed_filter_threshold: float = 0.7` — congestion score above which a cell is "bad" for any component
- `placement.seed_filter_hv_threshold: float = 0.5` — stricter threshold applied to HV-class components
- Defaults are conservative: low threshold (0.7) means mild filtering, doesn't break boards whose bottleneck map is sparse

### R5. Unit and Property Tests

Status: required

- **R5a.** Unit test: `filter_seed` accepts a seed where all components land in low-congestion cells (mock `BottleneckMap` with known scores)
- **R5b.** Unit test: `filter_seed` rejects a seed with one component in a high-congestion cell
- **R5c.** Unit test: HV-class component triggers rejection at a lower cell score than LV components (verifies R1's stricter HV threshold)
- **R5d.** Property test (Hypothesis, `max_examples=50`): for any seed, `filter_seed` is deterministic — calling twice with the same inputs returns the same result; calling on disjoint maps does not cross-contaminate
- **R5e.** Integration test: `_phased_placement` with `seed_filter_enabled=True` produces the same placements as the unfiltered path on a board with no bottleneck map (fallback path)
- **R5f.** Integration test: `_phased_placement` with `seed_filter_enabled=True` on the temper board shows `routing_completion_pct` increase ≥ 10 percentage points vs. unfiltered baseline

### R6. Observability Hooks

Status: required

Emit at log level INFO one JSON line per placement run with these keys: `event="seed_filter"`, `candidates_total`, `candidates_accepted`, `candidates_rejected`, `avg_bottleneck_score_accepted` (float), `threshold`, `hv_threshold`, `fallback_used` (bool, true when R2's empty-pool path fires).

### R7. Multi-retrigger compounding test

Status: required

An integration test simulates the DAG feedback loop by running the placer N=3 times, feeding the previous run's `routing_completion` and a recomputed bottleneck map into each subsequent call. Assert: (a) the fraction of seeds rejected by R1 is non-decreasing across the 3 runs, and (b) final `routing_completion_pct` >= the SC1 single-pass result.

## Out of Scope

- **Dynamic threshold adjustment during a single placement run.** K3 leaves the door open but R1 keeps threshold constant per call. A follow-up could feed the profiler's rolling completion metric back into the threshold, but that is a separate requirements document.
- **Modifying the DAG feedback contract.** The `routability-retry` contract stays unchanged — the filter is a transparent improvement to the placer it already retriggers.
- **Building the bottleneck map.** The map is produced by `BottleneckAnalysisStage`; this document only consumes it. Changes to bottleneck-map quality or coverage are a separate concern.
- **Per-zone filtering or zone-aware thresholding.** Today the threshold is uniform across the board. A future variant could lower the threshold near power components to allow more routing slack there, but R1 keeps it simple.
- **Spatial precomputation (KD-tree, quadtree).** O(1) cell-indexed lookup is fast enough on the bottleneck map's grid resolution; spatial indexing is a premature optimization.

## Success Criteria

- **SC1.** `routing_completion_pct` on the temper board improves by >= 10 percentage points vs. a 10-run unfiltered baseline on `main` (mean, stddev recorded in `docs/solutions/measurements/seed-filter-baseline.md` before this feature enters planning). If baseline stddev > 5pp, SC1 is reframed as a one-sided t-test with effect-size lower bound, not a fixed delta.
- **SC2.** HPWL on the temper board does not regress by more than 5% vs. the unfiltered baseline
- **SC3.** Filter is O(1) per seed: a profiler measurement shows seed-filter wall time is < 1% of total placement wall time on the temper board
- **SC4.** All 5 unit and property tests (R5a-R5e) pass in CI; integration test (R5f) shows the documented completion gain
- **SC5.** Placer continues to produce valid placements (passes `PlacementValidationStage`) on the 4 canonical test boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra) with `seed_filter_enabled=True`, AND each test setup asserts a non-empty `BottleneckMap` for that board; boards lacking a map are split into a separate test group exercising the R3 silent-disable fallback.
- **SC6.** Closure test (A4) reports no new DRC errors introduced by filtered placements on the temper board

## Dependencies

- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py:88-180` — seed/restart logic the filter integrates into
- `packages/temper-placer/src/temper_placer/deterministic/states.py` or `state.py` — `BoardState` container; must expose `bottleneck_analysis` (or equivalent) for R3
- `packages/temper-placer/src/temper_placer/router_v6/bottleneck_analysis.py` — `BottleneckAnalysisStage` output; source of the bottleneck map
- `packages/temper-placer/src/temper_placer/pipeline/dag_engine.py:316-374` — feedback contract `routability-retry`; unchanged but retriggers the filter
- `packages/temper-placer/src/temper_placer/io/config_loader.py` — placement config schema; add `seed_filter_enabled`, `seed_filter_threshold`, `seed_filter_hv_threshold` keys
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` — feedback-contract pattern; reference for the retry behavior the filter compounds with
- `docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md` — bottleneck-map production (Stage 2 micro-stage #5)
- `docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md` — origin ideation; 33% completion wall context

## Assumptions

1. **The bottleneck map is cell-indexed for O(1) lookup.** Verified by reading `bottleneck_analysis.py` output shape (per-cell score grid). If the map is sparse or quadtree-shaped, R1's lookup needs a one-line adjustment.
2. **`BoardState` either carries `bottleneck_analysis` or the placer can load the `placement.channels.json` sidecar.** Assumption based on the ideation doc's note that the sidecar already exists. If neither is true, R3 needs to be expanded.
3. **HV components can be identified from the netlist via `NetClassRules.safety_category`.** Past learning confirms this is SSOT for HV/LV classification. R1's stricter HV threshold relies on this classification being available at seed-filter time.
4. **Seed candidates are generated with known component positions, not incremental.** The placer knows where each component will go in a given seed before optimization runs, so sampling is well-defined. Verified by reading `_phased_placement` flow.
5. **The 4 canonical test boards have bottleneck maps.** Closure test parity (SC5) assumes Stage 2 channel analysis runs on these boards. If any lacks bottleneck data, R3's silent-disable fallback covers it.
6. **`hypothesis` is already a test dependency.** Same assumption as the stage-decomposition brainstorm; if not present, add to `pyproject.toml` test extras.

## Open Questions

### Resolve Before Planning

- **[Affects R3][Technical]** Where does the placer load the bottleneck map from in production today? `BoardState.bottleneck_analysis` populated by the deterministic pipeline, or `placement.channels.json` written by Router V6? The deterministic pipeline currently does not run Router V6's Stage 2; verify the data path.
- **[Affects R1][Technical]** What is the exact bottleneck-map cell resolution on the temper board? Affects whether `(x, y)` → cell index is a floor or round operation, and what floating-point precision is required.
- **[Affects R4][Process]** Should `seed_filter_enabled` default to `True` or `False`? `True` commits the project to the filter as the new normal; `False` keeps it as an opt-in improvement. Recommendation: `True` with the 0.7 threshold, since the fallback to unfiltered on missing-map boards prevents breakage.
- **[Affects R5f][Process]** Where does the "10 percentage points" baseline for SC1 come from? A prior run, a back-of-envelope estimate, or a theoretical bound? Need a concrete baseline measurement (unfiltered closure test on the current `main` branch) before claiming SC1.

### Deferred to Planning

- **[Affects SC3][Needs research]** Can the existing profiler (`ProfilingContext`) emit per-stage wall time, or does R6's observability hook need a separate timer? Determine the lightest logging path during planning.
- **[Affects R5d][Needs research]** What Hypothesis strategy generates valid `(x, y)` positions inside a board's bounds? May need a `@composite` strategy that picks refs from a known netlist and samples positions in `board.outline`.
- **[Affects R6][Design]** Should the observability log line be structured JSON, a `logging.info` formatted string, or a metric emitted to a sidecar? Match the project's existing observability conventions.
- **[Affects R3][Technical]** Does the deterministic pipeline's `DeterministicPipeline.run()` populate `bottleneck_analysis` on `BoardState`, or is that a Router V6-only field? If Router V6-only, the placer's loader path needs a fallback to the sidecar JSON.
