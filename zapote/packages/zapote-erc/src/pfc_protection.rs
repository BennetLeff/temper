//! Source-bound protection model for the TI UCC28180 PFC controller.
//!
//! Thresholds are taken from the electrical-characteristics min/max table,
//! rather than typical values.  The model describes what the controller does;
//! it does not claim that PWM inhibition disconnects an energized mains bus.

use crate::power_entry;
use zapote_core::{CheckReport, Finding};

pub const RULES: [&str; 9] = [
    "ERC.PFC.PROTECTION.UVLO",
    "ERC.PFC.PROTECTION.STANDBY",
    "ERC.PFC.PROTECTION.OVP_HYSTERESIS",
    "ERC.PFC.PROTECTION.ISENSE_OPEN",
    "ERC.PFC.PROTECTION.ICOMP",
    "ERC.PFC.PROTECTION.SOC_PCL",
    "ERC.PFC.PROTECTION.BIAS_PRIORITY",
    "ERC.PFC.PROTECTION.EXTERNAL_DISCONNECT",
    "ERC.PFC.PROTECTION.TIMING",
];

/// UCC28180 electrical-characteristics limits (datasheet Rev D, table 7.5).
/// Voltages are volts and current-sense thresholds are negative volts.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DatasheetLimits {
    pub vcc_on_min: f64,
    pub vcc_on_max: f64,
    pub vcc_off_min: f64,
    pub vcc_off_max: f64,
    pub vsense_olp_min_fraction: f64,
    pub vsense_olp_max_fraction: f64,
    pub vovp_h_min_fraction: f64,
    pub vovp_h_max_fraction: f64,
    pub vovp_reset_min_fraction: f64,
    pub vovp_reset_max_fraction: f64,
    /// ISOP's 0.085 V value is typical only; there is no datasheet minimum.
    pub visop_typ: f64,
    pub visop_max: f64,
    /// The table's unit/columns conflict with the prose (0.2 V versus
    /// 0.2/0.25 %VREF). Keep both as an explicit ambiguity; no bound is used.
    pub icomp_typ_v: f64,
    pub icomp_max_v: f64,
    pub soc_min: f64,
    pub soc_max: f64,
    pub pcl_min: f64,
    pub pcl_max: f64,
}

