# CP-SAT Benchmark Suite — Plan

`artifact_contract: ce-unified-plan/v1` · `artifact_readiness: requirements-only` · `product_contract_source: ce-brainstorm`

## Goal Capsule

**Objective:** Replace the dead JAX benchmarks with a CP-SAT benchmark suite covering 5 scenarios from trivial to production scale, running in CI on every PR with DRC-regression gating.

**Product authority:** temper-placer maintainers.
**Open blockers:** None — requirements-only; planning decides file layout, CI workflow name, and baseline format.

## Quality Strategy

All implementation MUST follow three verification disciplines:

1. **TDD (Test-Driven Development).** Write the benchmark assertion before the benchmark scenario. Every scenario starts as a failing test that asserts on solve status, wall-time ceiling, and DRC counts. No scenario is accepted without a test that fails before it passes.

2. **PBT (Property-Based Testing).** For synthetic netlist generators, use Hypothesis to verify invariants across random component counts: benchmark output is valid JSON with required fields, wall-time is non-negative and monotonic in component count, and DRC error count is bounded by component count. At least 3 invariant properties per scenario family.

3. **Mathematical Induction (Base-Case Proofs).** Prove that the benchmark suite's scaling model generalizes:
   - **Base case (n=10):** Trivial scenario produces valid metrics.
   - **Inductive step:** Prove that if the benchmark suite is sound for n components, it is sound for n+10 components — the wall-time trend is monotonic, the DRC error floor is sub-linear in n, and the solve-status distribution converges.
   - This is a **rigor requirement, not an implementation detail** — the plan artifact must include a section documenting the base case and induction hypothesis before implementation begins.

## Product Contract

### Key Decisions

- `session-settled:` Benchmarks use synthetic netlists for scale scenarios and production PCL configs for realism.
- `session-settled:` CI runs Trivial + Small + Temper PCL on every PR; Medium + Stress are manual-only.
- `session-settled:` DRC regression (any new error) blocks merge. Wall-time increase >50% triggers non-blocking alert.
- `session-settled:` Baselines stored as per-scenario JSON in `benchmarks/baselines/`, compared with ±20% wall-time tolerance.

### Metrics

1. Wall-clock solve time (`solve_time_s`)
2. Solve status (OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN)
3. Round-trip count until convergence
4. DRC pass rate via kicad-cli
5. Audit pass rate via PlacementAuditor
6. Completion % (routed_nets / total_nets)
7. Peak memory (manual stress scenarios only)
8. CP-SAT constraint and variable count
9. UNSAT core size when INFEASIBLE

### Benchmark Scenarios

| Scenario | Components | Input | Time Limit | CI |
|---|---|---|---|---|
| Trivial | 10 synthetic | constraints_minimal.yaml | 2 s | Yes |
| Small | 20 synthetic | constraints_medium.yaml | 10 s | Yes |
| Medium | 50 synthetic | constraints_large.yaml | 60 s | Manual |
| Temper PCL | 13 real | temper_induction.yaml PCL | 30 s | Yes |
| Stress | 33 real | temper.kicad_pcb full PCL + routing | None | Manual |

### Comparison Baseline

- Golden JSON per scenario in `benchmarks/baselines/`
- 5-seed random-initialization spread for variance bounds
- Human-designed placement as DRC upper-bound reference
- Deprecated JAX results as historical annotation only

### Output Format

- JSONL per run at `benchmarks/results/cp_sat_metrics.jsonl`
- Console summary table (status, wall-time, rounds, DRC errors, audit)
- GitHub step-summary markdown in CI
- Baseline diff report in `--compare` mode

### CI Integration

- New workflow: `cp-sat-benchmarks.yml`
- Trivial + Small + Temper PCL on every PR, timeout 10 min
- DRC error increase over baseline blocks merge
- Wall-time +50% triggers non-blocking PR comment
- Medium + Stress scenarios via `uv run python benchmarks/cp_sat_bench.py --full`

## Outstanding Questions

- Exact baseline tolerance values per scenario (tune after first 10 PR runs)
- Whether to gate on audit pass/fail in addition to DRC
- JSON schema for baseline files (defer to planning)

## How This Work Fits Together

- **Replaces** the deprecated `benchmarks/bench_optimizer.py` (JAX-only)
- **Extends** the pattern from `benchmarks/bench_net_ordering.py` to full CP-SAT solve
- **Feeds into** the profiling setup (002) by providing reproducible workloads
- **Blocks** Rust migration validation (003) — need benchmarks to prove perf gains
