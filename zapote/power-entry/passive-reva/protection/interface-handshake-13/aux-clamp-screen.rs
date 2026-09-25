//! Conditional static LT4363 screen, not transient qualification or a part selection.
fn main() {
    let top_min = 60_400.0 * 0.99;
    let top_max = 60_400.0 * 1.01;
    let bottom_min = 4_990.0 * 0.99;
    let bottom_max = 4_990.0 * 1.01;
    let min = 1.25 * (1.0 + top_min / bottom_max) - 1e-6 * top_min;
    let max = 1.30 * (1.0 + top_max / bottom_min) + 1e-6 * top_max;
    assert!(min > 15.75 && max < 18.0);
    println!("quantity,value,unit,scope");
    println!("static_clamp_min,{min:.6},V,conditional_total_resistor_tolerance_1percent");
    println!("static_clamp_max,{max:.6},V,conditional_total_resistor_tolerance_1percent");
    println!("dynamic_headroom,{:.6},V,not_guaranteed_peak",18.0-max);
    println!("normal_margin,{:.6},V,not_drop_or_transient_budget",min-15.75);
}
