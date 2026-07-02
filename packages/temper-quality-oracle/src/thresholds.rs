/// Threshold evaluation — checks quality config against all constraints.
///
/// Produces violations for:
/// - IPC-2221 creepage/clearance violations (HV-LV component pairs)
/// - Loop-area limit violations
/// - Thermal clearance violations

use crate::types::{
    PlacementState, QualityConfig, QualityMetrics, PcbSpecification,
    Violation, ViolationType,
};

pub fn evaluate(
    config: &QualityConfig,
    placement: &PlacementState,
    metrics: &QualityMetrics,
    spec: &PcbSpecification,
    classifications: &[crate::types::NetClassification],
) -> Vec<Violation> {
    let mut violations = Vec::new();

    evaluate_clearance(config, placement, &mut violations);
    evaluate_loop_areas(spec, metrics, &mut violations);
    evaluate_thermal(config, placement, &mut violations);
    evaluate_zones(config, placement, classifications, &mut violations);

    violations
}

fn evaluate_clearance(
    config: &QualityConfig,
    placement: &PlacementState,
    violations: &mut Vec<Violation>,
) {
    if config.hv_components.is_empty() || config.lv_components.is_empty() {
        return;
    }

    let min_clearance = config.min_hv_lv_clearance_mm;

    for hv_ref in &config.hv_components {
        for lv_ref in &config.lv_components {
            if hv_ref == lv_ref {
                continue;
            }
            let Some(hv_pos) = placement.component_refs.iter().position(|r| r == hv_ref) else {
                continue;
            };
            let Some(lv_pos) = placement.component_refs.iter().position(|r| r == lv_ref) else {
                continue;
            };

            let (hx, hy) = placement.positions[hv_pos];
            let (lx, ly) = placement.positions[lv_pos];

            let dx = hx - lx;
            let dy = hy - ly;
            let distance = (dx * dx + dy * dy).sqrt();

            if distance < min_clearance {
                violations.push(Violation {
                    violation_type: ViolationType::CreepageInsufficient,
                    description: format!(
                        "HV component {} and LV component {} are {:.2}mm apart; required >= {:.2}mm",
                        hv_ref, lv_ref, distance, min_clearance
                    ),
                    components: vec![hv_ref.clone(), lv_ref.clone()],
                    actual_value: distance,
                    required_value: min_clearance,
                });
            }
        }
    }
}

fn evaluate_loop_areas(
    _spec: &PcbSpecification,
    _metrics: &QualityMetrics,
    violations: &mut Vec<Violation>,
) {
    let threshold = 0.3;
    if _metrics.loop_area_score.value() < threshold {
        violations.push(Violation {
            violation_type: ViolationType::LoopAreaExceeded,
            description: format!(
                "loop_area_score {:.4} is below threshold {:.2}",
                _metrics.loop_area_score.value(),
                threshold
            ),
            components: vec![],
            actual_value: _metrics.loop_area_score.value(),
            required_value: threshold,
        });
    }
}

fn evaluate_thermal(
    config: &QualityConfig,
    placement: &PlacementState,
    violations: &mut Vec<Violation>,
) {
    let thermal_refs: Vec<&String> = config.thermal_components.iter().collect();
    if thermal_refs.len() < 2 {
        return;
    }

    let min_spacing = 10.0;

    for i in 0..thermal_refs.len() {
        for j in (i + 1)..thermal_refs.len() {
            let Some(pos_i) = placement.component_refs.iter().position(|r| r == thermal_refs[i]) else {
                continue;
            };
            let Some(pos_j) = placement.component_refs.iter().position(|r| r == thermal_refs[j]) else {
                continue;
            };

            let (ix, iy) = placement.positions[pos_i];
            let (jx, jy) = placement.positions[pos_j];

            let dx = ix - jx;
            let dy = iy - jy;
            let dist = (dx * dx + dy * dy).sqrt();

            if dist < min_spacing {
                violations.push(Violation {
                    violation_type: ViolationType::ThermalClearanceViolated,
                    description: format!(
                        "thermal components {} and {} are {:.2}mm apart; min spacing is {:.2}mm",
                        thermal_refs[i], thermal_refs[j], dist, min_spacing
                    ),
                    components: vec![thermal_refs[i].clone(), thermal_refs[j].clone()],
                    actual_value: dist,
                    required_value: min_spacing,
                });
            }
        }
    }
}

