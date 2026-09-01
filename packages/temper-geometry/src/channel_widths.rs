// Batched Euclidean-distance width lookup for channel-width measurement.
//
// Python reference: temper_placer/router_v6/channel_widths.py::
// `_edt_width_lookup` — bilinear interpolation over the 4 nearest EDT
// grid points, with masked-out cells contributing 0.0, returning
// width = 2 * d * cell_size. The batch form exists because the width
// sampling hot loop (~12k calls per layer) is pure-Python per-call
// overhead; one FFI crossing computes all samples with the EXACT same
// f64 arithmetic order, so results are bit-identical to the per-point
// reference.

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Build the raster mask used by the channel-width EDT and run the exact
/// transform in one Rust-owned operation.  Shapely remains the owner of
/// geometry objects; the Python boundary supplies only flattened outer and
/// hole rings (`[x0, y0, x1, y1, ...]`).
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (outer_rings, holes, bounds, cell_size))]
pub fn prepare_channel_widths_edt(
    outer_rings: Vec<Vec<f64>>,
    holes: Vec<Vec<Vec<f64>>>,
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
) -> PyResult<(Vec<u8>, Vec<u8>, usize, usize)> {
    if outer_rings.len() != holes.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "outer_rings and holes must have the same length",
        ));
    }
    if !cell_size.is_finite() || cell_size <= 0.0 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "cell_size must be positive and finite",
        ));
    }
    if !bounds.0.is_finite()
        || !bounds.1.is_finite()
        || !bounds.2.is_finite()
        || !bounds.3.is_finite()
    {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "bounds must be finite",
        ));
    }
    let (edt, mask, height, width) =
        prepare_channel_widths_edt_kernel(&outer_rings, &holes, bounds, cell_size);
    let mut edt_bytes = Vec::with_capacity(edt.len() * 8);
    for value in edt {
        edt_bytes.extend_from_slice(&value.to_le_bytes());
    }
    Ok((edt_bytes, mask, height, width))
}

/// Pure-Rust owner of channel-width raster preparation.
pub fn prepare_channel_widths_edt_kernel(
    outer_rings: &[Vec<f64>],
    holes: &[Vec<Vec<f64>>],
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
) -> (Vec<f64>, Vec<u8>, usize, usize) {
    let (min_x, min_y, max_x, max_y) = bounds;
    // Same operation order as int(np.ceil((max - min) / cell_size)) + 1.
    let width = ((max_x - min_x) / cell_size).ceil() as usize + 1;
    let height = ((max_y - min_y) / cell_size).ceil() as usize + 1;
    let mut mask = vec![0u8; height * width];
    let polygons: Vec<(Vec<(f64, f64)>, Vec<Vec<(f64, f64)>>)> = outer_rings
        .iter()
        .zip(holes.iter())
        .map(|(outer, holes)| {
            (ring_points(outer), holes.iter().map(|hole| ring_points(hole)).collect())
        })
        .collect();

    // Scanlines make the production multi-million-cell grid proportional to
    // rows plus ring edges, rather than checking every edge for every cell.
    for row in 0..height {
        let y = min_y + row as f64 * cell_size;
        for (outer, holes) in &polygons {
            let mut intervals = pair_intervals(&ring_crossings(outer, y));
            for hole in holes {
                intervals = subtract_intervals(&intervals, &pair_intervals(&ring_crossings(hole, y)));
            }
            for (lo, hi) in intervals {
                let first = (((lo - min_x) / cell_size).floor() as i64 + 1).max(0);
                let last = (((hi - min_x) / cell_size).ceil() as i64 - 1).min(width as i64 - 1);
                if first <= last {
                    for col in first as usize..=last as usize {
                        mask[row * width + col] = 1;
                    }
                }
            }
        }
        for (outer, holes) in &polygons {
            clear_horizontal_boundary(&mut mask, row, width, min_x, y, cell_size, outer);
            clear_grid_edge_boundary(&mut mask, row, width, min_x, y, cell_size, outer);
            for hole in holes {
                clear_horizontal_boundary(&mut mask, row, width, min_x, y, cell_size, hole);
                clear_grid_edge_boundary(&mut mask, row, width, min_x, y, cell_size, hole);
            }
        }
    }
    let edt = crate::edt::exact_edt(&mask, height, width);
    (edt, mask, height, width)
}

fn ring_points(ring: &[f64]) -> Vec<(f64, f64)> {
    ring.chunks_exact(2).map(|pair| (pair[0], pair[1])).collect()
}

fn ring_crossings(ring: &[(f64, f64)], y: f64) -> Vec<f64> {
    let mut crossings = Vec::new();
    for i in 0..ring.len() {
        let (x1, y1) = ring[i];
        let (x2, y2) = ring[(i + 1) % ring.len()];
        if y1 != y2 && ((y1 <= y && y < y2) || (y2 <= y && y < y1)) {
            crossings.push(x1 + (y - y1) / (y2 - y1) * (x2 - x1));
        }
    }
    crossings.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    crossings
}

