// Router V6 occupancy-grid rasterisation kernels (Wave 4), migrated from
// `temper_placer/router_v6/occupancy_grid.py`'s `OccupancyGrid` methods:
// `mark_path_blocked`, `mark_segment_blocked`, `unmark_segment_blocked`,
// `unmark_path`, `get_blocking_nets`, `mark_via_blocked`, `downsample`.
//
// Python references: `_OracleOccupancyGrid` in
// `packages/temper-placer/tests/router_v6/_occupancy_raster_py_oracle.py`
// (a verbatim pin of the pre-migration class); the differential lives in
// `test_occupancy_grid_rust_differential.py`.
//
// NOT migrated (glue / library-dependent):
//   - `build_occupancy_grid`: its hot path is `shapely.contains()` (a GEOS
//     prepared-geometry predicate) over points sampled inside a polygon
//     produced by `available_area.buffer(-inflation_mm, quad_segs=4)` (a
//     GEOS/JTS buffer-erosion operation with its own curve tessellation).
//     Neither GEOS's `contains` predicate nor its buffering algorithm has an
//     accessible pure-Rust equivalent guaranteed bit-identical to what
//     `shapely` calls — reimplementing point-in-polygon here (even with the
//     crate's own `polygon::point_in_polygon_winding`) would test a
//     DIFFERENT algorithm against a boundary GEOS computed, with no
//     guarantee the boundary matches at all (same shape of refusal as the
//     `np.dot`-dispatches-to-Accelerate-BLAS case: the reference is opaque
//     library behaviour, not a reimplementable kernel). Left in Python.
//   - `world_to_grid` / `grid_to_world`: trivial arithmetic; the migrated
//     kernels below inline the identical bit-exact conversion rather than
//     exposing it as a standalone entry point.
//   - `is_free` / `is_blocked` / `free_cell_count` / `blocked_cell_count` /
//     `occupancy_ratio` / `width_mm` / `height_mm`: trivial property
//     accessors, already O(1) or a single vectorized numpy reduction.
//   - `mark_path_blocked_3d`: thin per-layer dispatch loop over the
//     now-Rust-backed `mark_path_blocked`.
//   - `OccupancyGridStage.run` / `validate_occupancy_grid`: stage
//     orchestration / validation glue.
//
// Bit-exactness notes (measured; see also grid_raster.rs / host_math.rs):
//
//  - `** 2` / `** 0.5` on the float path-interpolation distance
//    (`((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) ** 0.5`) are CPython libm
//    `pow` (`float_pow`), NOT `powi`/`sqrt` — routed through
//    `host_math::pow`.
//  - `mark_via_blocked`'s per-cell distance
//    (`((x-cx)**2 + (y-cy)**2) ** 0.5 * cell_size`) squares Python INTS
//    (`x`, `cx`, `y`, `cy` are all grid-index ints in the reference), so
//    `(x-cx)**2` is EXACT integer exponentiation, not a float `pow` call —
//    the sum is computed in i64 and only the final `** 0.5` goes through
//    `host_math::pow`.
//  - `int(x)` truncates toward zero (`x as i64` matches for finite `x`);
//    `int(inf)`/`int(nan)` RAISE (OverflowError / ValueError respectively)
//    — replicated explicitly, since Rust's `as i64` would otherwise
//    saturate silently instead of raising.
//  - `int(np.ceil(x))`: `np.ceil` (unlike `math.ceil`) propagates inf/nan
//    through unchanged; the subsequent `int()` is what raises. Same
//    OverflowError/ValueError split as above.
//  - Writing an out-of-`int8`-range `net_id` into the grid (always `int8`,
//    per `build_occupancy_grid`'s `np.full(..., dtype=np.int8)`) raises
//    `OverflowError` from numpy's scalar-to-int8 cast — even for an EMPTY
//    target slice (measured against numpy 2.4.6:
//    `arr[0:0, 0:0] = 200` still raises `OverflowError`). The rectangular
//    kernels replicate this: the range check fires before any write,
//    gated only on "will at least one point actually be marked" — an
//    all-degenerate path (every sub-segment has `steps <= 0`) marks
//    nothing and therefore never raises, matching the reference.
//    `mark_via_blocked`'s inner loop is a plain nested Python `for` (one
//    scalar assignment per matching cell), checked per-cell rather than
//    upfront — but since `net_id` is the SAME value on every iteration, an
//    out-of-range `net_id` always raises on the FIRST matching cell,
//    before that cell's own write lands, so a call that raises never
//    mutates the grid at all (measured: unlike the rectangular kernels,
//    which raise unconditionally once any point would be marked, this one
//    raises only when at least one cell GEOMETRICALLY matches — a via
//    whose bbox has zero matching cells never raises regardless of
//    `net_id`, pinned by `test_mark_via_blocked_zero_matches_raises_nothing`).
//    Checked per-cell (not upfront) purely to mirror the reference's
//    control flow, not because it changes the observable outcome here.
//  - `unmark_path` does NOT consult `static_mask` (only
//    `unmark_segment_blocked` does) — a real asymmetry in the reference,
//    preserved as-is rather than "fixed".
//  - `get_blocking_nets` returns a Python `set[int]`; this kernel returns
//    a SORTED, deduplicated `Vec<i64>` so no set/dict iteration order ever
//    reaches the boundary (`check_hash_order_determinism.py`'s concern) —
//    the Python wrapper rewraps it as `set(...)` to preserve the public
//    return type.

