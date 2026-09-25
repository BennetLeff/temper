//! Conditional load screens, never a complete supply-current guarantee.
fn main() {
    let aux_max = 15.75;
    let relay_upper_at_23c = aux_max / (360.0 * 0.90 + 91.0 * 0.99);
    let disable_upper = aux_max / (1000.0 * 0.99);
    let residual = 0.075 - relay_upper_at_23c - disable_upper;
    let fs_nominal = 129_107.0;
    println!("quantity,value,unit,scope");
    println!(
        "relay_current_screen,{:.6},mA,23C_coil_minus10pct_dropR_minus1pct_zero_FETdrop",
        1000.0 * relay_upper_at_23c
    );
    println!(
        "disable_pullup_screen,{:.6},mA,aux15.75_Rminus1pct_zero_FETdrop",
        1000.0 * disable_upper
    );
    println!(
        "remaining_in_75mA_after_two_terms,{:.6},mA,not_available_margin_until_other_loads_bounded",
        1000.0 * residual
    );
    println!(
        "gate_charge_example,{:.6},mA,120nC_typical_at10V_and_nominal129107Hz_not_bound",
        120e-9 * fs_nominal * 1000.0
    );
    for other_ma in [5.0, 10.0, 15.0] {
        let charge_nc = (residual - other_ma / 1000.0) / fs_nominal * 1e9;
        println!("qg_allowance_other_{other_ma:.0}mA,{charge_nc:.6},nC,sensitivity_not_part_spec");
    }
    let prior = 0.075 + 5.0 * 0.075 / (0.7 * 14.625);
    let revised = 0.075 + 5.25 * 0.075 / (0.7 * 14.25);
    println!(
        "prior_conditional_load,{:.6},mA,nominal5V_and14.625V",
        prior * 1000.0
    );
    println!(
        "revised_conditional_load,{:.6},mA,logic5max5.25_and_protectedauxmin14.25_eta_assumed70pct",
        revised * 1000.0
    );
    println!(
        "all_path_R_max,{:.6},ohm,zero_switch_wire_drop_and_no_added_load",
        (14.625 - 14.25) / revised
    );
    println!(
        "logic_bleed_current,{:.6},mA,5.25V_220ohm_minus1pct",
        5.25 / (220.0 * 0.99) * 1000.0
    );
}
