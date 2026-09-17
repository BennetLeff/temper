//! Bounded first-order CCM loss estimates built from [`pfc_currents`].

use crate::pfc_currents::{self, Config};
use serde::Serialize;

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Moments {
    pub input_power_w: f64,
    pub input_rms_a: f64,
    pub switch_rms_a: f64,
    pub diode_rms_a: f64,
    pub capacitor_rms_a: f64,
    pub rectified_mean_a: f64,
    pub diode_mean_a: f64,
    pub mean_turn_on_a: f64,
    pub mean_turn_off_a: f64,
    pub switch_duty_mean: f64,
}

fn positive(name: &str, x: f64) -> Result<f64, String> {
    if x.is_finite() && x > 0.0 {
        Ok(x)
    } else {
        Err(format!("{name} must be finite and positive"))
    }
}
fn nonnegative(name: &str, x: f64) -> Result<f64, String> {
    if x.is_finite() && x >= 0.0 {
        Ok(x)
    } else {
        Err(format!("{name} must be finite and nonnegative"))
    }
}
fn finite_result(name: &str, x: f64) -> Result<f64, String> {
    x.is_finite()
        .then_some(x)
        .ok_or_else(|| format!("{name} overflowed or is non-finite"))
}

/// Weighted moments from the authoritative switching waveform.
pub fn moments(config: Config) -> Result<Moments, String> {
    let profile = pfc_currents::calculate(config)?;
    let mut rectified = 0.0;
    let mut switch_mean = 0.0;
    let mut duty = 0.0;
    for s in &profile.samples {
        if s.weight > 0.0 {
            rectified += s.weight * s.inductor_a.abs();
            switch_mean += s.weight * s.switch_a;
            duty += s.weight * if s.switch_a > 0.0 { 1.0 } else { 0.0 };
        }
    }
    let line_peak = config.line_rms_v * std::f64::consts::SQRT_2;
    let ripple_mean = line_peak / (config.inductance_h * config.switching_hz)
        * (2.0 / std::f64::consts::PI - line_peak / (2.0 * config.bus_v));
    let avg_mean =
        2.0 * std::f64::consts::SQRT_2 * profile.fundamental_rms_a / std::f64::consts::PI;
    // Enforce branch-current conservation by construction after weighted accumulation.
    let diode_mean = rectified - switch_mean;
    let out = Moments {
        input_power_w: profile.input_power_w,
        input_rms_a: profile.input_rms_a,
        switch_rms_a: profile.switch_rms_a,
        diode_rms_a: profile.diode_rms_a,
        capacitor_rms_a: profile.capacitor_rms_a,
        rectified_mean_a: rectified,
        diode_mean_a: diode_mean,
        mean_turn_on_a: avg_mean - ripple_mean / 2.0,
        mean_turn_off_a: avg_mean + ripple_mean / 2.0,
        switch_duty_mean: duty,
    };
    for (name, value) in [
        ("rectified_mean_a", out.rectified_mean_a),
        ("diode_mean_a", out.diode_mean_a),
        ("mean_turn_on_a", out.mean_turn_on_a),
        ("mean_turn_off_a", out.mean_turn_off_a),
        ("switch_duty_mean", out.switch_duty_mean),
    ] {
        finite_result(name, value)?;
    }
    Ok(out)
}

pub fn resistive_w(rms_a: f64, resistance_ohm: f64) -> Result<f64, String> {
    let i = nonnegative("rms_a", rms_a)?;
    let r = nonnegative("resistance_ohm", resistance_ohm)?;
    finite_result("resistive_w", i * i * r)
}

pub fn resistance_at_temperature(
    r25_ohm: f64,
    temp_c: f64,
    alpha_per_k: f64,
) -> Result<f64, String> {
    let r = positive("r25_ohm", r25_ohm)?;
    if !temp_c.is_finite() || !alpha_per_k.is_finite() {
        return Err("temperature and alpha must be finite".into());
    }
    let out = r * (1.0 + alpha_per_k * (temp_c - 25.0));
    if out > 0.0 {
        finite_result("resistance_at_temperature", out)
    } else {
        Err("temperature-adjusted resistance must be positive".into())
    }
}

pub fn diode_w(mean_a: f64, rms_a: f64, intercept_v: f64, slope_ohm: f64) -> Result<f64, String> {
    let mean = nonnegative("mean_a", mean_a)?;
    let rms = nonnegative("rms_a", rms_a)?;
    let vf = nonnegative("intercept_v", intercept_v)?;
    let slope = nonnegative("slope_ohm", slope_ohm)?;
    finite_result("diode_w", vf * mean + slope * rms * rms)
}

pub fn switching_overlap_w(
    bus_v: f64,
    fsw_hz: f64,
    mean_turn_on_a: f64,
    mean_turn_off_a: f64,
    rise_s: f64,
    fall_s: f64,
) -> Result<f64, String> {
    let v = positive("bus_v", bus_v)?;
    let f = positive("fsw_hz", fsw_hz)?;
    let on = nonnegative("mean_turn_on_a", mean_turn_on_a)?;
    let off = nonnegative("mean_turn_off_a", mean_turn_off_a)?;
    let tr = nonnegative("rise_s", rise_s)?;
    let tf = nonnegative("fall_s", fall_s)?;
    finite_result("switching_overlap_w", 0.5 * v * f * (on * tr + off * tf))
}

