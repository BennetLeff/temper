//! Thin composition boundary for the standalone interlock validator.

use zapote_core::{CheckReport, Finding};

pub fn run_interlock(source: &str, native: &str, contract: &str) -> CheckReport {
    let mut report = zapote_erc::interlock::validate(source, native);
    let contract_value: serde_json::Value = match serde_json::from_str(contract) {
        Ok(value) => value,
        Err(error) => {
            report.findings.push(Finding::fail(
                "ERC.INTERLOCK.CONTRACT",
                error.to_string(),
                "interface-contract",
            ));
            return CheckReport::from_findings(
                report.findings,
                report.checked_rules,
                report.coverage_gaps,
            );
        }
    };
    let native_value: serde_json::Value = serde_json::from_str(native).unwrap_or_default();
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
                ("fault_inv_bypass", "fault_inv", "14"),
                ("control_inv_bypass", "control_inv", "14"),
                ("aggregate_bypass", "aggregate", "14"),
                ("latch_bypass", "latch", "8"),
                ("watchdog_bypass", "watchdog", "5"),
                ("common_bypass", "common", "5"),
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
                report
                    .findings
                    .push(if distance.is_some_and(|d| d.is_finite() && d <= 5.0) {
                        Finding::pass(
                            "DRC.INTERLOCK.LOCALITY",
                            format!("{cap}.1 to {ic}.{pin}: {distance:?} mm"),
                            cap,
                        )
                    } else {
                        Finding::fail(
                            "DRC.INTERLOCK.LOCALITY",
                            format!("{cap}.1 to {ic}.{pin}: {distance:?} mm; required <=5 mm"),
                            cap,
                        )
                    });
            }
            report.checked_rules.push("DRC.INTERLOCK.LOCALITY".into());
            let clearance = zapote_drc::current_sense::native_clearance(&evidence, 0.15);
            report.findings.extend(clearance.findings);
            report.checked_rules.extend(clearance.checked_rules);
        }
        Err(error) => report.findings.push(Finding::indeterminate(
            "DRC.INTERLOCK.NATIVE_INPUT",
            format!("native geometry schema unavailable: {error}"),
            "native",
        )),
    }
    let expected = serde_json::json!({
      "schema": "zapote.interlock.contract.v1",
      "supply_v": [
        3.135,
        3.465
      ],
      "fault_inputs": [
        "ocp",
        "ovp",
        "hs",
        "coil",
        "rtd",
        "runaway",
        "aux"
      ],
      "fault_active_high": true,
      "reset_active_low_edge": true,
      "sensor_live_required": true,
      "sensor_live_producer": "integration-obligation-not-yet-implemented",
      "permit_active_high": true,
      "receiver_pulldown_required": true,
      "watchdog_timeout_s": [
        0.9,
        1.6,
        2.5
      ],
      "power_on_reset_delay_s": [
        0.12,
        0.2,
        0.3
      ],
      "logic_inputs_v": {
        "low_max": 0.3,
        "high_min": 2.7
      },
      "aggregate_input_leakage_a": 2e-05,
      "reset_pulse_min_s": 1e-06,
      "reset_after_all_good_s": 0.001,
      "qualification": "indeterminate",
      "physical_tests": "NOT RUN"
    });
    report.findings.push(if contract_value == expected {
        Finding::pass("ERC.INTERLOCK.INTERFACE_CONTRACT", "reviewed supply, leakage, timing and interface assumptions are unchanged", "contract")
    } else {
        Finding::fail("ERC.INTERLOCK.INTERFACE_CONTRACT", "contract differs from the reviewed electrical assumptions; update model and qualification deliberately", "contract")
    });
    report
        .checked_rules
        .push("ERC.INTERLOCK.INTERFACE_CONTRACT".into());
    CheckReport::from_findings(report.findings, report.checked_rules, report.coverage_gaps)
}

pub fn parse_and_run(source: &[u8], native: &[u8], contract: &[u8]) -> Result<CheckReport, String> {
    let source = std::str::from_utf8(source).map_err(|e| format!("source is not UTF-8: {e}"))?;
    let native = std::str::from_utf8(native).map_err(|e| format!("native is not UTF-8: {e}"))?;
    let contract =
        std::str::from_utf8(contract).map_err(|e| format!("contract is not UTF-8: {e}"))?;
    Ok(run_interlock(source, native, contract))
}
