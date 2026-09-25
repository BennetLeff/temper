//! Explicit power-path ampacity and isolation obligations.
//!
//! This module is deliberately a contract checker, not a thermal qualification
//! model.  Currents, copper thickness and the native object population are
//! inputs; missing values therefore remain indeterminate.  In particular, a
//! component outline or package width is never used as a pad-width proxy.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding, Status};

pub const AMPACITY_RULE: &str = "DRC.POWER.PATH_AMPACITY";
pub const ISOLATION_RULE: &str = "DRC.POWER.ISOLATION_POPULATION";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PowerPath {
    pub id: String,
    pub nets: Vec<String>,
    pub current_rms_a: Option<f64>,
    pub current_peak_a: Option<f64>,
    pub copper_thickness_um: Option<f64>,
    pub trace_ids: Vec<String>,
    pub via_ids: Vec<String>,
    pub pad_ids: Vec<String>, // component.pad identifiers, e.g. "L1.1"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AmpacityContract {
    pub paths: Vec<PowerPath>,
    pub min_finished_copper_um: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IsolationContract {
    pub required_barrier_ids: Vec<String>,
    pub barriers: Vec<BarrierEvidence>,
    pub allowed_crossings: Vec<AllowedCrossing>,
    #[serde(default)]
    pub observed_crossings: Vec<AllowedCrossing>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BarrierEvidence {
    pub id: String,
    pub present: bool,
    pub surface_path_mm: Option<f64>,
    pub required_surface_path_mm: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AllowedCrossing {
    pub id: String,
    pub barrier_id: String,
    pub from_domain: String,
    pub to_domain: String,
}

fn finding(
    status: Status,
    rule: &str,
    message: impl Into<String>,
    object: String,
    actual: Option<String>,
    required: Option<String>,
) -> Finding {
    Finding {
        rule: rule.into(),
        severity: if status == Status::Fail {
            "error".into()
        } else {
            "warning".into()
        },
        status,
        message: message.into(),
        object,
        actual,
        required,
    }
}

// Reuse the already copied and provenanced Temper IPC scalar.
use crate::ipc::external_capacity_a;

pub fn validate_ampacity(native: &UnitNativeEvidence, contract: &AmpacityContract) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    if !contract.min_finished_copper_um.is_finite() || contract.min_finished_copper_um <= 0.0 {
        findings.push(finding(
            Status::Fail,
            AMPACITY_RULE,
            "minimum finished copper must be finite and positive".to_string(),
            "contract.min_finished_copper_um".into(),
            Some(contract.min_finished_copper_um.to_string()),
            Some("positive finite thickness".into()),
        ));
    }
    if contract.paths.is_empty() {
        gaps.push("required power-path population is empty".into());
        findings.push(finding(
            Status::Indeterminate,
            AMPACITY_RULE,
            "no authored power paths supplied",
            "paths".into(),
            None,
            Some("at least one reviewed path".into()),
        ));
    }
    for path in &contract.paths {
        let object = format!("path:{}", path.id);
        let Some(thickness) = path.copper_thickness_um else {
            findings.push(finding(
                Status::Indeterminate,
                AMPACITY_RULE,
                "finished copper is required; no value was inferred",
                object,
                None,
                Some("finished copper plus reviewed RMS current".into()),
            ));
            continue;
        };
        if !thickness.is_finite() || thickness <= 0.0 {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "current and copper thickness must be finite and positive",
                object,
                Some(format!("thickness_um={thickness}")),
                Some("positive finite thickness".into()),
            ));
            continue;
        }
        if thickness < contract.min_finished_copper_um {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "finished copper is below the authored path minimum",
                format!("path:{}.copper", path.id),
                Some(format!("{thickness:.3} um")),
                Some(format!(">= {:.3} um", contract.min_finished_copper_um)),
            ));
        }
        let nets: BTreeSet<_> = path.nets.iter().collect();
        let traces: Vec<_> = native
            .traces
            .iter()
            .filter(|t| path.trace_ids.contains(&t.id) && nets.contains(&t.net))
            .collect();
        if traces.len() != path.trace_ids.len() || traces.is_empty() {
            findings.push(finding(
                Status::Indeterminate,
                AMPACITY_RULE,
                "path trace population is incomplete or empty",
                format!("path:{}.traces", path.id),
                Some(format!(
                    "{}/{} trace IDs resolved",
                    traces.len(),
                    path.trace_ids.len()
                )),
                Some("all authored traces resolved".into()),
            ));
            continue;
        }
        for trace in traces {
            if !trace.width_mm.is_finite() || trace.width_mm <= 0.0 {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "trace width must be finite and positive",
                    trace.id.clone(),
                    Some(trace.width_mm.to_string()),
                    Some("positive finite width".into()),
                ));
                continue;
            }
            let capacity = external_capacity_a(trace.width_mm, thickness);
            if !capacity.is_finite() || capacity <= 0.0 {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "computed trace capacity is not finite and positive",
                    trace.id.clone(),
                    Some(capacity.to_string()),
                    Some("positive finite capacity".into()),
                ));
                continue;
            }
            let Some(current) = path.current_rms_a else {
                findings.push(finding(
                    Status::Indeterminate,
                    AMPACITY_RULE,
                    "actual trace geometry evaluated, but branch RMS current is unproven",
                    trace.id.clone(),
                    Some(format!(
                        "width={:.3} mm, capacity={capacity:.3} A",
                        trace.width_mm
                    )),
                    Some("reviewed branch RMS waveform bound".into()),
                ));
                continue;
            };
            let actual = format!(
                "width={:.3} mm, capacity={capacity:.3} A, rms={current:.3} A",
                trace.width_mm
            );
            if !current.is_finite() || current <= 0.0 || capacity + f64::EPSILON < current {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "actual trace neck is below the explicit RMS path current",
                    trace.id.clone(),
                    Some(actual),
                    Some(format!("capacity >= {current:.3} A")),
                ));
            } else {
                findings.push(finding(
                    Status::Pass,
                    AMPACITY_RULE,
                    "actual trace width meets the IPC screening capacity",
                    trace.id.clone(),
                    Some(actual),
                    Some(format!("capacity >= {current:.3} A")),
                ));
            }
        }
        for id in &path.via_ids {
            let Some(via) = native
                .vias
                .iter()
                .find(|v| v.id == *id && nets.contains(&v.net))
            else {
                findings.push(finding(
                    Status::Indeterminate,
                    AMPACITY_RULE,
                    "authored via is absent from native evidence",
                    id.clone(),
                    None,
                    Some("native via with matching net".into()),
                ));
                continue;
            };
            if !via.diameter_mm.is_finite()
                || !via.drill_mm.is_finite()
                || via.diameter_mm <= via.drill_mm
                || via.diameter_mm <= 0.0
                || via.drill_mm <= 0.0
            {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "via has no positive copper annulus",
                    id.clone(),
                    Some(format!(
                        "diameter={:.3}, drill={:.3} mm",
                        via.diameter_mm, via.drill_mm
                    )),
                    Some("diameter > drill > 0".into()),
                ));
            }
            findings.push(finding(
                Status::Indeterminate,
                AMPACITY_RULE,
                "via geometry is present but via current capacity is not modeled",
                id.clone(),
                None,
                Some("validated via-current model".into()),
            ));
        }
        let resolved_pads: Vec<_> = native
            .components
            .iter()
            .flat_map(|c| {
                c.footprint_pads
                    .iter()
                    .map(|p| format!("{}.{}", c.id, p.pad))
            })
            .filter(|id| path.pad_ids.contains(id))
            .collect();
        if path.pad_ids.is_empty() || resolved_pads.len() != path.pad_ids.len() {
            findings.push(finding(
                Status::Indeterminate,
                AMPACITY_RULE,
                "actual pad population is required; package dimensions cannot substitute",
                format!("path:{}.pads", path.id),
                None,
                Some("at least one component.pad native pad".into()),
            ));
        }
        if !path.pad_ids.is_empty() && resolved_pads.len() == path.pad_ids.len() {
            findings.push(finding(
                Status::Indeterminate,
                AMPACITY_RULE,
                "pad geometry is present but pad/current-sharing capacity is not modeled",
                format!("path:{}.pads", path.id),
                Some(format!("{} native pads", resolved_pads.len())),
                Some("validated pad-current and sharing model".into()),
            ));
        }
    }
    CheckReport::from_findings(findings, vec![AMPACITY_RULE.into()], gaps)
}

