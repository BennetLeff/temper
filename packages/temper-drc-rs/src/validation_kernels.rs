//! Pure Rust DRC validation kernels — portable to wasm32.
//!
//! These are the compute-only kernels extracted from [`super::validation`]
//! (the Python→Rust Wave-4 Phase 4 validation slice).  Each has **no** pyo3
//! types in its signature and compiles under `--no-default-features`
//! (wasm32-unknown-unknown).
//!
//! ## Portable kernels (this module)
//!
//! | Kernel | Python origin | Family |
//! |---|---|---|
//! | `infer_package_type` | `drc_oracle._infer_package_type` | drc |
//! | `tht_hole_collisions` | `tht_check.validate_hole_clearance` (pairwise) | drc |
//! | `trace_length` | `trace_analyzer.calculate_actual_trace_length` | drc |
//! | `min_hv_lv_trace_clearance` | `trace_analyzer.calculate_min_hv_lv_clearance` | safety |
//! | `issue_fingerprint` | `drc_fence._issue_fingerprint` | drc |
//!
//! ## Non-portable kernels (remain in `validation.rs` behind `#[cfg(feature = "python")]`)
//!
//! | Kernel | Reason |
//! |---|---|
//! | `rdl_sum` | Calls Python `math.hypot` via a pyo3 callable — cannot be wasm-portable |
//! | `geometric_validate` | Builds PyList/PyDict inside its decision loop; returning findings as pyo3 Python objects |
//! | `parse_drc_violation` | Interacts with a Python dict via pyo3 `Bound<'_, PyDict>` |
//! | `compute_drc_penalty` | Looks up weights in Python `Bound<'_, PyDict>` objects |
//! | `group_violations` | Normalizes Python dicts into `Py<PyDict>` records |
//! | `metrics_summary` | Accumulates metrics via C Python's `PyNumber_Add` (`+` operator) |
//!
//! ## Design boundaries
//!
//! - GEOS / `scipy.spatial.ConvexHull` / `kicad-cli` are NOT reimplementable
//!   and stay Python-side.
//! - Float formatting with fixed precision (`:.2f`/`:.3f`/`.1f`) matches
//!   CPython bit-for-bit (measured 100k/100k on random values).
//! - `CPython`'s `x ** y` is libm `pow` — NOT repeated multiplication and
//!   NOT `sqrt`.  All `** 2` / `** 0.5` sites go through
//!   [`crate::pymath::pow`], which dlsym's the host libm on native and
//!   falls back to `f64::powf` on wasm32 (R15: advisory-only divergence).
//! - The wasm32 fallback to `f64::powf` is documented in
//!   [`crate::pymath`] — LLVM may fold constant-exponent calls to
//!   `x*x`/`sqrt`, which disagree with libm `pow`; on wasm32 this is
//!   tolerable because the tier is advisory (R15).

use crate::pymath;

// ---------------------------------------------------------------------------
// drc_oracle._infer_package_type
// ---------------------------------------------------------------------------

/// Infer the SMD package type from a footprint name (verbatim port of
/// `drc_oracle._infer_package_type` — first-match keyword order preserved,
/// case-insensitive substring matching, `None`/empty → `"smd"`).
pub fn infer_package_type(footprint: Option<String>) -> String {
    let fp = footprint.unwrap_or_default().to_lowercase();
    if ["tht", "through", "pin", "dip"].iter().any(|p| fp.contains(p)) {
        return "tht".to_string();
    }
    if fp.contains("to-247") || fp.contains("to247") {
        return "to247".to_string();
    }
    if fp.contains("to-220") || fp.contains("to220") {
        return "to220".to_string();
    }
    if fp.contains("bga") {
        return "bga".to_string();
    }
    if fp.contains("qfn") {
        return "qfn".to_string();
    }
    if fp.contains("qfp") || fp.contains("tqfp") {
        return "qfp".to_string();
    }
    if fp.contains("dpak") || fp.contains("d2pak") {
        return "dpak".to_string();
    }
    "smd".to_string()
}

// ---------------------------------------------------------------------------
// tht_check.validate_hole_clearance — pairwise half
// ---------------------------------------------------------------------------

