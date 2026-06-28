---
date: 2026-06-28
topic: router-v6-rust-topology
---

# Router V6 Rust Topology Stage

## Summary

A Rust crate under PyO3 replaces the Router V6 topology routing stage — constraint model building, SAT encoding, CDCL solving with correct cardinality constraints, and channel assignment extraction. The existing Python SAT model dataclasses form the API contract. A Python fallback preserves current behavior when the Rust binary is unavailable.

---

## Problem Frame

Router V6's topology stage (`packages/temper-placer/src/temper_placer/router_v6/topology_solver.py`) uses a greedy round-robin SAT solver that is acknowledged as a placeholder — the source itself notes "A production implementation would use a real SAT solver like Z3 or MiniSat." The solver builds a 338K-variable model for 23 nets on the Temper PCB, then assigns channels by round-robin with no backjumping, no watched literals, and no clause learning.

The capacity constraint encoding in `sat_model.py:198-225` is unsound: it encodes an "at least one must be false" clause that allows channel overflow when `max_nets > 1`. A channel rated for 3 nets could silently accept 6. These violations surface downstream only as DRC failures or as physically unroutable assignments in Stage 4 — there is no solver-level correctness enforcement.

The constraint model (`constraint_model.py`) encodes diff pair requirements, layer restrictions, and capacity limits as abstract constraints, but the translation to SAT clauses is lossy and the solver cannot diagnose why a problem is unsatisfiable. There is no unsat-core extraction, no incremental solving, and no partial-solution fallback on timeout.

A Rust CDCL solver with proper `AtMostK` totalizer encoding for capacity, clause learning, and unsat-core extraction would make the topology stage provably correct for capacity, diff pairs, and layer restrictions — and would produce actionable diagnostics when routing is impossible.

---

## Actors

- A1. **Router V6 Pipeline** — the Python `RouterV6Pipeline` at `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` that invokes the topology stage as part of the 5-stage routing pipeline
- A2. **Closure Test** — the CI gate at `packages/temper-placer/tests/closure/test_router_completion.py` that validates completion rate (SM1 ≥90%), DRC pass rate (SM2 ≥96.7%), and wall-time (SM6 ≤105% baseline)
- A3. **Developer** — the person maintaining or debugging router behavior who needs to understand why a net failed to route

---

## Key Flows

- F1. **Topology routing with Rust backend**
  - **Trigger:** `RouterV6Pipeline` calls the topology stage with parsed PCB data (skeletons and nets)
  - **Actors:** A1
  - **Steps:** Python passes parsed PCB data across the PyO3 boundary → Rust builds the constraint model (R7) → Rust encodes to CNF (R8) → Rust CDCL solver runs with clause learning and cardinality totalizers → Rust extracts a `TopologyGraph` of channel assignments (R9) and returns it to Python for Stage 4 consumption
  - **Outcome:** Correct channel assignments with capacity, diff pair, and layer constraints all enforced
  - **Covered by:** R1, R2, R3, R7, R8, R9

- F2. **Rust crate is a required dependency**
  - **Trigger:** `import temper_rust_router` fails
  - **Actors:** A1
  - **Steps:** Pipeline raises `ImportError` with a message directing the developer to install `temper-rust-router` (no silent fallback)
  - **Outcome:** Clear failure — the pipeline does not silently produce incorrect routing assignments
  - **Covered by:** R4

- F3. **Profiling the Rust solver**
  - **Trigger:** Developer runs profiling script
  - **Actors:** A2, A3
  - **Steps:** Script runs the full closure test with warm-up + measured pass → captures wall time, completion rate, DRC pass rate → writes JSON summary
  - **Outcome:** Quantified solver performance baseline for regression detection
  - **Covered by:** R6

---

## Requirements

**Solver correctness**
- R1. The Rust CDCL solver must correctly encode and enforce channel capacity constraints using `AtMostK` cardinality encoding (totalizer or sequential counter), such that no channel assignment exceeds its computed capacity.
- R2. The Rust CDCL solver must correctly enforce diff pair constraints (both nets of a pair must use the same channel) and layer constraints (nets restricted to specific layers).
- R10. When the solver determines a problem is unsatisfiable, it must extract a minimal unsat-core — the subset of constraints that make the problem unsolvable — and return it alongside the `UNSATISFIABLE` status.

