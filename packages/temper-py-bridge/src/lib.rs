// =============================================================================
// temper-py-bridge — shared PyO3 bridge utilities for all temper Rust crates
// =============================================================================
//
// Provides:
//  - catch_unwind utility to prevent Rust panics from aborting the Python process
//  - Error helpers: py_runtime_err, py_value_err, panic_to_err
//  - Dict extraction trait: extract_str, extract_f64, extract_opt_str, etc.
//  - Re-exports of FromPyDict / ToPyDict derive macros
//
// =============================================================================

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::panic;

pub use temper_py_bridge_derive::{FromPyDict, ToPyDict};

// ---------------------------------------------------------------------------
// catch_unwind utilities
// ---------------------------------------------------------------------------

/// Convert a panic payload into a PyRuntimeError with a descriptive message.
pub fn panic_to_err(e: Box<dyn std::any::Any + Send>) -> PyErr {
    let msg = if let Some(s) = e.downcast_ref::<String>() {
        s.clone()
    } else if let Some(s) = e.downcast_ref::<&str>() {
        s.to_string()
    } else {
        "unknown panic".to_string()
    };
    PyRuntimeError::new_err(msg)
}

/// Catch Rust panics and convert them to Python RuntimeError.
///
/// Returns `PyResult<T>` — on panic, the panic message is returned as
/// a Python RuntimeError; on success, the result is passed through.
///
/// # Example
///
/// ```ignore
/// use temper_py_bridge::catch_unwind;
///
/// #[pyfunction]
/// fn my_func() -> PyResult<f64> {
///     catch_unwind(|| crate::core::compute()).map_err(temper_py_bridge::panic_to_err)
/// }
/// ```
pub fn catch_unwind<F, R>(f: F) -> Result<R, Box<dyn std::any::Any + Send>>
where
    F: FnOnce() -> R + std::panic::UnwindSafe,
{
    panic::catch_unwind(f)
}

/// Convenience: `catch_unwind` with automatic panic→PyRuntimeError conversion.
///
/// # Example
///
/// ```ignore
/// use temper_py_bridge::catch_panic;
///
/// #[pyfunction]
/// fn my_func() -> PyResult<f64> {
///     catch_panic(|| crate::core::compute())
/// }
/// ```
pub fn catch_panic<F, R>(f: F) -> PyResult<R>
where
    F: FnOnce() -> PyResult<R>,
{
    match panic::catch_unwind(panic::AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(panic_info) => {
            let msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic".to_string()
            };
            Err(PyRuntimeError::new_err(msg))
        }
    }
}

// ---------------------------------------------------------------------------
// PyErr helpers
// ---------------------------------------------------------------------------

/// Create a PyRuntimeError from a displayable message.
pub fn py_runtime_err(msg: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(msg.to_string())
}

/// Create a PyValueError from a displayable message.
pub fn py_value_err(msg: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(msg.to_string())
}

// ---------------------------------------------------------------------------
// Dict extraction trait
// ---------------------------------------------------------------------------

/// Extension trait providing PyDict extraction methods on `&Bound<'_, PyDict>`.
pub trait DictExtract<'py> {
    fn extract_str(&self, key: &str) -> PyResult<String>;
    fn extract_opt_str(&self, key: &str) -> PyResult<Option<String>>;
    fn extract_f64(&self, key: &str, default: f64) -> PyResult<f64>;
    fn extract_f64_required(&self, key: &str) -> PyResult<f64>;
    fn extract_opt_f64(&self, key: &str) -> PyResult<Option<f64>>;
    fn extract_bool(&self, key: &str) -> PyResult<bool>;
    fn extract_opt_bool(&self, key: &str) -> PyResult<Option<bool>>;
    fn extract_bool_default(&self, key: &str, default: bool) -> PyResult<bool>;
    fn extract_str_list(&self, key: &str) -> PyResult<Vec<String>>;
    fn extract_dict_list(&self, key: &str) -> PyResult<Vec<Bound<'py, PyDict>>>;
    fn extract_dict(&self, key: &str) -> PyResult<Bound<'py, PyDict>>;
    fn extract_opt_dict(&self, key: &str) -> PyResult<Option<Bound<'py, PyDict>>>;
}

