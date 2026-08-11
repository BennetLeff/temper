/// IPC-2221 creepage/clearance table.
///
/// Encodes the exact voltage bracket boundaries from the canonical PCB design
/// standard.  The table is monotonic: each bracket's max voltage is strictly
/// greater than the previous, and each clearance is >= the previous.
///
/// Boundaries sourced from `router_v6/creepage_check.py:382-433`:
///   0-15V → 0.13mm,  16-30V → 0.25mm,  31-50V → 0.50mm,
///   51-100V → 0.80mm, 101-150V → 1.25mm, 151-170V → 1.60mm,
///   171-250V → 3.20mm, 251-300V → 6.40mm, 301-600V → 8.00mm,
///   601-1000V → 12.00mm
/// A single voltage bracket: voltages up to `max_voltage` require at least
/// `clearance_mm` creepage distance.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CreepageBracket {
    pub max_voltage: f64,
    pub clearance_mm: f64,
}

/// IPC-2221 bracket table — ordered by ascending max_voltage.
pub const IPC2221_BRACKETS: [CreepageBracket; 10] = [
    CreepageBracket { max_voltage: 15.0, clearance_mm: 0.13 },
    CreepageBracket { max_voltage: 30.0, clearance_mm: 0.25 },
    CreepageBracket { max_voltage: 50.0, clearance_mm: 0.50 },
    CreepageBracket { max_voltage: 100.0, clearance_mm: 0.80 },
    CreepageBracket { max_voltage: 150.0, clearance_mm: 1.25 },
    CreepageBracket { max_voltage: 170.0, clearance_mm: 1.60 },
    CreepageBracket { max_voltage: 250.0, clearance_mm: 3.20 },
    CreepageBracket { max_voltage: 300.0, clearance_mm: 6.40 },
    CreepageBracket { max_voltage: 600.0, clearance_mm: 8.00 },
    CreepageBracket { max_voltage: 1000.0, clearance_mm: 12.00 },
];

/// Return the required creepage distance (mm) for a given working voltage.
///
/// Uses the first bracket whose max_voltage covers the input.  Voltages
/// above the highest bracket (1000V) return the max clearance (12.0mm).
pub fn required_clearance(voltage: f64) -> f64 {
    for bracket in &IPC2221_BRACKETS {
        if voltage <= bracket.max_voltage {
            return bracket.clearance_mm;
        }
    }
    // Above highest bracket — return the maximum defined clearance
    IPC2221_BRACKETS.last().map(|b| b.clearance_mm).unwrap_or(12.0)
}

