---
date: 2026-06-22
type: feat
origin: docs/ideation/2026-06-22-pipeline-profiling-correctness-speed-ideation.md
status: completed
---

# Plan: Pipeline Profiling & Validation Toolkit

## Problem Frame

The temper-placer has three routing pipelines (PipelineOrchestrator, RouterV6Pipeline, DeterministicPipeline) with scattered profiling — 6+ ad-hoc profiling scripts, broken perf_counter duplicates, ProfileStats collected but never consumed, and Stage 2's sub-steps with zero timing instrumentation. There is no systematic validation of routing output correctness: Hypothesis PBT and golden fixtures are absent. Every optimization cycle is manual.

This plan builds a layered profiling and validation toolkit designed for parallel agent dispatch: instrumentation that auto-measures every pipeline stage, validation that catches correctness regressions, and an autoprof experiment loop that connects profiling data to targeted fixes.

## High-Level Technical Design

Three independent layers, dispatched in parallel after the shared instrumentation foundation:

```
Layer 1: Instrumentation                  Layer 2: Validation
┌──────────────────────────┐              ┌──────────────────────────┐
│ UnifiedPipelineProfiler  │              │ Hypothesis PBT Suite     │
│ Stage 2 Sub-Step Timers  │              │ Golden Fixture Tests     │
│ Wire ProfileStats output │              │                          │
└────────────┬─────────────┘              └────────────┬─────────────┘
             │                                         │
             └──────────────┬──────────────────────────┘
                            │
                    Layer 3: Autoprof
              ┌──────────────────────────┐
              │ GPBM Autoprof Experiment │
              │ Bottleneck identification│
              │ Before/after delta table │
              └──────────────────────────┘
```

*This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

## Output Structure

```
packages/temper-placer/src/temper_placer/profiling/
    __init__.py
    instrumentation.py        # UnifiedPipelineProfiler + Stage2 timers
    validation/               # Hypothesis PBT + golden fixtures
        __init__.py
        invariants.py
        fixtures/
    autoprof.py               # GPBM experiment loop integration
packages/temper-placer/tests/
    test_instrumentation.py
    test_validation.py
    test_autoprof.py
```

## Implementation Units

### U1. Unified Pipeline Profiler

