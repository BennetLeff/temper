//! Sparse direct solve kernel — the faer sparse-LU solver that replaces
//! scipy `spsolve` (SuperLU) for the FDM systems of both U5
//! (`thermal_fdm.py`) and U7 (`thermal_scorer.py`).
//!
//! The solve is a *direct* factorization (same algorithm class as
//! SuperLU), so it is deterministic given the matrix and RHS. It is NOT
//! bit-identical to SuperLU — the two libraries pivot and fill
//! differently, so the forward solution differs in the last ulp. The
//! divergence is measured and pinned by
//! `tests/physics/test_thermal_solve_rust_differential.py` (max
//! |T_faer − T_scipy| ≈ 5.7e-12 K over the 144-case FDM corpus,
//! 2026-08-09), and every consumer of the temperature field compares
//! via a physics tolerance ≥ 1e-9 K — see the "Sparse solve kernel
//! (U5/U7) — characterization and migration decision" section of
//! `VERIFICATION.md` for the full record (the KTD9 keep is overturned
//! there under the wave-4 re-decidable rule).
//!
//! Adoption of this kernel is what closed the last two scipy imports in
//! `packages/temper-placer/src` (the `coo_matrix`/`spsolve` calls that
//! used to live in `thermal_fdm._assemble_system` and
//! `thermal_scorer._convective_fdm_solve`).

/// Solve A·x = b with faer's sparse LU (partial row pivoting), given the
/// matrix as COO triplets. Returns the solution vector, or an Err
/// (message) on malformed input or a singular matrix.///
/// `rows`/`cols`/`values` are the COO triplets (as produced by the
/// `assemble_system_py` / `assemble_convective_system_py` kernels);
/// `b` is the RHS vector; `n` is the matrix dimension. Validation is
/// explicit and fallible (the caller's Python wrapper surfaces failures
/// as exceptions) — no panics on malformed input.
pub fn solve_sparse_lu(
    rows: &[usize],
    cols: &[usize],
    values: &[f64],
    b: &[f64],
    n: usize,
) -> Result<Vec<f64>, String> {
    if rows.len() != cols.len() || rows.len() != values.len() {
        return Err(format!(
            "triplet length mismatch: rows={} cols={} values={}",
            rows.len(),
            cols.len(),
            values.len()
        ));
    }
    if b.len() != n {
        return Err(format!(
            "rhs length {} != matrix dimension {n}",
            b.len()
        ));
    }
    for (i, (&r, &c)) in rows.iter().zip(cols.iter()).enumerate() {
        if r >= n || c >= n {
            return Err(format!(
                "triplet {i} out of range: ({r}, {c}) for dimension {n}"
            ));
        }
    }

    use faer::linalg::solvers::Solve;

    let triplets: Vec<faer::sparse::Triplet<usize, usize, f64>> = rows
        .iter()
        .zip(cols.iter())
        .zip(values.iter())
        .map(|((&r, &c), &v)| faer::sparse::Triplet::new(r, c, v))
        .collect();
    let mat = faer::sparse::SparseColMat::<usize, f64>::try_new_from_triplets(n, n, &triplets)
        .map_err(|e| format!("triplet construction: {e:?}"))?;
    let rhs = faer::col::Col::from_fn(n, |i| b[i]);
    let lu = mat
        .sp_lu()
        .map_err(|e| format!("sp_lu factorization (singular matrix?): {e:?}"))?;
    let x = lu.solve(&rhs);
    Ok((0..n).map(|i| x[i]).collect::<Vec<f64>>())
}

