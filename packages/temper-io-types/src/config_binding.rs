// config_board_binding: extract_config_refs, verify_config_matches_netlist.
//
// The original implementation walked an arbitrary Python object tree
// (`PyDict`/`PyTuple`/`PyList`) directly. That tree shape — nested
// dict/list/string — is exactly what `serde_json::Value` models, so the
// pure core here operates on `Value` instead: the pyo3 boundary converts
// the incoming Python object into a `Value` once, and everything after
// that (the recursive ref-collection walk, the missing-ref diff, the error
// message) is ordinary Rust with no Python dependency.

use serde_json::Value;
use std::collections::HashSet;

/// Config keys whose value is a single component reference designator.
pub fn is_single_ref_key(key: &str) -> bool {
    matches!(
        key,
        "component"
            | "component_ref"
            | "signal_component"
            | "target_component"
            | "hv_component"
            | "from_component"
            | "to_component"
    )
}

/// Config keys whose value is a list of component reference designators
/// (or a mapping keyed by them).
pub fn is_list_ref_key(key: &str) -> bool {
    matches!(key, "components" | "fixed_components")
}

fn collect_ref_container(value: &Value, refs: &mut HashSet<String>) {
    match value {
        Value::Object(map) => {
            for key in map.keys() {
                refs.insert(key.clone());
            }
        }
        Value::Array(items) => {
            for item in items {
                if let Value::String(s) = item {
                    refs.insert(s.clone());
                }
            }
        }
        _ => {}
    }
}

fn collect_config_refs(node: &Value, refs: &mut HashSet<String>) {
    match node {
        Value::Object(map) => {
            for (key, value) in map {
                if is_single_ref_key(key) {
                    if let Value::String(s) = value {
                        refs.insert(s.clone());
                    }
                } else if is_list_ref_key(key) {
                    collect_ref_container(value, refs);
                } else {
                    collect_config_refs(value, refs);
                }
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_config_refs(item, refs);
            }
        }
        _ => {}
    }
}

/// Collect every component reference designator a config mentions. Pure
/// core of `extract_config_refs`.
pub fn extract_config_refs(config: &Value) -> HashSet<String> {
    let mut refs = HashSet::new();
    collect_config_refs(config, &mut refs);
    refs
}

/// Refs the config names that are absent from `netlist_refs`, sorted.
/// Empty means the config matches the board.
pub fn missing_refs(config_refs: &HashSet<String>, netlist_refs: &HashSet<String>) -> Vec<String> {
    let mut missing: Vec<String> = config_refs
        .iter()
        .filter(|r| !netlist_refs.contains(*r))
        .cloned()
        .collect();
    missing.sort();
    missing
}

/// Build the `ConfigBoardMismatchError` message for a non-empty
/// `missing` list, matching the pre-Rust-port Python wording exactly.
pub fn format_mismatch_message(config_name: &str, missing: &[String]) -> String {
    let sample = missing
        .iter()
        .take(10)
        .map(|s| s.as_str())
        .collect::<Vec<_>>()
        .join(", ");
    let more = if missing.len() > 10 {
        format!(" (+{} more)", missing.len() - 10)
    } else {
        String::new()
    };
    format!(
        "Config '{}' references {} component ref(s) not present in the board netlist: {}{}. This config was likely authored for a different board.",
        config_name,
        missing.len(),
        sample,
        more
    )
}

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;
    use pyo3::create_exception;
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyList, PySet, PyTuple};

    create_exception!(
        temper_io_types,
        ConfigBoardMismatchError,
        pyo3::exceptions::PyValueError
    );

    /// Convert an arbitrary Python object into the `serde_json::Value`
    /// shape `extract_config_refs`'s pure core understands: dict -> object
    /// (errors if a key isn't a string, matching the old `key.extract::<String>()?`
    /// behaviour), tuple/list -> array, str -> string, everything else ->
    /// null (the pure walker only ever inspects containers and strings, so
    /// this is behaviourally identical to the old code silently skipping
    /// non-container/non-string values).
    fn py_to_value(value: &Bound<'_, PyAny>) -> PyResult<Value> {
        if let Ok(dict) = value.cast::<PyDict>() {
            let mut map = serde_json::Map::new();
            for (k, v) in dict {
                let key: String = k.extract()?;
                map.insert(key, py_to_value(&v)?);
            }
            return Ok(Value::Object(map));
        }
        if let Ok(tuple) = value.cast::<PyTuple>() {
            let mut arr = Vec::with_capacity(tuple.len());
            for item in tuple {
                arr.push(py_to_value(&item)?);
            }
            return Ok(Value::Array(arr));
        }
        if let Ok(list) = value.cast::<PyList>() {
            let mut arr = Vec::with_capacity(list.len());
            for item in list {
                arr.push(py_to_value(&item)?);
            }
            return Ok(Value::Array(arr));
        }
        if let Ok(s) = value.extract::<String>() {
            return Ok(Value::String(s));
        }
        Ok(Value::Null)
    }

    #[pyfunction]
    pub fn extract_config_refs(py: Python<'_>, config: Bound<'_, PyAny>) -> PyResult<Py<PySet>> {
        let value = py_to_value(&config)?;
        let refs = super::extract_config_refs(&value);
        Ok(PySet::new(py, refs.iter().map(|s| s.as_str()))?.unbind())
    }

    #[pyfunction]
    #[pyo3(signature = (config_refs, netlist_refs, *, config_name))]
    pub fn verify_config_matches_netlist(
        config_refs: Bound<'_, PyAny>,
        netlist_refs: Bound<'_, PyAny>,
        config_name: String,
    ) -> PyResult<()> {
        let mut board_refs: HashSet<String> = HashSet::new();
        for item in netlist_refs.try_iter()? {
            board_refs.insert(item?.extract::<String>()?);
        }

        let mut config_ref_set: HashSet<String> = HashSet::new();
        for item in config_refs.try_iter()? {
            config_ref_set.insert(item?.extract::<String>()?);
        }

        let missing = super::missing_refs(&config_ref_set, &board_refs);
        if missing.is_empty() {
            return Ok(());
        }

        let message = super::format_mismatch_message(&config_name, &missing);
        let err = ConfigBoardMismatchError::new_err(message);
        // Attach structured fields to the exception instance so callers can
        // inspect `missing_refs` / `config_name` directly, matching the
        // pre-Rust-port Python implementation's contract (and this module's
        // test suite).
        let py = config_refs.py();
        err.value(py).setattr("missing_refs", missing)?;
        err.value(py).setattr("config_name", config_name)?;
        Err(err)
    }
}

