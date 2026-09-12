//! P1 power/domain composition for PFC and gate-drive saved candidates.
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding, Status};
use zapote_drc::power_integrity::{
    validate_ampacity, validate_isolation, AmpacityContract, IsolationContract, PowerPath,
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
    let net = match unit {
        P1Unit::Pfc => "PFC_BUS_PLUS_390V",
        P1Unit::GateDrive => "v15_ls",
    };
    let traces: Vec<_> = evidence
        .traces
        .iter()
        .filter(|t| t.net == net)
        .map(|t| t.id.clone())
        .collect();
    let vias: Vec<_> = evidence
        .vias
        .iter()
        .filter(|v| v.net == net)
        .map(|v| v.id.clone())
        .collect();
    let pads: Vec<_> = evidence
        .components
        .iter()
        .flat_map(|c| {
            c.footprint_pads
                .iter()
                .filter(|p| p.net == net)
                .map(|p| format!("{}.{}", c.id, p.pad))
        })
        .collect();
    append(
        &mut r,
        validate_ampacity(
            &evidence,
            &AmpacityContract {
                min_finished_copper_um: 70.0,
                paths: vec![PowerPath {
                    id: net.into(),
                    nets: vec![net.into()],
                    current_rms_a: None,
                    current_peak_a: None,
                    copper_thickness_um: copper_um,
                    trace_ids: traces,
                    via_ids: vias,
                    pad_ids: pads,
                }],
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
    r.coverage_gaps.push("Capacity screening uses nominal saved outer copper and an assumed 20 C rise; finished copper and permitted rise are not qualified. Only the selected bus/bias net is inventoried, not all power branches.".into());
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