/// PyO3 wrapper: parses the RHS byte buffer, runs `solve_sparse_lu`,
/// and returns the solution as little-endian f64 bytes. All failures
/// surface as `ValueError` (never a panic across the FFI boundary).
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyBytes;
#[cfg(feature = "python")]
use temper_py_bridge;

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (rows, cols, values, b_bytes, n))]
pub fn solve_sparse_lu_py(
    py: Python<'_>,
    rows: Vec<usize>,
    cols: Vec<usize>,
    values: Vec<f64>,
    b_bytes: Vec<u8>,
    n: usize,
) -> PyResult<Bound<'_, PyBytes>> {
    let x: Vec<f64> = temper_py_bridge::catch_unwind(|| {
        if b_bytes.len() != n * 8 {
            return Err(format!(
                "rhs byte buffer length {} != {n} floats",
                b_bytes.len()
            ));
        }
        let b: Vec<f64> = b_bytes
            .chunks_exact(8)
            .map(|c| {
                let mut a = [0u8; 8];
                a.copy_from_slice(c);
                f64::from_le_bytes(a)
            })
            .collect();
        solve_sparse_lu(&rows, &cols, &values, &b, n)
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(PyErr::new::<pyo3::exceptions::PyValueError, _>)?;
    let mut out = Vec::with_capacity(x.len() * 8);
    for v in x {
        out.extend_from_slice(&v.to_le_bytes());
    }
    PyBytes::new_with(py, out.len(), |buf| {
        buf.copy_from_slice(&out);
        Ok(())
    })
}

#[cfg(test)]
mod tests {
    // The crate denies `unwrap`/`expect` in production code (Cargo.toml
    // `[lints.clippy]`); a failing unwrap in a test IS the test failure,
    // so the test modules lift the lint locally (same convention as
    // `heat_removal.rs`).
    #![allow(clippy::expect_used, clippy::unwrap_used)]

    use super::*;

    #[test]
    fn solves_trivial_1x1_system() {
        // [2] x = [4]  ->  x = [2]
        let x = solve_sparse_lu(&[0], &[0], &[2.0], &[4.0], 1).unwrap();
        assert_eq!(x, vec![2.0]);
    }

    #[test]
    fn solves_2x2_diagonal_system() {
        // diag(3, 5) x = [6, 15] -> x = [2, 3]
        let x = solve_sparse_lu(&[0, 1], &[0, 1], &[3.0, 5.0], &[6.0, 15.0], 2).unwrap();
        assert_eq!(x, vec![2.0, 3.0]);
    }

    #[test]
    fn solves_tridiagonal_system() {
        // [4 -1 0; -1 4 -1; 0 -1 4] x = [1; 2; 3]
        let rows = vec![0usize, 0, 1, 1, 1, 2, 2];
        let cols = vec![0usize, 1, 0, 1, 2, 1, 2];
        let vals = vec![4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0];
        let b = vec![1.0, 2.0, 3.0];
        let x = solve_sparse_lu(&rows, &cols, &vals, &b, 3).unwrap();
        let residual = (0..3)
            .map(|r| {
                let row: Vec<(usize, f64)> = rows
                    .iter()
                    .zip(cols.iter())
                    .zip(vals.iter())
                    .filter(|((&rr, _), _)| rr == r)
                    .map(|((_, &c), &v)| (c, v))
                    .collect();
                row.iter().map(|(c, v)| v * x[*c]).sum::<f64>()
            })
            .collect::<Vec<f64>>();
        for (r, expected) in residual.iter().zip(b.iter()) {
            assert!((r - expected).abs() < 1e-12, "{r} vs {expected}");
        }
    }

    #[test]
    fn rejects_length_mismatch() {
        assert!(solve_sparse_lu(&[0, 1], &[0], &[2.0, 3.0], &[4.0], 2).is_err());
        assert!(solve_sparse_lu(&[0], &[0], &[2.0], &[4.0, 5.0], 2).is_err());
    }

    #[test]
    fn rejects_out_of_range_triplets() {
        assert!(solve_sparse_lu(&[0, 2], &[0, 0], &[2.0, 3.0], &[4.0, 5.0], 2).is_err());
    }

    #[test]
    fn singular_matrix_returns_nonfinite_not_err() {
        // A singular matrix does NOT raise through faer (sp_lu succeeds and
        // the back-substitution yields a non-finite value). This matches the
        // pre-migration scipy behavior, which emits a RuntimeWarning and
        // returns NaN rather than raising — both solvers are non-raising on
        // a singular matrix, so the Python wrapper's fail-closed path is not
        // the behavior a singular matrix exercises (same as before).
        let x = solve_sparse_lu(&[0, 1], &[0, 1], &[0.0, 5.0], &[4.0, 5.0], 2).unwrap();
        assert!(!x[0].is_finite(), "singular solve must yield a non-finite value, got {x:?}");
        assert_eq!(x[1], 1.0);
    }

    #[test]
    fn deterministic_across_calls() {
        let rows = vec![0usize, 1];
        let cols = vec![0usize, 1];
        let vals = vec![2.0, 7.0];
        let b = vec![4.0, 21.0];
        let x1 = solve_sparse_lu(&rows, &cols, &vals, &b, 2).unwrap();
        let x2 = solve_sparse_lu(&rows, &cols, &vals, &b, 2).unwrap();
        assert_eq!(x1, x2);
        assert_eq!(x1.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
                   x2.iter().map(|v| v.to_bits()).collect::<Vec<_>>());
    }
}
