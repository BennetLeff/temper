//! First-harmonic *rejection* matrix for the provisional paired coil/pan rows.
//! No row is an operating permission or a thermal / switching rating.
use std::env;
use std::f64::consts::{PI, SQRT_2};
use std::fs;

const INPUT_HEADER: &str =
    "id,topology,bus_v,loaded_l_uh,coil_r_ohm,reflected_pan_r_ohm,tank_c_nf,frequency_khz,permit,v15_ok";
const OUTPUT_HEADER: &str = "id,bus_v,c_nf,f_khz,f_res_khz,phase_deg,i1_rms_a,i1_sine_peak_a,cap_ac_rms_v,cap_abs_sine_peak_v,ideal_equal_share_a,ocp_45a_overlap,cap_9p5a_proxy_overlap";
// These are comparison markers, not validated continuous-current limits:
// current-sense's stated 45-55 A peak trip band, and a historical 47 kHz
// interpolation of CDE 942C's 70 C / 100 kHz table (see report).
const OCP_BAND_LOW_A: f64 = 45.0;
const HISTORICAL_CAP_47KHZ_PROXY_A: f64 = 9.5;
const CAP_COUNT: f64 = 3.0;
const HISTORICAL_BANK_ESR_OHM: f64 = 0.004 / CAP_COUNT;

#[derive(Clone, Debug)]
struct Pan {
    id: String,
    l_h: f64,
    r_ohm: f64,
}

fn parse_pans(input: &str) -> Result<Vec<Pan>, String> {
    let mut rows = input
        .lines()
        .filter(|line| !line.is_empty() && !line.starts_with('#'));
    if rows.next() != Some(INPUT_HEADER) {
        return Err("wrong provisional pan CSV header".into());
    }
    let mut pans = Vec::new();
    for (offset, line) in rows.enumerate() {
        let fields: Vec<_> = line.split(',').map(str::trim).collect();
        if fields.len() != 10
            || fields[1] != "half_hot0"
            || fields[8] != "yes"
            || fields[9] != "yes"
        {
            return Err(format!(
                "line {}: unexpected pan row shape or state",
                offset + 2
            ));
        }
        let number = |i: usize| {
            fields[i]
                .parse::<f64>()
                .map_err(|_| format!("line {}: invalid number", offset + 2))
        };
        let bus = number(2)?;
        let l = number(3)?;
        let coil_r = number(4)?;
        let pan_r = number(5)?;
        let c = number(6)?;
        let f = number(7)?;
        if fields[0].is_empty()
            || fields[0].contains(',')
            || [bus, l, coil_r, pan_r, c, f].iter().any(|x| !x.is_finite())
            || bus <= 0.0
            || l <= 0.0
            || coil_r < 0.0
            || pan_r < 0.0
            || c <= 0.0
            || f <= 0.0
        {
            return Err(format!("line {}: nonphysical pan row", offset + 2));
        }
        pans.push(Pan {
            id: fields[0].to_owned(),
            l_h: l * 1e-6,
            r_ohm: coil_r + pan_r,
        });
    }
    if pans.len() != 8 {
        return Err(format!(
            "expected 8 paired pan scenarios, found {}",
            pans.len()
        ));
    }
    Ok(pans)
}

#[derive(Clone, Copy, Debug)]
struct ResultPoint {
    resonance_khz: f64,
    phase_deg: f64,
    current_rms_a: f64,
    current_sine_peak_a: f64,
    capacitor_ac_rms_v: f64,
    capacitor_abs_sine_peak_v: f64,
    ideal_equal_share_a: f64,
}

