// HV-isolation clearance/creepage geometry (Wave 3 #7 — the safety
// validator) behind temper_placer/router_v6/creepage_check.py.
//
// Python reference: creepage_check.py `_point_to_segment_distance`,
// `_closest_point_on_segment`, `_segments_intersect`,
// `_segment_to_segment_info`, the same-layer min-aggregation loop in
// `_find_clearance_violations`, `_calculate_required_creepage`, and
// `_is_high_voltage_net`.  The route-object extraction
// (`_extract_segments`) and the per-net report orchestration
// (`verify_creepage`) stay in Python.
//
// Bit-exactness: identical f64 operation order (left-to-right,
// two-op chains stay two ops), CPython `math.hypot` (Dekker
// double-double vector_norm, shared with pad_geometry.rs), and
// Python-builtin `min`/`max` NaN semantics (see `py_min`/`py_max`).

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Python builtin `max(a, b)` for two args — returns `a` whenever `b > a`
/// is false, so max(NaN, x) == NaN but max(x, NaN) == x (Rust's
/// `f64::max` would discard the NaN).  Equal operands also return `a`,
/// which is why `max(0.0, -0.0)` is `+0.0` while `max(-0.0, 0.0)` is
/// `-0.0` — a distinction `f64::max` does not make either.
///
/// `pub(crate)`: shared with `drc_constraints_geometry.rs`, whose
/// reference clamps with the same builtins.  One implementation, so the
/// two cannot drift.
pub(crate) fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// Python builtin `min(a, b)` for two args — returns `a` whenever `b < a`
/// is false, so min(NaN, x) == NaN but min(x, NaN) == x.
pub(crate) fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// Mirrors creepage_check.py `_point_to_segment_distance` exactly:
/// clamped projection onto the segment, CPython `math.hypot` at both the
/// degenerate-arm and the final distance.
fn point_to_segment_distance(
    px: f64,
    py: f64,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
) -> f64 {
    let dx = x2 - x1;
    let dy = y2 - y1;
    let denom = dx * dx + dy * dy;
    if denom == 0.0 || !denom.is_finite() {
        // Zero-length segment (point) or non-finite direction: the
        // distance is the point-to-point distance to (x1, y1).
        return crate::pad_geometry::py_hypot(px - x1, py - y1);
    }
    // Clamped projection parameter t ∈ [0, 1] — builtin min/max NaN
    // semantics: min(1.0, NaN) == 1.0, so a NaN point projects onto the
    // far endpoint before hypot turns the result back into NaN.
    let t = ((px - x1) * dx + (py - y1) * dy) / denom;
    let t = py_min(1.0, t);
    let t = py_max(0.0, t);
    let proj_x = x1 + t * dx;
    let proj_y = y1 + t * dy;
    crate::pad_geometry::py_hypot(px - proj_x, py - proj_y)
}

/// Mirrors creepage_check.py `_closest_point_on_segment` exactly — same
/// projection formula, returns the clamped point on the segment.
fn closest_point_on_segment(
    px: f64,
    py: f64,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
) -> (f64, f64) {
    let dx = x2 - x1;
    let dy = y2 - y1;
    let denom = dx * dx + dy * dy;
    if denom == 0.0 || !denom.is_finite() {
        return (x1, y1);
    }
    let t = ((px - x1) * dx + (py - y1) * dy) / denom;
    let t = py_min(1.0, t);
    let t = py_max(0.0, t);
    (x1 + t * dx, y1 + t * dy)
}

