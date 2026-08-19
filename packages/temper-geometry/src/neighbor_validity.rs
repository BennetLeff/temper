//! Neighbor-validity tensor construction for Router V6 A*.
//!
//! Rust port of `router_v6/neighbor_validity.py`'s
//! `build_neighbor_validity_tensor_2d`.  The pinned Python oracle lives at
//! `packages/temper-placer/tests/router_v6/_neighbor_validity_py_oracle.py`
//! and `test_neighbor_validity_rust_differential.py` proves this kernel
//! reproduces it BIT-IDENTICALLY on the production board's own occupancy
//! grids.
//!
//! # What the tensor means
//!
//! `tensor[r, c, d]` is true iff moving from cell `(row=r, col=c)` in
//! direction `d` lands on a free, in-bounds cell — where "free" means the
//! occupancy grid holds 0 there, and (when a corridor mask is supplied) the
//! destination is also inside the corridor.  Direction encoding matches the
//! router's 8-move convention, `DIRS_8` in the Python module:
//! 0=E, 1=SE, 2=S, 3=SW, 4=W, 5=NW, 6=N, 7=NE, as `(dx, dy)` where `dx`
//! steps the COLUMN and `dy` steps the ROW.
//!
//! # Why this is a port and not a rewrite
//!
//! The Python builds the tensor with eight full-grid numpy slice
//! assignments, one per direction.  Each writes into `tensor[..., d]`,
//! which is a stride-8 destination, and each materialises its own
//! `dst == 0` temporary.  On this board's real F.Cu grid (2380 x 1680) that
//! is ~30 MB of output touched eight times through a strided writer, plus
//! eight ~4 MB temporaries.  Measured on a full production route: 752 calls,
//! 8.81 s.
//!
//! This kernel computes all eight directions for a cell together and writes
//! them as eight CONTIGUOUS bytes, so the output is written once, in order.
//! The bounds checks are hoisted out of the hot path by splitting the grid
//! into an interior (every neighbour in bounds) and its border.
//!
//! # Exact-reproduction notes
//!
//! * The Python zero-initialises the tensor and only fills the sub-rectangle
//!   of SOURCE cells whose destination is in bounds; every other entry stays
//!   false.  This kernel writes `false` for those entries explicitly, which
//!   is the same result for a caller-zeroed or caller-arbitrary buffer.
//! * `grid` is compared against 0 as `i8`.  The Python compares the raw
//!   `int8` occupancy array against 0, so net ids (positive) and the
//!   static-obstacle sentinel (-1) are both "occupied", identically.
//! * The corridor mask is a numpy `bool_` array viewed as `uint8`; any
//!   non-zero byte is "in corridor", matching numpy's truthiness.

use std::cell::Cell;

/// `(dx, dy)` per direction index — dx steps the column, dy steps the row.
/// Must stay identical to `neighbor_validity.DIRS_8`.
pub const DIRS_8: [(i64, i64); 8] = [
    (1, 0),   // 0: E
    (1, 1),   // 1: SE
    (0, 1),   // 2: S
    (-1, 1),  // 3: SW
    (-1, 0),  // 4: W
    (-1, -1), // 5: NW
    (0, -1),  // 6: N
    (1, -1),  // 7: NE
];

