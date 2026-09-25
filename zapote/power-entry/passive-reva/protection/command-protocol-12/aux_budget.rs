//! Conditional static arithmetic; no claim about actual eFuse turnoff or VOUT peak.
fn main() {
    let top_min = 130_000.0 * 0.99;
    let top_max = 130_000.0 * 1.01;
    let bottom_min = 10_000.0 * 0.99;
    let bottom_max = 10_000.0 * 1.01;
    let leakage = 100e-9;
    // KCL: Vtrip = Vthreshold*(1+Rtop/Rbottom) + Ipin*Rtop.
    let min = 1.17 * (1.0 + top_min / bottom_max) - leakage * top_min;
    let max = 1.225 * (1.0 + top_max / bottom_min) + leakage * top_max;
    let rth = top_min * bottom_max / (top_min + bottom_max);
    let normal_pin_max = 15.75 * bottom_max / (top_min + bottom_max) + leakage * rth;
    println!("quantity,value,unit,scope");
    println!("trip_min,{min:.6},V,conditional_static");
    println!("trip_max,{max:.6},V,conditional_static");
    println!("normal_pin_max,{normal_pin_max:.6},V,at_AUX15.75");
    println!("normal_pin_margin,{:.6},V,against_min_OVP1.17", 1.17-normal_pin_max);
    println!("trip_to_18_margin,{:.6},V,not_a_transient_bound", 18.0-max);
    for capacitance_uf in [1.0, 10.0, 47.0] {
        println!("net_charge_allowance_at_{capacitance_uf:.0}uF,{:.6},uC,hypothetical_effective_downstream_C_start15.75V_no_parasitics", (18.0-15.75)*capacitance_uf);
    }
    let budget_ma = 75.0 + 5.0*75.0/(0.7*14.625);
    println!("legacy_conditional_downstream_load,{budget_ma:.6},mA,excludes_new_isolator_and_unbounded_startup");
    println!("ilim120k_active_limit_min,85,mA,less_than_conditional_load");
    println!("ilim120k_circuit_breaker_min,45,mA,less_than_conditional_load");
}
