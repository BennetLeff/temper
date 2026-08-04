//! Copper-coverage grid kernels (Wave 4, Phase 4).
//!
//! Ports the grid arithmetic of
//! `temper_placer/physics/copper_coverage.py::copper_coverage_grid`
//! (issue #137 — the per-cell effective copper fraction [0, 1] the
//! thermal FDM solver consumes) to Rust: the board-area / keepout /
//! mounting-hole circle MASKS and the per-trace
//! `np.minimum(1.0, grid + cell_cov)` accumulation.  The Python module
//! keeps its public API (`copper_coverage_grid`,
//! `check_thermal_plausibility`, `SANITY_CEILING_C`), the polygon
//! rasterisation boundary (`temper_geometry`), the trace-object
//! introspection (`_trace_layer_match`), and the final weighted-sum /
//! fraction / clip numpy lines; the mask and trace-accumulation
//! arithmetic delegate here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! - **B1 (host libm via dlsym):** `(cx - mx) ** 2` on a numpy array
//!   with an INT exponent dispatches to numpy's per-element power,
//!   measured bit-identical to host libm `pow(x, 2.0)` (2026-08-04;
//!   note `np.power(a, 2.0)` with a FLOAT exponent is numpy's x*x path
//!   and is NOT libm — the reference here uses the int-exponent form).
//!   `kr ** 2` on a Python float is libm `pow` too.  Both resolve via
//!   `hostmath`.
//! - **B7 (f64 operation order):** cell centres are
//!   `ox + ((col + 0.5) * cs)` — the numpy `(col_idx + 0.5) * cs + ox`
//!   order; `(cx - mx)**2 + (cy - my)**2 < kr**2` keeps the
//!   parenthesized power sums.  Rect bounds compare with IEEE `<=`.
//! - **`np.minimum` NaN semantics:** `np.minimum(1.0, x)` propagates
//!   NaN from either operand; the trace-accumulation kernel implements
//!   that explicitly (Rust `f64::min` would discard NaN).
//! - **Iteration order:** the mask accumulation is order-independent
//!   (bool OR); the trace path accumulates per trace in the caller's
//!   list order, exactly like the reference.
//!
//! R24: N/A as a *constraint encoding* — the copper fraction is an
//! input FIELD the FDM solver consumes, not a CP-SAT constraint gating
//! on a physics quantity.  The applicable contract is bit-exact parity
//! (R1a); the field's [0, 1] boundedness is asserted by the PBT suite.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyBytes;
#[cfg(feature = "python")]
use temper_py_bridge;

use crate::hostmath;