pub fn validate_isolation(contract: &IsolationContract) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let mut barrier_ids = BTreeSet::new();
    for barrier in &contract.barriers {
        if barrier.id.trim().is_empty() || !barrier_ids.insert(barrier.id.as_str()) {
            findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "barrier IDs must be unique and non-empty".to_string(),
                "barriers".into(),
                Some(barrier.id.clone()),
                Some("unique non-empty barrier ID".into()),
            ));
        }
        if let Some(value) = barrier.surface_path_mm {
            if !value.is_finite() || value < 0.0 {
                findings.push(finding(
                    Status::Fail,
                    ISOLATION_RULE,
                    "observed surface path must be finite and non-negative",
                    barrier.id.clone(),
                    Some(value.to_string()),
                    Some("finite value >= 0".into()),
                ));
            }
        }
        if let Some(value) = barrier.required_surface_path_mm {
            if !value.is_finite() || value < 0.0 {
                findings.push(finding(
                    Status::Fail,
                    ISOLATION_RULE,
                    "required surface path must be finite and non-negative",
                    barrier.id.clone(),
                    Some(value.to_string()),
                    Some("finite value >= 0".into()),
                ));
            }
        }
    }
    if contract.required_barrier_ids.is_empty() {
        gaps.push("required isolation barrier population is empty".into());
        findings.push(finding(
            Status::Indeterminate,
            ISOLATION_RULE,
            "no required barrier was authored; insulation cannot be accepted from clearance alone",
            "barriers".into(),
            None,
            Some("reviewed barrier population".into()),
        ));
    }
    for id in &contract.required_barrier_ids {
        let Some(barrier) = contract.barriers.iter().find(|b| b.id == *id) else {
            findings.push(finding(
                Status::Indeterminate,
                ISOLATION_RULE,
                "required barrier has no evidence record",
                id.clone(),
                None,
                Some("present barrier plus surface-path evidence".into()),
            ));
            continue;
        };
        if !barrier.present {
            findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "required physical isolation barrier is absent",
                id.clone(),
                Some("present=false".into()),
                Some("present=true".into()),
            ));
            continue;
        }
        match (barrier.surface_path_mm, barrier.required_surface_path_mm) {
            (Some(actual), Some(required))
                if actual.is_finite() && required.is_finite() && actual >= required =>
            {
                findings.push(finding(
                    Status::Pass,
                    ISOLATION_RULE,
                    "surface-path evidence meets the authored requirement",
                    id.clone(),
                    Some(format!("{actual:.3} mm")),
                    Some(format!(">= {required:.3} mm")),
                ))
            }
            (Some(actual), Some(required)) => findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "surface-path evidence is below the authored requirement",
                id.clone(),
                Some(format!("{actual:.3} mm")),
                Some(format!(">= {required:.3} mm")),
            )),
            _ => findings.push(finding(
                Status::Indeterminate,
                ISOLATION_RULE,
                "barrier exists but surface-path/material evidence is incomplete",
                id.clone(),
                None,
                Some("measured surface path and supported material/cutout assumptions".into()),
            )),
        }
    }
    for crossing in &contract.allowed_crossings {
        if !contract.required_barrier_ids.contains(&crossing.barrier_id) {
            findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "allowed domain crossing references an unrequired barrier",
                crossing.id.clone(),
                Some(crossing.barrier_id.clone()),
                Some("required barrier ID".into()),
            ));
        }
        if crossing.id.trim().is_empty()
            || crossing.from_domain.trim().is_empty()
            || crossing.to_domain.trim().is_empty()
        {
            findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "crossing ID and both domains are required",
                crossing.id.clone(),
                None,
                Some("non-empty crossing tuple".into()),
            ));
        }
    }
    let mut observed_ids = BTreeSet::new();
    for crossing in &contract.observed_crossings {
        if crossing.id.trim().is_empty() || !observed_ids.insert(crossing.id.as_str()) {
            findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "observed crossing IDs must be unique and non-empty",
                crossing.id.clone(),
                None,
                Some("unique crossing ID".into()),
            ));
        }
        let matching = contract.allowed_crossings.iter().any(|allowed| {
            allowed.id == crossing.id
                && allowed.from_domain == crossing.from_domain
                && allowed.to_domain == crossing.to_domain
                && allowed.barrier_id == crossing.barrier_id
        });
        if !matching {
            findings.push(finding(
                Status::Fail,
                ISOLATION_RULE,
                "observed crossing does not match an allowed ID/domain/barrier tuple",
                crossing.id.clone(),
                Some(format!(
                    "{} -> {} via {}",
                    crossing.from_domain, crossing.to_domain, crossing.barrier_id
                )),
                Some("exact authored crossing tuple".into()),
            ));
        }
    }
    CheckReport::from_findings(findings, vec![ISOLATION_RULE.into()], gaps)
}

