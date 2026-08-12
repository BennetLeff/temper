// Residual leaf compute of the D3 clearance-grid cluster (Rust Orchestration
// Engine plan 2026-08-09-001, Phase D batch D3) — the three pieces of the
// `ClearanceGrid` container and the grid stage that were STILL Python after
// the rasterisation kernels moved to `grid_raster.rs`:
//
//   temper_placer/deterministic/stages/_grid_core.py:
//     - `blocked_count` / `blocked_count_on_layer` (the `np.sum(arr != 0)`
//       reductions) -> `count_blocked_cells` / `count_blocked_cells_py`;
//     - `is_available`'s per-sample cell read -> `grid_cell_available` /
//       `grid_cell_available_py`;
//   temper_placer/deterministic/stages/_grid_stage.py (EXP-13 exclusion
//   zone blocking, reproduced in temper-orchestration `grid_stage.rs`):
//     - the per-cell `if curr == 0 or curr == net_id: arr[row, col] = -2`
//       numpy-write loop -> `block_exclusion_zone` /
//       `block_exclusion_zone_into_grid_py`.
//
// These are the *conservatism* paths of the creepage/HV-clearance safety
// contract: `blocked_count` drives the U2 expansion-log `cells_added`
// bookkeeping, `is_available` is the U3 fence's per-sample availability
// assertion, and the exclusion zone is the EXP-13 signal-avoidance block.
//
// Conservative-bound argument (restated, R24-adjacent): every one of these
// three is a monotone write/reduction over the grid, never an under-report.
// `blocked_count` counts *every* non-zero cell (a superset of any routing
// obstacle); `is_available` returns false on any non-zero cell whose id is
// not the caller's own net (a cell the caller could route through is only
// declared free when both arrays are exactly 0 for that net — it can never
// under-state blockage); `block_exclusion_zone` only ever *writes* -2 (it
// converts free/own-net cells to obstacle, it never clears a cell, so the
// exclusion zone can only over-block).  All three are integer-exact — the
// only float is the `x / cell` mm->cell coordinate conversion, whose
// truncation (`int()` / `as i64`, both toward zero) is bit-identical — so
// the differential pins them bit-exactly against the Python oracle.
//
// What stays Python: `ClearanceGrid` itself (the numpy-backed container,
// net-id registration, bbox computation, `get_net_id`), the exception
// classes, and `_EXPANSION_LOG` — the same orchestration/bookkeeping split
// `grid_raster.rs` already documents.

#[cfg(feature = "python")]
use pyo3::buffer::PyBuffer;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::cell::Cell;
#[cfg(feature = "python")]
use temper_py_bridge;

// ---------------------------------------------------------------------------
// Pure kernels (no pyo3, unit-testable without libpython)
// ---------------------------------------------------------------------------

/// Count the blocked cells in one layer (`blocked_count_on_layer`'s inner
/// reduction, verbatim): the number of non-zero cells in `trace` plus the
/// number of non-zero cells in `pad`.  Integer-exact by construction.
fn count_blocked_cells(trace: &[Cell<i32>], pad: &[Cell<i32>]) -> i64 {
    let trace_count = trace.iter().filter(|c| c.get() != 0).count() as i64;
    let pad_count = pad.iter().filter(|c| c.get() != 0).count() as i64;
    trace_count + pad_count
}

/// `ClearanceGrid.is_available`'s per-sample cell read, verbatim.  The layer
/// bounds check (`layer < 0 or layer >= layer_count`) and the `net_name ->
/// net_id` resolution stay in the Python wrapper (the latter touches the
/// container's net registry); this kernel receives the layer's two arrays,
/// the grid dimensions, the mm coordinate and the already-resolved
/// `net_id` (None when the caller passed no net).
///
/// `row = int(y / cell)` / `col = int(x / cell)`: Python `int()` truncates
/// toward zero, exactly like the `as i64` cast here (both operate on the
/// same IEEE-754 division, so the quotient is bit-identical and the
/// truncation agrees for every finite in-range value).
#[expect(clippy::too_many_arguments, reason = "verbatim port of is_available's body; a config struct would change the ported signature")]
fn grid_cell_available(
    trace: &[Cell<i32>],
    pad: &[Cell<i32>],
    cols: usize,
    rows: usize,
    cell_size_mm: f64,
    x_mm: f64,
    y_mm: f64,
    net_id: Option<i32>,
) -> bool {
    let row = (y_mm / cell_size_mm) as i64;
    let col = (x_mm / cell_size_mm) as i64;
    if row < 0 || row >= rows as i64 || col < 0 || col >= cols as i64 {
        return false; // out of bounds == blocked
    }
    let idx = row as usize * cols + col as usize;
    let t_id = trace[idx].get();
    if t_id != 0 && Some(t_id) != net_id {
        return false;
    }
    let p_id = pad[idx].get();
    !(p_id != 0 && Some(p_id) != net_id)
}

