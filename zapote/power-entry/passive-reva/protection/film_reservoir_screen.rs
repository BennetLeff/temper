//! Finite screen for the diode-side film-capacitor option after F2 opens.
//!
//! This reuses the immediate-off algebra retained in
//! `active-rectifier/experiments/f2-open/f2_open_timed.rs`:
//! Vpeak = Vin + sqrt((V0 - Vin)^2 + L/C * I0^2).
//! It is a screen for a healthy, controllable U9 only. It does not model the
//! detector, controller delay, restart, a failed-short U9, or the fuse.

const VIN: f64 = 169.705627485;
const L: f64 = 180e-6;

fn immediate_off_peak(v0: f64, i0: f64, c: f64) -> f64 {
    VIN + ((v0 - VIN).powi(2) + L / c * i0.powi(2)).sqrt()
}

fn unfused_energy(c: f64, v: f64) -> f64 {
    0.5 * c * v * v
}

fn main() {
    println!("cap_uF,v0_v,i0_a,vpeak_v,energy_at_500v_j");
    for c in [10e-6, 22e-6, 47e-6] {
        for v0 in [389.6153846, 424.68, 454.33] {
            for i0 in [14.0, 40.0] {
                println!("{:.1},{:.7},{:.1},{:.6},{:.6}", c * 1e6, v0, i0,
                    immediate_off_peak(v0, i0, c), unfused_energy(c, 500.0));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn larger_cap_reduces_healthy_switch_peak_at_same_state() {
        let p10 = immediate_off_peak(424.68, 40.0, 10e-6);
        let p22 = immediate_off_peak(424.68, 40.0, 22e-6);
        let p47 = immediate_off_peak(424.68, 40.0, 47e-6);
        assert!(p10 > p22 && p22 > p47);
        assert!((p10 - 475.992960947).abs() < 1e-9);
        assert!((p22 - 449.174480365).abs() < 1e-9);
        assert!((p47 - 436.425687124).abs() < 1e-9);
    }

    #[test]
    fn larger_cap_increases_unfused_energy() {
        assert!(unfused_energy(47e-6, 500.0) > unfused_energy(22e-6, 500.0));
        assert!((unfused_energy(10e-6, 500.0) - 1.25).abs() < 1e-12);
        assert!((unfused_energy(22e-6, 500.0) - 2.75).abs() < 1e-12);
        assert!((unfused_energy(47e-6, 500.0) - 5.875).abs() < 1e-12);
    }

}
