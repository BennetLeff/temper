//! Pure-Rust owned data model for the orchestration data-model port (unit
//! O-C3/U2).
//!
//! This crate is the home of the OWNED leaf structs (`Component`/`Pin`/`Net`)
//! that later units (U3's `Board`/`Netlist` aggregates, U4's remaining fields)
//! compose into a full `CoreBoardState`. It carries **no pyo3 dependency** —
//! the structs here are plain Rust data, importable from the orchestration
//! pyo3 surface (which implements the `Marshal` boundary around them) and,
//! once O-C4 does the physical crate split, from the `wasm32-unknown-unknown`
//! tier. See `packages/temper-orchestration/VERIFICATION.md` (unit O-C3/U2)
//! for the crate-home decision and the field-by-field type rationale.
//!
//! # The `Val`/`Plain` convention (from unit O-C3/U0)
//!
//! The Python dataclasses these mirror (`temper_placer/core/netlist.py`,
//! pinned VERBATIM in `temper-design-bundle`'s pyclasses) perform **no
//! `__init__` coercion**: `Component("R1", "fp", (1, 2))` stores `int`
//! bounds, so `Component.width` returns `int` `1`, not `1.0`. A Rust field
//! typed `f64` would silently widen every such value, changing `repr`, `==`
//! and downstream numpy dtype promotion. The convention (established in
//! `temper-orchestration`'s `marshal.rs`, U0) is therefore:
//!
//! * [`Val`] — the canonical type for a scalar field that can hold `int` OR
//!   `float`; it records which one it was and round-trips it unchanged.
//!   Used for [`Component::bounds`], the one field the pipeline demonstrably
//!   populates with ints (see `netlist_contracts.rs:11-28` and
//!   `dense_package_detection.py:67`'s `bounds=(7, 7)` docstring).
//! * concrete Rust scalars (`String`/`bool`/`f64`/`i64`) — for fields whose
//!   contract type is unambiguous and whose real pipeline values are always
//!   that type. A `f64` field REJECTS an int-shaped value loudly (the U0
//!   "an int is not a float" discipline) rather than widening it.
//! * plain Rust collections — `Vec<(String, String)>` for an insertion-ordered
//!   `dict[str, str]` (`attributes`), `Vec<String>` for a `frozenset` read in
//!   iteration order (`tags`), `(f64, f64)` for the always-float
//!   `tuple[float, float]` fields (`position`, `initial_position`).
//!
//! `Plain` (the lossless nested-value tree with its `Opaque` passthrough for
//! numpy/shapely/foreign pyclasses) stays in `temper-orchestration`'s
//! `marshal.rs` — it is pyo3-shaped by construction and none of the leaf
//! structs here need it.

/// The concrete-Python-type canonical for a field that can hold `int` OR
/// `float` (e.g. a component's bounds `(1, 2)` vs `(1.0, 2.0)`).
///
/// Round-trips preserving WHICH it was — `extract::<f64>()` alone would
/// silently widen `int` `1` to `float` `1.0`, changing `repr` (`1` → `1.0`),
/// `==` against int-sensitive code, and downstream numpy dtype promotion.
///
/// `PartialEq` (not `Eq`) deliberately: `Float(f64)` may hold a NaN, which
/// breaks `Eq` reflexivity.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Val {
    Int(i64),
    Float(f64),
}

/// A pin on a component (mirrors `Pin` in `temper_placer/core/netlist.py`).
///
/// Field types: `position` is the always-float `tuple[float, float]` pin
/// offset (`(f64, f64)` — an int-shaped coordinate is a loud marshalling
/// error, per the U0 "an int is not a float" discipline); the float scalar
/// fields (`width`/`height`/`drill`/`roundrect_ratio`/`pad_rotation_deg`)
/// are concrete `f64` for the same reason. `net` is `Option<String>` (the
/// dataclass default is `None`, which is also a legal explicit value).
#[derive(Clone, Debug, PartialEq)]
pub struct Pin {
    pub name: String,
    pub number: String,
    pub position: (f64, f64),
    pub net: Option<String>,
    pub width: f64,
    pub height: f64,
    pub shape: String,
    pub layer: String,
    pub drill: f64,
    pub is_pth: bool,
    pub roundrect_ratio: f64,
    pub pad_rotation_deg: f64,
}

