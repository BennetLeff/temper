//! The U5 (O-C3) owned COLLECTION element structs + the owned collection
//! field types for the remaining `BoardState` fields (`zones`,
//! `component_zone_map`, `zone_slots`, `layer_assignments`, `routes`,
//! `vias`, `violations`, `placements`, `component_domain_map`, and the three
//! violation lists `drc_violations` / `connectivity_violations` /
//! `placement_violations`).
//!
//! # The element-type survey (reused vs new)
//!
//! Every candidate wire-format type was checked before defining anything:
//!
//! - `temper-drc-rs`'s `violation_contracts::Violation` is a **pyclass**
//!   whose `type`/`severity`/`description`/`pos` slots are uncoerced
//!   `Py<PyAny>` passthrough handles — it is the DRC-feedback *wire class*,
//!   not an owned wire format, and it lives in a pyo3 crate this crate
//!   cannot depend on. Not reusable.
//! - The design-bundle contract pyclasses (`Zone` in `board_contracts.rs`,
//!   `LayerAssignment` in `deterministic_leaves.rs`, `Trace`/`Via` in
//!   `board_contracts.rs`) are **pyclasses with uncoerced `Py<PyAny>`
//!   fields** — they are the Python-visible classes, not owned Rust data.
//!   The deterministic `Zone` (`stages/zone_geometry.py`, 2 fields) is a
//!   different class from the board `Zone` (11 fields) entirely.
//! - `temper-drc-rs`'s `DrcViaSnapshot`/`DrcTraceSnapshot` are K1-dict
//!   snapshots for the DRC kernel input — a deliberately different shape
//!   (flat `x`/`y` floats, no `net: Option`), not the board `Via`/`Trace`
//!   contract. Not reusable.
//!
//! Conclusion: **all U5 element types are NEW owned structs**, defined here
//! so the pyo3-free (wasm32) tier can hold them; the `Marshal` impls (the
//! pyo3 half) live in `temper-orchestration`'s `netlist_owned.rs`.
//!
//! # The owned collection field types
//!
//! | `BoardState` field | Python shape | Owned type |
//! |---|---|---|
//! | `zones` | `frozenset[Zone]` | [`ZoneSet`] (`HashSet<Zone>`) |
//! | `component_zone_map` | `frozenset[(str, str)]` | [`StrPairSet`] |
//! | `component_domain_map` | `frozenset[(str, str)]` | [`StrPairSet`] |
//! | `zone_slots` | `frozenset[(str, tuple[slots])]` | [`ZoneSlotsSet`] |
//! | `layer_assignments` | `frozenset[LayerAssignment]` | [`LayerAssignmentSet`] |
//! | `routes` | `frozenset[Trace]` | [`RouteSet`] |
//! | `vias` | `frozenset[Via]` | [`ViaSet`] |
//! | `placements` | `frozenset[(ref, (x, y))]` | [`PlacementSet`] |
//! | `violations` | PreflightReport dict | [`PreflightReport`] |
//! | `drc_violations` | `tuple[Violation, ...] \| None` | [`ViolationList`] |
//! | `connectivity_violations` | `tuple[ConnectivityViolation, ...] \| None` | [`ConnectivityViolationList`] |
//! | `placement_violations` | `tuple[PlacementViolation, ...] \| None` | [`PlacementViolationList`] |
//!
//! # The set-iteration-order bound (inherited from U1 — NARROWER than it looks)
//!
//! Every `frozenset`-backed field is owned as a `HashSet` of its element
//! type, structurally like U1's `HashSet<SlotId>`: membership content and
//! `==` are preserved in every round-trip. The orchestration-side
//! `to_python` sorts the rebuilt elements by their Python `repr` before
//! insertion (see `netlist_owned.rs`), which makes the rebuild REPRODUCIBLE
//! WITHIN a fixed process/`PYTHONHASHSEED` (repeated rebuilds of the same
//! owned value agree) — this comment previously claimed that also makes the
//! rebuilt frozenset's iteration order "a DETERMINISTIC function of the
//! values" full stop, i.e. stable ACROSS different `PYTHONHASHSEED` values.
//! That is FALSE for every element type this crate actually defines: `Zone`,
//! `Trace`/`Via`, `LayerAssignment`, the `(str, str)` pair types, etc. all
//! hash through at least one `str` field, and CPython salts `str`/`bytes`
//! hashing per process (PEP 456) — empirically disproven during PR #1137's
//! investigation (same repr-sorted insertion sequence, different final
//! frozenset iteration order across 5+ `PYTHONHASHSEED` values). U1's ORIGINAL
//! claim is still true for `HashSet<SlotId>` specifically, because `SlotId`
//! is `(f64, f64)` and CPython does not salt float hashing — that narrower
//! fact does not generalize to string-hashing element types, and restating it
//! here as if it did was the bug. Bit-identity (type + `repr` + `==`) is
//! pinned by the round-trip gate only on the guaranteed shapes (empty /
//! single-element, where order is vacuous); a multi-element set round-trips
//! content-identically (type, `==`, membership) but its iteration order is
//! NOT asserted across runs — callers needing a stable visible order must
//! sort explicitly at the point of consumption (see
//! `temper_placer.io._write_tracks`'s emission-key pattern, and PR #1137's
//! fix to the dedup stages' "first wins" tie-break).
//!
//! # The owned-equality bound (frozenset elements)
//!
//! The `Eq`/`Hash` impls here mirror CPython's *set-element* semantics:
//! `-0.0` normalizes to `0.0` (CPython `hash(0.0) == hash(-0.0)` and
//! `(0.0,) == (-0.0,)`), and NaN folds to one canonical form so `Eq` stays
//! reflexive. The [`Val`]-shaped fields (`Zone.bounds`, `LayerAssignment
//! .layer`) keep the int-vs-float distinction: `Int(2)` is NOT equal to
//! `Float(2.0)` in the owned model (the U0 `Val` discipline), so their
//! hashes are variant-tagged. CPython's `==` is COARSER there (`2 == 2.0`,
//! `hash(2) == hash(2.0)`), so Python would dedupe `LayerAssignment('N', 2)`
//! and `LayerAssignment('N', 2.0)` in one frozenset where the owned set can
//! hold both — but any set READ from Python cannot contain both (Python
//! already deduped them), so the round-trip preserves content in every
//! case. A set constructed by hand in Rust could hold both; rebuilding it
//! would collapse them to the Python-first element. Recorded bound.