/// Verify that the bracket table is monotonic:
/// - Each max_voltage > previous
/// - Each clearance_mm >= previous
pub fn verify_monotonic() -> Result<(), String> {
    for i in 1..IPC2221_BRACKETS.len() {
        let prev = &IPC2221_BRACKETS[i - 1];
        let curr = &IPC2221_BRACKETS[i];
        if curr.max_voltage <= prev.max_voltage {
            return Err(format!(
                "bracket {} max_voltage ({}) <= bracket {} max_voltage ({})",
                i, curr.max_voltage, i - 1, prev.max_voltage
            ));
        }
        if curr.clearance_mm < prev.clearance_mm {
            return Err(format!(
                "bracket {} clearance ({}) < bracket {} clearance ({})",
                i, curr.clearance_mm, i - 1, prev.clearance_mm
            ));
        }
    }
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn test_monotonic_by_construction() {
        verify_monotonic().expect("IPC-2221 brackets must be monotonic");
    }

    #[cfg_attr(test, test)]
    fn test_required_clearance_known_values() {
        assert!((required_clearance(0.0) - 0.13).abs() < 1e-10);
        assert!((required_clearance(10.0) - 0.13).abs() < 1e-10);
        assert!((required_clearance(15.0) - 0.13).abs() < 1e-10);
        assert!((required_clearance(16.0) - 0.25).abs() < 1e-10);
        assert!((required_clearance(30.0) - 0.25).abs() < 1e-10);
        assert!((required_clearance(110.0) - 1.25).abs() < 1e-10);
        assert!((required_clearance(230.0) - 3.20).abs() < 1e-10);
        assert!((required_clearance(250.0) - 3.20).abs() < 1e-10);
        assert!((required_clearance(251.0) - 6.40).abs() < 1e-10);
        assert!((required_clearance(500.0) - 8.00).abs() < 1e-10);
        assert!((required_clearance(600.0) - 8.00).abs() < 1e-10);
        assert!((required_clearance(800.0) - 12.00).abs() < 1e-10);
        assert!((required_clearance(1500.0) - 12.00).abs() < 1e-10);
    }

    #[cfg_attr(test, test)]
    fn test_required_clearance_edge_boundaries() {
        assert!((required_clearance(50.0) - 0.50).abs() < 1e-10);
        assert!((required_clearance(51.0) - 0.80).abs() < 1e-10);
        assert!((required_clearance(100.0) - 0.80).abs() < 1e-10);
        assert!((required_clearance(101.0) - 1.25).abs() < 1e-10);
        assert!((required_clearance(170.0) - 1.60).abs() < 1e-10);
        assert!((required_clearance(171.0) - 3.20).abs() < 1e-10);
        assert!((required_clearance(300.0) - 6.40).abs() < 1e-10);
        assert!((required_clearance(301.0) - 8.00).abs() < 1e-10);
        assert!((required_clearance(1000.0) - 12.00).abs() < 1e-10);
        assert!((required_clearance(1001.0) - 12.00).abs() < 1e-10);
    }

    // --- proptest: required_clearance monotonicity ---

    // Carries its own `#[cfg(test)]`, redundant under `cargo test` (the parent
    // `tests` module already has one) but load-bearing for the wasm32 tier: it
    // makes `scripts/gen_wasm_test_registry.py` census this module separately,
    // so the `proptest` dev-dependency -- absent from the non-test build the
    // registry compiles into -- excludes only these properties and not the
    // parent module's plain `#[test]`s.  Same shape as `temper-thermal`'s.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module, clippy::expect_used, clippy::unwrap_used)]
    mod proptests {

        use super::*;
        use proptest::prelude::*;

        proptest! {
            // --------------------------------------------------------------
            // Property I1: required_clearance is non-decreasing in voltage.
            // Higher voltage => no smaller clearance.
            // --------------------------------------------------------------
            #[test]
            fn prop_clearance_monotonic(
                v1 in prop::num::f64::NORMAL,
                v2 in prop::num::f64::NORMAL,
            ) {
                // Order directly: prop_assume!(v1 <= v2) rejects ~50% and
                // trips proptest's global-reject limit at high PROPTEST_CASES.
                let (v1, v2) = if v1 <= v2 { (v1, v2) } else { (v2, v1) };
                let c1 = required_clearance(v1);
                let c2 = required_clearance(v2);
                prop_assert!(c1 <= c2,
                    "required_clearance({v1})={c1} > required_clearance({v2})={c2}");
            }

            // --------------------------------------------------------------
            // Property I2: required_clearance is bounded: always one of
            // the bracket values or the maximum.
            // --------------------------------------------------------------
            #[test]
            fn prop_clearance_in_known_set(v in prop::num::f64::NORMAL) {
                let c = required_clearance(v);
                let known: Vec<f64> = IPC2221_BRACKETS.iter()
                    .map(|b| b.clearance_mm)
                    .collect();
                prop_assert!(known.contains(&c),
                    "required_clearance({v})={c} not in bracket set {known:?}");
            }

            // --------------------------------------------------------------
            // Property I3: For any voltage <= the max bracket, the
            // clearance is the bracket value covering it.
            // --------------------------------------------------------------
            #[test]
            fn prop_clearance_covers_input(v in 0.0f64..1000.0f64) {
                let c = required_clearance(v);
                // Find the bracket: first with max_voltage >= v.
                let expected = IPC2221_BRACKETS.iter()
                    .find(|b| v <= b.max_voltage)
                    .map(|b| b.clearance_mm)
                    .unwrap_or(12.0);
                prop_assert!((c - expected).abs() < f64::EPSILON,
                    "required_clearance({v})={c}, expected {expected}");
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("ipc2221::tests::test_monotonic_by_construction", test_monotonic_by_construction),
        ("ipc2221::tests::test_required_clearance_known_values", test_required_clearance_known_values),
        ("ipc2221::tests::test_required_clearance_edge_boundaries", test_required_clearance_edge_boundaries),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
