//! Pure-Rust IPC standard calculations for PCB design — core logic extracted from temper-ipc.
//!
//! Tests live here.  The pyo3 wrappers in `temper-ipc` are thin adapters.

use std::collections::HashMap;

/// Calculate maximum current capacity using IPC-2221 formula.
///
/// I = k * ΔT^0.44 * A^0.725  where A is cross-sectional area in mils².
pub fn estimate_trace_current(
    width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> f64 {
    let width_mils = width_mm * 39.3701;
    let thickness_mils = thickness_oz * 1.37;
    let area_mils2 = width_mils * thickness_mils;
    let k = if internal_layer { 0.024 } else { 0.048 };
    k * temp_rise_c.powf(0.44) * area_mils2.powf(0.725)
}

/// Conservative current estimate (internal layer, 1oz, 10°C rise).
pub fn estimate_current_from_net_class(
    trace_width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
) -> f64 {
    estimate_trace_current(trace_width_mm, thickness_oz, temp_rise_c, true)
}

/// Pre-computed lookup table for 1oz copper, 10°C rise, internal layers.
pub fn trace_current_table_1oz() -> HashMap<String, f64> {
    let mut map = HashMap::new();
    map.insert("0.15".into(), 0.7);
    map.insert("0.2".into(), 1.0);
    map.insert("0.25".into(), 1.2);
    map.insert("0.4".into(), 2.0);
    map.insert("0.5".into(), 2.5);
    map.insert("1.0".into(), 5.0);
    map.insert("2.0".into(), 9.5);
    map.insert("3.0".into(), 14.0);
    map.insert("5.0".into(), 22.0);
    map.insert("10.0".into(), 42.0);
    map
}

/// Calculate minimum trace width for a given current using IPC-2152.
pub fn calculate_min_trace_width(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> f64 {
    if current_amps <= 0.0 {
        return 0.0;
    }
    let k = if internal_layer { 0.024 } else { 0.048 };
    let area_mils2 = (current_amps / (k * temp_rise_c.powf(0.44))).powf(1.0 / 0.725);
    let thickness_mils = copper_weight_oz * 1.37;
    let width_mils = area_mils2 / thickness_mils;
    width_mils / 39.3701
}

/// Per-net expected currents from W2 R3 requirements.
///
/// Peak currents for switching nets, RMS for AC, average for supply rails.
pub fn net_currents() -> HashMap<String, f64> {
    let mut map = HashMap::new();
    map.insert("DC_BUS+".into(), 16.0);
    map.insert("AC_L".into(), 10.0);
    map.insert("AC_N".into(), 10.0);
    map.insert("SW_NODE".into(), 16.0);
    map.insert("GATE_H".into(), 2.0);
    map.insert("GATE_L".into(), 2.0);
    map.insert("+3V3".into(), 0.5);
    map.insert("+5V".into(), 0.5);
    map.insert("+15V".into(), 0.2);
    map
}

/// Default current for unlisted signal nets (100 mA).
pub const DEFAULT_SIGNAL_CURRENT: f64 = 0.1;

/// Resolve expected current for a net from the W2 current table.
///
/// Performs case-insensitive substring matching against net_currents().
/// Falls back to DEFAULT_SIGNAL_CURRENT (100 mA) for unlisted nets.
pub fn get_net_current(net_name: &str) -> f64 {
    let name_upper = net_name.to_uppercase();
    for (key, current) in net_currents() {
        if name_upper.contains(&key) {
            return current;
        }
    }
    DEFAULT_SIGNAL_CURRENT
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_estimate_external_1oz_10c() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, false);
        assert!((i - 0.87).abs() < 0.01, "external 0.25mm should be ~0.87A, got {i}");
    }

    #[test]
    fn test_estimate_internal_conservative() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, true);
        assert!((i - 0.44).abs() < 0.01, "internal 0.25mm should be ~0.44A, got {i}");
    }

    #[test]
    fn test_estimate_from_net_class() {
        let i = estimate_current_from_net_class(0.25, 1.0, 10.0);
        assert_eq!(i, estimate_trace_current(0.25, 1.0, 10.0, true));
    }

    #[test]
    fn test_table_lookup() {
        let table = trace_current_table_1oz();
        assert_eq!(table["0.25"], 1.2);
        assert_eq!(table["10.0"], 42.0);
    }

    #[test]
    fn test_min_trace_width_roundtrip() {
        // Width → current → width should be approximately identity
        let width = 1.0;
        let current = estimate_trace_current(width, 1.0, 10.0, true);
        let width2 = calculate_min_trace_width(current, 1.0, 10.0, true);
        assert!((width - width2).abs() < 0.05, "round-trip error: {width} vs {width2}");
    }

    #[test]
    fn test_ipc2152_min_width_basic() {
        // Verify against Python doctest values
        let w = calculate_min_trace_width(0.5, 1.0, 10.0, false);
        assert!((w - 0.1160).abs() < 0.0001, "external 0.5A -> {w}, expected 0.1160");
        let w = calculate_min_trace_width(0.5, 1.0, 10.0, true);
        assert!((w - 0.3019).abs() < 0.0001, "internal 0.5A -> {w}, expected 0.3019");
        let w = calculate_min_trace_width(2.0, 1.0, 10.0, false);
        assert!((w - 0.784).abs() < 0.001, "external 2A -> {w}, expected 0.784");
    }

    #[test]
    fn test_ipc2152_current_capacity_roundtrip() {
        // Forward capacity round-trips with inverse
        let w = estimate_trace_current(0.1160, 1.0, 10.0, false);
        assert!((w - 0.5).abs() < 0.01, "current_capacity -> {w}, expected 0.5");
        let w = estimate_trace_current(0.784, 1.0, 10.0, false);
        assert!((w - 2.0).abs() < 0.01, "current_capacity -> {w}, expected 2.0");
    }

    #[test]
    fn test_get_net_current_exact() {
        assert!((get_net_current("DC_BUS+") - 16.0).abs() < 1e-9);
        assert!((get_net_current("AC_L") - 10.0).abs() < 1e-9);
        assert!((get_net_current("+3V3") - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_get_net_current_case_insensitive() {
        assert!((get_net_current("dc_bus+") - 16.0).abs() < 1e-9);
        assert!((get_net_current("ac_l") - 10.0).abs() < 1e-9);
    }

    #[test]
    fn test_get_net_current_substring() {
        assert!((get_net_current("+3V3_SENSE") - 0.5).abs() < 1e-9);
        assert!((get_net_current("NET_SW_NODE_1") - 16.0).abs() < 1e-9);
    }

    #[test]
    fn test_get_net_current_fallback() {
        assert!((get_net_current("RANDOM_NET") - 0.1).abs() < 1e-9);
    }

    #[test]
    fn test_get_net_current_zero_current() {
        let w = calculate_min_trace_width(0.0, 1.0, 10.0, false);
        assert_eq!(w, 0.0);
    }
}
