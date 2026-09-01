<!-- provenance: commit=ba8fd59ba5ddd0bf6127963157c770c11c3d4314 dirty=false -->

# Cross-extension `Py<T>` downcast breaks pyclass identity — Tier-1 tightening must not use `extract::<Py<T>>()`

**Date:** 2026-08-12
**Base:** `origin/main` @ `1b3dcfee2` (the U-A merge), reverted by `ba8fd59ba`.

## The failure

Unit U-A (Tier-1 `BoardState` downcasts) tightened `board`/`netlist`/`loops`/`design_rules`
from `Option<Py<PyAny>>` to `Option<Py<Board>>`/`Py<Netlist>`/`Py<LoopCollection>`/`Py<DesignRules>`,
adding `temper-design-bundle` as an optional dependency of `temper-orchestration` and
downcasting via `value.extract::<Py<T>>()` in `d1_bridge.rs::attr_opt_typed`.

Result on a clean rebuild: `RuntimeError: net_ordering: TypeError: 'Netlist' object is not an
instance of 'Netlist'` — 18 failures in the D1/D3/pipeline differentials. The Rust cargo tests
(the agent's 1108) pass; the Python cross-`.so` path fails.

## Root cause

`temper-design-bundle` and `temper-orchestration` are **two separate extension `.so` files**.
When orchestration links design-bundle as an rlib dependency, each `.so` gets its **own copy of
design-bundle's pyclass `LazyTypeObject` statics**. `add_class::<Netlist>()` runs only in the
design-bundle `.so`; the orchestration `.so`'s `Netlist::type_object(py)` lazily **creates a second
`PyType`** also named `Netlist`. `extract::<Py<Netlist>>()` checks `isinstance(obj,
orchestration_copy_of_Netlist_type)`, which is False against a `Netlist` created by the
design-bundle `.so` — hence `'Netlist' object is not an instance of 'Netlist'`.

This is the reason the 2026-08-09 orchestration plan's R-A mitigation said "no orchestration
stage is migrated before Phase A has created the types it reads" — and the deeper reason the plan
(and the brainstorm) noted `temper-orchestration` deliberately carries "zero crate deps except
pyo3". A Rust `Py<T>` field naming a pyclass registered in a *different* extension crate is the
bug; it is not a stale-`.so` artifact (a clean `make extensions`-style rebuild of all crates did
not fix it).

## Correct approaches (re-scoped U-A)

1. **Runtime class lookup** (smallest, keeps the value of validation): keep the field
   `Py<PyAny>`, and in the accessor validate against the class object obtained from Python —
   `py.import("temper_design_bundle_python")?.getattr("netlist_contracts")?.getattr("Netlist")?` —
   then `value.is_instance(&cls)`. The field stays `Py<PyAny>`, so the Rust type does not name
   the foreign pyclass; the "tightening" is runtime validation, not a Rust type change.
2. **Single-`.so` consolidation** (the real fix): move `BoardState` + the stage code into a crate
   that owns the pyclass registration (e.g. into `temper-design-bundle`, or a new
   `temper-orchestration-runtime` that re-exports rather than re-links the pyclasses). Then
   `Py<T>` downcasts share one type object and work.
3. **Keep `Py<PyAny>` + typed docstring** (zero-risk floor): document the expected class per field,
   marshal through the design-bundle `.so`'s own methods (`PyModule::import`), which is what
   D1–D7 already do.

The 3 leaf-compute ports that ran alongside U-A (grid, phase/slot, validation/partition) are
**unaffected** — they port `#[pyfunction]` kernels (module-level functions), not pyclass field
types, so they carry no cross-`.so` identity hazard.