**Interface preservation**
- R3. The existing Python `SATModel`, `SATVariable`, and `SATClause` dataclasses in `packages/temper-placer/src/temper_placer/router_v6/sat_model.py` remain as the public API for building and inspecting SAT models. The Rust crate accepts and returns data compatible with these types.
- R4. The Rust crate is a required dependency — if not installed, the pipeline fails with a clear `ImportError` (no silent fallback to the known-broken Python solver).

**Testing and validation**
- R5. The Rust solver output is validated by a constraint audit that checks every capacity, diff-pair, and layer constraint against the solver's assignments — producing zero violations for valid models.
- R6. A profiling script runs the full closure test with the Rust backend and reports completion rate, DRC pass rate, wall time, per-net routing latency distribution (p50/p95/p99), solver iteration count, and memory peak.

**Full topology pipeline in Rust**
- R7. Constraint model building — creating `NetChannelVar`, `ViaVar`, `CapacityConstraint`, `DiffPairConstraint`, and `LayerConstraint` instances from skeletons and nets — must execute in Rust, consuming parsed PCB data from Python.
- R8. SAT encoding — translating the constraint model into SAT variables and clauses — must execute in Rust, producing a CNF representation consumed by the CDCL solver.
- R9. Topology extraction — converting the solver's variable assignments into a `TopologyGraph` of channel paths for Stage 4 geometric realization — must execute in Rust, returning structured channel assignments to Python.

**Build and deployment**
- R11. The Rust crate must build via `maturin`, produce platform wheels for macOS (arm64) and Linux (x86-64), and compile in CI as part of the existing GitHub Actions workflow.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R5.** Given a constraint model with 4 nets sharing a channel rated for 2 nets, when the Rust CDCL solver runs, it produces an assignment where at most 2 nets use the channel — the remaining 2 are assigned to different channels or the problem is correctly reported as unsatisfiable.
- AE2. **Covers R4.** Given the Rust crate is not installed (no `.so`/`.dylib` found), when `RouterV6Pipeline` invokes the topology stage, it logs "Rust SAT solver not available, falling back to Python solver" and routes with the existing greedy solver, producing the same completion rate as the pre-Rust baseline.
- AE3. **Covers R6.** Given `temper-rust-router` installed, when the closure test runs on `pcb/temper.kicad_pcb`, the profiling script reports completion rate, wall time, p50/p95/p99 latency, and solver iterations.
- AE4. **Covers R10.** Given a constraint model where two critical nets share a narrow channel that cannot fit both, when the solver returns UNSATISFIABLE, the unsat-core identifies the specific capacity constraint and the two nets involved, rather than reporting a generic failure.

---

## Success Criteria

- SC1. The closure test on `pcb/temper.kicad_pcb` with the Rust solver produces a completion rate at or above the Python solver's current completion rate, with channel capacity violations reduced to zero (measured by post-solve capacity audit).
- SC2. DRC pass rate on the closure test does not regress — the Rust solver's channel assignments produce physically routable paths in Stage 4 with identical or fewer DRC errors.
- SC3. A developer investigating a routing failure can read an unsat-core to identify which specific constraints (by channel and net) made the problem unsatisfiable, without needing to read the SAT model or solver internals.
- SC4. The Rust crate builds and passes all tests in CI on both macOS (arm64) and Linux (x86-64) within the existing CI timeout budget.

---

## Scope Boundaries

- A* pathfinding remains in Python/Numba (`astar_core_numba.py`) — the existing `@njit` kernel already delivers LLVM-level performance and Rust would be parity at best with added FFI overhead
- State serialization (`to_dict`/`from_dict`), YAML config parsing, and component lookup remain in Python — deferred until the SAT crate proves the Rust/PyO3 pattern works in this repo
- The Python SAT model dataclasses (`sat_model.py`) are frozen for this work — no interface redesign, no schema changes
- The pipeline refactoring described in `docs/architecture/PIPELINE_REFRACTORING_PLAN.md` Phases 0–4 proceeds independently; the Rust crate pins to the current interface and adapts later if the refactoring changes it

---

## Key Decisions

