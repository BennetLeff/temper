// Wave 4: `placer/cp_sat/fixed_copper.py`'s pad-rotation / half-extent /
// item-geometry / exact-clearance-oracle kernels (issue #523, R24).
//
// Python reference: `temper_placer/placer/cp_sat/fixed_copper.py`, pinned
// verbatim at `packages/temper-placer/tests/placer/cp_sat/_fixed_copper_py_oracle.py`
// (commit 1dd54e3f2cc58e9dd6cbc5b3c54d68b4d0374ae9).
//
// Scope (per `docs/evidence/2026-08-06-never-port-triage.md` section 4's
// carve-out of this file from the `placer/cp_sat/**` whole-subtree
// JUSTIFIED-KEEP): the pad-rotation / half-extent / layer-resolution /
// item-geometry / exact-clearance-oracle math below has nothing to do with
// the ortools CP-SAT boundary and is ported here. `encode_fixed_copper_constraints`,
// `_pad_rotation_tables_with` and `_add_no_overlap` build `ortools.CpModel`
// `BoolVar`/`Add`/`AddElement`/`OnlyEnforceIf` calls directly -- that IS the
// solver boundary itself -- and stay in Python, calling into the kernels
// below for every piece of arithmetic they need (`_rotated`, `_mm_to_units`).
//
// Not ported: the zone-kind `exact_clearance_mm` branch's shapely
// `poly.buffer(0)` self-intersection repair. `zone_exact_clearance` below
// assumes a simple (non-self-intersecting) polygon, which is what
// `parse_kicad_pcb` produces and what the 96-zone production board and this
// module's own BMC test corpus (`test_fixed_copper.py`) exercise -- the
// module docstring itself measures every production zone as convex. An
// actually self-intersecting zone polygon would need shapely's GEOS-backed
// repair to match exactly, which is out of scope for a from-scratch Rust
// port (see the parallel GEOS-convex-hull entanglement the triage records
// for `router_v6/_convex_hull_from_positions`).
//
// Numerical contract (see module docstring in the oracle for the geometry
// this mirrors):
// * `round(x)` (no ndigits) -> CPython round-half-to-even, raising on
//   non-finite input exactly like `int()` does (`py_round_to_i64` below).
// * `math.ceil` -> raises on non-finite (`crate::congestion::ceil_to_int`).
// * `%` (float modulo, `pad_rotation_deg % 180.0`) -> Python's sign-of-
//   divisor convention, NOT Rust's `%` (sign-of-dividend).
// * `math.cos`/`math.sin` -> the host CPython process's own libm
//   (`crate::pad_geometry::math_cos_sin`).
// * `math.hypot` -> CPython's compensated `vector_norm`
//   (`crate::pad_geometry::py_hypot`).
// * Builtin `min`/`max` -> `crate::creepage_check::{py_min, py_max}` for the
//   2-arg forms; `cpython_min_n`/`cpython_max_n` below for the >2-arg
//   builtin-`min`/`max` call sites (`_point_rect_distance`'s 4-way min,
//   `_rect_segment_distance`'s corner min).
// * `_point_segment_distance` in THIS file now DELEGATES to
//   `creepage_check::point_to_segment_distance` (2026-08-13 epsilon
//   consolidation, see
//   `docs/evidence/2026-08-13-point-to-segment-distance-epsilon-consolidation.md`).
//   Its own degenerate check (`dx == 0.0 and dy == 0.0`, exact equality) was
//   measured bit-identical to the canonical `denom == 0.0 or
//   not denom.is_finite()` contract on every finite input covered by this
//   file's own pinned oracle (`_fixed_copper_py_oracle.py`) and on a
//   6000+-case board-scale + near-degenerate (1e-15mm..1mm segment length)
//   corpus swept for this consolidation -- the two contracts differ only
//   on non-finite/overflowing denom, which this file's oracle never
//   exercises and real board geometry (mm-scale, 20-254 range) cannot
//   reach. The canonical contract is additionally correct where this
//   file's own convention was not: it stays finite instead of
//   propagating NaN/Inf when a coordinate overflows. This is NOT the same
//   situation as `drc_constraints_geometry.rs`'s or `geometry_kernels.rs`'s
//   own epsilon-threshold conventions (`seg_len_sq < 1e-10` /
//   `len2 < 1e-12`), which genuinely disagree with the canonical contract
//   on ~20-24% of near-degenerate segments (measured) and remain a
//   documented, deliberate KEEP -- see the evidence doc above.

use crate::congestion::ceil_to_int;
use crate::creepage_check::{py_max, py_min};
use crate::pad_geometry::{math_cos_sin, py_hypot};

#[cfg(feature = "python")]
use pyo3::exceptions::{PyOverflowError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyList, PyTuple};

/// An axis-aligned rectangle (x0, y0, x1, y1), mm.
type Rect = (f64, f64, f64, f64);
/// `other_pad_item_geom`'s (exact rect, encoded rect, slack_mm).
type PadItemGeom = (Rect, Rect, f64);

/// Four copper layers of the stackup, canonical order (matches the Python
/// `COPPER_LAYERS` frozenset's members; order is irrelevant to the Python
/// side, which always wraps the result in `frozenset(...)`).
const COPPER_LAYER_NAMES: [&str; 4] = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"];

