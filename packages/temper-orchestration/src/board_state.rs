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
use temper_data_model::{
    ConnectivityViolationList, LayerAssignmentSet, PlacementSet, PlacementViolationList, Route,
    StrPairSet, ViolationList, ZoneSet, ZoneSlotsSet,
};

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
/// A `BoardState.routes` element.
///
/// `routes` is documented as "frozenset of Trace objects", and every
/// PRODUCTION write site (`DRCSweepStage`, `TrackDeduplicationStage`,
/// `ShortCircuitDetectionStage`) only ever inserts `Trace`s. But the pinned
/// oracle (`tests/deterministic/_drc_sweep_run_py_oracle.py`) and every one
/// of those ported stages' own `run_inner` bodies explicitly guard with
/// `isinstance(entry, Trace)` and pass a non-Trace entry through UNCHANGED
/// ("non-Trace route entries pass through" is in their doc comments) — a
/// defensive contract the differential suite tests directly
/// (`test_ds_non_trace_route_entries_pass_through`,
/// `test_td_non_trace_pass_through_and_stdout`, and
/// `test_dedup_via_before_duplicates_remaps_indices`, which puts a `Via` in
/// `routes`). `Route::from_python` requires Trace-shaped attributes
/// (`.start`/`.end`/...), so a non-Trace element must not be forced through
/// it. `Opaque` keeps it as an identity-preserved Python reference instead —
/// the same "Keeps" philosophy `marshal.rs`'s `Plain::Opaque` documents for
/// values with no owned representation.
#[derive(Clone, Debug)]
pub enum RouteEntry {
    Trace(Route),
    Opaque(pyo3::Py<PyAny>),
}

#[cfg(feature = "python")]
impl PartialEq for RouteEntry {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (RouteEntry::Trace(a), RouteEntry::Trace(b)) => a == b,
            // Identity, not `==`: an opaque entry has no owned
            // representation to compare structurally (the same "Keeps"
            // reasoning `Plain::Opaque` uses).
            (RouteEntry::Opaque(a), RouteEntry::Opaque(b)) => a.as_ptr() == b.as_ptr(),
            _ => false,
        }
    }
}

#[cfg(feature = "python")]
impl Eq for RouteEntry {}

#[cfg(feature = "python")]
impl Hash for RouteEntry {
    fn hash<H: Hasher>(&self, state: &mut H) {
        match self {
            RouteEntry::Trace(r) => {
                0u8.hash(state);
                r.hash(state);
            }
            RouteEntry::Opaque(o) => {
                1u8.hash(state);
                (o.as_ptr() as usize).hash(state);
            }
        }
    }
}

#[cfg(feature = "python")]
/// A `BoardState.vias` element — the `RouteEntry` pattern applied to `vias`.
///
/// `DRCSweepStage`/`ViaValidationStage`/`ViaDeduplicationStage` guard every
/// `vias` read with `isinstance(entry, Via)` and pass a non-Via entry
/// through unchanged, the same documented tolerance `routes` has for
/// non-Trace entries (see `RouteEntry`'s doc). `Via::from_python` requires
/// Via-shaped attributes (`.position`/`.drill`/...), so a non-Via element
/// keeps as an opaque identity-preserved Python reference instead.
#[derive(Clone, Debug)]
pub enum ViaEntry {
    Via(temper_data_model::Via),
    Opaque(pyo3::Py<PyAny>),
}

#[cfg(feature = "python")]
impl PartialEq for ViaEntry {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (ViaEntry::Via(a), ViaEntry::Via(b)) => a == b,
            (ViaEntry::Opaque(a), ViaEntry::Opaque(b)) => a.as_ptr() == b.as_ptr(),
            _ => false,
        }
    }
}

#[cfg(feature = "python")]
impl Eq for ViaEntry {}

#[cfg(feature = "python")]
impl Hash for ViaEntry {
    fn hash<H: Hasher>(&self, state: &mut H) {
        match self {
            ViaEntry::Via(v) => {
                0u8.hash(state);
                v.hash(state);
            }
            ViaEntry::Opaque(o) => {
                1u8.hash(state);
                (o.as_ptr() as usize).hash(state);
            }
        }
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
    // U6 (O-C3): the three validation-result fields ported off `Py<PyAny>` —
    // each is the Python `tuple[Violation, ...] | None` ↔ the owned
    // `*List` `Vec` newtype (U5). Round-trip through `marshal.rs` is lossless
    // (the U5 round-trip gate); stages write the tuple through the owned type,
    // the Python side is unchanged.
    pub drc_violations: Option<ViolationList>, // tuple[Violation, ...] | None
    pub design_rules: Option<pyo3::Py<PyAny>>,
    pub connectivity_violations: Option<ConnectivityViolationList>, // tuple[ConnectivityViolation, ...] | None
    pub placement_violations: Option<PlacementViolationList>, // tuple[PlacementViolation, ...] | None
    // U6 (O-C3) group-2: the six remaining COLLECTION fields ported off
    // `Py<PyAny>` — each is the Python `frozenset[T, ...] | None` ↔ the
    // owned `*Set` `HashSet` newtype (U5). Round-trip through `marshal.rs`
    // is lossless for the guaranteed shapes (the U5 round-trip gate);
    // stages write the frozenset through the owned type, the Python side is
    // unchanged. The rebuilt frozenset's iteration order is a deterministic
    // function of the VALUES (the U5 sorted-repr rebuild), never the
    // process-random `HashSet` order.
    pub placements: Option<PlacementSet>, // frozenset of placements
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
    pub routes: Option<HashSet<RouteEntry>>, // frozenset of Trace objects (+ opaque non-Trace pass-through)
    pub vias: Option<HashSet<ViaEntry>>, // frozenset of Via objects (+ opaque non-Via pass-through)
    pub violations: Option<pyo3::Py<PyAny>>,
    pub zones: Option<ZoneSet>, // frozenset of zone-geometry Zone objects
    pub component_zone_map: Option<StrPairSet>, // frozenset of (ref, zone) pairs
    pub zone_slots: Option<ZoneSlotsSet>, // frozenset of (zone, tuple(slots)) entries
    pub layer_assignments: Option<LayerAssignmentSet>, // frozenset of LayerAssignment objects
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
