---
title: "feat: Extend Timing Gate Coverage to RouterV6Pipeline and PipelineOrchestrator"
type: feat
status: draft
date: 2026-06-29
origin: docs/plans/2026-06-22-022-feat-per-stage-timing-regression-gate-plan.md (deferred scope — OQ4)
depends_on:
  - docs/plans/2026-06-22-022-feat-per-stage-timing-regression-gate-plan.md  (completed; provides timing gate CLI, TimingResult/measure_stage_timing contract, CI check step)
  - docs/plans/2026-06-22-015-feat-pipeline-profiling-validation-toolkit-plan.md  (PipelineProfiler with Stage2Orchestrator sub-step timers, RouteProfileStats)
  - docs/plans/2026-06-22-009-feat-golden-fixture-ladder-plan.md                   (non-breaking manifest addition pattern — R12)
---

# feat: Extend Timing Gate Coverage to RouterV6Pipeline and PipelineOrchestrator

## Summary

Plan 022's per-stage timing gate covers only `DeterministicPipeline`'s 14 stages. `RouterV6Pipeline` stages (Stage 1-5, plus 8 Stage 2 sub-steps) and `PipelineOrchestrator` phases (8 phases: input through output) already have profiling instrumentation — `PipelineProfiler` sub-step timers in `Stage2Orchestrator`, `RouteProfileStats` in `astar_core_numba` — but no timing regression enforcement. This plan adds RouterV6Pipeline and PipelineOrchestrator entries to `timing_baselines.yaml` and wires them into `temper timing check`, the `temper timing baseline --pipeline` flag, and the CI timing check step. Non-breaking addition — existing DeterministicPipeline baselines are unaffected (Plan 022 R12 pattern).

Two implementation units: U1 adopts the existing `--pipeline` flag already specified in Plan 022 U2's CLI design to capture RouterV6Pipeline and PipelineOrchestrator baselines into the manifest. U2 wires those baselines into the CI check step in `python-tests.yml`.

---

## Problem Frame

Plan 022's timing gate explicitly deferred RouterV6Pipeline and PipelineOrchestrator coverage (OQ4: "Start with DeterministicPipeline only... RouterV6Pipeline and PipelineOrchestrator baselines are added non-breakingly later (R12)"). The gate now blocks only DeterministicPipeline stage slowdowns. Meanwhile:

- `RouterV6Pipeline` stages are actively under decomposition (strangler fig), with Stage 2 decomposed into 8 micro-stages and Stage 4 backed by A* pathfinding. Each decomposition changes timing profile — but no CI gate detects slowdowns.
- `PipelineOrchestrator` phases are the entry point for CI closure tests. Phase-level slowdowns (e.g., geometric optimization taking longer due to placement changes) are invisible to the gate.
- Both pipelines already have profiling instrumentation from Plan 015: `Stage2Orchestrator` uses `self._profiler.sub_step("stage2", stage.name)` to record per-sub-step wall-clock, and `RouteProfileStats` in `astar_core_numba` captures A* per-path latency. These timers are collected but never compared against a committed baseline.
- The `temper timing baseline --pipeline` flag is already specified in Plan 022 U2 but only exercised on `DeterministicPipeline`. The infrastructure supports multi-pipeline baselines in the manifest schema (`pipeline: DeterministicPipeline` field).

The gap: profiling data exists, the CLI flag exists, the manifest schema supports multi-pipeline entries — but no baselines are committed and no CI enforcement runs for these pipelines.

---

## Requirements

From Plan 022 OQ4 and the deferred scope section:

**Baseline Capture (R1–R2):**
- R1. `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed` captures wall-clock timing for RouterV6Pipeline stages (Stage 1: escape vias, Stage 2: channel analysis, Stage 3: topological routing, Stage 4: geometric realization, Stage 5: post-processing). Stage 2 sub-steps (8 micro-stages) are optionally captured via `--sub-steps`.
- R2. `temper timing baseline --pipeline PipelineOrchestrator --board temper_placed` captures wall-clock timing for each of the 8 orchestrator phases (input, semantic, topological, preflight, geometric, routing, refinement, output).

