---
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
