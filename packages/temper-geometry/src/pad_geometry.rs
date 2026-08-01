// Pad geometry (Wave 2, isolation-barrier slice) — the shared, exact
// shape-aware pad-radius model.
//
// Python reference: temper_placer/core/pad_geometry.py
// (pad_corner_radius / pad_core_half_extents / pad_support_radius /
// pad_axis_radius / pad_bounding_radius) and the barrier sweep in
// temper_placer/placer/cp_sat/isolation_barrier.py
// (_axis_gap / _project_onto_barrier_axis / _best_rotation_for_barrier).
//
// This is the shared model behind the REQ-SAFE isolation-barrier
// constraint encoder, the keepout gate (check_isolation_keepout.py) and
// the router's pad-inflation paths — one implementation in Rust, with
// the Python modules delegating, so every consumer cannot drift apart.
//
// Bit-exactness: identical f64 operation order (left-to-right), same
// correctly-rounded libm cos/sin/hypot, same integer-exact rotation
// table. Pinned by the differential suite.

use pyo3::prelude::*;
use temper_py_bridge;

const DEFAULT_ROUNDRECT_RATIO: f64 = 0.25;

// The host Python process's math.cos/math.sin (uv standalone builds ship
// their own libm; the extension's statically-bound f64::cos/sin can
// differ from it in the last ulp — measured: f64::sin differed for a
// real input while f64::cos matched). Resolve cos/sin through dlsym so
// the crate matches the runtime's math bit-exactly; fall back to the
// std intrinsics when dlsym is unavailable.
use std::sync::OnceLock;

type MathFn = unsafe extern "C" fn(f64) -> f64;

fn dlsym_math(symbol: &str) -> Option<MathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    unsafe {
        let p = dlsym(RTLD_DEFAULT, symbol.as_ptr());
        if p.is_null() {
            None
        } else {
            Some(std::mem::transmute::<*mut u8, MathFn>(p))
        }
    }
}

unsafe extern "C" fn fallback_cos(x: f64) -> f64 {
    f64::cos(x)
}

unsafe extern "C" fn fallback_sin(x: f64) -> f64 {
    f64::sin(x)
}

fn host_cos() -> &'static MathFn {
    static F: OnceLock<Option<MathFn>> = OnceLock::new();
    F.get_or_init(|| dlsym_math("cos").or(Some(fallback_cos)))
        .as_ref()
        .unwrap()
}

fn host_sin() -> &'static MathFn {
    static F: OnceLock<Option<MathFn>> = OnceLock::new();
    F.get_or_init(|| dlsym_math("sin").or(Some(fallback_sin)))
        .as_ref()
        .unwrap()
}

fn math_cos(x: f64) -> f64 {
    unsafe { host_cos()(x) }
}

pub(crate) fn math_sin(x: f64) -> f64 {
    unsafe { host_sin()(x) }
}

pub(crate) fn math_cos_sin(x: f64) -> (f64, f64) {
    unsafe { (host_cos()(x), host_sin()(x)) }
}

/// Pad-shape codes passed across the FFI boundary. The Python wrapper
/// (`temper_placer/core/pad_geometry.py`'s `shape_code()`) maps its
/// `KNOWN_SHAPES` to these before calling; unrecognized shapes are sent
/// as `SHAPE_UNKNOWN` and fall back to the safe r=0 sharp-corner model
/// (identical to the old unrecognized-string fallback). Codes are
/// pinned by the differential suites on both sides.
pub(crate) const SHAPE_CIRCLE: i64 = 0;
pub(crate) const SHAPE_OVAL: i64 = 1;
pub(crate) const SHAPE_RECT: i64 = 2;
pub(crate) const SHAPE_ROUNDRECT: i64 = 3;
pub(crate) const SHAPE_THRU_HOLE: i64 = 4;
/// Sentinel the Python wrapper sends for unrecognized shapes; Rust never
/// reads it (the `_` fallback in `shape_kind` covers it), it exists to
/// document the FFI contract.
#[allow(dead_code)]
pub(crate) const SHAPE_UNKNOWN: i64 = 99;

