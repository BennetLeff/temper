//! Pure-Rust DSN (Specctra) format utilities.
//!
//! Tests live here.  The `#[pyfunction]` wrappers in `lib.rs` are thin adapters
//! over this module.

use regex::Regex;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::LazyLock;

/// Compiles a regex from a source literal. Infallible: every pattern passed
/// here is a compile-time constant in this file, so `Regex::new` cannot fail.
#[expect(clippy::expect_used, reason = "literal patterns compiled from source cannot fail")]
fn static_regex(pattern: &'static str) -> Regex {
    Regex::new(pattern).expect("invalid static regex literal")
}

static NON_SEMANTIC_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        static_regex(r"^;exported-at:"),
        static_regex(r"^;tool-version:"),
        static_regex(r"^;machine:"),
        static_regex(r"^;path:"),
    ]
});

/// Strip non-semantic metadata lines and normalize whitespace.
///
/// Removes lines matching `;exported-at:`, `;tool-version:`, etc.
/// Ensures exactly one trailing newline and no trailing blank lines.
pub fn normalize_dsn(dsn_text: &str) -> String {
    let patterns = &*NON_SEMANTIC_PATTERNS;
    let mut filtered: Vec<&str> = dsn_text
        .lines()
        .filter(|line| !patterns.iter().any(|p| p.is_match(line)))
        .map(str::trim_end)
        .collect();
    while filtered.last() == Some(&"") {
        filtered.pop();
    }
    filtered.push("");
    filtered.join("\n")
}

/// Check whether a DSN string is already normalized.
///
/// Returns `false` if any non-semantic metadata lines are present,
/// or if the trailing newline structure doesn't match the normalized form.
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

/// Remove ASCII control characters (except newline, tab) from DSN text.
pub fn strip_control_chars(dsn_text: &str) -> String {
    dsn_text
        .chars()
        .filter(|&ch| ch == '\n' || ch == '\t' || ch as u32 >= 0x20)
        .collect()
}