**CI Enforcement (R3–R4):**
- R3. `temper timing check` covers all baselines in `timing_baselines.yaml` regardless of pipeline — RouterV6Pipeline and PipelineOrchestrator stages are checked with the same 20% margin / 10ms floor as DeterministicPipeline stages.
- R4. The CI timing check step in `python-tests.yml` runs `temper timing check --ci --json` which automatically includes all pipelines in the manifest. No per-pipeline opt-in required — the check reads the manifest, iterates all entries.

**Non-Breaking Addition (R5):**
- R5. Adding RouterV6Pipeline and PipelineOrchestrator baselines does not modify, invalidate, or re-check existing DeterministicPipeline entries. New pipeline entries are additive.

---

## High-Level Technical Design

*This illustrates the intended approach and is directional guidance for review, not implementation specification.*

### How the `--pipeline` flag already works

Plan 022 U2 designed `temper timing baseline` with a `--pipeline` / `-p` flag defaulting to `"DeterministicPipeline"`. The CLI design (Plan 022 lines 213–258) already accepts `RouterV6Pipeline` and `PipelineOrchestrator` as valid values. The same `measure_stage_timing()` function in `timing_gate.py` handles multi-pipeline measurement — the pipeline name is a string parameter passed through to the profiler.

When `--pipeline RouterV6Pipeline` is passed, the baseline command constructs the RouterV6Pipeline, runs its stages, and captures per-stage wall-clock via the existing `PipelineProfiler` (or fallback time measurement). The resulting `TimingResult` records `pipeline: "RouterV6Pipeline"` and is written to `timing_baselines.yaml` alongside existing DeterministicPipeline entries.

### Stage 2 sub-step baselines

RouterV6Pipeline Stage 2 delegates to `Stage2Orchestrator`, which runs 8 micro-stages:
`obstacle_map`, `routing_space`, `channel_skeleton`, `channel_widths`, `occupancy_grid`, `layer_capacity`, `routing_demand`, `bottleneck_analysis`.

When `PipelineProfiler` is active, `Stage2Orchestrator.run()` wraps each micro-stage with `self._profiler.sub_step("stage2", stage.name)` (see `stage2_orchestrator.py:68`). The profiler records per-sub-step wall-clock in `StageTiming.sub_steps`. The timing gate can extract these sub-step timings for baseline capture and check.

The `--sub-steps` flag (optionally added to `temper timing baseline`) controls whether sub-step timings are captured during baseline measurement. Once sub-step entries exist in the manifest, `temper timing check` covers them automatically (K3). Without `--sub-steps`, only the top-level Stage 2 wall-clock is captured (the aggregate of all 8 micro-stages).

### PipelineOrchestrator phase measurement

`PipelineOrchestrator` runs 8 phases via `StageDAGEngine`. The `PipelineProfiler` wraps each phase handler call. Phase names are the `PipelinePhase` enum values: `input`, `semantic`, `topological`, `preflight`, `geometric`, `routing`, `refinement`, `output`. Some phases may be skipped based on config (e.g., `skip_routing` skips routing and refinement phases). The profiler records wall-clock for each executed phase.

### Manifest schema — no changes needed

`timing_baselines.yaml` already supports multi-pipeline entries via the `pipeline` field (Plan 022 U3 schema, line 307). RouterV6Pipeline and PipelineOrchestrator entries use the same schema:

```yaml
- board: temper_placed
  pipeline: RouterV6Pipeline
  stage: stage4
  wall_ms_mean: 15230.5
  wall_ms_p95: 15800.2
  n_runs: 3
  individual_ms: [15000.1, 15230.5, 15800.2]
  git_hash: "a1b2c3d4e5f6..."
  captured_at: "2026-06-29T14:30:00Z"
```

### CI integration

The existing CI step at `python-tests.yml:139` runs `temper timing check --ci --json`. This command loads all entries from `timing_baselines.yaml`, measures each (board, pipeline, stage) tuple, and compares against the baseline. When RouterV6Pipeline and PipelineOrchestrator baselines are added to the manifest, they are automatically included in the check — no CI workflow changes needed beyond removing the `continue-on-error: true` guard once baselines are committed.

---

## Implementation Units

### U1. Capture RouterV6Pipeline and PipelineOrchestrator baselines

**Goal:** Run `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed` and `temper timing baseline --pipeline PipelineOrchestrator --board temper_placed` to populate `timing_baselines.yaml` with new pipeline entries. Add `--sub-steps` flag to the baseline command for Stage 2 sub-step capture.

