// Wave 4: `temper_placer/router_v6/trace_width_assignment.py` — Stage 4.4
// trace-width classification.  The `PathfindingResult`-driven orchestration
// (`assign_trace_widths`, which unions the routed/partial/tree path name
// sets) and the `TraceWidth`/`TraceWidthAssignment` dataclasses stay in
// Python; the per-net classification crosses this boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_spatial_drc_cluster_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Contract
// ---------------------------------------------------------------------------
// * `_kw_boundary_match` is the regex `(?:^|_)kw(?:$|[\d_])` with
//   `re.escape(kw)` and a trailing `_` stripped from each keyword.  All
//   keywords are alphanumeric/underscore (regex metacharacters never appear),
//   so a manual scan with boundary checks replicates the regex exactly,
//   leftmost-match-first.
// * `_determine_trace_width` checks HV keywords first, then
//   power keywords OR a leading `+` (`^\+`), then gate/drive keywords, then
//   default.  `power_width * 0.6` uses the f64 literal `0.6` (same binary
//   value in Python and Rust).
// * Net names are ASCII (Python `str.upper()` is replicated with
//   `to_ascii_uppercase()`); this is the pinned contract.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// `_kw_boundary_match`: does any keyword occur in `upper` delimited by
/// `_`/start-of-string before and `_`/digit/end-of-string after?
fn kw_boundary_match_impl(upper: &str, keywords: &[&str]) -> bool {
    let bytes = upper.as_bytes();
    let n = bytes.len();
    for kw in keywords {
        let kw = kw.strip_suffix('_').unwrap_or(kw);
        let kwb = kw.as_bytes();
        let k = kwb.len();
        if k == 0 || k > n {
            continue;
        }
        for i in 0..=(n - k) {
            if &bytes[i..i + k] == kwb {
                let pre_ok = i == 0 || bytes[i - 1] == b'_';
                let post_ok = i + k == n || bytes[i + k].is_ascii_digit() || bytes[i + k] == b'_';
                if pre_ok && post_ok {
                    return true;
                }
            }
        }
    }
    false
}

