use thiserror::Error;

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct Diagnostic {
    pub code: String,
    pub message: String,
    pub references: Vec<String>,
}

#[derive(Debug, Error)]
pub enum DesignBundleError {
    #[error("design bundle validation failed: {0:?}")]
    Validation(Vec<Diagnostic>),
    #[error("invalid document: {0}")]
    Document(String),
    #[error("serialization failed: {0}")]
    Serialization(String),
}

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