/// The model's shape kind. `thru_hole` normalizes to `Circle` (the old
/// `normalize_shape` string rewrite); unrecognized codes fall back to
/// `Rect` — sharp corners, r = 0, safe (never under-reports; the Python
/// wrapper emits the warning).
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum ShapeKind {
    Circle,
    Oval,
    Rect,
    Roundrect,
}

pub(crate) fn shape_kind(code: i64) -> ShapeKind {
    match code {
        SHAPE_CIRCLE | SHAPE_THRU_HOLE => ShapeKind::Circle,
        SHAPE_OVAL => ShapeKind::Oval,
        SHAPE_ROUNDRECT => ShapeKind::Roundrect,
        // SHAPE_RECT and unrecognized codes: sharp corners.
        _ => ShapeKind::Rect,
    }
}

pub(crate) fn corner_radius(width: f64, height: f64, shape: i64, ratio: f64) -> f64 {
    match shape_kind(shape) {
        // circle pads: width == height == diameter; take the larger
        // defensively so malformed input stays conservative.
        ShapeKind::Circle => width.max(height) / 2.0,
        ShapeKind::Oval => width.min(height) / 2.0,
        ShapeKind::Roundrect => ratio * width.min(height),
        // rect and unrecognized shapes: sharp corners, r = 0 (safe,
        // never under-reports; the Python wrapper emits the warning).
        ShapeKind::Rect => 0.0,
    }
}

pub(crate) fn core_half_extents(width: f64, height: f64, shape: i64, ratio: f64) -> (f64, f64) {
    let r = corner_radius(width, height, shape, ratio);
    ((width / 2.0 - r).max(0.0), (height / 2.0 - r).max(0.0))
}

fn support_radius(
    width: f64,
    height: f64,
    shape: i64,
    direction_rad: f64,
    rotation_rad: f64,
    ratio: f64,
) -> f64 {
    let local_angle = direction_rad - rotation_rad;
    let (dx, dy) = (math_cos(local_angle), math_sin(local_angle));
    let (hw, hh) = core_half_extents(width, height, shape, ratio);
    let r = corner_radius(width, height, shape, ratio);
    hw * dx.abs() + hh * dy.abs() + r
}

fn axis_radius(width: f64, height: f64, shape: i64, axis: i64, rotation_rad: f64, ratio: f64) -> f64 {
    // Python's reference: `0.0 if axis == 0 else math.pi / 2.0` — the
    // DIVISION, not FRAC_PI_2: fl(pi)/2 = 0x1.921fb54442d18p0 while
    // FRAC_PI_2 = 0x1.921fb54442d17p0 (1 ulp apart), and the difference
    // propagates through cos/sin to the last ulp of the radius.
    let direction = if axis == 0 { 0.0 } else { std::f64::consts::PI / 2.0 };
    support_radius(width, height, shape, direction, rotation_rad, ratio)
}

pub(crate) fn bounding_radius(width: f64, height: f64, shape: i64, ratio: f64) -> f64 {
    let (hw, hh) = core_half_extents(width, height, shape, ratio);
    let r = corner_radius(width, height, shape, ratio);
    py_hypot(hw, hh) + r
}

/// CPython 3.12's `math.hypot` (2-arg `vector_norm`), replicated exactly:
/// Dekker double-double compensated norm with fma-based `dl_mul`
/// (CPython's default build; Apple's fma is accurate). Rust's
/// `f64::hypot` (libm) differs from this in the last ulp, so the exact
/// algorithm is ported — see CPython Modules/mathmodule.c `vector_norm`.
///
/// `pub(crate)`: shared by every module whose reference calls
/// `math.hypot` (the creepage/clearance geometry in `creepage_check.rs`
/// is the second consumer, added Wave 3).
pub(crate) fn py_hypot(x: f64, y: f64) -> f64 {
    // CPython `math_hypot_impl` returns NaN up front when any input is
    // NaN (before vector_norm runs); the `f64::max` below would otherwise
    // discard a NaN argument.  And hypot(±inf, anything) is +inf, which
    // the vector_norm path would turn into NaN through the fma-based
    // correction (CPython's frexp gives e=0 for inf, ours does not), so
    // both guards are exact CPython semantics, not approximations.
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    if x.is_infinite() || y.is_infinite() {
        return f64::INFINITY;
    }
    let x = x.abs();
    let y = y.abs();
    let max = x.max(y);
    if max == 0.0 {
        return 0.0;
    }
    vector_norm_2(x, y, max)
}

