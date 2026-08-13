//! The U4 (O-C3) owned `DRCOracle` RULES surface: the portable half of
//! `router_v6/constraints_drc_oracle.py::DRCOracle` and the
//! `router_v6/constraints_design_rules.py::ClearanceMatrix` it wraps.
//!
//! # Owned vs keep
//!
//! The `DRCOracle` is a stateful Python object (a pickled `BoardState`
//! field) whose numeric bodies already delegate to `temper_drc_rs` kernels.
//! Its STATE splits into a portable plain-data half (the clearance tables,
//! the scalar config, the R3 clearance credits, the `pin_owner` Mapping)
//! and a foreign half (the spatial index and the rich config models):
//!
//! | Field | Owned type | Why |
//! |---|---|---|
//! | `rules._clearances` | `Vec<(String, String, f64)>` | `dict[(class_a, class_b) → float]`, insertion-ordered — the class-pair table (`_clearances_wire()` already produces this exact shape) |
//! | `rules._net_to_class` | `Vec<(String, String)>` | `dict[net → class]`, insertion-ordered |
//! | `rules._differential_pairs` | `Vec<(String, String, f64)>` | the `_diff_pairs_wire()` shape — each `frozenset` key read in its own iteration order (the kernels canonicalize the unordered pair, so the stored `(a, b)` order is load-bearing only for repr) |
//! | `rules.default_{clearance,track_width,via_diameter,via_drill}` | `f64` | always-float dataclass defaults (the U0 "concrete `f64` for the unambiguous always-float contract") |
//! | `rules._net_class_rules` | *keep* | `dict[str, NetClassRules]` — the VALUES are pydantic `NetClassRules` models; the drc-rs `DrcNetClassRuleSnapshot` wire type is a deliberate K1 SUBSET, so owning the subset would LOSE `dru_priority`/`via_template`/`target_impedance`/`layer`/`via_cost_multiplier`/`layer_costs` on a full round-trip |
//! | `rules.zone_manager` | *keep* | `ZoneManager | None` — a plain (identity-`==`) class holding `RoutingZone` objects with shapely-adjacent polygons; spatial, like `geometry` |
//! | `geometry` | *keep* | `PCBGeometry` — the Python-visible rstar R-tree over `Track`/`Pad`/`Via` objects |
//! | `_search_multiplier` | `f64` | always-float (`3.0`) |
//! | `enable_internal_layer_creepage` | `bool` | |
//! | `clearance_credits` | `Vec<ClearanceCredit>` | the `_credits_wire()` shape in *insertion order* (the oracle iterates `dict.items()` and the first match wins) |
//! | `pin_owner` (Mapping form) | `Vec<(String, String)>` | `dict[pin_id → component_ref]`, insertion-ordered |
//! | `pin_owner` (Callable form) | *keep* | a live `Callable[[str], str | None]` — foreign, identity passthrough |
//!
//! The net-class safety-category RESOLUTION kernel
//! (`resolve_safety_category`, AGENTS.md N4) is already Rust in
//! `temper-drc-rs` — this crate does NOT reimplement it; the owned structs
//! carry the `safety_category` as *data* (inside the kept `_net_class_rules`
//! models) and never re-derive it.
//!
//! # The concrete-`f64` discipline
//!
//! The clearance/credit floats are concrete `f64` (rejecting an int-shaped
//! value loudly, per the U0 "an int is not a float" rule) because the real
//! pipeline always writes floats: `add_clearance_credit` explicitly
//! `float()`-coerces every field, `set_class_to_class_clearance` is called
//! with float literals or parsed KiCad floats, and `add_differential_pair`
//! computes its value through the Rust `clearance_diff_pair_required_py`
//! kernel (always a float). An int-shaped rules value is a marshalling
//! error, not a silent widen.

/// The owned `ClearanceMatrix` rules surface (the clearance TABLES; the
/// `_net_class_rules` models and the `zone_manager` are pyo3-side keeps —
/// see the module doc's field table).
///
/// Field names mirror the drc-rs wire shapes so a later integration can map
/// 1:1 onto `temper_drc_rs`'s `engine::ClearanceRule` / the
/// `_clearances_wire()` / `_diff_pairs_wire()` tuples.
#[derive(Clone, Debug, PartialEq)]
pub struct ClearanceMatrix {
    /// `_clearances`: `(class_a, class_b) -> clearance_mm` rows in insertion
    /// order (each ordering `set_class_to_class_clearance` stored is its own
    /// row — the kernel probes `(a, b)` then `(b, a)` itself).
    pub clearances: Vec<(String, String, f64)>,
    /// `_net_to_class`: net name -> class name, insertion-ordered.
    pub net_to_class: Vec<(String, String)>,
    /// `_differential_pairs`: `(net_a, net_b, required_clearance)` rows in
    /// the dict's insertion order; the unordered `frozenset` key is read in
    /// its own iteration order.
    pub differential_pairs: Vec<(String, String, f64)>,
    pub default_clearance: f64,
    pub default_track_width: f64,
    pub default_via_diameter: f64,
    pub default_via_drill: f64,
}