pub fn gate_drive_w(qg_c: f64, vdrive_v: f64, fsw_hz: f64) -> Result<f64, String> {
    let q = nonnegative("qg_c", qg_c)?;
    let v = nonnegative("vdrive_v", vdrive_v)?;
    let f = positive("fsw_hz", fsw_hz)?;
    finite_result("gate_drive_w", q * v * f)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> Config {
        Config {
            line_rms_v: 120.0,
            input_rms_limit_a: 10.0,
            bus_v: 400.0,
            inductance_h: 1e-3,
            switching_hz: 100_000.0,
            phase_samples: 256,
        }
    }

    #[test]
    fn moments_match_waveform_and_conserve_rectified_current() {
        let cfg = config();
        let profile = crate::pfc_currents::calculate(cfg).unwrap();
        let m = moments(cfg).unwrap();
        assert!((m.input_power_w - profile.input_power_w).abs() < 1e-10);
        assert!((m.input_rms_a - profile.input_rms_a).abs() < 1e-10);
        assert!((m.switch_rms_a - profile.switch_rms_a).abs() < 1e-10);
        assert!((m.diode_rms_a - profile.diode_rms_a).abs() < 1e-10);
        assert!((m.capacitor_rms_a - profile.capacitor_rms_a).abs() < 1e-10);
        assert!(
            (m.switch_rms_a.powi(2) + m.diode_rms_a.powi(2) - profile.inductor_rms_a.powi(2)).abs()
                < 1e-8
        );
        let expected_diode: f64 = profile.samples.iter().map(|s| s.weight * s.diode_a).sum();
        assert!((m.diode_mean_a - expected_diode).abs() < 1e-10);
    }

    #[test]
    fn closed_form_no_ripple_limit_uses_sin_cubed_moment() {
        // E[|sin|^3] = 4/(3π), anchoring branch RMS independently.
        let mut cfg = config();
        cfg.inductance_h = 1e6;
        // Midpoint quadrature of |sin| converges as O(N^-2).
        cfg.phase_samples = 65_536;
        let m = moments(cfg).unwrap();
        let p = crate::pfc_currents::calculate(cfg).unwrap();
        let peak = p.fundamental_rms_a * std::f64::consts::SQRT_2;
        let line_peak = cfg.line_rms_v * std::f64::consts::SQRT_2;
        let diode_sq = peak * peak * (line_peak / cfg.bus_v) * 4.0 / (3.0 * std::f64::consts::PI);
        assert!((m.diode_rms_a.powi(2) - diode_sq).abs() < 1e-8);
        assert!(
            (m.rectified_mean_a
                - p.fundamental_rms_a * 2.0 * std::f64::consts::SQRT_2 / std::f64::consts::PI)
                .abs()
                < 1e-8
        );
        assert!((m.diode_mean_a - p.input_power_w / cfg.bus_v).abs() < 1e-8);
    }

    #[test]
    fn edge_events_are_phase_weighted_not_duty_weighted() {
        let cfg = config();
        let m = moments(cfg).unwrap();
        let p = crate::pfc_currents::calculate(cfg).unwrap();
        let avg = 2.0 * std::f64::consts::SQRT_2 * p.fundamental_rms_a / std::f64::consts::PI;
        let ripple = (cfg.line_rms_v * std::f64::consts::SQRT_2)
            / (cfg.inductance_h * cfg.switching_hz)
            * (2.0 / std::f64::consts::PI
                - cfg.line_rms_v * std::f64::consts::SQRT_2 / (2.0 * cfg.bus_v));
        assert!((m.mean_turn_on_a - (avg - ripple / 2.0)).abs() < 1e-10);
        assert!((m.mean_turn_off_a - (avg + ripple / 2.0)).abs() < 1e-10);
        let duty_weighted = p.samples.iter().map(|s| s.weight * s.switch_a).sum::<f64>();
        assert!((m.mean_turn_on_a - duty_weighted).abs() > 1e-3);
    }

    #[test]
    fn loss_helpers_have_expected_scaling_and_reject_bad_inputs() {
        assert!((resistive_w(2.0, 3.0).unwrap() - 12.0).abs() < 1e-12);
        assert!(
            (resistive_w(4.0, 3.0).unwrap() / resistive_w(2.0, 3.0).unwrap() - 4.0).abs() < 1e-12
        );
        assert!((resistance_at_temperature(1.0, 45.0, 0.00393).unwrap() - 1.0786).abs() < 1e-5);
        assert!((diode_w(2.0, 3.0, 1.0, 0.1).unwrap() - 2.9).abs() < 1e-12);
        assert!(resistive_w(f64::NAN, 1.0).is_err());
        assert!(resistance_at_temperature(-1.0, 25.0, 0.003).is_err());
        assert!(diode_w(-1.0, 1.0, 1.0, 0.1).is_err());
        assert!(switching_overlap_w(400.0, 100_000.0, 2.0, 3.0, 1e-8, 1e-8).is_ok());
        assert!(gate_drive_w(1e-6, 10.0, 100_000.0).is_ok());
        assert!(gate_drive_w(f64::INFINITY, 10.0, 100_000.0).is_err());
        assert!(resistive_w(-1.0, 1.0).is_err());
        assert!(switching_overlap_w(f64::MAX, f64::MAX, f64::MAX, 1.0, 1.0, 1.0).is_err());
    }
}
