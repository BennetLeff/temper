//! Independent thermal scorer kernels (Wave 3 candidate #6) — bit-exact
//! mirrors of `temper_placer/validation/thermal_scorer.py`'s pure compute:
//! `_build_conductivity_field_gs`, `_build_heat_source_field_gs`, and
//! `_assemble_convective_system` (the 5-point harmonic-mean stencil with
//! convective/Robin boundary conditions on the three non-heatsink edges).
//!
//! The sparse SOLVE stays in scipy (SuperLU) per the KTD9 verdict — this
//! module moves the assembly/compute loops only.  The falsifiability
//! assertion (1.0 deg-C threshold vs the U5 field solver) is a separate,
//! preserved Python-side contract and is untouched here.
//!
//! Bit-exactness: identical f64 operation order throughout (harmonic mean
//! `2.0/(1.0/k_a + 1.0/k_b)`, direction accumulation order
//! east→west→north→south→convective→sink→Q, `conv_coeff = h*t/cs*1e-6`
//! left-to-right).  The heat-source kernel even replicates the reference's
//! numpy negative-slice wrap for fully off-grid-low devices (a latent
//! reference quirk, identical in U5's thermal_fdm.py) so the two can never
//! silently diverge.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use temper_py_bridge;

// ---------------------------------------------------------------------------
// Conductivity field
// ---------------------------------------------------------------------------

