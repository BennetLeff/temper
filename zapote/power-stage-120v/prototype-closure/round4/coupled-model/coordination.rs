//! Explicit arithmetic screens. None models an interrupting fuse arc.
#[derive(Debug)]
struct Caps {
    min_f: [f64; 3],
    max_f: [f64; 3],
    current_a: [Option<f64>; 3],
    ac_peak_v: Option<f64>,
    dvdt_v_us: Option<f64>,
    frequency_hz: Option<f64>,
    max_case_c: Option<f64>,
}
// A sinusoidal RMS screen only. Arbitrary switching waveforms require direct
// per-capacitor RMS, peak voltage and dV/dt checks, not this conversion.
fn admitted_bank_current(c: &Caps, f: f64, temp: f64) -> Option<f64> {
    if !f.is_finite()
        || f <= 0.
        || !temp.is_finite()
        || !c.max_case_c?.is_finite()
        || !c.ac_peak_v?.is_finite()
        || !c.dvdt_v_us?.is_finite()
        || (0..3).any(|i| {
            !c.min_f[i].is_finite()
                || !c.max_f[i].is_finite()
                || c.min_f[i] <= 0.
                || c.max_f[i] < c.min_f[i]
        })
    {
        return None;
    }
    if c.frequency_hz? != f || temp > c.max_case_c? || c.ac_peak_v? <= 0. || c.dvdt_v_us? <= 0. {
        return None;
    }
    let mut bound = f64::INFINITY;
    for i in 0..3 {
        let total = c.max_f[i]
            + c.min_f
                .iter()
                .enumerate()
                .filter(|(j, _)| *j != i)
                .map(|(_, x)| x)
                .sum::<f64>();
        let share = c.max_f[i] / total;
        let limit = c.current_a[i]?;
        if limit <= 0. || !limit.is_finite() {
            return None;
        }
        bound = bound.min(limit / share);
    }
    let min_bank: f64 = c.min_f.iter().sum();
    let voltage_bound =
        std::f64::consts::TAU * f * min_bank * c.ac_peak_v? / std::f64::consts::SQRT_2;
    let slew_bound = min_bank * c.dvdt_v_us? * 1e6 / std::f64::consts::SQRT_2;
    Some(bound.min(voltage_bound).min(slew_bound))
}
fn main() {
    let vrms: f64 = 140.;
    for n in [4., 3.] {
        let r = 22. * 0.99;
        let amps = vrms / (n * r);
        let each = amps * amps * r;
        println!(
            "{n} series22Ω elements at-1%: {:.6}Arms {:.6}W/part {:.6}J/part in500ms",
            amps,
            each,
            each * 0.5
        );
    }
    let i2t_aux = 0.8615;
    let peak: f64 = 30.;
    println!(
        "AUX halfsine time to catalog prearcI2t (not time-current model): {:.6}ms",
        2. * i2t_aux / peak.powi(2) * 1000.
    );
    let caps = Caps {
        min_f: [0.198e-6, 0.198e-6, 0.09e-6],
        max_f: [0.242e-6, 0.242e-6, 0.11e-6],
        current_a: [None, None, None],
        ac_peak_v: None,
        dvdt_v_us: Some(2854.),
        frequency_hz: None,
        max_case_c: None,
    };
    println!("Selected50kHz tank application current admission: {:?} (None means0A commissioning permission)",admitted_bank_current(&caps,50000.,70.));
}
#[cfg(test)]
mod tests {
    use super::*;
    fn c() -> Caps {
        Caps {
            min_f: [0.198e-6, 0.198e-6, 0.09e-6],
            max_f: [0.242e-6, 0.242e-6, 0.11e-6],
            current_a: [Some(10.3), Some(10.3), Some(9.2)],
            ac_peak_v: Some(600.),
            dvdt_v_us: Some(2854.),
            frequency_hz: Some(100000.),
            max_case_c: Some(70.),
        }
    }
    #[test]
    fn missing_ac_denies() {
        let mut a = c();
        a.ac_peak_v = None;
        assert!(admitted_bank_current(&a, 100000., 70.).is_none())
    }
    #[test]
    fn frequency_mismatch_denies() {
        assert!(admitted_bank_current(&c(), 50000., 70.).is_none())
    }
    #[test]
    fn hot_denies() {
        assert!(admitted_bank_current(&c(), 100000., 71.).is_none())
    }
    #[test]
    fn sharing_uses_independent_tolerances() {
        let x = admitted_bank_current(&c(), 100000., 70.).unwrap();
        assert!((x - 22.55785123966942).abs() < 1e-8)
    }
    #[test]
    fn resistor_short_corner_below100w() {
        let i = 140. / (3. * 21.78);
        assert!(i * i * 21.78 < 100.)
    }
    #[test]
    fn voltage_rating_actually_limits_current() {
        let mut a = c();
        a.ac_peak_v = Some(1.);
        let expected = std::f64::consts::TAU * 100000. * 0.486e-6 / std::f64::consts::SQRT_2;
        assert!((admitted_bank_current(&a, 100000., 70.).unwrap() - expected).abs() < 1e-12);
    }
    #[test]
    fn slew_rating_actually_limits_current() {
        let mut a = c();
        a.dvdt_v_us = Some(0.1);
        let expected = 0.486e-6 * 0.1e6 / std::f64::consts::SQRT_2;
        assert!((admitted_bank_current(&a, 100000., 70.).unwrap() - expected).abs() < 1e-12);
    }
}
