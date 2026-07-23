# Python → Rust Migration Roadmap — Plan

`artifact_contract: ce-unified-plan/v1` · `artifact_readiness: requirements-only` · `product_contract_source: ce-brainstorm`

## Goal Capsule

**Objective:** Migrate the 6 highest-ROI Python hot paths to Rust, starting with CongestionTensor (2-3 days, lowest risk, unblocks A* migration) and progressing through corridor, copper coverage, channel widths, A* Numba kernel, and thermal FDM.

**Product authority:** temper-placer + temper-geometry maintainers.
**Open blockers:** None at requirements level. Planning decides exact Rust crate assignments, PyO3 bridge patterns, and validation harness design.

## Quality Strategy

All implementation MUST follow three verification disciplines. These are **non-negotiable gates** — no migrated module is accepted for merge without satisfying all three:

1. **TDD (Test-Driven Development).** Write the Rust implementation's test before the Rust implementation. For every migrated function (e.g., `CongestionTensor::cost()`), the Python reference implementation serves as the oracle: write a Rust test that calls the Python function, captures its output, and asserts the Rust function produces identical results. The test fails (Rust function doesn't exist yet) → implement → test passes. Every public method on every migrated struct must have at least one TDD-derived test.

2. **PBT (Property-Based Testing).** Use `proptest` (Rust) to verify invariants across random inputs for each migrated module:
   - **CongestionTensor:** cost is monotonically increasing with usage count; `cost(row, col) ≥ 1.0` for all cells; `increment` + `decay` ≈ identity for factor=1.0.
   - **copper_coverage:** grid values are bounded [0, 1]; coverage is monotonic in copper weight; empty board produces zero coverage.
   - **astar_core_numba:** path length is bounded by Manhattan distance × √2 (octilinear); heuristic is admissible (never overestimates); path never revisits a cell.
   - At least 5 invariant properties per migrated module. Property tests run on every PR via `cargo test`.

3. **Mathematical Induction (Base-Case Proofs).** Prove that each migration generalizes from its smallest input to the production scale:
   - **Base case:** For the smallest meaningful input (1×1 grid for CongestionTensor, 2-pin net for A*, single-layer board for copper coverage), the Rust output matches Python bit-identically.
   - **Inductive step:** Prove that if the migration is correct for an input of size n, it is correct for size n+1 — the algorithm's correctness does not depend on input dimensionality or scale.
   - **Structural induction variant (for A*):** Prove correctness by induction on path length. Base case: a path of 1 cell (start = goal) is trivially correct. Inductive step: if the algorithm produces a correct path of length k, extending by one optimal step produces a correct path of length k+1, because the heuristic is admissible and the cost function is monotonic.
   - Each migrated module must document its base case and induction hypothesis in a `VERIFICATION.md` file co-located with the source. The closure test suite (`ci_closure_test.py`) acts as the empirical verification of the induction claim.

### Verification Gates Per Target

| Target | TDD Tests | PBT Properties | Induction Proof |
|--------|:---:|:---:|:---:|
| CongestionTensor | 4 (one per method) | 5 (monotonic, bounded, decay-identity, weight-linear, reset-zero) | Grid-cell induction |
| corridor.py | 1 | 3 (connected, bounded, symmetric) | Component-count induction |
| copper_coverage.py | 3 | 5 (bounded, monotonic, empty-zero, full-one, additive) | Layer-count induction |
| channel_widths.py | 2 | 5 (non-negative, monotonic, scale-invariant, symmetric, bounded) | Grid-resolution induction |
| astar_core_numba.py | 5 | 6 (admissible, non-revisiting, optimal-lower-bound, monotonic-cost, path-connectivity, termination) | Path-length induction |
| thermal_fdm.py | 3 | 5 (energy-conserving, positive-temperature, steady-state-unique, boundary-respecting, mesh-convergent) | Mesh-refinement induction |

## Product Contract

### Key Decisions

