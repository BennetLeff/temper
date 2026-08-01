// Copper-coverage polygon rasterisation — the hot loop of
// temper_placer/physics/copper_coverage.py::_rasterise_polygon_mask.
//
// Ray-casting (even-odd rule) point-in-polygon test per cell centre,
// with the EXACT arithmetic order of the Python reference so the bool
// mask is bit-identical: (yi > cy) != (yj > cy), strict x-crossing
// comparison cx < ((px[j]-px[i]) * (cy-yi) / (yj-yi) + px[i]), all in
// f64. Returns the mask as bytes (1 byte per cell, 0/1) for the
// Python wrapper's np.frombuffer view.

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use temper_py_bridge;

#[pyfunction]
#[pyo3(signature = (polygon, height_cells, width_cells, ox, oy, cs))]
pub fn rasterise_polygon_mask(
    py: Python<'_>,
    polygon: Vec<(f64, f64)>,
    height_cells: usize,
    width_cells: usize,
    ox: f64,
    oy: f64,
    cs: f64,
) -> PyResult<Bound<'_, PyBytes>> {
    let mask = temper_py_bridge::catch_unwind(|| {
        polygon_mask(&polygon, height_cells, width_cells, ox, oy, cs)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    PyBytes::new_with(py, mask.len(), |b| {
        b.copy_from_slice(&mask);
        Ok(())
    })
}

/// Pure-Rust rasterisation (1 byte per cell, 0/1), kept separate from the
/// pyo3 boundary so unit tests run without libpython.
fn polygon_mask(
    polygon: &[(f64, f64)],
    height_cells: usize,
    width_cells: usize,
    ox: f64,
    oy: f64,
    cs: f64,
) -> Vec<u8> {
    let mut mask = vec![0u8; height_cells * width_cells];
    let n = polygon.len();
    if n < 3 {
        return mask;
    }
    let px: Vec<f64> = polygon.iter().map(|p| p.0).collect();
    let py: Vec<f64> = polygon.iter().map(|p| p.1).collect();

    for row in 0..height_cells {
        let cy = oy + (row as f64 + 0.5) * cs;
        for col in 0..width_cells {
            let cx = ox + (col as f64 + 0.5) * cs;

            let mut inside = false;
            let mut j = n - 1;
            for i in 0..n {
                let yi = py[i];
                let yj = py[j];
                if ((yi > cy) != (yj > cy))
                    && (cx < (px[j] - px[i]) * (cy - yi) / (yj - yi) + px[i])
                {
                    inside = !inside;
                }
                j = i;
            }
            if inside {
                mask[row * width_cells + col] = 1;
            }
        }
    }
    mask
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
    fn test_square_centred() {
        // 10x10 grid, cs=1, origin (0,0); square (2,2)-(8,8)
        let poly = vec![(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)];
        let mask = polygon_mask(&poly, 10, 10, 0.0, 0.0, 1.0);
        let grid = mask_to_grid(&mask, 10, 10);
        assert!(grid[2][2] && grid[7][7]);
        assert!(!grid[1][1] && !grid[8][8] && !grid[5][9]);
    }

    #[test]
    fn test_edge_semantics_match_strict_comparisons() {
        // Cell centres on integer coords (origin -0.5, cs 1): the square
        // (0,0)-(4,4). Values asserted here mirror the Python even-odd
        // ray cast bit-for-bit (strict > and <); the differential suite
        // pins these against the numpy oracle on randomized inputs.
        let poly = vec![(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)];
        let mask = polygon_mask(&poly, 5, 5, -0.5, -0.5, 1.0);
        let grid = mask_to_grid(&mask, 5, 5);
        assert!(grid[0][0]); // centre (0,0) on the corner vertex
        assert!(grid[0][1]); // centre (1,0) on the bottom edge
        assert!(grid[2][2]); // centre (2,2) interior vertex of the ray
        assert!(!grid[4][4]); // centre (4,4) corner vertex, exit ray
    }

    #[test]
    fn test_fewer_than_three_vertices_is_empty() {
        let mask = polygon_mask(&[(0.0, 0.0), (1.0, 1.0)], 10, 10, 0.0, 0.0, 1.0);
        assert!(mask.iter().all(|&v| v == 0));
    }

    #[test]
    fn test_concave_polygon_even_odd() {
        // L-shape: even-odd rule excludes the notch.
        let poly = vec![
            (0.0, 0.0),
            (8.0, 0.0),
            (8.0, 3.0),
            (3.0, 3.0),
            (3.0, 8.0),
            (0.0, 8.0),
        ];
        let mask = polygon_mask(&poly, 10, 10, 0.0, 0.0, 1.0);
        let grid = mask_to_grid(&mask, 10, 10);
        assert!(grid[1][1]); // inside the L arm
        assert!(grid[6][1]); // inside the vertical arm
        assert!(!grid[6][6]); // in the notch
    }

    #[test]
    fn test_offset_grid_alignment() {
        // All 25 cell centres (6+2c, 6+2r) fall inside (5,5)-(15,15).
        let poly = vec![(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0)];
        let mask = polygon_mask(&poly, 5, 5, 5.0, 5.0, 2.0);
        assert_eq!(mask.iter().filter(|&&v| v == 1).count(), 25);
    }
}
