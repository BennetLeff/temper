//! Bounded bootstrap charge screen for the selected UCC21530BQDWKRQ1.
//! This is a charge-balance screen, not a switching or safety qualification.

fn main() {
    let vaux_nom = 15.0_f64;
    let vaux_tol = 0.025_f64;
    let ripple_pp = 0.200_f64;
    let vf_max = 1.10_f64; // conservative ES1J screening input
    let vf_min = 0.60_f64; // startup-energy sensitivity only
    let uvlo = 8.0_f64; // BQ 8-V UVLO threshold used for hard cutoff
    let uvlo_design_min = 9.2_f64; // conservative recommended operating floor
    let c_nom = 1000e-6_f64;
    let c_tol = 0.20_f64;
    let c_min = c_nom * (1.0 - c_tol);
    let r_boot = 47.0_f64;
    let iq_max = 2.5e-3_f64; // retained TI driver supply-current screening value
    let pull_down = (vaux_nom * (1.0 + vaux_tol) - vf_max) / 10_000.0;
    let leakage = 0.25e-3_f64; // explicit allowance; exact high-side leakage remains source input
    let i_hold = iq_max + pull_down + leakage;
    let half_cycle = 1.0 / (2.0 * 60.0);
    let q_removed = i_hold * half_cycle;
    let droop = q_removed / c_min;
    let vaux_min = vaux_nom * (1.0 - vaux_tol) - ripple_pp / 2.0;
    let source_min = vaux_min - vf_max;
    let tau = r_boot * c_min;
    // The high-side interval is followed by a separate recharge interval.
    // Solve the periodic fixed point instead of assuming the capacitor starts
    // at source_min every cycle or that a constant recharge current applies.
    let equilibrium = source_min - i_hold * r_boot;
    let decay = (-half_cycle / tau).exp();
    let v_start = (equilibrium * (1.0 - decay) - droop * decay)
        / (1.0 - decay);
    let v_hold_end = v_start - droop;
    let v_recharge_end = equilibrium + (v_hold_end - equilibrium) * decay;
    let recharge_current_at_start = (source_min - v_hold_end - i_hold * r_boot) / r_boot;
    let recharge_time_to_uvlo = if v_hold_end < uvlo_design_min {
        let target = (uvlo_design_min - equilibrium) / (v_hold_end - equilibrium);
        if target > 0.0 && target < 1.0 { -tau * target.ln() } else { f64::NAN }
    } else { 0.0 };
    // Startup uses the maximum capacitor and maximum rail, with the minimum
    // diode drop, because that is the largest resistor pulse/energy case.
    let c_max = c_nom * (1.0 + c_tol);
    let vaux_max = vaux_nom * (1.0 + vaux_tol) + ripple_pp / 2.0;
    let startup_source = vaux_max - vf_min;
    let startup_current = startup_source / r_boot;
    let startup_energy = 0.5 * c_max * startup_source * startup_source;
    println!("{{\"vaux_min_v\":{vaux_min:.6},\"source_min_v\":{source_min:.6},\"c_min_f\":{c_min:.9},\"c_max_f\":{c_max:.9},\"hold_current_a\":{i_hold:.9},\"half_cycle_s\":{half_cycle:.9},\"charge_removed_c\":{q_removed:.9},\"droop_v\":{droop:.9},\"equilibrium_v\":{equilibrium:.6},\"vboot_start_v\":{v_start:.6},\"vboot_hold_end_v\":{v_hold_end:.6},\"vboot_recharge_end_v\":{v_recharge_end:.6},\"uvlo_v\":{uvlo:.3},\"uvlo_design_min_v\":{uvlo_design_min:.3},\"uvlo_margin_v\":{:.6},\"design_margin_v\":{:.6},\"recharge_current_start_a\":{recharge_current_at_start:.6},\"recharge_time_to_design_min_s\":{recharge_time_to_uvlo:.9},\"recharge_tau_s\":{tau:.9},\"startup_source_v\":{startup_source:.6},\"startup_current_a\":{startup_current:.6},\"startup_energy_j\":{startup_energy:.6}}}", v_hold_end - uvlo, v_hold_end - uvlo_design_min);
}
