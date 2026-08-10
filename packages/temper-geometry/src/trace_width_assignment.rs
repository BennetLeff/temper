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
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(kw_boundary_match_py, m)?)?;
    m.add_function(wrap_pyfunction!(determine_trace_width_py, m)?)?;
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

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("trace_width_assignment::tests::kw_boundary_match_cases", kw_boundary_match_cases),
        ("trace_width_assignment::tests::determine_trace_width_precedence", determine_trace_width_precedence),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
