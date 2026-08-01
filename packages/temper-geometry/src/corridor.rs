// Corridor mask extraction — coarse-to-fine routing corridor.
//
// Python reference: temper_placer/router_v6/corridor.py
//
// Given a coarse path (list of (col, row) coarse cells), produces a
// boolean mask on the fine grid defining the routing corridor: each
// coarse cell maps to its fine-grid rectangle, expanded by
// buffer_cells in every direction and clamped to the fine grid.
// Returns the mask as bytes (1 byte per cell, 0/1) so the Python
// wrapper can build a numpy bool view via np.frombuffer.

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use temper_py_bridge;

#[pyfunction]
#[pyo3(signature = (coarse_path, coarse_factor, buffer_cells, fine_rows, fine_cols))]
pub fn extract_corridor_mask(
    py: Python<'_>,
    coarse_path: Vec<i64>,
    coarse_factor: i64,
    buffer_cells: i64,
    fine_rows: usize,
    fine_cols: usize,
) -> PyResult<Bound<'_, PyBytes>> {
    // The caller flattens its (col, row) pairs into one int array; pair
    // them back up here. (Bit-exact with the old Vec<(i64, i64)> — the
    // element order is unchanged.)
    let path: Vec<(i64, i64)> = coarse_path
        .chunks_exact(2)
        .map(|c| (c[0], c[1]))
        .collect();
    let mask = temper_py_bridge::catch_unwind(|| {
        corridor_mask(path, coarse_factor, buffer_cells, fine_rows, fine_cols)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    PyBytes::new_with(py, mask.len(), |b| {
        b.copy_from_slice(&mask);
        Ok(())
    })
}

/// Pure-Rust mask computation (1 byte per fine cell, 0/1), kept separate
/// from the pyo3 boundary so unit tests run without libpython.
fn corridor_mask(
    coarse_path: Vec<(i64, i64)>,
    coarse_factor: i64,
    buffer_cells: i64,
    fine_rows: usize,
    fine_cols: usize,
) -> Vec<u8> {
    let mut mask = vec![0u8; fine_rows * fine_cols];
    // Collect the per-row column intervals from every coarse cell, then
    // sort+merge them and fill each row once. The mask is 0/1 and fills
    // are idempotent, so writing the merged union of intervals per row is
    // byte-identical to writing every interval individually.
    let mut rows: Vec<Vec<(usize, usize)>> = (0..fine_rows).map(|_| Vec::new()).collect();
    for (cx, cy) in coarse_path {
        let r0 = (cy * coarse_factor - buffer_cells).max(0) as usize;
        let r1 = wrap_clamp((cy + 1) * coarse_factor + buffer_cells, fine_rows);
        let c0 = (cx * coarse_factor - buffer_cells).max(0) as usize;
        let c1 = wrap_clamp((cx + 1) * coarse_factor + buffer_cells, fine_cols);
        if r0 < r1 && c0 < c1 {
            for row in rows.iter_mut().take(r1).skip(r0) {
                row.push((c0, c1));
            }
        }
    }
    for (r, mut intervals) in rows.into_iter().enumerate() {
        if intervals.is_empty() {
            continue;
        }
        intervals.sort_unstable();
        let base = r * fine_cols;
        let mut s = intervals[0].0;
        let mut e = intervals[0].1;
        for &(cs, ce) in &intervals[1..] {
            if cs <= e {
                // Overlaps (or touches) the running interval — extend it.
                e = e.max(ce);
            } else {
                mask[base + s..base + e].fill(1);
                s = cs;
                e = ce;
            }
        }
        mask[base + s..base + e].fill(1);
    }
    mask
}

/// Python-slice semantics for a bound: negative bounds wrap relative to
/// the length (numpy `mask[r0:r1]` with a negative `r1` counts from the
/// end); then clamp into [0, len]. Matches the numpy oracle exactly,
/// including the wrap domain — a raw `max(0)` here would silently
/// diverge from the reference for `buffer_cells < -(cy+1)*factor`.
fn wrap_clamp(bound: i64, len: usize) -> usize {
    let len_i = len as i64;
    let wrapped = if bound < 0 { len_i + bound } else { bound };
    wrapped.clamp(0, len_i) as usize
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mask_to_grid(mask: &[u8], rows: usize, cols: usize) -> Vec<Vec<bool>> {
        (0..rows)
            .map(|r| (0..cols).map(|c| mask[r * cols + c] == 1).collect())
            .collect()
    }

    #[test]
    fn test_single_cell_rectangle() {
        // Coarse (2,3), factor 4, buffer 0 -> fine rows 12..16, cols 8..12
        let mask = corridor_mask(vec![(2, 3)], 4, 0, 100, 200);
        let grid = mask_to_grid(&mask, 100, 200);
        assert!(grid[12][8] && grid[15][11]);
        assert!(!grid[11][8] && !grid[16][8] && !grid[12][7]);
    }

    #[test]
    fn test_buffer_expansion() {
        // Coarse (0,0), factor 4, buffer 2 -> fine 0..6 both axes
        let mask = corridor_mask(vec![(0, 0)], 4, 2, 100, 100);
        let grid = mask_to_grid(&mask, 100, 100);
        assert!(grid[0][0] && grid[5][5]);
        assert!(!grid[6][6]);
    }

    #[test]
    fn test_clamping_at_grid_bounds() {
        // Huge buffer -> whole grid covered
        let mask = corridor_mask(vec![(0, 0)], 4, 100, 10, 10);
        assert!(mask.iter().all(|&v| v == 1));
    }

    #[test]
    fn test_empty_path() {
        let mask = corridor_mask(vec![], 4, 2, 100, 200);
        assert!(mask.iter().all(|&v| v == 0));
    }

    #[test]
    fn test_multi_cell_or_accumulates() {
        let mask = corridor_mask(vec![(0, 0), (1, 1)], 4, 0, 20, 20);
        let grid = mask_to_grid(&mask, 20, 20);
        assert!(grid[0][0] && grid[4][4] && grid[5][5]);
        assert!(!grid[10][10]);
    }

    #[test]
    fn test_mask_is_symmetric_under_path_reversal() {
        let path = vec![(0, 0), (0, 1), (1, 1), (2, 0)];
        let a = corridor_mask(path.clone(), 4, 2, 40, 40);
        let mut rev = path;
        rev.reverse();
        let b = corridor_mask(rev, 4, 2, 40, 40);
        assert_eq!(a, b);
    }

    #[test]
    fn test_negative_buffer_below_underflow_wraps_like_numpy() {
        // buffer -5 with cy=0, factor 4 -> r1 = 4-5 = -1 -> numpy slice
        // bound -1 wraps to rows-1: rect rows 5..9, cols 5..9.
        let mask = corridor_mask(vec![(0, 0)], 4, -5, 10, 10);
        let grid = mask_to_grid(&mask, 10, 10);
        assert!(!grid[4][4]);
        assert!(grid[5][5]);
        assert!(grid[8][8]);
        assert!(!grid[9][9]); // -1 is exclusive -> row 9 excluded
    }

    #[test]
    fn test_negative_buffer_below_grid_length_wraps_to_empty() {
        // buffer -12 with factor 4: r1 = -8 -> wraps to rows-8 = 2 < r0=12
        // -> empty rect (numpy mask[12:-8] is empty).
        let mask = corridor_mask(vec![(0, 0)], 4, -12, 10, 10);
        assert!(mask.iter().all(|&v| v == 0));
    }
}
