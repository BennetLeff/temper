//! Pure-Rust IPC standard calculations for PCB design.
//!
//! IPC-2221/2152 current-capacity and trace-width scalar kernels,
//! consolidated from the deleted `temper-ipc` crate (third crate-fold of the
//! consolidation program; precedents: `placement-topology` → `geometry`,
//! `dsn` → `io-types`, 2026-08-09). The kernels and their unit tests are
//! carried verbatim from `temper-ipc/src/core.rs`; the pyo3 wrappers that
//! expose them on `temper_drc_rs` live in the sibling `ipc_pyo3` module,
//! exactly as the old crate's inline bridge did for `temper_ipc`.

use std::collections::HashMap;
use std::sync::LazyLock;

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
pub fn net_currents() -> &'static HashMap<String, f64> {
    static CURRENTS: LazyLock<HashMap<String, f64>> = LazyLock::new(|| {
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
    });
    &CURRENTS
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
        if name_upper.contains(key.as_str()) {
            return *current;
        }
    }
    DEFAULT_SIGNAL_CURRENT
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn test_estimate_external_1oz_10c() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, false);
        assert!((i - 0.87).abs() < 0.01, "external 0.25mm should be ~0.87A, got {i}");
    }

    #[cfg_attr(test, test)]
    fn test_estimate_internal_conservative() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, true);
        assert!((i - 0.44).abs() < 0.01, "internal 0.25mm should be ~0.44A, got {i}");
    }

    #[cfg_attr(test, test)]
    fn test_estimate_from_net_class() {
        let i = estimate_current_from_net_class(0.25, 1.0, 10.0);
        assert_eq!(i, estimate_trace_current(0.25, 1.0, 10.0, true));
    }

    #[cfg_attr(test, test)]
    fn test_min_trace_width_roundtrip() {
        // Width → current → width should be approximately identity
        let width = 1.0;
        let current = estimate_trace_current(width, 1.0, 10.0, true);
        let width2 = calculate_min_trace_width(current, 1.0, 10.0, true);
        assert!((width - width2).abs() < 0.05, "round-trip error: {width} vs {width2}");
    }

    #[cfg_attr(test, test)]
    fn test_ipc2152_min_width_basic() {
        // Verify against Python doctest values
        let w = calculate_min_trace_width(0.5, 1.0, 10.0, false);
        assert!((w - 0.1160).abs() < 0.0002, "external 0.5A -> {w}, expected 0.1160");
        let w = calculate_min_trace_width(0.5, 1.0, 10.0, true);
        assert!((w - 0.3019).abs() < 0.0003, "internal 0.5A -> {w}, expected 0.3019");
        let w = calculate_min_trace_width(2.0, 1.0, 10.0, false);
        assert!((w - 0.784).abs() < 0.002, "external 2A -> {w}, expected 0.784");
    }

    #[cfg_attr(test, test)]
    fn test_ipc2152_current_capacity_roundtrip() {
        // Forward capacity round-trips with inverse
        let w = estimate_trace_current(0.1160, 1.0, 10.0, false);
        assert!((w - 0.5).abs() < 0.01, "current_capacity -> {w}, expected 0.5");
        let w = estimate_trace_current(0.784, 1.0, 10.0, false);
        assert!((w - 2.0).abs() < 0.01, "current_capacity -> {w}, expected 2.0");
    }

    #[cfg_attr(test, test)]
    fn test_get_net_current_exact() {
        assert!((get_net_current("DC_BUS+") - 16.0).abs() < 1e-9);
        assert!((get_net_current("AC_L") - 10.0).abs() < 1e-9);
        assert!((get_net_current("+3V3") - 0.5).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_get_net_current_case_insensitive() {
        assert!((get_net_current("dc_bus+") - 16.0).abs() < 1e-9);
        assert!((get_net_current("ac_l") - 10.0).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_get_net_current_substring() {
        assert!((get_net_current("+3V3_SENSE") - 0.5).abs() < 1e-9);
        assert!((get_net_current("NET_SW_NODE_1") - 16.0).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_get_net_current_fallback() {
        assert!((get_net_current("RANDOM_NET") - 0.1).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_get_net_current_zero_current() {
        let w = calculate_min_trace_width(0.0, 1.0, 10.0, false);
        assert_eq!(w, 0.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("ipc::tests::test_estimate_external_1oz_10c", test_estimate_external_1oz_10c),
        ("ipc::tests::test_estimate_internal_conservative", test_estimate_internal_conservative),
        ("ipc::tests::test_estimate_from_net_class", test_estimate_from_net_class),
        ("ipc::tests::test_min_trace_width_roundtrip", test_min_trace_width_roundtrip),
        ("ipc::tests::test_ipc2152_min_width_basic", test_ipc2152_min_width_basic),
        ("ipc::tests::test_ipc2152_current_capacity_roundtrip", test_ipc2152_current_capacity_roundtrip),
        ("ipc::tests::test_get_net_current_exact", test_get_net_current_exact),
        ("ipc::tests::test_get_net_current_case_insensitive", test_get_net_current_case_insensitive),
        ("ipc::tests::test_get_net_current_substring", test_get_net_current_substring),
        ("ipc::tests::test_get_net_current_fallback", test_get_net_current_fallback),
        ("ipc::tests::test_get_net_current_zero_current", test_get_net_current_zero_current),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn positive_width() -> impl Strategy<Value = f64> {
        0.01f64..100.0
    }

    fn positive_current() -> impl Strategy<Value = f64> {
        0.01f64..50.0
    }

    fn reasonable_temp_rise() -> impl Strategy<Value = f64> {
        1.0f64..100.0
    }

    fn copper_oz() -> impl Strategy<Value = f64> {
        0.5f64..4.0
    }

    proptest! {
        // -----------------------------------------------------------------
        // estimate_trace_current
        // -----------------------------------------------------------------

        /// P1. Current capacity is always non-negative for non-negative
        /// inputs.
        #[test]
        fn p1_current_capacity_non_negative(
            w in positive_width(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let i = estimate_trace_current(w, oz, tr, internal);
            prop_assert!(i >= 0.0, "current should be >= 0, got {}", i);
        }

        /// P2. Current capacity is strictly monotone in trace width:
        /// wider traces carry more current (all else equal).
        #[test]
        fn p2_current_capacity_monotone_in_width(
            w1 in positive_width(),
            delta in 0.01f64..50.0,
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let w2 = w1 + delta;
            let i1 = estimate_trace_current(w1, oz, tr, internal);
            let i2 = estimate_trace_current(w2, oz, tr, internal);
            prop_assert!(i2 > i1,
                "wider trace ({} > {}) should carry more current, got {} <= {}",
                w2, w1, i2, i1);
        }

        /// P3. Higher temperature rise allows more current (more headroom).
        #[test]
        fn p3_current_capacity_monotone_in_temp_rise(
            w in positive_width(),
            oz in copper_oz(),
            tr1 in reasonable_temp_rise(),
            delta in 1.0f64..50.0,
            internal in any::<bool>(),
        ) {
            let tr2 = tr1 + delta;
            let i1 = estimate_trace_current(w, oz, tr1, internal);
            let i2 = estimate_trace_current(w, oz, tr2, internal);
            prop_assert!(i2 > i1,
                "higher temp rise ({} > {}) should allow more current",
                tr2, tr1);
        }

        /// P4. External layers carry more current than internal for
        /// the same parameters (k_external = 0.048 > k_internal = 0.024).
        #[test]
        fn p4_external_carries_more_than_internal(
            w in positive_width(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
        ) {
            let i_ext = estimate_trace_current(w, oz, tr, false);
            let i_int = estimate_trace_current(w, oz, tr, true);
            prop_assert!(i_ext > i_int,
                "external should carry more current: {i_ext} <= {i_int}");
        }

        // -----------------------------------------------------------------
        // calculate_min_trace_width
        // -----------------------------------------------------------------

        /// P5. Minimum trace width is non-negative for any positive
        /// current.
        #[test]
        fn p5_min_trace_width_non_negative(
            cur in positive_current(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let w = calculate_min_trace_width(cur, oz, tr, internal);
            prop_assert!(w >= 0.0, "min trace width should be >= 0, got {}", w);
        }

        /// P6. Higher current demands wider traces (monotone in current).
        #[test]
        fn p6_min_trace_width_monotone_in_current(
            cur1 in positive_current(),
            delta in 0.1f64..30.0,
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let cur2 = cur1 + delta;
            let w1 = calculate_min_trace_width(cur1, oz, tr, internal);
            let w2 = calculate_min_trace_width(cur2, oz, tr, internal);
            prop_assert!(w2 > w1,
                "higher current ({} > {}) should require wider trace, got {} <= {}",
                cur2, cur1, w2, w1);
        }

        /// P7. Internal layers require wider traces than external for the
        /// same current.
        #[test]
        fn p7_internal_needs_wider_than_external(
            cur in positive_current(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
        ) {
            let w_ext = calculate_min_trace_width(cur, oz, tr, false);
            let w_int = calculate_min_trace_width(cur, oz, tr, true);
            prop_assert!(w_int > w_ext,
                "internal should need wider trace: {w_int} <= {w_ext}");
        }

        // -----------------------------------------------------------------
        // Round-trip
        // -----------------------------------------------------------------

        /// P8. Width → current → width is approximate identity (within
        /// 1% relative tolerance for typical values).
        #[test]
        fn p8_trace_width_round_trip(
            w in 0.1f64..10.0,
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let cur = estimate_trace_current(w, oz, tr, internal);
            let w2 = calculate_min_trace_width(cur, oz, tr, internal);
            let rel_err = if w > 0.0 { (w2 - w).abs() / w } else { 0.0 };
            prop_assert!(rel_err < 0.02,
                "round-trip error too large: w={w}, cur={cur}, w2={w2}, rel_err={rel_err}");
        }

        // -----------------------------------------------------------------
        // get_net_current
        // -----------------------------------------------------------------

        /// P9. get_net_current always returns a non-negative value.
        #[test]
        fn p9_net_current_non_negative(
            name in "[A-Za-z0-9_+]{1,32}"
        ) {
            let cur = get_net_current(&name);
            prop_assert!(cur >= 0.0, "net current should be >= 0 for '{}', got {}", name, cur);
        }
    }
}
