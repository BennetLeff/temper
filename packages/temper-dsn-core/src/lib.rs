//! Pure-Rust DSN (Specctra) format utilities — core logic extracted from temper-dsn.
//!
//! Tests live here.  The pyo3 wrappers in `temper-dsn` are thin adapters.

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

pub fn normalize_dsn(dsn_text: &str) -> String {
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
    filtered.join("\n")
}

pub fn is_dsn_normalized(dsn_text: &str) -> bool {
    let patterns = &*NON_SEMANTIC_PATTERNS;
    for line in dsn_text.lines() {
        if patterns.iter().any(|p| p.is_match(line)) {
            return false;
        }
    }
    if !dsn_text.ends_with('\n') {
        return false;
    }
    if dsn_text.ends_with("\n\n") {
        return false;
    }
    dsn_text.chars().all(|ch| ch as u32 >= 32 || ch == '\n' || ch == '\r' || ch == '\t')
}

pub fn strip_control_chars(dsn_text: &str) -> String {
    dsn_text
        .chars()
        .filter(|&ch| ch == '\n' || ch == '\t' || ch as u32 >= 0x20)
        .collect()
}

pub fn compute_dsn_schema_hash(
    layer_names: Vec<String>,
    layer_types: HashMap<String, String>,
    footprints: HashMap<String, usize>,
    nets: Vec<String>,
) -> String {
    let mut schema = serde_json::Map::new();

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

    let mut fp_sorted: Vec<_> = footprints.iter().collect();
    fp_sorted.sort_by_key(|(k, _)| *k);
    let mut fp_obj = serde_json::Map::new();
    for (name, count) in fp_sorted {
        fp_obj.insert(name.clone(), serde_json::Value::Number((*count).into()));
    }
    schema.insert("footprints".into(), serde_json::Value::Object(fp_obj));

    let mut nets_sorted = nets.clone();
    nets_sorted.sort();
    schema.insert("nets".into(), serde_json::Value::Array(nets_sorted.into_iter().map(serde_json::Value::String).collect()));

    let mut rules = serde_json::Map::new();
    rules.insert("trace_width".into(), serde_json::Value::Number(13.into()));
    rules.insert("clearance".into(), serde_json::Value::Number(12.into()));
    schema.insert("rules".into(), serde_json::Value::Object(rules));

    let canonical = serde_json::to_string(&schema).unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    format!("{:x}", hasher.finalize())
}

pub fn embed_schema_header(dsn_text: &str, schema_hash: &str) -> String {
    let header = format!(";schema-version: sha256:{}", schema_hash);
    if let Some(nl_pos) = dsn_text.find('\n') {
        if dsn_text.starts_with(";schema-version:") {
            return format!("{}{}", header, &dsn_text[nl_pos..]);
        }
    }
    format!("{}\n{}", header, dsn_text)
}

pub fn extract_schema_hash(dsn_text: &str) -> Option<String> {
    let prefix = ";schema-version: sha256:";
    for line in dsn_text.lines() {
        if let Some(hash) = line.strip_prefix(prefix) {
            return Some(hash.trim().to_string());
        }
    }
    None
}

#[derive(Debug, PartialEq)]
pub enum DsnValidationError {
    HashMismatch { expected: String, received: String },
}

pub fn validate_dsn(dsn_text: &str, expected_hash: &str) -> Result<(), DsnValidationError> {
    let received = extract_schema_hash(dsn_text);
    if received.as_deref() != Some(expected_hash) {
        return Err(DsnValidationError::HashMismatch {
            expected: expected_hash.into(),
            received: received.unwrap_or_else(|| "MISSING".into()),
        });
    }
    Ok(())
}

pub fn validate_or_warn_dsn(dsn_text: &str, expected_hash: &str) -> bool {
    let received = extract_schema_hash(dsn_text);
    received.as_deref() == Some(expected_hash)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_strips_non_semantic() {
        let input = ";exported-at: 2024\ndata line 1\n;tool-version: 1.0\ndata line 2\n";
        let result = normalize_dsn(input);
        assert_eq!(result, "data line 1\ndata line 2\n");
    }

    #[test]
    fn test_normalize_trailing_newline() {
        let input = "line1\nline2\n\n\n";
        let result = normalize_dsn(input);
        assert_eq!(result, "line1\nline2\n");
    }

    #[test]
    fn test_is_normalized_true() {
        assert!(is_dsn_normalized("clean data\n"));
    }

    #[test]
    fn test_is_normalized_false_non_semantic() {
        assert!(!is_dsn_normalized(";exported-at: now\ndata\n"));
    }

    #[test]
    fn test_is_normalized_false_no_newline() {
        assert!(!is_dsn_normalized("no newline"));
    }

    #[test]
    fn test_is_normalized_false_double_newline() {
        assert!(!is_dsn_normalized("data\n\n"));
    }

    #[test]
    fn test_strip_control_chars() {
        let input = "hello\x00world\n";
        let result = strip_control_chars(input);
        assert_eq!(result, "helloworld\n");
    }

    #[test]
    fn test_strip_control_chars_keeps_tabs() {
        let input = "col1\tcol2\n";
        let result = strip_control_chars(input);
        assert_eq!(result, "col1\tcol2\n");
    }
}
