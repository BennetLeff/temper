# pyo3 0.23 → 0.29 Migration Strategy

**Date:** 2026-07-23
**PRs blocked:** #186 (temper-geometry), #334 (temper-rust-router)
**Scope:** medium

**Status:** EXECUTED 2026-07-23 in PR #336 (squash commit `ad4d7d8f`). The migration strategy described here was applied; `temper-geometry` and `temper-rust-router` are now on pyo3 0.29. Kept as historical reference + future-migration template.

---

## Current State

| Crate | pyo3 version | PR bumping | Compiles? | Tests pass? |
|-------|-------------|------------|-----------|-------------|
| temper-geometry | 0.23.5 | #186 → 0.29.0 | yes | NO |
| temper-rust-router | 0.23.5 | #334 → 0.29.0 | NO (14 errors) | N/A |
| temper-dsn | 0.29.0 | — | yes | yes |
| temper-ipc | 0.29.0 | — | yes | yes |
| temper-io-types | 0.29.0 | — | yes | yes |
| temper-drc-rs | 0.23.5 | — | yes | yes |
| temper-constraints | ? (likely 0.23) | — | yes | yes |

The workspace already has mixed pyo3 versions (0.23 and 0.29 coexist), and
tests pass on main when crates on different versions are loaded into the same
Python process.  The issue is specifically that moving ONE of the two remaining
0.23 crates to 0.29 while the other stays at 0.23 creates a mixed-version
boundary inside the loop-extractor execution path.

## Diagnosis

### PR #334 — temper-rust-router: COMPILATION FAILURE

14 errors in `types_py_bridge.rs` and `lib.rs`.  Five classes of breakage:

1. **`PyObject` type removed** — replaced by `Py<PyAny>`.
   `Vec<PyObject>` in function signatures and `PyObject` return types must change.

2. **`Python::with_gil(|py| { ... })` removed** — `model_from_python` (line 16
   of `types_py_bridge.rs`) and `audit_result` (line 187 of `lib.rs`) use this
   pattern.  In pyo3 0.29 the closure-accepting `with_gil` is gone; callers
   must receive `py: Python<'_>` as a parameter instead.

3. **`Bound::downcast()` without turbofish removed** — lines 112, 116, 136 of
   `types_py_bridge.rs` use bare `downcast()?` with type inference from the
   return type.  pyo3 0.29 requires explicit turbofish: `downcast::<PyList>()?`.

4. **`PyList::empty(py)` removed** — replaced by `PyList::new(py, iter)` or
   `PyList::new_bound(py, [])`.  Used at `lib.rs:98` and `lib.rs:188`.

5. **`PyDict::new(py)` / `PyList::new(py, ...)` API** — these function-name
   forms were removed. The replacement depends on exact pyo3 0.29 API surface;
   `temper-io-types` (already on 0.29) demonstrates the working pattern:
   ```rust
   let d = PyDict::new(py);           // still works in 0.29
   let lst = PyList::new(py, iter)?;  // works; iter of Py<PyAny> or Bound objects
   ```
   But `PyList::new(py, [])` may need explicit typing or `PyList::new_bound`.

### PR #186 — temper-geometry: TEST FAILURE (zero results)

**Failing test:** `tests/core/test_loop_extractor.py::TestAutoExtraction::test_get_critical_loops`

**Assertion that fails:**
```python
loops = auto_extract_loops(half_bridge_netlist)
critical = loops.get_critical_loops()
assert len(critical) >= 3   # Commutation + 2 gate drives
# Fails: assert 0 >= 3, where 0 = len([])
```

**Call chain:**
1. `test_get_critical_loops` → calls `auto_extract_loops(half_bridge_netlist)`
   (`loop_extractor.py:442`)
2. `auto_extract_loops` → tries Rust backend: `auto_extract_loops_rs(netlist, topology_hints)`
   (`loop_extractor_rs.py:132`)
3. `auto_extract_loops_rs` → `import temper_rust_router`, calls
   `temper_rust_router.auto_extract_loops_rust(json_str)` (`loop_extractor_rs.py:154`)
