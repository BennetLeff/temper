---
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
