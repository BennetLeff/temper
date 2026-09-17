//! Piecewise-linear clamped-inductive switching sensitivity, not a circuit solver.
//!
//! TI SLUA618A figures 3–5 separate current transfer and Miller voltage motion.
//! The caller supplies their charges, two event currents, and duty-weighted RMS.
//! Gate current is approximated at the plateau and capped by the driver's peak
//! rating. This does not reproduce its output I–V curve or certify device loss.
use serde::Serialize;

const MAX_STEPS: usize = 1_000_000;

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Config {
    pub bus_v: f64,
    pub switching_hz: f64,
    pub turn_on_current_a: f64,
    pub turn_off_current_a: f64,
    /// RMS over the entire switching cycle, including off time as zero.
    pub switch_rms_a: f64,
    pub gate_bias_v: f64,
    pub qg_c: f64,
    pub qgd_c: f64,
    /// Explicit assumed charge during current transfer, NOT Qg-Qgd or total Qgs.
    pub current_transfer_charge_c: f64,
    pub gate_plateau_v: f64,
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
    pub assumed_gate_current_a: f64,
    pub current_transfer_ns: f64,
    pub miller_ns: f64,
    pub current_transfer_energy_j: f64,
    pub miller_energy_j: f64,
    pub overlap_energy_j: f64,
    pub coss_energy_j: f64,
    /// L*di/dt added to the bus at the supplied event current; not a peak bound.
    pub event_vds_estimate_v: f64,
    pub steps: usize,
    pub timestep_s: f64,
    /// Agreement with triangle areas, NOT circuit energy conservation.
    pub quadrature_relative_error: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Result {
    pub model_version: &'static str,
    pub inputs: Config,
    pub turn_on: Transition,
    pub turn_off: Transition,
    pub overlap_loss_w: f64,
    pub output_capacitance_loss_w: f64,
    pub switching_loss_w: f64,
    pub conduction_loss_w: f64,
    /// Dissipated across the driver/gate network, not all in the MOSFET die.
    pub gate_charge_loss_w: f64,
    /// Partial MOSFET loss under the assumed waveform; not a thermal verdict.
    pub modeled_mosfet_loss_w: f64,
    pub mosfet_plus_gate_loss_w: f64,
    pub quadrature_checked: bool,
}

fn positive(name: &str, value: f64) -> std::result::Result<(), String> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(format!("{name} must be finite and positive"))
    }
}
fn nonnegative(name: &str, value: f64) -> std::result::Result<(), String> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(format!("{name} must be finite and nonnegative"))
    }
}

// Independent stages: no simultaneous opposing V and I ramps. Ideal on-state
// Vds=0 here; duty-weighted I²R is accounted separately and never added twice.
fn waveform(on: bool, t: f64, ti: f64, tv: f64) -> (f64, f64) {
    if on {
        if t < ti {
            (1.0, t / ti)
        } else {
            (1.0 - (t - ti) / tv, 1.0)
        }
    } else if t < tv {
        (t / tv, 1.0)
    } else {
        (1.0, 1.0 - (t - tv) / ti)
    }
}

fn transition(c: Config, on: bool) -> std::result::Result<Transition, String> {
    let resistance = c.external_gate_r_ohm + c.intrinsic_gate_r_ohm;
    positive("total gate resistance", resistance)?;
    let gate_current = if on {
        c.driver_source_peak_a
            .min((c.gate_bias_v - c.gate_plateau_v) / resistance)
    } else {
        c.driver_sink_peak_a.min(c.gate_plateau_v / resistance)
    };
    positive("effective gate current", gate_current)?;
    let ti = c.current_transfer_charge_c / gate_current;
    let tv = c.qgd_c / gate_current;
    let duration = ti + tv;
    positive("current transfer duration", ti)?;
    positive("Miller duration", tv)?;
    positive("transition duration", duration)?;
    let requested = (duration / c.timestep_s).ceil().max(2.0);
    if !requested.is_finite() || requested > MAX_STEPS as f64 {
        return Err("transition exceeds integration step budget".into());
    }
    if duration >= 1.0 / c.switching_hz {
        return Err("transition exceeds switching period".into());
    }
    let steps = requested as usize;
    let dt = duration / steps as f64;
    let current = if on {
        c.turn_on_current_a
    } else {
        c.turn_off_current_a
    };
    let mut current_energy = 0.0;
    let mut miller_energy = 0.0;
    for step in 0..steps {
        // Split bins at the stage boundary. Midpoint integration is exact for
        // each linear stage even when the requested dt straddles that boundary.
        let lo = step as f64 * dt;
        let hi = (step + 1) as f64 * dt;
        let boundary = if on { ti } else { tv };
        for (a, b) in [(lo, hi.min(boundary)), (lo.max(boundary), hi)] {
            if b <= a {
                continue;
            }
            let t = 0.5 * (a + b);
            let (v, i) = waveform(on, t, ti, tv);
            let energy = c.bus_v * current * v * i * (b - a);
            if (on && t < ti) || (!on && t >= tv) {
                current_energy += energy;
            } else {
                miller_energy += energy;
            }
        }
    }
    let overlap = current_energy + miller_energy;
    let expected = 0.5 * c.bus_v * current * duration;
    let error = if expected > 0.0 {
        ((overlap - expected) / expected).abs()
    } else {
        0.0
    };
    let vds = c.bus_v
        + if on {
            0.0
        } else {
            c.loop_inductance_h * current / ti
        };
    if !overlap.is_finite()
        || !expected.is_finite()
        || !error.is_finite()
        || error > 1e-9
        || !vds.is_finite()
    {
        return Err("non-finite result or failed triangle-area quadrature check".into());
    }
    Ok(Transition {
        direction: if on { "turn-on" } else { "turn-off" },
        current_a: current,
        assumed_gate_current_a: gate_current,
        current_transfer_ns: ti * 1e9,
        miller_ns: tv * 1e9,
        current_transfer_energy_j: current_energy,
        miller_energy_j: miller_energy,
        overlap_energy_j: overlap,
        coss_energy_j: if on { c.coss_energy_j } else { 0.0 },
        event_vds_estimate_v: vds,
        steps,
        timestep_s: dt,
        quadrature_relative_error: error,
    })
}

