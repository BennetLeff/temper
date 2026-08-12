// Configuration-space corridor erosion for width-aware A* routing.
//
// Why this exists (docs/evidence/2026-08-11-track-width-shorting-root-cause.md,
// docs/evidence/2026-08-11-corridor-aware-astar-spike.md): Router V6's A*
// searches the occupancy grid at CENTRELINE resolution -- one free/blocked
// bit per cell -- while `OccupancyGrid.mark_path_blocked` (which delegates
// to `occupancy_raster::mark_path_rect`) marks copper at FULL WIDTH
// (`trace_width / 2 + clearance`, rasterised as a square stamp swept along
// the path -- see `occupancy_raster::mark_point_rect`). A* can therefore
// return a centreline that is clear even though the trace's actual
// footprint, once drawn at width, overlaps existing copper. This is the
// root cause the spike traces `shorting_items`/`track_width` to.
//
// The fix is a standard configuration-space (C-space) erosion: shrink the
// free-space mask by the net's own footprint radius BEFORE A* searches it,
// so any cell A* is allowed to step onto is guaranteed to have its full
// footprint clear. `neighbor_validity.build_neighbor_validity_tensor_2d`
// already accepts a `corridor_mask` for an unrelated reason (coarse-to-fine
// restriction) -- this module produces a mask of the same shape and
// semantics (`True`/`1` = usable) so it can be fed through that same
// parameter without touching the Rust A* kernel at all.
//
// Structuring-element parity with the marking function (load-bearing).
// `mark_path_rect`'s `mark_point_rect` stamps a SQUARE window of half-width
// `expansion = ceil((trace_width / 2 + clearance) / cell_size)` cells
// around each interpolated path point -- a Chebyshev (L-infinity) ball, NOT
// a Euclidean disc and NOT a rotated rectangle (the "rect" in the name
// refers to the per-point stamp shape, not the swept envelope, which is a
// square-capped sausage). Eroding the free mask by that identical square
// window is therefore the EXACT inverse, not an approximation: a cell is a
// valid corridor centre iff every cell `mark_point_rect` would stamp from
// that centre is free. Using a Euclidean disc here instead (the obvious
// first instinct) would disagree with the marking function at the
// corners of the stamp and manufacture a new violation class -- exactly
// the trap the spike's brief warns about.
//
// `expansion_cells_ceil` below reproduces `occupancy_raster::expansion_cells`'s
// `ceil` rounding on the same formula. It is a deliberately independent
// implementation rather than a cross-module call: `occupancy_raster` is
// compiled only under the `python` feature (its whole module doc explains
// why -- it is "pyo3-flavoured throughout"), while this module is
// unconditional so it can be exercised on the `wasm32` test tier. Both
// compute `ceil(radius_mm / cell_size)`; there is no room for the two to
// disagree on a shared one-line formula, but see this module's own tests
// for a same-crate spot-check against hand-computed expectations that
// mirror `mark_point_rect`'s documented behaviour directly.
//
// Own-net exemption. A net's own already-placed copper and its own pads
// share its `net_id` on the grid (see `occupancy_raster.rs`'s marking
// kernels -- `mark_path_rect`/`mark_via_circle` both write `net_id`, never
// a generic "occupied" sentinel). Naively eroding around every nonzero
// cell would mark the net's own start/goal pad cells invalid too -- a
// systematic false "no path" for every net, since every net's own pads are
// always adjacent to its own start/goal search endpoints. `erode_free_mask`
// takes `net_id` and treats a cell as an OBSTACLE only when it is nonzero
// AND not equal to `net_id`; own-net cells are free for this purpose,
// mirroring the existing `cell_value != 0 && cell_value != net_id`
// exemption `router_v6.astar_core._astar_search` already applies to direct
// (non-eroded) occupancy checks for `net_id >= 0` searches.

#[cfg(feature = "python")]
use pyo3::buffer::PyBuffer;
#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyBytes;

/// `ceil(radius_mm / cell_size)`, saturating rather than panicking on
/// non-finite input or a non-positive `cell_size`.
///
/// Unlike `occupancy_raster::expansion_cells`, this does not need to
/// reproduce CPython's `ZeroDivisionError`/`OverflowError` RAISING
/// behaviour -- this module is new capability, not a port of an existing
/// Python function, so there is no reference to stay bit-exact with. It
/// only needs to reproduce the ROUNDING (`ceil`, not `floor`/`round`) --
/// see the module doc comment above for why that specific choice is
/// load-bearing. `f64 as i64` in Rust saturates on NaN (-> 0) and +-inf
/// (-> i64::MAX / i64::MIN) rather than panicking, so the explicit guards
/// below exist for documentation/determinism, not to prevent a panic that
/// could not happen anyway.
pub fn expansion_cells_ceil(radius_mm: f64, cell_size: f64) -> i64 {
    if !radius_mm.is_finite() || !cell_size.is_finite() || cell_size <= 0.0 {
        return 0;
    }
    (radius_mm / cell_size).ceil() as i64
}