/// `_determine_trace_width`: returns `(width_mm, reason)` with the reference's
/// exact reason strings.
pub fn determine_trace_width(
    net_name: &str,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> (f64, &'static str) {
    let name_upper = net_name.to_ascii_uppercase();

    if kw_boundary_match_impl(&name_upper, &["AC_", "HV_", "HIGH_VOLTAGE"]) {
        return (hv_width, "High voltage net requires wider trace");
    }

    if kw_boundary_match_impl(&name_upper, &["GND", "VCC", "VDD", "VSS", "POWER"])
        || name_upper.starts_with('+')
    {
        return (power_width, "Power net requires wider trace for current capacity");
    }

    if kw_boundary_match_impl(&name_upper, &["GATE", "DRIVE"]) {
        return (power_width * 0.6, "Gate drive signal requires medium-width trace");
    }

    (default_width, "Standard signal trace")
}

// ---------------------------------------------------------------------------
// Layer-aware ampacity kernel (PR #1195 fallout: `determine_trace_width`
// above picks between three *flat* width constants with no knowledge of
// current or of which physical layer -- and therefore which copper weight --
// a segment will land on. PR #1178 declared the board's stackup 2oz
// outer / 1oz inner; PR #1195 taught the router to actually place copper on
// the inner signal layers (In3.Cu/In4.Cu). A width picked for 2oz outer
// copper is silently wrong (too narrow) once it can land on 1oz inner
// copper -- IPC-2221B's own external/internal `k` constants differ too
// (0.048 vs 0.024: internal traces cannot shed heat to air), so the gap
// compounds copper-cross-section halving with a further ~2x current-density
// derating at fixed width.
//
// This is the authoritative, correctly-sourced IPC-2221B formula --
// `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §2 cites it directly
// (k=0.048 external / 0.024 internal, exponents 0.44/0.725), and
// `scripts/check_stackup_copper_weight_gate.py` enforces that doc's
// assumed copper weights against the board's own declared stackup. The
// identical formula and constants already live, verbatim, in
// `temper-drc-rs/src/ipc.rs::{estimate_trace_current,
// calculate_min_trace_width}` -- that crate cannot be a dependency *here*
// (temper-drc-rs already depends on temper-geometry for pad-touch
// predicates; the reverse edge would be a cycle), so this is a from-scratch
// copy of the same cited public formula, not a second, divergent
// implementation. `test_ipc2221b_matches_sibling_known_values` below pins
// this copy against the exact same known-value assertions
// `temper-drc-rs/src/ipc.rs`'s own test module carries, so the two cannot
// silently drift apart.
//
// NOT the same as `temper-placer/temper-constraints/src/ipc.rs`'s
// `ipc2152_forward`/`min_width_ipc2152` (k_ext=0.065, flat 0.65 internal
// derate) -- that constant is unsourced (no citation anywhere in this repo)
// and diverges from this formula by ~35-75% depending on internal/external.
// StackupGate calls that unsourced variant today; this module does not.
// ---------------------------------------------------------------------------

/// IPC-2221B current-carrying capacity (A) for a trace of the given width,
/// copper weight, and layer type. Forward direction of the same formula
/// `ipc2221b_min_trace_width_mm` inverts.
///
/// `I = k * ΔT^0.44 * A^0.725`, `k = 0.048` (external) or `0.024`
/// (internal), `A` = cross-sectional area in mils² = width_mils *
/// (copper_weight_oz * 1.37).
pub fn ipc2221b_current_capacity_a(
    width_mm: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> f64 {
    let width_mils = width_mm * 39.3701;
    let thickness_mils = copper_weight_oz * 1.37;
    let area_mils2 = width_mils * thickness_mils;
    let k = if internal_layer { 0.024 } else { 0.048 };
    k * temp_rise_c.powf(0.44) * area_mils2.powf(0.725)
}

/// IPC-2221B minimum trace width (mm) to carry `current_a`, given the
/// *actual* copper weight of the layer the trace will occupy and whether
/// that layer is internal or external. Inverse of
/// `ipc2221b_current_capacity_a`.
///
/// Unlike `determine_trace_width`'s `power_width`/`hv_width`/`default_width`
/// constants, this has no notion of a single global calibration: the same
/// current on 1oz internal copper and 2oz external copper produces two
/// different widths, correctly, because both physical inputs are explicit
/// parameters -- the class of bug this function exists to make
/// unrepresentable (a caller cannot compute *a* width without supplying
/// *which* copper weight and layer type it is for).
pub fn ipc2221b_min_trace_width_mm(
    current_a: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> f64 {
    if current_a <= 0.0 {
        return 0.0;
    }
    let k = if internal_layer { 0.024 } else { 0.048 };
    let area_mils2 = (current_a / (k * temp_rise_c.powf(0.44))).powf(1.0 / 0.725);
    let thickness_mils = copper_weight_oz * 1.37;
    let width_mils = area_mils2 / thickness_mils;
    width_mils / 39.3701
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn kw_boundary_match_py(upper: String, keywords: Vec<String>) -> PyResult<bool> {
    let kws: Vec<&str> = keywords.iter().map(|s| s.as_str()).collect();
    temper_py_bridge::catch_unwind(|| kw_boundary_match_impl(&upper, &kws))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn determine_trace_width_py(
    net_name: String,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> PyResult<(f64, String)> {
    temper_py_bridge::catch_unwind(|| {
        let (w, r) = determine_trace_width(&net_name, default_width, power_width, hv_width);
        (w, r.to_string())
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn ipc2221b_current_capacity_a_py(
    width_mm: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        ipc2221b_current_capacity_a(width_mm, copper_weight_oz, temp_rise_c, internal_layer)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn ipc2221b_min_trace_width_mm_py(
    current_a: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        ipc2221b_min_trace_width_mm(current_a, copper_weight_oz, temp_rise_c, internal_layer)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(kw_boundary_match_py, m)?)?;
    m.add_function(wrap_pyfunction!(determine_trace_width_py, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2221b_current_capacity_a_py, m)?)?;
    m.add_function(wrap_pyfunction!(ipc2221b_min_trace_width_mm_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn kw_boundary_match_cases() {
        assert!(kw_boundary_match_impl("AC_L", &["AC_"]));
        assert!(kw_boundary_match_impl("3V3_HV", &["HV_"]));
        assert!(kw_boundary_match_impl("HV", &["HV_"]));
        assert!(kw_boundary_match_impl("HIGH_VOLTAGE_SIDE", &["HIGH_VOLTAGE"]));
        assert!(!kw_boundary_match_impl("NONHV", &["HV_"])); // no leading boundary
        assert!(!kw_boundary_match_impl("HVX", &["HV_"])); // trailing X not in [$_\d]
        assert!(kw_boundary_match_impl("GND", &["GND"]));
        assert!(kw_boundary_match_impl("GND_1", &["GND"]));
        assert!(!kw_boundary_match_impl("SIGND", &["GND"]));
    }

    #[cfg_attr(test, test)]
    fn determine_trace_width_precedence() {
        assert_eq!(determine_trace_width("AC_L", 0.1, 0.5, 0.6), (0.6, "High voltage net requires wider trace"));
        assert_eq!(determine_trace_width("GATE_HS", 0.1, 0.5, 0.6), (0.3, "Gate drive signal requires medium-width trace"));
        assert_eq!(determine_trace_width("GND", 0.1, 0.5, 0.6), (0.5, "Power net requires wider trace for current capacity"));
        assert_eq!(determine_trace_width("+5V", 0.1, 0.5, 0.6), (0.5, "Power net requires wider trace for current capacity"));
        assert_eq!(determine_trace_width("SIG_1", 0.1, 0.5, 0.6), (0.1, "Standard signal trace"));
    }

    /// Pins this crate's from-scratch copy of the IPC-2221B formula against
    /// the exact same known-value assertions
    /// `temper-drc-rs/src/ipc.rs::tests` carries for
    /// `estimate_trace_current`/`calculate_min_trace_width` (bit-exact
    /// argument order and constants), so the two copies -- which cannot
    /// share code across the crate-dependency direction -- cannot silently
    /// drift apart. See the module doc above `ipc2221b_current_capacity_a`
    /// for why this crate needs its own copy at all.
    #[cfg_attr(test, test)]
    fn test_ipc2221b_matches_sibling_known_values() {
        let i = ipc2221b_current_capacity_a(0.25, 1.0, 10.0, false);
        assert!((i - 0.87).abs() < 0.01, "external 0.25mm should be ~0.87A, got {i}");
        let i = ipc2221b_current_capacity_a(0.25, 1.0, 10.0, true);
        assert!((i - 0.44).abs() < 0.01, "internal 0.25mm should be ~0.44A, got {i}");

        let w = ipc2221b_min_trace_width_mm(0.5, 1.0, 10.0, false);
        assert!((w - 0.1160).abs() < 0.0002, "external 0.5A -> {w}, expected 0.1160");
        let w = ipc2221b_min_trace_width_mm(0.5, 1.0, 10.0, true);
        assert!((w - 0.3019).abs() < 0.0003, "internal 0.5A -> {w}, expected 0.3019");
        let w = ipc2221b_min_trace_width_mm(2.0, 1.0, 10.0, false);
        assert!((w - 0.784).abs() < 0.002, "external 2A -> {w}, expected 0.784");
    }

    #[cfg_attr(test, test)]
    fn test_ipc2221b_zero_current_is_zero_width() {
        assert_eq!(ipc2221b_min_trace_width_mm(0.0, 1.0, 10.0, false), 0.0);
        assert_eq!(ipc2221b_min_trace_width_mm(-1.0, 1.0, 10.0, false), 0.0);
    }

    #[cfg_attr(test, test)]
    fn test_ipc2221b_round_trip() {
        let width = 1.0;
        let current = ipc2221b_current_capacity_a(width, 1.0, 10.0, true);
        let width2 = ipc2221b_min_trace_width_mm(current, 1.0, 10.0, true);
        assert!((width - width2).abs() < 0.05, "round-trip error: {width} vs {width2}");
    }

    /// The exact scenario this module was written for: a 20mil (0.508mm)
    /// trace calibrated for 2oz outer copper, evaluated at 1oz inner
    /// copper. Internal derating (k=0.024 vs 0.048) plus the copper-weight
    /// halving (1oz vs 2oz) means the SAME width carries meaningfully less
    /// current internally -- this pins that the two kernels actually
    /// disagree in the documented direction, not just that they run.
    #[cfg_attr(test, test)]
    fn test_2oz_outer_vs_1oz_inner_capacity_gap() {
        let outer_2oz = ipc2221b_current_capacity_a(0.508, 2.0, 10.0, false);
        let inner_1oz = ipc2221b_current_capacity_a(0.508, 1.0, 10.0, true);
        assert!(
            inner_1oz < outer_2oz * 0.5,
            "1oz-internal capacity ({inner_1oz}) should be well under half of \
             2oz-external capacity ({outer_2oz}) at the same width"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("trace_width_assignment::tests::kw_boundary_match_cases", kw_boundary_match_cases),
        ("trace_width_assignment::tests::determine_trace_width_precedence", determine_trace_width_precedence),
        ("trace_width_assignment::tests::test_ipc2221b_matches_sibling_known_values", test_ipc2221b_matches_sibling_known_values),
        ("trace_width_assignment::tests::test_ipc2221b_zero_current_is_zero_width", test_ipc2221b_zero_current_is_zero_width),
        ("trace_width_assignment::tests::test_ipc2221b_round_trip", test_ipc2221b_round_trip),
        ("trace_width_assignment::tests::test_2oz_outer_vs_1oz_inner_capacity_gap", test_2oz_outer_vs_1oz_inner_capacity_gap),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
mod ipc2221b_proptests {
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
        /// Capacity is non-negative for any non-negative input.
        #[test]
        fn p1_capacity_non_negative(
            w in positive_width(), oz in copper_oz(), tr in reasonable_temp_rise(), internal in any::<bool>(),
        ) {
            prop_assert!(ipc2221b_current_capacity_a(w, oz, tr, internal) >= 0.0);
        }

        /// External capacity strictly exceeds internal capacity for
        /// identical width/copper-weight/ΔT (k_ext=0.048 > k_int=0.024) --
        /// the property whose violation this whole module exists to catch.
        #[test]
        fn p2_external_exceeds_internal(
            w in positive_width(), oz in copper_oz(), tr in reasonable_temp_rise(),
        ) {
            let ext = ipc2221b_current_capacity_a(w, oz, tr, false);
            let int = ipc2221b_current_capacity_a(w, oz, tr, true);
            prop_assert!(ext > int, "external ({ext}) should exceed internal ({int})");
        }

        /// Heavier copper (higher oz) at fixed width/ΔT carries strictly
        /// more current -- the property this module's copper-weight
        /// awareness exists to respect.
        #[test]
        fn p3_capacity_monotone_in_copper_weight(
            w in positive_width(), oz1 in 0.5f64..3.0, delta in 0.1f64..2.0, tr in reasonable_temp_rise(), internal in any::<bool>(),
        ) {
            let oz2 = oz1 + delta;
            let c1 = ipc2221b_current_capacity_a(w, oz1, tr, internal);
            let c2 = ipc2221b_current_capacity_a(w, oz2, tr, internal);
            prop_assert!(c2 > c1, "heavier copper ({oz2}oz > {oz1}oz) should carry more current");
        }

        /// Minimum width is non-negative.
        #[test]
        fn p4_min_width_non_negative(
            cur in positive_current(), oz in copper_oz(), tr in reasonable_temp_rise(), internal in any::<bool>(),
        ) {
            prop_assert!(ipc2221b_min_trace_width_mm(cur, oz, tr, internal) >= 0.0);
        }

        /// Internal layers need a strictly wider trace than external for
        /// the same current/copper-weight/ΔT.
        #[test]
        fn p5_internal_needs_wider_than_external(
            cur in positive_current(), oz in copper_oz(), tr in reasonable_temp_rise(),
        ) {
            let w_ext = ipc2221b_min_trace_width_mm(cur, oz, tr, false);
            let w_int = ipc2221b_min_trace_width_mm(cur, oz, tr, true);
            prop_assert!(w_int > w_ext, "internal ({w_int}) should need more width than external ({w_ext})");
        }

        /// Width -> current -> width round-trips within 2% relative error.
        #[test]
        fn p6_round_trip(
            w in 0.1f64..10.0, oz in copper_oz(), tr in reasonable_temp_rise(), internal in any::<bool>(),
        ) {
            let cur = ipc2221b_current_capacity_a(w, oz, tr, internal);
            let w2 = ipc2221b_min_trace_width_mm(cur, oz, tr, internal);
            let rel_err = if w > 0.0 { (w2 - w).abs() / w } else { 0.0 };
            prop_assert!(rel_err < 0.02, "round-trip error too large: w={w}, cur={cur}, w2={w2}");
        }
    }
}