#[cfg(feature = "python")]
pub use py_bridge::{
    ConfigBoardMismatchError, extract_config_refs as extract_config_refs_py,
    verify_config_matches_netlist,
};

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use serde_json::json;

    #[cfg_attr(test, test)]
    fn single_ref_key_collects_string_value() {
        let config = json!({ "component": "R1" });
        let refs = extract_config_refs(&config);
        assert_eq!(refs, HashSet::from(["R1".to_string()]));
    }

    #[cfg_attr(test, test)]
    fn list_ref_key_collects_list_items() {
        let config = json!({ "components": ["R1", "R2"] });
        let refs = extract_config_refs(&config);
        assert_eq!(refs, HashSet::from(["R1".to_string(), "R2".to_string()]));
    }

    #[cfg_attr(test, test)]
    fn list_ref_key_collects_mapping_keys() {
        let config = json!({ "fixed_components": { "R1": [1.0, 2.0], "R2": [3.0, 4.0] } });
        let refs = extract_config_refs(&config);
        assert_eq!(refs, HashSet::from(["R1".to_string(), "R2".to_string()]));
    }

    #[cfg_attr(test, test)]
    fn nested_structure_is_traversed() {
        let config = json!({
            "groups": [
                { "hv_component": "Q1" },
                { "signal_component": "U2" },
            ]
        });
        let refs = extract_config_refs(&config);
        assert_eq!(refs, HashSet::from(["Q1".to_string(), "U2".to_string()]));
    }

    #[cfg_attr(test, test)]
    fn missing_refs_is_sorted_set_difference() {
        let config_refs = HashSet::from(["R1".to_string(), "R2".to_string(), "R3".to_string()]);
        let netlist_refs = HashSet::from(["R1".to_string()]);
        assert_eq!(
            missing_refs(&config_refs, &netlist_refs),
            vec!["R2".to_string(), "R3".to_string()]
        );
    }

    #[cfg_attr(test, test)]
    fn missing_refs_empty_when_subset() {
        let config_refs = HashSet::from(["R1".to_string()]);
        let netlist_refs = HashSet::from(["R1".to_string(), "R2".to_string()]);
        assert!(missing_refs(&config_refs, &netlist_refs).is_empty());
    }

    #[cfg_attr(test, test)]
    fn format_mismatch_message_truncates_sample() {
        let missing: Vec<String> = (0..12).map(|i| format!("R{i}")).collect();
        let msg = format_mismatch_message("fixture", &missing);
        assert!(msg.contains("12 component ref(s)"));
        assert!(msg.contains("(+2 more)"));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("config_binding::tests::single_ref_key_collects_string_value", single_ref_key_collects_string_value),
        ("config_binding::tests::list_ref_key_collects_list_items", list_ref_key_collects_list_items),
        ("config_binding::tests::list_ref_key_collects_mapping_keys", list_ref_key_collects_mapping_keys),
        ("config_binding::tests::nested_structure_is_traversed", nested_structure_is_traversed),
        ("config_binding::tests::missing_refs_is_sorted_set_difference", missing_refs_is_sorted_set_difference),
        ("config_binding::tests::missing_refs_empty_when_subset", missing_refs_empty_when_subset),
        ("config_binding::tests::format_mismatch_message_truncates_sample", format_mismatch_message_truncates_sample),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
