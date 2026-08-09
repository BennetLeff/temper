# JUSTIFIED-KEEP Verdict — `core/state.py`

**Date**: 2026-08-09  
**Branch**: `fanout/migrate-core-5` (ce-work, fan-out unit 5 of 10)  
**Base commit**: `db3994773ba1329dd05246500a5b1db2c7b4b45f` (origin/main)  
**Module**: `packages/temper-placer/src/temper_placer/core/state.py`  
**Classification**: product runtime  
**Decision**: JUSTIFIED-KEEP (with one RETIRE for dead code)  
**Wave-4 plan status**: Not assigned to any phase; flagged Phase 4/5 "stays Python" in `reference_loader.py:8`

---

## Classification (Step 1)

| Symbol | Class | Rationale |
|--------|-------|-----------|
| `PlacementState` (dataclass, lines 23–207) | product runtime | Central state object imported by 16 production modules; holds component positions/rotations as numpy arrays |
| `rotation_matrix` (function, lines 210–222) | dead code | Zero production callers; replaced by Rust-backed `geometry/transform.py::get_rotation_matrix` |
| `rotate_points` (function, lines 225–242) | dead code | Zero production callers; replaced by Rust-backed `geometry/transform.py::rotate_points` |

---

## Decision (Step 2)

### `PlacementState` → JUSTIFIED-KEEP

**Blocker**: `PlacementState` is a **numpy-data container** — its three fields (`positions: (N,2) float32`, `rotation_logits: (N,4) float32`, `net_virtual_nodes: (M,2) float32 | None`) are numpy `NDArray` objects, and every consumer treats them as numpy arrays (direct `.positions`/`.rotation_logits` access, passed to `np.asarray()`, sliced with numpy indexing, etc.).

A Rust pyclass migration would produce a **pure-delegation wrapper**: the pyclass would hold `Py<PyArray2<f32>>` opaque handles, and every field access, factory method, and computation would cross the PyO3 boundary to call numpy (`np.array()`, `np.zeros()`, `np.full()`, `np.argmax()`, `.shape`). The "Rust" code would become a thin delegation shim that:

1. Builds Python lists in Rust (via `PyList::new` + `append`) for `from_positions_dict`/`from_netlist_and_board`
2. Passes those lists to Python's `np.array()` constructor
3. Returns `Py<PyArray2<f32>>` handles that consumers dereference back to numpy

This adds PyO3 boundary crossings for every operation while removing **zero** computation from Python — all the work still happens inside numpy (C/Fortran). The migration is **net-negative**: more code, more complexity, no performance gain, no safety gain.

The bit-exact parity is *technically* achievable (by delegating all numpy operations to numpy), but that does not make the migration valuable. The pipeline's parity rule ("a candidate whose parity cannot be pinned bit-exactly is reported and recorded") is not the blocker here — the blocker is that the migration has negative value.

**Precedent**: The repo already follows this pattern for numpy-boundary modules. `core/graph.py` (and the entire `core_graph_cluster` of 7 migrated files) migrated its **compute kernels** (net-clique expansion, `Coo @ vector` matvec, rotation/mirror arithmetic, `math.hypot`/midpoint/radius scalars) to Rust but kept the numpy-construction/concatentation boundaries in Python. `compute_eigenvector_centrality` in `netlist.py` is explicitly kept Python because it wraps `numpy.linalg.eigh` (LAPACK `?syevd`) — migrating it as a delegation wrapper would "add a boundary crossing while proving nothing" (per its own R3 note).

**re-decidable**: If a future wave migrates all 16 consumers to use Rust-native types instead of numpy arrays, `PlacementState` could then hold `Vec<[f32; 2]>` / `Vec<[f32; 4]>` natively. That would be a genuine migration (Rust-native data, no numpy delegation). But that requires migrating the consumers first — this is a data type, and its shape is defined by what its consumers expect.

### `rotation_matrix`, `rotate_points` → RETIRE

Dead JAX-era code confirmed by `docs/evidence/2026-07-30-rotation-sign-remaining-sites.md` (line 47: "Not a bug -- dead code. Deprecated JAX-era leftover. Zero production callers"). The `geometry/transform.py` module provides Rust-backed equivalents (`get_rotation_matrix`, `rotate_points`, `batch_rotate_points`) delegating to `temper-geometry`. The test file `tests/core/test_state.py` is the only caller, and those tests exercise dead code.

**Retirement is recorded here but not executed** — deleting dead functions requires updating the test file (removing `TestRotationMatrix`, `TestRotatePoints`, `TestSampleRotation` classes), which is a separate PR. This verdict records the classification; the actual deletion is tracked as a follow-up.

---

## Evidence (Step 3)