- Full topology stage (encode + solve + decode) in Rust, not solver-only: the constraint model building and SAT encoding are also correctness-sensitive — a correct solver fed incorrectly-encoded constraints produces correct-looking wrong answers. Rust's type system statically encodes invariants (capacity bounds, diff-pair coupling, layer restrictions) that Python can only enforce at runtime.
- Pinning to the current SAT model interface: starting now is higher value than waiting for the pipeline refactoring to complete; the interface adaptation cost is small relative to the correctness gain
- CDCL from scratch over wrapping an existing Rust SAT library: the cardinality encoding (totalizer/sequential counter) and unsat-core extraction are tightly coupled to the solver internals; wrapping a generic SAT library would require working around its encoding choices
- The Rust crate is the source of truth for topology correctness — the Python solver remains as a fallback for environments without the Rust toolchain, but its known capacity-enforcement limitations are documented in the fallback warning

### Rejected alternatives

- **Fixing the AtMostK encoding in Python only.** A correct sequential-counter or totalizer encoding (~100 lines of Python) would close the unsound-capacity bug at `sat_model.py:198-225` without introducing Rust. Rejected because the goal includes encoding invariants in Rust's type system (channel capacity, diff-pair coupling, layer restrictions) that Python cannot statically enforce, and because a real CDCL solver with clause learning and unsat-core extraction is a prerequisite for future topology-stage improvements (incremental solving, partial-solution fallback on timeout).
- **Wrapping python-sat (pysat).** pysat provides pip-installable CDCL solving with native `CardEnc.AtMostK` support and unsat-core extraction. Rejected because it adds a Python dependency rather than reducing Python surface area, does not encode invariants in the type system, and would still require the Rust pattern to be proven separately for later Phase 5 work (serialization, config parsing).
- **Wrapping an existing Rust SAT library (rustsat, varisat, splr).** These provide CDCL solving but their cardinality-encoding and unsat-core APIs vary; evaluating each against the topology constraint shape (338K variables, many nets, small capacity bounds) is deferred to planning as a build-vs-wrap decision. The current bet is that a purpose-built solver with domain-specific encoding will be simpler than adapting a general-purpose library.

---

## Dependencies / Assumptions

- The team has Rust fluency and will own the CDCL solver long-term — this is the first Rust crate in the repo but the team is committed to the language and toolchain
- The `maturin` build toolchain and PyO3 are available and functional for macOS arm64 and Linux x86-64 — verified against current `pip` and Rust toolchain availability
- The existing Python `SATModel`/`SATVariable`/`SATClause` dataclasses in `sat_model.py` are the stable API contract; this assumption is recorded and will be validated if the pipeline refactoring proposes interface changes
- Numba remains the A* acceleration path; this work does not introduce a second native dependency conflict because Numba is already optional (graceful degrade to pure-Python A* exists)
- The Rust crate is the source of truth for topology correctness; the Python fallback solver is retained for environments without the Rust toolchain and its known limitations are documented in the fallback warning

---

## Outstanding Questions

### Resolve Before Planning

[None]

### Deferred to Planning

- Affects R1 [Technical] Which cardinality encoding (totalizer, sequential counter, cardinality network) is the best fit for the channel capacity constraint shape (many nets, small capacity bound)?
- Affects R10 [Technical] What is the unsat-core extraction algorithm (proof-logging vs assumption-based vs deletion-filtering) and how large are the cores in practice?
- Affects R10 [Needs research] What is the actual UNSAT rate across a representative sample of PCB designs? If infrequent, R10 may not earn its complexity budget.
- Affects R11 [Technical] Does the existing CI use `maturin` or should we evaluate `setuptools-rust` or a custom build step for the GitHub Actions workflow?
- Affects R3 [Needs research] What is the exact serialization format across the PyO3 boundary — DIMACS CNF strings, pyo3 `PyList` of `PyTuple`, or a custom binary format with numpy arrays?
- Affects R5 [Implementation] Golden-parity test fixtures for the topology stage do not exist (`test_stage3_golden_parity.py` is a one-line skip). Who creates the fixtures and under what correctness criteria? The Rust solver cannot be validated against R5 until fixtures are generated from the Python solver's correct outputs.
- Affects R1 [Technical] Should the Rust crate be a separate installable package (own `pyproject.toml` + `maturin`) or integrated into the existing `temper-placer` package? The existing `temper-placer` uses `hatchling` as its build backend.
- Affects Key Decisions [Technical] Evaluate existing Rust SAT libraries (rustsat, varisat, splr) against the topology constraint shape before committing to a from-scratch CDCL build. The build-vs-wrap decision should be informed by concrete API gaps rather than a priori assumptions about coupling.
