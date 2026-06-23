---
type: feat
origin: docs/brainstorms/2026-06-23-channel-aware-scoring-requirements.md
status: completed
date: 2026-06-23
---

# Channel-Aware Placement Scoring — Implementation Plan

## Problem Frame

The placer (`phased_component_assignment`) and the router (`RouterV6Pipeline`) share a board but share no feedback. Placement scores slots using only `slot_scorer` (soft constraints) plus HPWL wirelength with a 0.1 weight, while Router V6 Stage 2 produces rich routing-foresight data — obstacle maps, occupancy grids, bottleneck scores — serialized to `placement.channels.json` but never consumed. Ten of 24 nets fail routing on the 4 canonical boards (33% completion) because placement picks slots that score well on wirelength but sit in congestion cells. This plan wires the sidecar's snapshot into the placer's `score_slot` closure as an additive, weighted, gracefully-degrading routability term, and adds a DRC fence invariant to catch components placed inside CRITICAL bottleneck cells.

## Implementation Units

### U1. Channel Sidecar Module

**Goal.** Add a typed loader for `placement.channels.json` that returns a frozen `ChannelMap` dataclass and degrades gracefully to `ChannelMap.empty()` on any error.

**Requirements.** R1, R2, R5

**Files.**
- `packages/temper-placer/src/temper_placer/deterministic/channels.py` (new module)
- `packages/temper-placer/src/temper_placer/deterministic/__init__.py` (re-export `ChannelMap`, `ChannelSidecarError`)

**Approach.** New module exposes:
- `@dataclass(frozen=True) class Bottleneck(x, y, layer, severity, score)`
- `@dataclass(frozen=True) class ChannelMap(grid, cell_size_um, bottlenecks)` with classmethod `empty()` returning a sentinel zero-bottleneck map and `load_from_sidecar(path)` doing JSON parse + schema validation
- `class ChannelSidecarError(Exception)`
- `routability_penalty(slot: tuple[float, float], channel_map: ChannelMap) -> float` — converts `slot` (mm) to grid coordinates via `gx = int(math.floor((x_mm * 1000.0) / cell_size_um))` (and analogously for `gy`), reads occupancy and bottleneck severity, returns `severity_weight * (0.5 + 0.5 * occupancy)` (monotonically increasing in occupancy, bounded to `[0.0, 1.0]`); out-of-grid slots (`gx < 0 or gx >= grid_width`, or analogously for `gy`) return `0.0`
- Severity weights: `LOW=0.05, MEDIUM=0.15, HIGH=0.4, CRITICAL=1.0`
- Validate `temper_schema_hash` against an allowlist constant; unknown hash raises `ChannelSidecarError`

**Test scenarios.**
- `test_load_valid_sidecar`: sidecar matching schema → `ChannelMap` populated; `grid` is `tuple[tuple[int, ...], ...]`; `bottlenecks` are typed records
- `test_load_missing_file`: `ChannelMap.empty()` returned, no exception
- `test_load_malformed_json`: `ChannelSidecarError` raised with file path in message
- `test_load_unknown_severity`: `ChannelSidecarError` raised naming the bad severity value
- `test_load_unknown_schema_hash`: `ChannelSidecarError` raised
- `test_penalty_in_grid_free`: slot in free cell on un-bottlenecked layer → `0.0`
- `test_penalty_critical_full_free`: slot at CRITICAL cell, occupancy 0.0 → `0.5` (`severity_weight * (0.5 + 0.5 * 0)` = `1.0 * 0.5`)
- `test_penalty_out_of_grid`: slot outside grid bounds (`gx < 0` or `gx >= grid_width`) → `0.0`
- `test_penalty_fully_occupied_returns_max`: CRITICAL cell, occupancy 1.0 → `1.0` (`severity_weight * (0.5 + 0.5 * 1)` = `1.0 * 1.0`); the maximum penalty a slot can incur
- `test_penalty_at_cell_boundary_consistent`: two slots 1µm apart straddling a cell boundary must land in distinct grid cells (`floor` semantics) and produce different penalties when the two cells differ in severity
- `test_empty_map_returns_zero`: `routability_penalty(slot, ChannelMap.empty())` → `0.0` for any slot

