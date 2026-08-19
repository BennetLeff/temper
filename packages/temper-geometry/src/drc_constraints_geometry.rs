// DRC constraint geometry (Wave 4, router_v6 core slice).
//
// Python reference: `temper_placer/router_v6/constraints_geometry.py` --
// the geometric distance kernel behind the router's DRC oracle
// (`constraints_drc_oracle.py`), the connectivity checks
// (`router_v6/connectivity.py`) and the deterministic pipeline's
// pad-attachment test (`deterministic/stages/connectivity_validation.py`).
//
// The verbatim pre-migration copy this module must reproduce
// bit-identically is pinned at
// `packages/temper-placer/tests/router_v6/_constraints_geometry_py_oracle.py`
// (commit c5875adad) and compared by
// `test_constraints_geometry_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Why this is NOT `creepage_check.rs::point_to_segment_distance`
// ---------------------------------------------------------------------------
// This crate already carries a `point_to_segment_distance` for
// `creepage_check.py`.  It is a DIFFERENT function and reusing it here
// would be a silent behaviour change:
//
//   creepage_check.py      : degenerate when `denom == 0.0 || !denom.is_finite()`
//   constraints_geometry.py: degenerate when `seg_len_sq < 1e-10`
//
// A segment of length 1e-6 (seg_len_sq 1e-12) takes the degenerate arm in
// the reference ported here and the projection arm in the creepage one.
// The two references genuinely disagree; the migration preserves each as
// written rather than unifying them, and this comment exists so a future
// "obvious de-duplication" is recognised as the behaviour change it is.
//
// ---------------------------------------------------------------------------
// Numerical contract
// ---------------------------------------------------------------------------
// * `math.hypot` -> `py_hypot` (CPython's compensated `vector_norm`).  It
//   is NOT `sqrt(x*x + y*y)`: measured, 17.1% of random 2-vectors
//   disagree.  `f64::hypot` (libm) also differs in the last ulp.
// * `math.radians(x)` -> `x * (PI / 180.0)`.  CPython computes
//   `degToRad = Py_MATH_PI / 180.0` once and multiplies; the alternative
//   association `(x * PI) / 180.0` disagrees on 27.9% of random angles
//   (measured, 55817/200000).
// * `math.cos` / `math.sin` -> the host CPython process's own libm through
//   `dlsym` (`pad_geometry::math_cos_sin`), because a statically bound
//   `f64::sin` differs from a uv-standalone build's libm in the last ulp.
//   CPython additionally raises `ValueError("math domain error")` for an
//   infinite argument, where libm returns NaN silently -- replicated at the
//   pyo3 boundary by `check_finite_rotation`.
// * Builtin `min`/`max` -> `py_min` / `py_max`.  They propagate NaN from
//   the LEFT operand only and return the FIRST argument on ties, so
//   `max(0.0, -0.0)` is `+0.0` while `max(-0.0, 0.0)` is `-0.0`.
//   `f64::max`/`f64::min` do neither and `f64::clamp` panics when
//   `min > max` where this reference does not.
// * No `powi`/`powf` anywhere: the reference squares with `x * x`.
//
// R24 (physical quantities): every scalar crossing this boundary is a
// length in **millimetres** in the board coordinate frame, except
// `rotation`, which is **degrees** counter-clockwise in KiCad's
// footprint-child convention (R(-theta), see
// `temper_placer/geometry/kicad_transform`).  The kernel performs no unit
// conversion beyond the explicit `degrees -> radians` above; there is no
// mixed-unit arithmetic, and the boundary carries plain f64 because the
// Python reference does.

use crate::creepage_check::{py_max, py_min};
use crate::pad_geometry::py_hypot;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// CPython's `degToRad`: `Py_MATH_PI / 180.0`, computed once, then
/// multiplied.  See the module comment for why the association matters.
const DEG_TO_RAD: f64 = std::f64::consts::PI / 180.0;

/// `math.radians(x)`.
fn radians(deg: f64) -> f64 {
    deg * DEG_TO_RAD
}

/// KiCad R(-theta) footprint-child rotation.
///
/// Delegates to `kicad_transform` rather than re-typing the formula:
/// same `pad_geometry::math_cos_sin` host-libm kernel, same operation
/// order, so the swap is bit-identical by construction.
fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    crate::kicad_transform::rotate_local_to_world(x, y, theta_rad)
}

