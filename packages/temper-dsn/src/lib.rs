use pyo3::prelude::*;
use regex::Regex;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::LazyLock;

static NON_SEMANTIC_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"^;exported-at:").unwrap(),
        Regex::new(r"^;tool-version:").unwrap(),
        Regex::new(r"^;machine:").unwrap(),
        Regex::new(r"^;path:").unwrap(),
    ]
});

// ---------------------------------------------------------------------------
// DSN Normalizer
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// DSN Schema Hash
// ---------------------------------------------------------------------------

/// Compute a SHA-256 schema hash from layer/footprint/net info.
#[pyfunction]
fn compute_dsn_schema_hash(
    layer_names: Vec<String>,
    layer_types: HashMap<String, String>,
    footprints: HashMap<String, usize>,
    nets: Vec<String>,
) -> PyResult<String> {
    let mut schema = serde_json::Map::new();

    // Layers
    let mut names_sorted = layer_names.clone();
    names_sorted.sort();
    let mut types_map = serde_json::Map::new();
    for name in &names_sorted {
        let lt = layer_types.get(name).cloned().unwrap_or_else(|| "signal".into());
        types_map.insert(name.clone(), serde_json::Value::String(lt));
    }
    let mut layers_obj = serde_json::Map::new();
    layers_obj.insert("count".into(), serde_json::Value::Number(names_sorted.len().into()));
    layers_obj.insert("names".into(), serde_json::Value::Array(names_sorted.iter().cloned().map(serde_json::Value::String).collect()));
    layers_obj.insert("types".into(), serde_json::Value::Object(types_map));
    schema.insert("layers".into(), serde_json::Value::Object(layers_obj));

    // Footprints (sorted by name)
    let mut fp_sorted: Vec<_> = footprints.iter().collect();
    fp_sorted.sort_by_key(|(k, _)| *k);
    let mut fp_obj = serde_json::Map::new();
    for (name, count) in fp_sorted {
        fp_obj.insert(name.clone(), serde_json::Value::Number((*count).into()));
    }
    schema.insert("footprints".into(), serde_json::Value::Object(fp_obj));

    // Nets (sorted)
    let mut nets_sorted = nets.clone();
    nets_sorted.sort();
    schema.insert("nets".into(), serde_json::Value::Array(nets_sorted.into_iter().map(serde_json::Value::String).collect()));

    // Rules
    let mut rules = serde_json::Map::new();
    rules.insert("trace_width".into(), serde_json::Value::Number(13.into()));
    rules.insert("clearance".into(), serde_json::Value::Number(12.into()));
    schema.insert("rules".into(), serde_json::Value::Object(rules));

    let canonical = serde_json::to_string(&schema).unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    Ok(format!("{:x}", hasher.finalize()))
}

#[pyfunction]
fn embed_schema_header(dsn_text: &str, schema_hash: &str) -> PyResult<String> {
    let header = format!(";schema-version: sha256:{}", schema_hash);
    if let Some(nl_pos) = dsn_text.find('\n') {
        if dsn_text.starts_with(";schema-version:") {
            return Ok(format!("{}{}", header, &dsn_text[nl_pos..]));
        }
    }
    Ok(format!("{}\n{}", header, dsn_text))
}

#[pyfunction]
fn extract_schema_hash(dsn_text: &str) -> PyResult<Option<String>> {
    let prefix = ";schema-version: sha256:";
    for line in dsn_text.lines() {
        if let Some(hash) = line.strip_prefix(prefix) {
            return Ok(Some(hash.trim().to_string()));
        }
    }
    Ok(None)
}

#[pyfunction]
fn validate_dsn(dsn_text: &str, expected_hash: &str) -> PyResult<()> {
    let received = extract_schema_hash(dsn_text)?;
    if received.as_deref() != Some(expected_hash) {
        let msg = format!(
            "DSN schema version mismatch: expected sha256:{}, got sha256:{}. The upstream stage may have changed its output format.",
            expected_hash,
            received.as_deref().unwrap_or("MISSING"),
        );
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(msg));
    }
    Ok(())
}

#[pyfunction]
fn validate_or_warn_dsn(dsn_text: &str, expected_hash: &str) -> PyResult<bool> {
    let received = extract_schema_hash(dsn_text)?;
    Ok(received.as_deref() == Some(expected_hash))
}

/// A pyo3 module exposing DSN utility functions.
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
