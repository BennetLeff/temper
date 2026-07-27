---
type: feat
origin: docs/brainstorms/2026-07-08-router-build-unblock-requirements.md
status: completed
date: 2026-07-08
swept: 2026-07-25
swept_basis: "referenced in git history; 11/15 paths exist"
---

# feat: Split temper-rust-router Crate + Fix Venv — Router Build Unblock (W0)

## Summary

Split `temper-rust-router` into a pure-Rust rlib crate (`temper-rust-router-core`, no pyo3) and a cdylib-only pyo3 wrapper (`temper-rust-router`). Update `temper-constraint-compiler` to depend on `-core`. Document the non-conda Python requirement. The fix resolves the `PyInterpreterState_Get: GIL not held` crash on conda Python by eliminating the double-libpython from the `rlib` variant of the pyo3 extension.

**Gate:** `import temper_rust_router` succeeds without GIL crash. `PlaceRouteLoop.run()` completes end-to-end on a fresh `uv venv --python 3.12` checkout on macOS arm64.

---

## Problem Frame

`temper-rust-router` currently specifies `crate-type = ["cdylib", "rlib"]`. The `rlib` variant exists because `temper-constraint-compiler` path-depends on the router crate for Rust-to-Rust calls. But pyo3 guidance is that a crate imported as a Python module should be `cdylib`-only—the `rlib` variant is what lets libpython leak into the extension `.so`, producing the double-libpython GIL crash on conda Python (see `docs/solutions/build-errors/stale-rust-build-artifacts-gil-crash-2026-07-06.md`).

The fix is a clean architectural split: move all non-pyo3 logic to a separate rlib crate, leaving only the pyo3 wrapper in the cdylib extension crate. This also allows `temper-constraint-compiler` to link the pure-Rust rlib without pulling pyo3 into its transitive dependency graph.

### Module categorization

The following modules in `packages/temper-rust-router/src/` do **not** import `pyo3` and move to `-core`:

| Module | Contents |
|--------|----------|
| `solver.rs` | CaDiCaL CDCL solver via rustsat traits |
| `encoding.rs` | Constraint model → CNF translation |
| `extraction.rs` | Solver assignments → TopologyGraph |
| `combinator/` | Constraint combinator rewrite engine (RW1-RW7), primitive types, lowering |
| `loop_extractor/{mod,classify,extract,types}.rs` | Loop extraction (no bridge.rs) |
| `audit.rs` | Constraint audit against solver output |
| `bmc.rs` | Bounded model checking engine |
| `esl.rs` | Encoder Specification Language ground-truth |
| `provenance.rs` | UNSAT core reverse-mapping |
| `tension.rs` | Pre-solve tension detection |
| `watchdog.rs` | CEGAR lazy grounding loop |

The following modules import `pyo3` and stay in the wrapper crate:

| Module | Contents |
|--------|----------|
| `lib.rs` | `#[pymodule]` entry point, pyfunctions, pymodule init |
| `types.rs` | pyclass types (`Variable`, `NetChannelVar`, …) — pyo3 macros |
| `types_py_bridge.rs` | Python → Rust bridge for constraint model data |
| `loop_extractor/bridge.rs` | Python JSON bridge for loop extraction |

`types.rs` is a special case: it currently contains both pyclass types (requiring pyo3 derives) and internal-only Rust types (`InternalVariable`, `InternalConstraint`, `SolverStatus`, `TopologyResult`, `NetTopology`, `BundleClass`, etc.). The internal types move to `-core/src/types.rs`; the pyclass types remain in the wrapper's `types.rs`.

---

## Requirements

- **R1 (crate split).** Create `temper-rust-router-core` as a pure-Rust rlib with no pyo3 dependency. Slim `temper-rust-router` to cdylib-only, re-exporting from `-core` via thin pyo3 wrappers.
- **R2 (constraint-compiler dependency).** `temper-constraint-compiler` depends on `temper-rust-router-core`, not the pyo3 wrapper.
- **R3 (venv documentation).** Document `.python-version` with `3.12` and note non-conda Python requirement in README.

---

## Scope Boundaries

- pyo3 version or maturin configuration changes are out of scope.
- Other crates (`temper-drc-rs`, `temper-constraints`, `temper-quality-oracle`) are unaffected.
- The non-conda venv is a permanent environment change, not a temporary workaround.
- Public API re-exports from the wrapper crate must preserve all existing Python imports (module name, function names, class names unchanged).

---

## Implementation Units