use std::collections::HashSet;
use std::hash::{Hash, Hasher};

use crate::Val;

// ---------------------------------------------------------------------------
// Float/Val equality + hashing helpers (mirror `board_state::SlotId`'s
// normalized-bits semantics, defined here so the pyo3-free crate can hold
// these element types without importing orchestration)
// ---------------------------------------------------------------------------

/// Python `==` for floats: value equality with `NaN == NaN` folded true so
/// the set-element `Eq` impls stay reflexive (NaNs never occur in real
/// pipeline data — the U1 `feq` convention).
fn feq(a: f64, b: f64) -> bool {
    a == b || (a.is_nan() && b.is_nan())
}

/// The hash of a float under Python-set semantics: `hash(0.0) ==
/// hash(-0.0)` (CPython normalizes them) and every NaN hashes to one
/// canonical form so `Hash` agrees with [`feq`]'s NaN folding. Mirrors
/// orchestration's `board_state::slot_bits` bit-for-bit.
fn f64_bits(f: f64) -> u64 {
    if f == 0.0 {
        0
    } else if f.is_nan() {
        0x7ff8_0000_0000_0000
    } else {
        f.to_bits()
    }
}

/// Owned equality for [`Val`]: the variant is part of the value (`Int(2)`
/// != `Float(2.0)` — the U0 discipline), floats compare with [`feq`].
fn val_eq(a: &Val, b: &Val) -> bool {
    match (a, b) {
        (Val::Int(x), Val::Int(y)) => x == y,
        (Val::Float(x), Val::Float(y)) => feq(*x, *y),
        _ => false,
    }
}

/// The hash of a [`Val`], variant-tagged so `Hash` agrees with [`val_eq`]:
/// the `Int` branch always has the low bit set, the `Float` branch never
/// does (CPython's own `hash(2) == hash(2.0)` cross-type equality is
/// deliberately NOT reproduced — the owned model distinguishes them).
fn val_bits(v: &Val) -> u64 {
    match v {
        Val::Int(i) => (*i as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15) | 0x01,
        Val::Float(f) => f64_bits(*f) & !0x01,
    }
}

