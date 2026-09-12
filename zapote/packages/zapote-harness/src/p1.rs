//! P1 power/domain composition for PFC and gate-drive saved candidates.
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding, Status};
use zapote_drc::power_integrity::{
    validate_ampacity, validate_isolation, validate_pad_entries, validate_via_current_sharing,
    AmpacityContract, IsolationContract, PadEntryContract, PowerPath, ViaCurrentSharingContract,
};
use zapote_erc::domain_contract::{validate, DomainContract, PinContract};
use zapote_erc::source_circuit::Circuit;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum P1Unit {
    Pfc,
    GateDrive,
}

fn append(dst: &mut CheckReport, src: CheckReport) {
    dst.findings.extend(src.findings);
    dst.checked_rules.extend(src.checked_rules);
    dst.coverage_gaps.extend(src.coverage_gaps);
}

fn finalize(report: &mut CheckReport) {
    report.status = if report.findings.iter().any(|f| f.status == Status::Fail) {
        Status::Fail
    } else if report
        .findings
        .iter()
        .any(|f| f.status == Status::Indeterminate)
        || !report.coverage_gaps.is_empty()
    {
        Status::Indeterminate
    } else {
        Status::Pass
    };
}

fn expected_domain(unit: P1Unit, net: &str) -> (&'static str, &'static str) {
    match unit {
        P1Unit::Pfc if net == "PE_CHASSIS" => ("PE", "protective-earth"),
        P1Unit::Pfc => ("HOT", "hot-referenced-circuit"),
        P1Unit::GateDrive
            if [
                "v3v3", "ctrl_gnd", "pwm_h", "pwm_l", "permit", "dis", "dt", "g", "nc_7",
            ]
            .contains(&net) =>
        {
            ("SELV", "gate-control")
        }
        P1Unit::GateDrive if ["gate_h_out", "gate_h_kelvin", "outa", "vdda"].contains(&net) => {
            ("GATE_H", "floating-high-side")
        }
        P1Unit::GateDrive if ["gate_l_out", "gate_l_kelvin", "outb", "v15_ls"].contains(&net) => {
            ("GATE_L", "floating-low-side")
        }
        P1Unit::GateDrive => ("UNCLASSIFIED", "unreviewed-net"),
    }
}