impl Default for DatasheetLimits {
    fn default() -> Self {
        Self {
            vcc_on_min: 10.8,
            vcc_on_max: 12.1,
            vcc_off_min: 9.1,
            vcc_off_max: 10.3,
            vsense_olp_min_fraction: 0.156,
            vsense_olp_max_fraction: 0.176,
            vovp_h_min_fraction: 1.07,
            vovp_h_max_fraction: 1.11,
            vovp_reset_min_fraction: 1.00,
            vovp_reset_max_fraction: 1.04,
            visop_typ: 0.085,
            visop_max: 0.14,
            icomp_typ_v: 0.20,
            icomp_max_v: 0.25,
            soc_min: -0.259,
            soc_max: -0.312,
            pcl_min: -0.345,
            pcl_max: -0.438,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProtectionAction {
    NoModeledInhibit,
    Standby,
    UvloOff,
    OvpLatchedOff,
    IsenseOpenOff,
    SoftOvercurrent,
    PeakCurrentImmediateOff,
    Indeterminate,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ProtectionScenario {
    pub vcc: f64,
    pub vsense: f64,
    pub vref: f64,
    pub isense: f64,
    pub icomp: f64,
    pub ovp_latched: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ProtectionDecision {
    pub action: ProtectionAction,
    pub guaranteed: bool,
    pub propagation_delay_bound_ms: Option<f64>,
}

fn finite_nonnegative(values: &[f64]) -> bool {
    values.iter().all(|v| v.is_finite() && *v >= 0.0)
}

fn valid_limits(l: DatasheetLimits) -> bool {
    finite_nonnegative(&[
        l.vcc_on_min,
        l.vcc_on_max,
        l.vcc_off_min,
        l.vcc_off_max,
        l.vsense_olp_min_fraction,
        l.vsense_olp_max_fraction,
        l.vovp_h_min_fraction,
        l.vovp_h_max_fraction,
        l.vovp_reset_min_fraction,
        l.vovp_reset_max_fraction,
        l.visop_typ,
        l.visop_max,
        l.icomp_typ_v,
        l.icomp_max_v,
    ]) && l.vcc_on_min <= l.vcc_on_max
        && l.vcc_off_min <= l.vcc_off_max
        && l.vsense_olp_min_fraction <= l.vsense_olp_max_fraction
        && l.vovp_h_min_fraction <= l.vovp_h_max_fraction
        && l.vovp_reset_min_fraction <= l.vovp_reset_max_fraction
        && l.icomp_typ_v <= l.icomp_max_v
        && l.soc_max <= l.soc_min
        && l.pcl_max <= l.pcl_min
        && l.soc_min.is_finite()
        && l.soc_max.is_finite()
        && l.pcl_min.is_finite()
        && l.pcl_max.is_finite()
}

/// Evaluate one operating/fault point.  Values in datasheet uncertainty bands
/// are indeterminate; they are never silently treated as safe.
pub fn assess_scenario(s: ProtectionScenario, limits: DatasheetLimits) -> ProtectionDecision {
    if !valid_limits(limits)
        || !finite_nonnegative(&[s.vcc, s.vsense, s.vref, s.icomp])
        || !s.isense.is_finite()
        || s.vref <= 0.0
    {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    // A lost bias supply dominates an external permit/clamp: PWM is disabled
    // by UVLO and no gate-safety claim is made while VCC is in the hysteresis band.
    if s.vcc < limits.vcc_off_min {
        return ProtectionDecision {
            action: ProtectionAction::UvloOff,
            guaranteed: true,
            propagation_delay_bound_ms: None,
        };
    }
    if s.vcc <= limits.vcc_off_max || s.vcc < limits.vcc_on_max {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    // High OVP is a latch until the reset threshold is crossed.  Use the
    // conservative max threshold for a guaranteed trip and min reset threshold
    // for a guaranteed release.
    if s.ovp_latched {
        if s.vsense < limits.vovp_reset_min_fraction * s.vref {
            // The latch has released; continue through standby, open-pin,
            // current-limit and other protections before allowing PWM.
        } else if s.vsense >= limits.vovp_reset_max_fraction * s.vref {
            return ProtectionDecision {
                action: ProtectionAction::OvpLatchedOff,
                guaranteed: true,
                propagation_delay_bound_ms: None,
            };
        } else {
            return ProtectionDecision {
                action: ProtectionAction::Indeterminate,
                guaranteed: false,
                propagation_delay_bound_ms: None,
            };
        }
    }
    if s.vsense >= limits.vovp_h_max_fraction * s.vref {
        return ProtectionDecision {
            action: ProtectionAction::OvpLatchedOff,
            guaranteed: true,
            propagation_delay_bound_ms: None,
        };
    }
    if s.vsense > limits.vovp_h_min_fraction * s.vref {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    if s.vsense <= limits.vsense_olp_min_fraction * s.vref {
        return ProtectionDecision {
            action: ProtectionAction::Standby,
            guaranteed: true,
            propagation_delay_bound_ms: None,
        };
    }
    if s.vsense < limits.vsense_olp_max_fraction * s.vref {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    if s.isense >= limits.visop_max {
        return ProtectionDecision {
            action: ProtectionAction::IsenseOpenOff,
            guaranteed: true,
            propagation_delay_bound_ms: None,
        };
    }
    // ISOP has only a typical 0.085 V point, so values below the 0.14 V
    // maximum cannot prove that the open-pin comparator is or is not active.
    if s.isense >= 0.0 && s.isense < limits.visop_max {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    // TI's table/prose disagree on ICOMP units and only provide typical/max
    // values. Never claim a guaranteed ICOMP shutdown from this ambiguity.
    if s.icomp <= limits.icomp_max_v {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    if s.isense <= limits.pcl_max {
        return ProtectionDecision {
            action: ProtectionAction::PeakCurrentImmediateOff,
            guaranteed: true,
            propagation_delay_bound_ms: None,
        };
    }
    if s.isense <= limits.pcl_min {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    if s.isense <= limits.soc_max {
        return ProtectionDecision {
            action: ProtectionAction::SoftOvercurrent,
            guaranteed: true,
            propagation_delay_bound_ms: None,
        };
    }
    if s.isense <= limits.soc_min {
        return ProtectionDecision {
            action: ProtectionAction::Indeterminate,
            guaranteed: false,
            propagation_delay_bound_ms: None,
        };
    }
    ProtectionDecision {
        action: ProtectionAction::NoModeledInhibit,
        guaranteed: false,
        propagation_delay_bound_ms: None,
    }
}

/// Bind the model to the reviewed Atopile source and publish its coverage.
/// Missing timing, external permit producers, and mains isolation remain
/// indeterminate by construction.
pub fn evaluate_source(source: &str) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let topology_ok = power_entry::validate_source(source).is_ok();
    let uvlo_cases_ok = topology_ok
        && assess_scenario(
            ProtectionScenario {
                vcc: 9.0,
                vsense: 5.0,
                vref: 5.0,
                isense: -0.01,
                icomp: 2.0,
                ovp_latched: false,
            },
            DatasheetLimits::default(),
        )
        .action
            == ProtectionAction::UvloOff
        && assess_scenario(
            ProtectionScenario {
                vcc: 12.0,
                vsense: 5.0,
                vref: 5.0,
                isense: -0.01,
                icomp: 2.0,
                ovp_latched: false,
            },
            DatasheetLimits::default(),
        )
        .action
            == ProtectionAction::Indeterminate;
    findings.push(if uvlo_cases_ok {
        Finding::pass(RULES[0], "executed source-bound UVLO cases: 9.0 V guarantees off while 12.0 V remains in the startup uncertainty band", "U11.VCC")
    } else {
        Finding::fail(RULES[0], "source topology does not satisfy the reviewed UCC28180 power-entry contract", "power-entry.source")
    });
    if !topology_ok {
        for rule in RULES.iter().skip(1).take(6) {
            findings.push(Finding::fail(
                rule,
                "source binding failed; protection claim is not evaluated",
                "power-entry.source",
            ));
        }
        findings.push(Finding::indeterminate(
            RULES[7],
            "source binding failed; external disconnect remains unmodeled",
            "power-entry.mains",
        ));
        findings.push(Finding::indeterminate(
            RULES[8],
            "source binding failed; shutdown timing cannot be bounded",
            "power-entry.timing",
        ));
        return CheckReport::from_findings(
            findings,
            RULES.map(str::to_owned).to_vec(),
            vec!["source topology invalid".into()],
        );
    }
    let l = DatasheetLimits::default();
    let checks = [
        (
            RULES[1],
            ProtectionScenario {
                vcc: 15.0,
                vsense: 0.7,
                vref: 5.0,
                isense: -0.01,
                icomp: 2.0,
                ovp_latched: false,
            },
            ProtectionAction::Standby,
            "VSENSE standby threshold",
        ),
        (
            RULES[2],
            ProtectionScenario {
                vcc: 15.0,
                vsense: 5.6,
                vref: 5.0,
                isense: 0.0,
                icomp: 2.0,
                ovp_latched: false,
            },
            ProtectionAction::OvpLatchedOff,
            "high OVP shutdown",
        ),
        (
            RULES[3],
            ProtectionScenario {
                vcc: 15.0,
                vsense: 5.0,
                vref: 5.0,
                isense: 0.2,
                icomp: 2.0,
                ovp_latched: false,
            },
            ProtectionAction::IsenseOpenOff,
            "ISENSE open-pin shutdown",
        ),
        (
            RULES[4],
            ProtectionScenario {
                vcc: 15.0,
                vsense: 5.0,
                vref: 5.0,
                isense: -0.01,
                icomp: 0.1,
                ovp_latched: false,
            },
            ProtectionAction::Indeterminate,
            "ICOMP unit ambiguity",
        ),
        (
            RULES[5],
            ProtectionScenario {
                vcc: 15.0,
                vsense: 5.0,
                vref: 5.0,
                isense: -0.32,
                icomp: 2.0,
                ovp_latched: false,
            },
            ProtectionAction::SoftOvercurrent,
            "SOC average-current limit",
        ),
        (
            RULES[5],
            ProtectionScenario {
                vcc: 15.0,
                vsense: 5.0,
                vref: 5.0,
                isense: -0.45,
                icomp: 2.0,
                ovp_latched: false,
            },
            ProtectionAction::PeakCurrentImmediateOff,
            "PCL immediate gate shutdown",
        ),
        (
            RULES[6],
            ProtectionScenario {
                vcc: 9.0,
                vsense: 5.0,
                vref: 5.0,
                isense: 0.0,
                icomp: 2.0,
                ovp_latched: false,
            },
            ProtectionAction::UvloOff,
            "UVLO bias priority",
        ),
    ];
    for (rule, scenario, expected, object) in checks {
        let decision = assess_scenario(scenario, l);
        if expected == ProtectionAction::Indeterminate && decision.action == expected {
            findings.push(Finding::indeterminate(
                rule,
                format!("executed datasheet case remains indeterminate: {object}"),
                object,
            ));
        } else if decision.action == expected && decision.guaranteed && rule == RULES[6] {
            findings.push(Finding::indeterminate(rule,"UVLO inhibits PWM at the tested 9 V point; the inhibit-clamp release versus UVLO sequence during bias decay is not time-modeled",object));
        } else if decision.action == expected && decision.guaranteed {
            findings.push(Finding::pass(
                rule,
                format!("executed independent datasheet-bound scenario: {object}"),
                object,
            ));
        } else {
            findings.push(Finding::fail(
                rule,
                format!(
                    "datasheet-bound scenario returned {:?}, expected guaranteed {:?}",
                    decision.action, expected
                ),
                object,
            ));
        }
    }
    gaps.push("UCC28180 datasheet does not provide a guaranteed propagation delay for these shutdown paths".into());
    gaps.push("PWM inhibition does not provide mains isolation or disconnect the rectifier/boost bus; an external mains disconnect and stored-energy discharge contract is missing".into());
    findings.push(Finding::indeterminate(RULES[7], "controller PWM disable is not galvanic mains isolation; external disconnect and discharge behavior are unmodeled", "power-entry.mains"));
    findings.push(Finding::indeterminate(RULES[8], "datasheet provides no guaranteed propagation delay for UVLO, OLP, OVP, ISOP, ICOMP, SOC, or PCL shutdown", "power-entry.timing"));
    CheckReport::from_findings(findings, RULES.map(str::to_owned).to_vec(), gaps)
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;

    fn nominal() -> ProtectionScenario {
        ProtectionScenario {
            vcc: 15.0,
            vsense: 5.0,
            vref: 5.0,
            isense: 0.0,
            icomp: 2.0,
            ovp_latched: false,
        }
    }

    #[test]
    fn uvlo_dominates_permit_and_has_hysteresis_band() {
        let mut s = nominal();
        s.vcc = 9.0;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::UvloOff
        );
        s.vcc = 10.0;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
        s.vcc = 12.0;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
    }

    #[test]
    fn ovp_latches_until_conservative_reset() {
        let mut s = nominal();
        s.vsense = 5.6;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::OvpLatchedOff
        );
        s.ovp_latched = true;
        s.vsense = 5.1;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
        s.vsense = 4.9;
        s.isense = -0.01;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::NoModeledInhibit
        );
        s.vsense = 5.1;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
    }

    #[test]
    fn soc_and_pcl_are_not_conflated() {
        let mut s = nominal();
        s.isense = -0.30;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
        s.isense = -0.40;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
        s.isense = -0.32;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::SoftOvercurrent
        );
        s.isense = -0.45;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::PeakCurrentImmediateOff
        );
    }

    #[test]
    fn invalid_source_never_passes_and_static_uvlo_does_not_qualify_bias_decay() {
        let invalid = evaluate_source("{}");
        assert_eq!(invalid.findings.len(), RULES.len());
        assert!(!invalid.findings.iter().any(|f| f.status == Status::Pass));
        let report = evaluate_source(include_str!(
            "../../../power-entry/candidate/source-manifest.json"
        ));
        for rule in [RULES[4], RULES[6], RULES[7], RULES[8]] {
            assert!(report
                .findings
                .iter()
                .any(|f| f.rule == rule && f.status == Status::Indeterminate));
        }
    }
    #[test]
    fn malformed_values_fail_closed() {
        let mut s = nominal();
        s.vref = f64::NAN;
        assert_eq!(
            assess_scenario(s, DatasheetLimits::default()).action,
            ProtectionAction::Indeterminate
        );
    }

    #[test]
    fn source_binding_keeps_missing_isolation_indeterminate() {
        let source = include_str!("../../../power-entry/candidate/source-manifest.json");
        let report = evaluate_source(source);
        assert_eq!(report.findings[0].status, Status::Pass);
        assert_eq!(
            report.findings.last().unwrap().status,
            Status::Indeterminate
        );
        assert!(report
            .coverage_gaps
            .iter()
            .any(|gap| gap.contains("mains isolation")));
    }
}
