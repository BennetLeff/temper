//! Construction harness for the standalone active-PFC power-entry unit.
//! Source topology is checked separately from native physical evidence;
//! missing measurements remain explicit indeterminate coverage.

use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding, Status};

fn append(dst: &mut CheckReport, src: CheckReport) {
    dst.findings.extend(src.findings);
    dst.checked_rules.extend(src.checked_rules);
    dst.coverage_gaps.extend(src.coverage_gaps);
}

fn validate_connectivity(source: &str, evidence: &UnitNativeEvidence) -> Result<(), String> {
    let circuit =
        zapote_erc::source_circuit::Circuit::parse(source, zapote_erc::power_entry::ENTRY)?;
    let mut expected: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (endpoint, net) in circuit.pins {
        expected.entry(net).or_default().insert(endpoint);
    }
    let mut actual: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for cluster in &evidence.connectivity_clusters {
        if cluster.source != "native" {
            return Err("copper connectivity requires native evidence".into());
        }
        if actual.contains_key(&cluster.net) {
            return Err(format!(
                "native net {} is split across multiple connectivity clusters",
                cluster.net
            ));
        }
        actual.insert(cluster.net.clone(), cluster.nodes.iter().cloned().collect());
    }
    if actual.keys().collect::<BTreeSet<_>>() != expected.keys().collect::<BTreeSet<_>>() {
        return Err("native connectivity net census differs from source graph".into());
    }
    for (net, want) in expected {
        let got = actual.get(&net).expect("checked net census");
        if got != &want {
            return Err(format!(
                "native copper cluster for {net} differs: expected {} nodes, got {}",
                want.len(),
                got.len()
            ));
        }
    }
    Ok(())
}

pub fn run(source: &str, native: &str, board: &[u8]) -> CheckReport {
    let mut r = CheckReport::from_findings(vec![], vec![], vec![]);
    append(&mut r, zapote_erc::pfc_interfaces::validate(source));
    append(&mut r, zapote_erc::pfc_protection::evaluate_source(source));
    append(&mut r, zapote_erc::pfc_shunt::evaluate_source(source));
    r.checked_rules.push("ERC.POWER_ENTRY.SOURCE_GRAPH".into());
    r.findings
        .push(match zapote_erc::power_entry::validate(source, native) {
            Ok(()) => Finding::pass(
                "ERC.POWER_ENTRY.SOURCE_GRAPH",
                "reviewed PFC component and net graph matches the construction contract",
                "PowerEntryUnit",
            ),
            Err(e) => Finding::fail("ERC.POWER_ENTRY.SOURCE_GRAPH", e, "PowerEntryUnit"),
        });

    let digest = format!("{:x}", Sha256::digest(board));
    append(
        &mut r,
        zapote_drc::stackup::validate_native_export(native, &digest),
    );
    append(&mut r, zapote_drc::native_binding::validate(native));
    r.checked_rules.push("DRC.POWER_ENTRY.SAVED_BYTES".into());
    let native_json: serde_json::Value = serde_json::from_str(native).unwrap_or_default();
    r.findings.push(
        if native_json["board_file_utf8"].as_str().map(str::as_bytes) == Some(board) {
            Finding::pass(
                "DRC.POWER_ENTRY.SAVED_BYTES",
                "native evidence contains the supplied board bytes",
                "board",
            )
        } else {
            Finding::fail(
                "DRC.POWER_ENTRY.SAVED_BYTES",
                "native export is stale or refers to different board bytes",
                "board",
            )
        },
    );

    match serde_json::from_str::<UnitNativeEvidence>(native) {
        Ok(evidence) => {
            r.checked_rules.push("DRC.POWER_ENTRY.CONNECTIVITY".into());
            r.findings
                .push(match validate_connectivity(source, &evidence) {
                    Ok(()) => Finding::pass(
                        "DRC.POWER_ENTRY.CONNECTIVITY",
                        "native copper clusters exactly match every source net",
                        "connectivity_clusters",
                    ),
                    Err(e) => {
                        Finding::fail("DRC.POWER_ENTRY.CONNECTIVITY", e, "connectivity_clusters")
                    }
                });
            append(&mut r, power_entry_clearance_profile(&evidence));
        }
        Err(e) => r.findings.push(Finding::fail(
            "DRC.POWER_ENTRY.NATIVE_INPUT",
            format!("native evidence is not a UnitNativeEvidence export: {e}"),
            "native",
        )),
    }
    r.checked_rules.push("ERC.POWER_ENTRY.NOMINAL_MODEL".into());
    r.findings.push(match zapote_erc::power_entry::nominal_screen() {
        Ok(screen) => Finding::pass("ERC.POWER_ENTRY.NOMINAL_MODEL", format!("nominal control/bleeder model constructed: bus {:.1} V, bleed {:.3} W each, external HOT permit required", screen.bus_setpoint_v, screen.bleeder_power_each_w), "PowerEntryUnit"),
        Err(e) => Finding::fail("ERC.POWER_ENTRY.NOMINAL_MODEL", e, "PowerEntryUnit"),
    });
    r.coverage_gaps.extend([
        "External isolated bias supply, HOT permit, precharge and bypass sequencing are required; this harness does not implement them.",
        "15 A RMS foldback/PF behavior is a declared input constraint, not a measured result.",
        "Bus bleeder decay, relay timing, semiconductor/capacitor thermal limits, EMC, insulation and mains qualification are NOT RUN.",
    ].map(str::to_owned));
    CheckReport::from_findings(r.findings, r.checked_rules, r.coverage_gaps)
}

fn power_entry_clearance_profile(evidence: &UnitNativeEvidence) -> CheckReport {
    let hv: BTreeSet<String> = [
        "AC_L_RECTIFIED_INPUT",
        "AC_N_RECTIFIED_INPUT",
        "l1",
        "l2",
        "ac1",
        "ac2",
        "plus",
        "a1",
        "PFC_BUS_PLUS_390V",
        // Elevated-voltage feedback ladder taps; do not waive their pad
        // spacing merely because the ladder is a functional signal.
        "r_vtop-p2",
        "r_vtop2-p2",
        "r_vtop3-p2",
        "r_vtop4-p2",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    zapote_drc::current_sense::native_clearance_profile(evidence, &hv, "PE_CHASSIS", 2.0, 6.0, 0.2)
}

pub fn exit_code(status: Status) -> i32 {
    match status {
        Status::Pass => 0,
        Status::Fail => 1,
        Status::Indeterminate => 2,
    }
}