**Goal:** Replace scattered profiling scripts with a single profiling module that auto-instruments pipeline stages, fixes broken perf_counter calls, wires ProfileStats output, and writes structured JSON.

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/profiling/__init__.py` (add PipelineProfiler/ProfileReport exports)
- Create: `packages/temper-placer/src/temper_placer/profiling/instrumentation.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` (fix broken double-perf_counter at lines ~730-757)
- Modify: `packages/temper-placer/src/temper_placer/routing/maze_router.py` (expose ProfileStats via get_profile_stats())
- Create: `packages/temper-placer/tests/test_instrumentation.py`

**Approach:**
- `PipelineProfiler` context manager with `__enter__` / `__exit__` that records wall-clock and CPU time per stage
- `ProfileReport` dataclass: per-stage wall-clock, cpu-time, iterations; JSON-serializable with optional sub-step breakdown
- Wire into pipeline entry points: `PipelineOrchestrator`, `RouterV6Pipeline`, `DeterministicPipeline` — the profiler is passed via constructor injection or a `profiler=` parameter on the `run()` method. Each pipeline's injection pattern is documented in the profiler module docstring
- Fix the broken `perf_counter()` duplicates in `astar_pathfinding.py` — replace doubled timing block with single block, add `per_path_latency_ms` to `ProfileReport`
- Expose MazeRouter `ProfileStats` fields (numba_time_ms, python_time_ms, dist_map_ms) via `get_profile_stats()` method; `PipelineProfiler` merges these into the report
- Output: Emit `PipelineMetricsRecord` records to the canonical `pipeline_metrics.jsonl` (Plan 010 K2) or standalone JSON via `ProfileReport.to_json()`

**Patterns to follow:** `losses/base.py:record_timings()` for JAX-aware timing with `block_until_ready()`; `maze_router.py:ProfileStats` dataclass

**Test scenarios:**
- Context manager: entering and exiting records wall-clock > 0 and returns valid ProfileReport
- Sub-steps: nested context manager produces hierarchical timing breakdown with parent > sum of children
- Broken perf_counter fix: routing a net on a small test board produces a single per-path latency value, not a corrupted pair
- ProfileStats wiring: after routing, `ProfileReport` contains `numba_time_ms` and `dist_map_ms` populated from MazeRouter stats
- JSON output: `ProfileReport.to_json()` produces valid, parseable JSON with fields present even when zero

**Verification:** Any of the 3 pipelines can be run with a profiler and produce a structured JSON report. Broken perf_counter duplicates removed.

---

### U2. Stage 2 Sub-Step Instrumentation

**Goal:** Add per-sub-step timers to all 7 Stage 2 channel analysis sub-steps, surfacing each sub-step's timing in the unified profiler output.

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (`_run_stage2` method)
- Modify: `packages/temper-placer/tests/test_instrumentation.py` (add Stage 2 specific tests)

**Approach:**
- In `RouterV6Pipeline._run_stage2()`, wrap each of the 7 logical sub-steps with `profiler.sub_step(name)` context manager
- Sub-steps (matching the actual code at lines 370-458): obstacle map + routing space, channel skeleton, channel widths, occupancy grid, layer capacity, routing demand, bottleneck analysis
- Sub-step timings nest under the parent Stage 2 entry in the `ProfileReport`
- Use `time.perf_counter_ns()` for sub-step timing (finer resolution)
- Output appears in the same JSON / `measurements.jsonl` as the parent profiler report

**Patterns to follow:** `pipeline.py:_run_stage2` existing sub-step calls at lines 370-458; U1's `PipelineProfiler.sub_step()` API

**Test scenarios:**
- Run Stage 2 on a test board with profiler enabled — output contains 7 sub-step entries with non-zero wall-clock
- Sub-step timings sum approximately to parent Stage 2 timing (within 5% tolerance for overhead)
- Empty board (no nets): sub-steps still execute and produce timing entries (don't crash on empty)

**Verification:** `measurements.jsonl` shows which Stage 2 sub-step dominates latency on the Piantor keyboard test board.

---

### U3. Wire ProfileStats into Unified Profiler

**Goal:** Wire the existing MazeRouter ProfileStats fields into the unified profiler output and write integration tests validating the perf-counter fix from U1.

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/routing/maze_router.py` (add `get_profile_stats()` method)
- Modify: `packages/temper-placer/tests/test_instrumentation.py` (add integration tests)

**Approach:**
- Add `get_profile_stats()` method to MazeRouter exposing `self.stats.profile` fields (numba_time_ms, python_time_ms, astar_total_ms, dist_map_ms)
- Write integration tests verifying U1's perf_counter fix produces valid per-path latencies
- The `PipelineProfiler` calls `get_profile_stats()` after routing and merges data into `ProfileReport`

**Patterns to follow:** `ProfileStats` dataclass; U1's `ProfileReport` schema

**Test scenarios:**
- After a routing run with `PipelineProfiler`, the report contains `numba_time_ms`, `python_time_ms`, and `astar_total_ms` matching the router's internal counters
- Per-path latency: route 10 nets, each has exactly one latency entry (no duplicates), all values > 0
- Backward compat: existing stats printing in `scripts/profile_routing.py` still works (reads same fields)

**Verification:** Running `scripts/profile_routing.py` produces per-path latencies that are real (not corrupted), matching the unified profiler output.

---

### U4. Hypothesis PBT for Geometric Routing Invariants

