// ClearanceGrid rasterisation kernels (Wave 3, candidate #1) — the hot
// compute of the deterministic clearance-grid stage.
//
// Python references:
//   temper_placer/deterministic/stages/_grid_core.py  — the JIT
//     `_block_circle` / `_block_segment` loops and the
//     pure-Python `block_rect` / `unblock_circle` / `occupancy_bitmap`
//     loops (the rasterisation kernels);
//   temper_placer/deterministic/stages/_grid_fence.py — the U3 fence's
//     sample generation (circle + rect creepage-boundary samples);
//   temper_placer/deterministic/stages/_grid_hv.py   — the per-layer
//     creepage-factor application and the zone→closest-component
//     spatial selection.
//
// The Python modules keep their public API and delegate here; the
// deterministic-stage orchestration (bbox computation, net-id
// resolution, expansion-log bookkeeping, violation assembly, config
// errors) stays Python.
//
// Bit-exactness: identical f64 operation order (left-to-right) with
// `x ** 2` / `x ** 0.5` computed as libm `pow` (CPython's float_pow —
// NOT `x * x` / `sqrt`), and pow/cos/sin resolved through dlsym so the
// crate calls the exact libm the host Python runtime uses.  The uv
// standalone build ships its own libm whose results can differ from the
// crate's statically-bound f64 intrinsics in the last ulp (measured for
// sin; see pad_geometry.rs for the established pattern).  The grids are
// mutated in place through numpy's buffer protocol (PyBuffer<i32>),
// exactly like the JIT originals.

#[cfg(feature = "python")]
use pyo3::buffer::PyBuffer;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::cell::Cell;
#[cfg(feature = "python")]
use temper_py_bridge;

// The dlsym "host math" helpers (pow/cos/sin, resolved to the host
// Python runtime's libm so `x ** 2` / `x ** 0.5` / `math.cos` / `math.sin`
// match bit-for-bit) previously lived here; they were extracted to
// `crate::host_math` when the Phase-5 deterministic geometry kernels
// needed the same helpers. The `math_pow`/`math_cos`/`math_sin` names are
// aliased here so the kernels below read exactly as they did.
use crate::host_math::{cos as math_cos, pow as math_pow, sin as math_sin};

// ---------------------------------------------------------------------------
// Pure kernels (no pyo3, unit-testable without libpython)
// ---------------------------------------------------------------------------

/// Merge one cell per the JIT reference: free -> net_id, same net ->
/// unchanged, any other occupied value -> conflict (-1).
#[inline]
fn merge_cell(cur: i32, net_id: i32) -> i32 {
    if cur == 0 {
        net_id
    } else if cur != net_id {
        -1
    } else {
        cur
    }
}

/// Rasterise a disc into `grid` (the retired JIT `_block_circle` loop,
/// verbatim):
/// per cell centre (col*cell + cell/2, row*cell + cell/2), block when
/// dist <= total_radius with the merge semantics above.
///
/// `grid` is the flat C-contiguous row-major int32 cells of shape
/// (rows, cols); only the bbox [min_row, max_row) x [min_col, max_col)
/// is touched.
#[expect(clippy::too_many_arguments, reason = "verbatim port of the retired JIT _block_circle loop; a config struct would change the ported loop shape")]
fn block_circle_into_grid(
    grid: &[Cell<i32>],
    cols: usize,
    cx: f64,
    cy: f64,
    total_radius: f64,
    net_id: i32,
    cell_size_mm: f64,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) {
    for row in min_row..max_row {
        let cell_y = row as f64 * cell_size_mm + cell_size_mm / 2.0;
        for col in min_col..max_col {
            let cell_x = col as f64 * cell_size_mm + cell_size_mm / 2.0;
            let dist = math_pow(math_pow(cell_x - cx, 2.0) + math_pow(cell_y - cy, 2.0), 0.5);
            if dist <= total_radius {
                let idx = row * cols + col;
                grid[idx].set(merge_cell(grid[idx].get(), net_id));
            }
        }
    }
}