// The solver is always built with units_per_mm=100 -- 1 model unit == 0.01mm.
const UNITS_PER_MM: f64 = 100.0;
// Diagonal-edge half-planes are computed at 100x model resolution
// (0.0001 mm) -- see `_convex_polygon_edges`'s module docstring.
const FINE_UNITS_PER_MM: f64 = 10_000.0;
const FINE_TO_MODEL: i64 = 100; // 10_000 / 100
// Minimum encoded half-extent, mm (1 model unit).
const MIN_HALF_MM: f64 = 0.01;

// ---------------------------------------------------------------------------
// Host-math / CPython-semantics helpers local to this kernel
// ---------------------------------------------------------------------------

/// CPython `round(x)` (no ndigits) converted to `int`: round-half-to-even,
/// raising exactly as `PyLong_FromDouble` does on a non-finite input.
fn py_round_to_i64(x: f64) -> Result<i64, RoundError> {
    if x.is_nan() {
        return Err(RoundError::Nan);
    }
    if x.is_infinite() {
        return Err(RoundError::Infinite);
    }
    Ok(crate::host_math::py_round(x) as i64)
}

pub(crate) enum RoundError {
    Nan,
    Infinite,
}

#[cfg(feature = "python")]
impl From<RoundError> for PyErr {
    fn from(e: RoundError) -> PyErr {
        match e {
            RoundError::Nan => PyValueError::new_err("cannot convert float NaN to integer"),
            RoundError::Infinite => {
                PyOverflowError::new_err("cannot convert float infinity to integer")
            }
        }
    }
}

/// `_mm_to_units`: round-half-even on `mm * 100`, then force the result to
/// even parity (`if raw % 2: raw -= 1`). Rust's `%` differs from Python's in
/// sign for negative operands, but only the ZERO-ness is tested here, which
/// both languages agree on.
pub(crate) fn mm_to_units(mm: f64) -> Result<i64, RoundError> {
    let mut raw = py_round_to_i64(mm * UNITS_PER_MM)?;
    if raw % 2 != 0 {
        raw -= 1;
    }
    Ok(raw)
}

/// `_mm_to_fine_units`: round-half-even on `mm * 10_000`, no parity trim.
pub(crate) fn mm_to_fine_units(mm: f64) -> Result<i64, RoundError> {
    py_round_to_i64(mm * FINE_UNITS_PER_MM)
}

/// Python's `%` for floats: `fmod`-based, result takes the sign of the
/// divisor (unless exactly zero). `pad_rotation_deg % 180.0` is always
/// non-negative here because the divisor is positive, but this is written
/// generally so it cannot silently regress if that changes.
fn py_float_mod(a: f64, b: f64) -> f64 {
    let r = a % b; // Rust's `%` is `fmod` (sign of dividend)
    if r != 0.0 && (r < 0.0) != (b < 0.0) {
        r + b
    } else {
        r
    }
}

/// CPython builtin `min(...)` over N args: `acc = vals[0]; for x in
/// vals[1..] { if x < acc { acc = x } }` -- keeps the FIRST minimum on a
/// tie and the FIRST NaN (a later NaN compares false against anything and
/// is dropped).
fn cpython_min_n(vals: &[f64]) -> f64 {
    let mut acc = vals[0];
    for &x in &vals[1..] {
        if x < acc {
            acc = x;
        }
    }
    acc
}

// ---------------------------------------------------------------------------
// Pad geometry: rotation, half-extent, layer resolution
// ---------------------------------------------------------------------------

/// `_pin_copper_layers`: through-hole (`is_pth` or `layer == "all"`) pads
/// occupy all four copper layers; SMD pads occupy their one declared layer
/// if it is a copper layer, else none.
pub(crate) fn pin_copper_layers(is_pth: bool, layer: Option<&str>) -> Vec<&'static str> {
    if is_pth || layer == Some("all") {
        return COPPER_LAYER_NAMES.to_vec();
    }
    match layer {
        Some(l) => COPPER_LAYER_NAMES
            .iter()
            .copied()
            .filter(|&c| c == l)
            .collect(),
        None => Vec::new(),
    }
}

/// `_local_pad_half`: axis-aligned local half-extents, accounting for the
/// pad's own intrinsic rotation via the AABB of the rotated rectangle.
pub(crate) fn local_pad_half(width: f64, height: f64, pad_rotation_deg: f64) -> (f64, f64) {
    let hw = width / 2.0;
    let hh = height / 2.0;
    let phi = py_float_mod(pad_rotation_deg, 180.0) * (std::f64::consts::PI / 180.0);
    if phi == 0.0 {
        return (hw, hh);
    }
    let (raw_c, raw_s) = math_cos_sin(phi);
    let (c, s) = (raw_c.abs(), raw_s.abs());
    (hw * c + hh * s, hw * s + hh * c)
}

/// `_rotated`: the exact hand-unrolled closed form of the model's four
/// quadrant rotations. Returns (offset_x, offset_y, half_w, half_h).
pub(crate) fn rotated(lx: f64, ly: f64, hw: f64, hh: f64, rot_idx: i64) -> Rect {
    match rot_idx.rem_euclid(4) {
        0 => (lx, ly, hw, hh),
        1 => (ly, -lx, hh, hw),
        2 => (-lx, -ly, hw, hh),
        _ => (-ly, lx, hh, hw),
    }
}

