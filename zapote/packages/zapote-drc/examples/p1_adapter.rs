//! Execute P1 checks on an actual native extractor receipt.
//! Usage: cargo run -p zapote-drc --example p1_adapter -- <pfc|gate-drive> <native.json>
use serde_json::Value;
use std::{env, fs};
use zapote_core::unit::UnitNativeEvidence;
use zapote_drc::power_integrity::{
    validate_ampacity, validate_isolation, AmpacityContract, IsolationContract, PowerPath,
};

fn domain_for(unit: &str, net: &str) -> (&'static str, &'static str) {
    if unit == "pfc" {
        if net.starts_with("AC_")
            || net.starts_with("PFC_BUS")
            || [
                "plus",
                "minus",
                "l1",
                "l2",
                "a1",
                "ac1",
                "ac2",
                "PE_CHASSIS",
            ]
            .contains(&net)
        {
            return ("HOT", "power");
        }
        ("SELV", "control")
    } else if net.starts_with("v3v3")
        || net == "ctrl_gnd"
        || net.starts_with("pwm_")
        || net == "permit"
    {
        ("SELV", "control")
    } else {
        ("HOT", "gate-drive")
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
    let current = if unit == "pfc" { 15.0 } else { 2.5 };
    let ampacity = validate_ampacity(
        &native,
        &AmpacityContract {
            min_finished_copper_um: 70.0,
            paths: vec![PowerPath {
                id: target_net.into(),
                nets: vec![target_net.into()],
                current_rms_a: Some(current),
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
            let (domain, role) = domain_for(unit, &c.net);
            Some(zapote_erc::domain_contract::PinContract {
                id,
                domain: domain.into(),
                expected_domain: Some(domain.into()),
                role: role.into(),
                net: Some(c.net.clone()),
                intentional_nc: false,
            })
        })
        .collect();
    let domain =
        zapote_erc::domain_contract::validate(&zapote_erc::domain_contract::DomainContract {
            domains: vec!["HOT".into(), "SELV".into()],
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
    });
    let out = serde_json::json!({"schema":"zapote.p1.execution.v1","unit":unit,"native_receipt":args[2],"board_sha256":native.board_sha256,"extractor_sha256":native.extractor_sha256,"populations":{"components":native.components.len(),"connections":native.connections.len(),"traces":native.traces.len(),"vias":native.vias.len()},"ampacity":ampacity,"domain":domain,"isolation":isolation,"status":"indeterminate"});
    println!("{}", serde_json::to_string_pretty(&out)?);
    Ok(())
}
