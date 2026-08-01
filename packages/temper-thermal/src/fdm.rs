//! FDM assembly kernels — bit-exact mirrors of
//! `temper_placer/physics/thermal_fdm.py` (`_assemble_system`,
//! `_trace_to_cell_coverage`; the `_point_to_segment_distance` check is
//! inlined in `trace_coverage_inner`).

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use temper_py_bridge;

// ---------------------------------------------------------------------------
// System assembly
// ---------------------------------------------------------------------------

/// Assemble the sparse linear system A·T = b.
///
/// Mirrors `_assemble_system` exactly: 5-point stencil with harmonic-mean
/// interface conductivity `2/(1/k_a + 1/k_b)`, Dirichlet face at the
/// heatsink edge (coeff `2*k_c/dx2`, RHS `coeff*ambient`), Neumann
/// adiabatic elsewhere, optional per-cell vertical sink `h_cell` on the
/// diagonal and `h_cell*ambient` on the RHS, and `Q` added last to the
/// RHS. Accumulation ORDER on the diagonal and RHS matches the Python
/// reference (east, west, north, south, then sink, then Q) so the f64
/// sums are bit-identical.
///
/// Returns (rows, cols, values, b) — the matrix as COO triplets plus the
/// RHS vector; the Python side builds scipy CSR from the triplets.
#[pyfunction]
#[pyo3(signature = (k_field_bytes, q_bytes, h_field_bytes, height_cells, width_cells, ambient_c, cell_size_mm, heatsink_edge))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
pub fn assemble_system(
    k_field_bytes: Vec<u8>,
    q_bytes: Vec<u8>,
    h_field_bytes: Option<Vec<u8>>,
    height_cells: usize,
    width_cells: usize,
    ambient_c: f64,
    cell_size_mm: f64,
    heatsink_edge: String,
) -> (Vec<i64>, Vec<i64>, Vec<f64>, Vec<f64>) {
    let k = parse_f64s(&k_field_bytes);
    let q = parse_f64s(&q_bytes);
    let hf = h_field_bytes.map(|b| parse_f64s(&b));
    let n = height_cells * width_cells;
    debug_assert_eq!(k.len(), n);
    debug_assert_eq!(q.len(), n);

    let (h, w) = (height_cells, width_cells);
    let dx2 = cell_size_mm * cell_size_mm;
    let hs = heatsink_edge.to_uppercase();

    let mut rows: Vec<i64> = Vec::with_capacity(n * 5);
    let mut cols: Vec<i64> = Vec::with_capacity(n * 5);
    let mut vals: Vec<f64> = Vec::with_capacity(n * 5);
    let mut b = vec![0.0f64; n];

    for row in 0..h {
        for col in 0..w {
            let idx = row * w + col;
            let mut diag = 0.0f64;
            let k_c = k[idx];

            // East
            if col + 1 < w {
                let k_e = harmonic(k_c, k[idx + 1]);
                let coeff = k_e / dx2;
                rows.push(idx as i64);
                cols.push((idx + 1) as i64);
                vals.push(-coeff);
                diag += coeff;
            } else if heatsink_face(row, col, "east", h, w, &hs) {
                let coeff = 2.0 * k_c / dx2;
                diag += coeff;
                b[idx] += coeff * ambient_c;
            }

            // West
            if col >= 1 {
                let k_w = harmonic(k_c, k[idx - 1]);
                let coeff = k_w / dx2;
                rows.push(idx as i64);
                cols.push((idx - 1) as i64);
                vals.push(-coeff);
                diag += coeff;
            } else if heatsink_face(row, col, "west", h, w, &hs) {
                let coeff = 2.0 * k_c / dx2;
                diag += coeff;
                b[idx] += coeff * ambient_c;
            }

            // North (row+1 = larger y)
            if row + 1 < h {
                let k_n = harmonic(k_c, k[idx + w]);
                let coeff = k_n / dx2;
                rows.push(idx as i64);
                cols.push((idx + w) as i64);
                vals.push(-coeff);
                diag += coeff;
            } else if heatsink_face(row, col, "north", h, w, &hs) {
                let coeff = 2.0 * k_c / dx2;
                diag += coeff;
                b[idx] += coeff * ambient_c;
            }

            // South
            if row >= 1 {
                let k_s = harmonic(k_c, k[idx - w]);
                let coeff = k_s / dx2;
                rows.push(idx as i64);
                cols.push((idx - w) as i64);
                vals.push(-coeff);
                diag += coeff;
            } else if heatsink_face(row, col, "south", h, w, &hs) {
                let coeff = 2.0 * k_c / dx2;
                diag += coeff;
                b[idx] += coeff * ambient_c;
            }

            // Vertical sink term h(T - T_amb)
            if let Some(hf) = &hf {
                let h_cell = hf[idx];
                if h_cell > 0.0 {
                    diag += h_cell;
                    b[idx] += h_cell * ambient_c;
                }
            }

            rows.push(idx as i64);
            cols.push(idx as i64);
            vals.push(diag);
            b[idx] += q[idx];
        }
    }

    (rows, cols, vals, b)
}