/// Erode a net-tagged occupancy grid by a square (Chebyshev) structuring
/// element of half-width `expansion` cells, exempting `net_id` from the
/// obstacle set.
///
/// `grid` is row-major `height_cells * width_cells`, using the same value
/// convention as `OccupancyGrid.grid`: `0` = free, `net_id` = that net's
/// own copper/pads, anything else nonzero (another net's `net_id`, or the
/// `-1` static-obstacle sentinel) = an obstacle for this erosion.
///
/// Returns a `height_cells * width_cells` mask (row-major, `1` = valid
/// corridor cell: a trace footprint centred here touches no obstacle;
/// `0` = invalid).
///
/// A footprint window that extends past the grid boundary is treated as
/// free out there, not blocked: `mark_point_rect` clamps its own writes to
/// the grid bounds (see `occupancy_raster.rs`), so nothing can ever
/// actually be marked outside the array -- there is nothing for an
/// out-of-bounds footprint to collide with. This is the OPPOSITE
/// convention from `downsample_or_blocks`, which treats out-of-bounds as
/// blocked for an unrelated, conservative reason (see that function's own
/// doc comment) -- the two are deliberately different, not inconsistent.
///
/// Implemented as a 2D summed-area table over the obstacle mask, so the
/// cost is `O(width_cells * height_cells)` regardless of `expansion` (no
/// per-cell window loop over `(2*expansion+1)^2` cells).
pub fn erode_free_mask(
    grid: &[i8],
    width_cells: usize,
    height_cells: usize,
    net_id: i64,
    expansion: i64,
) -> Vec<u8> {
    if width_cells == 0 || height_cells == 0 {
        return Vec::new();
    }
    let w = width_cells;
    let h = height_cells;
    debug_assert_eq!(grid.len(), w * h);

    // (h+1) x (w+1) summed-area table with a zero border, so every
    // rectangle sum below is exactly 4 lookups with no row/col-0
    // special-casing.
    let mut sat = vec![0i64; (h + 1) * (w + 1)];
    for r in 0..h {
        let mut row_sum = 0i64;
        let sat_row = r * (w + 1);
        let sat_row_next = (r + 1) * (w + 1);
        for c in 0..w {
            let v = grid[r * w + c] as i64;
            let is_obstacle = v != 0 && v != net_id;
            row_sum += is_obstacle as i64;
            sat[sat_row_next + c + 1] = sat[sat_row + c + 1] + row_sum;
        }
    }

    let e = expansion.max(0) as usize;
    let mut out = vec![0u8; h * w];
    for r in 0..h {
        let r1 = r.saturating_sub(e);
        let r2 = r.saturating_add(e).min(h - 1);
        for c in 0..w {
            let c1 = c.saturating_sub(e);
            let c2 = c.saturating_add(e).min(w - 1);
            let sum = sat[(r2 + 1) * (w + 1) + (c2 + 1)]
                - sat[r1 * (w + 1) + (c2 + 1)]
                - sat[(r2 + 1) * (w + 1) + c1]
                + sat[r1 * (w + 1) + c1];
            out[r * w + c] = (sum == 0) as u8;
        }
    }
    out
}

/// Convenience: `erode_free_mask` with the expansion radius derived from
/// `(trace_width, clearance, cell_size)` the exact same way
/// `occupancy_raster::mark_path_rect` derives it
/// (`radius_mm = trace_width / 2.0 + clearance`, then `ceil` to cells) --
/// see the module doc comment for why this parity is load-bearing.
pub fn corridor_mask_for_net(
    grid: &[i8],
    width_cells: usize,
    height_cells: usize,
    net_id: i64,
    trace_width: f64,
    clearance: f64,
    cell_size: f64,
) -> Vec<u8> {
    let radius_mm = trace_width / 2.0 + clearance;
    let expansion = expansion_cells_ceil(radius_mm, cell_size);
    erode_free_mask(grid, width_cells, height_cells, net_id, expansion)
}