/// `pad_world_rect`: the pad's world axis-aligned rectangle (x0,y0,x1,y1).
pub(crate) fn pad_world_rect(
    lx: f64,
    ly: f64,
    hw: f64,
    hh: f64,
    rot_idx: i64,
    cx: f64,
    cy: f64,
) -> Rect {
    let (ox, oy, hwx, hwy) = rotated(lx, ly, hw, hh, rot_idx);
    (cx + ox - hwx, cy + oy - hwy, cx + ox + hwx, cy + oy + hwy)
}

/// `_clamped_half_mm`: the half-extent the CP-SAT encoder actually encodes
/// (clamped to a minimum of 0.01 mm so the interval stays non-degenerate).
pub(crate) fn clamped_half_mm(half_mm: f64) -> f64 {
    py_max(MIN_HALF_MM, half_mm)
}

/// `encoded_pad_world_rect`: identical to `pad_world_rect` except the
/// half-extents are clamped before the world transform.
pub(crate) fn encoded_pad_world_rect(
    lx: f64,
    ly: f64,
    hw: f64,
    hh: f64,
    rot_idx: i64,
    cx: f64,
    cy: f64,
) -> Rect {
    let (ox, oy, hwx, hwy) = rotated(lx, ly, hw, hh, rot_idx);
    let hwx = clamped_half_mm(hwx);
    let hwy = clamped_half_mm(hwy);
    (cx + ox - hwx, cy + oy - hwy, cx + ox + hwx, cy + oy + hwy)
}

// ---------------------------------------------------------------------------
// Point/segment/rect geometry -- delegates to the crate's canonical kernel
// (see module header's "epsilon consolidation" note)
// ---------------------------------------------------------------------------

/// `_point_segment_distance`: delegates to
/// `creepage_check::point_to_segment_distance`, the crate's canonical
/// point-to-segment kernel. Measured bit-identical to this file's own
/// former `dx == 0.0 and dy == 0.0` exact-equality convention on every
/// finite input this file's pinned oracle exercises (see module header).
pub(crate) fn point_segment_distance(
    px: f64,
    py_: f64,
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
) -> f64 {
    crate::creepage_check::point_to_segment_distance(px, py_, ax, ay, bx, by)
}

/// `_point_rect_distance`: 0 if the point is inside/on the rect, else the
/// min over the 4 edges of `point_segment_distance` (CPython 4-arg `min`).
pub(crate) fn point_rect_distance(px: f64, py_: f64, rect: Rect) -> f64 {
    let (x0, y0, x1, y1) = rect;
    if x0 <= px && px <= x1 && y0 <= py_ && py_ <= y1 {
        return 0.0;
    }
    let d0 = point_segment_distance(px, py_, x0, y0, x1, y0);
    let d1 = point_segment_distance(px, py_, x1, y0, x1, y1);
    let d2 = point_segment_distance(px, py_, x1, y1, x0, y1);
    let d3 = point_segment_distance(px, py_, x0, y1, x0, y0);
    cpython_min_n(&[d0, d1, d2, d3])
}

fn ccw(px: f64, py_: f64, qx: f64, qy: f64, rx: f64, ry: f64) -> f64 {
    (qx - px) * (ry - py_) - (qy - py_) * (rx - px)
}

/// `_segments_intersect`: proper or improper intersection of a0-a1, b0-b1.
pub(crate) fn segments_intersect(
    a0: (f64, f64),
    a1: (f64, f64),
    b0: (f64, f64),
    b1: (f64, f64),
) -> bool {
    let (ax0, ay0) = a0;
    let (ax1, ay1) = a1;
    let (bx0, by0) = b0;
    let (bx1, by1) = b1;
    let d1 = ccw(bx0, by0, bx1, by1, ax0, ay0);
    let d2 = ccw(bx0, by0, bx1, by1, ax1, ay1);
    let d3 = ccw(ax0, ay0, ax1, ay1, bx0, by0);
    let d4 = ccw(ax0, ay0, ax1, ay1, bx1, by1);
    if ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
        && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
    {
        return true;
    }
    // Builtin `min`/`max` (`py_min`/`py_max`), matching the reference's own
    // `min(bx0, bx1) <= ax0 <= max(bx0, bx1)` -- see this file's numerical
    // contract note on NaN/signed-zero tie-breaking.
    let on_a = d1 == 0.0
        && py_min(bx0, bx1) <= ax0
        && ax0 <= py_max(bx0, bx1)
        && py_min(by0, by1) <= ay0
        && ay0 <= py_max(by0, by1);
    let on_a_end = d2 == 0.0
        && py_min(bx0, bx1) <= ax1
        && ax1 <= py_max(bx0, bx1)
        && py_min(by0, by1) <= ay1
        && ay1 <= py_max(by0, by1);
    let on_b = d3 == 0.0
        && py_min(ax0, ax1) <= bx0
        && bx0 <= py_max(ax0, ax1)
        && py_min(ay0, ay1) <= by0
        && by0 <= py_max(ay0, ay1);
    let on_b_end = d4 == 0.0
        && py_min(ax0, ax1) <= bx1
        && bx1 <= py_max(ax0, ax1)
        && py_min(ay0, ay1) <= by1
        && by1 <= py_max(ay0, ay1);
    on_a || on_a_end || on_b || on_b_end
}