**Requirements:** R1, R2, R5

**Dependencies:** Plan 022 U1–U3 (timing measurement contract, baseline CLI, manifest schema)

**Files:**
- `packages/temper-placer/src/temper_placer/cli/timing.py` (modify — ensure `--pipeline` flag resolves RouterV6Pipeline and PipelineOrchestrator; add `--sub-steps` flag)
- `packages/temper-placer/src/temper_placer/profiling/timing_gate.py` (modify — add RouterV6Pipeline and PipelineOrchestrator measurement paths if not already handled by generic pipeline dispatch)
- `power_pcb_dataset/timing_baselines.yaml` (modify — add RouterV6Pipeline and PipelineOrchestrator entries)

**Approach:**

1. **RouterV6Pipeline measurement.** The `measure_stage_timing()` function already takes a `pipeline` parameter. When `pipeline="RouterV6Pipeline"`, it constructs `RouterV6Pipeline(profiler=profiler)` and runs it against the board. The profiler records per-stage wall-clock for Stage 1 (escape vias), Stage 2 (channel analysis — aggregate), Stage 3 (topological routing), Stage 4 (geometric realization), and Stage 5 (post-processing).

2. **PipelineOrchestrator measurement.** When `pipeline="PipelineOrchestrator"`, constructs `PipelineOrchestrator` from `PipelineConfig` with appropriate board input, runs the pipeline, and the `PipelineProfiler` captures per-phase wall-clock for each of the 8 phases. Skipped phases (per config) produce no timing entry (no-op phases don't need baselines).

3. **Stage 2 sub-steps.** Add `--sub-steps` flag to `timing baseline`. When active, after measuring Stage 2, the profiler's `StageTiming.sub_steps` dict is extracted and individual sub-step entries are written as separate manifest entries with `stage: "stage2.obstacle_map"`, `stage: "stage2.routing_space"`, etc. Once committed to the manifest, `temper timing check` covers sub-step entries automatically (K3).

4. **Manifest population.** Running `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed` appends RouterV6Pipeline entries to `timing_baselines.yaml`. Existing DeterministicPipeline entries are unchanged (R5, Plan 022 R12 pattern).

**Stage names for the manifest:**

| Pipeline | Stage | Description |
|---|---|---|
| RouterV6Pipeline | stage1 | Escape via generation |
| RouterV6Pipeline | stage2 | Channel analysis (aggregate, 8 sub-steps) |
| RouterV6Pipeline | stage2.obstacle_map | Stage 2 sub-step |
| RouterV6Pipeline | stage2.routing_space | Stage 2 sub-step |
| RouterV6Pipeline | stage2.channel_skeleton | Stage 2 sub-step |
| RouterV6Pipeline | stage2.channel_widths | Stage 2 sub-step |
| RouterV6Pipeline | stage2.occupancy_grid | Stage 2 sub-step |
| RouterV6Pipeline | stage2.layer_capacity | Stage 2 sub-step |
| RouterV6Pipeline | stage2.routing_demand | Stage 2 sub-step |
| RouterV6Pipeline | stage2.bottleneck_analysis | Stage 2 sub-step |
| RouterV6Pipeline | stage3 | Topological routing (SAT) |
| RouterV6Pipeline | stage4 | Geometric realization (A*) |
| RouterV6Pipeline | stage5 | Post-processing (smoothing, vias, width, results) |
| PipelineOrchestrator | input | PCB + constraint loading |
| PipelineOrchestrator | semantic | Loop extraction, ownership assignment |
| PipelineOrchestrator | topological | Adjacency/separation reasoning |
| PipelineOrchestrator | preflight | Constraint satisfiability verification |
| PipelineOrchestrator | geometric | JAX gradient descent placement optimization |
| PipelineOrchestrator | routing | Routability check via RouterV6Pipeline |
| PipelineOrchestrator | refinement | Placement-routing iteration loop |
| PipelineOrchestrator | output | Write placed PCB, reports |

**Sub-step handling detail:** Stage 2 sub-steps use the sub-step timer in `Stage2Orchestrator.run()` (`stage2_orchestrator.py:68`). The `PipelineProfiler` exposes sub-step timings via `StageTiming.sub_steps`. The timing gate reads `ProfileReport.stage_timings["stage2"].sub_steps` to capture per-sub-step entries. Each sub-step gets its own manifest entry with `stage: "stage2.<sub_step_name>"` and `pipeline: RouterV6Pipeline`.

**Patterns to follow:**
- Plan 022 U2 for `temper timing baseline` CLI dispatch
- Plan 022 U3 for manifest schema (non-breaking addition)
- `PipelineProfiler.sub_step()` at `instrumentation.py` for sub-step timer contract
- `Stage2Orchestrator.run()` at `stage2_orchestrator.py:62-71` for sub-step measurement integration point

**Test scenarios:**
- `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed` produces entries for stages 1-5 with `wall_ms_mean > 0`.
- `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed --sub-steps` additionally produces entries for all 8 stage2 sub-steps.
- `temper timing baseline --pipeline PipelineOrchestrator --board temper_placed` produces entries for executed phases with `wall_ms_mean > 0`.
- Existing DeterministicPipeline entries in `timing_baselines.yaml` are unmodified after running baseline on RouterV6Pipeline (R5).
- Running baseline on a board with no routing data (near-zero stage timings) still produces valid entries (uses floor-ms logic from Plan 022 U4).
- PipelineOrchestrator constructs from defaults on clean checkout using the board path from golden_manifest.yaml. If additional config is needed, the timing baseline command raises a clear error with the missing config key.

**Verification:** Run `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed`; inspect `timing_baselines.yaml` for new RouterV6Pipeline entries. Run `temper timing baseline --pipeline PipelineOrchestrator --board temper_placed`; inspect for new PipelineOrchestrator entries. Confirm DeterministicPipeline entries are unchanged.

---

### U2. CI integration — include router stages in timing check

**Goal:** Ensure that `temper timing check --ci --json` in CI covers RouterV6Pipeline and PipelineOrchestrator baselines once they are committed to the manifest. Remove the `continue-on-error: true` guard. Verify that the combined check (all three pipelines) completes within CI time budget.

**Requirements:** R3, R4

**Dependencies:** U1 (baselines must be committed to manifest)

**Files:**
- `.github/workflows/python-tests.yml` (modify — remove `continue-on-error: true` on timing check step, ensure time budget accommodates router stages)
- `packages/temper-placer/src/temper_placer/cli/timing.py` (modify if needed — ensure `check` command iterates all pipeline entries from manifest)

**Approach:**

1. **The check command already iterates all manifest entries.** `temper timing check` loads all entries from `timing_baselines.yaml` (Plan 022 U4, line 383) and checks each `(board, pipeline, stage)` tuple. When RouterV6Pipeline and PipelineOrchestrator entries exist in the manifest, they are automatically included — no command-line changes needed.

2. **CI step update.** The existing timing check step at `python-tests.yml:139`: 
   ```yaml
   - name: Per-stage timing regression check
     run: uv run temper timing check --ci --json
     continue-on-error: true  # temper CLI may not be installed; temper-N6-U8
   ```
   Remove `continue-on-error: true` once baselines are committed and verified passing. The comment references `temper-N6-U8` which is addressed by this plan.

3. **Time budget verification.** DeterministicPipeline check takes <2 minutes (Plan 022 SC3). RouterV6Pipeline adds ~2-3 minutes (Stage 4 A* pathfinding dominates). PipelineOrchestrator adds ~3-5 minutes (JAX geometric optimization). Combined check: ~7-10 minutes. The `checks` job has `timeout-minutes: 15` — within budget. If the combined time exceeds budget, the timing check can be moved to a separate job with its own timeout.

4. **Path triggers.** The existing `paths` filter in `python-tests.yml` already includes `power_pcb_dataset/timing_baselines.yaml` — baseline updates trigger the check. No path filter changes needed.

5. **Ancestry check.** The `--ci` flag's git ancestry enforcement (Plan 022 U4, line 463) applies uniformly to all manifest entries regardless of pipeline. RouterV6Pipeline and PipelineOrchestrator baselines must be captured at a commit that is an ancestor of PR HEAD.

**Patterns to follow:**
- Plan 022 U5 for CI integration pattern (timing check step, timeout, path triggers)
- Plan 009 U7 for ancestry check pattern

**Test scenarios:**
- PR that doesn't touch router code: `temper timing check` passes for all three pipelines.
- PR that slows RouterV6Pipeline Stage 4 by 30%: `temper timing check` fails with `FAIL: RouterV6Pipeline/stage4 (+30.0%, limit: +20.0%)`.
- PR that slows PipelineOrchestrator geometric phase: `temper timing check` fails with `FAIL: PipelineOrchestrator/geometric`.
- PR with intentional router slowdown + regenerated baselines: `temper timing check` passes for all pipelines.
- CI timing check completes in under 10 minutes for all three pipelines on `temper_placed` board.

**Verification:**
1. Commit RouterV6Pipeline and PipelineOrchestrator baselines.
2. Open a PR that introduces `time.sleep(0.5)` in RouterV6Pipeline Stage 4.
3. CI timing check step fails.
4. Regenerate baseline with `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed --stage stage4 --overwrite`, commit to same PR.
5. CI timing check step passes.

---

## Key Technical Decisions

**K1: Reuse existing `--pipeline` flag, not create new commands.** Plan 022 U2 already specifies `--pipeline RouterV6Pipeline` and the manifest schema supports multi-pipeline entries. Adding new pipelines is a matter of passing the right string — no CLI redesign needed.

**K2: Sub-steps as separate manifest entries with dotted names (`stage2.obstacle_map`).** The manifest schema uses `stage: string` (not an enum). Dotted names (`stage2.obstacle_map`) are valid YAML keys and unambiguous identifiers. The `PipelineProfiler.sub_steps` dict uses the same sub-step names as keys — direct mapping. Sub-steps are optional (`--sub-steps` flag) to keep CI time manageable and because sub-step timing is primarily useful during Stage 2 decomposition work.

**K3: `temper timing check` auto-covers all pipelines in the manifest.** No per-pipeline opt-in. The check reads the manifest and checks every entry. This ensures that once baselines are committed, enforcement is automatic — no "forgot to add the new pipeline to CI" failure mode.

**K4: Continue-on-error removal is gated on baselines being committed.** The `continue-on-error: true` guard in CI exists because `temper timing check` fails when there are no baselines to check (empty manifest → "No timing baselines to check"). Once RouterV6Pipeline and PipelineOrchestrator baselines are committed alongside DeterministicPipeline baselines, the manifest is never empty and the guard can be removed.

**K5: Single board baseline (`temper_placed`).** Following Plan 022's initial scope, baselines are captured on a single canonical board (`temper_placed`). Additional boards can be added non-breakingly (R12). The `temper_placed` board exercises all RouterV6Pipeline stages (has nets to route) and all PipelineOrchestrator phases (has components to place).

---

## Scope Boundaries

### In Scope
- RouterV6Pipeline stage baselines: Stage 1 (escape vias), Stage 2 (channel analysis — aggregate), Stage 3 (topological routing), Stage 4 (geometric realization), Stage 5 (post-processing)
- RouterV6Pipeline Stage 2 sub-step baselines: 8 micro-stages (opt-in via `--sub-steps`)
- PipelineOrchestrator phase baselines: 8 phases (input, semantic, topological, preflight, geometric, routing, refinement, output)
- `temper timing baseline --pipeline RouterV6Pipeline` and `temper timing baseline --pipeline PipelineOrchestrator`
- `temper timing check` auto-coverage of all pipeline baselines in manifest
- CI timing check step enforcement for all three pipelines
- 20% margin with 10ms floor (same threshold as DeterministicPipeline)
- Non-breaking addition to `timing_baselines.yaml` (R12 pattern)
- Single canonical board (`temper_placed`) for initial baselines

### Deferred for Follow-Up Work
- **Sub-step timing gate for Stage 4 A* pathfinding.** `RouteProfileStats` in `astar_core_numba` captures per-path latency, but sub-step-level timing for Stage 4 is not wired into `PipelineProfiler` sub-steps. When that wiring is done, `--sub-steps stage4` can be added.
- **Additional canonical boards for router diversity.** `temper_placed` has 23 nets — sufficient for initial coverage. Boards with different net densities (e.g., `complex_board` with 50+ nets) can be added non-breakingly when discovered regressions suggest coverage gaps.
- **Baseline auto-tightening for router stages.** Same as Plan 022 deferred scope — if CI observes consistent timing well below baseline, the gate could self-tighten. Deferred until enough historical data exists.
- **RouterV6Pipeline Stage 0 (PCB parse) and Stage 0.5 (legalization).** These stages run as part of pipeline initialization but are not separately profiled. When they get PipelineProfiler instrumentation, baselines can be added non-breakingly.

### Out of Scope
- Modifying RouterV6Pipeline stages to expose additional profiling hooks — the existing `PipelineProfiler` instrumentation is sufficient.
- Sub-step-level timing for stages other than Stage 2.
- Introducing new gate thresholds or margins — uses the same 20% margin / 10ms floor as DeterministicPipeline.
- `temper timing regenerate` changes — the existing command works for any pipeline.

---

## Dependencies / Prerequisites

**Upstream dependencies (must exist before this work):**
- **Plan 022 (Per-Stage Timing Regression Gate) — implemented.** Provides `measure_stage_timing()`, `TimingResult`, `TimingReport`, `temper timing` CLI group, `timing_baselines.yaml` manifest, and CI check step. The infrastructure supports multi-pipeline baselines by design.
- **Plan 015 (Pipeline Profiling Toolkit) — PipelineProfiler and Stage2Orchestrator sub-step timers.** The `PipelineProfiler.sub_step("stage2", stage.name)` call in `Stage2Orchestrator.run()` provides the per-sub-step timing data.

**New dependencies introduced:**
- None. All code paths already exist — this plan adds manifest entries and exercises existing CLI flags.

**Downstream consumers (work unblocked by this):**
- RouterV6Pipeline decomposition work (strangler fig) — developers get timing gate enforcement on their changes.
- PipelineOrchestrator changes — phase-level slowdowns from placement or routing changes are detected.
- Plan 015 U6 (Autoprof) — router stage baselines provide "before" data for router optimization experiments.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| RouterV6Pipeline Stage 4 (A*) runtime varies significantly between CI runs | Medium (false failures) | Low | Stage 4 is CPU-bound (A* pathfinding), not I/O-bound. GitHub Actions `ubuntu-latest` has consistent CPU performance. The 20% margin accommodates ±5% variance. If false positives occur, the `--margin` flag is tunable per invocation. |
| JAX geometric optimization in PipelineOrchestrator has high warmup overhead | Medium (inflated timing on first run) | Low | Plan 022 R3 already specifies warmup exclusion. The geometric phase runs JAX gradient descent; the warmup pass includes JIT compilation. Measurement uses runs 2..N. |
| Combined timing check (3 pipelines) exceeds 15-minute CI timeout | Medium (CI job timeout) | Low | See U2 time budget analysis: DeterministicPipeline ~2 min, RouterV6Pipeline ~3 min, PipelineOrchestrator ~5 min = ~10 min total. 15-minute timeout has headroom. If over budget, split into separate job. |
| Stage2Orchestrator sub-step profiler not integrated at baseline capture time | Low (missing sub-step data) | Medium | The `--sub-steps` flag is optional. If `PipelineProfiler.sub_step()` is not called, sub-steps are silently absent. The flag only activates if the profiler is active. |
| `temper timing check` with no baselines exits with message, not error (Plan 022 U4 test scenario) | Low (CI passes silently) | Low | Once baselines are committed for all three pipelines, the manifest is never empty. The empty-manifest case is only possible before first baseline capture — not after this plan lands. |

---

## System-Wide Impact

- **Developer workflow:** After this plan lands, any PR that changes RouterV6Pipeline or PipelineOrchestrator code must pass the timing gate. Developers run `temper timing check` locally (same as for DeterministicPipeline) to verify before pushing.
- **CI pipeline:** The existing `timing-check` step in `python-tests.yml` automatically covers all three pipelines. Job time increases by ~5-8 minutes. The `continue-on-error: true` guard is removed.
- **Repository layout:**
  - `power_pcb_dataset/timing_baselines.yaml` grows by ~20 new entries (5 RouterV6Pipeline stages + 8 sub-steps + 8 PipelineOrchestrator phases = ~21 entries at ~300 bytes each ≈ 6 KB).
  - `packages/temper-placer/src/temper_placer/cli/timing.py` may need minor changes for `--sub-steps` flag and RouterV6Pipeline/PipelineOrchestrator dispatch.
  - `packages/temper-placer/src/temper_placer/profiling/timing_gate.py` may need minor changes for RouterV6Pipeline and PipelineOrchestrator measurement paths.
  - `.github/workflows/python-tests.yml` — remove `continue-on-error: true` on timing check step.
- **No changes to `pyproject.toml`, firmware, PCB designs, or KiCad schematics.**

---

## Success Criteria

- **SC1.** `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed` produces entries in `timing_baselines.yaml` for stages 1-5 with `wall_ms_mean > 0`.
- **SC2.** `temper timing baseline --pipeline RouterV6Pipeline --board temper_placed --sub-steps` additionally produces entries for all 8 stage2 sub-steps.
- **SC3.** `temper timing baseline --pipeline PipelineOrchestrator --board temper_placed` produces entries for all 8 orchestrator phases.
- **SC4.** `temper timing check` covers all three pipelines and exits 0 on a clean checkout with committed baselines.
- **SC5.** CI timing check step in `python-tests.yml` blocks PRs that exceed the 20% threshold on any RouterV6Pipeline or PipelineOrchestrator stage.
- **SC6.** Existing DeterministicPipeline baselines are unaffected — verified by `git diff` on those entries before and after adding new pipeline entries.

---

## Outstanding Questions

- **OQ1 (Stage 2 sub-step granularity):** Should sub-steps be captured by default (always-on) or only with `--sub-steps` opt-in? **Initial answer in this plan:** Opt-in via `--sub-steps`. Sub-step timing is most useful during Stage 2 decomposition work; always-on would increase CI time by ~1 minute for 8 additional stages with marginal value on PRs that don't touch Stage 2.
- **OQ2 (PipelineOrchestrator phase baselines on clean checkout):** The orchestrator requires a fully configured pipeline environment (KiCad board, constraints YAML, JAX warmup). Can the baseline command construct this from `golden_manifest.yaml` without additional configuration? **Initial answer in this plan:** The `PipelineConfig` can be constructed from defaults and the board path from `golden_manifest.yaml`. If additional config is needed, `temper timing baseline --pipeline PipelineOrchestrator` can accept a `--config` flag.
- **OQ3 (Stage 0.5 legalization):** Legalization is opt-in in `RouterV6Pipeline`. Should it have a baseline? **Initial answer in this plan:** No — legalization is not separately profiled in the current `PipelineProfiler` instrumentation. When it gets a profiler hook, a baseline can be added non-breakingly.
- **OQ4 (Continue-on-error guard removal timing):** Should the guard be removed in the same PR that commits the baselines, or in a follow-up? **Initial answer in this plan:** Same PR. The commit includes both the new baselines and the CI change. If the check fails, the PR itself can't merge — which is the desired behavior (you can't commit baselines unless they pass).