struct DL {
    hi: f64,
    lo: f64,
}

fn dl_fast_sum(a: f64, b: f64) -> DL {
    let s = a + b;
    DL { hi: s, lo: (a - s) + b }
}

fn dl_mul(x: f64, y: f64) -> DL {
    let z = x * y;
    DL { hi: z, lo: x.mul_add(y, -z) }
}

fn frexp(x: f64) -> (f64, i32) {
    let bits = x.to_bits();
    let e = ((bits >> 52) & 0x7ff) as i32 - 1022;
    let m = f64::from_bits((bits & 0x800f_ffff_ffff_ffff) | 0x3fe0_0000_0000_0000);
    (m, e)
}

fn vector_norm_2(x: f64, y: f64, max: f64) -> f64 {
    let (_, max_e) = frexp(max);
    if max_e < -1023 {
        // Subnormal inputs: convert to normals, recurse, rescale (CPython
        // `if (max_e < -1023)` branch). Unreachable for pad-scale values,
        // implemented for exactness.
        return f64::MIN_POSITIVE * vector_norm_2(x / f64::MIN_POSITIVE, y / f64::MIN_POSITIVE, max / f64::MIN_POSITIVE);
    }
    let scale = 2f64.powi(-max_e);
    let mut csum = 1.0f64;
    let mut frac1 = 0.0f64;
    let mut frac2 = 0.0f64;
    for v in [x * scale, y * scale] {
        let pr = dl_mul(v, v);
        let sm = dl_fast_sum(csum, pr.hi);
        csum = sm.hi;
        frac1 += pr.lo;
        frac2 += sm.lo;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let pr = dl_mul(-h, h);
    let sm = dl_fast_sum(csum, pr.hi);
    csum = sm.hi;
    frac1 += pr.lo;
    frac2 += sm.lo;
    let x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h); // differential correction
    h / scale
}

// ---------------------------------------------------------------------------
// Barrier sweep
// ---------------------------------------------------------------------------

/// Integer-exact rotation mapping (the model's 4 axis-aligned rotations,
/// KiCad R(-theta) convention):
///   rot=0: (gx, gy) = ( lx,  ly)
///   rot=1: (gx, gy) = ( ly, -lx)
///   rot=2: (gx, gy) = (-lx, -ly)
///   rot=3: (gx, gy) = (-ly,  lx)
fn project_onto_barrier_axis(local_x: f64, local_y: f64, rot_value: i64, barrier_axis: i64) -> f64 {
    let (gx, gy) = match rot_value {
        0 => (local_x, local_y),
        1 => (local_y, -local_x),
        2 => (-local_x, -local_y),
        _ => (-local_y, local_x),
    };
    if barrier_axis == 0 { gx } else { gy }
}

/// A pad as consumed by the barrier sweep:
/// (x, y, width, height, shape_code, roundrect_ratio). `shape_code` is
/// the FFI int enum (see `SHAPE_*`); the Python wrapper maps it once.
type PadTuple = (f64, f64, f64, f64, i64, f64);

fn pad_projection(p: &PadTuple, rot_value: i64, barrier_axis: i64) -> (f64, f64) {
    let (x, y, w, h, shape, ratio) = p;
    let proj = project_onto_barrier_axis(*x, *y, rot_value, barrier_axis);
    // Python reference: `rot_value * math.pi / 2.0` (multiply then divide,
    // NOT rot_value * FRAC_PI_2 — the latter differs in the last ulp for
    // odd rot_values, propagating into the axis radius).
    let rad = axis_radius(*w, *h, *shape, barrier_axis, rot_value as f64 * std::f64::consts::PI / 2.0, *ratio);
    (proj, rad)
}

