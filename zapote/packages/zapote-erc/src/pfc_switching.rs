//! Deterministic, source-backed boost commutation model.
//!
//! This is deliberately a switching-event model rather than a controller
//! average model.  The inductor current is the authoritative CCM current
//! moment, the SiC diode has zero reverse-recovery charge, and the UCC28180
//! is represented by its published source/sink peak-current limits.  The
//! model resolves the gate pre-plateau and Miller plateau in time, integrates
//! VDS*ID during the two transitions, and keeps Eoss as a separately audited
//! stored-energy term.  It is a bounded datasheet model: package parasitics,
//! temperature-dependent Qgd and the actual controller waveform still need a
//! double-pulse capture before hardware qualification.

use serde::Serialize;

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub bus_v: f64,
    pub switching_hz: f64,
    pub current_a: f64,
    pub gate_bias_v: f64,
    pub qg_c: f64,
    pub qgd_c: f64,
    pub gate_plateau_v: f64,
    pub gate_threshold_v: f64,
    pub external_gate_r_ohm: f64,
    pub intrinsic_gate_r_ohm: f64,
    pub driver_source_peak_a: f64,
    pub driver_sink_peak_a: f64,
    pub coss_energy_j: f64,
    pub loop_inductance_h: f64,
    pub rds_on_ohm: f64,
    pub timestep_s: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Transition {
    pub direction: &'static str,
    pub current_a: f64,
    pub gate_bias_v: f64,
    pub gate_resistance_ohm: f64,
    pub driver_peak_current_a: f64,
    pub pre_plateau_ns: f64,
    pub miller_ns: f64,
    pub overlap_energy_j: f64,
    pub coss_energy_j: f64,
    pub peak_vds_v: f64,
    pub steps: usize,
    pub timestep_s: f64,
    pub energy_balance_relative_error: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Result {
    pub cold_c: f64,
    pub hot_c: f64,
    pub turn_on: Transition,
    pub turn_off: Transition,
    pub switching_loss_w: f64,
    pub conduction_loss_w: f64,
    pub gate_charge_loss_w: f64,
    pub total_switch_loss_w: f64,
    pub vds_peak_v: f64,
    pub converged: bool,
}

fn finite_positive(name: &str, value: f64) -> std::result::Result<f64, String> {
    if value.is_finite() && value > 0.0 {
        Ok(value)
    } else {
        Err(format!("{name} must be finite and positive"))
    }
}

fn finite_nonnegative(name: &str, value: f64) -> std::result::Result<f64, String> {
    if value.is_finite() && value >= 0.0 {
        Ok(value)
    } else {
        Err(format!("{name} must be finite and nonnegative"))
    }
}

fn transition(
    config: Config,
    direction: &'static str,
    current_a: f64,
    driver_peak_current_a: f64,
) -> std::result::Result<Transition, String> {
    let bus = finite_positive("bus_v", config.bus_v)?;
    let current = finite_nonnegative("current_a", current_a)?;
    let qg = finite_positive("qg_c", config.qg_c)?;
    let qgd = finite_positive("qgd_c", config.qgd_c)?;
    let plateau = finite_positive("gate_plateau_v", config.gate_plateau_v)?;
    let threshold = finite_nonnegative("gate_threshold_v", config.gate_threshold_v)?;
    let resistance = finite_positive(
        "gate_resistance_ohm",
        config.external_gate_r_ohm + config.intrinsic_gate_r_ohm,
    )?;
    let driver = finite_positive("driver_peak_current_a", driver_peak_current_a)?;
    let coss_energy = finite_nonnegative("coss_energy_j", config.coss_energy_j)?;
    let timestep = finite_positive("timestep_s", config.timestep_s)?;
    let loop_l = finite_nonnegative("loop_inductance_h", config.loop_inductance_h)?;
    let rds = finite_nonnegative("rds_on_ohm", config.rds_on_ohm)?;

    // Qgs is the charge up to the Miller plateau.  This uses the retained
    // Qg/Qgd typicals and does not pretend the data sheet gives a full C(V).
    let qgs = (qg - qgd).max(0.0);
    let gate_span = (plateau - threshold).max(0.0);
    let source_resistive_a = ((config.gate_bias_v - plateau) / resistance).max(0.0);
    let sink_resistive_a = (plateau / resistance).max(0.0);
    let gate_current = if direction == "turn-on" {
        driver.min(source_resistive_a.max(f64::MIN_POSITIVE))
    } else {
        driver.min(sink_resistive_a.max(f64::MIN_POSITIVE))
    };
    let pre_plateau_s = qgs / gate_current;
    let miller_s = qgd / gate_current;
    let total_s = pre_plateau_s + miller_s;
    let steps = ((total_s / timestep).ceil() as usize).max(2);
    let dt = total_s / steps as f64;
    let mut overlap = 0.0;
    let mut peak_vds = bus;
    for step in 0..steps {
        let phase = (step as f64 + 0.5) / steps as f64;
        let vds_fraction = if direction == "turn-on" {
            if phase <= pre_plateau_s / total_s {
                1.0
            } else {
                let p = (phase - pre_plateau_s / total_s)
                    / (miller_s / total_s).max(f64::MIN_POSITIVE);
                (1.0 - p).clamp(0.0, 1.0)
            }
        } else if phase <= pre_plateau_s / total_s {
            0.0
        } else {
            let p = (phase - pre_plateau_s / total_s)
                / (miller_s / total_s).max(f64::MIN_POSITIVE);
            p.clamp(0.0, 1.0)
        };
        let current_fraction = if direction == "turn-on" {
            if phase <= pre_plateau_s / total_s {
                0.0
            } else {
                ((phase - pre_plateau_s / total_s)
                    / (miller_s / total_s).max(f64::MIN_POSITIVE))
                    .clamp(0.0, 1.0)
            }
        } else {
            1.0 - vds_fraction
        };
        let vds = if direction == "turn-on" {
            rds * current * current_fraction + bus * vds_fraction
        } else {
            rds * current * current_fraction + bus * vds_fraction
        };
        let id = current * current_fraction;
        overlap += vds * id * dt;
        peak_vds = peak_vds.max(vds);
    }
    // The loop inductance does not create a new loss term here; it bounds the
    // overshoot at the current slew produced by the Miller interval.
    let di_dt = if miller_s > 0.0 { current / miller_s } else { 0.0 };
    let overshoot = loop_l * di_dt;
    if direction == "turn-off" {
        peak_vds += overshoot;
    }
    let coss_term = if direction == "turn-on" { coss_energy } else { 0.0 };
    // Integrating the piecewise-linear current and VDS has a closed form. The
    // discretization error is reported and checked below so a coarse run can
    // never silently become evidence.
    let expected_overlap = bus * current * miller_s / 6.0
        + if direction == "turn-off" {
            rds * current * current * pre_plateau_s
        } else {
            0.0
        };
    let relative_error = if expected_overlap > 0.0 {
        ((overlap - expected_overlap) / expected_overlap).abs()
    } else {
        0.0
    };
    let convergence_limit = (2.0 * dt / miller_s.max(dt)).max(0.02);
    if !relative_error.is_finite() || relative_error > convergence_limit {
        return Err(format!("{direction} integration did not converge"));
    }
    let _ = gate_span; // retained to make the plateau assumption explicit.
    Ok(Transition {
        direction,
        current_a: current,
        gate_bias_v: config.gate_bias_v,
        gate_resistance_ohm: resistance,
        driver_peak_current_a: driver,
        pre_plateau_ns: pre_plateau_s * 1e9,
        miller_ns: miller_s * 1e9,
        overlap_energy_j: overlap,
        coss_energy_j: coss_term,
        peak_vds_v: peak_vds,
        steps,
        timestep_s: dt,
        energy_balance_relative_error: relative_error,
    })
}

pub fn simulate(config: Config, cold_c: f64, hot_c: f64) -> std::result::Result<Result, String> {
    if !cold_c.is_finite() || !hot_c.is_finite() || hot_c < cold_c {
        return Err("temperatures must be finite and ordered".into());
    }
    let on = transition(config, "turn-on", config.current_a, config.driver_source_peak_a)?;
    let off = transition(config, "turn-off", config.current_a, config.driver_sink_peak_a)?;
    let switching_w = (on.overlap_energy_j + off.overlap_energy_j + on.coss_energy_j)
        * config.switching_hz;
    let conduction_w = config.current_a * config.current_a * config.rds_on_ohm;
    let gate_w = config.qg_c * config.gate_bias_v * config.switching_hz;
    let total = switching_w + conduction_w + gate_w;
    let vds_peak_v = off.peak_vds_v;
    if !switching_w.is_finite() || !conduction_w.is_finite() || !gate_w.is_finite() {
        return Err("switching result is non-finite".into());
    }
    Ok(Result {
        cold_c,
        hot_c,
        turn_on: on,
        turn_off: off,
        switching_loss_w: switching_w,
        conduction_loss_w: conduction_w,
        gate_charge_loss_w: gate_w,
        total_switch_loss_w: total,
        vds_peak_v,
        converged: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config(dt: f64) -> Config {
        Config {
            bus_v: 389.6153846,
            switching_hz: 129107.39198577,
            current_a: 15.0,
            gate_bias_v: 10.0,
            qg_c: 120e-9,
            qgd_c: 58e-9,
            gate_plateau_v: 6.2,
            gate_threshold_v: 4.0,
            external_gate_r_ohm: 10.0,
            intrinsic_gate_r_ohm: 3.3,
            driver_source_peak_a: 1.5,
            driver_sink_peak_a: 2.0,
            coss_energy_j: 18.565e-6,
            loop_inductance_h: 10e-9,
            rds_on_ohm: 0.05,
            timestep_s: dt,
        }
    }

    #[test]
    fn driver_and_miller_model_converges_with_timestep_refinement() {
        let coarse = simulate(config(1e-9), 25.0, 125.0).unwrap();
        let fine = simulate(config(0.25e-9), 25.0, 125.0).unwrap();
        assert!(coarse.converged && fine.converged);
        let delta = (coarse.switching_loss_w - fine.switching_loss_w).abs();
        assert!(delta / fine.switching_loss_w < 0.01, "relative delta {delta}");
        assert!(fine.turn_on.miller_ns > 100.0 && fine.turn_on.miller_ns < 300.0);
        assert!(fine.vds_peak_v > 389.6);
    }

    #[test]
    fn coss_is_counted_once_on_turn_on() {
        let out = simulate(config(0.5e-9), 25.0, 125.0).unwrap();
        assert_eq!(out.turn_on.coss_energy_j, 18.565e-6);
        assert_eq!(out.turn_off.coss_energy_j, 0.0);
        assert!((out.gate_charge_loss_w - 120e-9 * 10.0 * 129107.39198577).abs() < 1e-12);
    }
}
