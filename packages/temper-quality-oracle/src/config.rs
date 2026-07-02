/// Quality config population from derived constraints + netlist.
///
/// Ports `infer_quality_config()` from Python:
/// - Thermal components: large packages (TO-247, TO-220, D2PAK, module, heatsink) or area > 100mm²
/// - HV components: power transistors, diodes, bulk caps (>50mm² area)
/// - LV components: small ICs (SOIC, QFP, BGA, QFN, SOT, area < 100mm²)
/// - Critical loops: gate drive nets with >=2 components

use crate::types::{
    ComponentInfo, DerivedConstraints, Netlist, QualityConfig,
};
use std::collections::{BTreeSet, HashMap};

pub fn build_config(
    netlist: &Netlist,
    constraints: &DerivedConstraints,
) -> QualityConfig {
    let mut thermal = BTreeSet::new();
    let mut hv = BTreeSet::new();
    let mut lv = BTreeSet::new();

    for comp in &netlist.components {
        let fp_lower = comp.footprint.to_lowercase();
        let ref_upper = comp.ref_des.to_uppercase();
        let area = comp.width_mm * comp.height_mm;

        let is_thermal = ["to-247", "to-220", "d2pak", "module", "heatsink"]
            .iter()
            .any(|pkg| fp_lower.contains(pkg))
            || area > 100.0;
        if is_thermal {
            thermal.insert(comp.ref_des.clone());
        }

        let is_hv = (ref_upper.starts_with('Q')
            || ref_upper.starts_with('D')
            || ref_upper.starts_with("TR")
            || ref_upper.starts_with('U')
            || fp_lower.contains("igbt")
            || fp_lower.contains("mosfet"))
            && area > 50.0;
        if is_hv {
            hv.insert(comp.ref_des.clone());
        }

        let is_lv = ["soic", "qfp", "bga", "qfn", "sot"]
            .iter()
            .any(|pkg| fp_lower.contains(pkg))
            && area < 100.0;
        if is_lv {
            lv.insert(comp.ref_des.clone());
        }
    }

    let mut loops: Vec<Vec<String>> = Vec::new();
    for net in &netlist.nets {
        let net_upper = net.name.to_uppercase();
        let is_gate_drive = ["GATE", "DRV", "DRIVE"]
            .iter()
            .any(|kw| net_upper.contains(kw));
        if is_gate_drive && net.pins.len() >= 2 {
            let loop_refs: Vec<String> = net.pins.iter().take(3).cloned().collect();
            if loop_refs.len() >= 2 {
                loops.push(loop_refs);
            }
        }
    }
    loops.truncate(3);

    QualityConfig {
        thermal_components: thermal,
        hv_components: hv,
        lv_components: lv,
        zone_assignments: HashMap::new(),
        loop_components: loops,
        min_hv_lv_clearance_mm: constraints.hv_lv_isolation_mm,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::NetInfo;

    fn test_netlist() -> Netlist {
        Netlist {
            nets: vec![
                NetInfo {
                    name: "GATE_DRV_H".into(),
                    pins: vec!["Q1".into(), "R1".into(), "D1".into()],
                },
                NetInfo {
                    name: "SIG1".into(),
                    pins: vec!["U1".into(), "R2".into()],
                },
            ],
            components: vec![
                ComponentInfo {
                    ref_des: "Q1".into(),
                    footprint: "TO-247".into(),
                    width_mm: 15.0,
                    height_mm: 20.0,
                    voltage: 230.0,
                },
                ComponentInfo {
                    ref_des: "U1".into(),
                    footprint: "SOIC-8".into(),
                    width_mm: 5.0,
                    height_mm: 4.0,
                    voltage: 3.3,
                },
                ComponentInfo {
                    ref_des: "R1".into(),
                    footprint: "R0805".into(),
                    width_mm: 2.0,
                    height_mm: 1.2,
                    voltage: 0.0,
                },
                ComponentInfo {
                    ref_des: "D1".into(),
                    footprint: "SOD-123".into(),
                    width_mm: 2.5,
                    height_mm: 1.5,
                    voltage: 0.0,
                },
                ComponentInfo {
                    ref_des: "R2".into(),
                    footprint: "R0805".into(),
                    width_mm: 2.0,
                    height_mm: 1.2,
                    voltage: 0.0,
                },
            ],
        }
    }

    #[test]
    fn test_config_populates_thermal() {
        let config = build_config(&test_netlist(), &DerivedConstraints::default());
        assert!(config.thermal_components.contains("Q1"));
    }

    #[test]
    fn test_config_populates_hv() {
        let config = build_config(&test_netlist(), &DerivedConstraints::default());
        assert!(config.hv_components.contains("Q1"));
    }

    #[test]
    fn test_config_populates_lv() {
        let config = build_config(&test_netlist(), &DerivedConstraints::default());
        assert!(config.lv_components.contains("U1"));
    }

    #[test]
    fn test_config_loop_components() {
        let config = build_config(&test_netlist(), &DerivedConstraints::default());
        assert_eq!(config.loop_components.len(), 1);
        let gate_loop = &config.loop_components[0];
        assert!(gate_loop.contains(&"Q1".to_string()));
        assert!(gate_loop.len() >= 2);
    }

    #[test]
    fn test_config_empty_netlist() {
        let netlist = Netlist { nets: vec![], components: vec![] };
        let config = build_config(&netlist, &DerivedConstraints::default());
        assert!(config.thermal_components.is_empty());
        assert!(config.hv_components.is_empty());
        assert!(config.lv_components.is_empty());
        assert!(config.loop_components.is_empty());
    }

    #[test]
    fn test_config_loop_components_ge_2() {
        let config = build_config(&test_netlist(), &DerivedConstraints::default());
        for loop_refs in &config.loop_components {
            assert!(loop_refs.len() >= 2);
        }
    }

    #[test]
    fn test_config_default_clearance() {
        let config = build_config(&test_netlist(), &DerivedConstraints::default());
        assert!((config.min_hv_lv_clearance_mm - 6.5).abs() < 1e-10);
    }
}
