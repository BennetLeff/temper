//! Composition boundary for the standalone voltage sensing validator.
use sha2::{Digest, Sha256};
use zapote_core::{CheckReport, Finding, Status};

pub fn run_voltage_sense(source_utf8: &str, native_utf8: &str) -> CheckReport {
    let mut report = zapote_erc::voltage_sense::validate(source_utf8, native_utf8);
    let native = serde_json::from_str::<serde_json::Value>(native_utf8).unwrap_or_default();
    let stack = zapote_drc::stackup::validate_native_export(
        native_utf8,
        native["board_sha256"].as_str().unwrap_or(""),
    );
    report.findings.extend(stack.findings);
    report.checked_rules.extend(stack.checked_rules);
    let binding = zapote_drc::native_binding::validate(native_utf8);
    report.findings.extend(binding.findings);
    report.checked_rules.extend(binding.checked_rules);
    match serde_json::from_str::<zapote_core::unit::UnitNativeEvidence>(native_utf8) {
        Ok(evidence) => {
            for (cap, ic, pin) in [
                ("c_comp", "comp", "5"),
                ("c_ref_in", "reference", "4"),
                ("c_ref_out", "reference", "5"),
            ] {
                let pad = |id: &str, number: &str| {
                    evidence
                        .components
                        .iter()
                        .find(|c| c.id == id)
                        .and_then(|c| c.footprint_pads.iter().find(|p| p.pad == number))
                };
                let distance = pad(cap, "1").zip(pad(ic, pin)).map(|(a, b)| {
                    (a.position_mm[0] - b.position_mm[0]).hypot(a.position_mm[1] - b.position_mm[1])
                });
                let message = format!("{cap}.1 to {ic}.{pin} pad-centre locality {distance:?} mm; required <=5 mm (not a loop-inductance claim)");
                report
                    .findings
                    .push(if distance.is_some_and(|d| d.is_finite() && d <= 5.) {
                        Finding::pass("DRC.VOLTAGE.LOCALITY", message, cap)
                    } else {
                        Finding::fail("DRC.VOLTAGE.LOCALITY", message, cap)
                    });
            }
            report.checked_rules.push("DRC.VOLTAGE.LOCALITY".into());
            let clearance = zapote_drc::current_sense::native_clearance(&evidence, 0.2);
            report.findings.extend(clearance.findings);
            report.checked_rules.extend(clearance.checked_rules);
        }
        Err(e) => report.findings.push(Finding::fail(
            "DRC.VOLTAGE.INPUT",
            format!("native geometry: {e}"),
            "native",
        )),
    }
    CheckReport::from_findings(report.findings, report.checked_rules, report.coverage_gaps)
}

pub fn parse_and_run(source: &[u8], native: &[u8]) -> Result<CheckReport, String> {
    let source_text =
        std::str::from_utf8(source).map_err(|e| format!("source is not UTF-8: {e}"))?;
    let native_text =
        std::str::from_utf8(native).map_err(|e| format!("native export is not UTF-8: {e}"))?;
    Ok(run_voltage_sense(source_text, native_text))
}

pub fn input_hash(source: &[u8], native: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update((source.len() as u64).to_le_bytes());
    h.update(source);
    h.update(native);
    format!("{:x}", h.finalize())
}

pub fn passed(report: &CheckReport) -> bool {
    report.status == Status::Pass
}
