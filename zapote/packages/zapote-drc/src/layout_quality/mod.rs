//! Advisory layout metrics, with explicit units and model boundaries.
//!
//! These kernels compare candidate layouts; they do not certify a board. Field
//! extraction, operating envelopes and native-object identity belong to callers.
//! Malformed or non-finite inputs are errors, never zero-valued improvements.
#![deny(missing_docs)]

pub mod assembly;
pub mod capacitance;
pub mod copper;
pub mod coupling;
pub mod decoupling;
pub mod report;
pub mod returns;
pub mod thermal;

use std::collections::BTreeSet;

/// An invalid input or numerically unrepresentable result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Error {}

pub(crate) fn ensure(condition: bool, message: &str) -> Result<(), Error> {
    if condition {
        Ok(())
    } else {
        Err(Error(message.into()))
    }
}
pub(crate) fn finite(value: f64, field: &str) -> Result<f64, Error> {
    if !value.is_finite() {
        return Err(Error(format!("{field} must be finite")));
    }
    Ok(value)
}
pub(crate) fn nonnegative(value: f64, field: &str) -> Result<f64, Error> {
    finite(value, field)?;
    if value < 0.0 {
        return Err(Error(format!("{field} must be nonnegative")));
    }
    Ok(value)
}
pub(crate) fn positive(value: f64, field: &str) -> Result<f64, Error> {
    finite(value, field)?;
    if value <= 0.0 {
        return Err(Error(format!("{field} must be positive")));
    }
    Ok(value)
}
pub(crate) fn identities<'a>(ids: impl IntoIterator<Item = &'a str>) -> Result<(), Error> {
    let mut seen = BTreeSet::new();
    for id in ids {
        ensure(!id.trim().is_empty(), "object identity must not be blank")?;
        if !seen.insert(id) {
            return Err(Error(format!("duplicate object identity: {id}")));
        }
    }
    Ok(())
}