**Verification.** Module imports cleanly; `pyright` clean; `ruff` clean; unit tests pass.

### U2. Placer Score-Thread Integration

**Goal.** Thread `ChannelMap` through `PhasedComponentAssignmentStage` so `score_slot` adds `routability_penalty(slot, channel_map) * w_r` with default `w_r=0.05`, preserving current behavior when `channel_map is None`.

**Requirements.** R3, R5, R9

**Files.**
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py:447-455` (modify `score_slot` closure; add `channel_map` and `w_r` constructor params)
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (constructor; `invariants` property)

**Approach.**
- Add `channel_map: ChannelMap | None = None` and `w_r: float = 0.05` keyword params to `__init__`; default `None` preserves current behavior for callers that do not produce a sidecar
- Log a `WARNING` at construction if `channel_map is None` (signals under-instrumented runs)
- Update `score_slot` to compute `constraint_penalty + wirelength * 0.1 + (routability_penalty(slot, self.channel_map) * self.w_r if self.channel_map else 0.0)`
- `w_r=0.0` produces identical output to `channel_map=None` (no sidecar) — explicit escape hatch
- Hot path: `routability_penalty` must not allocate; grid stored as flat tuple for O(1) integer index
- Both `_place_optimize` and `_simple_greedy_placement` use the same `score_slot` closure — both get routability awareness for free

**Test scenarios.**
- `test_score_slot_with_sidecar`: stage constructed with a CRITICAL bottleneck cell at occupancy 1.0 (worst case — penalty = 1.0 raw, score contribution = `1.0 * w_r = 0.05`); component with two candidate slots (one in CRITICAL, one wirelength-shorter by 0.05mm) — sidecar-on path picks the wirelength-shorter slot only when wirelength delta exceeds the CRITICAL score contribution (0.05 worst case); confirms K3 weight math under the `severity_weight * (0.5 + 0.5 * occupancy)` formula
- `test_score_slot_no_sidecar_matches_baseline`: `channel_map=None` produces byte-identical `score_slot` output to pre-change snapshot fixture
- `test_score_slot_w_r_zero_matches_baseline`: `w_r=0.0` matches baseline
- `test_warning_logged_when_no_sidecar`: caplog captures WARNING with "channel_map" in message
- `test_per_call_under_5_microseconds`: benchmark on the 4 canonical boards' sidecars; assert median < 5µs/call (R9 SC5)

**Verification.** Existing placer tests unchanged; new tests pass; perf benchmark under budget.

### U3. Pipeline Orchestration & Closure Test Plumbing

**Goal.** The deterministic pipeline loads `placement.channels.json` once per run (if present) and injects it into the placement stage; the closure test invokes channel analysis between parse and place so a sidecar exists for placement to consume.

**Requirements.** R4 (R4a, R4b, R4c, R4d), R5, R7 (R7e)

**Files.**
- `packages/temper-placer/src/temper_placer/deterministic/__init__.py:67-127` (pipeline orchestration)
- `packages/temper-placer/src/temper_placer/regression/closure_test.py` (closure test sequence)
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:241-326` (Stage 2 invocation; not modified, only called)

**Approach.**
- In pipeline `__init__.py:67-127`, before instantiating `PhasedComponentAssignmentStage`, look for `placement.channels.json` in the run output dir; on hit, call `ChannelMap.load_from_sidecar` and pass the result to the stage; on miss/error, log WARNING and pass `None`
- Cache the loaded `ChannelMap` once per pipeline run (R4c); do not re-read per component
- Closure test: new order is parse (produces netlist + board outline) → channel analysis (`RouterV6Pipeline._run_stage2(netlist, board_outline, components=[])` to produce the sidecar) → load sidecar into `ChannelMap` → assert sidecar's `cell_size_um` equals the placer's expected `PLACER_CELL_SIZE_UM` constant, otherwise raise a hard error → place (with sidecar) → route → DRC
- Wrap channel analysis in try/except; on ImportError or failure, log WARNING and fall back to current placement (R4d)
- Sidecar load count is tracked per-pipeline-instance as `self._sidecar_load_count: int = 0`, incremented inside `load_from_sidecar` (or in the pipeline `__init__` wrapper that calls it); asserted `== 1` at the end of the same pipeline run (R7e). The counter lives on the `ChannelMap` instance (or the pipeline wrapper) — never as a module-level global — so it is thread-safe and does not flake under pytest-xdist

