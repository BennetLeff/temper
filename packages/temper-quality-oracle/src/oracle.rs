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
    use proptest::prelude::*;
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

    proptest! {
        #[test]
        fn pbt_oracle_empty_board_always_passes(
            metrics in prop::array::uniform7(0.0f64..1.0f64),
            wirelength in 0.0f64..10000.0f64,
        ) {
            let pre = PrecomputedMetrics {
                thermal_score: metrics[0],
                zone_compliance_score: metrics[1],
                hv_lv_clearance_score: metrics[2],
                loop_area_score: metrics[3],
                congestion_score: metrics[4],
                compactness_score: metrics[5],
                connectivity_clustering_score: metrics[6],
                total_wirelength_mm: wirelength,
            };
            let verdict = evaluate_quality(
                &empty_spec(),
                &empty_netlist(),
                &empty_placement(),
                &pre,
            );
            prop_assert!(verdict.is_pass());
        }

        #[test]
        fn pbt_oracle_deterministic(
            metrics in prop::array::uniform7(0.0f64..1.0f64),
        ) {
            let pre = PrecomputedMetrics {
                thermal_score: metrics[0],
                zone_compliance_score: metrics[1],
                hv_lv_clearance_score: metrics[2],
                loop_area_score: metrics[3],
                congestion_score: metrics[4],
                compactness_score: metrics[5],
                connectivity_clustering_score: metrics[6],
                total_wirelength_mm: 100.0,
            };
            let v1 = evaluate_quality(&empty_spec(), &empty_netlist(), &empty_placement(), &pre);
            let v2 = evaluate_quality(&empty_spec(), &empty_netlist(), &empty_placement(), &pre);
            prop_assert_eq!(v1.is_pass(), v2.is_pass());
        }

        #[test]
        fn pbt_oracle_rejects_invalid_scores(
            bad_score in prop::num::f64::NORMAL,
        ) {
            prop_assume!(bad_score < 0.0 || bad_score > 1.0 || bad_score.is_nan());
            let pre = PrecomputedMetrics {
                thermal_score: bad_score,
                ..valid_metrics()
            };
            let verdict = evaluate_quality(
                &empty_spec(),
                &empty_netlist(),
                &empty_placement(),
                &pre,
            );
            prop_assert!(!verdict.is_pass());
        }

        #[test]
        fn pbt_clearance_monotonicity_adding_component(
            mut positions in prop::collection::vec((-50.0f64..150.0f64, -50.0f64..150.0f64), 1..8),
            extra_x in -100.0f64..200.0f64,
            extra_y in -100.0f64..200.0f64,
        ) {
            let refs: Vec<String> = (1..=positions.len()).map(|i| format!("C{i}")).collect();
            let mut components: Vec<ComponentInfo> = refs.iter().map(|r| ComponentInfo {
                ref_des: r.clone(),
                footprint: "R0805".into(),
                width_mm: 2.0,
                height_mm: 1.2,
                voltage: 0.0,
            }).collect();
            let len = components.len();
            components[0].voltage = 230.0;
            components[0].footprint = "TO-247".into();
            if len > 1 {
                components[1].voltage = 3.3;
                components[1].footprint = "SOIC-8".into();
            }

            let netlist = Netlist { nets: vec![], components: components.clone() };
            let placement_before = PlacementState {
                positions: positions.clone(),
                component_refs: refs.clone(),
                board_width_mm: 100.0,
                board_height_mm: 100.0,
            };

            let verdict_before = evaluate_quality(
                &empty_spec(), &netlist, &placement_before, &valid_metrics(),
            );
            let violations_before = match &verdict_before {
                QualityVerdict::Fail { violations, .. } => violations.len(),
                QualityVerdict::Pass { .. } => 0,
            };

            positions.push((extra_x, extra_y));
            let mut refs_after = refs.clone();
            refs_after.push("EXTRA".into());
            let mut components_after = components;
            components_after.push(ComponentInfo {
                ref_des: "EXTRA".into(), footprint: "R0805".into(),
                width_mm: 2.0, height_mm: 1.2, voltage: 0.0,
            });
            let netlist_after = Netlist { nets: vec![], components: components_after };
            let placement_after = PlacementState {
                positions,
                component_refs: refs_after,
                board_width_mm: 100.0,
                board_height_mm: 100.0,
            };

            let verdict_after = evaluate_quality(
                &empty_spec(), &netlist_after, &placement_after, &valid_metrics(),
            );
            let violations_after = match &verdict_after {
                QualityVerdict::Fail { violations, .. } => violations.len(),
                QualityVerdict::Pass { .. } => 0,
            };

            prop_assert!(violations_after >= violations_before,
                "adding a component must not reduce clearance violation count: before={violations_before}, after={violations_after}"
            );
        }

        #[test]
        fn pbt_roundtrip_no_panic(
            n_components in 0usize..10,
            metrics in prop::array::uniform7(0.0f64..1.0f64),
        ) {
            let refs: Vec<String> = (0..n_components).map(|i| format!("C{i}")).collect();
            let positions: Vec<(f64, f64)> = (0..n_components)
                .map(|i| (i as f64 * 10.0, 0.0))
                .collect();
            let components: Vec<ComponentInfo> = refs.iter().map(|r| ComponentInfo {
                ref_des: r.clone(),
                footprint: "R0805".into(),
                width_mm: 2.0, height_mm: 1.2, voltage: 0.0,
            }).collect();
            let netlist = Netlist {
                nets: refs.iter().map(|r| NetInfo { name: r.clone(), pins: vec![r.clone()] }).collect(),
                components,
            };
            let placement = PlacementState {
                positions,
                component_refs: refs,
                board_width_mm: 200.0,
                board_height_mm: 200.0,
            };
            let pre = PrecomputedMetrics {
                thermal_score: metrics[0],
                zone_compliance_score: metrics[1],
                hv_lv_clearance_score: metrics[2],
                loop_area_score: metrics[3],
                congestion_score: metrics[4],
                compactness_score: metrics[5],
                connectivity_clustering_score: metrics[6],
                total_wirelength_mm: 100.0,
            };
            let _verdict = evaluate_quality(&empty_spec(), &netlist, &placement, &pre);
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