/// `_rect_segment_distance`: 0 if the rect and segment intersect (checked
/// via the 4 rect edges, in the reference's exact order); else the min over
/// (4 corner-to-segment distances, 2 endpoint-to-rect distances), floored
/// at 0.0.
pub(crate) fn rect_segment_distance(
    rect: Rect,
    a: (f64, f64),
    b: (f64, f64),
) -> f64 {
    let (x0, y0, x1, y1) = rect;
    if segments_intersect(a, b, (x0, y0), (x1, y0)) || segments_intersect(a, b, (x1, y0), (x1, y1))
    {
        return 0.0;
    }
    if segments_intersect(a, b, (x1, y1), (x0, y1)) || segments_intersect(a, b, (x0, y1), (x0, y0))
    {
        return 0.0;
    }
    let corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)];
    let corner_dists: Vec<f64> = corners
        .iter()
        .map(|&(cx, cy)| point_segment_distance(cx, cy, a.0, a.1, b.0, b.1))
        .collect();
    let mut d = cpython_min_n(&corner_dists);
    d = cpython_min_n(&[d, point_rect_distance(a.0, a.1, rect), point_rect_distance(b.0, b.1, rect)]);
    py_max(0.0, d)
}

/// `_rect_rect_gap`: 0 if the rects overlap/touch, else the exact
/// Euclidean edge-to-edge gap.
pub(crate) fn rect_rect_gap(ra: Rect, rb: Rect) -> f64 {
    if ra.0 <= rb.2 && rb.0 <= ra.2 && ra.1 <= rb.3 && rb.1 <= ra.3 {
        return 0.0;
    }
    let dx = py_max(0.0, py_max(rb.0 - ra.2, ra.0 - rb.2));
    let dy = py_max(0.0, py_max(rb.1 - ra.3, ra.1 - rb.3));
    py_hypot(dx, dy)
}

/// Point-in-polygon (ray casting, PNPOLY). Only reached after
/// `zone_exact_clearance` has ruled out any boundary touch, so the exact
/// tie-breaking convention at a vertex/edge does not matter for that call
/// site's correctness.
fn point_in_polygon(px: f64, py_: f64, polygon: &[(f64, f64)]) -> bool {
    let n = polygon.len();
    let mut inside = false;
    let mut j = n - 1;
    for i in 0..n {
        let (xi, yi) = polygon[i];
        let (xj, yj) = polygon[j];
        if (yi > py_) != (yj > py_) && px < (xj - xi) * (py_ - yi) / (yj - yi) + xi {
            inside = !inside;
        }
        j = i;
    }
    inside
}

fn point_in_rect_inclusive(px: f64, py_: f64, rect: Rect) -> bool {
    rect.0 <= px && px <= rect.2 && rect.1 <= py_ && py_ <= rect.3
}

/// The zone branch of `exact_clearance_mm`: shapely's
/// `prep(poly).intersects(box)` -> 0.0, else `box.distance(poly)`, for a
/// SIMPLE (non-self-intersecting) polygon -- see module header for the one
/// documented gap (the `poly.buffer(0)` self-intersection repair).
///
/// If any polygon edge touches/crosses the rect boundary (or is nested
/// inside it), the shapes intersect (distance 0). Otherwise, by a Jordan-
/// curve argument, the rect is either fully inside the polygon, fully
/// inside no part of it, or fully outside -- so a single interior-point
/// test on each side after the edge loop finds it decides containment, and
/// the true separation (when genuinely disjoint) is the min distance from
/// the (filled) rect to any polygon edge, which is what the edge loop
/// already computed.
pub(crate) fn zone_exact_clearance(pad_rect: Rect, polygon: &[(f64, f64)]) -> f64 {
    let n = polygon.len();
    if n == 0 {
        return f64::INFINITY;
    }
    let mut touched = false;
    let mut min_d = f64::INFINITY;
    for i in 0..n {
        let p0 = polygon[i];
        let p1 = polygon[(i + 1) % n];
        let d = rect_segment_distance(pad_rect, p0, p1);
        if d == 0.0 {
            touched = true;
        }
        if d < min_d {
            min_d = d;
        }
    }
    if touched {
        return 0.0;
    }
    if point_in_rect_inclusive(polygon[0].0, polygon[0].1, pad_rect) {
        return 0.0;
    }
    let cx = (pad_rect.0 + pad_rect.2) / 2.0;
    let cy = (pad_rect.1 + pad_rect.3) / 2.0;
    if point_in_polygon(cx, cy, polygon) {
        return 0.0;
    }
    min_d
}

// ---------------------------------------------------------------------------
// segment_slack_mm
// ---------------------------------------------------------------------------

