use thiserror::Error;

/// A single validation diagnostic produced during bundle assembly.
///
/// Contains a machine-readable `code`, a human-readable `message`,
/// and a list of `references` (component or net names) that triggered the issue.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct Diagnostic {
    pub code: String,
    pub message: String,
    pub references: Vec<String>,
}

/// Errors that can occur during design bundle assembly and validation.
#[derive(Debug, Error)]
pub enum DesignBundleError {
    /// One or more validation diagnostics were produced.
    #[error("design bundle validation failed: {0:?}")]
    Validation(Vec<Diagnostic>),
    /// An input document (atopile, netlist, PCL) could not be parsed.
    #[error("invalid document: {0}")]
    Document(String),
    /// The assembled bundle could not be serialized.
    #[error("serialization failed: {0}")]
    Serialization(String),
}

/// Construct a [`DesignBundleError::Validation`] from a code, message, and references.
pub fn diagnostic(
    code: &str,
    message: impl Into<String>,
    references: Vec<String>,
) -> DesignBundleError {
    DesignBundleError::Validation(vec![Diagnostic {
        code: code.into(),
        message: message.into(),
        references,
    }])
}