fn evaluate_zones(
    _config: &QualityConfig,
    _placement: &PlacementState,
    _classifications: &[crate::types::NetClassification],
    _violations: &mut Vec<Violation>,
) {
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::QualityMetrics;
    use std::collections::{BTreeSet, HashMap};

    fn test_placement() -> PlacementState {
        PlacementState {
            positions: vec![
                (5.0, 5.0),
                (10.0, 5.0),
                (50.0, 50.0),
            ],
            component_refs: vec!["Q1".into(), "U1".into(), "R1".into()],
            board_width_mm: 100.0,
            board_height_mm: 100.0,
        }
    }

    #[test]
    fn test_clearance_violation_detected() {
        let config = QualityConfig {
            hv_components: BTreeSet::from(["Q1".into()]),
            lv_components: BTreeSet::from(["U1".into()]),
            min_hv_lv_clearance_mm: 10.0,
            ..empty_config()
        };
        let placement = test_placement();
        let violations = evaluate(
            &config,
            &placement,
            &dummy_metrics(),
            &empty_spec(),
            &[],
        );
        assert!(!violations.is_empty());
        let v = &violations[0];
        assert_eq!(v.violation_type, ViolationType::CreepageInsufficient);
        assert!(v.actual_value < 10.0);
        assert!((v.required_value - 10.0).abs() < 1e-10);
    }

    #[test]
    fn test_no_clearance_violation_when_far_apart() {
        let config = QualityConfig {
            hv_components: BTreeSet::from(["Q1".into()]),
            lv_components: BTreeSet::from(["R1".into()]),
            min_hv_lv_clearance_mm: 5.0,
            ..empty_config()
        };
        let placement = test_placement();
        let violations = evaluate(
            &config,
            &placement,
            &dummy_metrics(),
            &empty_spec(),
            &[],
        );
        assert!(violations.is_empty());
    }

    #[test]
    fn test_thermal_violation_detected() {
        let config = QualityConfig {
            thermal_components: BTreeSet::from(["Q1".into(), "U1".into()]),
            ..empty_config()
        };
        let placement = test_placement();
        let violations = evaluate(
            &config,
            &placement,
            &dummy_metrics(),
            &empty_spec(),
            &[],
        );
        assert!(!violations.is_empty());
        let has_thermal = violations.iter().any(|v| {
            v.violation_type == ViolationType::ThermalClearanceViolated
        });
        assert!(has_thermal);
    }

    #[test]
    fn test_empty_config_no_violations() {
        let violations = evaluate(
            &empty_config(),
            &test_placement(),
            &dummy_metrics(),
            &empty_spec(),
            &[],
        );
        assert!(violations.is_empty());
    }

    #[test]
    fn test_loop_area_violation_with_bad_score() {
        let config = QualityConfig {
            loop_components: vec![vec!["Q1".into(), "U1".into(), "R1".into()]],
            ..empty_config()
        };
        let mut metrics = dummy_metrics();
        metrics.loop_area_score = crate::types::NormalizedScore::new(0.1).unwrap();
        let violations = evaluate(
            &config,
            &test_placement(),
            &metrics,
            &empty_spec(),
            &[],
        );
        let has_loop = violations
            .iter()
            .any(|v| v.violation_type == ViolationType::LoopAreaExceeded);
        assert!(has_loop);
    }

    fn empty_config() -> QualityConfig {
        QualityConfig {
            thermal_components: BTreeSet::new(),
            hv_components: BTreeSet::new(),
            lv_components: BTreeSet::new(),
            zone_assignments: HashMap::new(),
            loop_components: vec![],
            min_hv_lv_clearance_mm: 4.0,
        }
    }

    fn dummy_metrics() -> QualityMetrics {
        crate::types::QualityMetrics::from_precomputed(&crate::types::PrecomputedMetrics {
            thermal_score: 0.5,
            zone_compliance_score: 0.5,
            hv_lv_clearance_score: 0.5,
            loop_area_score: 0.5,
            congestion_score: 0.5,
            compactness_score: 0.5,
            connectivity_clustering_score: 0.5,
            total_wirelength_mm: 100.0,
        })
        .unwrap()
    }

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
}