/// `segment_slack_mm`: exact worst-case conservatism of a segment's bbox
/// encoding -- max over the 4 box corners of
/// `dist(corner, segment) - width/2 - margin`, floored at 0.0.
pub(crate) fn segment_slack_mm(p0: (f64, f64), p1: (f64, f64), width: f64, margin: f64) -> f64 {
    // Builtin `min`/`max`, not `f64::min`/`f64::max` (differ on NaN and on
    // signed-zero ties -- see `py_min`/`py_max`'s own doc comments).
    let box_ = (
        py_min(p0.0, p1.0) - width / 2.0 - margin,
        py_min(p0.1, p1.1) - width / 2.0 - margin,
        py_max(p0.0, p1.0) + width / 2.0 + margin,
        py_max(p0.1, p1.1) + width / 2.0 + margin,
    );
    let corners = [
        (box_.0, box_.1),
        (box_.2, box_.1),
        (box_.2, box_.3),
        (box_.0, box_.3),
    ];
    let mut worst = 0.0f64;
    for c in corners {
        let excess = point_segment_distance(c.0, c.1, p0.0, p0.1, p1.0, p1.1) - width / 2.0 - margin;
        if excess > worst {
            worst = excess;
        }
    }
    worst
}

// ---------------------------------------------------------------------------
// Item geometry: segment / via / zone-rect / other-pad
// ---------------------------------------------------------------------------

const GRID_HEADROOM_MM: f64 = 0.02;

/// `_segment_item`'s rect + slack (net/layers/label/exact dict assembly
/// stays in the Python shim).
pub(crate) fn segment_item_geom(
    start: (f64, f64),
    end: (f64, f64),
    width: f64,
    margin: f64,
) -> (Rect, f64) {
    let pad = width / 2.0 + margin + GRID_HEADROOM_MM;
    let x0 = py_min(start.0, end.0) - pad;
    let x1 = py_max(start.0, end.0) + pad;
    let y0 = py_min(start.1, end.1) - pad;
    let y1 = py_max(start.1, end.1) + pad;
    let slack = segment_slack_mm(start, end, width, margin + GRID_HEADROOM_MM);
    ((x0, y0, x1, y1), slack)
}

/// `_via_item`'s rect + slack.
pub(crate) fn via_item_geom(pos: (f64, f64), diameter: f64, margin: f64) -> (Rect, f64) {
    let pad = diameter / 2.0 + margin + GRID_HEADROOM_MM;
    let rect = (pos.0 - pad, pos.1 - pad, pos.0 + pad, pos.1 + pad);
    let slack = (2.0f64.sqrt() - 1.0) * pad;
    (rect, slack)
}

/// CPython builtin `max(...)` over N args -- the `cpython_min_n` mirror.
fn cpython_max_n(vals: &[f64]) -> f64 {
    let mut acc = vals[0];
    for &x in &vals[1..] {
        if x > acc {
            acc = x;
        }
    }
    acc
}

/// `_zone_item`'s rect (slack is always `inf`, computed in the Python
/// shim as before -- not a numeric kernel).
///
/// Operation order matters: the reference is `min(xs) - margin -
/// _GRID_HEADROOM_MM` (two LEFT-TO-RIGHT subtractions) and `max(xs) +
/// margin + _GRID_HEADROOM_MM` (two left-to-right additions), NOT
/// `min(xs) - (margin + headroom)` -- the two association orders can differ
/// in the last ulp.
pub(crate) fn zone_item_rect(polygon: &[(f64, f64)], margin: f64) -> Rect {
    let xs: Vec<f64> = polygon.iter().map(|p| p.0).collect();
    let ys: Vec<f64> = polygon.iter().map(|p| p.1).collect();
    (
        cpython_min_n(&xs) - margin - GRID_HEADROOM_MM,
        cpython_min_n(&ys) - margin - GRID_HEADROOM_MM,
        cpython_max_n(&xs) + margin + GRID_HEADROOM_MM,
        cpython_max_n(&ys) + margin + GRID_HEADROOM_MM,
    )
}

/// `_other_component_pad_item`'s exact rect, encoded (margin-expanded)
/// rect, and slack.
#[allow(clippy::too_many_arguments)]
pub(crate) fn other_pad_item_geom(
    lx: f64,
    ly: f64,
    hw: f64,
    hh: f64,
    rot_idx: i64,
    cx: f64,
    cy: f64,
    margin: f64,
) -> PadItemGeom {
    let (ox, oy, hwx, hwy) = rotated(lx, ly, hw, hh, rot_idx);
    let rect = (cx + ox - hwx, cy + oy - hwy, cx + ox + hwx, cy + oy + hwy);
    let m = margin + GRID_HEADROOM_MM;
    let encoded = (rect.0 - m, rect.1 - m, rect.2 + m, rect.3 + m);
    let slack = (2.0f64.sqrt() - 1.0) * m;
    (rect, encoded, slack)
}

// ---------------------------------------------------------------------------
// Convex zone edges (#567 rectilinear + #651 general convex)
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
pub(crate) enum Edge {
    /// `("x"|"y", coord, sign)`. `is_x`: true=x axis, false=y axis.
    Axis { is_x: bool, coord: f64, sign: i64 },
    /// `("n", a, b, r)`.
    Diag { a: i64, b: i64, r: i64 },
}

fn cross(ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    ax * by - ay * bx
}

