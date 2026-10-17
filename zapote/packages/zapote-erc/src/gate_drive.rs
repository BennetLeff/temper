//! Structural checks for the compiled UCC21550 gate-drive candidate.
//!
//! This module deliberately stops at source/native graph correctness and
//! bounded timing equations. Gate voltage, bootstrap charge, isolation, EMI,
//! and switching qualification remain physical test evidence.

use crate::power_stage_models::{dead_time_corners, ModelError};
use crate::source_circuit::Circuit;

pub const ENTRY: &str = "elec/src/gate_drive_unit.ato:GateDriveUnit";
const AO3400A_RDS_MAX_AT_2V5_OHM: f64 = 0.048;
// Explicit bounded characterization envelope, not an AOS datasheet guarantee.
const AO3400A_HOT_RDS_BOUND_OHM: f64 = 2.0 * AO3400A_RDS_MAX_AT_2V5_OHM;
const AO3400A_GATE_LEAK_BOUND_A: f64 = 100e-9;

fn component<'a>(c: &'a Circuit, id: &str) -> Result<&'a crate::source_circuit::Component, String> {
    c.components
        .get(id)
        .ok_or_else(|| format!("missing component {id}"))
}

fn resistance(value: Option<&str>) -> Option<f64> {
    let token = value?.split_whitespace().next()?;
    let (number, multiplier) = if let Some(v) = token.strip_suffix("kohm") {
        (v, 1_000.0)
    } else if let Some(v) = token.strip_suffix("ohm") {
        (v, 1.0)
    } else {
        return None;
    };
    number.parse::<f64>().ok().map(|v| v * multiplier)
}

fn exact_resistor(c: &Circuit, id: &str, nominal: f64, mpn: &str) -> Result<(), String> {
    let part = component(c, id)?;
    if part.mpn != mpn {
        return Err(format!("{id} MPN {} != {mpn}", part.mpn));
    }
    let actual = resistance(part.value.as_deref())
        .ok_or_else(|| format!("{id} has no parseable resistance value"))?;
    if (actual - nominal).abs() > nominal * 0.001 {
        return Err(format!("{id} is {actual} ohm, expected {nominal} ohm"));
    }
    Ok(())
}

fn model_error(e: ModelError) -> String {
    format!("dead-time model rejected corners: {e:?}")
}

/// Validate the candidate source graph against its compiled native export.
/// `native` is intentionally a required caller-supplied artifact; this
/// function never substitutes a runtime donor or silently trusts source-only
/// connectivity.
pub fn validate_source(source: &str) -> Result<(), String> {
    let circuit = Circuit::parse(source, ENTRY)?;
    check_source(&circuit)
}

pub fn validate(source: &str, native: &str) -> Result<(), String> {
    let circuit = Circuit::parse(source, ENTRY)?;
    circuit.bind_native(native)?;
    check_source(&circuit)
}