**Test scenarios.**
- `test_pipeline_loads_sidecar_when_present`: pre-staged `placement.channels.json` in tmp output dir → `ChannelMap` is constructed and passed to stage; sidecar loader counter == 1
- `test_pipeline_missing_sidecar_uses_none`: no sidecar file → stage constructed with `channel_map=None`; WARNING logged
- `test_pipeline_malformed_sidecar_falls_back`: corrupt JSON → `ChannelMap.empty()`; WARNING logged with path
- `test_pipeline_reads_sidecar_once`: instantiate two independent pipelines in the same test (each in its own tmp output dir with a pre-staged sidecar); place 1000 components through each; assert each pipeline's `_sidecar_load_count == 1` independently. Confirms the counter is per-instance, not shared, and is not incremented by per-component placement activity
- `test_closure_test_runs_channel_analysis_first`: monkeypatched `RouterV6Pipeline._run_stage2`; assert called between parse and place
- `test_closure_test_sidecar_grid_matches_placer_grid`: sidecar produced with a known `cell_size_um`; assert `ChannelMap.load_from_sidecar(...).cell_size_um == PLACER_CELL_SIZE_UM`; assert mismatch raises a hard error (not a soft WARNING) so downstream placement never consumes a misaligned grid
- `test_closure_test_falls_back_when_router_unavailable`: monkeypatch to raise `ImportError`; closure test completes with WARNING, no hard failure

**Verification.** Pipeline integration test passes; closure test ordering verified; counter assertion holds.

### U4. DRC Fence Invariant

**Goal.** Add a per-stage invariant declaration on `PhasedComponentAssignmentStage` that flags any placed component center falling inside a CRITICAL-severity bottleneck cell.

**Requirements.** R6

**Files.**
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (`invariants` property and check logic)

**Approach.**
- Add `"no_component_center_in_critical_bottleneck"` to the `invariants` property when `self.channel_map is not None`; omit it otherwise (no false positives on degraded runs)
- Center-only sampling in the initial implementation (R6 explicitly allows deferral of footprint-extent sampling; invariant name reflects that)
- After placement completes, iterate placed components; for each `(ref, x_mm, y_mm)`, convert to grid coords; if cell is in `bottlenecks` with `severity == "CRITICAL"`, append violation `{ref, x, y, layer, severity}`
- Violations report names component ref, bottleneck coordinates, and severity
- Soft-launch: WARNING-only for 2 weeks, then fence-fail (consistent with the per-stage DRC fence soft-launch policy from `docs/solutions/design-patterns/per-stage-drc-fence-verification-2026-06-22.md`)

**Test scenarios.**
- `test_invariant_declared_when_sidecar_loaded`: stage with non-None `channel_map` exposes `no_component_center_in_critical_bottleneck` in `invariants`
- `test_invariant_absent_when_no_sidecar`: stage with `channel_map=None` does not expose the invariant
- `test_invariant_flags_component_in_critical_cell`: stage placed a component at a known CRITICAL cell → invariant check reports violation with `ref`, coordinates, and `severity="CRITICAL"`
- `test_invariant_passes_component_in_free_cell`: stage placed a component in a non-bottlenecked cell → no violation
- `test_invariant_passes_component_in_medium_bottleneck`: MEDIUM/HIGH severity cells do not trigger (only CRITICAL does)

**Verification.** Invariant present, correct, and properly conditional on sidecar availability.

### U5. Parity & Property-Based Test Suites

**Goal.** Gate landing with a parity test (sidecar on vs off) and a hypothesis-driven PBT suite for the penalty function.