/// Signed orientation of (c) relative to the directed line (a)→(b):
/// `(bx - ax) * (cy - ay) - (by - ay) * (cx - ax)`.
fn orient(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> f64 {
    (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
}

/// Mirrors creepage_check.py `_segments_intersect`: PROPER intersection
/// only (strict `< 0.0` orientation products — shared endpoints and
/// collinear overlaps do not count), then the intersection point via the
/// parameter on segment 2.  Returns `(intersects, ix, iy)`.
#[expect(clippy::too_many_arguments, reason = "creepage_check.py port mirrors _segments_intersect's 2-segment signature 1:1; a config struct would change the ported shape")]
fn segments_intersect(
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    x3: f64,
    y3: f64,
    x4: f64,
    y4: f64,
) -> (bool, f64, f64) {
    let o1 = orient(x1, y1, x2, y2, x3, y3);
    let o2 = orient(x1, y1, x2, y2, x4, y4);
    let o3 = orient(x3, y3, x4, y4, x1, y1);
    let o4 = orient(x3, y3, x4, y4, x2, y2);
    if o1 * o2 < 0.0 && o3 * o4 < 0.0 {
        let dx1 = x2 - x1;
        let dy1 = y2 - y1;
        let dx2 = x4 - x3;
        let dy2 = y4 - y3;
        let denom = dx1 * dy2 - dy1 * dx2;
        if denom != 0.0 {
            let t = ((x1 - x3) * dy1 - (y1 - y3) * dx1) / denom;
            let ix = x3 + t * dx2;
            let iy = y3 + t * dy2;
            return (true, ix, iy);
        }
    }
    (false, 0.0, 0.0)
}

/// Mirrors creepage_check.py `_segment_to_segment_info`: minimum distance
/// between two segments plus the closest points (p1 on segment 1, p2 on
/// segment 2).  Returns `(dist, cx1, cy1, cx2, cy2)`.
///
/// Order preserved exactly: intersection shortcut first, then seg1's
/// endpoints against seg2, then seg2's endpoints against seg1, each with
/// strict `<` so NaN distances never displace a finite best.
#[expect(clippy::too_many_arguments, reason = "creepage_check.py port mirrors _segment_to_segment_info's 2-segment signature 1:1; a config struct would change the ported shape")]
fn segment_to_segment_info(
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    x3: f64,
    y3: f64,
    x4: f64,
    y4: f64,
) -> (f64, f64, f64, f64, f64) {
    let (intersects, ix, iy) = segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4);
    if intersects {
        return (0.0, ix, iy, ix, iy);
    }
    let mut best_dist = f64::INFINITY;
    let mut best_p1 = (0.0, 0.0);
    let mut best_p2 = (0.0, 0.0);
    for (px, py) in [(x1, y1), (x2, y2)] {
        let d = point_to_segment_distance(px, py, x3, y3, x4, y4);
        if d < best_dist {
            best_dist = d;
            best_p1 = (px, py);
            best_p2 = closest_point_on_segment(px, py, x3, y3, x4, y4);
        }
    }
    for (px, py) in [(x3, y3), (x4, y4)] {
        let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
        if d < best_dist {
            best_dist = d;
            best_p1 = closest_point_on_segment(px, py, x1, y1, x2, y2);
            best_p2 = (px, py);
        }
    }
    (best_dist, best_p1.0, best_p1.1, best_p2.0, best_p2.1)
}

/// A route segment as extracted by Python `_extract_segments`:
/// (x1, y1, x2, y2, layer).
type Seg = (f64, f64, f64, f64, String);

/// Mirrors the same-layer min-aggregation loop in creepage_check.py
/// `_find_clearance_violations`: the worst-case (closest-approach)
/// distance between two routes' segment sets, restricted to same-layer
/// pairs, with the midpoint of the closest approach.  Returns
/// `(best_dist, mid_x, mid_y)` — `(inf, 0.0, 0.0)` when no same-layer
/// pair exists.
fn min_clearance_distance(segs1: &[Seg], segs2: &[Seg]) -> (f64, f64, f64) {
    let mut best_dist = f64::INFINITY;
    let mut best_loc = (0.0, 0.0);
    for (x1, y1, x2, y2, layer1) in segs1 {
        for (x3, y3, x4, y4, layer2) in segs2 {
            if layer1 != layer2 {
                // Different layers — via-to-via creepage is not modelled.
                continue;
            }
            let (dist, c1x, c1y, c2x, c2y) =
                segment_to_segment_info(*x1, *y1, *x2, *y2, *x3, *y3, *x4, *y4);
            if dist < best_dist {
                best_dist = dist;
                // Midpoint of closest approach as violation location.
                best_loc = ((c1x + c2x) / 2.0, (c1y + c2y) / 2.0);
            }
        }
    }
    (best_dist, best_loc.0, best_loc.1)
}

/// Mirrors creepage_check.py `_calculate_required_creepage`: the
/// simplified IPC-2221 voltage→creepage table.  NaN/inf raise (the
/// Python wrapper surfaces this as ValueError); negative voltages fall
/// through to the lowest bracket, exactly like the reference.
fn required_creepage_bracket(voltage: f64) -> f64 {
    if voltage <= 15.0 {
        0.13
    } else if voltage <= 30.0 {
        0.25
    } else if voltage <= 50.0 {
        0.5
    } else if voltage <= 100.0 {
        0.8
    } else if voltage <= 150.0 {
        1.25
    } else if voltage <= 170.0 {
        1.6
    } else if voltage <= 250.0 {
        3.2
    } else if voltage <= 300.0 {
        6.4
    } else if voltage <= 600.0 {
        8.0
    } else {
        12.0
    }
}

/// Python `repr` of a non-finite f64: `nan`, `inf`, `-inf` — the exact
/// spellings CPython's `{voltage!r}` produces for the ValueError message.
fn py_repr_nonfinite(v: f64) -> String {
    if v.is_nan() {
        "nan".to_string()
    } else if v > 0.0 {
        "inf".to_string()
    } else {
        "-inf".to_string()
    }
}

/// Word-boundary keyword scan, the exact semantics of the reference's
/// `(?:^|_)kw(?:$|[\d_])` regex.  Candidate start positions are 0 and
/// every index right after a `_` (ASCII `_` never appears inside a
/// multi-byte UTF-8 char, so a byte scan is safe); the trailing check
/// decodes the next char so Unicode decimal digits match Python re's
/// `\d` (`char::to_digit(10)` is exactly the Nd property).
fn word_bounded(name: &str, kw: &str) -> bool {
    let bytes = name.as_bytes();
    if name.len() < kw.len() {
        return false;
    }
    let mut i = 0usize;
    loop {
        if (i == 0 || bytes[i - 1] == b'_') && name[i..].starts_with(kw) {
            let after = i + kw.len();
            if after == name.len() {
                return true;
            }
            if let Some(c) = name[after..].chars().next() {
                // char::is_digit(10) is exactly the Unicode Nd property
                // (Python re `\d`); is_ascii_digit would miss non-ASCII digits.
                #[expect(clippy::is_digit_ascii_radix, reason = "Unicode Nd property required to match Python re \\d")]
                let is_digit = c.is_digit(10);
                if c == '_' || is_digit {
                    return true;
                }
            }
        }
        match bytes[i..].iter().position(|&b| b == b'_') {
            Some(p) => i += p + 1,
            None => return false,
        }
    }
}

/// `(?:^|_)kw` — leading boundary only, no trailing constraint (the
/// reference's "B+" special case, which has no alphanumeric trailing
/// boundary to anchor on).
fn word_bounded_prefix(name: &str, kw: &str) -> bool {
    let bytes = name.as_bytes();
    if name.len() < kw.len() {
        return false;
    }
    let mut i = 0usize;
    loop {
        if (i == 0 || bytes[i - 1] == b'_') && name[i..].starts_with(kw) {
            return true;
        }
        match bytes[i..].iter().position(|&b| b == b'_') {
            Some(p) => i += p + 1,
            None => return false,
        }
    }
}

/// Mirrors creepage_check.py `_is_high_voltage_net`: keyword order and
/// word-boundary discipline identical to the reference (the 2026-07-27
/// fix — word-boundary on `_`, never plain substring).  Keyword set and
/// evaluation order preserved verbatim.
fn is_high_voltage_net(net_name: &str) -> bool {
    let name_upper = net_name.to_uppercase();
    const BROAD_KEYWORDS: [&str; 11] = [
        "HIGH_VOLTAGE",
        "MAINS",
        "LINE",
        "NEUTRAL",
        "PRIMARY",
        "HOT",
        "L1",
        "L2",
        "L3",
        "PHASE",
        "VBUS",
    ];
    for kw in BROAD_KEYWORDS {
        if word_bounded(&name_upper, kw) {
            return true;
        }
    }
    if word_bounded_prefix(&name_upper, "B+") {
        return true;
    }
    if word_bounded(&name_upper, "AC") {
        return true;
    }
    word_bounded(&name_upper, "HV")
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn point_to_segment_distance_py(
    px: f64,
    py: f64,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| point_to_segment_distance(px, py, x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn closest_point_on_segment_py(
    px: f64,
    py: f64,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| closest_point_on_segment(px, py, x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn segments_intersect_py(
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    x3: f64,
    y3: f64,
    x4: f64,
    y4: f64,
) -> PyResult<(bool, f64, f64)> {
    temper_py_bridge::catch_unwind(|| segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn segment_to_segment_info_py(
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    x3: f64,
    y3: f64,
    x4: f64,
    y4: f64,
) -> PyResult<(f64, f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| segment_to_segment_info(x1, y1, x2, y2, x3, y3, x4, y4))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn min_clearance_distance_py(segs1: Vec<Seg>, segs2: Vec<Seg>) -> PyResult<(f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| min_clearance_distance(&segs1, &segs2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn calculate_required_creepage_py(voltage: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        if voltage.is_nan() || !voltage.is_finite() {
            return Err(PyValueError::new_err(format!(
                "Voltage must be a finite number, got {}",
                py_repr_nonfinite(voltage)
            )));
        }
        Ok(required_creepage_bracket(voltage))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn is_high_voltage_net_py(net_name: String) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| is_high_voltage_net(&net_name))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn point_to_segment_zero_length_segment() {
        // Degenerate (point) segment: point-to-point distance.
        let d = point_to_segment_distance(3.0, 4.0, 1.0, 1.0, 1.0, 1.0);
        assert_eq!(d, crate::pad_geometry::py_hypot(2.0, 3.0));
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_on_segment_is_zero() {
        assert_eq!(point_to_segment_distance(5.0, 0.0, 0.0, 0.0, 10.0, 0.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_projection_clamps() {
        // Beyond the far endpoint → distance to the endpoint.
        assert_eq!(point_to_segment_distance(12.0, 0.0, 0.0, 0.0, 10.0, 0.0), 2.0);
        // Before the near endpoint → distance to the near endpoint.
        assert_eq!(point_to_segment_distance(-3.0, 0.0, 0.0, 0.0, 10.0, 0.0), 3.0);
    }

    #[cfg_attr(test, test)]
    fn segments_intersect_crossing() {
        // Reference-pinned values: the pre-migration t formula is
        // `cross(P1-P3, d1) / cross(d1, d2)` = −t_true, so the reported
        // intersection mirrors through P3 (ix=-5, iy=15 here, not (5,5)).
        // Bit-exact migration replicates this; dist is 0 either way, so
        // the pass/fail verdict is unaffected. Recorded in VERIFICATION.md.
        let (hit, ix, iy) = segments_intersect(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0);
        assert!(hit);
        assert_eq!((ix, iy), (-5.0, 15.0));
    }

    #[cfg_attr(test, test)]
    fn segments_intersect_shared_endpoint_is_not_proper() {
        let (hit, _, _) = segments_intersect(0.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 10.0);
        assert!(!hit);
    }

    #[cfg_attr(test, test)]
    fn segment_to_segment_parallel_gap() {
        let (dist, _, _, _, _) = segment_to_segment_info(0.0, 0.0, 10.0, 0.0, 0.0, 2.0, 10.0, 2.0);
        assert_eq!(dist, 2.0);
    }

    #[cfg_attr(test, test)]
    fn segment_to_segment_crossing_is_zero() {
        let (dist, c1x, c1y, c2x, c2y) =
            segment_to_segment_info(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0);
        assert_eq!(dist, 0.0);
        assert_eq!((c1x, c1y), (c2x, c2y));
    }

    #[cfg_attr(test, test)]
    fn min_clearance_filters_by_layer() {
        let segs1 = vec![(0.0, 0.0, 10.0, 0.0, "F.Cu".to_string())];
        let segs2 = vec![(0.0, 0.5, 10.0, 0.5, "B.Cu".to_string())];
        let (dist, _, _) = min_clearance_distance(&segs1, &segs2);
        assert_eq!(dist, f64::INFINITY); // no same-layer pair
        let segs3 = vec![(0.0, 0.5, 10.0, 0.5, "F.Cu".to_string())];
        let (dist, mx, my) = min_clearance_distance(&segs1, &segs3);
        assert_eq!(dist, 0.5);
        // Strict `<` tie-break: the first endpoint (0,0) wins, so the
        // midpoint of the closest approach is (0.0, 0.25) — pinned.
        assert_eq!((mx, my), (0.0, 0.25));
    }

    #[cfg_attr(test, test)]
    fn required_creepage_brackets() {
        assert_eq!(required_creepage_bracket(15.0), 0.13);
        assert_eq!(required_creepage_bracket(15.000001), 0.25);
        assert_eq!(required_creepage_bracket(50.0), 0.5);
        assert_eq!(required_creepage_bracket(100.0), 0.8);
        assert_eq!(required_creepage_bracket(150.0), 1.25);
        assert_eq!(required_creepage_bracket(170.0), 1.6);
        assert_eq!(required_creepage_bracket(250.0), 3.2);
        assert_eq!(required_creepage_bracket(300.0), 6.4);
        assert_eq!(required_creepage_bracket(600.0), 8.0);
        assert_eq!(required_creepage_bracket(601.0), 12.0);
        assert_eq!(required_creepage_bracket(-5.0), 0.13); // falls to lowest bracket
    }

    #[cfg_attr(test, test)]
    fn hv_word_boundary_positive() {
        for name in ["AC_L", "AC1", "_AC", "AC_", "HV_BUS", "HV1", "B+", "BUS_L1", "PHASE_L2"] {
            assert!(is_high_voltage_net(name), "{name}");
        }
    }

    #[cfg_attr(test, test)]
    fn hv_word_boundary_negative() {
        // The 2026-07-27 regression set: substring matches must NOT fire.
        for name in [
            "discharge.k_dis1-coil1",
            "discharge.k_dis1-coil2",
            "safety-line",
            "safety.ovp-line",
            "TRACE",
            "ACH",
            "CAC",
            "HIVE",
            "BEHAVE",
            "XHVX",
            "AC-",
            "AC.",
            "AC:",
        ] {
            assert!(!is_high_voltage_net(name), "{name}");
        }
    }

    #[cfg_attr(test, test)]
    fn hv_case_insensitive() {
        assert!(is_high_voltage_net("ac_l"));
        assert!(is_high_voltage_net("hv_bus"));
        assert!(!is_high_voltage_net("trace"));
    }

    #[cfg_attr(test, test)]
    fn hv_non_ascii_does_not_crash() {
        for name in ["\u{03b1}\u{03b2}", "\u{4e2d}\u{6587}", "\u{30a2}\u{30a4}", "net\u{2013}name"] {
            let _ = is_high_voltage_net(name);
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("creepage_check::tests::point_to_segment_zero_length_segment", point_to_segment_zero_length_segment),
        ("creepage_check::tests::point_to_segment_on_segment_is_zero", point_to_segment_on_segment_is_zero),
        ("creepage_check::tests::point_to_segment_projection_clamps", point_to_segment_projection_clamps),
        ("creepage_check::tests::segments_intersect_crossing", segments_intersect_crossing),
        ("creepage_check::tests::segments_intersect_shared_endpoint_is_not_proper", segments_intersect_shared_endpoint_is_not_proper),
        ("creepage_check::tests::segment_to_segment_parallel_gap", segment_to_segment_parallel_gap),
        ("creepage_check::tests::segment_to_segment_crossing_is_zero", segment_to_segment_crossing_is_zero),
        ("creepage_check::tests::min_clearance_filters_by_layer", min_clearance_filters_by_layer),
        ("creepage_check::tests::required_creepage_brackets", required_creepage_brackets),
        ("creepage_check::tests::hv_word_boundary_positive", hv_word_boundary_positive),
        ("creepage_check::tests::hv_word_boundary_negative", hv_word_boundary_negative),
        ("creepage_check::tests::hv_case_insensitive", hv_case_insensitive),
        ("creepage_check::tests::hv_non_ascii_does_not_crash", hv_non_ascii_does_not_crash),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based and metamorphic tests — Phase 1 of the WASM verification tier
// plan (docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md).
//
// Ported from packages/temper-placer/tests/router_v6/test_creepage_geometry_pbt.py,
// which drives these same kernels through the pyo3 layer at 200 examples. Running
// them natively removes both the interpreter round trip and the CI budget that
// caps the Python suite, so `cases` here is set an order of magnitude higher.
//
// These target the private kernels directly, which same-module tests can reach.
// The module needs no `pub` surface until the same properties run on wasm.
//
// Property IDs match the Python source so the correspondence stays traceable.
// P1-P5 are invariants; M1-M3 are metamorphic relations (a class the repo had
// none of before this, and which Wave 4's discipline contract R1d requires at
// three per module).
// ---------------------------------------------------------------------------
#[cfg(test)]
mod properties {
    use super::*;
    use proptest::prelude::*;

    /// Board-scale coordinates. Bounded rather than unrestricted f64 because
    /// these kernels model physical geometry in millimetres; NaN and 1e300 are
    /// not inputs the caller can produce, and admitting them would test the
    /// float type rather than the kernel.
    fn coord() -> impl Strategy<Value = f64> {
        -50.0f64..50.0f64
    }

    type Seg8 = (f64, f64, f64, f64, f64, f64, f64, f64);

    fn seg_pair() -> impl Strategy<Value = Seg8> {
        (coord(), coord(), coord(), coord(), coord(), coord(), coord(), coord())
    }

    fn dist(s: Seg8) -> f64 {
        segment_to_segment_info(s.0, s.1, s.2, s.3, s.4, s.5, s.6, s.7).0
    }

    fn translate(s: Seg8, tx: f64, ty: f64) -> Seg8 {
        (s.0 + tx, s.1 + ty, s.2 + tx, s.3 + ty, s.4 + tx, s.5 + ty, s.6 + tx, s.7 + ty)
    }

    fn rotate(s: Seg8, theta: f64) -> Seg8 {
        let (c, sn) = (theta.cos(), theta.sin());
        let r = |x: f64, y: f64| (x * c - y * sn, x * sn + y * c);
        let (a, b) = r(s.0, s.1);
        let (cc, d) = r(s.2, s.3);
        let (e, f) = r(s.4, s.5);
        let (g, h) = r(s.6, s.7);
        (a, b, cc, d, e, f, g, h)
    }

    fn scale(s: Seg8, k: f64) -> Seg8 {
        (s.0 * k, s.1 * k, s.2 * k, s.3 * k, s.4 * k, s.5 * k, s.6 * k, s.7 * k)
    }

    proptest! {
        #![proptest_config(ProptestConfig { cases: 2000, ..ProptestConfig::default() })]

        /// P1. A distance is never negative.
        #[test]
        fn p1_distance_is_non_negative(s in seg_pair()) {
            prop_assert!(dist(s) >= 0.0, "negative distance {}", dist(s));
        }

        /// P2. Swapping the two segments is bit-exact, not merely close. The
        /// distance is a minimum over the same four endpoint-to-opposite-segment
        /// values regardless of argument order, so any difference means the
        /// reduction is order-dependent.
        ///
        /// This is the property most exposed to the wasm/native divergence: this
        /// module sits alongside the `dlsym`-resolved CPython libm, and on wasm32
        /// those calls fall back to Rust's libm. Bit-exactness is expected to
        /// hold on both individually; it is equality *across* the two builds that
        /// is not promised.
        #[test]
        fn p2_swapping_segments_is_bit_exact(s in seg_pair()) {
            let swapped = (s.4, s.5, s.6, s.7, s.0, s.1, s.2, s.3);
            prop_assert_eq!(dist(s), dist(swapped));
        }

        /// P3. Moving a point directly away from a segment never decreases its
        /// distance.
        #[test]
        fn p3_distance_is_monotonic_moving_away(
            x1 in coord(), y1 in coord(), x2 in coord(), y2 in coord(),
            px in coord(), py in coord(), step in 0.1f64..10.0f64,
        ) {
            let near = point_to_segment_distance(px, py, x1, y1, x2, y2);
            let (cx, cy) = closest_point_on_segment(px, py, x1, y1, x2, y2);
            let (dx, dy) = (px - cx, py - cy);
            let len = (dx * dx + dy * dy).sqrt();
            prop_assume!(len > 1e-9); // on the segment: "away" has no direction
            let far = point_to_segment_distance(
                px + dx / len * step, py + dy / len * step, x1, y1, x2, y2,
            );
            prop_assert!(far >= near - 1e-9, "{far} < {near}");
        }

        /// P4. Distance is bounded above by the distance between midpoints —
        /// the midpoints are two points on the segments, so the minimum over all
        /// pairs cannot exceed them.
        #[test]
        fn p4_distance_is_bounded_by_midpoints(s in seg_pair()) {
            let (m1x, m1y) = ((s.0 + s.2) / 2.0, (s.1 + s.3) / 2.0);
            let (m2x, m2y) = ((s.4 + s.6) / 2.0, (s.5 + s.7) / 2.0);
            let mid = ((m1x - m2x).powi(2) + (m1y - m2y).powi(2)).sqrt();
            prop_assert!(dist(s) <= mid + 1e-9, "{} > {mid}", dist(s));
        }

        /// P5. The IPC-2221 creepage bracket is non-decreasing in voltage. A
        /// higher voltage must never require less clearance — an inversion here
        /// would under-specify isolation on a mains-connected board.
        #[test]
        fn p5_creepage_bracket_is_monotonic_in_voltage(
            a in 0.0f64..1200.0, b in 0.0f64..1200.0,
        ) {
            let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
            prop_assert!(
                required_creepage_bracket(hi) >= required_creepage_bracket(lo),
                "bracket({hi}) < bracket({lo})"
            );
        }

        /// M1 (metamorphic). Translating both segments together leaves the
        /// distance unchanged. Tolerance rather than equality because the
        /// translation itself loses low bits at board scale.
        #[test]
        fn m1_distance_invariant_under_translation(
            s in seg_pair(), tx in -100.0f64..100.0, ty in -100.0f64..100.0,
        ) {
            let before = dist(s);
            let after = dist(translate(s, tx, ty));
            prop_assert!((after - before).abs() < 1e-6, "{before} -> {after}");
        }

        /// M2 (metamorphic). Rotating both segments about the origin leaves the
        /// distance unchanged, up to cos/sin rounding.
        #[test]
        fn m2_distance_invariant_under_rotation(
            s in seg_pair(), theta in 0.0f64..std::f64::consts::TAU,
        ) {
            let before = dist(s);
            let after = dist(rotate(s, theta));
            prop_assert!((after - before).abs() < 1e-6, "{before} -> {after}");
        }

        /// M3 (metamorphic). Scaling both segments by k scales the distance by
        /// k. This relation is not in the Python source; it is added here
        /// because a distance kernel that is translation- and rotation-invariant
        /// can still get units wrong, and scale is what catches that.
        #[test]
        fn m3_distance_scales_with_geometry(s in seg_pair(), k in 0.1f64..10.0) {
            let before = dist(s);
            let after = dist(scale(s, k));
            let expected = before * k;
            prop_assert!(
                (after - expected).abs() <= 1e-6 * expected.max(1.0),
                "scaling by {k}: expected {expected}, got {after}"
            );
        }
    }
}