/// `kicad_transform.place_local_to_world` -- rotate then translate, in the
/// oracle's op order (the shared helper composes it the same way).
fn place_local_to_world(lx: f64, ly: f64, ox: f64, oy: f64, theta_rad: f64) -> (f64, f64) {
    crate::kicad_transform::place_local_to_world(lx, ly, ox, oy, theta_rad)
}

/// R(+theta), the inverse of `rotate_local_to_world`
/// (`kicad_transform.rotate_world_to_local`).
fn rotate_world_to_local(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    crate::kicad_transform::rotate_world_to_local(x, y, theta_rad)
}

// ---------------------------------------------------------------------------
// point / segment
// ---------------------------------------------------------------------------

/// `point_to_segment_distance(point, segment)`.
pub fn point_to_segment_distance(px: f64, py: f64, x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    let ppx = px - x1;
    let ppy = py - y1;
    let sx = x2 - x1;
    let sy = y2 - y1;
    let seg_len_sq = sx * sx + sy * sy;
    // NaN takes the `else` arm here exactly as Python's `<` does.
    if seg_len_sq < 1e-10 {
        return py_hypot(ppx, ppy);
    }
    let t = py_max(0.0, py_min(1.0, (ppx * sx + ppy * sy) / seg_len_sq));
    let closest_x = x1 + t * sx;
    let closest_y = y1 + t * sy;
    py_hypot(px - closest_x, py - closest_y)
}

/// The nested `_orientation` helper: 0 = collinear, 1 = clockwise,
/// 2 = counter-clockwise.  A NaN cross product falls through both
/// comparisons and yields 2, exactly as the Python does.
fn orientation(px: f64, py: f64, qx: f64, qy: f64, rx: f64, ry: f64) -> i32 {
    let val = (qy - py) * (rx - qx) - (qx - px) * (ry - qy);
    if val.abs() < 1e-10 {
        0
    } else if val > 0.0 {
        1
    } else {
        2
    }
}

/// The nested `_on_segment` helper: does `q` lie in the axis-aligned box
/// spanned by `p` and `r`?
fn on_segment(px: f64, py: f64, qx: f64, qy: f64, rx: f64, ry: f64) -> bool {
    py_min(px, rx) <= qx && qx <= py_max(px, rx) && py_min(py, ry) <= qy && qy <= py_max(py, ry)
}

/// `_segments_intersect(seg1, seg2)`.
#[allow(clippy::too_many_arguments)]
pub fn segments_intersect(
    p1x: f64,
    p1y: f64,
    q1x: f64,
    q1y: f64,
    p2x: f64,
    p2y: f64,
    q2x: f64,
    q2y: f64,
) -> bool {
    let o1 = orientation(p1x, p1y, q1x, q1y, p2x, p2y);
    let o2 = orientation(p1x, p1y, q1x, q1y, q2x, q2y);
    let o3 = orientation(p2x, p2y, q2x, q2y, p1x, p1y);
    let o4 = orientation(p2x, p2y, q2x, q2y, q1x, q1y);

    if o1 != o2 && o3 != o4 {
        return true;
    }
    if o1 == 0 && on_segment(p1x, p1y, p2x, p2y, q1x, q1y) {
        return true;
    }
    if o2 == 0 && on_segment(p1x, p1y, q2x, q2y, q1x, q1y) {
        return true;
    }
    if o3 == 0 && on_segment(p2x, p2y, p1x, p1y, q2x, q2y) {
        return true;
    }
    o4 == 0 && on_segment(p2x, p2y, q1x, q1y, q2x, q2y)
}

