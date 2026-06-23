---
<<<<<<< HEAD
title: "feat: Seed Filtering by Channel Bottleneck Map"
type: feat
status: active
date: 2026-06-23
origin: docs/brainstorms/2026-06-23-seed-filtering-requirements.md
---

# feat: Seed Filtering by Channel Bottleneck Map

## Problem Frame

The deterministic placer's seed-and-restart loop (in `phased_component_assignment.py:115-180`) tries multiple initial seed positions, optimizes from each, and keeps the lowest-HPWL result. Today seeds are picked blind to where routing will be hard; on the temper board only 8/24 nets route (33% completion wall) because 10 nets are blocked by HV-creepage pockets the placer cannot see when choosing seeds. Stage 2 micro-stage #5 (`bottleneck_analysis.py`) already produces a per-cell congestion score grid, and the DAG `routability-retry` contract re-invokes the placer each retrigger — but every retrigger re-seeds in the dark. A pre-filter that samples the bottleneck map at each candidate seed's component positions and discards seeds whose components land in high-congestion cells is O(1) per check, requires no new infrastructure, and compounds with each retry.

## Implementation Units

### Step 0. R-D1 Pre-Implementation Spike (blocking gate before U1)

**Goal:** Confirm that `BottleneckMap` data is actually reachable from the deterministic placer's `BoardState` on the canonical temper board fixture **before** U1 lands. This is a binary go/no-go spike, not a feature. If no-go, the whole plan is blocked: U1's loader would degrade to "always None", U4's filter would silently disable, and SC1 (routing completion gain) would be unmeasurable. Better to discover that in 30 minutes of grep than 3 days of unit tests.

**Why a separate pre-step, not "resolve during U1":** R-D1 was originally listed as a U1 sub-task, but its answer is a precondition for U1's correctness, not an in-flight detail. A U1 that starts without a confirmed data path risks landing a loader that *technically works* (returns `None` cleanly) but is *practically dead code* (no production board ever populates `BoardState.bottleneck_analysis` and no sidecar exists). Promoting R-D1 to a pre-step forces the answer to be visible in the PR's commit history.

**Files inspected (read-only, no edits):**
- `packages/temper-placer/src/temper_placer/deterministic/state.py` (lines 28-90: `BoardState` definition and `bottleneck_analysis` field)
- `packages/temper-placer/src/temper_placer/router_v6/bottleneck_analysis.py` (the producer stage)
- `packages/temper-placer/src/temper_placer/deterministic/pipeline.py` (the deterministic runner that would populate the field)
- The temper board fixture loader (search for the fixture path used in `tests/integration/test_closure_canonical_boards.py`)

**Spike procedure (run on a clean `main` checkout, in this order):**

