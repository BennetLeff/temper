/// Constraint derivation from PCB specification.
///
/// Ports `derive_constraints_from_spec()` from Python:
/// - EMI → max component spacing (sqrt(area) * 0.8)
/// - Thermal → min clearance (power * 2.0)
/// - Signal Integrity → max placement distance (max_len / 1.5)
/// - Safety → HV-LV isolation (6.5mm default)

use crate::types::{DerivedConstraints, NetClassification, PcbSpecification};

pub fn derive(spec: &PcbSpecification, _classifications: &[NetClassification]) -> DerivedConstraints {
    let mut constraints = DerivedConstraints {
        hv_lv_isolation_mm: 6.5,
        ..Default::default()
    };

    for (loop_name, max_area) in &spec.max_loop_area_mm2 {
        let max_side = max_area.sqrt();
        constraints.loop_spacing.insert(
            format!("{}_max_dist", loop_name),
            max_side * 0.8,
        );
    }

    for (ref_des, power) in &spec.power_dissipation {
        constraints.thermal_clearances.insert(
            format!("{}_min_clearance", ref_des),
            power * 2.0,
        );
    }

    for (net_name, max_len) in &spec.max_length_mm {
        constraints.si_max_placement_dist.insert(
            format!("{}_max_placement_dist", net_name),
            max_len / 1.5,
        );
    }

    constraints
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_derive_emi_loop_spacing() {
        let spec = PcbSpecification {
            name: "test".into(),
            max_loop_area_mm2: HashMap::from([
                ("commutation_loop".into(), 80.0),
            ]),
            power_dissipation: HashMap::new(),
            max_length_mm: HashMap::new(),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        };
        let classifications = vec![];
        let derived = derive(&spec, &classifications);
        let expected = 80.0_f64.sqrt() * 0.8;
        assert!((derived.loop_spacing["commutation_loop_max_dist"] - expected).abs() < 1e-6);
    }

    #[test]
    fn test_derive_thermal_clearance() {
        let spec = PcbSpecification {
            name: "test".into(),
            max_loop_area_mm2: HashMap::new(),
            power_dissipation: HashMap::from([
                ("Q1".into(), 15.0),
                ("Q2".into(), 10.0),
            ]),
            max_length_mm: HashMap::new(),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        };
        let derived = derive(&spec, &[]);
        assert!((derived.thermal_clearances["Q1_min_clearance"] - 30.0).abs() < 1e-6);
        assert!((derived.thermal_clearances["Q2_min_clearance"] - 20.0).abs() < 1e-6);
    }

    #[test]
    fn test_derive_si_max_placement_dist() {
        let spec = PcbSpecification {
            name: "test".into(),
            max_loop_area_mm2: HashMap::new(),
            power_dissipation: HashMap::new(),
            max_length_mm: HashMap::from([
                ("CLK".into(), 100.0),
            ]),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        };
        let derived = derive(&spec, &[]);
        let expected = 100.0 / 1.5;
        assert!((derived.si_max_placement_dist["CLK_max_placement_dist"] - expected).abs() < 1e-6);
    }

    #[test]
    fn test_derive_hv_lv_isolation_default() {
        let spec = PcbSpecification {
            name: "test".into(),
            max_loop_area_mm2: HashMap::new(),
            power_dissipation: HashMap::new(),
            max_length_mm: HashMap::new(),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        };
        let derived = derive(&spec, &[]);
        assert!((derived.hv_lv_isolation_mm - 6.5).abs() < 1e-6);
    }

    #[test]
    fn test_derive_empty_spec() {
        let spec = PcbSpecification {
            name: "empty".into(),
            max_loop_area_mm2: HashMap::new(),
            power_dissipation: HashMap::new(),
            max_length_mm: HashMap::new(),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        };
        let derived = derive(&spec, &[]);
        assert!(derived.loop_spacing.is_empty());
        assert!(derived.thermal_clearances.is_empty());
        assert!(derived.si_max_placement_dist.is_empty());
    }

    #[test]
    fn test_derived_distances_non_negative() {
        let spec = PcbSpecification {
            name: "test".into(),
            max_loop_area_mm2: HashMap::from([
                ("tiny_loop".into(), 0.01),
            ]),
            power_dissipation: HashMap::new(),
            max_length_mm: HashMap::from([
                ("short".into(), 0.1),
            ]),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        };
        let derived = derive(&spec, &[]);
        for (_, v) in &derived.loop_spacing {
            assert!(*v >= 0.0, "loop spacing must be non-negative");
        }
        for (_, v) in &derived.si_max_placement_dist {
            assert!(*v >= 0.0, "SI placement dist must be non-negative");
        }
    }
}
