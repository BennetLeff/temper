use pyo3::prelude::*;
use regex::Regex;
use std::sync::LazyLock;

static NON_SEMANTIC_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"^;exported-at:").unwrap(),
        Regex::new(r"^;tool-version:").unwrap(),
        Regex::new(r"^;machine:").unwrap(),
        Regex::new(r"^;path:").unwrap(),
    ]
});

fn pyerr(msg: impl std::fmt::Display) -> PyErr {
    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(msg.to_string())
}

/// Strip non-semantic comment lines and normalise whitespace in DSN text.
#[pyfunction]
fn normalize_dsn(dsn_text: &str) -> PyResult<String> {
    let patterns = &*NON_SEMANTIC_PATTERNS;
    let mut filtered: Vec<&str> = dsn_text
        .lines()
        .filter(|line| !patterns.iter().any(|p| p.is_match(line)))
        .map(|line| line.trim_end())
        .collect();
    while filtered.last() == Some(&"") {
        filtered.pop();
    }
    filtered.push("");
    Ok(filtered.join("\n"))
}

/// Return true if the DSN text has already been normalised.
#[pyfunction]
fn is_dsn_normalized(dsn_text: &str) -> PyResult<bool> {
    let patterns = &*NON_SEMANTIC_PATTERNS;
    for line in dsn_text.lines() {
        if patterns.iter().any(|p| p.is_match(line)) {
            return Ok(false);
        }
    }
    if !dsn_text.ends_with('\n') {
        return Ok(false);
    }
    if dsn_text.ends_with("\n\n") {
        return Ok(false);
    }
    Ok(dsn_text.chars().all(|ch| ch as u32 >= 32 || ch == '\n' || ch == '\r' || ch == '\t'))
}

/// Strip ASCII control characters from DSN text, keeping newlines and tabs.
#[pyfunction]
fn strip_control_chars(dsn_text: &str) -> PyResult<String> {
    Ok(dsn_text
        .chars()
        .filter(|&ch| ch == '\n' || ch == '\t' || ch as u32 >= 0x20)
        .collect())
}

/// A pyo3 module exposing DSN utility functions.
#[pymodule]
fn temper_dsn(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(normalize_dsn, m)?)?;
    m.add_function(wrap_pyfunction!(is_dsn_normalized, m)?)?;
    m.add_function(wrap_pyfunction!(strip_control_chars, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_strips_non_semantic() {
        let input = ";exported-at: 2024\ndata line 1\n;tool-version: 1.0\ndata line 2\n";
        let result = normalize_dsn(input).unwrap();
        assert_eq!(result, "data line 1\ndata line 2\n");
    }

    #[test]
    fn test_normalize_trailing_newline() {
        let input = "line1\nline2\n\n\n";
        let result = normalize_dsn(input).unwrap();
        assert_eq!(result, "line1\nline2\n");
    }

    #[test]
    fn test_is_normalized_true() {
        assert!(is_dsn_normalized("clean data\n").unwrap());
    }

    #[test]
    fn test_is_normalized_false_non_semantic() {
        assert!(!is_dsn_normalized(";exported-at: now\ndata\n").unwrap());
    }

    #[test]
    fn test_is_normalized_false_no_newline() {
        assert!(!is_dsn_normalized("no newline").unwrap());
    }

    #[test]
    fn test_is_normalized_false_double_newline() {
        assert!(!is_dsn_normalized("data\n\n").unwrap());
    }

    #[test]
    fn test_strip_control_chars() {
        let input = "hello\x00world\n";
        let result = strip_control_chars(input).unwrap();
        assert_eq!(result, "helloworld\n");
    }

    #[test]
    fn test_strip_control_chars_keeps_tabs() {
        let input = "col1\tcol2\n";
        let result = strip_control_chars(input).unwrap();
        assert_eq!(result, "col1\tcol2\n");
    }
}