/// A component to be placed on the PCB (mirrors `Component` — the *netlist*
/// component, distinct from the board `Component`).
///
/// [`bounds`](Self::bounds) is `Vec<Val>`: the `(width, height)` tuple whose
/// elements the pipeline demonstrably writes as `int` OR `float` (the
/// concrete-Python-type hazard). Every other numeric field is concrete:
/// `initial_position` is `Option<(f64, f64)>` (the always-float
/// `tuple[float, float] | None`), `initial_rotation_quadrant`/`initial_side` are
/// `Option<i64>` (`int | None`). `attributes` is an insertion-ordered
/// `dict[str, str]`; `tags` is a `frozenset` of strings read in iteration
/// order (a frozenset has no duplicates, so a `Vec` is faithful).
#[derive(Clone, Debug, PartialEq)]
pub struct Component {
    pub ref_: String,
    pub footprint: String,
    pub bounds: Vec<Val>,
    pub pins: Vec<Pin>,
    pub net_class: String,
    pub zone: Option<String>,
    pub fixed: bool,
    pub initial_position: Option<(f64, f64)>,
    pub initial_rotation_quadrant: Option<i64>,
    pub initial_side: Option<i64>,
    pub attributes: Vec<(String, String)>,
    pub tags: Vec<String>,
    pub sheetpath: Option<String>,
}

/// An electrical net connecting multiple pins (mirrors `Net`).
///
/// `pins` is `Vec<(String, String)>`: the `list[tuple[str, str]]` of
/// `(component_ref, pin_name)` pairs (each pair a 2-tuple, the list
/// insertion-ordered). The float scalars `weight`/`max_current` are concrete
/// `f64` (their dataclass defaults are float literals and the pipeline always
/// passes floats).
#[derive(Clone, Debug, PartialEq)]
pub struct Net {
    pub name: String,
    pub pins: Vec<(String, String)>,
    pub net_class: String,
    pub weight: f64,
    pub max_current: f64,
    pub voltage_class: String,
}

/// Pure zone-assignment kernel shared by the design-bundle leaf binding and
/// the orchestration stage.  Keeping this reduction in the pyo3-free data
/// model means the orchestration stage can marshal the Python netlist once
/// and compute without calling back into a Python module.
pub mod zone_assignment {
    use std::collections::HashMap;

    /// Assign each component to its deterministic placement zone.
    ///
    /// `components` is in netlist order.  Each net is `(name, net_class,
    /// pins)` in netlist order; `None` represents a missing/None Python
    /// `net_class` and therefore falls through to Signal.  The order and
    /// duplicate-net semantics intentionally mirror the former Python leaf.
    pub fn assign_component_zones(
        components: &[String],
        nets: &[(String, Option<String>, Vec<(String, String)>)],
    ) -> Vec<(String, String)> {
        let mut net_class_map: HashMap<&str, &str> = HashMap::with_capacity(nets.len());
        for (name, net_class, _) in nets {
            if let Some(net_class) = net_class.as_deref() {
                net_class_map.insert(name, net_class);
            }
        }

        let mut comp_nets: HashMap<&str, Vec<&str>> = HashMap::new();
        for (name, _, pins) in nets {
            for (component_ref, _) in pins {
                comp_nets
                    .entry(component_ref.as_str())
                    .or_default()
                    .push(name.as_str());
            }
        }

        components
            .iter()
            .map(|component_ref| {
                let nets_of = comp_nets
                    .get(component_ref.as_str())
                    .map(Vec::as_slice)
                    .unwrap_or(&[]);
                let zone = if component_ref.starts_with("U_MCU") {
                    "MCU"
                } else if nets_of.iter().any(|name| {
                    let upper = name.to_uppercase();
                    ["SPI", "I2C", "UART"]
                        .iter()
                        .any(|protocol| upper.contains(protocol))
                }) {
                    "MCU"
                } else if nets_of
                    .iter()
                    .any(|name| net_class_map.get(name).copied() == Some("HighVoltage"))
                {
                    "HV"
                } else if nets_of
                    .iter()
                    .any(|name| net_class_map.get(name).copied() == Some("Power"))
                {
                    "Power"
                } else {
                    "Signal"
                };
                (component_ref.clone(), zone.to_string())
            })
            .collect()
    }