**Goal:** Build a Hypothesis property-based test suite that generates random-but-valid board layouts and asserts geometric routing invariants at DeterministicPipeline stage boundaries.

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/src/temper_placer/profiling/validation/__init__.py`
- Create: `packages/temper-placer/src/temper_placer/profiling/validation/invariants.py`
- Create: `packages/temper-placer/tests/test_validation.py`

**Approach:**
- Hypothesis strategy `valid_board_layout()` that generates: 1-8 components with random positions, 2-16 pads per component, 1-4 layers, random obstacle rectangles. This is constrained PBT input generation — NOT the deferred synthetic board generator for production-scale stress testing
- Invariant assertions, each as a separate Hypothesis test:
  - **Connectivity**: For every net, the routed output contains a continuous path connecting all pads — no dangling segments
  - **Clearance**: Distance between traces of different nets >= `min_clearance`
  - **Non-overlap**: No two traces from different nets occupy the same grid cell on the same layer without a via
  - **Boundary containment**: All traces and vias lie within the board outline
  - **Net conservation**: Input net count == output net count; no net is lost or created
  - **Determinism**: Running the same input twice produces identical output (bit-exact)
- Each invariant test configures `max_examples=1000` for CI, with shrinking enabled
- Uses `DeterministicPipeline` for its immutable `BoardState` guarantee
- `@settings(deadline=None)` to disable Hypothesis timing deadlines

**Patterns to follow:** `tests/deterministic/test_production_regressions.py` for pipeline-level integration tests

**Test scenarios:**
- Connectivity: strategy generates a 2-pad net with a blocking obstacle — routing produces a path going around it while staying connected
- Clearance: two adjacent nets with minimal separation must not have crossing or touching traces
- Boundary: a pad near the board edge must not produce traces exceeding board dimensions
- Determinism: running the same random board twice with identical seed produces byte-identical `BoardState`
- Empty board: strategy generates a valid board with zero nets — pipeline runs without crashing
- Shrinking: intentionally break a clearance invariant and verify Hypothesis produces a minimal counterexample with <= 5 components

**Verification:** `pytest tests/test_validation.py -k "hypothesis"` runs 1000 random boards without invariant failures. If an invariant fails, Hypothesis prints the minimal reproducer.

---

### U5. Golden Fixture Snapshot Tests

**Goal:** Commit golden fixture files containing full routing output for curated input boards. Tests assert output equality against goldens.

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/src/temper_placer/profiling/validation/fixtures/` (directory)
- Create: `packages/temper-placer/src/temper_placer/profiling/validation/fixtures/piantor_left_input.json`
- Create: `packages/temper-placer/src/temper_placer/profiling/validation/fixtures/piantor_left_golden.json`
- Modify: `packages/temper-placer/tests/test_validation.py` (add golden fixture test)

**Approach:**
- Input fixture: a minimal serialized `BoardState` representing a known input board (start with Piantor Left, reduced to 3-5 nets for speed)
- Golden fixture: the `DeterministicPipeline.run(input)` output, serialized as JSON with sorted keys for diff-ability
- Non-deterministic fields (timestamps, runtime, iteration counts) are stripped from comparison
- Floating-point coordinates rounded to 6 decimal places for comparison stability
- Test: `assert serialize(pipeline.run(input_fixture)) == golden_fixture`
- Regeneration: `python -m temper_placer.profiling.validation regen-goldens` regenerates all golden files and prints diffs

**Patterns to follow:** `tests/regression/test_closure.py` for pipeline-level fixture loading; `regression/corpus_runner.py` for baseline comparison

**Test scenarios:**
- Exact match: running the deterministic pipeline on the input fixture produces output identical to the committed golden
- Intentional change: modifying a cost parameter causes the test to fail with a diff showing the changed coordinates
- Regeneration: running `regen-goldens` overwrites existing goldens and succeeds
- Missing golden: if a golden file is deleted, the test fails with a clear message (not an opaque file-not-found traceback)
- Floating-point stability: the same board run on different machines produces identical output within 6-decimal-place tolerance

**Verification:** Modifying a routing heuristic and running the golden test produces a diff. Reverting the change makes the test pass again.

---

### U6. GPBM Autoprof Experiment Loop

**Goal:** Build an `autoprof` experiment type that consumes Layer 1 profiling data to identify bottlenecks and produce before/after delta tables.

**Dependencies:** U1, U2, U3