fn pair_intervals(crossings: &[f64]) -> Vec<(f64, f64)> {
    crossings.chunks_exact(2).filter_map(|pair| {
        (pair[1] > pair[0]).then_some((pair[0], pair[1]))
    }).collect()
}

fn subtract_intervals(outer: &[(f64, f64)], holes: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let mut result = Vec::new();
    for &(lo, hi) in outer {
        let mut cursor = lo;
        for &(hole_lo, hole_hi) in holes {
            if hole_hi <= cursor { continue; }
            if hole_lo >= hi { break; }
            if hole_lo > cursor { result.push((cursor, hole_lo.min(hi))); }
            cursor = cursor.max(hole_hi);
            if cursor >= hi { break; }
        }
        if cursor < hi { result.push((cursor, hi)); }
    }
    result
}

fn clear_horizontal_boundary(
    mask: &mut [u8], row: usize, width: usize, min_x: f64, y: f64,
    cell_size: f64, ring: &[(f64, f64)],
) {
    for i in 0..ring.len() {
        let (x1, y1) = ring[i];
        let (x2, y2) = ring[(i + 1) % ring.len()];
        if y1 != y2 || y1 != y { continue; }
        let first = (((x1.min(x2) - min_x) / cell_size).ceil() as i64).max(0);
        let last = (((x1.max(x2) - min_x) / cell_size).floor() as i64).min(width as i64 - 1);
        if first <= last {
            for col in first as usize..=last as usize { mask[row * width + col] = 0; }
        }
    }
}

fn clear_grid_edge_boundary(
    mask: &mut [u8], row: usize, width: usize, min_x: f64, y: f64,
    cell_size: f64, ring: &[(f64, f64)],
) {
    for i in 0..ring.len() {
        let (x1, y1) = ring[i];
        let (x2, y2) = ring[(i + 1) % ring.len()];
        if y1 == y2 || !((y1 <= y && y <= y2) || (y2 <= y && y <= y1)) { continue; }
        let x = x1 + (y - y1) / (y2 - y1) * (x2 - x1);
        let grid_x = (x - min_x) / cell_size;
        let col = grid_x.round();
        if col == grid_x && (0.0..width as f64).contains(&col) {
            mask[row * width + col as usize] = 0;
        }
    }
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (xs, ys, edt_bytes, mask_bytes, height_cells, width_cells, bounds, cell_size))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
pub fn edt_width_lookup_batch(
    xs: Vec<f64>,
    ys: Vec<f64>,
    edt_bytes: Vec<u8>,
    mask_bytes: Vec<u8>,
    height_cells: usize,
    width_cells: usize,
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
) -> Vec<f64> {
    edt_width_lookup_batch_kernel(
        &xs,
        &ys,
        &edt_bytes,
        &mask_bytes,
        height_cells,
        width_cells,
        bounds,
        cell_size,
    )
}

/// Pure-Rust owner for the batched EDT lookup.  The pyo3 function above is
/// only an ABI adapter; orchestration crates call this kernel directly so a
/// Rust-owned numerical path does not cross Python merely to reach Rust.
#[expect(
    clippy::too_many_arguments,
    reason = "The public kernel mirrors the stable Python-facing argument contract"
)]
pub fn edt_width_lookup_batch_kernel(
    xs: &[f64],
    ys: &[f64],
    edt_bytes: &[u8],
    mask_bytes: &[u8],
    height_cells: usize,
    width_cells: usize,
    bounds: (f64, f64, f64, f64),
    cell_size: f64,
) -> Vec<f64> {
    let (min_x, min_y, _, _) = bounds;
    // Infallible by design: the Python wrapper validates grid lengths and
    // raises ValueError there. (No pyo3 exceptions in this crate — the
    // error machinery breaks `cargo test` linking for extension-module
    // crates without libpython.)
    let edt = parse_f64_bytes(edt_bytes);
    debug_assert_eq!(edt.len(), height_cells * width_cells);
    debug_assert_eq!(mask_bytes.len(), height_cells * width_cells);
    edt_width_lookup_batch_inner(
        xs,
        ys,
        &edt,
        mask_bytes,
        height_cells,
        width_cells,
        min_x,
        min_y,
        cell_size,
    )
}