**Requirements.** R7 (R7a, R7b, R7c, R7d), R8 (R8a–R8f)

**Files.**
- `packages/temper-placer/tests/deterministic/test_channel_scoring_parity.py` (new)
- `packages/temper-placer/tests/deterministic/test_channel_penalty_pbt.py` (new)

**Approach.**
- **Parity suite.** For each of `["Piantor_Right", "LibreSolar_BMS", "RP2040_DesignGuide", "BitAxe_Ultra"]`: (1) baseline `channel_map=None` closure test run; (2) sidecar-on closure test run; assert 100%-routing boards remain at 100% (R7b); assert non-decreasing completion (R7b); assert `< 2%` wirelength delta on already-routing boards (R7b); regression on a previously-passing board → `pytest.fail("regression: board X completion dropped from 100% to Y% with sidecar")` (R7c)
- **Monotonicity.** Across seeds 0–4 on each board, mean `router_completion_pct` of sidecar-on ≥ mean of sidecar-off (R7d); if variance is high, switch to Wilcoxon rank test during planning
- **PBT suite.** Use `hypothesis` with ≥ 100 examples per property: (R8a) `0.0 ≤ penalty ≤ 1.0`; (R8b) free + non-bottlenecked → `0.0`; (R8c) CRITICAL + occupancy 1.0 → `1.0` (maximum); (R8c′) CRITICAL + occupancy 0.0 → `0.5`; (R8d) severity monotonicity `LOW ≤ MEDIUM ≤ HIGH ≤ CRITICAL`; (R8e) occupancy monotonicity (penalty non-decreasing in occupancy, holding severity fixed); (R8f) out-of-grid → `0.0`
- PBT includes a deliberately-injected bug guard: temporarily mutate `routability_penalty` to return `1.5`; assert PBT catches it (SC3)

**Test scenarios.**
- `test_parity_piantor_100pct_remains_100pct`: sidecar-on matches sidecar-off completion on Piantor_Right
- `test_parity_wirelength_delta_under_2pct`: `< 2%` change on already-routing boards
- `test_parity_failure_message_format`: a forced regression produces the exact message `regression: board X completion dropped from 100% to Y% with sidecar`
- `test_parity_monotonicity_across_seeds`: mean sidecar-on ≥ mean sidecar-off over seeds 0..4
- `test_pbt_penalty_bounded`: R8a
- `test_pbt_free_cell_zero`: R8b
- `test_pbt_critical_full_free_one`: R8c
- `test_pbt_severity_monotonic`: R8d
- `test_pbt_occupancy_monotonic`: R8e
- `test_pbt_out_of_grid_zero`: R8f
- `test_pbt_catches_injected_violation`: monkeypatched `routability_penalty` returning 1.5 → PBT fails (SC3)

**Verification.** Parity suite gates CI; PBT suite green; injected-bug test confirms the gate has teeth.

### U6. Soft-Launch Flip (WARNING → fence-fail)

**Goal.** Own the U4 DRC-fence invariant's WARNING-only → hard-fail transition with a single named flag, tests for both states, and a tracked follow-up issue so the 2-week flip is not lost.

**Requirements.** R6 (soft-launch policy)