    #[cfg(test)]
    mod tests {
        use super::assign_component_zones;

        #[test]
        fn priority_and_net_order_match_leaf_contract() {
            let components = vec!["R1".into(), "U_MCU1".into(), "Q1".into(), "J1".into()];
            let nets = vec![
                (
                    "HV_RELAY".into(),
                    Some("HighVoltage".into()),
                    vec![("Q1".into(), "1".into())],
                ),
                (
                    "spi_mosi".into(),
                    Some("Signal".into()),
                    vec![("J1".into(), "1".into())],
                ),
            ];
            assert_eq!(
                assign_component_zones(&components, &nets),
                vec![
                    ("R1".into(), "Signal".into()),
                    ("U_MCU1".into(), "MCU".into()),
                    ("Q1".into(), "HV".into()),
                    ("J1".into(), "MCU".into()),
                ]
            );
        }

        #[test]
        fn missing_or_none_net_class_falls_through() {
            let components = vec!["R1".into()];
            let nets = vec![(
                "N1".into(),
                None,
                vec![("R1".into(), "1".into())],
            )];
            assert_eq!(
                assign_component_zones(&components, &nets),
                vec![("R1".into(), "Signal".into())]
            );
        }
    }
}

/// The U3 (O-C3) owned AGGREGATE structs — [`Board`] + [`Netlist`],
/// composing the U2 leaves. See the module's own doc for the field-by-field
/// owned-vs-keep classification.
pub mod aggregates;
pub use aggregates::{Board, Netlist};

/// The U4 (O-C3) owned `ClearageGrid` core — the scalar dims + the net-id
/// registry (the numpy `int32` cell arrays are the pyo3-side keeps). See the
/// module's own doc for the owned-vs-keep classification and the
/// dtype-preservation argument.
pub mod clearance_grid;
pub use clearance_grid::ClearanceGrid;

/// The U4 (O-C3) owned `DRCOracle` RULES surface — the clearance tables, the
/// R3 credits, the config scalars and the `pin_owner` Mapping (the
/// `_net_class_rules` models, `zone_manager`, and the `PCBGeometry` index are
/// the pyo3-side keeps). See the module's own doc for the field table.
pub mod drc_oracle;
pub use drc_oracle::{ClearanceCredit, ClearanceMatrix, DrcOracle};

/// The U5 (O-C3) owned COLLECTION element structs + the owned collection
/// field types for the remaining `BoardState` fields (`zones`,
/// `component_zone_map`, `zone_slots`, `layer_assignments`, `routes`,
/// `vias`, `violations`, `placements`, `component_domain_map`, and the
/// three violation lists). See the module's own doc for the
/// element-survey (reused vs new) and the field→owned-type table.
pub mod collections;
pub use collections::{
    ConnectivityViolation, ConnectivityViolationList, LayerAssignment, LayerAssignmentSet,
    OwnedPlain, Placement, PlacementSet, PlacementViolation, PlacementViolationList,
    PreflightCheck, PreflightReport, Route, RouteSet, SlotPos, StrPairSet, Via, ViaSet,
    Violation, ViolationList, Zone, ZoneSet, ZoneSlots, ZoneSlotsSet,
};

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// `Val` is the int-vs-float distinction made a *type*: `Val::Int(1)`
    /// must NOT equal `Val::Float(1.0)`, or the whole point of the canonical
    /// type is lost (a widened `1` → `1.0` would then be `==`-indistinguishable).
    #[test]
    fn val_distinguishes_int_from_float() {
        assert_eq!(Val::Int(1), Val::Int(1));
        assert_eq!(Val::Float(1.0), Val::Float(1.0));
        assert_ne!(Val::Int(1), Val::Float(1.0), "int 1 must not equal float 1.0");
        assert_ne!(Val::Int(0), Val::Float(0.0), "int 0 must not equal float 0.0");
        // -0.0 vs 0.0 are equal as f64 (Python `-0.0 == 0.0`), so they are the
        // same Val — matching CPython float equality.
        assert_eq!(Val::Float(-0.0), Val::Float(0.0));
    }
}
