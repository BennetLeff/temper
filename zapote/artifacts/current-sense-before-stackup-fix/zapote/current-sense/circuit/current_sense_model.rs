//! Bounded analytical model for the standalone current-sense source proposal.
//!
//! This is deliberately dependency-free so it can be replayed with `rustc`.
//! It models a bounded DC transfer function and both comparator polarities.
//! It is not a SPICE model and does not assert device timing, CT ratio or
//! magnetizing-current/frequency behavior, hysteresis, clamp energy, or
//! hardware qualification.

#[derive(Clone, Copy)]
struct Params {
    vcc: f64,
    burden_ohm: f64,
    bias_top_ohm: f64,
    bias_bottom_ohm: f64,
    hi_top_ohm: f64,
    hi_bottom_ohm: f64,
    lo_top_ohm: f64,
    lo_bottom_ohm: f64,
    sense_series_ohm: f64,
    host_load_a: f64,
    ratio: f64,
}

const TLV_VOS_MAX_V: f64 = 0.004;
const TLV_CMRR_MIN_DB: f64 = 56.0;
const TRIP_COMMON_MODE_DELTA_V: f64 = 0.7521;

fn cmrr_error_bound_v(common_mode_delta_v: f64, cmrr_db: f64) -> f64 {
    common_mode_delta_v / 10_f64.powf(cmrr_db / 20.0)
}

fn divider(vcc: f64, top: f64, bottom: f64) -> f64 {
    vcc * bottom / (top + bottom)
}

fn divider_loaded(vcc: f64, top: f64, bottom: f64, load_a: f64) -> f64 {
    let r_th = top * bottom / (top + bottom);
    divider(vcc, top, bottom) - load_a * r_th
}

fn trip_currents(
    p: Params,
    bias_load_a: f64,
    hi_load_a: f64,
    lo_load_a: f64,
    positive_offset_v: f64,
    negative_offset_v: f64,
) -> (f64, f64) {
    let bias = divider_loaded(p.vcc, p.bias_top_ohm, p.bias_bottom_ohm, bias_load_a);
    let hi = divider_loaded(p.vcc, p.hi_top_ohm, p.hi_bottom_ohm, hi_load_a);
    let lo = divider_loaded(p.vcc, p.lo_top_ohm, p.lo_bottom_ohm, lo_load_a);
    // Two comparator inputs share SENSE_MON. Their bounded input-bias current
    // flows through the 1 kΩ series resistor and the CT burden. This is a
    // deliberately conservative signed source offset.
    // Clamp leakage, host monitor loading, and comparator input bias all
    // traverse the bias Thevenin resistance and the 1 kΩ + burden source
    // path. Their signed sum is swept independently below. Host loading is
    // bounded to 0.35 uA, corresponding to a >=10 Mohm monitor input.
    let source_load_a = bias_load_a;
    let sense_offset_v = source_load_a * (p.sense_series_ohm + p.burden_ohm);
    // KCL at the loaded source is:
    //   VBIAS = VBIAS0 - I_load*Rth
    //   SENSE = VBIAS + Vsignal - I_load*(Rseries + Rburden)
    // Solving SENSE=HI and SENSE=LO for the positive and negative signal
    // magnitudes therefore adds the source-path drop for the positive
    // polarity and subtracts it for the negative polarity.  Keep these
    // signs explicit: a load that pulls VBIAS down must move the two trip
    // directions apart, rather than canceling the source-path drop.
    let positive = (hi - bias + sense_offset_v - positive_offset_v) * p.ratio / p.burden_ohm;
    let negative = (bias - lo - sense_offset_v + negative_offset_v) * p.ratio / p.burden_ohm;
    (positive, negative)
}

fn corner(value: f64, tolerance: f64, high: bool) -> f64 {
    if high {
        value * (1.0 + tolerance)
    } else {
        value * (1.0 - tolerance)
    }
}