/// Pairwise THT hole collision check (verbatim port of the pairwise half of
/// `tht_check.validate_hole_clearance`). Each hole is `(ref, pad, x, y,
/// radius)` — the delegation module computes `radius = drill / 2.0` exactly
/// as the oracle did. Returns violation messages formatted with `:.3f`
/// (CPython-parity fixed-point formatting, measured).
pub fn tht_hole_collisions(
    holes: Vec<(String, String, f64, f64, f64)>,
    min_clearance: f64,
) -> Vec<String> {
    let mut violations = Vec::new();
    for i in 0..holes.len() {
        for j in (i + 1)..holes.len() {
            let (ref_i, pad_i, x_i, y_i, r_i) = &holes[i];
            let (ref_j, pad_j, x_j, y_j, r_j) = &holes[j];
            let dx = x_i - x_j;
            let dy = y_i - y_j;
            // CPython `** 2` is libm pow, not `x*x` (see module doc);
            // the oracle's `(a - b) ** 2` must match bit-for-bit.
            let dist = (pymath::pow(dx, 2.0) + pymath::pow(dy, 2.0)).sqrt();
            let required = r_i + r_j + min_clearance;
            if dist < required {
                violations.push(format!(
                    "{ref_i}.{pad_i} <-> {ref_j}.{pad_j}: dist={dist:.3}mm (min {required:.3}mm)"
                ));
            }
        }
    }
    violations
}

// ---------------------------------------------------------------------------
// trace_analyzer kernels
// ---------------------------------------------------------------------------

/// Total routed length of one net (verbatim port of
/// `trace_analyzer.calculate_actual_trace_length`). CPython's `dx**2` is
/// libm `pow` — NOT repeated multiplication (measured 262/200000
/// mismatches of `x*x` vs `x**2` on this platform), so the kernel squares
/// through [`pymath::pow`].
///
/// `net` is `Option<String>` because the Trace contract is
/// `net: str | None` (core/board.py): a None-net trace is skipped exactly
/// like the oracle's `if trace.net == net_name` — `None` never equals a str
/// `net_name` — rather than raising on extraction.
pub fn trace_length(
    traces: Vec<(Option<String>, f64, f64, f64, f64)>,
    net_name: &str,
) -> f64 {
    let mut length = 0.0_f64;
    for (net, x1, y1, x2, y2) in &traces {
        if net.as_ref().is_some_and(|n| n == net_name) {
            let dx = x2 - x1;
            let dy = y2 - y1;
            length += (pymath::pow(dx, 2.0) + pymath::pow(dy, 2.0)).sqrt();
        }
    }
    length
}

/// Minimum HV↔LV trace endpoint distance (verbatim port of
/// `trace_analyzer.calculate_min_hv_lv_clearance`). Each trace is
/// `(x1, y1, x2, y2)`; the four endpoint-pair distances are minimized.
/// Empty HV or LV arm → `+inf` (the oracle's `float("inf")`).
pub fn min_hv_lv_trace_clearance(
    hv: &[(f64, f64, f64, f64)],
    lv: &[(f64, f64, f64, f64)],
) -> f64 {
    if hv.is_empty() || lv.is_empty() {
        return f64::INFINITY;
    }
    let mut min_dist = f64::INFINITY;
    for (hx1, hy1, hx2, hy2) in hv {
        for (lx1, ly1, lx2, ly2) in lv {
            for (px, py) in [(*hx1, *hy1), (*hx2, *hy2)] {
                for (qx, qy) in [(*lx1, *ly1), (*lx2, *ly2)] {
                    let dx = px - qx;
                    let dy = py - qy;
                    // numpy's norm is sqrt(dot) — plain f64 arithmetic +
                    // correctly-rounded sqrt (measured 0/200000 mismatches).
                    let dist = (dx * dx + dy * dy).sqrt();
                    min_dist = min_dist.min(dist);
                }
            }
        }
    }
    min_dist
}

// ---------------------------------------------------------------------------
// drc_fence kernels
// ---------------------------------------------------------------------------

