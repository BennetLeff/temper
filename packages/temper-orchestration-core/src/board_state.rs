//! `CoreBoardState` — the owned, pyo3-free data model (SPIKE skeleton).
//!
//! This is the wasm32-tier forcing function: `temper-orchestration`'s
//! `BoardState` (`board_state.rs`) holds 23 `Option<pyo3::Py<PyAny>>` fields,
//! which cannot exist in a wasm32 module (there is no interpreter to own the
//! object). Running the loop on the Worker tier therefore REQUIRES every
//! field to become an owned Rust struct. That transformation is exactly the
//! pure-Rust data-model port laid out in
//! `/tmp/opencode/rust-pure-datamodel-brainstorm.md` §1.1 (units U0-U4).
//!
//! This file demonstrates the SHAPE of that port on a representative subset
//! of the fields (the brainstorm's own "trivial" and "yes" rows) — enough to
//! prove `CoreBoardState` compiles for wasm32 and feeds the decision kernels
//! in `decisions.rs`. It deliberately omits the "hard keeps" (`config` =
//! pydantic, `routing_corridors`/`domain_regions` = shapely) except as
//! documented placeholders, because those are the brainstorm's open questions,
//! not a spike's job to resolve.
//!
//! Mapping to the real `BoardState` fields (brainstorm §1.1 row numbers):
//!
//! | This skeleton       | Real field            | Brainstorm verdict |
//! |---------------------|-----------------------|--------------------|
//! | `net_order`         | `net_order` (owned)   | already owned (#23) |
//! | `zones`             | `zones`               | Yes, trivial (#18) |
//! | `placements`        | `placements`          | Yes (#9)           |
//! | `drc_violations`    | `drc_violations`      | Yes (#6)           |
//! | `used_slots`        | `used_slots`          | Yes (#10)          |
//! | `component_domain_map` | `component_domain_map` | Yes (#12)        |
//! | `config`            | `config` (pydantic)   | hard keep (#11) — placeholder enum |
//!
//! The concrete-Python-type hazard (brainstorm §5.1) is out of scope for the
//! skeleton: the real port must resolve `Val`-enum vs. per-field canonical-type
//! for bit-exact `repr`/`==`/numpy-dtype parity. The skeleton uses plain
//! `f64`/`String`/`i64` to keep the shape legible.

use std::collections::{HashMap, HashSet};

/// A zone's name and axis-aligned bounds (brainstorm §1.1 #18 — "trivial").
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ZoneOwned {
    pub name: String,
    pub bounds: RectOwned,
}

/// A 2D axis-aligned rectangle (the owned twin of the Python
/// `((x0, y0), (x1, y1))` zone bounds).
#[derive(Debug, Clone, Copy, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct RectOwned {
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
}

/// A placement: a component reference and its resolved position (brainstorm
/// §1.1 #9).
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PlacementOwned {
    pub reference: String,
    pub x: f64,
    pub y: f64,
    pub rotation: f64,
}

/// A DRC violation (brainstorm §1.1 #6 — `Violation` is a plain dataclass;
/// `Point` already exists in `temper-geometry::types`).
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ViolationOwned {
    pub violation_type: String,
    pub geometry_a_id: String,
    pub geometry_b_id: String,
    pub net_a: String,
    pub net_b: String,
    pub clearance_actual: f64,
    pub clearance_required: f64,
    pub x: f64,
    pub y: f64,
}

/// The HV/LV domain assignment (brainstorm §1.1 #12).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum Domain {
    Hv,
    Lv,
}

/// The `config` field is the brainstorm's hard keep #11 (pydantic, R7 SSOT,
/// "final authority, never reimplemented"). The pure-Rust pipeline does not
/// reimplement it; it carries the config as one of (a) an opaque token owned
/// by the host tier, or (b) the already-migrated typed `PipelineConfig`.
///
/// This enum is a PLACEHOLDER that documents the boundary; the real port's
/// decision (keep-as-opaque vs. serde-port) is out of scope for a spike.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum CoreConfig {
    /// The host owns the pydantic object; the core only carries a key.
    Opaque(String),
    /// The typed placement-pipeline config that has already landed in Rust
    /// (`pipeline_state::PipelineConfig`).
    Typed,
}

/// The owned, pyo3-free snapshot of the board at a pipeline point.
///
/// `Clone` here is a real (deep-ish) clone of owned data — the opposite of
/// the `BoardState` clone, which is a reference-count bump on `Py<PyAny>`.
/// The pure-Rust pipeline can afford it because `Stage::run` takes the state
/// by value; a real implementation would `Arc` the large fields (grid, oracle)
/// to keep the per-stage clone cheap. Noted, not resolved, here.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct CoreBoardState {
    pub net_order: Vec<String>,
    pub zones: Vec<ZoneOwned>,
    pub placements: HashMap<String, PlacementOwned>,
    pub drc_violations: Vec<ViolationOwned>,
    pub used_slots: HashSet<String>,
    pub component_domain_map: HashMap<String, Domain>,
    pub config: Option<CoreConfig>,
}

impl CoreBoardState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_net_order(mut self, net_order: Vec<String>) -> Self {
        self.net_order = net_order;
        self
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn core_board_state_holds_owned_data_without_pyany() {
        // The point of the whole crate, stated as a test: every field is an
        // owned Rust value, so no `Py<PyAny>` (and no pyo3 dependency) exists
        // anywhere in the type graph. This compiles only because that is true.
        let mut state = CoreBoardState::new();
        state.net_order = vec!["VCC".into(), "GND".into()];
        state.zones.push(ZoneOwned {
            name: "hv".into(),
            bounds: RectOwned { x0: 0.0, y0: 0.0, x1: 10.0, y1: 5.0 },
        });
        state
            .placements
            .insert("R1".into(), PlacementOwned { reference: "R1".into(), x: 1.0, y: 2.0, rotation: 0.0 });
        state.drc_violations.push(ViolationOwned {
            violation_type: "clearance".into(),
            geometry_a_id: "a".into(),
            geometry_b_id: "b".into(),
            net_a: "VCC".into(),
            net_b: "GND".into(),
            clearance_actual: 0.3,
            clearance_required: 1.0,
            x: 4.0,
            y: 4.0,
        });
        state.component_domain_map.insert("R1".into(), Domain::Hv);
        state.config = Some(CoreConfig::Opaque("host-key".into()));

        assert_eq!(state.zones.len(), 1);
        assert_eq!(state.placements.len(), 1);
        assert_eq!(state.drc_violations.len(), 1);
        assert_eq!(state.component_domain_map["R1"], Domain::Hv);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("board_state::tests::core_board_state_holds_owned_data_without_pyany", core_board_state_holds_owned_data_without_pyany),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