/// Signed area (shoelace, x2) and convexity check shared by both edge
/// builders. Returns `None` for a degenerate (<3 vertices, zero-area, or
/// non-convex) polygon.
fn polygon_winding_if_convex(polygon: &[(f64, f64)]) -> Option<bool> {
    let n = polygon.len();
    if n < 3 {
        return None;
    }
    let mut area2 = 0.0;
    for i in 0..n {
        let (x0, y0) = polygon[i];
        let (x1, y1) = polygon[(i + 1) % n];
        area2 += x0 * y1 - x1 * y0;
    }
    if area2.abs() < 1e-9 {
        return None;
    }
    let cw = area2 < 0.0;
    for i in 0..n {
        let (x0, y0) = polygon[i];
        let (x1, y1) = polygon[(i + 1) % n];
        for &(px, py_) in polygon {
            let mut c = cross(x1 - x0, y1 - y0, px - x0, py_ - y0);
            if cw {
                c = -c;
            }
            if c < -1e-9 {
                return None;
            }
        }
    }
    Some(cw)
}

/// `_rectilinear_convex_edges` (#567): axis-aligned convex polygons only;
/// `None` for anything else (diagonal edge, non-convex, degenerate).
pub(crate) fn rectilinear_convex_edges(polygon: &[(f64, f64)], margin: f64) -> Option<Vec<Edge>> {
    let cw = polygon_winding_if_convex(polygon)?;
    let n = polygon.len();
    let mut edges = Vec::with_capacity(n);
    for i in 0..n {
        let (x0, y0) = polygon[i];
        let (x1, y1) = polygon[(i + 1) % n];
        if (x0 - x1).abs() < 1e-9 {
            let upward = y1 > y0;
            let interior_minus = upward != cw;
            if interior_minus {
                edges.push(Edge::Axis { is_x: true, coord: x0 + margin, sign: 1 });
            } else {
                edges.push(Edge::Axis { is_x: true, coord: x0 - margin, sign: -1 });
            }
        } else if (y0 - y1).abs() < 1e-9 {
            let rightward = x1 > x0;
            let interior_plus = rightward != cw;
            if interior_plus {
                edges.push(Edge::Axis { is_x: false, coord: y0 - margin, sign: -1 });
            } else {
                edges.push(Edge::Axis { is_x: false, coord: y0 + margin, sign: 1 });
            }
        } else {
            return None; // diagonal edge -> bbox fallback
        }
    }
    Some(edges)
}

fn is_axis_aligned(p0: (f64, f64), p1: (f64, f64)) -> bool {
    (p0.0 - p1.0).abs() < 1e-9 || (p0.1 - p1.1).abs() < 1e-9
}

/// `_convex_polygon_edges` (#651): general convex polygons, axis-aligned or
/// diagonal edges. Delegates to `rectilinear_convex_edges` for a purely
/// rectilinear polygon (identical object shape to the #567 path), exactly
/// as the Python reference does.
pub(crate) fn convex_polygon_edges(
    polygon: &[(f64, f64)],
    margin_mm: f64,
) -> Result<Option<Vec<Edge>>, RoundError> {
    let cw = match polygon_winding_if_convex(polygon) {
        Some(cw) => cw,
        None => return Ok(None),
    };
    let n = polygon.len();
    let ring_edges: Vec<((f64, f64), (f64, f64))> =
        (0..n).map(|i| (polygon[i], polygon[(i + 1) % n])).collect();
    if ring_edges.iter().all(|&(p0, p1)| is_axis_aligned(p0, p1)) {
        return Ok(rectilinear_convex_edges(polygon, margin_mm));
    }

    let normalized: Vec<(f64, f64)> = if cw {
        polygon.iter().rev().copied().collect()
    } else {
        polygon.to_vec()
    };
    let n = normalized.len();
    let margin_shift_fine = (margin_mm + GRID_HEADROOM_MM) * FINE_UNITS_PER_MM;
    let mut edges = Vec::with_capacity(n);
    for i in 0..n {
        let (x0, y0) = normalized[i];
        let (x1, y1) = normalized[(i + 1) % n];
        if (x0 - x1).abs() < 1e-9 {
            let upward = y1 > y0;
            if upward {
                edges.push(Edge::Axis { is_x: true, coord: x0 + margin_mm, sign: 1 });
            } else {
                edges.push(Edge::Axis { is_x: true, coord: x0 - margin_mm, sign: -1 });
            }
        } else if (y0 - y1).abs() < 1e-9 {
            let rightward = x1 > x0;
            if rightward {
                edges.push(Edge::Axis { is_x: false, coord: y0 - margin_mm, sign: -1 });
            } else {
                edges.push(Edge::Axis { is_x: false, coord: y0 + margin_mm, sign: 1 });
            }
        } else {
            let x0f = mm_to_fine_units(x0)?;
            let y0f = mm_to_fine_units(y0)?;
            let x1f = mm_to_fine_units(x1)?;
            let y1f = mm_to_fine_units(y1)?;
            let dxf = x1f - x0f;
            let dyf = y1f - y0f;
            if dxf == 0 && dyf == 0 {
                continue;
            }
            let a = dyf;
            let b = -dxf;
            let length_fine = py_hypot(dxf as f64, dyf as f64);
            let d0 = (a as f64) * (x0f as f64) + (b as f64) * (y0f as f64);
            let r = ceil_to_int(d0 + margin_shift_fine * length_fine)
                .map_err(|_| RoundError::Infinite)?;
            edges.push(Edge::Diag { a: a * FINE_TO_MODEL, b: b * FINE_TO_MODEL, r });
        }
    }
    if edges.is_empty() {
        Ok(None)
    } else {
        Ok(Some(edges))
    }
}

