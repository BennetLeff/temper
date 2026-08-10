// Wave 4 Phase B: temper_placer/heuristics/structural.py's `create_keepout_mask`
// (survey: the largest pure-compute block in `heuristics/`, and the only
// substantial numpy-array kernel in that package -- everything else in
// `heuristics/` is netlist/regex orchestration around a handful of scalar
// arithmetic calls).
//
// Python reference: `create_keepout_mask` in
// `packages/temper-placer/src/temper_placer/heuristics/structural.py`
// (pinned verbatim at `packages/temper-placer/tests/heuristics/_structural_py_oracle.py`).
// The Python module keeps its public API and delegates the mask
// construction to `keepout_mask_flags_py`; board/constraints field
// extraction and numpy array construction stay Python (orchestration).
//
// Bit-exactness notes (see the oracle file for the full trap catalogue):
//
// - `int(x)` truncates toward zero. Rust's `f64 as i64` cast ALSO
//   truncates toward zero (not floor) for finite in-range values, so a
//   plain `as i64` cast reproduces CPython's `int()` here -- there is no
//   discrepancy to work around, unlike the `int(math.ceil(x))` trap
//   elsewhere in this program.
// - The margin edge fill (`mask[:margin_cells, :] = False`, etc.) only
//   runs behind `if margin_cells > 0`, mirrored exactly below with the
//   same guard rather than a general slice-normalization helper.
// - The mounting-hole and keepout-region loops are NOT so simple: the
//   region loop computes `mx_max = min(width_cells, int(...) + 1)`, which
//   can be **negative** for a keepout region whose buffered edge lies to
//   the left of / above the board. A Python slice `mask[a:b]` with a
//   negative `b` is NOT "clamp to zero" -- it means "count back from the
//   end" (`b += length`, then clamp to 0). `normalize_slice_bound` below
//   replicates that exactly; using a naive `.max(0)` instead would
//   silently keep cells that Python discards (or vice versa) whenever a
//   keepout region's computed bound goes negative. This is mutation-tested
//   by `test_negative_region_bound_counts_from_end`.
// - Every operation in this function only ever clears bits (never sets one
//   back to `true`), so unlike the JIT rasterisation kernels in
//   `grid_raster.rs` the three keepout sources (margin, holes, regions)
//   compose order-independently -- their union is the same regardless of
//   application order. The Rust kernel still applies them in the same
//   order as the Python source for auditability.

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Normalize one bound of a Python `step=1` slice index against a
/// dimension of length `length`: negative values count back from the end
/// (clamped to 0), non-negative values clamp to `length`. Used for the
/// keepout-region loop's `mx_min`/`mx_max`/`my_min`/`my_max`, which the
/// Python source computes with `max(0, ...)` / `min(width_cells, ...)`
/// but which can still end up negative on the `min(...)` side.
fn normalize_slice_bound(raw: i64, length: i64) -> usize {
    let v = if raw < 0 {
        (raw + length).max(0)
    } else {
        raw.min(length)
    };
    v as usize
}