// This module's kernels raise pyo3 exceptions to mirror CPython's own
// `int(inf)`/`int(nan)`/int8-overflow behaviour (see the bit-exactness
// notes above), so — unlike this crate's other rasterisation modules,
// which keep pure kernels pyo3-free and only wrap them at the bridge
// layer — the kernels here are pyo3-flavoured throughout. The whole
// module is therefore gated on the `python` feature at its `pub mod`
// declaration in `lib.rs` rather than piecemeal internally.
use pyo3::buffer::PyBuffer;
use pyo3::exceptions::{PyOverflowError, PyValueError, PyZeroDivisionError};
use pyo3::prelude::*;
use std::cell::Cell;

use crate::host_math;

// ---------------------------------------------------------------------------
// Pure numeric helpers (unit-testable without libpython)
// ---------------------------------------------------------------------------

/// CPython `int(x)` truncation-toward-zero, raising exactly like
/// `int(float)` does for non-finite input (`OverflowError` for +-inf,
/// `ValueError` for nan).
fn py_int_trunc(x: f64) -> PyResult<i64> {
    if x.is_nan() {
        return Err(PyValueError::new_err("cannot convert float NaN to integer"));
    }
    if x.is_infinite() {
        return Err(PyOverflowError::new_err(
            "cannot convert float infinity to integer",
        ));
    }
    Ok(x as i64)
}

/// `int(np.ceil(x))`.
fn py_int_ceil(x: f64) -> PyResult<i64> {
    py_int_trunc(x.ceil())
}

/// Plain CPython `float / float`: unlike numpy division, this RAISES
/// `ZeroDivisionError` for a zero divisor (`+0.0` or `-0.0`, both compare
/// equal to `0.0`) instead of producing inf/nan — measured:
/// `0.6 / 0.0` raises `ZeroDivisionError: float division by zero` in
/// plain Python, where `np.float64(0.6) / 0.0` would instead warn and
/// return `inf`. Every `/` in the reference kernels below (`world_to_grid`,
/// `expansion`, `steps`) is this plain-float form, NOT a numpy division —
/// so a zero `cell_size` raises HERE, before `np.ceil`/`int()` ever run
/// (those only see the OUTPUT of an already-successful division).
fn py_float_div(num: f64, den: f64) -> PyResult<f64> {
    if den == 0.0 {
        return Err(PyZeroDivisionError::new_err("float division by zero"));
    }
    Ok(num / den)
}

/// `self.world_to_grid(x_mm, y_mm)` verbatim.
fn world_to_grid(
    x_mm: f64,
    y_mm: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
) -> PyResult<(i64, i64)> {
    Ok((
        py_int_trunc(py_float_div(x_mm - origin_x, cell_size)?)?,
        py_int_trunc(py_float_div(y_mm - origin_y, cell_size)?)?,
    ))
}

/// `expansion = int(np.ceil(radius_mm / self.cell_size))`.
fn expansion_cells(radius_mm: f64, cell_size: f64) -> PyResult<i64> {
    py_int_ceil(py_float_div(radius_mm, cell_size)?)
}

/// `steps = int(np.ceil(dist / (self.cell_size / 2)))`, with `dist` the
/// libm-`pow`-computed Euclidean distance between two float points
/// (`((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) ** 0.5`). `self.cell_size / 2`
/// (division by the int literal `2`) can never itself be a zero-divisor
/// error; it becomes the (possibly zero) divisor of the outer division.
fn segment_steps(x1: f64, y1: f64, x2: f64, y2: f64, cell_size: f64) -> PyResult<i64> {
    let dx = x2 - x1;
    let dy = y2 - y1;
    let dist = host_math::pow(host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0), 0.5);
    py_int_ceil(py_float_div(dist, cell_size / 2.0)?)
}

/// `x_start,x_end,y_start,y_end` clamp verbatim
/// (`max(0, cx-expansion)` / `min(dim, cx+expansion+1)`). `x_end`/`y_end`
/// are the RAW `min(...)` result and MAY be negative (when
/// `cx + expansion + 1 < 0`, i.e. the point is far enough off the
/// negative edge of the grid) — callers that index via a numpy SLICE
/// must run these through `slice_stop` before using them (see below);
/// callers that index via a `range()` loop (`mark_via_circle`) must NOT,
/// and use these values as-is.
fn clamp_bbox(
    cx: i64,
    cy: i64,
    expansion: i64,
    width_cells: i64,
    height_cells: i64,
) -> (i64, i64, i64, i64) {
    let x_start = (cx - expansion).max(0);
    let x_end = (cx + expansion + 1).min(width_cells);
    let y_start = (cy - expansion).max(0);
    let y_end = (cy + expansion + 1).min(height_cells);
    (x_start, x_end, y_start, y_end)
}

