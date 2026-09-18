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

/// First-order Miller-plateau edge-time estimate for a MOSFET driven through
/// an external and intrinsic gate resistance.  This is a scoped sensitivity,
/// not a switching-energy prediction: UCC28180 source impedance, plateau
/// voltage, layout inductance and bias-dependent Qgd still require a waveform.
pub fn gate_network_edge_s(
    qgd_c: f64,
    drive_v: f64,
    external_r_ohm: f64,
    intrinsic_r_ohm: f64,
) -> Result<f64, String> {
    let q = nonnegative("qgd_c", qgd_c)?;
    let v = positive("drive_v", drive_v)?;
    let re = nonnegative("external_r_ohm", external_r_ohm)?;
    let ri = nonnegative("intrinsic_r_ohm", intrinsic_r_ohm)?;
    finite_result("gate_network_edge_s", q * (re + ri) / v)
}

/// Interpolate the manufacturer's `Eoss(VDS)` curve in joules.
///
/// `Coss eq.` in the ST datasheet is defined by equal charging time to 80 %
/// of `VDSS`; it is deliberately not accepted here as an energy equivalent.
/// The curve points are digitized from the manufacturer's typical curve, so
/// callers must retain the source revision and digitization uncertainty with
/// their result.
pub fn eoss_from_curve(points: &[(f64, f64)], vds_v: f64) -> Result<f64, String> {
    let v = nonnegative("vds_v", vds_v)?;
    if points.len() < 2 {
        return Err("Eoss curve needs at least two points".into());
    }
    for window in points.windows(2) {
        let (v0, e0) = window[0];
        let (v1, e1) = window[1];
        if !v0.is_finite()
            || !e0.is_finite()
            || !v1.is_finite()
            || !e1.is_finite()
            || v0 < 0.0
            || v1 <= v0
            || e0 < 0.0
            || e1 < 0.0
        {
            return Err("Eoss curve points must be finite, ordered and nonnegative".into());
        }
    }
    let &(v_last, _) = points.last().unwrap();
    if v > v_last {
        return Err(format!("vds_v {v} exceeds Eoss curve maximum {v_last}"));
    }
    let index = points
        .windows(2)
        .position(|window| v <= window[1].0)
        .unwrap_or(points.len() - 2);
    let (v0, e0) = points[index];
    let (v1, e1) = points[index + 1];
    let out = e0 + (e1 - e0) * (v - v0) / (v1 - v0);
    finite_result("eoss_from_curve", out)
}

/// Convert a source-backed `Eoss(VDS)` point to hard-switched turn-on loss.
///
/// This term is separate from measured Eon/Eoff overlap energy. Summing both
/// without checking the measurement definition double-counts the output
/// capacitance discharge.
pub fn output_capacitance_eoss_w(eoss_j: f64, fsw_hz: f64) -> Result<f64, String> {
    let e = nonnegative("eoss_j", eoss_j)?;
    let f = positive("fsw_hz", fsw_hz)?;
    finite_result("output_capacitance_eoss_w", e * f)
}

/// A forward-drop characteristic: forward voltage as a function of forward
/// current, traced from a manufacturer's typical curve.
///
/// The curve carries its own source binding so a caller cannot silently pair a
/// traced curve with a different document revision. Points ascend in current.
/// A current at or below the first point clamps to that point's voltage, which
/// overestimates drop near the line zero crossing rather than extrapolating an
/// unstable knee. A current above the last point is an error, never an
/// extrapolation.
#[derive(Clone, Debug, PartialEq)]
pub struct ForwardDropCurve {
    points: Vec<(f64, f64)>,
    source_sha256: String,
}

impl ForwardDropCurve {
    pub fn new(points: Vec<(f64, f64)>, source_sha256: &str) -> Result<Self, String> {
        if source_sha256.len() != 64
            || !source_sha256.chars().all(|c| c.is_ascii_hexdigit())
        {
            return Err("forward-drop curve needs a 64-hex-digit source sha256".into());
        }
        if points.len() < 2 {
            return Err("forward-drop curve needs at least two points".into());
        }
        for window in points.windows(2) {
            let (i0, v0) = window[0];
            let (i1, v1) = window[1];
            if !i0.is_finite()
                || !v0.is_finite()
                || !i1.is_finite()
                || !v1.is_finite()
                || i0 < 0.0
                || i1 <= i0
                || v0 < 0.0
                || v1 < 0.0
            {
                return Err(
                    "forward-drop points must be finite, ordered in current and nonnegative".into(),
                );
            }
        }
        Ok(Self {
            points,
            source_sha256: source_sha256.to_ascii_lowercase(),
        })
    }

