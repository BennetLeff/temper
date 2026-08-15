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
//
// Consolidation (2026-08-13, defect-multiplier audit finding #4 /
// duplicate-pyo3-registration incident): this module used to carry its own
// private `kw_boundary_match_impl`, independently reimplementing the exact
// `(?:^|_)kw(?:$|[\d_])` predicate `via_clearance.rs::kw_boundary_match`
// (née `word_bounded`) already computes, AND independently exported it to
// Python as `#[pyfunction] kw_boundary_match_py` -- the identical name
// `via_clearance.rs` also exports.  Both got `wrap_pyfunction!`'d into the
// same `temper_geometry` pymodule (`lib.rs`'s `#[pymodule] fn
// temper_geometry`); pyo3's `PyModule::add_function` is a plain attribute
// `setattr`, so the later `register()` call silently overwrote the earlier
// one -- `via_clearance::register` runs after this module's `register` in
// `lib.rs`, so Python callers were always getting `via_clearance`'s
// implementation regardless of which module's docstring they read.
// Verified byte-for-byte behaviorally equivalent before consolidating
// (972 real-net x real-keyword-set pairs + 2028 synthetic hyphen/underscore
// variants, 0 mismatches) -- this is a pure delegation, not a behavior
// change. `determine_trace_width` now calls `via_clearance::kw_boundary_match`
// directly; the duplicate private impl and the duplicate pyo3 export are
// both gone. See `docs/evidence/2026-08-13-pyo3-duplicate-registration-kw-boundary-match.md`.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// `_determine_trace_width`: returns `(width_mm, reason)` with the reference's
/// exact reason strings.  Keyword matching delegates to
/// `via_clearance::kw_boundary_match` (see the consolidation note above) --
/// there is exactly one `(?:^|_)kw(?:$|[\d_])` implementation in this crate
/// now, not two.
pub fn determine_trace_width(
    net_name: &str,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> (f64, &'static str) {
    let name_upper = net_name.to_ascii_uppercase();

    if crate::via_clearance::kw_boundary_match(&name_upper, &["AC_", "HV_", "HIGH_VOLTAGE"]) {
        return (hv_width, "High voltage net requires wider trace");
    }

    if crate::via_clearance::kw_boundary_match(&name_upper, &["GND", "VCC", "VDD", "VSS", "POWER"])
        || name_upper.starts_with('+')
    {
        return (power_width, "Power net requires wider trace for current capacity");
    }

    if crate::via_clearance::kw_boundary_match(&name_upper, &["GATE", "DRIVE"]) {
        return (power_width * 0.6, "Gate drive signal requires medium-width trace");
    }

    (default_width, "Standard signal trace")
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

// `kw_boundary_match_py` is NOT re-exported from this module.  It used to
// be (see the consolidation note at the top of this file) -- the sole
// pyo3-visible `kw_boundary_match_py` now lives in `via_clearance.rs`, the
// same underlying predicate `determine_trace_width` above calls directly.
// A second `#[pyfunction] kw_boundary_match_py` here would silently shadow
// (or be shadowed by) that one again the moment both `register()`s ran in
// the same `#[pymodule]` -- exactly the defect this consolidation fixes.
// `scripts/check_pyo3_duplicate_registration.py` fails CI closed if this
// regresses.

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
        // Exercises `via_clearance::kw_boundary_match` at the call site
        // `determine_trace_width` actually uses post-consolidation -- proves
        // the delegation preserved every case this module's own test used to
        // pin against its now-deleted private `kw_boundary_match_impl`.
        use crate::via_clearance::kw_boundary_match;
        assert!(kw_boundary_match("AC_L", &["AC_"]));
        assert!(kw_boundary_match("3V3_HV", &["HV_"]));
        assert!(kw_boundary_match("HV", &["HV_"]));
        assert!(kw_boundary_match("HIGH_VOLTAGE_SIDE", &["HIGH_VOLTAGE"]));
        assert!(!kw_boundary_match("NONHV", &["HV_"])); // no leading boundary
        assert!(!kw_boundary_match("HVX", &["HV_"])); // trailing X not in [$_\d]
        assert!(kw_boundary_match("GND", &["GND"]));
        assert!(kw_boundary_match("GND_1", &["GND"]));
        assert!(!kw_boundary_match("SIGND", &["GND"]));
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
