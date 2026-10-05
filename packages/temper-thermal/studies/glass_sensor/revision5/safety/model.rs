//! R5 engineering screens, not a qualified safety detector.
use std::{
    error::Error,
    f64::consts::PI,
    fs::{self, File},
    io::{BufWriter, Write},
    path::Path,
};
const P0: f64 = 101_325.0;
const T0: f64 = 298.15;
const AREA: f64 = PI * 0.008 * 0.008 / 4.0;
const PRESSURE_BUDGET: f64 = 0.003;
fn resistance(diameter: f64, length: f64, viscosity: f64) -> f64 {
    128.0 * viscosity * length / (PI * diameter.powi(4))
}
fn sealed_pressure(
    hot_volume: f64,
    cold_volume: f64,
    hot_temp: f64,
    cold_temp: f64,
    swept_volume: f64,
) -> f64 {
    P0 * ((hot_volume + cold_volume) / T0)
        / ((hot_volume - swept_volume) / hot_temp + cold_volume / cold_temp)
        - P0
}
fn vent_pressure(source: f64, resistance: f64, volume: f64, seconds: f64) -> f64 {
    source * resistance * (1.0 - (-seconds / (resistance * volume / P0)).exp())
}
fn challenge(samples: [f64; 3], encoder_stroke_mm: f64) -> bool {
    encoder_stroke_mm >= 0.4
        && samples[0] >= 25.0
        && samples[0] < 220.0
        && samples[1].abs() <= 21.25
        && samples[2] >= 25.0
        && samples[2] < 220.0
}
fn pulse(g: f64, c: f64, watts: f64, seconds: f64) -> f64 {
    watts / g * (1.0 - (-g * seconds / c).exp())
}
fn output(dir: &Path, name: &str) -> Result<BufWriter<File>, std::io::Error> {
    Ok(BufWriter::new(File::create(dir.join(name))?))
}
fn main() -> Result<(), Box<dyn Error>> {
    let arg = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "results".to_string());
    let dir = Path::new(&arg);
    fs::create_dir_all(dir)?;
    let mut vent = output(dir, "vent_screen.csv")?;
    writeln!(vent,"tube_id_mm,tube_length_mm,heat_rate_K_s,motion_speed_mm_s,restriction_multiplier,flow_ml_s,pressure_Pa,force_mN,tau_s,within_3mN")?;
    for d in [0.5_f64, 1.0, 1.5, 2.0] {
        for rate in [0.0, 1.0, 10.0] {
            for speed in [0.0, 1.0, 20.0] {
                for blockage in [1.0, 10.0, 100.0] {
                    let r = resistance(d * 1e-3, 0.1, 3e-5) * blockage;
                    // Assumed hot gas volume1mL; bulk T=298K maximizes initial expansion source.
                    let q = 1e-6 / T0 * rate + AREA * speed * 1e-3;
                    let dp = q * r;
                    let force = dp * AREA;
                    writeln!(
                        vent,
                        "{d},100,{rate},{speed},{blockage},{:.9},{dp:.9},{:.9},{:.9},{}",
                        q * 1e6,
                        force * 1000.0,
                        r * 11e-6 / P0,
                        force <= PRESSURE_BUDGET
                    )?;
                }
            }
        }
    }
    vent.flush()?;
    let mut blocked = output(dir, "sealed_screen.csv")?;
    writeln!(
        blocked,
        "cold_volume_ml,hot_temp_C,cold_temp_C,stroke_mm,pressure_Pa,force_mN,within_3mN"
    )?;
    for vc in [0.0, 10.0, 100.0] {
        for hot in [25.0, 100.0, 250.0] {
            for cold in [25.0, 60.0] {
                for stroke in [0.0, 0.25, 1.2] {
                    let p = sealed_pressure(
                        1e-6,
                        vc * 1e-6,
                        hot + 273.15,
                        cold + 273.15,
                        AREA * stroke * 1e-3,
                    );
                    writeln!(
                        blocked,
                        "{vc},{hot},{cold},{stroke},{p:.9},{:.9},{}",
                        p * AREA * 1000.0,
                        p.abs() * AREA <= PRESSURE_BUDGET
                    )?;
                }
            }
        }
    }
    blocked.flush()?;
    let mut balance = output(dir, "pressure_balance.csv")?;
    writeln!(balance,"differential_pressure_Pa,max_area_mismatch_mm2,max_fractional_area_mismatch,equivalent_diameter_mismatch_um")?;
    for p in [60.0, 1000.0, 10_000.0, 76_500.0] {
        let a = PRESSURE_BUDGET / p;
        writeln!(
            balance,
            "{p},{:.9},{:.9},{:.9}",
            a * 1e6,
            a / AREA,
            a / (PI * 0.008 / 2.0) * 1e6
        )?;
    }
    balance.flush()?;
    let mut transient = output(dir, "vent_transient.csv")?;
    writeln!(
        transient,
        "restriction_multiplier,time_s,pressure_Pa,force_mN"
    )?;
    for restriction in [1.0, 10.0, 100.0] {
        for time in [0.001, 0.01, 0.1, 1.0] {
            let r = resistance(0.0015, 0.1, 3e-5) * restriction;
            let p = vent_pressure(1e-6 / T0 * 10.0 + AREA * 0.020, r, 11e-6, time);
            writeln!(
                transient,
                "{restriction},{time},{p:.9},{:.9}",
                p * AREA * 1000.0
            )?;
        }
    }
    transient.flush()?;
    let mut faults = output(dir, "challenge_counterexamples.csv")?;
    writeln!(faults,"state,initial_um,retracted_um,returned_um,encoder_stroke_mm,passes_challenge,actual_local_contact")?;
    for (name, samples, contact) in [
        ("pan_present_free", [100.0, 0.0, 100.0], true),
        ("rigid_island_seizure", [100.0, 100.0, 100.0], false),
        ("rigid_witness_seizure", [100.0, 100.0, 100.0], false),
        ("constant_fresh_data", [100.0, 100.0, 100.0], false),
        ("elastic_jam_no_pan", [100.0, 0.0, 100.0], false),
        ("force_carrying_insulator", [100.0, 0.0, 100.0], false),
        ("command_correlated_fake_data", [100.0, 0.0, 100.0], false),
    ] {
        writeln!(
            faults,
            "{name},{},{},{},0.4,{},{}",
            samples[0],
            samples[1],
            samples[2],
            challenge(samples, 0.4),
            contact
        )?;
    }
    faults.flush()?;
    let mut electrical = output(dir, "electrical_counterexamples.csv")?;
    writeln!(electrical,"state,resistance_ohm,parallel_capacitance_pF,frequency_Hz,abs_impedance_ohm,phase_degrees,passes_example_100ohm_20degree_gate,thermal_conductance_W_K")?;
    let whisker_area = PI * (5e-6_f64).powi(2) / 4.0;
    for (name, resistance, capacitance, thermal) in [
        ("bare_clean_contact_example", 1.0, 100e-12, 0.13),
        (
            "dry_10um_gap",
            1e12,
            8.854e-12 * AREA / 10e-6 + 100e-12,
            0.0,
        ),
        ("insulating_coating_example", 1e9, 1e-9, 0.13),
        (
            "conductive_liquid_100um_gap",
            0.0001 / (0.1 * AREA),
            100e-12,
            0.6 * AREA / 0.0001,
        ),
        (
            "steel_whisker_5um_diameter_1mm_long",
            7e-7 * 0.001 / whisker_area,
            100e-12,
            15.0 * whisker_area / 0.001,
        ),
        ("pickup_wires_short", 1.0, 100e-12, 0.0),
    ] {
        for hz in [1000.0, 10000.0] {
            let g = 1.0 / resistance;
            let b = 2.0 * PI * hz * capacitance;
            let z = 1.0 / (g * g + b * b).sqrt();
            let phase = -b.atan2(g) * 180.0 / PI;
            writeln!(
                electrical,
                "{name},{resistance:.9},{:.9},{hz},{z:.9},{phase:.9},{},{thermal:.12}",
                capacitance * 1e12,
                z < 100.0 && phase.abs() < 20.0
            )?;
        }
    }
    electrical.flush()?;
    println!(
        "Pressure budget: {:.6}Pa; equivalent water head: {:.6}mm",
        PRESSURE_BUDGET / AREA,
        PRESSURE_BUDGET / (AREA * 1000.0 * 9.81) * 1000.0
    );
    println!("Pulse counterexample: equal total G=0.13 W/K from pan or other heat sink gives equal {:.9}K rise",pulse(0.13,0.04,0.1,0.1));
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sealed_isothermal_no_motion_has_zero_pressure() {
        assert!(sealed_pressure(1e-6, 10e-6, T0, T0, 0.0).abs() < 1e-9);
    }
    #[test]
    fn all_hot_sealed_matches_ideal_gas() {
        assert!(
            (sealed_pressure(1e-6, 0.0, 523.15, T0, 0.0) - P0 * (523.15 / T0 - 1.0)).abs() < 1e-8
        );
    }
    #[test]
    fn diameter_doubling_reduces_resistance_sixteenfold() {
        assert!((resistance(0.001, 0.1, 3e-5) / resistance(0.002, 0.1, 3e-5) - 16.0).abs() < 1e-12);
    }
    #[test]
    fn gas_time_constant_has_analytic_fraction() {
        let r = resistance(0.0015, 0.1, 3e-5);
        let q = 1e-6;
        assert!(
            (vent_pressure(q, r, 11e-6, r * 11e-6 / P0) / (q * r) - (1.0 - (-1.0_f64).exp())).abs()
                < 1e-12
        );
    }
    #[test]
    fn trapped_cold_reservoir_does_not_remove_hot_pressure() {
        assert!(sealed_pressure(1e-6, 10e-6, 523.15, T0, 0.0) * AREA > 0.003);
    }
    #[test]
    fn rigid_seizure_challenge_rejected() {
        assert!(!challenge([100.0, 100.0, 100.0], 0.4));
    }
    #[test]
    fn actuator_not_moving_is_rejected() {
        assert!(!challenge([100.0, 0.0, 100.0], 0.0));
    }
    #[test]
    fn elastic_jam_is_counterexample_not_claimed_covered() {
        assert!(challenge([100.0, 0.0, 100.0], 0.4));
    }
    #[test]
    fn thermal_pulse_cannot_identify_path_destination() {
        let pan = 0.12;
        let body = 0.01;
        let no_pan = 0.0;
        let wet_body = 0.13;
        assert!(
            (pulse(pan + body, 0.04, 0.1, 0.1) - pulse(no_pan + wet_body, 0.04, 0.1, 0.1)).abs()
                < 1e-12
        );
    }
}