/// Build the board-area / keepout / active-area masks for a
/// `(height_cells, width_cells)` grid.  Mirrors `copper_coverage_grid`
/// verbatim:
///
/// - Cell centres: `cx = ox + ((col as f64 + 0.5) * cs)`,
///   `cy = oy + ((row as f64 + 0.5) * cs)` (the numpy
///   `ox + (col_idx + 0.5) * cs` broadcast shape, evaluated per
///   element).
/// - `inside_board`: when `has_polygon` is set, the caller-provided
///   rasterised polygon mask (`(h, w)` bool bytes, one byte per cell,
///   1 = inside) is used directly; otherwise the rect compare
///   `cx >= ox && cx <= ox + board_w && cy >= oy && cy <= oy + board_h`
///   (board_w/board_h are the board width/height).
/// - `in_keepout`: any keepout rect `(kx0, ky0, kx1, ky1)` contains
///   the cell centre (`kx0 <= cx <= kx1 && ky0 <= cy <= ky1`), or any
///   mounting hole `(mx, my, keepout_radius)` circle satisfies
///   `pow(cx - mx, 2.0) + pow(cy - my, 2.0) < pow(kr, 2.0)` (B1 pow,
///   B7 grouping) — accumulated with bool OR in list order.
/// - `active_area = inside_board && !in_keepout`.
///
/// Returns `(inside_bytes, keepout_bytes, active_bytes)` — one byte
/// per cell (0/1).
#[expect(clippy::too_many_arguments)]
pub fn copper_masks(
    height_cells: usize,
    width_cells: usize,
    ox: f64,
    oy: f64,
    cs: f64,
    board_w: f64,
    board_h: f64,
    has_polygon: bool,
    polygon_mask: &[u8],
    keepouts: &[f64],
    holes: &[f64],
) -> (Vec<u8>, Vec<u8>, Vec<u8>) {
    let h = height_cells;
    let w = width_cells;
    let n = h * w;
    let mut inside = vec![0u8; n];
    let mut keepout = vec![0u8; n];

    for r in 0..h {
        for c in 0..w {
            let idx = r * w + c;
            let cx = ox + (c as f64 + 0.5) * cs;
            let cy = oy + (r as f64 + 0.5) * cs;

            // inside_board
            let in_board = if has_polygon {
                polygon_mask[idx] != 0
            } else {
                cx >= ox && cx <= ox + board_w && cy >= oy && cy <= oy + board_h
            };
            if in_board {
                inside[idx] = 1;
            }

            // keepout rects
            let mut in_ko = false;
            for k in keepouts.chunks_exact(4) {
                if k[0] <= cx && cx <= k[2] && k[1] <= cy && cy <= k[3] {
                    in_ko = true;
                    break;
                }
            }
            // mounting-hole circles: (cx - mx)**2 + (cy - my)**2 < kr**2.
            // Measured 2026-08-04: numpy's `** 2` on an ARRAY with an
            // integer exponent dispatches to the x*x multiply path
            // (bit-identical to a*a, NOT libm pow), while `kr**2` on a
            // Python float is libm pow.  The kernel mirrors both
            // exactly — mul for the array offsets (B7), host libm pow
            // for the scalar radius (B1).
            if !in_ko {
                for hole in holes.chunks_exact(3) {
                    let (mx, my, kr) = (hole[0], hole[1], hole[2]);
                    let dx = cx - mx;
                    let dy = cy - my;
                    let d2 = dx * dx + dy * dy;
                    if d2 < hostmath::pow(kr, 2.0) {
                        in_ko = true;
                        break;
                    }
                }
            }
            if in_ko {
                keepout[idx] = 1;
            }
        }
    }

    let mut active = vec![0u8; n];
    for i in 0..n {
        active[i] = inside[i] & (keepout[i] ^ 1);
    }
    (inside, keepout, active)
}

/// Per-trace copper-accumulation: `grid = np.minimum(1.0, grid +
/// cell_cov)` with the reference's NaN semantics (NaN propagates from
/// either operand — `np.minimum(1.0, nan) == nan`, measured 2026-08-04;
/// Rust `f64::min` would discard it).  `grid`/`cell_cov` are
/// little-endian f64 arrays of equal length; returns the updated grid.
pub fn copper_trace_accumulate(grid: &[f64], cell_cov: &[f64]) -> Vec<f64> {
    let n = grid.len();
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let t = grid[i] + cell_cov[i];
        out.push(if t.is_nan() {
            f64::NAN
        } else if t > 1.0 {
            1.0
        } else {
            t
        });
    }
    out
}

fn to_bytes<'py>(py: Python<'py>, vals: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    PyBytes::new_with(py, vals.len(), |b| {
        b.copy_from_slice(vals);
        Ok(())
    })
}

fn f64_to_bytes<'py>(py: Python<'py>, vals: &[f64]) -> PyResult<Bound<'py, PyBytes>> {
    let mut out = Vec::with_capacity(vals.len() * 8);
    for v in vals {
        out.extend_from_slice(&v.to_le_bytes());
    }
    PyBytes::new_with(py, out.len(), |b| {
        b.copy_from_slice(&out);
        Ok(())
    })
}

fn parse_f64s(bytes: &[u8]) -> Vec<f64> {
    debug_assert_eq!(bytes.len() % 8, 0);
    bytes
        .chunks_exact(8)
        .map(|c| {
            let mut a = [0u8; 8];
            a.copy_from_slice(c);
            f64::from_le_bytes(a)
        })
        .collect()
}

