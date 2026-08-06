//! Wave-4 Phase 2: the placer's `core/` CONTRACT layer in Rust.
//!
//! Phase 2 is the program's pivot: downstream Python (`io/`, `pipeline/`,
//! `router_v6/`, `validation/`) should stop marshalling contract objects
//! across the pyo3 boundary on every call. The deliverable is therefore
//! `#[pyclass]` types (`Rect`, `PinInfo`, `PlacementViolation`,
//! `FabPreset`) plus the pure kernels their modules own, not a bag of
//! free functions.
//!
//! Layout follows the crate's existing split: each module is pure Rust
//! (compiles for `wasm32-unknown-unknown`, no pyo3), and
//! [`pybridge`] — gated on the `python` feature — is the only place
//! that touches Python objects.
//!
//! ## What is here, and what is deliberately not
//!
//! Ported: `Rect` (board.py), `units`, `net_classification`,
//! `manufacturing`, `placement_drc`, and
//! `netlist.build_adjacency_matrix`.
//!
//! Not ported, with reasons recorded in the PR rather than churned:
//!
//! * `Board`/`Zone`/`Netlist`/`Component`/`Net`/`Pin` — mutable
//!   dataclasses whose `list`/`dict` fields are mutated in place by
//!   downstream code (`board.zones.append`, `netlist.components[...]`,
//!   `build_indices()` rebuilding `_zone_map`). A pyclass that converts
//!   its `Vec` to a fresh Python list on every access would drop those
//!   mutations silently, and no existing test would catch it.
//! * `board.py`'s layer helpers — a 4-entry dict lookup plus an
//!   `isinstance` dispatch on a Python `IntEnum`. There is no compute to
//!   move; a port would add an FFI hop to a dict lookup.
//! * `LayerStackup`/`Layer` — structurally untyped (the dataclass
//!   accepts any container of any element), `Layer` is mutable and
//!   deliberately unhashable, and every method is O(4). A pyclass must
//!   either narrow the accepted types (a public-API change) or read the
//!   originals back through the boundary on every call (no marshalling
//!   saved).
//! * `netlist.compute_eigenvector_centrality` — `np.linalg.eigh`, i.e.
//!   the host LAPACK. Bit-exactness is not reproducible without linking
//!   the same LAPACK build; claiming parity here would be unmeasurable.
//! * `topology.UnionFind` — keys are arbitrary Python hashables, so a
//!   Rust port must call back into Python to hash on every `find`. That
//!   adds FFI cost instead of removing it, which fails the Phase-2
//!   premise.

pub mod adjacency;
pub mod manufacturing;
pub mod netclass;
pub mod placement_drc;
pub mod pyrepr;
pub mod rect;
pub mod units;

#[cfg(feature = "python")]
pub mod pybridge;
