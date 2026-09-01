//! Shared Python attribute helpers for typed DRC marshalling.
//!
//! Migrated from `temper_placer/validation/drc_oracle.py` (Wave 4, marshalling
//! boundary fanout). The former dict-building bridge was superseded by the
//! typed constructors in `drc_marshal.rs` and had no production callers.
//!
//! The pydantic `PlacementConstraints` model stays Python (JUSTIFIED-KEEP);
//! only the shared attribute extraction helpers remain here for typed
//! marshalling and oracle-input construction.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// infer_package_type — footprint → package-type classification
// (verbatim port from the Python drc_oracle.py)
// ---------------------------------------------------------------------------

/// Infer SMD package type from footprint name.
///
/// This is already available as `temper_drc_rs.infer_package_type` (the
/// Phase 4 migration), but the dict builders need it internally and calling
/// back into the module from Rust is unnecessary indirection.  The body here
/// is the same keyword-first-match, case-insensitive substring search.
///
/// `pub(crate)` since Phase-A U5 (`drc_marshal.rs`) reuses it for the typed
/// `DrcBoardSnapshot` constructors.
pub(crate) fn infer_package_type(footprint: Option<&str>) -> &'static str {
    let fp_lower = footprint.unwrap_or("").to_lowercase();
    let fp = fp_lower.as_str();
    if fp.contains("tht") || fp.contains("through") || fp.contains("pin") || fp.contains("dip") {
        return "tht";
    }
    if fp.contains("to-247") || fp.contains("to247") {
        return "to247";
    }
    if fp.contains("to-220") || fp.contains("to220") {
        return "to220";
    }
    if fp.contains("bga") {
        return "bga";
    }
    if fp.contains("qfn") {
        return "qfn";
    }
    if fp.contains("qfp") || fp.contains("tqfp") {
        return "qfp";
    }
    if fp.contains("dpak") || fp.contains("d2pak") {
        return "dpak";
    }
    "smd"
}

// ---------------------------------------------------------------------------
// Helpers: extract Python object attributes
// ---------------------------------------------------------------------------

/// Get a required float attribute from a Python object.
pub(crate) fn get_attr_f64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<f64> {
    obj.getattr(name)?
        .extract::<f64>()
        .map_err(|e| PyValueError::new_err(format!(".{name} is not a float: {e}")))
}

/// Get an optional float attribute (None if absent or None).
pub(crate) fn get_attr_opt_f64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<f64>> {
    match obj.getattr(name) {
        Ok(val) if !val.is_none() => {
            let v: f64 = val.extract().map_err(|e| {
                PyValueError::new_err(format!(".{name} is not a float: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

/// Get a required string attribute.
pub(crate) fn get_attr_str(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    obj.getattr(name)?
        .extract::<String>()
        .map_err(|e| PyValueError::new_err(format!(".{name} is not a string: {e}")))
}

/// Get an optional string attribute.
pub(crate) fn get_attr_opt_str(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<String>> {
    match obj.getattr(name) {
        Ok(val) if !val.is_none() => {
            let v: String = val.extract().map_err(|e| {
                PyValueError::new_err(format!(".{name} is not a string: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

/// Get an optional int attribute.
pub(crate) fn get_attr_opt_i64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<i64>> {
    match obj.getattr(name) {
        Ok(val) if !val.is_none() => {
            let v: i64 = val.extract().map_err(|e| {
                PyValueError::new_err(format!(".{name} is not an int: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

// ---------------------------------------------------------------------------
// Rust unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn infer_package_type_basics() {
        assert_eq!(infer_package_type(Some("Resistor_SMD:R_0603")), "smd");
        assert_eq!(infer_package_type(None), "smd");
        assert_eq!(infer_package_type(Some("")), "smd");
        assert_eq!(infer_package_type(Some("TO-247")), "to247");
        assert_eq!(infer_package_type(Some("BGA-100")), "bga");
        assert_eq!(infer_package_type(Some("QFN-32")), "qfn");
        assert_eq!(infer_package_type(Some("TQFP-64")), "qfp");
        assert_eq!(infer_package_type(Some("DPAK")), "dpak");
        assert_eq!(infer_package_type(Some("THT_HEADER")), "tht");
        // precedence: tht beats to-247
        assert_eq!(infer_package_type(Some("TO-247-THT")), "tht");
        // first-match: qfn beats dpak
        assert_eq!(infer_package_type(Some("QFN_DPAK")), "qfn");
        // case insensitivity
        assert_eq!(infer_package_type(Some("TqFp")), "qfp");
    }
}