/// pyo3 bridge for [`copper_masks`].  `polygon_mask` is `None` when
/// the board has no polygon outline (rect compare is used);
/// `keepouts` is a flat `[kx0, ky0, kx1, ky1, ...]`; `holes` a flat
/// `[mx, my, keepout_radius, ...]`.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (height_cells, width_cells, ox, oy, cs, board_w, board_h, has_polygon, polygon_mask, keepouts, holes))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python reference signature"
)]
pub fn copper_masks_py(
    py: Python<'_>,
    height_cells: usize,
    width_cells: usize,
    ox: f64,
    oy: f64,
    cs: f64,
    board_w: f64,
    board_h: f64,
    has_polygon: bool,
    polygon_mask: Option<Vec<u8>>,
    keepouts: Vec<f64>,
    holes: Vec<f64>,
) -> PyResult<(Bound<'_, PyBytes>, Bound<'_, PyBytes>, Bound<'_, PyBytes>)> {
    let pm = polygon_mask.unwrap_or_default();
    let (inside, keepout, active) = temper_py_bridge::catch_unwind(|| {
        copper_masks(
            height_cells, width_cells, ox, oy, cs, board_w, board_h, has_polygon, &pm, &keepouts,
            &holes,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok((to_bytes(py, &inside)?, to_bytes(py, &keepout)?, to_bytes(py, &active)?))
}

/// pyo3 bridge for [`copper_trace_accumulate`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (trace_grid_bytes, cell_cov_bytes))]
pub fn copper_trace_accumulate_py(
    py: Python<'_>,
    trace_grid_bytes: Vec<u8>,
    cell_cov_bytes: Vec<u8>,
) -> PyResult<Bound<'_, PyBytes>> {
    let grid = parse_f64s(&trace_grid_bytes);
    let cov = parse_f64s(&cell_cov_bytes);
    let out = temper_py_bridge::catch_unwind(|| copper_trace_accumulate(&grid, &cov))
        .map_err(temper_py_bridge::panic_to_err)?;
    f64_to_bytes(py, &out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rect_inside_board() {
        // 4x4 grid, cs=1, origin (0,0), board 4x4 → every cell inside.
        let (inside, _, active) = copper_masks(4, 4, 0.0, 0.0, 1.0, 4.0, 4.0, false, &[], &[], &[]);
        assert!(inside.iter().all(|&b| b == 1));
        assert!(active.iter().all(|&b| b == 1));
    }

    #[test]
    fn keepout_rect_excludes_cells() {
        // Keepout covering the bottom-left 2x2 cells of a 4x4 grid.
        let (_, keepout, active) = copper_masks(4, 4, 0.0, 0.0, 1.0, 4.0, 4.0, false, &[], &[0.0, 0.0, 2.0, 2.0], &[]);
        assert_eq!(keepout[0], 1); // cell (0,0) centre (0.5, 0.5) inside
        assert_eq!(keepout[4], 1); // cell (0,1) centre (1.5, 0.5) inside
        assert_eq!(keepout[2], 0); // cell (0,2) centre (2.5, 0.5) outside
        assert_eq!(active[0], 0);
        assert_eq!(active[2], 1);
    }

    #[test]
    fn hole_circle_excludes() {
        // Hole at (0.5, 0.5) with radius 1.0 covers cell (0,0) only.
        let (_, keepout, _) = copper_masks(4, 4, 0.0, 0.0, 1.0, 4.0, 4.0, false, &[], &[], &[0.5, 0.5, 1.0]);
        assert_eq!(keepout[0], 1);
        assert_eq!(keepout[1], 0);
        assert_eq!(keepout[4], 0);
    }

    #[test]
    fn polygon_mask_passthrough() {
        // has_polygon → the caller's mask is used verbatim.
        let mut pm = vec![0u8; 16];
        pm[0] = 1;
        pm[7] = 1;
        let (inside, _, _) = copper_masks(4, 4, 0.0, 0.0, 1.0, 100.0, 100.0, true, &pm, &[], &[]);
        assert_eq!(inside[0], 1);
        assert_eq!(inside[7], 1);
        assert_eq!(inside[1], 0);
    }

    #[test]
    fn trace_accumulate_min_caps_at_one() {
        let g = vec![0.3, 0.8, 0.0];
        let c = vec![0.2, 0.4, 0.0];
        let out = copper_trace_accumulate(&g, &c);
        assert_eq!(out, vec![0.5, 1.0, 0.0]);
    }

    #[test]
    fn trace_accumulate_nan_propagates() {
        // np.minimum(1.0, x) propagates NaN from either operand.
        let g = vec![f64::NAN, 0.5];
        let c = vec![0.5, f64::NAN];
        let out = copper_trace_accumulate(&g, &c);
        assert!(out[0].is_nan());
        assert!(out[1].is_nan());
    }
}