/// Pure-Rust batch lookup (returns one width per (x, y) sample), kept
/// separate from the pyo3 boundary so unit tests run without libpython.
#[expect(
    clippy::too_many_arguments,
    reason = "Direct port of the Python reference signature; grouping into a config struct would churn the hot path"
)]
fn edt_width_lookup_batch_inner(
    xs: &[f64],
    ys: &[f64],
    edt: &[f64],
    mask: &[u8],
    height_cells: usize,
    width_cells: usize,
    min_x: f64,
    min_y: f64,
    cell_size: f64,
) -> Vec<f64> {
    let w = width_cells as i64;
    let h = height_cells as i64;
    xs.iter()
        .zip(ys.iter())
        .map(|(&x, &y)| {
            // Bit-exact mirror of the Python reference arithmetic order.
            // Divergence note: NaN/±inf coordinates saturate to 0 via the
            // `as i64` cast (Python's int(np.floor(nan)) raises) — not
            // reachable from real skeleton samples (finite coords, fixed
            // cell size); a future untrusted-coordinate caller would get
            // 0.0 instead of an exception.
            let gx = (x - min_x) / cell_size;
            let gy = (y - min_y) / cell_size;
            let ix = gx.floor() as i64;
            let iy = gy.floor() as i64;
            let fx = gx - ix as f64;
            let fy = gy - iy as f64;
            if ix < 0 || iy < 0 || ix + 1 >= w || iy + 1 >= h {
                return 0.0;
            }
            let (iy, ix) = (iy, ix); // keep i64 for the arithmetic
            let at = |r: i64, c: i64| (r * w + c) as usize;
            let d00 = if mask[at(iy, ix)] != 0 { edt[at(iy, ix)] } else { 0.0 };
            let d10 = if mask[at(iy, ix + 1)] != 0 { edt[at(iy, ix + 1)] } else { 0.0 };
            let d01 = if mask[at(iy + 1, ix)] != 0 { edt[at(iy + 1, ix)] } else { 0.0 };
            let d11 = if mask[at(iy + 1, ix + 1)] != 0 { edt[at(iy + 1, ix + 1)] } else { 0.0 };
            let d = (d00 * (1.0 - fx) + d10 * fx) * (1.0 - fy)
                + (d01 * (1.0 - fx) + d11 * fx) * fy;
            2.0 * d * cell_size
        })
        .collect()
}

