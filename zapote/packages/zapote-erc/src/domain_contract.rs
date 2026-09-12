//! Exact pin-role/domain compatibility for unit interfaces.
//!
//! Domain labels are authored facts.  A component census or net name alone
//! cannot establish pin ERC; every reviewed pin must be present, classified,
//! and either connected to the expected domain or explicitly marked NC.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use zapote_core::{CheckReport, Finding, Status};

pub const RULE: &str = "ERC.POWER.DOMAIN_PIN_CONTRACT";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PinContract {
    pub id: String,
    pub domain: String,
    /// Reviewed expected domain; `domain` is the observed/native
    /// classification supplied by the adapter.
    #[serde(default)]
    pub expected_domain: Option<String>,
    pub role: String,
    pub net: Option<String>,
    pub intentional_nc: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainContract {
    pub domains: Vec<String>,
    pub pins: Vec<PinContract>,
    pub allowed_crossings: Vec<DomainCrossing>,
    pub observed_crossings: Vec<ObservedCrossing>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainCrossing {
    pub id: String,
    pub from_domain: String,
    pub to_domain: String,
    pub isolation_barrier_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObservedCrossing {
    pub id: String,
    pub from_domain: String,
    pub to_domain: String,
    pub barrier_id: Option<String>,
}

fn push(
    findings: &mut Vec<Finding>,
    status: Status,
    msg: impl Into<String>,
    object: impl Into<String>,
    actual: Option<String>,
    required: Option<String>,
) {
    findings.push(Finding {
        rule: RULE.into(),
        severity: if status == Status::Fail {
            "error".into()
        } else {
            "warning".into()
        },
        status,
        message: msg.into(),
        object: object.into(),
        actual,
        required,
    });
}

/// Validate exact domain/pin obligations and permitted isolated crossings.
pub fn validate(contract: &DomainContract) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let known: BTreeSet<_> = contract.domains.iter().map(String::as_str).collect();
    if known.is_empty() {
        gaps.push("domain population is empty".into());
        push(
            &mut findings,
            Status::Indeterminate,
            "no authored voltage domains; compatibility is not established",
            "domains",
            None,
            Some("complete domain census".into()),
        );
    }
    let mut ids = BTreeSet::new();
    for pin in &contract.pins {
        if !ids.insert(&pin.id) {
            push(
                &mut findings,
                Status::Fail,
                "pin ID is duplicated",
                pin.id.clone(),
                None,
                Some("unique package pin IDs".into()),
            );
        }
        if !known.contains(pin.domain.as_str()) {
            push(
                &mut findings,
                Status::Fail,
                "pin references an unknown domain",
                pin.id.clone(),
                Some(pin.domain.clone()),
                Some("authored domain".into()),
            );
        }
        if let Some(expected) = &pin.expected_domain {
            if expected != &pin.domain {
                push(
                    &mut findings,
                    Status::Fail,
                    "pin domain disagrees with reviewed role contract",
                    pin.id.clone(),
                    Some(pin.domain.clone()),
                    Some(expected.clone()),
                );
            }
        } else {
            push(
                &mut findings,
                Status::Indeterminate,
                "pin has no independently authored expected domain",
                pin.id.clone(),
                Some(pin.domain.clone()),
                Some("expected domain".into()),
            );
        }
        if pin.role.trim().is_empty() {
            push(
                &mut findings,
                Status::Fail,
                "pin role is required",
                pin.id.clone(),
                None,
                Some("reviewed role".into()),
            );
        }
        if pin.intentional_nc && pin.net.is_some() {
            push(
                &mut findings,
                Status::Fail,
                "intentional NC pin must not carry a net",
                pin.id.clone(),
                pin.net.clone(),
                Some("net absent".into()),
            );
        }
        if !pin.intentional_nc && pin.net.as_deref().unwrap_or("").trim().is_empty() {
            push(
                &mut findings,
                Status::Indeterminate,
                "connected pin has no observed net; exact connectivity cannot be qualified",
                pin.id.clone(),
                None,
                Some("native net binding".into()),
            );
        }
    }
    if contract.pins.is_empty() {
        gaps.push("pin population is empty".into());
        push(
            &mut findings,
            Status::Indeterminate,
            "no package pins supplied; coarse component membership is insufficient",
            "pins",
            None,
            Some("complete package-pin census".into()),
        );
    }
    for crossing in &contract.allowed_crossings {
        if !known.contains(crossing.from_domain.as_str())
            || !known.contains(crossing.to_domain.as_str())
        {
            push(
                &mut findings,
                Status::Fail,
                "allowed crossing references an unknown domain",
                crossing.id.clone(),
                None,
                Some("known domains on both sides".into()),
            );
        }
        if crossing.from_domain == crossing.to_domain {
            push(
                &mut findings,
                Status::Fail,
                "allowed crossing must join distinct domains",
                crossing.id.clone(),
                None,
                Some("from != to".into()),
            );
        }
        if crossing.isolation_barrier_id.trim().is_empty() {
            push(
                &mut findings,
                Status::Indeterminate,
                "allowed crossing has no physical barrier identity",
                crossing.id.clone(),
                None,
                Some("reviewed isolation barrier".into()),
            );
        }
    }
    let mut seen = BTreeSet::new();
    for crossing in &contract.allowed_crossings {
        if crossing.id.trim().is_empty() || !seen.insert(&crossing.id) {
            push(
                &mut findings,
                Status::Fail,
                "allowed crossing ID must be unique and nonempty",
                &crossing.id,
                None,
                None,
            );
        }
    }
    seen.clear();
    for crossing in &contract.observed_crossings {
        if crossing.id.trim().is_empty()
            || !seen.insert(&crossing.id)
            || !contract.allowed_crossings.iter().any(|a| {
                a.id == crossing.id
                    && a.from_domain == crossing.from_domain
                    && a.to_domain == crossing.to_domain
                    && crossing.barrier_id.as_deref() == Some(a.isolation_barrier_id.as_str())
                    && !a.isolation_barrier_id.trim().is_empty()
            })
        {
            push(
                &mut findings,
                Status::Fail,
                "observed crossing must match the complete allowed ID/domain/barrier tuple",
                &crossing.id,
                None,
                None,
            );
        }
    }
    if !contract.allowed_crossings.is_empty() && contract.observed_crossings.is_empty() {
        gaps.push("allowed crossing population has no observed native crossing evidence".into());
        push(
            &mut findings,
            Status::Indeterminate,
            "crossing contract exists but native crossing population is absent",
            "observed_crossings",
            Some("0".into()),
            Some("observed crossing evidence".into()),
        );
    }
    CheckReport::from_findings(findings, vec![RULE.into()], gaps)
}

/// Gate-drive and PFC adapters use the same exact contract checker; keeping
/// the adapter separate prevents a generic donor registry from silently
/// changing a unit's reviewed domain policy.
pub fn validate_gate_drive(contract: &DomainContract) -> CheckReport {
    validate(contract)
}
pub fn validate_pfc(contract: &DomainContract) -> CheckReport {
    validate(contract)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn base() -> DomainContract {
        DomainContract {
            domains: vec!["HOT".into(), "SELV".into()],
            pins: vec![
                PinContract {
                    id: "U1.1".into(),
                    domain: "HOT".into(),
                    expected_domain: Some("HOT".into()),
                    role: "power".into(),
                    net: Some("HV".into()),
                    intentional_nc: false,
                },
                PinContract {
                    id: "U1.2".into(),
                    domain: "SELV".into(),
                    expected_domain: Some("SELV".into()),
                    role: "NC".into(),
                    net: None,
                    intentional_nc: true,
                },
            ],
            allowed_crossings: vec![DomainCrossing {
                id: "iso1".into(),
                from_domain: "HOT".into(),
                to_domain: "SELV".into(),
                isolation_barrier_id: "barrier".into(),
            }],
            observed_crossings: vec![ObservedCrossing {
                id: "iso1".into(),
                from_domain: "HOT".into(),
                to_domain: "SELV".into(),
                barrier_id: Some("barrier".into()),
            }],
        }
    }
    #[test]
    fn reviewed_contract_passes() {
        assert_eq!(validate(&base()).status, Status::Pass);
    }
    #[test]
    fn feedback_tap_misclassification_fails() {
        let mut c = base();
        c.pins[0].domain = "SELV".into();
        assert_eq!(validate(&c).status, Status::Fail);
    }
    #[test]
    fn missing_barrier_fails() {
        let mut c = base();
        c.observed_crossings[0].barrier_id = None;
        assert_eq!(validate(&c).status, Status::Fail);
    }
    #[test]
    fn intentional_nc_with_net_fails() {
        let mut c = base();
        c.pins[1].net = Some("NC".into());
        assert_eq!(validate(&c).status, Status::Fail);
    }
    #[test]
    fn swapped_native_domain_membership_fails_against_fixed_expectation() {
        let mut c = base();
        c.pins[0].domain = "SELV".into();
        c.pins[0].expected_domain = Some("HOT".into());
        assert_eq!(validate(&c).status, Status::Fail);
    }
    #[test]
    fn protective_earth_is_distinct_from_hot() {
        let mut c = base();
        c.domains.push("PE".into());
        c.pins.push(PinContract {
            id: "J1.PE".into(),
            domain: "PE".into(),
            expected_domain: Some("PE".into()),
            role: "protective-earth".into(),
            net: Some("PE_CHASSIS".into()),
            intentional_nc: false,
        });
        assert_eq!(validate(&c).status, Status::Pass);
        c.pins[2].domain = "HOT".into();
        assert_eq!(validate(&c).status, Status::Fail);
    }
    #[test]
    fn matching_crossing_id_cannot_hide_wrong_domain_or_barrier() {
        for which in 0..3 {
            let mut c = base();
            assert_eq!(validate(&c).status, Status::Pass);
            match which {
                0 => c.observed_crossings[0].from_domain = "SELV".into(),
                1 => c.observed_crossings[0].barrier_id = Some("different".into()),
                _ => c.observed_crossings.push(c.observed_crossings[0].clone()),
            };
            assert_eq!(validate(&c).status, Status::Fail);
        }
    }
}
