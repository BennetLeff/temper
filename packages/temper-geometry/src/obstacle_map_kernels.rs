// Wave 4, spatial-tier-2 unit: `router_v6/obstacle_map.py`'s two
// `Point(x, y).buffer(r, quad_segs=8)` via sites (escape vias and
// pre-existing vias).
//
// The S1 spike (`docs/evidence/2026-08-04-geos-polygon-algebra-spike.md`)
// proved the `Point.buffer` sites are portable *exactly* (§4.1), while
// `LineString.buffer` (§4.2, 32 of 66 vertices are GEOS offset-curve
// artifacts with no closed form) and `poly.buffer(0)` (§4.3, a
// GEOS-internal fixed point with no derivable semantics) are
// JUSTIFIED-KEEP with named blockers.  `unary_union` also stays in Python.
//
// This kernel reproduces GEOS's own circle construction
// (`OffsetSegmentGenerator::createCircle` + `addDirectedFillet` +
// `Angle::sinCosSnap`, GEOS 3.13.1) bit-for-bit, so the ring this returns
// is byte-identical to the ring of the shapely polygon the pre-migration
// code produced.  Verified: 0/400 random circles (cx, cy in [-100, 100],
// r in [1e-3, 20]) differ from `Point.buffer(r, quad_segs=q).exterior`
// ring for q = 8.
//
// Construction (transcribed from GEOS, not re-derived):
//
//   createCircle(p, d):            // d = radius
//     pts = [(p.x + d, p.y)]       // start point
//     addDirectedFillet(p, 0.0, PI_TIMES_2, CLOCKWISE, d)
//       totalAngle = |0.0 - PI_TIMES_2|           // PI_TIMES_2 = 2*MATH_PI
//       nSegs = (int)(totalAngle / fillet + 0.5)  // fillet = (MATH_PI/2)/q
//       angleInc = totalAngle / nSegs
//       for i in 0..nSegs:
//         angle = 0.0 + (-1.0 * i) * angleInc
//         sin, cos = sinCosSnap(angle)            // host libm + <5e-16 snap
//         pt = (p.x + d*cos, p.y + d*sin)
//         addPt(pt)                               // skips the exact start dup
//     closeRing()                                 // append pts[0]
//
//   Angle::sinCosSnap: std::sin/std::cos from the host libm, then any
//   component with |x| < 5e-16 is set to exactly 0.0 — this is why the
//   cardinal points are exact (±r, 0) / (0, ±r) instead of carrying the
//   ~1e-17 libm residual, and it is the part the S1 spike's naive closed
//   form `cx + r*cos(-k*pi/16)` missed.
//
//   MATH_PI is GEOS's `3.14159265358979323846` constant (geos/constants.h),
//   not `std::f64::consts::PI` written out — the two round to the same f64,
//   but the constant expression shape is preserved per bit-exactness class
//   B7.
//
// A point buffered by distance <= 0 is empty in GEOS
// (`isLineOffsetEmpty`), which shapely reports as `POLYGON EMPTY`; the
// Python shim maps the empty result here to `Polygon()`.

/// GEOS's `MATH_PI` constant (geos/constants.h) written at its declared
/// precision.  clippy flags it as "approximate PI" — that is exactly the
/// point: the constant must be reproduced as GEOS declares it, not as the
/// Rust std constant, so the constant expression shape matches the oracle
/// (bit-exactness class B7).
#[allow(clippy::approx_constant, clippy::excessive_precision)]
const GEOS_MATH_PI: f64 = 3.14159265358979323846;

/// GEOS `Angle::sinCosSnap(ang)`: host-libm sin/cos, snapping components
/// with magnitude < 5e-16 to exactly 0.0.
fn geos_sin_cos_snap(angle: f64) -> (f64, f64) {
    let mut s = crate::host_math::sin(angle);
    let mut c = crate::host_math::cos(angle);
    if s.abs() < 5e-16 {
        s = 0.0;
    }
    if c.abs() < 5e-16 {
        c = 0.0;
    }
    (s, c)
}

