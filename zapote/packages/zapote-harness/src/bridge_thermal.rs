//! Harness binding for the power-entry bridge-neck thermal evidence.
//!
//! The thermal solver validates a retained numerical experiment. It does not
//! establish an allowable package, copper, or enclosure temperature: those
//! are assembly and rating inputs that remain explicitly indeterminate here.

use std::{collections::BTreeSet, path::Path};

use zapote_core::{CheckReport, Finding};

use crate::pfc_power::Report as PfcReport;

const NUMERICAL_RULE: &str = "THERMAL.POWER_ENTRY.BRIDGE_NECK_NUMERICAL";
const APPLICABILITY_RULE: &str = "THERMAL.POWER_ENTRY.BRIDGE_NECK_APPLICABILITY";
pub const RULES: [&str; 2] = [NUMERICAL_RULE, APPLICABILITY_RULE];

const NETS: [&str; 4] = ["minus", "ac1", "ac2", "plus"];

/// Run the retained bridge-neck replay and bind its currents to the PFC
/// branch model. Missing evidence is indeterminate; supplied evidence that
/// cannot be replayed or bound fails closed. A successful replay is still
/// conditional because cooling and temperature ratings are unqualified.
pub fn run(evidence_root: Option<&Path>, board: &[u8], pfc: Option<&PfcReport>) -> CheckReport {
    let mut findings = Vec::new();
    let numerical = match evidence_root {
        None => {
            findings.push(Finding::indeterminate(
                NUMERICAL_RULE,
                "bridge-neck thermal evidence directory was not supplied",
                "power-entry.bridge-necks",
            ));
            false
        }
        Some(root) if !root.is_dir() => {
            findings.push(Finding::fail(
                NUMERICAL_RULE,
                format!(
                    "bridge-neck thermal evidence directory is missing: {}",
                    root.display()
                ),
                root.display().to_string(),
            ));
            false
        }
        Some(root) => match zapote_thermal::neck_run::replay(root, board) {
            Err(error) => {
                findings.push(Finding::fail(
                    NUMERICAL_RULE,
                    format!("bridge-neck thermal evidence replay failed: {error:#}"),
                    root.display().to_string(),
                ));
                false
            }
            Ok(assessment) => {
                let mut errors = validate_assessment(&assessment.cases);
                errors.extend(bind_currents(&assessment.cases, pfc));
                if errors.is_empty() {
                    findings.push(Finding::pass(
                        NUMERICAL_RULE,
                        "bridge-neck thermal evidence replayed and currents bound to PFC branches",
                        root.display().to_string(),
                    ));
                    true
                } else {
                    findings.push(Finding::fail(
                        NUMERICAL_RULE,
                        errors.join("; "),
                        root.display().to_string(),
                    ));
                    false
                }
            }
        },
    };

    // This is deliberately emitted for every PowerEntry run, including a
    // numerically valid replay. No package, copper, solder, or enclosure
    // temperature limit is established by the retained model.
    findings.push(Finding::indeterminate(
        APPLICABILITY_RULE,
        if numerical {
            "thermal replay is numerical evidence only; bridge package, solder, rest-board temperatures and cooling are assumed, with no rating contract"
        } else {
            "thermal applicability is unqualified; bridge package, solder, rest-board temperatures and cooling have no rating contract"
        },
        "power-entry.bridge-necks",
    ));

    CheckReport::from_findings(
        findings,
        RULES.iter().map(|rule| (*rule).into()).collect(),
        vec![],
    )
}

fn validate_assessment(cases: &[zapote_thermal::neck_run::Case]) -> Vec<String> {
    let scenario_names: Vec<String> = zapote_thermal::neck_run::scenarios()
        .into_iter()
        .map(|scenario| scenario.name)
        .collect();
    let expected: BTreeSet<_> = NETS
        .iter()
        .flat_map(|net| {
            scenario_names
                .iter()
                .map(move |scenario| ((*net).to_owned(), scenario.clone()))
        })
        .collect();
    let mut seen = BTreeSet::new();
    let mut errors = Vec::new();
    for case in cases {
        if !NETS.contains(&case.net.as_str()) {
            errors.push(format!("unexpected bridge-neck net {}", case.net));
            continue;
        }
        if !scenario_names
            .iter()
            .any(|name| name == &case.scenario.name)
        {
            errors.push(format!(
                "unexpected bridge-neck scenario {} for {}",
                case.scenario.name, case.net
            ));
        }
        if !case.scenario.params.current_a.is_finite() || case.scenario.params.current_a <= 0.0 {
            errors.push(format!(
                "non-positive or non-finite current for {} / {}",
                case.net, case.scenario.name
            ));
        }
        let measurement = &case.measurement;
        if !measurement.resistance_ohm.is_finite()
            || !measurement.joule_power_w.is_finite()
            || !measurement.max_temperature_k.is_finite()
            || measurement.resistance_ohm <= 0.0
            || measurement.joule_power_w < 0.0
        {
            errors.push(format!(
                "invalid thermal measurement for {} / {}",
                case.net, case.scenario.name
            ));
        }
        if !seen.insert((case.net.clone(), case.scenario.name.clone())) {
            errors.push(format!(
                "duplicate thermal case {} / {}",
                case.net, case.scenario.name
            ));
        }
    }
    if seen.len() != expected.len() || seen.iter().any(|key| !expected.contains(key)) {
        errors.push(format!(
            "thermal evidence case population is incomplete: got {}, expected {}",
            seen.len(),
            expected.len()
        ));
    }
    errors
}