/// Python slice-stop normalisation for `grid[start:raw_end]`.
///
/// **Measured, previously-unhandled trap:** `x_end`/`y_end` above are fed
/// straight into a numpy SLICE (`self.grid[y_start:y_end, x_start:x_end]
/// = net_id`) in the reference, NOT a `range()`. A negative slice stop in
/// Python/numpy does NOT mean "empty" — it WRAPS AROUND to count from the
/// end of the axis: `min(width_cells, cx + expansion + 1)` can be
/// negative when a path/segment point lands far enough off the NEGATIVE
/// edge of the grid, and `grid[1:4, 0:-1] = 9` on a 13-wide axis then
/// blocks columns 0..11 (everything except the last column), not
/// nothing. Measured against numpy 2.4.6. `mark_via_circle` is IMMUNE:
/// its bbox feeds a `range()` loop, and `range(0, -1)` really is empty —
/// only the four slice-based kernels (`mark_path_blocked`,
/// `mark_segment_blocked`, `unmark_segment_blocked`, `unmark_path`) hit
/// this.
fn slice_stop(raw_end: i64, dim: i64) -> i64 {
    if raw_end < 0 {
        (dim + raw_end).max(0)
    } else {
        raw_end.min(dim)
    }
}

/// numpy's int8 scalar-assignment range check: `arr[...] = net_id` on an
/// `int8` array raises `OverflowError` for `net_id` outside `[-128, 127]`
/// — even for an empty target slice.
fn check_i8_write(net_id: i64) -> PyResult<i8> {
    if !(i8::MIN as i64..=i8::MAX as i64).contains(&net_id) {
        Err(PyOverflowError::new_err(format!(
            "Python integer {net_id} out of bounds for int8"
        )))
    } else {
        Ok(net_id as i8)
    }
}

/// `t = s / steps; x = p1[0] + t*(p2[0]-p1[0]); y = p1[1] + t*(p2[1]-p1[1])`.
fn interpolated_point(p1: (f64, f64), p2: (f64, f64), s: i64, steps: i64) -> (f64, f64) {
    let t = (s as f64) / (steps as f64);
    (p1.0 + t * (p2.0 - p1.0), p1.1 + t * (p2.1 - p1.1))
}

// ---------------------------------------------------------------------------
// Grid-mutating kernels
// ---------------------------------------------------------------------------

/// The `mark_point` closure shared by `mark_path_blocked` /
/// `mark_segment_blocked`: unconditional overwrite of the clamped bbox to
/// `net_id`.
#[allow(clippy::too_many_arguments)]
fn mark_point_rect(
    grid: &[Cell<i8>],
    width_cells: i64,
    height_cells: i64,
    x_mm: f64,
    y_mm: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    expansion: i64,
    net_id_i8: i8,
) -> PyResult<()> {
    let (cx, cy) = world_to_grid(x_mm, y_mm, origin_x, origin_y, cell_size)?;
    let (x_start, x_end_raw, y_start, y_end_raw) =
        clamp_bbox(cx, cy, expansion, width_cells, height_cells);
    let x_end = slice_stop(x_end_raw, width_cells); // slice consumer: wraps on negative
    let y_end = slice_stop(y_end_raw, height_cells);
    for row in y_start..y_end {
        for col in x_start..x_end {
            let idx = (row * width_cells + col) as usize;
            grid[idx].set(net_id_i8);
        }
    }
    Ok(())
}

/// `mark_path_blocked` verbatim: no fallback on a degenerate (`steps<=0`)
/// sub-segment — silently skipped, exactly like the reference. Empty/
/// single-point paths never write and never raise.
#[allow(clippy::too_many_arguments)]
pub fn mark_path_rect(
    grid: &[Cell<i8>],
    width_cells: i64,
    height_cells: i64,
    path: &[(f64, f64)],
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    if path.len() < 2 {
        return Ok(());
    }
    let radius_mm = trace_width / 2.0 + clearance;
    let expansion = expansion_cells(radius_mm, cell_size)?;

    let mut segments = Vec::with_capacity(path.len() - 1);
    for w in path.windows(2) {
        let steps = segment_steps(w[0].0, w[0].1, w[1].0, w[1].1, cell_size)?;
        segments.push((w[0], w[1], steps));
    }
    // Only check the int8 range if at least one mark_point call is about
    // to happen: an all-degenerate path never writes and therefore never
    // raises, matching the reference (which evaluates the check lazily,
    // per numpy slice-assignment, inside the loop body).
    if !segments.iter().any(|(_, _, steps)| *steps > 0) {
        return Ok(());
    }
    let net_id_i8 = check_i8_write(net_id)?;

    for (p1, p2, steps) in segments {
        if steps > 0 {
            for s in 0..=steps {
                let (x, y) = interpolated_point(p1, p2, s, steps);
                mark_point_rect(
                    grid, width_cells, height_cells, x, y, origin_x, origin_y, cell_size,
                    expansion, net_id_i8,
                )?;
            }
        }
    }
    Ok(())
}

/// `mark_segment_blocked` verbatim: single segment, WITH the degenerate
/// (`steps<=0`) fallback that marks `p1` directly — unlike
/// `mark_path_blocked`, so at least one write (and hence the range check)
/// always happens.
#[allow(clippy::too_many_arguments)]
pub fn mark_segment_rect(
    grid: &[Cell<i8>],
    width_cells: i64,
    height_cells: i64,
    p1: (f64, f64),
    p2: (f64, f64),
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    let radius_mm = trace_width / 2.0 + clearance;
    let expansion = expansion_cells(radius_mm, cell_size)?;
    let steps = segment_steps(p1.0, p1.1, p2.0, p2.1, cell_size)?;
    let net_id_i8 = check_i8_write(net_id)?;

    if steps > 0 {
        for s in 0..=steps {
            let (x, y) = interpolated_point(p1, p2, s, steps);
            mark_point_rect(
                grid, width_cells, height_cells, x, y, origin_x, origin_y, cell_size, expansion,
                net_id_i8,
            )?;
        }
    } else {
        mark_point_rect(
            grid, width_cells, height_cells, p1.0, p1.1, origin_x, origin_y, cell_size,
            expansion, net_id_i8,
        )?;
    }
    Ok(())
}