4. Rust `auto_extract_loops_rust` — in `temper-rust-router/src/loop_extractor/bridge.rs:122`
   — deserializes JSON, runs extraction, returns JSON.
   Function is still compiled against pyo3 **0.23** (PR #186 only bumps temper-geometry).

**Root cause:** When `temper_geometry` (pyo3 0.29) and `temper_rust_router` (pyo3
0.23) are both loaded into the same Python process during testing, the two pyo3
versions' module-initialization code both run.  Both versions call into the
CPython C API to register functions, types, and module state.  The 0.23 pyo3
compiled into `temper_rust_router.so` sees a Python interpreter whose internal
state was partially initialized by pyo3 0.29.  This causes the
`auto_extract_loops_rust` pyfunction wrapper to execute but produce zero
results — the function runs (returns `{"ok": true}`) but the loop extraction
produces an empty list (`"loops": []`).  The Python-side fallback wrappers
return this (non-None, but empty) result, bypassing the pure-Python fallback
path.

The fix is to migrate **both** crates to pyo3 0.29 simultaneously (or migrate
temper-rust-router first, since its `.so` is the one actually running the
failing function).  Migrating temper-geometry in isolation while temper-rust-router
stays at 0.23 creates an untestable mixed-version boundary.

## Breaking Changes in pyo3 0.23 → 0.29 Affecting These Crates

| Change | Version | Affects |
|--------|---------|---------|
| `PyObject` type alias removed; use `Py<PyAny>` | 0.24-0.25 | temper-rust-router |
| `Python::with_gil(closure)` removed; receive `Python<'_>` parameter | 0.25 | temper-rust-router |
| `Bound::downcast()` without turbofish → `downcast::<T>()` | 0.24 | temper-rust-router |
| `FromPyObject` derive behavior changed; `#[pyclass(from_py_object)]` opt-in | 0.29 | temper-io-types already uses this |
| `PyList::empty(py)` → `PyList::new(py, [])` or `PyList::new_bound(py, [])` | 0.25+ | temper-rust-router |
| `[pymethods]` inside `#[pyclass]` — mostly unchanged for simple cases | — | temper-geometry (already compatible) |
| `#[pyfunction]` with `Python<'_>` parameter or plain args — both still work | — | temper-geometry (already compatible) |

Important: `temper-geometry`'s bridge code (`bridge.rs`) uses **no** `PyObject`,
`Python::with_gil`, `downcast()`, or `PyList::empty`.  It only uses
`#[pyfunction]`, `wrap_pyfunction!`, `PyResult<T>`, `Vec<f64>`, tuples, and
`catch_unwind`.  All of these are compatible with pyo3 0.29 unchanged.
`temper-geometry` should compile and work correctly on 0.29 — IF temper-rust-router
is also on 0.29 (or if the loop extractor test isn't run in a process that also
loads temper-geometry on 0.29).

## Already-Migrated Crates' Patterns (Reference Templates)

**temper-dsn** (`packages/temper-dsn/src/lib.rs`) — simplest pattern:
```rust
#[pyfunction]
fn normalize_dsn(dsn_text: &str) -> PyResult<String> {
    Ok(temper_dsn_core::normalize_dsn(dsn_text))
}

#[pymodule]
fn temper_dsn(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(normalize_dsn, m)?)?;
    Ok(())
}
```
Key: NO `Python<'_>` parameter needed (function doesn't touch Python objects).

**temper-io-types** (`packages/temper-io-types/src/lib.rs`) — complex pattern:
```rust
use pyo3::IntoPyObject;   // new trait for 0.29
use pyo3::types::{PyDict, PyList, PyTuple};

#[pyfunction]
fn parse_footprint_courtyard(py: Python<'_>, path: PathBuf) -> PyResult<FootprintBounds> {
    // Uses py for Python API calls
}

#[pyfunction]
fn isolation_slot_aabb(slot: Bound<'_, PyAny>, component_xy: (f64, f64)) -> PyResult<...> {
    // Bound<'_, PyAny> instead of &PyAny
}

#[pyclass(from_py_object)]
#[derive(Clone)]
struct TraceSegment { ... }

#[pymodule]
fn temper_io_types(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<TraceSegment>()?;
    m.add_function(wrap_pyfunction!(parse_footprint_courtyard, m)?)?;
    Ok(())
}
```

## Loop Extractor "Returns 0 Results" Symptom

The Rust function at `packages/temper-rust-router/src/loop_extractor/bridge.rs:122`:

```rust
#[pyfunction]
pub fn auto_extract_loops_rust(_py: Python<'_>, json_str: &str) -> PyResult<String> {
    let input: NetlistInput = serde_json::from_str(json_str).map_err(...)?;
    let (comps, nets, manual) = convert_input(input);
    match auto_extract_loops(&comps, &nets, &manual) {
        Ok(loops) => {
            let out = ExtractionOutput {
                ok: true,
                error: None,
                loops: Some(loops.iter().map(|l| LoopOut { ... }).collect()),
            };
            Ok(serde_json::to_string(&out).unwrap())
        }
        Err(e) => { /* returns ok:false */ }
    }
}
```

This function does NOT use pyo3-specific types beyond `Python<'_>` (the GIL token)
and `PyResult<String>` (return type).  Both are compatible with pyo3 0.29.  The
function would compile without changes on pyo3 0.29.  The "returns 0 results"
symptom is caused by the **caller** (the Python side) invoking the function
through a pyo3 0.23 wrapper while pyo3 0.29 has already initialized in-process
state.  Migrating temper-rust-router to 0.29 eliminates the mixed-version
boundary entirely.

## Recommended Approach

**Migrate temper-rust-router to pyo3 0.29 first**, then bump temper-geometry.
The reverse order (geometry first) is what #186 tried and it fails because
temper-rust-router stays at 0.23.  A single PR that bumps both crates
simultaneously is also viable and avoids the intermediate broken state.

PR #284 (temp-feat-shared-py-bridge) is a refactoring PR that creates a shared
`temper-py-bridge` crate with derive macros — it does NOT bump pyo3 versions
and is orthogonal to this migration.  #186 and #334 are NOT redundant and need
actual engineering work.

## Per-Crate Migration Recipe

### temper-rust-router (PR #334 — 14 compilation errors, ~5 files, ~50 lines changed)

**File 1: `packages/temper-rust-router/src/types_py_bridge.rs`**
- Line 13-14: `Vec<PyObject>` → `Vec<Py<PyAny>>` (function signature and body)
- Line 16: `Python::with_gil(|py| {` → add `py: Python<'_>` parameter to
  `model_from_python`.  All callers (`lib.rs` lines 35, 152) already have `py`
  in scope — pass it through.
- Line 61,64: `downcast::<PyList>()`, `downcast::<PyTuple>()` — turbofish form
  already used, no change needed.
- Line 112: `binding.downcast()?` → `binding.downcast::<PyList>()?`
- Line 116: `item.downcast()?` → `item.downcast::<PyDict>()?`
- Line 136: `bfn_binding.downcast()?` → `bfn_binding.downcast::<PyDict>()?`

**File 2: `packages/temper-rust-router/src/lib.rs`**
- Line 29: `PyResult<PyObject>` → `PyResult<Py<PyAny>>`
- Line 31-32: `Vec<PyObject>` → `Vec<Py<PyAny>>`.  The `.into()` from
  `v.into()` should yield `Py<PyAny>` automatically.
- Line 98: `PyList::empty(py)` → `PyList::new(py, [] as [Py<PyAny>; 0])?` or
  check what `temper-io-types` uses for empty-list creation (likely
  `PyList::new(py, std::iter::empty::<Py<PyAny>>())`).
- Line 142-148: Add `py: Python<'_>` parameter to `audit_result` signature.
- Line 148: `PyResult<PyObject>` → `PyResult<Py<PyAny>>`
- Line 149-150: `Vec<PyObject>` → `Vec<Py<PyAny>>`
- Line 187: Remove `Python::with_gil(|py| {` — use the `py` from parameter
  directly.  Adjust indentation (remove one level of nesting).
- Line 188: `PyList::empty(py)` → `PyList::new(py, [] as [Py<PyAny>; 0])?`
- Line 35,152: Pass `py` to `model_from_python(py, ...)` (signature changed above).

**File 3: `packages/temper-rust-router/Cargo.toml`**
- Line 13: `pyo3 = { version = "0.23", ... }` → `pyo3 = { version = "0.29", ... }`

**File 4: `packages/temper-rust-router/src/loop_extractor/bridge.rs`**
- No code changes needed — already pyo3-0.29-compatible.

**File 5: `packages/temper-geometry/Cargo.toml`** (in the same PR, or as follow-up)
- Line 14: `pyo3 = { version = "0.23", ... }` → `pyo3 = { version = "0.29", ... }`
- No Rust code changes needed in temper-geometry (all `#[pyfunction]` signatures
  are compatible; `register_functions` already uses `&Bound<'_, PyModule>`).

### temper-geometry (PR #186 — 0 compilation errors, ~0 code changes needed)

temper-geometry's bridge code is already compatible with pyo3 0.29.  The only
change is the `Cargo.toml` version bump.  If both crates are in the same PR,
temper-geometry requires zero code changes.

## Worked Example: Failed CI Run

**PR:** #186 (run 29780445277, 2026-07-20)
**Test:** `tests/core/test_loop_extractor.py::TestAutoExtraction::test_get_critical_loops`
**Failure:**
```
>       assert len(critical) >= 3
E       assert 0 >= 3
E        +  where 0 = len([])
```
**Cause:** `temper_rust_router.auto_extract_loops_rust(json_str)` returned
`{"ok": true, "loops": []}` — zero loops extracted.  Mixed pyo3 versions in the
same process (temper-geometry at 0.29, temper-rust-router at 0.23) caused the
pyo3-0.23 function wrapper to malfunction.

**Fix:** Migrate temper-rust-router to pyo3 0.29 in the same PR, or as a
separate PR merged before the temper-geometry bump.

## Recommendation

**CAN-AGENT-DO-THIS-IN-A-FOCUSED-PR: yes**
Estimated effort: 2-3 hours (half-day).
Per-crate decomposition: temper-rust-router migration can be one PR (~50 lines
changed across 3 files + Cargo.toml); temper-geometry bump is 1-line Cargo.toml
change that can be tacked onto same PR or follow immediately.

The migration follows the well-understood pyo3 0.29 patterns already established
by `temper-dsn`, `temper-ipc`, and `temper-io-types`.  No refactoring-arc-scale
changes needed — these are mechanical API renames.