// ---------------------------------------------------------------------------
// The frozenset ELEMENT structs — each mirrors the hashable Python object
// the field's frozenset holds (`Eq` + `Hash` required for the `HashSet`)
// ---------------------------------------------------------------------------

/// A placement zone (`stages/zone_geometry.py::Zone`, the 2-field frozen
/// dataclass the `ZoneGeometryStage` writes into `BoardState.zones` — NOT
/// the 11-field `board_contracts.Zone`).
///
/// `bounds` is `((Val, Val), (Val, Val))`: the stage's int-vs-float
/// type-carrying canon is documented in `zone_geometry_stage.rs` ("HV
/// `x_min`/every `y_min` are Python `int` `0`, board-dims pass through with
/// their original type"), so each coordinate is `Val`-shaped.
#[derive(Clone, Debug)]
pub struct Zone {
    pub name: String,
    /// `((x_min, y_min), (x_max, y_max))` — the nested 2-tuple the
    /// dataclass stores.
    pub bounds: ((Val, Val), (Val, Val)),
}

impl PartialEq for Zone {
    fn eq(&self, other: &Self) -> bool {
        self.name == other.name
            && val_eq(&self.bounds.0 .0, &other.bounds.0 .0)
            && val_eq(&self.bounds.0 .1, &other.bounds.0 .1)
            && val_eq(&self.bounds.1 .0, &other.bounds.1 .0)
            && val_eq(&self.bounds.1 .1, &other.bounds.1 .1)
    }
}

impl Eq for Zone {}

impl Hash for Zone {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.name.hash(state);
        val_bits(&self.bounds.0 .0).hash(state);
        val_bits(&self.bounds.0 .1).hash(state);
        val_bits(&self.bounds.1 .0).hash(state);
        val_bits(&self.bounds.1 .1).hash(state);
    }
}

/// A routed trace segment (`board_contracts.Trace`, frozen — the element of
/// `BoardState.routes`; `Route` is the owned name so the pyo3-free crate
/// need not shadow anything).
///
/// Coordinates/width are concrete `f64`: the router and the D6 tests
/// construct `Trace(start=..., end=..., width=0.2, ...)` with floats only —
/// an int-shaped coordinate or width is a loud marshalling error (the U1
/// "slot coordinates are floats" policy), never a silent widen.
#[derive(Clone, Debug)]
pub struct Route {
    pub start: (f64, f64),
    pub end: (f64, f64),
    pub width: f64,
    pub layer: String,
    pub net: Option<String>,
}

impl PartialEq for Route {
    fn eq(&self, other: &Self) -> bool {
        feq(self.start.0, other.start.0)
            && feq(self.start.1, other.start.1)
            && feq(self.end.0, other.end.0)
            && feq(self.end.1, other.end.1)
            && feq(self.width, other.width)
            && self.layer == other.layer
            && self.net == other.net
    }
}

impl Eq for Route {}

impl Hash for Route {
    fn hash<H: Hasher>(&self, state: &mut H) {
        f64_bits(self.start.0).hash(state);
        f64_bits(self.start.1).hash(state);
        f64_bits(self.end.0).hash(state);
        f64_bits(self.end.1).hash(state);
        f64_bits(self.width).hash(state);
        self.layer.hash(state);
        self.net.hash(state);
    }
}

/// A plated through-hole via (`board_contracts.Via`, frozen — the element
/// of `BoardState.vias`).
///
/// `position`/`drill`/`width` are concrete `f64` (the router and the D6
/// stages always produce floats — int-shaped values are loud errors);
/// `layers` is the `("F.Cu", "B.Cu")` 2-tuple the pyclass defaults to and
/// every construction site passes.
#[derive(Clone, Debug)]
pub struct Via {
    pub position: (f64, f64),
    pub drill: f64,
    pub width: f64,
    pub layers: (String, String),
    pub net: Option<String>,
    pub is_diff_pair: bool,
}

impl PartialEq for Via {
    fn eq(&self, other: &Self) -> bool {
        feq(self.position.0, other.position.0)
            && feq(self.position.1, other.position.1)
            && feq(self.drill, other.drill)
            && feq(self.width, other.width)
            && self.layers == other.layers
            && self.net == other.net
            && self.is_diff_pair == other.is_diff_pair
    }
}

impl Eq for Via {}

