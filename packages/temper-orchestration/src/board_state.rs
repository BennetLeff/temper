// U0 scaffolding (`dead_code` note): the phased `BoardState` is populated and
// consumed by stages that land in Phase C/D; until then the lib target has no
// constructor call (the Python-side differential tests exercise it through
// the `ConvergenceChecker` `Stage<BoardState>` impl).
#![allow(dead_code)]

// The phased `BoardState` struct — the Rust-side snapshot of the pipeline
// state that `Stage` implementations read and write (Rust Orchestration
// Engine plan 2026-08-09-001, D2).
//
// Mirror of Python `deterministic.state.BoardState`. The struct is PHASED:
// fields whose Python type has already landed in Rust are typed structs;
// the rest are `Option<Py<PyAny>>` placeholders. A `Py<PyAny>` field is
// promoted to a typed struct in the SAME PR that migrates the first Rust
// `Stage` that reads it (D2 — the type is never tightened speculatively).
// Unit O-C3/U1 promoted `used_slots` (a `frozenset` of `(x, y)` slot-id
// tuples) to `Option<HashSet<SlotId>>`; the remaining fields stay
// `Py<PyAny>` until their owning unit (U2+) ports them.
//
// Fields are `Option` because the pipeline populates them incrementally
// across stages; a stage that reads a field asserts it is `Some` or returns
// `Err(StageError)`. Fields are `pub` — the eventual Python `run()` shim
// constructs the initial `BoardState` from Python objects (crossing FFI once
// per pipeline, not per stage) by setting them directly.

#[cfg(feature = "python")]
use std::collections::HashSet;
#[cfg(feature = "python")]
use std::hash::{Hash, Hasher};

#[cfg(feature = "python")]
use pyo3::PyAny;

#[cfg(feature = "python")]
/// A grid-slot id: the `(x, y)` coordinate pair of a slot in the placement
/// grid (Python: a `(float, float)` tuple — zone slots are float grid
/// positions, see the D4/D5 oracles' `set[tuple[float, float]]`).
///
/// Hash/Eq normalize the float semantics Python gives a set element:
/// `(0.0, 5.0) == (-0.0, 5.0)` in Python, so the two slot ids must live in
/// the same `HashSet` cell here (`-0.0` is normalized to `0.0`, and all
/// NaNs — never a real slot id — to one canonical form, keeping `Eq`
/// reflexive). The stored bit patterns are the ORIGINAL values, so
/// `to_python` round-trips bit-identically: a `-0.0` leaf comes back as
/// `-0.0` (repr-identical, pinned by the U1 round-trip gate).
#[derive(Clone, Copy, Debug)]
pub struct SlotId(pub f64, pub f64);

#[cfg(feature = "python")]
impl PartialEq for SlotId {
    fn eq(&self, other: &Self) -> bool {
        feq(self.0, other.0) && feq(self.1, other.1)
    }
}

#[cfg(feature = "python")]
impl Eq for SlotId {}

#[cfg(feature = "python")]
impl Hash for SlotId {
    fn hash<H: Hasher>(&self, state: &mut H) {
        slot_bits(self.0).hash(state);
        slot_bits(self.1).hash(state);
    }
}

#[cfg(feature = "python")]
/// Python `==` for floats: value equality, with `NaN == NaN` folded true so
/// `SlotId`'s `Eq` stays reflexive (slot ids are never NaN in practice).
fn feq(a: f64, b: f64) -> bool {
    a == b || (a.is_nan() && b.is_nan())
}

#[cfg(feature = "python")]
/// The hash of a float under Python-set semantics: `hash(0.0) == hash(-0.0)`
/// (CPython normalizes them), and every NaN hashes to one canonical form so
/// `Hash` agrees with `feq`'s NaN folding. `pub(crate)` so the marshaller's
/// `to_python` can sort slot ids by the same normalized bits (deterministic
/// rebuild order).
pub(crate) fn slot_bits(f: f64) -> u64 {
    if f == 0.0 {
        0
    } else if f.is_nan() {
        0x7ff8_0000_0000_0000
    } else {
        f.to_bits()
    }
}