**Files.**
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py` (read `DRC_FENCE_FAIL_ENABLED`)
- `packages/temper-placer/src/temper_placer/deterministic/__init__.py` (or a new `flags.py`) — single source of truth for the constant
- New bd issue: `Flip DRC fence invariant to hard-fail` (linked as a follow-up to this plan's epic)

**Approach.**
- Define a single constant `DRC_FENCE_FAIL_ENABLED: bool` (default `False`, overridable via the `TEMPER_DRC_FENCE_FAIL` env var) read at invariant-check time by the `no_component_center_in_critical_bottleneck` check
- When `False`: violations are logged at WARNING level, no exception raised, placement run completes (current soft-launch behavior)
- When `True`: any violation raises, failing the pipeline run with the violation's `ref`, coordinates, and `severity` in the message
- File a follow-up bd issue titled `Flip DRC fence invariant to hard-fail` with this unit's flip as its acceptance criteria; link it back to this plan. The 2-week date from U4 is encoded in the issue's `due_at` field
- The constant lives in one module only; the invariant check does not import any other toggle

**Test scenarios.**
- `test_fence_warning_only_when_disabled`: `DRC_FENCE_FAIL_ENABLED=False`, component placed in CRITICAL cell → invariant check returns the violation, logs WARNING, does not raise; run completes
- `test_fence_hard_fails_when_enabled`: `DRC_FENCE_FAIL_ENABLED=True`, same scenario → `PhasedComponentAssignmentError` (or equivalent) raised with the violation's `ref` and `severity` in the message
- `test_fence_env_var_overrides_default`: setting `TEMPER_DRC_FENCE_FAIL=1` in `os.environ` flips behavior at runtime without code change
- `test_fence_non_critical_violations_unaffected`: HIGH/MEDIUM cells do not trigger the fence in either state (U4's invariant name is `no_component_center_in_critical_bottleneck`; severity is part of the contract)

**Verification.** Constant has one declaration; WARNING-only and hard-fail tests both pass; the follow-up bd issue exists and references this unit.

## Risks & Dependencies

- **R1: open question on field set.** The exact field names in `placement.channels.json` (per the brainstorm's "Resolve Before Planning" question) must be confirmed by reading the sidecar writer in `router_v6/` before U1 lands. If the writer uses different names, U1 adapts the loader.
- **R2: open question on grid resolution.** If cell size is 0.5mm and footprints are 2mm, center-only sampling may miss a corner sitting in a different cell. Initial implementation is center-only (per R6's allowed deferral); follow-up issue for footprint-extent sampling if parity results show missed violations.
- **R3: weight tuning.** `w_r=0.05` is the gate; R7b enforces no-regression on already-passing boards. If parity fails, the weight is tuned globally — not per-board.
- **D1: DRC fence soft-launch timeline.** R6 is WARNING-only for 2 weeks post-deploy; coordinate dates with the per-stage DRC fence initiative (`docs/solutions/design-patterns/per-stage-drc-fence-verification-2026-06-22.md`).
- **D2: closure test baseline wall-clock.** R9's 10% budget is relative; the current closure test wall-clock must be measured before U5 to set the absolute budget.
- **D3: Router V6 importability in closure test env.** If Router V6 is not importable, R4d's fallback applies and the initiative contributes zero placement improvement on that run.
- **D4: import-boundary lint.** Adding `deterministic/channels.py` may trigger `import-linter` boundaries if it imports from `router_v6` — the loader reads only the sidecar JSON (a plain dict), so no `router_v6` import is required. Run `scripts/import_linter_gate.py` before push.

## Scope Boundaries

### Deferred to Follow-Up Work

- **Re-running channel analysis after placement** (per-placement feedback loop) — requires a sidecar *writer* in the placer and a re-entry contract for the placement stage.
- **Per-net-class `w_r`** — HV nets (`NetClassRules.safety_category`) deserve higher weights because their routing failure is a safety issue, not just a completion-rate issue. Single global `w_r` for now.
- **Channel-aware seed filtering** — combining channel analysis with the seed-generation path in `_place_optimize` is a separate initiative (ideation #4).
- **Sidecar freshness checks** — mtime validation against source PCB; the placer currently trusts whatever sidecar exists.
- **Footprint-extent sampling for the DRC invariant** — center-only in the initial implementation; R6 explicitly allows deferral.

### Out of Scope

- **Modifying the channel analysis algorithm.** U1–U5 consume the sidecar; the 8 micro-stages in `router_v6/{obstacle_map, occupancy_grid, bottleneck_analysis, ...}.py` are not touched.
- **Replacing HPWL with a congestion-weighted wirelength metric.** The wirelength term remains HPWL-based.
- **Modifying DRC check implementations.** U4 adds a stage invariant declaration; `temper_drc` checks are unchanged.
- **Re-architecting the pipeline stage order.** U3 adds one step (load sidecar) and one optional step (channel analysis) to the closure test sequence; overall DAG is unchanged.