/// Rasterise a width-bearing segment into `grid` (the retired JIT
/// `_block_segment` loop, verbatim): project each cell centre onto the segment (clamped t via
/// the reference's min-then-max nesting — `max(0.0, min(1.0, t))` — which
/// is NOT `min(max(t,0),1)`: for t = nan CPython's min keeps its first
/// argument so t clamps to 1.0), then block when dist <= total_radius.
#[expect(clippy::too_many_arguments, reason = "verbatim port of the retired JIT _block_segment loop; a config struct would change the ported loop shape")]
fn block_segment_into_grid(
    grid: &[Cell<i32>],
    cols: usize,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    total_radius: f64,
    net_id: i32,
    cell_size_mm: f64,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) {
    let dx = x2 - x1;
    let dy = y2 - y1;
    let l2 = dx * dx + dy * dy;

    for row in min_row..max_row {
        let cell_y = row as f64 * cell_size_mm + cell_size_mm / 2.0;
        for col in min_col..max_col {
            let cell_x = col as f64 * cell_size_mm + cell_size_mm / 2.0;

            // Projection of point (cell_x, cell_y) onto the segment.
            let t_raw = ((cell_x - x1) * dx + (cell_y - y1) * dy) / l2;
            let t = (1.0_f64.min(t_raw)).max(0.0);

            let proj_x = x1 + t * dx;
            let proj_y = y1 + t * dy;

            let dist = math_pow(math_pow(cell_x - proj_x, 2.0) + math_pow(cell_y - proj_y, 2.0), 0.5);
            if dist <= total_radius {
                let idx = row * cols + col;
                grid[idx].set(merge_cell(grid[idx].get(), net_id));
            }
        }
    }
}

/// Rasterise a rectangle into `grid` (`block_rect`'s inner loop verbatim):
/// integer-only merge over the bbox — no floats, exact by construction.
fn block_rect_into_grid(
    grid: &[Cell<i32>],
    cols: usize,
    net_id: i32,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) {
    for row in min_row..max_row {
        for col in min_col..max_col {
            let idx = row * cols + col;
            grid[idx].set(merge_cell(grid[idx].get(), net_id));
        }
    }
}

/// Clear a disc in `grid` (`unblock_circle`'s inner loop verbatim): cells
/// whose centre is within radius_mm are reset to 0.
#[expect(clippy::too_many_arguments, reason = "verbatim port of the retired JIT unblock_circle loop; a config struct would change the ported loop shape")]
fn clear_circle_from_grid(
    grid: &[Cell<i32>],
    cols: usize,
    cx: f64,
    cy: f64,
    radius_mm: f64,
    cell_size_mm: f64,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) {
    for row in min_row..max_row {
        let cell_y = row as f64 * cell_size_mm + cell_size_mm / 2.0;
        for col in min_col..max_col {
            let cell_x = col as f64 * cell_size_mm + cell_size_mm / 2.0;
            let dist = math_pow(math_pow(cell_x - cx, 2.0) + math_pow(cell_y - cy, 2.0), 0.5);
            if dist <= radius_mm {
                grid[row * cols + col].set(0);
            }
        }
    }
}

/// Compute one layer's occupancy bitmap (`occupancy_bitmap`'s inner loop
/// verbatim): word w covers cols [w*64, min(w*64+64, cols)); bit k of the
/// word is 1 when trace or pad holds a non-zero id at that column.
/// Returns rows*stride u64 words, row-major.
fn occupancy_bitmap_row(
    trace: &[Cell<i32>],
    pad: &[Cell<i32>],
    cols: usize,
    rows: usize,
    stride: usize,
) -> Vec<u64> {
    let mut bitmap = vec![0u64; rows * stride];
    for row in 0..rows {
        for word in 0..stride {
            let start_col = word * 64;
            let end_col = (start_col + 64).min(cols);
            let mut word_val: u64 = 0;
            for col in start_col..end_col {
                let t_val = trace[row * cols + col].get();
                let p_val = pad[row * cols + col].get();
                if t_val != 0 || p_val != 0 {
                    word_val |= 1u64 << (col - start_col);
                }
            }
            bitmap[row * stride + word] = word_val;
        }
    }
    bitmap
}

