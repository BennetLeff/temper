//! Typed COO-triplet container — Phase A (U7).
//!
//! Python reference: `temper_placer/core/hypergraph.py`'s `Coo` dataclass
//! (the pre-migration source is pinned verbatim by
//! `packages/temper-placer/tests/core/test_hypergraph_coo_rust_differential.py`
//! and by `test_core_graph_cluster_rust_differential.py`'s `_oracle_coo_matmul`).
//! This unit (rust-orchestration plan
//! `docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md`,
//! Phase A table row for `core/hypergraph.py`) replaces the numpy-array
//! container with a **typed** pyclass whose storage is Rust `Vec` fields
//! (`row`/`col`: `Vec<i64>`, `data`: `Vec<f64>`, `shape`), making the
//! `hypergraph_coo_matvec` kernel's I/O typed at the boundary.
//!
//! # What stays numpy — and why (bit-exactness by delegation)
//!
//! The Python-visible surface is unchanged from the dataclass: `row`, `col`,
//! `data` and the `@` result are **numpy arrays**, because downstream
//! consumers and the existing differential/PBT suites read them as such
//! (`.row.tolist()`, `_arr(data)`'s `(dtype.str, shape, tobytes())` key in
//! the retained hypergraph-kernel tests, `got.shape[0]`,
//! elementwise indexing).  The getters therefore materialize fresh numpy
//! arrays *by calling numpy itself* (`numpy.array(vec, dtype=...)`) — the
//! dtype is preserved for `data` (the factory builds `float32`; the getter
//! returns `float32`, whose `f64`-stored values round-trip exactly), and
//! `row`/`col` return `int64` exactly as the factory constructs them.
//! Nothing is re-implemented Rust-side; numpy produces the bits.
//!
//! # Why `__matmul__` calls the kernel through Python, not a Rust link
//!
//! `hypergraph_coo_matvec` lives in `temper-geometry`.  The scatter-add must
//! be *the same code path* the pre-migration shim used, and the anti-vacuity
//! mutation guards in `test_core_graph_cluster_pbt.py` patch the Python-level
//! `temper_geometry.hypergraph_coo_matvec_py` attribute and re-run the
//! properties — a Rust-side direct call would bypass the mutation and turn
//! those vacuity guards into dead checks.  This method therefore imports
//! `temper_geometry` at call time and invokes the pyfunction (the same
//! lazy-import pattern `netlist_contracts.rs` uses for numpy), passing the
//! identical argument shape the shim passed: int64 `row`/`col`, float64
//! `data` (the shim's `data.astype(np.float64)` is implicit — the storage is
//! already `f64`), `n_rows`, and the caller's `other` object.  The kernel
//! validates and scatter-adds bit-identically, including the `minlength`
//! length extension, negative-`col` wrapping, and the oracle's
//! `IndexError`/`ValueError` raises.
//!
//! # Documented deviations (data-only; see `VERIFICATION.md`)
//!
//! - The constructor is typed (`Vec<i64>`/`Vec<f64>` extraction), so a
//!   non-numeric payload raises a pyo3 `TypeError` at construction where the
//!   duck-typed dataclass would have accepted it and failed later (or never).
//!   Every in-repo construction path passes int64/float32/float64 numpy
//!   arrays, which pyo3 extracts natively.
//! - `__eq__`/`__hash__` reproduce the frozen dataclass faithfully: equality
//!   compares the field tuples through Python (raising numpy's ambiguous-truth
//!   `ValueError` for distinct array objects, exactly as the dataclass does),
//!   and hashing raises `TypeError: unhashable type: 'numpy.ndarray'`.

use std::panic::AssertUnwindSafe;

use pyo3::exceptions::PyTypeError;
use pyo3::IntoPyObjectExt;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};

use crate::netlist_contracts::{dataclass_eq, dataclass_repr, repr_of};

/// `numpy` module handle — imported lazily at call time so importing the
/// extension never forces numpy (matching the `netlist_contracts.rs` pattern;
/// the oracle's shim imports numpy at module scope, but the extension is
/// imported by far more callers).
fn numpy(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "numpy")
}

fn np_array_from_f64(py: Python<'_>, values: &[f64], dtype: &str) -> PyResult<Py<PyAny>> {
    let np = numpy(py)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", np.getattr(dtype)?)?;
    let list = PyList::new(py, values.iter().copied())?;
    Ok(np.getattr("array")?.call((list,), Some(&kwargs))?.unbind())
}