impl Hash for Via {
    fn hash<H: Hasher>(&self, state: &mut H) {
        f64_bits(self.position.0).hash(state);
        f64_bits(self.position.1).hash(state);
        f64_bits(self.drill).hash(state);
        f64_bits(self.width).hash(state);
        self.layers.hash(state);
        self.net.hash(state);
        self.is_diff_pair.hash(state);
    }
}

/// A net→layer assignment (`deterministic_leaves.rs::LayerAssignment`,
/// frozen — the element of `BoardState.layer_assignments`).
///
/// `layer` is [`Val`]-shaped: the pyclass stores it UNCOERCED ("an int
/// layer stays int" — `assign_layer_by_net_class` returns `i64` and the
/// manual-assignment dict is int-keyed, but the no-coercion contract makes
/// a float layer legal too), so `2` stays `2` and `2.0` stays `2.0`.
#[derive(Clone, Debug)]
pub struct LayerAssignment {
    pub net_name: String,
    pub layer: Val,
    pub allow_layer_change: bool,
    pub is_plane: bool,
}

impl PartialEq for LayerAssignment {
    fn eq(&self, other: &Self) -> bool {
        self.net_name == other.net_name
            && val_eq(&self.layer, &other.layer)
            && self.allow_layer_change == other.allow_layer_change
            && self.is_plane == other.is_plane
    }
}

impl Eq for LayerAssignment {}

impl Hash for LayerAssignment {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.net_name.hash(state);
        val_bits(&self.layer).hash(state);
        self.allow_layer_change.hash(state);
        self.is_plane.hash(state);
    }
}

/// A placed component — the `(ref, (x, y))` 2-tuple element of
/// `BoardState.placements` (`frozenset(placements.items())` where the
/// values are the float grid positions `assign_inner` produced).
///
/// `position` is concrete `(f64, f64)` — the U1 slot-coordinate policy
/// (an int-shaped position is a loud error).
#[derive(Clone, Debug)]
pub struct Placement {
    pub ref_: String,
    pub position: (f64, f64),
}

impl PartialEq for Placement {
    fn eq(&self, other: &Self) -> bool {
        self.ref_ == other.ref_
            && feq(self.position.0, other.position.0)
            && feq(self.position.1, other.position.1)
    }
}

impl Eq for Placement {}

impl Hash for Placement {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.ref_.hash(state);
        f64_bits(self.position.0).hash(state);
        f64_bits(self.position.1).hash(state);
    }
}

/// A grid-slot position — the `(x, y)` float pair inside a `zone_slots`
/// entry's slots tuple. The pyo3-free twin of orchestration's `SlotId`
/// (same normalized-bits `Eq`/`Hash` semantics; defined here so
/// `temper-data-model` can hold `zone_slots` without importing the
/// python-gated `board_state` module).
#[derive(Clone, Copy, Debug)]
pub struct SlotPos(pub f64, pub f64);

impl PartialEq for SlotPos {
    fn eq(&self, other: &Self) -> bool {
        feq(self.0, other.0) && feq(self.1, other.1)
    }
}

impl Eq for SlotPos {}

impl Hash for SlotPos {
    fn hash<H: Hasher>(&self, state: &mut H) {
        f64_bits(self.0).hash(state);
        f64_bits(self.1).hash(state);
    }
}

/// One `zone_slots` entry — the `(zone_name, tuple_of_slots)` 2-tuple
/// element of `BoardState.zone_slots`. The slots tuple is ORDERED (a Python
/// tuple, not a set), so `slots` is a `Vec` preserving that order; the
/// element as a whole is hashable in Python (str + tuple of float tuples),
/// so this struct is `Eq + Hash` for the owning `HashSet`.
#[derive(Clone, Debug)]
pub struct ZoneSlots {
    pub zone: String,
    pub slots: Vec<SlotPos>,
}

impl PartialEq for ZoneSlots {
    fn eq(&self, other: &Self) -> bool {
        self.zone == other.zone && self.slots == other.slots
    }
}

impl Eq for ZoneSlots {}

impl Hash for ZoneSlots {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.zone.hash(state);
        self.slots.hash(state);
    }
}

// ---------------------------------------------------------------------------
// The tuple-backed ELEMENT structs — the violation dataclasses (the three
// violation lists are Python TUPLES, so these need no `Hash`)
// ---------------------------------------------------------------------------

