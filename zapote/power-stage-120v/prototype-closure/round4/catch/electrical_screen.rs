//! Conditional catch-carrier calculations; no installed current limit or fuse claim.
use std::{collections::BTreeMap, env, error::Error, fs};

fn read_lengths(text: &str) -> Result<BTreeMap<String, f64>, Box<dyn Error>> {
    let mut rows = BTreeMap::new();
    for line in text.lines().skip(1) {
        let (name, value) = line.split_once(',').ok_or("Malformed route row")?;
        let length: f64 = value.parse()?;
        if !length.is_finite() || length <= 0.0 || rows.insert(name.to_owned(), length).is_some() {
            return Err("Invalid or duplicate route".into());
        }
    }
    if rows.keys().map(String::as_str).collect::<Vec<_>>()
        != ["BUS_P", "FUSED_P_TO_ANODE", "HV_RET"]
    {
        return Err("Incomplete route set".into());
    }
    Ok(rows)
}

fn discharge_seconds(voltage: f64, branches: f64, worst_case: bool) -> f64 {
    let (cap_factor, resistance_factor) = if worst_case { (1.10, 1.07) } else { (1.0, 1.0) };
    47e-6 * cap_factor * (400e3 * resistance_factor / branches) * (voltage / 30.0).ln()
}

fn worst_resistor_power(voltage: f64) -> f64 {
    // Initial5% plus2% temperature allocation; not an assumed matched divider.
    voltage.powi(2) * 107e3 / (107e3_f64 + 3.0 * 93e3).powi(2)
}

fn main() -> Result<(), Box<dyn Error>> {
    let path = env::args().nth(1).ok_or("Pass route-lengths.csv")?;
    let routes = read_lengths(&fs::read_to_string(path)?)?;
    let total_mm = routes.values().sum::<f64>();
    let wire_r20 = total_mm / 1000.0 * 1.75 / 304.8;
    let wire_r105 = wire_r20 * (1.0 + 0.00393 * 85.0);
    let hole_radial_clearance = (2.8 - 0.05 - 1.25) / 2.0;
    let two_axis_offset = 2.0_f64.sqrt() * (0.4 + 0.1);
    println!("{{\"status\":\"CONDITIONAL_CALCULATION_NOT_RATING\",\"wire_length_mm\":{total_mm:.9},\"wire_only_nominal_r20_ohm\":{wire_r20:.12},\"wire_only_temperature_screen_r105_ohm\":{wire_r105:.12},\"wire_energy_at_historical_0p155225_A2s_J\":{:.12},\"bleed_nominal_198V_W\":{:.9},\"bleed_nominal_350V_W\":{:.9},\"bleed_nominal_600V_W\":{:.9},\"worst_one_resistor_600V_W\":{:.9},\"worst_one_resistor_700V_W\":{:.9},\"P105_linear_derating_screen_W\":{:.9},\"one_branch_discharge350_to30_worst_s\":{:.9},\"one_branch_discharge600_to30_worst_s\":{:.9},\"pin_capture_radial_margin_mm\":{:.9},\"inductance_extracted\":false,\"loop_inductance_sensitivity_H\":[0.0000002,0.000001,0.000003]}}",
        0.155225 * wire_r105, 198.0_f64.powi(2)/200e3,
        350.0_f64.powi(2)/200e3,600.0_f64.powi(2)/200e3,
        worst_resistor_power(600.0),worst_resistor_power(700.0),
        0.5 * (155.0-105.0)/(155.0-70.0),discharge_seconds(350.0,1.0,true),
        discharge_seconds(600.0,1.0,true),hole_radial_clearance-two_axis_offset);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn one_failed_bleed_doubles_discharge_time() {
        assert!(
            (discharge_seconds(350.0, 1.0, false) / discharge_seconds(350.0, 2.0, false) - 2.0)
                .abs()
                < 1e-12
        );
    }
    #[test]
    fn asymmetric_resistor_tolerances_are_worse_than_matched_nominal() {
        assert!(worst_resistor_power(600.0) > 600.0_f64.powi(2) / (16.0 * 100e3));
    }
    #[test]
    fn full_capacitor_nameplate_is_not_continuous_bleed_rating_at105c() {
        assert!(worst_resistor_power(700.0) > 0.5 * (155.0 - 105.0) / (155.0 - 70.0));
    }
    #[test]
    fn incomplete_and_nonfinite_route_evidence_are_rejected() {
        assert!(read_lengths("name,mm\nBUS_P,300\nHV_RET,400\n").is_err());
        assert!(read_lengths("name,mm\nBUS_P,NaN\nFUSED_P_TO_ANODE,200\nHV_RET,400\n").is_err());
        assert!(
            read_lengths("name,mm\nBUS_P,300\nBUS_P,400\nFUSED_P_TO_ANODE,200\nHV_RET,400\n")
                .is_err()
        );
    }
}