/// Generate the U3 fence's creepage-boundary samples
/// (`check_clearance_grid_conservatism`'s sample block verbatim): 8
/// samples for rect-shaped pads with non-zero size (4 corners + 4 edge
/// midpoints, each expanded by eff = eff_creep - inset), otherwise
/// sample_count_circle points on the circle of radius
/// pad_radius + eff_creep - inset.  Returns flat x,y pairs.
///
/// `shape` is the FFI pad-shape code (see `pad_geometry.rs` `SHAPE_*`);
/// oval/rect/roundrect are "rect-shaped", circle/thru_hole and unknown
/// codes fall to the circle branch (identical to the old string match).
#[expect(clippy::too_many_arguments, reason = "verbatim port of check_clearance_grid_conservatism's sample block; a config struct would change the ported shape")]
fn fence_samples(
    shape: i64,
    pos_x: f64,
    pos_y: f64,
    pad_radius: f64,
    pad_size_x: f64,
    pad_size_y: f64,
    eff_creep: f64,
    inset: f64,
    sample_count_circle: usize,
) -> Vec<f64> {
    let mut out = Vec::new();
    let is_rect = matches!(shape, crate::pad_geometry::SHAPE_OVAL | crate::pad_geometry::SHAPE_RECT | crate::pad_geometry::SHAPE_ROUNDRECT)
        && pad_size_x > 0.0
        && pad_size_y > 0.0;
    if is_rect {
        let w = pad_size_x;
        let h = pad_size_y;
        let eff = eff_creep - inset;
        // 4 corners expanded by eff on each side
        out.push(pos_x - w / 2.0 - eff);
        out.push(pos_y - h / 2.0 - eff);
        out.push(pos_x + w / 2.0 + eff);
        out.push(pos_y - h / 2.0 - eff);
        out.push(pos_x - w / 2.0 - eff);
        out.push(pos_y + h / 2.0 + eff);
        out.push(pos_x + w / 2.0 + eff);
        out.push(pos_y + h / 2.0 + eff);
        // 4 edge midpoints
        out.push(pos_x);
        out.push(pos_y - h / 2.0 - eff);
        out.push(pos_x);
        out.push(pos_y + h / 2.0 + eff);
        out.push(pos_x - w / 2.0 - eff);
        out.push(pos_y);
        out.push(pos_x + w / 2.0 + eff);
        out.push(pos_y);
    } else {
        let r = pad_radius + eff_creep - inset;
        for i in 0..sample_count_circle {
            let theta = 2.0 * std::f64::consts::PI * (i as f64) / (sample_count_circle as f64);
            out.push(pos_x + r * math_cos(theta));
            out.push(pos_y + r * math_sin(theta));
        }
    }
    out
}

/// Per-layer creepage-factor application (`effective_creepage` verbatim):
/// outer copper layers carry the full base creepage; inner layers carry
/// base * 0.30.  The layer-set membership test stays in the Python wrapper
/// (it resolves against the board's layer constants).
fn effective_creepage(is_outer: bool, base_creepage_mm: f64) -> f64 {
    if is_outer {
        base_creepage_mm
    } else {
        base_creepage_mm * 0.30
    }
}

/// The spatial fallback of `hv_pad_set` verbatim: filter `positions`
/// (ordered (ref, x, y) triples from dict insertion order) to those within
/// the zone bounds, then return the ref of the closest by squared distance
/// with first-min tie-breaking (Python's `min` keeps the first minimal
/// element — the Rust scan updates only on strict `<`).
fn closest_component_for_zone(
    positions: &[(String, f64, f64)],
    zx: f64,
    zy: f64,
    half_w: f64,
    half_h: f64,
) -> Option<String> {
    let mut best: Option<(&str, f64)> = None;
    for (ref_, px, py) in positions {
        let in_bounds = (zx - half_w) <= *px && *px <= (zx + half_w)
            && (zy - half_h) <= *py && *py <= (zy + half_h);
        if !in_bounds {
            continue;
        }
        let key = math_pow(*px - zx, 2.0) + math_pow(*py - zy, 2.0);
        match best {
            None => best = Some((ref_.as_str(), key)),
            Some((_, best_key)) if key < best_key => best = Some((ref_.as_str(), key)),
            _ => {}
        }
    }
    best.map(|(r, _)| r.to_string())
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

/// Return the grid's column count, or a Python error for non-2D buffers.
#[cfg(feature = "python")]
fn grid_cols(grid: &PyBuffer<i32>) -> PyResult<usize> {
    let shape = grid.shape();
    if shape.len() != 2 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "grid must be a 2D int32 array, got {} dimensions",
            shape.len()
        )));
    }
    Ok(shape[1])
}

