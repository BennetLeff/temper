/// Quality oracle entry point — orchestrates the full six-layer pipeline.
///
/// Single pure function: classify → derive → configure → evaluate → verdict.

use crate::classification::classify_nets;
use crate::config::build_config;
use crate::derivation::derive;
use crate::thresholds::evaluate;
use crate::types::{
    Netlist, PcbSpecification, PlacementState, PrecomputedMetrics, QualityMetrics,
    QualityVerdict,
};

pub fn evaluate_quality(
    spec: &PcbSpecification,
    netlist: &Netlist,
    placement: &PlacementState,
    precomputed: &PrecomputedMetrics,
) -> QualityVerdict {
    let classifications = classify_nets(netlist);
    let constraints = derive(spec, &classifications);
    let config = build_config(netlist, &constraints);

    let metrics = match QualityMetrics::from_precomputed(precomputed) {
        Ok(m) => m,
        Err(e) => {
            return QualityVerdict::Fail {
                metrics: QualityMetrics::from_precomputed(&PrecomputedMetrics {
                    thermal_score: 0.0,
                    zone_compliance_score: 0.0,
                    hv_lv_clearance_score: 0.0,
                    loop_area_score: 0.0,
                    congestion_score: 0.0,
                    compactness_score: 0.0,
                    connectivity_clustering_score: 0.0,
                    total_wirelength_mm: 0.0,
                })
                .unwrap_or_else(|_| {
                    panic!("zero-padded metrics should always be valid")
                }),
                violations: vec![crate::types::Violation {
                    violation_type: crate::types::ViolationType::CreepageInsufficient,
                    description: format!("Invalid precomputed metric: {e}"),
                    components: vec![],
                    actual_value: 0.0,
                    required_value: 0.0,
                }],
            };
        }
    };

    let violations = evaluate(&config, placement, &metrics, spec, &classifications);

    if violations.is_empty() {
        QualityVerdict::Pass { metrics }
    } else {
        QualityVerdict::Fail { metrics, violations }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{ComponentInfo, NetInfo};
    use std::collections::HashMap;

    fn empty_spec() -> PcbSpecification {
        PcbSpecification {
            name: "test".into(),
            max_loop_area_mm2: HashMap::new(),
            power_dissipation: HashMap::new(),
            max_length_mm: HashMap::new(),
            max_junction_temp_c: 125.0,
            ambient_temp_c: 40.0,
        }
    }

    fn empty_netlist() -> Netlist {
        Netlist { nets: vec![], components: vec![] }
    }

    fn empty_placement() -> PlacementState {
        PlacementState {
            positions: vec![],
            component_refs: vec![],
            board_width_mm: 100.0,
            board_height_mm: 100.0,
        }
    }

    fn valid_metrics() -> PrecomputedMetrics {
        PrecomputedMetrics {
            thermal_score: 0.5,
            zone_compliance_score: 0.5,
            hv_lv_clearance_score: 0.5,
            loop_area_score: 0.5,
            congestion_score: 0.5,
            compactness_score: 0.5,
            connectivity_clustering_score: 0.5,
            total_wirelength_mm: 100.0,
        }
    }

    #[test]
    fn test_oracle_empty_board_passes() {
        let verdict = evaluate_quality(
            &empty_spec(),
            &empty_netlist(),
            &empty_placement(),
            &valid_metrics(),
        );
        assert!(verdict.is_pass());
    }

    #[test]
    fn test_oracle_deterministic() {
        let verdict1 = evaluate_quality(
            &empty_spec(),
            &empty_netlist(),
            &empty_placement(),
            &valid_metrics(),
        );
        let verdict2 = evaluate_quality(
            &empty_spec(),
            &empty_netlist(),
            &empty_placement(),
            &valid_metrics(),
        );
        assert_eq!(
            verdict1.is_pass(),
            verdict2.is_pass(),
            "oracle must be deterministic"
        );
    }

    #[test]
    fn test_oracle_rejects_invalid_metrics() {
        let bad = PrecomputedMetrics {
            thermal_score: 1.5,
            ..valid_metrics()
        };
        let verdict = evaluate_quality(
            &empty_spec(),
            &empty_netlist(),
            &empty_placement(),
            &bad,
        );
        assert!(!verdict.is_pass(), "must fail on out-of-range score");
    }

    #[test]
    fn test_oracle_single_component_passes() {
        let spec = empty_spec();
        let netlist = Netlist {
            nets: vec![NetInfo { name: "SIG1".into(), pins: vec!["U1".into()] }],
            components: vec![ComponentInfo {
                ref_des: "U1".into(),
                footprint: "SOIC-8".into(),
                width_mm: 5.0,
                height_mm: 4.0,
                voltage: 3.3,
            }],
        };
        let placement = PlacementState {
            positions: vec![(50.0, 50.0)],
            component_refs: vec!["U1".into()],
            board_width_mm: 100.0,
            board_height_mm: 100.0,
        };
        let verdict = evaluate_quality(&spec, &netlist, &placement, &valid_metrics());
        assert!(verdict.is_pass());
    }

    #[test]
    fn test_oracle_hv_lv_violation_detected() {
        let spec = empty_spec();
        let netlist = Netlist {
            nets: vec![
                NetInfo { name: "SIG1".into(), pins: vec!["Q1".into(), "U1".into()] },
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
            ],
        };
        let placement = PlacementState {
            positions: vec![(5.0, 5.0), (6.0, 5.0)],
            component_refs: vec!["Q1".into(), "U1".into()],
            board_width_mm: 100.0,
            board_height_mm: 100.0,
        };
        let verdict = evaluate_quality(&spec, &netlist, &placement, &valid_metrics());
        assert!(!verdict.is_pass(), "HV-LV pair 1mm apart should fail");
        if let QualityVerdict::Fail { violations, .. } = &verdict {
            assert!(violations.iter().any(|v| {
                v.violation_type == crate::types::ViolationType::CreepageInsufficient
            }));
        }
    }
}
