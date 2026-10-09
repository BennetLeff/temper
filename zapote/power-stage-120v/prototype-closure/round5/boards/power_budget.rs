//! Source-table power screen. Manufacturer maxima and engineering reserves stay separate.
use std::{collections::BTreeMap, error::Error, fs, path::Path};

fn resistance(value: &str) -> Option<f64> {
    let token = value.split_whitespace().next()?;
    let raw = token.strip_suffix('R')?;
    let (digits, scale) = if let Some(n) = raw.strip_suffix('k') { (n, 1000.0) }
        else if let Some(n) = raw.strip_suffix('M') { (n, 1e6) } else { (raw, 1.0) };
    Some(digits.parse::<f64>().ok()? * scale)
}
fn audit(pins: &str) -> Result<(f64, f64, usize), Box<dyn Error>> {
    let rows: Vec<Vec<&str>> = pins.lines().skip(1).map(|l| l.split('\t').collect()).collect();
    let net = |r: &str, p: &str| rows.iter().find(|x| x[8] == r && x[4] == p).map(|x| x[7]);
    for (r, p, n) in [("R_BUCK_PRELOAD","1","REG3_5V"),("R_BUCK_PRELOAD","2","AUX_0V"),("REG3","1","AUX_24V"),("REG3","2","AUX_0V"),("REG3","3","REG3_5V"),("U_POSTREG","15","REG3_5V"),("U_POSTREG","16","REG3_5V"),("U_POSTREG","1","POD_3V3"),("U_POSTREG","3","POD_3V3"),("U_POSTREG","8","AUX_0V"),("U_POSTREG","11","AUX_0V"),("U_POSTREG","12","AUX_0V"),
        ("U_MCU","36","ADC_MCO_SOURCE"),("R_ADC_MCO","1","ADC_MCO_SOURCE"),("R_ADC_MCO","2","ADC_CLKIN"),
        ("R_HB_FAIL_LOW","1","CTRL_HEARTBEAT_OK"),("R_HB_FAIL_LOW","2","AUX_0V"),
        ("NT_COIL_STAR","1","COIL_RET"),("NT_COIL_STAR","2","AUX_0V")] {
        if net(r,p) != Some(n) { return Err(format!("power ECO mismatch {r}.{p}, expected {n}").into()); }
    }
    for name in ["KB_DRIVE","KT_DRIVE","KPA_DRIVE","KPB_DRIVE"] {
        let reference=format!("R_BUF_PD_{name}");
        if net(&reference,"1")!=Some(name)||net(&reference,"2")!=Some("AUX_0V") {
            return Err(format!("missing fail-low buffer bias {name}").into());
        }
    }
    for r in ["Q_K1","Q_K2","Q_KB","Q_KT","Q_KPA","Q_KPB"] {
        if net(r,"3") != Some("COIL_RET") { return Err(format!("{r} bypasses coil-return star").into()); }
    }
    if rows.iter().any(|r|r[1]=="LD1117S33TR") { return Err("obsolete linear regulator remains".into()); }
    let mut parts = BTreeMap::new();
    for r in &rows { parts.entry(r[0]).or_insert(r); }
    // Charge every >=300 ohm central resistor with the full 3.6 V and -1% resistance,
    // even series/divider/5V-only parts. This deliberately overbounds the DC resistor load.
    let passive_ma: f64 = parts.values().filter(|r|r[0].starts_with('R')).filter_map(|r|resistance(r[1]))
        .filter(|r|*r >= 300.0).map(|r|3600.0 / (r * 0.99)).sum();
    let logic = parts.values().filter(|r|r[1].starts_with("SN74LVC")).count();
    // Sum direct rail capacitors only; 20% positive tolerance bounds startup charge.
    let mut capacitance_uf = 0.0;
    for (reference, r) in &parts {
        if !reference.starts_with('C') || !rows.iter().any(|x|x[0]==*reference && x[7]=="POD_3V3") { continue; }
        let first = r[1].split_whitespace().next().ok_or("missing capacitor value")?;
        capacitance_uf += if let Some(v)=first.strip_suffix("uF") {v.parse::<f64>()?}
            else if let Some(v)=first.strip_suffix("nF") {v.parse::<f64>()? / 1000.0} else {return Err(format!("unknown capacitor {first}").into());};
    }
    // Each of six remote boards has 1uF + 0.1uF on the low side.
    capacitance_uf += 6.0 * 1.1;
    Ok((passive_ma, capacitance_uf * 1.2, logic))
}
fn main() -> Result<(), Box<dyn Error>> {
    let base = Path::new(file!()).parent().ok_or("missing source directory")?;
    let pins = fs::read_to_string(base.join("central/generated/pins.tsv"))?;
    let (passive, cap, logic) = audit(&pins)?;
    let maxima = 6.0*41.0 + 8.6 + 7.7 + 4.0*0.8 + 16.0*0.065 + 5.0*1.0 + 9.0*5.6 + logic as f64*0.010 + 3.0*0.2 + passive + 6.0*0.364;
    // These are design allocations, not falsely labelled manufacturer guaranteed maxima.
    let mode_reserve = 32.3 + 2.4 + 20.0 + 2.4 + 0.1; // MCU peripherals, ADC SPI, CMOS AC/leakage, timer active, supervisor allocation
    let steady = maxima + mode_reserve;
    let startup_ma = cap * 3.6 / 1.0; // 1ms linear-ramp sensitivity; not a promised start-up waveform
    assert!(steady < 1000.0); // 1ms is a sensitivity, not a guaranteed startup waveform.
    assert!(cap < 470.0);
    // PR03 39ohm1%: include250ppm/K*100K and5%+0.1ohm endurance allocation.
    let preload_min_ma = 4603.75 / (39.0*1.085+0.1);
    let preload_max_ma = 5396.25 / (39.0*0.915-0.1);
    let preload_max_w = 5.39625*preload_max_ma/1000.0;
    let buck_steady_ma = steady + 10.0 + preload_max_ma;
    assert!(preload_min_ma >= 100.0 && buck_steady_ma < 1000.0 && preload_max_w < 2.0);
    println!("{{\"status\":\"DESIGN_SCREEN_NOT_MEASURED\",\"manufacturer_and_passive_maxima_ma\":{maxima:.3},\"explicit_mode_reserves_ma\":{mode_reserve:.3},\"steady_design_ceiling_ma\":{steady:.3},\"passive_overbound_ma\":{passive:.3},\"logic_count\":{logic},\"output_capacitance_plus20pct_uf\":{cap:.3},\"one_ms_charge_sensitivity_ma\":{startup_ma:.3},\"one_ms_total_ma\":{:.3},\"regulator_rating_ma\":1000,\"buck_preload_min_ma\":{preload_min_ma:.3},\"buck_preload_max_ma\":{preload_max_ma:.3},\"buck_preload_max_w\":{preload_max_w:.3},\"ldo_ground_allocation_ma\":10,\"buck_steady_ceiling_ma\":{buck_steady_ma:.3},\"supplier_mode_reserves_require_validation\":true}}",steady+startup_ma);
    Ok(())
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn actual_board_satisfies_power_eco() { assert!(audit(include_str!("central/generated/pins.tsv")).is_ok()); }
    #[test] fn rejects_wrong_postreg_voltage() { assert!(audit(&include_str!("central/generated/pins.tsv").replace("11\t0P2V\tinput\tAUX_0V\tU_POSTREG", "11\t0P2V\tinput\tNC\tU_POSTREG")).is_err()); }
    #[test] fn rejects_old_clock_bypass() { assert!(audit(&include_str!("central/generated/pins.tsv").replace("ADC_MCO_SOURCE\tU_MCU", "ADC_CLKIN\tU_MCU")).is_err()); }
    #[test] fn rejects_coil_return_bypass() { assert!(audit(&include_str!("central/generated/pins.tsv").replace("COIL_RET\tQ_K1", "AUX_0V\tQ_K1")).is_err()); }
    #[test] fn rejects_missing_receiver_bias() { assert!(audit(&include_str!("central/generated/pins.tsv").lines().filter(|s|!s.ends_with("R_HB_FAIL_LOW")).collect::<Vec<_>>().join("\n")).is_err()); }
}
