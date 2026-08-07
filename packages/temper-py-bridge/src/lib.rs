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

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    use pyo3::types::{PyDict, PyList};
    use std::sync::Once;

    static PYTHON_INIT: Once = Once::new();

    /// Ensure the Python interpreter is initialized (once per process).
    /// Must be called before any test that uses `Python::attach` or pyo3
    /// APIs that require the interpreter.
    fn ensure_python_init() {
        PYTHON_INIT.call_once(|| {
            pyo3::Python::initialize();
        });
    }

    // ------------------------------------------------------------------
    // panic_to_err
    // ------------------------------------------------------------------

    #[test]
    fn panic_to_err_string_payload() {
        ensure_python_init();
        let err = panic_to_err(Box::new("static str payload".to_string()));
        let msg = err.to_string();
        assert!(msg.contains("static str payload"), "got: {msg}");
    }

    #[test]
    fn panic_to_err_str_ref_payload() {
        ensure_python_init();
        let s: &str = "borrowed str payload";
        let err = panic_to_err(Box::new(s));
        let msg = err.to_string();
        assert!(msg.contains("borrowed str payload"), "got: {msg}");
    }

    #[test]
    fn panic_to_err_unknown_payload() {
        ensure_python_init();
        let err = panic_to_err(Box::new(42u32));
        let msg = err.to_string();
        assert!(msg.contains("unknown panic"), "got: {msg}");
    }

    // ------------------------------------------------------------------
    // catch_unwind
    // ------------------------------------------------------------------

    #[test]
    fn catch_unwind_success() {
        let result = catch_unwind(|| 42);
        match result {
            Ok(v) => assert_eq!(v, 42),
            Err(_) => panic!("expected Ok"),
        }
    }

    #[test]
    fn catch_unwind_panic_caught() {
        use std::panic::{self, AssertUnwindSafe};
        let result = panic::catch_unwind(AssertUnwindSafe(|| {
            panic!("boom");
        }));
        assert!(result.is_err());
    }

    // ------------------------------------------------------------------
    // catch_panic
    // ------------------------------------------------------------------

    #[test]
    fn catch_panic_success() {
        ensure_python_init();
        let result: PyResult<i32> = catch_panic(|| Ok(7));
        assert_eq!(result.unwrap(), 7);
    }

    #[test]
    fn catch_panic_propagates_error() {
        ensure_python_init();
        let result: PyResult<i32> = catch_panic(|| {
            Err(py_value_err("not good"))
        });
        let e = result.unwrap_err();
        let msg = e.to_string();
        assert!(msg.contains("not good"), "got: {msg}");
    }

    #[test]
    fn catch_panic_converts_panic() {
        ensure_python_init();
        let result: PyResult<()> = catch_panic(|| -> PyResult<()> {
            panic!("unexpected");
        });
        let e = result.unwrap_err();
        let msg = e.to_string();
        assert!(msg.contains("unexpected"), "got: {msg}");
    }

    // ------------------------------------------------------------------
    // py_runtime_err / py_value_err
    // ------------------------------------------------------------------

    #[test]
    fn py_runtime_err_contains_message() {
        ensure_python_init();
        let e = py_runtime_err("something broke");
        assert!(e.to_string().contains("something broke"));
    }

    #[test]
    fn py_value_err_contains_message() {
        ensure_python_init();
        let e = py_value_err("bad value");
        assert!(e.to_string().contains("bad value"));
    }

    // ------------------------------------------------------------------
    // DictExtract — basic extraction
    // ------------------------------------------------------------------

    fn make_test_dict<'py>(py: Python<'py>) -> Bound<'py, PyDict> {
        let d = PyDict::new(py);
        d.set_item("name", "Alice").unwrap();
        d.set_item("age", 30.0_f64).unwrap();
        d.set_item("active", true).unwrap();
        d.set_item("tags", vec!["rust", "pyo3"]).unwrap();
        d.set_item("empty_tags", PyList::empty(py)).unwrap();
        d
    }

    #[test]
    fn extract_str_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let name = d.extract_str("name").unwrap();
            assert_eq!(name, "Alice");
        });
    }

    #[test]
    fn extract_str_missing() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let err = d.extract_str("nope").unwrap_err();
            assert!(err.to_string().contains("nope"));
        });
    }

    #[test]
    fn extract_opt_str_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let name = d.extract_opt_str("name").unwrap();
            assert_eq!(name, Some("Alice".to_string()));
        });
    }

    #[test]
    fn extract_opt_str_missing() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let name = d.extract_opt_str("nope").unwrap();
            assert_eq!(name, None);
        });
    }

    #[test]
    fn extract_opt_str_none() {
        ensure_python_init();
        Python::attach(|py| {
            let d = PyDict::new(py);
            d.set_item("x", py.None()).unwrap();
            let v = d.extract_opt_str("x").unwrap();
            assert_eq!(v, None);
        });
    }

    #[test]
    fn extract_f64_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let age = d.extract_f64("age", 0.0).unwrap();
            assert!((age - 30.0).abs() < f64::EPSILON);
        });
    }

    #[test]
    fn extract_f64_missing_returns_default() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let v = d.extract_f64("nope", 99.0).unwrap();
            assert!((v - 99.0).abs() < f64::EPSILON);
        });
    }

    #[test]
    fn extract_f64_none_returns_default() {
        ensure_python_init();
        Python::attach(|py| {
            let d = PyDict::new(py);
            d.set_item("x", py.None()).unwrap();
            let v = d.extract_f64("x", 42.0).unwrap();
            assert!((v - 42.0).abs() < f64::EPSILON);
        });
    }

    #[test]
    fn extract_f64_required_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let age = d.extract_f64_required("age").unwrap();
            assert!((age - 30.0).abs() < f64::EPSILON);
        });
    }

    #[test]
    fn extract_f64_required_missing() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let err = d.extract_f64_required("nope").unwrap_err();
            assert!(err.to_string().contains("nope"));
        });
    }

    #[test]
    fn extract_opt_f64_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let v: Option<f64> = d.extract_opt_f64("age").unwrap();
            assert!(v.is_some());
            assert!((v.unwrap() - 30.0).abs() < f64::EPSILON);
        });
    }

    #[test]
    fn extract_opt_f64_missing() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let v: Option<f64> = d.extract_opt_f64("nope").unwrap();
            assert_eq!(v, None);
        });
    }

    #[test]
    fn extract_bool_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            assert!(d.extract_bool("active").unwrap());
        });
    }

    #[test]
    fn extract_opt_bool_none() {
        ensure_python_init();
        Python::attach(|py| {
            let d = PyDict::new(py);
            d.set_item("x", py.None()).unwrap();
            let v = d.extract_opt_bool("x").unwrap();
            assert_eq!(v, None);
        });
    }

    #[test]
    fn extract_bool_default_missing() {
        ensure_python_init();
        Python::attach(|py| {
            let d = PyDict::new(py);
            let v = d.extract_bool_default("nope", true).unwrap();
            assert!(v);
        });
    }

    #[test]
    fn extract_str_list_present() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let tags = d.extract_str_list("tags").unwrap();
            assert_eq!(tags, vec!["rust", "pyo3"]);
        });
    }

    #[test]
    fn extract_str_list_missing_returns_empty() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let tags = d.extract_str_list("nope").unwrap();
            assert!(tags.is_empty());
        });
    }

    #[test]
    fn extract_str_list_empty_list() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            let tags = d.extract_str_list("empty_tags").unwrap();
            assert!(tags.is_empty());
        });
    }

    #[test]
    fn extract_dict_present() {
        ensure_python_init();
        Python::attach(|py| {
            let outer = PyDict::new(py);
            let inner = PyDict::new(py);
            inner.set_item("k", "v").unwrap();
            outer.set_item("inner", inner).unwrap();
            let extracted = outer.extract_dict("inner").unwrap();
            let v: String = extracted.get_item("k").unwrap().unwrap().extract().unwrap();
            assert_eq!(v, "v");
        });
    }

    #[test]
    fn extract_dict_missing() {
        ensure_python_init();
        Python::attach(|py| {
            let d = PyDict::new(py);
            let err = d.extract_dict("nope").unwrap_err();
            assert!(err.to_string().contains("nope"));
        });
    }

    #[test]
    fn extract_opt_dict_present() {
        ensure_python_init();
        Python::attach(|py| {
            let outer = PyDict::new(py);
            let inner = PyDict::new(py);
            inner.set_item("k", 1).unwrap();
            outer.set_item("inner", inner).unwrap();
            let opt = outer.extract_opt_dict("inner").unwrap();
            assert!(opt.is_some());
        });
    }

    #[test]
    fn extract_opt_dict_none_value() {
        ensure_python_init();
        Python::attach(|py| {
            let d = PyDict::new(py);
            d.set_item("x", py.None()).unwrap();
            let opt = d.extract_opt_dict("x").unwrap();
            assert!(opt.is_none());
        });
    }

    #[test]
    fn extract_dict_list_present() {
        ensure_python_init();
        Python::attach(|py| {
            let outer = PyDict::new(py);
            let items = PyList::empty(py);
            let d1 = PyDict::new(py);
            d1.set_item("a", 1).unwrap();
            items.append(d1).unwrap();
            outer.set_item("items", items).unwrap();
            let extracted = outer.extract_dict_list("items").unwrap();
            assert_eq!(extracted.len(), 1);
        });
    }

    // ------------------------------------------------------------------
    // Standalone functions (verify they delegate to DictExtract)
    // ------------------------------------------------------------------

    #[test]
    fn standalone_extractors_delegate() {
        ensure_python_init();
        Python::attach(|py| {
            let d = make_test_dict(py);
            assert_eq!(extract_str(&d, "name").unwrap(), "Alice");
            assert_eq!(
                extract_opt_str(&d, "name").unwrap(),
                Some("Alice".to_string())
            );
            assert!((extract_f64(&d, "age", 0.0).unwrap() - 30.0).abs() < f64::EPSILON);
            assert_eq!(extract_str_list(&d, "tags").unwrap(), vec!["rust", "pyo3"]);
        });
    }
}
