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

use pyo3::prelude::*;

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
    let (min_x, min_y, _, _) = bounds;
    // Infallible by design: the Python wrapper validates grid lengths and
    // raises ValueError there. (No pyo3 exceptions in this crate — the
    // error machinery breaks `cargo test` linking for extension-module
    // crates without libpython.)
    let edt = parse_f64_bytes(&edt_bytes);
    debug_assert_eq!(edt.len(), height_cells * width_cells);
    debug_assert_eq!(mask_bytes.len(), height_cells * width_cells);
    edt_width_lookup_batch_inner(
        &xs,
        &ys,
        &edt,
        &mask_bytes,
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

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
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

    #[test]
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

    #[test]
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

    #[test]
    fn test_out_of_bounds_samples_return_zero() {
        let (edt, mask, h, w) = sample_grid();
        // Grid spans x in [0, 8), y in [0, 6): all of these are OOB.
        let xs = vec![-0.5, 7.9, 8.0, 4.0];
        let ys = vec![4.0, 5.9, 6.0, 6.5];
        let got = edt_width_lookup_batch_inner(&xs, &ys, &edt, &mask, h, w, 0.0, 0.0, 1.0);
        assert_eq!(got, vec![0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_masked_out_cells_contribute_zero() {
        let (edt, mask, h, w) = sample_grid();
        // Point straddling the masked cell (0,0): its distance contribution
        // must be zeroed, exactly as in the reference.
        let got = edt_width_lookup_batch_inner(&[0.7], &[0.7], &edt, &mask, h, w, 0.0, 0.0, 1.0);
        let expect = ref_lookup(0.7, 0.7, &edt, &mask, h, w, 0.0, 0.0, 1.0);
        assert_eq!(got[0], expect);
    }
}