/// A DRC violation (`router_v6/constraints_drc_oracle.py::Violation` — the
/// `drc_violations` element). `clearance_actual`/`clearance_required` come
/// from the drc-rs `drc_oracle_validate_all_py` records (always floats);
/// `location` is the `Point(x, y)` the oracle builds from the kernel's
/// float coordinates. Not the `temper-drc-rs` `violation_contracts::Violation`
/// pyclass (checked in the module doc — different surface, different crate).
#[derive(Clone, Debug, PartialEq)]
pub struct Violation {
    pub type_: String,
    pub geometry_a_id: String,
    pub geometry_b_id: String,
    pub net_a: String,
    pub net_b: String,
    pub clearance_actual: f64,
    pub clearance_required: f64,
    pub location: (f64, f64),
}

/// A connectivity violation (`deterministic/stages/connectivity_validation.py
/// ::ConnectivityViolation` — the `connectivity_violations` element).
#[derive(Clone, Debug, PartialEq)]
pub struct ConnectivityViolation {
    pub type_: String,
    pub net: String,
    pub location: (f64, f64),
    pub description: String,
}

/// A placement violation (`deterministic/stages/placement_validation.py
/// ::PlacementViolation` — the `placement_violations` element). The four
/// optional fields default to `None` in the dataclass; the proximity/
/// signal-HV helpers leave them unset on the `missing_component` shape.
#[derive(Clone, Debug, PartialEq)]
pub struct PlacementViolation {
    pub constraint_name: String,
    pub violation_type: String,
    pub message: String,
    pub severity: String,
    pub component_a: Option<String>,
    pub component_b: Option<String>,
    pub actual_distance_mm: Option<f64>,
    pub required_distance_mm: Option<f64>,
}

// ---------------------------------------------------------------------------
// The `violations` (PreflightReport) structs — the report is plain data
// ---------------------------------------------------------------------------

/// A plain nested value (the pyo3-free subset of orchestration `Plain` that
/// the PreflightReport `details` dicts need): `None`/`bool`/`int`/`float`/
/// `str`/`list`/`dict` (str keys only). No `Opaque` (this crate is
/// pyo3-free), no `bytes`/`set`/`frozenset`/`tuple` — the report's
/// `details` in the real pipeline is `None` or a dict of lists of strings,
/// and an unsupported kind is a LOUD marshalling error, never a silent
/// kind-change.
#[derive(Clone, Debug, PartialEq)]
pub enum OwnedPlain {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    List(Vec<OwnedPlain>),
    Dict(Vec<(String, OwnedPlain)>),
}

/// One preflight check (`pipeline/preflight.py::PreflightCheck` shape, as
/// the dict the Rust `PreflightStage` writes: `name`/`result`/`message`/
/// `details`/`time_ms`).
#[derive(Clone, Debug, PartialEq)]
pub struct PreflightCheck {
    pub name: String,
    pub result: String,
    pub message: String,
    pub details: Option<OwnedPlain>,
    pub time_ms: f64,
}

/// The preflight report (`BoardState.violations` at runtime — the
/// PreflightReport-shaped dict `{checks, overall, total_time_ms}` the
/// `PreflightStage` writes; see `preflight_stage.rs`'s header comment).
#[derive(Clone, Debug, PartialEq)]
pub struct PreflightReport {
    pub checks: Vec<PreflightCheck>,
    pub overall: String,
    pub total_time_ms: f64,
}

// ---------------------------------------------------------------------------
// The owned COLLECTION FIELD types
// ---------------------------------------------------------------------------

macro_rules! set_newtype {
    ($name:ident, $elem:ty) => {
        /// The owned form of a `frozenset` `BoardState` field: a
        /// `HashSet` of the element type (U1's `HashSet<SlotId>` pattern —
        /// membership content + `==` preserved, deterministic sorted
        /// rebuild on write-back; see the module doc's bounds).
        #[derive(Clone, Debug, PartialEq)]
        pub struct $name(pub HashSet<$elem>);

        impl std::ops::Deref for $name {
            type Target = HashSet<$elem>;
            fn deref(&self) -> &Self::Target {
                &self.0
            }
        }
    };
}