/// `segment_to_segment_distance(seg1, seg2)`.
#[allow(clippy::too_many_arguments)]
pub fn segment_to_segment_distance(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> f64 {
    if segments_intersect(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y) {
        return 0.0;
    }
    let d1 = point_to_segment_distance(a1x, a1y, b1x, b1y, b2x, b2y);
    let d2 = point_to_segment_distance(a2x, a2y, b1x, b1y, b2x, b2y);
    let d3 = point_to_segment_distance(b1x, b1y, a1x, a1y, a2x, a2y);
    let d4 = point_to_segment_distance(b2x, b2y, a1x, a1y, a2x, a2y);
    // Builtin `min(d1, d2, d3, d4)`: seed with the first, then replace only
    // on a strict `<`.  Left-to-right, so a leading NaN survives.
    py_min(py_min(py_min(d1, d2), d3), d4)
}

/// `closest_points_segment_segment(seg1, seg2)` -> `(c1x, c1y, c2x, c2y)`.
#[allow(clippy::too_many_arguments)]
pub fn closest_points_segment_segment(
    p1x: f64,
    p1y: f64,
    q1x: f64,
    q1y: f64,
    p2x: f64,
    p2y: f64,
    q2x: f64,
    q2y: f64,
) -> (f64, f64, f64, f64) {
    let d1x = q1x - p1x;
    let d1y = q1y - p1y;
    let d2x = q2x - p2x;
    let d2y = q2y - p2y;
    let rx = p1x - p2x;
    let ry = p1y - p2y;

    let a = d1x * d1x + d1y * d1y;
    let e = d2x * d2x + d2y * d2y;
    let f = d2x * rx + d2y * ry;

    if a <= 1e-10 && e <= 1e-10 {
        return (p1x, p1y, p2x, p2y);
    }
    if a <= 1e-10 {
        let t = py_max(0.0, py_min(1.0, f / e));
        return (p1x, p1y, p2x + t * d2x, p2y + t * d2y);
    }
    if e <= 1e-10 {
        let c = d1x * rx + d1y * ry;
        let s = py_max(0.0, py_min(1.0, -c / a));
        return (p1x + s * d1x, p1y + s * d1y, p2x, p2y);
    }

    let c = d1x * rx + d1y * ry;
    let b = d1x * d2x + d1y * d2y;
    let denom = a * e - b * b;

    // `!= 0.0` is true for NaN in Python and in Rust alike, so a NaN denom
    // takes the division arm and poisons `s` -- preserved deliberately.
    let mut s = if denom != 0.0 {
        py_max(0.0, py_min(1.0, (b * f - c * e) / denom))
    } else {
        0.0
    };

    let mut t = (b * s + f) / e;

    if t < 0.0 {
        t = 0.0;
        s = py_max(0.0, py_min(1.0, -c / a));
    } else if t > 1.0 {
        t = 1.0;
        s = py_max(0.0, py_min(1.0, (b - c) / a));
    }

    (p1x + s * d1x, p1y + s * d1y, p2x + t * d2x, p2y + t * d2y)
}

/// `point_to_circle_distance(point, center, radius)`.
pub fn point_to_circle_distance(px: f64, py: f64, cx: f64, cy: f64, radius: f64) -> f64 {
    py_hypot(px - cx, py - cy) - radius
}

// ---------------------------------------------------------------------------
// rotated rect
// ---------------------------------------------------------------------------

/// `RotatedRect.corners` -> the 4 corners in TL, TR, BR, BL order.
pub fn rotated_rect_corners(cx: f64, cy: f64, w: f64, h: f64, rotation_deg: f64) -> [(f64, f64); 4] {
    let hw = w / 2.0;
    let hh = h / 2.0;
    let rad = radians(rotation_deg);
    // Literal transcription of the reference's `local_pts` list, including
    // the unary minus placement (`-hw` of `w == 0.0` is `-0.0`, which the
    // rotation then carries into the result's sign).
    let local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)];
    let mut out = [(0.0, 0.0); 4];
    for (i, (lx, ly)) in local.iter().enumerate() {
        out[i] = place_local_to_world(*lx, *ly, cx, cy, rad);
    }
    out
}

/// `RotatedRect.bounding_radius`.
pub fn rotated_rect_bounding_radius(w: f64, h: f64) -> f64 {
    py_hypot(w / 2.0, h / 2.0)
}

/// `point_to_rotated_rect_distance(point, rect)`.
pub fn point_to_rotated_rect_distance(
    px: f64,
    py: f64,
    cx: f64,
    cy: f64,
    w: f64,
    h: f64,
    rotation_deg: f64,
) -> f64 {
    let dx = px - cx;
    let dy = py - cy;
    let (local_x, local_y) = rotate_world_to_local(dx, dy, radians(rotation_deg));

    let hw = w / 2.0;
    let hh = h / 2.0;

    let qx = local_x.abs() - hw;
    let qy = local_y.abs() - hh;

    let exterior = py_hypot(py_max(0.0, qx), py_max(0.0, qy));
    let interior = py_min(py_max(qx, qy), 0.0);

    exterior + interior
}