1. `rg -n 'bottleneck_analysis' packages/temper-placer/src/temper_placer/deterministic/` — confirm at least one read site in the deterministic pipeline path (U1's loader is useless if the producer is Router V6-only and the deterministic pipeline never invokes Router V6).
2. Run the sidecar loader (U1's fallback path) against the temper board fixture end-to-end: instantiate the fixture's `BoardState`, call `load_bottleneck_map(state, sidecar_path=None)`, and check whether a populated `placement.channels.json` sidecar exists on disk for the fixture. If neither the in-state field nor a sidecar is populated, the loader returns `None` and the plan is blocked.
3. Print a one-line go/no-go summary:
   - `GO: bottleneck_analysis field present on BoardState AND sidecar populated for temper fixture`
   - `NO-GO: <which of (field, sidecar) is missing>; filter will silently disable on this board; SC1 unmeasurable`

**Outcomes:**

- **GO** → proceed to U1 as planned. Record the spike's output in the U1 PR description.
- **NO-GO** → **block U1**. Open a follow-up issue titled `Wire BottleneckAnalysisStage output into BoardState` with the spike's no-go message and link it as a discovered-from dependency. The choice is then between (a) extending this plan's scope to include the population step (re-plan U0 → U0.5 with an additional unit to wire `BottleneckAnalysisStage` into the deterministic pipeline's `BoardState` population), or (b) deferring the entire seed-filtering plan until the population step lands. Either choice requires an explicit amendment to this plan; do not silently proceed.

**Verification (this pre-step):** a single shell transcript (`scripts/spikes/rd1_bottleneck_data_path.sh`) committed to the PR with the one-line go/no-go output. CI does not need a gate; the human reviewer reads the transcript and the U1 PR description references it.

### U1. BottleneckMap Datatype and Loader

**Goal:** Define a frozen `BottleneckMap` dataclass with O(1) cell-indexed lookup and a loader that prefers `BoardState.bottleneck_analysis` and falls back to the `placement.channels.json` sidecar, returning `None` on miss.

**Requirements:** R3.

**Files:**
- `packages/temper-placer/src/temper_placer/deterministic/bottleneck_map.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/state.py` (extend `BoardState`)
- `packages/temper-placer/src/temper_placer/io/config_loader.py` (register sidecar path)

**Approach:** Frozen dataclass `BottleneckMap(cell_size_mm, width, height, origin_xy, scores: jax.Array)` with `score_at(x, y) -> float` that floors `(x - origin_x) / cell_size_mm` and returns the indexed score (clamp out-of-bounds to 0.0). `load_bottleneck_map(board_state, sidecar_path) -> BottleneckMap | None` reads from `board_state.bottleneck_analysis` first, then the sidecar, returning `None` if neither is present. The loader never raises on miss; downstream caller decides what `None` means.

**Test scenarios:**
- `test_score_at_cell_origin`: input cell at (0, 0) with score 0.9; action `score_at(0.0, 0.0)`; expect 0.9.
- `test_score_at_floor_rounding`: input 5mm cell, score 0.4 at column 1; action `score_at(7.0, 0.0)`; expect 0.4 (floors to col 1).
- `test_score_out_of_bounds_returns_zero`: input 10x10 grid; action `score_at(999.0, 999.0)`; expect 0.0.
- `test_load_prefers_board_state_attribute`: `BoardState(bottleneck_analysis=map_a)` + sidecar containing `map_b`; action `load_bottleneck_map(...)`; expect `map_a`.
- `test_load_falls_back_to_sidecar`: state without attribute + sidecar present; expect sidecar map.
- `test_load_returns_none_on_miss`: state without attribute + no sidecar; expect `None`, no exception.

**Verification:** `uv run pytest packages/temper-placer/tests/deterministic/test_bottleneck_map.py -v`; run `uv run python scripts/import_linter_gate.py` (boundary check covers new module).

### U2. `filter_seed` Pure Function

**Goal:** Implement the pure accept/reject function over a seed candidate and a `BottleneckMap`, applying the stricter HV threshold to HV-class components.

**Requirements:** R1, K1, K2.

**Files:**
- `packages/temper-placer/src/temper_placer/deterministic/seed_filter.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/rules/types.py` (consume `NetClassRules.safety_category`)

**Approach:** Module-level function `filter_seed(seed: dict[str, tuple[float, float]], bottleneck_map: BottleneckMap, threshold: float, hv_threshold: float, hv_refs: frozenset[str]) -> bool`. Iterate `seed.items()`; for each `(ref, (x, y))` look up `bottleneck_map.score_at(x, y)`; reject when score `>= threshold` for LV refs or `>= hv_threshold` for refs in `hv_refs`. The function has no I/O, no mutation, and no global state; `hv_refs` is computed once at call-site from `NetClassRules.safety_category` so the function stays pure.

**Test scenarios:**
- `test_accepts_all_low_congestion`: seed `{R1: (1, 1), R2: (2, 2)}` on a map with all scores 0.1, thresholds (0.7, 0.5); expect `True`.
- `test_rejects_one_high_congestion_lv`: seed with `R2` in a 0.8 cell; thresholds (0.7, 0.5); expect `False`.
- `test_hv_triggers_lower_threshold`: HV ref in 0.6 cell; thresholds (0.7, 0.5); expect `False` (0.6 >= 0.5).
- `test_lv_tolerates_hv_threshold`: LV ref in 0.6 cell; thresholds (0.7, 0.5); expect `True` (0.6 < 0.7).
- `test_determinism_property`: Hypothesis property test with `--hypothesis-max-examples=50` and these inline strategies (so the test is self-describing and the seed/maps are bounded to a realistic domain):
  - `seed = st.dictionaries(keys=st.text(min_size=1, max_size=4), values=st.tuples(st.floats(-50, 50, allow_nan=False), st.floats(-50, 50, allow_nan=False)), min_size=1, max_size=10)`
  - `bottleneck_map = st.builds(BottleneckMap, cell_size=st.floats(0.5, 10), width=st.integers(2, 32), height=st.integers(2, 32), origin=st.tuples(st.floats(-20, 20), st.floats(-20, 20)), scores=st.lists(st.floats(0, 1), min_size=4, max_size=1024))`
  - The strategy **must** include in the 50 examples at least one seed coordinate landing exactly on a cell boundary (i.e. `(x - origin_x) % cell_size == 0` for the chosen `cell_size`) and at least one seed coordinate with a negative component (to exercise `score_at` clamp + floor behavior at the map origin). Add an explicit `st.sampled(...)` mixin or `assume(...)` filter to enforce both conditions; reject (do not error) otherwise. Calling `filter_seed` twice with identical inputs returns identical result; calling on disjoint `BottleneckMap` instances does not mutate either.
- `test_disjoint_maps_no_cross_contamination`: two `BottleneckMap` instances; filtering on map A and then map B does not mutate either.

**Verification:** `uv run pytest packages/temper-placer/tests/deterministic/test_seed_filter.py -v` with `--hypothesis-max-examples=50`; CI gate asserts the property test logs at least one cell-boundary coordinate and at least one negative coordinate across the 50 examples (a small wrapper script reads the property-test event log and fails the gate otherwise).

### U3. Placement Configuration Knobs

**Goal:** Add the three `placement.seed_filter_*` config keys to the loader and a typed config object on the placement stage.

**Requirements:** R4.

**Files:**
- `packages/temper-placer/src/temper_placer/io/config_loader.py` (add fields)
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (consume config in `__init__`)

**Approach:** Extend the placement config schema with `seed_filter_enabled: bool = True`, `seed_filter_threshold: float = 0.7`, `seed_filter_hv_threshold: float = 0.5`. `PhasedComponentAssignmentStage.__init__` accepts a `seed_filter` dataclass (or `None` to disable). Defaults match brainstorm K3.

**Test scenarios:**
- `test_config_defaults_present`: load fixture config without `placement.*` keys; expect defaults (True, 0.7, 0.5).
- `test_config_override_respected`: load config with `seed_filter_enabled=False`; expect stage receives disabled filter.
- `test_invalid_threshold_rejected`: threshold=1.5; expect `ConfigValidationError` (out of [0, 1]).

**Verification:** `uv run pytest packages/temper-placer/tests/io/test_config_loader.py -v`.

### U4. Seed Pool Filtering Integration

**Goal:** Apply `filter_seed` to the candidate pool inside `_phased_placement` between generation and the `_place_optimize` step, with an empty-pool fallback to unfiltered seeds + warning.

**Requirements:** R2, K4.

**Files:**
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (modify `_phased_placement` at line 115-180)
- `packages/temper-placer/src/temper_placer/deterministic/instrumentation.py` (add log line per R6)

**Approach:** After the candidate pool is generated and before optimization, build `hv_refs` from `NetClassRules.safety_category == "HV"`; iterate the pool, keep candidates where `filter_seed(...)` returns `True`. If `bottleneck_map is None` (U1 returned `None`) or `seed_filter_enabled` is `False`, skip filtering and pass the original pool through unchanged. If filtering yields zero candidates, log a warning and pass the original pool through (R2 fallback). Emit one INFO JSON line per call with `event="seed_filter"`, `candidates_total`, `candidates_accepted`, `candidates_rejected`, `avg_bottleneck_score_accepted`, `threshold`, `hv_threshold`, `fallback_used`.

**Test scenarios:**
- `test_filter_disabled_passes_pool_through`: `seed_filter_enabled=False`; input pool of 5 random seeds; expect all 5 reach `_place_optimize`.
- `test_filter_missing_map_silent_disable`: `seed_filter_enabled=True`, no bottleneck map; expect pool passes through unchanged with no warning.
- `test_filter_rejects_high_congestion_seeds`: map with 3 of 5 seeds landing in 0.9 cells; expect those 3 dropped.
- `test_empty_pool_falls_back_with_warning`: aggressive threshold (0.01) rejects all; expect `fallback_used=True` and unfiltered pool used; log capture shows warning.
- `test_integration_fallback_matches_unfiltered_path`: run `_phased_placement` twice on a board without bottleneck data, once with filter enabled and once with it disabled; expect identical placement results.

**Verification:** `uv run pytest packages/temper-placer/tests/deterministic/stages/test_phased_component_assignment.py -v`.

### U5d. SC1 Baseline Measurement (pre-step on `main`, before feature flag flips)

**Goal:** Produce the 10-run unfiltered baseline that U5c will compare against. This unit lands as the **first** U5 work, on a branch that merges to `main` **before** the feature flag flips anywhere — its sole output is the committed `seed-filter-baseline.md` file.

**Requirements:** R5 (baseline arm only), SC1 measurement infrastructure.

**Files:**
- `docs/solutions/measurements/seed-filter-baseline.md` (new — 10 unfiltered runs on `main`; mean/stddev of `routing_completion_pct` and HPWL on the temper board)
- `tools/measurements/seed_filter_baseline.py` (new — runs the closure test N times, writes JSON + markdown)
- `.github/workflows/python-tests.yml` (add a CI job that re-runs the measurement on schedule and PRs a diff if mean moves > 1pp)

**Approach:** Land this PR **first**, on `main`, with the feature flag defaulting to off (i.e. before U3 lands). The closure test runs the temper board 10 times at a fixed seed, recording `routing_completion_pct` and HPWL into `seed-filter-baseline.md` (human-readable summary) and a sibling `seed-filter-baseline.json` (machine-readable, used by U5c's acceptance check). The accompanying addendum `docs/brainstorms/2026-06-23-seed-filtering-sc1-acceptance-addendum.md` pins the SC1 acceptance rule (t-test + effect-size lower bound when stddev > 5pp; fixed-threshold otherwise); U5c dispatches on `stddev_baseline` from this file.

**Predecessor ordering:** U5d must land on `main` and the baseline file must be committed **before** U5c runs in CI. U5c's test reads `seed-filter-baseline.json` and fails the test if the file is missing or its schema version is older than the one pinned in the test fixture.

**Test scenarios:**
- `test_baseline_file_schema_matches_fixture`: load committed `seed-filter-baseline.json`; expect keys `runs`, `mean_routing_completion_pct`, `stddev_routing_completion_pct`, `mean_hpwl`, `stddev_hpwl`, `git_sha`, `seed`; expect `len(runs) == 10` and `git_sha` matches `HEAD` of `main` at measurement time.
- `test_baseline_markdown_renders`: parse `seed-filter-baseline.md`; expect a markdown table with one row per run plus mean/stddev summary.

**Verification:** `uv run python tools/measurements/seed_filter_baseline.py --board temper --runs 10 --output docs/solutions/measurements/`; PR must show the generated `seed-filter-baseline.md` and `.json` diff; CI gate fails if the file is stale (>30 days old) on `main`.

### U5a. Routing Stub + Multi-Retrigger Integration Test (synthetic board)

**Goal:** Cover R7 with an integration test that simulates the DAG feedback loop on a synthetic board, without requiring a full pipeline build.

**Requirements:** R5 (R5a–R5f), R7; success criterion SC1 (rettrigger-accumulation arm only — final result is recorded, not compared to baseline here; U5c owns the comparison).

**Files:**
- `packages/temper-placer/tests/integration/test_seed_filter_retriggers.py` (new)

**Approach:** The retrigger test instantiates `PhasedComponentAssignmentStage` plus a routing stub. The stub implements the `RoutingStageLike` protocol: it accepts a placement, returns `routing_completion_pct` and a recomputed `BottleneckMap` for the next iteration. The test runs the loop N=3 times, passing `routing_completion` and the recomputed map between iterations; asserts (a) `candidates_rejected / candidates_total` is non-decreasing across iterations and (b) final `routing_completion_pct >= SC1 single-pass result for this synthetic board` (a self-contained threshold loaded from the test fixture, **not** the `seed-filter-baseline.md` file — that file is U5c's concern).

**Predecessors:** U4 (the filter must be wired into `_phased_placement`); R-D5 must be resolved (see Risks & Dependencies).

**Test scenarios:**
- `test_retriggers_non_decreasing_rejection`: 3-iteration loop on a synthetic board; expect rejection fraction at iter 3 >= iter 2 >= iter 1.
- `test_retriggers_final_completion_meets_sc1_local`: 3-iteration loop on a synthetic-board fixture with a local single-pass result; expect final `routing_completion_pct >= local_sc1_threshold`.
- `test_routing_stub_contract`: instantiate stub; assert it satisfies `RoutingStageLike` (callable with `placement -> (routing_completion, bottleneck_map)`).

**Verification:** `uv run pytest packages/temper-placer/tests/integration/test_seed_filter_retriggers.py -v`.

### U5b. Observability-Key Capture Test (no DAG wiring)

**Goal:** Cover R6 with a unit test that captures the log line emitted by `_phased_placement` and asserts every required key is present. This unit deliberately does **not** require the DAG retrigger path to be wired; it runs the placer directly and reads `instrumentation.py` output.

**Requirements:** R6; success criterion SC4 (observability arm).

**Files:**
- `packages/temper-placer/tests/deterministic/stages/test_phased_component_assignment.py` (extend with `test_observability_emits_required_keys`)

**Approach:** Run `_phased_placement` once with a known seed pool and bottleneck map; capture the INFO log via `caplog`; assert exactly one line has `event="seed_filter"` and contains all R6 keys: `candidates_total`, `candidates_accepted`, `candidates_rejected`, `avg_bottleneck_score_accepted`, `threshold`, `hv_threshold`, `fallback_used`. This is intentionally a **unit test on the stage**, not a DAG integration test — U5a owns the DAG-wiring half of the observability story.

**Predecessors:** U4.

**Test scenarios:**
- `test_observability_emits_required_keys`: caplog capture; expect one INFO line with all R6 keys present, `event="seed_filter"`, and `fallback_used=False` on the happy path.
- `test_observability_fallback_used_true`: caplog capture with an aggressive threshold that rejects all candidates; expect `fallback_used=True` and the original pool passed through.

**Verification:** `uv run pytest packages/temper-placer/tests/deterministic/stages/test_phased_component_assignment.py -v -k observability`.

### U5c. Canonical-Boards Closure Test + SC1 Acceptance

**Goal:** Run the 4 canonical boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra) with `seed_filter_enabled=True`, assert validation passes, and run the SC1 acceptance check against the committed baseline file from U5d.

**Requirements:** R5 (canonical-boards arm), R6 (DAG-wiring observability check), R7 (closure test); success criteria SC1, SC4 (closure arm), SC5, SC6.

**Files:**
- `packages/temper-placer/tests/integration/test_closure_canonical_boards.py` (extend with seed-filter-on group)
- `packages/temper-placer/tests/integration/test_sc1_acceptance.py` (new — owns the SC1 dispatch)

**Approach:** The closure test runs all 4 canonical boards with `seed_filter_enabled=True`, asserts a non-empty `BottleneckMap` for the boards that have one, confirms `PlacementValidationStage` passes (SC5), and asserts `drc_errors` count equals the per-board baseline count (SC6). Boards lacking a map are split into a separate test group exercising R3's silent-disable fallback. A second test (`test_sc1_acceptance_against_baseline`) loads `docs/solutions/measurements/seed-filter-baseline.json` from U5d, runs the temper board 10 times with the feature on, and dispatches the SC1 acceptance rule per the addendum `docs/brainstorms/2026-06-23-seed-filtering-sc1-acceptance-addendum.md` (t-test + effect-size lower bound `d_min = 0.5` when `stddev_baseline > 5pp`; fixed-delta `mean_filtered - mean_baseline >= 10.0pp` otherwise).

**Predecessors:** U4, U5a, U5b, **U5d** (the baseline file must be committed and present in the working tree when this test runs — U5c's test setup asserts the file's `git_sha` matches `HEAD~` of the feature branch's merge-base with `main`).

**Test scenarios:**
- `test_canonical_boards_with_map_validate`: run with filter on for 4 boards that have `BottleneckMap`; expect `PlacementValidationStage` clean and a non-empty `BottleneckMap` assertion in each test's `setup()`.
- `test_canonical_boards_without_map_silent_disable`: subset of boards lacking bottleneck data; expect placements identical to unfiltered baseline.
- `test_no_new_drc_errors`: closure test fixture asserts `drc_errors` count == baseline count on the temper board.
- `test_sc1_acceptance_against_baseline`: load `seed-filter-baseline.json` (U5d output); run temper board 10 times with filter on; dispatch on `stddev_baseline` per the SC1 addendum; assert the appropriate branch's condition holds.
- `test_sc1_baseline_missing_fails_loudly`: delete or move `seed-filter-baseline.json`; expect the test to fail with an explicit message naming U5d as the missing prerequisite, not a silent skip.

**Verification:** `uv run pytest packages/temper-placer/tests/integration/test_closure_canonical_boards.py packages/temper-placer/tests/integration/test_sc1_acceptance.py -v`; U5c's test run requires U5d's baseline file to be present and schema-valid.

## Risks & Dependencies

- **R-D1: Bottleneck map data path ambiguity (Open Question, brainstorm §Open Questions R3).** Resolved in the dedicated **pre-implementation spike at Step 0** (above), not inside U1. Step 0's go/no-go transcript is the resolution record; U1's PR description must reference it. If Step 0 emits `NO-GO`, U1 is blocked and either the plan is amended to include the population step or the plan is deferred until the bottleneck-population follow-up issue lands.
- **R-D2: Cell resolution / floor vs. round (Open Question R1).** U1 picks `floor` (matches grid-cell convention used by `bottleneck_analysis.py` output); document the choice in `bottleneck_map.py` docstring. If a reviewer finds the bottleneck analysis uses `round`, switch is a one-line change in `score_at`.
- **R-D3: HPWL regression.** SC2 caps regression at 5%. U4's integration test asserts the fallback path produces identical placements when the map is missing, so boards without bottleneck data are not at risk. The risk concentrates on the temper board with an aggressive threshold; default 0.7 is conservative per K3.
- **R-D4: HV classification availability.** U2's `hv_refs` is computed at call site from `NetClassRules.safety_category`; relies on Assumption 3 in the brainstorm. If classification is unavailable for some components, default them to LV (current behavior).
- **R-D5: Multi-retrigger compounding test (R7) — hard precondition for U5a.** U5a requires a routing stub that can report `routing_completion` and recompute a bottleneck map between iterations, **and** that stub must be wired into the DAG trigger path used in `dag_engine.py:316-374` (the `_evaluate_feedback_contracts` loop). **Resolve before U5a starts:** (a) confirm the stub can be invoked through `_evaluate_feedback_contracts` in a unit test (i.e. `StageDefinition.feedback_contracts[0].target_stage` resolves to the stub's handler path, and the retrigger callback fires on a `metric_val < threshold` match), or (b) escalate to an integration test against a built pipeline binary if unit-level wiring is infeasible. **A mocked `BottleneckMap` whose per-cell scores improve deterministically across iterations is NOT an acceptable substitute** — it would let R7 devolve into a tautology (the test passes because the test wrote the scores, not because the filter is doing useful work). The chosen resolution (a or b) is recorded as a comment at the top of `packages/temper-placer/tests/integration/test_seed_filter_retriggers.py` when U5a lands.
- **R-D6: DAG engine coupling.** The `routability-retry` contract in `dag_engine.py:316-374` is unchanged, but U5's observability hook must be reachable from the DAG trigger path. Verify the stage's `__call__` log line fires on DAG retrigger before declaring U5 done.

## Scope Boundaries

### Deferred to Follow-Up Work

- **Dynamic threshold adjustment during a single placement run** (K3 follow-up). Profiler feedback into threshold is a separate requirements document.
- **Per-zone filtering or zone-aware thresholding.** Uniform threshold per R1; zone-aware variant is a future brainstorm.
- **Spatial precomputation (KD-tree, quadtree).** O(1) cell-indexed lookup is sufficient at current map resolution; spatial indexing is premature.
- **Baseline measurement refactor.** The 10-run baseline in U5 lives in a markdown file; a later plan may move it to a JSON fixture in `power_pcb_dataset/goldens/`.
- **Wiring `BoardState.bottleneck_analysis` population into the deterministic pipeline.** Currently the field is Router V6-only; if the placer must run without a sidecar in production, a follow-up plan must add the population step.

### Out of Scope

- **Modifying the DAG `routability-retry` contract** (K5). The filter is transparent to the contract; any contract change is a separate brainstorm.
- **Building the bottleneck map.** `BottleneckAnalysisStage` is the producer; this plan only consumes. Quality or coverage changes to bottleneck analysis are a separate concern.
- **Direct routing-completion scoring inside `filter_seed`.** The filter uses the bottleneck map only; mixing routing-completion signals into seed filtering couples it to the router and breaks the O(1) per-check budget.
- **HV/LV guard strips, ghost-pad injection, channel-aware scoring, clearance obstacle expansion, isolation slot consumption, min-cut bottleneck detection.** All are sibling ideas from the ideation doc with their own plans or future plans; this plan touches only #4.
=======
title: "feat: Bottleneck-Map Seed Filtering for Phased Placement"
type: feat
status: active
date: 2026-06-23
origin: prior session — phased-placement quality retrofit
---

# feat: Bottleneck-Map Seed Filtering for Phased Placement

## Summary

A six-piece wiring change that gives the phased placement stage (R5) a way to reject placement *seeds* whose component cells sit in pre-routed congestion hotspots. The seed filter is a thin shim between the constraint compiler and the slot scorer: it does not change how a slot is scored, it changes which slots are *eligible* to be scored. The filter is grounded by a new pure function `filter_seed` (R1, K1, K2), a frozen per-cell `BottleneckMap` dataclass with O(1) `score_at(x, y)` (R3), a typed `SeedFilterConfig` (R4, K3) wired into `PlacementConstraints` and the YAML loader, an empty-pool fallback (R2, K4) so the placer never silently reduces to zero candidates, and one structured `INFO` log line per call (R6) carrying the keys an operator needs to debug a regression. A multi-retrigger integration test (R7) and a resolved design decision (R-D5) close out the loop. The feature is gated by a YAML key (`seed_filter.enabled`) and silently no-ops when no `BottleneckMap` is reachable on `BoardState`, so it is safe to ship enabled-by-default in dev and disable in production via a one-line config flip.

This plan corrects the seed-filter's *production wiring*: R1-R3 + R6 land in the per-stage `_apply_bottleneck_filter` call site at `phased_component_assignment.py:424`, not in a parallel pure function that the placer never invokes. The pure `filter_seed` (R1) remains the canonical rejection function and is what the integration test (R7) exercises, so the per-stage wiring and the pure function never diverge.

---

## Problem Frame

The phased placer today scores every candidate slot and picks the lowest score. The scoring function combines soft-constraint penalties with HPWL wirelength, but neither term encodes a *congestion prior*: a slot inside a routing hot spot can score acceptably on a single component and yet contribute to a placement that the router cannot realize. The bottleneck map — a per-cell congestion grid produced by `RouterV6Pipeline` stage 2/3 — is already computed and stored on `BoardState.bottleneck_analysis`, but nothing in the placement path reads it. The placer is "blind" to where the router will struggle until the router actually runs, and the router's first-pass failure mode is "no path found" with no actionable attribution back to which component triggered the congestion.

The seed filter is the cheap fix. A `BottleneckMap` is a 2D `tuple[float, ...]` indexed by integer cell coordinates, so `score_at(x, y)` is an O(1) integer divide + index. With cell size 2 mm and a 100x150 mm board the map is 50x75 = 3,750 cells, well under any memory ceiling. The filter call adds one integer divide + one float compare per candidate slot, on a candidate list that is already < 10,000 slots after zone conflation — total cost is sub-millisecond and dwarfed by the HPWL scoring it precedes.

The seed filter must satisfy four correctness contracts simultaneously:

1. **Pure core (R1, K1, K2).** `filter_seed(seed, bmap, threshold, hv_threshold, hv_refs) -> bool` is side-effect free, has no I/O, and never raises on a missing cell — out-of-bounds clamps to `0.0` so a partial map cannot cause over-rejection. Purity lets the test suite call it without a `BoardState` and lets the per-stage wiring share the same logic.
2. **Empty-pool fallback (R2, K4).** When the filter would drop every candidate slot, the placer must NOT silently produce an empty pool. The behavior is: emit a `WARNING` ("would reject all N candidates for <ref>; falling back to unfiltered pool") and pass the original pool through unchanged. The warning is grep-visible in CI logs, never a CI failure. The fallback preserves placement progress at the cost of one routing retry.
3. **Silent disable on missing data (R3).** When `BoardState.bottleneck_analysis` is not a `BottleneckMap` (no map reachable, sidecar absent, sidecar malformed), the filter returns the candidate list unchanged with **no log line at all**. The motivation: every `PhasedComponentAssignmentStage` instantiation in the dev workflow runs without a router pre-pass, and a startup WARNING on every dev run is noise.
4. **Per-call observability (R6).** Every filter call that actually runs (enabled + map reachable + at least one candidate) emits exactly one `INFO` log line with the keys: `event`, `component`, `candidates_total`, `candidates_accepted`, `candidates_rejected`, `avg_bottleneck_score_accepted`, `threshold`, `hv_threshold`, `is_hv`, `fallback_used`. The line is emitted at the *filter* call site, not the pure function, so it is automatically off in unit tests of `filter_seed` and on in integration tests of the stage.

Two design decisions sit between the requirements and the code:

**R-D5 (resolved: option (a)).** "Should the seed filter live in a feedback loop with the router, retriggering placement when the router's first pass fails?" Option (a) — exercise the contract through a synthetic routing stub (`tests/integration/_seed_filter_synthetic_routing.py`) and assert non-decreasing rejection fraction across iterations. Option (b) — wire the full DAG retrigger path. The stub is non-tautological (per-cell scores derived from placement density, not a constant), so option (a) covers the contract without taking on the DAG-instrumentation cost. The integration test at `test_seed_filter_retriggers.py:115` (`test_retriggers_non_decreasing_rejection`) is the executable form of R-D5.

**HV-class detection.** The placer does not know a priori which refs are HV; it must inspect the ref's pin nets against `PlacementConstraints.get_net_class` (which classifies by name substrings "HV"/"BUS"/"DC_BUS" as `HighVoltage` per `config_loader.py:712`, with a secondary check against `NetClassRules.safety_category == "HV"` for the model-driven path). The per-stage wiring forwards `comp_by_ref` so the HV check can run; the pure `filter_seed` takes an explicit `hv_refs: frozenset[str]` set computed by the caller. Both paths are covered by tests.

---

## Scope Boundaries

### In scope

- R1-R7: the pure `filter_seed` function, the empty-pool fallback, the silent-disable on missing map, the `SeedFilterConfig` dataclass, the multi-retrigger integration test, the structured `INFO` log line, and the synthetic routing stub that the integration test depends on.
- K1-K4: purity, side-effect-freeness, config validation, and the fallback warning.
- The `BottleneckMap` dataclass and its `load_bottleneck_map` loader, including the sidecar `placement.channels.json` parser and the `board_state.bottleneck_analysis` short-circuit.
- The YAML config key `seed_filter` (with `enabled`, `threshold`, `hv_threshold`) wired through `load_constraints` and into `PlacementConstraints.seed_filter` with a default-enabled `SeedFilterConfig()` factory.
- The per-stage wiring in `PhasedComponentAssignmentStage._place_optimize` (U4) that calls `_apply_bottleneck_filter` for each ref after the constraint filter and before the slot scorer.
- The structured log line contract (R6) and its two test files: `tests/deterministic/stages/test_phased_component_assignment.py::TestObservabilityR6` (per-stage wiring) and `tests/deterministic/stages/test_seed_filter_integration.py::TestFilterBehavior` (filter unit tests with logger capture).
- The forward-port of `comp_by_ref` from `_place_optimize` to `_apply_bottleneck_filter` so the per-ref HV check actually runs in production (P1 from code review).
- The integration test (`test_hv_ref_uses_hv_threshold_and_logs_is_hv`) that constructs a ref whose pin net triggers `get_net_class(...) == "HighVoltage"` and asserts the log line reports `is_hv=True` with `hv_threshold=0.5000` and `fallback_used=True` (because the synthetic 0.6 map score is above the stricter HV threshold).
- R-D5 resolution: option (a) via the synthetic stub.

### Deferred to companion plan

- **Option (b) for R-D5** (full DAG retrigger path with the real `RouterV6Pipeline`) is deferred to the strangler pipeline initiative (`docs/plans/2026-06-23-001-feat-strangler-stage4-astar-plan.md` and adjacent plans). The synthetic stub is the executable form of R-D5 today; flipping to option (b) is a separate scope decision owned by the pipeline team.
- **Per-cell congestion *write-back* from router to map** (so the seed filter improves monotonically across iterations) is not in this changeset. The stub's scores are derived from placement density; a real write-back would require a new side-channel from the router. The current changeset treats the map as static per run, which is the conservative correct behavior.
- **Auto-tuning of `threshold` and `hv_threshold` per-board.** The defaults (0.7 LV, 0.5 HV) are hard-coded in `SeedFilterConfig.__post_init__` and tested. A future plan could expose these as CLI flags or auto-derive them from the placement area; not now.
- **Multi-class thresholds beyond HV/LV** (e.g., a separate `finepitch_threshold` for the `FinePitch` net class). The `filter_seed` signature accepts an `hv_refs` set, so a future plan can add a parallel `finepitch_refs` set without breaking the API. Not in this changeset.

### Out of scope

- **Any change to the router itself.** The seed filter *consumes* the router's `BottleneckMap`; it does not modify the router's outputs. `RouterV6Pipeline` is untouched.
- **Any change to the constraint compiler.** The constraint filter (`slot_filter`) and scorer (`slot_scorer`) are unchanged. The seed filter runs *between* constraint filter and scorer, so existing placement behavior is preserved when the seed filter is disabled or no map is reachable.
- **Placement-failure attribution.** When the router ultimately fails to route a placement, the failure attribution (which ref triggered which hot spot) is not added in this changeset. The `INFO` log line gives per-ref rejection counts; a future plan can add a summary aggregator.
- **Refactor of the unreachable `_get_allowed_zones` block in `sequential_routing.py`.** That block is owned by the zone-confinement backlog, not the seed-filter backlog. The code review flagged it (P2, manual); a follow-up plan will delete the unreachable block + its unused imports + the `cost_map_weights` parameter, or gate it with a feature flag.
- **Traceability gate adoption.** The `TRACEABILITY` sentinel is opt-in per directory; `packages/temper-placer/tests/deterministic/` and `packages/temper-placer/src/temper_placer/deterministic/` will not opt in via this plan (no `@req` enforcement). The `@req` tags on this plan's deliverables remain human-readable, not machine-enforced, until a separate plan opts in.

---

## Key Technical Decisions

**The pure function is the source of truth; the per-stage wiring is a thin caller.** `filter_seed` (R1) at `deterministic/seed_filter.py` is the algorithm. `_apply_bottleneck_filter` at `phased_component_assignment.py:616` is the wiring: it loads the map from `BoardState`, applies the `enabled` gate (K3), emits the R6 log line, and calls `filter_seed` per ref. Two callers, one algorithm — divergence is impossible because the integration test (R7) exercises the same `filter_seed` the unit tests do.

**Out-of-bounds clamps to 0.0, never raises.** A `BottleneckMap` with `cell_size_mm=2.0` covering a 100x150 mm board has cells at indices (0,0) to (49,74). A component placed at (100, 75) is one cell past the edge. Returning a sentinel like `inf` would cause the filter to reject the slot (the score is "infinite" so it's "above any threshold"); returning a negative value would cause the filter to accept the slot even in high-congestion areas. Returning `0.0` is the only safe default: a missing map edge cannot cause over-rejection, and a missing map edge is "we don't know" so we treat it as "no congestion". The pure function and the per-stage wiring both depend on this contract.

**HV-class detection runs in the per-stage wiring, not the pure function.** The pure `filter_seed` takes an `hv_refs: frozenset[str]` set as an explicit argument; the per-stage wiring computes the set by walking the ref's pins and asking `PlacementConstraints.get_net_class` + `NetClassRules.safety_category`. The split keeps the pure function ignorant of the `PlacementConstraints` type (it only knows about `BottleneckMap` and threshold numbers), and lets a future "finepitch threshold" feature add a parallel `finepitch_refs: frozenset[str]` without a `PlacementConstraints` dependency in the pure function. The R6 log line carries `is_hv=True/False` so the operator can see which path ran for each ref.

**The `comp_by_ref` forward-port (P1 from code review).** Before this fix, `_place_optimize` built `comp_by_ref` at line 159 but did NOT pass it to `_apply_bottleneck_filter`. The HV-class detection inside the filter received `None` and short-circuited to `is_hv=False`, so every ref was evaluated against the LV threshold. The fix is one line at `phased_component_assignment.py:424` plus an updated docstring; the integration test `test_hv_ref_uses_hv_threshold_and_logs_is_hv` (P1 follow-up) is the executable form of the regression. The fix is P1 because it silently disabled the stricter HV threshold in production, which is a safety-relevant bug for boards with high-voltage nets.

**Empty-pool fallback is a WARNING + pass-through, not a hard error.** When the filter would drop every candidate, the alternative behaviors are: (a) fail the run with an error, (b) pass the unfiltered pool through, (c) pass a synthetic "any" pool through. Option (a) blocks the placer when a board is unusually congested; option (c) invents a pool that may have invalid zones. Option (b) is the least-surprising: the placer makes its normal slot-selection decision over the original pool, the routing retry either succeeds or fails on the same terms it would have without the filter. The `WARNING` log line names the ref and the count so the operator can see the pattern and tune `threshold`/`hv_threshold`.

**Silent disable on missing map is the *only* path that does not log.** The `INFO` log line (R6) is emitted only when the filter actually runs: enabled AND map reachable AND candidates non-empty. Silent disable on missing map means: no `INFO` line at all (not "INFO with `enabled=True, map=None`"). The motivation is dev-ergonomics: every `PhasedComponentAssignmentStage` invocation in the dev workflow runs without a router pre-pass, and a startup `INFO` on every dev run is noise. The CI integration tests that DO have a `BottleneckMap` will see the log line; the unit tests that don't will not. The asymmetry is intentional.

**R-D5 resolution: synthetic stub, not full DAG retrigger.** The stub at `tests/integration/_seed_filter_synthetic_routing.py` is non-tautological: per-cell scores are computed from the placement's component density using a saturating formula, so a spread placement produces a different map than a clumped placement. The integration test asserts (i) the routing stub contract is satisfied (`route(placement) -> (completion, BottleneckMap)`), (ii) the stub is deterministic (same placement in -> same map out), (iii) the stub's scores depend on the placement (spread < clumped), and (iv) across retriggers, the rejection fraction is non-decreasing. The stub's contract is captured in the `RoutingStageLike` Protocol; flipping to option (b) (full DAG retrigger) only requires replacing the stub with a real `RouterV6Pipeline.route` call. The plan does NOT include the option (b) work.

**Default-enabled but trivial-cost.** The factory `SeedFilterConfig()` returns `enabled=True, threshold=0.7, hv_threshold=0.5`. With no `BottleneckMap` reachable, the filter is a no-op (R3). With a map, the filter is a `tuple[int]` index + a `float` compare per candidate slot. The "default-enabled" choice is the safe one: the cost is sub-millisecond on the dev workflow (no map), and the benefit is automatic on the production workflow (map present). The YAML `seed_filter.enabled: false` flag is the explicit kill switch.

---

## Implementation Units

### Phase 1 — Pure core (lands in PR 1, U1)

**U1. Add `filter_seed` + `BottleneckMap`**
- **Files touched:** `packages/temper-placer/src/temper_placer/deterministic/seed_filter.py` (new), `packages/temper-placer/src/temper_placer/deterministic/bottleneck_map.py` (new).
- **Steps:**
  1. `BottleneckMap`: frozen dataclass with `cell_size_mm`, `width`, `height`, `origin_xy`, `scores: tuple[float, ...]`; `score_at(x, y)` returns 0.0 for out-of-bounds; `_coerce_score` clamps to [0, 1] and rejects booleans/`None`; `_from_sidecar_payload` parses a `placement.channels.json` payload; `load_bottleneck_map(board_state, sidecar_path=None)` looks up `board_state.bottleneck_analysis` first, then the sidecar.
  2. `filter_seed(seed, bmap, threshold, hv_threshold, hv_refs) -> bool`: iterates the seed, applies the stricter threshold to HV refs, returns `True` iff every ref passes.
- **Acceptance:** R1, R3, K1, K2. Both modules importable; no external side effects. Out-of-bounds returns 0.0. Sidecar payload with missing fields returns `None` and logs a WARNING.

### Phase 2 — Config wiring (lands in PR 1, U2)

**U2. Add `SeedFilterConfig` + YAML loader**
- **Files touched:** `packages/temper-placer/src/temper_placer/io/config_loader.py`.
- **Steps:**
  1. New `@dataclass SeedFilterConfig` with `enabled: bool = True`, `threshold: float = 0.7`, `hv_threshold: float = 0.5`. `__post_init__` validates both thresholds are finite and in [0, 1] (K3).
  2. New field `PlacementConstraints.seed_filter: SeedFilterConfig = field(default_factory=SeedFilterConfig)`.
  3. `load_constraints` parses the `seed_filter` YAML key (with `enabled`, `threshold`, `hv_threshold`) and constructs the config.
  4. Add `"seed_filter"` to `_KNOWN_CONFIG_KEYS` so the YAML linter accepts the new key.
- **Acceptance:** R4, K3. `SeedFilterConfig()` default-constructs without error. Invalid `threshold=2.0` raises `ValueError` at load time, not at placement time. YAML `seed_filter: {enabled: false, threshold: 0.8, hv_threshold: 0.6}` parses to the right values.

### Phase 3 — Per-stage wiring (lands in PR 2, U3)

**U3. Wire `_apply_bottleneck_filter` into `_place_optimize`**
- **Files touched:** `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py`.
- **Steps:**
  1. New `_is_hv_ref(ref, comp_by_ref) -> bool` walks the ref's pins and asks `get_net_class` + `NetClassRules.safety_category`.
  2. New `_apply_bottleneck_filter(ref, candidates, comp_by_ref=None) -> list[tuple]` loads the map from `self._bottleneck_map`, applies the per-ref threshold, emits the R6 `INFO` log line, handles the empty-pool fallback.
  3. In `run()`: load the bottleneck map at the start, clear it in `finally`.
  4. In `_place_optimize`: after the constraint filter and before the slot scorer, call `_apply_bottleneck_filter(ref, available_slots, comp_by_ref)`. The `comp_by_ref` forward-port is the P1 fix.
- **Acceptance:** R2, R3, R4, R6, K4. `_apply_bottleneck_filter` returns the unfiltered list when `config.enabled=False`, when `self._bottleneck_map is None`, and when the filter would empty the pool. The `INFO` log line carries every R6 key.

### Phase 4 — Tests (lands in PR 2, U4 + U5)

**U4. Pure-function tests**
- **Files touched:** `packages/temper-placer/tests/deterministic/test_seed_filter.py` (new), `packages/temper-placer/tests/deterministic/test_bottleneck_map.py` (new).
- **Steps:**
  1. `test_seed_filter.py`: every R1 contract (HV ref is rejected at score >= hv_threshold; LV ref is rejected at score >= threshold; all-pass returns True; out-of-bounds clamps to 0.0; empty `hv_refs` set means no ref is HV-class). Hypothesis PBT for K1 (purity — same inputs -> same outputs across calls).
  2. `test_bottleneck_map.py`: every R3 contract (`score_at` out-of-bounds = 0.0; sidecar with missing fields returns None and logs WARNING; sidecar with non-positive dimensions returns None; `bottleneck_analysis` short-circuit fires when the attribute is a `BottleneckMap`; sidecar fallback fires when the attribute is None).
- **Acceptance:** All tests pass; coverage of the pure modules is >= 95%.

**U5a. Per-stage integration tests + multi-retrigger integration test**
- **Files touched:** `packages/temper-placer/tests/deterministic/stages/test_seed_filter_integration.py` (new), `packages/temper-placer/tests/integration/_seed_filter_synthetic_routing.py` (new), `packages/temper-placer/tests/integration/test_seed_filter_retriggers.py` (new).
- **Steps:**
  1. `test_seed_filter_integration.py`: every per-stage wiring contract (R2 — empty-pool fallback logs WARNING + passes through; R3 — silent disable on missing map; R4 — `enabled=False` is a no-op; R6 — log line carries all keys; K4 — fallback is exercised when the threshold drops every candidate). Uses `caplog` to capture the `INFO` line and asserts each key.
  2. `_seed_filter_synthetic_routing.py`: the `RoutingStageLike` Protocol and `SyntheticRoutingStub` class. Per-cell scores derived from placement density; deterministic; contract: `route(placement) -> (completion, BottleneckMap)`.
  3. `test_seed_filter_retriggers.py`: R5 + R7 + R-D5. Tests the stub contract (callable with placement, deterministic, scores depend on placement). Tests retriggers produce non-decreasing rejection fractions. Tests the final completion meets the local SC1 threshold for the synthetic board.
- **Acceptance:** All tests pass; the synthetic stub is independently usable by future plans (option (b) for R-D5).

**U5b. Per-stage observability tests + HV forward-port test (P1 follow-up)**
- **Files touched:** `packages/temper-placer/tests/deterministic/stages/test_phased_component_assignment.py`.
- **Steps:**
  1. `TestObservabilityR6::test_observability_emits_required_keys`: the happy path — all R6 keys appear in the first log line, `fallback_used=False`.
  2. `TestObservabilityR6::test_observability_fallback_used_true`: aggressive threshold (0.01) triggers `fallback_used=True`.
  3. `TestObservabilityR6::test_hv_ref_uses_hv_threshold_and_logs_is_hv` (P1 follow-up): constructs an HV-class ref whose pin net triggers `get_net_class(...) == "HighVoltage"`, an LV ref, and a 0.6 uniform map with `threshold=0.7, hv_threshold=0.5`. Asserts the HV ref's log line carries `is_hv=True`, `hv_threshold=0.5000`, and `fallback_used=True`; the LV ref's log line carries `is_hv=False` and `fallback_used=False`.
- **Acceptance:** All three tests pass. The HV test would have failed before the P1 fix because `is_hv` would have been `False` for every ref.

---

## System-Wide Impact

- **`packages/temper-placer/src/temper_placer/deterministic/seed_filter.py`** — new (~50 lines).
- **`packages/temper-placer/src/temper_placer/deterministic/bottleneck_map.py`** — new (~170 lines).
- **`packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py`** — adds `_is_hv_ref` (~30 lines), `_apply_bottleneck_filter` (~90 lines), the `comp_by_ref` forward-port (1 line + comment), the `__init__` `seed_filter` parameter (4 lines), the `run()` map-load/clear (4 lines), and the `_place_optimize` call site (3 lines).
- **`packages/temper-placer/src/temper_placer/io/config_loader.py`** — adds `SeedFilterConfig` (~25 lines), the `seed_filter` field on `PlacementConstraints` (1 line), the YAML parsing block (~10 lines), and the `_KNOWN_CONFIG_KEYS` entry (1 line).
- **Tests** — 5 new test files (~800 lines total) covering pure core, per-stage wiring, observability, and the multi-retrigger integration.
- **No router changes. No constraint compiler changes. No CLI changes.** The feature is fully internal to the placer.
- **No firmware, no PCB schematics, no placer algorithm changes** (other than the new filter call site). Existing placement behavior is preserved when `seed_filter.enabled=False` or when no `BottleneckMap` is reachable.

---

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| The seed filter over-rejects and the placer makes no progress | Low (default threshold=0.7 is permissive) | Medium — empty `placements` dict | R2 fallback: WARNING + pass-through. CI asserts the fallback path is exercised when threshold=0.01 + 0.9 map. |
| The seed filter's HV detection misses a real HV ref | Low (substring rule + safety_category fallback) | Medium — HV ref placed in a hot spot, routing failure downstream | Both substring ("HV"/"BUS"/"DC_BUS") and `safety_category=="HV"` paths are tested. The `_is_hv_ref` helper is independently tested with both positive and negative cases. |
| The `comp_by_ref` forward-port (P1 fix) breaks an existing call site | Low (the signature is additive; `comp_by_ref=None` is the existing default) | High — every ref's `is_hv` was silently `False` before, and changing that could now reject slots the previous placer accepted | The P1 integration test (`test_hv_ref_uses_hv_threshold_and_logs_is_hv`) is the regression guard. The P1 fix changes behavior only for refs whose pin net triggers `get_net_class(...) == "HighVoltage"` — no other ref. The default `enabled=True, threshold=0.7` is permissive enough that an HV ref with a high-score cell is the only new rejection path. |
| The R6 `INFO` log line is too verbose in CI | Low (one line per ref, not per slot) | Low — log volume grows linearly with component count | The log line is at `INFO` level, not `WARNING`. CI can filter it out via `grep` or downgrade to `DEBUG` for noise-sensitive runs. Future plan: rate-limit or summarize. |
| The synthetic stub (R-D5 option (a)) diverges from a real router's bottleneck map shape | Medium (stub uses a saturating formula; a real router uses path-finding cost) | Low — integration test asserts a coarse property (non-decreasing rejection fraction), not exact map equality | The stub's contract is captured in the `RoutingStageLike` Protocol. Flipping to option (b) replaces the stub with a real `RouterV6Pipeline.route` call; the integration test's assertions (R5/R7) carry over unchanged. |
| The `BottleneckMap` sidecar `placement.channels.json` is malformed in a board's pre-pass output | Medium (the sidecar is generated by a separate script) | Low — the filter silently disables (R3) | The sidecar parser logs a WARNING with the specific field that failed. R3's silent-disable is intentional; the WARNING makes the malformed sidecar visible without blocking the placer. |
| A future plan adds a third net class (e.g., FinePitch) and the threshold is per-class, not HV/LV | Low (the `filter_seed` signature accepts `hv_refs` as a `frozenset`; the caller computes it) | Low — additive change | The per-stage wiring computes `hv_refs` from `PlacementConstraints`; a future "FinePitch threshold" adds a parallel `finepitch_refs` set. The pure function and per-stage wiring both accept a `frozenset[str]` per class; no signature breakage. |

---

## Test Strategy

- **Unit (R1, R3, K1, K2):** `packages/temper-placer/tests/deterministic/test_seed_filter.py` and `test_bottleneck_map.py` cover the pure core. Hypothesis PBT for purity (K1): 100+ examples assert that two calls with the same inputs produce the same output. Coverage >= 95% of the two pure modules.
- **Per-stage (R2, R3, R4, R6, K4):** `packages/temper-placer/tests/deterministic/stages/test_seed_filter_integration.py` and `test_phased_component_assignment.py::TestObservabilityR6` cover the wiring. `caplog` captures the `INFO` line and asserts every R6 key. The P1 follow-up test (`test_hv_ref_uses_hv_threshold_and_logs_is_hv`) is the regression guard for the `comp_by_ref` forward-port.
- **Integration (R5, R7, R-D5):** `packages/temper-placer/tests/integration/test_seed_filter_retriggers.py` exercises the synthetic stub contract, the non-decreasing rejection fraction, and the local SC1 threshold. The stub is independently usable for future plans that need a non-tautological routing feedback signal.
- **Manual smoke:** Run the canonical `run_router_v6.py` on a fixture board with `seed_filter: {enabled: true}` in the YAML config. Confirm (a) the `INFO` log line appears per ref in the route log, (b) the placement dict is non-empty, (c) the router's first-pass failure rate drops (or stays the same) vs the `seed_filter: {enabled: false}` baseline.
- **CI:** the existing `python-tests.yml` job runs all 5 new test files; the per-stage and integration tests trigger on any change to `packages/temper-placer/src/temper_placer/deterministic/**` or `packages/temper-placer/tests/deterministic/**`. No new CI jobs.

---

## Deferred to Implementation

- **Option (b) for R-D5** (real `RouterV6Pipeline.route` call instead of the synthetic stub) — the synthetic stub captures the contract; the real-router work is owned by the pipeline team and the strangler Stage 4 plan (`docs/plans/2026-06-23-001-feat-strangler-stage4-astar-plan.md`).
- **Per-cell congestion write-back from router to map** — requires a new side-channel from `RouterV6Pipeline`. Owned by the router team.
- **Auto-tuning of `threshold` and `hv_threshold` per-board** — the current defaults (0.7 LV, 0.5 HV) are hard-coded; a future plan could expose them as CLI flags or auto-derive them from the placement area.
- **Multi-class thresholds beyond HV/LV** (e.g., `FinePitch` threshold) — additive change to `filter_seed`'s signature; the `hv_refs: frozenset[str]` pattern generalizes to a `threshold_by_class: dict[str, float]`.
- **Failure attribution** (which ref triggered which hot spot when the router ultimately fails) — the per-ref R6 log line is the data source; a future plan can aggregate.
- **Refactor of the unreachable `_get_allowed_zones` block in `sequential_routing.py`** — owned by the zone-confinement backlog, not the seed-filter backlog. Code review flagged it (P2, manual); a follow-up plan will either delete the unreachable block + unused imports + the `cost_map_weights` parameter, or gate it with an explicit feature flag.
>>>>>>> feat/seed-filtering
