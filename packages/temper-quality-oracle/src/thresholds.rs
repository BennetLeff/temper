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
use std::collections::HashMap;

pub fn evaluate(
    config: &QualityConfig,
    placement: &PlacementState,
    metrics: &QualityMetrics,
    spec: &PcbSpecification,
    classifications: &[crate::types::NetClassification],
) -> Vec<Violation> {
    let mut violations = Vec::new();

    evaluate_clearance(config, placement, &mut violations);
    evaluate_loop_areas(spec, metrics, &config.loop_components, &mut violations);
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
    let index: HashMap<&str, usize> = placement
        .component_refs
        .iter()
        .enumerate()
        .map(|(i, r)| (r.as_str(), i))
        .collect();

    for hv_ref in &config.hv_components {
        let Some(&hv_pos) = index.get(hv_ref.as_str()) else {
            continue;
        };
        for lv_ref in &config.lv_components {
            if hv_ref == lv_ref {
                continue;
            }
            let Some(&lv_pos) = index.get(lv_ref.as_str()) else {
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
    metrics: &QualityMetrics,
    loop_components: &[Vec<String>],
    violations: &mut Vec<Violation>,
) {
    if loop_components.is_empty() {
        return;
    }
    let threshold = 0.3;
    if metrics.loop_area_score.value() < threshold {
        violations.push(Violation {
            violation_type: ViolationType::LoopAreaExceeded,
            description: format!(
                "loop_area_score {:.4} is below threshold {:.2}",
                metrics.loop_area_score.value(),
                threshold
            ),
            components: vec![],
            actual_value: metrics.loop_area_score.value(),
            required_value: threshold,
        });
    }
}

fn evaluate_thermal(
    config: &QualityConfig,
    placement: &PlacementState,
    violations: &mut Vec<Violation>,
) {
    let thermal = &config.thermal_components;
    if thermal.len() < 2 {
        return;
    }

    let min_spacing = 10.0;
    let index: HashMap<&str, usize> = placement
        .component_refs
        .iter()
        .enumerate()
        .map(|(i, r)| (r.as_str(), i))
        .collect();

    for (i, a) in thermal.iter().enumerate() {
        let Some(&pos_i) = index.get(a.as_str()) else {
            continue;
        };
        let (ix, iy) = placement.positions[pos_i];
        for b in thermal.iter().skip(i + 1) {
            let Some(&pos_j) = index.get(b.as_str()) else {
                continue;
            };

            let (jx, jy) = placement.positions[pos_j];

            let dx = ix - jx;
            let dy = iy - jy;
            let dist = (dx * dx + dy * dy).sqrt();

            if dist < min_spacing {
                violations.push(Violation {
                    violation_type: ViolationType::ThermalClearanceViolated,
                    description: format!(
                        "thermal components {} and {} are {:.2}mm apart; min spacing is {:.2}mm",
                        a, b, dist, min_spacing
                    ),
                    components: vec![a.clone(), b.clone()],
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
    // TODO(temper-xxx): Implement zone compliance checking — validate that components
    // assigned to zones (via QualityConfig::zone_assignments) are placed
    // within their designated zone boundaries. Currently all zone assignments
    // are silently accepted.
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    use crate::tests_common::{dummy_metrics, empty_spec};
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
}