/// Canonical issue fingerprint (verbatim port of
/// `drc_fence._issue_fingerprint`): `"code:message:" + ",".join(sorted(items))`.
/// Rust's `String` sort matches CPython's lexicographic str sort for UTF-8
/// (byte order == code-point order).
pub fn issue_fingerprint(code: &str, message: &str, mut affected_items: Vec<String>) -> String {
    affected_items.sort();
    format!("{code}:{message}:{}", affected_items.join(","))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -- infer_package_type -------------------------------------------------

    #[cfg_attr(test, test)]
    fn infer_package_type_smd_default() {
        assert_eq!(infer_package_type(None), "smd");
        assert_eq!(infer_package_type(Some(String::new())), "smd");
        assert_eq!(infer_package_type(Some("RESC1608X55N".into())), "smd");
    }

    #[cfg_attr(test, test)]
    fn infer_package_type_tht() {
        assert_eq!(
            infer_package_type(Some("PinHeader_2x03_P2.54mm".into())),
            "tht"
        );
        assert_eq!(
            infer_package_type(Some("DIP-8_W7.62mm".into())),
            "tht"
        );
        assert_eq!(
            infer_package_type(Some("through-hole-resistor".into())),
            "tht"
        );
    }

    #[cfg_attr(test, test)]
    fn infer_package_type_to_packages() {
        assert_eq!(infer_package_type(Some("TO-247-3".into())), "to247");
        assert_eq!(infer_package_type(Some("TO247".into())), "to247");
        assert_eq!(infer_package_type(Some("TO-220".into())), "to220");
        assert_eq!(infer_package_type(Some("to220-horiz".into())), "to220");
    }

    #[cfg_attr(test, test)]
    fn infer_package_type_other_keywords() {
        assert_eq!(infer_package_type(Some("BGA-256".into())), "bga");
        assert_eq!(infer_package_type(Some("QFN-32".into())), "qfn");
        assert_eq!(infer_package_type(Some("QFP-100".into())), "qfp");
        assert_eq!(infer_package_type(Some("TQFP-44".into())), "qfp");
        assert_eq!(infer_package_type(Some("DPAK-3".into())), "dpak");
        assert_eq!(infer_package_type(Some("D2PAK-7".into())), "dpak");
    }

    // -- tht_hole_collisions ------------------------------------------------

    #[cfg_attr(test, test)]
    fn tht_hole_collisions_no_violations() {
        // Two holes far apart
        let holes = vec![
            ("C1".into(), "1".into(), 0.0, 0.0, 0.5),
            ("C2".into(), "1".into(), 10.0, 10.0, 0.5),
        ];
        let violations = tht_hole_collisions(holes, 1.0);
        assert!(violations.is_empty(), "holes are far apart, should be clean");
    }

    #[cfg_attr(test, test)]
    fn tht_hole_collisions_collision() {
        // Two overlapping holes
        let holes = vec![
            ("C1".into(), "1".into(), 0.0, 0.0, 1.0),
            ("C2".into(), "1".into(), 1.0, 0.0, 1.0),
        ];
        let violations = tht_hole_collisions(holes, 0.5);
        assert!(!violations.is_empty(), "overlapping holes must flag");
        assert!(
            violations[0].contains("C1.1") && violations[0].contains("C2.1"),
            "message must reference both holes"
        );
    }

    #[cfg_attr(test, test)]
    fn tht_hole_collisions_at_threshold() {
        // Hole centers exactly 3.0mm apart, each radius 1.0mm, min_clearance 1.0mm
        // Required = 1.0 + 1.0 + 1.0 = 3.0. dist = 3.0 exactly → should flag (<)
        let holes = vec![
            ("C1".into(), "1".into(), 0.0, 0.0, 1.0),
            ("C2".into(), "1".into(), 3.0, 0.0, 1.0),
        ];
        let violations = tht_hole_collisions(holes, 1.0);
        assert!(
            violations.is_empty(),
            "exactly at threshold (dist=3.0, required=3.0) is not < required",
        );
    }

    // -- trace_length -------------------------------------------------------

    #[cfg_attr(test, test)]
    fn trace_length_empty() {
        let traces: Vec<(Option<String>, f64, f64, f64, f64)> = vec![];
        assert_eq!(trace_length(traces, "NET1"), 0.0);
    }

    #[cfg_attr(test, test)]
    fn trace_length_single_segment() {
        // A single 3-4-5 right triangle segment
        let traces = vec![(Some("NET1".into()), 0.0, 0.0, 3.0, 4.0)];
        let len = trace_length(traces, "NET1");
        assert!((len - 5.0).abs() < 1e-12, "3-4-5 → 5.0, got {len}");
    }

    #[cfg_attr(test, test)]
    fn trace_length_skips_other_nets() {
        let traces = vec![
            (Some("NET1".into()), 0.0, 0.0, 3.0, 4.0),
            (Some("NET2".into()), 0.0, 0.0, 100.0, 100.0),
        ];
        let len = trace_length(traces, "NET1");
        assert!((len - 5.0).abs() < 1e-12);
    }

    #[cfg_attr(test, test)]
    fn trace_length_none_net_skipped() {
        let traces = vec![
            (None, 0.0, 0.0, 100.0, 100.0),
            (Some("NET1".into()), 0.0, 0.0, 3.0, 4.0),
        ];
        let len = trace_length(traces, "NET1");
        assert!((len - 5.0).abs() < 1e-12);
    }

    // -- min_hv_lv_trace_clearance -------------------------------------------

    #[cfg_attr(test, test)]
    fn min_hv_lv_clearance_empty_returns_inf() {
        let hv: Vec<(f64, f64, f64, f64)> = vec![];
        let lv = vec![(0.0, 0.0, 1.0, 1.0)];
        assert!(min_hv_lv_trace_clearance(&hv, &lv).is_infinite());
        assert!(min_hv_lv_trace_clearance(&lv, &hv).is_infinite());
    }

    #[cfg_attr(test, test)]
    fn min_hv_lv_clearance_single_pair() {
        let hv = vec![(0.0, 0.0, 1.0, 0.0)];
        let lv = vec![(5.0, 0.0, 6.0, 0.0)];
        // Closest endpoints: (1.0, 0.0) ↔ (5.0, 0.0) → 4.0
        assert!(
            (min_hv_lv_trace_clearance(&hv, &lv) - 4.0).abs() < 1e-12
        );
    }

    #[cfg_attr(test, test)]
    fn min_hv_lv_clearance_diagonal() {
        let hv = vec![(0.0, 0.0, 3.0, 4.0)];
        let lv = vec![(6.0, 8.0, 9.0, 12.0)];
        // Closest: (3.0, 4.0) ↔ (6.0, 8.0) → sqrt(9+16) = 5.0
        assert!(
            (min_hv_lv_trace_clearance(&hv, &lv) - 5.0).abs() < 1e-12
        );
    }

    // -- issue_fingerprint --------------------------------------------------

    #[cfg_attr(test, test)]
    fn issue_fingerprint_empty_items() {
        let fp = issue_fingerprint("DRC_CLR_001", "clearance violation", vec![]);
        assert_eq!(fp, "DRC_CLR_001:clearance violation:");
    }

    #[cfg_attr(test, test)]
    fn issue_fingerprint_sorts_items() {
        let fp = issue_fingerprint(
            "DRC_CLR_001",
            "clearance violation",
            vec!["C2".into(), "C1".into()],
        );
        assert_eq!(fp, "DRC_CLR_001:clearance violation:C1,C2");
    }

    #[cfg_attr(test, test)]
    fn issue_fingerprint_single_item() {
        let fp = issue_fingerprint("ERC_001", "unconnected pin", vec!["U1.1".into()]);
        assert_eq!(fp, "ERC_001:unconnected pin:U1.1");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("validation_kernels::tests::infer_package_type_smd_default", infer_package_type_smd_default),
        ("validation_kernels::tests::infer_package_type_tht", infer_package_type_tht),
        ("validation_kernels::tests::infer_package_type_to_packages", infer_package_type_to_packages),
        ("validation_kernels::tests::infer_package_type_other_keywords", infer_package_type_other_keywords),
        ("validation_kernels::tests::tht_hole_collisions_no_violations", tht_hole_collisions_no_violations),
        ("validation_kernels::tests::tht_hole_collisions_collision", tht_hole_collisions_collision),
        ("validation_kernels::tests::tht_hole_collisions_at_threshold", tht_hole_collisions_at_threshold),
        ("validation_kernels::tests::trace_length_empty", trace_length_empty),
        ("validation_kernels::tests::trace_length_single_segment", trace_length_single_segment),
        ("validation_kernels::tests::trace_length_skips_other_nets", trace_length_skips_other_nets),
        ("validation_kernels::tests::trace_length_none_net_skipped", trace_length_none_net_skipped),
        ("validation_kernels::tests::min_hv_lv_clearance_empty_returns_inf", min_hv_lv_clearance_empty_returns_inf),
        ("validation_kernels::tests::min_hv_lv_clearance_single_pair", min_hv_lv_clearance_single_pair),
        ("validation_kernels::tests::min_hv_lv_clearance_diagonal", min_hv_lv_clearance_diagonal),
        ("validation_kernels::tests::issue_fingerprint_empty_items", issue_fingerprint_empty_items),
        ("validation_kernels::tests::issue_fingerprint_sorts_items", issue_fingerprint_sorts_items),
        ("validation_kernels::tests::issue_fingerprint_single_item", issue_fingerprint_single_item),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod proptests {
    use proptest::prelude::*;
    use super::*;

    /// Normal f64 — avoids NaN/inf.
    fn val() -> impl Strategy<Value = f64> {
        -1e4f64..1e4f64
    }

    /// A small trace segment (x1, y1, x2, y2).
    fn trace_seg() -> impl Strategy<Value = (f64, f64, f64, f64)> {
        (val(), val(), val(), val())
    }

    proptest! {
        /// P1. infer_package_type always returns one of the known strings.
        #[test]
        fn p1_infer_package_type_is_known(name in "[A-Za-z0-9_-]*") {
            let result = infer_package_type(Some(name));
            let known = ["smd", "tht", "to247", "to220", "bga", "qfn", "qfp", "dpak"];
            prop_assert!(known.contains(&result.as_str()),
                "unknown result '{}'", result);
        }

        /// P2. Violation count is 0 when the distance between holes
        /// exceeds the required clearance by a large margin.
        #[test]
        fn p2_tht_no_violations_when_distant(
            x1 in val(), y1 in val(),
            r1 in 0.0f64..1.0, r2 in 0.0f64..1.0,
        ) {
            let holes = vec![
                ("A".into(), "1".into(), x1, y1, r1),
                ("B".into(), "1".into(), x1 + 1000.0, y1 + 1000.0, r2),
            ];
            let violations = tht_hole_collisions(holes, 10.0);
            prop_assert!(violations.is_empty(),
                "distant holes should not collide: {:?}", violations);
        }

        /// P3. Each violation message references both component refs.
        #[test]
        fn p3_tht_violation_message_has_both_refs(
            ref_a in "[A-Z][a-z]?", ref_b in "[A-Z][a-z]?",
            x in val(), y in val(),
        ) {
            prop_assume!(ref_a != ref_b);
            let holes = vec![
                (ref_a.clone(), "1".into(), x, y, 5.0),
                (ref_b.clone(), "1".into(), x, y, 5.0),
            ];
            let violations = tht_hole_collisions(holes, 1.0);
            for msg in &violations {
                prop_assert!(msg.contains(&ref_a),
                    "message '{}' missing ref '{}'", msg, ref_a);
                prop_assert!(msg.contains(&ref_b),
                    "message '{}' missing ref '{}'", msg, ref_b);
            }
        }

        /// P4. min_hv_lv_trace_clearance is never negative for non-empty
        /// inputs.
        #[test]
        fn p4_min_clearance_non_negative(
            hv in prop::collection::vec(trace_seg(), 1..=4),
            lv in prop::collection::vec(trace_seg(), 1..=4),
        ) {
            let d = min_hv_lv_trace_clearance(&hv, &lv);
            prop_assert!(d >= 0.0, "negative clearance {}", d);
        }

        /// P5. min_hv_lv_trace_clearance is symmetric: swapping hv and lv
        /// gives the same result.
        #[test]
        fn p5_min_clearance_symmetric(
            hv in prop::collection::vec(trace_seg(), 0..=4),
            lv in prop::collection::vec(trace_seg(), 0..=4),
        ) {
            let d1 = min_hv_lv_trace_clearance(&hv, &lv);
            let d2 = min_hv_lv_trace_clearance(&lv, &hv);
            prop_assert_eq!(d1, d2,
                "asymmetric: hv/lv={}, lv/hv={}", d1, d2);
        }

        /// P6. issue_fingerprint contains the code and message strings.
        #[test]
        fn p6_fingerprint_contains_code_and_message(
            code in "[A-Z_]+",
            message in "[a-z ]+",
            items in prop::collection::vec("[A-Za-z0-9.]+", 0..=5),
        ) {
            let fp = issue_fingerprint(&code, &message, items);
            let expected_start = format!("{}:", code);
            let expected_mid = format!(":{}:", message);
            prop_assert!(fp.starts_with(&expected_start));
            prop_assert!(fp.contains(&expected_mid));
        }

        /// P7. The fingerprint is invariant under reordering of items.
        #[test]
        fn p7_fingerprint_order_invariant(
            code in "[A-Z_]+",
            message in "[a-z ]+",
            mut items in prop::collection::vec("[A-Za-z0-9.]+", 0..=5),
        ) {
            let fp1 = issue_fingerprint(&code, &message, items.clone());
            items.reverse();
            let fp2 = issue_fingerprint(&code, &message, items);
            prop_assert!(fp1 == fp2,
                "fingerprint not invariant: '{}' vs '{}'", fp1, fp2);
        }
    }
}