/// The `unmark_point` closure shared by `unmark_segment_blocked` /
/// `unmark_path`: cells matching `net_id` clear to 0; when `static_mask`
/// is supplied (only `unmark_segment_blocked` passes one), cells that
/// were ALSO static are restored to -1 instead. Never raises on the
/// int8 range (the only values ever written are 0 and -1).
#[allow(clippy::too_many_arguments)]
fn unmark_point_rect(
    grid: &[Cell<i8>],
    static_mask: Option<&[Cell<u8>]>,
    width_cells: i64,
    height_cells: i64,
    x_mm: f64,
    y_mm: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    expansion: i64,
    net_id: i64,
) -> PyResult<()> {
    let (cx, cy) = world_to_grid(x_mm, y_mm, origin_x, origin_y, cell_size)?;
    let (x_start, x_end_raw, y_start, y_end_raw) =
        clamp_bbox(cx, cy, expansion, width_cells, height_cells);
    let x_end = slice_stop(x_end_raw, width_cells); // slice consumer: wraps on negative
    let y_end = slice_stop(y_end_raw, height_cells);
    for row in y_start..y_end {
        for col in x_start..x_end {
            let idx = (row * width_cells + col) as usize;
            let is_net = grid[idx].get() as i64 == net_id;
            if !is_net {
                continue;
            }
            grid[idx].set(0);
            if let Some(sm) = static_mask {
                if sm[idx].get() != 0 {
                    grid[idx].set(-1);
                }
            }
        }
    }
    Ok(())
}

/// `unmark_segment_blocked` verbatim: single segment, WITH the
/// degenerate-steps fallback (unmarks `p1` directly) and WITH
/// `static_mask` restoration.
#[allow(clippy::too_many_arguments)]
pub fn unmark_segment_rect(
    grid: &[Cell<i8>],
    static_mask: Option<&[Cell<u8>]>,
    width_cells: i64,
    height_cells: i64,
    p1: (f64, f64),
    p2: (f64, f64),
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    let radius_mm = trace_width / 2.0 + clearance;
    let expansion = expansion_cells(radius_mm, cell_size)?;
    let steps = segment_steps(p1.0, p1.1, p2.0, p2.1, cell_size)?;

    if steps > 0 {
        for s in 0..=steps {
            let (x, y) = interpolated_point(p1, p2, s, steps);
            unmark_point_rect(
                grid, static_mask, width_cells, height_cells, x, y, origin_x, origin_y,
                cell_size, expansion, net_id,
            )?;
        }
    } else {
        unmark_point_rect(
            grid, static_mask, width_cells, height_cells, p1.0, p1.1, origin_x, origin_y,
            cell_size, expansion, net_id,
        )?;
    }
    Ok(())
}

/// `unmark_path` verbatim: path of points, NO degenerate-steps fallback,
/// and — a real asymmetry in the reference, preserved as-is — NEVER
/// consults `static_mask` even when the grid carries one.
#[allow(clippy::too_many_arguments)]
pub fn unmark_path_rect(
    grid: &[Cell<i8>],
    width_cells: i64,
    height_cells: i64,
    path: &[(f64, f64)],
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    if path.len() < 2 {
        return Ok(());
    }
    let radius_mm = trace_width / 2.0 + clearance;
    let expansion = expansion_cells(radius_mm, cell_size)?;

    for w in path.windows(2) {
        let (p1, p2) = (w[0], w[1]);
        let steps = segment_steps(p1.0, p1.1, p2.0, p2.1, cell_size)?;
        if steps > 0 {
            for s in 0..=steps {
                let (x, y) = interpolated_point(p1, p2, s, steps);
                unmark_point_rect(
                    grid, None, width_cells, height_cells, x, y, origin_x, origin_y, cell_size,
                    expansion, net_id,
                )?;
            }
        }
        // No else-fallback here: matches the reference (only
        // `unmark_segment_blocked` has one).
    }
    Ok(())
}

/// `get_blocking_nets` verbatim (read-only sampling), except the return
/// value is a SORTED, deduplicated `Vec<i64>` instead of an unordered
/// Python `set` — the Python wrapper rewraps it as a `set` to preserve
/// the public API.
pub fn blocking_net_ids(
    grid: &[i8],
    width_cells: i64,
    height_cells: i64,
    p1: (f64, f64),
    p2: (f64, f64),
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
) -> PyResult<Vec<i64>> {
    let steps = segment_steps(p1.0, p1.1, p2.0, p2.1, cell_size)?;
    let mut ids: Vec<i64> = Vec::new();
    if steps > 0 {
        for s in 0..=steps {
            let (x, y) = interpolated_point(p1, p2, s, steps);
            let (cx, cy) = world_to_grid(x, y, origin_x, origin_y, cell_size)?;
            if cx >= 0 && cx < width_cells && cy >= 0 && cy < height_cells {
                let idx = (cy * width_cells + cx) as usize;
                let val = grid[idx] as i64;
                if val > 0 {
                    ids.push(val);
                }
            }
        }
    }
    ids.sort_unstable();
    ids.dedup();
    Ok(ids)
}