/// `segment_to_rotated_rect_distance(segment, rect)`.
///
/// The reference opens with a call to `point_to_segment_distance` whose
/// result is discarded (a half-finished broad-phase, left in place with an
/// explanatory comment).  It is not reproduced here: it is a pure function
/// of its arguments with no observable effect, and it cannot raise --
/// `math.hypot` returns `inf` on overflow rather than raising (verified:
/// `math.hypot(1.7e308, 1.7e308)` -> `inf`, no exception), and every other
/// operation in it is plain f64 arithmetic.  Dropping it is therefore
/// observationally equivalent, and the differential corpus includes the
/// overflow inputs that would expose it if that reasoning were wrong.
#[allow(clippy::too_many_arguments)]
pub fn segment_to_rotated_rect_distance(
    sx: f64,
    sy: f64,
    ex: f64,
    ey: f64,
    cx: f64,
    cy: f64,
    w: f64,
    h: f64,
    rotation_deg: f64,
) -> f64 {
    let d_start = point_to_rotated_rect_distance(sx, sy, cx, cy, w, h, rotation_deg);
    let d_end = point_to_rotated_rect_distance(ex, ey, cx, cy, w, h, rotation_deg);
    if d_start <= 0.0 || d_end <= 0.0 {
        return py_min(d_start, d_end);
    }

    let corners = rotated_rect_corners(cx, cy, w, h, rotation_deg);
    let edges = [
        (corners[0], corners[1]),
        (corners[1], corners[2]),
        (corners[2], corners[3]),
        (corners[3], corners[0]),
    ];

    let mut min_dist = f64::INFINITY;
    let mut intersects = false;

    for (a, b) in edges.iter() {
        let d = segment_to_segment_distance(sx, sy, ex, ey, a.0, a.1, b.0, b.1);
        if d < 1e-9 {
            intersects = true;
        }
        min_dist = py_min(min_dist, d);
    }

    if intersects {
        return -1.0;
    }

    min_dist
}

// ---------------------------------------------------------------------------
// LineSegment properties
// ---------------------------------------------------------------------------

/// `LineSegment.length` (`Point.distance_to`).
pub fn segment_length(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    py_hypot(x1 - x2, y1 - y2)
}

/// `LineSegment.direction` -- the unit vector, or `(1.0, 0.0)` for a
/// degenerate segment.  The caller wraps the pair in `np.array`, so the
/// f64 dtype and `(2,)` shape are unchanged.
///
/// NOTE the reference uses `math.hypot(dx, dy)` here, NOT
/// `np.linalg.norm`: there is no BLAS `ddot` on this path, so the
/// FMA-vs-unfused OpenBLAS microkernel divergence that flakes PR #714 does
/// not apply to this module at all.
pub fn segment_direction(x1: f64, y1: f64, x2: f64, y2: f64) -> (f64, f64) {
    let dx = x2 - x1;
    let dy = y2 - y1;
    let length = py_hypot(dx, dy);
    if length < 1e-10 {
        return (1.0, 0.0);
    }
    (dx / length, dy / length)
}