pub fn simulate(c: Config) -> std::result::Result<Result, String> {
    for (name, value) in [
        ("bus_v", c.bus_v),
        ("switching_hz", c.switching_hz),
        ("gate_bias_v", c.gate_bias_v),
        ("qg_c", c.qg_c),
        ("qgd_c", c.qgd_c),
        ("current_transfer_charge_c", c.current_transfer_charge_c),
        ("gate_plateau_v", c.gate_plateau_v),
        ("driver_source_peak_a", c.driver_source_peak_a),
        ("driver_sink_peak_a", c.driver_sink_peak_a),
        ("timestep_s", c.timestep_s),
    ] {
        positive(name, value)?;
    }
    for (name, value) in [
        ("turn_on_current_a", c.turn_on_current_a),
        ("turn_off_current_a", c.turn_off_current_a),
        ("switch_rms_a", c.switch_rms_a),
        ("external_gate_r_ohm", c.external_gate_r_ohm),
        ("intrinsic_gate_r_ohm", c.intrinsic_gate_r_ohm),
        ("coss_energy_j", c.coss_energy_j),
        ("loop_inductance_h", c.loop_inductance_h),
        ("rds_on_ohm", c.rds_on_ohm),
    ] {
        nonnegative(name, value)?;
    }
    if c.gate_bias_v <= c.gate_plateau_v || c.qgd_c + c.current_transfer_charge_c >= c.qg_c {
        return Err(
            "bias must exceed plateau and event charges must leave room in total Qg".into(),
        );
    }
    let on = transition(c, true)?;
    let off = transition(c, false)?;
    let pair_s =
        (on.current_transfer_ns + on.miller_ns + off.current_transfer_ns + off.miller_ns) * 1e-9;
    if pair_s * c.switching_hz >= 1.0 {
        return Err("transition pair exceeds switching period".into());
    }
    let overlap = (on.overlap_energy_j + off.overlap_energy_j) * c.switching_hz;
    let output_capacitance = c.coss_energy_j * c.switching_hz;
    let switching = overlap + output_capacitance;
    let conduction = c.switch_rms_a.powi(2) * c.rds_on_ohm;
    let gate = c.qg_c * c.gate_bias_v * c.switching_hz;
    let mosfet = switching + conduction;
    let total = mosfet + gate;
    if !total.is_finite() {
        return Err("loss sum is non-finite".into());
    }
    Ok(Result {
        model_version: "clamped-inductive-linear-v2",
        inputs: c,
        turn_on: on,
        turn_off: off,
        overlap_loss_w: overlap,
        output_capacitance_loss_w: output_capacitance,
        switching_loss_w: switching,
        conduction_loss_w: conduction,
        gate_charge_loss_w: gate,
        modeled_mosfet_loss_w: mosfet,
        mosfet_plus_gate_loss_w: total,
        quadrature_checked: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config(dt: f64) -> Config {
        Config {
            bus_v: 400.0,
            switching_hz: 100_000.0,
            turn_on_current_a: 10.0,
            turn_off_current_a: 10.0,
            switch_rms_a: 15.0 * 0.5_f64.sqrt(),
            gate_bias_v: 10.0,
            qg_c: 100e-9,
            qgd_c: 15e-9,
            current_transfer_charge_c: 10e-9,
            gate_plateau_v: 5.0,
            external_gate_r_ohm: 10.0,
            intrinsic_gate_r_ohm: 0.0,
            driver_source_peak_a: 1.5,
            driver_sink_peak_a: 2.0,
            coss_energy_j: 18.565e-6,
            loop_inductance_h: 10e-9,
            rds_on_ohm: 0.05,
            timestep_s: dt,
        }
    }
    fn close(actual: f64, expected: f64) {
        assert!(
            (actual - expected).abs() < expected.abs().max(1e-12) * 1e-9,
            "{actual} != {expected}"
        );
    }
    #[test]
    fn clamped_inductive_miller_stage_has_triangle_energy() {
        let cfg = config(0.25e-9);
        let out = simulate(cfg).unwrap();
        let miller_only = 0.5 * cfg.bus_v * cfg.turn_on_current_a * out.turn_on.miller_ns * 1e-9;
        assert!(out.turn_on.overlap_energy_j >= miller_only * 0.999);
        close(out.turn_on.miller_energy_j, 60e-6);
    }
    #[test]
    fn independent_triangle_and_duty_anchors() {
        // TI SLUA618A figs 3–5: 20 ns current transfer, 30 ns Miller.
        // 400V * 10A * (20+30)ns / 2 = 100uJ each; 15A² * .05Ω * .5 = 5.625W.
        let out = simulate(config(7e-9)).unwrap();
        close(out.turn_on.current_transfer_ns, 20.0);
        close(out.turn_off.miller_ns, 30.0);
        close(out.turn_on.current_transfer_energy_j, 40e-6);
        close(out.turn_on.overlap_energy_j, 100e-6);
        close(out.turn_off.overlap_energy_j, 100e-6);
        close(out.overlap_loss_w, 20.0);
        close(out.conduction_loss_w, 5.625);
        close(out.turn_off.event_vds_estimate_v, 405.0);
    }
    #[test]
    fn stages_hold_current_or_voltage_and_reverse_order() {
        assert_eq!(waveform(true, 10.0, 20.0, 30.0), (1.0, 0.5));
        assert_eq!(waveform(true, 35.0, 20.0, 30.0), (0.5, 1.0));
        assert_eq!(waveform(false, 15.0, 20.0, 30.0), (0.5, 1.0));
        assert_eq!(waveform(false, 40.0, 20.0, 30.0), (1.0, 0.5));
    }
    #[test]
    fn driver_and_miller_model_converges_with_timestep_refinement() {
        let coarse = simulate(config(7e-9)).unwrap();
        let fine = simulate(config(0.25e-9)).unwrap();
        close(coarse.switching_loss_w, fine.switching_loss_w);
        close(fine.overlap_loss_w, 20.0);
    }
    #[test]
    fn asymmetric_event_currents_and_driver_caps() {
        let mut cfg = config(0.25e-9);
        cfg.driver_source_peak_a = 0.25; // twice the on interval
        cfg.turn_off_current_a = 20.0; // twice the off energy
        let out = simulate(cfg).unwrap();
        close(out.turn_on.overlap_energy_j, 200e-6);
        close(out.turn_off.overlap_energy_j, 200e-6);
        close(out.conduction_loss_w, 5.625); // independent of event-current inputs
    }
    #[test]
    fn eoss_once_and_gate_network_separate_from_die() {
        let mut cfg = config(0.5e-9);
        cfg.turn_on_current_a = 0.0;
        cfg.turn_off_current_a = 0.0;
        cfg.switch_rms_a = 0.0;
        let out = simulate(cfg).unwrap();
        assert_eq!(out.turn_off.coss_energy_j, 0.0);
        close(out.output_capacitance_loss_w, 1.8565);
        close(out.switching_loss_w, 1.8565);
        close(out.modeled_mosfet_loss_w, 1.8565);
        close(out.gate_charge_loss_w, 0.1);
        close(out.mosfet_plus_gate_loss_w, 1.9565);
        close(out.turn_off.event_vds_estimate_v, 400.0);
    }
    #[test]
    fn miller_change_does_not_change_current_slew_overshoot() {
        let mut cfg = config(1e-9);
        let initial = simulate(cfg).unwrap();
        cfg.qgd_c *= 2.0;
        let changed = simulate(cfg).unwrap();
        close(
            changed.turn_off.event_vds_estimate_v,
            initial.turn_off.event_vds_estimate_v,
        );
        close(
            changed.turn_off.miller_energy_j,
            2.0 * initial.turn_off.miller_energy_j,
        );
    }
    #[test]
    fn rejects_invalid_or_unbounded_inputs() {
        let base = config(1e-9);
        let cases = [
            Config {
                gate_bias_v: 5.0,
                ..base
            },
            Config {
                gate_bias_v: f64::NAN,
                ..base
            },
            Config {
                switching_hz: 0.0,
                ..base
            },
            Config {
                switching_hz: 15e6,
                ..base
            },
            Config {
                external_gate_r_ohm: -1.0,
                ..base
            },
            Config {
                current_transfer_charge_c: 0.0,
                ..base
            },
            Config {
                qgd_c: 100e-9,
                ..base
            },
            Config {
                driver_sink_peak_a: 0.0,
                ..base
            },
            Config {
                timestep_s: 1e-30,
                ..base
            },
            Config {
                turn_on_current_a: f64::INFINITY,
                ..base
            },
            Config {
                switch_rms_a: -1.0,
                ..base
            },
            Config {
                bus_v: f64::MAX,
                ..base
            },
            Config {
                loop_inductance_h: f64::MAX,
                ..base
            },
        ];
        for c in cases {
            assert!(simulate(c).is_err(), "accepted {c:?}");
        }
    }
}