fn parse_f64_bytes(bytes: &[u8]) -> Vec<f64> {
    debug_assert_eq!(bytes.len() % 8, 0, "edt byte buffer must be 8-aligned");
    bytes
        .chunks_exact(8)
        .map(|c| {
            let mut a = [0u8; 8];
            a.copy_from_slice(c);
            f64::from_le_bytes(a)
        })
        .collect()
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[expect(
        clippy::too_many_arguments,
        reason = "Test helper mirrors the per-point Python reference signature"
    )]
    fn ref_lookup(
        x: f64,
        y: f64,
        edt: &[f64],
        mask: &[u8],
        h: usize,
        w: usize,
        min_x: f64,
        min_y: f64,
        cell_size: f64,
    ) -> f64 {
        // The per-point Python reference, verbatim arithmetic.
        let gx = (x - min_x) / cell_size;
        let gy = (y - min_y) / cell_size;
        let ix = gx.floor() as i64;
        let iy = gy.floor() as i64;
        let fx = gx - ix as f64;
        let fy = gy - iy as f64;
        if ix < 0 || iy < 0 || ix + 1 >= w as i64 || iy + 1 >= h as i64 {
            return 0.0;
        }
        let idx = |r: usize, c: usize| r * w + c;
        let (iy, ix) = (iy as usize, ix as usize);
        let d00 = if mask[idx(iy, ix)] != 0 { edt[idx(iy, ix)] } else { 0.0 };
        let d10 = if mask[idx(iy, ix + 1)] != 0 { edt[idx(iy, ix + 1)] } else { 0.0 };
        let d01 = if mask[idx(iy + 1, ix)] != 0 { edt[idx(iy + 1, ix)] } else { 0.0 };
        let d11 = if mask[idx(iy + 1, ix + 1)] != 0 { edt[idx(iy + 1, ix + 1)] } else { 0.0 };
        let d = (d00 * (1.0 - fx) + d10 * fx) * (1.0 - fy) + (d01 * (1.0 - fx) + d11 * fx) * fy;
        2.0 * d * cell_size
    }

    fn sample_grid() -> (Vec<f64>, Vec<u8>, usize, usize) {
        let h = 6;
        let w = 8;
        let mut edt = vec![0.0f64; h * w];
        let mut mask = vec![0u8; h * w];
        for r in 0..h {
            for c in 0..w {
                let idx = r * w + c;
                mask[idx] = 1;
                edt[idx] = ((r * r + c * c) as f64).sqrt();
            }
        }
        mask[0] = 0; // a masked-out cell
        (edt, mask, h, w)
    }

    #[cfg_attr(test, test)]
    fn test_batch_matches_reference_bit_exact() {
        let (edt, mask, h, w) = sample_grid();
        let xs = vec![0.3, 1.5, 3.7, 6.9, 7.2, -1.0, 9.5, 2.0];
        let ys = vec![0.1, 2.2, 4.9, 5.4, 3.3, 1.0, 0.5, 7.0];
        let got = edt_width_lookup_batch_inner(&xs, &ys, &edt, &mask, h, w, 0.0, 0.0, 1.0);
        let expect: Vec<f64> = xs
            .iter()
            .zip(ys.iter())
            .map(|(&x, &y)| ref_lookup(x, y, &edt, &mask, h, w, 0.0, 0.0, 1.0))
            .collect();
        assert_eq!(got, expect);
    }

    #[cfg_attr(test, test)]
    fn test_batch_matches_reference_with_offset_and_cell_size() {
        let (edt, mask, h, w) = sample_grid();
        let xs = vec![10.6, 13.3, 16.2];
        let ys = vec![20.1, 21.9, 25.0];
        let got = edt_width_lookup_batch_inner(&xs, &ys, &edt, &mask, h, w, 10.0, 20.0, 0.5);
        let expect: Vec<f64> = xs
            .iter()
            .zip(ys.iter())
            .map(|(&x, &y)| ref_lookup(x, y, &edt, &mask, h, w, 10.0, 20.0, 0.5))
            .collect();
        assert_eq!(got, expect);
    }

    #[cfg_attr(test, test)]
    fn test_out_of_bounds_samples_return_zero() {
        let (edt, mask, h, w) = sample_grid();
        // Grid spans x in [0, 8), y in [0, 6): all of these are OOB.
        let xs = vec![-0.5, 7.9, 8.0, 4.0];
        let ys = vec![4.0, 5.9, 6.0, 6.5];
        let got = edt_width_lookup_batch_inner(&xs, &ys, &edt, &mask, h, w, 0.0, 0.0, 1.0);
        assert_eq!(got, vec![0.0, 0.0, 0.0, 0.0]);
    }

    #[cfg_attr(test, test)]
    fn test_masked_out_cells_contribute_zero() {
        let (edt, mask, h, w) = sample_grid();
        // Point straddling the masked cell (0,0): its distance contribution
        // must be zeroed, exactly as in the reference.
        let got = edt_width_lookup_batch_inner(&[0.7], &[0.7], &edt, &mask, h, w, 0.0, 0.0, 1.0);
        let expect = ref_lookup(0.7, 0.7, &edt, &mask, h, w, 0.0, 0.0, 1.0);
        assert_eq!(got[0], expect);
    }

    #[cfg_attr(test, test)]
    fn test_channel_width_raster_strict_boundary_and_hole() {
        let outer = vec![vec![0.0, 0.0, 6.0, 0.0, 6.0, 6.0, 0.0, 6.0, 0.0, 0.0]];
        let holes = vec![vec![2.0, 2.0, 4.0, 2.0, 4.0, 4.0, 2.0, 4.0, 2.0, 2.0]];
        let (_, mask, h, w) = prepare_channel_widths_edt_kernel(
            &outer, &[holes], (0.0, 0.0, 6.0, 6.0), 1.0,
        );
        assert_eq!((h, w), (7, 7));
        assert_eq!(mask[0], 0);
        assert_eq!(mask[2 * w + 2], 0); // hole boundary
        assert_eq!(mask[3 * w + 3], 0); // hole interior
        assert_eq!(mask[w + 1], 1);
    }

    #[cfg_attr(test, test)]
    fn test_channel_width_raster_asymmetric_polygon() {
        let outer = vec![vec![0.0, 0.0, 5.0, 1.0, 2.0, 7.0, 0.0, 0.0]];
        let (_, mask, h, w) = prepare_channel_widths_edt_kernel(
            &outer, &[Vec::new()], (0.0, 0.0, 5.0, 7.0), 0.5,
        );
        assert_eq!((h, w), (15, 11));
        assert!(mask.iter().any(|&cell| cell != 0));
        assert_eq!(mask[0], 0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("channel_widths::tests::test_batch_matches_reference_bit_exact", test_batch_matches_reference_bit_exact),
        ("channel_widths::tests::test_batch_matches_reference_with_offset_and_cell_size", test_batch_matches_reference_with_offset_and_cell_size),
        ("channel_widths::tests::test_out_of_bounds_samples_return_zero", test_out_of_bounds_samples_return_zero),
        ("channel_widths::tests::test_masked_out_cells_contribute_zero", test_masked_out_cells_contribute_zero),
        ("channel_widths::tests::test_channel_width_raster_strict_boundary_and_hole", test_channel_width_raster_strict_boundary_and_hole),
        ("channel_widths::tests::test_channel_width_raster_asymmetric_polygon", test_channel_width_raster_asymmetric_polygon),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