---

## Sources & References

- Origin: Plan 022 OQ4 (multi-pipeline baselines) and deferred scope section (line 623)
- Timing gate infrastructure: `docs/plans/2026-06-22-022-feat-per-stage-timing-regression-gate-plan.md`
- Profiling infrastructure: `docs/plans/2026-06-22-015-feat-pipeline-profiling-validation-toolkit-plan.md`
- Timing measurement contract: `packages/temper-placer/src/temper_placer/profiling/timing_gate.py`
- PipelineProfiler: `packages/temper-placer/src/temper_placer/profiling/instrumentation.py`
- Stage2Orchestrator sub-step timers: `packages/temper-placer/src/temper_placer/router_v6/stage2_orchestrator.py:62-71`
- RouterV6Pipeline stages: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:317-573`
- PipelineOrchestrator phases: `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py:36-46` (PipelinePhase enum), `orchestrator.py:209-218` (phase dispatch)
- Timing gate CLI: `packages/temper-placer/src/temper_placer/cli/timing.py`
- Timing baselines manifest: `power_pcb_dataset/timing_baselines.yaml`
- CI timing check step: `.github/workflows/python-tests.yml:139-143`
- Non-breaking addition pattern: Plan 009 U8 (golden fixture ladder)
- Stage stage adapter: `packages/temper-placer/src/temper_placer/adapters/router_v6_stage_adapter.py`
- RouteProfileStats: `packages/temper-placer/src/temper_placer/router_v6/astar_core_numba.py`
