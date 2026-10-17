//! First-harmonic series-tank screen for proposed inverter return topologies.
//!
//! Run with `rustc -O plant_screen.rs -o /tmp/temper-plant-screen &&
//! /tmp/temper-plant-screen cases.csv`. This deliberately does not model
//! commutation, diode recovery, startup, faults, temperature, or ZVS.

use std::env;
use std::error::Error;
use std::f64::consts::{PI, SQRT_2};
use std::fs;

const HISTORICAL_IGBT_VCE_RATING_V: f64 = 1200.0;
const HISTORICAL_CAP_BANK_ESR_OHM: f64 = 0.004 / 3.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Topology {
    HalfBridgeHot0,
    HalfBridgeMidpoint,
    FullBridgeHot0,
}

impl Topology {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "half_hot0" => Ok(Self::HalfBridgeHot0),
            "half_midpoint" => Ok(Self::HalfBridgeMidpoint),
            "full_hot0" => Ok(Self::FullBridgeHot0),
            _ => Err(format!("unsupported topology: {value}")),
        }
    }

    fn fundamental_rms(self, bus_v: f64) -> f64 {
        let half_bridge = SQRT_2 * bus_v / PI;
        match self {
            Self::HalfBridgeHot0 | Self::HalfBridgeMidpoint => half_bridge,
            Self::FullBridgeHot0 => 2.0 * half_bridge,
        }
    }

    fn capacitor_dc_bias(self, bus_v: f64) -> f64 {
        match self {
            Self::HalfBridgeHot0 => bus_v / 2.0,
            Self::HalfBridgeMidpoint | Self::FullBridgeHot0 => 0.0,
        }
    }
}

#[derive(Debug)]
struct Case<'a> {
    id: &'a str,
    topology: Topology,
    bus_v: f64,
    loaded_l_uh: f64,
    coil_r_ohm: f64,
    reflected_pan_r_ohm: f64,
    tank_c_nf: f64,
    frequency_khz: f64,
    permit: bool,
    v15_ok: bool,
}

#[derive(Debug)]
struct Screen {
    fundamental_v_rms: f64,
    tank_i_rms: f64,
    tank_i_peak_sine: f64,
    phase_deg: f64,
    resonance_khz: f64,
    capacitor_ac_v_rms: f64,
    capacitor_dc_bias_v: f64,
    capacitor_abs_peak_v: f64,
    coil_loss_w: f64,
    pan_reflected_loss_w: f64,
    capacitor_esr_loss_w: f64,
    nominal_vce_headroom_v: f64,
}

fn positive(name: &str, value: f64) -> Result<(), String> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(format!("{name} must be positive and finite"))
    }
}

fn screen(case: &Case<'_>) -> Result<Option<Screen>, String> {
    positive("bus_v", case.bus_v)?;
    positive("loaded_l_uh", case.loaded_l_uh)?;
    positive("tank_c_nf", case.tank_c_nf)?;
    positive("frequency_khz", case.frequency_khz)?;
    for (name, value) in [
        ("coil_r_ohm", case.coil_r_ohm),
        ("reflected_pan_r_ohm", case.reflected_pan_r_ohm),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(format!("{name} must be nonnegative and finite"));
        }
    }
    if case.bus_v >= HISTORICAL_IGBT_VCE_RATING_V {
        return Err("bus alone reaches or exceeds historical IGBT VCE rating".into());
    }
    if !case.permit || !case.v15_ok {
        return Ok(None);
    }

    let l_h = case.loaded_l_uh * 1e-6;
    let c_f = case.tank_c_nf * 1e-9;
    let omega = 2.0 * PI * case.frequency_khz * 1e3;
    let reactance = omega * l_h - 1.0 / (omega * c_f);
    let resistance = case.coil_r_ohm + case.reflected_pan_r_ohm + HISTORICAL_CAP_BANK_ESR_OHM;
    positive("series resistance", resistance)?;
    let fundamental_v_rms = case.topology.fundamental_rms(case.bus_v);
    let tank_i_rms = fundamental_v_rms / resistance.hypot(reactance);
    let capacitor_ac_v_rms = tank_i_rms / (omega * c_f);
    let capacitor_dc_bias_v = case.topology.capacitor_dc_bias(case.bus_v);

    Ok(Some(Screen {
        fundamental_v_rms,
        tank_i_rms,
        tank_i_peak_sine: SQRT_2 * tank_i_rms,
        phase_deg: reactance.atan2(resistance).to_degrees(),
        resonance_khz: 1.0 / (2.0 * PI * (l_h * c_f).sqrt()) / 1e3,
        capacitor_ac_v_rms,
        capacitor_dc_bias_v,
        capacitor_abs_peak_v: capacitor_dc_bias_v + SQRT_2 * capacitor_ac_v_rms,
        coil_loss_w: tank_i_rms.powi(2) * case.coil_r_ohm,
        pan_reflected_loss_w: tank_i_rms.powi(2) * case.reflected_pan_r_ohm,
        capacitor_esr_loss_w: tank_i_rms.powi(2) * HISTORICAL_CAP_BANK_ESR_OHM,
        nominal_vce_headroom_v: HISTORICAL_IGBT_VCE_RATING_V - case.bus_v,
    }))
}