/// `LineSegment.midpoint`.
pub fn segment_midpoint(x1: f64, y1: f64, x2: f64, y2: f64) -> (f64, f64) {
    ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

/// CPython's `math.cos`/`math.sin` raise `ValueError("math domain error")`
/// for an infinite argument (libm sets EDOM and returns NaN; CPython's
/// `math_1` wrapper turns "NaN out, non-NaN in" into that exception).
/// `math.radians` never raises and maps `±inf -> ±inf`, so the rotation is
/// infinite exactly when the trig call would raise -- checked once, up
/// front, which is observationally identical because nothing before the
/// first trig call in any of these entry points can raise.
#[cfg(feature = "python")]
fn check_finite_rotation(rotation_deg: f64) -> PyResult<()> {
    if rotation_deg.is_infinite() {
        return Err(PyValueError::new_err("math domain error"));
    }
    Ok(())
}

/// `rect.size[0]` / `rect.size[1]`.
///
/// The reference INDEXES the size tuple (it does not unpack it), so a
/// malformed `size` raises `IndexError('tuple index out of range')`, not
/// the `ValueError` a `w, h = rect.size` unpack would raise — and it does
/// so *after* the rotation trig, which is why `size` crosses the boundary
/// as a sequence instead of two pre-unpacked scalars.  Preserving the
/// exception type here is what keeps the migration a true no-op for
/// callers that catch it.  (`RotatedRect.corners` and
/// `RotatedRect.bounding_radius` DO unpack in the reference, and their
/// wrappers keep that unpack in Python, before the boundary.)
#[cfg(feature = "python")]
fn size_wh(size: &[f64]) -> PyResult<(f64, f64)> {
    match (size.first(), size.get(1)) {
        (Some(w), Some(h)) => Ok((*w, *h)),
        _ => Err(pyo3::exceptions::PyIndexError::new_err(
            "tuple index out of range",
        )),
    }
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_point_to_segment_distance_py(
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
pub fn drc_segment_to_segment_distance_py(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        segment_to_segment_distance(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_segments_intersect_py(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| segments_intersect(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_closest_points_segment_segment_py(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        closest_points_segment_segment(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_point_to_circle_distance_py(
    px: f64,
    py: f64,
    cx: f64,
    cy: f64,
    radius: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| point_to_circle_distance(px, py, cx, cy, radius))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_rotated_rect_corners_py(
    cx: f64,
    cy: f64,
    w: f64,
    h: f64,
    rotation_deg: f64,
) -> PyResult<Vec<(f64, f64)>> {
    check_finite_rotation(rotation_deg)?;
    temper_py_bridge::catch_unwind(|| rotated_rect_corners(cx, cy, w, h, rotation_deg).to_vec())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_rotated_rect_bounding_radius_py(w: f64, h: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| rotated_rect_bounding_radius(w, h))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_point_to_rotated_rect_distance_py(
    px: f64,
    py: f64,
    cx: f64,
    cy: f64,
    size: Vec<f64>,
    rotation_deg: f64,
) -> PyResult<f64> {
    // Order matters: the reference rotates (which is what raises on an
    // infinite angle) BEFORE it indexes `size`.
    check_finite_rotation(rotation_deg)?;
    let (w, h) = size_wh(&size)?;
    temper_py_bridge::catch_unwind(|| {
        point_to_rotated_rect_distance(px, py, cx, cy, w, h, rotation_deg)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn drc_segment_to_rotated_rect_distance_py(
    sx: f64,
    sy: f64,
    ex: f64,
    ey: f64,
    cx: f64,
    cy: f64,
    size: Vec<f64>,
    rotation_deg: f64,
) -> PyResult<f64> {
    check_finite_rotation(rotation_deg)?;
    let (w, h) = size_wh(&size)?;
    temper_py_bridge::catch_unwind(|| {
        segment_to_rotated_rect_distance(sx, sy, ex, ey, cx, cy, w, h, rotation_deg)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_segment_length_py(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| segment_length(x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_segment_direction_py(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| segment_direction(x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn drc_segment_midpoint_py(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| segment_midpoint(x1, y1, x2, y2))
        .map_err(temper_py_bridge::panic_to_err)
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn bits(x: f64) -> u64 {
        x.to_bits()
    }

    #[cfg_attr(test, test)]
    fn radians_uses_the_multiply_association() {
        let d = 33.7_f64;
        assert_eq!(bits(radians(d)), bits(d * (std::f64::consts::PI / 180.0)));
        let mut differ = 0;
        let mut x = -720.0_f64;
        while x < 720.0 {
            if bits(x * DEG_TO_RAD) != bits((x * std::f64::consts::PI) / 180.0) {
                differ += 1;
            }
            x += 0.017;
        }
        assert!(differ > 100, "associations no longer differ: {differ}");
    }

    #[cfg_attr(test, test)]
    fn hypot_is_not_naive_sqrt() {
        let mut differ = 0;
        let mut a = 0.001_f64;
        while a < 2.0 {
            let n = (a * a + (a * 1.7) * (a * 1.7)).sqrt();
            if bits(py_hypot(a, a * 1.7)) != bits(n) {
                differ += 1;
            }
            a += 0.0013;
        }
        assert!(differ > 10, "py_hypot collapsed to naive sqrt: {differ}");
    }

    #[cfg_attr(test, test)]
    fn py_min_max_propagate_nan_from_the_left_only() {
        assert!(py_min(f64::NAN, 1.0).is_nan());
        assert_eq!(py_min(1.0, f64::NAN), 1.0);
        assert!(py_max(f64::NAN, 0.0).is_nan());
        assert_eq!(py_max(0.0, f64::NAN), 0.0);
        assert!(py_max(0.0, -0.0).is_sign_positive());
        assert!(py_max(-0.0, 0.0).is_sign_negative());
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_degenerate_threshold_is_1e_10_on_the_squared_length() {
        // A discriminating input: the projection arm and the degenerate arm
        // disagree when the point does not project onto the start.
        let a = point_to_segment_distance(1.0, 0.0, 0.0, 0.0, 1e-5, 0.0);
        let b = point_to_segment_distance(1.0, 0.0, 0.0, 0.0, 1e-6, 0.0);
        assert_ne!(bits(a), bits(b));
    }

    #[cfg_attr(test, test)]
    fn segments_intersect_covers_every_collinear_arm() {
        assert!(segments_intersect(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0));
        assert!(segments_intersect(0.0, 0.0, 10.0, 0.0, 5.0, 0.0, 15.0, 0.0));
        assert!(!segments_intersect(0.0, 0.0, 10.0, 0.0, 15.0, 0.0, 25.0, 0.0));
        assert!(segments_intersect(0.0, 0.0, 10.0, 0.0, 10.0, 0.0, 20.0, 0.0));
        assert!(!segments_intersect(0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0));
    }

    #[cfg_attr(test, test)]
    fn rotated_rect_corners_follow_the_kicad_r_minus_theta_convention() {
        // 90 degrees: local (-hw, -hh) -> world (-hh, +hw) under R(-theta).
        // Under the (wrong) R(+theta) convention it would be (+hh, -hw).
        let c = rotated_rect_corners(0.0, 0.0, 4.0, 2.0, 90.0);
        assert!((c[0].0 - -1.0).abs() < 1e-12, "{:?}", c[0]);
        assert!((c[0].1 - 2.0).abs() < 1e-12, "{:?}", c[0]);
    }

    #[cfg_attr(test, test)]
    fn point_to_rotated_rect_distance_signs() {
        assert_eq!(point_to_rotated_rect_distance(0.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0), -1.0);
        assert_eq!(point_to_rotated_rect_distance(1.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0), 0.0);
        assert_eq!(point_to_rotated_rect_distance(5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0), 4.0);
    }

    #[cfg_attr(test, test)]
    fn segment_to_rotated_rect_distance_arms() {
        assert_eq!(
            segment_to_rotated_rect_distance(-5.0, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
            -1.0
        );
        assert_eq!(
            segment_to_rotated_rect_distance(0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
            -1.0
        );
        let d = segment_to_rotated_rect_distance(10.0, 10.0, 20.0, 20.0, 0.0, 0.0, 2.0, 3.0, 0.0);
        assert!(d > 0.0 && d.is_finite());
    }

    #[cfg_attr(test, test)]
    fn direction_degenerate_arm() {
        assert_eq!(segment_direction(0.0, 0.0, 0.0, 0.0), (1.0, 0.0));
        assert_eq!(segment_direction(0.0, 0.0, 1e-11, 0.0), (1.0, 0.0));
        assert_eq!(segment_direction(0.0, 0.0, 3.0, 4.0), (0.6, 0.8));
    }

    #[cfg_attr(test, test)]
    fn closest_points_degenerate_arms() {
        assert_eq!(
            closest_points_segment_segment(1.0, 1.0, 1.0, 1.0, 4.0, 5.0, 4.0, 5.0),
            (1.0, 1.0, 4.0, 5.0)
        );
        let r = closest_points_segment_segment(1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 10.0, 0.0);
        assert_eq!((r.0, r.1), (1.0, 1.0));
        assert_eq!((r.2, r.3), (1.0, 0.0));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("drc_constraints_geometry::tests::radians_uses_the_multiply_association", radians_uses_the_multiply_association),
        ("drc_constraints_geometry::tests::hypot_is_not_naive_sqrt", hypot_is_not_naive_sqrt),
        ("drc_constraints_geometry::tests::py_min_max_propagate_nan_from_the_left_only", py_min_max_propagate_nan_from_the_left_only),
        ("drc_constraints_geometry::tests::point_to_segment_degenerate_threshold_is_1e_10_on_the_squared_length", point_to_segment_degenerate_threshold_is_1e_10_on_the_squared_length),
        ("drc_constraints_geometry::tests::segments_intersect_covers_every_collinear_arm", segments_intersect_covers_every_collinear_arm),
        ("drc_constraints_geometry::tests::rotated_rect_corners_follow_the_kicad_r_minus_theta_convention", rotated_rect_corners_follow_the_kicad_r_minus_theta_convention),
        ("drc_constraints_geometry::tests::point_to_rotated_rect_distance_signs", point_to_rotated_rect_distance_signs),
        ("drc_constraints_geometry::tests::segment_to_rotated_rect_distance_arms", segment_to_rotated_rect_distance_arms),
        ("drc_constraints_geometry::tests::direction_degenerate_arm", direction_degenerate_arm),
        ("drc_constraints_geometry::tests::closest_points_degenerate_arms", closest_points_degenerate_arms),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