fn main() {
    let nominal = Params {
        vcc: 3.3,
        burden_ohm: 1.50,
        bias_top_ohm: 1_000.0,
        bias_bottom_ohm: 1_000.0,
        hi_top_ohm: 3_740.0,
        hi_bottom_ohm: 10_000.0,
        lo_top_ohm: 10_000.0,
        lo_bottom_ohm: 3_740.0,
        sense_series_ohm: 1_000.0,
        host_load_a: 0.0,
        ratio: 100.0,
    };
    let (positive_nominal, negative_nominal) = trip_currents(nominal, 0.0, 0.0, 0.0, 0.0, 0.0);

    let mut min_trip = f64::INFINITY;
    let mut max_trip = f64::NEG_INFINITY;
    let mut min_positive = f64::INFINITY;
    let mut max_positive = f64::NEG_INFINITY;
    let mut min_negative = f64::INFINITY;
    let mut max_negative = f64::NEG_INFINITY;
    // Sixteen independent bits: burden, two bias legs, four threshold legs,
    // rail, 4 uA total BAT54H clamp leakage, >=10 Mohm host monitor loading,
    // 10 nA combined TLV3201 input bias at SENSE_MON, 5 nA at each threshold
    // input, and signed comparator input error for each polarity. The diode
    // leakage bound is the 25 C data-sheet condition; do not extend this
    // result to a hot enclosure without hot-leakage qualification. CT ratio,
    // magnetizing current, frequency response, hysteresis, and unspecified
    // component tolerances are intentionally outside this model.
    let comparator_error_bound_v =
        TLV_VOS_MAX_V + cmrr_error_bound_v(TRIP_COMMON_MODE_DELTA_V, TLV_CMRR_MIN_DB);
    for mask in 0_u32..65536 {
        let mut p = nominal;
        p.vcc = corner(nominal.vcc, 0.05, mask & 128 != 0);
        p.burden_ohm = corner(nominal.burden_ohm, 0.01, mask & 1 != 0);
        p.bias_top_ohm = corner(nominal.bias_top_ohm, 0.001, mask & 2 != 0);
        p.bias_bottom_ohm = corner(nominal.bias_bottom_ohm, 0.001, mask & 4 != 0);
        p.hi_top_ohm = corner(nominal.hi_top_ohm, 0.001, mask & 8 != 0);
        p.hi_bottom_ohm = corner(nominal.hi_bottom_ohm, 0.001, mask & 16 != 0);
        p.lo_top_ohm = corner(nominal.lo_top_ohm, 0.001, mask & 32 != 0);
        p.lo_bottom_ohm = corner(nominal.lo_bottom_ohm, 0.001, mask & 64 != 0);
        p.sense_series_ohm = corner(nominal.sense_series_ohm, 0.01, mask & 32768 != 0);
        let clamp_leakage_a = if mask & 256 != 0 { 4e-6 } else { -4e-6 };
        p.host_load_a = if mask & 512 != 0 { 0.35e-6 } else { -0.35e-6 };
        let sense_input_bias_a = if mask & 1024 != 0 { 10e-9 } else { -10e-9 };
        let hi_input_bias_a = if mask & 2048 != 0 { 5e-9 } else { -5e-9 };
        let lo_input_bias_a = if mask & 4096 != 0 { 5e-9 } else { -5e-9 };
        let positive_offset_v = if mask & 8192 != 0 {
            comparator_error_bound_v
        } else {
            -comparator_error_bound_v
        };
        let negative_offset_v = if mask & 16384 != 0 {
            comparator_error_bound_v
        } else {
            -comparator_error_bound_v
        };
        let bias_load_a = clamp_leakage_a + p.host_load_a + sense_input_bias_a;
        let (pos, neg) = trip_currents(
            p,
            bias_load_a,
            hi_input_bias_a,
            lo_input_bias_a,
            positive_offset_v,
            negative_offset_v,
        );
        min_trip = min_trip.min(pos).min(neg);
        max_trip = max_trip.max(pos).max(neg);
        min_positive = min_positive.min(pos);
        max_positive = max_positive.max(pos);
        min_negative = min_negative.min(neg);
        max_negative = max_negative.max(neg);
    }

    let v_sense_0 = nominal.vcc / 2.0;
    let v_sense_88 = v_sense_0 + 88.0 * nominal.burden_ohm / nominal.ratio;
    let v_sense_m88 = v_sense_0 - 88.0 * nominal.burden_ohm / nominal.ratio;
    let burden_power_at_28_76 =
        (28.76 / nominal.ratio / 2.0_f64.sqrt()).powi(2) * nominal.burden_ohm;
    let bias_r_th = nominal.bias_top_ohm * nominal.bias_bottom_ohm
        / (nominal.bias_top_ohm + nominal.bias_bottom_ohm);
    let host_load_drop_at_88a =
        0.35e-6 * (bias_r_th + nominal.sense_series_ohm + nominal.burden_ohm);
    let cmrr_error_bound = cmrr_error_bound_v(TRIP_COMMON_MODE_DELTA_V, TLV_CMRR_MIN_DB);

    println!(
        "{{\"schema\":\"current_sense_unit_model.v3\",\"nominal_trip_a\":{{\"positive\":{positive_nominal:.9},\"negative\":{negative_nominal:.9}}},\"corner_trip_a\":{{\"min\":{min_trip:.9},\"max\":{max_trip:.9},\"positive_min\":{min_positive:.9},\"positive_max\":{max_positive:.9},\"negative_min\":{min_negative:.9},\"negative_max\":{max_negative:.9}}},\"sense_voltage_at_88a_v\":{{\"positive\":{v_sense_88:.9},\"negative\":{v_sense_m88:.9},\"host_load_bound_drop\":{host_load_drop_at_88a:.9}}},\"burden_power_at_28_76a_peak_w\":{burden_power_at_28_76:.9},\"modeled_bounds\":{{\"bat54h_total_reverse_leakage_a_at_25c\":0.000004,\"tlv3201_input_bias_a_per_input\":0.000000005,\"sense_input_bias_a_combined\":0.00000001,\"tlv3201_input_offset_max_v_at_vcm_midpoint\":{TLV_VOS_MAX_V},\"tlv3201_cmrr_min_db\":{TLV_CMRR_MIN_DB},\"cmrr_error_bound_v\":{cmrr_error_bound:.9},\"effective_comparator_error_bound_v\":{comparator_error_bound_v:.9},\"host_monitor_min_ohm\":10000000.0,\"host_monitor_load_bound_a\":0.00000035}},\"requirements\":{{\"trip_window_a\":[45.0,55.0],\"frequency_hz\":[20000.0,100000.0],\"ct_sensed_current_a\":88.0}},\"verdicts\":{{\"trip_corners_in_window\":{},\"trip_result_scope\":\"conditional_bounded_dc_corner_only\",\"overall_requirement\":\"INDETERMINATE\",\"both_polarities_modeled\":true,\"leakage_applicability\":\"25C_only_until_hot_data\",\"offset_cmrr_applicability\":\"conditional_at_3v3_nonmidpoint_commonmode\",\"physical_timing\":\"INDETERMINATE\",\"physical_isolation_pd3_12_6mm\":\"INDETERMINATE\",\"hardware_tests\":\"NOT_RUN\"}}}}",
        min_trip >= 45.0 && max_trip <= 55.0,
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nominal_trip_is_near_50a_for_both_polarities() {
        let p = Params {
            vcc: 3.3,
            burden_ohm: 1.50,
            bias_top_ohm: 1_000.0,
            bias_bottom_ohm: 1_000.0,
            hi_top_ohm: 3_740.0,
            hi_bottom_ohm: 10_000.0,
            lo_top_ohm: 10_000.0,
            lo_bottom_ohm: 3_740.0,
            sense_series_ohm: 1_000.0,
            host_load_a: 0.0,
            ratio: 100.0,
        };
        let (pos, neg) = trip_currents(p, 0.0, 0.0, 0.0, 0.0, 0.0);
        assert!((pos - 50.0).abs() < 1.0);
        assert!((neg - 50.0).abs() < 1.0);
    }

    #[test]
    fn current_waveform_stays_inside_rail_for_ct_rating() {
        let v_hi = 3.3 / 2.0 + 88.0 * 1.50 / 100.0;
        let v_lo = 3.3 / 2.0 - 88.0 * 1.50 / 100.0;
        assert!(v_hi < 3.3 + 0.2);
        assert!(v_lo > -0.2);
    }

    #[test]
    fn modeled_25c_leakage_stays_inside_trip_window() {
        let p = Params {
            vcc: 3.3,
            burden_ohm: 1.50,
            bias_top_ohm: 1_000.0,
            bias_bottom_ohm: 1_000.0,
            hi_top_ohm: 3_740.0,
            hi_bottom_ohm: 10_000.0,
            lo_top_ohm: 10_000.0,
            lo_bottom_ohm: 3_740.0,
            sense_series_ohm: 1_000.0,
            host_load_a: 0.0,
            ratio: 100.0,
        };
        for &bias_load in &[-4e-6, 4e-6] {
            for &sense_bias in &[-10e-9, 10e-9] {
                let error =
                    TLV_VOS_MAX_V + cmrr_error_bound_v(TRIP_COMMON_MODE_DELTA_V, TLV_CMRR_MIN_DB);
                let (pos, neg) =
                    trip_currents(p, bias_load + sense_bias, 5e-9, -5e-9, error, -error);
                assert!((45.0..=55.0).contains(&pos));
                assert!((45.0..=55.0).contains(&neg));
            }
        }
    }

    #[test]
    fn host_monitor_bound_is_explicitly_small() {
        let drop = 0.35e-6 * (500.0 + 1_000.0 + 1.50);
        assert!((drop - 0.000525525_f64).abs() < 1e-12);
        assert!(drop < 1e-3);
    }

    #[test]
    fn directional_load_moves_positive_and_negative_trips_apart() {
        let p = Params {
            vcc: 3.3,
            burden_ohm: 1.50,
            bias_top_ohm: 1_000.0,
            bias_bottom_ohm: 1_000.0,
            hi_top_ohm: 3_740.0,
            hi_bottom_ohm: 10_000.0,
            lo_top_ohm: 10_000.0,
            lo_bottom_ohm: 3_740.0,
            sense_series_ohm: 1_000.0,
            host_load_a: 0.0,
            ratio: 100.0,
        };
        let (pos0, neg0) = trip_currents(p, 0.0, 0.0, 0.0, 0.0, 0.0);
        let (pos_plus, neg_plus) = trip_currents(p, 4e-6, 0.0, 0.0, 0.0, 0.0);
        let (pos_minus, neg_minus) = trip_currents(p, -4e-6, 0.0, 0.0, 0.0, 0.0);
        assert!(pos_plus > pos0 && neg_plus < neg0);
        assert!(pos_minus < pos0 && neg_minus > neg0);
    }

    #[test]
    fn signed_kcl_oracle_matches_each_comparator_crossing() {
        let p = Params {
            vcc: 3.3,
            burden_ohm: 1.50,
            bias_top_ohm: 1_000.0,
            bias_bottom_ohm: 1_000.0,
            hi_top_ohm: 3_740.0,
            hi_bottom_ohm: 10_000.0,
            lo_top_ohm: 10_000.0,
            lo_bottom_ohm: 3_740.0,
            sense_series_ohm: 1_000.0,
            host_load_a: 0.0,
            ratio: 100.0,
        };
        let load = 4e-6;
        let bias = divider_loaded(p.vcc, p.bias_top_ohm, p.bias_bottom_ohm, load);
        let hi = divider(p.vcc, p.hi_top_ohm, p.hi_bottom_ohm);
        let lo = divider(p.vcc, p.lo_top_ohm, p.lo_bottom_ohm);
        let source_drop = load * (p.sense_series_ohm + p.burden_ohm);
        let (pos, neg) = trip_currents(p, load, 0.0, 0.0, 0.0, 0.0);
        let positive_signal = pos * p.burden_ohm / p.ratio;
        let negative_signal = -neg * p.burden_ohm / p.ratio;
        let positive_sense = bias + positive_signal - source_drop;
        let negative_sense = bias + negative_signal - source_drop;
        assert!((positive_sense - hi).abs() < 1e-12);
        assert!((negative_sense - lo).abs() < 1e-12);
    }
}
