---
title: "feat: Router V6 Rust topology stage with PyO3 SAT solver"
type: feat
status: active
date: 2026-06-28
origin: docs/brainstorms/2026-06-28-router-v6-rust-topology-requirements.md
---

# Router V6 Rust Topology Stage

## Summary

A `packages/temper-rust-router/` crate under PyO3 + maturin replaces the Router V6 topology stage with an integrated Rust SAT library (splr) providing correct `AtMostK` cardinality encoding, CDCL solving, and unsat-core extraction. The existing Python `ConstraintModel` / `SATModel` / `TopologicalSolution` types form the PyO3 interface contract. A `TEMPER_SAT_BACKEND` environment variable controls dispatch; the Python greedy solver remains as fallback with a documented correctness warning.

---

## Problem Frame

The current Python topology solver is a greedy round-robin heuristic with an unsound capacity encoding (`sat_model.py:198-225`). The brainstorm quantifies the capacity gap: a channel rated for 3 nets silently accepts 6. No backjumping, no watched literals, no clause learning, no unsat-core diagnostics. The Rust rewrite encodes channel capacity, diff-pair coupling, and layer restrictions as statically-typed invariants, with a real CDCL solver delivering provably correct assignments and actionable unsat-core diagnostics for routing failures.

---

## Requirements