/// `mark_via_blocked` verbatim: circular region, per-cell distance formula
/// computed on the INTEGER cell offsets (`(x-cx)**2` is exact CPython
/// integer exponentiation, not a float `pow`), scaled by `cell_size`
/// AFTER the `** 0.5`. The int8-range check happens per matching cell (a
/// plain nested Python `for` in the reference, one scalar assignment per
/// cell); since `net_id` is constant across the call, an out-of-range
/// value always raises on the FIRST matching cell (before that cell's own
/// write lands), so the grid is left completely unmutated by a raising
/// call — but ONLY raises if at least one cell geometrically matches
/// (`dist <= radius_mm`); a via whose bbox matches nothing never raises,
/// regardless of `net_id`.
#[allow(clippy::too_many_arguments)]
pub fn mark_via_circle(
    grid: &[Cell<i8>],
    width_cells: i64,
    height_cells: i64,
    x_mm: f64,
    y_mm: f64,
    via_diameter: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    let radius_mm = via_diameter / 2.0 + clearance;
    let expansion = expansion_cells(radius_mm, cell_size)?;
    let (cx, cy) = world_to_grid(x_mm, y_mm, origin_x, origin_y, cell_size)?;
    let (x_start, x_end, y_start, y_end) = clamp_bbox(cx, cy, expansion, width_cells, height_cells);

    for y in y_start..y_end {
        for x in x_start..x_end {
            let dx = x - cx;
            let dy = y - cy;
            let sq_sum = dx * dx + dy * dy; // exact i64, matches CPython int**2
            let dist = host_math::pow(sq_sum as f64, 0.5) * cell_size;
            if dist <= radius_mm {
                let net_id_i8 = check_i8_write(net_id)?;
                let idx = (y * width_cells + x) as usize;
                grid[idx].set(net_id_i8);
            }
        }
    }
    Ok(())
}

/// `downsample`'s block-reduce core: coarse cell `(by, bx)` is "blocked"
/// (`true`) iff ANY sub-cell in its `factor`x`factor` block is nonzero,
/// with out-of-bounds (padding) sub-cells treated as blocked — matching
/// `np.pad(..., constant_values=CellState.BLOCKED.value)` (BLOCKED = 1,
/// nonzero) followed by `np.any` over the block axes.
pub fn downsample_or_blocks(
    mask: &[u8],
    old_h: usize,
    old_w: usize,
    factor: usize,
) -> (Vec<u8>, usize, usize) {
    debug_assert!(factor >= 1);
    let new_h = old_h.div_ceil(factor).max(1);
    let new_w = old_w.div_ceil(factor).max(1);
    let mut out = vec![0u8; new_h * new_w];
    for by in 0..new_h {
        for bx in 0..new_w {
            let mut blocked = false;
            'outer: for dy in 0..factor {
                let ry = by * factor + dy;
                for dx in 0..factor {
                    let rx = bx * factor + dx;
                    let cell_blocked = if ry < old_h && rx < old_w {
                        mask[ry * old_w + rx] != 0
                    } else {
                        true // padded cell: BLOCKED sentinel (nonzero)
                    };
                    if cell_blocked {
                        blocked = true;
                        break 'outer;
                    }
                }
            }
            out[by * new_w + bx] = blocked as u8;
        }
    }
    (out, new_h, new_w)
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

fn grid_shape(grid: &PyBuffer<i8>) -> PyResult<(i64, i64)> {
    let shape = grid.shape();
    if shape.len() != 2 {
        return Err(PyValueError::new_err(format!(
            "grid must be a 2D int8 array, got {} dimensions",
            shape.len()
        )));
    }
    Ok((shape[0] as i64, shape[1] as i64)) // (rows/height, cols/width)
}

fn grid_cells<'a>(grid: &'a PyBuffer<i8>, py: Python<'a>) -> PyResult<&'a [Cell<i8>]> {
    grid.as_mut_slice(py).ok_or_else(|| {
        PyValueError::new_err("grid must be a writable, C-contiguous int8 array")
    })
}

fn mask_cells<'a>(buf: &'a PyBuffer<u8>, py: Python<'a>) -> PyResult<&'a [Cell<u8>]> {
    buf.as_mut_slice(py)
        .ok_or_else(|| PyValueError::new_err("mask must be a writable, C-contiguous uint8 array"))
}