#[cfg(feature = "python")]
fn grid_cells<'a>(grid: &'a PyBuffer<i32>, py: Python<'a>) -> PyResult<&'a [Cell<i32>]> {
    grid.as_mut_slice(py).ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(
            "grid must be a writable, C-contiguous int32 array",
        )
    })
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, cx, cy, total_radius, net_id, cell_size_mm, min_row, max_row, min_col, max_col))]
#[expect(clippy::too_many_arguments, reason = "PyO3 boundary mirrors the Python block_circle_into_grid signature 1:1; a config struct would change the FFI")]
pub fn block_circle_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i32>,
    cx: f64,
    cy: f64,
    total_radius: f64,
    net_id: i32,
    cell_size_mm: f64,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let cols = grid_cols(&grid)?;
        let cells = grid_cells(&grid, py)?;
        block_circle_into_grid(
            cells, cols, cx, cy, total_radius, net_id, cell_size_mm, min_row, max_row, min_col, max_col,
        );
        Ok(())
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, x1, y1, x2, y2, total_radius, net_id, cell_size_mm, min_row, max_row, min_col, max_col))]
#[expect(clippy::too_many_arguments, reason = "PyO3 boundary mirrors the Python block_segment_into_grid signature 1:1; a config struct would change the FFI")]
pub fn block_segment_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i32>,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
    total_radius: f64,
    net_id: i32,
    cell_size_mm: f64,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let cols = grid_cols(&grid)?;
        let cells = grid_cells(&grid, py)?;
        block_segment_into_grid(
            cells, cols, x1, y1, x2, y2, total_radius, net_id, cell_size_mm, min_row, max_row, min_col,
            max_col,
        );
        Ok(())
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, net_id, min_row, max_row, min_col, max_col))]
pub fn block_rect_into_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i32>,
    net_id: i32,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let cols = grid_cols(&grid)?;
        let cells = grid_cells(&grid, py)?;
        block_rect_into_grid(cells, cols, net_id, min_row, max_row, min_col, max_col);
        Ok(())
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, cx, cy, radius_mm, cell_size_mm, min_row, max_row, min_col, max_col))]
#[expect(clippy::too_many_arguments, reason = "PyO3 boundary mirrors the Python clear_circle_from_grid signature 1:1; a config struct would change the FFI")]
pub fn clear_circle_from_grid_py(
    py: Python<'_>,
    grid: PyBuffer<i32>,
    cx: f64,
    cy: f64,
    radius_mm: f64,
    cell_size_mm: f64,
    min_row: usize,
    max_row: usize,
    min_col: usize,
    max_col: usize,
) -> PyResult<()> {
    temper_py_bridge::catch_unwind(|| {
        let cols = grid_cols(&grid)?;
        let cells = grid_cells(&grid, py)?;
        clear_circle_from_grid(
            cells, cols, cx, cy, radius_mm, cell_size_mm, min_row, max_row, min_col, max_col,
        );
        Ok(())
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (trace, pad, rows, cols, stride))]
pub fn occupancy_bitmap_row_py(
    py: Python<'_>,
    trace: PyBuffer<i32>,
    pad: PyBuffer<i32>,
    rows: usize,
    cols: usize,
    stride: usize,
) -> PyResult<Vec<u64>> {
    temper_py_bridge::catch_unwind(|| {
        let t_cells = grid_cells(&trace, py)?;
        let p_cells = grid_cells(&pad, py)?;
        Ok(occupancy_bitmap_row(t_cells, p_cells, cols, rows, stride))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (shape, pos_x, pos_y, pad_radius, pad_size_x, pad_size_y, eff_creep, inset, sample_count_circle))]
#[expect(clippy::too_many_arguments, reason = "PyO3 boundary mirrors the Python fence_samples signature 1:1; a config struct would change the FFI")]
pub fn fence_samples_py(
    shape: i64,
    pos_x: f64,
    pos_y: f64,
    pad_radius: f64,
    pad_size_x: f64,
    pad_size_y: f64,
    eff_creep: f64,
    inset: f64,
    sample_count_circle: usize,
) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        Ok(fence_samples(
            shape,
            pos_x,
            pos_y,
            pad_radius,
            pad_size_x,
            pad_size_y,
            eff_creep,
            inset,
            sample_count_circle,
        ))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (is_outer, base_creepage_mm))]