/// The closed exterior ring (start point repeated at the end) of
/// `Point(cx, cy).buffer(radius, quad_segs=quad_segs)`, bit-identical to
/// GEOS's.  Returns the empty ring for `radius <= 0` (GEOS's
/// `isLineOffsetEmpty`).
pub fn circle_buffer_ring(cx: f64, cy: f64, radius: f64, quad_segs: i64) -> Vec<(f64, f64)> {
    if radius <= 0.0 {
        return Vec::new();
    }
    // OffsetSegmentGenerator clamps quadSegs to >= 1 before computing
    // filletAngleQuantum.
    let quad_segs = quad_segs.max(1);
    let pi_times_2 = 2.0 * GEOS_MATH_PI;
    let pi_over_2 = GEOS_MATH_PI / 2.0;
    let fillet = pi_over_2 / quad_segs as f64;
    let total = (0.0 - pi_times_2).abs();
    let n_seg = (total / fillet + 0.5) as i64;
    let ang_inc = total / n_seg as f64;

    let mut pts: Vec<(f64, f64)> = Vec::with_capacity(n_seg as usize + 2);
    pts.push((cx + radius, cy));
    for i in 0..n_seg {
        // `-1.0 * i as f64` preserves the oracle's `directionFactor * i`
        // expression shape (directionFactor is the double -1.0 in GEOS).
        #[allow(clippy::neg_multiply)]
        let angle = 0.0 + (-1.0 * i as f64) * ang_inc;
        let (s, c) = geos_sin_cos_snap(angle);
        let p = (cx + radius * c, cy + radius * s);
        // GEOS's segment list skips a point equal to the last one; for the
        // circle this fires only for i == 0 (the exact start duplicate).
        if pts.last() != Some(&p) {
            pts.push(p);
        }
    }
    pts.push(pts[0]);
    pts
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// pyo3 surface for `circle_buffer_ring`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn circle_buffer_ring_py(
    cx: f64,
    cy: f64,
    radius: f64,
    quad_segs: i64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(move || circle_buffer_ring(cx, cy, radius, quad_segs))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(circle_buffer_ring_py, m)?)?;
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
    fn ring_shape_for_quad_segs_8() {
        let ring = circle_buffer_ring(0.0, 0.0, 0.125, 8);
        // 32 distinct vertices + closure (the start duplicate is dropped).
        assert_eq!(ring.len(), 33);
        assert_eq!(ring[0], (0.125, 0.0));
        // Cardinal points snap to exact zeros (sinCosSnap), not libm
        // residuals.
        assert_eq!(ring[8], (0.0, -0.125));
        assert_eq!(ring[16], (-0.125, 0.0));
        assert_eq!(ring[24], (0.0, 0.125));
        assert_eq!(ring[0], ring[32]);
    }

    #[cfg_attr(test, test)]
    fn ring_is_clockwise_from_plus_x() {
        let ring = circle_buffer_ring(1.5, -2.25, 0.3, 8);
        // k=0 -> +x; k=1 -> clockwise (negative y delta).
        assert_eq!(ring[0], (1.8, -2.25));
        assert!(ring[1].1 < -2.25);
        assert_eq!(ring[0], ring[ring.len() - 1]);
    }

    #[cfg_attr(test, test)]
    fn nonpositive_radius_is_empty() {
        assert!(circle_buffer_ring(1.0, 2.0, 0.0, 8).is_empty());
        assert!(circle_buffer_ring(1.0, 2.0, -0.5, 8).is_empty());
        assert!(circle_buffer_ring(1.0, 2.0, -0.0, 8).is_empty());
    }

    #[cfg_attr(test, test)]
    fn quad_segs_is_clamped_to_at_least_one() {
        // GEOS clamps quadSegs < 1 to 1 -> a 4-gon.
        let ring = circle_buffer_ring(0.0, 0.0, 1.0, 0);
        assert_eq!(ring.len(), 5); // 4 distinct + closure
        let ring_neg = circle_buffer_ring(0.0, 0.0, 1.0, -3);
        assert_eq!(ring, ring_neg);
    }

    #[cfg_attr(test, test)]
    fn cardinal_snap_is_what_differentiates_from_naive_closed_form() {
        // The naive `cx + r*cos(-k*pi/16)` closed form carries a ~7.7e-18
        // residual at the k=8 cardinal point; GEOS snaps to exactly 0.0.
        let ring = circle_buffer_ring(0.0, 0.0, 0.125, 8);
        assert_eq!(ring[8].0, 0.0);
        let naive_x = 0.0 + 0.125 * crate::host_math::cos(-8.0 * (GEOS_MATH_PI / 16.0));
        assert_ne!(naive_x, 0.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("obstacle_map_kernels::tests::ring_shape_for_quad_segs_8", ring_shape_for_quad_segs_8),
        ("obstacle_map_kernels::tests::ring_is_clockwise_from_plus_x", ring_is_clockwise_from_plus_x),
        ("obstacle_map_kernels::tests::nonpositive_radius_is_empty", nonpositive_radius_is_empty),
        ("obstacle_map_kernels::tests::quad_segs_is_clamped_to_at_least_one", quad_segs_is_clamped_to_at_least_one),
        ("obstacle_map_kernels::tests::cardinal_snap_is_what_differentiates_from_naive_closed_form", cardinal_snap_is_what_differentiates_from_naive_closed_form),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