// ---------------------------------------------------------------------------
// exact_clearance_mm dispatch
// ---------------------------------------------------------------------------

pub(crate) fn exact_clearance_segment(
    pad_rect: Rect,
    p0: (f64, f64),
    p1: (f64, f64),
    width: f64,
) -> f64 {
    py_max(0.0, rect_segment_distance(pad_rect, p0, p1) - width / 2.0)
}

pub(crate) fn exact_clearance_via(
    pad_rect: Rect,
    center: (f64, f64),
    diameter: f64,
) -> f64 {
    py_max(0.0, point_rect_distance(center.0, center.1, pad_rect) - diameter / 2.0)
}

pub(crate) fn exact_clearance_pad(
    pad_rect: Rect,
    other_rect: Rect,
) -> f64 {
    rect_rect_gap(pad_rect, other_rect)
}

// ---------------------------------------------------------------------------
// pyo3 bindings
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_mm_to_units_py(mm: f64) -> PyResult<i64> {
    Ok(mm_to_units(mm)?)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_mm_to_fine_units_py(mm: f64) -> PyResult<i64> {
    Ok(mm_to_fine_units(mm)?)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_pin_copper_layers_py(is_pth: bool, layer: Option<String>) -> Vec<String> {
    pin_copper_layers(is_pth, layer.as_deref())
        .into_iter()
        .map(String::from)
        .collect()
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_local_pad_half_py(width: f64, height: f64, pad_rotation_deg: f64) -> (f64, f64) {
    local_pad_half(width, height, pad_rotation_deg)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_rotated_py(lx: f64, ly: f64, hw: f64, hh: f64, rot_idx: i64) -> Rect {
    rotated(lx, ly, hw, hh, rot_idx)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn fixed_copper_pad_world_rect_py(
    lx: f64,
    ly: f64,
    hw: f64,
    hh: f64,
    rot_idx: i64,
    cx: f64,
    cy: f64,
) -> Rect {
    pad_world_rect(lx, ly, hw, hh, rot_idx, cx, cy)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn fixed_copper_encoded_pad_world_rect_py(
    lx: f64,
    ly: f64,
    hw: f64,
    hh: f64,
    rot_idx: i64,
    cx: f64,
    cy: f64,
) -> Rect {
    encoded_pad_world_rect(lx, ly, hw, hh, rot_idx, cx, cy)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_segment_slack_mm_py(
    p0: (f64, f64),
    p1: (f64, f64),
    width: f64,
    margin: f64,
) -> f64 {
    segment_slack_mm(p0, p1, width, margin)
}

#[cfg(feature = "python")]
fn edge_to_pyobject<'py>(py: Python<'py>, e: &Edge) -> PyResult<Bound<'py, PyAny>> {
    match *e {
        Edge::Axis { is_x, coord, sign } => {
            let axis = if is_x { "x" } else { "y" };
            Ok(PyTuple::new(py, [axis.into_pyobject(py)?.into_any(), coord.into_pyobject(py)?.into_any(), sign.into_pyobject(py)?.into_any()])?.into_any())
        }
        Edge::Diag { a, b, r } => Ok(PyTuple::new(
            py,
            ["n".into_pyobject(py)?.into_any(), a.into_pyobject(py)?.into_any(), b.into_pyobject(py)?.into_any(), r.into_pyobject(py)?.into_any()],
        )?.into_any()),
    }
}

#[cfg(feature = "python")]
fn edges_to_pyobject<'py>(py: Python<'py>, edges: &[Edge]) -> PyResult<Bound<'py, PyAny>> {
    let list = PyList::empty(py);
    for e in edges {
        list.append(edge_to_pyobject(py, e)?)?;
    }
    Ok(PyTuple::new(py, list.iter())?.into_any())
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_rectilinear_convex_edges_py<'py>(
    py: Python<'py>,
    polygon: Vec<(f64, f64)>,
    margin: f64,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    match rectilinear_convex_edges(&polygon, margin) {
        None => Ok(None),
        Some(edges) => Ok(Some(edges_to_pyobject(py, &edges)?)),
    }
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_convex_polygon_edges_py<'py>(
    py: Python<'py>,
    polygon: Vec<(f64, f64)>,
    margin_mm: f64,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    match convex_polygon_edges(&polygon, margin_mm)? {
        None => Ok(None),
        Some(edges) => Ok(Some(edges_to_pyobject(py, &edges)?)),
    }
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_segment_item_geom_py(
    start: (f64, f64),
    end: (f64, f64),
    width: f64,
    margin: f64,
) -> (Rect, f64) {
    segment_item_geom(start, end, width, margin)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_via_item_geom_py(
    pos: (f64, f64),
    diameter: f64,
    margin: f64,
) -> (Rect, f64) {
    via_item_geom(pos, diameter, margin)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_zone_item_rect_py(polygon: Vec<(f64, f64)>, margin: f64) -> Rect {
    zone_item_rect(&polygon, margin)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn fixed_copper_other_pad_item_geom_py(
    lx: f64,
    ly: f64,
    hw: f64,
    hh: f64,
    rot_idx: i64,
    cx: f64,
    cy: f64,
    margin: f64,
) -> PadItemGeom {
    other_pad_item_geom(lx, ly, hw, hh, rot_idx, cx, cy, margin)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_point_rect_distance_py(p: (f64, f64), rect: Rect) -> f64 {
    point_rect_distance(p.0, p.1, rect)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_point_segment_distance_py(p: (f64, f64), a: (f64, f64), b: (f64, f64)) -> f64 {
    point_segment_distance(p.0, p.1, a.0, a.1, b.0, b.1)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_segments_intersect_py(
    a0: (f64, f64),
    a1: (f64, f64),
    b0: (f64, f64),
    b1: (f64, f64),
) -> bool {
    segments_intersect(a0, a1, b0, b1)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_rect_segment_distance_py(
    rect: Rect,
    a: (f64, f64),
    b: (f64, f64),
) -> f64 {
    rect_segment_distance(rect, a, b)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fixed_copper_rect_rect_gap_py(ra: Rect, rb: Rect) -> f64 {
    rect_rect_gap(ra, rb)
}

/// `exact_clearance_mm` dispatch. Exactly one of the kind-specific
/// argument groups is populated per `kind`; the Python shim (which reads
/// `item.kind`/`item.exact`) is responsible for that, exactly mirroring
/// the reference's `if item.kind == ...` dispatch.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (pad_rect, kind, p0=None, p1=None, width=None, center=None, diameter=None, other_rect=None, polygon=None))]
#[allow(clippy::too_many_arguments)]
pub fn fixed_copper_exact_clearance_mm_py(
    pad_rect: Rect,
    kind: &str,
    p0: Option<(f64, f64)>,
    p1: Option<(f64, f64)>,
    width: Option<f64>,
    center: Option<(f64, f64)>,
    diameter: Option<f64>,
    other_rect: Option<Rect>,
    polygon: Option<Vec<(f64, f64)>>,
) -> PyResult<f64> {
    match kind {
        "segment" => {
            let (p0, p1, width) = (
                p0.ok_or_else(|| PyValueError::new_err("segment kind requires p0"))?,
                p1.ok_or_else(|| PyValueError::new_err("segment kind requires p1"))?,
                width.ok_or_else(|| PyValueError::new_err("segment kind requires width"))?,
            );
            Ok(exact_clearance_segment(pad_rect, p0, p1, width))
        }
        "via" => {
            let (center, diameter) = (
                center.ok_or_else(|| PyValueError::new_err("via kind requires center"))?,
                diameter.ok_or_else(|| PyValueError::new_err("via kind requires diameter"))?,
            );
            Ok(exact_clearance_via(pad_rect, center, diameter))
        }
        "pad" => {
            let other_rect =
                other_rect.ok_or_else(|| PyValueError::new_err("pad kind requires other_rect"))?;
            Ok(exact_clearance_pad(pad_rect, other_rect))
        }
        "zone" => {
            let polygon = polygon.ok_or_else(|| PyValueError::new_err("zone kind requires polygon"))?;
            Ok(zone_exact_clearance(pad_rect, &polygon))
        }
        other => Err(PyValueError::new_err(format!(
            "unknown fixed-copper item kind {other:?}"
        ))),
    }
}

pub fn register(m: &Bound<'_, pyo3::types::PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fixed_copper_mm_to_units_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_mm_to_fine_units_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_pin_copper_layers_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_local_pad_half_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_rotated_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_pad_world_rect_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_encoded_pad_world_rect_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_segment_slack_mm_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_rectilinear_convex_edges_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_convex_polygon_edges_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_segment_item_geom_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_via_item_geom_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_zone_item_rect_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_other_pad_item_geom_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_point_rect_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_point_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_segments_intersect_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_rect_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_rect_rect_gap_py, m)?)?;
    m.add_function(wrap_pyfunction!(fixed_copper_exact_clearance_mm_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mm_to_units_matches_even_parity_examples() {
        // Pinned against the Python reference's `_mm_to_units`:
        //   mm_to_units(0.05) == 4, mm_to_units(0.0) == 0, mm_to_units(-0.05) == -6
        assert_eq!(mm_to_units(0.05).ok(), Some(4));
        assert_eq!(mm_to_units(0.0).ok(), Some(0));
        assert_eq!(mm_to_units(-0.05).ok(), Some(-6));
    }

    #[test]
    fn rotated_matches_quadrant_table() {
        assert_eq!(rotated(1.0, 2.0, 3.0, 4.0, 0), (1.0, 2.0, 3.0, 4.0));
        assert_eq!(rotated(1.0, 2.0, 3.0, 4.0, 1), (2.0, -1.0, 4.0, 3.0));
        assert_eq!(rotated(1.0, 2.0, 3.0, 4.0, 2), (-1.0, -2.0, 3.0, 4.0));
        assert_eq!(rotated(1.0, 2.0, 3.0, 4.0, 3), (-2.0, 1.0, 4.0, 3.0));
    }

    #[test]
    fn zone_exact_clearance_zero_when_intersecting() {
        let square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)];
        assert_eq!(zone_exact_clearance((1.0, 1.0, 2.0, 2.0), &square), 0.0);
    }

    #[test]
    fn zone_exact_clearance_positive_when_disjoint() {
        let square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)];
        let d = zone_exact_clearance((10.0, 10.0, 11.0, 11.0), &square);
        assert!(d > 0.0 && d.is_finite());
    }
}
