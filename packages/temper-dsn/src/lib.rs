//! Thin pyo3 adapter over the [`dsn`] module.
//!
//! Each `#[pyfunction]` delegates to pure-Rust logic in `dsn.rs`, which is
//! also where the unit tests live.

pub mod dsn;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use std::collections::HashMap;

#[cfg(feature = "python")]
#[pyfunction]
fn normalize_dsn(dsn_text: &str) -> PyResult<String> {
    Ok(dsn::normalize_dsn(dsn_text))
}

#[cfg(feature = "python")]
#[pyfunction]
fn is_dsn_normalized(dsn_text: &str) -> PyResult<bool> {
    Ok(dsn::is_dsn_normalized(dsn_text))
}

#[cfg(feature = "python")]
#[pyfunction]
fn strip_control_chars(dsn_text: &str) -> PyResult<String> {
    Ok(dsn::strip_control_chars(dsn_text))
}

#[cfg(feature = "python")]
#[pyfunction]
fn compute_dsn_schema_hash(
    layer_names: Vec<String>,
    layer_types: HashMap<String, String>,
    footprints: HashMap<String, usize>,
    nets: Vec<String>,
) -> PyResult<String> {
    Ok(dsn::compute_dsn_schema_hash(
        layer_names, layer_types, footprints, nets,
    ))
}

#[cfg(feature = "python")]
#[pyfunction]
fn embed_schema_header(dsn_text: &str, schema_hash: &str) -> PyResult<String> {
    Ok(dsn::embed_schema_header(dsn_text, schema_hash))
}

#[cfg(feature = "python")]
#[pyfunction]
fn extract_schema_hash(dsn_text: &str) -> PyResult<Option<String>> {
    Ok(dsn::extract_schema_hash(dsn_text))
}

#[cfg(feature = "python")]
#[pyfunction]
fn validate_dsn(dsn_text: &str, expected_hash: &str) -> PyResult<()> {
    dsn::validate_dsn(dsn_text, expected_hash).map_err(|e| match e {
        dsn::DsnValidationError::HashMismatch { expected, received } => {
            let msg = format!(
                "DSN schema version mismatch: expected sha256:{}, got sha256:{}. \
                 The upstream stage may have changed its output format.",
                expected, received,
            );
            PyErr::new::<pyo3::exceptions::PyValueError, _>(msg)
        }
    })
}

#[cfg(feature = "python")]
#[pyfunction]
fn validate_or_warn_dsn(dsn_text: &str, expected_hash: &str) -> PyResult<bool> {
    Ok(dsn::validate_or_warn_dsn(dsn_text, expected_hash))
}

#[cfg(feature = "python")]
#[pymodule]
fn temper_dsn(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(normalize_dsn, m)?)?;
    m.add_function(wrap_pyfunction!(is_dsn_normalized, m)?)?;
    m.add_function(wrap_pyfunction!(strip_control_chars, m)?)?;
    m.add_function(wrap_pyfunction!(compute_dsn_schema_hash, m)?)?;
    m.add_function(wrap_pyfunction!(embed_schema_header, m)?)?;
    m.add_function(wrap_pyfunction!(extract_schema_hash, m)?)?;
    m.add_function(wrap_pyfunction!(validate_dsn, m)?)?;
    m.add_function(wrap_pyfunction!(validate_or_warn_dsn, m)?)?;
    Ok(())
}