/// One R3 clearance credit: a `(component_ref, lv_pin, hv_pin)` triple keyed
/// to the `(effective_clearance_mm, half_width_mm, half_length_mm,
/// slot_midpoint_x, slot_midpoint_y, axis)` tuple `add_clearance_credit`
/// stores. `axis` is `"x"`/`"y"`/`None` (the cutout's primary axis).
#[derive(Clone, Debug, PartialEq)]
pub struct ClearanceCredit {
    pub component_ref: String,
    pub lv_pin: String,
    pub hv_pin: String,
    pub effective_clearance_mm: f64,
    pub half_width_mm: f64,
    pub half_length_mm: f64,
    pub slot_midpoint_x: f64,
    pub slot_midpoint_y: f64,
    pub axis: Option<String>,
}

/// The owned `DRCOracle` state surface (the rules tables + scalar config +
/// the credit table + the `pin_owner` Mapping). The foreign keeps — the
/// `_net_class_rules` models, the `zone_manager`, the `PCBGeometry` index,
/// and a Callable `pin_owner` — live on the pyo3 side (`OwnedDrcOracle` in
/// `temper-orchestration`'s `netlist_owned.rs`) as `Plain::Opaque` identity
/// passthroughs.
#[derive(Clone, Debug, PartialEq)]
pub struct DrcOracle {
    pub rules: ClearanceMatrix,
    pub search_multiplier: f64,
    pub enable_internal_layer_creepage: bool,
    /// `clearance_credits` in INSERTION order — the oracle iterates
    /// `dict.items()` and the first matching credit wins, so order is part of
    /// the value.
    pub clearance_credits: Vec<ClearanceCredit>,
    /// `pin_owner` in its Mapping form (`dict[pin_id → component_ref]`),
    /// insertion-ordered. A Callable `pin_owner` is the pyo3-side keep.
    pub pin_owner: Vec<(String, String)>,
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// The owned `ClearanceMatrix` is a pure-data table: the class-pair rows
    /// and net->class rows preserve insertion order (the load-bearing order
    /// for the wire formats the drc-rs kernels consume).
    #[test]
    fn clearance_matrix_holds_the_wire_tables() {
        let m = ClearanceMatrix {
            clearances: vec![
                ("Power".into(), "Signal".into(), 0.3),
                ("GND".into(), "Power".into(), 0.3),
            ],
            net_to_class: vec![("VCC".into(), "Power".into())],
            differential_pairs: vec![("USB_D+".into(), "USB_D-".into(), -0.05)],
            default_clearance: 0.2,
            default_track_width: 0.2,
            default_via_diameter: 0.6,
            default_via_drill: 0.3,
        };
        assert_eq!(m.clearances[0], ("Power".to_string(), "Signal".to_string(), 0.3));
        assert_eq!(m.clearances[1], ("GND".to_string(), "Power".to_string(), 0.3));
        assert_eq!(m.net_to_class[0], ("VCC".to_string(), "Power".to_string()));
        // The differential-pair value can legitimately be negative (the
        // `spacing_mm - 2*track_width` arithmetic, see the oracle docstring).
        assert_eq!(m.differential_pairs[0].2, -0.05);
        assert_eq!(m.default_clearance, 0.2);
    }

    /// A credit carries the full R3 tuple; `axis` is `None` for legacy
    /// callers that don't know the cutout orientation.
    #[test]
    fn credit_holds_the_full_r3_tuple() {
        let credit = ClearanceCredit {
            component_ref: "K3".into(),
            lv_pin: "2".into(),
            hv_pin: "1".into(),
            effective_clearance_mm: 1.5,
            half_width_mm: 0.75,
            half_length_mm: 4.0,
            slot_midpoint_x: 10.0,
            slot_midpoint_y: 20.0,
            axis: Some("x".into()),
        };
        assert_eq!(credit.component_ref, "K3");
        assert_eq!(credit.axis.as_deref(), Some("x"));
        let legacy = ClearanceCredit {
            axis: None,
            ..credit.clone()
        };
        assert_eq!(legacy.axis, None);
        assert_eq!(legacy.effective_clearance_mm, 1.5);
    }

    /// The owned oracle composes the rules with the config scalars, the
    /// credit table and the pin-owner map. `Val` is not used here — every
    /// numeric leaf is a concrete `f64`/`bool` per the module-doc discipline.
    #[test]
    fn oracle_composes_rules_credits_and_owner_map() {
        let oracle = DrcOracle {
            rules: ClearanceMatrix {
                clearances: vec![("HighVoltage".into(), "Signal".into(), 6.0)],
                net_to_class: vec![("HV_NET".into(), "HighVoltage".into())],
                differential_pairs: vec![],
                default_clearance: 0.2,
                default_track_width: 0.2,
                default_via_diameter: 0.6,
                default_via_drill: 0.3,
            },
            search_multiplier: 3.0,
            enable_internal_layer_creepage: true,
            clearance_credits: vec![ClearanceCredit {
                component_ref: "K3".into(),
                lv_pin: "2".into(),
                hv_pin: "1".into(),
                effective_clearance_mm: 1.5,
                half_width_mm: 0.75,
                half_length_mm: 4.0,
                slot_midpoint_x: 10.0,
                slot_midpoint_y: 20.0,
                axis: Some("x".into()),
            }],
            pin_owner: vec![("K3-1".into(), "K3".into()), ("K3-2".into(), "K3".into())],
        };
        assert_eq!(oracle.rules.clearances[0].2, 6.0);
        assert!(oracle.enable_internal_layer_creepage);
        assert_eq!(oracle.clearance_credits.len(), 1);
        assert_eq!(oracle.pin_owner[1], ("K3-2".to_string(), "K3".to_string()));
    }
}