set_newtype!(ZoneSet, Zone);
set_newtype!(StrPairSet, (String, String));
set_newtype!(ZoneSlotsSet, ZoneSlots);
set_newtype!(LayerAssignmentSet, LayerAssignment);
set_newtype!(RouteSet, Route);
set_newtype!(ViaSet, Via);
set_newtype!(PlacementSet, Placement);

macro_rules! list_newtype {
    ($name:ident, $elem:ty) => {
        /// The owned form of a `tuple[T, ...]` `BoardState` field: an
        /// order-preserving `Vec` of the element type (the tuple's order is
        /// load-bearing). The orchestration-side `Marshal` reads/writes a
        /// Python TUPLE (a list is rejected — the contract is a tuple).
        #[derive(Clone, Debug, PartialEq)]
        pub struct $name(pub Vec<$elem>);

        impl std::ops::Deref for $name {
            type Target = Vec<$elem>;
            fn deref(&self) -> &Self::Target {
                &self.0
            }
        }
    };
}

list_newtype!(ViolationList, Violation);
list_newtype!(ConnectivityViolationList, ConnectivityViolation);
list_newtype!(PlacementViolationList, PlacementViolation);

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// The owned `Eq` mirrors Python set-element semantics where Python's
    /// own `==` is float-value equality: `-0.0` equals `0.0` (and hashes
    /// the same), so `(0.0, 5.0)` and `(-0.0, 5.0)` are the SAME owned
    /// element — exactly the dedupe Python's frozenset performs.
    #[test]
    fn negative_zero_normalizes_in_set_elements() {
        let a = Placement {
            ref_: "R1".into(),
            position: (0.0, 5.0),
        };
        let b = Placement {
            ref_: "R1".into(),
            position: (-0.0, 5.0),
        };
        assert_eq!(a, b, "-0.0 must normalize to 0.0 in owned equality");
        let mut set = HashSet::new();
        set.insert(a);
        set.insert(b);
        assert_eq!(set.len(), 1, "the two placements must dedupe to one element");
    }

    /// The `Val` variant is part of the owned value: `Zone` bounds with
    /// `Val::Int` coordinates are NOT equal to `Val::Float` coordinates (the
    /// U0 discipline), and the hashes agree with that equality (the
    /// variant-tagged `val_bits`).
    #[test]
    fn val_variant_distinguishes_int_from_float_in_set_elements() {
        let int_zone = Zone {
            name: "HV".into(),
            bounds: ((Val::Int(0), Val::Int(0)), (Val::Int(50), Val::Int(80))),
        };
        let float_zone = Zone {
            name: "HV".into(),
            bounds: ((Val::Float(0.0), Val::Float(0.0)), (Val::Float(50.0), Val::Float(80.0))),
        };
        assert_ne!(int_zone, float_zone, "int coords must not equal float coords");
        let mut set = HashSet::new();
        set.insert(int_zone);
        set.insert(float_zone);
        assert_eq!(set.len(), 2, "int and float-shaped zones are distinct owned elements");
    }

    /// The layer field of `LayerAssignment` is `Val`-shaped: an int layer
    /// stays int in the owned value and round-trips without widening (the
    /// pyclass's no-coercion contract, pinned here at the data-model level).
    #[test]
    fn layer_assignment_layer_preserves_int_vs_float() {
        let la = LayerAssignment {
            net_name: "VCC".into(),
            layer: Val::Int(2),
            allow_layer_change: true,
            is_plane: true,
        };
        assert_eq!(la.layer, Val::Int(2));
        assert_ne!(la.layer, Val::Float(2.0));
    }

    /// The newtypes deref to their inner collections (test ergonomics +
    /// the stage-facing read surface).
    #[test]
    fn collection_newtypes_deref() {
        let list = ViolationList(vec![Violation {
            type_: "track_clearance".into(),
            geometry_a_id: "a".into(),
            geometry_b_id: "b".into(),
            net_a: "N1".into(),
            net_b: "N2".into(),
            clearance_actual: 0.1,
            clearance_required: 0.2,
            location: (1.0, 2.0),
        }]);
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].net_a, "N1");
        let set = ZoneSet(HashSet::from([Zone {
            name: "HV".into(),
            bounds: ((Val::Int(0), Val::Int(0)), (Val::Int(50), Val::Int(80))),
        }]));
        assert_eq!(set.len(), 1);
    }
}
