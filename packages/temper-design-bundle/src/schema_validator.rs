//! Wave 4 Phase 4 — regression slice: metric schema validation kernel.
//!
//! The validation decision compute of
//! `temper_placer/regression/schema_validator.py` (pinned verbatim as the
//! oracle `_schema_validator_py_oracle.py`, commit `0a29f15e3`) migrated
//! into `temper-design-bundle`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `validate_schema` | `SchemaValidator.validate` — the two-pass check (unknown-field sweep, then min/max/zero_is_valid range checks) |
//!
//! Design boundaries (argued in-source; see
//! `packages/temper-design-bundle/VERIFICATION.md`):
//!
//! - YAML loading and the schema-shape checks in `SchemaValidator.__init__`
//!   stay Python (I/O + marshalling). The kernel operates on the parsed
//!   field table marshalled by the delegation module.
//! - The kernel returns a `(field, reason_code)` pair; the delegation module
//!   formats the exact message with Python `str()` on the ORIGINAL dict
//!   values. No-format `str(float)` is a Python library semantic (`1.0` vs
//!   `1`) — int-vs-float leaves are type-carried Python-side, while the
//!   numeric *decision* (`value < min` etc.) is identical for the exact f64
//!   conversions of the schema/values involved.
//! - Iteration is over the metric dict's insertion order (a `Vec`, not a
//!   `HashMap`) — the two-pass, first-violation-raises semantics are
//!   preserved exactly: pass 1 reports the first UNKNOWN field (before any
//!   range check), pass 2 reports the first out-of-range field.
//! - A schema field without a `zero_is_valid` key defaults to True (the
//!   oracle's `constraints.get("zero_is_valid", True)`), applied by the
//!   delegation module while marshalling.
//! - A field with neither min nor max is unconstrained (except
//!   `zero_is_valid`); `value == 0.0` matches Python's `value == 0` for the
//!   float values this schema validates.
//!
//! pyo3 panic policy: pyo3's default `catch_unwind` at the `#[pyfunction]`
//! boundary (R1g).

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyModule;

/// Validate a metrics dict against a schema field table. Returns
/// `(field, reason_code)` for the first violation, or `None` when every
/// metric satisfies its constraints. Reason codes: `unknown`, `below_min`,
/// `above_max`, `zero_invalid` (mapped to messages by the delegation module).
#[pyfunction]
fn validate_schema(
    metrics: Vec<(String, f64)>,
    schema: Vec<(String, Option<f64>, Option<f64>, bool)>,
) -> PyResult<Option<(String, String)>> {
    let lookup: HashMap<&str, (&Option<f64>, &Option<f64>, &bool)> = schema
        .iter()
        .map(|(name, min, max, ziv)| (name.as_str(), (min, max, ziv)))
        .collect();

    // Pass 1: every metric field must be declared (first unknown in
    // insertion order), BEFORE any range check.
    for (field, _) in &metrics {
        if !lookup.contains_key(field.as_str()) {
            return Ok(Some((field.clone(), "unknown".to_string())));
        }
    }

    // Pass 2: min/max/zero_is_valid range checks in insertion order.
    for (field, value) in &metrics {
        let Some((min, max, zero_is_valid)) = lookup.get(field.as_str()) else {
            // Unreachable after pass 1; fail closed rather than silently
            // skipping the field.
            return Err(PyValueError::new_err(
                "schema invariant violated: declared field missing from lookup",
            ));
        };
        if let Some(min) = min
            && *value < *min
        {
            return Ok(Some((field.clone(), "below_min".to_string())));
        }
        if let Some(max) = max
            && *value > *max
        {
            return Ok(Some((field.clone(), "above_max".to_string())));
        }
        if !**zero_is_valid && *value == 0.0 {
            return Ok(Some((field.clone(), "zero_invalid".to_string())));
        }
    }
    Ok(None)
}

/// Register the kernel on the `temper_design_bundle_python` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(validate_schema, m)?)?;
    Ok(())
}