/// Build the `(rows, cols, 8)` neighbor-validity tensor into `out`.
///
/// `grid` is the row-major `(rows, cols)` occupancy array; `corridor` is an
/// optional row-major `(rows, cols)` mask.  `out` must be `rows * cols * 8`
/// bytes and is fully written (every entry assigned, none left stale).
///
/// Returns `Err` with a message when the slice lengths disagree with
/// `rows`/`cols` — a caller passing a mismatched buffer is a programming
/// error the FFI layer turns into a Python exception rather than reading
/// out of bounds.
pub fn build_neighbor_validity_tensor_2d(
    grid: &[i8],
    rows: usize,
    cols: usize,
    corridor: Option<&[u8]>,
    out: &mut [u8],
) -> Result<(), String> {
    let n = rows.checked_mul(cols).ok_or("rows * cols overflows usize")?;
    if grid.len() != n {
        return Err(format!("grid has {} cells, expected {rows}*{cols}={n}", grid.len()));
    }
    if let Some(m) = corridor {
        if m.len() != n {
            return Err(format!("corridor mask has {} cells, expected {n}", m.len()));
        }
    }
    let want = n.checked_mul(8).ok_or("rows * cols * 8 overflows usize")?;
    if out.len() != want {
        return Err(format!("out has {} bytes, expected {want}", out.len()));
    }
    if n == 0 {
        return Ok(());
    }

    // Fuse "unoccupied" and "in corridor" into one byte per cell, so the
    // eight per-direction reads below are a single indexed load each.
    let mut free: Vec<u8> = Vec::with_capacity(n);
    match corridor {
        Some(mask) => {
            for i in 0..n {
                free.push(u8::from(grid[i] == 0 && mask[i] != 0));
            }
        }
        None => {
            for i in 0..n {
                free.push(u8::from(grid[i] == 0));
            }
        }
    }

    // `Cell::from_mut(..).as_slice_of_cells()` is a SAFE std conversion, so
    // the one hot loop below serves both this `&mut [u8]` entry point (tests,
    // wasm) and the pyo3 path, which only ever has `&[Cell<u8>]` because
    // that is what `PyBuffer::as_mut_slice` hands back.  Writing the loop
    // once against `Cell` avoids both a duplicated implementation and the
    // scratch-buffer-plus-copy the first version of this port used -- that
    // version measured SLOWER than the numpy it replaced (10.54 s vs 8.81 s
    // over a full route) precisely because of the extra 32 MB pass.
    fill_from_free(&free, rows, cols, Cell::from_mut(out).as_slice_of_cells());
    Ok(())
}

/// The hot loop: turn the per-cell `free` byte array into the
/// `(rows, cols, 8)` tensor, writing eight CONTIGUOUS bytes per cell.
///
/// Split into an interior (every neighbour in bounds, no per-direction
/// bounds check) and its border.  `out` is written in full.
fn fill_from_free(free: &[u8], rows: usize, cols: usize, out: &[Cell<u8>]) {
    let icols = cols as i64;
    let irows = rows as i64;

    for r in 0..rows {
        let interior_row = r > 0 && r + 1 < rows;
        let row_base = r * cols;
        for c in 0..cols {
            let base = (row_base + c) * 8;
            if interior_row && c > 0 && c + 1 < cols {
                let idx = row_base + c;
                let up = idx - cols;
                let dn = idx + cols;
                out[base].set(free[idx + 1]); // E
                out[base + 1].set(free[dn + 1]); // SE
                out[base + 2].set(free[dn]); // S
                out[base + 3].set(free[dn - 1]); // SW
                out[base + 4].set(free[idx - 1]); // W
                out[base + 5].set(free[up - 1]); // NW
                out[base + 6].set(free[up]); // N
                out[base + 7].set(free[up + 1]); // NE
            } else {
                for (d, (dx, dy)) in DIRS_8.iter().enumerate() {
                    let nr = r as i64 + dy;
                    let nc = c as i64 + dx;
                    let v = if nr >= 0 && nr < irows && nc >= 0 && nc < icols {
                        free[(nr as usize) * cols + (nc as usize)]
                    } else {
                        0
                    };
                    out[base + d].set(v);
                }
            }
        }
    }
}

#[cfg(feature = "python")]
use pyo3::buffer::PyBuffer;
#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Read side: `as_slice` yields `ReadOnlyCell`s.
#[cfg(feature = "python")]
fn buf_read<'a, T: pyo3::buffer::Element>(
    buf: &'a PyBuffer<T>,
    py: Python<'a>,
) -> PyResult<&'a [pyo3::buffer::ReadOnlyCell<T>]> {
    buf.as_slice(py)
        .ok_or_else(|| PyValueError::new_err("buffer is not C-contiguous"))
}