fn point(pan: &Pan, bus_v: f64, c_nf: f64, f_khz: f64) -> ResultPoint {
    let c = c_nf * 1e-9;
    let omega = 2.0 * PI * f_khz * 1e3;
    let x = omega * pan.l_h - 1.0 / (omega * c);
    let r = pan.r_ohm + HISTORICAL_BANK_ESR_OHM;
    let current = (SQRT_2 * bus_v / PI) / r.hypot(x);
    let cap_ac = current / (omega * c);
    ResultPoint {
        resonance_khz: 1.0 / (2.0 * PI * (pan.l_h * c).sqrt()) / 1e3,
        phase_deg: x.atan2(r).to_degrees(),
        current_rms_a: current,
        current_sine_peak_a: SQRT_2 * current,
        capacitor_ac_rms_v: cap_ac,
        capacitor_abs_sine_peak_v: bus_v / 2.0 + SQRT_2 * cap_ac,
        ideal_equal_share_a: current / CAP_COUNT,
    }
}

fn output(pans: &[Pan]) -> String {
    let mut out = format!("{OUTPUT_HEADER}\n");
    // 390 V is nominal intent, not accepted maximum. 330 V is a sag probe.
    for bus in [390.0, 330.0] {
        for c in [270.0, 300.0, 330.0] {
            for f in [44.0, 47.0, 50.0] {
                for pan in pans {
                    let p = point(pan, bus, c, f);
                    let ocp = if p.current_sine_peak_a >= OCP_BAND_LOW_A {
                        "YES"
                    } else {
                        "NO"
                    };
                    let cap = if p.ideal_equal_share_a >= HISTORICAL_CAP_47KHZ_PROXY_A {
                        "YES"
                    } else {
                        "NO"
                    };
                    out.push_str(&format!("{},{bus:.0},{c:.0},{f:.0},{:.3},{:.3},{:.3},{:.3},{:.3},{:.3},{:.3},{ocp},{cap}\n",
                        pan.id, p.resonance_khz, p.phase_deg, p.current_rms_a,
                        p.current_sine_peak_a, p.capacitor_ac_rms_v,
                        p.capacitor_abs_sine_peak_v, p.ideal_equal_share_a));
                }
            }
        }
    }
    out
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args();
    let _program = args.next();
    let path = args
        .next()
        .ok_or("usage: candidate_matrix <provisional-pan-cases.csv>")?;
    if args.next().is_some() {
        return Err("usage: candidate_matrix <provisional-pan-cases.csv>".into());
    }
    let input = fs::read_to_string(path)?;
    print!("{}", output(&parse_pans(&input)?));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = concat!(
        "id,topology,bus_v,loaded_l_uh,coil_r_ohm,reflected_pan_r_ohm,tank_c_nf,frequency_khz,permit,v15_ok\n",
        "kit_reference_vessel,half_hot0,390,60,0.34,2.91,300,47,yes,yes\n");

    #[test]
    fn reference_matches_independent_plant_screen_to_display_precision() {
        let pan = parse_one(FIXTURE);
        let p = point(&pan, 390.0, 300.0, 47.0);
        assert!((p.current_rms_a - 24.36).abs() < 0.02);
    }

    fn parse_one(input: &str) -> Pan {
        let mut repeated = input.lines().next().unwrap().to_owned();
        repeated.push('\n');
        for _ in 0..8 {
            repeated.push_str(input.lines().nth(1).unwrap());
            repeated.push('\n');
        }
        parse_pans(&repeated).unwrap().remove(0)
    }

    #[test]
    fn phase_changes_sign_across_resonance() {
        let pan = parse_one(FIXTURE);
        assert!(point(&pan, 390.0, 300.0, 30.0).phase_deg < 0.0);
        assert!(point(&pan, 390.0, 300.0, 47.0).phase_deg > 0.0);
    }

    #[test]
    fn sag_reduces_current_only_at_fixed_impedance() {
        let pan = parse_one(FIXTURE);
        let high = point(&pan, 390.0, 300.0, 47.0).current_rms_a;
        let low = point(&pan, 330.0, 300.0, 47.0).current_rms_a;
        assert!((low / high - 330.0 / 390.0).abs() < 1e-12);
    }

    #[test]
    fn rejects_wrong_topology_and_nonphysical_row() {
        assert!(parse_pans(&FIXTURE.replace("half_hot0", "full_hot0")).is_err());
        assert!(parse_pans(&FIXTURE.replace(",60,", ",-60,")).is_err());
    }
}