fn bind_currents(cases: &[zapote_thermal::neck_run::Case], pfc: Option<&PfcReport>) -> Vec<String> {
    let Some(pfc) = pfc else {
        return vec!["PFC branch report is unavailable for thermal current binding".into()];
    };
    let mut errors = Vec::new();
    for case in cases {
        let current = case.scenario.params.current_a;
        // The 5 A case is intentional sensitivity evidence. Every nominal,
        // hot, copper, airflow, and full-current case must equal the actual
        // determined branch current from the PFC report.
        let Some(expected) = branch_current(&pfc.branches, &case.net) else {
            errors.push(format!(
                "no determined PFC bridge branch for thermal net {}",
                case.net
            ));
            continue;
        };
        if !current_matches(&case.scenario.name, current, expected) {
            errors.push(format!(
                "thermal current {} A for {} / {} does not match determined PFC branch {} A",
                current, case.net, case.scenario.name, expected
            ));
        }
    }
    errors
}

fn current_matches(scenario: &str, current: f64, expected: f64) -> bool {
    if scenario == "low-current" && (current - 5.0).abs() <= 1e-9 {
        return true;
    }
    let tolerance = 1e-6 * expected.abs().max(1.0);
    (current - expected).abs() <= tolerance
}

fn branch_current(branches: &[crate::pfc_power::Branch], net: &str) -> Option<f64> {
    // These exact UUID-plus-segment IDs identify the four bridge neck
    // traces in the source/native graph. Keep the net check as a second
    // binding dimension; a net-only match is not sufficient evidence.
    let expected_id = match net {
        "minus" => "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2",
        "ac1" => "6be299ab-3af0-4444-8bb5-c26c3d6443f6:2",
        "ac2" => "44d2e757-cc34-46a2-88aa-5ae29db62817:0",
        "plus" => "e7dc2c72-d7b2-4456-afa6-efe227e0f8f8:2",
        _ => return None,
    };
    let matches: Vec<&crate::pfc_power::Branch> = branches
        .iter()
        .filter(|branch| branch.net == net && branch.id == expected_id)
        .collect();
    if matches.len() != 1 {
        return None;
    }
    let value = matches[0].determined_rms_a?;
    (value.is_finite() && value > 0.0).then_some(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn branch(id: &str, net: &str, current: Option<f64>) -> crate::pfc_power::Branch {
        crate::pfc_power::Branch {
            id: id.into(),
            net: net.into(),
            kind: "trace".into(),
            width_mm: 2.5,
            determined_rms_a: current,
            rms_envelope_a: current.unwrap_or(0.0),
            sampled_peak_envelope_a: current.unwrap_or(0.0),
            nominal_external_capacity_a: None,
        }
    }

    #[test]
    fn missing_evidence_is_indeterminate_and_rules_are_checked() {
        let report = run(None, b"board", None);
        assert_eq!(report.status, zapote_core::Status::Indeterminate);
        assert_eq!(report.checked_rules, RULES.map(str::to_owned));
        assert!(report
            .findings
            .iter()
            .any(|finding| finding.rule == NUMERICAL_RULE));
        assert!(report
            .findings
            .iter()
            .any(|finding| finding.rule == APPLICABILITY_RULE));
    }

    #[test]
    fn configured_missing_evidence_is_a_failure() {
        let report = run(
            Some(Path::new("/nonexistent/zapote-thermal-evidence")),
            b"board",
            None,
        );
        assert_eq!(report.status, zapote_core::Status::Fail);
    }

    #[test]
    fn missing_uuid_does_not_fall_back_to_net_only() {
        let branches = vec![branch("unrelated:2", "minus", Some(15.0))];
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn segment_id_collision_cannot_supply_or_override_current() {
        let id = "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2";
        let collision = format!("{id}0000");
        let mut branches = vec![branch(&collision, "minus", Some(14.0))];
        assert_eq!(branch_current(&branches, "minus"), None);
        branches.push(branch(id, "minus", Some(15.0)));
        assert_eq!(branch_current(&branches, "minus"), Some(15.0));
        branches.push(branch(id, "minus", Some(15.0)));
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn undetermined_matching_segment_fails_closed() {
        let id = "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2";
        let branches = vec![branch(id, "minus", None)];
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn disagreeing_matching_segments_are_not_collapsed() {
        let id = "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2";
        let branches = vec![
            branch(id, "minus", Some(15.0)),
            branch(id, "minus", Some(14.0)),
        ];
        assert_eq!(branch_current(&branches, "minus"), None);
    }

    #[test]
    fn nominal_wrong_current_is_rejected_but_low_sensitivity_is_allowed() {
        assert!(!current_matches("nominal-medium", 14.0, 15.0));
        assert!(current_matches("low-current", 5.0, 15.0));
    }
}