- R1. Fix the unsound AtMostK encoding in Python — a correct sequential-counter or totalizer encoding replaces the broken "at least one must be false" clause at `sat_model.py:198-225`
- R2. Generate Stage 3 golden parity fixtures from corrected Python solver output on 3 canonical boards (temper_placed, minimal, complex) — a prerequisite for Rust solver validation
- R3. Create `packages/temper-rust-router/` as a separate maturin-based package with PyO3 bindings, CI build step, and platform wheels for macOS arm64 + Linux x86-64
- R4. Port constraint model types (`NetChannelVar`, `ViaVar`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`) to Rust, accepting parsed PCB data from Python
- R5. Implement SAT encoding (constraint model → CNF) in Rust and integrate splr as the CDCL solver with correct `AtMostK` cardinality encoding
- R6. Implement topology extraction (solver variable assignments → `TopologyGraph` of channel paths) in Rust
- R7. Wire Rust crate into `RouterV6Pipeline` behind `TEMPER_SAT_BACKEND` environment variable with graceful Python fallback and documented correctness warning
- R8. Validate Rust solver against golden fixtures — identical results for Python-correct cases, strictly correct for capacity-constrained cases — plus profiling comparison against Python baseline

**Origin actors:** A1 (Router V6 Pipeline), A2 (Closure Test), A3 (Developer)
**Origin flows:** F1 (Topology routing with Rust backend), F2 (Graceful degradation), F3 (A/B testing via feature flag)
**Origin acceptance examples:** AE1 (capacity enforcement), AE2 (fallback warning), AE3 (profiling comparison), AE4 (unsat-core diagnostics)

---

## Scope Boundaries

- A* pathfinding remains in Python/Numba — the `@njit` kernel already delivers LLVM-level performance
- State serialization, YAML config parsing, and component lookup remain in Python — deferred until this crate proves the Rust/PyO3 pattern
- The Python SAT model dataclasses (`sat_model.py`) are frozen — no interface redesign
- The pipeline refactoring (`docs/architecture/PIPELINE_REFRACTORING_PLAN.md` Phases 0–4) proceeds independently

### Deferred to Follow-Up Work

- Replace Numba A* with Rust A* — separate plan when the SAT crate proves the pattern
- Rust serialization crate (`temper-serialization`) — separate plan after this one ships
- Port constraint model building (`ModelBuilder._create_*` methods that walk NetworkX skeleton graphs) — currently R4 covers the types only; full model construction from raw parsed PCB data stays Python

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/sat_model.py` — `SATModel`, `SATVariable`, `SATClause` dataclasses (the Python-side API contract)
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` — `ConstraintModel`, `ModelBuilder`, `NetChannelVar`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint` (the types to port to Rust)
- `packages/temper-placer/src/temper_placer/router_v6/topology_solver.py` — `solve_topology()`, `TopologicalSolution`, `_check_assignment()` (the solver being replaced)
- `packages/temper-placer/src/temper_placer/router_v6/topology_extraction.py` — `extract_topology_solution()`, `TopologyGraph`, `NetTopology` (the extraction being ported)
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:522-573` — Stage 3 wiring (`_run_stage3`), the integration point
- `packages/temper-placer/src/temper_placer/router_v6/astar_core_numba.py` — Numba `@njit` graceful-degrade pattern (Rust crate follows the same `try/except ImportError` → fallback shape)
- `packages/temper-placer/tests/router_v6/test_topology_solver.py` — 6 existing unit tests, golden anchor for parity
- `packages/temper-placer/tests/router_v6/test_stage3_golden_parity.py` — one-line skip stub, target for R2
- `packages/temper-placer/tests/router_v6/test_stage2_golden_parity.py` — 170-line golden fixture pattern to replicate for Stage 3
- `packages/temper-placer/tests/router_v6/generate_stage2_goldens.py` — fixture generation pattern to replicate
- `.github/workflows/python-tests.yml` — CI entry point for Rust toolchain addition
- `packages/temper-placer/pyproject.toml` — existing `hatchling` build, stays untouched; new crate gets its own `maturin` config

### Institutional Learnings

- **Golden fixture ladder** (`docs/solutions/best-practices/golden-fixture-ladder-parity-testing-2026-06-22.md`): 3 canonical boards, deterministic JSON fixtures with geometric tolerance, CI gate via `golden-check.yml`. Stage 3 fixtures follow this exact pattern.
- **Micro-stage decomposition** (`docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md`): The active Stage 3 decomposition plan extracts 5 micro-stages. The Rust solver replaces the "SAT solve" micro-stage; the other 4 (constraint generation, variable mapping, assignment validation, model extraction) remain Python. The Rust crate's `Stage3Output` contract is the integration seam.
- **Closure test measurement** (`docs/solutions/performance-issues/router-v6-full-pipeline-5min-to-23s-2026-06-23.md`): Scalar counters (not `dict.append`), JIT warm-up before timing, consistent `enable_*` flags across comparison runs. The R12 profiling script follows this methodology.

### External References

- **splr** — pure-Rust CDCL SAT solver with native `AtMostK` cardinality constraint support via totalizers, unsat-core extraction via proof-logging, incremental solving. Actively maintained. Selected as the integration target over building from scratch (user decision: "wrap instead of build").
- **maturin** — PyO3 build tool, produces platform wheels, integrates with `uv`/`pip`. The PIPELINE_REFACTORING_PLAN.md already names maturin as the designated build tool for Rust in this repo.

---

## Key Technical Decisions

- **Wrap splr over build CDCL from scratch:** The user explicitly chose wrapping over building. splr provides correct `AtMostK` totalizer encoding, CDCL with clause learning, and unsat-core extraction — all features the brainstorm requires — as a maintained dependency rather than a bespoke implementation. This eliminates the CDCL correctness and maintenance risks identified in the doc review.
- **Separate package over integrated into temper-placer:** A standalone `packages/temper-rust-router/` with `maturin` keeps the existing `hatchling`-based `temper-placer` build untouched. CI adds a Rust toolchain step rather than replacing the Python build backend. The crate is installed as a pip dependency of `temper-placer`.
- **Structured PyO3 types over DIMACS CNF serialization:** Passing `ConstraintModel` → `TopologicalSolution` across the boundary as PyO3-native structs (not serialized strings) avoids parsing overhead and keeps the interface aligned with the Python dataclasses. The Rust crate mirrors the Python types as `#[pyclass]` structs.
- **Python AtMostK fix in the same plan, before golden fixtures:** The existing test infrastructure has no golden fixtures for Stage 3. Correct fixtures require a correct Python solver. Fixing the Python encoding first gives the Rust solver a validated correctness baseline — without it, golden-parity tests are vacuously satisfied.
- **Golden fixtures generated from Python output, not hand-written:** Follows the established Stage 2 pattern (`generate_stage2_goldens.py`). Three canonical boards (`temper_placed`, minimal, complex) with deterministic JSON output. The Rust solver is validated by re-running the corrected Python solver on these boards and comparing.

---

## Open Questions

### Resolved During Planning

- **Separate package or integrated?** Separate package `packages/temper-rust-router/` with `maturin`. Keeps `hatchling` untouched and follows the repo's `packages/*` convention.
- **Build or wrap CDCL solver?** Wrap. splr is the primary integration target; varisat as fallback if splr's API proves insufficient. User explicitly chose wrapping.
- **Python AtMostK fix in this plan?** Yes. Corrected Python output is the only source of golden fixtures, and fixtures gate Rust validation. The fix is on the critical path.

### Deferred to Implementation

- **Exact serialization format across the PyO3 boundary:** Splitting `ConstraintModel.variables` (List[NetChannelVar | ViaVar | ...]) and `ConstraintModel.constraints` (List[CapacityConstraint | DiffPairConstraint | ...]) into typed Rust vecs vs. passing as opaque Python objects with getattr access. Resolved during U4 when the constraint model types are mapped to `#[pyclass]`.
- **splr evaluation against the topology constraint shape:** splr's `AtMostK` API and unsat-core extraction must be validated against the actual 338K-variable Temper PCB constraint model. The evaluation happens in U5; if splr's API has gaps, varisat is the fallback.
- **CI Rust toolchain caching:** Whether to use `actions-rs/toolchain` or direct `rustup` in the GitHub Actions workflow. Depends on CI runner OS and cache key strategy — resolved during U3.
- **Unsatisfiability handling in the topology pipeline:** If the Rust solver returns UNSAT with an unsat-core, how does Stage 4 consume it? Currently Stage 4 receives a `TopologyGraph`; UNSAT requires a new error path. The plan defers the UNSAT→Stage 4 handoff design to implementation because the current closure test never hits UNSAT on the Temper PCB.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

The PyO3 boundary flows:

```
Python (pipeline.py)                 Rust (temper-rust-router)
═══════════════════                  ═══════════════════════════
                                     
RouterV6Pipeline._run_stage3()       
  │                                   
  ├─ if TEMPER_SAT_BACKEND=="rust":   
  │    │                              
  │    ├─ ModelBuilder.build() → ConstraintModel (Python)
  │    │                              
  │    └─ rust_router.solve(          RustConstraintModel::from_python(cm)
  │         constraint_model,    ──►    │
  │         net_names,                 ├─ encode_to_cnf() → CnfFormula
  │         skeletons,                 ├─ splr::Solver::solve(cnf, cardinality_constraints)
  │         channel_widths,            │    ├─ SAT → VariableAssignment
  │         design_rules               │    └─ UNSAT → UnsatCore
  │       )                            ├─ extract_topology(assignment) → TopologyGraph
  │       ◄──────────────────────────  │
  │       → TopologicalSolution       RustTopologyGraph::to_python()
  │       → TopologyGraph             
  │                                    
  └─ else:                             
       Python greedy solver
```

---

## Output Structure

```
packages/temper-rust-router/
├── Cargo.toml
├── pyproject.toml              # maturin build config
├── src/
│   ├── lib.rs                  # PyO3 module entry, #[pymodule]
│   ├── types.rs                # #[pyclass] mirrors: ConstraintModel, NetChannelVar, CapacityConstraint, etc.
│   ├── encoding.rs             # constraint model → CNF translation
│   ├── solver.rs               # splr integration, cardinality encoding, unsat-core extraction
│   └── extraction.rs           # variable assignments → TopologyGraph (channel paths)
└── tests/
    ├── test_types.rs           # Rust-side unit tests for type conversions
    ├── test_encoding.rs        # Rust-side unit tests for CNF encoding correctness
    └── test_extraction.rs      # Rust-side unit tests for topology extraction
```

---

## Implementation Units

### U1. Fix unsound AtMostK encoding in Python

**Goal:** Replace the broken capacity encoding at `sat_model.py:198-225` with a correct AtMostK sequential-counter or totalizer encoding, so the Python solver produces capacity-correct assignments.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/sat_model.py`
- Modify: `packages/temper-placer/tests/router_v6/test_sat_model.py`

**Approach:**
- The current encoding adds a single clause "at least one of the surplus N-K variables must be false" — unsound for K > 1. Replace with a sequential counter (Sinz 2005) that encodes `sum(vars) ≤ K` correctly. A sequential counter for K=3 with N=10 vars produces O(N*K) auxiliary variables and O(N*K) clauses — well within the solver's capacity.
- The fix lives inside `populate_sat_from_constraints()`, replacing only the `CapacityConstraint` branch. All other constraint types (DiffPair, Layer) are unaffected.
- Add unit tests to `test_sat_model.py` that construct a CapacityConstraint with known inputs (4 nets, capacity 2) and assert the Python solver produces an assignment with at most 2 true variables. This test doubles as the acceptance test for AE1.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/sat_model.py:197-225` — the existing capacity branch, to be replaced in-place

**Test scenarios:**
- Happy path: 4 nets, capacity 2 — solver assigns at most 2 nets to the channel
- Happy path: 6 nets, capacity 6 — all 6 nets assigned (at-capacity)
- Edge case: 1 net, capacity 0 — solver returns UNSATISFIABLE
- Edge case: 0 nets — no capacity constraint generated
- Integration: run full closure test on `pcb/temper.kicad_pcb` and verify channel capacity violations drop to zero (SC1 pre-check)

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_sat_model.py -k capacity` — all new tests pass
- Closure test produces zero post-solve capacity violations (audit script counts nets per channel vs. channel capacity)

---

### U2. Generate Stage 3 golden parity fixtures

**Goal:** Generate golden JSON fixtures for the topology stage on 3 canonical boards, using the corrected Python solver from U1, so the Rust solver has a validated correctness baseline.

**Requirements:** R2

**Dependencies:** U1 (corrected Python solver is the fixture source)

**Files:**
- Create: `packages/temper-placer/tests/router_v6/generate_stage3_goldens.py`
- Create: `packages/temper-placer/tests/fixtures/stage3_goldens/{board_name}/stage3_topology.json`
- Modify: `packages/temper-placer/tests/router_v6/test_stage3_golden_parity.py`

**Approach:**
- Create `generate_stage3_goldens.py` following the `generate_stage2_goldens.py` pattern: run `RouterV6Pipeline` with `skip_stage3=False` on each canonical board, extract the `Stage3Output` (constraint model variable list, SAT model variable+clause list, topological solution assignment dict, topology graph), and serialize to JSON with deterministic ordering.
- Three canonical boards per the golden fixture ladder: `temper_placed` (representative), a minimal board (2-3 nets, edge cases), a complex board (many nets, many channels).
- Update `test_stage3_golden_parity.py` from its one-line skip to a real golden-parity test: load fixture JSON, run `RouterV6Pipeline._run_stage3()`, compare field-by-field with 1e-3mm geometric tolerance.
- The fixture generation script asserts zero capacity violations on the generated output — the corrected Python solver guarantees this.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/generate_stage2_goldens.py` — fixture generation pattern
- `packages/temper-placer/tests/router_v6/test_stage2_golden_parity.py` — golden-parity test pattern
- `docs/solutions/best-practices/golden-fixture-ladder-parity-testing-2026-06-22.md` — 3-board ladder, deterministic JSON

**Test scenarios:**
- Happy path: `test_stage3_golden_parity` passes on all 3 canonical boards with corrected Python solver
- Regression: `test_stage3_golden_parity` fails if Python solver output changes (detects unintended solver drift)
- Edge case: fixture generation on minimal board with skip_stage3=True produces empty Stage3Output — handled gracefully

**Verification:**
- `python generate_stage3_goldens.py --all-boards` produces 3 JSON fixture files with zero capacity violations
- `python -m pytest packages/temper-placer/tests/router_v6/test_stage3_golden_parity.py` — passes on all boards
- Golden fixtures committed and tracked in `golden-check.yml` (or equivalent path-filter gate)

---

### U3. Create Rust crate scaffold with maturin + PyO3 + CI

**Goal:** Create `packages/temper-rust-router/` with a maturin build, PyO3 module entry, and Rust toolchain integration in CI.

**Requirements:** R3, R11 (origin)

**Dependencies:** None

**Files:**
- Create: `packages/temper-rust-router/Cargo.toml`
- Create: `packages/temper-rust-router/pyproject.toml`
- Create: `packages/temper-rust-router/src/lib.rs`
- Create: `packages/temper-rust-router/src/types.rs` (module declaration only, types in U4)
- Create: `packages/temper-rust-router/src/encoding.rs` (module declaration only, logic in U5)
- Create: `packages/temper-rust-router/src/solver.rs` (module declaration only, logic in U5)
- Create: `packages/temper-rust-router/src/extraction.rs` (module declaration only, logic in U6)
- Create: `packages/temper-rust-router/tests/test_types.rs`
- Modify: `.github/workflows/python-tests.yml`

**Approach:**
- Scaffold the crate with `maturin init` in `packages/temper-rust-router/`. The `Cargo.toml` declares `splr` as a dependency and `pyo3` with the `extension-module` feature. The `pyproject.toml` uses `maturin` as the build backend.
- The `lib.rs` exposes a single `#[pyfunction] solve_topology_rust(constraint_model: PyConstraintModel, ...) -> PyTopologyResult` entry point (function body is a stub until U7).
- Add a Rust toolchain step to `.github/workflows/python-tests.yml`: install `rustup` with the stable toolchain, run `maturin build --release` in the crate directory, and install the built wheel into the CI Python environment. The step runs before the existing `pytest` step.
- Add the `pyproject.toml` workspace member to the root `pyproject.toml`'s `[tool.uv.workspace]` if `uv` supports maturin-built packages, or document the separate install step.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_core_numba.py:50-55` — `_HAVE_NUMBA` graceful-degrade pattern (Rust crate follows same `try/except ImportError` shape in Python dispatch code)

**Test scenarios:**
- Build: `maturin build --release` produces a platform wheel
- Import: `python -c "import temper_rust_router"` succeeds after wheel install
- CI: `python-tests.yml` builds and installs the Rust crate; existing tests pass (the crate is not yet wired into the pipeline)
- Cross-platform: macOS arm64 and Linux x86-64 both produce functional wheels

**Verification:**
- `maturin build --release` exits 0 and produces a `.whl` file
- `pip install` the wheel; `import temper_rust_router` succeeds (stub function callable, returns dummy data)
- CI pipeline (`python-tests.yml`) passes with the Rust toolchain step included

---

### U4. Port constraint model types to Rust

**Goal:** Implement Rust `#[pyclass]` structs mirroring the Python constraint model types (`NetChannelVar`, `ViaVar`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`, `ConstraintModel`) so they can be constructed from Python and consumed by the Rust solver.

**Requirements:** R4, R3 (origin interface preservation)

**Dependencies:** U3 (crate scaffold exists)

**Files:**
- Create: `packages/temper-rust-router/src/types.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`
- Create: `packages/temper-rust-router/tests/test_types.rs`

**Approach:**
- For each Python dataclass in `constraint_model.py`, create a corresponding Rust struct with `#[pyclass]` and `#[pymethods]` implementing `__init__` (from Python) and `#[new]` (Rust-side construction). Fields map 1:1: `net_idx: usize`, `channel_id: String`, `capacity: f64`, etc.
- `ConstraintModel` wraps `Vec<Variable>` and `Vec<Constraint>`. Use Rust enums with `#[pyclass]` for the variable/constraint type hierarchy — PyO3 supports enum dispatch via `#[derive(FromPyObject)]` on wrapper types.
- The types module is tested independently of the solver: construct a `ConstraintModel` in Rust from hardcoded data, verify field accessors, then construct from Python via `temper_rust_router.ConstraintModel(net_idx=0, channel_id="L1_E5")` and verify round-trip.
- Deferred to follow-up: full `ModelBuilder._create_channel_vars()` / `_create_via_vars()` logic (walking NetworkX skeleton graphs). For now, Python builds the `ConstraintModel` and passes it to Rust.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:27-142` — the Python types to mirror

**Test scenarios:**
- Happy path: Construct `NetChannelVar`, `CapacityConstraint`, `ConstraintModel` in Rust — fields match Python counterparts
- Happy path: Construct types from Python via PyO3 — round-trip Python→Rust→Python preserves all fields
- Edge case: Empty `ConstraintModel` (zero variables, zero constraints) — handled without panic
- Edge case: ConstraintModel with 10,000 variables (approximating 338K variable Temper PCB after model building) — no performance cliff

**Verification:**
- `cargo test -p temper-rust-router test_types` — all Rust-side unit tests pass
- Python test: `pytest packages/temper-rust-router/tests/` — PyO3 round-trip tests pass

---

### U5. SAT encoding + integrate splr solver with cardinality constraints

**Goal:** Implement CNF encoding of the constraint model and integrate splr as the CDCL solver with correct AtMostK cardinality enforcement and unsat-core extraction.

**Requirements:** R5, R1-R2 (origin correctness), R10 (origin unsat-core)

**Dependencies:** U4 (constraint model types exist in Rust)

**Files:**
- Create: `packages/temper-rust-router/src/encoding.rs`
- Create: `packages/temper-rust-router/src/solver.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`
- Modify: `packages/temper-rust-router/Cargo.toml`
- Create: `packages/temper-rust-router/tests/test_encoding.rs`

**Approach:**
- `encoding.rs` translates each constraint type to CNF clauses:
  - `CapacityConstraint`: Uses splr's native `add_atmostk(vars, k)` API for correct totalizer-based AtMostK encoding. This is the critical correctness path — the Python encoding bug is the motivation for this entire plan.
  - `DiffPairConstraint`: Encodes `uses[p,c] ↔ uses[n,c]` as two implication clauses per channel.
  - `LayerConstraint`: Encodes `uses[n,c] = allowed` as a unit clause.
- `solver.rs` wraps splr: construct a `splr::Solver`, add all CNF clauses, add cardinality constraints via splr's API, call `solve()`. On SAT, extract the variable assignment map. On UNSAT, extract the unsat-core via splr's proof-logging.
- The solver returns a `SolverResult` enum: `Sat { assignments: HashMap<String, bool> }` or `Unsat { core: Vec<String> }`.
- splr evaluation against the actual Temper PCB constraint model happens here — if splr's AtMostK API has gaps (e.g., doesn't support the exact totalizer variant needed), evaluate varisat as fallback before writing custom encoding.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/sat_model.py:98-225` — the existing Python SAT encoding (all constraint types), to replicate correctly
- `packages/temper-placer/src/temper_placer/router_v6/topology_solver.py:42-141` — the existing solver interface, to replicate

**Test scenarios:**
- Happy path: Satisfiable model with capacity, diff-pair, and layer constraints — solver returns SAT with correct assignments
- Capacity: 4 nets, capacity 2 — solver assigns at most 2 nets (AE1 / R1)
- Diff pair: Two nets marked as diff pair — both assigned to same channel (R2)
- Layer restriction: Net restricted to layer L1 — assigned only to L1 channels (R2)
- UNSAT + unsat-core: Unsatisfiable model (2 nets, 1 narrow channel) — solver returns UNSAT with core identifying the capacity constraint and affected nets (AE4 / R10)
- Edge case: Empty model (zero constraints) — returns SAT with all variables false
- Performance: 338K-variable Temper PCB model solves within the existing 5s timeout (origin's `solve_topology` timeout)

**Verification:**
- `cargo test -p temper-rust-router test_encoding test_solver` — all unit tests pass
- Manual integration test: construct the Temper PCB constraint model in Python, pass to Rust solver, verify capacity-correct assignments and solvable within timeout

---

### U6. Topology extraction in Rust

**Goal:** Convert the Rust solver's variable assignments into a `TopologyGraph` of channel paths matching the Python `extract_topology_solution()` output format, returned to Python for Stage 4 consumption.

**Requirements:** R6, R9 (origin)

**Dependencies:** U5 (solver produces assignments)

**Files:**
- Create: `packages/temper-rust-router/src/extraction.rs`
- Modify: `packages/temper-rust-router/src/lib.rs`
- Create: `packages/temper-rust-router/tests/test_extraction.rs`

**Approach:**
- Parse the solver's variable assignment dict to identify which `uses_{net}_{channel_id}` variables are true. Group by net → list of assigned channel IDs. Build a `NetTopology` for each net with the channel path graph.
- The `TopologyGraph` output struct mirrors the Python `TopologyGraph(net_topologies: dict[str, NetTopology])` shape, with `NetTopology(net_name, path_graph edges, uses_channels list, total_length_estimate)`.
- The extraction is mechanical: given true variable assignments, group by net name prefix and channel ID suffix. No algorithmic complexity — it's a structured decode of the solver output.
- Return the `TopologyGraph` across PyO3 as a `#[pyclass]` struct that Python can consume directly.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/topology_extraction.py:1-120` — the Python extraction logic to replicate

**Test scenarios:**
- Happy path: 2 nets, each assigned to 1 channel — extraction produces 2 NetTopology entries with correct channel IDs
- Happy path: 1 net assigned to 3 channels (multi-hop) — extraction produces a path graph with 3 edges
- Edge case: Net with zero assigned channels (SAT solver assigned it elsewhere) — handled gracefully (empty path)
- Edge case: Variable name format edge cases (net names containing underscores) — parsing is robust to `uses_{net_name}_{channel_id}` where net_name itself contains underscores

**Verification:**
- `cargo test -p temper-rust-router test_extraction` — all unit tests pass
- Round-trip: Python builds ConstraintModel → Rust solves → Rust extracts TopologyGraph → Python inspects graph and confirms net→channel assignments match solver output

---

### U7. PyO3 bindings, feature flag, and Python fallback dispatch

**Goal:** Wire the Rust crate into `RouterV6Pipeline._run_stage3()` behind `TEMPER_SAT_BACKEND`, with graceful Python fallback and documented correctness warning.

**Requirements:** R7, R4 (origin fallback), R6 (origin feature flag)

**Dependencies:** U3 (crate buildable), U4 (types), U5 (solver), U6 (extraction)

**Files:**
- Modify: `packages/temper-rust-router/src/lib.rs`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
- Create: `packages/temper-placer/tests/router_v6/test_rust_backend_dispatch.py`

**Approach:**
- `lib.rs` exposes a single `#[pyfunction] fn solve_topology_rust(cm: &PyConstraintModel, net_names: Vec<String>) -> PyResult<PyTopologyResult>` that calls encoding → solving → extraction and returns a `PyTopologyResult { status, assignments, topology_graph, unsat_core, solver_time_ms }`.
- In `pipeline.py`, `_run_stage3()` reads `os.environ.get("TEMPER_SAT_BACKEND", "python")`. If `"rust"`:
  1. Try `from temper_rust_router import solve_topology_rust; solve_topology_rust(cm, net_names)`.
  2. On `ImportError`, log `"Rust SAT solver not available, falling back to Python solver. WARNING: The Python fallback solver has known capacity-enforcement limitations."` and dispatch to the existing Python solver.
  3. On success, wrap the `PyTopologyResult` into the existing `Stage3Output` dataclass.
- The feature flag defaults to `"python"` — Rust is opt-in until golden parity is proven.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/router_v6/astar_core_numba.py:347-355` — `_HAVE_NUMBA` graceful-degrade pattern
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py:522-573` — `_run_stage3()` wiring

**Test scenarios:**
- Happy path: `TEMPER_SAT_BACKEND=rust` with crate installed — Rust solver runs, produces Stage3Output, pipeline completes
- Fallback: `TEMPER_SAT_BACKEND=rust` with crate NOT installed — logs warning, dispatches to Python solver, pipeline completes (AE2)
- Default: No env var set — Python solver runs (unchanged behavior)
- Fallback: `TEMPER_SAT_BACKEND=python` — Python solver runs regardless of crate availability
- Integration: Full closure test with `TEMPER_SAT_BACKEND=rust` — completion rate and DRC pass rate match or exceed Python baseline

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_rust_backend_dispatch.py` — all dispatch tests pass
- Manual: `TEMPER_SAT_BACKEND=rust python scripts/ci_closure_test.py pcb/temper.kicad_pcb` — pipeline completes with Rust solver
- Manual: `TEMPER_SAT_BACKEND=rust python -c "import temper_placer.router_v6"` with crate uninstalled — logs warning, does not crash

---

### U8. Golden parity validation and profiling comparison

**Goal:** Validate the Rust solver against Stage 3 golden fixtures and produce a profiling comparison between Python and Rust backends on the closure test.

**Requirements:** R8, R5 (origin golden parity), R12 (origin profiling), R6 (origin A/B testing)

**Dependencies:** U2 (golden fixtures exist), U7 (Rust crate wired into pipeline)

**Files:**
- Modify: `packages/temper-placer/tests/router_v6/test_stage3_golden_parity.py`
- Create: `scripts/profile_rust_vs_python_topology.py`
- Modify: `packages/temper-placer/tests/router_v6/test_rust_backend_dispatch.py`

**Approach:**
- Update `test_stage3_golden_parity.py` to run with both `TEMPER_SAT_BACKEND=python` and `TEMPER_SAT_BACKEND=rust`, asserting:
  - For all 3 canonical boards, the Rust solver's `TopologyGraph` matches the golden fixture (field-by-field, 1e-3mm tolerance).
  - For capacity-constrained cases, the Rust solver produces assignments with zero capacity violations (post-solve audit).
- Create `scripts/profile_rust_vs_python_topology.py` following the closure test measurement methodology:
  - Run the full closure test twice (warm-up, then measured) for each backend.
  - Report: completion rate, DRC pass rate, wall time (total and per-stage), solver runtime (p50/p95/p99), solver iteration count (Rust: CDCL decisions; Python: greedy assignments), memory peak.
  - Output JSON to `metrics/rust_vs_python_topology.json`.
- No `safe_auto` or automated fixes here — this unit is purely validation and measurement.

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_stage2_golden_parity.py` — field-by-field golden comparison
- `docs/solutions/performance-issues/router-v6-full-pipeline-5min-to-23s-2026-06-23.md` — closure test profiling methodology
- `scripts/full_pipeline_profile.py` — profiling script output conventions

**Test scenarios:**
- Golden parity: `TEMPER_SAT_BACKEND=rust pytest test_stage3_golden_parity.py` — passes on all 3 canonical boards
- Golden parity: `TEMPER_SAT_BACKEND=python pytest test_stage3_golden_parity.py` — passes (Python baseline validated against same fixtures)
- Capacity audit: Rust solver on temper_placed produces zero capacity violations (AE1 / SC1)
- Profiling: `python scripts/profile_rust_vs_python_topology.py pcb/temper.kicad_pcb` — produces JSON with all required metrics
- Profiling: closure test completion rate with Rust ≥ Python baseline (SC1); DRC pass rate not regressed (SC2)

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_stage3_golden_parity.py` — passes with both backends
- `python scripts/profile_rust_vs_python_topology.py pcb/temper.kicad_pcb` — produces `metrics/rust_vs_python_topology.json` with Rust completion rate ≥ Python, DRC parity, Rust solver wall time reported

---

## System-Wide Impact

- **Interaction graph:** `RouterV6Pipeline._run_stage3()` is the single integration point. Stage 2 output (skeletons, channel_widths) is consumed unchanged. Stage 4 input (TopologyGraph) format is preserved — `Stage3Output` dataclass is the contract.
- **Error propagation:** `ImportError` on Rust crate → logged warning + Python fallback (graceful). Rust solver UNSAT → `SolverStatus.UNSATISFIABLE` with unsat-core propagated to `Stage3Output` and surfaced in routing diagnostics. Rust solver panic → caught by PyO3, converted to Python exception, pipeline fails with clear error (no silent crash).
- **State lifecycle risks:** None. The topology stage is stateless — each invocation is a pure function from parsed PCB data to channel assignments.
- **API surface parity:** `TEMPER_SAT_BACKEND` is the only new environment variable. No changes to the `RouterV6Pipeline` public API (`run()`, `route_pcb()`).
- **Integration coverage:** Closure test (`ci_closure_test.py`) exercises the full 5-stage pipeline with the Rust backend. The golden parity test validates Stage 3 output in isolation. The existing `test_wave3_skip_sat.py` verifies `skip_stage3` still works.
- **Unchanged invariants:** `skip_stage3=True` bypasses the Rust solver entirely (unchanged). All existing Stage 1, 2, 4, 5 code is untouched. The Python `SATModel`/`SATVariable`/`SATClause` dataclasses remain as-is for the Python fallback path.

---

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| splr API gaps for topology constraint shape | Medium | High | Evaluate splr's `AtMostK` against the actual 338K-variable model early in U5; varisat is the documented fallback. If neither works, escalate to from-scratch solver as a contingency (reopens the brainstorm's original CDCL-from-scratch decision). |
| Stage 3 decomposition plan changes the constraint model interface mid-flight | Medium | Medium | The Rust crate's PyO3 boundary is documented as version-locked to the current `constraint_model.py` types. If decomposition lands first, adapt the boundary in a follow-up unit (constrained scope — the solver core is interface-agnostic). |
| Rust toolchain adds CI build time that exceeds existing timeout | Low | Medium | maturin builds are cached via GitHub Actions `actions/cache` on `~/.cargo` and `target/`. First build is slow; subsequent builds are incremental. If caching is insufficient, split Rust build into a separate CI job that runs in parallel with Python tests. |
| Golden fixture generation exposes additional Python solver bugs beyond capacity encoding | Low | Medium | U1 fixes the known unsound capacity encoding. If golden fixture generation reveals other bugs in the Python solver (e.g., diff-pair constraint mishandling), fix them in U1's scope — the fixtures must be correct regardless of source. |
| splr unsat-core extraction produces cores too large to be actionable | Low | Low | The brainstorm's deferred question about unsat-core size is answered by measurement in U5. If cores are too large, splr's proof-logging can be post-processed to filter to the minimal core. If still too large, the feature is downgraded to FYI (the brainstorm already flags this as potentially unquantified value). |

---

## Documentation / Operational Notes

- Update `AGENTS.md` with the Rust toolchain requirement and `maturin build` instructions for local development
- Add a `README.md` to `packages/temper-rust-router/` documenting the PyO3 interface, the `TEMPER_SAT_BACKEND` flag, and the fallback behavior
- The fallback warning ("known capacity-enforcement limitations") is user-facing — ensure it appears in pipeline logs and CI output when the Rust backend is unavailable
- Monitor CI build times after adding the Rust toolchain step; if Rust compilation exceeds 5 minutes on cold cache, investigate sccache or mold linker

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-06-28-router-v6-rust-topology-requirements.md`
- **Architecture:** `docs/architecture/PIPELINE_REFRACTORING_PLAN.md` (Phase 5: Rust/Numba Acceleration)
- **Active decomposition:** `docs/plans/2026-06-22-019-feat-deploy-strangler-stage3-sat-plan.md`
- **Golden fixtures:** `docs/solutions/best-practices/golden-fixture-ladder-parity-testing-2026-06-22.md`
- **Closure test methodology:** `docs/solutions/performance-issues/router-v6-full-pipeline-5min-to-23s-2026-06-23.md`
- Related code: `packages/temper-placer/src/temper_placer/router_v6/sat_model.py`, `constraint_model.py`, `topology_solver.py`, `topology_extraction.py`, `pipeline.py`
- External: splr crate, maturin, PyO3

---

## Amendment — Post-Implementation (2026-06-28)

The plan was executed on `feat/router-v6-rust-topology`. Three decisions made
during implementation materially changed the plan's approach:

### 1. Golden fixtures → constraint audit

**Planned:** Generate Python golden fixtures for Stage 3, validate Rust solver
against them (U2, U8).

**Implemented:** Golden fixtures validate the solver against a *buggy reference*
(the Python solver has known correctness gaps beyond AtMostK). Instead, a
constraint audit module (`audit.rs`) validates the Rust solver's output directly
against the constraint model — checking every `CapacityConstraint`,
`DiffPairConstraint`, and `LayerConstraint`. This is stronger than golden
fixtures because it validates against the constraints themselves, not against
another solver's output.

The golden fixture files (`generate_stage3_goldens.py`,
`test_stage3_golden_parity.py`) were deleted and replaced with
`test_stage3_constraint_audit.py` which exercises the Rust solver end-to-end
with inline constraint auditing. pysat cross-validation confirms the Rust
solver agrees with Glucose3 on the same CNF.

### 2. Python fallback removed

**Planned:** `TEMPER_SAT_BACKEND` env var with graceful Python fallback (U7).

**Implemented:** The Python greedy solver cannot handle the sequential-counter
AtMostK encoding — it returns UNSAT on models that splr solves in <1ms. Keeping
it as a fallback would silently produce wrong answers. The Rust crate is now a
required dependency (`ImportError` if not installed, no silent degradation).
The `TEMPER_SAT_BACKEND` env var was removed entirely.

### 3. splr cardinality constraints via CNF encoding

**Planned:** splr's native `add_atmostk` API for `AtMostK` constraints (U5).

**Implemented:** splr 0.13 does not expose `add_atmostk`. The Sinz (2005)
sequential counter encoding was ported from Python to Rust
(`encoding.rs:encode_at_most_k`) and the cardinality constraints are encoded as
additional CNF clauses fed to splr. This is functionally equivalent but adds
O(n·k) auxiliary variables and clauses to the CNF formula.

### Updated U2 replacement

| File | Status |
|------|--------|
| `packages/temper-rust-router/src/audit.rs` | Constraint audit module |
| `packages/temper-rust-router/src/encoding.rs` | Sinz sequential counter + CNF encoding |
| `packages/temper-placer/tests/router_v6/test_stage3_constraint_audit.py` | End-to-end audit tests |
| `scripts/profile_rust_topology.py` | Single-backend profiling (renamed) |
| `packages/temper-placer/tests/router_v6/generate_stage3_goldens.py` | Deleted |
| `packages/temper-placer/tests/router_v6/test_stage3_golden_parity.py` | Deleted |