/// Run source/native binding, actual saved-board identity, exact pin domains,
/// and capacity-only native copper measurements. Unknown RMS currents remain
/// indeterminate while widths and capacities are still evaluated.
pub fn run(source: &str, native: &str, board: &[u8], unit: P1Unit) -> CheckReport {
    let mut r = CheckReport::from_findings(vec![], vec![], vec![]);
    let entry = match unit {
        P1Unit::Pfc => zapote_erc::power_entry::ENTRY,
        P1Unit::GateDrive => zapote_erc::gate_drive::ENTRY,
    };
    let parsed = Circuit::parse(source, entry);
    r.checked_rules
        .push("ERC.POWER.P1_SOURCE_NATIVE_BINDING".into());
    r.findings.push(match &parsed {
        Ok(c) => match c.bind_native(native) {
            Ok(()) => Finding::pass(
                "ERC.POWER.P1_SOURCE_NATIVE_BINDING",
                "source circuit and native package-pin membership agree",
                entry,
            ),
            Err(e) => Finding::fail("ERC.POWER.P1_SOURCE_NATIVE_BINDING", e, entry),
        },
        Err(e) => Finding::fail("ERC.POWER.P1_SOURCE_NATIVE_BINDING", e, entry),
    });
    let digest = format!("{:x}", Sha256::digest(board));
    let copper_um = std::str::from_utf8(board)
        .ok()
        .and_then(|text| zapote_drc::stackup::nominal_outer_copper_um(text).ok());
    r.checked_rules
        .push("DRC.POWER.P1_SAVED_BOARD_IDENTITY".into());
    let native_json: serde_json::Value = serde_json::from_str(native).unwrap_or_default();
    r.findings.push(
        if native_json["board_file_utf8"].as_str().map(str::as_bytes) == Some(board) {
            Finding::pass(
                "DRC.POWER.P1_SAVED_BOARD_IDENTITY",
                format!("native receipt binds supplied board bytes ({digest})"),
                "board",
            )
        } else {
            Finding::fail(
                "DRC.POWER.P1_SAVED_BOARD_IDENTITY",
                "native receipt does not bind supplied board bytes",
                "board",
            )
        },
    );
    let Ok(evidence) = serde_json::from_str::<UnitNativeEvidence>(native) else {
        r.findings.push(Finding::indeterminate(
            "DRC.POWER.P1_NATIVE_SCHEMA",
            "native receipt cannot be decoded",
            "native",
        ));
        finalize(&mut r);
        return r;
    };
    if let Ok(circuit) = parsed {
        let mut seen = BTreeSet::new();
        let mut pins = Vec::new();
        for c in &evidence.connections {
            let id = format!("{}.{}", c.component, c.pin);
            if !seen.insert(id.clone()) {
                continue;
            }
            let Some(source_net) = circuit.net(&id).ok() else {
                r.findings.push(Finding::fail(
                    "ERC.POWER.P1_SOURCE_NATIVE_BINDING",
                    "native endpoint is absent from source pin contract",
                    id,
                ));
                continue;
            };
            let (expected, role) = expected_domain(unit, source_net);
            let (observed, observed_role) = expected_domain(unit, &c.net);
            pins.push(PinContract {
                id,
                domain: observed.into(),
                expected_domain: Some(expected.into()),
                role: format!("{role}; observed={observed_role}"),
                net: Some(c.net.clone()),
                intentional_nc: false,
            });
        }
        let domains = match unit {
            P1Unit::Pfc => vec!["HOT".into(), "PE".into()],
            P1Unit::GateDrive => vec![
                "HOT".into(),
                "SELV".into(),
                "GATE_H".into(),
                "GATE_L".into(),
            ],
        };
        append(
            &mut r,
            validate(&DomainContract {
                domains,
                pins,
                allowed_crossings: vec![],
                observed_crossings: vec![],
            }),
        );
    }
    // These are the actual routed power/control paths in the maintained
    // candidates.  Each branch remains separately modeled: the 15 A PFC
    // input ceiling is not copied onto every same-net branch, and gate-drive
    // bias/output branches remain indeterminate until waveform bounds are
    // supplied by the reviewed operating contract.
    let nets: &[&str] = match unit {
        P1Unit::Pfc => &[
            "AC_L_RECTIFIED_INPUT",
            "AC_N_RECTIFIED_INPUT",
            "plus",
            "minus",
            "a1",
            "l1",
            "l2",
            "ac1",
            "ac2",
            "PFC_BUS_PLUS_390V",
            "PFC_BUS_MINUS",
            "AUX_15V_IN",
            "HOT_PERMIT_EXTERNAL",
            "RELAY_BYPASS_CTRL",
            "PE_CHASSIS",
        ],
        P1Unit::GateDrive => &[
            "v15_ls",
            "vdda",
            "outa",
            "outb",
            "gate_h_out",
            "gate_h_kelvin",
            "gate_l_out",
            "gate_l_kelvin",
        ],
    };
    let paths = nets
        .iter()
        .map(|net| PowerPath {
            id: (*net).into(),
            nets: vec![(*net).into()],
            current_rms_a: None,
            current_peak_a: None,
            copper_thickness_um: copper_um,
            trace_ids: evidence
                .traces
                .iter()
                .filter(|t| t.net == *net)
                .map(|t| t.id.clone())
                .collect(),
            via_ids: evidence
                .vias
                .iter()
                .filter(|v| v.net == *net)
                .map(|v| v.id.clone())
                .collect(),
            pad_ids: evidence
                .components
                .iter()
                .flat_map(|c| {
                    c.footprint_pads
                        .iter()
                        .filter(|p| p.net == *net)
                        .map(|p| format!("{}.{}", c.id, p.pad))
                })
                .collect(),
        })
        .collect();
    append(
        &mut r,
        validate_ampacity(
            &evidence,
            &AmpacityContract {
                min_finished_copper_um: 70.0,
                paths,
            },
        ),
    );
    // Empty authored populations are deliberately surfaced as incomplete;
    // these adapters cannot invent via plating, branch sharing, pad entry
    // mappings, or independent surface-path/material evidence.
    let via_branches = evidence
        .vias
        .iter()
        .filter(|v| nets.contains(&v.net.as_str()))
        .map(|v| zapote_drc::power_integrity::ViaCurrentBranch {
            id: format!("via:{}", v.id),
            net: v.net.clone(),
            via_ids: vec![v.id.clone()],
            current_rms_a: None,
            current_peak_a: None,
            plating_thickness_um: None,
            max_current_density_a_per_mm2: None,
            share: 1.0,
        })
        .collect();
    append(
        &mut r,
        validate_via_current_sharing(
            &evidence,
            &ViaCurrentSharingContract {
                branches: via_branches,
            },
        ),
    );
    let mut pad_entries = Vec::new();
    for c in &evidence.components {
        for p in &c.footprint_pads {
            if !nets.contains(&p.net.as_str()) {
                continue;
            }
            let pad_id = format!("{}.{}", c.id, p.pad);
            let trace = evidence
                .traces
                .iter()
                .filter(|t| t.net == p.net)
                .min_by(|a, b| {
                    let d = |t: &zapote_core::Trace| {
                        t.points_mm
                            .last()
                            .map(|q| (q[0] - p.position_mm[0]).hypot(q[1] - p.position_mm[1]))
                            .unwrap_or(f64::INFINITY)
                    };
                    d(a).total_cmp(&d(b))
                });
            if let Some(trace) = trace {
                pad_entries.push(zapote_drc::power_integrity::PadEntry {
                    id: format!("pad-entry:{}", pad_id),
                    trace_id: trace.id.clone(),
                    pad_id,
                    current_rms_a: None,
                    min_entry_width_mm: None,
                });
            }
        }
    }
    append(
        &mut r,
        validate_pad_entries(
            &evidence,
            &PadEntryContract {
                entries: pad_entries,
            },
        ),
    );
    append(
        &mut r,
        validate_isolation(&IsolationContract {
            required_barrier_ids: vec!["P1.REQUIRED_BARRIER".into()],
            barriers: vec![],
            allowed_crossings: vec![],
            observed_crossings: vec![],
        }),
    );
    r.coverage_gaps.push("Net and via candidates use nominal saved outer copper and an assumed 20 C rise. Branch extraction, exact pad-entry geometry, and surface-path modeling remain software gaps. Reviewed RMS/peak waveforms, plating/sharing, and material/cutout inputs are also absent.".into());
    finalize(&mut r);
    r
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn aggregate_status_preserves_failures() {
        let r = CheckReport::from_findings(
            vec![
                Finding::fail("x", "bad", "o"),
                Finding::indeterminate("y", "unknown", "o"),
            ],
            vec![],
            vec![],
        );
        assert_eq!(r.status, zapote_core::Status::Fail);
    }
}