### LOC
- `state.py`: **242 LOC** total
  - `PlacementState` class + methods: ~197 LOC (lines 1–207)
  - `rotation_matrix`: 13 LOC (lines 210–222)
  - `rotate_points`: 17 LOC (lines 225–242)

### Consumers (production source files, 16 excluding self)

| File | How it uses PlacementState |
|------|---------------------------|
| `core/__init__.py` | Re-export hub |
| `__init__.py` (top-level) | Re-export hub |
| `io/reference_loader.py` | Constructs via `from_netlist_and_board()`, accesses `.positions`/`.rotation_logits` |
| `io/_write_board.py` | Calls `.to_discrete()`, accesses `.positions[i, 0]`/`.positions[i, 1]` |
| `metrics/aesthetic.py` | Accesses `.positions`, `.rotation_logits` as `np.asarray()` |
| `metrics/external_oracle.py` | Calls `PlacementState.from_positions_dict()` |
| `metrics/physics.py` | Accesses `.positions` as `np.asarray()` / `np.array()` |
| `metrics/quality.py` | Accesses `.positions[idx]`, `netlist.n_components` |
| `regression/physics_oracle.py` | Accesses `.positions` as `np.asarray()` |
| `validation/base.py` | Type annotation in signature |
| `validation/drc.py` | Constructs `PlacementState(positions=..., rotation_logits=...)` |
| `validation/geometric.py` | Accesses `.positions`, calls `np.argmax(.rotation_logits)` directly |
| `validation/human_reference_extractor.py` | Constructs via constructor, accesses `.positions` |
| `validation/metrics.py` | Accesses `.positions`, calls `np.argmax(.rotation_logits)` directly |
| `validation/spice.py` | Constructs via constructor |
| `heuristics/pipeline.py` | Accesses `.n_components` |

Plus ~30 test files that construct/access `PlacementState`.

### Dependency surface

| Dependency | Bound to | Migration impact |
|-----------|----------|------------------|
| `numpy` (NDArray, np.array, np.zeros, np.full, np.argmax) | Core data fields | Blocking — replacing numpy arrays with Rust-native types would break all 16+ consumers |
| `Netlist` (Rust pyclass shim, `temper-design-bundle`) | `from_netlist_and_board()`, `from_positions_dict()` | Already migrated; accessed through PyO3 from Python |
| `Board` (Rust pyclass shim, `temper-design-bundle`) | `from_netlist_and_board()` | Already migrated; accessed through PyO3 from Python |

### Churn rate

```
f8b93186 retire(python): remove JAX-deprecated PlacementState stubs + dead test surface (225 LOC)
5a17025b fix: batch CI fixes — ruff, codegen, Docker pre-compile
2d216418 fix(placer): PlacementState.from_positions_dict() raised NameError('jnp') -- leftover JAX reference
ce6746aa feat(jax): numpy migration and import fixes (U4+U5+U6)
2f3d4601 feat(placer): add CP-SAT feasibility-first placer (U0-U8)
40f9e56e fix(types): resolve all mypy errors — 0 issues in 487 source files
b5cc3a2e fix(lint): resolve all 6614 ruff errors across packages/
```

**Signal: LOW**. The file has been stable since the JAX→numpy migration. Last meaningful change was the retirement of JAX stubs (f8b93186), which removed 225 LOC of dead code. Since then, only lint/type fixes. No new features, no algorithmic changes.

---

## Verification

- **Tests**: `tests/core/test_state.py` (10 tests), `tests/core/test_state_coverage.py` (4 tests) — all 14 pass at base commit
- **Import linter**: 0 violations (`import_linter_gate.py` PASSED)
- **No differential test exists** — confirming this module has not been partially migrated; no parity drift is present
- **Production consumers**: 16 source files, all import cleanly

---

## Follow-ups

1. **RETIRE `rotation_matrix` and `rotate_points`**: Delete dead functions from `state.py`, remove `TestRotationMatrix`/`TestRotatePoints`/`TestSampleRotation` from `tests/core/test_state.py`. The `TestSampleRotation` class exercises JAX-era Gumbel-Softmax sampling logic that is also dead — no production code calls `sample_rotation` (already marked `DEPRECATED`).
2. **Re-decidable trigger**: If a future wave migrates all 16 consumers to use Rust-native position/rotation types (e.g., `Vec<[f32; 2]>` instead of numpy arrays), re-open `PlacementState` for migration as a native Rust struct.

---

*This verdict follows the R3 recording template from `docs/wave4-discipline-contract.md` §3 and the pipeline hard rule: "a candidate whose parity cannot be pinned bit-exactly is reported and recorded, not faked" — extended here to "a candidate whose migration is net-negative is recorded, not forced."*
