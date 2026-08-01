/// Quality oracle entry point — orchestrates the full six-layer pipeline.
///
/// The pipeline is split into a placement-independent `prepare` stage
/// (classify → derive → configure, all functions of the (spec, netlist)
/// pair alone) and a per-placement `evaluate_prepared` stage. This mirrors
/// the Python predecessor, which assembled the quality config once and
/// scored every candidate placement state against it, and avoids
/// recomputing `classify_nets`/`derive`/`build_config` per evaluation.
use crate::classification::classify_nets;
use crate::config::build_config;
use crate::derivation::derive;
use crate::thresholds::evaluate;
use crate::types::{
    NetClassification, Netlist, PcbSpecification, PlacementState, PrecomputedMetrics,
    QualityConfig, QualityMetrics, QualityVerdict,
};

/// Cached, placement-independent pipeline state.
///
/// Everything that depends only on (spec, netlist) is computed once in
/// [`prepare_quality`] and reused for any number of placement states via
/// [`evaluate_prepared`].
#[derive(Debug, Clone)]
pub struct PreparedQuality {
    pub config: QualityConfig,
    pub classifications: Vec<NetClassification>,
    pub spec: PcbSpecification,
}

/// Setup stage: compute the quality config, net classifications, and keep
/// the spec, all of which are independent of any placement state.
pub fn prepare_quality(spec: &PcbSpecification, netlist: &Netlist) -> PreparedQuality {
    let classifications = classify_nets(netlist);
    let constraints = derive(spec, &classifications);
    let config = build_config(netlist, &constraints);
    PreparedQuality {
        config,
        classifications,
        spec: spec.clone(),
    }
}

/// Per-placement stage: validate the precomputed metrics and threshold them
/// against the cached config. No classification/derivation/config work here.
pub fn evaluate_prepared(
    prepared: &PreparedQuality,
    placement: &PlacementState,
    precomputed: &PrecomputedMetrics,
) -> QualityVerdict {
    let metrics = match QualityMetrics::from_precomputed(precomputed) {
        Ok(m) => m,
        Err(e) => {
            return QualityVerdict::Fail {
                metrics: QualityMetrics::zeroed(),
                violations: vec![crate::types::Violation {
                    violation_type: crate::types::ViolationType::InvalidMetric,
                    description: format!("Invalid precomputed metric: {e}"),
                    components: vec![],
                    actual_value: 0.0,
                    required_value: 0.0,
                }],
            };
        }
    };

    let violations = evaluate(
        &prepared.config,
        placement,
        &metrics,
        &prepared.spec,
        &prepared.classifications,
    );

    if violations.is_empty() {
        QualityVerdict::Pass { metrics }
    } else {
        QualityVerdict::Fail { metrics, violations }
    }
}

/// Single-shot entry point: prepare + evaluate in one call.
///
/// Kept for existing callers/tests; internally it is exactly
/// [`prepare_quality`] followed by [`evaluate_prepared`].
pub fn evaluate_quality(
    spec: &PcbSpecification,
    netlist: &Netlist,
    placement: &PlacementState,
    precomputed: &PrecomputedMetrics,
) -> QualityVerdict {
    let prepared = prepare_quality(spec, netlist);
    evaluate_prepared(&prepared, placement, precomputed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tests_common::{empty_placement, empty_spec, valid_metrics};
    use crate::types::{ComponentInfo, NetInfo};
    use proptest::prelude::*;

    fn empty_netlist() -> Netlist {
        Netlist { nets: vec![], components: vec![] }
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
            prop_assume!(!(0.0..=1.0).contains(&bad_score) || bad_score.is_nan());
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
            mut positions in prop::collection::vec((-50.0f64..150.0f64, -50.0f64..150.0f64), 2..8),
            extra_x in -100.0f64..200.0f64,
            extra_y in -100.0f64..200.0f64,
        ) {
            let hv_prefixes = ["Q", "D", "TR", "U"];
            let refs: Vec<String> = (1..=positions.len())
                .map(|i| format!("{}{i}", hv_prefixes[i % hv_prefixes.len()]))
                .collect();
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
    fn test_prepare_evaluate_matches_evaluate_quality() {
        let spec = empty_spec();
        let netlist = Netlist {
            nets: vec![
                NetInfo { name: "GATE_DRV_H".into(), pins: vec!["Q1".into(), "U1".into()] },
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
        let pre = valid_metrics();

        let single_shot = evaluate_quality(&spec, &netlist, &placement, &pre);
        let prepared = prepare_quality(&spec, &netlist);
        let split = evaluate_prepared(&prepared, &placement, &pre);

        assert_eq!(single_shot, split, "split pipeline must match single-shot");
        assert!(!split.is_pass(), "HV-LV pair 1mm apart should fail");
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