/// PyO3 wrapper: the pure kernel is infallible for well-formed inputs
/// (the Python side validates buffer lengths); this panics loudly as a
/// Python RuntimeError instead of aborting the interpreter if a
/// malformed buffer ever gets through.
#[pyfunction]
#[pyo3(signature = (k_field_bytes, q_bytes, h_field_bytes, height_cells, width_cells, ambient_c, cell_size_mm, heatsink_edge))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
pub fn assemble_system_py(
    k_field_bytes: Vec<u8>,
    q_bytes: Vec<u8>,
    h_field_bytes: Option<Vec<u8>>,
    height_cells: usize,
    width_cells: usize,
    ambient_c: f64,
    cell_size_mm: f64,
    heatsink_edge: String,
) -> (Vec<i64>, Vec<i64>, Vec<f64>, Vec<f64>) {
    temper_py_bridge::catch_unwind(|| {
        assemble_system(
            k_field_bytes,
            q_bytes,
            h_field_bytes,
            height_cells,
            width_cells,
            ambient_c,
            cell_size_mm,
            heatsink_edge,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
    .unwrap_or_default()
}

fn harmonic(k_a: f64, k_b: f64) -> f64 {
    // 2.0 / (1.0/k_a + 1.0/k_b) — exact reference operation order.
    2.0 / (1.0 / k_a + 1.0 / k_b)
}

fn heatsink_face(row: usize, col: usize, direction: &str, h: usize, w: usize, hs: &str) -> bool {
    match direction {
        "north" => row == h - 1 && hs == "TOP",
        "south" => row == 0 && hs == "BOTTOM",
        "east" => col == w - 1 && hs == "RIGHT",
        _ => col == 0 && hs == "LEFT",
    }
}

// ---------------------------------------------------------------------------
// Trace rasterisation
// ---------------------------------------------------------------------------

/// Rasterise a single fat trace segment to fractional copper coverage
/// per cell (anti-aliased, 4x4 supersampling). Mirrors
/// `_trace_to_cell_coverage` bit-for-bit. Returns the (height_cells,
/// width_cells) float64 grid as little-endian bytes.
#[pyfunction]
#[pyo3(signature = (x0, y0, x1, y1, trace_width_mm, origin_x, origin_y, cell_size_mm, height_cells, width_cells))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
pub fn trace_to_cell_coverage(
    py: Python<'_>,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    trace_width_mm: f64,
    origin_x: f64,
    origin_y: f64,
    cell_size_mm: f64,
    height_cells: usize,
    width_cells: usize,
) -> PyResult<Bound<'_, PyBytes>> {
    let grid = temper_py_bridge::catch_unwind(|| {
        trace_coverage_inner(
            x0, y0, x1, y1, trace_width_mm, origin_x, origin_y, cell_size_mm, height_cells,
            width_cells,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    let mut out = Vec::with_capacity(grid.len() * 8);
    for v in grid {
        out.extend_from_slice(&v.to_le_bytes());
    }
    PyBytes::new_with(py, out.len(), |b| {
        b.copy_from_slice(&out);
        Ok(())
    })
}

#[expect(
    clippy::too_many_arguments,
    reason = "Direct port of the Python reference signature; grouping into a config struct would churn the hot path"
)]
fn trace_coverage_inner(
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    trace_width_mm: f64,
    ox: f64,
    oy: f64,
    cs: f64,
    height_cells: usize,
    width_cells: usize,
) -> Vec<f64> {
    let half_w = trace_width_mm / 2.0;

    let x_min = x0.min(x1) - half_w;
    let x_max = x0.max(x1) + half_w;
    let y_min = y0.min(y1) - half_w;
    let y_max = y0.max(y1) + half_w;

    let col_min = 0.max(((x_min - ox) / cs).floor() as i64) as usize;
    let col_max = width_cells.min(((x_max - ox) / cs).ceil().max(0.0) as usize);
    let row_min = 0.max(((y_min - oy) / cs).floor() as i64) as usize;
    let row_max = height_cells.min(((y_max - oy) / cs).ceil().max(0.0) as usize);

    let mut coverage = vec![0.0f64; height_cells * width_cells];
    if col_max <= col_min || row_max <= row_min {
        return coverage;
    }

    let sub = 4.0f64;
    let n_sub = 4usize;
    // Segment invariants — hoisted out of the per-sub-sample loop. The
    // division/order below must stay byte-identical to the (now inlined)
    // `_point_to_segment_distance` reference (no inv_seg_len_sq shortcut).
    let dx = x1 - x0;
    let dy = y1 - y0;
    let seg_len_sq = dx * dx + dy * dy;
    let degenerate = seg_len_sq < 1e-18;
    for r in row_min..row_max {
        for c in col_min..col_max {
            let mut hit = 0u32;
            for sr in 0..n_sub {
                let y_s = oy + (r as f64 + (sr as f64 + 0.5) / sub) * cs;
                for sc in 0..n_sub {
                    let x_s = ox + (c as f64 + (sc as f64 + 0.5) / sub) * cs;
                    let dist = if degenerate {
                        ((x_s - x0).powi(2) + (y_s - y0).powi(2)).sqrt()
                    } else {
                        let t = (0.0f64)
                            .max((1.0f64).min(((x_s - x0) * dx + (y_s - y0) * dy) / seg_len_sq));
                        let proj_x = x0 + t * dx;
                        let proj_y = y0 + t * dy;
                        ((x_s - proj_x).powi(2) + (y_s - proj_y).powi(2)).sqrt()
                    };
                    if dist <= half_w {
                        hit += 1;
                    }
                }
            }
            coverage[r * width_cells + c] = f64::from(hit) / (sub * sub);
        }
    }
    coverage
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

// ---------------------------------------------------------------------------
// KTD9 spike: faer sparse-LU solve as a scipy spsolve (SuperLU) candidate.
// Parity is measured in Python (tests/physics/test_thermal_fdm_rust_differential.py
// KTD9 section); adoption is gated on the spike verdict (roadmap KTD9).
// ---------------------------------------------------------------------------

/// Solve A·x = b with faer's sparse LU (partial row pivoting), given the
/// matrix as COO triplets. Returns the solution as f64 bytes.
#[pyfunction]
#[pyo3(signature = (rows, cols, values, b_bytes, n))]
pub fn solve_faer_py(
    py: Python<'_>,
    rows: Vec<usize>,
    cols: Vec<usize>,
    values: Vec<f64>,
    b_bytes: Vec<u8>,
    n: usize,
) -> PyResult<Bound<'_, PyBytes>> {
    let x: Vec<f64> = temper_py_bridge::catch_unwind(|| -> Result<Vec<f64>, String> {
        use faer::linalg::solvers::Solve;

        let triplets: Vec<faer::sparse::Triplet<usize, usize, f64>> = rows
            .iter()
            .zip(cols.iter())
            .zip(values.iter())
            .map(|((&r, &c), &v)| faer::sparse::Triplet::new(r, c, v))
            .collect();
        let b = parse_f64s(&b_bytes);
        let mat = faer::sparse::SparseColMat::<usize, f64>::try_new_from_triplets(n, n, &triplets)
            .map_err(|e| format!("triplet construction: {e:?}"))?;
        let rhs = faer::col::Col::from_fn(n, |i| b[i]);
        let lu = mat.sp_lu().map_err(|e| format!("sp_lu factorization: {e:?}"))?;
        let x = lu.solve(&rhs);
        Ok((0..n).map(|i| x[i]).collect::<Vec<f64>>())
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(PyErr::new::<pyo3::exceptions::PyValueError, _>)?;
    let mut out = Vec::with_capacity(x.len() * 8);
    for v in x {
        out.extend_from_slice(&v.to_le_bytes());
    }
    PyBytes::new_with(py, out.len(), |b| {
        b.copy_from_slice(&out);
        Ok(())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn f64_bytes(vals: &[f64]) -> Vec<u8> {
        let mut out = Vec::new();
        for v in vals {
            out.extend_from_slice(&v.to_le_bytes());
        }
        out
    }

    #[expect(
        clippy::too_many_arguments,
        reason = "Test helper mirrors the Python reference signature"
    )]
    fn ref_assemble(
        k: &[f64],
        q: &[f64],
        hf: Option<&[f64]>,
        h: usize,
        w: usize,
        ambient: f64,
        cs: f64,
        hs_edge: &str,
    ) -> (Vec<i64>, Vec<i64>, Vec<f64>, Vec<f64>) {
        // The Python reference, verbatim.
        let dx2 = cs * cs;
        let mut rows = Vec::new();
        let mut cols = Vec::new();
        let mut vals = Vec::new();
        let mut b = vec![0.0f64; h * w];
        for row in 0..h {
            for col in 0..w {
                let idx = row * w + col;
                let mut diag = 0.0f64;
                let k_c = k[idx];
                if col + 1 < w {
                    let k_e = 2.0 / (1.0 / k_c + 1.0 / k[row * w + col + 1]);
                    let coeff = k_e / dx2;
                    rows.push(idx as i64);
                    cols.push((row * w + col + 1) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if col == w - 1 && hs_edge == "RIGHT" {
                    let coeff = 2.0 * k_c / dx2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                // west
                if col >= 1 {
                    let k_w = 2.0 / (1.0 / k_c + 1.0 / k[row * w + col - 1]);
                    let coeff = k_w / dx2;
                    rows.push(idx as i64);
                    cols.push((row * w + col - 1) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if col == 0 && hs_edge == "LEFT" {
                    let coeff = 2.0 * k_c / dx2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                // north
                if row + 1 < h {
                    let k_n = 2.0 / (1.0 / k_c + 1.0 / k[(row + 1) * w + col]);
                    let coeff = k_n / dx2;
                    rows.push(idx as i64);
                    cols.push(((row + 1) * w + col) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if row == h - 1 && hs_edge == "TOP" {
                    let coeff = 2.0 * k_c / dx2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                // south
                if row >= 1 {
                    let k_s = 2.0 / (1.0 / k_c + 1.0 / k[(row - 1) * w + col]);
                    let coeff = k_s / dx2;
                    rows.push(idx as i64);
                    cols.push(((row - 1) * w + col) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if row == 0 && hs_edge == "BOTTOM" {
                    let coeff = 2.0 * k_c / dx2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                if let Some(hf) = hf {
                    let h_cell = hf[idx];
                    if h_cell > 0.0 {
                        diag += h_cell;
                        b[idx] += h_cell * ambient;
                    }
                }
                rows.push(idx as i64);
                cols.push(idx as i64);
                vals.push(diag);
                b[idx] += q[idx];
            }
        }
        (rows, cols, vals, b)
    }

    #[test]
    fn test_assembly_matches_reference() {
        let h = 4;
        let w = 5;
        let k: Vec<f64> = (0..h * w).map(|i| 0.3 + (i as f64) * 0.1).collect();
        let q: Vec<f64> = (0..h * w).map(|i| (i as f64) * 0.01).collect();
        for hs in ["TOP", "BOTTOM", "LEFT", "RIGHT", "NORTH"] {
            for hf in [None, Some(vec![0.5f64; h * w]), Some(vec![0.0f64; h * w])] {
                let got = assemble_system(
                    f64_bytes(&k),
                    f64_bytes(&q),
                    hf.clone().map(|v| f64_bytes(&v)),
                    h,
                    w,
                    40.0,
                    0.5,
                    hs.to_string(),
                );
                let expect = ref_assemble(&k, &q, hf.as_deref(), h, w, 40.0, 0.5, hs);
                assert_eq!(got, expect, "heatsink={hs} h_field={}", hf.is_some());
            }
        }
    }

    #[test]
    fn test_trace_coverage_matches_reference() {
        // Reference: the Python algorithm, inline.
        let (x0, y0, x1, y1, tw): (f64, f64, f64, f64, f64) = (1.0, 1.0, 9.0, 7.0, 0.8);
        let (ox, oy, cs, h, w) = (0.0, 0.0, 0.5, 20, 20);
        let half_w = tw / 2.0;
        let mut expect = vec![0.0f64; h * w];
        let x_min = x0.min(x1) - half_w;
        let x_max = x0.max(x1) + half_w;
        let y_min = y0.min(y1) - half_w;
        let y_max = y0.max(y1) + half_w;
        let col_min = 0.max(((x_min - ox) / cs).floor() as i64) as usize;
        let col_max = w.min(((x_max - ox) / cs).ceil().max(0.0) as usize);
        let row_min = 0.max(((y_min - oy) / cs).floor() as i64) as usize;
        let row_max = h.min(((y_max - oy) / cs).ceil().max(0.0) as usize);
        let sub = 4.0f64;
        for r in row_min..row_max {
            for c in col_min..col_max {
                let mut hit = 0u32;
                for sr in 0..4usize {
                    let y_s = oy + (r as f64 + (sr as f64 + 0.5) / sub) * cs;
                    for sc in 0..4usize {
                        let x_s = ox + (c as f64 + (sc as f64 + 0.5) / sub) * cs;
                        // point-to-segment distance, Python-verbatim
                        let (px, py, ax, ay, bx, by) = (x_s, y_s, x0, y0, x1, y1);
                        let dx = bx - ax;
                        let dy = by - ay;
                        let seg_len_sq = dx * dx + dy * dy;
                        let d = if seg_len_sq < 1e-18 {
                            ((px - ax) * (px - ax) + (py - ay) * (py - ay)).sqrt()
                        } else {
                            let t = (0.0f64)
                                .max((1.0f64).min(((px - ax) * dx + (py - ay) * dy) / seg_len_sq));
                            let p_x = ax + t * dx;
                            let p_y = ay + t * dy;
                            ((px - p_x) * (px - p_x) + (py - p_y) * (py - p_y)).sqrt()
                        };
                        if d <= half_w {
                            hit += 1;
                        }
                    }
                }
                expect[r * w + c] = f64::from(hit) / (sub * sub);
            }
        }
        let got = trace_coverage_inner(x0, y0, x1, y1, tw, ox, oy, cs, h, w);
        assert_eq!(got, expect);
    }

    #[test]
    fn test_trace_coverage_off_grid_returns_zeros() {
        let got = trace_coverage_inner(100.0, 100.0, 105.0, 102.0, 0.5, 0.0, 0.0, 0.5, 10, 10);
        assert!(got.iter().all(|&v| v == 0.0));
    }

    #[test]
    fn test_trace_coverage_degenerate_segment() {
        // Zero-length segment: the 1e-18 fallback branch.
        let got = trace_coverage_inner(5.0, 5.0, 5.0, 5.0, 0.5, 0.0, 0.0, 0.5, 20, 20);
        assert!(got.iter().any(|&v| v > 0.0));
    }
}
