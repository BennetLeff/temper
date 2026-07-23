# Performance Profiling Setup — Plan

`artifact_contract: ce-unified-plan/v1` · `artifact_readiness: requirements-only` · `product_contract_source: ce-brainstorm`

## Goal Capsule

**Objective:** Wire the existing `PipelineProfiler` instrumentation into the 4 remaining hot paths (CP-SAT loop, KiCad I/O, copper coverage, thermal FDM) and add flame-graph generation to CI. Requires zero new annotation framework — only extending existing `profiler.stage()`/`sub_step()` calls.

**Product authority:** temper-placer maintainers.
**Open blockers:** None — all required infrastructure already exists in `profiling/`.

## Quality Strategy

All implementation MUST follow three verification disciplines:

1. **TDD (Test-Driven Development).** Write the timing assertion before wiring the instrumentation point. Every `profiler.sub_step()` call starts as a failing test that asserts the stage name appears in `ProfileReport.to_json()` output and the measured wall-time is within expected bounds. No instrumentation is accepted without a test that fails before it passes.

2. **PBT (Property-Based Testing).** For profiling output, use Hypothesis to verify invariants across random board configurations: the JSON output is valid and complete (all stages present, no negative durations), wall-time is additive (sum of sub-steps ≤ parent stage), and the flame-graph folded-stack format is valid per the Brendan Gregg spec. At least 2 invariant properties per profiling scenario.

3. **Mathematical Induction (Base-Case Proofs).** Prove that the profiling instrumentation is sound across the full pipeline:
   - **Base case (smoke board, 1 stage):** A single `profiler.stage()` call produces valid output.
   - **Inductive step:** Prove that if profiling instrumentation is correct for a pipeline of n stages, it remains correct when a new instrumented stage n+1 is added — the stage tree is well-formed, parent-child time accounting is consistent (parent ≥ sum of children), and no stage is double-counted or orphaned.
   - This is a **rigor requirement, not an implementation detail** — the plan artifact must include a section documenting the base case and induction hypothesis before implementation begins.

## Product Contract

### Key Decisions

- `session-settled:` No new profiling framework. Use existing `PipelineProfiler` + `ProfileReport` + `timing_gate.py`.
- `session-settled:` py-spy for sampling/flame graphs, cProfile for CI compatibility, samply for macOS Rust profiling.
- `session-settled:` Profiling does NOT block PR merge. Use `continue-on-error: true` with manual override via `skip-perf` label.
- `session-settled:` A* pathfinding is already fully instrumented (RouteProfileStats); it is P1 only for flame-graph generation.

### Hot Path Priority

| Priority | Path | Status | Action |
|:---:|------|--------|--------|
| P1 | A* pathfinding | Already instrumented | Add py-spy flame graphs to CI artifacts |
| P2 | CP-SAT loop | Wall-clock only | Wrap rounds with `profiler.stage("cp_sat_round_N")` |
| P3 | KiCad parser/writer | None | Add `profiler.sub_step` at parse/write entry points |
| P4 | Copper coverage | None | Wrap `copper_coverage_grid()` with `profiler.sub_step("physics", "copper")` |
| P5 | Thermal FDM | None | Wrap `solve_thermal_fdm()` with `profiler.sub_step("physics", "thermal_fdm")` |

### Tooling

- **Python**: py-spy (sampling, zero-instrumentation, Numba-compatible), scalene (line-level Python vs native split)
- **Rust**: samply (macOS), cargo-flamegraph (CI/Linux)
- **Mixed**: py-spy `--native` for Rust frames inline
- **CI**: cProfile (already wired) + scalene for drift detection

### Profiling Scenarios

| Scenario | Board | Use |
|---|---|---|
| Smoke | minimal_board fixture | Pre-commit (<5 s) |
| Typical | temper.kicad_pcb (149 comps) | Daily profiling, CI gates |
| Stress | medium_board fixture | A* congestion profiling |
| No-op | empty_board fixture | Baseline overhead measurement |
| Corpus | 4-board corpus | Weekly trend detection |

### Instrumentation Points (4 gaps)

1. CP-SAT loop: `profiler.stage("cp_sat_round_N")` per iteration
2. KiCad parser: `profiler.sub_step("parse", "parse_kicad_pcb_v6")`, `profiler.sub_step("parse", "netlist_build")`
3. KiCad writer: `profiler.sub_step("write", "write_placements")`, `profiler.sub_step("write", "zone_serialization")`
4. Physics: `profiler.sub_step("physics", "copper")`, `profiler.sub_step("physics", "thermal_fdm")`

### Output & Visualization

- Flame graphs: py-spy → speedscope JSON → FlameGraph.pl SVG (CI artifact)
- Per-net latency scatter plot in `pipeline_report.html`
- JSON Schema for `ProfileReport` output
- Integrate flame graph into `full_pipeline_profile.py`

### CI Integration

- Add py-spy flame graph step to `pr-perf-check.yml`
- Thresholds: 20% wall-time regression (alert), 10% completion drop (alert), any new DRC error (blocks)
- `--quick` mode on minimal board for pre-commit hook (<5 s)
- Weekly drift detection: >2σ in 30-day window triggers issue

## Outstanding Questions

- Whether to add `scalene` to CI (adds ~2 min to pipeline)
- Exact `--quick` mode board fixture (minimal_board vs empty_board)
- JSON Schema for ProfileReport (defer to planning)

## How This Work Fits Together

- **Extends** existing `profiling/` package — no new modules needed
- **Feeds** CP-SAT benchmarks (001) with reproducible profiling workloads
- **Enables** Rust migration validation (003) by providing before/after perf comparisons
- **Integrates with** existing `pr-perf-check.yml`, `metrics-record.yml`, `regression.yml`
