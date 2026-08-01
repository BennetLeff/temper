//! RTD safety model (Wave 2, thermal/RTD validators slice).
//!
//! Python reference: `temper_placer/validation/rtd_safety.py` — the
//! deterministic PT100/MAX31865 safety-threshold model behind the
//! THM-adjacent thermal protection chain. Ported pieces: the pure
//! numeric functions (`resistance_to_code`, `max31865_rtd_*`,
//! `hardware_window_voltage`, `reference_divider_voltage_v`,
//! `spi_rc_rise_time_ns`, `threshold_adc_codes`) and the two window
//! derivations (`derive_hardware_window`, `derive_max31865_hardware_window`).
//! The corner dataclasses, ValueError validation guards, and the digital
//! state machines stay Python (logic, not math).
//!
//! Bit-exactness: identical f64 operation order throughout; the
//! derivations return an overlap status code (0=ok, 1=low overlap,
//! 2=high overlap) so the Python wrapper can raise the exact reference
//! ValueError messages.

use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// Pure numeric core
// ---------------------------------------------------------------------------

/// MAX31865 15-bit resistance code: floor(32768 * R / Rref), clamped.
fn resistance_to_code(resistance_ohm: f64, rref_ohm: f64) -> i64 {
    if resistance_ohm <= 0.0 {
        return 0;
    }
    let full_scale = (1 << 15) as f64;
    let code = (full_scale * resistance_ohm / rref_ohm).floor() as i64;
    code.min((1 << 15) - 1)
}

/// RTD excitation current from the MAX31865 voltage-source topology.
fn max31865_rtd_current_a(resistance_ohm: f64, vbias_v: f64, rref_ohm: f64) -> f64 {
    vbias_v / (rref_ohm + resistance_ohm)
}

/// RTD-drop voltage: R * I.
fn max31865_rtd_voltage_v(resistance_ohm: f64, vbias_v: f64, rref_ohm: f64) -> f64 {
    resistance_ohm * max31865_rtd_current_a(resistance_ohm, vbias_v, rref_ohm)
}

/// Voltage seen by a high-impedance redundant window comparator.
fn hardware_window_voltage(resistance_ohm: f64, excitation_a: f64) -> f64 {
    resistance_ohm * excitation_a
}

/// Grounded two-resistor threshold from REF2025 VBIAS.
fn reference_divider_voltage_v(reference_v: f64, top_ohm: f64, bottom_ohm: f64) -> f64 {
    reference_v * bottom_ohm / (top_ohm + bottom_ohm)
}

/// 10--90% lumped-RC rise time in ns for one MAX31865 SPI line.
fn spi_rc_rise_time_ns(driver_output_ohm: f64, series_resistor_ohm: f64, load_capacitance_pf: f64) -> f64 {
    // ohm * pF is ps, so divide by 1000 to return ns.
    2.2 * (driver_output_ohm + series_resistor_ohm) * load_capacitance_pf / 1000.0
}

/// Inclusive low/high 15-bit ADC codes (ceil for low, floor for high).
fn threshold_adc_codes(rref_ohm: f64, short_ohm: f64, open_ohm: f64) -> (i64, i64) {
    let full_scale = (1 << 15) as f64;
    let low = (full_scale * short_ohm / rref_ohm).ceil() as i64;
    let high = (full_scale * open_ohm / rref_ohm).floor() as i64;
    (low, high)
}

// ---------------------------------------------------------------------------
// Window derivations
// ---------------------------------------------------------------------------

/// Derive the fault-safe comparator window. Mirrors
/// `derive_hardware_window`'s arithmetic exactly (the Python wrapper
/// performs the corner validation and raises the reference ValueErrors).
/// Returns (low_trip_v, high_trip_v, status) with status 0=ok,
/// 1=low-window overlap, 2=high-window overlap.
fn derive_hardware_window(
    bias_current_min_a: f64,
    bias_current_max_a: f64,
    comparator_offset_abs_v: f64,
    divider_tolerance_fraction: f64,
    required_margin_fraction: f64,
    short_max_ohm: f64,
    valid_min_ohm: f64,
    valid_max_ohm: f64,
    open_min_ohm: f64,
) -> (f64, f64, i64) {
    let current_min = bias_current_min_a;
    let current_max = bias_current_max_a;
    let offset = comparator_offset_abs_v;
    let divider_low = 1.0 - divider_tolerance_fraction;
    let divider_high = 1.0 + divider_tolerance_fraction;
    let margin = 1.0 + required_margin_fraction;

    let short_voltage_max = hardware_window_voltage(short_max_ohm, current_max);
    let valid_voltage_min = hardware_window_voltage(valid_min_ohm, current_min);
    let valid_voltage_max = hardware_window_voltage(valid_max_ohm, current_max);
    let open_voltage_min = hardware_window_voltage(open_min_ohm, current_min);

    let low_nominal_min = (short_voltage_max + offset) / divider_low;
    let low_nominal_max = (valid_voltage_min / margin - offset) / divider_high;
    let high_nominal_min = (valid_voltage_max * margin + offset) / divider_low;
    let high_nominal_max = (open_voltage_min - offset) / divider_high;

    if low_nominal_min > low_nominal_max {
        return (0.0, 0.0, 1);
    }
    if high_nominal_min > high_nominal_max {
        return (0.0, 0.0, 2);
    }
    (
        (low_nominal_min + low_nominal_max) / 2.0,
        (high_nominal_min + high_nominal_max) / 2.0,
        0,
    )
}

