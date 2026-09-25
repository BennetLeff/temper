//! Gate-drive construction checks composed over actual saved-board evidence.
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding};
use zapote_erc::source_circuit::Circuit;

fn append(into: &mut CheckReport, other: CheckReport) {
    into.findings.extend(other.findings);
    into.checked_rules.extend(other.checked_rules);
    into.coverage_gaps.extend(other.coverage_gaps);
}

/// The PCB bytes are a separate required input, not a hash copied from JSON.
pub fn run(source: &str, native: &str, board: &[u8]) -> CheckReport {
    let mut report = CheckReport::from_findings(vec![], vec![], vec![]);
    let topology = zapote_erc::gate_drive::validate(source, native);
    report.findings.push(match topology {
        Ok(()) => Finding::pass(
            "ERC.GATE_DRIVE.PACKAGE_GRAPH",
            "reviewed parts and all package-pin nets match the native export",
            "GateDriveUnit",
        ),
        Err(e) => Finding::fail("ERC.GATE_DRIVE.PACKAGE_GRAPH", e, "GateDriveUnit"),
    });
    report
        .checked_rules
        .push("ERC.GATE_DRIVE.PACKAGE_GRAPH".into());
    let digest = format!("{:x}", Sha256::digest(board));
    append(
        &mut report,
        zapote_drc::stackup::validate_native_export(native, &digest),
    );
    append(&mut report, zapote_drc::native_binding::validate(native));
    let embedded: serde_json::Value = serde_json::from_str(native).unwrap_or_default();
    report.findings.push(
        if embedded["board_file_utf8"].as_str().map(str::as_bytes) == Some(board) {
            Finding::pass(
                "DRC.GATE_DRIVE.SAVED_BYTES",
                "native evidence contains these exact PCB bytes",
                "board",
            )
        } else {
            Finding::fail(
                "DRC.GATE_DRIVE.SAVED_BYTES",
                "native export is stale or refers to a different PCB",
                "board",
            )
        },
    );
    report
        .checked_rules
        .push("DRC.GATE_DRIVE.SAVED_BYTES".into());
    match (
        Circuit::parse(source, zapote_erc::gate_drive::ENTRY),
        serde_json::from_str::<UnitNativeEvidence>(native),
    ) {
        (Ok(circuit), Ok(evidence)) => {
            append(
                &mut report,
                zapote_drc::current_sense::native_clearance(&evidence, 0.2),
            );
            let domain = |pins: &[&str]| -> Result<BTreeSet<String>, String> {
                pins.iter()
                    .map(|p| circuit.net(p).map(str::to_owned))
                    .collect()
            };
            let domains = (
                domain(&[
                    "driver.1",
                    "driver.2",
                    "host.3",
                    "driver.3",
                    "driver.4",
                    "driver.5",
                    "driver.6",
                    "driver.7",
                    "permit_sw.1",
                ]),
                domain(&["driver.14", "driver.15", "driver.16", "gate_h.1"]),
                domain(&["driver.9", "driver.10", "driver.11", "gate_l.1"]),
            );
            match domains {
                (Ok(primary), Ok(high), Ok(low)) => {
                    let secondary = high.union(&low).cloned().collect();
                    append(
                        &mut report,
                        zapote_drc::domain_clearance::validate(
                            &evidence, &primary, &secondary, 8.0,
                        ),
                    );
                    append(
                        &mut report,
                        zapote_drc::domain_clearance::validate(&evidence, &high, &low, 2.0),
                    );
                }
                _ => report.findings.push(Finding::fail(
                    "DRC.GATE_DRIVE.DOMAINS",
                    "required physical domain anchor is absent",
                    "driver",
                )),
            }
            for (cap, pin) in [("c_vcci", "3"), ("c_ls", "11"), ("c_boot", "16")] {
                let pad = |id: &str, number: &str| {
                    evidence
                        .components
                        .iter()
                        .find(|c| c.id == id)
                        .and_then(|c| c.footprint_pads.iter().find(|p| p.pad == number))
                };
                let distance = pad(cap, "1").zip(pad("driver", pin)).map(|(a, b)| {
                    (a.position_mm[0] - b.position_mm[0]).hypot(a.position_mm[1] - b.position_mm[1])
                });
                report
                    .findings
                    .push(if distance.is_some_and(|d| d.is_finite() && d <= 5.0) {
                        Finding::pass(
                            "DRC.GATE_DRIVE.BYPASS_LOCALITY",
                            format!("{cap}.1 to driver.{pin}: {distance:?} mm <=5 mm"),
                            cap,
                        )
                    } else {
                        Finding::fail(
                            "DRC.GATE_DRIVE.BYPASS_LOCALITY",
                            format!("{cap}.1 to driver.{pin}: {distance:?} mm; requires <=5 mm"),
                            cap,
                        )
                    });
            }
            report
                .checked_rules
                .push("DRC.GATE_DRIVE.BYPASS_LOCALITY".into());
        }
        (source, native) => report.findings.push(Finding::fail(
            "DRC.GATE_DRIVE.INPUT",
            format!("source: {:?}; native: {:?}", source.err(), native.err()),
            "input",
        )),
    }
    report.coverage_gaps.extend([
        "Spacing thresholds are prototype requirements; insulation system certification is not established.",
        "Dead-time interpolation uses an assumed characterization envelope; measured timing is NOT RUN.",
        "Bootstrap effective capacitance, diode recovery, gate charge, ringing and loaded thermal performance are NOT RUN.",
        "Native ERC/DRC reports must additionally pass zapote-native-reports with their command receipts.",
    ].map(str::to_owned));
    CheckReport::from_findings(report.findings, report.checked_rules, report.coverage_gaps)
}
