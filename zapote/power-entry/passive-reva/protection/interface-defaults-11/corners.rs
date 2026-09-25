//! Conditional DC screen, not a hardware certificate or transient clamp model.
fn main() {
    let rtop = 560_000.0_f64;
    let rbot = 100_000.0_f64;
    let resistance_deviation = 0.01_f64; // Required total deviation, including temperature.
    let iso_max = 22_000.0 * (1.0 + resistance_deviation);
    let rth_max = (rtop * rbot / (rtop + rbot)) * (1.0 + resistance_deviation);
    // LM4040A25I:19mV full-temperature error at100uA +1mV current change.
    // TLV3202:6mV offset and5nA per-input bias, at stated datasheet conditions.
    let reference_error = 0.020;
    let comparator_offset = 0.006;
    let bias_error = 5e-9 * (rth_max + iso_max) + 5e-9 * iso_max;
    let error = reference_error + comparator_offset + bias_error;
    let ratio_min =
        1.0 + rtop * (1.0 - resistance_deviation) / (rbot * (1.0 + resistance_deviation));
    let ratio_max =
        1.0 + rtop * (1.0 + resistance_deviation) / (rbot * (1.0 - resistance_deviation));
    let trip_min = (2.5 - error) * ratio_min;
    let trip_max = (2.5 + error) * ratio_max;
    let raw_low = 25e-6_f64 * 10_100.0;
    let decay_us = 10_100.0 * 1e-9 * ((5.5 - raw_low) / (1.51 - raw_low)).ln() * 1e6;
    let minimum_reference_bias_ua = (4.75 - 2.52) / 10_100.0 * 1e6 - 4.0 * 0.005;
    println!("{{\n  \"status\": \"conditional static screen; no timing or noise bound\",\n  \"nominal_ov_trip_v\": 16.5,\n  \"trip_min_v\": {trip_min:.6},\n  \"trip_max_v\": {trip_max:.6},\n  \"normal_upper_margin_v\": {:.6},\n  \"driver_18v_margin_v\": {:.6},\n  \"raw_low_at_25ua_v\": {raw_low:.6},\n  \"decay_to_1v51_at_1nf_us\": {decay_us:.6},\n  \"minimum_reference_bias_ua\": {minimum_reference_bias_ua:.6}\n}}", trip_min-15.75,18.0-trip_max);
    assert!(trip_min > 15.75 && trip_max < 18.0);
    assert!(raw_low < 0.3 && minimum_reference_bias_ua > 80.0);
}