### U1. Create `temper-rust-router-core` crate (rlib, no pyo3)

**Goal:** Establish the new `packages/temper-rust-router-core/` crate with all non-pyo3 modules, the internal-only types from `types.rs`, and the `loop_extractor` (minus `bridge.rs`). Cargo.toml declares `crate-type = ["rlib"]` and has zero pyo3 dependency.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Create: `packages/temper-rust-router-core/Cargo.toml`
- Create: `packages/temper-rust-router-core/src/lib.rs` — module declarations and public API re-exports
- Create: `packages/temper-rust-router-core/src/types.rs` — internal types extracted from `temper-rust-router/src/types.rs`
- Copy (from `temper-rust-router/src/`): `solver.rs`, `encoding.rs`, `extraction.rs`, `audit.rs`, `bmc.rs`, `esl.rs`, `provenance.rs`, `tension.rs`, `watchdog.rs`
- Copy: `combinator/` (all files: `mod.rs`, `lower.rs`, `rewrite.rs`, `proofs.rs`, `types.rs`, `integration.rs`)
- Copy: `loop_extractor/{mod.rs,classify.rs,extract.rs,types.rs}` (NOT `bridge.rs`)
- Copy: `Cargo.toml` dev-dependencies (proptest)
- Modify: `packages/temper-rust-router-core/pyproject.toml` — maturin metadata (if any) or empty (rlib may not need pyproject.toml for maturin since it's not a Python extension)

**Approach:**

1. Create `packages/temper-rust-router-core/Cargo.toml`:
   ```toml
   [package]
   name = "temper-rust-router-core"
   version = "0.1.0"
   edition = "2024"
   description = "Router V6 topology stage — pure-Rust core (SAT solver, topology extraction, loop extraction)"

   [lib]
   name = "temper_rust_router_core"
   crate-type = ["rlib"]

   [dependencies]
   rustsat = { version = "0.7.5", default-features = false, features = ["fxhash"] }
   rustsat-cadical = "0.7.5"
   serde = { version = "1", features = ["derive"] }
   serde_json = "1"
   thiserror = "1"

   [profile.release]
   panic = "unwind"

   [dev-dependencies]
   proptest = "1"
   ```
   Note: No pyo3 dependency. Same rustsat/serde/thiserror versions as the current router crate.

2. Extract internal types to `-core/src/types.rs`:
   - Move all non-pyo3 types: `InternalVariable`, `InternalConstraint`, `InternalConstraintModel`, `SatVariable`, `SatClause`, `SolverStatus`, `SolverStats`, `TopologyResult`, `NetTopology`, `TopologyGraph`, `BundleClass`, `InternalBundleManifest`, `BundledSolverResult`, `IntoInternal` trait.
   - Also move `TensionSeverity` and `TensionViolation` if defined in types.rs (check — may be in `tension.rs`).
   - Remove `use pyo3::prelude::*;` from the moved types file.
   - The pyclass types (`Variable`, `NetChannelVar`, `NetLayerVar`, `ViaVar`, `OrderVar`, `Constraint`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint` with their `#[pyclass]` and `#[pymethods]` blocks) stay in the wrapper crate's `types.rs`.

3. Write `-core/src/lib.rs` with module declarations and public API re-exports:
   ```rust
   pub mod audit;
   pub mod bmc;
   pub mod combinator;
   pub mod encoding;
   pub mod esl;
   pub mod extraction;
   pub mod loop_extractor;
   pub mod provenance;
   pub mod solver;
   pub mod tension;
   pub mod types;
   pub mod watchdog;

   pub use solver::solve_with_cadical;
   pub use extraction::extract_topology;
   pub use loop_extractor::extract::auto_extract_loops;
   pub use types::{SolverStats, SolverStatus, TopologyResult, /* … */};
   ```

4. Update intra-crate `use crate::` references in all migrated modules to point to the new crate name. For example, `use crate::types::InternalConstraint` stays valid within `-core` since `types` is declared in `-core/src/lib.rs`.

5. Copy existing tests from `packages/temper-rust-router/tests/` that test non-pyo3 modules:
   - `test_encoding.rs` → `packages/temper-rust-router-core/tests/`
   - `test_extraction.rs` → `packages/temper-rust-router-core/tests/`
   - `test_loop_extractor.rs` → `packages/temper-rust-router-core/tests/`
   - `test_types.rs` → `packages/temper-rust-router-core/tests/` (if it tests internal types)
   - Move proptest dependencies also.

**Patterns to follow:**
- `packages/temper-rust-router/src/lib.rs` — current module declaration structure.
- `packages/temper-constraint-compiler/Cargo.toml` — rlib crate pattern (it also declares `rlib` + `cdylib`; here we want `rlib`-only).

**Test scenarios:**
- `cargo build -p temper-rust-router-core` succeeds with no pyo3 in dependency tree.
- `cargo test -p temper-rust-router-core` passes all existing tests (encoding, extraction, loop_extractor, types).
- `cargo tree -p temper-rust-router-core -e normal | grep -i pyo3` returns empty (verifies no pyo3 in dep graph).

**Verification:** `temper-rust-router-core` compiles as rlib with no pyo3 linkage. All migrated tests pass unchanged.

---

### U2. Slim `temper-rust-router` to cdylib-only pyo3 wrapper

**Goal:** Reduce `temper-rust-router` to a thin pyo3 wrapper crate. It depends on `temper-rust-router-core`, removes the moved modules, and changes `crate-type` to `["cdylib"]`. The public Python API is preserved identically.

**Requirements:** R1

**Dependencies:** U1 (`-core` crate must exist and build)

**Files:**
- Modify: `packages/temper-rust-router/Cargo.toml` — change `crate-type`, add `temper-rust-router-core` dependency
- Modify: `packages/temper-rust-router/src/lib.rs` — thin wrapper re-exporting from `-core`
- Keep: `packages/temper-rust-router/src/types.rs` — pyclass types only (remove internal types moved to `-core`)
- Keep: `packages/temper-rust-router/src/types_py_bridge.rs` — update `use` paths to import internal types from `-core`
- Keep: `packages/temper-rust-router/src/loop_extractor/bridge.rs` — update `use` paths to import from `-core`
- Delete: Moved modules (`solver.rs`, `encoding.rs`, `extraction.rs`, `audit.rs`, `bmc.rs`, `esl.rs`, `provenance.rs`, `tension.rs`, `watchdog.rs`, `combinator/`, `loop_extractor/{mod,classify,extract,types}.rs`)

**Approach:**

1. Update `packages/temper-rust-router/Cargo.toml`:
   ```toml
   [package]
   name = "temper-rust-router"
   version = "0.1.0"
   edition = "2024"
   description = "Router V6 topology stage — pyo3 Python extension (wraps temper-rust-router-core)"

   [lib]
   name = "temper_rust_router"
   crate-type = ["cdylib"]

   [dependencies]
   temper-rust-router-core = { path = "../temper-rust-router-core" }
   pyo3 = { version = "0.23", features = ["extension-module"] }
   serde = { version = "1", features = ["derive"] }
   serde_json = "1"

   [profile.release]
   panic = "unwind"
   ```
   Note: `serde` and `serde_json` stay because `loop_extractor/bridge.rs` directly uses them.

2. Rewrite `packages/temper-rust-router/src/lib.rs`:
   - Keep the `#[pymodule]` function and `#[pyfunction]` exports unchanged.
   - Update `use` paths: internal types now come from `temper_rust_router_core::types::*`, solver from `temper_rust_router_core::solver::solve_with_cadical`, encoding from `temper_rust_router_core::encoding::encode_to_cnf`, etc.
   - Re-export `temper_rust_router_core::loop_extractor` for the `auto_extract_loops_rust` bridge.
   - Module declarations shrink to just the pyo3-wrapper modules:
     ```rust
     pub mod types;              // pyclass types (re-exporting -core internal types as needed)
     mod types_py_bridge;        // Python → Rust bridge
     pub mod loop_extractor;     // re-exports bridge.rs only
     ```
   - `mod combinator`, `mod encoding`, `mod extraction`, `mod solver` declarations are removed.

3. Update `types.rs` in the wrapper:
   - Remove all internal-only types (moved to `-core`).
   - Keep pyclass types: `Variable`, `NetChannelVar`, `NetLayerVar`, `ViaVar`, `OrderVar`, `Constraint`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`, and their `#[pymethods]` blocks.
   - Add `use temper_rust_router_core::types::*;` for internal types that the pyclass impls reference.
   - Remove the `IntoInternal` trait if it was in types.rs (moved to `-core`).

4. Update `types_py_bridge.rs`:
   - Change `use crate::types::{…}` to `use temper_rust_router_core::types::{…}`.

5. Update `loop_extractor/bridge.rs`:
   - Change `use crate::loop_extractor::extract::{…}` to `use temper_rust_router_core::loop_extractor::extract::{…}`.
   - Change `use crate::loop_extractor::types::ExtractionError` to `use temper_rust_router_core::loop_extractor::types::ExtractionError`.

6. Delete the moved source files from the wrapper crate directory.

7. Update `packages/temper-rust-router/tests/`:
   - Remove tests that were migrated to `-core`.
   - Keep any Python-side integration tests (if they exist via `pyproject.toml` test configuration).

**Patterns to follow:**
- pyo3's guidance: a Python extension crate should be `cdylib`-only. The wrapper delegates to the rlib, which contains the pure-Rust logic.
- `packages/temper-constraint-compiler/src/lib.rs` — example of a crate that imports from `temper-rust-router` via path dependency (the same pattern reversed).

**Test scenarios:**
- `maturin develop` in `packages/temper-rust-router/` produces a working `.so`.
- `import temper_rust_router` succeeds without GIL crash on a non-conda Python.
- `temper_rust_router.solve_topology_rust(vars, cons, net_names)` returns correct result shape.
- `temper_rust_router.auto_extract_loops_rust(json_str)` returns valid extraction JSON.
- `cargo build -p temper-rust-router` succeeds and produces only `.dylib`/`.so` (no `.rlib`).

**Verification:** `import temper_rust_router` works. All existing Python-accessible types and functions are available with identical signatures.

---

### U3. Update `temper-constraint-compiler` to depend on `-core`

**Goal:** Replace `temper-rust-router` dependency with `temper-rust-router-core` in `temper-constraint-compiler`, removing pyo3 from its transitive dependency tree.

**Requirements:** R2

**Dependencies:** U1 (`-core` crate must exist)

**Files:**
- Modify: `packages/temper-constraint-compiler/Cargo.toml` — swap dependency
- Modify: `packages/temper-constraint-compiler/src/lib.rs` — update `use` paths
- Modify: Any other `.rs` files in `temper-constraint-compiler/src/` that `use temper-rust-router::`

**Approach:**

1. Update `packages/temper-constraint-compiler/Cargo.toml`:
   ```toml
   [dependencies]
   pyo3 = { version = "0.23", features = ["extension-module"] }
   temper-rust-router-core = { path = "../temper-rust-router-core" }
   serde = { version = "1", features = ["derive"] }
   ```
   The `temper-rust-router` path dependency is removed; `temper-rust-router-core` is added.

2. Update all `use temper_rust_router::…` imports in constraint-compiler source files to `use temper_rust_router_core::…`:
   ```bash
   rg "temper_rust_router::" packages/temper-constraint-compiler/src/
   ```
   Replace with `temper_rust_router_core::`.

**Test scenarios:**
- `cargo build -p temper-constraint-compiler` succeeds.
- `cargo tree -p temper-constraint-compiler -e normal | grep -i pyo3` shows pyo3 as a direct dependency of `-compiler` but NOT as a dependency pulled in via `-core` (i.e., pyo3 is at depth 1, not depth 2+ from a transitive source).
- Constraint compiler's own tests pass (if any Rust-side tests exist).

**Verification:** `temper-constraint-compiler` builds without linking pyo3 through the router crate. No GIL crash candidates from the compiler's transitive deps.

---

### U4. Document venv requirements and verify gate

**Goal:** Ensure `.python-version` specifies `3.12`, document the non-conda Python requirement in README, and run the full gate verification: import check, PlaceRouteLoop end-to-end, constraint-compiler build.

**Requirements:** R3 (build reproducibility)

**Dependencies:** U1, U2 (crates must be split and buildable)

**Files:**
- Verify: `.python-version` — already `3.12` (no change needed)
- Modify: `README.md` — add note about non-conda Python requirement
- No code changes; verification steps only

**Approach:**

1. Verify `.python-version` reads `3.12` (already present at repo root).

2. Add a "Python Environment" section to `README.md` (after the Core Health badges, before the License section):
   ```markdown
   ## Python Environment

   This project requires a **non-conda Python** interpreter (python-build-standalone via `uv`
   or Homebrew Python). Conda/Miniconda/Miniforge Python links `libpython` in a way
   incompatible with pyo3 extension modules, producing a GIL-state crash on import.

   ```bash
   uv venv --python 3.12
   uv pip install -e ".[dev]"
   ```
   ```

3. Gate verification — three checks to run end-to-end:

   **Check A: Import gate**
   ```bash
   cd packages/temper-rust-router
   maturin develop
   python -c "import temper_rust_router; print('import OK')"
   ```
   Expected: `import OK` with no GIL crash.

   **Check B: PlaceRouteLoop gate**
   ```bash
   cd packages/temper-placer
   python -m temper_placer run --loop --board ../temper-board/kicad/temper.kicad_pcb
   ```
   Expected: `PlaceRouteLoop.run()` completes end-to-end, writes a routed `.kicad_pcb`.

   **Check C: Constraint-compiler build gate**
   ```bash
   cargo build -p temper-constraint-compiler
   ```
   Expected: Build succeeds. `cargo tree -p temper-constraint-compiler -e normal | grep temper-rust-router` shows `temper-rust-router-core`, not `temper-rust-router` (the old combined crate).

   **Check D: Test suite**
   ```bash
   cd packages/temper-rust-router-core && cargo test
   cd ../temper-rust-router && cargo test
   cd ../temper-placer && python -m pytest tests/placer/cp_sat/test_loop.py -v
   ```
   Expected: All tests pass unchanged.

**Test scenarios (gate):**
- `import temper_rust_router` — no GIL crash, no `PyInterpreterState_Get` error.
- `PlaceRouteLoop.run()` — completes without import errors; the loop controller calls through to the pyo3 functions in the wrapper crate.
- `temper-constraint-compiler` — builds against `temper-rust-router-core` without pyo3 transitively.
- All existing Python and Rust tests pass unchanged.

**Verification:** All gates pass on a fresh `uv venv --python 3.12` checkout. The routed `.kicad_pcb` is produced end-to-end.

---

## System-Wide Impact

- **Interaction graph:** `temper-rust-router` (cdylib, pyo3) → `temper-rust-router-core` (rlib, no pyo3). `temper-constraint-compiler` (cdylib+rlib, pyo3) → `temper-rust-router-core` (rlib, no pyo3). No cross-coupling between the two pyo3 extension crates.
- **Error propagation:** If `-core` fails to build, both the wrapper and the constraint-compiler fail at build time (not runtime).
- **State lifecycle:** No change. The wrapper is a stateless pass-through; all state lives in the pure-Rust core.
- **Unchanged invariants:** Python import paths, function signatures, class names, and return shapes are all preserved. The `temper_rust_router` Python module name is unchanged.
- **Performance:** No measurable impact. The rlib → cdylib function call is zero-cost; both crates are compiled together by Cargo.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `types.rs` split breaks pyclass internal type references | U2 explicitly keeps pyclass types in the wrapper and imports internal types from `-core`. The `#[pymethods]` blocks that reference internal types are updated to use `temper_rust_router_core::types::*`. |
| `use crate::` intra-module paths break after file moves | U1 bulk-renames `crate::` paths within `-core`. U2 updates the remaining wrapper modules to `use temper_rust_router_core::`. Search-and-replace with verification. |
| Tests in `tests/` directory reference moved files | U1 copies tests alongside their modules. U2 removes duplicated tests from the wrapper. |
| `serde`/`serde_json` are duplicated in both crates | Both crates need serde: `-core` for types, wrapper for `loop_extractor/bridge.rs` JSON bridge. This is fine — Cargo deduplicates versions. |
| `maturin develop` rebuilds fail due to stale `target/` | `cargo clean` before first `maturin develop` after the split (per `docs/solutions/build-errors/stale-rust-build-artifacts-gil-crash-2026-07-06.md`). |

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-08-router-build-unblock-requirements.md](../brainstorms/2026-07-08-router-build-unblock-requirements.md)
- **Gate contract:** [docs/brainstorms/2026-07-08-gate-contract.md](../brainstorms/2026-07-08-gate-contract.md)
- **Prior solution:** `docs/solutions/build-errors/stale-rust-build-artifacts-gil-crash-2026-07-06.md` — stale artifacts cause GIL crash; `cargo clean` fix. This plan addresses the root cause (double-libpython from rlib variant).
- `packages/temper-rust-router/Cargo.toml` — current `crate-type = ["cdylib", "rlib"]` (to be split)
- `packages/temper-rust-router/src/lib.rs` — `#[pymodule]` entry point, pyfunctions
- `packages/temper-rust-router/src/types.rs` — mixed pyclass + internal types (to be split)
- `packages/temper-constraint-compiler/Cargo.toml` — currently depends on `temper-rust-router` (to be changed to `-core`)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py:87` — `PlaceRouteLoop` class (gate target)
- pyo3 docs: "A crate imported as a Python module should be cdylib-only" — architectural guidance