fn check_source(circuit: &Circuit) -> Result<(), String> {
    let expected = [
        ("driver", "UCC21550BDWKR"),
        ("permit_sw", "AO3400A"),
        ("host", "B4B-XH-A(LF)(SN)"),
        ("supply", "61300211121"),
        ("gate_h", "61300211121"),
        ("gate_l", "61300211121"),
        ("vcc_3v3", "61300211121"),
        ("d_boot", "UF4007-E3/54"),
        ("c_vcci", "C0603C104K5RACTU"),
        ("c_ls", "C0603C104K5RACTU"),
        ("c_ls_bulk", "GRM32ER71H106KA12L"),
        ("c_boot", "GRM32ER71H106KA12L"),
        ("r_permit_series", "RC0603FR-071KL"),
        ("r_permit_pd", "RC0603FR-07100KL"),
        ("r_dis_pu", "RC0603FR-0710KL"),
        ("dt", "RC0603FR-0739KL"),
        ("rg_h", "RC1206FR-073R9L"),
        ("rg_l", "RC1206FR-073R9L"),
        ("rgs_h", "RC0603FR-072K2L"),
        ("rgs_l", "RC0603FR-072K2L"),
    ];
    if circuit.components.len() != expected.len() {
        return Err("gate-drive component census changed".into());
    }
    for (id, mpn) in expected {
        if component(circuit, id)?.mpn != mpn {
            return Err(format!("unreviewed exact part at {id}; expected {mpn}"));
        }
    }
    for (id, value) in [
        ("c_vcci", "100nF +/- 10%"),
        ("c_ls", "100nF +/- 10%"),
        ("c_ls_bulk", "10uF +/- 20%"),
        ("c_boot", "10uF +/- 20%"),
    ] {
        if component(circuit, id)?.value.as_deref() != Some(value) {
            return Err(format!("unreviewed capacitor value at {id}"));
        }
    }
    for id in ["rg_h", "rg_l"] {
        exact_resistor(circuit, id, 3.9, "RC1206FR-073R9L")?;
    }
    for id in ["rgs_h", "rgs_l"] {
        exact_resistor(circuit, id, 2_200.0, "RC0603FR-072K2L")?;
    }
    // One representative of EVERY intended net, including the unused pin.
    // Pairwise distinction prevents a source and PCB agreeing on a new short.
    circuit.require_distinct(&[
        "driver.1",
        "driver.2",
        "host.3",
        "driver.3",
        "driver.4",
        "driver.5",
        "driver.6",
        "driver.7",
        "permit_sw.1",
        "driver.9",
        "driver.10",
        "driver.11",
        "driver.14",
        "driver.15",
        "driver.16",
        "gate_h.1",
        "gate_l.1",
    ])?;
    let driver = component(&circuit, "driver")?;
    if driver.mpn != "UCC21550BDWKR" {
        return Err(format!("driver MPN {} is not UCC21550BDWKR", driver.mpn));
    }
    let switch = component(&circuit, "permit_sw")?;
    if switch.mpn != "AO3400A" {
        return Err(format!("permit switch MPN {} is not AO3400A", switch.mpn));
    }
    exact_resistor(&circuit, "r_permit_series", 1_000.0, "RC0603FR-071KL")?;
    exact_resistor(&circuit, "r_permit_pd", 100_000.0, "RC0603FR-07100KL")?;
    exact_resistor(&circuit, "r_dis_pu", 10_000.0, "RC0603FR-0710KL")?;
    exact_resistor(&circuit, "dt", 39_000.0, "RC0603FR-0739KL")?;

    // TI UCC21550 DW pin map: INA=1, INB=2, VCCI=3/8, GND=4,
    // DIS=5, DT=6, NC=7, VDDA=16, OUTA=15, VSSA=14,
    // VDDB=11, OUTB=10, VSSB=9. (TI datasheet Rev C, p. 4.)
    circuit.require_net(&["driver.1", "host.1"])?;
    circuit.require_net(&["driver.2", "host.2"])?;
    circuit.require_net(&["driver.4", "host.4"])?;
    circuit.require_distinct(&["driver.1", "driver.2"])?;
    circuit.require_net(&["driver.3", "driver.8", "c_vcci.1", "vcc_3v3.1"])?;
    circuit.require_net(&["driver.4", "vcc_3v3.2", "c_vcci.2"])?;
    circuit.require_net(&["driver.16", "d_boot.1", "c_boot.1"])?;
    circuit.require_net(&["driver.14", "c_boot.2", "gate_h.2"])?;
    circuit.require_net(&["driver.11", "d_boot.2", "c_ls.1", "c_ls_bulk.1"])?;
    circuit.require_net(&["driver.11", "supply.1"])?;
    circuit.require_net(&["driver.9", "c_ls.2", "c_ls_bulk.2", "gate_l.2"])?;
    circuit.require_net(&["driver.9", "supply.2"])?;
    circuit.require_net(&["driver.15", "rg_h.1"])?;
    circuit.require_net(&["driver.10", "rg_l.1"])?;
    circuit.require_distinct(&["driver.16", "driver.14", "driver.11", "driver.9"])?;
    circuit.require_net(&["d_boot.1", "c_boot.1"])?;
    circuit.require_net(&["d_boot.2", "c_ls.1"])?;
    circuit.require_distinct(&["d_boot.1", "d_boot.2"])?;

    // Gate and Kelvin returns must be separate at the driver pins. Each gate
    // has a series resistor and a dedicated 2.2-k pulldown to its Kelvin node.
    circuit.require_net(&["rg_h.2", "rgs_h.1", "gate_h.1"])?;
    circuit.require_net(&["rg_l.2", "rgs_l.1", "gate_l.1"])?;
    circuit.require_distinct(&["gate_h.1", "gate_h.2", "gate_l.1", "gate_l.2"])?;
    circuit.require_net(&["rgs_h.2", "driver.14"])?;
    circuit.require_net(&["rgs_l.2", "driver.9"])?;
    circuit.require_net(&["driver.6", "dt.1"])?;
    circuit.require_net(&["dt.2", "driver.4"])?;
    circuit.require_distinct(&["driver.4", "driver.14", "driver.9"])?;

    // Permit must be an inverting transistor stage: 1-k series into AO3400A
    // gate, 100-k gate pulldown, and 10-k DIS pullup. This means a missing or
    // low permit cannot leave DIS floating or falsely enable the driver.
    circuit.require_net(&["r_permit_series.1", "host.3"])?;
    circuit.require_net(&["r_permit_series.2", "permit_sw.1", "r_permit_pd.1"])?;
    circuit.require_net(&["permit_sw.2", "driver.4", "r_permit_pd.2"])?;
    circuit.require_net(&["permit_sw.3", "driver.5", "r_dis_pu.1"])?;
    circuit.require_net(&["r_dis_pu.2", "driver.3"])?;

    // A 2.7-V high input through 1 k drives a valid >2.5-V gate even with a
    // bounded 100-k pulldown; the 10-k pullup then holds DIS <= 0.8 V when Q1
    // is on. These are DC structural bounds, not transistor transfer curves.
    let r_series_max = 1_000.0 * 1.01;
    let r_pd_min = 100_000.0 * 0.95;
    let gate_high =
        2.7 * r_pd_min / (r_series_max + r_pd_min) - AO3400A_GATE_LEAK_BOUND_A * r_pd_min;
    let dis_low = 3.3 * AO3400A_HOT_RDS_BOUND_OHM / (10_000.0 * 0.95 + AO3400A_HOT_RDS_BOUND_OHM);
    if gate_high <= 2.5 || dis_low > 0.8 {
        return Err(format!(
            "permit DC bounds fail: gate={gate_high:.3} V DIS={dis_low:.3} V"
        ));
    }

    validate_model()?;
    Ok(())
}

/// Run the timing model independently of any source/native artifact.
pub fn validate_model() -> Result<(), String> {
    let dt = dead_time_report()?;
    if dt.min_ns < 300.0 {
        return Err(format!(
            "DT envelope is {:.1}..{:.1} ns",
            dt.min_ns, dt.max_ns
        ));
    }
    Ok(())
}

/// Return the assumed DT characterization envelope; callers must treat the
/// upper value as a report, not as a datasheet maximum guarantee.
pub fn dead_time_report() -> Result<crate::power_stage_models::DeadTimeSummary, String> {
    dead_time_corners(39.0, 0.01, 100.0, &[-40.0, 25.0, 125.0], (0.9, 1.1)).map_err(model_error)
}