/// The EXP-13 exclusion-zone write loop (`_grid_stage.py` verbatim): for each
/// cell in the bbox, write -2 when the cell is free (`0`) or already belongs
/// to the excluded net (`net_id`) — allowing an HV net to route through its
/// own exclusion zone — and leave every other occupied value untouched.
/// Integer-only, exact by construction.  Distinct from `merge_cell`: it never
/// writes a conflict (-1).
fn block_exclusion_zone(
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
            let cur = grid[idx].get();
            if cur == 0 || cur == net_id {
                grid[idx].set(-2);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

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
#[pyo3(signature = (trace, pad))]
pub fn count_blocked_cells_py(
    py: Python<'_>,
    trace: PyBuffer<i32>,
    pad: PyBuffer<i32>,
) -> PyResult<i64> {
    temper_py_bridge::catch_unwind(|| {
        let t_cells = grid_cells(&trace, py)?;
        let p_cells = grid_cells(&pad, py)?;
        Ok(count_blocked_cells(t_cells, p_cells))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (trace, pad, rows, cols, cell_size_mm, x_mm, y_mm, net_id))]
#[expect(clippy::too_many_arguments, reason = "PyO3 boundary mirrors the Python is_available signature 1:1")]
pub fn grid_cell_available_py(
    py: Python<'_>,
    trace: PyBuffer<i32>,
    pad: PyBuffer<i32>,
    rows: usize,
    cols: usize,
    cell_size_mm: f64,
    x_mm: f64,
    y_mm: f64,
    net_id: Option<i32>,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        let t_cells = grid_cells(&trace, py)?;
        let p_cells = grid_cells(&pad, py)?;
        Ok(grid_cell_available(
            t_cells,
            p_cells,
            cols,
            rows,
            cell_size_mm,
            x_mm,
            y_mm,
            net_id,
        ))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, net_id, min_row, max_row, min_col, max_col))]
pub fn block_exclusion_zone_into_grid_py(
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
        block_exclusion_zone(cells, cols, net_id, min_row, max_row, min_col, max_col);
        Ok(())
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn cells_from(v: &[i32]) -> Vec<Cell<i32>> {
        v.iter().map(|&x| Cell::new(x)).collect()
    }

    #[cfg_attr(test, test)]
    fn test_count_blocked_cells_counts_trace_and_pad() {
        let trace = cells_from(&[0, 1, 0, -1, 2, 0, 0, 0]);
        let pad = cells_from(&[0, 0, 3, 0, 0, -2, 0, 5]);
        // trace non-zero: 1, -1, 2 -> 3; pad non-zero: 3, -2, 5 -> 3.
        assert_eq!(count_blocked_cells(&trace, &pad), 6);
    }

    #[cfg_attr(test, test)]
    fn test_count_blocked_cells_empty_is_zero() {
        let empty = cells_from(&[0, 0, 0]);
        assert_eq!(count_blocked_cells(&empty, &empty), 0);
    }

    #[cfg_attr(test, test)]
    fn test_grid_cell_available_free_cell() {
        let trace = cells_from(&[0i32; 100]);
        let pad = cells_from(&[0i32; 100]);
        // centre of cell (4, 4) with cell size 1.0 -> x=4.5, y=4.5.
        assert!(grid_cell_available(&trace, &pad, 10, 10, 1.0, 4.5, 4.5, None));
    }

    #[cfg_attr(test, test)]
    fn test_grid_cell_available_own_net_transparent() {
        let trace = cells_from(&[0i32; 100]);
        let pad = cells_from(&[0i32; 100]);
        trace[4 * 10 + 4].set(3);
        assert!(grid_cell_available(&trace, &pad, 10, 10, 1.0, 4.5, 4.5, Some(3)));
        assert!(!grid_cell_available(&trace, &pad, 10, 10, 1.0, 4.5, 4.5, Some(7)));
        assert!(!grid_cell_available(&trace, &pad, 10, 10, 1.0, 4.5, 4.5, None));
    }

    #[cfg_attr(test, test)]
    fn test_grid_cell_available_out_of_bounds_blocked() {
        let trace = cells_from(&[0i32; 100]);
        let pad = cells_from(&[0i32; 100]);
        // -1.5 truncates toward zero to col -1 (< 0); 10.5 to row 10 (>= 10).
        assert!(!grid_cell_available(&trace, &pad, 10, 10, 1.0, -1.5, 5.5, None));
        assert!(!grid_cell_available(&trace, &pad, 10, 10, 1.0, 5.5, 10.5, None));
    }

    #[cfg_attr(test, test)]
    fn test_block_exclusion_zone_marks_free_and_own_net() {
        let cells = cells_from(&[0, 5, 7, 0, 5, 5, 0, 0, 0]);
        // 3x3 grid, net_id 5, whole grid bbox.
        block_exclusion_zone(&cells, 3, 5, 0, 3, 0, 3);
        // free -> -2; net_id 5 -> -2; other net 7 untouched.
        assert_eq!(cells[0].get(), -2);
        assert_eq!(cells[1].get(), -2);
        assert_eq!(cells[2].get(), 7);
        assert_eq!(cells[4].get(), -2);
    }

    #[cfg_attr(test, test)]
    fn test_block_exclusion_zone_respects_bbox() {
        let cells = cells_from(&[0i32; 25]);
        block_exclusion_zone(&cells, 5, 3, 1, 3, 1, 4);
        // bbox rows 1..3, cols 1..4 blocked; outside untouched.
        assert_eq!(cells[0].get(), 0); // (0,0) free
        assert_eq!(cells[6].get(), -2);
        assert_eq!(cells[2 * 5 + 3].get(), -2);
        assert_eq!(cells[2 * 5 + 4].get(), 0); // col 4 outside
        assert_eq!(cells[3 * 5 + 2].get(), 0); // row 3 outside
    }

    #[cfg_attr(test, test)]
    fn test_block_exclusion_zone_idempotent() {
        let cells = cells_from(&[0, 5, 7, 0, 5, 0, 9, 0, 0]);
        block_exclusion_zone(&cells, 3, 5, 0, 3, 0, 3);
        let after_first: Vec<i32> = cells.iter().map(|c| c.get()).collect();
        block_exclusion_zone(&cells, 3, 5, 0, 3, 0, 3);
        let after_second: Vec<i32> = cells.iter().map(|c| c.get()).collect();
        assert_eq!(after_first, after_second);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("grid_leaf::tests::test_count_blocked_cells_counts_trace_and_pad", test_count_blocked_cells_counts_trace_and_pad),
        ("grid_leaf::tests::test_count_blocked_cells_empty_is_zero", test_count_blocked_cells_empty_is_zero),
        ("grid_leaf::tests::test_grid_cell_available_free_cell", test_grid_cell_available_free_cell),
        ("grid_leaf::tests::test_grid_cell_available_own_net_transparent", test_grid_cell_available_own_net_transparent),
        ("grid_leaf::tests::test_grid_cell_available_out_of_bounds_blocked", test_grid_cell_available_out_of_bounds_blocked),
        ("grid_leaf::tests::test_block_exclusion_zone_marks_free_and_own_net", test_block_exclusion_zone_marks_free_and_own_net),
        ("grid_leaf::tests::test_block_exclusion_zone_respects_bbox", test_block_exclusion_zone_respects_bbox),
        ("grid_leaf::tests::test_block_exclusion_zone_idempotent", test_block_exclusion_zone_idempotent),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