/// Worst-case (minimum over every HV x SELV pair) edge-to-edge gap on one
/// LOCAL axis, rotation 0. Mirrors isolation_barrier.py::_axis_gap.
fn barrier_axis_gap(hv: &[PadTuple], selv: &[PadTuple], axis_idx: i64) -> f64 {
    let mut worst = f64::INFINITY;
    for hp in hv {
        for sp in selv {
            let h = if axis_idx == 0 { hp.0 } else { hp.1 };
            let s = if axis_idx == 0 { sp.0 } else { sp.1 };
            let hr = axis_radius(hp.2, hp.3, hp.4, axis_idx, 0.0, hp.5);
            let sr = axis_radius(sp.2, sp.3, sp.4, axis_idx, 0.0, sp.5);
            let gap = (h - s).abs() - hr - sr;
            if gap < worst {
                worst = gap;
            }
        }
    }
    worst
}

/// Pick the rotation (of the 4) giving the largest HV/SELV cluster gap on
/// barrier_axis, restricted to rotations keeping HV=lo / SELV=hi.
/// Mirrors isolation_barrier.py::_best_rotation_for_barrier exactly
/// (first-maximum tie-breaking, fallback on convention violation).
/// Returns (rot_value, gap_mm, convention_kept).
fn best_rotation_for_barrier(hv: &[PadTuple], selv: &[PadTuple], barrier_axis: i64) -> (i64, f64, bool) {
    let mut best: Option<(i64, f64)> = None;
    let mut fallback: Option<(i64, f64)> = None;
    for rot_value in 0..4i64 {
        let hv_proj: Vec<(f64, f64)> = hv.iter().map(|p| pad_projection(p, rot_value, barrier_axis)).collect();
        let selv_proj: Vec<(f64, f64)> = selv.iter().map(|p| pad_projection(p, rot_value, barrier_axis)).collect();
        let hv_mean: f64 = hv_proj.iter().map(|(p, _)| p).sum::<f64>() / hv_proj.len() as f64;
        let selv_mean: f64 = selv_proj.iter().map(|(p, _)| p).sum::<f64>() / selv_proj.len() as f64;
        let gap = hv_proj
            .iter()
            .flat_map(|(hp, hr)| selv_proj.iter().map(move |(sp, sr)| (hp - sp).abs() - hr - sr))
            .fold(f64::INFINITY, f64::min);
        match fallback {
            None => fallback = Some((rot_value, gap)),
            Some((_, g)) if gap > g => fallback = Some((rot_value, gap)),
            _ => {}
        }
        if hv_mean > selv_mean {
            continue; // would invert the board-wide HV=lo/SELV=hi convention
        }
        match best {
            None => best = Some((rot_value, gap)),
            Some((_, g)) if gap > g => best = Some((rot_value, gap)),
            _ => {}
        }
    }
    match best {
        Some((rot, gap)) => (rot, gap, true),
        None => fallback.map(|(rot, gap)| (rot, gap, false)).expect("rotation sweep produced no fallback"),
    }
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[pyfunction]
#[pyo3(signature = (width, height, shape, roundrect_ratio = DEFAULT_ROUNDRECT_RATIO))]
pub fn pad_corner_radius_py(width: f64, height: f64, shape: i64, roundrect_ratio: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| corner_radius(width, height, shape, roundrect_ratio)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (width, height, shape, roundrect_ratio = DEFAULT_ROUNDRECT_RATIO))]
pub fn pad_core_half_extents_py(width: f64, height: f64, shape: i64, roundrect_ratio: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| core_half_extents(width, height, shape, roundrect_ratio)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (width, height, shape, direction_rad, rotation_rad = 0.0, roundrect_ratio = DEFAULT_ROUNDRECT_RATIO))]
pub fn pad_support_radius_py(
    width: f64,
    height: f64,
    shape: i64,
    direction_rad: f64,
    rotation_rad: f64,
    roundrect_ratio: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| support_radius(width, height, shape, direction_rad, rotation_rad, roundrect_ratio))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (width, height, shape, axis, rotation_rad = 0.0, roundrect_ratio = DEFAULT_ROUNDRECT_RATIO))]
pub fn pad_axis_radius_py(
    width: f64,
    height: f64,
    shape: i64,
    axis: i64,
    rotation_rad: f64,
    roundrect_ratio: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| axis_radius(width, height, shape, axis, rotation_rad, roundrect_ratio))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (width, height, shape, roundrect_ratio = DEFAULT_ROUNDRECT_RATIO))]
