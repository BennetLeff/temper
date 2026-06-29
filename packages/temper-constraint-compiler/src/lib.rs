pub mod desugar_tier0;
pub mod desugar_tier1;
pub mod ir_tier0;
pub mod ir_tier1;
pub mod provenance;
pub mod pyo3_bridge;
pub mod type_lattice;

use pyo3::prelude::*;

#[pyfunction]
fn compile_pcl_constraints(
    _py: Python<'_>,
    _pcl_dicts: &Bound<'_, pyo3::types::PyList>,
    _net_class_dicts: &Bound<'_, pyo3::types::PyDict>,
    _component_map: &Bound<'_, pyo3::types::PyDict>,
    _zone_map: &Bound<'_, pyo3::types::PyDict>,
    _skeletons: &Bound<'_, pyo3::types::PyList>,
    _channel_widths: &Bound<'_, pyo3::types::PyDict>,
    _existing_vars: &Bound<'_, pyo3::types::PyList>,
    _existing_cons: &Bound<'_, pyo3::types::PyList>,
    _net_names: Vec<String>,
) -> PyResult<PyObject> {
    Err(PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>(
        "compile_pcl_constraints not yet implemented",
    ))
}

#[pyclass]
struct PyCompiler {
    #[allow(dead_code)]
    _placeholder: u8,
}

#[pymethods]
impl PyCompiler {
    #[new]
    fn new(_net_class_dicts: &Bound<'_, pyo3::types::PyDict>) -> PyResult<Self> {
        Err(PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>(
            "PyCompiler not yet implemented",
        ))
    }

    fn compile(&self, _pcl_dicts: Vec<PyObject>, _net_names: Vec<String>) -> PyResult<PyObject> {
        Err(PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>(
            "PyCompiler.compile not yet implemented",
        ))
    }

    fn recompile_delta(&self, _changed_net_indices: Vec<usize>) -> PyResult<PyObject> {
        Err(PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>(
            "PyCompiler.recompile_delta not yet implemented",
        ))
    }

    fn reverse_map_unsat_core(&self, _unsat_core_indices: Vec<usize>) -> PyResult<PyObject> {
        Err(PyErr::new::<pyo3::exceptions::PyNotImplementedError, _>(
            "PyCompiler.reverse_map_unsat_core not yet implemented",
        ))
    }
}

#[pymodule]
fn temper_constraint_compiler(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compile_pcl_constraints, m)?)?;
    m.add_class::<PyCompiler>()?;
    Ok(())
}