#[pyfunction]
#[pyo3(signature = (grid, path, trace_width, clearance, origin_x, origin_y, cell_size, net_id))]
#[allow(clippy::too_many_arguments)]
pub fn mark_path_rect_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    path: Vec<(f64, f64)>,
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let (rows, cols) = grid_shape(&grid)?;
        let cells = grid_cells(&grid, py)?;
        mark_path_rect(
            cells, cols, rows, &path, trace_width, clearance, origin_x, origin_y, cell_size,
            net_id,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
#[pyo3(signature = (grid, x1, y1, x2, y2, trace_width, clearance, origin_x, origin_y, cell_size, net_id))]
#[allow(clippy::too_many_arguments)]
pub fn mark_segment_rect_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let (rows, cols) = grid_shape(&grid)?;
        let cells = grid_cells(&grid, py)?;
        mark_segment_rect(
            cells, cols, rows, (x1, y1), (x2, y2), trace_width, clearance, origin_x, origin_y,
            cell_size, net_id,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
#[pyo3(signature = (grid, static_mask, x1, y1, x2, y2, trace_width, clearance, origin_x, origin_y, cell_size, net_id))]
#[allow(clippy::too_many_arguments)]
pub fn unmark_segment_rect_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    static_mask: Option<PyBuffer<u8>>,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let (rows, cols) = grid_shape(&grid)?;
        let cells = grid_cells(&grid, py)?;
        let sm_cells = match &static_mask {
            Some(buf) => Some(mask_cells(buf, py)?),
            None => None,
        };
        unmark_segment_rect(
            cells, sm_cells, cols, rows, (x1, y1), (x2, y2), trace_width, clearance, origin_x,
            origin_y, cell_size, net_id,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
#[pyo3(signature = (grid, path, trace_width, clearance, origin_x, origin_y, cell_size, net_id))]
#[allow(clippy::too_many_arguments)]
pub fn unmark_path_rect_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    path: Vec<(f64, f64)>,
    trace_width: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let (rows, cols) = grid_shape(&grid)?;
        let cells = grid_cells(&grid, py)?;
        unmark_path_rect(
            cells, cols, rows, &path, trace_width, clearance, origin_x, origin_y, cell_size,
            net_id,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
#[pyo3(signature = (grid, x1, y1, x2, y2, origin_x, origin_y, cell_size))]
#[allow(clippy::too_many_arguments)]
pub fn blocking_net_ids_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
) -> PyResult<Vec<i64>> {
    temper_py_bridge::catch_unwind(|| {
        let (rows, cols) = grid_shape(&grid)?;
        let cells = grid_cells(&grid, py)?;
        // Read-only use: `Cell<i8>::get()` copies, no aliasing hazard.
        let flat: Vec<i8> = cells.iter().map(|c| c.get()).collect();
        blocking_net_ids(&flat, cols, rows, (x1, y1), (x2, y2), origin_x, origin_y, cell_size)
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
#[pyo3(signature = (grid, x_mm, y_mm, via_diameter, clearance, origin_x, origin_y, cell_size, net_id))]
#[allow(clippy::too_many_arguments)]
pub fn mark_via_circle_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    x_mm: f64,
    y_mm: f64,
    via_diameter: f64,
    clearance: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
    net_id: i64,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let (rows, cols) = grid_shape(&grid)?;
        let cells = grid_cells(&grid, py)?;
        mark_via_circle(
            cells, cols, rows, x_mm, y_mm, via_diameter, clearance, origin_x, origin_y,
            cell_size, net_id,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
#[pyo3(signature = (mask, old_h, old_w, factor))]
pub fn downsample_or_blocks_py(
    py: Python<'_>,
    mask: PyBuffer<u8>,
    old_h: usize,
    old_w: usize,
    factor: i64,
) -> PyResult<(Vec<u8>, usize, usize)> {
    temper_py_bridge::catch_unwind(|| {
        if factor == 0 {
            return Err(PyZeroDivisionError::new_err("division by zero"));
        }
        if factor < 0 {
            return Err(PyValueError::new_err(
                "downsample factor must be positive",
            ));
        }
        let cells = mask_cells(&mask, py)?;
        let flat: Vec<u8> = cells.iter().map(|c| c.get()).collect();
        Ok(downsample_or_blocks(&flat, old_h, old_w, factor as usize))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

// ---------------------------------------------------------------------------
// Pure-kernel unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn cells_from(v: &[i8]) -> Vec<Cell<i8>> {
        v.iter().map(|&x| Cell::new(x)).collect()
    }
    fn cells_to(v: &[Cell<i8>]) -> Vec<i8> {
        v.iter().map(|c| c.get()).collect()
    }
    fn u8cells_from(v: &[u8]) -> Vec<Cell<u8>> {
        v.iter().map(|&x| Cell::new(x)).collect()
    }

    #[test]
    fn test_world_to_grid_truncates_toward_zero() {
        // -0.5mm / 1.0mm cell -> -0.5 -> int() truncates to 0, NOT floor (-1).
        let (cx, cy) = world_to_grid(-0.5, -0.5, 0.0, 0.0, 1.0).unwrap();
        assert_eq!((cx, cy), (0, 0));
        // -1.5 -> truncates to -1, not floor(-1.5) = -2.
        let (cx, _) = world_to_grid(-1.5, 0.0, 0.0, 0.0, 1.0).unwrap();
        assert_eq!(cx, -1);
    }

    #[test]
    fn test_world_to_grid_raises_on_nonfinite() {
        assert!(world_to_grid(f64::INFINITY, 0.0, 0.0, 0.0, 1.0).is_err());
        assert!(world_to_grid(f64::NAN, 0.0, 0.0, 0.0, 1.0).is_err());
    }

    #[test]
    fn test_expansion_ceil_overflow_raises() {
        // radius/cell_size = inf -> np.ceil(inf) = inf -> int(inf) raises.
        assert!(expansion_cells(1.0, 0.0).is_err());
    }

    #[test]
    fn test_check_i8_write_range() {
        assert_eq!(check_i8_write(127).unwrap(), 127);
        assert_eq!(check_i8_write(-128).unwrap(), -128);
        assert!(check_i8_write(128).is_err());
        assert!(check_i8_write(-129).is_err());
    }

    #[test]
    fn test_mark_path_rect_blocks_between_points() {
        let cells = cells_from(&[0i8; 100]);
        mark_path_rect(
            &cells, 10, 10, &[(0.5, 5.5), (9.5, 5.5)], 1.0, 0.0, 0.0, 0.0, 1.0, 7,
        )
        .unwrap();
        let g = cells_to(&cells);
        assert_eq!(g[5 * 10 + 0], 7);
        assert_eq!(g[5 * 10 + 9], 7);
        assert_eq!(g[3 * 10 + 5], 0); // untouched row
    }

    #[test]
    fn test_slice_stop_wraps_on_negative_like_python_slicing() {
        // grid[1:-1] on a 13-wide axis stops at index 12 (dim + (-1)),
        // NOT "before index -1" -- Python/numpy slice semantics, not
        // range() semantics.
        assert_eq!(slice_stop(-1, 13), 12);
        assert_eq!(slice_stop(-13, 13), 0);
        assert_eq!(slice_stop(-100, 13), 0); // clamps to 0, does not go negative
        assert_eq!(slice_stop(5, 13), 5); // non-negative: passthrough (already <= dim)
        assert_eq!(slice_stop(20, 13), 13); // non-negative: still capped at dim
    }

    #[test]
    fn test_mark_point_rect_negative_end_wraps_not_empty() {
        // A point far enough off the NEGATIVE edge of the grid produces a
        // raw x_end = cx + expansion + 1 < 0. Python's
        // `grid[y_start:y_end, x_start:x_end] = net_id` with a negative
        // x_end WRAPS to count from the end of the row, blocking almost
        // the whole row -- NOT a no-op. `mark_point_rect` must reproduce
        // this exactly (regression for a mismatch caught by the
        // differential suite against the pinned oracle).
        let cells = cells_from(&[0i8; 5 * 13]); // 5 rows x 13 cols
        // origin=(0,0), cell_size=1.0: x_mm=-3.4 -> cx = int(-3.4/1.0) = -3
        // (truncation toward zero). expansion=1 -> raw x_end = -3+1+1 = -1
        // -> wraps to col 12 (13 + (-1)), NOT "no columns".
        mark_point_rect(&cells, 13, 5, -3.4, 2.4, 0.0, 0.0, 1.0, 1, 9).unwrap();
        let g = cells_to(&cells);
        // y: cy = int(2.4/1.0) = 2, expansion 1 -> rows 1..4 (raw y_end=4,
        // non-negative, unaffected by wraparound).
        for row in 1..4 {
            for col in 0..12 {
                assert_eq!(g[row * 13 + col], 9, "row={row} col={col}");
            }
            assert_eq!(g[row * 13 + 12], 0, "last column must stay unblocked");
        }
        assert_eq!(g[0 * 13 + 0], 0); // row 0 untouched
        assert_eq!(g[4 * 13 + 0], 0); // row 4 untouched
    }

    #[test]
    fn test_mark_via_circle_immune_to_slice_wraparound() {
        // mark_via_circle's bbox feeds a range() loop, not a slice, so an
        // out-of-grid centre with a negative raw bbox bound must produce
        // NO marks at all -- unlike the rectangular kernels above.
        let cells = cells_from(&[0i8; 5 * 13]);
        // Same coordinates as the mark_point_rect wraparound case, but as
        // a via: cx=-3, cy=2, expansion depends on radius; force a small
        // expansion so the raw x_end is still negative.
        mark_via_circle(&cells, 13, 5, -3.4, 2.4, 0.4, 0.0, 0.0, 0.0, 1.0, 9).unwrap();
        assert_eq!(cells_to(&cells), vec![0i8; 5 * 13]);
    }

    #[test]
    fn test_mark_path_rect_empty_path_is_noop() {
        let cells = cells_from(&[0i8; 9]);
        mark_path_rect(&cells, 3, 3, &[], 1.0, 0.0, 0.0, 0.0, 1.0, 200).unwrap(); // net_id out of range but no points -> no raise
        assert_eq!(cells_to(&cells), vec![0i8; 9]);
    }

    #[test]
    fn test_mark_path_rect_out_of_range_net_id_raises_when_points_exist() {
        let cells = cells_from(&[0i8; 9]);
        let err = mark_path_rect(&cells, 3, 3, &[(0.5, 0.5), (2.5, 0.5)], 1.0, 0.0, 0.0, 0.0, 1.0, 200);
        assert!(err.is_err());
    }

    #[test]
    fn test_mark_segment_rect_degenerate_falls_back_to_p1() {
        // p1 == p2 -> dist 0 -> steps 0 -> fallback marks p1 (unlike
        // mark_path_rect, which would skip it).
        let cells = cells_from(&[0i8; 25]);
        mark_segment_rect(&cells, 5, 5, (2.5, 2.5), (2.5, 2.5), 0.0, 0.0, 0.0, 0.0, 1.0, 9).unwrap();
        assert_eq!(cells_to(&cells)[2 * 5 + 2], 9);
    }

    #[test]
    fn test_mark_path_rect_degenerate_segment_marks_nothing() {
        // Same degenerate p1==p2 case, but via the path (no-fallback) API.
        let cells = cells_from(&[0i8; 25]);
        mark_path_rect(&cells, 5, 5, &[(2.5, 2.5), (2.5, 2.5)], 0.0, 0.0, 0.0, 0.0, 1.0, 9).unwrap();
        assert_eq!(cells_to(&cells), vec![0i8; 25]);
    }

    #[test]
    fn test_unmark_segment_rect_restores_static_sentinel() {
        let mut grid_vals = [0i8; 25];
        grid_vals[2 * 5 + 2] = 7; // net occupies the static cell
        let cells = cells_from(&grid_vals);
        let mut static_vals = [0u8; 25];
        static_vals[2 * 5 + 2] = 1;
        let sm = u8cells_from(&static_vals);
        unmark_segment_rect(
            &cells, Some(&sm), 5, 5, (2.5, 2.5), (2.5, 2.5), 0.0, 0.0, 0.0, 0.0, 1.0, 7,
        )
        .unwrap();
        assert_eq!(cells_to(&cells)[2 * 5 + 2], -1);
    }

    #[test]
    fn test_unmark_segment_rect_no_static_mask_clears_to_zero() {
        let mut grid_vals = [0i8; 25];
        grid_vals[2 * 5 + 2] = 7;
        let cells = cells_from(&grid_vals);
        unmark_segment_rect(
            &cells, None, 5, 5, (2.5, 2.5), (2.5, 2.5), 0.0, 0.0, 0.0, 0.0, 1.0, 7,
        )
        .unwrap();
        assert_eq!(cells_to(&cells)[2 * 5 + 2], 0);
    }

    #[test]
    fn test_unmark_path_rect_ignores_static_mask_asymmetry() {
        // unmark_path never restores -1, even when the cell was static,
        // because the reference never reads static_mask here.
        let mut grid_vals = [0i8; 25];
        grid_vals[2 * 5 + 2] = 7;
        let cells = cells_from(&grid_vals);
        unmark_path_rect(
            &cells, 5, 5, &[(2.0, 2.5), (2.99, 2.5)], 0.0, 0.0, 0.0, 0.0, 1.0, 7,
        )
        .unwrap();
        assert_eq!(cells_to(&cells)[2 * 5 + 2], 0);
    }

    #[test]
    fn test_blocking_net_ids_sorted_and_deduped() {
        let mut grid_vals = [0i8; 100];
        // Lay a straight horizontal line of alternating net ids across row 5.
        for x in 0..10 {
            grid_vals[5 * 10 + x] = if x % 2 == 0 { 3 } else { 9 };
        }
        let ids = blocking_net_ids(&grid_vals, 10, 10, (0.5, 5.5), (9.5, 5.5), 0.0, 0.0, 1.0).unwrap();
        assert_eq!(ids, vec![3, 9]);
    }

    #[test]
    fn test_mark_via_circle_overflow_raises_before_any_write() {
        // net_id is CONSTANT across the call, so the int8-range check
        // fails identically on every matching cell -- meaning it always
        // fails on the very FIRST match, before that cell's own write
        // lands. A raising call therefore mutates nothing at all (see the
        // module doc comment above `mark_via_circle`).
        let cells = cells_from(&[0i8; 9]);
        let err = mark_via_circle(&cells, 3, 3, 1.5, 1.5, 1.0, 0.0, 0.0, 0.0, 1.0, 500);
        assert!(err.is_err());
        assert_eq!(cells_to(&cells), vec![0i8; 9]);
    }

    #[test]
    fn test_mark_via_circle_zero_matches_never_raises() {
        // An out-of-range net_id only raises when at least one cell
        // geometrically matches; a via placed entirely outside the grid
        // (empty bbox after clamping) never enters the match check at
        // all, so it never raises regardless of net_id.
        let cells = cells_from(&[0i8; 9]);
        mark_via_circle(&cells, 3, 3, -100.0, -100.0, 0.0, 0.0, 0.0, 0.0, 1.0, 500).unwrap();
        assert_eq!(cells_to(&cells), vec![0i8; 9]);
    }

    #[test]
    fn test_mark_via_circle_blocks_disc() {
        let cells = cells_from(&[0i8; 49]);
        mark_via_circle(&cells, 7, 7, 3.5, 3.5, 2.0, 0.0, 0.0, 0.0, 1.0, 5).unwrap();
        let g = cells_to(&cells);
        assert_eq!(g[3 * 7 + 3], 5);
        assert_eq!(g[3 * 7 + 4], 5);
        assert_eq!(g[0 * 7 + 0], 0); // corner outside radius
    }

    #[test]
    fn test_downsample_or_blocks_any_nonzero() {
        let mut mask = vec![0u8; 4 * 4];
        mask[1 * 4 + 1] = 1; // one blocked sub-cell in the top-left 2x2 block
        let (out, nh, nw) = downsample_or_blocks(&mask, 4, 4, 2);
        assert_eq!((nh, nw), (2, 2));
        assert_eq!(out, vec![1, 0, 0, 0]);
    }

    #[test]
    fn test_downsample_or_blocks_pads_conservatively() {
        // 3x3 at factor 2 -> new dims ceil(3/2)=2; the padded (4th) row/col
        // is treated as blocked, so the bottom-right coarse cell is
        // blocked even though all 3x3 source cells are free.
        let mask = vec![0u8; 3 * 3];
        let (out, nh, nw) = downsample_or_blocks(&mask, 3, 3, 2);
        assert_eq!((nh, nw), (2, 2));
        // top-left block is fully in-bounds and free
        assert_eq!(out[0], 0);
        // bottom-right block includes padded (out-of-bounds) cells -> blocked
        assert_eq!(out[nw - 1 + (nh - 1) * nw], 1);
    }
}
