//! Attempt-scoped passive cooling budget derivation.

const AMBIENT_C: f64 = 40.0;
const THETA_SA_FORCED: f64 = 0.16;
const RECORDED_AIR_RISE_K: f64 = 1.9431851439784267;
const REFERENCE_TOTAL_W: f64 = 110.6;

fn air_rise_coefficient_k_per_w() -> f64 { RECORDED_AIR_RISE_K / REFERENCE_TOTAL_W }
fn sink_c(total_heat_w: f64) -> f64 {
    AMBIENT_C + (THETA_SA_FORCED + air_rise_coefficient_k_per_w()) * total_heat_w
}
fn allowable_heat_w(limit_c: f64) -> f64 {
    (limit_c - AMBIENT_C) / (THETA_SA_FORCED + air_rise_coefficient_k_per_w())
}

fn main() {
    let bridge_and_fan_w = 45.6;
    let stw_low_w = 112.90499166572496;
    let stw_high_w = 157.43656708737427;
    println!("{{");
    println!("  \"air_rise_coefficient_k_per_w\": {:.15},", air_rise_coefficient_k_per_w());
    println!("  \"screen_sink_c\": {:.15},", sink_c(110.6));
    println!("  \"allowable_total_at_60c_w\": {:.15},", allowable_heat_w(60.0));
    println!("  \"natural_catalog_allowable_at_60c_w\": 40.0,");
    println!("  \"stw_screen_total_low_w\": {:.15},", bridge_and_fan_w + stw_low_w);
    println!("  \"stw_screen_total_high_w\": {:.15},", bridge_and_fan_w + stw_high_w);
    println!("  \"stw_sink_low_c\": {:.15},", sink_c(bridge_and_fan_w + stw_low_w));
    println!("  \"stw_sink_high_c\": {:.15}", sink_c(bridge_and_fan_w + stw_high_w));
    println!("}}");
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retained_screen_reproduces_sink() { assert!((sink_c(110.6) - 59.63918514397842).abs() < 1e-12); }
    #[test]
    fn capacity_scales_air_rise_with_heat() { assert!((allowable_heat_w(60.0) - 112.63196429910035).abs() < 1e-12); }
    #[test]
    fn stw_sensitivity_is_above_screen() {
        assert!(sink_c(45.6 + 112.90499166572496) > 60.0);
        assert!(sink_c(45.6 + 157.43656708737427) > 60.0);
    }
}
