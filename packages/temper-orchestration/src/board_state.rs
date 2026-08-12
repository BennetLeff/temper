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
//
// Fields are `Option` because the pipeline populates them incrementally
// across stages; a stage that reads a field asserts it is `Some` or returns
// `Err(StageError)`. Fields are `pub` — the eventual Python `run()` shim
// constructs the initial `BoardState` from Python objects (crossing FFI once
// per pipeline, not per stage) by setting them directly.

#[cfg(feature = "python")]
use pyo3::PyAny;

#[cfg(feature = "python")]
/// Immutable snapshot of the board at a pipeline point.
///
/// Cloning is cheap for the `Py<PyAny>` fields (a reference-count bump);
/// `net_order` is the one owned field the deterministic stages mutate.
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
    pub placements: Option<pyo3::Py<PyAny>>,    // frozenset of placements
    pub used_slots: Option<pyo3::Py<PyAny>>,     // frozenset of slot ids
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