**Files:**
- Create: `packages/temper-placer/src/temper_placer/profiling/autoprof.py`
- Create: `packages/temper-placer/tests/test_autoprof.py`

**Approach:**
- `AutoprofExperiment` class with two phases:
  1. **Measure**: Runs the pipeline on benchmark boards with `PipelineProfiler` enabled, collects `ProfileReport` per board
  2. **Compare**: Takes a "before" profile (stored from a previous run) and an "after" profile, produces a delta table: stage name, before p95, after p95, delta %, direction
- Integrates with GPBM `measurements.jsonl`: each experiment run appends a record with experiment type `autoprof`, the identified bottleneck, and the delta table
- Does NOT suggest or apply fixes — identifies targets and measures their impact
- Delta classification: configurable thresholds (default: >5% significant, 1-5% marginal, <1% noise)
- The autoprof experiment only consumes Layer 1 profiling data (timing). Layer 2 validation correctness gates run independently via pytest; autoprof references their pass/fail status as a metadata field in the experiment record

**Patterns to follow:** GPBM `measure.py` for measurement collection; `experiments/framework/MEASUREMENT_SPEC.yaml` for metric definitions

**Test scenarios:**
- Single board: autoprof on a single board produces a ProfileReport and identifies a bottleneck stage by name
- Delta table: running autoprof twice (unchanged code) produces a delta table where all stages show <1% change
- Intentional slowdown: adding `time.sleep(0.05)` to Stage 2 makes autoprof flag Stage 2 as regressed with >5% delta
- GPBM integration: autoprof run appends a valid record to `measurements.jsonl` with experiment type "autoprof"
- Multiple boards: running on 2+ boards identifies the bottleneck as the stage with the highest p95 across all boards
- Missing baseline: running autoprof with a non-existent baseline name produces a clear error message

**Verification:** Running `autoprof` on the Piantor board produces a Markdown delta table comparing against a stored baseline. Modifying a pipeline stage to be 10% slower produces a delta row showing regression.

---

## Implementation Order

```
U1 (Unified Profiler) ── foundation, must go first
├── U2 (Stage 2 Sub-Steps) ── depends on U1
└── U3 (Wire ProfileStats) ── depends on U1

U4 (Hypothesis PBT) ── independent, anytime
U5 (Golden Fixtures) ── independent, anytime

U6 (Autoprof Loop) ── depends on U1, U2, U3
```

Parallel dispatch: {U2, U3} after U1 completes; U4 and U5 at any time (including during U1-U3 work); U6 after U1-U3 complete.

## Scope Boundaries

### Deferred to Follow-Up Work
- CI integration for profiling gates (differential flame graphs, benchmark regression detection)
- DRC fence overhead quantification via A/B probe
- Synthetic board generator for production-scale stress testing
- ProfileStats time-series observatory / dashboard (including historical trend queries)
- Numba vs Python speedup ratio CI guardrail
- Routing quality CI gates (baseline allowlist + hard-block + ratchet)

## Key Decisions

- **Layer isolation**: Instrumentation and validation are independent — no profiling code imports validation code. Enables parallel implementation.
- **ProfileReport as the seam**: The `ProfileReport` dataclass is the single output format for Layer 1 that Layer 3 (autoprof) and future CI gates consume.
- **GPBM format reuse**: Extend existing `measurements.jsonl` / GPBM format rather than invent a second metric pipeline.
- **Correctness-first validation**: Hypothesis tests and golden fixtures are runtime gates that fail on any violation — no tolerance bands, no allowlists.
- **DeterministicPipeline as PBT target**: Uses `DeterministicPipeline` rather than `RouterV6Pipeline` because its immutable `BoardState` guarantees repeatability.
- **Autoprof only consumes Layer 1**: Validation results are referenced as metadata, not as inputs the autoprof loop depends on for its core delta-table function.
- **Profiler injection via constructor**: Each pipeline accepts the profiler via its constructor (`__init__`) or as a keyword argument to `run()` — the profiler module's docstring documents the pattern per pipeline.