pub fn effective_creepage_py(is_outer: bool, base_creepage_mm: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| effective_creepage(is_outer, base_creepage_mm))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (positions, zx, zy, half_w, half_h))]
pub fn closest_component_for_zone_py(
    positions: Vec<(String, f64, f64)>,
    zx: f64,
    zy: f64,
    half_w: f64,
    half_h: f64,
) -> PyResult<Option<String>> {
    temper_py_bridge::catch_unwind(|| closest_component_for_zone(&positions, zx, zy, half_w, half_h))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn cells_from(v: &[i32]) -> Vec<Cell<i32>> {
        v.iter().map(|&x| Cell::new(x)).collect()
    }

    fn cells_to(v: &[Cell<i32>]) -> Vec<i32> {
        v.iter().map(|c| c.get()).collect()
    }

    #[cfg_attr(test, test)]
    fn test_merge_cell_semantics() {
        assert_eq!(merge_cell(0, 5), 5);
        assert_eq!(merge_cell(5, 5), 5);
        assert_eq!(merge_cell(3, 5), -1);
        assert_eq!(merge_cell(-1, 5), -1);
        assert_eq!(merge_cell(-2, -2), -2);
        assert_eq!(merge_cell(0, -2), -2);
    }

    #[cfg_attr(test, test)]
    fn test_block_circle_blocks_and_conflicts() {
        let cells = cells_from(&[0i32; 100]);
        block_circle_into_grid(&cells, 10, 4.5, 4.5, 1.0, 7, 1.0, 0, 10, 0, 10);
        let g = cells_to(&cells);
        assert_eq!(g[4 * 10 + 4], 7);
        assert_eq!(g[4 * 10 + 3], 7);
        assert_eq!(g[3 * 10 + 3], 0); // diagonal is sqrt(2) away
        // second net on the same circle -> conflict
        block_circle_into_grid(&cells, 10, 4.5, 4.5, 1.0, 9, 1.0, 0, 10, 0, 10);
        let g = cells_to(&cells);
        assert_eq!(g[4 * 10 + 4], -1);
    }

    #[cfg_attr(test, test)]
    fn test_block_rect_is_integer_exact() {
        let cells = cells_from(&[0i32; 25]);
        block_rect_into_grid(&cells, 5, -2, 1, 4, 2, 5);
        let g = cells_to(&cells);
        assert_eq!(g[7], -2);
        assert_eq!(g[3 * 5 + 4], -2);
        assert_eq!(g[0], 0);
        assert_eq!(g[20], 0);
    }

    #[cfg_attr(test, test)]
    fn test_degenerate_segment_clamps_t_to_one() {
        // L2 == 0 -> t = nan -> Python min(1.0, nan) = 1.0 -> circle around
        // the endpoint.  The kernel must reproduce that, not early-return.
        let cells = cells_from(&[0i32; 225]);
        block_segment_into_grid(&cells, 15, 5.0, 5.0, 5.0, 5.0, 2.0, 7, 1.0, 0, 15, 0, 15);
        let g = cells_to(&cells);
        assert_eq!(g[5 * 15 + 5], 7); // centre (5.5, 5.5), dist 0.707 <= 2
        assert_eq!(g[5 * 15 + 4], 7); // centre (4.5, 5.5), dist 0.707 <= 2
        assert_eq!(g[2 * 15 + 5], 0); // centre (2.5, 5.5), dist 2.55 > 2
    }

    #[cfg_attr(test, test)]
    fn test_segment_blocks_along_the_line() {
        let cells = cells_from(&[0i32; 100]);
        block_segment_into_grid(&cells, 10, 0.0, 5.0, 10.0, 5.0, 0.5, 7, 1.0, 0, 10, 0, 10);
        let g = cells_to(&cells);
        assert_eq!(g[5 * 10 + 5], 7); // midpoint of the segment
        assert_eq!(g[5 * 10 + 9], 7); // endpoint cell
        assert_eq!(g[3 * 10 + 5], 0); // a row above the line is free
    }

    #[cfg_attr(test, test)]
    fn test_clear_circle_resets_only_within_radius() {
        let cells = cells_from(&[3i32; 100]);
        clear_circle_from_grid(&cells, 10, 4.5, 4.5, 1.0, 1.0, 0, 10, 0, 10);
        let g = cells_to(&cells);
        assert_eq!(g[4 * 10 + 4], 0);
        assert_eq!(g[4 * 10 + 3], 0);
        assert_eq!(g[3 * 10 + 3], 3); // diagonal outside radius
    }

    #[cfg_attr(test, test)]
    fn test_occupancy_bitmap_words_and_bits() {
        let cols = 130; // stride = (130 + 63) // 64 = 3 words
        let stride = 3;
        let trace = cells_from(&vec![0i32; 20 * cols]);
        let pad = cells_from(&vec![0i32; 20 * cols]);
        trace[3].set(1);
        pad[cols + 63].set(1); // word 0, bit 63
        pad[cols + 64].set(1); // word 1, bit 0
        let bmp = occupancy_bitmap_row(&trace, &pad, cols, 20, stride);
        assert_eq!(bmp.len(), 20 * stride);
        assert_eq!(bmp[0], 1u64 << 3);
        assert_eq!(bmp[stride], 1u64 << 63);
        assert_eq!(bmp[stride + 1], 1u64 << 0);
        assert_eq!(bmp[2 * stride + 2], 0);
    }

    #[cfg_attr(test, test)]
    fn test_fence_samples_circle_angles() {
        let s = fence_samples(0, 10.0, 10.0, 1.0, 0.0, 0.0, 2.0, 0.25, 4);
        assert_eq!(s.len(), 8);
        let r = 1.0 + 2.0 - 0.25;
        // i=0: theta = 0 -> (cx + r, cy)
        assert_eq!(s[0], 10.0 + r * math_cos(0.0));
        assert_eq!(s[1], 10.0 + r * math_sin(0.0));
        // i=2: theta = 2*pi*2/4 = pi -> (cx - r, cy)
        assert_eq!(s[4], 10.0 + r * math_cos(2.0 * std::f64::consts::PI * 2.0 / 4.0));
        assert_eq!(s[5], 10.0 + r * math_sin(2.0 * std::f64::consts::PI * 2.0 / 4.0));
    }

    #[cfg_attr(test, test)]
    fn test_fence_samples_rect_has_eight() {
        let s = fence_samples(2, 0.0, 0.0, 0.0, 4.0, 2.0, 0.5, 0.25, 16);
        assert_eq!(s.len(), 16);
        // corner (cx - w/2 - eff, cy - h/2 - eff)
        assert_eq!(s[0], 0.0 - 2.0 - 0.25);
        assert_eq!(s[1], 0.0 - 1.0 - 0.25);
        // edge midpoints: (cx, cy + h/2 + eff) then (cx - w/2 - eff, cy)
        assert_eq!(s[10], 0.0);
        assert_eq!(s[11], 0.0 + 1.0 + 0.25);
        assert_eq!(s[12], 0.0 - 2.0 - 0.25);
        assert_eq!(s[13], 0.0);
    }

    #[cfg_attr(test, test)]
    fn test_fence_samples_unknown_shape_circle_branch() {
        // Unknown shape codes (e.g. 99) fall to the circle branch, exactly
        // like the old unrecognized-string match.
        assert_eq!(fence_samples(99, 0.0, 0.0, 1.0, 4.0, 2.0, 0.5, 0.0, 4).len(), 8);
        assert_eq!(fence_samples(0, 0.0, 0.0, 1.0, 4.0, 2.0, 0.5, 0.0, 4).len(), 8);
    }

    #[cfg_attr(test, test)]
    fn test_effective_creepage_arms() {
        assert_eq!(effective_creepage(true, 6.0), 6.0);
        assert_eq!(effective_creepage(false, 6.0), 6.0 * 0.30);
        assert_eq!(effective_creepage(false, 0.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn test_closest_component_first_min_and_bounds() {
        let pos = vec![
            ("A".to_string(), 10.0, 0.0),
            ("B".to_string(), 10.0, 0.0), // exact tie with A: A stays first
            ("C".to_string(), 100.0, 100.0), // outside the zone
        ];
        assert_eq!(
            closest_component_for_zone(&pos, 10.0, 0.0, 5.0, 5.0).as_deref(),
            Some("A")
        );
        // C is outside the bounds, so A is picked even though C's zone
        // is closer in raw distance terms only if inside...
        assert_eq!(
            closest_component_for_zone(&pos, 0.0, 0.0, 1.0, 1.0),
            None
        );
        assert_eq!(closest_component_for_zone(&[], 0.0, 0.0, 1.0, 1.0), None);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("grid_raster::tests::test_merge_cell_semantics", test_merge_cell_semantics),
        ("grid_raster::tests::test_block_circle_blocks_and_conflicts", test_block_circle_blocks_and_conflicts),
        ("grid_raster::tests::test_block_rect_is_integer_exact", test_block_rect_is_integer_exact),
        ("grid_raster::tests::test_degenerate_segment_clamps_t_to_one", test_degenerate_segment_clamps_t_to_one),
        ("grid_raster::tests::test_segment_blocks_along_the_line", test_segment_blocks_along_the_line),
        ("grid_raster::tests::test_clear_circle_resets_only_within_radius", test_clear_circle_resets_only_within_radius),
        ("grid_raster::tests::test_occupancy_bitmap_words_and_bits", test_occupancy_bitmap_words_and_bits),
        ("grid_raster::tests::test_fence_samples_circle_angles", test_fence_samples_circle_angles),
        ("grid_raster::tests::test_fence_samples_rect_has_eight", test_fence_samples_rect_has_eight),
        ("grid_raster::tests::test_fence_samples_unknown_shape_circle_branch", test_fence_samples_unknown_shape_circle_branch),
        ("grid_raster::tests::test_effective_creepage_arms", test_effective_creepage_arms),
        ("grid_raster::tests::test_closest_component_first_min_and_bounds", test_closest_component_first_min_and_bounds),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    /// Small net ids (1..99) — keep them in i32 range but away from
    /// conflict sentinels like -1, 0.
    fn net_id() -> impl Strategy<Value = i32> {
        1i32..99
    }

    proptest! {
        // -----------------------------------------------------------------
        // merge_cell
        // -----------------------------------------------------------------

        /// P1. merge_cell(0, n) returns n (free cell accepts first occupant).
        #[test]
        fn p1_merge_cell_free_accepts(n in net_id()) {
            prop_assert_eq!(merge_cell(0, n), n);
        }

        /// P2. merge_cell(n, n) returns n (same net = no change).
        #[test]
        fn p2_merge_cell_same_net_idempotent(n in net_id()) {
            prop_assert_eq!(merge_cell(n, n), n);
        }

        /// P3. merge_cell(a, b) returns -1 when a > 0 and a != b (conflict).
        #[test]
        fn p3_merge_cell_different_positive_nets_conflict(
            a in net_id(), b in net_id(),
        ) {
            prop_assume!(a != b);
            prop_assert_eq!(merge_cell(a, b), -1);
        }

        /// P4. merge_cell(-1, anything) stays -1 (already a conflict).
        #[test]
        fn p4_merge_cell_conflict_is_sticky(n in net_id()) {
            prop_assert_eq!(merge_cell(-1, n), -1);
        }

        // -----------------------------------------------------------------
        // effective_creepage
        // -----------------------------------------------------------------

        /// P5. Outer layers carry the full base creepage unchanged.
        #[test]
        fn p5_effective_creepage_outer_is_identity(base in 0.0f64..100.0) {
            prop_assert_eq!(effective_creepage(true, base), base);
        }

        /// P6. Inner layers carry base * 0.30.
        #[test]
        fn p6_effective_creepage_inner_is_scaled(base in 0.0f64..100.0) {
            prop_assert_eq!(effective_creepage(false, base), base * 0.30);
        }

        // -----------------------------------------------------------------
        // closest_component_for_zone
        // -----------------------------------------------------------------

        /// P7. When positions are empty, result is always None.
        #[test]
        fn p7_closest_component_empty_returns_none(
            zx in -10.0f64..10.0, zy in -10.0f64..10.0,
            hw in 1.0f64..10.0, hh in 1.0f64..10.0,
        ) {
            prop_assert_eq!(closest_component_for_zone(&[], zx, zy, hw, hh), None);
        }

        /// P8. When the result is Some, it equals one of the input refs.
        #[test]
        fn p8_closest_component_result_is_an_input_ref(
            refs in prop::collection::vec("[A-Z][a-z]?", 1..=8),
            xs in prop::collection::vec(-10.0f64..10.0, 1..=8),
            ys in prop::collection::vec(-10.0f64..10.0, 1..=8),
            zx in 0.0f64..2.0,
            zy in 0.0f64..2.0,
        ) {
            // All generated positions are within [-10,10]; use a zone that
            // covers the whole area to guarantee at least one is in-bounds.
            let n = refs.len().min(xs.len()).min(ys.len());
            let positions: Vec<(String, f64, f64)> = (0..n)
                .map(|i| (refs[i].clone(), xs[i], ys[i]))
                .collect();
            if let Some(result) = closest_component_for_zone(&positions, zx, zy, 20.0, 20.0) {
                let matches = positions.iter().any(|(r, _, _)| *r == result);
                prop_assert!(matches, "result '{result}' not in inputs");
            }
        }
    }
}