#[cfg(feature = "python")]
/// Immutable snapshot of the board at a pipeline point.
///
/// Cloning is cheap for the `Py<PyAny>` fields (a reference-count bump);
/// the owned fields (`net_order`, `used_slots`) clone their values.
#[derive(Clone)]
pub struct BoardState {
    // ---- Already-migrated or trivial types ----
    pub net_order: Vec<String>,

    // ---- Marshalling-pending (Phase A): `Py<PyAny>` ----
    pub board: Option<pyo3::Py<PyAny>>,
    pub netlist: Option<pyo3::Py<PyAny>>,
    pub loops: Option<pyo3::Py<PyAny>>,
    pub grid: Option<pyo3::Py<PyAny>>,
    pub drc_oracle: Option<pyo3::Py<PyAny>>,
    pub drc_violations: Option<pyo3::Py<PyAny>>,
    pub design_rules: Option<pyo3::Py<PyAny>>,
    pub connectivity_violations: Option<pyo3::Py<PyAny>>,
    pub placement_violations: Option<pyo3::Py<PyAny>>,
    pub placements: Option<pyo3::Py<PyAny>>, // frozenset of placements
    // U1 (O-C3): the first field ported off `Py<PyAny>` — a `frozenset` of
    // `(x, y)` slot-id tuples (float grid coords) ↔ `HashSet<SlotId>`.
    // Round-trip through `marshal.rs` is bit-identical (U0 gate shape +
    // the U1 gate); stages read/write it through the marshaller, the Python
    // side is unchanged.
    pub used_slots: Option<HashSet<SlotId>>, // frozenset of slot ids
    pub config: Option<pyo3::Py<PyAny>>,
    pub component_domain_map: Option<pyo3::Py<PyAny>>,
    pub routing_corridors: Option<pyo3::Py<PyAny>>,
    pub domain_regions: Option<pyo3::Py<PyAny>>,
    pub routes: Option<pyo3::Py<PyAny>>,
    pub vias: Option<pyo3::Py<PyAny>>,
    pub violations: Option<pyo3::Py<PyAny>>,
    pub zones: Option<pyo3::Py<PyAny>>,
    pub component_zone_map: Option<pyo3::Py<PyAny>>,
    pub zone_slots: Option<pyo3::Py<PyAny>>,
    pub layer_assignments: Option<pyo3::Py<PyAny>>,
    // D5: the per-(component, lv_pin, hv_pin) clearance reclaim dict emitted
    // by ZoneAwareSlotGenerationStage (Python value may also be None -- a
    // None Python value maps to Rust None, like every other field).
    pub reclaim_by_pin_pair: Option<pyo3::Py<PyAny>>,
}

#[cfg(feature = "python")]
impl BoardState {
    /// Create an empty state — all fields `None`.
    pub fn new() -> Self {
        Self {
            net_order: Vec::new(),
            board: None,
            netlist: None,
            loops: None,
            grid: None,
            drc_oracle: None,
            drc_violations: None,
            design_rules: None,
            connectivity_violations: None,
            placement_violations: None,
            placements: None,
            used_slots: None,
            config: None,
            component_domain_map: None,
            routing_corridors: None,
            domain_regions: None,
            routes: None,
            vias: None,
            violations: None,
            zones: None,
            component_zone_map: None,
            zone_slots: None,
            layer_assignments: None,
            reclaim_by_pin_pair: None,
        }
    }

    /// Builder: set the net ordering (the one typed, owned field).
    pub fn with_net_order(mut self, net_order: Vec<String>) -> Self {
        self.net_order = net_order;
        self
    }
}

#[cfg(feature = "python")]
impl Default for BoardState {
    fn default() -> Self {
        Self::new()
    }
}