/// Pure kernel for `create_keepout_mask` (no pyo3, unit-testable without
/// libpython). `width_cells` x `height_cells` must match the caller's
/// `mask` allocation (`int(board.width/resolution_mm)+1` x
/// `int(board.height/resolution_mm)+1`, computed Python-side since it also
/// sizes the numpy array).
///
/// Returns a fresh `height_cells * width_cells` row-major bool vector,
/// `true` = valid placement, mirroring `np.ones(...)` followed by the
/// three keepout passes.
#[expect(
    clippy::too_many_arguments,
    reason = "mirrors the Python create_keepout_mask signature 1:1; a config struct would obscure the field-by-field trap notes above"
)]
pub fn keepout_mask_flags(
    width_cells: usize,
    height_cells: usize,
    ox: f64,
    oy: f64,
    resolution_mm: f64,
    board_margin_mm: f64,
    buffer_mm: f64,
    mounting_holes: &[(f64, f64, f64)],
    keepout_regions: &[(f64, f64, f64, f64)],
) -> Vec<bool> {
    let mut mask = vec![true; height_cells * width_cells];
    let w = width_cells;
    let h = height_cells;

    // Mark board edges as invalid (margin).
    let margin = board_margin_mm + buffer_mm;
    let margin_cells = (margin / resolution_mm) as i64;

    if margin_cells > 0 {
        let mc = margin_cells as usize;
        // Top rows: mask[:margin_cells, :] = False
        for row in 0..mc.min(h) {
            for col in 0..w {
                mask[row * w + col] = false;
            }
        }
        // Bottom rows: mask[-margin_cells:, :] = False
        let bottom_start = h.saturating_sub(mc);
        for row in bottom_start..h {
            for col in 0..w {
                mask[row * w + col] = false;
            }
        }
        // Left cols: mask[:, :margin_cells] = False
        for row in 0..h {
            for col in 0..mc.min(w) {
                mask[row * w + col] = false;
            }
        }
        // Right cols: mask[:, -margin_cells:] = False
        let right_start = w.saturating_sub(mc);
        for row in 0..h {
            for col in right_start..w {
                mask[row * w + col] = false;
            }
        }
    }

    // Mark mounting holes as invalid (circular keepout).
    for &(hx, hy, keepout_radius) in mounting_holes {
        let clearance = keepout_radius + buffer_mm;
        let cx = ((hx - ox) / resolution_mm) as i64;
        let cy = ((hy - oy) / resolution_mm) as i64;
        let cr = (clearance / resolution_mm) as i64;

        let mut dy = -cr;
        while dy <= cr {
            let mut dx = -cr;
            while dx <= cr {
                if dx * dx + dy * dy <= cr * cr {
                    let mx = cx + dx;
                    let my = cy + dy;
                    if mx >= 0 && (mx as usize) < w && my >= 0 && (my as usize) < h {
                        let idx = (my as usize) * w + (mx as usize);
                        mask[idx] = false;
                    }
                }
                dx += 1;
            }
            dy += 1;
        }
    }

    // Mark explicit keepout regions as invalid.
    for &(x_min, y_min, x_max, y_max) in keepout_regions {
        let x_min_buf = x_min - buffer_mm;
        let y_min_buf = y_min - buffer_mm;
        let x_max_buf = x_max + buffer_mm;
        let y_max_buf = y_max + buffer_mm;

        let mx_min_raw = (0i64).max(((x_min_buf - ox) / resolution_mm) as i64);
        let my_min_raw = (0i64).max(((y_min_buf - oy) / resolution_mm) as i64);
        let mx_max_raw = (w as i64).min(((x_max_buf - ox) / resolution_mm) as i64 + 1);
        let my_max_raw = (h as i64).min(((y_max_buf - oy) / resolution_mm) as i64 + 1);

        let mx_min = normalize_slice_bound(mx_min_raw, w as i64);
        let mx_max = normalize_slice_bound(mx_max_raw, w as i64);
        let my_min = normalize_slice_bound(my_min_raw, h as i64);
        let my_max = normalize_slice_bound(my_max_raw, h as i64);

        if mx_min < mx_max && my_min < my_max {
            for row in my_min..my_max {
                for col in mx_min..mx_max {
                    mask[row * w + col] = false;
                }
            }
        }
    }

    mask
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    width_cells,
    height_cells,
    ox,
    oy,
    resolution_mm,
    board_margin_mm,
    buffer_mm,
    mounting_holes,
    keepout_regions
))]
#[expect(
    clippy::too_many_arguments,
    reason = "PyO3 boundary mirrors the Python create_keepout_mask signature 1:1"
)]
pub fn keepout_mask_flags_py(
    width_cells: usize,
    height_cells: usize,
    ox: f64,
    oy: f64,
    resolution_mm: f64,
    board_margin_mm: f64,
    buffer_mm: f64,
    mounting_holes: Vec<(f64, f64, f64)>,
    keepout_regions: Vec<(f64, f64, f64, f64)>,
) -> PyResult<Vec<bool>> {
    temper_py_bridge::catch_unwind(|| {
        keepout_mask_flags(
            width_cells,
            height_cells,
            ox,
            oy,
            resolution_mm,
            board_margin_mm,
            buffer_mm,
            &mounting_holes,
            &keepout_regions,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn count_false(mask: &[bool]) -> usize {
        mask.iter().filter(|&&v| !v).count()
    }

    #[cfg_attr(test, test)]
    fn test_all_valid_when_no_keepouts_and_zero_margin() {
        let mask = keepout_mask_flags(5, 4, 0.0, 0.0, 1.0, -1.0, 0.0, &[], &[]);
        // board_margin_mm + buffer_mm = -1.0 -> margin_cells <= 0, guard skips.
        assert_eq!(mask.len(), 20);
        assert!(mask.iter().all(|&v| v));
    }

    #[cfg_attr(test, test)]
    fn test_margin_clears_border_ring() {
        // 10x8 grid, margin 1 cell.
        let mask = keepout_mask_flags(10, 8, 0.0, 0.0, 1.0, 1.0, 0.0, &[], &[]);
        // Interior 8x6 remains true, ring is false.
        for row in 0..8usize {
            for col in 0..10usize {
                let expect_false = row == 0 || row == 7 || col == 0 || col == 9;
                assert_eq!(mask[row * 10 + col], !expect_false, "row={row} col={col}");
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_mounting_hole_clears_disc() {
        let mask = keepout_mask_flags(
            11,
            11,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            &[(5.0, 5.0, 2.0)],
            &[],
        );
        // Center cell always cleared.
        assert!(!mask[5 * 11 + 5]);
        // Far corner untouched.
        assert!(mask[0]);
    }

    #[cfg_attr(test, test)]
    fn test_mounting_hole_boundary_is_inclusive() {
        // Python: `if dx * dx + dy * dy <= cr * cr`. cr=2 -> the cell at
        // exactly dx=2, dy=0 (distance^2 == cr^2 == 4) must be cleared.
        // A `<` mutant clears everything strictly inside the disc but
        // leaves this exact boundary cell valid.
        let mask = keepout_mask_flags(11, 11, 0.0, 0.0, 1.0, 0.0, 0.0, &[(5.0, 5.0, 2.0)], &[]);
        assert!(!mask[5 * 11 + 7], "boundary cell (dx=2, dy=0) must be cleared");
        // And just outside the disc (dx=3, dy=0, distance^2=9 > 4) must stay valid.
        assert!(mask[5 * 11 + 8], "cell just outside the disc must stay valid");
    }

    #[cfg_attr(test, test)]
    fn test_margin_cells_truncates_not_rounds() {
        // board_margin_mm=3.0, buffer_mm=0.7 -> margin=3.7 -> int(3.7) == 3
        // (truncation), NOT round(3.7) == 4. A rounding mutant clears one
        // extra row/column of margin on every edge.
        let mask = keepout_mask_flags(20, 20, 0.0, 0.0, 1.0, 3.0, 0.7, &[], &[]);
        // Row 3 (the 4th row, 0-indexed) must be VALID under truncation
        // (only rows 0..3 are margin); a rounding mutant would clear it too.
        assert!(mask[3 * 20 + 10], "row 3 must be valid: margin_cells truncates to 3, not 4");
        assert!(!mask[2 * 20 + 10], "row 2 must still be cleared (within the 3-cell margin)");
    }

    #[cfg_attr(test, test)]
    fn test_keepout_region_clears_rect() {
        let mask = keepout_mask_flags(
            10,
            10,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            &[],
            &[(2.0, 2.0, 4.0, 4.0)],
        );
        assert!(!mask[3 * 10 + 3]);
        assert!(mask[0]);
    }

    #[cfg_attr(test, test)]
    fn test_negative_region_bound_counts_from_end() {
        // A keepout region whose buffered right edge is far to the left of
        // the board origin drives mx_max negative before normalization.
        // Python's `mask[:, mx_min:mx_max]` with a negative mx_max counts
        // back from width_cells, NOT "clamp to 0" (which would make the
        // slice empty). width_cells=10, x_max_buf - ox = -5 at
        // resolution 1.0 -> int(-5)+1 = -4 -> mx_max_raw = min(10, -4) = -4
        // -> normalized = 10 + (-4) = 6. mx_min stays 0 (clamped by the
        // Python max(0, ...) before normalization). The y range is chosen
        // to span the full board (0..3) so the row bound doesn't also
        // collapse to empty and mask the column-bound behaviour.
        let mask = keepout_mask_flags(
            10,
            3,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            &[],
            &[(-100.0, 0.0, -5.0, 10.0)],
        );
        // Columns [0, 6) on every touched row should be cleared per the
        // negative-index-counts-from-the-end semantics; columns [6, 10)
        // must remain valid.
        for row in 0..3usize {
            for col in 0..6usize {
                assert!(!mask[row * 10 + col], "row={row} col={col} expected cleared");
            }
            for col in 6..10usize {
                assert!(mask[row * 10 + col], "row={row} col={col} expected valid");
            }
        }
    }

    #[cfg_attr(test, test)]
    fn test_empty_mask_dims() {
        let mask = keepout_mask_flags(0, 0, 0.0, 0.0, 1.0, 0.0, 0.0, &[], &[]);
        assert!(mask.is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_holes_and_regions_only_clear_never_set() {
        // Order independence: applying a hole that overlaps a
        // keepout-cleared region should not "restore" any cell.
        let mask = keepout_mask_flags(
            10,
            10,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            &[(3.0, 3.0, 5.0)],
            &[(2.0, 2.0, 4.0, 4.0)],
        );
        assert!(count_false(&mask) > 0);
        assert!(!mask[3 * 10 + 3]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("heuristics_geometry::tests::test_all_valid_when_no_keepouts_and_zero_margin", test_all_valid_when_no_keepouts_and_zero_margin),
        ("heuristics_geometry::tests::test_margin_clears_border_ring", test_margin_clears_border_ring),
        ("heuristics_geometry::tests::test_mounting_hole_clears_disc", test_mounting_hole_clears_disc),
        ("heuristics_geometry::tests::test_mounting_hole_boundary_is_inclusive", test_mounting_hole_boundary_is_inclusive),
        ("heuristics_geometry::tests::test_margin_cells_truncates_not_rounds", test_margin_cells_truncates_not_rounds),
        ("heuristics_geometry::tests::test_keepout_region_clears_rect", test_keepout_region_clears_rect),
        ("heuristics_geometry::tests::test_negative_region_bound_counts_from_end", test_negative_region_bound_counts_from_end),
        ("heuristics_geometry::tests::test_empty_mask_dims", test_empty_mask_dims),
        ("heuristics_geometry::tests::test_holes_and_regions_only_clear_never_set", test_holes_and_regions_only_clear_never_set),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