pub fn pad_bounding_radius_py(width: f64, height: f64, shape: i64, roundrect_ratio: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| bounding_radius(width, height, shape, roundrect_ratio)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (hv_pads, selv_pads, axis_idx))]
pub fn barrier_axis_gap_py(hv_pads: Vec<PadTuple>, selv_pads: Vec<PadTuple>, axis_idx: i64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| barrier_axis_gap(&hv_pads, &selv_pads, axis_idx)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (hv_pads, selv_pads, barrier_axis))]
pub fn best_rotation_for_barrier_py(hv_pads: Vec<PadTuple>, selv_pads: Vec<PadTuple>, barrier_axis: i64) -> PyResult<(i64, f64, bool)> {
    temper_py_bridge::catch_unwind(|| best_rotation_for_barrier(&hv_pads, &selv_pads, barrier_axis)).map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_corner_radius_shapes() {
        assert_eq!(corner_radius(2.0, 2.0, SHAPE_CIRCLE, 0.25), 1.0);
        assert_eq!(corner_radius(4.0, 2.0, SHAPE_OVAL, 0.25), 1.0);
        assert_eq!(corner_radius(4.0, 2.0, SHAPE_ROUNDRECT, 0.25), 0.5);
        assert_eq!(corner_radius(4.0, 2.0, SHAPE_RECT, 0.25), 0.0);
        assert_eq!(corner_radius(4.0, 2.0, SHAPE_UNKNOWN, 0.25), 0.0); // safe fallback
        assert_eq!(corner_radius(3.0, 3.0, SHAPE_THRU_HOLE, 0.25), 1.5); // normalized
    }

    #[test]
    fn test_support_radius_axis_aligned() {
        // 2x1 roundrect r=0.25: hw=0.75, hh=0.25, r=0.25.
        // axis X at rot 0: 0.75 + 0 + 0.25 = 1.0
        assert!((support_radius(2.0, 1.0, SHAPE_ROUNDRECT, 0.0, 0.0, 0.25) - 1.0).abs() < 1e-12);
        // axis Y at rot 0: 0 + 0.25 + 0.25 = 0.5
        assert!((support_radius(2.0, 1.0, SHAPE_ROUNDRECT, std::f64::consts::FRAC_PI_2, 0.0, 0.25) - 0.5).abs() < 1e-12);
    }

    #[test]
    fn test_rotation_maps_exact() {
        assert_eq!(project_onto_barrier_axis(3.0, 4.0, 0, 0), 3.0);
        assert_eq!(project_onto_barrier_axis(3.0, 4.0, 1, 0), 4.0);
        assert_eq!(project_onto_barrier_axis(3.0, 4.0, 2, 0), -3.0);
        assert_eq!(project_onto_barrier_axis(3.0, 4.0, 3, 0), -4.0);
        assert_eq!(project_onto_barrier_axis(3.0, 4.0, 1, 1), -3.0);
    }

    #[test]
    fn test_barrier_gap_and_rotation() {
        let hv = vec![(0.0, 0.0, 2.0, 1.0, SHAPE_ROUNDRECT, 0.25)];
        let selv = vec![(10.0, 0.0, 2.0, 1.0, SHAPE_ROUNDRECT, 0.25)];
        let gap = barrier_axis_gap(&hv, &selv, 0);
        assert!((gap - 8.0).abs() < 1e-9); // 10 - 1.0 (hv rad) - 1.0 (selv rad)
        let (rot, best, kept) = best_rotation_for_barrier(&hv, &selv, 0);
        assert_eq!(rot, 0);
        assert!((best - 8.0).abs() < 1e-9);
        assert!(kept);
    }

    #[test]
    fn test_rotation_searches_other_axis() {
        // HV/SELV separated along local Y only; barrier axis X must pick a
        // 90-degree rotation to bring the Y separation onto the barrier.
        let hv = vec![(0.0, 0.0, 1.0, 1.0, SHAPE_CIRCLE, 0.25)];
        let selv = vec![(0.0, 10.0, 1.0, 1.0, SHAPE_CIRCLE, 0.25)];
        let (rot, best, _) = best_rotation_for_barrier(&hv, &selv, 0);
        assert!(rot == 1 || rot == 3, "expected a 90-degree rotation, got {rot}");
        assert!((best - 9.0).abs() < 1e-9); // 10 - 0.5 - 0.5
    }
}