/// Build the per-cell in-plane conductance k_eff (W/K).  Mirrors
/// `_build_conductivity_field_gs`: `k_fr4_eff + (k_cu_eff - k_fr4_eff) *
/// clip(frac, 0, 1)` with `k_*_eff = k_* * thickness_mm * 1e-3`, elementwise.
/// When no copper grid is given, returns a uniform k_fr4_eff grid.
#[pyfunction]
#[pyo3(signature = (k_fr4, k_copper, board_thickness_mm, copper_grid_bytes, height_cells, width_cells))]
pub fn build_conductivity_field_py(
    py: Python<'_>,
    k_fr4: f64,
    k_copper: f64,
    board_thickness_mm: f64,
    copper_grid_bytes: Option<Vec<u8>>,
    height_cells: usize,
    width_cells: usize,
) -> PyResult<Bound<'_, PyBytes>> {
    let grid = temper_py_bridge::catch_unwind(|| {
        build_conductivity_field_inner(
            k_fr4,
            k_copper,
            board_thickness_mm,
            copper_grid_bytes,
            height_cells,
            width_cells,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok(PyBytes::new(py, &grid))
}

fn build_conductivity_field_inner(
    k_fr4: f64,
    k_copper: f64,
    board_thickness_mm: f64,
    copper_grid_bytes: Option<Vec<u8>>,
    height_cells: usize,
    width_cells: usize,
) -> Vec<u8> {
    let n = height_cells * width_cells;
    // k_*_eff = k_* * thickness_mm * 1e-3 — reference operation order.
    let k_fr4_eff = k_fr4 * board_thickness_mm * 1e-3;
    let k_cu_eff = k_copper * board_thickness_mm * 1e-3;
    let mut out = Vec::with_capacity(n * 8);
    match copper_grid_bytes {
        None => {
            for _ in 0..n {
                out.extend_from_slice(&k_fr4_eff.to_le_bytes());
            }
        }
        Some(bytes) => {
            let frac = parse_f64s(&bytes);
            debug_assert_eq!(frac.len(), n);
            for v in frac {
                // k_fr4_eff + (k_cu_eff - k_fr4_eff) * clip(frac, 0, 1) —
                // elementwise op order identical to the numpy reference.
                // f64::clamp(NaN) returns NaN, matching np.clip.
                let k = k_fr4_eff + (k_cu_eff - k_fr4_eff) * v.clamp(0.0, 1.0);
                out.extend_from_slice(&k.to_le_bytes());
            }
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Heat-source field
// ---------------------------------------------------------------------------

/// Build the per-cell areal heat source Q (W/mm^2) from device positions
/// and powers.  Mirrors `_build_heat_source_field_gs`: each device's power
/// is spread over a 5x5 mm footprint using `floor`/`ceil` cell bounds,
/// `n_cells = max(1, ...)`, `Q_density = power / (n_cells * cs * cs)`,
/// accumulated in device order (dict insertion order).
///
/// Devices are passed as ordered `(name, x_mm, y_mm)` tuples and powers as
/// ordered `(name, power)` pairs so iteration order is preserved exactly.
/// The reference's numpy negative-slice wrap for fully off-grid-low devices
/// is replicated (`py_slice_indices`).
#[pyfunction]
#[pyo3(signature = (devices, power_map, origin_x, origin_y, cell_size_mm, height_cells, width_cells))]
pub fn build_heat_source_field_py(
    py: Python<'_>,
    devices: Vec<(String, f64, f64)>,
    power_map: Vec<(String, f64)>,
    origin_x: f64,
    origin_y: f64,
    cell_size_mm: f64,
    height_cells: usize,
    width_cells: usize,
) -> PyResult<Bound<'_, PyBytes>> {
    let grid = temper_py_bridge::catch_unwind(|| {
        build_heat_source_field_inner(
            &devices,
            &power_map,
            origin_x,
            origin_y,
            cell_size_mm,
            height_cells,
            width_cells,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok(PyBytes::new(py, &grid))
}

fn build_heat_source_field_inner(
    devices: &[(String, f64, f64)],
    power_map: &[(String, f64)],
    ox: f64,
    oy: f64,
    cs: f64,
    height_cells: usize,
    width_cells: usize,
) -> Vec<u8> {
    let n = height_cells * width_cells;
    let mut q = vec![0.0f64; n];
    let powers: HashMap<&str, f64> = power_map
        .iter()
        .map(|(name, p)| (name.as_str(), *p))
        .collect();

    let footprint_mm = 5.0;
    let half_f = footprint_mm / 2.0;

    for (name, dx, dy) in devices {
        let power = match powers.get(name.as_str()) {
            Some(&p) => p,
            None => 0.0,
        };
        if power <= 0.0 {
            continue;
        }

        // Cell bounds — same float math as the reference, left-to-right.
        let col_min = (0i64).max(((dx - half_f - ox) / cs).floor() as i64);
        let col_max = (width_cells as i64).min(((dx + half_f - ox) / cs).ceil() as i64);
        let row_min = (0i64).max(((dy - half_f - oy) / cs).floor() as i64);
        let row_max = (height_cells as i64).min(((dy + half_f - oy) / cs).ceil() as i64);

        // n_cells uses the clamped (pre-slice-wrap) bounds, exactly like the
        // reference: max(1, (row_max - row_min) * (col_max - col_min)).
        let n_cells = ((row_max - row_min) * (col_max - col_min)).max(1);
        // Q_density = power / (n_cells * cs * cs).
        let q_density = power / (n_cells as f64 * cs * cs);

        // Numpy slice semantics for Q[row_min:row_max, col_min:col_max]:
        // a negative END wraps by adding the axis length, then both bounds
        // clamp to [0, len]; empty when lo >= hi.  row_min/col_min are
        // already >= 0, so only the end can wrap (see py_slice_indices).
        let rows = py_slice_indices(row_min, row_max, height_cells);
        let cols = py_slice_indices(col_min, col_max, width_cells);
        for &r in &rows {
            for &c in &cols {
                q[r * width_cells + c] += q_density;
            }
        }
    }

    let mut out = Vec::with_capacity(n * 8);
    for v in q {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out
}

/// Python `slice(lo, hi)` on an axis of length `n`: negative `hi` wraps by
/// adding `n`, then both bounds clamp to `[0, n]`; empty when `lo >= hi`.
/// Only the end needs wrapping here (the reference clamps the start with
/// `max(0, ...)` before slicing).
fn py_slice_indices(lo: i64, hi: i64, n: usize) -> Vec<usize> {
    let hi_wrapped = if hi < 0 { hi + n as i64 } else { hi };
    let lo_c = lo.clamp(0, n as i64);
    let hi_c = hi_wrapped.clamp(0, n as i64);
    if lo_c >= hi_c {
        Vec::new()
    } else {
        (lo_c..hi_c).map(|i| i as usize).collect()
    }
}

// ---------------------------------------------------------------------------
// Convective system assembly
// ---------------------------------------------------------------------------

/// Assemble the sparse linear system A·T = b for the convective-boundary
/// FDM.  Mirrors `_assemble_convective_system` exactly: 5-point
/// harmonic-mean stencil, Dirichlet face at the heatsink edge (coeff
/// `2*k_c/dx2`, RHS `coeff*ambient`), convective (Robin) term
/// `conv_coeff = h_conv * t_mm / cs * 1e-6` at the three non-heatsink
/// edges, optional per-cell vertical sink, and Q added last to the RHS.
/// Accumulation ORDER on the diagonal and RHS matches the Python reference
/// (east, west, north, south, convective, sink, then Q) so the f64 sums are
/// bit-identical.
///
/// Returns (rows, cols, values, b) — the matrix as COO triplets plus the
/// RHS vector; the Python side builds scipy CSR from the triplets and keeps
/// the sparse solve in scipy (SuperLU).
#[pyfunction]
#[pyo3(signature = (k_field_bytes, q_bytes, h_field_bytes, height_cells, width_cells, ambient_c, cell_size_mm, board_thickness_mm, h_conv, heatsink_edge))]
pub fn assemble_convective_system_py(
    k_field_bytes: Vec<u8>,
    q_bytes: Vec<u8>,
    h_field_bytes: Option<Vec<u8>>,
    height_cells: usize,
    width_cells: usize,
    ambient_c: f64,
    cell_size_mm: f64,
    board_thickness_mm: f64,
    h_conv: f64,
    heatsink_edge: String,
) -> (Vec<i64>, Vec<i64>, Vec<f64>, Vec<f64>) {
    temper_py_bridge::catch_unwind(|| {
        assemble_convective_system_inner(
            k_field_bytes,
            q_bytes,
            h_field_bytes,
            height_cells,
            width_cells,
            ambient_c,
            cell_size_mm,
            board_thickness_mm,
            h_conv,
            heatsink_edge,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
    .unwrap_or_default()
}

fn assemble_convective_system_inner(
    k_field_bytes: Vec<u8>,
    q_bytes: Vec<u8>,
    h_field_bytes: Option<Vec<u8>>,
    height_cells: usize,
    width_cells: usize,
    ambient_c: f64,
    cell_size_mm: f64,
    board_thickness_mm: f64,
    h_conv: f64,
    heatsink_edge: String,
) -> (Vec<i64>, Vec<i64>, Vec<f64>, Vec<f64>) {
    let k = parse_f64s(&k_field_bytes);
    let q = parse_f64s(&q_bytes);
    let hf = h_field_bytes.map(|b| parse_f64s(&b));
    let n = height_cells * width_cells;
    debug_assert_eq!(k.len(), n);
    debug_assert_eq!(q.len(), n);

    let (h, w) = (height_cells, width_cells);
    let cs = cell_size_mm;
    let dx2 = cs * cs;
    let dy2 = cs * cs;
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
                let coeff = k_n / dy2;
                rows.push(idx as i64);
                cols.push((idx + w) as i64);
                vals.push(-coeff);
                diag += coeff;
            } else if heatsink_face(row, col, "north", h, w, &hs) {
                let coeff = 2.0 * k_c / dy2;
                diag += coeff;
                b[idx] += coeff * ambient_c;
            }

            // South
            if row >= 1 {
                let k_s = harmonic(k_c, k[idx - w]);
                let coeff = k_s / dy2;
                rows.push(idx as i64);
                cols.push((idx - w) as i64);
                vals.push(-coeff);
                diag += coeff;
            } else if heatsink_face(row, col, "south", h, w, &hs) {
                let coeff = 2.0 * k_c / dy2;
                diag += coeff;
                b[idx] += coeff * ambient_c;
            }

            // Convective (Robin) boundary term at non-heatsink edge cells:
            // conv_coeff = h_conv * t_mm / cs * 1e-6 (left-to-right).
            if convective_edge_cell(row, col, h, w, &hs) {
                let conv_coeff = h_conv * board_thickness_mm / cs * 1e-6;
                diag += conv_coeff;
                b[idx] += conv_coeff * ambient_c;
            }

            // Through-plane heat-removal sink (U5-compatible, #141)
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

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/// Harmonic mean interface conductivity — exact reference operation order.
fn harmonic(k_a: f64, k_b: f64) -> f64 {
    2.0 / (1.0 / k_a + 1.0 / k_b)
}

/// True when (row, col) lies on the declared heatsink edge
/// (`_is_heatsink_edge_cell`).
fn heatsink_edge_cell(row: usize, col: usize, h: usize, w: usize, hs: &str) -> bool {
    match hs {
        "TOP" => row == h - 1,
        "BOTTOM" => row == 0,
        "LEFT" => col == 0,
        "RIGHT" => col == w - 1,
        _ => false,
    }
}

/// True when (row, col) is on one of the three NON-heatsink edges but NOT
/// on the heatsink edge (`_is_convective_edge_cell`).
fn convective_edge_cell(row: usize, col: usize, h: usize, w: usize, hs: &str) -> bool {
    let on_non_hs = (row == 0 && hs != "BOTTOM")
        || (row == h - 1 && hs != "TOP")
        || (col == 0 && hs != "LEFT")
        || (col == w - 1 && hs != "RIGHT");
    on_non_hs && !heatsink_edge_cell(row, col, h, w, hs)
}

/// True when the face in *direction* is the outer boundary in the heatsink
/// direction — the Dirichlet face (`_is_heatsink_boundary_face_u7`).
fn heatsink_face(row: usize, col: usize, direction: &str, h: usize, w: usize, hs: &str) -> bool {
    match direction {
        "north" => row == h - 1 && hs == "TOP",
        "south" => row == 0 && hs == "BOTTOM",
        "east" => col == w - 1 && hs == "RIGHT",
        _ => col == 0 && hs == "LEFT",
    }
}

fn parse_f64s(bytes: &[u8]) -> Vec<f64> {
    debug_assert_eq!(bytes.len() % 8, 0);
    bytes
        .chunks_exact(8)
        .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
        .collect()
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

    // --- conductivity field ---

    #[test]
    fn test_conductivity_field_matches_reference() {
        let k_fr4 = 0.3;
        let k_copper = 385.0;
        let t_mm = 1.6;
        let frac: Vec<f64> = vec![0.0, 0.25, 0.5, 1.0, 1.5, -0.5];
        let got = build_conductivity_field_inner(k_fr4, k_copper, t_mm, Some(f64_bytes(&frac)), 2, 3);
        let k_fr4_eff = k_fr4 * t_mm * 1e-3;
        let k_cu_eff = k_copper * t_mm * 1e-3;
        let expect: Vec<f64> = frac
            .iter()
            .map(|v| k_fr4_eff + (k_cu_eff - k_fr4_eff) * v.clamp(0.0, 1.0))
            .collect();
        let got_f: Vec<f64> = got
            .chunks_exact(8)
            .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
            .collect();
        assert_eq!(got_f, expect);
    }

    #[test]
    fn test_conductivity_field_uniform_when_no_copper() {
        let got = build_conductivity_field_inner(0.3, 385.0, 1.6, None, 4, 5);
        let got_f: Vec<f64> = got
            .chunks_exact(8)
            .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
            .collect();
        assert!(got_f.iter().all(|&v| v == 0.3 * 1.6 * 1e-3));
    }

    // --- heat-source field ---

    #[test]
    fn test_heat_source_field_matches_reference() {
        // Two overlapping devices, insertion order preserved.
        let devices = vec![
            ("A".to_string(), 3.0, 3.0),
            ("B".to_string(), 6.0, 3.0),
            ("C".to_string(), 5.0, 5.0),
        ];
        let powers = vec![("A".to_string(), 10.0), ("B".to_string(), 5.0), ("C".to_string(), 20.0)];
        let got = build_heat_source_field_inner(&devices, &powers, 0.0, 0.0, 1.0, 10, 10);
        let got_f: Vec<f64> = got
            .chunks_exact(8)
            .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
            .collect();
        // Reference semantics: device A covers cols 1..=7, rows 1..=7
        // (5mm footprint centered at 3.0 -> [0.5, 5.5] -> floor 0, ceil 6
        // wait: (3.0-2.5)/1 = 0.5 -> floor 0; (3.0+2.5)/1 = 5.5 -> ceil 6;
        // so cols 0..6, rows 0..6, n_cells = 36.
        let a = 10.0 / (36.0 * 1.0);
        // Device B at (6,3): (6-2.5)=3.5 -> floor 3; (6+2.5)=8.5 -> ceil 9;
        // cols 3..9, rows 0..6, n_cells = 36.
        let b = 5.0 / (36.0 * 1.0);
        // Device C at (5,5): (5-2.5)=2.5 -> floor 2; (5+2.5)=7.5 -> ceil 8;
        // cols 2..8, rows 2..8, n_cells = 36.
        let c = 20.0 / (36.0 * 1.0);
        let cell = |r: usize, ccol: usize| {
            let mut v = 0.0;
            if r < 6 && ccol < 6 {
                v += a;
            }
            if r < 6 && ccol >= 3 && ccol < 9 {
                v += b;
            }
            if r >= 2 && r < 8 && ccol >= 2 && ccol < 8 {
                v += c;
            }
            v
        };
        for r in 0..10 {
            for ccol in 0..10 {
                let idx = r * 10 + ccol;
                let expect = cell(r, ccol);
                assert_eq!(got_f[idx], expect, "cell ({r},{ccol})");
            }
        }
    }

    #[test]
    fn test_heat_source_field_zero_power_skipped() {
        let devices = vec![("Q1".to_string(), 5.0, 5.0)];
        let powers = vec![("Q1".to_string(), 0.0)];
        let got = build_heat_source_field_inner(&devices, &powers, 0.0, 0.0, 1.0, 10, 10);
        assert!(got.iter().all(|&b| b == 0));
    }

    #[test]
    fn test_heat_source_field_off_grid_high_is_noop() {
        let devices = vec![("Q1".to_string(), 500.0, 500.0)];
        let powers = vec![("Q1".to_string(), 15.0)];
        let got = build_heat_source_field_inner(&devices, &powers, 0.0, 0.0, 1.0, 10, 10);
        assert!(got.iter().all(|&b| b == 0));
    }

    #[test]
    fn test_heat_source_field_off_grid_low_wraps_like_numpy() {
        // Fully off-grid-low device: numpy slice [0:-2] wraps to [0, w-2).
        let devices = vec![("Q1".to_string(), -5.0, -5.0)];
        let powers = vec![("Q1".to_string(), 15.0)];
        let got = build_heat_source_field_inner(&devices, &powers, 0.0, 0.0, 1.0, 10, 12);
        let got_f: Vec<f64> = got
            .chunks_exact(8)
            .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
            .collect();
        // n_cells uses the clamped pre-wrap bounds: rows 0..-2 -> max(1, -4) = 1
        // hmm: row_min=0, row_max=min(10, ceil(-2.5))=-2 -> ( -2 - 0 ) = -2;
        // col same -> n_cells = max(1, 4) = 4; density = 15/4.
        let density = 15.0 / 4.0;
        for r in 0..10 {
            for c in 0..12 {
                let in_rows = r < 8; // wrapped [0:-2] -> rows 0..8
                let in_cols = c < 10; // wrapped [0:-2] -> cols 0..10
                let expect = if in_rows && in_cols { density } else { 0.0 };
                assert_eq!(got_f[r * 12 + c], expect, "cell ({r},{c})");
            }
        }
    }

    // --- convective assembly ---

    fn ref_assemble_convective(
        k: &[f64],
        q: &[f64],
        hf: Option<&[f64]>,
        h: usize,
        w: usize,
        ambient: f64,
        cs: f64,
        t_mm: f64,
        h_conv: f64,
        hs_edge: &str,
    ) -> (Vec<i64>, Vec<i64>, Vec<f64>, Vec<f64>) {
        // The Python reference, verbatim.
        let dx2 = cs * cs;
        let dy2 = cs * cs;
        let mut rows = Vec::new();
        let mut cols = Vec::new();
        let mut vals = Vec::new();
        let mut b = vec![0.0f64; h * w];
        let hs = hs_edge.to_uppercase();
        for row in 0..h {
            for col in 0..w {
                let idx = row * w + col;
                let mut diag = 0.0f64;
                let k_c = k[idx];
                // east
                if col + 1 < w {
                    let k_e = 2.0 / (1.0 / k_c + 1.0 / k[row * w + col + 1]);
                    let coeff = k_e / dx2;
                    rows.push(idx as i64);
                    cols.push((row * w + col + 1) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if col == w - 1 && hs == "RIGHT" {
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
                } else if col == 0 && hs == "LEFT" {
                    let coeff = 2.0 * k_c / dx2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                // north
                if row + 1 < h {
                    let k_n = 2.0 / (1.0 / k_c + 1.0 / k[(row + 1) * w + col]);
                    let coeff = k_n / dy2;
                    rows.push(idx as i64);
                    cols.push(((row + 1) * w + col) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if row == h - 1 && hs == "TOP" {
                    let coeff = 2.0 * k_c / dy2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                // south
                if row >= 1 {
                    let k_s = 2.0 / (1.0 / k_c + 1.0 / k[(row - 1) * w + col]);
                    let coeff = k_s / dy2;
                    rows.push(idx as i64);
                    cols.push(((row - 1) * w + col) as i64);
                    vals.push(-coeff);
                    diag += coeff;
                } else if row == 0 && hs == "BOTTOM" {
                    let coeff = 2.0 * k_c / dy2;
                    diag += coeff;
                    b[idx] += coeff * ambient;
                }
                // convective edge term (Robin) — non-heatsink edge cells
                let on_edge = (row == 0 && hs != "BOTTOM")
                    || (row == h - 1 && hs != "TOP")
                    || (col == 0 && hs != "LEFT")
                    || (col == w - 1 && hs != "RIGHT");
                let is_hs_cell = match hs.as_str() {
                    "TOP" => row == h - 1,
                    "BOTTOM" => row == 0,
                    "LEFT" => col == 0,
                    "RIGHT" => col == w - 1,
                    _ => false,
                };
                if on_edge && !is_hs_cell {
                    let conv_coeff = h_conv * t_mm / cs * 1e-6;
                    diag += conv_coeff;
                    b[idx] += conv_coeff * ambient;
                }
                // sink
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
                for h_conv in [0.0, 10.0] {
                    let got = assemble_convective_system_inner(
                        f64_bytes(&k),
                        f64_bytes(&q),
                        hf.clone().map(|v| f64_bytes(&v)),
                        h,
                        w,
                        40.0,
                        0.5,
                        1.6,
                        h_conv,
                        hs.to_string(),
                    );
                    let expect = ref_assemble_convective(
                        &k, &q, hf.as_deref(), h, w, 40.0, 0.5, 1.6, h_conv, hs,
                    );
                    assert_eq!(got, expect, "heatsink={hs} h_field={} h_conv={h_conv}", hf.is_some());
                }
            }
        }
    }

    #[test]
    fn test_assembly_single_cell_grid() {
        let k = vec![0.5];
        let q = vec![0.2];
        for hs in ["TOP", "BOTTOM", "LEFT", "RIGHT"] {
            let got = assemble_convective_system_inner(
                f64_bytes(&k), f64_bytes(&q), None, 1, 1, 40.0, 1.0, 1.6, 10.0, hs.to_string(),
            );
            let expect = ref_assemble_convective(&k, &q, None, 1, 1, 40.0, 1.0, 1.6, 10.0, hs);
            assert_eq!(got, expect, "heatsink={hs}");
            // Single cell on a 1x1 grid sits on EVERY edge, so it is a
            // heatsink-edge cell for any declared heatsink edge: the face
            // in the heatsink direction is Dirichlet and the cell gets NO
            // convective term (is_convective_edge_cell excludes heatsink
            // cells).  diagonal = 2*k_c/dx2; b = coeff*ambient + q.
            assert_eq!(got.2[0], 2.0 * 0.5 / 1.0);
            assert_eq!(got.3[0], 2.0 * 0.5 / 1.0 * 40.0 + 0.2);
        }
    }
}