fn np_array_from_i64(py: Python<'_>, values: &[i64]) -> PyResult<Py<PyAny>> {
    let np = numpy(py)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", np.getattr("int64")?)?;
    let list = PyList::new(py, values.iter().copied())?;
    Ok(np.getattr("array")?.call((list,), Some(&kwargs))?.unbind())
}

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at the compute boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// The stored `data` dtype, preserved so the getter materializes the same
/// numpy dtype the caller constructed with (the factory builds `float32`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DataDtype {
    F64,
    F32,
}

/// Typed COO-triplet container — the marshalling boundary of the
/// `hypergraph_coo_matvec` kernel (see the module docstring).
#[pyclass(frozen, from_py_object, module = "temper_design_bundle_python.hypergraph_contracts")]
#[derive(Debug, Clone)]
pub struct Coo {
    row: Vec<i64>,
    col: Vec<i64>,
    data: Vec<f64>,
    data_dtype: DataDtype,
    shape: (usize, usize),
}

impl Coo {
    fn data_is_float32(py: Python<'_>, data: &Bound<'_, PyAny>) -> PyResult<bool> {
        let np = numpy(py)?;
        let ndarray = np.getattr("ndarray")?;
        if data.is_instance(&ndarray)? {
            let dtype_name: String = data.getattr("dtype")?.getattr("name")?.extract()?;
            return Ok(dtype_name == "float32");
        }
        Ok(false)
    }

    fn np_row(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        np_array_from_i64(py, &self.row)
    }

    fn np_col(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        np_array_from_i64(py, &self.col)
    }

    fn np_data(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self.data_dtype {
            DataDtype::F32 => np_array_from_f64(py, &self.data, "float32"),
            DataDtype::F64 => np_array_from_f64(py, &self.data, "float64"),
        }
    }
}

#[pymethods]
impl Coo {
    #[new]
    #[pyo3(signature = (row, col, data, shape))]
    fn new(
        py: Python<'_>,
        row: Vec<i64>,
        col: Vec<i64>,
        data: &Bound<'_, PyAny>,
        shape: (usize, usize),
    ) -> PyResult<Self> {
        let data_dtype = if Self::data_is_float32(py, data)? {
            DataDtype::F32
        } else {
            DataDtype::F64
        };
        let data: Vec<f64> = data.extract()?;
        Ok(Self { row, col, data, data_dtype, shape })
    }

    /// `(nnz,)` row-index array (materialized int64 numpy, exactly as the
    /// factory constructs it).
    #[getter]
    fn row(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.np_row(py)
    }

    /// `(nnz,)` column-index array (materialized int64 numpy).
    #[getter]
    fn col(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.np_col(py)
    }

    /// `(nnz,)` value array, dtype preserved from construction (`float32` for
    /// the factory's `np.array(data, dtype=np.float32)`, else `float64`).
    #[getter]
    fn data(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.np_data(py)
    }

    /// Matrix dimensions `(N_nodes, N_hyperedges)`.
    #[getter]
    fn shape(&self) -> (usize, usize) {
        self.shape
    }

    /// Number of stored triplets.
    #[getter]
    fn nnz(&self) -> usize {
        self.data.len()
    }

    /// The transpose container — `Coo(row=self.col, col=self.row, ...)`,
    /// dtype and values preserved, exactly as the dataclass's `.T` did.
    #[allow(non_snake_case)]
    #[getter]
    fn T(&self) -> Self {
        Self {
            row: self.col.clone(),
            col: self.row.clone(),
            data: self.data.clone(),
            data_dtype: self.data_dtype,
            shape: (self.shape.1, self.shape.0),
        }
    }

