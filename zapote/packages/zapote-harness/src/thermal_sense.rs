//! Harness composition for the standalone thermal sensing unit.
use zapote_core::{CheckReport, Finding};

pub fn run_thermal_sense(source: &str, native: &str, contract: &str) -> CheckReport {
    let mut report = zapote_erc::thermal_sense::validate(source, native, contract);
    let native_value = serde_json::from_str::<serde_json::Value>(native).unwrap_or_default();
    let stack = zapote_drc::stackup::validate_native_export(
        native,
        native_value["board_sha256"].as_str().unwrap_or(""),
    );
    report.findings.extend(stack.findings);
    report.checked_rules.extend(stack.checked_rules);
    let binding = zapote_drc::native_binding::validate(native);
    report.findings.extend(binding.findings);
    report.checked_rules.extend(binding.checked_rules);
    match serde_json::from_str::<zapote_core::unit::UnitNativeEvidence>(native) {
        Ok(evidence) => {
            for (cap, ic, pin) in [
                ("hs_bypass", "hs_comp", "5"),
                ("coil_bypass", "coil_comp", "5"),
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
                let message = format!(
                    "{cap}.1 to {ic}.{pin} pad-centre locality {distance:?} mm; required <=5 mm"
                );
                report
                    .findings
                    .push(if distance.is_some_and(|d| d.is_finite() && d <= 5.) {
                        Finding::pass("DRC.THERMAL.LOCALITY", message, cap)
                    } else {
                        Finding::fail("DRC.THERMAL.LOCALITY", message, cap)
                    });
            }
            report.checked_rules.push("DRC.THERMAL.LOCALITY".into());
            let clearance = zapote_drc::current_sense::native_clearance(&evidence, 0.2);
            report.findings.extend(clearance.findings);
            report.checked_rules.extend(clearance.checked_rules);
        }
        Err(e) => report.findings.push(Finding::fail(
            "DRC.THERMAL.INPUT",
            format!("native geometry: {e}"),
            "native",
        )),
    }
    CheckReport::from_findings(report.findings, report.checked_rules, report.coverage_gaps)
}

pub fn parse_and_run(source: &[u8], native: &[u8], contract: &[u8]) -> Result<CheckReport, String> {
    let s = std::str::from_utf8(source).map_err(|e| format!("source is not UTF-8: {e}"))?;
    let n = std::str::from_utf8(native).map_err(|e| format!("native is not UTF-8: {e}"))?;
    let c =
        std::str::from_utf8(contract).map_err(|e| format!("sensor contract is not UTF-8: {e}"))?;
    Ok(run_thermal_sense(s, n, c))
}
