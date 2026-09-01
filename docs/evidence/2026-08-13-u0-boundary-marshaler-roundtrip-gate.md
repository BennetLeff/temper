<!-- provenance: commit=5f5f0dd1d1966be34d2ee1fc173c94754bd8e9de dirty=false -->

# U0 boundary marshaller + round-trip losslessness gate — owned structs dodge the cross-`.so` pyclass-identity blocker by construction

**Date:** 2026-08-13
**Base:** `origin/main` @ `b5e94b6f1`.
**Branch:** `migrate/o-c3-u0-marshaler`; first commit `5f5f0dd1d`.

## What this unit proves

Unit O-C3/U0 is the foundation of the orchestration data-model port: it
builds the boundary marshaller and the round-trip losslessness gate that
every later unit (U1–U4) relies on to replace the 23
`Option<Py<PyAny>>` `BoardState` fields with owned Rust structs. U0 is the
foundational *proof*, not the port itself — nothing in `board_state.rs` or
any stage is changed.

## The marshaller (`packages/temper-orchestration/src/marshal.rs`)

- **`Marshal` trait** + free functions `to_owned::<T>(obj)` /
  `to_python::<T>(py, owned)`. Every impl reads scalars via
  `extract::<f64>()` / `extract::<i64>()` / `extract::<String>()` and
  iterates collections. **Never `extract::<Py<T>>()`** — that is the exact
  call whose duplicated-`LazyTypeObject` check broke `Netlist` identity
  across the two `.so` files (see
  `docs/evidence/2026-08-12-cross-extension-pyclass-identity.md`). An owned
  struct with plain scalar/collection fields cannot name a foreign pyclass,
  so the blocker cannot arise. This is the whole point of the port: the
  single-`.so` consolidation is unnecessary for the *data model*.
- **`Val` enum** (`Int(i64) | Float(f64)`) — the canonical type for the
  concrete-Python-type hazard (`netlist_contracts.rs:11-28`): a field that
  can hold `int` OR `float` (component bounds `(1, 2)` vs `(1.0, 2.0)`)
  records which one it was and round-trips it unchanged. A bare `f64` field
  would silently widen `1` → `1.0` (repr/`==`/numpy-dtype change).
- **`Plain` enum** — the lossless nested-value tree (`Null`/`Bool`/`Int`/
  `Float`/`Str`/`Bytes`/`Tuple`/`List`/`Set`/`FrozenSet`/`Dict`/`Opaque`),
  preserving the concrete collection kind and every leaf type.

## The round-trip gate

`assert_roundtrip::<T>(py, "<python literal>")` (reusable — U1+ plug their
types in) marshals to `T` and back and asserts **bit-identity**: exact type
(`get_type().is(...)`), identical `repr`, and NaN-aware `==` (two NaN floats
count as equal — `nan == nan` is `False` in CPython, but the round-trip
reproduced the same bit pattern).

Lossless-proven: `i64`↔`int`, `f64`↔`float` (incl. NaN/±inf),
`bool`↔`bool`, `String`↔`str`, `Val`↔`int|float`, `Option<T>`↔`None|T`,
`Vec<T>`↔`list`, `Plain`↔any nested builtin tree. The scalar impls each
*reject* the sibling numeric type rather than widen it (`f64` rejects
`int`, `i64` rejects `bool`, `Val` rejects `bool`/`str`) — negative tests
pin those guards.

End-to-end proof on **real field shapes**: `BoardState.placements`
(`frozenset` of `(ref, (x, y))` tuples) and `used_slots` (`frozenset` of
integer slot-id tuples) are read via `getattr` — exactly as a U1+ stage
will — marshalled to `Plain`, and round-tripped bit-identically.

## Keeps (types that cannot round-trip through an owned struct)

`Plain::Opaque` passes the object through by reference — identity
preserved, nothing reconstructed. Deliberate for numpy arrays (dtype and
element bit patterns are numpy's own; a Rust float conversion could widen
`float32` → `float64`), shapely/GEOS geometries, and pyclasses owned by
other `.so` files. They stay `Py<PyAny>`-shaped until their owner crate
migrates them; forcing a lossy copy is worse than leaving them opaque.

## Gates

- `cargo test --lib`: 1122 passed (1112 pre-existing + 10 new).
- `cargo clippy --all-targets`: clean.
- `cargo check --no-default-features`: clean (wasm-tier unaffected — the
  module is `#[cfg(feature = "python")]`-gated).
- `scripts/gen_wasm_test_registry.py --crate temper-orchestration --check`:
  up to date (1019 tests; `marshal::tests` censused `python-gated`, 10).
- `make regen-check`: unchanged — the two `need attention` items (drifted
  `_pipeline_core_py_oracle.py` pin from #1113, unmanifested
  `measure_uncapped_drc.py` from #1111) are pre-existing on origin/main.