/// Compute a deterministic SHA-256 hash of the DSN schema.
///
/// The hash covers layer count/names/types, footprint counts, net names,
/// and default trace/clearance rules. Identical schemas produce identical hashes.
pub fn compute_dsn_schema_hash(
    layer_names: Vec<String>,
    layer_types: HashMap<String, String>,
    footprints: HashMap<String, usize>,
    nets: Vec<String>,
) -> String {
    let mut schema = serde_json::Map::new();

    let mut names_sorted = layer_names;
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

    let mut nets_sorted = nets;
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

/// Embed a schema-version header into DSN text.
///
/// Prepends `;schema-version: sha256:<hash>`. If a header already exists,
/// it is replaced in-place.
pub fn embed_schema_header(dsn_text: &str, schema_hash: &str) -> String {
    let header = format!(";schema-version: sha256:{}", schema_hash);
    if let Some(nl_pos) = dsn_text.find('\n')
        && dsn_text.starts_with(";schema-version:")
    {
        return format!("{}{}", header, &dsn_text[nl_pos..]);
    }
    format!("{}\n{}", header, dsn_text)
}

/// Extract the schema-version hash from a DSN header, if present.
pub fn extract_schema_hash(dsn_text: &str) -> Option<String> {
    let prefix = ";schema-version: sha256:";
    for line in dsn_text.lines() {
        if let Some(hash) = line.strip_prefix(prefix) {
            return Some(hash.trim().to_string());
        }
    }
    None
}

/// Validation error produced by [`validate_dsn`].
#[derive(Debug, PartialEq, Eq)]
pub enum DsnValidationError {
    /// The extracted schema hash does not match the expected hash.
    HashMismatch {
        /// The hash that was expected.
        expected: String,
        /// The hash actually found in the DSN text.
        received: String,
    },
}

/// Validate DSN text against an expected schema hash.
///
/// Returns [`DsnValidationError::HashMismatch`] if the embedded hash
/// doesn't match `expected_hash` or is missing.
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

/// Validate DSN without panicking — returns `true` on match.
pub fn validate_or_warn_dsn(dsn_text: &str, expected_hash: &str) -> bool {
    let received = extract_schema_hash(dsn_text);
    received.as_deref() == Some(expected_hash)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn test_normalize_strips_non_semantic() {
        let input = ";exported-at: 2024\ndata line 1\n;tool-version: 1.0\ndata line 2\n";
        let result = normalize_dsn(input);
        assert_eq!(result, "data line 1\ndata line 2\n");
    }

    #[cfg_attr(test, test)]
    fn test_normalize_trailing_newline() {
        let input = "line1\nline2\n\n\n";
        let result = normalize_dsn(input);
        assert_eq!(result, "line1\nline2\n");
    }

    #[cfg_attr(test, test)]
    fn test_is_normalized_true() {
        assert!(is_dsn_normalized("clean data\n"));
    }

    #[cfg_attr(test, test)]
    fn test_is_normalized_false_non_semantic() {
        assert!(!is_dsn_normalized(";exported-at: now\ndata\n"));
    }

    #[cfg_attr(test, test)]
    fn test_is_normalized_false_no_newline() {
        assert!(!is_dsn_normalized("no newline"));
    }

    #[cfg_attr(test, test)]
    fn test_is_normalized_false_double_newline() {
        assert!(!is_dsn_normalized("data\n\n"));
    }

    #[cfg_attr(test, test)]
    fn test_strip_control_chars() {
        let input = "hello\x00world\n";
        let result = strip_control_chars(input);
        assert_eq!(result, "helloworld\n");
    }

    #[cfg_attr(test, test)]
    fn test_strip_control_chars_keeps_tabs() {
        let input = "col1\tcol2\n";
        let result = strip_control_chars(input);
        assert_eq!(result, "col1\tcol2\n");
    }

    #[cfg_attr(test, test)]
    fn normalize_dsn_strips_crlf() {
        let input = "line1\r\n;exported-at: 2024\r\nline2\r\n";
        let result = normalize_dsn(input);
        assert_eq!(result, "line1\nline2\n");
    }

    // ---------- deterministic: compute_dsn_schema_hash ----------------------

    #[cfg_attr(test, test)]
    fn schema_hash_is_deterministic() {
        let h1 = compute_dsn_schema_hash(
            vec!["F.Cu".into(), "B.Cu".into()],
            std::collections::HashMap::new(),
            std::collections::HashMap::new(),
            vec!["GND".into(), "VCC".into()],
        );
        let h2 = compute_dsn_schema_hash(
            vec!["F.Cu".into(), "B.Cu".into()],
            std::collections::HashMap::new(),
            std::collections::HashMap::new(),
            vec!["VCC".into(), "GND".into()],  // different net order
        );
        assert_eq!(h1, h2, "schema hash depends on net order");
    }

    #[cfg_attr(test, test)]
    fn schema_hash_distinguishes_layer_counts() {
        let h2 = compute_dsn_schema_hash(
            vec!["F.Cu".into(), "B.Cu".into()],
            std::collections::HashMap::new(),
            std::collections::HashMap::new(),
            vec![],
        );
        let h4 = compute_dsn_schema_hash(
            vec!["F.Cu".into(), "B.Cu".into(), "In1.Cu".into(), "In2.Cu".into()],
            std::collections::HashMap::new(),
            std::collections::HashMap::new(),
            vec![],
        );
        assert_ne!(h2, h4, "schema hash should distinguish 2 vs 4 layers");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("dsn::tests::test_normalize_strips_non_semantic", test_normalize_strips_non_semantic),
        ("dsn::tests::test_normalize_trailing_newline", test_normalize_trailing_newline),
        ("dsn::tests::test_is_normalized_true", test_is_normalized_true),
        ("dsn::tests::test_is_normalized_false_non_semantic", test_is_normalized_false_non_semantic),
        ("dsn::tests::test_is_normalized_false_no_newline", test_is_normalized_false_no_newline),
        ("dsn::tests::test_is_normalized_false_double_newline", test_is_normalized_false_double_newline),
        ("dsn::tests::test_strip_control_chars", test_strip_control_chars),
        ("dsn::tests::test_strip_control_chars_keeps_tabs", test_strip_control_chars_keeps_tabs),
        ("dsn::tests::normalize_dsn_strips_crlf", normalize_dsn_strips_crlf),
        ("dsn::tests::schema_hash_is_deterministic", schema_hash_is_deterministic),
        ("dsn::tests::schema_hash_distinguishes_layer_counts", schema_hash_distinguishes_layer_counts),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
// A sibling module rather than `#[test] fn`s mixed into `tests` above, matching
// `pyfmt.rs`, `stackup_validator.rs`, `placer_core/units.rs` and
// `placer_core/placer_compute.rs`.  `proptest` is a dev-dependency, so it is
// absent from the ordinary (non-test) build the `wasm32` registry compiles
// into; keeping these apart is what lets the deterministic tests above join
// the tier instead of being excluded alongside them.
#[cfg(test)]
mod proptests {
    use super::*;

    // ---------- proptest: normalize_dsn -------------------------------------

    #[test]
    fn normalize_dsn_is_idempotent() {
        use proptest::prelude::*;
        let line = "[a-zA-Z0-9 _,.;:()\\-]{0,40}";
        proptest!(|(lines in proptest::collection::vec(line, 0..10))| {
            let input = lines.join("\n") + "\n\n\n";
            let once = normalize_dsn(&input);
            let twice = normalize_dsn(&once);
            prop_assert_eq!(once, twice, "normalize_dsn is not idempotent");
        });
    }

    #[test]
    fn normalize_dsn_preserves_data_lines() {
        use proptest::prelude::*;
        let line = "[a-zA-Z0-9]{1,20}";
        proptest!(|(lines in proptest::collection::vec(line, 1..10))| {
            let input = format!(";exported-at: today\n{}\n;tool-version: x\n", lines.join("\n"));
            let output = normalize_dsn(&input);
            for l in &lines {
                prop_assert!(output.contains(l.as_str()),
                    "normalize_dsn lost line '{}'", l);
            }
        });
    }

    // ---------- proptest: strip_control_chars -------------------------------

    #[test]
    fn strip_control_chars_is_dsn_normalized_result() {
        use proptest::prelude::*;
        let any_char = proptest::char::any();
        proptest!(|(ch in any_char)| {
            let input = format!("x{ch}y\n");
            let stripped = strip_control_chars(&input);
            // After stripping, the result should contain only valid chars
            // (printable + tab + newline).
            for c in stripped.chars() {
                prop_assert!(
                    c == '\n' || c == '\t' || c as u32 >= 0x20,
                    "strip_control_chars left control char U+{:04X}", c as u32
                );
            }
        });
    }

    // ---------- proptest: is_dsn_normalized ---------------------------------

    #[test]
    fn normalize_dsn_produces_is_normalized_true() {
        use proptest::prelude::*;
        let line = "[a-zA-Z0-9]{1,40}";
        proptest!(|(lines in proptest::collection::vec(line, 1..10))| {
            let input = format!(";exported-at: now\n{}\n;path: /x\n\n", lines.join("\n"));
            let normalized = normalize_dsn(&input);
            prop_assert!(is_dsn_normalized(&normalized),
                "normalize_dsn output is not is_dsn_normalized: {:?}", normalized);
        });
    }
}
