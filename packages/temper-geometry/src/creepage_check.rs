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
///
/// Canonical point-to-segment distance for the repo (issue #987): the three
/// Wave-4 reimplementations in `temper-design-bundle`/`temper-drc-rs`
/// (constraint_model.rs, deterministic_phase.rs, deterministic_leaf_drc.rs)
/// were deduplicated onto this kernel on 2026-08-11. The 1-ulp divergence
/// from their `sqrt`/`pow` closes is documented in
/// `docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md`.
pub fn point_to_segment_distance(
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
///
/// UNSOURCED (flagged 2026-08-15, safety-assertion audit): this table is
/// hedged in-source as "(simplified)" and there is NO recovered IPC-2221
/// table anywhere in docs/ -- the values are SNAPSHOT pins of this
/// implementation, not verified against primary text. Do not present them
/// as a sourced IPC-2221 figure. The bracket data is duplicated in
/// tests/router_v6/_ipc2221_brackets.py (single shared test-data copy,
/// UNSOURCED label there) and in this crate's own unit test
/// `required_creepage_brackets` below; `_calculate_required_creepage`'s
/// docstring documents the table for the Python surface.
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
        // SNAPSHOT pin of the (simplified) IPC-2221 bracket table. UNSOURCED:
        // no recovered IPC-2221 table exists in docs/; see the
        // `required_creepage_bracket` doc comment. Shared test data lives in
        // tests/router_v6/_ipc2221_brackets.py.
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


    // ------------------------------------------------------------------
    // Deterministic wasm32 mirrors of the 15 properties in `mod properties`
    // below (P1-P5, M1-M3, P6-P12). `proptest` is a dev-dependency and does
    // not link into this crate's `wasm-registry` (non-test) build (see
    // `scripts/gen_wasm_test_registry.py`'s `PROPTEST_USE` exclusion), so
    // the native `proptest!` block below is UNCHANGED and keeps exploring
    // randomly on the native tier. These are a deterministic, seeded,
    // `wasm32`-reachable sibling -- same shape as
    // `temper-orchestration/src/clearance.rs`'s and
    // `temper-drc-rs/src/rules/drc/property_campaigns.rs`'s mirrors.
    //
    // Every property here targets a private kernel of this module
    // (`segment_to_segment_info`, `closest_point_on_segment`,
    // `required_creepage_bracket`), so it cannot be reached from a sibling
    // top-level campaign module the way `temper-geometry`'s existing
    // `property_campaigns*.rs` reach only `pub` kernels -- it has to live
    // here, inside this module's own `mod tests`, where `use super::*`
    // already gives it access.
    //
    // The uniform-sampling trap (see this crate's own keepout-property
    // precedent, and `temper-thermal`/`temper-quality-oracle`/
    // `temper-io-types`'s versions of the same failure): a CLEARANCE
    // property is exactly the shape that trap targets. Two segments drawn
    // uniformly at random over a board-scale range are essentially always
    // far apart, so a naive seeded mirror would report green forever
    // without ever exercising the near-threshold / touching / crossing
    // region the kernel exists to get right. Every generator below that
    // feeds a clearance-relevant property (`cc_gen_seg_pair`,
    // `cc_gen_point_seg_close`, `cc_gen_voltage_pair`) is deliberately
    // biased toward that region, and each has its own coverage-guard test
    // below that measures and asserts a minimum non-trivial hit rate
    // instead of merely hoping for one -- see each guard's doc comment for
    // the measured number.
    //
    // SplitMix64 is duplicated here rather than imported from a shared
    // module -- this crate's own precedent (`property_campaigns_2.rs` /
    // `property_campaigns_3.rs`'s doc comments) duplicates this same
    // ~30-line PRNG per campaign file specifically so appending to one
    // file can never collide with a concurrent agent's edits to another;
    // the same reasoning applies to this file, which a concurrent agent
    // mirroring `smooth.rs`/`polygon.rs`/`grid_raster.rs`/`units.rs` does
    // not touch.
    // ------------------------------------------------------------------
    struct SplitMix64(u64);

    impl SplitMix64 {
        fn new(seed: u64) -> Self {
            Self(seed)
        }

        fn next_u64(&mut self) -> u64 {
            self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = self.0;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        }

        /// Uniform float in `[0, 1)`.
        fn next_f64(&mut self) -> f64 {
            (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
        }

        /// Uniform float in `[lo, hi)`.
        fn range(&mut self, lo: f64, hi: f64) -> f64 {
            lo + self.next_f64() * (hi - lo)
        }

        /// Uniform index in `[0, n)`.
        fn index(&mut self, n: usize) -> usize {
            (self.next_u64() % n as u64) as usize
        }
    }

    /// A property-local PRNG stream, independent of the base-case
    /// generator's own stream, so a property's extra randomized parameter
    /// (translation, rotation, scale, step) never correlates with which
    /// base case `seed` produced -- same pattern as
    /// `temper-drc-rs/src/rules/drc/property_campaigns.rs`'s `sub_rng`.
    fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
        SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
    }

    // --- Shared generator: seg_pair (feeds P1, P2, P4, M1, M2, M3) -----

    type CcSeg8 = (f64, f64, f64, f64, f64, f64, f64, f64);

    fn cc_dist(s: CcSeg8) -> f64 {
        segment_to_segment_info(s.0, s.1, s.2, s.3, s.4, s.5, s.6, s.7).0
    }

    /// IPC-2221 bracket thresholds (mm) this module's own
    /// `required_creepage_bracket` enforces, plus zero -- the separations
    /// worth biasing toward for a segment-to-segment clearance kernel.
    const CC_GAP_SCALE: [f64; 6] = [0.0, 0.13, 0.5, 1.6, 3.2, 8.0];

    /// A segment pair over the native `coord()` board-scale domain
    /// (-50..50mm). `seed % 3 == 0` draws two fully independent random
    /// segments (the native strategy's own domain -- almost always far
    /// apart: see `cc_seg_pair_coverage_guard_hits_close_and_crossing_cases`
    /// for the measured rate). `seed % 3 == 1` deliberately builds a base
    /// segment and a parallel twin offset by a small, creepage-scale gap.
    /// `seed % 3 == 2` deliberately builds two segments that PROPERLY cross
    /// (distance exactly 0 via the `segments_intersect` shortcut) by
    /// constructing both through a shared interior point at transversal
    /// angles.
    fn cc_gen_seg_pair(seed: u64) -> CcSeg8 {
        let mut rng = SplitMix64::new(seed);
        match seed % 3 {
            0 => (
                rng.range(-50.0, 50.0), rng.range(-50.0, 50.0),
                rng.range(-50.0, 50.0), rng.range(-50.0, 50.0),
                rng.range(-50.0, 50.0), rng.range(-50.0, 50.0),
                rng.range(-50.0, 50.0), rng.range(-50.0, 50.0),
            ),
            1 => {
                let x1 = rng.range(-40.0, 40.0);
                let y1 = rng.range(-40.0, 40.0);
                let len = rng.range(1.0, 20.0);
                let theta = rng.range(0.0, std::f64::consts::TAU);
                let x2 = x1 + len * theta.cos();
                let y2 = y1 + len * theta.sin();
                let gap = CC_GAP_SCALE[rng.index(CC_GAP_SCALE.len())] + rng.range(0.0, 0.05);
                let (perp_x, perp_y) = (-theta.sin(), theta.cos());
                let x3 = x1 + perp_x * gap;
                let y3 = y1 + perp_y * gap;
                let x4 = x2 + perp_x * gap;
                let y4 = y2 + perp_y * gap;
                (x1, y1, x2, y2, x3, y3, x4, y4)
            }
            _ => {
                let cx = rng.range(-40.0, 40.0);
                let cy = rng.range(-40.0, 40.0);
                let theta1 = rng.range(0.0, std::f64::consts::PI);
                let a1 = rng.range(1.0, 15.0);
                let b1 = rng.range(1.0, 15.0);
                let x1 = cx - a1 * theta1.cos();
                let y1 = cy - a1 * theta1.sin();
                let x2 = cx + b1 * theta1.cos();
                let y2 = cy + b1 * theta1.sin();
                // A distinct, non-parallel, non-coincident second angle:
                // the offset stays inside (0.15, PI - 0.15) so the two
                // lines through (cx, cy) are never parallel (0) or the
                // same line traversed the other way (PI).
                let theta2 = theta1 + rng.range(0.15, std::f64::consts::PI - 0.15);
                let a2 = rng.range(1.0, 15.0);
                let b2 = rng.range(1.0, 15.0);
                let x3 = cx - a2 * theta2.cos();
                let y3 = cy - a2 * theta2.sin();
                let x4 = cx + b2 * theta2.cos();
                let y4 = cy + b2 * theta2.sin();
                (x1, y1, x2, y2, x3, y3, x4, y4)
            }
        }
    }

    fn cc_p1_distance_is_non_negative_impl(seed: u64) {
        let d = cc_dist(cc_gen_seg_pair(seed));
        assert!(d >= 0.0, "seed={seed}: negative distance {d}");
    }

    fn cc_p2_swapping_segments_is_bit_exact_impl(seed: u64) {
        let s = cc_gen_seg_pair(seed);
        let swapped = (s.4, s.5, s.6, s.7, s.0, s.1, s.2, s.3);
        assert_eq!(cc_dist(s), cc_dist(swapped), "seed={seed}");
    }

    fn cc_p4_distance_is_bounded_by_midpoints_impl(seed: u64) {
        let s = cc_gen_seg_pair(seed);
        let (m1x, m1y) = ((s.0 + s.2) / 2.0, (s.1 + s.3) / 2.0);
        let (m2x, m2y) = ((s.4 + s.6) / 2.0, (s.5 + s.7) / 2.0);
        let mid = ((m1x - m2x).powi(2) + (m1y - m2y).powi(2)).sqrt();
        let d = cc_dist(s);
        assert!(d <= mid + 1e-9, "seed={seed}: {d} > {mid}");
    }

    fn cc_m1_distance_invariant_under_translation_impl(seed: u64) {
        let s = cc_gen_seg_pair(seed);
        let mut rng = sub_rng(seed, 0xA1);
        let tx = rng.range(-100.0, 100.0);
        let ty = rng.range(-100.0, 100.0);
        let translated = (
            s.0 + tx, s.1 + ty, s.2 + tx, s.3 + ty,
            s.4 + tx, s.5 + ty, s.6 + tx, s.7 + ty,
        );
        let before = cc_dist(s);
        let after = cc_dist(translated);
        assert!((after - before).abs() < 1e-6, "seed={seed}: {before} -> {after}");
    }

    fn cc_m2_distance_invariant_under_rotation_impl(seed: u64) {
        let s = cc_gen_seg_pair(seed);
        let mut rng = sub_rng(seed, 0xA2);
        let theta = rng.range(0.0, std::f64::consts::TAU);
        let (c, sn) = (theta.cos(), theta.sin());
        let r = |x: f64, y: f64| (x * c - y * sn, x * sn + y * c);
        let (a, b) = r(s.0, s.1);
        let (cc, d) = r(s.2, s.3);
        let (e, f) = r(s.4, s.5);
        let (g, h) = r(s.6, s.7);
        let rotated = (a, b, cc, d, e, f, g, h);
        let before = cc_dist(s);
        let after = cc_dist(rotated);
        assert!((after - before).abs() < 1e-6, "seed={seed}: {before} -> {after}");
    }

    fn cc_m3_distance_scales_with_geometry_impl(seed: u64) {
        let s = cc_gen_seg_pair(seed);
        let mut rng = sub_rng(seed, 0xA3);
        let k = rng.range(0.1, 10.0);
        let scaled = (
            s.0 * k, s.1 * k, s.2 * k, s.3 * k,
            s.4 * k, s.5 * k, s.6 * k, s.7 * k,
        );
        let before = cc_dist(s);
        let after = cc_dist(scaled);
        let expected = before * k;
        assert!(
            (after - expected).abs() <= 1e-6 * expected.max(1.0),
            "seed={seed}: scaling by {k}: expected {expected}, got {after}"
        );
    }

    /// Measures the `cc_gen_seg_pair` corpus's own hit rate against the
    /// two branches its comment claims: exact touching/crossing
    /// (`dist == 0.0`) and creepage-relevant closeness (`dist < 5.0` mm).
    /// Measured at N=50: 19/50 (38%) exactly 0.0 (the `seed % 3 == 2`
    /// crossing branch), 40/50 (80%) within 5mm (crossing + the
    /// `seed % 3 == 1` small-gap branch). Thresholds below are set with
    /// headroom under those measured numbers so the guard fails loudly,
    /// not flakily, if the generator regresses toward the
    /// uniform-sampling trap this module's own doc comment warns about.
    #[cfg_attr(test, test)]
    fn cc_seg_pair_coverage_guard_hits_close_and_crossing_cases() {
        let n = 50u64;
        let mut close = 0u32;
        let mut zero = 0u32;
        for seed in 0..n {
            let d = cc_dist(cc_gen_seg_pair(seed));
            if d < 5.0 {
                close += 1;
            }
            if d == 0.0 {
                zero += 1;
            }
        }
        assert!(close * 100 >= n as u32 * 40, "only {close}/{n} seeds landed within 5mm (close+crossing)");
        assert!(zero * 100 >= n as u32 * 15, "only {zero}/{n} seeds landed exactly on a crossing/touching case");
    }

    // --- Shared generator: point_seg_close (feeds P3, P6, P9, P10, P11) --

    /// A `(px, py, x1, y1, x2, y2)` case biased toward the point being
    /// close to (or exactly on, or just past an endpoint of) the segment
    /// -- the region where the clamped projection and the
    /// `py_min`/`py_max` builtin-NaN-semantics branches actually matter.
    /// `seed % 3 == 0` draws all six coordinates independently from
    /// `wide_coord()` (the native strategy's own domain); see
    /// `cc_point_seg_close_coverage_guard` for how rarely that alone lands
    /// near the segment. The other two thirds place the point at a
    /// parametric position along (or just past) the segment, offset
    /// perpendicular by a small, creepage-scale distance.
    fn cc_gen_point_seg_close(seed: u64) -> (f64, f64, f64, f64, f64, f64) {
        let mut rng = SplitMix64::new(seed);
        match seed % 3 {
            0 => (
                rng.range(-200.0, 200.0), rng.range(-200.0, 200.0),
                rng.range(-200.0, 200.0), rng.range(-200.0, 200.0),
                rng.range(-200.0, 200.0), rng.range(-200.0, 200.0),
            ),
            _ => {
                let x1 = rng.range(-150.0, 150.0);
                let y1 = rng.range(-150.0, 150.0);
                let len = rng.range(1.0, 40.0);
                let theta = rng.range(0.0, std::f64::consts::TAU);
                let x2 = x1 + len * theta.cos();
                let y2 = y1 + len * theta.sin();
                // t in [-0.2, 1.2]: mostly interior, sometimes just past
                // an endpoint -- the clamp region P12 targets explicitly
                // and this shared generator exercises incidentally too.
                let t = rng.range(-0.2, 1.2);
                let along_x = x1 + t * len * theta.cos();
                let along_y = y1 + t * len * theta.sin();
                let offset = rng.range(0.0, 8.0);
                let (perp_x, perp_y) = (-theta.sin(), theta.cos());
                let px = along_x + perp_x * offset;
                let py = along_y + perp_y * offset;
                (px, py, x1, y1, x2, y2)
            }
        }
    }

    fn cc_p3_distance_is_monotonic_moving_away_impl(seed: u64) {
        let (px, py, x1, y1, x2, y2) = cc_gen_point_seg_close(seed);
        let mut rng = sub_rng(seed, 0xB3);
        let step = rng.range(0.1, 10.0);
        let near = point_to_segment_distance(px, py, x1, y1, x2, y2);
        let (cx, cy) = closest_point_on_segment(px, py, x1, y1, x2, y2);
        let (dx, dy) = (px - cx, py - cy);
        let len = (dx * dx + dy * dy).sqrt();
        if len <= 1e-9 {
            // On the segment: "away" has no direction -- same skip the
            // native proptest's `prop_assume!` makes.
            return;
        }
        let far = point_to_segment_distance(
            px + dx / len * step, py + dy / len * step, x1, y1, x2, y2,
        );
        assert!(far >= near - 1e-9, "seed={seed}: {far} < {near}");
    }

    fn cc_p6_ptsd_is_non_negative_impl(seed: u64) {
        let (px, py, x1, y1, x2, y2) = cc_gen_point_seg_close(seed);
        let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
        assert!(d >= 0.0, "seed={seed}: negative distance {d}");
    }

    fn cc_p9_ptsd_bounded_by_endpoints_impl(seed: u64) {
        let (px, py, x1, y1, x2, y2) = cc_gen_point_seg_close(seed);
        if (x2 - x1).powi(2) + (y2 - y1).powi(2) < 1e-6 {
            return; // degenerate segment; same filter non_degenerate_seg applies
        }
        let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
        let de1 = crate::pad_geometry::py_hypot(px - x1, py - y1);
        let de2 = crate::pad_geometry::py_hypot(px - x2, py - y2);
        let bound = de1.min(de2);
        assert!(d <= bound + 1e-12, "seed={seed}: ptsd={d} > min(de1={de1}, de2={de2})");
    }

    fn cc_p10_ptsd_segment_reversal_preserves_distance_impl(seed: u64) {
        let (px, py, x1, y1, x2, y2) = cc_gen_point_seg_close(seed);
        let forward = point_to_segment_distance(px, py, x1, y1, x2, y2);
        let reversed = point_to_segment_distance(px, py, x2, y2, x1, y1);
        assert!(
            (forward - reversed).abs() <= 1e-9,
            "seed={seed}: forward {forward} != reversed {reversed} (diff {})",
            (forward - reversed).abs()
        );
    }

    fn cc_p11_ptsd_translation_invariant_impl(seed: u64) {
        let (px, py, x1, y1, x2, y2) = cc_gen_point_seg_close(seed);
        let mut rng = sub_rng(seed, 0xB1);
        let tx = rng.range(-100.0, 100.0);
        let ty = rng.range(-100.0, 100.0);
        let before = point_to_segment_distance(px, py, x1, y1, x2, y2);
        let after = point_to_segment_distance(px + tx, py + ty, x1 + tx, y1 + ty, x2 + tx, y2 + ty);
        assert!((after - before).abs() < 1e-6, "seed={seed}: {before} -> {after} after translation");
    }

    /// Measures how often `cc_gen_point_seg_close` lands within 5mm of the
    /// segment -- the region P3/P6/P9/P10/P11 need to actually exercise
    /// the clamp/near-zero code paths rather than trivially passing on a
    /// far-away point. Measured at N=50: 24/50 (48%) within 5mm.
    #[cfg_attr(test, test)]
    fn cc_point_seg_close_coverage_guard() {
        let n = 50u64;
        let mut near = 0u32;
        for seed in 0..n {
            let (px, py, x1, y1, x2, y2) = cc_gen_point_seg_close(seed);
            let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
            if d < 5.0 {
                near += 1;
            }
        }
        assert!(near * 100 >= n as u32 * 40, "only {near}/{n} seeds landed within 5mm of the segment");
    }

    // --- P5: creepage bracket boundary straddling -----------------------

    /// The 9 IPC-2221 bracket breakpoints `required_creepage_bracket`
    /// switches on.
    const CC_BRACKETS: [f64; 9] = [15.0, 30.0, 50.0, 100.0, 150.0, 170.0, 250.0, 300.0, 600.0];

    /// A `(lo, hi)` voltage pair (`lo <= hi`). `seed % 3 == 0` draws
    /// uniformly over the full 0..1200V range -- the native strategy's own
    /// domain, where `lo` and `hi` land in the SAME bracket on most draws
    /// (10 brackets spread unevenly over 1200V), making the monotonicity
    /// check trivially true (`bracket(hi) == bracket(lo)`) without ever
    /// exercising the actual step. The other two thirds deliberately
    /// straddle one of the 9 breakpoints (by a random small margin, or
    /// pinned exactly at the breakpoint on the low side) so the mirror
    /// actually walks the step function.
    fn cc_gen_voltage_pair(seed: u64) -> (f64, f64) {
        let mut rng = SplitMix64::new(seed);
        match seed % 3 {
            0 => {
                let a = rng.range(0.0, 1200.0);
                let b = rng.range(0.0, 1200.0);
                if a <= b { (a, b) } else { (b, a) }
            }
            1 => {
                let bp = CC_BRACKETS[rng.index(CC_BRACKETS.len())];
                let delta = rng.range(0.01, 5.0);
                (bp - delta, bp + delta)
            }
            _ => {
                let bp = CC_BRACKETS[rng.index(CC_BRACKETS.len())];
                let delta = rng.range(0.001, 3.0);
                (bp, bp + delta)
            }
        }
    }

    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(seed: u64) {
        let (lo, hi) = cc_gen_voltage_pair(seed);
        assert!(
            required_creepage_bracket(hi) >= required_creepage_bracket(lo),
            "seed={seed}: bracket({hi}) < bracket({lo})"
        );
    }

    /// Measures how often `cc_gen_voltage_pair` actually straddles a
    /// bracket boundary (`bracket(lo) != bracket(hi)`) rather than landing
    /// in the same bracket on both sides. Measured at N=50: 42/50 (84%)
    /// straddle a boundary.
    #[cfg_attr(test, test)]
    fn cc_p5_coverage_guard_straddles_a_bracket() {
        let n = 50u64;
        let mut straddle = 0u32;
        for seed in 0..n {
            let (lo, hi) = cc_gen_voltage_pair(seed);
            if required_creepage_bracket(hi) != required_creepage_bracket(lo) {
                straddle += 1;
            }
        }
        assert!(straddle * 100 >= n as u32 * 40, "only {straddle}/{n} seeds crossed a bracket boundary");
    }

    // --- P7, P8, P12: already target the interesting region by ---------
    // --- construction (on-segment / degenerate / collinear-beyond), so --
    // --- no separate biased generator or coverage guard is needed: the --
    // --- assertion IS the proof, on every seed. ------------------------

    fn cc_p7_ptsd_zero_on_segment_interior_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x1 = rng.range(-200.0, 200.0);
        let y1 = rng.range(-200.0, 200.0);
        let x2 = rng.range(-200.0, 200.0);
        let y2 = rng.range(-200.0, 200.0);
        if (x2 - x1).powi(2) + (y2 - y1).powi(2) < 1e-6 {
            return;
        }
        let t = rng.range(0.0, 1.0);
        let px = x1 + t * (x2 - x1);
        let py = y1 + t * (y2 - y1);
        let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
        assert!(d < 1e-10, "seed={seed}: distance to point on segment interior is {d} (should be 0)");
    }

    fn cc_p8_ptsd_degenerate_is_py_hypot_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let px = rng.range(-200.0, 200.0);
        let py = rng.range(-200.0, 200.0);
        let sx = rng.range(-200.0, 200.0);
        let sy = rng.range(-200.0, 200.0);
        let got = point_to_segment_distance(px, py, sx, sy, sx, sy);
        let expected = crate::pad_geometry::py_hypot(px - sx, py - sy);
        assert_eq!(got, expected, "seed={seed}: degenerate-segment distance mismatch");
    }

    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x1 = rng.range(-200.0, 200.0);
        let y1 = rng.range(-200.0, 200.0);
        let x2 = rng.range(-200.0, 200.0);
        let y2 = rng.range(-200.0, 200.0);
        if (x2 - x1).powi(2) + (y2 - y1).powi(2) < 1e-6 {
            return;
        }
        let dx = x2 - x1;
        let dy = y2 - y1;
        let beyond_factor = if seed.is_multiple_of(2) { -1.0 } else { 2.0 };
        let px = x1 + beyond_factor * dx;
        let py = y1 + beyond_factor * dy;
        let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
        let de1 = crate::pad_geometry::py_hypot(px - x1, py - y1);
        let de2 = crate::pad_geometry::py_hypot(px - x2, py - y2);
        let expected = de1.min(de2);
        assert!(
            (d - expected).abs() < 1e-12,
            "seed={seed}: collinear-beyond: got {d} vs endpoint min {expected}"
        );
    }


    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors) ---
    // 15 properties x 50 seeds = 750 distinct-input wasm tests.
    // --- cc_p1_distance_is_non_negative: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_000() { cc_p1_distance_is_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_001() { cc_p1_distance_is_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_002() { cc_p1_distance_is_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_003() { cc_p1_distance_is_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_004() { cc_p1_distance_is_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_005() { cc_p1_distance_is_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_006() { cc_p1_distance_is_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_007() { cc_p1_distance_is_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_008() { cc_p1_distance_is_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_009() { cc_p1_distance_is_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_010() { cc_p1_distance_is_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_011() { cc_p1_distance_is_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_012() { cc_p1_distance_is_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_013() { cc_p1_distance_is_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_014() { cc_p1_distance_is_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_015() { cc_p1_distance_is_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_016() { cc_p1_distance_is_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_017() { cc_p1_distance_is_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_018() { cc_p1_distance_is_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_019() { cc_p1_distance_is_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_020() { cc_p1_distance_is_non_negative_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_021() { cc_p1_distance_is_non_negative_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_022() { cc_p1_distance_is_non_negative_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_023() { cc_p1_distance_is_non_negative_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_024() { cc_p1_distance_is_non_negative_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_025() { cc_p1_distance_is_non_negative_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_026() { cc_p1_distance_is_non_negative_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_027() { cc_p1_distance_is_non_negative_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_028() { cc_p1_distance_is_non_negative_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_029() { cc_p1_distance_is_non_negative_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_030() { cc_p1_distance_is_non_negative_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_031() { cc_p1_distance_is_non_negative_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_032() { cc_p1_distance_is_non_negative_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_033() { cc_p1_distance_is_non_negative_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_034() { cc_p1_distance_is_non_negative_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_035() { cc_p1_distance_is_non_negative_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_036() { cc_p1_distance_is_non_negative_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_037() { cc_p1_distance_is_non_negative_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_038() { cc_p1_distance_is_non_negative_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_039() { cc_p1_distance_is_non_negative_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_040() { cc_p1_distance_is_non_negative_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_041() { cc_p1_distance_is_non_negative_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_042() { cc_p1_distance_is_non_negative_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_043() { cc_p1_distance_is_non_negative_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_044() { cc_p1_distance_is_non_negative_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_045() { cc_p1_distance_is_non_negative_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_046() { cc_p1_distance_is_non_negative_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_047() { cc_p1_distance_is_non_negative_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_048() { cc_p1_distance_is_non_negative_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p1_distance_is_non_negative_seed_049() { cc_p1_distance_is_non_negative_impl(49); }
    // --- cc_p2_swapping_segments_is_bit_exact: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_000() { cc_p2_swapping_segments_is_bit_exact_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_001() { cc_p2_swapping_segments_is_bit_exact_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_002() { cc_p2_swapping_segments_is_bit_exact_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_003() { cc_p2_swapping_segments_is_bit_exact_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_004() { cc_p2_swapping_segments_is_bit_exact_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_005() { cc_p2_swapping_segments_is_bit_exact_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_006() { cc_p2_swapping_segments_is_bit_exact_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_007() { cc_p2_swapping_segments_is_bit_exact_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_008() { cc_p2_swapping_segments_is_bit_exact_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_009() { cc_p2_swapping_segments_is_bit_exact_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_010() { cc_p2_swapping_segments_is_bit_exact_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_011() { cc_p2_swapping_segments_is_bit_exact_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_012() { cc_p2_swapping_segments_is_bit_exact_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_013() { cc_p2_swapping_segments_is_bit_exact_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_014() { cc_p2_swapping_segments_is_bit_exact_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_015() { cc_p2_swapping_segments_is_bit_exact_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_016() { cc_p2_swapping_segments_is_bit_exact_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_017() { cc_p2_swapping_segments_is_bit_exact_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_018() { cc_p2_swapping_segments_is_bit_exact_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_019() { cc_p2_swapping_segments_is_bit_exact_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_020() { cc_p2_swapping_segments_is_bit_exact_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_021() { cc_p2_swapping_segments_is_bit_exact_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_022() { cc_p2_swapping_segments_is_bit_exact_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_023() { cc_p2_swapping_segments_is_bit_exact_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_024() { cc_p2_swapping_segments_is_bit_exact_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_025() { cc_p2_swapping_segments_is_bit_exact_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_026() { cc_p2_swapping_segments_is_bit_exact_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_027() { cc_p2_swapping_segments_is_bit_exact_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_028() { cc_p2_swapping_segments_is_bit_exact_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_029() { cc_p2_swapping_segments_is_bit_exact_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_030() { cc_p2_swapping_segments_is_bit_exact_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_031() { cc_p2_swapping_segments_is_bit_exact_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_032() { cc_p2_swapping_segments_is_bit_exact_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_033() { cc_p2_swapping_segments_is_bit_exact_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_034() { cc_p2_swapping_segments_is_bit_exact_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_035() { cc_p2_swapping_segments_is_bit_exact_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_036() { cc_p2_swapping_segments_is_bit_exact_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_037() { cc_p2_swapping_segments_is_bit_exact_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_038() { cc_p2_swapping_segments_is_bit_exact_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_039() { cc_p2_swapping_segments_is_bit_exact_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_040() { cc_p2_swapping_segments_is_bit_exact_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_041() { cc_p2_swapping_segments_is_bit_exact_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_042() { cc_p2_swapping_segments_is_bit_exact_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_043() { cc_p2_swapping_segments_is_bit_exact_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_044() { cc_p2_swapping_segments_is_bit_exact_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_045() { cc_p2_swapping_segments_is_bit_exact_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_046() { cc_p2_swapping_segments_is_bit_exact_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_047() { cc_p2_swapping_segments_is_bit_exact_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_048() { cc_p2_swapping_segments_is_bit_exact_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p2_swapping_segments_is_bit_exact_seed_049() { cc_p2_swapping_segments_is_bit_exact_impl(49); }
    // --- cc_p3_distance_is_monotonic_moving_away: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_000() { cc_p3_distance_is_monotonic_moving_away_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_001() { cc_p3_distance_is_monotonic_moving_away_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_002() { cc_p3_distance_is_monotonic_moving_away_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_003() { cc_p3_distance_is_monotonic_moving_away_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_004() { cc_p3_distance_is_monotonic_moving_away_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_005() { cc_p3_distance_is_monotonic_moving_away_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_006() { cc_p3_distance_is_monotonic_moving_away_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_007() { cc_p3_distance_is_monotonic_moving_away_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_008() { cc_p3_distance_is_monotonic_moving_away_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_009() { cc_p3_distance_is_monotonic_moving_away_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_010() { cc_p3_distance_is_monotonic_moving_away_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_011() { cc_p3_distance_is_monotonic_moving_away_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_012() { cc_p3_distance_is_monotonic_moving_away_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_013() { cc_p3_distance_is_monotonic_moving_away_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_014() { cc_p3_distance_is_monotonic_moving_away_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_015() { cc_p3_distance_is_monotonic_moving_away_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_016() { cc_p3_distance_is_monotonic_moving_away_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_017() { cc_p3_distance_is_monotonic_moving_away_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_018() { cc_p3_distance_is_monotonic_moving_away_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_019() { cc_p3_distance_is_monotonic_moving_away_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_020() { cc_p3_distance_is_monotonic_moving_away_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_021() { cc_p3_distance_is_monotonic_moving_away_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_022() { cc_p3_distance_is_monotonic_moving_away_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_023() { cc_p3_distance_is_monotonic_moving_away_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_024() { cc_p3_distance_is_monotonic_moving_away_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_025() { cc_p3_distance_is_monotonic_moving_away_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_026() { cc_p3_distance_is_monotonic_moving_away_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_027() { cc_p3_distance_is_monotonic_moving_away_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_028() { cc_p3_distance_is_monotonic_moving_away_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_029() { cc_p3_distance_is_monotonic_moving_away_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_030() { cc_p3_distance_is_monotonic_moving_away_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_031() { cc_p3_distance_is_monotonic_moving_away_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_032() { cc_p3_distance_is_monotonic_moving_away_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_033() { cc_p3_distance_is_monotonic_moving_away_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_034() { cc_p3_distance_is_monotonic_moving_away_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_035() { cc_p3_distance_is_monotonic_moving_away_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_036() { cc_p3_distance_is_monotonic_moving_away_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_037() { cc_p3_distance_is_monotonic_moving_away_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_038() { cc_p3_distance_is_monotonic_moving_away_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_039() { cc_p3_distance_is_monotonic_moving_away_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_040() { cc_p3_distance_is_monotonic_moving_away_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_041() { cc_p3_distance_is_monotonic_moving_away_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_042() { cc_p3_distance_is_monotonic_moving_away_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_043() { cc_p3_distance_is_monotonic_moving_away_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_044() { cc_p3_distance_is_monotonic_moving_away_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_045() { cc_p3_distance_is_monotonic_moving_away_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_046() { cc_p3_distance_is_monotonic_moving_away_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_047() { cc_p3_distance_is_monotonic_moving_away_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_048() { cc_p3_distance_is_monotonic_moving_away_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p3_distance_is_monotonic_moving_away_seed_049() { cc_p3_distance_is_monotonic_moving_away_impl(49); }
    // --- cc_p4_distance_is_bounded_by_midpoints: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_000() { cc_p4_distance_is_bounded_by_midpoints_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_001() { cc_p4_distance_is_bounded_by_midpoints_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_002() { cc_p4_distance_is_bounded_by_midpoints_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_003() { cc_p4_distance_is_bounded_by_midpoints_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_004() { cc_p4_distance_is_bounded_by_midpoints_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_005() { cc_p4_distance_is_bounded_by_midpoints_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_006() { cc_p4_distance_is_bounded_by_midpoints_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_007() { cc_p4_distance_is_bounded_by_midpoints_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_008() { cc_p4_distance_is_bounded_by_midpoints_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_009() { cc_p4_distance_is_bounded_by_midpoints_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_010() { cc_p4_distance_is_bounded_by_midpoints_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_011() { cc_p4_distance_is_bounded_by_midpoints_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_012() { cc_p4_distance_is_bounded_by_midpoints_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_013() { cc_p4_distance_is_bounded_by_midpoints_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_014() { cc_p4_distance_is_bounded_by_midpoints_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_015() { cc_p4_distance_is_bounded_by_midpoints_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_016() { cc_p4_distance_is_bounded_by_midpoints_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_017() { cc_p4_distance_is_bounded_by_midpoints_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_018() { cc_p4_distance_is_bounded_by_midpoints_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_019() { cc_p4_distance_is_bounded_by_midpoints_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_020() { cc_p4_distance_is_bounded_by_midpoints_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_021() { cc_p4_distance_is_bounded_by_midpoints_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_022() { cc_p4_distance_is_bounded_by_midpoints_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_023() { cc_p4_distance_is_bounded_by_midpoints_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_024() { cc_p4_distance_is_bounded_by_midpoints_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_025() { cc_p4_distance_is_bounded_by_midpoints_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_026() { cc_p4_distance_is_bounded_by_midpoints_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_027() { cc_p4_distance_is_bounded_by_midpoints_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_028() { cc_p4_distance_is_bounded_by_midpoints_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_029() { cc_p4_distance_is_bounded_by_midpoints_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_030() { cc_p4_distance_is_bounded_by_midpoints_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_031() { cc_p4_distance_is_bounded_by_midpoints_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_032() { cc_p4_distance_is_bounded_by_midpoints_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_033() { cc_p4_distance_is_bounded_by_midpoints_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_034() { cc_p4_distance_is_bounded_by_midpoints_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_035() { cc_p4_distance_is_bounded_by_midpoints_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_036() { cc_p4_distance_is_bounded_by_midpoints_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_037() { cc_p4_distance_is_bounded_by_midpoints_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_038() { cc_p4_distance_is_bounded_by_midpoints_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_039() { cc_p4_distance_is_bounded_by_midpoints_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_040() { cc_p4_distance_is_bounded_by_midpoints_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_041() { cc_p4_distance_is_bounded_by_midpoints_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_042() { cc_p4_distance_is_bounded_by_midpoints_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_043() { cc_p4_distance_is_bounded_by_midpoints_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_044() { cc_p4_distance_is_bounded_by_midpoints_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_045() { cc_p4_distance_is_bounded_by_midpoints_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_046() { cc_p4_distance_is_bounded_by_midpoints_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_047() { cc_p4_distance_is_bounded_by_midpoints_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_048() { cc_p4_distance_is_bounded_by_midpoints_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p4_distance_is_bounded_by_midpoints_seed_049() { cc_p4_distance_is_bounded_by_midpoints_impl(49); }
    // --- cc_p5_creepage_bracket_is_monotonic_in_voltage: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_000() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_001() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_002() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_003() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_004() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_005() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_006() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_007() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_008() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_009() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_010() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_011() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_012() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_013() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_014() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_015() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_016() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_017() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_018() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_019() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_020() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_021() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_022() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_023() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_024() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_025() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_026() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_027() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_028() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_029() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_030() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_031() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_032() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_033() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_034() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_035() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_036() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_037() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_038() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_039() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_040() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_041() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_042() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_043() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_044() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_045() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_046() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_047() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_048() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_049() { cc_p5_creepage_bracket_is_monotonic_in_voltage_impl(49); }
    // --- cc_m1_distance_invariant_under_translation: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_000() { cc_m1_distance_invariant_under_translation_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_001() { cc_m1_distance_invariant_under_translation_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_002() { cc_m1_distance_invariant_under_translation_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_003() { cc_m1_distance_invariant_under_translation_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_004() { cc_m1_distance_invariant_under_translation_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_005() { cc_m1_distance_invariant_under_translation_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_006() { cc_m1_distance_invariant_under_translation_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_007() { cc_m1_distance_invariant_under_translation_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_008() { cc_m1_distance_invariant_under_translation_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_009() { cc_m1_distance_invariant_under_translation_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_010() { cc_m1_distance_invariant_under_translation_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_011() { cc_m1_distance_invariant_under_translation_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_012() { cc_m1_distance_invariant_under_translation_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_013() { cc_m1_distance_invariant_under_translation_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_014() { cc_m1_distance_invariant_under_translation_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_015() { cc_m1_distance_invariant_under_translation_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_016() { cc_m1_distance_invariant_under_translation_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_017() { cc_m1_distance_invariant_under_translation_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_018() { cc_m1_distance_invariant_under_translation_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_019() { cc_m1_distance_invariant_under_translation_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_020() { cc_m1_distance_invariant_under_translation_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_021() { cc_m1_distance_invariant_under_translation_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_022() { cc_m1_distance_invariant_under_translation_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_023() { cc_m1_distance_invariant_under_translation_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_024() { cc_m1_distance_invariant_under_translation_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_025() { cc_m1_distance_invariant_under_translation_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_026() { cc_m1_distance_invariant_under_translation_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_027() { cc_m1_distance_invariant_under_translation_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_028() { cc_m1_distance_invariant_under_translation_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_029() { cc_m1_distance_invariant_under_translation_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_030() { cc_m1_distance_invariant_under_translation_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_031() { cc_m1_distance_invariant_under_translation_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_032() { cc_m1_distance_invariant_under_translation_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_033() { cc_m1_distance_invariant_under_translation_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_034() { cc_m1_distance_invariant_under_translation_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_035() { cc_m1_distance_invariant_under_translation_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_036() { cc_m1_distance_invariant_under_translation_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_037() { cc_m1_distance_invariant_under_translation_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_038() { cc_m1_distance_invariant_under_translation_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_039() { cc_m1_distance_invariant_under_translation_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_040() { cc_m1_distance_invariant_under_translation_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_041() { cc_m1_distance_invariant_under_translation_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_042() { cc_m1_distance_invariant_under_translation_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_043() { cc_m1_distance_invariant_under_translation_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_044() { cc_m1_distance_invariant_under_translation_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_045() { cc_m1_distance_invariant_under_translation_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_046() { cc_m1_distance_invariant_under_translation_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_047() { cc_m1_distance_invariant_under_translation_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_048() { cc_m1_distance_invariant_under_translation_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_m1_distance_invariant_under_translation_seed_049() { cc_m1_distance_invariant_under_translation_impl(49); }
    // --- cc_m2_distance_invariant_under_rotation: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_000() { cc_m2_distance_invariant_under_rotation_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_001() { cc_m2_distance_invariant_under_rotation_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_002() { cc_m2_distance_invariant_under_rotation_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_003() { cc_m2_distance_invariant_under_rotation_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_004() { cc_m2_distance_invariant_under_rotation_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_005() { cc_m2_distance_invariant_under_rotation_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_006() { cc_m2_distance_invariant_under_rotation_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_007() { cc_m2_distance_invariant_under_rotation_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_008() { cc_m2_distance_invariant_under_rotation_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_009() { cc_m2_distance_invariant_under_rotation_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_010() { cc_m2_distance_invariant_under_rotation_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_011() { cc_m2_distance_invariant_under_rotation_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_012() { cc_m2_distance_invariant_under_rotation_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_013() { cc_m2_distance_invariant_under_rotation_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_014() { cc_m2_distance_invariant_under_rotation_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_015() { cc_m2_distance_invariant_under_rotation_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_016() { cc_m2_distance_invariant_under_rotation_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_017() { cc_m2_distance_invariant_under_rotation_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_018() { cc_m2_distance_invariant_under_rotation_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_019() { cc_m2_distance_invariant_under_rotation_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_020() { cc_m2_distance_invariant_under_rotation_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_021() { cc_m2_distance_invariant_under_rotation_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_022() { cc_m2_distance_invariant_under_rotation_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_023() { cc_m2_distance_invariant_under_rotation_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_024() { cc_m2_distance_invariant_under_rotation_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_025() { cc_m2_distance_invariant_under_rotation_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_026() { cc_m2_distance_invariant_under_rotation_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_027() { cc_m2_distance_invariant_under_rotation_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_028() { cc_m2_distance_invariant_under_rotation_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_029() { cc_m2_distance_invariant_under_rotation_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_030() { cc_m2_distance_invariant_under_rotation_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_031() { cc_m2_distance_invariant_under_rotation_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_032() { cc_m2_distance_invariant_under_rotation_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_033() { cc_m2_distance_invariant_under_rotation_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_034() { cc_m2_distance_invariant_under_rotation_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_035() { cc_m2_distance_invariant_under_rotation_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_036() { cc_m2_distance_invariant_under_rotation_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_037() { cc_m2_distance_invariant_under_rotation_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_038() { cc_m2_distance_invariant_under_rotation_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_039() { cc_m2_distance_invariant_under_rotation_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_040() { cc_m2_distance_invariant_under_rotation_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_041() { cc_m2_distance_invariant_under_rotation_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_042() { cc_m2_distance_invariant_under_rotation_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_043() { cc_m2_distance_invariant_under_rotation_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_044() { cc_m2_distance_invariant_under_rotation_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_045() { cc_m2_distance_invariant_under_rotation_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_046() { cc_m2_distance_invariant_under_rotation_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_047() { cc_m2_distance_invariant_under_rotation_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_048() { cc_m2_distance_invariant_under_rotation_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_m2_distance_invariant_under_rotation_seed_049() { cc_m2_distance_invariant_under_rotation_impl(49); }
    // --- cc_m3_distance_scales_with_geometry: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_000() { cc_m3_distance_scales_with_geometry_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_001() { cc_m3_distance_scales_with_geometry_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_002() { cc_m3_distance_scales_with_geometry_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_003() { cc_m3_distance_scales_with_geometry_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_004() { cc_m3_distance_scales_with_geometry_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_005() { cc_m3_distance_scales_with_geometry_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_006() { cc_m3_distance_scales_with_geometry_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_007() { cc_m3_distance_scales_with_geometry_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_008() { cc_m3_distance_scales_with_geometry_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_009() { cc_m3_distance_scales_with_geometry_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_010() { cc_m3_distance_scales_with_geometry_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_011() { cc_m3_distance_scales_with_geometry_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_012() { cc_m3_distance_scales_with_geometry_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_013() { cc_m3_distance_scales_with_geometry_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_014() { cc_m3_distance_scales_with_geometry_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_015() { cc_m3_distance_scales_with_geometry_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_016() { cc_m3_distance_scales_with_geometry_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_017() { cc_m3_distance_scales_with_geometry_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_018() { cc_m3_distance_scales_with_geometry_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_019() { cc_m3_distance_scales_with_geometry_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_020() { cc_m3_distance_scales_with_geometry_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_021() { cc_m3_distance_scales_with_geometry_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_022() { cc_m3_distance_scales_with_geometry_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_023() { cc_m3_distance_scales_with_geometry_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_024() { cc_m3_distance_scales_with_geometry_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_025() { cc_m3_distance_scales_with_geometry_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_026() { cc_m3_distance_scales_with_geometry_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_027() { cc_m3_distance_scales_with_geometry_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_028() { cc_m3_distance_scales_with_geometry_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_029() { cc_m3_distance_scales_with_geometry_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_030() { cc_m3_distance_scales_with_geometry_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_031() { cc_m3_distance_scales_with_geometry_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_032() { cc_m3_distance_scales_with_geometry_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_033() { cc_m3_distance_scales_with_geometry_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_034() { cc_m3_distance_scales_with_geometry_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_035() { cc_m3_distance_scales_with_geometry_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_036() { cc_m3_distance_scales_with_geometry_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_037() { cc_m3_distance_scales_with_geometry_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_038() { cc_m3_distance_scales_with_geometry_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_039() { cc_m3_distance_scales_with_geometry_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_040() { cc_m3_distance_scales_with_geometry_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_041() { cc_m3_distance_scales_with_geometry_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_042() { cc_m3_distance_scales_with_geometry_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_043() { cc_m3_distance_scales_with_geometry_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_044() { cc_m3_distance_scales_with_geometry_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_045() { cc_m3_distance_scales_with_geometry_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_046() { cc_m3_distance_scales_with_geometry_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_047() { cc_m3_distance_scales_with_geometry_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_048() { cc_m3_distance_scales_with_geometry_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_m3_distance_scales_with_geometry_seed_049() { cc_m3_distance_scales_with_geometry_impl(49); }
    // --- cc_p6_ptsd_is_non_negative: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_000() { cc_p6_ptsd_is_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_001() { cc_p6_ptsd_is_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_002() { cc_p6_ptsd_is_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_003() { cc_p6_ptsd_is_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_004() { cc_p6_ptsd_is_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_005() { cc_p6_ptsd_is_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_006() { cc_p6_ptsd_is_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_007() { cc_p6_ptsd_is_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_008() { cc_p6_ptsd_is_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_009() { cc_p6_ptsd_is_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_010() { cc_p6_ptsd_is_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_011() { cc_p6_ptsd_is_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_012() { cc_p6_ptsd_is_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_013() { cc_p6_ptsd_is_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_014() { cc_p6_ptsd_is_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_015() { cc_p6_ptsd_is_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_016() { cc_p6_ptsd_is_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_017() { cc_p6_ptsd_is_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_018() { cc_p6_ptsd_is_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_019() { cc_p6_ptsd_is_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_020() { cc_p6_ptsd_is_non_negative_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_021() { cc_p6_ptsd_is_non_negative_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_022() { cc_p6_ptsd_is_non_negative_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_023() { cc_p6_ptsd_is_non_negative_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_024() { cc_p6_ptsd_is_non_negative_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_025() { cc_p6_ptsd_is_non_negative_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_026() { cc_p6_ptsd_is_non_negative_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_027() { cc_p6_ptsd_is_non_negative_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_028() { cc_p6_ptsd_is_non_negative_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_029() { cc_p6_ptsd_is_non_negative_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_030() { cc_p6_ptsd_is_non_negative_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_031() { cc_p6_ptsd_is_non_negative_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_032() { cc_p6_ptsd_is_non_negative_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_033() { cc_p6_ptsd_is_non_negative_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_034() { cc_p6_ptsd_is_non_negative_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_035() { cc_p6_ptsd_is_non_negative_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_036() { cc_p6_ptsd_is_non_negative_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_037() { cc_p6_ptsd_is_non_negative_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_038() { cc_p6_ptsd_is_non_negative_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_039() { cc_p6_ptsd_is_non_negative_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_040() { cc_p6_ptsd_is_non_negative_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_041() { cc_p6_ptsd_is_non_negative_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_042() { cc_p6_ptsd_is_non_negative_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_043() { cc_p6_ptsd_is_non_negative_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_044() { cc_p6_ptsd_is_non_negative_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_045() { cc_p6_ptsd_is_non_negative_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_046() { cc_p6_ptsd_is_non_negative_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_047() { cc_p6_ptsd_is_non_negative_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_048() { cc_p6_ptsd_is_non_negative_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p6_ptsd_is_non_negative_seed_049() { cc_p6_ptsd_is_non_negative_impl(49); }
    // --- cc_p7_ptsd_zero_on_segment_interior: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_000() { cc_p7_ptsd_zero_on_segment_interior_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_001() { cc_p7_ptsd_zero_on_segment_interior_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_002() { cc_p7_ptsd_zero_on_segment_interior_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_003() { cc_p7_ptsd_zero_on_segment_interior_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_004() { cc_p7_ptsd_zero_on_segment_interior_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_005() { cc_p7_ptsd_zero_on_segment_interior_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_006() { cc_p7_ptsd_zero_on_segment_interior_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_007() { cc_p7_ptsd_zero_on_segment_interior_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_008() { cc_p7_ptsd_zero_on_segment_interior_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_009() { cc_p7_ptsd_zero_on_segment_interior_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_010() { cc_p7_ptsd_zero_on_segment_interior_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_011() { cc_p7_ptsd_zero_on_segment_interior_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_012() { cc_p7_ptsd_zero_on_segment_interior_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_013() { cc_p7_ptsd_zero_on_segment_interior_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_014() { cc_p7_ptsd_zero_on_segment_interior_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_015() { cc_p7_ptsd_zero_on_segment_interior_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_016() { cc_p7_ptsd_zero_on_segment_interior_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_017() { cc_p7_ptsd_zero_on_segment_interior_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_018() { cc_p7_ptsd_zero_on_segment_interior_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_019() { cc_p7_ptsd_zero_on_segment_interior_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_020() { cc_p7_ptsd_zero_on_segment_interior_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_021() { cc_p7_ptsd_zero_on_segment_interior_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_022() { cc_p7_ptsd_zero_on_segment_interior_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_023() { cc_p7_ptsd_zero_on_segment_interior_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_024() { cc_p7_ptsd_zero_on_segment_interior_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_025() { cc_p7_ptsd_zero_on_segment_interior_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_026() { cc_p7_ptsd_zero_on_segment_interior_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_027() { cc_p7_ptsd_zero_on_segment_interior_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_028() { cc_p7_ptsd_zero_on_segment_interior_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_029() { cc_p7_ptsd_zero_on_segment_interior_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_030() { cc_p7_ptsd_zero_on_segment_interior_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_031() { cc_p7_ptsd_zero_on_segment_interior_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_032() { cc_p7_ptsd_zero_on_segment_interior_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_033() { cc_p7_ptsd_zero_on_segment_interior_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_034() { cc_p7_ptsd_zero_on_segment_interior_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_035() { cc_p7_ptsd_zero_on_segment_interior_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_036() { cc_p7_ptsd_zero_on_segment_interior_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_037() { cc_p7_ptsd_zero_on_segment_interior_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_038() { cc_p7_ptsd_zero_on_segment_interior_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_039() { cc_p7_ptsd_zero_on_segment_interior_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_040() { cc_p7_ptsd_zero_on_segment_interior_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_041() { cc_p7_ptsd_zero_on_segment_interior_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_042() { cc_p7_ptsd_zero_on_segment_interior_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_043() { cc_p7_ptsd_zero_on_segment_interior_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_044() { cc_p7_ptsd_zero_on_segment_interior_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_045() { cc_p7_ptsd_zero_on_segment_interior_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_046() { cc_p7_ptsd_zero_on_segment_interior_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_047() { cc_p7_ptsd_zero_on_segment_interior_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_048() { cc_p7_ptsd_zero_on_segment_interior_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p7_ptsd_zero_on_segment_interior_seed_049() { cc_p7_ptsd_zero_on_segment_interior_impl(49); }
    // --- cc_p8_ptsd_degenerate_is_py_hypot: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_000() { cc_p8_ptsd_degenerate_is_py_hypot_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_001() { cc_p8_ptsd_degenerate_is_py_hypot_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_002() { cc_p8_ptsd_degenerate_is_py_hypot_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_003() { cc_p8_ptsd_degenerate_is_py_hypot_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_004() { cc_p8_ptsd_degenerate_is_py_hypot_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_005() { cc_p8_ptsd_degenerate_is_py_hypot_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_006() { cc_p8_ptsd_degenerate_is_py_hypot_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_007() { cc_p8_ptsd_degenerate_is_py_hypot_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_008() { cc_p8_ptsd_degenerate_is_py_hypot_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_009() { cc_p8_ptsd_degenerate_is_py_hypot_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_010() { cc_p8_ptsd_degenerate_is_py_hypot_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_011() { cc_p8_ptsd_degenerate_is_py_hypot_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_012() { cc_p8_ptsd_degenerate_is_py_hypot_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_013() { cc_p8_ptsd_degenerate_is_py_hypot_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_014() { cc_p8_ptsd_degenerate_is_py_hypot_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_015() { cc_p8_ptsd_degenerate_is_py_hypot_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_016() { cc_p8_ptsd_degenerate_is_py_hypot_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_017() { cc_p8_ptsd_degenerate_is_py_hypot_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_018() { cc_p8_ptsd_degenerate_is_py_hypot_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_019() { cc_p8_ptsd_degenerate_is_py_hypot_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_020() { cc_p8_ptsd_degenerate_is_py_hypot_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_021() { cc_p8_ptsd_degenerate_is_py_hypot_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_022() { cc_p8_ptsd_degenerate_is_py_hypot_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_023() { cc_p8_ptsd_degenerate_is_py_hypot_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_024() { cc_p8_ptsd_degenerate_is_py_hypot_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_025() { cc_p8_ptsd_degenerate_is_py_hypot_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_026() { cc_p8_ptsd_degenerate_is_py_hypot_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_027() { cc_p8_ptsd_degenerate_is_py_hypot_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_028() { cc_p8_ptsd_degenerate_is_py_hypot_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_029() { cc_p8_ptsd_degenerate_is_py_hypot_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_030() { cc_p8_ptsd_degenerate_is_py_hypot_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_031() { cc_p8_ptsd_degenerate_is_py_hypot_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_032() { cc_p8_ptsd_degenerate_is_py_hypot_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_033() { cc_p8_ptsd_degenerate_is_py_hypot_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_034() { cc_p8_ptsd_degenerate_is_py_hypot_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_035() { cc_p8_ptsd_degenerate_is_py_hypot_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_036() { cc_p8_ptsd_degenerate_is_py_hypot_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_037() { cc_p8_ptsd_degenerate_is_py_hypot_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_038() { cc_p8_ptsd_degenerate_is_py_hypot_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_039() { cc_p8_ptsd_degenerate_is_py_hypot_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_040() { cc_p8_ptsd_degenerate_is_py_hypot_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_041() { cc_p8_ptsd_degenerate_is_py_hypot_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_042() { cc_p8_ptsd_degenerate_is_py_hypot_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_043() { cc_p8_ptsd_degenerate_is_py_hypot_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_044() { cc_p8_ptsd_degenerate_is_py_hypot_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_045() { cc_p8_ptsd_degenerate_is_py_hypot_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_046() { cc_p8_ptsd_degenerate_is_py_hypot_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_047() { cc_p8_ptsd_degenerate_is_py_hypot_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_048() { cc_p8_ptsd_degenerate_is_py_hypot_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p8_ptsd_degenerate_is_py_hypot_seed_049() { cc_p8_ptsd_degenerate_is_py_hypot_impl(49); }
    // --- cc_p9_ptsd_bounded_by_endpoints: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_000() { cc_p9_ptsd_bounded_by_endpoints_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_001() { cc_p9_ptsd_bounded_by_endpoints_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_002() { cc_p9_ptsd_bounded_by_endpoints_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_003() { cc_p9_ptsd_bounded_by_endpoints_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_004() { cc_p9_ptsd_bounded_by_endpoints_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_005() { cc_p9_ptsd_bounded_by_endpoints_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_006() { cc_p9_ptsd_bounded_by_endpoints_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_007() { cc_p9_ptsd_bounded_by_endpoints_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_008() { cc_p9_ptsd_bounded_by_endpoints_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_009() { cc_p9_ptsd_bounded_by_endpoints_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_010() { cc_p9_ptsd_bounded_by_endpoints_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_011() { cc_p9_ptsd_bounded_by_endpoints_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_012() { cc_p9_ptsd_bounded_by_endpoints_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_013() { cc_p9_ptsd_bounded_by_endpoints_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_014() { cc_p9_ptsd_bounded_by_endpoints_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_015() { cc_p9_ptsd_bounded_by_endpoints_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_016() { cc_p9_ptsd_bounded_by_endpoints_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_017() { cc_p9_ptsd_bounded_by_endpoints_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_018() { cc_p9_ptsd_bounded_by_endpoints_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_019() { cc_p9_ptsd_bounded_by_endpoints_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_020() { cc_p9_ptsd_bounded_by_endpoints_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_021() { cc_p9_ptsd_bounded_by_endpoints_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_022() { cc_p9_ptsd_bounded_by_endpoints_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_023() { cc_p9_ptsd_bounded_by_endpoints_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_024() { cc_p9_ptsd_bounded_by_endpoints_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_025() { cc_p9_ptsd_bounded_by_endpoints_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_026() { cc_p9_ptsd_bounded_by_endpoints_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_027() { cc_p9_ptsd_bounded_by_endpoints_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_028() { cc_p9_ptsd_bounded_by_endpoints_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_029() { cc_p9_ptsd_bounded_by_endpoints_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_030() { cc_p9_ptsd_bounded_by_endpoints_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_031() { cc_p9_ptsd_bounded_by_endpoints_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_032() { cc_p9_ptsd_bounded_by_endpoints_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_033() { cc_p9_ptsd_bounded_by_endpoints_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_034() { cc_p9_ptsd_bounded_by_endpoints_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_035() { cc_p9_ptsd_bounded_by_endpoints_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_036() { cc_p9_ptsd_bounded_by_endpoints_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_037() { cc_p9_ptsd_bounded_by_endpoints_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_038() { cc_p9_ptsd_bounded_by_endpoints_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_039() { cc_p9_ptsd_bounded_by_endpoints_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_040() { cc_p9_ptsd_bounded_by_endpoints_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_041() { cc_p9_ptsd_bounded_by_endpoints_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_042() { cc_p9_ptsd_bounded_by_endpoints_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_043() { cc_p9_ptsd_bounded_by_endpoints_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_044() { cc_p9_ptsd_bounded_by_endpoints_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_045() { cc_p9_ptsd_bounded_by_endpoints_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_046() { cc_p9_ptsd_bounded_by_endpoints_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_047() { cc_p9_ptsd_bounded_by_endpoints_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_048() { cc_p9_ptsd_bounded_by_endpoints_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p9_ptsd_bounded_by_endpoints_seed_049() { cc_p9_ptsd_bounded_by_endpoints_impl(49); }
    // --- cc_p10_ptsd_segment_reversal_preserves_distance: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_000() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_001() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_002() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_003() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_004() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_005() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_006() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_007() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_008() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_009() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_010() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_011() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_012() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_013() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_014() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_015() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_016() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_017() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_018() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_019() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_020() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_021() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_022() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_023() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_024() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_025() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_026() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_027() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_028() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_029() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_030() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_031() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_032() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_033() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_034() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_035() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_036() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_037() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_038() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_039() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_040() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_041() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_042() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_043() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_044() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_045() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_046() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_047() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_048() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p10_ptsd_segment_reversal_preserves_distance_seed_049() { cc_p10_ptsd_segment_reversal_preserves_distance_impl(49); }
    // --- cc_p11_ptsd_translation_invariant: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_000() { cc_p11_ptsd_translation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_001() { cc_p11_ptsd_translation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_002() { cc_p11_ptsd_translation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_003() { cc_p11_ptsd_translation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_004() { cc_p11_ptsd_translation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_005() { cc_p11_ptsd_translation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_006() { cc_p11_ptsd_translation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_007() { cc_p11_ptsd_translation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_008() { cc_p11_ptsd_translation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_009() { cc_p11_ptsd_translation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_010() { cc_p11_ptsd_translation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_011() { cc_p11_ptsd_translation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_012() { cc_p11_ptsd_translation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_013() { cc_p11_ptsd_translation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_014() { cc_p11_ptsd_translation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_015() { cc_p11_ptsd_translation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_016() { cc_p11_ptsd_translation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_017() { cc_p11_ptsd_translation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_018() { cc_p11_ptsd_translation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_019() { cc_p11_ptsd_translation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_020() { cc_p11_ptsd_translation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_021() { cc_p11_ptsd_translation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_022() { cc_p11_ptsd_translation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_023() { cc_p11_ptsd_translation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_024() { cc_p11_ptsd_translation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_025() { cc_p11_ptsd_translation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_026() { cc_p11_ptsd_translation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_027() { cc_p11_ptsd_translation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_028() { cc_p11_ptsd_translation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_029() { cc_p11_ptsd_translation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_030() { cc_p11_ptsd_translation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_031() { cc_p11_ptsd_translation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_032() { cc_p11_ptsd_translation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_033() { cc_p11_ptsd_translation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_034() { cc_p11_ptsd_translation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_035() { cc_p11_ptsd_translation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_036() { cc_p11_ptsd_translation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_037() { cc_p11_ptsd_translation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_038() { cc_p11_ptsd_translation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_039() { cc_p11_ptsd_translation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_040() { cc_p11_ptsd_translation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_041() { cc_p11_ptsd_translation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_042() { cc_p11_ptsd_translation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_043() { cc_p11_ptsd_translation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_044() { cc_p11_ptsd_translation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_045() { cc_p11_ptsd_translation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_046() { cc_p11_ptsd_translation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_047() { cc_p11_ptsd_translation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_048() { cc_p11_ptsd_translation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p11_ptsd_translation_invariant_seed_049() { cc_p11_ptsd_translation_invariant_impl(49); }
    // --- cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance: 50 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_000() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_001() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_002() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_003() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_004() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_005() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_006() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_007() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_008() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_009() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_010() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_011() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_012() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_013() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_014() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_015() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_016() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_017() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_018() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_019() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_020() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_021() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_022() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_023() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_024() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_025() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_026() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_027() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_028() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_029() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_030() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_031() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_032() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_033() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_034() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_035() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_036() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_037() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_038() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_039() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_040() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_041() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_042() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_043() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_044() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_045() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_046() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_047() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_048() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_049() { cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_impl(49); }
    // --- END generated seeded property-mirror wrappers ---

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
        ("creepage_check::tests::cc_seg_pair_coverage_guard_hits_close_and_crossing_cases", cc_seg_pair_coverage_guard_hits_close_and_crossing_cases),
        ("creepage_check::tests::cc_point_seg_close_coverage_guard", cc_point_seg_close_coverage_guard),
        ("creepage_check::tests::cc_p5_coverage_guard_straddles_a_bracket", cc_p5_coverage_guard_straddles_a_bracket),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_000", cc_p1_distance_is_non_negative_seed_000),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_001", cc_p1_distance_is_non_negative_seed_001),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_002", cc_p1_distance_is_non_negative_seed_002),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_003", cc_p1_distance_is_non_negative_seed_003),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_004", cc_p1_distance_is_non_negative_seed_004),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_005", cc_p1_distance_is_non_negative_seed_005),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_006", cc_p1_distance_is_non_negative_seed_006),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_007", cc_p1_distance_is_non_negative_seed_007),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_008", cc_p1_distance_is_non_negative_seed_008),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_009", cc_p1_distance_is_non_negative_seed_009),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_010", cc_p1_distance_is_non_negative_seed_010),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_011", cc_p1_distance_is_non_negative_seed_011),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_012", cc_p1_distance_is_non_negative_seed_012),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_013", cc_p1_distance_is_non_negative_seed_013),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_014", cc_p1_distance_is_non_negative_seed_014),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_015", cc_p1_distance_is_non_negative_seed_015),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_016", cc_p1_distance_is_non_negative_seed_016),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_017", cc_p1_distance_is_non_negative_seed_017),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_018", cc_p1_distance_is_non_negative_seed_018),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_019", cc_p1_distance_is_non_negative_seed_019),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_020", cc_p1_distance_is_non_negative_seed_020),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_021", cc_p1_distance_is_non_negative_seed_021),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_022", cc_p1_distance_is_non_negative_seed_022),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_023", cc_p1_distance_is_non_negative_seed_023),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_024", cc_p1_distance_is_non_negative_seed_024),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_025", cc_p1_distance_is_non_negative_seed_025),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_026", cc_p1_distance_is_non_negative_seed_026),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_027", cc_p1_distance_is_non_negative_seed_027),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_028", cc_p1_distance_is_non_negative_seed_028),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_029", cc_p1_distance_is_non_negative_seed_029),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_030", cc_p1_distance_is_non_negative_seed_030),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_031", cc_p1_distance_is_non_negative_seed_031),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_032", cc_p1_distance_is_non_negative_seed_032),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_033", cc_p1_distance_is_non_negative_seed_033),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_034", cc_p1_distance_is_non_negative_seed_034),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_035", cc_p1_distance_is_non_negative_seed_035),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_036", cc_p1_distance_is_non_negative_seed_036),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_037", cc_p1_distance_is_non_negative_seed_037),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_038", cc_p1_distance_is_non_negative_seed_038),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_039", cc_p1_distance_is_non_negative_seed_039),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_040", cc_p1_distance_is_non_negative_seed_040),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_041", cc_p1_distance_is_non_negative_seed_041),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_042", cc_p1_distance_is_non_negative_seed_042),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_043", cc_p1_distance_is_non_negative_seed_043),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_044", cc_p1_distance_is_non_negative_seed_044),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_045", cc_p1_distance_is_non_negative_seed_045),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_046", cc_p1_distance_is_non_negative_seed_046),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_047", cc_p1_distance_is_non_negative_seed_047),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_048", cc_p1_distance_is_non_negative_seed_048),
        ("creepage_check::tests::cc_p1_distance_is_non_negative_seed_049", cc_p1_distance_is_non_negative_seed_049),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_000", cc_p2_swapping_segments_is_bit_exact_seed_000),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_001", cc_p2_swapping_segments_is_bit_exact_seed_001),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_002", cc_p2_swapping_segments_is_bit_exact_seed_002),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_003", cc_p2_swapping_segments_is_bit_exact_seed_003),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_004", cc_p2_swapping_segments_is_bit_exact_seed_004),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_005", cc_p2_swapping_segments_is_bit_exact_seed_005),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_006", cc_p2_swapping_segments_is_bit_exact_seed_006),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_007", cc_p2_swapping_segments_is_bit_exact_seed_007),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_008", cc_p2_swapping_segments_is_bit_exact_seed_008),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_009", cc_p2_swapping_segments_is_bit_exact_seed_009),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_010", cc_p2_swapping_segments_is_bit_exact_seed_010),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_011", cc_p2_swapping_segments_is_bit_exact_seed_011),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_012", cc_p2_swapping_segments_is_bit_exact_seed_012),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_013", cc_p2_swapping_segments_is_bit_exact_seed_013),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_014", cc_p2_swapping_segments_is_bit_exact_seed_014),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_015", cc_p2_swapping_segments_is_bit_exact_seed_015),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_016", cc_p2_swapping_segments_is_bit_exact_seed_016),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_017", cc_p2_swapping_segments_is_bit_exact_seed_017),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_018", cc_p2_swapping_segments_is_bit_exact_seed_018),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_019", cc_p2_swapping_segments_is_bit_exact_seed_019),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_020", cc_p2_swapping_segments_is_bit_exact_seed_020),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_021", cc_p2_swapping_segments_is_bit_exact_seed_021),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_022", cc_p2_swapping_segments_is_bit_exact_seed_022),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_023", cc_p2_swapping_segments_is_bit_exact_seed_023),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_024", cc_p2_swapping_segments_is_bit_exact_seed_024),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_025", cc_p2_swapping_segments_is_bit_exact_seed_025),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_026", cc_p2_swapping_segments_is_bit_exact_seed_026),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_027", cc_p2_swapping_segments_is_bit_exact_seed_027),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_028", cc_p2_swapping_segments_is_bit_exact_seed_028),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_029", cc_p2_swapping_segments_is_bit_exact_seed_029),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_030", cc_p2_swapping_segments_is_bit_exact_seed_030),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_031", cc_p2_swapping_segments_is_bit_exact_seed_031),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_032", cc_p2_swapping_segments_is_bit_exact_seed_032),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_033", cc_p2_swapping_segments_is_bit_exact_seed_033),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_034", cc_p2_swapping_segments_is_bit_exact_seed_034),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_035", cc_p2_swapping_segments_is_bit_exact_seed_035),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_036", cc_p2_swapping_segments_is_bit_exact_seed_036),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_037", cc_p2_swapping_segments_is_bit_exact_seed_037),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_038", cc_p2_swapping_segments_is_bit_exact_seed_038),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_039", cc_p2_swapping_segments_is_bit_exact_seed_039),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_040", cc_p2_swapping_segments_is_bit_exact_seed_040),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_041", cc_p2_swapping_segments_is_bit_exact_seed_041),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_042", cc_p2_swapping_segments_is_bit_exact_seed_042),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_043", cc_p2_swapping_segments_is_bit_exact_seed_043),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_044", cc_p2_swapping_segments_is_bit_exact_seed_044),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_045", cc_p2_swapping_segments_is_bit_exact_seed_045),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_046", cc_p2_swapping_segments_is_bit_exact_seed_046),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_047", cc_p2_swapping_segments_is_bit_exact_seed_047),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_048", cc_p2_swapping_segments_is_bit_exact_seed_048),
        ("creepage_check::tests::cc_p2_swapping_segments_is_bit_exact_seed_049", cc_p2_swapping_segments_is_bit_exact_seed_049),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_000", cc_p3_distance_is_monotonic_moving_away_seed_000),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_001", cc_p3_distance_is_monotonic_moving_away_seed_001),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_002", cc_p3_distance_is_monotonic_moving_away_seed_002),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_003", cc_p3_distance_is_monotonic_moving_away_seed_003),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_004", cc_p3_distance_is_monotonic_moving_away_seed_004),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_005", cc_p3_distance_is_monotonic_moving_away_seed_005),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_006", cc_p3_distance_is_monotonic_moving_away_seed_006),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_007", cc_p3_distance_is_monotonic_moving_away_seed_007),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_008", cc_p3_distance_is_monotonic_moving_away_seed_008),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_009", cc_p3_distance_is_monotonic_moving_away_seed_009),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_010", cc_p3_distance_is_monotonic_moving_away_seed_010),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_011", cc_p3_distance_is_monotonic_moving_away_seed_011),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_012", cc_p3_distance_is_monotonic_moving_away_seed_012),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_013", cc_p3_distance_is_monotonic_moving_away_seed_013),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_014", cc_p3_distance_is_monotonic_moving_away_seed_014),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_015", cc_p3_distance_is_monotonic_moving_away_seed_015),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_016", cc_p3_distance_is_monotonic_moving_away_seed_016),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_017", cc_p3_distance_is_monotonic_moving_away_seed_017),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_018", cc_p3_distance_is_monotonic_moving_away_seed_018),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_019", cc_p3_distance_is_monotonic_moving_away_seed_019),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_020", cc_p3_distance_is_monotonic_moving_away_seed_020),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_021", cc_p3_distance_is_monotonic_moving_away_seed_021),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_022", cc_p3_distance_is_monotonic_moving_away_seed_022),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_023", cc_p3_distance_is_monotonic_moving_away_seed_023),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_024", cc_p3_distance_is_monotonic_moving_away_seed_024),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_025", cc_p3_distance_is_monotonic_moving_away_seed_025),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_026", cc_p3_distance_is_monotonic_moving_away_seed_026),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_027", cc_p3_distance_is_monotonic_moving_away_seed_027),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_028", cc_p3_distance_is_monotonic_moving_away_seed_028),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_029", cc_p3_distance_is_monotonic_moving_away_seed_029),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_030", cc_p3_distance_is_monotonic_moving_away_seed_030),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_031", cc_p3_distance_is_monotonic_moving_away_seed_031),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_032", cc_p3_distance_is_monotonic_moving_away_seed_032),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_033", cc_p3_distance_is_monotonic_moving_away_seed_033),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_034", cc_p3_distance_is_monotonic_moving_away_seed_034),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_035", cc_p3_distance_is_monotonic_moving_away_seed_035),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_036", cc_p3_distance_is_monotonic_moving_away_seed_036),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_037", cc_p3_distance_is_monotonic_moving_away_seed_037),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_038", cc_p3_distance_is_monotonic_moving_away_seed_038),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_039", cc_p3_distance_is_monotonic_moving_away_seed_039),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_040", cc_p3_distance_is_monotonic_moving_away_seed_040),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_041", cc_p3_distance_is_monotonic_moving_away_seed_041),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_042", cc_p3_distance_is_monotonic_moving_away_seed_042),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_043", cc_p3_distance_is_monotonic_moving_away_seed_043),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_044", cc_p3_distance_is_monotonic_moving_away_seed_044),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_045", cc_p3_distance_is_monotonic_moving_away_seed_045),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_046", cc_p3_distance_is_monotonic_moving_away_seed_046),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_047", cc_p3_distance_is_monotonic_moving_away_seed_047),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_048", cc_p3_distance_is_monotonic_moving_away_seed_048),
        ("creepage_check::tests::cc_p3_distance_is_monotonic_moving_away_seed_049", cc_p3_distance_is_monotonic_moving_away_seed_049),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_000", cc_p4_distance_is_bounded_by_midpoints_seed_000),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_001", cc_p4_distance_is_bounded_by_midpoints_seed_001),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_002", cc_p4_distance_is_bounded_by_midpoints_seed_002),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_003", cc_p4_distance_is_bounded_by_midpoints_seed_003),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_004", cc_p4_distance_is_bounded_by_midpoints_seed_004),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_005", cc_p4_distance_is_bounded_by_midpoints_seed_005),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_006", cc_p4_distance_is_bounded_by_midpoints_seed_006),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_007", cc_p4_distance_is_bounded_by_midpoints_seed_007),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_008", cc_p4_distance_is_bounded_by_midpoints_seed_008),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_009", cc_p4_distance_is_bounded_by_midpoints_seed_009),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_010", cc_p4_distance_is_bounded_by_midpoints_seed_010),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_011", cc_p4_distance_is_bounded_by_midpoints_seed_011),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_012", cc_p4_distance_is_bounded_by_midpoints_seed_012),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_013", cc_p4_distance_is_bounded_by_midpoints_seed_013),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_014", cc_p4_distance_is_bounded_by_midpoints_seed_014),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_015", cc_p4_distance_is_bounded_by_midpoints_seed_015),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_016", cc_p4_distance_is_bounded_by_midpoints_seed_016),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_017", cc_p4_distance_is_bounded_by_midpoints_seed_017),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_018", cc_p4_distance_is_bounded_by_midpoints_seed_018),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_019", cc_p4_distance_is_bounded_by_midpoints_seed_019),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_020", cc_p4_distance_is_bounded_by_midpoints_seed_020),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_021", cc_p4_distance_is_bounded_by_midpoints_seed_021),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_022", cc_p4_distance_is_bounded_by_midpoints_seed_022),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_023", cc_p4_distance_is_bounded_by_midpoints_seed_023),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_024", cc_p4_distance_is_bounded_by_midpoints_seed_024),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_025", cc_p4_distance_is_bounded_by_midpoints_seed_025),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_026", cc_p4_distance_is_bounded_by_midpoints_seed_026),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_027", cc_p4_distance_is_bounded_by_midpoints_seed_027),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_028", cc_p4_distance_is_bounded_by_midpoints_seed_028),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_029", cc_p4_distance_is_bounded_by_midpoints_seed_029),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_030", cc_p4_distance_is_bounded_by_midpoints_seed_030),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_031", cc_p4_distance_is_bounded_by_midpoints_seed_031),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_032", cc_p4_distance_is_bounded_by_midpoints_seed_032),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_033", cc_p4_distance_is_bounded_by_midpoints_seed_033),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_034", cc_p4_distance_is_bounded_by_midpoints_seed_034),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_035", cc_p4_distance_is_bounded_by_midpoints_seed_035),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_036", cc_p4_distance_is_bounded_by_midpoints_seed_036),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_037", cc_p4_distance_is_bounded_by_midpoints_seed_037),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_038", cc_p4_distance_is_bounded_by_midpoints_seed_038),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_039", cc_p4_distance_is_bounded_by_midpoints_seed_039),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_040", cc_p4_distance_is_bounded_by_midpoints_seed_040),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_041", cc_p4_distance_is_bounded_by_midpoints_seed_041),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_042", cc_p4_distance_is_bounded_by_midpoints_seed_042),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_043", cc_p4_distance_is_bounded_by_midpoints_seed_043),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_044", cc_p4_distance_is_bounded_by_midpoints_seed_044),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_045", cc_p4_distance_is_bounded_by_midpoints_seed_045),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_046", cc_p4_distance_is_bounded_by_midpoints_seed_046),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_047", cc_p4_distance_is_bounded_by_midpoints_seed_047),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_048", cc_p4_distance_is_bounded_by_midpoints_seed_048),
        ("creepage_check::tests::cc_p4_distance_is_bounded_by_midpoints_seed_049", cc_p4_distance_is_bounded_by_midpoints_seed_049),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_000", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_000),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_001", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_001),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_002", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_002),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_003", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_003),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_004", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_004),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_005", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_005),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_006", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_006),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_007", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_007),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_008", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_008),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_009", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_009),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_010", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_010),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_011", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_011),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_012", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_012),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_013", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_013),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_014", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_014),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_015", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_015),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_016", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_016),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_017", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_017),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_018", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_018),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_019", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_019),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_020", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_020),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_021", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_021),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_022", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_022),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_023", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_023),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_024", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_024),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_025", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_025),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_026", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_026),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_027", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_027),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_028", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_028),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_029", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_029),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_030", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_030),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_031", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_031),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_032", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_032),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_033", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_033),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_034", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_034),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_035", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_035),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_036", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_036),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_037", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_037),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_038", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_038),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_039", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_039),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_040", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_040),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_041", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_041),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_042", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_042),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_043", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_043),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_044", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_044),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_045", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_045),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_046", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_046),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_047", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_047),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_048", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_048),
        ("creepage_check::tests::cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_049", cc_p5_creepage_bracket_is_monotonic_in_voltage_seed_049),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_000", cc_m1_distance_invariant_under_translation_seed_000),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_001", cc_m1_distance_invariant_under_translation_seed_001),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_002", cc_m1_distance_invariant_under_translation_seed_002),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_003", cc_m1_distance_invariant_under_translation_seed_003),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_004", cc_m1_distance_invariant_under_translation_seed_004),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_005", cc_m1_distance_invariant_under_translation_seed_005),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_006", cc_m1_distance_invariant_under_translation_seed_006),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_007", cc_m1_distance_invariant_under_translation_seed_007),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_008", cc_m1_distance_invariant_under_translation_seed_008),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_009", cc_m1_distance_invariant_under_translation_seed_009),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_010", cc_m1_distance_invariant_under_translation_seed_010),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_011", cc_m1_distance_invariant_under_translation_seed_011),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_012", cc_m1_distance_invariant_under_translation_seed_012),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_013", cc_m1_distance_invariant_under_translation_seed_013),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_014", cc_m1_distance_invariant_under_translation_seed_014),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_015", cc_m1_distance_invariant_under_translation_seed_015),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_016", cc_m1_distance_invariant_under_translation_seed_016),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_017", cc_m1_distance_invariant_under_translation_seed_017),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_018", cc_m1_distance_invariant_under_translation_seed_018),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_019", cc_m1_distance_invariant_under_translation_seed_019),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_020", cc_m1_distance_invariant_under_translation_seed_020),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_021", cc_m1_distance_invariant_under_translation_seed_021),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_022", cc_m1_distance_invariant_under_translation_seed_022),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_023", cc_m1_distance_invariant_under_translation_seed_023),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_024", cc_m1_distance_invariant_under_translation_seed_024),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_025", cc_m1_distance_invariant_under_translation_seed_025),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_026", cc_m1_distance_invariant_under_translation_seed_026),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_027", cc_m1_distance_invariant_under_translation_seed_027),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_028", cc_m1_distance_invariant_under_translation_seed_028),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_029", cc_m1_distance_invariant_under_translation_seed_029),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_030", cc_m1_distance_invariant_under_translation_seed_030),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_031", cc_m1_distance_invariant_under_translation_seed_031),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_032", cc_m1_distance_invariant_under_translation_seed_032),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_033", cc_m1_distance_invariant_under_translation_seed_033),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_034", cc_m1_distance_invariant_under_translation_seed_034),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_035", cc_m1_distance_invariant_under_translation_seed_035),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_036", cc_m1_distance_invariant_under_translation_seed_036),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_037", cc_m1_distance_invariant_under_translation_seed_037),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_038", cc_m1_distance_invariant_under_translation_seed_038),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_039", cc_m1_distance_invariant_under_translation_seed_039),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_040", cc_m1_distance_invariant_under_translation_seed_040),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_041", cc_m1_distance_invariant_under_translation_seed_041),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_042", cc_m1_distance_invariant_under_translation_seed_042),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_043", cc_m1_distance_invariant_under_translation_seed_043),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_044", cc_m1_distance_invariant_under_translation_seed_044),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_045", cc_m1_distance_invariant_under_translation_seed_045),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_046", cc_m1_distance_invariant_under_translation_seed_046),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_047", cc_m1_distance_invariant_under_translation_seed_047),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_048", cc_m1_distance_invariant_under_translation_seed_048),
        ("creepage_check::tests::cc_m1_distance_invariant_under_translation_seed_049", cc_m1_distance_invariant_under_translation_seed_049),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_000", cc_m2_distance_invariant_under_rotation_seed_000),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_001", cc_m2_distance_invariant_under_rotation_seed_001),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_002", cc_m2_distance_invariant_under_rotation_seed_002),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_003", cc_m2_distance_invariant_under_rotation_seed_003),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_004", cc_m2_distance_invariant_under_rotation_seed_004),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_005", cc_m2_distance_invariant_under_rotation_seed_005),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_006", cc_m2_distance_invariant_under_rotation_seed_006),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_007", cc_m2_distance_invariant_under_rotation_seed_007),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_008", cc_m2_distance_invariant_under_rotation_seed_008),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_009", cc_m2_distance_invariant_under_rotation_seed_009),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_010", cc_m2_distance_invariant_under_rotation_seed_010),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_011", cc_m2_distance_invariant_under_rotation_seed_011),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_012", cc_m2_distance_invariant_under_rotation_seed_012),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_013", cc_m2_distance_invariant_under_rotation_seed_013),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_014", cc_m2_distance_invariant_under_rotation_seed_014),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_015", cc_m2_distance_invariant_under_rotation_seed_015),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_016", cc_m2_distance_invariant_under_rotation_seed_016),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_017", cc_m2_distance_invariant_under_rotation_seed_017),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_018", cc_m2_distance_invariant_under_rotation_seed_018),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_019", cc_m2_distance_invariant_under_rotation_seed_019),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_020", cc_m2_distance_invariant_under_rotation_seed_020),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_021", cc_m2_distance_invariant_under_rotation_seed_021),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_022", cc_m2_distance_invariant_under_rotation_seed_022),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_023", cc_m2_distance_invariant_under_rotation_seed_023),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_024", cc_m2_distance_invariant_under_rotation_seed_024),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_025", cc_m2_distance_invariant_under_rotation_seed_025),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_026", cc_m2_distance_invariant_under_rotation_seed_026),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_027", cc_m2_distance_invariant_under_rotation_seed_027),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_028", cc_m2_distance_invariant_under_rotation_seed_028),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_029", cc_m2_distance_invariant_under_rotation_seed_029),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_030", cc_m2_distance_invariant_under_rotation_seed_030),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_031", cc_m2_distance_invariant_under_rotation_seed_031),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_032", cc_m2_distance_invariant_under_rotation_seed_032),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_033", cc_m2_distance_invariant_under_rotation_seed_033),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_034", cc_m2_distance_invariant_under_rotation_seed_034),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_035", cc_m2_distance_invariant_under_rotation_seed_035),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_036", cc_m2_distance_invariant_under_rotation_seed_036),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_037", cc_m2_distance_invariant_under_rotation_seed_037),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_038", cc_m2_distance_invariant_under_rotation_seed_038),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_039", cc_m2_distance_invariant_under_rotation_seed_039),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_040", cc_m2_distance_invariant_under_rotation_seed_040),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_041", cc_m2_distance_invariant_under_rotation_seed_041),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_042", cc_m2_distance_invariant_under_rotation_seed_042),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_043", cc_m2_distance_invariant_under_rotation_seed_043),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_044", cc_m2_distance_invariant_under_rotation_seed_044),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_045", cc_m2_distance_invariant_under_rotation_seed_045),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_046", cc_m2_distance_invariant_under_rotation_seed_046),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_047", cc_m2_distance_invariant_under_rotation_seed_047),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_048", cc_m2_distance_invariant_under_rotation_seed_048),
        ("creepage_check::tests::cc_m2_distance_invariant_under_rotation_seed_049", cc_m2_distance_invariant_under_rotation_seed_049),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_000", cc_m3_distance_scales_with_geometry_seed_000),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_001", cc_m3_distance_scales_with_geometry_seed_001),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_002", cc_m3_distance_scales_with_geometry_seed_002),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_003", cc_m3_distance_scales_with_geometry_seed_003),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_004", cc_m3_distance_scales_with_geometry_seed_004),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_005", cc_m3_distance_scales_with_geometry_seed_005),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_006", cc_m3_distance_scales_with_geometry_seed_006),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_007", cc_m3_distance_scales_with_geometry_seed_007),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_008", cc_m3_distance_scales_with_geometry_seed_008),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_009", cc_m3_distance_scales_with_geometry_seed_009),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_010", cc_m3_distance_scales_with_geometry_seed_010),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_011", cc_m3_distance_scales_with_geometry_seed_011),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_012", cc_m3_distance_scales_with_geometry_seed_012),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_013", cc_m3_distance_scales_with_geometry_seed_013),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_014", cc_m3_distance_scales_with_geometry_seed_014),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_015", cc_m3_distance_scales_with_geometry_seed_015),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_016", cc_m3_distance_scales_with_geometry_seed_016),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_017", cc_m3_distance_scales_with_geometry_seed_017),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_018", cc_m3_distance_scales_with_geometry_seed_018),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_019", cc_m3_distance_scales_with_geometry_seed_019),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_020", cc_m3_distance_scales_with_geometry_seed_020),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_021", cc_m3_distance_scales_with_geometry_seed_021),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_022", cc_m3_distance_scales_with_geometry_seed_022),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_023", cc_m3_distance_scales_with_geometry_seed_023),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_024", cc_m3_distance_scales_with_geometry_seed_024),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_025", cc_m3_distance_scales_with_geometry_seed_025),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_026", cc_m3_distance_scales_with_geometry_seed_026),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_027", cc_m3_distance_scales_with_geometry_seed_027),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_028", cc_m3_distance_scales_with_geometry_seed_028),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_029", cc_m3_distance_scales_with_geometry_seed_029),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_030", cc_m3_distance_scales_with_geometry_seed_030),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_031", cc_m3_distance_scales_with_geometry_seed_031),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_032", cc_m3_distance_scales_with_geometry_seed_032),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_033", cc_m3_distance_scales_with_geometry_seed_033),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_034", cc_m3_distance_scales_with_geometry_seed_034),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_035", cc_m3_distance_scales_with_geometry_seed_035),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_036", cc_m3_distance_scales_with_geometry_seed_036),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_037", cc_m3_distance_scales_with_geometry_seed_037),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_038", cc_m3_distance_scales_with_geometry_seed_038),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_039", cc_m3_distance_scales_with_geometry_seed_039),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_040", cc_m3_distance_scales_with_geometry_seed_040),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_041", cc_m3_distance_scales_with_geometry_seed_041),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_042", cc_m3_distance_scales_with_geometry_seed_042),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_043", cc_m3_distance_scales_with_geometry_seed_043),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_044", cc_m3_distance_scales_with_geometry_seed_044),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_045", cc_m3_distance_scales_with_geometry_seed_045),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_046", cc_m3_distance_scales_with_geometry_seed_046),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_047", cc_m3_distance_scales_with_geometry_seed_047),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_048", cc_m3_distance_scales_with_geometry_seed_048),
        ("creepage_check::tests::cc_m3_distance_scales_with_geometry_seed_049", cc_m3_distance_scales_with_geometry_seed_049),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_000", cc_p6_ptsd_is_non_negative_seed_000),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_001", cc_p6_ptsd_is_non_negative_seed_001),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_002", cc_p6_ptsd_is_non_negative_seed_002),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_003", cc_p6_ptsd_is_non_negative_seed_003),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_004", cc_p6_ptsd_is_non_negative_seed_004),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_005", cc_p6_ptsd_is_non_negative_seed_005),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_006", cc_p6_ptsd_is_non_negative_seed_006),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_007", cc_p6_ptsd_is_non_negative_seed_007),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_008", cc_p6_ptsd_is_non_negative_seed_008),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_009", cc_p6_ptsd_is_non_negative_seed_009),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_010", cc_p6_ptsd_is_non_negative_seed_010),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_011", cc_p6_ptsd_is_non_negative_seed_011),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_012", cc_p6_ptsd_is_non_negative_seed_012),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_013", cc_p6_ptsd_is_non_negative_seed_013),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_014", cc_p6_ptsd_is_non_negative_seed_014),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_015", cc_p6_ptsd_is_non_negative_seed_015),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_016", cc_p6_ptsd_is_non_negative_seed_016),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_017", cc_p6_ptsd_is_non_negative_seed_017),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_018", cc_p6_ptsd_is_non_negative_seed_018),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_019", cc_p6_ptsd_is_non_negative_seed_019),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_020", cc_p6_ptsd_is_non_negative_seed_020),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_021", cc_p6_ptsd_is_non_negative_seed_021),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_022", cc_p6_ptsd_is_non_negative_seed_022),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_023", cc_p6_ptsd_is_non_negative_seed_023),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_024", cc_p6_ptsd_is_non_negative_seed_024),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_025", cc_p6_ptsd_is_non_negative_seed_025),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_026", cc_p6_ptsd_is_non_negative_seed_026),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_027", cc_p6_ptsd_is_non_negative_seed_027),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_028", cc_p6_ptsd_is_non_negative_seed_028),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_029", cc_p6_ptsd_is_non_negative_seed_029),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_030", cc_p6_ptsd_is_non_negative_seed_030),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_031", cc_p6_ptsd_is_non_negative_seed_031),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_032", cc_p6_ptsd_is_non_negative_seed_032),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_033", cc_p6_ptsd_is_non_negative_seed_033),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_034", cc_p6_ptsd_is_non_negative_seed_034),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_035", cc_p6_ptsd_is_non_negative_seed_035),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_036", cc_p6_ptsd_is_non_negative_seed_036),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_037", cc_p6_ptsd_is_non_negative_seed_037),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_038", cc_p6_ptsd_is_non_negative_seed_038),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_039", cc_p6_ptsd_is_non_negative_seed_039),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_040", cc_p6_ptsd_is_non_negative_seed_040),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_041", cc_p6_ptsd_is_non_negative_seed_041),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_042", cc_p6_ptsd_is_non_negative_seed_042),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_043", cc_p6_ptsd_is_non_negative_seed_043),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_044", cc_p6_ptsd_is_non_negative_seed_044),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_045", cc_p6_ptsd_is_non_negative_seed_045),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_046", cc_p6_ptsd_is_non_negative_seed_046),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_047", cc_p6_ptsd_is_non_negative_seed_047),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_048", cc_p6_ptsd_is_non_negative_seed_048),
        ("creepage_check::tests::cc_p6_ptsd_is_non_negative_seed_049", cc_p6_ptsd_is_non_negative_seed_049),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_000", cc_p7_ptsd_zero_on_segment_interior_seed_000),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_001", cc_p7_ptsd_zero_on_segment_interior_seed_001),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_002", cc_p7_ptsd_zero_on_segment_interior_seed_002),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_003", cc_p7_ptsd_zero_on_segment_interior_seed_003),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_004", cc_p7_ptsd_zero_on_segment_interior_seed_004),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_005", cc_p7_ptsd_zero_on_segment_interior_seed_005),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_006", cc_p7_ptsd_zero_on_segment_interior_seed_006),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_007", cc_p7_ptsd_zero_on_segment_interior_seed_007),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_008", cc_p7_ptsd_zero_on_segment_interior_seed_008),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_009", cc_p7_ptsd_zero_on_segment_interior_seed_009),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_010", cc_p7_ptsd_zero_on_segment_interior_seed_010),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_011", cc_p7_ptsd_zero_on_segment_interior_seed_011),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_012", cc_p7_ptsd_zero_on_segment_interior_seed_012),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_013", cc_p7_ptsd_zero_on_segment_interior_seed_013),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_014", cc_p7_ptsd_zero_on_segment_interior_seed_014),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_015", cc_p7_ptsd_zero_on_segment_interior_seed_015),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_016", cc_p7_ptsd_zero_on_segment_interior_seed_016),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_017", cc_p7_ptsd_zero_on_segment_interior_seed_017),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_018", cc_p7_ptsd_zero_on_segment_interior_seed_018),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_019", cc_p7_ptsd_zero_on_segment_interior_seed_019),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_020", cc_p7_ptsd_zero_on_segment_interior_seed_020),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_021", cc_p7_ptsd_zero_on_segment_interior_seed_021),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_022", cc_p7_ptsd_zero_on_segment_interior_seed_022),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_023", cc_p7_ptsd_zero_on_segment_interior_seed_023),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_024", cc_p7_ptsd_zero_on_segment_interior_seed_024),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_025", cc_p7_ptsd_zero_on_segment_interior_seed_025),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_026", cc_p7_ptsd_zero_on_segment_interior_seed_026),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_027", cc_p7_ptsd_zero_on_segment_interior_seed_027),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_028", cc_p7_ptsd_zero_on_segment_interior_seed_028),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_029", cc_p7_ptsd_zero_on_segment_interior_seed_029),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_030", cc_p7_ptsd_zero_on_segment_interior_seed_030),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_031", cc_p7_ptsd_zero_on_segment_interior_seed_031),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_032", cc_p7_ptsd_zero_on_segment_interior_seed_032),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_033", cc_p7_ptsd_zero_on_segment_interior_seed_033),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_034", cc_p7_ptsd_zero_on_segment_interior_seed_034),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_035", cc_p7_ptsd_zero_on_segment_interior_seed_035),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_036", cc_p7_ptsd_zero_on_segment_interior_seed_036),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_037", cc_p7_ptsd_zero_on_segment_interior_seed_037),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_038", cc_p7_ptsd_zero_on_segment_interior_seed_038),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_039", cc_p7_ptsd_zero_on_segment_interior_seed_039),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_040", cc_p7_ptsd_zero_on_segment_interior_seed_040),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_041", cc_p7_ptsd_zero_on_segment_interior_seed_041),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_042", cc_p7_ptsd_zero_on_segment_interior_seed_042),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_043", cc_p7_ptsd_zero_on_segment_interior_seed_043),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_044", cc_p7_ptsd_zero_on_segment_interior_seed_044),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_045", cc_p7_ptsd_zero_on_segment_interior_seed_045),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_046", cc_p7_ptsd_zero_on_segment_interior_seed_046),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_047", cc_p7_ptsd_zero_on_segment_interior_seed_047),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_048", cc_p7_ptsd_zero_on_segment_interior_seed_048),
        ("creepage_check::tests::cc_p7_ptsd_zero_on_segment_interior_seed_049", cc_p7_ptsd_zero_on_segment_interior_seed_049),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_000", cc_p8_ptsd_degenerate_is_py_hypot_seed_000),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_001", cc_p8_ptsd_degenerate_is_py_hypot_seed_001),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_002", cc_p8_ptsd_degenerate_is_py_hypot_seed_002),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_003", cc_p8_ptsd_degenerate_is_py_hypot_seed_003),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_004", cc_p8_ptsd_degenerate_is_py_hypot_seed_004),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_005", cc_p8_ptsd_degenerate_is_py_hypot_seed_005),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_006", cc_p8_ptsd_degenerate_is_py_hypot_seed_006),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_007", cc_p8_ptsd_degenerate_is_py_hypot_seed_007),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_008", cc_p8_ptsd_degenerate_is_py_hypot_seed_008),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_009", cc_p8_ptsd_degenerate_is_py_hypot_seed_009),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_010", cc_p8_ptsd_degenerate_is_py_hypot_seed_010),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_011", cc_p8_ptsd_degenerate_is_py_hypot_seed_011),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_012", cc_p8_ptsd_degenerate_is_py_hypot_seed_012),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_013", cc_p8_ptsd_degenerate_is_py_hypot_seed_013),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_014", cc_p8_ptsd_degenerate_is_py_hypot_seed_014),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_015", cc_p8_ptsd_degenerate_is_py_hypot_seed_015),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_016", cc_p8_ptsd_degenerate_is_py_hypot_seed_016),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_017", cc_p8_ptsd_degenerate_is_py_hypot_seed_017),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_018", cc_p8_ptsd_degenerate_is_py_hypot_seed_018),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_019", cc_p8_ptsd_degenerate_is_py_hypot_seed_019),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_020", cc_p8_ptsd_degenerate_is_py_hypot_seed_020),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_021", cc_p8_ptsd_degenerate_is_py_hypot_seed_021),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_022", cc_p8_ptsd_degenerate_is_py_hypot_seed_022),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_023", cc_p8_ptsd_degenerate_is_py_hypot_seed_023),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_024", cc_p8_ptsd_degenerate_is_py_hypot_seed_024),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_025", cc_p8_ptsd_degenerate_is_py_hypot_seed_025),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_026", cc_p8_ptsd_degenerate_is_py_hypot_seed_026),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_027", cc_p8_ptsd_degenerate_is_py_hypot_seed_027),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_028", cc_p8_ptsd_degenerate_is_py_hypot_seed_028),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_029", cc_p8_ptsd_degenerate_is_py_hypot_seed_029),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_030", cc_p8_ptsd_degenerate_is_py_hypot_seed_030),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_031", cc_p8_ptsd_degenerate_is_py_hypot_seed_031),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_032", cc_p8_ptsd_degenerate_is_py_hypot_seed_032),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_033", cc_p8_ptsd_degenerate_is_py_hypot_seed_033),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_034", cc_p8_ptsd_degenerate_is_py_hypot_seed_034),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_035", cc_p8_ptsd_degenerate_is_py_hypot_seed_035),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_036", cc_p8_ptsd_degenerate_is_py_hypot_seed_036),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_037", cc_p8_ptsd_degenerate_is_py_hypot_seed_037),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_038", cc_p8_ptsd_degenerate_is_py_hypot_seed_038),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_039", cc_p8_ptsd_degenerate_is_py_hypot_seed_039),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_040", cc_p8_ptsd_degenerate_is_py_hypot_seed_040),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_041", cc_p8_ptsd_degenerate_is_py_hypot_seed_041),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_042", cc_p8_ptsd_degenerate_is_py_hypot_seed_042),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_043", cc_p8_ptsd_degenerate_is_py_hypot_seed_043),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_044", cc_p8_ptsd_degenerate_is_py_hypot_seed_044),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_045", cc_p8_ptsd_degenerate_is_py_hypot_seed_045),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_046", cc_p8_ptsd_degenerate_is_py_hypot_seed_046),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_047", cc_p8_ptsd_degenerate_is_py_hypot_seed_047),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_048", cc_p8_ptsd_degenerate_is_py_hypot_seed_048),
        ("creepage_check::tests::cc_p8_ptsd_degenerate_is_py_hypot_seed_049", cc_p8_ptsd_degenerate_is_py_hypot_seed_049),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_000", cc_p9_ptsd_bounded_by_endpoints_seed_000),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_001", cc_p9_ptsd_bounded_by_endpoints_seed_001),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_002", cc_p9_ptsd_bounded_by_endpoints_seed_002),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_003", cc_p9_ptsd_bounded_by_endpoints_seed_003),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_004", cc_p9_ptsd_bounded_by_endpoints_seed_004),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_005", cc_p9_ptsd_bounded_by_endpoints_seed_005),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_006", cc_p9_ptsd_bounded_by_endpoints_seed_006),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_007", cc_p9_ptsd_bounded_by_endpoints_seed_007),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_008", cc_p9_ptsd_bounded_by_endpoints_seed_008),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_009", cc_p9_ptsd_bounded_by_endpoints_seed_009),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_010", cc_p9_ptsd_bounded_by_endpoints_seed_010),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_011", cc_p9_ptsd_bounded_by_endpoints_seed_011),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_012", cc_p9_ptsd_bounded_by_endpoints_seed_012),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_013", cc_p9_ptsd_bounded_by_endpoints_seed_013),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_014", cc_p9_ptsd_bounded_by_endpoints_seed_014),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_015", cc_p9_ptsd_bounded_by_endpoints_seed_015),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_016", cc_p9_ptsd_bounded_by_endpoints_seed_016),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_017", cc_p9_ptsd_bounded_by_endpoints_seed_017),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_018", cc_p9_ptsd_bounded_by_endpoints_seed_018),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_019", cc_p9_ptsd_bounded_by_endpoints_seed_019),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_020", cc_p9_ptsd_bounded_by_endpoints_seed_020),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_021", cc_p9_ptsd_bounded_by_endpoints_seed_021),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_022", cc_p9_ptsd_bounded_by_endpoints_seed_022),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_023", cc_p9_ptsd_bounded_by_endpoints_seed_023),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_024", cc_p9_ptsd_bounded_by_endpoints_seed_024),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_025", cc_p9_ptsd_bounded_by_endpoints_seed_025),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_026", cc_p9_ptsd_bounded_by_endpoints_seed_026),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_027", cc_p9_ptsd_bounded_by_endpoints_seed_027),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_028", cc_p9_ptsd_bounded_by_endpoints_seed_028),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_029", cc_p9_ptsd_bounded_by_endpoints_seed_029),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_030", cc_p9_ptsd_bounded_by_endpoints_seed_030),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_031", cc_p9_ptsd_bounded_by_endpoints_seed_031),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_032", cc_p9_ptsd_bounded_by_endpoints_seed_032),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_033", cc_p9_ptsd_bounded_by_endpoints_seed_033),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_034", cc_p9_ptsd_bounded_by_endpoints_seed_034),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_035", cc_p9_ptsd_bounded_by_endpoints_seed_035),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_036", cc_p9_ptsd_bounded_by_endpoints_seed_036),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_037", cc_p9_ptsd_bounded_by_endpoints_seed_037),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_038", cc_p9_ptsd_bounded_by_endpoints_seed_038),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_039", cc_p9_ptsd_bounded_by_endpoints_seed_039),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_040", cc_p9_ptsd_bounded_by_endpoints_seed_040),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_041", cc_p9_ptsd_bounded_by_endpoints_seed_041),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_042", cc_p9_ptsd_bounded_by_endpoints_seed_042),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_043", cc_p9_ptsd_bounded_by_endpoints_seed_043),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_044", cc_p9_ptsd_bounded_by_endpoints_seed_044),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_045", cc_p9_ptsd_bounded_by_endpoints_seed_045),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_046", cc_p9_ptsd_bounded_by_endpoints_seed_046),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_047", cc_p9_ptsd_bounded_by_endpoints_seed_047),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_048", cc_p9_ptsd_bounded_by_endpoints_seed_048),
        ("creepage_check::tests::cc_p9_ptsd_bounded_by_endpoints_seed_049", cc_p9_ptsd_bounded_by_endpoints_seed_049),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_000", cc_p10_ptsd_segment_reversal_preserves_distance_seed_000),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_001", cc_p10_ptsd_segment_reversal_preserves_distance_seed_001),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_002", cc_p10_ptsd_segment_reversal_preserves_distance_seed_002),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_003", cc_p10_ptsd_segment_reversal_preserves_distance_seed_003),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_004", cc_p10_ptsd_segment_reversal_preserves_distance_seed_004),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_005", cc_p10_ptsd_segment_reversal_preserves_distance_seed_005),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_006", cc_p10_ptsd_segment_reversal_preserves_distance_seed_006),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_007", cc_p10_ptsd_segment_reversal_preserves_distance_seed_007),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_008", cc_p10_ptsd_segment_reversal_preserves_distance_seed_008),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_009", cc_p10_ptsd_segment_reversal_preserves_distance_seed_009),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_010", cc_p10_ptsd_segment_reversal_preserves_distance_seed_010),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_011", cc_p10_ptsd_segment_reversal_preserves_distance_seed_011),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_012", cc_p10_ptsd_segment_reversal_preserves_distance_seed_012),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_013", cc_p10_ptsd_segment_reversal_preserves_distance_seed_013),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_014", cc_p10_ptsd_segment_reversal_preserves_distance_seed_014),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_015", cc_p10_ptsd_segment_reversal_preserves_distance_seed_015),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_016", cc_p10_ptsd_segment_reversal_preserves_distance_seed_016),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_017", cc_p10_ptsd_segment_reversal_preserves_distance_seed_017),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_018", cc_p10_ptsd_segment_reversal_preserves_distance_seed_018),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_019", cc_p10_ptsd_segment_reversal_preserves_distance_seed_019),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_020", cc_p10_ptsd_segment_reversal_preserves_distance_seed_020),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_021", cc_p10_ptsd_segment_reversal_preserves_distance_seed_021),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_022", cc_p10_ptsd_segment_reversal_preserves_distance_seed_022),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_023", cc_p10_ptsd_segment_reversal_preserves_distance_seed_023),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_024", cc_p10_ptsd_segment_reversal_preserves_distance_seed_024),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_025", cc_p10_ptsd_segment_reversal_preserves_distance_seed_025),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_026", cc_p10_ptsd_segment_reversal_preserves_distance_seed_026),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_027", cc_p10_ptsd_segment_reversal_preserves_distance_seed_027),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_028", cc_p10_ptsd_segment_reversal_preserves_distance_seed_028),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_029", cc_p10_ptsd_segment_reversal_preserves_distance_seed_029),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_030", cc_p10_ptsd_segment_reversal_preserves_distance_seed_030),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_031", cc_p10_ptsd_segment_reversal_preserves_distance_seed_031),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_032", cc_p10_ptsd_segment_reversal_preserves_distance_seed_032),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_033", cc_p10_ptsd_segment_reversal_preserves_distance_seed_033),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_034", cc_p10_ptsd_segment_reversal_preserves_distance_seed_034),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_035", cc_p10_ptsd_segment_reversal_preserves_distance_seed_035),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_036", cc_p10_ptsd_segment_reversal_preserves_distance_seed_036),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_037", cc_p10_ptsd_segment_reversal_preserves_distance_seed_037),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_038", cc_p10_ptsd_segment_reversal_preserves_distance_seed_038),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_039", cc_p10_ptsd_segment_reversal_preserves_distance_seed_039),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_040", cc_p10_ptsd_segment_reversal_preserves_distance_seed_040),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_041", cc_p10_ptsd_segment_reversal_preserves_distance_seed_041),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_042", cc_p10_ptsd_segment_reversal_preserves_distance_seed_042),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_043", cc_p10_ptsd_segment_reversal_preserves_distance_seed_043),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_044", cc_p10_ptsd_segment_reversal_preserves_distance_seed_044),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_045", cc_p10_ptsd_segment_reversal_preserves_distance_seed_045),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_046", cc_p10_ptsd_segment_reversal_preserves_distance_seed_046),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_047", cc_p10_ptsd_segment_reversal_preserves_distance_seed_047),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_048", cc_p10_ptsd_segment_reversal_preserves_distance_seed_048),
        ("creepage_check::tests::cc_p10_ptsd_segment_reversal_preserves_distance_seed_049", cc_p10_ptsd_segment_reversal_preserves_distance_seed_049),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_000", cc_p11_ptsd_translation_invariant_seed_000),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_001", cc_p11_ptsd_translation_invariant_seed_001),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_002", cc_p11_ptsd_translation_invariant_seed_002),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_003", cc_p11_ptsd_translation_invariant_seed_003),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_004", cc_p11_ptsd_translation_invariant_seed_004),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_005", cc_p11_ptsd_translation_invariant_seed_005),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_006", cc_p11_ptsd_translation_invariant_seed_006),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_007", cc_p11_ptsd_translation_invariant_seed_007),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_008", cc_p11_ptsd_translation_invariant_seed_008),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_009", cc_p11_ptsd_translation_invariant_seed_009),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_010", cc_p11_ptsd_translation_invariant_seed_010),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_011", cc_p11_ptsd_translation_invariant_seed_011),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_012", cc_p11_ptsd_translation_invariant_seed_012),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_013", cc_p11_ptsd_translation_invariant_seed_013),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_014", cc_p11_ptsd_translation_invariant_seed_014),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_015", cc_p11_ptsd_translation_invariant_seed_015),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_016", cc_p11_ptsd_translation_invariant_seed_016),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_017", cc_p11_ptsd_translation_invariant_seed_017),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_018", cc_p11_ptsd_translation_invariant_seed_018),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_019", cc_p11_ptsd_translation_invariant_seed_019),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_020", cc_p11_ptsd_translation_invariant_seed_020),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_021", cc_p11_ptsd_translation_invariant_seed_021),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_022", cc_p11_ptsd_translation_invariant_seed_022),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_023", cc_p11_ptsd_translation_invariant_seed_023),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_024", cc_p11_ptsd_translation_invariant_seed_024),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_025", cc_p11_ptsd_translation_invariant_seed_025),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_026", cc_p11_ptsd_translation_invariant_seed_026),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_027", cc_p11_ptsd_translation_invariant_seed_027),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_028", cc_p11_ptsd_translation_invariant_seed_028),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_029", cc_p11_ptsd_translation_invariant_seed_029),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_030", cc_p11_ptsd_translation_invariant_seed_030),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_031", cc_p11_ptsd_translation_invariant_seed_031),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_032", cc_p11_ptsd_translation_invariant_seed_032),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_033", cc_p11_ptsd_translation_invariant_seed_033),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_034", cc_p11_ptsd_translation_invariant_seed_034),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_035", cc_p11_ptsd_translation_invariant_seed_035),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_036", cc_p11_ptsd_translation_invariant_seed_036),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_037", cc_p11_ptsd_translation_invariant_seed_037),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_038", cc_p11_ptsd_translation_invariant_seed_038),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_039", cc_p11_ptsd_translation_invariant_seed_039),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_040", cc_p11_ptsd_translation_invariant_seed_040),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_041", cc_p11_ptsd_translation_invariant_seed_041),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_042", cc_p11_ptsd_translation_invariant_seed_042),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_043", cc_p11_ptsd_translation_invariant_seed_043),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_044", cc_p11_ptsd_translation_invariant_seed_044),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_045", cc_p11_ptsd_translation_invariant_seed_045),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_046", cc_p11_ptsd_translation_invariant_seed_046),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_047", cc_p11_ptsd_translation_invariant_seed_047),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_048", cc_p11_ptsd_translation_invariant_seed_048),
        ("creepage_check::tests::cc_p11_ptsd_translation_invariant_seed_049", cc_p11_ptsd_translation_invariant_seed_049),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_000", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_000),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_001", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_001),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_002", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_002),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_003", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_003),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_004", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_004),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_005", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_005),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_006", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_006),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_007", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_007),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_008", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_008),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_009", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_009),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_010", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_010),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_011", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_011),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_012", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_012),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_013", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_013),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_014", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_014),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_015", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_015),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_016", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_016),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_017", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_017),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_018", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_018),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_019", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_019),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_020", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_020),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_021", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_021),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_022", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_022),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_023", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_023),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_024", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_024),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_025", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_025),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_026", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_026),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_027", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_027),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_028", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_028),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_029", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_029),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_030", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_030),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_031", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_031),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_032", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_032),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_033", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_033),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_034", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_034),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_035", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_035),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_036", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_036),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_037", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_037),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_038", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_038),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_039", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_039),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_040", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_040),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_041", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_041),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_042", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_042),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_043", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_043),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_044", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_044),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_045", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_045),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_046", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_046),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_047", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_047),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_048", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_048),
        ("creepage_check::tests::cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_049", cc_p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance_seed_049),
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

    // --- P6-P12 helper strategies (used inside the proptest! block) ---

    /// A wider coordinate range for the point-to-segment kernel
    /// itself, since it models board geometry in mm and the
    /// canonical 200 mm board fits comfortably here.
    fn wide_coord() -> impl Strategy<Value = f64> {
        -200.0f64..200.0f64
    }

    /// A non-degenerate segment (endpoints at least 1 µm apart).
    fn non_degenerate_seg() -> impl Strategy<Value = (f64, f64, f64, f64)> {
        (wide_coord(), wide_coord(), wide_coord(), wide_coord())
            .prop_filter("segment too short", |&(x1, y1, x2, y2)| {
                let dx = x2 - x1;
                let dy = y2 - y1;
                dx * dx + dy * dy >= 1e-6
            })
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

        // --------------------------------------------------------------
        // P6-P12: direct properties of the canonical
        // point_to_segment_distance kernel (issue #987 — the 4-copy
        // dedupe unified A/B/C onto the py_hypot contract).  These are
        // new allocations rather than renumbering the existing set so
        // the correspondence tables stay stable.
        // --------------------------------------------------------------

        /// P6. point_to_segment_distance is never negative for finite
        /// inputs.
        #[test]
        fn p6_ptsd_is_non_negative(
            px in wide_coord(), py in wide_coord(),
            x1 in wide_coord(), y1 in wide_coord(),
            x2 in wide_coord(), y2 in wide_coord(),
        ) {
            let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
            prop_assert!(d >= 0.0, "negative distance {}", d);
        }

        /// P7. A point lying on the segment interior has distance zero.
        #[test]
        fn p7_ptsd_zero_on_segment_interior(
            seg in non_degenerate_seg(), t in 0.0f64..1.0f64,
        ) {
            let (x1, y1, x2, y2) = seg;
            let px = x1 + t * (x2 - x1);
            let py = y1 + t * (y2 - y1);
            let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
            prop_assert!(
                d < 1e-10,
                "distance to point on segment interior is {} (should be 0)", d
            );
        }

        /// P8. A zero-length (degenerate) segment returns the
        /// point-to-point distance computed by py_hypot — not by sqrt,
        /// not by pow.
        #[test]
        fn p8_ptsd_degenerate_is_py_hypot(
            px in wide_coord(), py in wide_coord(),
            sx in wide_coord(), sy in wide_coord(),
        ) {
            let got = point_to_segment_distance(px, py, sx, sy, sx, sy);
            let expected = crate::pad_geometry::py_hypot(px - sx, py - sy);
            // Bit-exact — the degenerate arm literally calls py_hypot.
            prop_assert_eq!(got, expected,
                "degenerate-segment distance mismatch");
        }

        /// P9. The distance to a segment never exceeds the distance to
        /// either endpoint (the projection shortens or keeps the same).
        #[test]
        fn p9_ptsd_bounded_by_endpoints(
            px in wide_coord(), py in wide_coord(),
            seg in non_degenerate_seg(),
        ) {
            let (x1, y1, x2, y2) = seg;
            let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
            let de1 = crate::pad_geometry::py_hypot(px - x1, py - y1);
            let de2 = crate::pad_geometry::py_hypot(px - x2, py - y2);
            let bound = de1.min(de2);
            prop_assert!(
                d <= bound + 1e-12,
                "ptsd={} > min(de1={}, de2={})",
                d, de1, de2
            );
        }

        /// P10. Reversing the segment direction yields the same distance
        /// within floating-point rounding.  (NOT bit-exact — the
        /// projection formula `x1 + t*dx` rounds slightly differently
        /// from `x2 + (1-t)*(-dx)` when the point is nearly collinear.)
        #[test]
        fn p10_ptsd_segment_reversal_preserves_distance(
            px in wide_coord(), py in wide_coord(),
            x1 in wide_coord(), y1 in wide_coord(),
            x2 in wide_coord(), y2 in wide_coord(),
        ) {
            let forward = point_to_segment_distance(px, py, x1, y1, x2, y2);
            let reversed = point_to_segment_distance(px, py, x2, y2, x1, y1);
            prop_assert!(
                (forward - reversed).abs() <= 1e-12,
                "forward {} ≠ reversed {} (diff {})",
                forward, reversed, (forward - reversed).abs()
            );
        }

        /// P11. Translating the point and segment by the same vector
        /// preserves the distance (within floating-point rounding).
        #[test]
        fn p11_ptsd_translation_invariant(
            px in wide_coord(), py in wide_coord(),
            x1 in wide_coord(), y1 in wide_coord(),
            x2 in wide_coord(), y2 in wide_coord(),
            tx in -100.0f64..100.0f64, ty in -100.0f64..100.0f64,
        ) {
            let before = point_to_segment_distance(px, py, x1, y1, x2, y2);
            let after = point_to_segment_distance(
                px + tx, py + ty, x1 + tx, y1 + ty, x2 + tx, y2 + ty,
            );
            prop_assert!((after - before).abs() < 1e-6, "{} -> {} after translation", before, after);
        }

        /// P12. A point and segment that are collinear but the point is
        /// BEYOND the segment (projection clamps to the nearer endpoint)
        /// yields exactly the endpoint distance.
        #[test]
        fn p12_ptsd_collinear_beyond_endpoint_yields_endpoint_distance(
            seg in non_degenerate_seg(),
            beyond_factor in proptest::strategy::Union::new(vec![
                proptest::strategy::Just(-1.0),
                proptest::strategy::Just(2.0),
            ]).boxed(),
        ) {
            let (x1, y1, x2, y2) = seg;
            let dx = x2 - x1;
            let dy = y2 - y1;
            let px = x1 + beyond_factor * dx;
            let py = y1 + beyond_factor * dy;
            let d = point_to_segment_distance(px, py, x1, y1, x2, y2);
            // The nearer endpoint is either (x1,y1) or (x2,y2).
            let de1 = crate::pad_geometry::py_hypot(px - x1, py - y1);
            let de2 = crate::pad_geometry::py_hypot(px - x2, py - y2);
            let expected = de1.min(de2);
            prop_assert!(
                (d - expected).abs() < 1e-12,
                "collinear-beyond: got {} vs endpoint min {}",
                d, expected
            );
        }
    }



    // ------------------------------------------------------------------
    // Edge-case tests for the canonical point_to_segment_distance kernel.
    // These are NOT proptest-driven; they are targeted fixes for the
    // failure classes the spike identified (inf segments, NaN points,
    // denormal magnitudes, large coordinates).  Every assertion pins the
    // canonical py_hypot contract — a sqrt- or pow-close reimplementation
    // would diverge on at least one of these.
    // ------------------------------------------------------------------

    /// The degenerate branch fires on `!denom.is_finite()` as well as
    /// `denom == 0.0`.  An infinite segment endpoint makes `denom` either
    /// `inf` or `NaN`, both of which are !finite — the canonical kernel
    /// falls through to the point-to-point arm (py_hypot), returning
    /// `inf` rather than `NaN`.  Copy A (constraint_model) only checked
    /// `== 0` and would return `NaN` here.
    #[test]
    fn ptsd_infinite_segment_uses_py_hypot_degenerate_arm() {
        // inf segment endpoint → denom = inf (dx = inf - 0 = inf → dx² = inf)
        let d = point_to_segment_distance(5.0, 3.0, 0.0, 0.0, f64::INFINITY, 0.0);
        // py_hypot(5-0, 3-0) = hypot(5,3) ≈ 5.830951894845301
        assert!(d.is_finite(), "infinite-segment distance should be finite, got {d}");
        assert!((d - 5.830951894845301).abs() < 1e-12, "got {d}");

        // -inf segment endpoint — same branch.
        let d2 = point_to_segment_distance(5.0, 3.0, 0.0, 0.0, f64::NEG_INFINITY, 0.0);
        assert!(d2.is_finite(), "-inf-segment distance should be finite, got {d2}");
        assert!((d2 - 5.830951894845301).abs() < 1e-12, "got {d2}");
    }

    /// A NaN point coordinate propagates: the clamped projection lands
    /// on the far endpoint (NaN `t` → py_min(1,NaN)=1 → py_max(0,1)=1),
    /// then `py_hypot(NaN - proj_x, ...)` returns NaN.
    #[test]
    fn ptsd_nan_point_yields_nan() {
        let d = point_to_segment_distance(f64::NAN, 0.0, 0.0, 0.0, 10.0, 0.0);
        assert!(d.is_nan(), "NaN-px should yield NaN, got {d}");

        let d2 = point_to_segment_distance(5.0, f64::NAN, 0.0, 0.0, 10.0, 0.0);
        assert!(d2.is_nan(), "NaN-py should yield NaN, got {d2}");
    }

    /// A finite point with a NaN segment endpoint triggers the
    /// degenerate arm (denom is NaN → !finite), returning py_hypot of
    /// the finite point to the finite endpoint → NaN (because one leg
    /// of the hypot is NaN).  All three copies agree here; this pins
    /// that the canonical kernel preserves that behavior.
    #[test]
    fn ptsd_nan_segment_endpoint_yields_nan() {
        let d = point_to_segment_distance(5.0, 0.0, f64::NAN, 0.0, 10.0, 0.0);
        assert!(d.is_nan(), "NaN-seg-endpoint should yield NaN, got {d}");
    }

    /// Very large (but finite) coordinates: the canonical kernel must
    /// not overflow intermediate `dx*dx` where a naive `sqrt(dx²+dy²)`
    /// would (Copy A's failure mode).  `py_hypot`'s Dekker double-double
    /// rescales before squaring, so `denom = dx²+dy²` may overflow to
    /// `inf` — but the canonical kernel then falls through to the
    /// `!denom.is_finite()` degenerate arm and calls `py_hypot` on the
    /// point-to-endpoint vector, which also rescales internally.
    ///
    /// The point is offset by 1e150 from the segment — enough to survive
    /// f64 precision at this magnitude (ULP ≈ 1e134).  A sqrt-based
    /// reimplementation would overflow to inf here; the canonical
    /// returns a finite result.
    #[test]
    fn ptsd_large_coordinates_stay_finite() {
        let big = 1e150_f64;
        // Segment from (0,0) to (2*big, 0) — dx = 2e150, dx² overflows.
        let seg_x2 = 2.0 * big;
        // Point at (big, big) — well off the segment, offset = 1e150.
        let d = point_to_segment_distance(big, big, 0.0, 0.0, seg_x2, 0.0);
        // denom = dx² = (2e150)² overflows to inf → degenerate arm →
        // py_hypot(big - 0, big - 0) = hypot(1e150, 1e150) ≈ 1.414e150.
        assert!(d.is_finite(), "large-coordinate distance should be finite, got {d}");
        assert!(d > 1e149, "expected ~1.4e150, got {d}");
    }

    /// Denormal-magnitude inputs: the canonical kernel uses py_hypot
    /// which preserves subnormals.  Copy A (`sqrt(dx²+dy²)`) flushes
    /// intermediates to zero.  This is the spike's definitive
    /// discriminator — any sqrt-based reimplementation would fail this.
    #[test]
    fn ptsd_denormal_inputs_preserved_by_py_hypot() {
        let tiny = 1e-200_f64;
        let d = point_to_segment_distance(tiny, tiny, 0.0, 0.0, tiny, 0.0);
        // Degenerate segment (denom ≈ 1e-400, too small for f64 → 0.0),
        // so py_hypot(tiny-0, tiny-0) = hypot(tiny, tiny) ≈ 1.4e-200.
        assert!(d > 0.0, "denormal distance should be > 0, got {d}");
        assert!(d < 1e-100, "denormal distance should be tiny, got {d}");
        assert!(d.is_finite(), "denormal distance should be finite, got {d}");
    }

    /// Point EXACTLY at the segment endpoint: distance should be 0.0
    /// (bit-exact, not merely ~0).
    #[test]
    fn ptsd_point_at_segment_endpoint_is_zero() {
        assert_eq!(
            point_to_segment_distance(0.0, 0.0, 0.0, 0.0, 10.0, 5.0),
            0.0,
            "point at start endpoint"
        );
        assert_eq!(
            point_to_segment_distance(10.0, 5.0, 0.0, 0.0, 10.0, 5.0),
            0.0,
            "point at far endpoint"
        );
    }
}
