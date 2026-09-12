//! Nominal, steady-state CCM current waveforms for the boost PFC entry.
//!
//! The model is intentionally an electrical current-bound model.  It omits
//! efficiency, control-loop transients, inrush, short-circuit behaviour, and
//! thermal qualification.  The inductor ripple is retained in every RMS
//! result, so a stated input RMS limit is not accidentally treated as a
//! fundamental-only limit.

use serde::Serialize;
use std::f64::consts::{PI, SQRT_2};

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Config {
    pub line_rms_v: f64,
    pub input_rms_limit_a: f64,
    pub bus_v: f64,
    pub inductance_h: f64,
    pub switching_hz: f64,
    pub phase_samples: usize,
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Sample {
    /// Normalized switching-state weight (positive sample weights sum to one).
    pub weight: f64,
    /// Sign of the original AC line at this phase midpoint.
    pub line_sign: f64,
    /// Instantaneous inductor current at a switching-ramp sample.
    pub inductor_a: f64,
    /// Actual switching-state branch currents; their sum is the inductor current.
    pub switch_a: f64,
    pub diode_a: f64,
    /// Constant ideal DC-link load current and instantaneous capacitor current.
    pub load_a: f64,
    pub capacitor_a: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct Profile {
    pub samples: Vec<Sample>,
    pub input_power_w: f64,
    pub fundamental_rms_a: f64,
    pub input_rms_a: f64,
    pub input_peak_a: f64,
    pub inductor_rms_a: f64,
    pub switch_rms_a: f64,
    pub diode_rms_a: f64,
    pub load_rms_a: f64,
    pub capacitor_rms_a: f64,
    pub inductor_peak_a: f64,
    pub switch_peak_a: f64,
    pub diode_peak_a: f64,
    pub capacitor_peak_a: f64,
    pub duty_min: f64,
    pub duty_max: f64,
    pub ripple_peak_to_peak_max_a: f64,
}

const GAUSS_X: [f64; 2] = [0.211_324_865_405_187_13, 0.788_675_134_594_812_9];

fn positive_finite(x: f64) -> bool {
    x.is_finite() && x > 0.0
}

/// Calculate a sinusoidal ideal CCM boost waveform with triangular switching ripple.
pub fn calculate(config: Config) -> Result<Profile, String> {
    for (name, value) in [
        ("line_rms_v", config.line_rms_v),
        ("input_rms_limit_a", config.input_rms_limit_a),
        ("bus_v", config.bus_v),
        ("inductance_h", config.inductance_h),
        ("switching_hz", config.switching_hz),
    ] {
        if !positive_finite(value) {
            return Err(format!("{name} must be finite and positive"));
        }
    }
    if config.phase_samples < 32
        || config.phase_samples > 1_000_000
        || !config.phase_samples.is_multiple_of(2)
    {
        return Err("phase_samples must be an even number between 32 and 1,000,000".into());
    }
    let line_peak = config.line_rms_v * SQRT_2;
    if line_peak >= config.bus_v {
        return Err("line peak must be below bus voltage for valid boost duty".into());
    }

    // Ripple variance is independent of the fundamental amplitude.  Solve
    // I_rms^2 = I1_rms^2 + E[delta-I^2/12] exactly with phase quadrature.
    let ripple_variance = phase_midpoint_average(config, |theta| {
        let v = line_peak * theta.sin().abs();
        let d = 1.0 - v / config.bus_v;
        let ripple = v * d / (config.inductance_h * config.switching_hz);
        ripple * ripple / 12.0
    });
    let fundamental_rms_sq = config.input_rms_limit_a.powi(2) - ripple_variance;
    if !fundamental_rms_sq.is_finite() || fundamental_rms_sq <= 0.0 {
        return Err("input RMS limit is below the unavoidable ripple RMS".into());
    }
    let fundamental_rms = fundamental_rms_sq.sqrt();
    let input_peak = fundamental_rms * SQRT_2;
    let input_power = config.line_rms_v * fundamental_rms;
    let load_a = input_power / config.bus_v;

    let mut sums = Moments::default();
    let mut samples = Vec::with_capacity(config.phase_samples);
    let n = config.phase_samples as f64;
    for k in 0..config.phase_samples {
        let theta = 2.0 * PI * (k as f64 + 0.5) / n;
        let sign = if theta.sin() >= 0.0 { 1.0 } else { -1.0 };
        let v = line_peak * theta.sin().abs();
        let duty = 1.0 - v / config.bus_v;
        let delta = v * duty / (config.inductance_h * config.switching_hz);
        let avg = input_peak * theta.sin().abs();
        let valley = avg - delta / 2.0;
        let hi = avg + delta / 2.0;
        if valley < -1e-10 {
            return Err("calculated inductor valley enters DCM".into());
        }
        // Two Gauss points in each switching interval preserve the exact
        // second moment of each linear ON/OFF ramp.  Samples are actual
        // branch states, so consumers can integrate pulsed branch current.
        for x in GAUSS_X {
            let on_current = valley + delta * x;
            samples.push(Sample {
                weight: duty / (2.0 * n),
                line_sign: sign,
                inductor_a: on_current,
                switch_a: on_current,
                diode_a: 0.0,
                load_a,
                capacitor_a: -load_a,
            });
            let off_current = hi - delta * x;
            samples.push(Sample {
                weight: (1.0 - duty) / (2.0 * n),
                line_sign: sign,
                inductor_a: off_current,
                switch_a: 0.0,
                diode_a: off_current,
                load_a,
                capacitor_a: off_current - load_a,
            });
            sums.add(point_moments(on_current, duty, load_a, true));
            sums.add(point_moments(off_current, 1.0 - duty, load_a, false));
        }
        // Endpoints witness peaks without changing the Gauss-integrated RMS.
        for current in [valley, hi] {
            for on in [true, false] {
                samples.push(Sample {
                    weight: 0.0,
                    line_sign: sign,
                    inductor_a: current,
                    switch_a: if on { current } else { 0.0 },
                    diode_a: if on { 0.0 } else { current },
                    load_a,
                    capacitor_a: if on { -load_a } else { current - load_a },
                });
            }
        }
    }
    sums.scale(1.0 / (2.0 * n));
    let (peak_current, ripple_max, duty_min, duty_max) = extrema(config, input_peak);
    Ok(Profile {
        samples,
        input_power_w: input_power,
        fundamental_rms_a: fundamental_rms,
        input_rms_a: config.input_rms_limit_a,
        input_peak_a: peak_current,
        inductor_rms_a: sums.inductor_sq.sqrt(),
        switch_rms_a: sums.switch_sq.sqrt(),
        diode_rms_a: sums.diode_sq.sqrt(),
        load_rms_a: sums.load_sq.sqrt(),
        capacitor_rms_a: sums.capacitor_sq.sqrt(),
        inductor_peak_a: peak_current,
        switch_peak_a: peak_current,
        diode_peak_a: peak_current,
        capacitor_peak_a: (peak_current - load_a).abs().max(load_a),
        duty_min,
        duty_max,
        ripple_peak_to_peak_max_a: ripple_max,
    })
}

#[derive(Default)]
struct Moments {
    inductor_sq: f64,
    switch_sq: f64,
    diode_sq: f64,
    load_sq: f64,
    capacitor_sq: f64,
}

impl Moments {
    fn add(&mut self, o: Self) {
        self.inductor_sq += o.inductor_sq;
        self.switch_sq += o.switch_sq;
        self.diode_sq += o.diode_sq;
        self.load_sq += o.load_sq;
        self.capacitor_sq += o.capacitor_sq;
    }
    fn scale(&mut self, factor: f64) {
        self.inductor_sq *= factor;
        self.switch_sq *= factor;
        self.diode_sq *= factor;
        self.load_sq *= factor;
        self.capacitor_sq *= factor;
    }
}

fn point_moments(current: f64, active_fraction: f64, load: f64, switch: bool) -> Moments {
    let capacitor = if switch { -load } else { current - load };
    Moments {
        inductor_sq: active_fraction * current * current,
        switch_sq: if switch {
            active_fraction * current * current
        } else {
            0.0
        },
        diode_sq: if switch {
            0.0
        } else {
            active_fraction * current * current
        },
        load_sq: active_fraction * load * load,
        capacitor_sq: active_fraction * capacitor * capacitor,
    }
}

fn extrema(config: Config, peak: f64) -> (f64, f64, f64, f64) {
    let mut current_peak: f64 = 0.0;
    let mut ripple_peak: f64 = 0.0;
    let mut duty_min: f64 = 1.0;
    let mut duty_max: f64 = 0.0;
    for k in 0..=100_000 {
        let theta = PI * k as f64 / 100_000.0;
        let v = config.line_rms_v * SQRT_2 * theta.sin();
        let duty = 1.0 - v / config.bus_v;
        let ripple = v * duty / (config.inductance_h * config.switching_hz);
        current_peak = current_peak.max(peak * theta.sin() + ripple / 2.0);
        ripple_peak = ripple_peak.max(ripple);
        duty_min = duty_min.min(duty);
        duty_max = duty_max.max(duty);
    }
    (current_peak, ripple_peak, duty_min, duty_max)
}

fn phase_midpoint_average(config: Config, f: impl Fn(f64) -> f64) -> f64 {
    let n = config.phase_samples as f64;
    (0..config.phase_samples)
        .map(|k| f(2.0 * PI * (k as f64 + 0.5) / n))
        .sum::<f64>()
        / n
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> Config {
        Config {
            line_rms_v: 120.0,
            input_rms_limit_a: 15.0,
            bus_v: 400.0,
            inductance_h: 300e-6,
            switching_hz: 65_000.0,
            phase_samples: 2048,
        }
    }

    #[test]
    fn true_rms_hits_limit_and_ripple_is_included() {
        let p = calculate(config()).unwrap();
        assert!((p.input_rms_a - 15.0).abs() < 1e-12);
        assert!(p.input_peak_a > p.fundamental_rms_a * SQRT_2 * 0.999);
        assert!(p.ripple_peak_to_peak_max_a > 0.0);
    }

    #[test]
    fn branch_rms_values_differ_and_sample_kcl_holds() {
        let p = calculate(config()).unwrap();
        assert!((p.switch_rms_a - p.diode_rms_a).abs() > 0.01);
        for s in p.samples {
            assert!((s.switch_a + s.diode_a - s.inductor_a).abs() < 1e-12);
        }
    }

    #[test]
    fn energy_and_capacitor_mean_balance() {
        let p = calculate(config()).unwrap();
        let mean_cap: f64 = p.samples.iter().map(|s| s.weight * s.capacitor_a).sum();
        let mean_diode: f64 = p.samples.iter().map(|s| s.weight * s.diode_a).sum();
        assert!(mean_cap.abs() < 0.02);
        assert!((mean_diode * 400.0 - p.input_power_w).abs() < 1.0);
        assert!((p.load_rms_a - p.input_power_w / 400.0).abs() < 1e-10);
        for (reported, field) in [
            (p.load_rms_a, (|s: &Sample| s.load_a) as fn(&Sample) -> f64),
            (
                p.inductor_rms_a,
                (|s: &Sample| s.inductor_a) as fn(&Sample) -> f64,
            ),
            (
                p.switch_rms_a,
                (|s: &Sample| s.switch_a) as fn(&Sample) -> f64,
            ),
            (
                p.diode_rms_a,
                (|s: &Sample| s.diode_a) as fn(&Sample) -> f64,
            ),
            (
                p.capacitor_rms_a,
                (|s: &Sample| s.capacitor_a) as fn(&Sample) -> f64,
            ),
        ] {
            let sampled = p
                .samples
                .iter()
                .map(|s| s.weight * field(s).powi(2))
                .sum::<f64>()
                .sqrt();
            assert!((reported - sampled).abs() < 1e-10);
        }
    }

    #[test]
    fn inductor_moment_matches_independent_gauss_oracle() {
        let c = config();
        let p = calculate(c).unwrap();
        let expected_sq = phase_midpoint_average(c, |theta| {
            let v = c.line_rms_v * SQRT_2 * theta.sin().abs();
            let duty = 1.0 - v / c.bus_v;
            let ripple = v * duty / (c.inductance_h * c.switching_hz);
            let average = p.fundamental_rms_a * SQRT_2 * theta.sin().abs();
            average * average + ripple * ripple / 12.0
        });
        assert!((p.inductor_rms_a * p.inductor_rms_a - expected_sq).abs() < 1e-7);
    }

    #[test]
    fn switch_and_diode_moments_match_ideal_duty_formula() {
        let c = config();
        let p = calculate(c).unwrap();
        let i_peak = p.fundamental_rms_a * SQRT_2;
        let switch_sq = phase_midpoint_average(c, |theta| {
            let v = c.line_rms_v * SQRT_2 * theta.sin().abs();
            let duty = 1.0 - v / c.bus_v;
            let delta = v * duty / (c.inductance_h * c.switching_hz);
            let ramp_sq = (i_peak * theta.sin().abs()).powi(2) + delta * delta / 12.0;
            duty * ramp_sq
        });
        let diode_sq = phase_midpoint_average(c, |theta| {
            let v = c.line_rms_v * SQRT_2 * theta.sin().abs();
            let duty = 1.0 - v / c.bus_v;
            let delta = v * duty / (c.inductance_h * c.switching_hz);
            let ramp_sq = (i_peak * theta.sin().abs()).powi(2) + delta * delta / 12.0;
            (1.0 - duty) * ramp_sq
        });
        assert!((p.switch_rms_a.powi(2) - switch_sq).abs() < 1e-7);
        assert!((p.diode_rms_a.powi(2) - diode_sq).abs() < 1e-7);
    }

    #[test]
    fn invalid_configuration_is_rejected() {
        let mut c = config();
        c.bus_v = 100.0;
        assert!(calculate(c).is_err());
        let mut c = config();
        c.phase_samples = 0;
        assert!(calculate(c).is_err());
    }
}