/// Write side: `as_mut_slice` yields writable `Cell`s (same shape
/// `occupancy_raster.rs`'s `grid_cells` uses for in-place grid mutation).
#[cfg(feature = "python")]
fn buf_write<'a, T: pyo3::buffer::Element>(
    buf: &'a PyBuffer<T>,
    py: Python<'a>,
) -> PyResult<&'a [std::cell::Cell<T>]> {
    buf.as_mut_slice(py)
        .ok_or_else(|| PyValueError::new_err("out buffer is not writable/C-contiguous"))
}

/// Fill a caller-allocated `(rows, cols, 8)` `uint8` buffer with the
/// neighbor-validity tensor.
///
/// The output buffer is allocated on the PYTHON side and written in place —
/// the same zero-copy `PyBuffer` shape `occupancy_raster.rs`'s
/// `mark_path_rect_into_grid_py` already uses for the write direction.
/// Returning a `Vec<u8>` instead would add a full ~30 MB Rust allocation
/// plus a copy into a `PyBytes` on every call, which is most of what this
/// port exists to remove.
///
/// `grid` is the `int8` occupancy array, `out` a writable `uint8` buffer of
/// `rows * cols * 8` bytes, `corridor_mask` an optional `uint8` view of the
/// bool corridor mask.  Shapes are taken from `rows`/`cols` and validated
/// against every buffer's length.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, rows, cols, out, corridor_mask=None))]
pub fn build_neighbor_validity_tensor_2d_py(
    py: Python<'_>,
    grid: PyBuffer<i8>,
    rows: usize,
    cols: usize,
    out: PyBuffer<u8>,
    corridor_mask: Option<PyBuffer<u8>>,
) -> PyResult<()> {
    if out.readonly() {
        return Err(PyValueError::new_err("out buffer is read-only"));
    }
    temper_py_bridge::catch_unwind(|| {
        let g = buf_read(&grid, py)?;
        let o = buf_write(&out, py)?;
        let n = rows
            .checked_mul(cols)
            .ok_or_else(|| PyValueError::new_err("rows * cols overflows usize"))?;
        if g.len() != n {
            return Err(PyValueError::new_err(format!(
                "grid has {} cells, expected {rows}*{cols}={n}",
                g.len()
            )));
        }
        let want = n
            .checked_mul(8)
            .ok_or_else(|| PyValueError::new_err("rows * cols * 8 overflows usize"))?;
        if o.len() != want {
            return Err(PyValueError::new_err(format!(
                "out has {} bytes, expected {want}",
                o.len()
            )));
        }
        // Build `free` straight off the Python buffers: no intermediate copy
        // of the grid, and -- crucially -- no scratch copy of the ~32 MB
        // output.  The tensor is written ONCE, directly into the numpy
        // array Python allocated.
        let mut free: Vec<u8> = Vec::with_capacity(n);
        match &corridor_mask {
            Some(b) => {
                let m = buf_read(b, py)?;
                if m.len() != n {
                    return Err(PyValueError::new_err(format!(
                        "corridor mask has {} cells, expected {n}",
                        m.len()
                    )));
                }
                for i in 0..n {
                    free.push(u8::from(g[i].get() == 0 && m[i].get() != 0));
                }
            }
            None => {
                for i in 0..n {
                    free.push(u8::from(g[i].get() == 0));
                }
            }
        }
        if n > 0 {
            fill_from_free(&free, rows, cols, o);
        }
        Ok(())
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_neighbor_validity_tensor_2d_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
#[allow(clippy::indexing_slicing)]
pub(crate) mod tests {
    use super::*;

    /// Straightforward transcription of the Python's per-cell meaning, used
    /// as an in-crate reference for the optimised interior/border split.
    fn reference(
        grid: &[i8],
        rows: usize,
        cols: usize,
        corridor: Option<&[u8]>,
    ) -> Vec<u8> {
        let mut out = vec![0u8; rows * cols * 8];
        for r in 0..rows {
            for c in 0..cols {
                for (d, (dx, dy)) in DIRS_8.iter().enumerate() {
                    let nr = r as i64 + dy;
                    let nc = c as i64 + dx;
                    let ok = nr >= 0
                        && (nr as usize) < rows
                        && nc >= 0
                        && (nc as usize) < cols
                        && grid[(nr as usize) * cols + nc as usize] == 0
                        && corridor
                            .is_none_or(|m| m[(nr as usize) * cols + nc as usize] != 0);
                    out[(r * cols + c) * 8 + d] = u8::from(ok);
                }
            }
        }
        out
    }

    fn lcg(seed: &mut u64) -> u64 {
        *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        *seed >> 33
    }

    #[cfg_attr(test, test)]
    fn matches_reference_on_random_grids() {
        let mut seed = 0x5eed_1234u64;
        for &(rows, cols) in &[
            (1usize, 1usize),
            (1, 7),
            (7, 1),
            (2, 2),
            (3, 3),
            (5, 9),
            (17, 13),
        ] {
            for use_mask in [false, true] {
                let grid: Vec<i8> = (0..rows * cols)
                    .map(|_| match lcg(&mut seed) % 3 {
                        0 => 0i8,
                        1 => 7i8,
                        _ => -1i8,
                    })
                    .collect();
                let mask: Vec<u8> = (0..rows * cols)
                    .map(|_| u8::from(lcg(&mut seed) % 2 == 0))
                    .collect();
                let m = if use_mask { Some(mask.as_slice()) } else { None };
                let want = reference(&grid, rows, cols, m);
                let mut got = vec![0xAAu8; rows * cols * 8];
                build_neighbor_validity_tensor_2d(&grid, rows, cols, m, &mut got)
                    .unwrap_or_else(|e| panic!("kernel failed: {e}"));
                assert_eq!(
                    got, want,
                    "mismatch at rows={rows} cols={cols} use_mask={use_mask}"
                );
            }
        }
    }

    #[cfg_attr(test, test)]
    fn fully_occupied_grid_has_no_valid_moves() {
        let (rows, cols) = (6usize, 5usize);
        let grid = vec![3i8; rows * cols];
        let mut out = vec![1u8; rows * cols * 8];
        build_neighbor_validity_tensor_2d(&grid, rows, cols, None, &mut out)
            .unwrap_or_else(|e| panic!("kernel failed: {e}"));
        assert!(out.iter().all(|&b| b == 0), "occupied grid reported a valid move");
    }

    #[cfg_attr(test, test)]
    fn free_interior_cell_has_all_eight_moves() {
        let (rows, cols) = (3usize, 3usize);
        let grid = vec![0i8; rows * cols];
        let mut out = vec![0u8; rows * cols * 8];
        build_neighbor_validity_tensor_2d(&grid, rows, cols, None, &mut out)
            .unwrap_or_else(|e| panic!("kernel failed: {e}"));
        let centre = (cols + 1) * 8;
        assert!(
            out[centre..centre + 8].iter().all(|&b| b == 1),
            "centre of a free 3x3 should have all 8 moves valid"
        );
        // A corner (0,0) can only move E, SE, S.
        assert_eq!(&out[0..8], &[1, 1, 1, 0, 0, 0, 0, 0]);
    }

    #[cfg_attr(test, test)]
    fn length_mismatch_is_an_error_not_a_panic() {
        let grid = vec![0i8; 9];
        let mut out = vec![0u8; 9 * 8];
        assert!(build_neighbor_validity_tensor_2d(&grid, 3, 4, None, &mut out).is_err());
        let mut short = vec![0u8; 4];
        assert!(build_neighbor_validity_tensor_2d(&grid, 3, 3, None, &mut short).is_err());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("neighbor_validity::tests::matches_reference_on_random_grids", matches_reference_on_random_grids),
        ("neighbor_validity::tests::fully_occupied_grid_has_no_valid_moves", fully_occupied_grid_has_no_valid_moves),
        ("neighbor_validity::tests::free_interior_cell_has_all_eight_moves", free_interior_cell_has_all_eight_moves),
        ("neighbor_validity::tests::length_mismatch_is_an_error_not_a_panic", length_mismatch_is_an_error_not_a_panic),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
