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
    let circuit = zapote_erc::power_entry::parse(source)?;
    let no_connects = zapote_erc::power_entry::no_connects(source)?;
    let mut expected: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (endpoint, net) in circuit.pins {
        if no_connects.contains(&endpoint.as_str()) {
            continue;
        }
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
            append(&mut r, power_entry_clearance_profile(source, &evidence));
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

fn power_entry_clearance_profile(source: &str, evidence: &UnitNativeEvidence) -> CheckReport {
    if zapote_erc::power_entry::entry(source) == Ok(zapote_erc::power_entry::ACTIVE_ENTRY) {
        return active_clearance_profile(source, evidence);
    }
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

/// Construction spacing policy, not insulation qualification. Floating gate
/// and bootstrap nets follow their source terminal, not logic ground. First
/// check every distinct net at the functional floor; then coalesce only the
/// reviewed low-differential groups for the existing high-voltage checker.
fn active_clearance_profile(source: &str, evidence: &UnitNativeEvidence) -> CheckReport {
    const RULE: &str = "DRC.NATIVE.CLEARANCE_PROFILE";
    let domains = (|| -> Result<BTreeMap<String, String>, String> {
        zapote_erc::power_entry::validate_source(source)?;
        let c = zapote_erc::power_entry::parse(source)?;
        let mut groups = BTreeMap::new();
        for (domain, pins) in [
            (
                "RECTIFIER_L",
                ["bridge.1", "bridge.2", "bridge.3", "q_hl.1"],
            ),
            (
                "RECTIFIER_R",
                ["bridge.12", "bridge.13", "bridge.14", "q_hr.1"],
            ),
        ] {
            for pin in pins {
                groups.insert(c.net(pin)?.to_owned(), domain.to_owned());
            }
        }
        Ok(groups)
    })();
    let groups = match domains {
        Ok(g) => g,
        Err(e) => {
            return CheckReport::from_findings(
                vec![Finding::fail(RULE, e, "active domains")],
                vec![RULE.into()],
                vec![],
            )
        }
    };
    let mut local = zapote_drc::current_sense::native_clearance(evidence, 0.2);
    for finding in &mut local.findings {
        finding.rule = RULE.into();
    }
    local.checked_rules = vec![RULE.into()];
    let mut grouped = evidence.clone();
    let remap = |net: &mut String| {
        if let Some(domain) = groups.get(net) {
            *net = domain.clone();
        }
    };
    for component in &mut grouped.components {
        for pad in &mut component.footprint_pads {
            remap(&mut pad.net);
        }
    }
    for trace in &mut grouped.traces {
        remap(&mut trace.net);
    }
    for via in &mut grouped.vias {
        remap(&mut via.net);
    }
    for zone in &mut grouped.zones {
        remap(&mut zone.net);
    }
    let hv = [
        "AC_L_RECTIFIED_INPUT",
        "AC_N_RECTIFIED_INPUT",
        "l1",
        "l2",
        "RECTIFIER_L",
        "RECTIFIER_R",
        "RECTIFIER_POSITIVE",
        "a1",
        "BOOST_DIODE_POSITIVE",
        "PFC_BUS_PLUS_390V",
        "bleeder1-p2",
        "r_vtop-p2",
        "r_vtop2-p2",
        "r_vtop3-p2",
        "r_vtop4-p2",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    append(
        &mut local,
        zapote_drc::current_sense::native_clearance_profile(
            &grouped,
            &hv,
            "PE_CHASSIS",
            2.0,
            6.0,
            0.2,
        ),
    );
    local.coverage_gaps.push("0.2 mm local / 2 mm between elevated-voltage domains / 6 mm to PE are retained construction floors. Surface creepage, package-internal insulation, pollution degree, material group and surge qualification are not established by this copper-clearance check.".into());
    CheckReport::from_findings(local.findings, local.checked_rules, local.coverage_gaps)
}

#[cfg(test)]
mod active_tests {
    use super::*;
    const SOURCE: &str =
        include_str!("../../../power-entry/active-rectifier/candidate/source-manifest.json");
    const NATIVE: &str = include_str!("../../../power-entry/active-rectifier/evidence/vsense-diode-side-02/native.json");

    #[test]
    fn half_bus_bleeder_midpoint_uses_high_voltage_spacing() {
        let mut evidence: UnitNativeEvidence = serde_json::from_str(NATIVE).unwrap();
        for (id, pin, x) in [("bleeder1", "2", 1000.), ("c_icomp", "1", 1002.)] {
            let pad = evidence.components.iter_mut().find(|c| c.id == id).unwrap()
                .footprint_pads.iter_mut().find(|p| p.pad == pin).unwrap();
            pad.position_mm = [x, 1000.];
            pad.size_mm = [0.1, 0.1];
        }
        let report = active_clearance_profile(SOURCE, &evidence);
        assert!(report.findings.iter().any(|f| f.object.contains("bleeder1.2")
            && f.object.contains("c_icomp.1") && f.status == Status::Fail
            && f.message.contains("2.000000")));
    }

    #[test]
    fn intentional_nc_does_not_hide_a_missing_or_split_connected_net() {
        let evidence: UnitNativeEvidence = serde_json::from_str(NATIVE).unwrap();
        validate_connectivity(SOURCE, &evidence).unwrap();
        let mut missing = evidence.clone();
        missing
            .connectivity_clusters
            .retain(|c| c.net != "RECTIFIER_POSITIVE");
        assert!(validate_connectivity(SOURCE, &missing)
            .unwrap_err()
            .contains("net census"));
        let mut split = evidence;
        split
            .connectivity_clusters
            .push(split.connectivity_clusters[0].clone());
        assert!(validate_connectivity(SOURCE, &split)
            .unwrap_err()
            .contains("split"));
    }

    #[test]
    fn floating_gate_domains_keep_local_clearance_and_cross_domain_failures() {
        let evidence: UnitNativeEvidence = serde_json::from_str(NATIVE).unwrap();
        let report = active_clearance_profile(SOURCE, &evidence);
        // The unchanged standard SOIC footprint is a discriminating oracle:
        // 2*1.27 - 0.60 = 1.94 mm between gates in different HV domains.
        assert!(report
            .findings
            .iter()
            .any(|f| f.object == "bridge.3 / bridge.5"
                && f.status == Status::Fail
                && f.message.contains("1.940000")));
        assert!(!report
            .findings
            .iter()
            .any(|f| f.object == "bridge.1 / bridge.2" && f.status == Status::Fail));
        // Same floating domain still has to meet the 0.2 mm functional floor.
        let mut short = evidence;
        let bridge = short
            .components
            .iter_mut()
            .find(|c| c.id == "bridge")
            .unwrap();
        let first = bridge
            .footprint_pads
            .iter()
            .find(|p| p.pad == "1")
            .unwrap()
            .position_mm;
        bridge
            .footprint_pads
            .iter_mut()
            .find(|p| p.pad == "2")
            .unwrap()
            .position_mm = first;
        let report = active_clearance_profile(SOURCE, &short);
        assert!(report
            .findings
            .iter()
            .any(|f| f.object == "bridge.1 / bridge.2" && f.status == Status::Fail));
    }
}
