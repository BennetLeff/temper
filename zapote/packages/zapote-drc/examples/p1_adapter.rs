//! Execute P1 checks on an actual native extractor receipt.
//! Usage: cargo run -p zapote-drc --example p1_adapter -- <pfc|gate-drive> <native.json>
use serde_json::Value;
use std::{env, fs};
use zapote_core::unit::UnitNativeEvidence;
use zapote_drc::power_integrity::{
    validate_ampacity, validate_isolation, AmpacityContract, IsolationContract, PowerPath,
};

/// Reviewed source expectation, independent from the native receipt labels.
fn expected_domain(unit: &str, net: &str) -> (&'static str, &'static str) {
    if unit == "pfc" {
        if net == "PE_CHASSIS" {
            ("PE", "protective-earth")
        } else {
            ("HOT", "power-or-hot-control")
        }
    } else if net.starts_with("v3v3")
        || net == "ctrl_gnd"
        || net.starts_with("pwm_")
        || net == "permit"
    {
        ("SELV", "control")
    } else if net == "gate_h_out" || net == "gate_h_kelvin" {
        ("GATE_H", "isolated-gate")
    } else if net == "gate_l_out" || net == "gate_l_kelvin" {
        ("GATE_L", "isolated-gate")
    } else if ["dis", "dt", "g", "nc_7", "outa", "outb", "v15_ls", "vdda"].contains(&net) {
        ("HOT", "reviewed-isolated-bias")
    } else {
        ("UNCLASSIFIED", "unreviewed-net")
    }
}

/// Native observation mapping is deliberately separate from the reviewed
/// expectation. The receipt has net membership but no domain field.
fn observed_domain(unit: &str, net: &str) -> (&'static str, &'static str) {
    if unit == "pfc" {
        if net == "PE_CHASSIS" {
            ("PE", "native-protective-earth")
        } else {
            ("HOT", "native-net")
        }
    } else if ["v3v3", "ctrl_gnd", "pwm_h", "pwm_l", "permit"].contains(&net) {
        ("SELV", "native-net")
    } else if ["gate_h_out", "gate_h_kelvin"].contains(&net) {
        ("GATE_H", "native-net")
    } else if ["gate_l_out", "gate_l_kelvin"].contains(&net) {
        ("GATE_L", "native-net")
    } else {
        ("HOT", "native-net")
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 3 || !["pfc", "gate-drive"].contains(&args[1].as_str()) {
        return Err("usage: p1_adapter <pfc|gate-drive> <native.json>".into());
    }
    let unit = &args[1];
    let raw: Value = serde_json::from_slice(&fs::read(&args[2])?)?;
    let native: UnitNativeEvidence = serde_json::from_value(raw)?;
    let target_net = if unit == "pfc" {
        "PFC_BUS_PLUS_390V"
    } else {
        "v15_ls"
    };
    let trace_ids = native
        .traces
        .iter()
        .filter(|t| t.net == target_net)
        .map(|t| t.id.clone())
        .collect();
    let via_ids = native
        .vias
        .iter()
        .filter(|v| v.net == target_net)
        .map(|v| v.id.clone())
        .collect();
    let pad_ids = native
        .components
        .iter()
        .flat_map(|c| {
            c.footprint_pads
                .iter()
                .filter(|p| p.net == target_net)
                .map(|p| format!("{}.{}", c.id, p.pad))
        })
        .collect();
    // The saved receipts do not bind a reviewed branch waveform. Evaluate
    // actual widths while keeping RMS current explicitly unproven.
    let ampacity = validate_ampacity(
        &native,
        &AmpacityContract {
            min_finished_copper_um: 70.0,
            paths: vec![PowerPath {
                id: target_net.into(),
                nets: vec![target_net.into()],
                current_rms_a: None,
                current_peak_a: None,
                copper_thickness_um: Some(70.0),
                trace_ids,
                via_ids,
                pad_ids,
            }],
        },
    );
    let mut seen = std::collections::BTreeSet::new();
    let pins = native
        .connections
        .iter()
        .filter_map(|c| {
            let id = format!("{}.{}", c.component, c.pin);
            if !seen.insert(id.clone()) {
                return None;
            }
            let (expected, role) = expected_domain(unit, &c.net);
            let (domain, observed_role) = observed_domain(unit, &c.net);
            Some(zapote_erc::domain_contract::PinContract {
                id,
                domain: domain.into(),
                expected_domain: Some(expected.into()),
                role: format!("{role}; observed={observed_role}"),
                net: Some(c.net.clone()),
                intentional_nc: false,
            })
        })
        .collect();
    let domain =
        zapote_erc::domain_contract::validate(&zapote_erc::domain_contract::DomainContract {
            domains: vec![
                "HOT".into(),
                "SELV".into(),
                "PE".into(),
                "GATE_H".into(),
                "GATE_L".into(),
            ],
            pins,
            allowed_crossings: vec![],
            observed_crossings: vec![],
        });
    // The native receipt has no barrier/Edge.Cuts surface-path extraction.
    // Keep the required population absent so the result is indeterminate;
    // never turn a caller-supplied boolean into evidence that a barrier exists.
    let isolation = validate_isolation(&IsolationContract {
        required_barrier_ids: vec!["p1-required-barrier".into()],
        barriers: vec![],
        allowed_crossings: vec![],
        observed_crossings: vec![],
    });
    let status = if [ampacity.status, domain.status, isolation.status]
        .contains(&zapote_core::Status::Fail)
    {
        "fail"
    } else if [ampacity.status, domain.status, isolation.status]
        .contains(&zapote_core::Status::Indeterminate)
    {
        "indeterminate"
    } else {
        "pass"
    };
    let exit_code = if status == "fail" {
        2
    } else if status == "indeterminate" {
        3
    } else {
        0
    };
    let out = serde_json::json!({"schema":"zapote.p1.execution.v1","unit":unit,"native_receipt":args[2],"board_sha256":native.board_sha256,"extractor_sha256":native.extractor_sha256,"populations":{"components":native.components.len(),"connections":native.connections.len(),"traces":native.traces.len(),"vias":native.vias.len()},"ampacity":ampacity,"domain":domain,"isolation":isolation,"status":status});
    println!("{}", serde_json::to_string_pretty(&out)?);
    std::process::exit(exit_code)
}