impl<'py> DictExtract<'py> for Bound<'py, PyDict> {
    fn extract_str(&self, key: &str) -> PyResult<String> {
        self.get_item(key)?
            .ok_or_else(|| py_value_err(format!("missing required key: {key}")))?
            .extract::<String>()
            .map_err(|e| py_value_err(format!("key '{key}' is not a string: {e}")))
    }

    fn extract_opt_str(&self, key: &str) -> PyResult<Option<String>> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => Ok(Some(val.extract::<String>().map_err(|e| {
                py_value_err(format!("key '{key}' is not a string: {e}"))
            })?)),
            _ => Ok(None),
        }
    }

    fn extract_f64(&self, key: &str, default: f64) -> PyResult<f64> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                val.extract::<f64>().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a number: {e}"))
                })
            }
            _ => Ok(default),
        }
    }

    fn extract_f64_required(&self, key: &str) -> PyResult<f64> {
        self.get_item(key)?
            .ok_or_else(|| py_value_err(format!("missing required key: {key}")))?
            .extract::<f64>()
            .map_err(|e| py_value_err(format!("key '{key}' is not a number: {e}")))
    }

    fn extract_opt_f64(&self, key: &str) -> PyResult<Option<f64>> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                let v: f64 = val.extract().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a number: {e}"))
                })?;
                Ok(Some(v))
            }
            _ => Ok(None),
        }
    }

    fn extract_bool(&self, key: &str) -> PyResult<bool> {
        self.get_item(key)?
            .ok_or_else(|| py_value_err(format!("missing required key: {key}")))?
            .extract::<bool>()
            .map_err(|e| py_value_err(format!("key '{key}' is not a bool: {e}")))
    }

    fn extract_opt_bool(&self, key: &str) -> PyResult<Option<bool>> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                let v: bool = val.extract().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a bool: {e}"))
                })?;
                Ok(Some(v))
            }
            _ => Ok(None),
        }
    }

    fn extract_bool_default(&self, key: &str, default: bool) -> PyResult<bool> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                val.extract::<bool>().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a bool: {e}"))
                })
            }
            _ => Ok(default),
        }
    }

    fn extract_str_list(&self, key: &str) -> PyResult<Vec<String>> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                let list: Bound<'_, PyList> = val.cast_into::<PyList>().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a list: {e}"))
                })?;
                let mut result = Vec::with_capacity(list.len());
                for item in list.iter() {
                    result.push(item.extract::<String>().map_err(|e| {
                        py_value_err(format!("item in '{key}' list is not a string: {e}"))
                    })?);
                }
                Ok(result)
            }
            _ => Ok(Vec::new()),
        }
    }

    fn extract_dict_list(&self, key: &str) -> PyResult<Vec<Bound<'py, PyDict>>> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                let list: Bound<'_, PyList> = val.cast_into::<PyList>().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a list: {e}"))
                })?;
                let mut result = Vec::with_capacity(list.len());
                for item in list.iter() {
                    let d: Bound<'_, PyDict> = item.cast_into::<PyDict>().map_err(|e| {
                        py_value_err(format!("item in '{key}' list is not a dict: {e}"))
                    })?;
                    result.push(d.clone());
                }
                Ok(result)
            }
            _ => Ok(Vec::new()),
        }
    }

    fn extract_dict(&self, key: &str) -> PyResult<Bound<'py, PyDict>> {
        let item = self
            .get_item(key)?
            .ok_or_else(|| py_value_err(format!("missing required key: {key}")))?;
        item.cast_into::<PyDict>()
            .map_err(|e| py_value_err(format!("key '{key}' is not a dict: {e}")))
    }

    fn extract_opt_dict(&self, key: &str) -> PyResult<Option<Bound<'py, PyDict>>> {
        match self.get_item(key)? {
            Some(val) if !val.is_none() => {
                let d: Bound<'_, PyDict> = val.cast_into::<PyDict>().map_err(|e| {
                    py_value_err(format!("key '{key}' is not a dict: {e}"))
                })?;
                Ok(Some(d.clone()))
            }
            _ => Ok(None),
        }
    }
}

// ---------------------------------------------------------------------------
// Standalone extraction functions (convenience, for non-trait usage)
// ---------------------------------------------------------------------------

pub fn extract_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    DictExtract::extract_str(dict, key)
}

pub fn extract_opt_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    DictExtract::extract_opt_str(dict, key)
}

pub fn extract_f64(dict: &Bound<'_, PyDict>, key: &str, default: f64) -> PyResult<f64> {
    DictExtract::extract_f64(dict, key, default)
}

pub fn extract_opt_f64(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<f64>> {
    DictExtract::extract_opt_f64(dict, key)
}

pub fn extract_opt_bool(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<bool>> {
    DictExtract::extract_opt_bool(dict, key)
}

pub fn extract_str_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    DictExtract::extract_str_list(dict, key)
}

pub fn extract_dict_list<'py>(
    dict: &Bound<'py, PyDict>,
    key: &str,
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    DictExtract::extract_dict_list(dict, key)
}