    /// Sparse matrix-vector product `self @ other`, bit-identical to the
    /// pre-migration `Coo.__matmul__` (see the module docstring).
    fn __matmul__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        guard(|| {
            let np = numpy(py)?;
            let n_rows = self.shape.0;
            // `if self.nnz == 0: return np.zeros(n_rows, dtype=np.float64)`
            // — checked BEFORE the kernel call, like the oracle.
            if self.data.is_empty() {
                let kwargs = PyDict::new(py);
                kwargs.set_item("dtype", np.getattr("float64")?)?;
                return np.getattr("zeros")?.call((n_rows,), Some(&kwargs))?.unbind().into_py_any(py);
            }
            let tg = PyModule::import(py, "temper_geometry")?;
            let kernel = tg.getattr("hypergraph_coo_matvec_py")?;
            let row_arr = np_array_from_i64(py, &self.row)?;
            let col_arr = np_array_from_i64(py, &self.col)?;
            let data_arr = np_array_from_f64(py, &self.data, "float64")?;
            let result: Vec<f64> = kernel
                .call((row_arr, col_arr, data_arr, n_rows as i64, other), None)?
                .extract()?;
            // `np.array(result)` — the shim's float64 wrap of the kernel row.
            np.getattr("array")?.call1((result,))?.unbind().into_py_any(py)
        })
    }

    /// Frozen dataclass `__repr__`: `Coo(row=..., col=..., data=..., shape=...)`
    /// with numpy's own array reprs.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let row = self.np_row(py)?;
        let col = self.np_col(py)?;
        let data = self.np_data(py)?;
        let shape: Py<PyAny> = (self.shape.0, self.shape.1).into_bound_py_any(py)?.unbind();
        Ok(dataclass_repr(
            "Coo",
            &[
                ("row", repr_of(&row, py)?),
                ("col", repr_of(&col, py)?),
                ("data", repr_of(&data, py)?),
                ("shape", repr_of(&shape, py)?),
            ],
        ))
    }

    /// Frozen dataclass `__eq__`: compares the field tuples through Python —
    /// which, for distinct numpy array objects, raises numpy's ambiguous-truth
    /// `ValueError` exactly as the dataclass does (and returns `NotImplemented`
    /// for a foreign class).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let this = slf.borrow();
        let lhs = vec![
            this.np_row(py)?,
            this.np_col(py)?,
            this.np_data(py)?,
            (this.shape.0, this.shape.1).into_bound_py_any(py)?.unbind(),
        ];
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            let o = o.cast::<Self>()?;
            let o = o.borrow();
            Ok(vec![
                o.np_row(py)?,
                o.np_col(py)?,
                o.np_data(py)?,
                (o.shape.0, o.shape.1).into_bound_py_any(py)?.unbind(),
            ])
        })
    }

    /// `eq=True, frozen=True` with numpy fields → the dataclass's generated
    /// `__hash__` raises `TypeError: unhashable type: 'numpy.ndarray'`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'numpy.ndarray'"))
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "hypergraph_contracts")?;
    sub.add_class::<Coo>()?;
    module.add_submodule(&sub)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests (no Python objects involved — pure Rust semantics)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn coo() -> Coo {
        Coo {
            row: vec![0, 1],
            col: vec![0, 1],
            data: vec![2.0, 3.0],
            data_dtype: DataDtype::F64,
            shape: (2, 2),
        }
    }

    #[test]
    fn transpose_swaps_row_col_and_shape() {
        let t = coo().T();
        assert_eq!(t.row, vec![0, 1]);
        assert_eq!(t.col, vec![0, 1]);
        assert_eq!(t.data, vec![2.0, 3.0]);
        assert_eq!(t.shape, (2, 2));
    }

    #[test]
    fn transpose_rectangular_swaps_dims() {
        let c = Coo {
            row: vec![0, 1, 1],
            col: vec![0, 0, 1],
            data: vec![1.0, 1.0, 1.0],
            data_dtype: DataDtype::F64,
            shape: (2, 2),
        };
        let t = c.T();
        assert_eq!(t.shape, (2, 2));
        assert_eq!(t.row, vec![0, 0, 1]);
        assert_eq!(t.col, vec![0, 1, 1]);
    }

    #[test]
    fn nnz_is_data_len() {
        let c = coo();
        assert_eq!(c.nnz(), 2);
        let empty = Coo {
            row: vec![],
            col: vec![],
            data: vec![],
            data_dtype: DataDtype::F64,
            shape: (3, 4),
        };
        assert_eq!(empty.nnz(), 0);
    }

    #[test]
    fn float32_marker_preserved_across_transpose() {
        let c = Coo {
            row: vec![0],
            col: vec![0],
            data: vec![1.5],
            data_dtype: DataDtype::F32,
            shape: (1, 1),
        };
        assert_eq!(c.T().data_dtype, DataDtype::F32);
    }
}