#[cfg(feature = "python")]
fn grid_shape(grid: &PyBuffer<i8>) -> PyResult<(usize, usize)> {
    let shape = grid.shape();
    if shape.len() != 2 {
        return Err(PyValueError::new_err(format!(
            "grid must be a 2D int8 array, got {} dimensions",
            shape.len()
        )));
    }
    Ok((shape[0], shape[1])) // (rows/height, cols/width)
}

/// Read-only flattened copy of the grid buffer. Mirrors
/// `occupancy_raster::blocking_net_ids_py`'s own read-only pattern: a
/// writable `PyBuffer` is requested (the only kind `self.grid`, an int8
/// numpy array, ever presents) but only ever read here via `Cell::get()`,
/// which copies -- no aliasing hazard from treating the interior mutably.
#[cfg(feature = "python")]
fn grid_flat(grid: &PyBuffer<i8>, py: Python<'_>) -> PyResult<Vec<i8>> {
    let cells = grid
        .as_mut_slice(py)
        .ok_or_else(|| PyValueError::new_err("grid must be a writable, C-contiguous int8 array"))?;
    Ok(cells.iter().map(|c| c.get()).collect())
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (grid, net_id, trace_width, clearance, cell_size))]
pub fn corridor_mask_for_net_py<'py>(
    py: Python<'py>,
    grid: PyBuffer<i8>,
    net_id: i64,
    trace_width: f64,
    clearance: f64,
    cell_size: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let (rows, cols) = grid_shape(&grid)?;
    let flat = grid_flat(&grid, py)?;
    let mask = temper_py_bridge::catch_unwind(|| {
        corridor_mask_for_net(&flat, cols, rows, net_id, trace_width, clearance, cell_size)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    PyBytes::new_with(py, mask.len(), |b| {
        b.copy_from_slice(&mask);
        Ok(())
    })
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // expansion_cells_ceil
    // -----------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_expansion_cells_ceil_rounds_up() {
        // 1.05mm / 0.1mm cell = 10.5 -> ceil -> 11, not 10 (floor) or 10
        // (round-to-even).
        assert_eq!(expansion_cells_ceil(1.05, 0.1), 11);
    }

    #[cfg_attr(test, test)]
    fn test_expansion_cells_ceil_exact_division_no_extra_cell() {
        assert_eq!(expansion_cells_ceil(1.0, 0.1), 10);
    }

    #[cfg_attr(test, test)]
    fn test_expansion_cells_ceil_zero_radius_is_zero_cells() {
        assert_eq!(expansion_cells_ceil(0.0, 0.1), 0);
    }

    #[cfg_attr(test, test)]
    fn test_expansion_cells_ceil_saturates_on_nonfinite_instead_of_panicking() {
        assert_eq!(expansion_cells_ceil(f64::NAN, 0.1), 0);
        assert_eq!(expansion_cells_ceil(1.0, 0.0), 0);
        assert_eq!(expansion_cells_ceil(1.0, -0.1), 0);
        assert_eq!(expansion_cells_ceil(f64::INFINITY, 0.1), 0);
    }

    // -----------------------------------------------------------------
    // erode_free_mask -- own-net exemption (the false-negative trap the
    // spike brief calls out by name).
    // -----------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_own_net_pad_is_exempt_from_erosion() {
        // 7x7 grid, all free except a 3x3 block of net 5's own pad in the
        // centre. Eroding by expansion=1 for net_id=5: the pad cells and
        // their immediate free neighbours must all stay valid, because a
        // net's own copper is never an obstacle to itself.
        let w = 7;
        let h = 7;
        let mut grid = vec![0i8; w * h];
        for r in 2..5 {
            for c in 2..5 {
                grid[r * w + c] = 5;
            }
        }
        let mask = erode_free_mask(&grid, w, h, 5, 1);
        // Centre of the pad: valid (own net).
        assert_eq!(mask[3 * w + 3], 1, "own-net pad centre must stay valid");
        // A free cell one step outside the pad, whose (2*1+1)=3-wide
        // window is entirely free-or-own-net: valid.
        assert_eq!(mask[w + 1], 1);
        // Far corner, fully free: valid.
        assert_eq!(mask[0], 1);
    }

    #[cfg_attr(test, test)]
    fn test_other_net_pad_is_not_exempt() {
        // Same layout, but erosion runs for a DIFFERENT net (7): the 3x3
        // block belonging to net 5 is a real obstacle now, and cells whose
        // window would touch it are invalid.
        let w = 7;
        let h = 7;
        let mut grid = vec![0i8; w * h];
        for r in 2..5 {
            for c in 2..5 {
                grid[r * w + c] = 5;
            }
        }
        let mask = erode_free_mask(&grid, w, h, 7, 1);
        assert_eq!(mask[3 * w + 3], 0, "inside a different net's pad: invalid");
        // (1,1)'s 3x3 window is rows/cols 0..=2 -- touches row 2, which is
        // the pad's own top edge starting at col 2 -- (1,1)'s window
        // reaches col 0..=2 too, so it touches grid[2][2] == 5: invalid.
        assert_eq!(mask[w + 1], 0);
        // Far corner: still valid, its window never reaches the pad.
        assert_eq!(mask[0], 1);
    }

    #[cfg_attr(test, test)]
    fn test_static_obstacle_sentinel_is_never_exempt() {
        // net_id can never legitimately be the static sentinel (-1), but
        // erosion must still treat -1 as an obstacle regardless of which
        // net is searching -- board-outline/keepout cells are never
        // "this net's own copper".
        let w = 3;
        let h = 3;
        let mut grid = vec![0i8; w * h];
        grid[w + 1] = -1;
        let mask = erode_free_mask(&grid, w, h, 5, 1);
        assert!(mask.iter().all(|&v| v == 0), "every cell's window touches the static obstacle");
    }

    // -----------------------------------------------------------------
    // erode_free_mask -- out-of-bounds is free, not blocked (the opposite
    // convention from downsample_or_blocks; see the module doc comment).
    // -----------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_out_of_bounds_footprint_does_not_invalidate_edge_cells() {
        // Entirely free 3x3 grid, huge expansion: every window extends far
        // past the grid on all sides, but nothing out there can ever be
        // marked (mark_point_rect clamps its own writes), so every cell
        // stays valid.
        let w = 3;
        let h = 3;
        let grid = vec![0i8; w * h];
        let mask = erode_free_mask(&grid, w, h, 1, 100);
        assert!(mask.iter().all(|&v| v == 1));
    }

    // -----------------------------------------------------------------
    // erode_free_mask -- square (Chebyshev) structuring element, exact
    // window boundary (the corner-disagreement trap vs. a Euclidean disc).
    // -----------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_structuring_element_is_square_not_disc() {
        // A single obstacle cell at the ORIGIN corner of a large free
        // grid, expansion=2. A Euclidean-disc erosion would exempt a
        // diagonal cell at Chebyshev distance 2 but Euclidean distance
        // 2*sqrt(2) =~ 2.83 (i.e. treat (2,2) as outside a radius-2 disc);
        // the square structuring element used here does not -- (2,2) is
        // exactly 2 cells away on BOTH axes, inside the 5x5 window
        // centred there, so it must be invalidated.
        let w = 9;
        let h = 9;
        let mut grid = vec![0i8; w * h];
        grid[0] = 7; // obstacle at (row=0, col=0), some other net
        let mask = erode_free_mask(&grid, w, h, 1, 2);
        // (2,2): window rows/cols 0..=4 -> touches (0,0): invalid.
        assert_eq!(mask[2 * w + 2], 0, "diagonal cell within Chebyshev radius must be invalid");
        // (3,3): window rows/cols 1..=5 -> does NOT touch (0,0): valid.
        assert_eq!(mask[3 * w + 3], 1, "diagonal cell outside Chebyshev radius must be valid");
        // (0,2): window rows 0..=2, cols 0..=4 -> touches (0,0): invalid.
        // A Euclidean disc of radius 2 would also invalidate this cardinal
        // case (distance exactly 2) -- it is the DIAGONAL case above that
        // is the actual disc-vs-square discriminator; this one is just an
        // ordinary correctness check on the window bounds.
        assert_eq!(mask[2], 0);
    }

    // -----------------------------------------------------------------
    // erode_free_mask vs. a naive O(w*h*(2e+1)^2) reference -- the
    // summed-area-table implementation is an optimisation, not a
    // different algorithm; this pins the two together over a handful of
    // hand-built, non-trivial grids.
    // -----------------------------------------------------------------

    fn erode_free_mask_naive(
        grid: &[i8],
        width_cells: usize,
        height_cells: usize,
        net_id: i64,
        expansion: i64,
    ) -> Vec<u8> {
        let w = width_cells as i64;
        let h = height_cells as i64;
        let e = expansion.max(0);
        let mut out = vec![0u8; width_cells * height_cells];
        for r in 0..h {
            for c in 0..w {
                let mut valid = true;
                'window: for dr in -e..=e {
                    for dc in -e..=e {
                        let rr = r + dr;
                        let cc = c + dc;
                        if rr < 0 || rr >= h || cc < 0 || cc >= w {
                            continue; // out of bounds: free, per the module doc.
                        }
                        let v = grid[(rr as usize) * width_cells + (cc as usize)] as i64;
                        if v != 0 && v != net_id {
                            valid = false;
                            break 'window;
                        }
                    }
                }
                out[(r as usize) * width_cells + (c as usize)] = valid as u8;
            }
        }
        out
    }

    #[cfg_attr(test, test)]
    fn test_sat_implementation_matches_naive_reference() {
        // A handful of small, irregular grids: scattered obstacles from
        // several different nets, plus the static sentinel, at a few
        // different expansion radii.
        let w = 11;
        let h = 9;
        let mut grid = vec![0i8; w * h];
        let obstacles: &[(usize, usize, i8)] = &[
            (0, 0, 3),
            (0, 10, 3),
            (8, 0, -1),
            (4, 5, 7),
            (4, 6, 7),
            (5, 5, 7),
            (1, 3, 5),
            (2, 9, -1),
            (7, 7, 5),
        ];
        for &(r, c, v) in obstacles {
            grid[r * w + c] = v;
        }
        for &net_id in &[0i64, 5, 7, -1, 99] {
            for &expansion in &[0i64, 1, 2, 3, 5] {
                let got = erode_free_mask(&grid, w, h, net_id, expansion);
                let want = erode_free_mask_naive(&grid, w, h, net_id, expansion);
                assert_eq!(
                    got, want,
                    "mismatch at net_id={net_id} expansion={expansion}"
                );
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_empty_grid_dimensions_return_empty_mask() {
        assert_eq!(erode_free_mask(&[], 0, 0, 1, 2), Vec::<u8>::new());
        assert_eq!(erode_free_mask(&[], 5, 0, 1, 2), Vec::<u8>::new());
    }

    // -----------------------------------------------------------------
    // corridor_mask_for_net -- the (trace_width, clearance, cell_size) ->
    // expansion pipeline end to end.
    // -----------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_corridor_mask_for_net_matches_manual_expansion() {
        // trace_width=2.0mm, clearance=0.5mm -> radius_mm=1.5,
        // cell_size=0.5mm -> expansion=ceil(3.0)=3. Cross-checked against
        // calling erode_free_mask directly with expansion=3.
        let w = 15;
        let h = 15;
        let mut grid = vec![0i8; w * h];
        grid[7 * w + 7] = 9; // some other net, dead centre
        let via_helper = corridor_mask_for_net(&grid, w, h, 1, 2.0, 0.5, 0.5);
        let direct = erode_free_mask(&grid, w, h, 1, 3);
        assert_eq!(via_helper, direct);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("corridor_erosion::tests::test_expansion_cells_ceil_rounds_up", test_expansion_cells_ceil_rounds_up),
        ("corridor_erosion::tests::test_expansion_cells_ceil_exact_division_no_extra_cell", test_expansion_cells_ceil_exact_division_no_extra_cell),
        ("corridor_erosion::tests::test_expansion_cells_ceil_zero_radius_is_zero_cells", test_expansion_cells_ceil_zero_radius_is_zero_cells),
        ("corridor_erosion::tests::test_expansion_cells_ceil_saturates_on_nonfinite_instead_of_panicking", test_expansion_cells_ceil_saturates_on_nonfinite_instead_of_panicking),
        ("corridor_erosion::tests::test_own_net_pad_is_exempt_from_erosion", test_own_net_pad_is_exempt_from_erosion),
        ("corridor_erosion::tests::test_other_net_pad_is_not_exempt", test_other_net_pad_is_not_exempt),
        ("corridor_erosion::tests::test_static_obstacle_sentinel_is_never_exempt", test_static_obstacle_sentinel_is_never_exempt),
        ("corridor_erosion::tests::test_out_of_bounds_footprint_does_not_invalidate_edge_cells", test_out_of_bounds_footprint_does_not_invalidate_edge_cells),
        ("corridor_erosion::tests::test_structuring_element_is_square_not_disc", test_structuring_element_is_square_not_disc),
        ("corridor_erosion::tests::test_sat_implementation_matches_naive_reference", test_sat_implementation_matches_naive_reference),
        ("corridor_erosion::tests::test_empty_grid_dimensions_return_empty_mask", test_empty_grid_dimensions_return_empty_mask),
        ("corridor_erosion::tests::test_corridor_mask_for_net_matches_manual_expansion", test_corridor_mask_for_net_matches_manual_expansion),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
