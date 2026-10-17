//! Analytic demands only. No thermal, contact, fuse, or insulation pass is implied.
//! Standalone rustc; do not build a shared PyO3 crate for this calculation.
use std::f64::consts::SQRT_2;

fn parallel(a: f64, b: f64) -> f64 {
    assert!(a.is_finite() && b.is_finite() && a > 0.0 && b > 0.0);
    a * b / (a + b)
}

fn energy(c: f64, v: f64) -> f64 {
    assert!(c.is_finite() && v.is_finite() && c >= 0.0 && v >= 0.0);
    0.5 * c * v * v
}

fn main() {
    let r_branch_min = 22.0 * 0.99;
    let r_min = parallel(r_branch_min, r_branch_min);
    let v_rms = 140.0_f64;
    let v_peak = v_rms * SQRT_2;
    let fault_p = v_rms.powi(2) / r_min;
    let c_total = 47e-6 * 1.2 + (5.8e-6 + 13.6e-6) * 1.1;
    println!("evidence_class=CALCULATED_DEMAND_NOT_COMPONENT_QUALIFICATION");
    println!("r_pre_min_ohm={r_min:.6}");
    println!("fault_current_peak_a={:.6}", v_peak / r_min);
    println!("fault_current_rms_a={:.6}", v_rms / r_min);
    println!("fault_power_total_w={fault_p:.6}");
    println!("fault_energy_500ms_total_j={:.6}", fault_p * 0.5);
    println!("fault_energy_500ms_per_branch_j={:.6}", fault_p * 0.25);
    println!("catch_cap_max_f={:.9}", 47e-6 * 1.2);
    println!(
        "catch_charge_energy_at_198v_j={:.6}",
        energy(47e-6 * 1.2, 198.0)
    );
    println!("all_capacitance_max_f={c_total:.9}");
    println!(
        "all_capacitance_energy_at_198v_j={:.6}",
        energy(c_total, 198.0)
    );
    for v in [100.0_f64, 120.0, 127.0, 140.0] {
        let test_r_min = 220.0 * 0.99;
        let test_r_max = 220.0 * 1.01;
        println!("v_rms={v} proof_min_current_a={:.6} proof_max_power_w={:.6} proof_energy_100ms_j={:.6} open_bypass_vdrop_peak_v={:.6}",
            v/test_r_max, v*v/test_r_min, v*v/test_r_min*0.1,
            v*SQRT_2*r_min/(test_r_max+r_min));
    }
    let ratio = 4020.0 / (4.0 * 249000.0 + 4020.0);
    println!("amc_divider_ratio={ratio:.9}");
    println!("amc_input_at_198v={:.6}", 198.0 * ratio);
    println!("contactor_close_max_ms={:.3}", 63.0 * 1.15);
    println!("contactor_open_max_ms={:.3}", 20.0 * 1.2);
    println!(
        "startup_close_tracking_bypass_ms={:.3}",
        2.0 * 63.0 * 1.15 + 40.0
    );
    println!("three_contactor_coils_w={:.3}", 3.0 * 5.4);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn two_branches_and_one_open_are_distinct() {
        assert_eq!(parallel(22.0, 22.0), 11.0);
        assert!(parallel(22.0, 1e12) > 21.99);
    }
    #[test]
    fn proof_open_bypass_cannot_meet_one_volt_with_real_test_current() {
        for v in [100.0, 120.0, 127.0, 140.0] {
            let i = v / (220.0 * 1.01 + 11.0 * 0.99);
            assert!(i > 0.4);
            assert!(i * 11.0 * 0.99 * SQRT_2 > 6.0);
        }
    }
    #[test]
    fn resistor_500ms_demand_is_under_proposed_500j_each_test() {
        let demand = 140.0_f64.powi(2) / (22.0 * 0.99) * 0.5;
        assert!(demand > 449.0 && demand < 500.0);
    }
    #[test]
    fn fifty_hz_two_cycles_fit_selected_budget_but_not_old_100ms() {
        let close_tracking_bypass = 2.0 * 63.0 * 1.15 + 40.0;
        assert!(close_tracking_bypass > 100.0);
        assert!(close_tracking_bypass < 300.0);
    }
    #[test]
    fn catch_cap_cannot_be_omitted_from_charge_energy() {
        let old = energy((5.8e-6 + 13.6e-6) * 1.1, 198.0);
        let with_catch = old + energy(47e-6 * 1.2, 198.0);
        assert!(with_catch > 3.0 * old);
        assert!(with_catch < 1.6);
    }
    #[test]
    fn dc_short_can_remain_below_line_fuse_rating() {
        assert!(140.0 / (11.0 * 0.99) < 15.0);
    }
    #[test]
    #[should_panic]
    fn invalid_resistance_is_not_a_result() {
        parallel(0.0, 22.0);
    }
    #[test]
    #[should_panic]
    fn nonfinite_energy_is_not_a_result() {
        energy(f64::NAN, 198.0);
    }
}