    pub fn source_sha256(&self) -> &str {
        &self.source_sha256
    }

    pub fn points(&self) -> &[(f64, f64)] {
        &self.points
    }

    /// Forward voltage at `current_a`. Clamps at the low end; errors above the
    /// traced maximum.
    pub fn forward_v(&self, current_a: f64) -> Result<f64, String> {
        let i = nonnegative("current_a", current_a)?;
        let last = self.points.last().unwrap().0;
        if i > last {
            return Err(format!(
                "current {i} A exceeds forward-drop curve maximum {last} A"
            ));
        }
        if i <= self.points[0].0 {
            return finite_result("forward_v", self.points[0].1);
        }
        let idx = self
            .points
            .windows(2)
            .position(|w| i <= w[1].0)
            .unwrap_or(self.points.len() - 2);
        let (i0, v0) = self.points[idx];
        let (i1, v1) = self.points[idx + 1];
        finite_result("forward_v", v0 + (v1 - v0) * (i - i0) / (i1 - i0))
    }
}

/// Rectified bridge conduction loss from a forward-drop curve and the
/// authoritative switching waveform.
///
/// `element_count` is the number of diode elements in the line path at every
/// instant (two for a single-phase bridge). `parallel_branches` is the number of
/// bridges sharing the line current equally, so the per-branch current is the
/// line current divided by it. With a flat curve the result reduces to
/// `element_count * V_f * rectified mean current` and is independent of
/// `parallel_branches`; with a real curve the two cases diverge, which is why
/// sharing stays an explicit input rather than a constant folded into the caller.
///
/// The flat curve is the linear case of this same model; [`diode_w`] is its
/// closed form in current moments, kept for callers that have moments and no
/// waveform.
pub fn forward_drop_w(
    curve: &ForwardDropCurve,
    samples: &[crate::pfc_currents::Sample],
    element_count: f64,
    parallel_branches: f64,
) -> Result<f64, String> {
    let elements = positive("element_count", element_count)?;
    let branches = positive("parallel_branches", parallel_branches)?;
    if samples.is_empty() {
        return Err("forward-drop integration needs the waveform samples".into());
    }
    let mut total = 0.0;
    let mut weighted = 0.0;
    for sample in samples {
        if sample.weight <= 0.0 {
            continue;
        }
        let line = sample.inductor_a.abs() / branches;
        total += sample.weight * branches * elements * curve.forward_v(line)? * line;
        weighted += sample.weight;
    }
    if weighted <= 0.0 {
        return Err("forward-drop integration found no weighted samples".into());
    }
    finite_result("forward_drop_w", total)
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
        assert!((gate_network_edge_s(58e-9, 10.0, 10.0, 3.3).unwrap() - 77.14e-9).abs() < 1e-11);
        assert!(gate_network_edge_s(58e-9, 0.0, 10.0, 3.3).is_err());
        let curve = [(0.0, 0.0), (200.0, 7.0e-6), (400.0, 19.5e-6)];
        let eoss = eoss_from_curve(&curve, 400.0).unwrap();
        assert!((eoss - 19.5e-6).abs() < 1e-12);
        assert!((output_capacitance_eoss_w(eoss, 130_000.0).unwrap() - 2.535).abs() < 1e-12);
        assert!(
            (output_capacitance_eoss_w(eoss, 65_000.0).unwrap()
                - output_capacitance_eoss_w(eoss, 130_000.0).unwrap() / 2.0)
                .abs()
                < 1e-12
        );
        assert!(eoss_from_curve(&curve, 500.0).is_err());
        assert!(output_capacitance_eoss_w(-1.0, 130_000.0).is_err());
        assert!(output_capacitance_eoss_w(19.5e-6, 0.0).is_err());
        assert!(resistive_w(-1.0, 1.0).is_err());
        assert!(switching_overlap_w(f64::MAX, f64::MAX, f64::MAX, 1.0, 1.0, 1.0).is_err());
    }

    const CURVE_SHA: &str = "c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02";

    fn curve_samples() -> Vec<crate::pfc_currents::Sample> {
        pfc_currents::calculate(config()).unwrap().samples
    }

    fn mean_and_rms(samples: &[crate::pfc_currents::Sample]) -> (f64, f64) {
        let (mut mean, mut sq) = (0.0, 0.0);
        for s in samples {
            if s.weight > 0.0 {
                mean += s.weight * s.inductor_a.abs();
                sq += s.weight * s.inductor_a * s.inductor_a;
            }
        }
        (mean, sq.sqrt())
    }

    #[test]
    fn flat_curve_reproduces_the_constant_drop_result() {
        let samples = curve_samples();
        let flat = ForwardDropCurve::new(vec![(0.0, 1.05), (100.0, 1.05)], CURVE_SHA).unwrap();
        let (mean, _) = mean_and_rms(&samples);
        let got = forward_drop_w(&flat, &samples, 2.0, 1.0).unwrap();
        let want = 2.0 * 1.05 * mean;
        assert!((got - want).abs() < 1e-9, "flat identity: {got} vs {want}");
    }

    #[test]
    fn linear_curve_agrees_with_the_moment_form() {
        // V(i) = a + b*i => loss = elements * (a*mean + b*rms^2) = elements * diode_w(..)
        let samples = curve_samples();
        let (a, b) = (0.70, 0.010);
        let linear =
            ForwardDropCurve::new(vec![(0.0, a), (100.0, a + 100.0 * b)], CURVE_SHA).unwrap();
        let (mean, rms) = mean_and_rms(&samples);
        let from_curve = forward_drop_w(&linear, &samples, 2.0, 1.0).unwrap();
        let from_moments = 2.0 * diode_w(mean, rms, a, b).unwrap();
        assert!(
            (from_curve - from_moments).abs() < 1e-9,
            "curve {from_curve} vs moments {from_moments}"
        );
    }

    #[test]
    fn parallel_sharing_changes_a_nonlinear_curve_but_not_a_flat_one() {
        let samples = curve_samples();
        let flat = ForwardDropCurve::new(vec![(0.0, 1.05), (100.0, 1.05)], CURVE_SHA).unwrap();
        let one = forward_drop_w(&flat, &samples, 2.0, 1.0).unwrap();
        let two = forward_drop_w(&flat, &samples, 2.0, 2.0).unwrap();
        assert!((one - two).abs() < 1e-9, "a flat curve must be sharing-invariant");
        let curve = ForwardDropCurve::new(
            vec![(0.01, 0.70), (1.0, 0.75), (10.0, 0.95), (100.0, 1.40)],
            CURVE_SHA,
        )
        .unwrap();
        let one = forward_drop_w(&curve, &samples, 2.0, 1.0).unwrap();
        let two = forward_drop_w(&curve, &samples, 2.0, 2.0).unwrap();
        assert!(two < one, "splitting a rising curve must reduce loss: {two} vs {one}");
    }

    #[test]
    fn curve_clamps_low_and_errors_above_its_maximum() {
        let curve = ForwardDropCurve::new(vec![(0.01, 0.70), (10.0, 0.95)], CURVE_SHA).unwrap();
        assert!((curve.forward_v(0.0).unwrap() - 0.70).abs() < 1e-12);
        assert!((curve.forward_v(0.01).unwrap() - 0.70).abs() < 1e-12);
        assert!((curve.forward_v(10.0).unwrap() - 0.95).abs() < 1e-12);
        assert!(curve.forward_v(10.1).is_err(), "must not extrapolate above the trace");
    }

    #[test]
    fn malformed_curves_are_rejected() {
        assert!(ForwardDropCurve::new(vec![(0.0, 1.0)], CURVE_SHA).is_err());
        assert!(ForwardDropCurve::new(vec![(0.0, 1.0), (0.0, 1.1)], CURVE_SHA).is_err());
        assert!(ForwardDropCurve::new(vec![(0.0, 1.0), (1.0, -1.0)], CURVE_SHA).is_err());
        assert!(ForwardDropCurve::new(vec![(0.0, 1.0), (1.0, f64::NAN)], CURVE_SHA).is_err());
        assert!(ForwardDropCurve::new(vec![(0.0, 1.0), (1.0, 1.1)], "deadbeef").is_err());
    }

    #[test]
    fn integration_rejects_empty_or_unweighted_waveforms() {
        let curve = ForwardDropCurve::new(vec![(0.0, 1.0), (10.0, 1.2)], CURVE_SHA).unwrap();
        assert!(forward_drop_w(&curve, &[], 2.0, 1.0).is_err());
        let unweighted = vec![crate::pfc_currents::Sample {
            weight: 0.0,
            line_sign: 1.0,
            inductor_a: 1.0,
            switch_a: 1.0,
            diode_a: 0.0,
            load_a: 0.0,
            capacitor_a: 0.0,
        }];
        assert!(forward_drop_w(&curve, &unweighted, 2.0, 1.0).is_err());
    }
}