- `session-settled:` CongestionTensor is the first target — simplest API, designated home in temper-geometry, unblocks the A* migration chain.
- `session-settled:` Every migration must produce bit-identical output verified by the closure test suite (`ci_closure_test.py`).
- `session-settled:` Validation follows a two-tier pattern: element-wise comparison for arrays (float32: bit-identical; float64: 1e-15) and path-level comparison for routing (every path bit-identical).
- `session-settled:` corridor.py is the warm-up target (1 day, proves the PyO3 bridge pattern before tackling larger modules).

### Ranked Migration Targets

| # | Candidate | Days | Risk | Perf Gain | Home Crate | Why |
|---|-----------|:---:|:---:|:---:|---|---|
| 1 | CongestionTensor | 2-3 | Low | Unblocks A* | temper-geometry | 4 methods, pure float32. Prerequisite for #5 |
| 2 | corridor.py | 1 | Very Low | Warm-up win | temper-geometry | 49-line mask builder. Proves PyO3 bridge |
| 3 | copper_coverage.py | 5-7 | Medium | Moderate | temper-geometry | Standalone grid builder, Python double-loops |
| 4 | channel_widths.py | 5-8 | Medium | Moderate | temper-geometry | EDT lookup hot loop. Replace scipy with `edt` crate |
| 5 | astar_core_numba.py | 8-12 | High | Numba cold-start elimination | temper-rust-router-core | Crown jewel. Must be last — consumes #1 |
| 6 | thermal_fdm.py | 10-15 | High | High (10-50x assembly) | temper-thermal (new) | Biggest win, highest risk. Needs sparse solver parity |

### Validation Strategy (per target)

| Target | Validation |
|--------|-----------|
| CongestionTensor | Compare `cost()`/`increment()` outputs on fixed paths — bit-identical float32 |
| corridor.py | Compare boolean masks element-wise on 10 corpus boards |
| copper_coverage.py | Compare `copper_coverage_grid` output arrays element-wise; fp64 tolerance 1e-15 |
| channel_widths.py | Compare node/edge widths on corpus; float tolerance 1e-6 mm |
| astar_core_numba.py | Run full closure test suite; every path bit-identical |
| thermal_fdm.py | Compare T_grid element-wise; tolerance 1e-12 K; gate: `ci_identity_check.py --thermal` |

### Prerequisites Chain

```
CongestionTensor (#1) ──┐
corridor.py (#2)        │ (independent warm-up)
                         ├──→ astar_core_numba.py (#5)
copper_coverage.py (#3) ─┤
                         ├──→ thermal_fdm.py (#6)
channel_widths.py (#4) ──┘
```

### Rust Crate Assignments

- **temper-geometry**: CongestionTensor, corridor, copper_coverage, channel_widths (all geometry/math)
- **temper-rust-router-core**: astar_core_numba replacement (router domain)
- **temper-thermal** (new): thermal_fdm replacement (separate domain, needs sparse solver dependency)

### Performance Gain Estimates

- CongestionTensor: Negligible alone (not a bottleneck); enables A* migration
- corridor.py: <1% (too small to matter alone)
- copper_coverage.py: 5-15x on rasterization (Python nested loops → Rust)
- channel_widths.py: 3-8x on EDT lookups (scipy → native)
- astar_core_numba.py: 1.5-2x + Numba cold-start elimination
- thermal_fdm.py: 10-50x on matrix assembly (Python loops → Rust)

## Outstanding Questions

- Whether `temper-thermal` should be a new crate or extend an existing one (e.g., temper-geometry)
- Exact sparse solver library for thermal_fdm (faer, sprs, or SuperLU FFI wrapper)
- `edt` crate compatibility with scipy.ndimage.distance_transform_edt output format
- Numba→Rust A* determinism: can closure tests guarantee path-identical output with different floating-point order?

## How This Work Fits Together

- **Depends on** CP-SAT benchmarks (001) to prove performance gains
- **Depends on** profiling setup (002) to produce before/after comparisons
- **Extends** existing Rust crates (temper-geometry, temper-rust-router-core)
- **Creates** one new crate (temper-thermal) for the thermal FDM solver
- **Each target is independently deliverable** — the chain shows dependencies, not a monolith