fn parse_case(line: &str) -> Result<Case<'_>, String> {
    let fields: Vec<_> = line.split(',').map(str::trim).collect();
    if fields.len() != 10 {
        return Err(format!("expected 10 CSV columns, got {}", fields.len()));
    }
    let parse_number = |index: usize| -> Result<f64, String> {
        fields[index]
            .parse::<f64>()
            .map_err(|_| format!("invalid number in column {}", index + 1))
    };
    let parse_bool = |index: usize| -> Result<bool, String> {
        match fields[index] {
            "yes" => Ok(true),
            "no" => Ok(false),
            _ => Err(format!("column {} must be yes or no", index + 1)),
        }
    };
    Ok(Case {
        id: fields[0],
        topology: Topology::parse(fields[1])?,
        bus_v: parse_number(2)?,
        loaded_l_uh: parse_number(3)?,
        coil_r_ohm: parse_number(4)?,
        reflected_pan_r_ohm: parse_number(5)?,
        tank_c_nf: parse_number(6)?,
        frequency_khz: parse_number(7)?,
        permit: parse_bool(8)?,
        v15_ok: parse_bool(9)?,
    })
}

fn run(input: &str) -> Result<(), String> {
    println!("id,status,v1_rms_v,tank_i_rms_a,tank_i_peak_sine_a,phase_deg,f_res_khz,cap_ac_rms_v,cap_dc_bias_v,cap_abs_peak_v,coil_loss_w,pan_reflected_loss_w,cap_esr_loss_w,nominal_vce_headroom_v");
    for (line_number, line) in input.lines().enumerate() {
        if line.trim().is_empty() || line.starts_with('#') || line.starts_with("id,") {
            continue;
        }
        let case =
            parse_case(line).map_err(|error| format!("line {}: {error}", line_number + 1))?;
        match screen(&case) {
            Ok(Some(value)) => println!(
                "{},SCREEN_ONLY,{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2},{:.2}",
                case.id,
                value.fundamental_v_rms,
                value.tank_i_rms,
                value.tank_i_peak_sine,
                value.phase_deg,
                value.resonance_khz,
                value.capacitor_ac_v_rms,
                value.capacitor_dc_bias_v,
                value.capacitor_abs_peak_v,
                value.coil_loss_w,
                value.pan_reflected_loss_w,
                value.capacitor_esr_loss_w,
                value.nominal_vce_headroom_v
            ),
            Ok(None) => println!("{},INHIBITED,,,,,,,,,,,,", case.id),
            Err(error) => println!("{},REJECT:{},,,,,,,,,,,,", case.id, error.replace(',', ";")),
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args();
    let _program = args.next();
    let path = args.next().ok_or("usage: plant_screen <cases.csv>")?;
    if args.next().is_some() {
        return Err("usage: plant_screen <cases.csv>".into());
    }
    let input = fs::read_to_string(path)?;
    run(&input)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const REFERENCE: &str = "reference,half_hot0,390,59.84,0.34,2.91,300,47,yes,yes";

    #[test]
    fn direct_return_and_midpoint_have_same_ideal_ac_but_different_dc_bias() {
        let direct = screen(&parse_case(REFERENCE).unwrap()).unwrap().unwrap();
        let midpoint = screen(
            &parse_case("midpoint,half_midpoint,390,59.84,0.34,2.91,300,47,yes,yes").unwrap(),
        )
        .unwrap()
        .unwrap();
        assert!((direct.tank_i_rms - midpoint.tank_i_rms).abs() < 1e-12);
        assert_eq!(direct.capacitor_dc_bias_v, 195.0);
        assert_eq!(midpoint.capacitor_dc_bias_v, 0.0);
    }

    #[test]
    fn full_bridge_doubles_fundamental_current_for_same_tank() {
        let half = screen(&parse_case(REFERENCE).unwrap()).unwrap().unwrap();
        let full =
            screen(&parse_case("full,full_hot0,390,59.84,0.34,2.91,300,47,yes,yes").unwrap())
                .unwrap()
                .unwrap();
        assert!((full.tank_i_rms / half.tank_i_rms - 2.0).abs() < 1e-12);
    }

    #[test]
    fn nonphysical_inductance_is_rejected() {
        let case = parse_case("bad,half_hot0,390,0,0.34,2.91,300,47,yes,yes").unwrap();
        assert!(screen(&case).is_err());
    }

    #[test]
    fn bus_above_device_rating_is_rejected() {
        let case = parse_case("bad,half_hot0,1200,59.84,0.34,2.91,300,47,yes,yes").unwrap();
        assert!(screen(&case).is_err());
    }

    #[test]
    fn lost_gate_supply_has_no_steady_switching_solution() {
        let case = parse_case("loss,half_hot0,390,59.84,0.34,2.91,300,47,yes,no").unwrap();
        assert!(screen(&case).unwrap().is_none());
    }
}