/// A branch of plated vias carrying a declared share of a waveform.  The
/// adapter must provide plating and current density; neither is inferred from
/// a whole-bus rating.  The barrel model is intentionally conservative:
/// `pi * drill * plating` is the longitudinal copper section.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ViaCurrentBranch {
    pub id: String,
    pub net: String,
    pub via_ids: Vec<String>,
    pub current_rms_a: Option<f64>,
    pub current_peak_a: Option<f64>,
    pub plating_thickness_um: Option<f64>,
    pub max_current_density_a_per_mm2: Option<f64>,
    /// Fraction of the branch waveform assigned to each via in `via_ids`.
    pub share: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ViaCurrentSharingContract {
    pub branches: Vec<ViaCurrentBranch>,
}

pub fn validate_via_current_sharing(
    native: &UnitNativeEvidence,
    contract: &ViaCurrentSharingContract,
) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    if contract.branches.is_empty() {
        gaps.push("via-current branch population is empty".into());
        findings.push(finding(
            Status::Indeterminate,
            AMPACITY_RULE,
            "no via-current sharing branches supplied",
            "via_branches".into(),
            None,
            Some("reviewed branch population".into()),
        ));
    }
    let mut seen = BTreeSet::new();
    let mut seen_vias = BTreeSet::new();
    for branch in &contract.branches {
        let first_finding = findings.len();
        if branch.id.trim().is_empty() || !seen.insert(branch.id.as_str()) {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "via-current branch IDs must be unique and non-empty",
                branch.id.clone(),
                None,
                None,
            ));
        }
        if branch.via_ids.is_empty()
            || !branch.share.is_finite()
            || branch.share <= 0.0
            || branch.share > 1.0
            || (branch.share * branch.via_ids.len() as f64 - 1.0).abs() > 1e-9
        {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "via waveform, share, and current-density inputs must be finite and positive",
                branch.id.clone(),
                None,
                Some("0 < RMS <= peak; 0 < share <= 1; positive density".into()),
            ));
            continue;
        }
        for id in &branch.via_ids {
            if !seen_vias.insert(id.as_str()) {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "a native via is assigned to more than one sharing branch",
                    id.clone(),
                    None,
                    Some("one reviewed current-sharing branch".into()),
                ));
                continue;
            }
            let Some(via) = native.vias.iter().find(|v| v.id == *id) else {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "authored sharing via is absent from native evidence",
                    id.clone(),
                    None,
                    Some("native via".into()),
                ));
                continue;
            };
            if branch.net.trim().is_empty() || via.net != branch.net {
                findings.push(Finding::fail(
                    AMPACITY_RULE,
                    "via does not belong to the authored branch net",
                    id.clone(),
                ));
                continue;
            }
            if via.from_layer.trim().is_empty()
                || via.to_layer.trim().is_empty()
                || via.from_layer == via.to_layer
            {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "via must span two named layers",
                    id.clone(),
                    None,
                    Some("distinct from/to layers".into()),
                ));
                continue;
            }
            if !via.diameter_mm.is_finite()
                || !via.drill_mm.is_finite()
                || via.diameter_mm <= via.drill_mm
                || via.drill_mm <= 0.0
            {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "via has invalid drill or annulus",
                    id.clone(),
                    None,
                    Some("diameter > drill > 0".into()),
                ));
                continue;
            }
        }
        if findings[first_finding..]
            .iter()
            .any(|f| f.status == Status::Fail)
        {
            continue;
        }
        let (Some(rms), Some(peak), Some(density), Some(plating)) = (
            branch.current_rms_a,
            branch.current_peak_a,
            branch.max_current_density_a_per_mm2,
            branch.plating_thickness_um,
        ) else {
            findings.push(finding(
                Status::Indeterminate,
                AMPACITY_RULE,
                "via waveform, plating, or current-density bound is unavailable",
                branch.id.clone(),
                None,
                Some("reviewed RMS/peak, plating, and density bounds".into()),
            ));
            continue;
        };
        if !rms.is_finite()
            || rms <= 0.0
            || !peak.is_finite()
            || peak < rms
            || !density.is_finite()
            || density <= 0.0
            || !plating.is_finite()
            || plating <= 0.0
        {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "via waveform, plating, and current-density inputs must be finite and positive",
                branch.id.clone(),
                None,
                Some("0 < RMS <= peak; positive plating and density".into()),
            ));
            continue;
        }
        for id in &branch.via_ids {
            let Some(via) = native.vias.iter().find(|v| v.id == *id) else {
                continue;
            };
            let copper_area = std::f64::consts::PI * via.drill_mm * (plating / 1000.0);
            let capacity = copper_area * density;
            let demand = rms * branch.share;
            if capacity.is_finite() && capacity >= demand {
                findings.push(finding(
                    Status::Pass,
                    AMPACITY_RULE,
                    "via barrel meets its declared RMS share",
                    id.clone(),
                    Some(format!(
                        "capacity={capacity:.3} A, demand={demand:.3} A, peak={:.3} A",
                        peak * branch.share
                    )),
                    Some(format!(">= {demand:.3} A")),
                ));
            } else {
                findings.push(finding(
                    Status::Fail,
                    AMPACITY_RULE,
                    "via barrel is below its declared RMS share",
                    id.clone(),
                    Some(format!("capacity={capacity:.3} A, demand={demand:.3} A")),
                    Some(format!(">= {demand:.3} A")),
                ));
            }
        }
    }
    CheckReport::from_findings(findings, vec![AMPACITY_RULE.into()], gaps)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PadEntry {
    pub id: String,
    pub trace_id: String,
    pub pad_id: String,
    pub current_rms_a: Option<f64>,
    pub min_entry_width_mm: Option<f64>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PadEntryContract {
    pub entries: Vec<PadEntry>,
}

pub fn validate_pad_entries(
    native: &UnitNativeEvidence,
    contract: &PadEntryContract,
) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    if contract.entries.is_empty() {
        gaps.push("pad-entry population is empty".into());
    }
    for entry in &contract.entries {
        if entry
            .current_rms_a
            .map(|x| !x.is_finite() || x <= 0.0)
            .unwrap_or(false)
            || entry
                .min_entry_width_mm
                .map(|x| !x.is_finite() || x <= 0.0)
                .unwrap_or(false)
        {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "pad-entry current and width must be finite and positive",
                entry.id.clone(),
                None,
                None,
            ));
            continue;
        }
        let pad = native.components.iter().find_map(|c| {
            c.footprint_pads
                .iter()
                .find(|p| format!("{}.{}", c.id, p.pad) == entry.pad_id)
        });
        let Some(pad) = pad else {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "pad-entry pad is absent from native evidence",
                entry.pad_id.clone(),
                None,
                Some("native component.pad".into()),
            ));
            continue;
        };
        let Some(trace) = native
            .traces
            .iter()
            .find(|t| t.id == entry.trace_id && t.net == pad.net)
        else {
            findings.push(finding(
                Status::Fail,
                AMPACITY_RULE,
                "pad-entry trace is absent or on a different net",
                entry.trace_id.clone(),
                None,
                Some("native trace with matching net".into()),
            ));
            continue;
        };
        if !trace.width_mm.is_finite()
            || trace.width_mm <= 0.0
            || trace.points_mm.len() < 2
            || pad.size_mm.iter().any(|x| !x.is_finite() || *x <= 0.0)
        {
            findings.push(Finding::fail(
                AMPACITY_RULE,
                "malformed native pad/trace geometry",
                entry.id.clone(),
            ));
            continue;
        }
        // This association is only a same-net candidate. An endpoint envelope
        // or whole-pad projection cannot prove a copper neck or entry chord.
        findings.push(finding(Status::Indeterminate, AMPACITY_RULE,
            "same-net pad/trace candidate; actual entry polygon, current and neck validation remain unimplemented",
            entry.id.clone(), Some(format!("trace_width={:.3} mm", trace.width_mm)),
            Some("native polygon/chord oracle and branch-current contract".into())));
    }
    CheckReport::from_findings(findings, vec![AMPACITY_RULE.into()], gaps)
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::{Component, Connection, ConnectivityCluster, Trace, Via};
    fn native() -> UnitNativeEvidence {
        UnitNativeEvidence {
            polygon_max_error_mm: 0.0,
            board_sha256: "x".into(),
            extractor_sha256: "y".into(),
            copper_layer_count: 2,
            components: vec![Component {
                id: "J1".into(),
                mpn: "x".into(),
                kind: "x".into(),
                position_mm: vec![0.0, 0.0],
                footprint_pads: vec![],
            }],
            connections: vec![Connection {
                component: "J1".into(),
                pin: "1".into(),
                net: "HV".into(),
            }],
            connectivity_clusters: vec![ConnectivityCluster {
                net: "HV".into(),
                nodes: vec![],
                source: "native".into(),
            }],
            traces: vec![Trace {
                id: "neck".into(),
                net: "HV".into(),
                points_mm: vec![[0.0, 0.0], [1.0, 0.0]],
                layer: "F.Cu".into(),
                width_mm: 0.2,
            }],
            vias: vec![Via {
                id: "v1".into(),
                net: "HV".into(),
                position_mm: [0.0, 0.0],
                from_layer: "F.Cu".into(),
                to_layer: "B.Cu".into(),
                drill_mm: 0.3,
                diameter_mm: 0.6,
            }],
            zones: vec![],
        }
    }
    #[test]
    fn narrow_real_trace_fails() {
        let report = validate_ampacity(
            &native(),
            &AmpacityContract {
                min_finished_copper_um: 35.0,
                paths: vec![PowerPath {
                    id: "pfc".into(),
                    nets: vec!["HV".into()],
                    current_rms_a: Some(15.0),
                    current_peak_a: Some(21.0),
                    copper_thickness_um: Some(35.0),
                    trace_ids: vec!["neck".into()],
                    via_ids: vec!["v1".into()],
                    pad_ids: vec!["J1.1".into()],
                }],
            },
        );
        assert_eq!(report.status, Status::Fail);
    }
    #[test]
    fn missing_path_is_indeterminate() {
        let report = validate_ampacity(
            &native(),
            &AmpacityContract {
                min_finished_copper_um: 35.0,
                paths: vec![],
            },
        );
        assert_eq!(report.status, Status::Indeterminate);
    }
    #[test]
    fn missing_barrier_fails_closed() {
        let report = validate_isolation(&IsolationContract {
            required_barrier_ids: vec!["iso".into()],
            barriers: vec![],
            allowed_crossings: vec![],
            observed_crossings: vec![],
        });
        assert_eq!(report.status, Status::Indeterminate);
    }
    #[test]
    fn removed_barrier_fails() {
        let report = validate_isolation(&IsolationContract {
            required_barrier_ids: vec!["iso".into()],
            barriers: vec![BarrierEvidence {
                id: "iso".into(),
                present: false,
                surface_path_mm: None,
                required_surface_path_mm: Some(8.0),
            }],
            allowed_crossings: vec![],
            observed_crossings: vec![],
        });
        assert_eq!(report.status, Status::Fail);
    }

    #[test]
    fn removed_via_is_preserved_as_indeterminate() {
        let mut contract = AmpacityContract {
            min_finished_copper_um: 35.0,
            paths: vec![PowerPath {
                id: "pfc".into(),
                nets: vec!["HV".into()],
                current_rms_a: Some(1.0),
                current_peak_a: Some(2.0),
                copper_thickness_um: Some(35.0),
                trace_ids: vec!["neck".into()],
                via_ids: vec!["removed-via".into()],
                pad_ids: vec!["J1.1".into()],
            }],
        };
        let report = validate_ampacity(&native(), &contract);
        assert_eq!(report.status, Status::Indeterminate);
        contract.paths[0].via_ids.clear();
        assert_eq!(
            validate_ampacity(&native(), &contract).status,
            Status::Indeterminate
        );
    }

    #[test]
    fn via_sharing_rejects_missing_plating_and_accepts_explicit_equal_share() {
        let n = native();
        let missing = validate_via_current_sharing(
            &n,
            &ViaCurrentSharingContract {
                branches: vec![ViaCurrentBranch {
                    id: "v".into(),
                    net: "HV".into(),
                    via_ids: vec!["v1".into()],
                    current_rms_a: Some(2.0),
                    current_peak_a: Some(3.0),
                    plating_thickness_um: None,
                    max_current_density_a_per_mm2: Some(200.0),
                    share: 1.0,
                }],
            },
        );
        assert_eq!(missing.status, Status::Indeterminate);
        let ok = validate_via_current_sharing(
            &n,
            &ViaCurrentSharingContract {
                branches: vec![ViaCurrentBranch {
                    id: "v".into(),
                    net: "HV".into(),
                    via_ids: vec!["v1".into()],
                    current_rms_a: Some(2.0),
                    current_peak_a: Some(3.0),
                    plating_thickness_um: Some(25.0),
                    max_current_density_a_per_mm2: Some(200.0),
                    share: 1.0,
                }],
            },
        );
        assert_eq!(ok.status, Status::Pass);
    }

    #[test]
    fn via_mapping_is_checked_before_missing_electrical_inputs() {
        let mut contract = ViaCurrentSharingContract {
            branches: vec![ViaCurrentBranch {
                id: "candidate".into(),
                net: "wrong-net".into(),
                via_ids: vec!["v1".into()],
                current_rms_a: None,
                current_peak_a: None,
                plating_thickness_um: None,
                max_current_density_a_per_mm2: None,
                share: 1.0,
            }],
        };
        let wrong = validate_via_current_sharing(&native(), &contract);
        assert_eq!(wrong.status, Status::Fail);
        assert!(!wrong.findings.iter().any(|f| f.status == Status::Pass));
        contract.branches[0].net = "HV".into();
        assert_eq!(
            validate_via_current_sharing(&native(), &contract).status,
            Status::Indeterminate
        );
        contract.branches[0].via_ids[0] = "removed-via".into();
        assert_eq!(
            validate_via_current_sharing(&native(), &contract).status,
            Status::Fail
        );
    }

    #[test]
    fn pad_candidate_cannot_claim_entry_geometry_and_rejects_missing_trace() {
        let mut n = native();
        n.components[0].footprint_pads.push(zapote_core::Pad {
            pad: "1".into(),
            net: "HV".into(),
            position_mm: [1.0, 0.0],
            size_mm: [2.0, 1.0],
            drill_mm: [0.0, 0.0],
            shape: 1,
            roundrect_ratio: None,
            layers: vec!["F.Cu".into()],
            orientation_deg: 45.0,
        });
        let report = validate_pad_entries(
            &n,
            &PadEntryContract {
                entries: vec![PadEntry {
                    id: "e".into(),
                    trace_id: "neck".into(),
                    pad_id: "J1.1".into(),
                    current_rms_a: Some(1.0),
                    min_entry_width_mm: Some(1.2),
                }],
            },
        );
        assert_eq!(report.status, Status::Indeterminate);
        n.traces.clear();
        assert_eq!(
            validate_pad_entries(
                &n,
                &PadEntryContract {
                    entries: vec![PadEntry {
                        id: "e".into(),
                        trace_id: "neck".into(),
                        pad_id: "J1.1".into(),
                        current_rms_a: Some(1.0),
                        min_entry_width_mm: Some(1.2),
                    }]
                }
            )
            .status,
            Status::Fail
        );
    }
}