/// MAX31865 VBIAS/RREF variant of the derivation.
fn derive_max31865_hardware_window(
    comparator_offset_abs_v: f64,
    divider_tolerance_fraction: f64,
    vbias_min_v: f64,
    vbias_max_v: f64,
    rref_nominal_ohm: f64,
    rref_tolerance_fraction: f64,
    short_max_ohm: f64,
    valid_min_ohm: f64,
    valid_max_ohm: f64,
    open_min_ohm: f64,
    required_margin_fraction: f64,
) -> (f64, f64, i64) {
    let rref_min = rref_nominal_ohm * (1.0 - rref_tolerance_fraction);
    let rref_max = rref_nominal_ohm * (1.0 + rref_tolerance_fraction);
    let offset = comparator_offset_abs_v;
    let divider_low = 1.0 - divider_tolerance_fraction;
    let divider_high = 1.0 + divider_tolerance_fraction;
    let margin = 1.0 + required_margin_fraction;

    let short_voltage_max = max31865_rtd_voltage_v(short_max_ohm, vbias_max_v, rref_min);
    let valid_voltage_min = max31865_rtd_voltage_v(valid_min_ohm, vbias_min_v, rref_max);
    let valid_voltage_max = max31865_rtd_voltage_v(valid_max_ohm, vbias_max_v, rref_min);
    let open_voltage_min = max31865_rtd_voltage_v(open_min_ohm, vbias_min_v, rref_max);

    let low_nominal_min = (short_voltage_max + offset) / divider_low;
    let low_nominal_max = (valid_voltage_min / margin - offset) / divider_high;
    let high_nominal_min = (valid_voltage_max * margin + offset) / divider_low;
    let high_nominal_max = (open_voltage_min - offset) / divider_high;

    if low_nominal_min > low_nominal_max {
        return (0.0, 0.0, 1);
    }
    if high_nominal_min > high_nominal_max {
        return (0.0, 0.0, 2);
    }
    (
        (low_nominal_min + low_nominal_max) / 2.0,
        (high_nominal_min + high_nominal_max) / 2.0,
        0,
    )
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[pyfunction]
#[pyo3(signature = (resistance_ohm, rref_ohm))]
pub fn rtd_resistance_to_code_py(resistance_ohm: f64, rref_ohm: f64) -> i64 {
    resistance_to_code(resistance_ohm, rref_ohm)
}

#[pyfunction]
#[pyo3(signature = (resistance_ohm, vbias_v, rref_ohm))]
pub fn rtd_max31865_current_a_py(resistance_ohm: f64, vbias_v: f64, rref_ohm: f64) -> f64 {
    max31865_rtd_current_a(resistance_ohm, vbias_v, rref_ohm)
}

#[pyfunction]
#[pyo3(signature = (resistance_ohm, vbias_v, rref_ohm))]
pub fn rtd_max31865_voltage_v_py(resistance_ohm: f64, vbias_v: f64, rref_ohm: f64) -> f64 {
    max31865_rtd_voltage_v(resistance_ohm, vbias_v, rref_ohm)
}

#[pyfunction]
#[pyo3(signature = (resistance_ohm, excitation_a))]
pub fn rtd_hardware_window_voltage_py(resistance_ohm: f64, excitation_a: f64) -> f64 {
    hardware_window_voltage(resistance_ohm, excitation_a)
}

#[pyfunction]
#[pyo3(signature = (reference_v, top_ohm, bottom_ohm))]
pub fn rtd_reference_divider_voltage_v_py(reference_v: f64, top_ohm: f64, bottom_ohm: f64) -> f64 {
    reference_divider_voltage_v(reference_v, top_ohm, bottom_ohm)
}

#[pyfunction]
#[pyo3(signature = (driver_output_ohm, series_resistor_ohm, load_capacitance_pf))]
pub fn rtd_spi_rc_rise_time_ns_py(
    driver_output_ohm: f64,
    series_resistor_ohm: f64,
    load_capacitance_pf: f64,
) -> f64 {
    spi_rc_rise_time_ns(driver_output_ohm, series_resistor_ohm, load_capacitance_pf)
}

#[pyfunction]
#[pyo3(signature = (rref_ohm, short_ohm, open_ohm))]
pub fn rtd_threshold_adc_codes_py(rref_ohm: f64, short_ohm: f64, open_ohm: f64) -> (i64, i64) {
    threshold_adc_codes(rref_ohm, short_ohm, open_ohm)
}

#[pyfunction]
#[pyo3(signature = (bias_current_min_a, bias_current_max_a, comparator_offset_abs_v, divider_tolerance_fraction, required_margin_fraction, short_max_ohm, valid_min_ohm, valid_max_ohm, open_min_ohm))]
pub fn rtd_derive_hardware_window_py(
    bias_current_min_a: f64,
    bias_current_max_a: f64,
    comparator_offset_abs_v: f64,
    divider_tolerance_fraction: f64,
    required_margin_fraction: f64,
    short_max_ohm: f64,
    valid_min_ohm: f64,
    valid_max_ohm: f64,
    open_min_ohm: f64,
) -> (f64, f64, i64) {
    derive_hardware_window(
        bias_current_min_a,
        bias_current_max_a,
        comparator_offset_abs_v,
        divider_tolerance_fraction,
        required_margin_fraction,
        short_max_ohm,
        valid_min_ohm,
        valid_max_ohm,
        open_min_ohm,
    )
}

#[pyfunction]
#[pyo3(signature = (comparator_offset_abs_v, divider_tolerance_fraction, vbias_min_v, vbias_max_v, rref_nominal_ohm, rref_tolerance_fraction, short_max_ohm, valid_min_ohm, valid_max_ohm, open_min_ohm, required_margin_fraction))]
pub fn rtd_derive_max31865_hardware_window_py(
    comparator_offset_abs_v: f64,
    divider_tolerance_fraction: f64,
    vbias_min_v: f64,
    vbias_max_v: f64,
    rref_nominal_ohm: f64,
    rref_tolerance_fraction: f64,
    short_max_ohm: f64,
    valid_min_ohm: f64,
    valid_max_ohm: f64,
    open_min_ohm: f64,
    required_margin_fraction: f64,
) -> (f64, f64, i64) {
    derive_max31865_hardware_window(
        comparator_offset_abs_v,
        divider_tolerance_fraction,
        vbias_min_v,
        vbias_max_v,
        rref_nominal_ohm,
        rref_tolerance_fraction,
        short_max_ohm,
        valid_min_ohm,
        valid_max_ohm,
        open_min_ohm,
        required_margin_fraction,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resistance_to_code() {
        // 100 ohm / 430 ohm * 32768 = 7620.4... -> 7620
        assert_eq!(resistance_to_code(100.0, 430.0), 7620);
        assert_eq!(resistance_to_code(0.0, 430.0), 0);
        // Clamped at 15-bit max.
        assert_eq!(resistance_to_code(1e6, 430.0), 32767);
    }

    #[test]
    fn test_threshold_adc_codes() {
        // short 10 ohm: ceil(32768*10/430) = ceil(762.05) = 763
        // open 300 ohm: floor(32768*300/430) = floor(22861.4) = 22861
        let (low, high) = threshold_adc_codes(430.0, 10.0, 300.0);
        assert_eq!(low, 763);
        assert_eq!(high, 22861);
        assert!(low < high);
    }

    #[test]
    fn test_max31865_voltage() {
        // 100 ohm, VBIAS 2.0, RREF 430: I = 2/530 = 3.7736e-3; V = 0.37736
        let v = max31865_rtd_voltage_v(100.0, 2.0, 430.0);
        assert!((v - 2.0 * 100.0 / 530.0).abs() < 1e-12);
    }

    #[test]
    fn test_derive_window_known_corners() {
        // 100..194.1 ohm valid window, 0.2 margin, 1 mA excitation:
        // the derived trip must sit strictly between the short and valid
        // voltage extremes.
        let (low, high, status) = derive_hardware_window(
            0.001, 0.001, 0.0, 0.0, 0.2, 10.0, 100.0, 194.1, 300.0,
        );
        assert_eq!(status, 0);
        assert!(low > 10.0 * 0.001 && low < 100.0 * 0.001);
        assert!(high > 194.1 * 0.001 && high < 300.0 * 0.001);
        assert!(low < high);
    }

    #[test]
    fn test_derive_window_overlap_detected() {
        // A 0.2 margin with an impossibly narrow valid window must overlap.
        let (_, _, status) = derive_hardware_window(
            0.001, 0.001, 0.0, 0.0, 0.2, 10.0, 10.5, 10.6, 11.0,
        );
        assert!(status == 1 || status == 2);
    }

    #[test]
    fn test_reference_divider() {
        // 1.25 * 10000 / (61900 + 10000) = 0.1739...
        let v = reference_divider_voltage_v(1.25, 61_900.0, 10_000.0);
        assert!((v - 1.25 * 10_000.0 / 71_900.0).abs() < 1e-12);
    }
}
